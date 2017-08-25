from subprocess import PIPE, Popen

GIT_LOG_FORMAT = ['%H', '%an', '%ae', '%ad', '%s']
GIT_LOG_FORMAT = '%x1f'.join(GIT_LOG_FORMAT) + '%x1e'

class Git():
    def __init__(self):
        self.index = 0
        self.git_parse = ""
        self.parse_id = ""

    def id(self):
        self.git_parse = Popen('git log --format="%s"' % GIT_LOG_FORMAT, shell=True, stdout=PIPE)
        (log, _) = self.git_parse.communicate()
        log = str(log)
        for self.index in range(2,42):
            self.parse_id += log[self.index]
        print(self.parse_id)

parser = Git()
parser.id()



