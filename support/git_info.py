from subprocess import PIPE, Popen


class GitData():
    def __init__(self):
        self.index = 0
        self.git_parse = ""
        self.parse_id = ""
        self.parse_date = ""
        self.git_parse = Popen('git log', shell=True, stdout=PIPE)
        (log, _) = self.git_parse.communicate()
        self.log = str(log)

    def code_id(self):
        self.index = self.log.find("commit ") + len("commit ")
        while self.log[self.index] != ' ' and self.log[self.index] != '\\':
            self.parse_id += str(self.log[self.index])
            self.index += 1
        print(self.parse_id)
        return self.parse_id

    def code_date(self):
        self.index = self.log.find("Date:   ") + len("Date:   ")
        while self.log[self.index] != '\\':
            self.parse_date += str(self.log[self.index])
            self.index += 1
        print(self.parse_date)
        return self.parse_date

# parser = Git()
# parser.code_id()
# parser.code_date()



