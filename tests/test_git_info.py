import os
import unittest
from subprocess import CompletedProcess
from unittest.mock import patch

from support.git_info import GitData


class TestGitData(unittest.TestCase):
    @patch("support.git_info.subprocess.run")
    def test_reads_latest_commit_metadata(self, run):
        commit_hash = "0123456789abcdef0123456789abcdef01234567"
        commit_date = "2026-09-02T10:20:30+02:00"
        run.return_value = CompletedProcess(
            args=[], returncode=0, stdout=f"{commit_hash}\n{commit_date}\n", stderr=""
        )

        git_data = GitData()

        self.assertEqual(git_data.code_id(), commit_hash)
        self.assertEqual(git_data.code_date(), commit_date)
        repo_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        run.assert_called_once_with(
            ["git", "-C", repo_dir, "log", "-1", "--format=%H%n%cI"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )

    @patch("support.git_info.LOGGER.warning")
    @patch("support.git_info.subprocess.run")
    def test_command_failure_returns_unknown_and_warns_once(self, run, warning):
        run.return_value = CompletedProcess(
            args=[], returncode=128, stdout="", stderr="fatal: not a git repository"
        )

        git_data = GitData()

        self.assertEqual(git_data.code_id(), "unknown")
        self.assertEqual(git_data.code_date(), "unknown")
        self.assertEqual(warning.call_count, 1)


if __name__ == "__main__":
    unittest.main()
