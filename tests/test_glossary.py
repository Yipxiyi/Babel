from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from babel_epub.glossary import (
    build_glossary_terms,
    detect_glossary_issues,
    render_glossary_markdown,
    repair_untranslated_terms,
)
from babel_epub.pipeline import write_jsonl


class GlossaryTests(unittest.TestCase):
    def test_structured_glossary_filters_noise_and_locks_known_terms(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            pipeline_dir = Path(tmp)
            write_jsonl(
                pipeline_dir / "blocks.jsonl",
                [
                    {
                        "id": "chapter.xhtml::0001",
                        "source_text": "Rook Barkwater met Rook in the Deepwoods.",
                    },
                    {
                        "id": "chapter.xhtml::0002",
                        "source_text": "There Rook saw a banderbear near Lake Landing.",
                    },
                    {
                        "id": "chapter.xhtml::0003",
                        "source_text": "Rook thanked the banderbear.",
                    },
                    {
                        "id": "chapter.xhtml::0004",
                        "source_text": "His boots were wet. She said, I’m tired. Night fell quickly. Wumeru listened to Wumeru.",
                    },
                ],
            )

            terms = build_glossary_terms(pipeline_dir, "Simplified Chinese")
            by_source = {term["source"]: term for term in terms}
            markdown = render_glossary_markdown("Simplified Chinese", terms)

            self.assertIn("Rook", by_source)
            self.assertIn("Deepwoods", by_source)
            self.assertIn("banderbear", by_source)
            self.assertNotIn("There", by_source)
            self.assertNotIn("His", by_source)
            self.assertNotIn("She", by_source)
            self.assertNotIn("I’m", by_source)
            self.assertNotIn("Night", by_source)
            self.assertEqual(by_source["Rook"]["translation"], "鲁克")
            self.assertEqual(by_source["Deepwoods"]["translation"], "深林")
            self.assertEqual(by_source["banderbear"]["translation"], "班德熊")
            self.assertEqual(by_source["Rook"]["status"], "approved")
            self.assertEqual(by_source["Wumeru"]["status"], "pending")
            self.assertFalse(by_source["Wumeru"]["locked"])
            self.assertEqual(by_source["Wumeru"]["translation"], "")
            self.assertIn("| Rook | 鲁克 |", markdown)
            self.assertTrue((pipeline_dir / "glossary_terms.json").exists())

    def test_ai_qa_detects_and_repairs_untranslated_locked_terms(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            pipeline_dir = Path(tmp)
            (pipeline_dir / "translated").mkdir()
            write_jsonl(
                pipeline_dir / "batches" / "batch_001_chapter_01.jsonl",
                [{"id": "chapter.xhtml::0001", "source_text": "Rook entered the Deepwoods.", "source_html": '<p class="body">Rook entered the Deepwoods.</p>'}],
            )
            write_jsonl(
                pipeline_dir / "translated" / "batch_001_chapter_01.translated.jsonl",
                [{"id": "chapter.xhtml::0001", "translated_html": '<p class="body">Rook走进了Deepwoods。</p>'}],
            )
            (pipeline_dir / "batch_manifest.json").write_text(
                json.dumps(
                    [
                        {
                            "batch": 1,
                            "input": "batches/batch_001_chapter_01.jsonl",
                            "output": "translated/batch_001_chapter_01.translated.jsonl",
                        }
                    ],
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            terms = [
                {
                    "source": "Rook",
                    "translation": "鲁克",
                    "type": "person",
                    "aliases": [],
                    "frequency": 3,
                    "evidence": [],
                    "status": "approved",
                    "confidence": 0.95,
                    "locked": True,
                },
                {
                    "source": "Deepwoods",
                    "translation": "深林",
                    "type": "place",
                    "aliases": [],
                    "frequency": 3,
                    "evidence": [],
                    "status": "approved",
                    "confidence": 0.95,
                    "locked": True,
                },
            ]

            issues = detect_glossary_issues(pipeline_dir, terms)
            repaired = repair_untranslated_terms(pipeline_dir, terms, issues)
            remaining = detect_glossary_issues(pipeline_dir, terms)
            output = (pipeline_dir / "translated" / "batch_001_chapter_01.translated.jsonl").read_text(
                encoding="utf-8"
            )

            self.assertEqual(repaired, 1)
            self.assertEqual(remaining, [])
            self.assertIn("鲁克走进了深林", output)


if __name__ == "__main__":
    unittest.main()
