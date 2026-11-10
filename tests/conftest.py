import os
import sys

# The firmware modules under test are plain Python with no board imports.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "firmware", "lib"))
