# -*- coding: utf-8 -*-

import os
import tempfile
import unittest

from core import env_utils


class EnvUtilsTests(unittest.TestCase):
    def setUp(self):
        fd, self.path = tempfile.mkstemp(suffix=".env")
        os.close(fd)

    def tearDown(self):
        if os.path.exists(self.path):
            os.remove(self.path)

    def _write(self, text):
        with open(self.path, "w", encoding="utf-8") as f:
            f.write(text)

    def test_update_existing_key_preserves_others_and_comments(self):
        self._write("# header\nDNSE_API_KEY=old\nOTHER=keep\n")
        env_utils.update_env({"DNSE_API_KEY": "new"}, path=self.path)
        with open(self.path, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertIn("# header", content)
        self.assertIn("OTHER=keep", content)
        values = env_utils.load_env(self.path)
        self.assertEqual(values["DNSE_API_KEY"], "new")
        self.assertEqual(values["OTHER"], "keep")

    def test_append_new_key(self):
        self._write("EXISTING=1\n")
        env_utils.update_env({"DNSE_WS_ENABLED": "true"}, path=self.path)
        values = env_utils.load_env(self.path)
        self.assertEqual(values["EXISTING"], "1")
        self.assertEqual(values["DNSE_WS_ENABLED"], "true")

    def test_create_file_when_missing(self):
        os.remove(self.path)
        env_utils.update_env({"DNSE_STOCK_ACCOUNT_NO": "12345"}, path=self.path)
        self.assertEqual(env_utils.load_env(self.path)["DNSE_STOCK_ACCOUNT_NO"], "12345")

    def test_load_strips_quotes(self):
        self._write('KEY="quoted value"\n')
        self.assertEqual(env_utils.load_env(self.path)["KEY"], "quoted value")


if __name__ == "__main__":
    unittest.main()
