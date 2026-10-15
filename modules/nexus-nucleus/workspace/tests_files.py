"""
Step 5 — the project file viewer (docs/NUCLEUS-REVAMP.md §3).

Browse, download, view-as-HTML over the project's folder, with the walls
proven: paths can't leave the folder (`..`, absolute, symlinks out), big
files are download-only, binary is never "rendered", rendered pages carry
CSP sandbox, and someone without the project gets a 404 like everywhere else.
"""
import os
import shutil
import tempfile
from pathlib import Path

from django.test import Client

from chat.tests import MentionRightFixture
from nucleus.models import CompanyAccess, User
from workspace.services import get_project_folder_name


class FileViewerTests(MentionRightFixture):
    def setUp(self):
        super().setUp()
        self.tmp = tempfile.mkdtemp(prefix="nx-files-test-")
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        override = self.settings(PROJECTS_ROOT=Path(self.tmp))
        override.enable()
        self.addCleanup(override.disable)

        self.root = Path(self.tmp) / get_project_folder_name(self.p1)
        (self.root / "sub").mkdir(parents=True)
        (self.root / "readme.md").write_text("# Hello\n\nSome **bold** text.\n")
        (self.root / "script.py").write_text("print('hi')\n")
        (self.root / "data.bin").write_bytes(b"\x00\x01\x02\x03")
        (self.root / "sub" / "note.txt").write_text("plain note")
        # A symlink pointing OUT of the project folder — must never be served.
        os.symlink("/etc/hostname", self.root / "sneaky")

        self.base = f"/api/v1/projects/{self.p1.id}/files/"

    def listing(self, user, path=""):
        return self.call("get", self.base, user, {"path": path} if path else None)

    def content(self, user, path, as_html=False):
        params = {"path": path}
        if as_html:
            params["as"] = "html"
        return self.call("get", f"{self.base}content/", user, params)

    @staticmethod
    def body(response) -> bytes:
        if hasattr(response, "streaming_content"):
            return b"".join(response.streaming_content)
        return response.content

    # ── Browse ────────────────────────────────────────────────────────────

    def test_listing_shows_folders_first_then_files(self):
        r = self.listing(self.owner)
        self.assertEqual(r.status_code, 200, r.content)
        data = r.json()
        self.assertEqual(data["path"], "")
        self.assertFalse(data["truncated"])
        names = [e["name"] for e in data["entries"]]
        self.assertEqual(names[0], "sub")                      # folders first
        self.assertEqual(data["entries"][0]["type"], "dir")
        self.assertIn("readme.md", names)
        readme = next(e for e in data["entries"] if e["name"] == "readme.md")
        self.assertEqual(readme["type"], "file")
        self.assertGreater(readme["size"], 0)
        self.assertTrue(readme["modified"])

    def test_listing_a_subfolder(self):
        r = self.listing(self.owner, "sub")
        self.assertEqual(r.status_code, 200, r.content)
        data = r.json()
        self.assertEqual(data["path"], "sub")
        self.assertEqual([e["name"] for e in data["entries"]], ["note.txt"])

    def test_a_viewer_can_browse_but_an_outsider_404s(self):
        r = self.listing(self.vera)                            # company Viewer
        self.assertEqual(r.status_code, 200, r.content)
        outsider = User.objects.create_user(username="out", email="out@acme.test", password="x")
        CompanyAccess.objects.create(company=self.company, user=outsider, role="member", invited_by=self.owner)
        r = self.listing(outsider)                             # no role → no project
        self.assertEqual(r.status_code, 404, r.content)

    def test_a_project_with_no_folder_yet_is_a_409(self):
        r = self.call("get", f"/api/v1/projects/{self.p2.id}/files/", self.owner)
        self.assertEqual(r.status_code, 409, r.content)

    # ── Download ──────────────────────────────────────────────────────────

    def test_download_returns_the_bytes_as_an_attachment(self):
        r = self.content(self.owner, "script.py")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(self.body(r), b"print('hi')\n")
        self.assertIn("attachment", r.headers.get("Content-Disposition", ""))

    def test_missing_file_and_mixed_up_kinds(self):
        self.assertEqual(self.content(self.owner, "nope.txt").status_code, 404)
        self.assertEqual(self.content(self.owner, "sub").status_code, 400)      # a folder
        self.assertEqual(self.listing(self.owner, "readme.md").status_code, 400)  # a file

    # ── The wall ──────────────────────────────────────────────────────────

    def test_paths_cannot_leave_the_project_folder(self):
        self.assertEqual(self.listing(self.owner, "../").status_code, 400)
        self.assertEqual(self.content(self.owner, "../../etc/passwd").status_code, 400)
        # A leading slash is read project-relative (friendly to frontends),
        # so this asks for <project>/etc/passwd — which simply doesn't exist.
        self.assertEqual(self.content(self.owner, "/etc/passwd").status_code, 404)
        # A symlink that points out resolves out — refused the same way.
        self.assertEqual(self.content(self.owner, "sneaky").status_code, 400)
        self.assertEqual(self.content(self.owner, "sneaky", as_html=True).status_code, 400)

    # ── View as HTML ──────────────────────────────────────────────────────

    def test_markdown_views_as_a_sandboxed_html_page(self):
        r = self.content(self.owner, "readme.md", as_html=True)
        self.assertEqual(r.status_code, 200, r.content)
        self.assertIn("text/html", r.headers["Content-Type"])
        self.assertEqual(r.headers.get("Content-Security-Policy"), "sandbox")
        self.assertIn(b"Hello", r.content)
        # Rendered (markdown installed) or readable escaped text (not yet) —
        # both are a page, never a blank or an error.
        self.assertTrue(b"<h1>" in r.content or b"<pre>" in r.content, r.content)

    def test_code_views_as_html_too(self):
        r = self.content(self.owner, "script.py", as_html=True)
        self.assertEqual(r.status_code, 200, r.content)
        self.assertIn(b"print", r.content)

    def test_big_files_are_download_only(self):
        from workspace import files as file_viewer
        (self.root / "big.txt").write_bytes(b"x" * (file_viewer.RENDER_MAX_BYTES + 1))
        r = self.content(self.owner, "big.txt", as_html=True)
        self.assertEqual(r.status_code, 413)
        r = self.content(self.owner, "big.txt")                # download still fine
        self.assertEqual(r.status_code, 200)

    def test_binary_is_never_rendered(self):
        r = self.content(self.owner, "data.bin", as_html=True)
        self.assertEqual(r.status_code, 415)
        r = self.content(self.owner, "data.bin")               # download still fine
        self.assertEqual(r.status_code, 200)
        self.assertEqual(self.body(r), b"\x00\x01\x02\x03")
