"""Parse the data from the cameras using gphoto2"""

from app import use_dummy_cams
if not use_dummy_cams:
    import gphoto2 as gp
    from app import tricap_cameras
    from support.camera_image import save_last_file

    class ParseData():

        def parse_data(self, data, number):
            self.context = tricap_cameras[number].get_camera_context()
            self.text = tricap_cameras[number].get_camera().get_summary(self.context)

            self.tex = str(self.text)
            self.parse[number] = ""
            self.index = self.tex.find(data) + len(data)
            while self.tex[self.index] != ' ' and self.tex[self.index] != '\n':
                self.parse[number] += str(self.tex[self.index])
                self.index += 1
            return self.parse[number]

        def get_last_image(self, number):
            self.context_file = tricap_cameras[number].get_camera_context()
            self.camera_file = tricap_cameras[number].get_camera()
            save_last_file(self.camera_file, self.context_file)

        @staticmethod
        def parse_serial_number(number):  # self parameter
            # self.serial_number = self.parse_data("Serial Number: ", number)
            return tricap_cameras[number].serial_num

        def parse_available_space(self, number):
            self.available_space = self.parse_data("Free Space (Bytes): ", number)
            self.available_space = int(self.available_space)/(1024*1024)
            return str(self.available_space) + " Mb"

        def parse_battery_level(self, number):
            self.serial_number = self.parse_data("value: ", number)
            return self.serial_number

        def parse_camera(self, number):
            self.context = tricap_cameras[number].get_camera_context()
            self.text = tricap_cameras[number].get_camera().get_summary(self.context)

            self.tex = str(self.text)
            self.parse = [""]*3
            self.parse[0] = tricap_cameras[number].serial_num
            self.index = self.tex.find("Free Space (Bytes): ") + len("Free Space (Bytes): ")
            while self.tex[self.index] != ' ' and self.tex[self.index] != '\n':
                self.parse[1] += str(self.tex[self.index])
                self.index += 1
            self.index = self.tex.find("value: ") + len("value: ")
            while self.tex[self.index] != ' ' and self.tex[self.index] != '\n':
                self.parse[2] += str(self.tex[self.index])
                self.index += 1

            return self.parse[0], str(int(self.parse[1])/(1024*1024)), self.parse[2].strip('%')

else: # test code
    class ParseData():
        @staticmethod
        def parse_serial_number(number):
            return number+1