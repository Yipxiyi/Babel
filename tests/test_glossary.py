from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from babel_epub.glossary import (
    build_glossary_terms,
    detect_deterministic_quality,
    detect_glossary_issues,
    render_glossary_markdown,
    repair_untranslated_terms,
)
from babel_epub.glossary_io import export_glossary_text, import_glossary_text, merge_glossary_terms
from babel_epub.pipeline import write_jsonl


class GlossaryTests(unittest.TestCase):
    def test_glossary_import_export_round_trips_csv_tbx_and_markdown(self) -> None:
        terms = [
            {
                "source": "Rook",
                "translation": "鲁克",
                "type": "person",
                "aliases": ["Rook Barkwater"],
                "frequency": 7,
                "evidence": ["Rook walked."],
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
                "status": "pending",
                "confidence": 0.72,
                "locked": False,
            },
        ]

        for fmt in ("csv", "tbx", "md"):
            exported = export_glossary_text(terms, fmt, target_language="Simplified Chinese")
            imported = import_glossary_text(exported, fmt)
            by_source = {term["source"]: term for term in imported}
            self.assertEqual(by_source["Rook"]["translation"], "鲁克")
            self.assertEqual(by_source["Rook"]["status"], "approved")
            self.assertTrue(by_source["Rook"]["locked"])
            self.assertEqual(by_source["Deepwoods"]["translation"], "深林")

        japanese_tbx = export_glossary_text(
            [{"source": "Rook", "translation": "ルーク", "status": "approved", "locked": True}],
            "tbx",
            target_language="Japanese",
        )
        japanese_terms = import_glossary_text(japanese_tbx, "tbx")
        self.assertEqual(japanese_terms[0]["source"], "Rook")
        self.assertEqual(japanese_terms[0]["translation"], "ルーク")

        merged = merge_glossary_terms(
            [{"source": "Rook", "translation": "旧译", "status": "approved", "locked": True}],
            [{"source": "Rook", "translation": "鲁克", "status": "pending", "locked": False}],
        )
        self.assertEqual(merged[0]["translation"], "鲁克")
        self.assertEqual(merged[0]["status"], "approved")
        self.assertTrue(merged[0]["locked"])

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
                    {
                        "id": "chapter.xhtml::0005",
                        "source_text": "Great Storm Chamber stood above the city. Great things were expected there.",
                    },
                ],
            )

            terms = build_glossary_terms(pipeline_dir, "Simplified Chinese", glossary_preset="edge-chronicles")
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
            self.assertEqual(by_source["Great Storm Chamber"]["aliases"], [])
            self.assertNotIn("Great", by_source)
            self.assertEqual(by_source["Rook"]["status"], "approved")
            self.assertEqual(by_source["Wumeru"]["status"], "pending")
            self.assertFalse(by_source["Wumeru"]["locked"])
            self.assertEqual(by_source["Wumeru"]["translation"], "")
            self.assertIn("| Rook | 鲁克 |", markdown)
            self.assertTrue((pipeline_dir / "glossary_terms.json").exists())


    def test_default_glossary_does_not_use_project_specific_preset(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            pipeline_dir = Path(tmp)
            write_jsonl(
                pipeline_dir / "blocks.jsonl",
                [
                    {"id": "chapter.xhtml::0001", "source_text": "Rook met Rook in the Deepwoods."},
                    {"id": "chapter.xhtml::0002", "source_text": "Rook saw the Deepwoods again."},
                ],
            )

            terms = build_glossary_terms(pipeline_dir, "Simplified Chinese")
            by_source = {term["source"]: term for term in terms}

            self.assertIn("Rook", by_source)
            self.assertEqual(by_source["Rook"]["translation"], "")
            self.assertEqual(by_source["Rook"]["status"], "pending")
            self.assertIn("Deepwoods", by_source)
            self.assertEqual(by_source["Deepwoods"]["translation"], "")
            self.assertEqual(by_source["Deepwoods"]["status"], "pending")
            self.assertEqual(by_source["Deepwoods"]["type"], "person")

    def test_structured_glossary_filters_modern_dialogue_noise(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            pipeline_dir = Path(tmp)
            write_jsonl(
                pipeline_dir / "blocks.jsonl",
                [
                    {
                        "id": "chapter.xhtml::0001",
                        "source_text": "Logan met Grace. Yeah, Logan said, okay, Where are we going?",
                    },
                    {
                        "id": "chapter.xhtml::0002",
                        "source_text": "Then Grace called Logan. Fuck, Dad, God, and Twitter were not people.",
                    },
                    {
                        "id": "chapter.xhtml::0003",
                        "source_text": "Grace saw Logan on Friday. Because, Which, Not, Coach, Jesus.",
                    },
                    {
                        "id": "chapter.xhtml::0004",
                        "source_text": "Grace smiled at Logan.",
                    },
                    {
                        "id": "chapter.xhtml::0005",
                        "source_text": "Because. Which. Not. Coach. Jesus. Where. Friday. Hell. Once. Oh God.",
                    },
                    {
                        "id": "chapter.xhtml::0006",
                        "source_text": "Hell. Once. Oh God. T-shirt.",
                    },
                    {
                        "id": "chapter.xhtml::0007",
                        "source_text": "T-shirt.",
                    },
                ],
            )

            terms = build_glossary_terms(pipeline_dir, "Simplified Chinese")
            by_source = {term["source"]: term for term in terms}

            self.assertIn("Logan", by_source)
            self.assertIn("Grace", by_source)
            for noise in (
                "Because",
                "Coach",
                "Dad",
                "Friday",
                "Fuck",
                "God",
                "Hell",
                "Jesus",
                "Not",
                "Oh God",
                "Okay",
                "Once",
                "T-shirt",
                "Then",
                "Twitter",
                "Where",
                "Which",
                "Yeah",
            ):
                self.assertNotIn(noise, by_source)

    def test_structured_glossary_filters_bookish_sentence_start_noise(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            pipeline_dir = Path(tmp)
            write_jsonl(
                pipeline_dir / "blocks.jsonl",
                [
                    {
                        "id": "chapter.xhtml::0001",
                        "source_text": "Rook watched Wumeru from the bridge. From there, Wumeru waved to Rook.",
                    },
                    {
                        "id": "chapter.xhtml::0002",
                        "source_text": "Its light flickered. Each path bent away. Despite the mist, Quickly they moved.",
                    },
                    {
                        "id": "chapter.xhtml::0003",
                        "source_text": "Slowly, Welcome, Stay, Far, Time, Light, Earth, No-one.",
                    },
                    {
                        "id": "chapter.xhtml::0004",
                        "source_text": "Aargh. Urrgh. Wuh. Wuh-wuh. Whup. The Skyraider watched Rook.",
                    },
                    {
                        "id": "chapter.xhtml::0005",
                        "source_text": "Several. Around. Pass. Steady. More. Fare. Wumeru stayed with Rook.",
                    },
                    {
                        "id": "chapter.xhtml::0006",
                        "source_text": "Believe. Fifty. Study. Stop. Aye. Darkness. Wumeru saw Rook.",
                    },
                    {
                        "id": "chapter.xhtml::0007",
                        "source_text": "Apart. Dead. Ever. Flying. Loom. Open Sky. Stone Gardens. Sometimes. Wahoo.",
                    },
                    {
                        "id": "chapter.xhtml::0008",
                        "source_text": "Apart. Dead. Ever. Flying. Loom. Open Sky. Stone Gardens. Sometimes. Wahoo.",
                    },
                    {
                        "id": "chapter.xhtml::0009",
                        "source_text": "Beneath. Delicious. Help. Looking. Golden Nest.",
                    },
                    {
                        "id": "chapter.xhtml::0010",
                        "source_text": "Beneath. Delicious. Help. Looking. Golden Nest.",
                    },
                    {
                        "id": "chapter.xhtml::0011",
                        "source_text": "Heart. Leave. Nor.",
                    },
                    {
                        "id": "chapter.xhtml::0012",
                        "source_text": "Heart. Leave. Nor.",
                    },
                    {
                        "id": "chapter.xhtml::0013",
                        "source_text": "Down.",
                    },
                    {
                        "id": "chapter.xhtml::0014",
                        "source_text": "Down.",
                    },
                ],
            )

            terms = build_glossary_terms(pipeline_dir, "Simplified Chinese", glossary_preset="edge-chronicles")
            by_source = {term["source"]: term for term in terms}

            self.assertIn("Rook", by_source)
            self.assertIn("Wumeru", by_source)
            self.assertEqual(by_source["Open Sky"]["type"], "place")
            self.assertEqual(by_source["Stone Gardens"]["type"], "place")
            self.assertEqual(by_source["Golden Nest"]["type"], "place")
            for noise in (
                "Aargh",
                "Apart",
                "Around",
                "Aye",
                "Believe",
                "Beneath",
                "Darkness",
                "Dead",
                "Delicious",
                "Despite",
                "Down",
                "Each",
                "Earth",
                "Ever",
                "Fare",
                "Far",
                "Fifty",
                "Flying",
                "From",
                "Heart",
                "Help",
                "Its",
                "Leave",
                "Light",
                "Looking",
                "Loom",
                "More",
                "No-one",
                "Nor",
                "Open",
                "Pass",
                "Quickly",
                "Several",
                "Slowly",
                "Sometimes",
                "Stay",
                "Steady",
                "Stop",
                "Study",
                "The Skyraider",
                "Time",
                "Urrgh",
                "Wahoo",
                "Welcome",
                "Whup",
                "Wuh",
                "Wuh-wuh",
            ):
                self.assertNotIn(noise, by_source)

    def test_deterministic_quality_flags_untranslated_punctuation_and_person_drift(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            pipeline_dir = Path(tmp)
            write_jsonl(
                pipeline_dir / "batches" / "batch_001_chapter_01.jsonl",
                [
                    {
                        "id": "chapter.xhtml::0001",
                        "source_text": 'Lyra whispered, "The ancient door remained completely silent tonight."',
                        "source_html": '<p>Lyra whispered, "The ancient door remained completely silent tonight."</p>',
                    }
                ],
            )
            write_jsonl(
                pipeline_dir / "translated" / "batch_001_chapter_01.translated.jsonl",
                [
                    {
                        "id": "chapter.xhtml::0001",
                        "translated_html": "<p>她低声说：The ancient door remained completely silent tonight.</p>",
                    }
                ],
            )
            (pipeline_dir / "batch_manifest.json").write_text(
                json.dumps(
                    [
                        {
                            "batch": 1,
                            "chapter_label": "Chapter 1",
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
                    "source": "Lyra",
                    "translation": "莱拉",
                    "type": "person",
                    "aliases": [],
                    "frequency": 1,
                    "evidence": [],
                    "status": "approved",
                    "confidence": 0.95,
                    "locked": True,
                }
            ]

            report = detect_deterministic_quality(pipeline_dir, terms)
            kinds = {issue["kind"] for issue in report["issues"]}

            self.assertEqual(report["row_count"], 1)
            self.assertGreater(report["untranslated_ratio"], 0)
            self.assertEqual(report["blocking_count"], 1)
            self.assertEqual(report["nonblocking_count"], 2)
            self.assertIn("long-untranslated-segment", kinds)
            self.assertIn("punctuation-quote-drift", kinds)
            self.assertIn("person-name-drift", kinds)
            self.assertEqual(report["chapter_summary_consistency"]["chapters_with_issues"], 1)

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
