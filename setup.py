from cx_Freeze import setup, Executable

base = None

executables = [Executable("SD_card_reader.py", base=base)]

setup(
    name = "Tricap SD card reader",
    version = "1.0",
    description = 'Read three SD cards from the TriCap rig',
    executables = executables
)