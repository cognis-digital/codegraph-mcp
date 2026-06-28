import sys
from pathlib import Path

# Make the package importable when running the tests without installing.
sys.path.insert(0, str(Path(__file__).resolve().parent))
