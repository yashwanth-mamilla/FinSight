#!/usr/bin/env python3

import sys
import os

# Add src to path so finsight can be imported
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from finsight.cli import main

if __name__ == "__main__":
    sys.exit(main())
