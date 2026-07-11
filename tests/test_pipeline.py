from __future__ import annotations

import json
import stat
import tempfile
import unittest
import zipfile
from argparse import Namespace
from pathlib import Path

from babel_epub.pipeline import (
    classify_doc,
    command_apply,
    command_audit,
    command_prepare,
    command_validate_batches,
    extract_name_candidates,
    has_translatable_text,
    safe_extract,
    validate_translation_rows,
    read_jsonl,
    write_batches,
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


def make_epub3_nav_epub(path: Path) -> None:
    root = path.parent / "epub3_src"
    write_text(root / "mimetype", "application/epub+zip")
    write_text(
        root / "META-INF" / "container.xml",
        """<?xml version="1.0"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles><rootfile full-path="EPUB/package.opf" media-type="application/oebps-package+xml"/></rootfiles>
</container>
""",
    )
    write_text(
        root / "EPUB" / "package.opf",
        """<?xml version="1.0" encoding="utf-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="bookid">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:title>EPUB3</dc:title><dc:language>ja</dc:language></metadata>
  <manifest>
    <item id="nav" href="nav/nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>
    <item id="c1" href="chapter1.xhtml" media-type="application/xhtml+xml"/>
  </manifest>
  <spine><itemref idref="c1"/></spine>
</package>
""",
    )
    write_text(
        root / "EPUB" / "nav" / "nav.xhtml",
        """<?xml version="1.0" encoding="utf-8"?>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops">
  <body><nav epub:type="toc"><ol><li><a href="../chapter1.xhtml">第一章 ナビ</a></li></ol></nav></body>
</html>
""",
    )
    write_text(
        root / "EPUB" / "chapter1.xhtml",
        """<?xml version="1.0" encoding="utf-8"?>
<html xmlns="http://www.w3.org/1999/xhtml"><body><h1 id="c1">第一章</h1><p>こんにちは世界。</p></body></html>
""",
    )
    with zipfile.ZipFile(path, "w") as archive:
        archive.write(root / "mimetype", "mimetype", compress_type=zipfile.ZIP_STORED)
        for file_path in sorted(root.rglob("*")):
            if file_path.is_dir() or file_path.name == "mimetype":
                continue
            archive.write(file_path, file_path.relative_to(root).as_posix(), compress_type=zipfile.ZIP_DEFLATED)


def make_html_resource_epub(path: Path) -> None:
    root = path.parent / "html_src"
    write_text(root / "mimetype", "application/epub+zip")
    write_text(
        root / "META-INF" / "container.xml",
        """<?xml version="1.0"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles><rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/></rootfiles>
</container>
""",
    )
    write_text(
        root / "OEBPS" / "content.opf",
        """<?xml version="1.0" encoding="utf-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="bookid">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:title>HTML Book</dc:title><dc:language>en</dc:language></metadata>
  <manifest>
    <item id="c1" href="chapter1.html" media-type="text/html"/>
    <item id="c2" href="chapter2.html" media-type="text/html"/>
    <item id="missing-style" href="styles/missing.css" media-type="text/css"/>
  </manifest>
  <spine><itemref idref="c1"/><itemref idref="c2"/></spine>
</package>
""",
    )
    write_text(
        root / "OEBPS" / "chapter1.html",
        """<?xml version="1.0" encoding="utf-8"?>
<html xmlns="http://www.w3.org/1999/xhtml"><body>
  <p id="start">Hello from HTML.</p>
  <a href="chapter2.html#missing">Broken anchor</a>
  <a href="mailto:test@example.com">Email</a>
  <img src="images/missing.png" alt="Missing" />
  <img src="data:image/png;base64,AAAA" alt="Inline" />
  <link href="styles/missing.css" rel="stylesheet" />
</body></html>
""",
    )
    write_text(
        root / "OEBPS" / "chapter2.html",
        """<?xml version="1.0" encoding="utf-8"?>
<html xmlns="http://www.w3.org/1999/xhtml"><body><p id="present">Second.</p></body></html>
""",
    )
    with zipfile.ZipFile(path, "w") as archive:
        archive.write(root / "mimetype", "mimetype", compress_type=zipfile.ZIP_STORED)
        for file_path in sorted(root.rglob("*")):
            if file_path.is_dir() or file_path.name == "mimetype":
                continue
            archive.write(file_path, file_path.relative_to(root).as_posix(), compress_type=zipfile.ZIP_DEFLATED)


class PipelineTests(unittest.TestCase):

    def test_safe_extract_rejects_path_traversal_absolute_and_symlink_entries(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            outside = tmp_path / "escape.txt"
            cases = [
                ("../escape.txt", None),
                ("/tmp/escape.txt", None),
                ("C:/temp/escape.txt", None),
                ("OEBPS/link", stat.S_IFLNK | 0o777),
            ]
            for index, (entry_name, mode) in enumerate(cases):
                archive_path = tmp_path / f"bad-{index}.epub"
                with zipfile.ZipFile(archive_path, "w") as archive:
                    if mode is None:
                        archive.writestr(entry_name, "bad")
                    else:
                        info = zipfile.ZipInfo(entry_name)
                        info.external_attr = mode << 16
                        archive.writestr(info, "target")
                with zipfile.ZipFile(archive_path) as archive:
                    with self.assertRaisesRegex(ValueError, "unsafe"):
                        safe_extract(archive, tmp_path / f"out-{index}")
            self.assertFalse(outside.exists())

    def test_audit_rejects_malicious_epub_without_writing_outside_target(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            bad_epub = tmp_path / "bad.epub"
            escaped = tmp_path / "evil.txt"
            with zipfile.ZipFile(bad_epub, "w") as archive:
                archive.writestr("mimetype", "application/epub+zip")
                archive.writestr("../evil.txt", "owned")
            with self.assertRaisesRegex(ValueError, "unsafe"):
                command_audit(Namespace(epub=bad_epub, out=tmp_path / "audit.json"))
            self.assertFalse(escaped.exists())

    def test_validate_translation_rows_rejects_id_count_order_and_structure_errors(self) -> None:
        batch_rows = [
            {"id": "a", "source_html": '<p class="body" title="t">Hello <a href="x.xhtml#n" id="n">world</a>.</p>'},
            {"id": "b", "source_html": '<p><img src="cover.jpg" alt="Cover" /></p>'},
        ]
        self.assertIn(
            "duplicate translated row id: a",
            validate_translation_rows(
                batch_rows,
                [
                    {"id": "a", "translated_html": '<p class="body" title="t">你好 <a href="x.xhtml#n" id="n">世界</a>。</p>'},
                    {"id": "a", "translated_html": '<p>重复</p>'},
                ],
            ),
        )
        missing_extra = validate_translation_rows(
            batch_rows,
            [
                {"id": "a", "translated_html": '<p class="body" title="t">你好 <a href="x.xhtml#n" id="n">世界</a>。</p>'},
                {"id": "c", "translated_html": "<p>额外</p>"},
            ],
        )
        self.assertIn("missing translated row for b", missing_extra)
        self.assertIn("unexpected translated row id: c", missing_extra)
        self.assertIn("translated row order changed: expected source batch order", missing_extra)
        reordered = validate_translation_rows(
            batch_rows,
            [
                {"id": "b", "translated_html": '<p><img src="cover.jpg" alt="Cover" /></p>'},
                {"id": "a", "translated_html": '<p class="body" title="t">你好 <a href="x.xhtml#n" id="n">世界</a>。</p>'},
            ],
        )
        self.assertIn("translated row order changed: expected source batch order", reordered)
        bad_structure = validate_translation_rows(
            batch_rows,
            [
                {"id": "a", "translated_html": '<p class="changed" title="t">你好 <a href="changed.xhtml#n" id="n">世界</a>。</p>'},
                {"id": "b", "translated_html": '<p><img src="cover.jpg" alt="Changed" /></p>'},
            ],
        )
        self.assertTrue(any("attribute 'class' changed" in issue for issue in bad_structure))
        self.assertTrue(any("href" in issue for issue in bad_structure))
        self.assertTrue(any("alt" in issue for issue in bad_structure))
        missing_html = validate_translation_rows(batch_rows, [{"id": "a"}, {"id": "b", "translated_html": 7}])
        self.assertIn("missing translated_html for a", missing_html)
        self.assertIn("missing translated_html for b", missing_html)


    def test_has_translatable_text_is_unicode_aware(self) -> None:
        for text in ("你好世界", "こんにちは世界", "안녕하세요", "Привет мир", "مرحبا بالعالم", "Hello world"):
            self.assertTrue(has_translatable_text(text), text)
        for text in ("12345", "— 42 —", "page_12", "#fff", "margin-left: 12px"):
            self.assertFalse(has_translatable_text(text), text)

    def test_epub3_nav_labels_are_used_for_chapters(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            input_epub = tmp_path / "epub3.epub"
            make_epub3_nav_epub(input_epub)
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
            chapters = json.loads((work_dir / "pipeline" / "chapters.json").read_text(encoding="utf-8"))
            self.assertEqual(chapters[0]["label"], "第一章 ナビ")
            rows = read_jsonl(work_dir / "pipeline" / "blocks.jsonl")
            self.assertTrue(any(row["source_text"] == "こんにちは世界。" for row in rows))

    def test_audit_scans_html_spine_and_local_resources(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            input_epub = tmp_path / "html.epub"
            make_html_resource_epub(input_epub)
            with self.assertRaises(SystemExit):
                command_audit(Namespace(epub=input_epub, out=tmp_path / "audit.json"))
            report = json.loads((tmp_path / "audit.json").read_text(encoding="utf-8"))
            self.assertIn("OEBPS/styles/missing.css", report["missing_manifest_items"])
            self.assertTrue(any("chapter2.html#missing" in item for item in report["broken_internal_links"]))
            self.assertTrue(any("images/missing.png" in item for item in report["broken_resource_links"]))
            self.assertTrue(any("styles/missing.css" in item for item in report["broken_resource_links"]))
            self.assertGreaterEqual(report["external_links"], 1)

    def test_classify_doc_accepts_chapter_titles_with_suffixes(self) -> None:
        self.assertEqual(classify_doc("Chapter 1"), "chapter")
        self.assertEqual(classify_doc("Chapter 1 - THE GREAT STORM CHAMBER LIBRARY"), "chapter")
        self.assertEqual(classify_doc("Chapter 12: The Road"), "chapter")

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


    def test_write_batches_respects_character_and_token_budgets(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            pipeline_dir = Path(tmp)
            rows = [
                {
                    "id": f"chapter.xhtml::{index:04d}",
                    "order": 1,
                    "file": "chapter.xhtml",
                    "seq": index,
                    "tag": "p",
                    "chapter_label": "Chapter",
                    "chapter_kind": "chapter",
                    "source_text": "x" * 20,
                    "source_html": "x" * 20,
                }
                for index in range(1, 5)
            ]
            write_jsonl(pipeline_dir / "blocks.jsonl", rows)

            batches = write_batches(pipeline_dir, max_blocks=10, max_chars=45)

            self.assertEqual([batch["block_count"] for batch in batches], [2, 2])
            self.assertEqual([batch["source_chars"] for batch in batches], [40, 40])
            self.assertEqual([batch["estimated_tokens"] for batch in batches], [10, 10])

            batches = write_batches(pipeline_dir, max_blocks=10, max_tokens=5)
            self.assertEqual([batch["block_count"] for batch in batches], [1, 1, 1, 1])

            with self.assertRaisesRegex(ValueError, "max_chars"):
                write_batches(pipeline_dir, max_blocks=10, max_chars=0)

    def test_name_candidates_reuse_glossary_noise_filter(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            pipeline_dir = Path(tmp)
            write_jsonl(
                pipeline_dir / "blocks.jsonl",
                [
                    {"id": "chapter.xhtml::0001", "source_text": "Logan met Grace. Yeah, Okay, Dad, Where."},
                    {"id": "chapter.xhtml::0002", "source_text": "Grace called Logan. Fuck, God, Twitter, Not."},
                    {"id": "chapter.xhtml::0003", "source_text": "Logan found Grace on Friday. Because, Which, Coach, Jesus."},
                    {"id": "chapter.xhtml::0004", "source_text": "Logan’s grin met Grace’s laugh."},
                    {
                        "id": "chapter.xhtml::0005",
                        "source_text": "Because. Which. Coach. Jesus. Where. Not. Friday. Logan’s Grace’s. Hell. Once. Oh God. T-shirt.",
                    },
                    {"id": "chapter.xhtml::0006", "source_text": "Hell. Once. Oh God. T-shirt."},
                    {
                        "id": "chapter.xhtml::0007",
                        "source_text": "From. Its. Each. Despite. Quickly. Slowly. Welcome. Stay. Far. Time. No-one. Aargh. Urrgh. Wuh-wuh. The Skyraider.",
                    },
                    {
                        "id": "chapter.xhtml::0008",
                        "source_text": "From. Its. Each. Despite. Quickly. Slowly. Welcome. Stay. Far. Time. No-one. Aargh. Urrgh. Wuh-wuh. The Skyraider.",
                    },
                    {
                        "id": "chapter.xhtml::0009",
                        "source_text": "Several. Around. Pass. Steady. More. Fare. Believe. Fifty. Study. Stop. Aye. Darkness.",
                    },
                    {
                        "id": "chapter.xhtml::0010",
                        "source_text": "Several. Around. Pass. Steady. More. Fare. Believe. Fifty. Study. Stop. Aye. Darkness.",
                    },
                    {
                        "id": "chapter.xhtml::0011",
                        "source_text": "Apart. Dead. Ever. Flying. Loom. Sometimes. Wahoo.",
                    },
                    {
                        "id": "chapter.xhtml::0012",
                        "source_text": "Apart. Dead. Ever. Flying. Loom. Sometimes. Wahoo.",
                    },
                    {
                        "id": "chapter.xhtml::0013",
                        "source_text": "Beneath. Delicious. Help. Looking.",
                    },
                    {
                        "id": "chapter.xhtml::0014",
                        "source_text": "Beneath. Delicious. Help. Looking.",
                    },
                    {
                        "id": "chapter.xhtml::0015",
                        "source_text": "Heart. Leave. Nor.",
                    },
                    {
                        "id": "chapter.xhtml::0016",
                        "source_text": "Heart. Leave. Nor.",
                    },
                    {
                        "id": "chapter.xhtml::0017",
                        "source_text": "Down.",
                    },
                    {
                        "id": "chapter.xhtml::0018",
                        "source_text": "Down.",
                    },
                ],
            )

            rows = extract_name_candidates(pipeline_dir, min_count=2)
            by_term = {row["term"]: row for row in rows}

            self.assertIn("Logan", by_term)
            self.assertIn("Grace", by_term)
            self.assertEqual(by_term["Logan"]["count"], 4)
            self.assertEqual(by_term["Grace"]["count"], 4)
            self.assertNotIn("Logan’s", by_term)
            self.assertNotIn("Grace’s", by_term)
            for noise in (
                "Because",
                "Apart",
                "Around",
                "Aye",
                "Believe",
                "Beneath",
                "Coach",
                "Dad",
                "Darkness",
                "Dead",
                "Delicious",
                "Despite",
                "Down",
                "Each",
                "Ever",
                "Fare",
                "Far",
                "Fifty",
                "Flying",
                "Friday",
                "From",
                "Fuck",
                "God",
                "Heart",
                "Help",
                "Hell",
                "Jesus",
                "Its",
                "Leave",
                "Looking",
                "Loom",
                "More",
                "Not",
                "No-one",
                "Nor",
                "Oh God",
                "Okay",
                "Once",
                "Pass",
                "Quickly",
                "Several",
                "Slowly",
                "Sometimes",
                "Stay",
                "Steady",
                "Stop",
                "Study",
                "T-shirt",
                "The Skyraider",
                "Time",
                "Twitter",
                "Wahoo",
                "Welcome",
                "Where",
                "Which",
                "Wuh-wuh",
                "Yeah",
            ):
                self.assertNotIn(noise, by_term)


if __name__ == "__main__":
    unittest.main()
