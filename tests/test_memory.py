from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from babel_epub.jobs import BabelJobEngine
from babel_epub.memory import TranslationMemoryStore, memory_path_for, normalize_memory_project_id
from babel_epub.providers import ProviderSettings


class TranslationMemoryTests(unittest.TestCase):
    def test_job_engine_reuses_one_store_for_the_same_project(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            engine = BabelJobEngine(Path(tmp) / "jobs")
            settings = ProviderSettings(
                provider="fake",
                model="fake-model",
                target_language="Simplified Chinese",
                memory_enabled=True,
                memory_project_id="series-a",
            )

            self.assertIs(engine._memory_store_for(settings), engine._memory_store_for(settings))

    def test_store_lookup_export_and_import_roundtrip(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            source = {
                "id": "chapter.xhtml::0001",
                "source_text": "Hello world.",
                "source_html": "<p>Hello world.</p>",
            }
            translated = {"id": source["id"], "translated_html": "<p>你好，世界。</p>"}
            store = TranslationMemoryStore(memory_path_for(tmp_path, "Series A"), project_id="Series A")

            self.assertEqual(normalize_memory_project_id("Series A"), "Series-A")
            self.assertTrue(store.upsert_segment(source, translated, target_language="Simplified Chinese"))
            store.save()
            hit = store.lookup(source, "Simplified Chinese")
            self.assertIsNotNone(hit)
            self.assertEqual(hit.row["translated_html"], "<p>你好，世界。</p>")
            self.assertIsNone(store.lookup(source, "Japanese"))

            exported = tmp_path / "export.json"
            store.export_to(exported)
            payload = json.loads(exported.read_text(encoding="utf-8"))
            self.assertEqual(len(payload["segments"]), 1)

            imported = TranslationMemoryStore(tmp_path / "imported.json", project_id="other")
            result = imported.import_from(exported)
            self.assertEqual(result["imported"], 1)
            imported_hit = imported.lookup(source, "Simplified Chinese")
            self.assertIsNotNone(imported_hit)
            self.assertEqual(imported.stats()["segment_entries"], 1)


if __name__ == "__main__":
    unittest.main()
