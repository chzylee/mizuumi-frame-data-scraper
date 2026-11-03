import os
import json
import shutil
import tempfile
import unittest
import filehelper


class TestWriteJsonIfChanged(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.path = os.path.join(self.dir, "Kouma-C.json")

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def test_first_write_creates(self):
        status = filehelper.write_json_if_changed(self.path, {"moves": [1, 2]})
        self.assertEqual(status, "created")
        self.assertTrue(os.path.exists(self.path))

    def test_identical_write_is_unchanged_and_does_not_touch_file(self):
        filehelper.write_json_if_changed(self.path, {"moves": [1, 2]})
        mtime_before = os.path.getmtime(self.path)
        status = filehelper.write_json_if_changed(self.path, {"moves": [1, 2]})
        # Unchanged data must not rewrite the file at all.
        self.assertEqual(status, "unchanged")
        self.assertEqual(os.path.getmtime(self.path), mtime_before)

    def test_changed_write_updates(self):
        filehelper.write_json_if_changed(self.path, {"moves": [1, 2]})
        status = filehelper.write_json_if_changed(self.path, {"moves": [1, 2, 3]})
        self.assertEqual(status, "updated")
        with open(self.path, encoding="utf-8") as json_file:
            self.assertEqual(json.load(json_file)["moves"], [1, 2, 3])

    def test_key_order_is_not_a_change(self):
        filehelper.write_json_if_changed(self.path, {"a": 1, "b": 2})
        status = filehelper.write_json_if_changed(self.path, {"b": 2, "a": 1})
        self.assertEqual(status, "unchanged")

    def test_content_hash_is_stable_and_order_independent(self):
        self.assertEqual(
            filehelper.content_hash({"a": 1, "b": 2}),
            filehelper.content_hash({"b": 2, "a": 1}),
        )
        self.assertNotEqual(
            filehelper.content_hash({"a": 1}),
            filehelper.content_hash({"a": 2}),
        )


class TestLocalDataDirs(unittest.TestCase):
    def test_only_the_scraped_directory_is_created(self):
        root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        scraped = os.path.join(root, "local-data", "scraped")
        original = filehelper.SCRAPED_DIRECTORY
        filehelper.SCRAPED_DIRECTORY = scraped
        self.addCleanup(setattr, filehelper, "SCRAPED_DIRECTORY", original)
        filehelper.ensure_local_data_dirs_exist()
        self.assertEqual(os.listdir(os.path.join(root, "local-data")), ["scraped"])
        self.assertFalse(hasattr(filehelper, "OVERRIDES_DIRECTORY"))


if __name__ == "__main__":
    unittest.main()
