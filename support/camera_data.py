"""Parse the data from the cameras using gphoto2"""
import gphoto2 as gp
from app import tricap_cameras


class ParseData():
    #def __init__(self):

        # self.context = gp.Context()
        # self.camera_list = []  # make a list of all available cameras
        # for self.name, self.addr in self.context.camera_autodetect():
        #     self.camera_list.append((self.name, self.addr))
        # if not self.camera_list:
        #     print('No camera detected')
        #
        # self.camera_list.sort(key=lambda x: x[0])
        # # ask user to choose one
        # # for self.index, (self.name, self.addr) in enumerate(self.camera_list):
        # #     print('{:d}:  {:s}  {:s}'.format(self.index, self.addr, self.name))
        # self.parse = [""]*3

    def parse_data(self, data, number):
        # self.name, self.addr = self.camera_list[number]  # choice
        # self.camera = gp.Camera()
        # # search ports for camera port name
        # self.port_info_list = gp.PortInfoList()
        # self.port_info_list.load()
        # self.idx = self.port_info_list.lookup_path(self.addr)
        # self.camera.set_port_info(self.port_info_list[self.idx])
        # self.camera.init(self.context)
        self.context = tricap_cameras[number].get_camera_context()
        self.text = tricap_cameras[number].get_camera().get_summary(self.context)
        # self.text = self.camera.get_summary(self.context)

        self.tex = str(self.text)
        self.parse[number] = ""
        self.index = self.tex.find(data) + len(data)
        while self.tex[self.index] != ' ' and self.tex[self.index] != '\n':
            self.parse[number] += str(self.tex[self.index])
            self.index += 1
        return self.parse[number]

    def parse_serial_number(self, number):
        self.serial_number = self.parse_data("Serial Number: ", number)
        return self.serial_number

    def parse_available_space(self, number):
        self.available_space = self.parse_data("Free Space (Bytes): ", number)
        self.available_space = int(self.available_space)/(1024*1024)
        return str(self.available_space) + " Mb"

    def parse_battery_level(self, number):
        self.serial_number = self.parse_data("value: ", number)
        return self.serial_number

    def parse_camera(self, number):
        # self.name, self.addr = self.camera_list[number]  # choice
        # self.camera = gp.Camera()
        # # search ports for camera port name
        # self.port_info_list = gp.PortInfoList()
        # self.port_info_list.load()
        # self.idx = self.port_info_list.lookup_path(self.addr)
        # self.camera.set_port_info(self.port_info_list[self.idx])
        # self.camera.init(self.context)
        self.context = tricap_cameras[number].get_camera_context()
        self.text = tricap_cameras[number].get_camera().get_summary(self.context)
        # self.text = self.camera.get_summary(self.context)

        self.tex = str(self.text)
        self.parse = [""]*3
        self.index = self.tex.find("Serial Number: ") + len("Serial Number: ")
        while self.tex[self.index] != ' ' and self.tex[self.index] != '\n':
            self.parse[0] += str(self.tex[self.index])
            self.index += 1
        self.index = self.tex.find("Free Space (Bytes): ") + len("Free Space (Bytes): ")
        while self.tex[self.index] != ' ' and self.tex[self.index] != '\n':
            self.parse[1] += str(self.tex[self.index])
            self.index += 1
        self.index = self.tex.find("value: ") + len("value: ")
        while self.tex[self.index] != ' ' and self.tex[self.index] != '\n':
            self.parse[2] += str(self.tex[self.index])
            self.index += 1

        return self.parse[0], str(int(self.parse[1])/(1024*1024)) + " Mb", self.parse[2]


# camera_data = ParseData()
# serNum = ""
# freeSpace = ""
# batt = ""
# for nums in range(3):
#     serNum, freeSpace, batt = camera_data.parse_camera(nums)
#     print(serNum)
#     print(freeSpace)
#     print(batt)


    # print(camera_data.parse_available_space(nums))
    # print(camera_data.parse_serial_number(nums))
    # print(camera_data.parse_battery_level(nums))
