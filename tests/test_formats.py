from __future__ import annotations

import tempfile
import unittest
from argparse import Namespace
from pathlib import Path

from babel_epub.formats import (
    BookFormatError,
    detect_input_format,
    supported_input_extensions,
)
from babel_epub.pipeline import command_prepare, read_jsonl


class FormatTests(unittest.TestCase):
    def test_supported_formats_include_mainstream_ebook_extensions(self) -> None:
        extensions = supported_input_extensions()

        for extension in {
            ".epub",
            ".txt",
            ".html",
            ".htm",
            ".mobi",
            ".azw",
            ".azw3",
            ".kfx",
            ".pdf",
            ".fb2",
            ".docx",
            ".rtf",
            ".cbz",
            ".cbr",
        }:
            self.assertIn(extension, extensions)

    def test_txt_input_is_converted_to_epub_workspace_without_external_tools(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            input_book = tmp_path / "book.txt"
            input_book.write_text("Chapter One\n\nHello world.\n\nSecond paragraph.", encoding="utf-8")
            work_dir = tmp_path / "work"

            command_prepare(
                Namespace(
                    input_book=input_book,
                    input_epub=None,
                    work_dir=work_dir,
                    glossary=tmp_path / "translation_glossary.md",
                    target_language="Simplified Chinese",
                    max_blocks=10,
                    force=False,
                )
            )

            blocks = read_jsonl(work_dir / "pipeline" / "blocks.jsonl")
            metadata = (work_dir / "pipeline" / "input_format.json").read_text(encoding="utf-8")
            self.assertGreaterEqual(len(blocks), 2)
            self.assertIn("Hello world.", " ".join(row["source_text"] for row in blocks))
            self.assertIn('"input_format": ".txt"', metadata)
            self.assertTrue((work_dir / "input.epub").exists())

    def test_html_input_preserves_basic_emphasis_after_internal_conversion(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            input_book = tmp_path / "book.html"
            input_book.write_text("<h1>Start</h1><p>Hello <em>world</em>.</p>", encoding="utf-8")
            work_dir = tmp_path / "work"

            command_prepare(
                Namespace(
                    input_book=input_book,
                    input_epub=None,
                    work_dir=work_dir,
                    glossary=tmp_path / "translation_glossary.md",
                    target_language="Simplified Chinese",
                    max_blocks=10,
                    force=False,
                )
            )

            blocks = read_jsonl(work_dir / "pipeline" / "blocks.jsonl")
            self.assertEqual([row["tag"] for row in blocks], ["h1", "p"])
            self.assertIn("<em>world</em>", blocks[1]["source_html"])

    def test_calibre_backed_format_reports_clear_error_when_converter_is_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            input_book = tmp_path / "book.azw3"
            input_book.write_bytes(b"not really azw3")

            with self.assertRaisesRegex(BookFormatError, "ebook-convert"):
                detect_input_format(input_book).to_epub(
                    input_book,
                    tmp_path / "out.epub",
                    converter_path="/definitely/missing/ebook-convert",
                )


if __name__ == "__main__":
    unittest.main()
