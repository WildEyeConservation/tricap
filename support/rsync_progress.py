"""Parse the live output of an rsync run for progress reporting."""

from __future__ import annotations

import re
from collections.abc import Iterator
from typing import Any, Protocol

# %b makes rsync print the per-file line when the transfer finishes, not when it starts.
RSYNC_PROGRESS_ARGS = ["--info=progress2", "--out-format=%i|%b|%n"]

# progress2 line, e.g. "  1,234,567  12%   95.30MB/s    0:01:23 (xfr#42, to-chk=10/42)"
_PROGRESS = re.compile(r"^\s*([\d,]+)\s+\d+%")


class SupportsRead1(Protocol):
    """A binary stream that returns whatever is available without blocking for a full buffer."""

    def read1(self, size: int = ..., /) -> bytes: ...


def iter_lines(stream: SupportsRead1) -> Iterator[str]:
    """Yield output lines. progress2 ends lines with \r, everything else with \n."""
    buf = b""
    while chunk := stream.read1(8192):
        buf += chunk
        *lines, buf = re.split(rb"[\r\n]", buf)
        for raw in lines:
            if raw.strip():
                yield raw.decode("utf-8", "replace")
    if buf.strip():
        yield buf.decode("utf-8", "replace")


def parse_line(line: str) -> tuple[str, Any] | None:
    """Classify a line as ("bytes", total_so_far), ("file", name), ("error", text) or None."""
    m = _PROGRESS.match(line)
    if m:
        return "bytes", int(m.group(1).replace(",", ""))
    if line.startswith("rsync"):  # "rsync: ..." and "rsync error: ..."
        return "error", line.strip()
    parts = line.split("|", 2)
    if len(parts) == 3 and len(parts[0]) >= 2 and parts[0][0] in "<>" and parts[0][1] == "f":
        return "file", parts[2]
    return None
