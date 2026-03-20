import unittest
import tempfile
from pathlib import Path
from unittest.mock import patch
from io import StringIO

import anagram as anagram_module
from anagram import AnagramStore

WORD_LIST = ["listen", "silent", "enlist", "inlets", "google", "gogle", "python"]


class TestAnagramKey(unittest.TestCase):
    def setUp(self):
        self.store = AnagramStore()

    def test_anagrams_share_key(self):
        self.assertEqual(self.store._key("listen"), self.store._key("silent"))
        self.assertEqual(self.store._key("listen"), self.store._key("enlist"))
        self.assertEqual(self.store._key("listen"), self.store._key("inlets"))

    def test_non_anagrams_differ(self):
        self.assertNotEqual(self.store._key("listen"), self.store._key("google"))

    def test_case_insensitive_key(self):
        self.assertEqual(self.store._key("Listen"), self.store._key("SILENT"))


class TestAnagramStore(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".txt")
        self.tmp.close()
        self.store_path = Path(self.tmp.name)
        self.store_path.write_text("")
        self.patcher = patch.object(anagram_module, "STORE", self.store_path)
        self.patcher.start()
        self.store = AnagramStore()

    def tearDown(self):
        self.patcher.stop()
        self.store_path.unlink(missing_ok=True)

    # --- add ---
    def test_add_persists_words(self):
        self.store.add(["listen", "silent"])
        all_words = [w for group in self.store._load().values() for w in group]
        self.assertIn("listen", all_words)
        self.assertIn("silent", all_words)

    def test_add_deduplicates(self):
        self.store.add(WORD_LIST)
        self.store.add(["listen", "google"])
        words = [w for group in self.store._load().values() for w in group]
        self.assertEqual(words.count("listen"), 1)
        self.assertEqual(words.count("google"), 1)

    def test_add_case_insensitive_dedup(self):
        self.store.add(["Listen"])
        self.store.add(["listen"])
        self.assertEqual(len(self.store._load()), 1)

    # --- check ---
    def test_check_anagrams(self):
        with patch("sys.stdout", new_callable=StringIO) as out:
            self.store.check("listen", "silent")
        self.assertIn("are anagrams", out.getvalue())

    def test_check_not_anagrams(self):
        with patch("sys.stdout", new_callable=StringIO) as out:
            self.store.check("listen", "google")
        self.assertIn("NOT", out.getvalue())

    # --- find ---
    def test_find_returns_anagrams(self):
        self.store.add(WORD_LIST)
        with patch("sys.stdout", new_callable=StringIO) as out:
            self.store.find("listen")
        result = out.getvalue()
        self.assertIn("silent", result)
        self.assertIn("enlist", result)
        self.assertIn("inlets", result)

    def test_find_excludes_query_word(self):
        self.store.add(WORD_LIST)
        with patch("sys.stdout", new_callable=StringIO) as out:
            self.store.find("listen")
        results = out.getvalue().split(": ", 1)[-1]  # strip "Anagrams of 'listen': "
        self.assertNotIn("listen", results)

    def test_find_no_match(self):
        self.store.add(WORD_LIST)
        with patch("sys.stdout", new_callable=StringIO) as out:
            self.store.find("python")
        self.assertIn("No anagrams", out.getvalue())

    # --- group ---
    def test_group_correct_families(self):
        self.store.add(WORD_LIST)
        with patch("sys.stdout", new_callable=StringIO) as out:
            self.store.group()
        output = out.getvalue()
        # listen/silent/enlist/inlets form one group, google and gogle are separate
        self.assertEqual(output.count("Group"), 4)

    def test_group_empty_store(self):
        with patch("sys.stdout", new_callable=StringIO) as out:
            self.store.group()
        self.assertIn("empty", out.getvalue())

    # --- export ---
    def test_export_creates_file(self):
        self.store.add(WORD_LIST)
        export_path = self.store_path.parent / "test_export.txt"
        self.store.export(str(export_path))
        self.assertTrue(export_path.exists())
        content = export_path.read_text()
        self.assertEqual(content.count("Group"), 4)
        export_path.unlink()

    def test_export_empty_store(self):
        with patch("sys.stdout", new_callable=StringIO) as out:
            self.store.export("irrelevant.txt")
        self.assertIn("empty", out.getvalue())


if __name__ == "__main__":
    unittest.main(verbosity=2)
