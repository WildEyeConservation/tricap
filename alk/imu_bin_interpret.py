import struct
from datetime import datetime

# Define the struct format
rec = struct.Struct("<9hd")

def read_binary_file(filename):
    records = []
    with open(filename, "rb") as f:
        while chunk := f.read(rec.size):
            if len(chunk) != rec.size:
                break  # incomplete record at the end
            unpacked = rec.unpack(chunk)
            
            # unpacked = (ACCx, ACCy, ACCz, GYRx, GYRy, GYRz, MAGx, MAGy, MAGz, timestamp)
            acc = unpacked[0:3]
            gyr = unpacked[3:6]
            mag = unpacked[6:9]
            timestamp = datetime.fromtimestamp(unpacked[9])
            
            records.append({
                "ACC": acc,
                "GYR": gyr,
                "MAG": mag,
                "timestamp": timestamp
            })
    return records

# Example usage
if __name__ == "__main__":
    data = read_binary_file("accelData_20250902_150126.bin")
    for rec in data[-20:]:  # print first 5
        print(rec)
