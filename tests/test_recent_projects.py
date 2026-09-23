"""Tests for Recent Projects history tracking in codebone."""
import tempfile
import unittest
from pathlib import Path

from src.config import Config


class TestRecentProjects(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.config_path = Path(self.tmp_dir.name) / "config.json"
        self.config = Config(self.config_path)

    def tearDown(self):
        self.tmp_dir.cleanup()

    def test_default_empty_recent_projects(self):
        self.assertEqual(self.config.recent_projects, [])

    def test_add_and_mru_order(self):
        p1 = "/path/to/project_a"
        p2 = "/path/to/project_b"
        p3 = "/path/to/project_c"

        self.config.add_recent_project(p1)
        self.config.add_recent_project(p2)
        self.config.add_recent_project(p3)

        recents = self.config.recent_projects
        self.assertEqual(len(recents), 3)
        self.assertEqual(recents[0], p3)
        self.assertEqual(recents[1], p2)
        self.assertEqual(recents[2], p1)

        # Re-adding p1 should bump it to the front
        self.config.add_recent_project(p1)
        recents_after = self.config.recent_projects
        self.assertEqual(len(recents_after), 3)
        self.assertEqual(recents_after[0], p1)
        self.assertEqual(recents_after[1], p3)
        self.assertEqual(recents_after[2], p2)

    def test_max_limit_enforced(self):
        for i in range(15):
            self.config.add_recent_project(f"/path/to/proj_{i}")

        recents = self.config.recent_projects
        self.assertEqual(len(recents), 10)
        self.assertEqual(recents[0], "/path/to/proj_14")
        self.assertEqual(recents[-1], "/path/to/proj_5")

    def test_remove_recent_project(self):
        self.config.add_recent_project("/a")
        self.config.add_recent_project("/b")
        self.config.remove_recent_project("/a")

        self.assertEqual(self.config.recent_projects, ["/b"])

    def test_clear_recent_projects(self):
        self.config.add_recent_project("/a")
        self.config.add_recent_project("/b")
        self.config.clear_recent_projects()

        self.assertEqual(self.config.recent_projects, [])

    def test_persistence_across_instances(self):
        self.config.add_recent_project("/persistent/proj")

        # Load fresh instance from same file
        new_config = Config(self.config_path)
        self.assertEqual(new_config.recent_projects, ["/persistent/proj"])


if __name__ == "__main__":
    unittest.main()
