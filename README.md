# Tricap

## Software installation

### Basic setup

1. Login to the raspberri pi with username pi and password raspberry.

1. Connect to the internet using and enable I2C

```
sudo raspi-config
```

Select: System options -> Wireless LAN -> Enter your SSID and password -> Reboot
Select: Interface options -> I2C -> Enable -> Reboot

1. Update your raspberry pi and install the required libraries

```
sudo apt-get update && sudo apt-get upgrade
sudo apt-get install git-all
sudo apt-get install python3-pip
sudo apt-get install python3-rpi.gpio
sudo apt-get install python3-scipy
sudo apt-get install libraw-dev
sudo apt-get install -y libimage-exiftool-perl
sudo apt-get install python3-smbus
sudo apt-get install libexif12 libgphoto2-6 libgphoto2-port12 libltdl7
sudo apt-get install python-opencv
sudo apt-get install libatlas-base-dev
```

### Clone the tricap git repository

```
cd /home/pi/
git clone git@bitbucket.org:innoventix/tricap.git
cd tricap/
git checkout -b gpio-cam origin/gpio-cam
```

### Change executable scripts

```
cd /home/pi/tricap/
sudo chmod +x tricap_launch_tester.py
sudo chmod +x wifi_setup.sh
sudo chmod +x tricap_launcher.sh
sudo chmod +x python_setup.sh
mkdir logs
cp default.cfg initial.cfg
```

### Install the required python libraries

```
cd /home/pi/tricap/
sudo ./python_setup.sh
```

### Other updates

add enable_uart=1 to /boot/cmdline.txt

```
sudo nano /boot/cmdline.txt
```

### Create and start tricap service

```
sudo cp /home/pi/tricap/tricap.service /etc/systemd/system/tricap.service
sudo systemctl daemon-reload
sudo systemctl enable tricap.service
sudo systemctl start tricap.service
```

### Create and start udp service

```
sudo cp /home/pi/tricap/udp-ip.service /etc/systemd/system/udp-ip.service
sudo systemctl daemon-reload
sudo systemctl enable udp-ip.service
sudo systemctl start udp-ip.service
```

## Hardware setup

### GPIO outputs

1. Pin 11 (GPIO 17) is used to trigger a capture by generating a rising edge and remains high for 1ms.

2. Pin 13 (GPIO 27) is used to toggle an LED as feedback for detecting a capture. The output will be high on startup and output a low voltage for 200ms after a successful capture detection.

### GPIO inputs

1. Pin 15 (GPIO 22) is used to detect a successful capture. The input uses an internal pull-up resistor and will wait for a rising edge.

### Berry GPS IMU

1. The Berry GPS IMU module connects to the raspberry pi on GPIO pins 1 to 10.