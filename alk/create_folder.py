from datetime import datetime
import logging
import os
import sys
import threading
import time

import gphoto2 as gp

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

def create_camera_file(camera, name, path='/'):
  camera.folder_make_dir(path, name)

def print_files(camera):
  camera_files = list_camera_files(camera)
  if not camera_files:
    print('No files found')
    return 1
  for path in camera_files:
    print(path)

def main():
  logging.basicConfig(format='%(levelname)s: %(name)s: %(message)s', level=logging.WARNING)
  callback_obj = gp.check_result(gp.use_python_logging())
  camera = gp.Camera()
  camera.init(gp.Context())

  # print_files(camera)
  # print('Create file')
  # create_camera_file(camera, 'test', '/store_00020001/DCIM/')
  # print('Sleep for 1s')
  # time.sleep(1)
  # print_files(camera)

  camera_files = camera.get_all_files('/store_00020001/DCIM/102CANON')

  return 0

if __name__ == "__main__":
  sys.exit(main())