from __future__ import annotations

import zipfile
import tempfile
import json
import threading
import time
import unittest
from pathlib import Path

from babel_epub.jobs import BabelJobEngine, JobRequest, ProviderSettings
from babel_epub.providers import (
    FakeProvider,
    OpenAICompatibleProvider,
    TranslationProvider,
    parse_translated_rows,
    repair_translated_row_structure,
)
from test_pipeline import make_minimal_epub


def make_epub_with_paragraphs(path: Path, paragraph_count: int) -> None:
    base_epub = path.with_name("base.epub")
    make_minimal_epub(base_epub)
    chapter = """<?xml version="1.0" encoding="utf-8"?>
<html xmlns="http://www.w3.org/1999/xhtml">
  <head><title>Chapter 1</title><link rel="stylesheet" href="style.css"/></head>
  <body>
    <h1 id="chapter-1">Chapter One</h1>
{paragraphs}
  </body>
</html>
""".format(
        paragraphs="\n".join(
            f'    <p class="body">Paragraph {index} for translation.</p>'
            for index in range(1, paragraph_count + 1)
        )
    )
    with zipfile.ZipFile(base_epub) as source_archive, zipfile.ZipFile(path, "w") as target_archive:
        for info in source_archive.infolist():
            content = source_archive.read(info.filename)
            if info.filename == "OEBPS/chapter1.xhtml":
                content = chapter.encode("utf-8")
            target_archive.writestr(info, content)


class JobEngineTests(unittest.TestCase):
    def test_autofill_glossary_terms_only_fills_pending_empty_terms(self) -> None:
        class GlossaryDraftProvider(TranslationProvider):
            def translate_batch(self, rows: list[dict], glossary: str, context: str) -> list[dict]:
                return [
                    {"id": row["id"], "translated_html": f"<p>译:{row['source_text']}</p>"}
                    for row in rows
                ]

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            input_epub = tmp_path / "input.epub"
            make_minimal_epub(input_epub)
            engine = BabelJobEngine(tmp_path / "jobs", provider_factory=lambda _settings: GlossaryDraftProvider())
            job = engine.create_job(
                JobRequest(filename="input.epub", content=input_epub.read_bytes(), target_language="Simplified Chinese")
            )
            engine.update_glossary_terms(
                job.job_id,
                [
                    {
                        "source": "Rook",
                        "translation": "",
                        "type": "person",
                        "aliases": [],
                        "frequency": 7,
                        "evidence": ["Rook opened the door."],
                        "status": "pending",
                        "confidence": 0.62,
                        "locked": False,
                    },
                    {
                        "source": "Deepwoods",
                        "translation": "深林",
                        "type": "place",
                        "aliases": [],
                        "frequency": 4,
                        "evidence": [],
                        "status": "pending",
                        "confidence": 0.72,
                        "locked": False,
                    },
                    {
                        "source": "Twig",
                        "translation": "",
                        "type": "person",
                        "aliases": [],
                        "frequency": 3,
                        "evidence": [],
                        "status": "approved",
                        "confidence": 0.9,
                        "locked": True,
                    },
                    {
                        "source": "Mud",
                        "translation": "",
                        "type": "special",
                        "aliases": [],
                        "frequency": 2,
                        "evidence": [],
                        "status": "ignored",
                        "confidence": 0.2,
                        "locked": False,
                    },
                ],
            )

            updated = engine.autofill_glossary_terms(
                job.job_id,
                ProviderSettings(provider="fake", model="fake-model", target_language="Simplified Chinese"),
            )
            terms = {term["source"]: term for term in engine.read_glossary_terms(job.job_id)}
            markdown = updated.glossary_path.read_text(encoding="utf-8")

            self.assertEqual(terms["Rook"]["translation"], "译:Rook")
            self.assertEqual(terms["Rook"]["status"], "pending")
            self.assertFalse(terms["Rook"]["locked"])
            self.assertEqual(terms["Deepwoods"]["translation"], "深林")
            self.assertEqual(terms["Twig"]["translation"], "")
            self.assertEqual(terms["Mud"]["translation"], "")
            self.assertEqual(updated.glossary_summary["pending"], 2)
            self.assertIn("Rook -> 译:Rook", markdown)
            self.assertIn("glossary-autofill", [event["type"] for event in updated.events])

    def test_autofill_provider_settings_error_does_not_fail_job(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            input_epub = tmp_path / "input.epub"
            make_minimal_epub(input_epub)
            engine = BabelJobEngine(tmp_path / "jobs", provider_factory=lambda _settings: FakeProvider())
            job = engine.create_job(
                JobRequest(filename="input.epub", content=input_epub.read_bytes(), target_language="Simplified Chinese")
            )

            with self.assertRaisesRegex(ValueError, "api_key is required"):
                engine.autofill_glossary_terms(
                    job.job_id,
                    ProviderSettings(
                        provider="openai-compatible",
                        base_url="https://api.openai.com/v1",
                        api_key="",
                        model="gpt-4.1",
                        target_language="Simplified Chinese",
                    ),
                )

            current = engine.get_job(job.job_id)
            self.assertEqual(current.status, "prepared")
            self.assertNotIn("failed", [event["type"] for event in current.events])

    def test_job_engine_runs_full_translation_job(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            input_epub = tmp_path / "input.epub"
            make_minimal_epub(input_epub)
            engine = BabelJobEngine(tmp_path / "jobs", provider_factory=lambda _settings: FakeProvider())

            job = engine.create_job(
                JobRequest(
                    filename="input.epub",
                    content=input_epub.read_bytes(),
                    target_language="Simplified Chinese",
                    title="示例书",
                    language="zh-CN",
                    output_format="epub",
                )
            )
            self.assertEqual(job.status, "prepared")
            self.assertEqual(job.block_count, 2)
            self.assertTrue((job.work_dir / "pipeline" / "WORKER_INSTRUCTIONS.md").exists())

            finished = engine.run_job(
                job.job_id,
                ProviderSettings(provider="fake", model="fake-model", target_language="Simplified Chinese"),
            )

            self.assertEqual(finished.status, "completed")
            self.assertEqual(finished.max_concurrency, 3)
            self.assertEqual(finished.completed_batches, 1)
            self.assertEqual(finished.total_batches, 1)
            self.assertTrue(finished.output_epub and finished.output_epub.exists())
            self.assertTrue(finished.output_book and finished.output_book.exists())
            self.assertEqual(finished.output_book.suffix, ".epub")
            self.assertTrue(finished.audit_path and finished.audit_path.exists())
            self.assertTrue(finished.report_path and finished.report_path.exists())
            with zipfile.ZipFile(finished.output_epub) as archive:
                self.assertIsNone(archive.testzip())
                chapter = archive.read("OEBPS/chapter1.xhtml").decode("utf-8")
            self.assertIn("测试翻译", chapter)

    def test_failed_job_records_events_and_failed_batch(self) -> None:
        class FailOnSecondBatchProvider(FakeProvider):
            def __init__(self) -> None:
                self.calls = 0

            def translate_batch(self, rows: list[dict], glossary: str, context: str) -> list[dict]:
                self.calls += 1
                if self.calls == 2:
                    raise ValueError("provider returned invalid JSONL at line 1: preview=<html>")
                return super().translate_batch(rows, glossary, context)

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            input_epub = tmp_path / "input.epub"
            make_minimal_epub(input_epub)
            provider = FailOnSecondBatchProvider()
            engine = BabelJobEngine(tmp_path / "jobs", provider_factory=lambda _settings: provider)
            job = engine.create_job(
                JobRequest(
                    filename="input.epub",
                    content=input_epub.read_bytes(),
                    target_language="Simplified Chinese",
                    max_blocks=1,
                )
            )

            failed = engine.run_job(
                job.job_id,
                ProviderSettings(
                    provider="fake",
                    model="fake-model",
                    target_language="Simplified Chinese",
                    max_concurrency=1,
                    max_retries=0,
                ),
            )

            self.assertEqual(failed.status, "failed")
            self.assertEqual(failed.completed_batches, 1)
            self.assertEqual(failed.failed_batch["batch"], 2)
            self.assertEqual(len(failed.failed_batches), 1)
            self.assertIsNone(failed.current_batch)
            self.assertFalse(failed.active_batches)
            self.assertTrue(failed.last_active_at)
            self.assertIn("provider returned invalid JSONL", failed.message)
            self.assertIn("failed", [event["type"] for event in failed.events])
            self.assertIn("batch-failed", [event["type"] for event in failed.events])
            self.assertIn("batch-start", [event["type"] for event in failed.events])
            self.assertIn("batch-done", [event["type"] for event in failed.events])

    def test_official_openai_without_api_key_fails_before_running(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            input_epub = tmp_path / "input.epub"
            make_minimal_epub(input_epub)
            engine = BabelJobEngine(tmp_path / "jobs", provider_factory=lambda _settings: FakeProvider())
            job = engine.create_job(
                JobRequest(
                    filename="input.epub",
                    content=input_epub.read_bytes(),
                    target_language="Simplified Chinese",
                )
            )

            with self.assertRaisesRegex(ValueError, "api_key is required"):
                engine.start_job(
                    job.job_id,
                    ProviderSettings(
                        provider="openai-compatible",
                        base_url="https://api.openai.com/v1",
                        api_key="",
                        model="gpt-4.1",
                        target_language="Simplified Chinese",
                    ),
                )

            failed = engine.get_job(job.job_id)
            self.assertEqual(failed.status, "failed")
            self.assertNotEqual(failed.status, "running")
            self.assertIn("api_key is required", failed.message)
            self.assertIn("failed", [event["type"] for event in failed.events])

    def test_retryable_timeout_records_retry_event_and_completes(self) -> None:
        class TimeoutOnceProvider(FakeProvider):
            calls = 0

            def translate_batch(self, rows: list[dict], glossary: str, context: str) -> list[dict]:
                type(self).calls += 1
                if type(self).calls == 1:
                    raise TimeoutError("provider read timed out")
                return super().translate_batch(rows, glossary, context)

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            input_epub = tmp_path / "input.epub"
            make_minimal_epub(input_epub)
            engine = BabelJobEngine(tmp_path / "jobs", provider_factory=lambda _settings: TimeoutOnceProvider())
            job = engine.create_job(
                JobRequest(
                    filename="input.epub",
                    content=input_epub.read_bytes(),
                    target_language="Simplified Chinese",
                )
            )

            finished = engine.run_job(
                job.job_id,
                ProviderSettings(
                    provider="fake",
                    model="fake-model",
                    target_language="Simplified Chinese",
                    max_concurrency=1,
                    max_retries=1,
                ),
            )

            self.assertEqual(finished.status, "completed")
            self.assertIn("batch-retry", [event["type"] for event in finished.events])

    def test_validation_failure_is_retried_and_can_complete(self) -> None:
        class MissingRowOnceProvider(FakeProvider):
            calls = 0

            def translate_batch(self, rows: list[dict], glossary: str, context: str) -> list[dict]:
                type(self).calls += 1
                translated = super().translate_batch(rows, glossary, context)
                if type(self).calls == 1:
                    return translated[:1]
                return translated

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            input_epub = tmp_path / "input.epub"
            make_minimal_epub(input_epub)
            engine = BabelJobEngine(tmp_path / "jobs", provider_factory=lambda _settings: MissingRowOnceProvider())
            job = engine.create_job(
                JobRequest(
                    filename="input.epub",
                    content=input_epub.read_bytes(),
                    target_language="Simplified Chinese",
                )
            )

            finished = engine.run_job(
                job.job_id,
                ProviderSettings(
                    provider="fake",
                    model="fake-model",
                    target_language="Simplified Chinese",
                    max_concurrency=1,
                    max_retries=1,
                ),
            )

            self.assertEqual(finished.status, "completed")
            self.assertIn("batch-retry", [event["type"] for event in finished.events])

    def test_provider_safety_rejection_splits_batch_into_smaller_chunks(self) -> None:
        class RejectLargeBatchProvider(FakeProvider):
            large_calls = 0
            single_row_calls = 0

            def translate_batch(self, rows: list[dict], glossary: str, context: str) -> list[dict]:
                if len(rows) > 1:
                    type(self).large_calls += 1
                    raise ValueError(
                        "provider returned invalid JSONL: preview=The request was rejected "
                        "because it was considered high risk"
                    )
                type(self).single_row_calls += 1
                return super().translate_batch(rows, glossary, context)

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            input_epub = tmp_path / "input.epub"
            make_epub_with_paragraphs(input_epub, paragraph_count=3)
            engine = BabelJobEngine(tmp_path / "jobs", provider_factory=lambda _settings: RejectLargeBatchProvider())
            job = engine.create_job(
                JobRequest(
                    filename="input.epub",
                    content=input_epub.read_bytes(),
                    target_language="Simplified Chinese",
                    max_blocks=10,
                )
            )

            finished = engine.run_job(
                job.job_id,
                ProviderSettings(
                    provider="fake",
                    model="fake-model",
                    target_language="Simplified Chinese",
                    max_concurrency=1,
                    max_retries=0,
                ),
            )

            self.assertEqual(finished.status, "completed")
            self.assertEqual(finished.completed_batches, 1)
            self.assertEqual(RejectLargeBatchProvider.large_calls, 1)
            self.assertEqual(RejectLargeBatchProvider.single_row_calls, 4)
            self.assertIn("batch-split", [event["type"] for event in finished.events])

    def test_max_concurrency_limits_parallel_batch_execution(self) -> None:
        class SlowCountingProvider(FakeProvider):
            active = 0
            max_seen = 0
            lock = threading.Lock()

            def translate_batch(self, rows: list[dict], glossary: str, context: str) -> list[dict]:
                with type(self).lock:
                    type(self).active += 1
                    type(self).max_seen = max(type(self).max_seen, type(self).active)
                try:
                    time.sleep(0.05)
                    return super().translate_batch(rows, glossary, context)
                finally:
                    with type(self).lock:
                        type(self).active -= 1

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            input_epub = tmp_path / "input.epub"
            make_epub_with_paragraphs(input_epub, paragraph_count=6)
            engine = BabelJobEngine(tmp_path / "jobs", provider_factory=lambda _settings: SlowCountingProvider())
            job = engine.create_job(
                JobRequest(
                    filename="input.epub",
                    content=input_epub.read_bytes(),
                    target_language="Simplified Chinese",
                    max_blocks=1,
                )
            )

            finished = engine.run_job(
                job.job_id,
                ProviderSettings(
                    provider="fake",
                    model="fake-model",
                    target_language="Simplified Chinese",
                    max_concurrency=3,
                ),
            )

            self.assertEqual(finished.status, "completed")
            self.assertEqual(finished.completed_batches, finished.total_batches)
            self.assertGreater(SlowCountingProvider.max_seen, 1)
            self.assertLessEqual(SlowCountingProvider.max_seen, 3)
            self.assertEqual(finished.max_concurrency, 3)

    def test_one_failed_batch_continues_other_batches_then_job_fails(self) -> None:
        class FailParagraphTwoProvider(FakeProvider):
            def translate_batch(self, rows: list[dict], glossary: str, context: str) -> list[dict]:
                if any("Paragraph 2" in row.get("source_text", "") for row in rows):
                    raise RuntimeError("provider HTTP 500: overloaded")
                return super().translate_batch(rows, glossary, context)

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            input_epub = tmp_path / "input.epub"
            make_epub_with_paragraphs(input_epub, paragraph_count=4)
            engine = BabelJobEngine(tmp_path / "jobs", provider_factory=lambda _settings: FailParagraphTwoProvider())
            job = engine.create_job(
                JobRequest(
                    filename="input.epub",
                    content=input_epub.read_bytes(),
                    target_language="Simplified Chinese",
                    max_blocks=1,
                )
            )

            failed = engine.run_job(
                job.job_id,
                ProviderSettings(
                    provider="fake",
                    model="fake-model",
                    target_language="Simplified Chinese",
                    max_concurrency=3,
                    max_retries=0,
                ),
            )

            self.assertEqual(failed.status, "failed")
            self.assertEqual(failed.completed_batches, failed.total_batches - 1)
            self.assertEqual(len(failed.failed_batches), 1)
            self.assertFalse(failed.active_batches)
            event_types = [event["type"] for event in failed.events]
            self.assertIn("batch-failed", event_types)
            self.assertEqual(event_types.count("batch-done"), failed.completed_batches)

    def test_resume_skips_existing_valid_batches(self) -> None:
        class FailOnSecondBatchProvider(FakeProvider):
            def __init__(self) -> None:
                self.calls = 0

            def translate_batch(self, rows: list[dict], glossary: str, context: str) -> list[dict]:
                self.calls += 1
                if self.calls == 2:
                    raise ValueError("provider returned invalid JSONL at line 1")
                return super().translate_batch(rows, glossary, context)

        class CountingFakeProvider(FakeProvider):
            def __init__(self) -> None:
                self.calls = 0

            def translate_batch(self, rows: list[dict], glossary: str, context: str) -> list[dict]:
                self.calls += 1
                return super().translate_batch(rows, glossary, context)

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            input_epub = tmp_path / "input.epub"
            make_minimal_epub(input_epub)
            failing_provider = FailOnSecondBatchProvider()
            engine = BabelJobEngine(tmp_path / "jobs", provider_factory=lambda _settings: failing_provider)
            job = engine.create_job(
                JobRequest(
                    filename="input.epub",
                    content=input_epub.read_bytes(),
                    target_language="Simplified Chinese",
                    max_blocks=1,
                )
            )
            failed = engine.run_job(
                job.job_id,
                ProviderSettings(
                    provider="fake",
                    model="fake-model",
                    target_language="Simplified Chinese",
                    max_concurrency=1,
                    max_retries=0,
                ),
            )
            self.assertEqual(failed.status, "failed")
            self.assertEqual(failed.completed_batches, 1)

            resume_provider = CountingFakeProvider()
            engine.provider_factory = lambda _settings: resume_provider
            finished = engine.run_job(
                job.job_id,
                ProviderSettings(
                    provider="fake",
                    model="fake-model",
                    target_language="Simplified Chinese",
                    max_concurrency=3,
                ),
                resume=True,
            )

            self.assertEqual(finished.status, "completed")
            self.assertEqual(finished.completed_batches, finished.total_batches)
            self.assertEqual(resume_provider.calls, 1)
            self.assertIn("batch-skip", [event["type"] for event in finished.events])

    def test_old_job_json_without_concurrency_fields_still_loads(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            input_epub = tmp_path / "input.epub"
            make_minimal_epub(input_epub)
            engine = BabelJobEngine(tmp_path / "jobs", provider_factory=lambda _settings: FakeProvider())
            job = engine.create_job(
                JobRequest(
                    filename="input.epub",
                    content=input_epub.read_bytes(),
                    target_language="Simplified Chinese",
                )
            )
            state_path = job.work_dir / "job.json"
            data = json.loads(state_path.read_text(encoding="utf-8"))
            for key in ("active_batches", "failed_batches", "max_concurrency", "events", "last_active_at"):
                data.pop(key, None)
            state_path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

            reloaded = BabelJobEngine(tmp_path / "jobs")
            loaded = reloaded.get_job(job.job_id)

            self.assertEqual(loaded.max_concurrency, 3)
            self.assertEqual(loaded.active_batches, [])
            self.assertEqual(loaded.failed_batches, [])
            self.assertTrue(loaded.events)

    def test_running_job_json_is_marked_failed_on_restart(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            input_epub = tmp_path / "input.epub"
            make_minimal_epub(input_epub)
            engine = BabelJobEngine(tmp_path / "jobs", provider_factory=lambda _settings: FakeProvider())
            job = engine.create_job(
                JobRequest(
                    filename="input.epub",
                    content=input_epub.read_bytes(),
                    target_language="Simplified Chinese",
                )
            )
            state_path = job.work_dir / "job.json"
            data = json.loads(state_path.read_text(encoding="utf-8"))
            data["status"] = "running"
            data["message"] = "Translating batches."
            data["active_batches"] = [{"batch": 1}]
            state_path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

            reloaded = BabelJobEngine(tmp_path / "jobs")
            loaded = reloaded.get_job(job.job_id)

            self.assertEqual(loaded.status, "failed")
            self.assertFalse(loaded.active_batches)
            self.assertIn("Interrupted before completion", loaded.message)
            self.assertIn("failed", [event["type"] for event in loaded.events])

    def test_list_jobs_returns_most_recent_activity_first(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            input_epub = tmp_path / "input.epub"
            make_minimal_epub(input_epub)
            engine = BabelJobEngine(tmp_path / "jobs", provider_factory=lambda _settings: FakeProvider())
            first = engine.create_job(
                JobRequest(filename="first.epub", content=input_epub.read_bytes(), target_language="Simplified Chinese")
            )
            second = engine.create_job(
                JobRequest(filename="second.epub", content=input_epub.read_bytes(), target_language="Simplified Chinese")
            )
            engine._mutate_job(first.job_id, lambda job: setattr(job, "last_active_at", "2026-01-01T00:00:00Z"))
            engine._mutate_job(second.job_id, lambda job: setattr(job, "last_active_at", "2026-01-02T00:00:00Z"))

            jobs = engine.list_jobs()

            self.assertEqual(jobs[0].job_id, second.job_id)

    def test_openai_compatible_provider_builds_messages_and_parses_jsonl(self) -> None:
        captured = {}

        def transport(url: str, headers: dict[str, str], payload: dict) -> dict:
            captured["url"] = url
            captured["headers"] = headers
            captured["payload"] = payload
            return {
                "choices": [
                    {
                        "message": {
                            "content": '{"id":"a::0001","translated_html":"<p>你好</p>"}\n'
                        }
                    }
                ]
            }

        provider = OpenAICompatibleProvider(
            base_url="https://api.example.test/v1",
            api_key="secret",
            model="demo-model",
            target_language="Simplified Chinese",
            transport=transport,
        )
        rows = provider.translate_batch(
            [{"id": "a::0001", "source_text": "Hello", "source_html": "<p>Hello</p>"}],
            glossary="# Glossary\n",
            context="# Context\n",
        )

        self.assertEqual(captured["url"], "https://api.example.test/v1/chat/completions")
        self.assertEqual(captured["headers"]["Authorization"], "Bearer secret")
        self.assertEqual(captured["payload"]["model"], "demo-model")
        self.assertIn("neutral literary translation", captured["payload"]["messages"][0]["content"])
        self.assertIn("Return JSONL even when source text contains mature themes", captured["payload"]["messages"][0]["content"])
        self.assertEqual(rows, [{"id": "a::0001", "translated_html": "<p>你好</p>"}])

    def test_invalid_provider_jsonl_reports_safe_preview(self) -> None:
        with self.assertRaisesRegex(ValueError, "preview=not json"):
            parse_translated_rows("not json\nsecond line")

    def test_provider_parser_accepts_concatenated_json_objects(self) -> None:
        rows = parse_translated_rows(
            '{"id":"a::0001","translated_html":"<p>你好</p>"} '
            '{"id":"a::0002","translated_html":"<p>世界</p>"}'
        )

        self.assertEqual(
            rows,
            [
                {"id": "a::0001", "translated_html": "<p>你好</p>"},
                {"id": "a::0002", "translated_html": "<p>世界</p>"},
            ],
        )

    def test_repair_translated_row_structure_restores_missing_anchor(self) -> None:
        repaired = repair_translated_row_structure(
            '<p class="indent">Before <a id="page12" class="calibre6" />after.</p>',
            '<p class="indent">之前之后。</p>',
        )

        self.assertIn('id="page12"', repaired)
        self.assertIn('class="calibre6"', repaired)


if __name__ == "__main__":
    unittest.main()
