#!/usr/bin/python
#
#    This program  reads the angles from the acceleromteer, gyroscope
#    and mangnetometer on a BerryIMU connected to a Raspberry Pi.
#
#    This program includes two filters (low pass and median) to improve the
#    values returned from BerryIMU by reducing noise.
#
#    The BerryIMUv1, BerryIMUv2 and BerryIMUv3 are supported
#
#    This script is python 2.7 and 3 compatible
#
#    Feel free to do whatever you like with this code.
#    Distributed as-is; no warranty is given.
#
#    http://ozzmaker.com/



import sys
import time
import math
from .IMU import IMU
import datetime
import os
from threading import Thread
import struct

from config import MOUNT_POINT

RAD_TO_DEG = 57.29578
M_PI = 3.14159265358979323846
G_GAIN = 0.070          # [deg/s/LSB]  If you change the dps for gyro, you need to update this value accordingly
AA =  0.40              # Complementary filter constant
MAG_LPF_FACTOR = 0.4    # Low pass filter constant magnetometer
ACC_LPF_FACTOR = 0.4    # Low pass filter constant for accelerometer
ACC_MEDIANTABLESIZE = 9         # Median filter table size for accelerometer. Higher = smoother but a longer delay
MAG_MEDIANTABLESIZE = 9         # Median filter table size for magnetometer. Higher = smoother but a longer delay
SAMPLE_PERIOD_S = 0.01          # your sampling period -> 22 bytes per sample -> ~7.5MB per hour at 100Hz
FLUSH_INTERVAL_S = 60           # write to SD once per minute

class BerryImu(IMU):
    def __init__(self, capturing_lock = None):
        super().__init__()

        ################# Compass Calibration values ############
        self._magXmin = -786
        self._magYmin = -2984
        self._magZmin = 103
        self._magXmax = 1633
        self._magYmax = -905
        self._magZmax = 2731
        ############### END Calibration offsets #################

        #Kalman filter variables
        self._Q_angle = 0.02
        self._Q_gyro = 0.0015
        self._R_angle = 0.005
        self._y_bias = 0.0
        self._x_bias = 0.0
        self._XP_00 = 0.0
        self._XP_01 = 0.0
        self._XP_10 = 0.0
        self._XP_11 = 0.0
        self._YP_00 = 0.0
        self._YP_01 = 0.0
        self._YP_10 = 0.0
        self._YP_11 = 0.0
        self._KFangleX = 0.0
        self._KFangleY = 0.0
        self.buffer = bytearray()

        self._capturing_lock = capturing_lock

        now = datetime.datetime.now()
        self._startDate = now.strftime('%Y_%m_%d')
        self.complete_dir = os.path.join(MOUNT_POINT, self._startDate)
        self._dest = os.path.join(self.complete_dir, 'accelData.bin')
        if not os.path.isdir(self.complete_dir):
            os.makedirs(self.complete_dir)

        self.detectIMU()     #Detect if BerryIMU is connected.
        if(self._BerryIMUversion == 99):
            print("No BerryIMU found...")
            return
        self.initIMU()       #Initialise the accelerometer, gyroscope and compass

        self.mainThread = Thread(target=self.sample_raw_data, daemon=True)
        self.mainThread.start()

    def kalmanFilterY (self, accAngle, gyroRate, DT):
        y=0.0
        S=0.0

        self._KFangleY = self._KFangleY + DT * (gyroRate - self._y_bias)

        self._YP_00 = self._YP_00 + ( - DT * (self._YP_10 + self._YP_01) + self._Q_angle * DT )
        self._YP_01 = self._YP_01 + ( - DT * self._YP_11 )
        self._YP_10 = self._YP_10 + ( - DT * self._YP_11 )
        self._YP_11 = self._YP_11 + ( + self._Q_gyro * DT )

        y = accAngle - self._KFangleY
        S = self._YP_00 + self._R_angle
        K_0 = self._YP_00 / S
        K_1 = self._YP_10 / S

        self._KFangleY = self._KFangleY + ( K_0 * y )
        self._y_bias = self._y_bias + ( K_1 * y )

        self._YP_00 = self._YP_00 - ( K_0 * self._YP_00 )
        self._YP_01 = self._YP_01 - ( K_0 * self._YP_01 )
        self._YP_10 = self._YP_10 - ( K_1 * self._YP_00 )
        self._YP_11 = self._YP_11 - ( K_1 * self._YP_01 )

        return self._KFangleY

    def kalmanFilterX (self, accAngle, gyroRate, DT):
        x=0.0
        S=0.0

        self._KFangleX = self._KFangleX + DT * (gyroRate - self._x_bias)

        self._XP_00 = self._XP_00 + ( - DT * (self._XP_10 + self._XP_01) + self._Q_angle * DT )
        self._XP_01 = self._XP_01 + ( - DT * self._XP_11 )
        self._XP_10 = self._XP_10 + ( - DT * self._XP_11 )
        self._XP_11 = self._XP_11 + ( + self._Q_gyro * DT )

        x = accAngle - self._KFangleX
        S = self._XP_00 + self._R_angle
        K_0 = self._XP_00 / S
        K_1 = self._XP_10 / S

        self._KFangleX = self._KFangleX + ( K_0 * x )
        self._x_bias = self._x_bias + ( K_1 * x )

        self._XP_00 = self._XP_00 - ( K_0 * self._XP_00 )
        self._XP_01 = self._XP_01 - ( K_0 * self._XP_01 )
        self._XP_10 = self._XP_10 - ( K_1 * self._XP_00 )
        self._XP_11 = self._XP_11 - ( K_1 * self._XP_01 )

        return self._KFangleX
    
    def flush_buffer(self):
        """Write and fsync the RAM buffer to the SD, then clear it."""
        now = datetime.datetime.now()

        if self._startDate != now.strftime('%Y_%m_%d'):
            self._startDate = now.strftime('%Y_%m_%d')
        with self._capturing_lock:
            if os.path.ismount(MOUNT_POINT):
                self.complete_dir = os.path.join(MOUNT_POINT, self._startDate)
            else:
                # print("SSD not mounted, falling back to builtin storage GPS_IMU_Data for Accel data")
                self.complete_dir = os.path.join("/home/radxa/GPS_IMU_Data", self._startDate)
            self._dest = os.path.join(self.complete_dir, 'accelData.bin')

        # Big write (fewer metadata updates) + fsync for durability
        with open(self._dest, "ab", buffering=1024 * 1024) as f:
            f.write(self.buffer)
            f.flush()
            os.fsync(f.fileno())
        self.buffer.clear()

    def sample_raw_data(self):
        # Precompile struct for speed & clarity (little-endian; adjust if needed)
        # 9 x int16 + 1 x double
        rec = struct.Struct("<9hd")
        next_flush = time.time() + FLUSH_INTERVAL_S

        while True:
            #Read the accelerometer,gyroscope and magnetometer values
            try:
                ACCx = self.readACCx()
                ACCy = self.readACCy()
                ACCz = self.readACCz()
                GYRx = self.readGYRx()
                GYRy = self.readGYRy()
                GYRz = self.readGYRz()
                MAGx = self.readMAGx()
                MAGy = self.readMAGy()
                MAGz = self.readMAGz()

                # Pack directly into bytes and extend the RAM buffer
                now = datetime.datetime.now()
                self.buffer += rec.pack(
                    ACCx, ACCy, ACCz,
                    GYRx, GYRy, GYRz,
                    MAGx, MAGy, MAGz,
                    now.timestamp()
                )

                # Periodic flush
                t = time.time()
                if t >= next_flush:
                    self.flush_buffer()
                    # set the next flush time; avoid drift by stepping in 60s chunks
                    # in case loop ran late
                    while next_flush <= t:
                        next_flush += FLUSH_INTERVAL_S
            except Exception as ex:
                continue
            time.sleep(SAMPLE_PERIOD_S)

    def process(self):
        # not used anymore -> replaced with sample_raw_data
        gyroXangle = 0.0
        gyroYangle = 0.0
        gyroZangle = 0.0
        kalmanX = 0.0
        kalmanY = 0.0
        oldXMagRawValue = 0
        oldYMagRawValue = 0
        oldZMagRawValue = 0
        oldXAccRawValue = 0
        oldYAccRawValue = 0
        oldZAccRawValue = 0

        a = datetime.datetime.now()

        #Setup the tables for the mdeian filter. Fill them all with '1' so we dont get devide by zero error
        acc_medianTable1X = [1] * ACC_MEDIANTABLESIZE
        acc_medianTable1Y = [1] * ACC_MEDIANTABLESIZE
        acc_medianTable1Z = [1] * ACC_MEDIANTABLESIZE
        acc_medianTable2X = [1] * ACC_MEDIANTABLESIZE
        acc_medianTable2Y = [1] * ACC_MEDIANTABLESIZE
        acc_medianTable2Z = [1] * ACC_MEDIANTABLESIZE
        mag_medianTable1X = [1] * MAG_MEDIANTABLESIZE
        mag_medianTable1Y = [1] * MAG_MEDIANTABLESIZE
        mag_medianTable1Z = [1] * MAG_MEDIANTABLESIZE
        mag_medianTable2X = [1] * MAG_MEDIANTABLESIZE
        mag_medianTable2Y = [1] * MAG_MEDIANTABLESIZE
        mag_medianTable2Z = [1] * MAG_MEDIANTABLESIZE

        while True:
            #Read the accelerometer,gyroscope and magnetometer values
            ACCx = self.readACCx()
            ACCy = self.readACCy()
            ACCz = self.readACCz()
            GYRx = self.readGYRx()
            GYRy = self.readGYRy()
            GYRz = self.readGYRz()
            MAGx = self.readMAGx()
            MAGy = self.readMAGy()
            MAGz = self.readMAGz()
        

            #Apply compass calibration
            MAGx -= (self._magXmin + self._magXmax) /2
            MAGy -= (self._magYmin + self._magYmax) /2
            MAGz -= (self._magZmin + self._magZmax) /2

            #Swap axis directions to avoid gyro lock when PI is mounted vertically:
            # z = -y
            # y = z
            temp = ACCz
            ACCz = -1*ACCy
            ACCy = temp
            temp = GYRz
            GYRz = -1*GYRy
            GYRy = temp

            # Magnetometer axes are not in the same direction as the self axes
            # z = y
            # y = -z
            temp = MAGz
            MAGz = MAGy
            MAGy = -temp

            ##Calculate loop Period(LP). How long between Gyro Reads
            b = datetime.datetime.now() - a
            a = datetime.datetime.now()
            LP = b.microseconds / (1000000 * 1.0)
            outputString = "Loop Time %5.2f " % ( LP )

            ###############################################
            #### Apply low pass filter ####
            ###############################################
            MAGx =  MAGx  * MAG_LPF_FACTOR + oldXMagRawValue*(1 - MAG_LPF_FACTOR);
            MAGy =  MAGy  * MAG_LPF_FACTOR + oldYMagRawValue*(1 - MAG_LPF_FACTOR);
            MAGz =  MAGz  * MAG_LPF_FACTOR + oldZMagRawValue*(1 - MAG_LPF_FACTOR);
            ACCx =  ACCx  * ACC_LPF_FACTOR + oldXAccRawValue*(1 - ACC_LPF_FACTOR);
            ACCy =  ACCy  * ACC_LPF_FACTOR + oldYAccRawValue*(1 - ACC_LPF_FACTOR);
            ACCz =  ACCz  * ACC_LPF_FACTOR + oldZAccRawValue*(1 - ACC_LPF_FACTOR);

            oldXMagRawValue = MAGx
            oldYMagRawValue = MAGy
            oldZMagRawValue = MAGz
            oldXAccRawValue = ACCx
            oldYAccRawValue = ACCy
            oldZAccRawValue = ACCz

            #########################################
            #### Median filter for accelerometer ####
            #########################################
            # cycle the table
            for x in range (ACC_MEDIANTABLESIZE-1,0,-1 ):
                acc_medianTable1X[x] = acc_medianTable1X[x-1]
                acc_medianTable1Y[x] = acc_medianTable1Y[x-1]
                acc_medianTable1Z[x] = acc_medianTable1Z[x-1]

            # Insert the lates values
            acc_medianTable1X[0] = ACCx
            acc_medianTable1Y[0] = ACCy
            acc_medianTable1Z[0] = ACCz

            # Copy the tables
            acc_medianTable2X = acc_medianTable1X[:]
            acc_medianTable2Y = acc_medianTable1Y[:]
            acc_medianTable2Z = acc_medianTable1Z[:]

            # Sort table 2
            acc_medianTable2X.sort()
            acc_medianTable2Y.sort()
            acc_medianTable2Z.sort()

            # The middle value is the value we are interested in
            ACCx = acc_medianTable2X[int(ACC_MEDIANTABLESIZE/2)];
            ACCy = acc_medianTable2Y[int(ACC_MEDIANTABLESIZE/2)];
            ACCz = acc_medianTable2Z[int(ACC_MEDIANTABLESIZE/2)];

            #########################################
            #### Median filter for magnetometer ####
            #########################################
            # cycle the table
            for x in range (MAG_MEDIANTABLESIZE-1,0,-1 ):
                mag_medianTable1X[x] = mag_medianTable1X[x-1]
                mag_medianTable1Y[x] = mag_medianTable1Y[x-1]
                mag_medianTable1Z[x] = mag_medianTable1Z[x-1]

            # Insert the latest values
            mag_medianTable1X[0] = MAGx
            mag_medianTable1Y[0] = MAGy
            mag_medianTable1Z[0] = MAGz

            # Copy the tables
            mag_medianTable2X = mag_medianTable1X[:]
            mag_medianTable2Y = mag_medianTable1Y[:]
            mag_medianTable2Z = mag_medianTable1Z[:]

            # Sort table 2
            mag_medianTable2X.sort()
            mag_medianTable2Y.sort()
            mag_medianTable2Z.sort()

            # The middle value is the value we are interested in
            MAGx = mag_medianTable2X[int(MAG_MEDIANTABLESIZE/2)];
            MAGy = mag_medianTable2Y[int(MAG_MEDIANTABLESIZE/2)];
            MAGz = mag_medianTable2Z[int(MAG_MEDIANTABLESIZE/2)];

            #Convert Gyro raw to degrees per second
            rate_gyr_x =  GYRx * G_GAIN
            rate_gyr_y =  GYRy * G_GAIN
            rate_gyr_z =  GYRz * G_GAIN

            #Calculate the angles from the gyro.
            gyroXangle += rate_gyr_x * LP
            gyroYangle += rate_gyr_y * LP
            gyroZangle += rate_gyr_z * LP

            #Convert Accelerometer values to degrees
            AccXangle = (math.atan2(ACCy, ACCz) * RAD_TO_DEG)
            AccYangle = (math.atan2(ACCz, ACCx) + M_PI) * RAD_TO_DEG

            #Change the rotation value of the accelerometer to -/+ 180 and
            #move the Y axis '0' point to up.  This makes it easier to read.
            if AccYangle > 90:
                AccYangle -= 270.0
            else:
                AccYangle += 90.0

            #Complementary filter used to combine the accelerometer and gyro values.
            # CFangleX=AA*(CFangleX+rate_gyr_x*LP) +(1 - AA) * AccXangle
            # CFangleY=AA*(CFangleY+rate_gyr_y*LP) +(1 - AA) * AccYangle

            #Kalman filter used to combine the accelerometer and gyro values.
            kalmanY = self.kalmanFilterY(AccYangle, rate_gyr_y, LP)
            kalmanX = self.kalmanFilterX(AccXangle, rate_gyr_x, LP)

            #Calculate heading
            heading = 180 * math.atan2(MAGy,MAGx) / M_PI

            #Only have our heading between 0 and 360
            if heading < 0:
                heading += 360

            ####################################################################
            ###################Tilt compensated heading#########################
            ####################################################################
            #Normalize accelerometer raw values.
            numerator = math.sqrt(ACCx * ACCx + ACCy * ACCy + ACCz * ACCz)
            if numerator != 0:
                accXnorm = ACCx/numerator
                accYnorm = ACCy/numerator
            else:
                print("Cannot divide by zero")
                time.sleep(SAMPLE_PERIOD_S)
                continue

            #Calculate pitch and roll
            pitch = math.asin(accXnorm)
            roll = -math.asin(accYnorm/math.cos(pitch))

            #Calculate the new tilt compensated values
            #The compass and accelerometer are orientated differently on the the BerryIMUv1, v2 and v3.
            #This needs to be taken into consideration when performing the calculations

            #X compensation
            if(self._BerryIMUversion == 1 or self._BerryIMUversion == 3):            #LSM9DS0 and (LSM6DSL & LIS2MDL)
                magXcomp = MAGx*math.cos(pitch)+MAGz*math.sin(pitch)
            else:                                                                #LSM9DS1
                magXcomp = MAGx*math.cos(pitch)-MAGz*math.sin(pitch)

            #Y compensation
            if(self._BerryIMUversion == 1 or self._BerryIMUversion == 3):            #LSM9DS0 and (LSM6DSL & LIS2MDL)
                magYcomp = MAGx*math.sin(roll)*math.sin(pitch)+MAGy*math.cos(roll)-MAGz*math.sin(roll)*math.cos(pitch)
            else:                                                                #LSM9DS1
                magYcomp = MAGx*math.sin(roll)*math.sin(pitch)+MAGy*math.cos(roll)+MAGz*math.sin(roll)*math.cos(pitch)

            #Calculate tilt compensated heading
            tiltCompensatedHeading = 180 * math.atan2(magYcomp,magXcomp)/M_PI

            if tiltCompensatedHeading < 0:
                tiltCompensatedHeading += 360

            ##################### END Tilt Compensation ########################

            now = datetime.datetime.now()
            # Check if the time has been updated to write to the correct directory
            if self._startDate != now.strftime('%Y_%m_%d'):
                self._startDate = now.strftime('%Y_%m_%d')
                self.complete_dir = os.path.join(MOUNT_POINT, self._startDate)
                self._dest = os.path.join(self.complete_dir, 'accelData.csv')
            with self._capturing_lock:
                if os.path.ismount(MOUNT_POINT):
                    if not os.path.isdir(self.complete_dir):
                        os.makedirs(self.complete_dir)
                    with open(self._dest,"ta", buffering=8192) as f:
                        f.write(str(now.timestamp())+","+str(ACCx)+","+str(ACCy)+","+str(ACCz)+","+str(rate_gyr_x)+","+str(rate_gyr_y)+","+str(rate_gyr_z)+","+str(gyroXangle)+","+str(gyroYangle)+","+str(gyroZangle)+","+str(MAGx)+","+str(MAGy)+","+str(MAGz)+","+str(heading)+","+str(tiltCompensatedHeading)+","+str(kalmanX)+","+str(kalmanY)+"\n")
                else:
                    self.complete_dir = os.path.join("/home/radxa/GPS_IMU_Data", self._startDate)
                    self._dest = os.path.join(self.complete_dir, 'accelData.csv')
                    if not os.path.isdir(self.complete_dir):
                        print("SSD not mounted, falling back to builtin storage GPS_IMU_Data for Accel data")
                        os.makedirs(self.complete_dir)
                    with open(self._dest,"ta", buffering=8192) as f:
                        f.write(str(now.timestamp())+","+str(ACCx)+","+str(ACCy)+","+str(ACCz)+","+str(rate_gyr_x)+","+str(rate_gyr_y)+","+str(rate_gyr_z)+","+str(gyroXangle)+","+str(gyroYangle)+","+str(gyroZangle)+","+str(MAGx)+","+str(MAGy)+","+str(MAGz)+","+str(heading)+","+str(tiltCompensatedHeading)+","+str(kalmanX)+","+str(kalmanY)+"\n")
            # if 1:                       #Change to '0' to stop showing the angles from the accelerometer
            #     outputString += "#  ACCX Angle %5.2f ACCY Angle %5.2f  #  " % (AccXangle, AccYangle)

            # if 1:                       #Change to '0' to stop  showing the angles from the gyro
            #     outputString +="\t# GRYX Angle %5.2f  GYRY Angle %5.2f  GYRZ Angle %5.2f # " % (gyroXangle,gyroYangle,gyroZangle)

            # # if 1:                       #Change to '0' to stop  showing the angles from the complementary filter
            # #     outputString +="\t#  CFangleX Angle %5.2f   CFangleY Angle %5.2f  #" % (CFangleX,CFangleY)

            # outputString +="\t# HEADING %5.2f  tiltCompensatedHeading %5.2f #" % (heading,tiltCompensatedHeading)

            # outputString +="# kalmanX %5.2f   kalmanY %5.2f #" % (kalmanX,kalmanY)
            # outputString += "# Raw accelerometer x: %5.2f y: %5.2f z: %5.2f #" % (ACCx,ACCy,ACCz)
            # print(outputString)

            #slow program down a bit, makes the output more readable
            time.sleep(SAMPLE_PERIOD_S)