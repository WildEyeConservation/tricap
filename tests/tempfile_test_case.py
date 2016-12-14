"""tempfiler_test - base test class when having to deal with temp files. Does not need the app."""

import tempfile
import shutil
import os

import unittest

from config import CONFIG_FP


class TempFilerTestCase(unittest.TestCase):
    """Base test class when having to deal with temp files."""

    def setUp(self):
        """Instantiate a temporary directory. Serves as an init."""
        self.temp_file_count = 0
        self.temp_dir = None
        self.bk_config_fp = None

        self.tempdir = tempfile.mkdtemp()

        self.temp_file_count = 0

    def tearDown(self):
        """Destroy the temporary directory."""
        for root, _, filenames in os.walk(self.tempdir):
            for filename in filenames:
                os.remove(os.path.join(root, filename))

        shutil.rmtree(self.tempdir)

    def _create_temp_file(self):
        temp_fp = os.path.join(self.tempdir, str(self.temp_file_count) + '.temp')
        ftemp = open(temp_fp, 'w')
        ftemp.close()
        self.temp_file_count += 1
        return temp_fp


class TricapTempFilerTestCase(TempFilerTestCase):
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
