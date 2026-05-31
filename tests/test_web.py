from __future__ import annotations

import unittest

from babel_epub.web import _parse_multipart_form, render_index_html


class WebTests(unittest.TestCase):
    def test_web_shell_exposes_upload_provider_progress_and_downloads(self) -> None:
        html = render_index_html()

        self.assertIn("Upload Book", html)
        self.assertIn(".azw3", html)
        self.assertIn(".mobi", html)
        self.assertIn(".pdf", html)
        self.assertIn("API Provider", html)
        self.assertIn("Glossary", html)
        self.assertIn("Job Progress", html)
        self.assertIn("Download EPUB", html)
        self.assertIn("/api/jobs", html)
        self.assertIn("OpenAI Compatible", html)

    def test_multipart_parser_preserves_binary_file_content(self) -> None:
        body = (
            b"--abc\r\n"
            b'Content-Disposition: form-data; name="epub"; filename="book.epub"\r\n'
            b"Content-Type: application/epub+zip\r\n\r\n"
            b"PK\x03\x04binary payload \x00 \r\n"
            b"--abc\r\n"
            b'Content-Disposition: form-data; name="target_language"\r\n\r\n'
            b"Simplified Chinese\r\n"
            b"--abc--\r\n"
        )
        form = _parse_multipart_form("multipart/form-data; boundary=abc", body)

        self.assertEqual(form["epub"].filename, "book.epub")
        self.assertEqual(form["epub"].content, b"PK\x03\x04binary payload \x00 ")
        self.assertEqual(form["target_language"].value, "Simplified Chinese")


if __name__ == "__main__":
    unittest.main()
