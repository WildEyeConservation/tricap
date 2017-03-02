"""TempFilerTestCase for TriCap."""

import shutil
import os

from common_tests.tempfiler_test_case import TempFilerTestCase

from config import CONFIG_FP


class TriCapTempFilerTestCase(TempFilerTestCase):
    """Tricap temp filer, takes care of backing up the config file."""

    def setUp(self):
        """Instantiate a temporary directory and backup the config file. Serves as an init."""
        super().setUp()

        self.bk_config_fp = os.path.join(self.tempdir, 'initial.cfg_bk')
        shutil.copyfile(CONFIG_FP, self.bk_config_fp)

    def tearDown(self):
        """Restore the config file and destroy the temporary directory."""
        shutil.copyfile(self.bk_config_fp, CONFIG_FP)

        super().tearDown()
