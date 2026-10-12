import sys

if __name__ == "__main__":
    print("Process exiting with error code 1", file=sys.stderr)
    sys.exit(1)
