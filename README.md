# Tricap

## Install

### Basic setup

1. Login with username pi and password raspberry.

1. Connect to the internet using

```
sudo raspi-config
```

Select: System options -> Wireless LAN -> Enter your SSID and password -> Reboot

1. Update your raspberry pi and install the required libraries

```
sudo apt-get update && sudo apt-get upgrade
sudo apt-get install git-all
```

### Clone the tricap git repository

```
cd /home/pi/
git clone git@bitbucket.org:innoventix/tricap.git
```

### Change executable scripts

```
cd /home/pi/tricap/
sudo chmod +x tricap_launch_tester.py
sudo chmod +x wifi_setup.sh
sudo chmod +x tricap_launcher.sh
```

### Create and start service

```
sudo cp /home/pi/tricap/tricap.service /etc/systemd/system/tricap.service
sudo systemctl daemon-reload
sudo systemctl enable tricap.service
sudo systemctl start tricap.service
```