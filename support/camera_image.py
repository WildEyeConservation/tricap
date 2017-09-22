from __future__ import print_function

import logging
import os
import io
import sys
from matplotlib import pyplot as plt

from PIL import Image

import gphoto2 as gp


def list_files(camera, context, path='/'):
    result = []
    # get files
    for name, value in gp.check_result(
            gp.gp_camera_folder_list_files(camera, path, context)):
        result.append(os.path.join(path, name))
    # read folders
    folders = []
    for name, value in gp.check_result(
            gp.gp_camera_folder_list_folders(camera, path, context)):
        folders.append(name)
    # recurse over subfolders
    for name in folders:
        result.extend(list_files(camera, context, os.path.join(path, name)))
    return result


def save_last_file(camera, context):
    # logging.basicConfig(
    #     format='%(levelname)s: %(name)s: %(message)s', level=logging.WARNING)
    # gp.check_result(gp.use_python_logging())
    # camera = gp.check_result(gp.gp_camera_new())
    # context = gp.gp_context_new()
    # gp.check_result(gp.gp_camera_init(camera, context)) # Init camera

    # Get above info from already used cameras
    print('Getting list of files')
    files = list_files(camera, context)
    if not files:
        print('No files found')
        return 1
    path = files[len(files)-1]
    print('Copying %s to memory in 100 kilobyte chunks' % path)
    folder, name = os.path.split(path)
    file_info = gp.check_result(gp.gp_camera_file_get_info(
        camera, folder, name, context))
    data = bytearray(file_info.file.size)
    view = memoryview(data)
    chunk_size = 100 * 1024
    offset = 0
    while offset < len(data):
        bytes_read = gp.check_result(gp.gp_camera_file_read(
            camera, folder, name, gp.GP_FILE_TYPE_NORMAL,
            offset, view[offset:offset + chunk_size], context))
        offset += bytes_read
        #print(bytes_read)
    print(' '.join(map(str, data[0:10])))
    import rawpy
    import imageio
    raw = rawpy.imread(io.BytesIO(data))
    rgb = raw.postprocess()
    imageio.imsave('defaultend.jpg', rgb)
    gp.check_result(gp.gp_camera_exit(camera, context))
    return 0

# gphoto2 -f /store_00020002/DCIM/100PHOTO -d 1























if __name__ == "__main__":
    sys.exit(main())
