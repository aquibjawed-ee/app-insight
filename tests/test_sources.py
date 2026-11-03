"""Source lists: every supported format yields the same repositories, with optional columns, and nothing is fetched to read them."""
import os
import subprocess
import sys
import tempfile
import unittest
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
from app_insight import sources as SRC  # noqa: E402

SHEET = ('<?xml version="1.0"?><worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>'
         '<row r="1"><c r="A1" t="s"><v>0</v></c><c r="B1" t="s"><v>1</v></c></row>'
         '<row r="2"><c r="A2" t="s"><v>2</v></c><c r="B2" t="s"><v>3</v></c></row>'
         '<row r="3"><c r="A3" t="inlineStr"><is><t>git@gitlab.example.com:grp/orders.git</t></is></c></row></sheetData></worksheet>')
STRINGS = ('<?xml version="1.0"?><sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
           '<si><t>Repo URL</t></si><si><t>Team</t></si><si><t>https://github.com/acme/payments.git</t></si><si><t>payments</t></si></sst>')


class SourcesTest(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp(prefix="src-")

    def w(self, name, text):
        p = os.path.join(self.d, name)
        with open(p, "w") as fh:
            fh.write(text)
        return p

    def test_csv_with_header_reads_the_repo_column_and_optional_columns(self):
        p = self.w("r.csv", "Name,Repository,Branch,Team\npay,https://github.com/acme/payments.git,main,payments\n,git@gitlab.example.com:grp/orders.git,,\n")
        s = SRC.read_list(p)
        self.assertEqual([x.spec for x in s], ["https://github.com/acme/payments.git", "git@gitlab.example.com:grp/orders.git"])
        self.assertEqual((s[0].name, s[0].branch, s[0].team), ("pay", "main", "payments"))
        self.assertTrue(all(x.remote for x in s))
        self.assertEqual(s[1].slug(), "gitlab.example.com__grp__orders")  # host and full path: a clone folder per repository

    def test_csv_without_header_uses_the_first_column(self):
        s = SRC.read_list(self.w("r.csv", "https://github.com/acme/a.git,x\nhttps://github.com/acme/b.git,y\n"))
        self.assertEqual(len(s), 2)

    def test_txt_ignores_comments_and_reads_an_optional_branch(self):
        s = SRC.read_list(self.w("r.txt", "# estate\nhttps://github.com/acme/a.git develop\n\nhttps://github.com/acme/b.git # legacy\n"))
        self.assertEqual([(x.spec, x.branch) for x in s], [("https://github.com/acme/a.git", "develop"), ("https://github.com/acme/b.git", None)])

    def test_xlsx_is_read_without_extra_libraries(self):
        p = os.path.join(self.d, "r.xlsx")
        with zipfile.ZipFile(p, "w") as z:
            z.writestr("xl/sharedStrings.xml", STRINGS)
            z.writestr("xl/worksheets/sheet1.xml", SHEET)
        s = SRC.read_list(p)
        self.assertEqual([x.spec for x in s], ["https://github.com/acme/payments.git", "git@gitlab.example.com:grp/orders.git"])
        self.assertEqual(s[0].team, "payments")

    def test_a_folder_of_repositories_expands_to_each_repository(self):
        for n in ("a", "b"):
            os.makedirs(os.path.join(self.d, "estate", n))
            subprocess.run(["git", "init", "-q", os.path.join(self.d, "estate", n)], check=True)
        os.makedirs(os.path.join(self.d, "estate", "not-a-repo"))
        s = SRC.expand([os.path.join(self.d, "estate")])
        self.assertEqual(sorted(os.path.basename(x.spec) for x in s), ["a", "b"])

    def test_duplicates_are_dropped_and_a_missing_local_path_fails_alone(self):
        s = SRC.expand(["https://github.com/acme/a.git", "https://github.com/acme/a.git", os.path.join(self.d, "missing")])
        self.assertEqual(len(s), 2)
        SRC.fetch(s[1], os.path.join(self.d, "repos"))
        self.assertEqual((s[1].status, s[1].error), ("failed", "local path not found"))


if __name__ == "__main__":
    unittest.main()
