"""
© Copyright 2020 HP Development Company, L.P.
SPDX-License-Identifier: GPL-2.0-only
"""

import os
import time
import unittest
import shutil
import yaml

from integration_test.helper import check_output, clear
from integration_test.helper import PATH_TEST, ML_GIT_DIR
from integration_test.output_messages import messages


class AcceptanceTests(unittest.TestCase):

    def setUp(self):
        os.chdir(PATH_TEST)
        self.maxDiff = None

    def test_01_init_root_directory(self):
        if os.path.exists(ML_GIT_DIR):
            self.assertIn(messages[1], check_output('ml-git init'))
        else:
            self.assertIn(messages[0], check_output('ml-git init'))
        config = os.path.join(ML_GIT_DIR, "config.yaml")
        self.assertTrue(os.path.exists(config))

    def test_02_init_subfoldery(self):
        clear(ML_GIT_DIR)
        self.assertIn(messages[0], check_output("ml-git init"))
        os.chdir(".ml-git")
        self.assertIn(messages[1],check_output("ml-git init"))

    def test_03_init_already_initialized_repository(self):
        clear(ML_GIT_DIR)
        self.assertIn(messages[0], check_output("ml-git init"))
        self.assertIn(messages[1],check_output("ml-git init"))


if __name__ == "__main__":
   unittest.main()