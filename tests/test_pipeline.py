from __future__ import annotations

import json
import tempfile
import unittest
import zipfile
from argparse import Namespace
from pathlib import Path

from babel_epub.pipeline import (
    command_apply,
    command_audit,
    command_prepare,
    command_validate_batches,
    read_jsonl,
    write_jsonl,
)


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def make_minimal_epub(path: Path) -> None:
    root = path.parent / "epub_src"
    write_text(root / "mimetype", "application/epub+zip")
    write_text(
        root / "META-INF" / "container.xml",
        """<?xml version="1.0"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles>
    <rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/>
  </rootfiles>
</container>
""",
    )
    write_text(
        root / "OEBPS" / "content.opf",
        """<?xml version="1.0" encoding="utf-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="2.0" unique-identifier="bookid">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:title>Sample Book</dc:title>
    <dc:language>en</dc:language>
    <dc:identifier id="bookid">sample</dc:identifier>
  </metadata>
  <manifest>
    <item id="ncx" href="toc.ncx" media-type="application/x-dtbncx+xml"/>
    <item id="c1" href="chapter1.xhtml" media-type="application/xhtml+xml"/>
    <item id="style" href="style.css" media-type="text/css"/>
  </manifest>
  <spine toc="ncx">
    <itemref idref="c1"/>
  </spine>
</package>
""",
    )
    write_text(root / "OEBPS" / "style.css", "p { font-style: normal; }\n")
    write_text(
        root / "OEBPS" / "toc.ncx",
        """<?xml version="1.0" encoding="utf-8"?>
<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" version="2005-1">
  <head><meta name="dtb:uid" content="sample"/></head>
  <docTitle><text>Sample Book</text></docTitle>
  <navMap>
    <navPoint id="nav1" playOrder="1">
      <navLabel><text>Chapter 1</text></navLabel>
      <content src="chapter1.xhtml"/>
    </navPoint>
  </navMap>
</ncx>
""",
    )
    write_text(
        root / "OEBPS" / "chapter1.xhtml",
        """<?xml version="1.0" encoding="utf-8"?>
<html xmlns="http://www.w3.org/1999/xhtml">
  <head><title>Chapter 1</title><link rel="stylesheet" href="style.css"/></head>
  <body>
    <h1 id="chapter-1">Chapter One</h1>
    <p class="body">Hello <em>world</em>.</p>
  </body>
</html>
""",
    )
    with zipfile.ZipFile(path, "w") as archive:
        archive.write(root / "mimetype", "mimetype", compress_type=zipfile.ZIP_STORED)
        for file_path in sorted(root.rglob("*")):
            if file_path.is_dir() or file_path.name == "mimetype":
                continue
            archive.write(file_path, file_path.relative_to(root).as_posix(), compress_type=zipfile.ZIP_DEFLATED)


class PipelineTests(unittest.TestCase):
    def test_prepare_validate_apply_and_audit(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            input_epub = tmp_path / "input.epub"
            make_minimal_epub(input_epub)
            work_dir = tmp_path / "work"
            glossary = tmp_path / "translation_glossary.md"

            command_prepare(
                Namespace(
                    input_epub=input_epub,
                    work_dir=work_dir,
                    glossary=glossary,
                    target_language="Simplified Chinese",
                    max_blocks=10,
                    force=False,
                )
            )

            batch_path = work_dir / "pipeline" / "batches" / "batch_001_chapter1_01.jsonl"
            translated_path = work_dir / "pipeline" / "translated" / "batch_001_chapter1_01.translated.jsonl"
            source_rows = read_jsonl(batch_path)
            self.assertEqual([row["tag"] for row in source_rows], ["h1", "p"])
            write_jsonl(
                translated_path,
                [
                    {"id": source_rows[0]["id"], "translated_html": '<h1 id="chapter-1">第一章</h1>'},
                    {
                        "id": source_rows[1]["id"],
                        "translated_html": '<p class="body">你好，<em>世界</em>。</p>',
                    },
                ],
            )

            command_validate_batches(Namespace(pipeline_dir=work_dir / "pipeline"))
            output_epub = tmp_path / "output.epub"
            command_apply(
                Namespace(
                    work_dir=work_dir,
                    output_epub=output_epub,
                    title="示例书",
                    language="zh-CN",
                )
            )
            command_audit(Namespace(epub=output_epub, out=tmp_path / "audit.json"))

            with zipfile.ZipFile(output_epub) as archive:
                self.assertIsNone(archive.testzip())
                content = archive.read("OEBPS/chapter1.xhtml").decode("utf-8")
                opf = archive.read("OEBPS/content.opf").decode("utf-8")
            self.assertIn("第一章", content)
            self.assertIn("你好，", content)
            self.assertIn("<dc:language>zh-CN</dc:language>", opf)
            self.assertIn(
                '"output_format": ".epub"',
                (work_dir / "pipeline" / "output_format.json").read_text(encoding="utf-8"),
            )

    def test_placeholder_translation_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            input_epub = tmp_path / "input.epub"
            make_minimal_epub(input_epub)
            work_dir = tmp_path / "work"
            command_prepare(
                Namespace(
                    input_epub=input_epub,
                    work_dir=work_dir,
                    glossary=tmp_path / "translation_glossary.md",
                    target_language="Simplified Chinese",
                    max_blocks=10,
                    force=False,
                )
            )
            batch_path = work_dir / "pipeline" / "batches" / "batch_001_chapter1_01.jsonl"
            translated_path = work_dir / "pipeline" / "translated" / "batch_001_chapter1_01.translated.jsonl"
            source_rows = read_jsonl(batch_path)
            write_jsonl(
                translated_path,
                [
                    {"id": source_rows[0]["id"], "translated_html": '<h1 id="chapter-1">第1段译文。</h1>'},
                    {"id": source_rows[1]["id"], "translated_html": '<p class="body">第2段译文。</p>'},
                ],
            )
            with self.assertRaises(SystemExit):
                command_validate_batches(Namespace(pipeline_dir=work_dir / "pipeline"))
            report = json.loads((work_dir / "pipeline" / "batch_validation.json").read_text(encoding="utf-8"))
            self.assertGreaterEqual(report["issue_count"], 2)


if __name__ == "__main__":
    unittest.main()
