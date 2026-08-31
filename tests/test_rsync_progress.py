import io
import unittest

from support.rsync_progress import iter_lines, parse_line


class ParseLineTest(unittest.TestCase):
    def test_progress_line_gives_cumulative_bytes(self):
        self.assertEqual(parse_line("  1,234,567  12%   95.30MB/s    0:01:23 (xfr#42, to-chk=10/42)"), ("bytes", 1234567))
        self.assertEqual(parse_line("987654  3%  1.00MB/s  0:00:01"), ("bytes", 987654))

    def test_transferred_file_line(self):
        self.assertEqual(parse_line(">f+++++++++|25165824|2024_01_01/DSC00001.ARW"), ("file", "2024_01_01/DSC00001.ARW"))
        self.assertEqual(parse_line(">f.st......|0|a|b.txt"), ("file", "a|b.txt"))

    def test_directories_and_noise_ignored(self):
        self.assertIsNone(parse_line("cd+++++++++|0|2024_01_01/"))
        self.assertIsNone(parse_line("sending incremental file list"))
        self.assertIsNone(parse_line(""))

    def test_error_lines(self):
        self.assertEqual(parse_line("rsync error: some files/attrs were not transferred (code 23) at main.c(1338)")[0], "error")
        self.assertEqual(parse_line("rsync: [sender] read errors mapping \"x\": Input/output error (5)")[0], "error")


class IterLinesTest(unittest.TestCase):
    def test_splits_on_cr_and_lf_across_chunks(self):
        class Chunky(io.BytesIO):
            def read1(self, n=-1):
                return super().read1(5)

        stream = Chunky(b"  100  1%  x\r  200  2%  x\r>f+++++++++|200|a.txt\n  300  3%  x\rtail")
        self.assertEqual(list(iter_lines(stream)), [
            "  100  1%  x", "  200  2%  x", ">f+++++++++|200|a.txt", "  300  3%  x", "tail",
        ])
