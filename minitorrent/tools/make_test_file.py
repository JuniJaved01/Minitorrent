"""
tools/make_test_file.py  --  OWNER: MAAZ
Create a random test file.     python tools/make_test_file.py big.bin 50      (50 MB)
"""

import os  # random bytes
import sys  # command-line arguments


def main():
    path = sys.argv[1]  # output file name
    megabytes = int(sys.argv[2]) if len(sys.argv) > 2 else 50  # size in MB (default 50)
    with open(path, "wb") as f:  # create the file
        for _ in range(megabytes):  # one megabyte at a time keeps RAM low
            f.write(os.urandom(1024 * 1024))  # random bytes, so every chunk hash differs
    print("created %s (%d MB)" % (path, megabytes))  # confirm


if __name__ == "__main__":  # only when run as a program
    main()  # go
