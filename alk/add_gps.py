import os, json, csv
import numpy as np
from scipy import interpolate
from datetime import datetime

MOUNT_POINT = "D:/Alkmaar/Indlovu/tricap/ExifData"
DATE_STRING = "2022_10_12"

# read gps data
imu_dir = os.path.join(MOUNT_POINT, DATE_STRING)
complete_gps_dir = os.path.join(imu_dir, 'gpsData.csv')

gps_times = []
pi_times = []
lats = []
longs = []
alts = []
qualities = []
gpsLatDir = ''
gpsLongDir = ''
with open(complete_gps_dir) as csv_file:
  csv_reader = csv.reader(csv_file, delimiter=',')
  for row in csv_reader:
    # print(f"row {row}")
    if len(row) > 8:
      try:
        qualities.append(float(row[0]))
        gps_times.append(float(row[1]))
        pi_times.append(float(row[2]))
        lats.append(float(row[3]))
        gpsLatDir = row[4]
        longs.append(float(row[5]))
        gpsLongDir = row[6]
        alts.append(float(row[7]))
      except:
        print('Read gps error')

qualities = np.asarray(qualities)
gps_times = np.asarray(gps_times)
pi_times = np.asarray(pi_times)
lats = np.asarray(lats)
longs = np.asarray(longs)
alts = np.asarray(alts)

f_qual = interpolate.interp1d(gps_times, qualities)
# f_gps_times = interpolate.interp1d(gps_times, pi_times)
f_lats = interpolate.interp1d(gps_times, lats)
f_longs = interpolate.interp1d(gps_times, longs)
f_alts = interpolate.interp1d(gps_times, alts)

# read accelerometer data
complete_accel_dir = os.path.join(imu_dir, 'accelData.csv')

heading = []
headingComp = []
kalmanX = []
kalmanY = []
pi_times = []
with open(complete_accel_dir) as csv_file:
  csv_reader = csv.reader(csv_file, delimiter=',')
  for row in csv_reader:
    if len(row) > 16:
      pi_times.append(float(row[0]))
      heading.append(float(row[13]))
      headingComp.append(float(row[14]))
      kalmanX.append(float(row[15]))
      kalmanY.append(float(row[16]))

heading = np.asarray(heading)
headingComp = np.asarray(headingComp)
kalmanX = np.asarray(kalmanX)
kalmanY = np.asarray(kalmanY)
pi_times = np.asarray(pi_times)

f_heading = interpolate.interp1d(pi_times, heading)
f_headingComp = interpolate.interp1d(pi_times, headingComp)
f_kalmanX = interpolate.interp1d(pi_times, kalmanX)
f_kalmanY = interpolate.interp1d(pi_times, kalmanY)

# cam_session_dir = os.path.join(MOUNT_POINT, DATE_STRING)
complete_cam_dir = os.path.join(MOUNT_POINT, 'exif_ssd.json')
ssd_info = {}
with open(complete_cam_dir, 'r') as f:
    ssd_info = json.load(f)
for session in ssd_info:
  print(f"Session {session['sessionId']}")
  cams_info = session['sessionInfo']
  for cam in cams_info:
    images = cam['exifInfo']
    for im in images:
      im_time = float(datetime.strptime(im['SubSecDateTimeOriginal'], '%Y:%m:%d %H:%M:%S.%f').timestamp())
      try:
        im['GPSDateStamp'] = im_time
        # im['GPSDateStamp'] = np.array(f_gps_times([im_time]))[0]
        im['GPSLatitude'] = np.array(f_lats([im_time]))[0]
        im['GPSLongitude'] = np.array(f_longs([im_time]))[0]
        im['GPSAltitude'] = np.array(f_alts([im_time]))[0]
        im['GPSQuality'] = np.array(f_qual([im_time]))[0]
        im['Heading'] = np.array(f_heading([im_time]))[0]    
        im['HeadingComp'] = np.array(f_headingComp([im_time]))[0]     
        im['KalmanX'] = np.array(f_kalmanX([im_time]))[0]     
        im['KalmanY'] = np.array(f_kalmanY([im_time]))[0]                        
        im['GPSLatitudeDir'] = gpsLatDir
        im['GPSLongitudeDir'] = gpsLongDir
      except Exception as ex:
        print(f"Exception {ex}")
    cam['exifInfo'] = images
with open(complete_cam_dir, 'w') as f:
  json.dump(ssd_info, f, sort_keys=True)   
