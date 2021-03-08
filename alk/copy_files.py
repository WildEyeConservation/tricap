from datetime import datetime
import logging
import os
import sys
import threading
import time

import gphoto2 as gp

# PHOTO_DIR = os.path.expanduser('/home/pi/Pictures/from_camera')
PHOTO_DIR = os.path.expanduser('/mnt/samsung_ssd/from_camera')

def get_target_dir(timestamp, index):
  addDir = "{}/{}/".format(timestamp.strftime('%Y/%Y_%m_%d'), str(index))
  return os.path.join(PHOTO_DIR, addDir)

def list_computer_files():
  result = []
  for root, dirs, files in os.walk(os.path.expanduser(PHOTO_DIR)):
    for name in files:
      if '.thumbs' in dirs:
        dirs.remove('.thumbs')
      if name in ('.directory',):
        continue
      ext = os.path.splitext(name)[1].lower()
      if ext in ('.db',):
        continue
      result.append(os.path.join(root, name))
  return result

def list_camera_files(camera, path='/'):
  result = []
  # get files
  gp_list = camera.folder_list_files(path)
  for name, value in gp_list:
    result.append(os.path.join(path, name))
  # read folders
  folders = []
  gp_list = camera.folder_list_folders(path)
  for name, value in gp_list:
    folders.append(name)
  # recurse over subfolders
  for name in folders:
    result.extend(list_camera_files(camera, os.path.join(path, name)))
  return result

def get_camera_file_info(camera, path):
  folder, name = os.path.split(path)
  return camera.file_get_info(folder, name)

def detect_cameras():
  port_info_list = gp.PortInfoList()
  port_info_list.load()
  print("port_info_list %s" % (port_info_list))
  cameras = []
  for name, address in gp.Camera().autodetect():
    print('Adding camera %s at address %s ' % (name, address))
    camera = gp.Camera()
    port_info = port_info_list[port_info_list.lookup_path(address)]
    camera.set_port_info(port_info)
    camera.init(gp.Context())
    cameras.append(camera)
  return cameras

def cpy_images(camera, computer_files, index, stop):
  portInfo = camera.get_port_info().get_path()
  print('Port speed %s, Port info %s' % (camera.get_port_speed(), portInfo))
  print('Getting list of files from camera...')
  camera_files = list_camera_files(camera)
  if not camera_files:
    print('No files found')
    return 1
  print('Copying files to %s' % (PHOTO_DIR))
  for path in camera_files:
    if stop():
      camera.exit()
      return

    info = get_camera_file_info(camera, path)
    timestamp = datetime.fromtimestamp(info.file.mtime)
    folder, name = os.path.split(path)
    dest_dir = get_target_dir(timestamp, index)
    dest = os.path.join(dest_dir, name)
    if dest in computer_files:
      continue
    print('%s -> %s' % (path, dest_dir))
    if not os.path.isdir(dest_dir):
      os.makedirs(dest_dir)
    camera_file = camera.file_get(folder, name, gp.GP_FILE_TYPE_RAW)
    for attemp in range(3):
      try:
        gp.check_result(gp.gp_file_save(camera_file, dest))
        camera.file_delete(folder, name)
      except:
        print("Save exception, sleep...")
        time.sleep(2)
      else:
        break
    else:
      print("Attemps failed")

  camera.exit()

def main():
  logging.basicConfig(format='%(levelname)s: %(name)s: %(message)s', level=logging.WARNING)
  callback_obj = gp.check_result(gp.use_python_logging())
  computer_files = list_computer_files()
  cameras = detect_cameras()
  start = datetime.now()
  print(start)

  threads = list()
  stop_thread = False
  for index, camera in enumerate(cameras):
    x = threading.Thread(target=cpy_images, args=(camera, computer_files, index, lambda : stop_thread, ), daemon=True)
    threads.append(x)
    x.start()
      
  for thread in threads:
    thread.join()

  end = datetime.now()
  print(end)
  print((end-start).total_seconds())

  return 0

if __name__ == "__main__":
  sys.exit(main())
