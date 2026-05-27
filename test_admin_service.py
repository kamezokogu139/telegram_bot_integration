import json
import os
import tempfile
import unittest
from unittest.mock import patch

import admin_service


class AdminServiceStorageTests(unittest.TestCase):
    def test_corrupt_admins_file_does_not_crash_auth_checks(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            admins_path = os.path.join(tmpdir, "admins.json")
            with open(admins_path, "w") as f:
                f.write("{")

            with patch.object(admin_service, "ADMINS_FILE", admins_path):
                try:
                    approved = admin_service.is_approved(123)
                except json.JSONDecodeError as exc:
                    self.fail(f"is_approved should not crash on corrupt admins.json: {exc}")

            self.assertFalse(approved)

    def test_non_object_admins_file_does_not_crash_auth_checks(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            admins_path = os.path.join(tmpdir, "admins.json")
            with open(admins_path, "w") as f:
                json.dump([], f)

            with patch.object(admin_service, "ADMINS_FILE", admins_path):
                try:
                    approved = admin_service.is_approved(123)
                except AttributeError as exc:
                    self.fail(f"is_approved should not crash on malformed admins.json: {exc}")

            self.assertFalse(approved)

    def test_failed_admins_write_keeps_existing_file_intact(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            admins_path = os.path.join(tmpdir, "admins.json")
            original = {"owner": 7, "approved": [8]}
            with open(admins_path, "w") as f:
                json.dump(original, f)

            def failing_dump(data, fp, indent=None):
                fp.write("{")
                raise RuntimeError("simulated write failure")

            with (
                patch.object(admin_service, "ADMINS_FILE", admins_path),
                patch.object(admin_service.json, "dump", failing_dump),
            ):
                with self.assertRaises(RuntimeError):
                    admin_service._write({"owner": 9, "approved": []})

            with open(admins_path, "r") as f:
                self.assertEqual(json.load(f), original)


if __name__ == "__main__":
    unittest.main()
