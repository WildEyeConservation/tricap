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

# context = gp.Context()
# camera_list = []  # make a list of all available cameras
# for name, addr in context.camera_autodetect():
#     camera_list.append((name, addr))
# if not camera_list:
#     print('No camera detected')
#
# camera_list.sort(key=lambda x: x[0])
# # ask user to choose one
# for index, (name, addr) in enumerate(camera_list):
#     print('{:d}:  {:s}  {:s}'.format(index, addr, name))
# # choice = input('Please input number of chosen camera: ')
# # choice = int(choice)
# # if choice < 0 or choice >= len(camera_list):
# #     print('Number out of range')
#
#     # initialise chosen camera
# cameraNumber = 0
#
# for cameraNumber in range(3):
#     name, addr = camera_list[cameraNumber]  # choice
#     camera = gp.Camera()
#     # search ports for camera port name
#     port_info_list = gp.PortInfoList()
#     port_info_list.load()
#     idx = port_info_list.lookup_path(addr)
#     camera.set_port_info(port_info_list[idx])
#     camera.init(context)
#     text = camera.get_summary(context)
#     print('Summary')
#     print('=======')
#     print(str(text))


class ParseData():
    def __init__(self):
        self.context = gp.Context()
        self.camera_list = []  # make a list of all available cameras
        for self.name, self.addr in self.context.camera_autodetect():
            self.camera_list.append((self.name, self.addr))
        if not self.camera_list:
            print('No camera detected')

        self.camera_list.sort(key=lambda x: x[0])
        # ask user to choose one
        for self.index, (self.name, self.addr) in enumerate(self.camera_list):
            print('{:d}:  {:s}  {:s}'.format(self.index, self.addr, self.name))
        self.parse[0] = ""
        self.parse[1] = ""
        self.parse[2] = ""

    def parse_data(self, data):
        for self.cameraNumber in range(3):
            self.name, self.addr = self.camera_list[self.cameraNumber]  # choice
            self.camera = gp.Camera()
            # search ports for camera port name
            self.port_info_list = gp.PortInfoList()
            self.port_info_list.load()
            self.idx = self.port_info_list.lookup_path(self.addr)
            self.camera.set_port_info(self.port_info_list[self.idx])
            self.camera.init(self.context)
            self.text = self.camera.get_summary(self.context)

            self.tex = str(self.text)
            self.parse[self.cameraNumber] = ""
            self.index = self.tex.find(data) + len(data)
            while self.tex[self.index] != ' ' and self.tex[self.index] != '\n':
                self.parse[self.cameraNumber] += str(self.tex[self.index])
                self.index += 1
        return self.parse

    def parse_serial_number(self, number):
        self.serial_number = self.parse_data("Serial Number: ")
        return self.serial_number[number]

    def parse_available_space(self, number):
        self.available_space = self.parse_data("Free Space (Bytes): ")
        self.available_space = int(self.available_space[number])/(1024*1024)
        return str(self.available_space) + " Mb"

    def parse_battery_level(self, number):
        self.serial_number = self.parse_data("value: ")
        return self.serial_number[number].strip("%")

camera_data = ParseData()
for nums in range(3):
    print(camera_data.parse_available_space(nums))
    print(camera_data.parse_serial_number(nums))
    print(camera_data.parse_battery_level(nums))
