"""To run tricap in a loop."""

from multiprocessing import Process
from time import sleep


def worker():
    """Thread."""
    print('Starting Server')
    exec(open("./tricap.py").read())


if __name__ == '__main__':
    process = None
    while True:
        if process is None or process.is_alive() is False:
            process = Process(target=worker, daemon=True)
            process.start()
        else:
            process.join(5)
            print('.')
            sleep(5)
