from __future__ import annotations

import zipfile
import tempfile
import unittest
from pathlib import Path

from babel_epub.jobs import BabelJobEngine, JobRequest, ProviderSettings
from babel_epub.providers import FakeProvider, OpenAICompatibleProvider
from test_pipeline import make_minimal_epub


class JobEngineTests(unittest.TestCase):
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
            self.assertEqual(finished.completed_batches, 1)
            self.assertEqual(finished.total_batches, 1)
            self.assertTrue(finished.output_epub and finished.output_epub.exists())
            self.assertTrue(finished.audit_path and finished.audit_path.exists())
            self.assertTrue(finished.report_path and finished.report_path.exists())
            with zipfile.ZipFile(finished.output_epub) as archive:
                self.assertIsNone(archive.testzip())
                chapter = archive.read("OEBPS/chapter1.xhtml").decode("utf-8")
            self.assertIn("测试翻译", chapter)

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
        self.assertEqual(rows, [{"id": "a::0001", "translated_html": "<p>你好</p>"}])


if __name__ == "__main__":
    unittest.main()
