#!/usr/bin/env python

from h2rMultiWii import MultiWii
import time

def main():
    board = MultiWii("/dev/ttyUSB0")
    print("Calibrate ACC... make sure we are level and still.")
    time.sleep(1)
    board.send_rc_CMD(0, MultiWii.ACC_CALIBRATION, [])
    board.receiveDataPacket()
    time.sleep(2)
    print("Done!")
    
if __name__ == "__main__":
    main()
