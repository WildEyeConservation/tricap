import logging
import os
import re
import subprocess
from datetime import datetime

LOGGER = logging.getLogger(__name__)
UNKNOWN = "unknown"


class GitData:
    def __init__(self, repo_dir=None):
        if repo_dir is None:
            repo_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

        self._code_id = UNKNOWN
        self._code_date = UNKNOWN

        try:
            result = subprocess.run(
                ["git", "-C", repo_dir, "log", "-1", "--format=%H%n%cI"],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
        except (OSError, subprocess.SubprocessError) as error:
            LOGGER.warning("Unable to read Git metadata: %s", error)
            return

        if result.returncode != 0:
            LOGGER.warning("Unable to read Git metadata: git exited with code %s", result.returncode)
            return

        lines = result.stdout.splitlines()
        if len(lines) != 2 or not self._valid_hash(lines[0]) or not self._valid_date(lines[1]):
            LOGGER.warning("Unable to read Git metadata: unparseable git output")
            return

        self._code_id, self._code_date = lines

    @staticmethod
    def _valid_hash(value):
        return re.fullmatch(r"[0-9a-fA-F]{40}", value) is not None

    @staticmethod
    def _valid_date(value):
        try:
            datetime.fromisoformat(value)
        except (TypeError, ValueError):
            return False
        return True

    def code_id(self):
        return self._code_id

    def code_date(self):
        return self._code_date
