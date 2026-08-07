import unittest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from tests import test_ml_filter

if __name__ == "__main__":
    suite = unittest.defaultTestLoader.loadTestsFromModule(test_ml_filter)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    sys.exit(0 if result.wasSuccessful() else 1)
