"""Parse the data from the cameras using gphoto2"""
import gphoto2 as gp


class ParseCamera():
    def __init__(self):
        self.context = gp.Context()
        self.camera = gp.Camera()
        self.camera.init(self.context)
        self.text = self.camera.get_summary(self.context)
        self.tex = str(self.text)
        self.parse = ""

    def parsing(self, data):
        self.parse = ""
        self.index = self.tex.find(data) + len(data)
        while self.tex[self.index] != ' ' and self.tex[self.index] != '\n':
            self.parse += str(self.tex[self.index])
            self.index += 1
        return self.parse

    def parse_serial_number(self):
        self.serial_number = self.parsing("Serial Number: ")
        return self.serial_number

    def parse_available_space(self):
        self.available_space = self.parsing("Free Space (Bytes): ")
        self.available_space = int(self.available_space)/(1024*1024)
        return str(self.available_space) + " Mb"

    def parse_battery_level(self):
        self.serial_number = self.parsing("value: ")
        return self.serial_number.strip("%")

# Pi test code
# camera_data = ParseCamera()
# print(camera_data.parse_available_space())
# print(camera_data.parse_serial_number())
# print(camera_data.parse_battery_level())

context = gp.Context()
# make a list of all available cameras
camera_list = []
for name, addr in context.camera_autodetect():
    camera_list.append((name, addr))
if not camera_list:
    print('No camera detected')

camera_list.sort(key=lambda x: x[0])
# ask user to choose one
for index, (name, addr) in enumerate(camera_list):
    print('{:d}:  {:s}  {:s}'.format(index, addr, name))
choice = input('Please input number of chosen camera: ')
if choice < 0 or choice >= len(camera_list):
    print('Number out of range')

    # initialise chosen camera
name, addr = camera_list[choice]
camera = gp.Camera()
    # search ports for camera port name
port_info_list = gp.PortInfoList()
port_info_list.load()
idx = port_info_list.lookup_path(addr)
camera.set_port_info(port_info_list[idx])
camera.init(context)
text = camera.get_summary(context)
print('Summary')
print('=======')
print(str(text))
