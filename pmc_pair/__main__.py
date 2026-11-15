import sys

from .cli import main

# The guard matters: worker processes started with "spawn"/"forkserver" re-import this module.
if __name__ == "__main__":
    sys.exit(main())
