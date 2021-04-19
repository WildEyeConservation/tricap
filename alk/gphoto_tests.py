from datetime import datetime
import logging, os, sys, threading, time
import gphoto2 as gp

import hashlib, json

temp = {
  "name": 'Alkmaar',
  "values": [{
    "start": 0,
    "end": 10
  }, {
    "start": 20,
    "end": 30
  }]
}

temp2 = hashlib.md5(str(temp).encode()).hexdigest()

print(temp2)

def get_session_ids():
  ids = []
  for root, dirs, files in os.walk('/mnt/ext_cam_storage'):
    # print(root, dirs, files)
    for name in files:
      if name == 'exif.json':
        a, b = os.path.split(root)
        c, d = os.path.split(a)
        print(a, b, c, d)

get_session_ids()

# cameras = []
# port_info_list = gp.PortInfoList()
# port_info_list.load()
# for name, address in gp.Camera().autodetect():
#   print('Adding camera %s at address %s ' % (name, address))
#   camera = gp.Camera()
#   port_info = port_info_list[port_info_list.lookup_path(address)]
#   camera.set_port_info(port_info)
#   camera.init(gp.Context())
#   cameras.append(camera)

# if len(cameras) == 0:
#   exit()

# cam = cameras[0]

# cam.folder_make_dir('/store_00020001/DCIM/100CANON', 'new', gp.Context())




# camera.exit()
