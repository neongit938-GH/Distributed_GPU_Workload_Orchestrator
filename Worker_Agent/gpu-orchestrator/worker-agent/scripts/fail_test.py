import sys

if __name__ == "__main__":
    print("Intentional failure logged to stderr", file=sys.stderr)
    sys.exit(42)
