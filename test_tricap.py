""" D Joubert 16 November 2016 - Unit Tests For TriCap"""

import unittest

from tests.test_settings import TestSettings

DO_BEHAVIOUR_TESTS = True

if DO_BEHAVIOUR_TESTS is True:
    from tests.test_settings import TestBehaviourSettings

if __name__ == '__main__':
    unittest.main()
