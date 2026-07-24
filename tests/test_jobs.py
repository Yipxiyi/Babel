from __future__ import annotations

import zipfile
import tempfile
import json
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from babel_epub.jobs import BabelJobEngine, JobRequest, ProviderSettings
from babel_epub.providers import (
    DeepLProvider,
    FakeProvider,
    GoogleTranslateProvider,
    OpenAICompatibleProvider,
    OpenAIResponsesProvider,
    RateLimitState,
    TranslationProvider,
    estimate_cost,
    estimate_rows_tokens,
    make_provider,
    parse_translated_rows,
    repair_translated_row_structure,
)
from babel_epub.glossary import render_glossary_markdown, read_glossary_terms
from babel_epub.pipeline import element_to_snippet, parse_snippet, read_jsonl
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


    def test_create_job_can_apply_glossary_preset(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            input_epub = tmp_path / "input.epub"
            make_minimal_epub(input_epub)
            chapter = """<?xml version="1.0" encoding="utf-8"?>
<html xmlns="http://www.w3.org/1999/xhtml"><body>
  <p>Rook walked into the Deepwoods.</p>
  <p>Rook left the Deepwoods.</p>
</body></html>
"""
            rewritten = tmp_path / "rewritten.epub"
            with zipfile.ZipFile(input_epub) as source, zipfile.ZipFile(rewritten, "w") as target:
                for info in source.infolist():
                    content = source.read(info.filename)
                    if info.filename == "OEBPS/chapter1.xhtml":
                        content = chapter.encode("utf-8")
                    target.writestr(info, content)
            engine = BabelJobEngine(tmp_path / "jobs", provider_factory=lambda _settings: FakeProvider())
            job = engine.create_job(
                JobRequest(
                    filename="input.epub",
                    content=rewritten.read_bytes(),
                    target_language="Simplified Chinese",
                    glossary_preset="edge-chronicles",
                )
            )
            terms = {term["source"]: term for term in engine.read_glossary_terms(job.job_id)}

            self.assertEqual(job.glossary_preset, "edge-chronicles")
            self.assertEqual(terms["Rook"]["translation"], "鲁克")
            self.assertEqual(terms["Rook"]["status"], "approved")
            self.assertEqual(terms["Deepwoods"]["translation"], "深林")
            self.assertIn("edge-chronicles", (job.work_dir / "job.json").read_text(encoding="utf-8"))

    def test_job_engine_imports_and_exports_glossary_terms(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            input_epub = tmp_path / "input.epub"
            make_minimal_epub(input_epub)
            engine = BabelJobEngine(tmp_path / "jobs", provider_factory=lambda _settings: FakeProvider())
            job = engine.create_job(
                JobRequest(filename="input.epub", content=input_epub.read_bytes(), target_language="Simplified Chinese")
            )
            csv_content = "source,translation,type,status,confidence,locked\nRook,鲁克,person,approved,0.95,true\n"

            updated, terms, summary = engine.import_glossary_terms(job.job_id, csv_content, fmt="csv")
            exported = engine.export_glossary_terms(job.job_id, fmt="csv")

            self.assertEqual(summary["imported"], 1)
            self.assertEqual({term["source"]: term for term in terms}["Rook"]["translation"], "鲁克")
            self.assertIn("Rook", exported)
            self.assertIn("glossary-import", [event["type"] for event in updated.events])
            self.assertIn("| Rook | 鲁克 | person |", updated.glossary_path.read_text(encoding="utf-8"))

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

    def test_translation_memory_reuses_exact_source_rows_across_jobs(self) -> None:
        class NoTranslateProvider(TranslationProvider):
            def translate_batch(self, rows: list[dict], glossary: str, context: str) -> list[dict]:
                raise AssertionError("provider should not be called for full memory hit")

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            input_epub = tmp_path / "input.epub"
            make_minimal_epub(input_epub)
            engine = BabelJobEngine(tmp_path / "jobs", provider_factory=lambda _settings: FakeProvider())
            settings = ProviderSettings(
                provider="fake",
                model="fake-model",
                target_language="Simplified Chinese",
                memory_enabled=True,
                memory_project_id="series-a",
            )
            first = engine.create_job(
                JobRequest(filename="input.epub", content=input_epub.read_bytes(), target_language="Simplified Chinese")
            )
            finished_first = engine.run_job(first.job_id, settings)
            self.assertEqual(finished_first.status, "completed")
            self.assertEqual(finished_first.memory_project_id, "series-a")
            self.assertEqual(finished_first.memory_summary["segment_entries"], finished_first.block_count)
            self.assertIn("memory-write", [event["type"] for event in finished_first.events])

            engine.provider_factory = lambda _settings: NoTranslateProvider()
            second = engine.create_job(
                JobRequest(filename="input.epub", content=input_epub.read_bytes(), target_language="Simplified Chinese")
            )
            finished_second = engine.run_job(second.job_id, settings)

            self.assertEqual(finished_second.status, "completed")
            self.assertEqual(finished_second.memory_summary["segment_entries"], finished_first.block_count)
            self.assertIn("memory-hit", [event["type"] for event in finished_second.events])
            with zipfile.ZipFile(finished_second.output_epub) as archive:
                chapter = archive.read("OEBPS/chapter1.xhtml").decode("utf-8")
            self.assertIn("测试翻译", chapter)

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
            self.assertEqual(finished.max_concurrency, 2)
            self.assertEqual(finished.adaptive_plan["execution"]["request_timeout"], 600.0)
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

    def test_async_preparation_builds_adaptive_plan_and_splits_oversized_paragraph(self) -> None:
        class CapturingProvider(FakeProvider):
            largest_source = 0

            def translate_batch(self, rows: list[dict], glossary: str, context: str) -> list[dict]:
                type(self).largest_source = max(
                    type(self).largest_source,
                    max(len(str(row.get("source_html", ""))) for row in rows),
                )
                return super().translate_batch(rows, glossary, context)

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            base_epub = tmp_path / "base.epub"
            upload_epub = tmp_path / "large.epub"
            make_minimal_epub(base_epub)
            long_text = "A long sentence for adaptive translation. " * 400
            with zipfile.ZipFile(base_epub) as source, zipfile.ZipFile(upload_epub, "w") as target:
                for info in source.infolist():
                    content = source.read(info.filename)
                    if info.filename == "OEBPS/chapter1.xhtml":
                        content = (
                            '<?xml version="1.0" encoding="utf-8"?>'
                            '<html xmlns="http://www.w3.org/1999/xhtml"><body>'
                            f'<p class="body">{long_text}</p></body></html>'
                        ).encode("utf-8")
                    target.writestr(info, content)

            engine = BabelJobEngine(tmp_path / "jobs", provider_factory=lambda _settings: CapturingProvider())
            job = engine.create_job_from_file_async(
                JobRequest(filename="large.epub", target_language="Simplified Chinese"),
                upload_epub,
            )
            self.assertEqual(job.status, "preparing")
            deadline = time.time() + 3
            while time.time() < deadline and engine.get_job(job.job_id).status == "preparing":
                time.sleep(0.01)
            prepared = engine.get_job(job.job_id)
            self.assertEqual(prepared.status, "prepared")
            self.assertTrue(prepared.adaptive_plan["enabled"])
            self.assertGreater(prepared.adaptive_plan["preparation"]["oversized_block_count"], 0)
            self.assertEqual(prepared.adaptive_plan["warnings"][0]["code"], "oversized-source-blocks")

            finished = engine.run_job(
                job.job_id,
                ProviderSettings(provider="fake", model="fake-model", target_language="Simplified Chinese"),
            )
            self.assertEqual(finished.status, "completed")
            self.assertIn("block-split", [event["type"] for event in finished.events])
            self.assertLessEqual(CapturingProvider.largest_source, 8_000)

    def test_async_upload_handoff_failure_removes_temporary_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            upload = tmp_path / "upload.epub"
            upload.write_bytes(b"temporary upload")
            engine = BabelJobEngine(tmp_path / "jobs")

            with patch("babel_epub.jobs.shutil.move", side_effect=OSError("disk unavailable")):
                failed = engine.create_job_from_file_async(
                    JobRequest(filename="upload.epub"),
                    upload,
                )

            self.assertEqual(failed.status, "failed")
            self.assertFalse(upload.exists())
            self.assertEqual(failed.diagnostics[-1]["stage"], "upload")

    def test_empty_source_reports_source_file_diagnostic_with_guidance(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            engine = BabelJobEngine(Path(tmp) / "jobs")
            with self.assertRaisesRegex(RuntimeError, "No translatable text"):
                engine.create_job(
                    JobRequest(filename="empty.txt", content=b"\n\n  \n", target_language="Simplified Chinese")
                )
            failed = engine.list_jobs()[0]
            self.assertEqual(failed.status, "failed")
            self.assertEqual(failed.diagnostics[-1]["owner"], "source_file")
            self.assertTrue(failed.diagnostics[-1]["guidance"])

    def test_completed_job_records_provider_usage_summary(self) -> None:
        class UsageProvider(FakeProvider):
            def translate_batch(self, rows: list[dict], glossary: str, context: str) -> list[dict]:
                self._record_response_usage(
                    {"usage": {"prompt_tokens": 11, "completion_tokens": 7, "total_tokens": 18}}
                )
                return super().translate_batch(rows, glossary, context)

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            input_epub = tmp_path / "input.epub"
            make_minimal_epub(input_epub)
            engine = BabelJobEngine(tmp_path / "jobs", provider_factory=lambda _settings: UsageProvider())
            job = engine.create_job(
                JobRequest(filename="input.epub", content=input_epub.read_bytes(), target_language="Simplified Chinese")
            )

            finished = engine.run_job(
                job.job_id,
                ProviderSettings(provider="fake", model="fake-model", target_language="Simplified Chinese"),
            )

            self.assertEqual(finished.status, "completed")
            self.assertEqual(finished.usage_summary["requests"], 1)
            self.assertEqual(finished.usage_summary["prompt_tokens"], 11)
            self.assertEqual(finished.usage_summary["completion_tokens"], 7)
            self.assertEqual(finished.usage_summary["total_tokens"], 18)
            self.assertEqual(finished.usage_summary["by_scope"]["translation"]["total_tokens"], 18)

    def test_ai_qa_summary_separates_nonblocking_locked_translation_drift(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            input_epub = tmp_path / "input.epub"
            make_minimal_epub(input_epub)
            engine = BabelJobEngine(tmp_path / "jobs", provider_factory=lambda _settings: FakeProvider())
            job = engine.create_job(
                JobRequest(filename="input.epub", content=input_epub.read_bytes(), target_language="Simplified Chinese")
            )
            engine.update_glossary_terms(
                job.job_id,
                [
                    {
                        "source": "Hello",
                        "translation": "你好",
                        "type": "term",
                        "aliases": [],
                        "frequency": 1,
                        "evidence": [],
                        "status": "approved",
                        "confidence": 0.95,
                        "locked": True,
                    }
                ],
            )

            finished = engine.run_job(
                job.job_id,
                ProviderSettings(provider="fake", model="fake-model", target_language="Simplified Chinese"),
            )

            self.assertEqual(finished.status, "completed")
            self.assertEqual(finished.ai_qa_status, "passed")
            self.assertEqual(finished.ai_qa_summary["blocking_remaining"], 0)
            self.assertGreaterEqual(finished.ai_qa_summary["nonblocking_remaining"], 1)
            self.assertGreaterEqual(finished.ai_qa_summary["remaining"], 1)
            self.assertIn("untranslated_ratio", finished.ai_qa_summary)
            self.assertIn("long_untranslated_segments", finished.ai_qa_summary)
            self.assertIn("punctuation_quote_drift", finished.ai_qa_summary)
            self.assertIn("person_name_drift", finished.ai_qa_summary)
            report = json.loads(finished.ai_quality_report_path.read_text(encoding="utf-8"))
            self.assertEqual(len(report["glossary_issues"]), 1)
            self.assertIn("quality", report)
            self.assertIn("chapter_summary_consistency", report["quality"])


    def test_provider_budget_stops_before_next_batch_and_resume_can_continue(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            input_epub = tmp_path / "input.epub"
            make_epub_with_paragraphs(input_epub, 2)
            engine = BabelJobEngine(tmp_path / "jobs", provider_factory=lambda _settings: FakeProvider())
            job = engine.create_job(
                JobRequest(
                    filename="input.epub",
                    content=input_epub.read_bytes(),
                    target_language="Simplified Chinese",
                    max_blocks=1,
                )
            )
            pipeline_dir = job.work_dir / "pipeline"
            manifest = json.loads((pipeline_dir / "batch_manifest.json").read_text(encoding="utf-8"))
            first_rows = read_jsonl(pipeline_dir / manifest[0]["input"])
            glossary = render_glossary_markdown(job.target_language, read_glossary_terms(job.work_dir))
            context = (pipeline_dir / "translation_context.md").read_text(encoding="utf-8")
            settings = ProviderSettings(
                provider="fake",
                model="fake-model",
                target_language="Simplified Chinese",
                max_concurrency=1,
                max_retries=0,
                input_cost_per_1m_tokens=1.0,
                output_cost_per_1m_tokens=1.0,
            )
            estimate = estimate_rows_tokens(first_rows, glossary, context)
            first_cost = estimate_cost(settings, estimate["prompt_tokens"], estimate["completion_tokens"])
            limited = ProviderSettings(
                provider="fake",
                model="fake-model",
                target_language="Simplified Chinese",
                max_concurrency=2,
                max_retries=0,
                budget_limit=first_cost + 0.000001,
                input_cost_per_1m_tokens=1.0,
                output_cost_per_1m_tokens=1.0,
            )

            failed = engine.run_job(job.job_id, limited)
            self.assertEqual(failed.status, "failed")
            self.assertEqual(failed.completed_batches, 1)
            self.assertTrue(failed.usage_summary["budget_exceeded"])
            self.assertIn("budget-stop", [event["type"] for event in failed.events])

            resumed = engine.run_job(
                job.job_id,
                ProviderSettings(
                    provider="fake",
                    model="fake-model",
                    target_language="Simplified Chinese",
                    max_concurrency=1,
                    max_retries=0,
                    budget_limit=1.0,
                    input_cost_per_1m_tokens=1.0,
                    output_cost_per_1m_tokens=1.0,
                ),
                resume=True,
            )
            self.assertEqual(resumed.status, "completed")
            self.assertEqual(resumed.completed_batches, resumed.total_batches)

    def test_rate_limiter_waits_when_request_window_is_exhausted(self) -> None:
        now = [0.0]
        sleeps: list[float] = []

        def sleeper(delay: float) -> None:
            sleeps.append(delay)
            now[0] += delay

        limiter = RateLimitState(1, 0, clock=lambda: now[0], sleeper=sleeper)
        self.assertEqual(limiter.acquire(10), 0.0)
        self.assertEqual(limiter.acquire(10), 60.0)
        self.assertEqual(sleeps, [60.0])

    def test_deepl_google_and_ollama_provider_adapters_build_expected_requests(self) -> None:
        rows = [{"id": "row-1", "source_html": "<p>Hello</p>", "source_text": "Hello"}]
        captured: list[dict] = []

        def deepl_transport(url, headers, payload):
            captured.append({"url": url, "headers": headers, "payload": payload})
            return {"translations": [{"text": "<p>你好</p>"}]}

        deepl = DeepLProvider(api_key="secret", target_language="Simplified Chinese", transport=deepl_transport)
        self.assertEqual(deepl.translate_batch(rows, "", "")[0]["translated_html"], "<p>你好</p>")
        self.assertTrue(captured[-1]["url"].endswith("/translate"))
        self.assertEqual(captured[-1]["payload"]["tag_handling"], "html")
        self.assertEqual(captured[-1]["payload"]["target_lang"], "ZH")

        def google_transport(url, headers, payload):
            captured.append({"url": url, "headers": headers, "payload": payload})
            return {"data": {"translations": [{"translatedText": "<p>你好</p>"}]}}

        google = GoogleTranslateProvider(api_key="secret", target_language="zh-CN", transport=google_transport)
        self.assertEqual(google.translate_batch(rows, "", "")[0]["translated_html"], "<p>你好</p>")
        self.assertIn("key=secret", captured[-1]["url"])
        self.assertEqual(captured[-1]["payload"]["format"], "html")

        self.assertIsInstance(
            make_provider(
                ProviderSettings(
                    provider="deepl",
                    api_key="secret",
                    model="",
                    target_language="Simplified Chinese",
                )
            ),
            DeepLProvider,
        )
        self.assertIsInstance(
            make_provider(
                ProviderSettings(
                    provider="google-translate",
                    api_key="secret",
                    model="",
                    target_language="Simplified Chinese",
                )
            ),
            GoogleTranslateProvider,
        )

        ollama = make_provider(ProviderSettings(provider="ollama", model="llama3", target_language="Simplified Chinese"))
        self.assertIsInstance(ollama, OpenAICompatibleProvider)
        self.assertEqual(ollama.base_url, "http://127.0.0.1:11434/v1")

    def test_failed_job_records_events_and_failed_batch(self) -> None:
        class FailOnSecondBatchProvider(FakeProvider):
            def __init__(self) -> None:
                self.calls = 0

            def translate_batch(self, rows: list[dict], glossary: str, context: str) -> list[dict]:
                self.calls += 1
                if any("Hello" in row.get("source_text", "") for row in rows):
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
            self.assertEqual(failed.diagnostics[-1]["owner"], "api")
            self.assertTrue(failed.diagnostics[-1]["guidance"])

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


    def test_start_job_concurrent_calls_only_start_one_worker(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            input_epub = tmp_path / "input.epub"
            make_minimal_epub(input_epub)
            engine = BabelJobEngine(tmp_path / "jobs", provider_factory=lambda _settings: FakeProvider())
            job = engine.create_job(
                JobRequest(filename="input.epub", content=input_epub.read_bytes(), target_language="Simplified Chinese")
            )
            started = threading.Event()
            release = threading.Event()
            calls = []

            def fake_run_job(
                job_id,
                settings,
                resume=False,
                ai_qa_enabled=True,
                auto_title_enabled=False,
                batch_filter=None,
            ):
                calls.append(job_id)
                started.set()
                release.wait(5)
                return engine.get_job(job_id)

            engine.run_job = fake_run_job
            settings = ProviderSettings(provider="fake", model="fake-model", target_language="Simplified Chinese")
            results = []
            errors = []

            def call_start() -> None:
                try:
                    results.append(engine.start_job(job.job_id, settings))
                except Exception as exc:
                    errors.append(exc)

            threads = [threading.Thread(target=call_start) for _ in range(8)]
            for thread in threads:
                thread.start()
            self.assertTrue(started.wait(2))
            for thread in threads:
                thread.join()
            release.set()
            worker = engine._threads[job.job_id]
            worker.join(2)

            self.assertFalse(errors)
            self.assertEqual(len(results), 8)
            self.assertEqual(calls, [job.job_id])

    def test_duplicate_start_with_invalid_settings_cannot_fail_running_job(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            input_epub = tmp_path / "input.epub"
            make_minimal_epub(input_epub)
            engine = BabelJobEngine(tmp_path / "jobs", provider_factory=lambda _settings: FakeProvider())
            job = engine.create_job(
                JobRequest(filename="input.epub", content=input_epub.read_bytes())
            )
            started = threading.Event()
            release = threading.Event()

            def blocking_run_job(*_args, **_kwargs):
                started.set()
                release.wait(5)
                return engine.get_job(job.job_id)

            engine.run_job = blocking_run_job
            valid = ProviderSettings(
                provider="fake",
                model="fake-model",
                target_language="Simplified Chinese",
            )
            engine.start_job(job.job_id, valid)
            self.assertTrue(started.wait(2))

            duplicate = engine.start_job(
                job.job_id,
                ProviderSettings(
                    provider="openai-compatible",
                    base_url="https://api.openai.com/v1",
                    api_key="",
                    model="gpt-4.1",
                    target_language="Simplified Chinese",
                ),
            )

            self.assertEqual(duplicate.status, "running")
            self.assertFalse(any("api_key is required" in error for error in duplicate.errors))
            release.set()
            engine._threads[job.job_id].join(2)
            self.assertEqual(engine.get_job(job.job_id).status, "running")
            self.assertEqual([event["type"] for event in engine.get_job(job.job_id).events].count("run-starting"), 1)

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
            self.assertIn("batch-split", [event["type"] for event in finished.events])

    def test_validation_failure_splits_batch_and_can_complete(self) -> None:
        class MissingRowsFromLargeBatchProvider(FakeProvider):
            large_calls = 0
            single_row_calls = 0

            def translate_batch(self, rows: list[dict], glossary: str, context: str) -> list[dict]:
                translated = super().translate_batch(rows, glossary, context)
                if len(rows) > 1:
                    type(self).large_calls += 1
                    return translated[:1]
                type(self).single_row_calls += 1
                return translated

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            input_epub = tmp_path / "input.epub"
            make_epub_with_paragraphs(input_epub, paragraph_count=3)
            engine = BabelJobEngine(
                tmp_path / "jobs",
                provider_factory=lambda _settings: MissingRowsFromLargeBatchProvider(),
            )
            job = engine.create_job(
                JobRequest(
                    filename="input.epub",
                    content=input_epub.read_bytes(),
                    target_language="Simplified Chinese",
                    max_blocks=10,
                    adaptive_enabled=False,
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
            self.assertGreater(MissingRowsFromLargeBatchProvider.large_calls, 0)
            self.assertGreater(MissingRowsFromLargeBatchProvider.single_row_calls, 0)
            self.assertIn("batch-split", [event["type"] for event in finished.events])

    def test_oversized_preserved_whitespace_survives_split_merge(self) -> None:
        class WhitespacePreservingProvider(TranslationProvider):
            def translate_batch(self, rows: list[dict], glossary: str, context: str) -> list[dict]:
                translated: list[dict] = []
                for row in rows:
                    root = parse_snippet(str(row["source_html"]))
                    source_text = "".join(root.itertext())
                    root.text = "".join("译" if not char.isspace() else char for char in source_text)
                    translated.append({"id": row["id"], "translated_html": element_to_snippet(root)})
                return translated

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            base_epub = tmp_path / "base.epub"
            input_epub = tmp_path / "preserved.epub"
            make_minimal_epub(base_epub)
            source_text = ("\n\tAlpha  Beta\n" * 700) + "\n  Omega\t\n"
            chapter = (
                '<?xml version="1.0" encoding="utf-8"?>'
                '<html xmlns="http://www.w3.org/1999/xhtml"><body>'
                f'<p xml:space="preserve">{source_text}</p>'
                "</body></html>"
            )
            with zipfile.ZipFile(base_epub) as source, zipfile.ZipFile(input_epub, "w") as target:
                for info in source.infolist():
                    content = source.read(info.filename)
                    if info.filename == "OEBPS/chapter1.xhtml":
                        content = chapter.encode("utf-8")
                    target.writestr(info, content)

            engine = BabelJobEngine(
                tmp_path / "jobs",
                provider_factory=lambda _settings: WhitespacePreservingProvider(),
            )
            job = engine.create_job(
                JobRequest(
                    filename="preserved.epub",
                    content=input_epub.read_bytes(),
                    target_language="Simplified Chinese",
                    max_chars=3_000,
                    adaptive_enabled=False,
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
                ai_qa_enabled=False,
            )

            self.assertEqual(finished.status, "completed")
            self.assertIn("block-split", [event["type"] for event in finished.events])
            with zipfile.ZipFile(finished.output_epub) as archive:
                chapter_root = parse_snippet(
                    archive.read("OEBPS/chapter1.xhtml").decode("utf-8").split("?>", 1)[-1]
                )
            paragraph = next(element for element in chapter_root.iter() if element.tag.endswith("p"))
            expected = "".join("译" if not char.isspace() else char for char in source_text)
            self.assertEqual(paragraph.text, expected)

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
            self.assertEqual(RejectLargeBatchProvider.large_calls, 3)
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
            self.assertEqual(finished.max_concurrency, 2)

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
                if any("Hello" in row.get("source_text", "") for row in rows):
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

    def test_batch_filter_translates_only_selected_batch_then_allows_resume(self) -> None:
        class CountingFakeProvider(FakeProvider):
            def __init__(self) -> None:
                self.batch_sizes: list[int] = []

            def translate_batch(self, rows: list[dict], glossary: str, context: str) -> list[dict]:
                self.batch_sizes.append(len(rows))
                return super().translate_batch(rows, glossary, context)

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            input_epub = tmp_path / "input.epub"
            make_epub_with_paragraphs(input_epub, paragraph_count=2)
            first_provider = CountingFakeProvider()
            engine = BabelJobEngine(tmp_path / "jobs", provider_factory=lambda _settings: first_provider)
            job = engine.create_job(
                JobRequest(
                    filename="input.epub",
                    content=input_epub.read_bytes(),
                    target_language="Simplified Chinese",
                    max_blocks=1,
                )
            )
            manifest = json.loads((job.work_dir / "pipeline" / "batch_manifest.json").read_text(encoding="utf-8"))
            self.assertGreaterEqual(len(manifest), 2)

            filtered = engine.run_job(
                job.job_id,
                ProviderSettings(
                    provider="fake",
                    model="fake-model",
                    target_language="Simplified Chinese",
                    max_concurrency=1,
                ),
                resume=True,
                ai_qa_enabled=False,
                batch_filter=[2],
            )

            self.assertEqual(filtered.status, "prepared")
            self.assertEqual(filtered.completed_batches, 1)
            self.assertEqual(first_provider.batch_sizes, [1])
            self.assertFalse((job.work_dir / "pipeline" / manifest[0]["output"]).exists())
            self.assertTrue((job.work_dir / "pipeline" / manifest[1]["output"]).exists())
            self.assertIn("batch-filter-done", [event["type"] for event in filtered.events])

            resume_provider = CountingFakeProvider()
            engine.provider_factory = lambda _settings: resume_provider
            finished = engine.run_job(
                job.job_id,
                ProviderSettings(
                    provider="fake",
                    model="fake-model",
                    target_language="Simplified Chinese",
                    max_concurrency=1,
                ),
                resume=True,
                ai_qa_enabled=False,
            )

            self.assertEqual(finished.status, "completed")
            self.assertEqual(finished.completed_batches, finished.total_batches)
            self.assertEqual(len(resume_provider.batch_sizes), len(manifest) - 1)
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

    def test_pre_adaptive_job_preserves_manual_execution_settings(self) -> None:
        captured_settings: list[ProviderSettings] = []

        def provider_factory(settings: ProviderSettings) -> FakeProvider:
            captured_settings.append(settings)
            return FakeProvider()

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            input_epub = tmp_path / "input.epub"
            make_minimal_epub(input_epub)
            engine = BabelJobEngine(tmp_path / "jobs", provider_factory=provider_factory)
            job = engine.create_job(
                JobRequest(
                    filename="input.epub",
                    content=input_epub.read_bytes(),
                    target_language="Simplified Chinese",
                )
            )
            state_path = job.work_dir / "job.json"
            data = json.loads(state_path.read_text(encoding="utf-8"))
            data.pop("adaptive_enabled", None)
            data.pop("adaptive_plan", None)
            state_path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

            reloaded = BabelJobEngine(tmp_path / "jobs", provider_factory=provider_factory)
            loaded = reloaded.get_job(job.job_id)
            self.assertFalse(loaded.adaptive_enabled)
            self.assertEqual(loaded.adaptive_plan, {})

            finished = reloaded.run_job(
                job.job_id,
                ProviderSettings(
                    provider="fake",
                    model="fake-model",
                    target_language="Simplified Chinese",
                    max_concurrency=1,
                    request_timeout=900,
                    max_retries=0,
                ),
                ai_qa_enabled=False,
            )

            self.assertEqual(finished.status, "completed")
            self.assertTrue(captured_settings)
            self.assertTrue(all(settings.max_concurrency == 1 for settings in captured_settings))
            self.assertTrue(all(settings.request_timeout == 900 for settings in captured_settings))
            self.assertTrue(all(settings.max_retries == 0 for settings in captured_settings))
            self.assertEqual(
                finished.adaptive_plan["execution"],
                {
                    "max_concurrency": 1,
                    "request_timeout": 900.0,
                    "max_retries": 0,
                    "dynamic_batch_split": True,
                    "reason": "Using advanced execution overrides from Settings.",
                },
            )

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


    def test_load_existing_jobs_skips_corrupt_job_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            input_epub = tmp_path / "input.epub"
            make_minimal_epub(input_epub)
            data_dir = tmp_path / "jobs"
            engine = BabelJobEngine(data_dir, provider_factory=lambda _settings: FakeProvider())
            job = engine.create_job(
                JobRequest(filename="input.epub", content=input_epub.read_bytes(), target_language="Simplified Chinese")
            )
            corrupt_dir = data_dir / "corrupt"
            corrupt_dir.mkdir(parents=True)
            (corrupt_dir / "job.json").write_text("{not valid json", encoding="utf-8")

            reloaded = BabelJobEngine(data_dir, provider_factory=lambda _settings: FakeProvider())
            jobs = reloaded.list_jobs()

            self.assertEqual([loaded.job_id for loaded in jobs], [job.job_id])

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
                ],
                "usage": {"prompt_tokens": 13, "completion_tokens": 5, "total_tokens": 18},
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
        self.assertEqual(provider.usage_snapshot()["total_tokens"], 18)



    def test_openai_responses_provider_can_request_json_schema(self) -> None:
        captured = {}

        def transport(url, headers, payload):
            captured["url"] = url
            captured["headers"] = headers
            captured["payload"] = payload
            return {
                "output_text": json.dumps(
                    {"rows": [{"id": "row-1", "translated_html": "<p>你好</p>"}]},
                    ensure_ascii=False,
                ),
                "usage": {"input_tokens": 12, "output_tokens": 5},
            }

        provider = OpenAIResponsesProvider(
            base_url="https://api.openai.com/v1",
            api_key="sk-test",
            model="gpt-4.1",
            target_language="Simplified Chinese",
            structured_output_enabled=True,
            transport=transport,
        )
        rows = [{"id": "row-1", "source_text": "Hello", "source_html": "<p>Hello</p>"}]

        translated = provider.translate_batch(rows, "", "")

        self.assertEqual(translated[0]["translated_html"], "<p>你好</p>")
        self.assertEqual(captured["url"], "https://api.openai.com/v1/responses")
        self.assertEqual(captured["payload"]["text"]["format"]["type"], "json_schema")
        self.assertEqual(provider.usage_snapshot()["total_tokens"], 17)

    def test_openai_compatible_provider_can_request_structured_output_schema(self) -> None:
        captured = {}

        def transport(url: str, headers: dict[str, str], payload: dict) -> dict:
            captured["payload"] = payload
            return {
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "rows": [
                                        {"id": "a::0001", "translated_html": "<p>你好</p>"}
                                    ]
                                }
                            )
                        }
                    }
                ]
            }

        provider = OpenAICompatibleProvider(
            base_url="https://api.example.test/v1",
            api_key="secret",
            model="demo-model",
            target_language="Simplified Chinese",
            structured_output_enabled=True,
            transport=transport,
        )
        rows = provider.translate_batch(
            [{"id": "a::0001", "source_text": "Hello", "source_html": "<p>Hello</p>"}],
            glossary="# Glossary\n",
            context="# Context\n",
        )

        response_format = captured["payload"]["response_format"]
        self.assertEqual(response_format["type"], "json_schema")
        self.assertEqual(response_format["json_schema"]["name"], "babel_translated_rows")
        self.assertTrue(response_format["json_schema"]["strict"])
        self.assertIn("`rows` array", captured["payload"]["messages"][0]["content"])
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

    def test_provider_parser_recovers_malformed_xhtml_attribute_quotes(self) -> None:
        rows = parse_translated_rows(
            '{"id":"a::0001","translated_html":"<p class="indent">第一段</p>"}\n'
            '{"id":"a::0002","translated_html":"<p><img alt="" src="cover.jpg" /></p>"}'
        )

        self.assertEqual(
            rows,
            [
                {"id": "a::0001", "translated_html": '<p class="indent">第一段</p>'},
                {"id": "a::0002", "translated_html": '<p><img alt="" src="cover.jpg" /></p>'},
            ],
        )

    def test_provider_parser_recovers_prefixed_relaxed_rows(self) -> None:
        rows = parse_translated_rows(
            'jsonl {"id":"a::0001","translated_html":"<p class="indent">第一段</p>"} '
            '{"id":"a::0002","translated_html":"<p>第二段</p>"}'
        )

        self.assertEqual(
            rows,
            [
                {"id": "a::0001", "translated_html": '<p class="indent">第一段</p>'},
                {"id": "a::0002", "translated_html": "<p>第二段</p>"},
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
