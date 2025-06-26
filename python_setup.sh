#!/bin/bash

# List of packages to install
packages=(
    anytree
    asn1crypto
    certifi
    chardet
    click
    cryptography
    cython
    DateTime
    entrypoints
    ExifRead
    Flask
    flask-wtf
    gphoto2
    idna
    imutils
    itsdangerous
    Jinja2
    joblib
    keyring
    MarkupSafe
    netifaces
    numpy
    opencv
    opencv-python
    Pillow
    pip
    protobuf
    PyBluez
    pycrypto
    PyGObject
    pynmea2
    pyserial
    pytz
    pyxdg
    python-dateutil
    rawkit
    rawpy
    requests
    RPi
    scikit
    SecretStorage
    setuptools
    six
    ssh
    smbus
    threaded
    threadpoolctl
    urllib3
    Werkzeug
    wheel
    WTForms
    zope
    pyexifinfo
)

# Install each package using pip
for package in "${packages[@]}"
do
    sudo pip3 install $package
done

sudo python3 -m pip install git+https://github.com/letmaik/rawpy.git