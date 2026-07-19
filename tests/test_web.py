from __future__ import annotations

import json
import os
import unittest
import tempfile
import time
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

from babel_epub import __version__
from babel_epub.jobs import BabelJobEngine, JobRequest
from babel_epub.providers import TranslationProvider
from babel_epub.web import (
    BabelWebHandler,
    FormPart,
    _field_int,
    _max_upload_bytes,
    _merge_provider_settings,
    _package_version,
    _parse_multipart_form,
    _public_provider_settings,
    _read_provider_settings,
    _resolve_static_path,
    _write_provider_settings,
    render_index_html,
)
from test_pipeline import make_minimal_epub


ROOT = Path(__file__).resolve().parents[1]


class WebTests(unittest.TestCase):
    def test_autofill_endpoint_reuses_saved_provider_key(self) -> None:
        class CapturingProvider(TranslationProvider):
            api_key = ""

            def __init__(self, api_key: str) -> None:
                type(self).api_key = api_key

            def translate_batch(self, rows: list[dict], glossary: str, context: str) -> list[dict]:
                return [
                    {"id": row["id"], "translated_html": f"<p>译:{row['source_text']}</p>"}
                    for row in rows
                ]

        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp) / "jobs"
            input_epub = Path(tmp) / "input.epub"
            make_minimal_epub(input_epub)
            engine = BabelJobEngine(
                data_dir,
                provider_factory=lambda settings: CapturingProvider(settings.api_key),
            )
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
                        "frequency": 3,
                        "evidence": [],
                        "status": "pending",
                        "confidence": 0.6,
                        "locked": False,
                    }
                ],
            )
            _write_provider_settings(
                data_dir,
                {
                    "provider": "openai-compatible",
                    "base_url": "https://api.example.test/v1",
                    "model": "demo-model",
                    "api_key": "saved-secret",
                },
            )
            payload = json.dumps(
                {
                    "provider": "openai-compatible",
                    "base_url": "https://api.example.test/v1",
                    "model": "demo-model",
                    "api_key": "",
                    "target_language": "Simplified Chinese",
                }
            ).encode("utf-8")
            captured = {}
            handler = object.__new__(BabelWebHandler)
            handler.engine = engine
            handler.headers = {"Content-Length": str(len(payload))}
            handler.rfile = BytesIO(payload)
            handler._send_json = lambda data, status=200: captured.update(data=data, status=status)

            handler._autofill_glossary_terms(job.job_id)

            body = captured["data"]
            self.assertEqual(CapturingProvider.api_key, "saved-secret")
            self.assertEqual(body["glossary_terms"][0]["translation"], "译:Rook")
            self.assertEqual(body["filled"], 1)

    def test_web_shell_exposes_upload_provider_progress_and_downloads(self) -> None:
        html = render_index_html()
        app_source = (ROOT / "web" / "src" / "App.tsx").read_text(encoding="utf-8")

        self.assertIn('id="root"', html)
        self.assertIn('type="module"', html)
        self.assertIn("/assets/", html)
        self.assertIn("Upload Book", app_source)
        self.assertIn(".azw3", app_source)
        self.assertIn(".mobi", app_source)
        self.assertIn(".pdf", app_source)
        self.assertIn("API Provider", app_source)
        self.assertIn("SettingsModal", app_source)
        self.assertNotIn("ProviderPanel", app_source)
        self.assertIn("Concurrency", app_source)
        self.assertIn("Request timeout", app_source)
        self.assertIn("Retries", app_source)
        self.assertIn("Saved API key available", app_source)
        self.assertIn("/api/provider-settings", app_source)
        self.assertIn("Glossary", app_source)
        self.assertIn("Job Progress", app_source)
        self.assertIn("max_concurrency", app_source)
        self.assertIn("request_timeout", app_source)
        self.assertIn("max_retries", app_source)
        self.assertIn("active_batches", app_source)
        self.assertIn("failed_batches", app_source)
        self.assertIn("Output format", app_source)
        self.assertIn("Batch character limit", app_source)
        self.assertIn("Adaptive processing", app_source)
        self.assertIn("adaptive_enabled", app_source)
        self.assertNotIn('name="max_chars"', app_source)
        self.assertIn("DiagnosticPanel", app_source)
        self.assertIn("Download Book", app_source)
        self.assertIn("AZW3", app_source)
        self.assertIn("HTMLZ", app_source)
        self.assertIn("KEPUB", app_source)
        self.assertIn("terminalLog", app_source)
        self.assertIn("Resume Translation", app_source)
        self.assertIn("loadLatestJob", app_source)
        self.assertIn("/api/jobs", app_source)
        self.assertIn("OpenAI Compatible", app_source)
        self.assertIn("Guide", app_source)
        self.assertIn("Start with upload", app_source)
        self.assertIn("View current job", app_source)
        self.assertIn("中文", app_source)
        self.assertIn("LanguageSelect", app_source)
        self.assertIn("language.zh} / {language.label", app_source)
        self.assertIn("zh-CN", app_source)
        self.assertIn("准备工作区", app_source)
        self.assertIn("审查术语表", app_source)
        self.assertIn("粗略耗时预估", app_source)
        self.assertIn("formatEstimateRange", app_source)
        self.assertIn("Provider 用量", app_source)
        self.assertIn("UsagePanel", app_source)
        self.assertIn("usage_summary", app_source)
        self.assertIn("glossary-terms", app_source)
        self.assertIn("glossary-terms/autofill", app_source)
        self.assertIn("GlossaryModal", app_source)
        self.assertIn("AI Fill Translations", app_source)
        self.assertIn("ProgressBar isIndeterminate", app_source)
        self.assertIn("Drafting glossary translations", app_source)
        self.assertIn("Approve all", app_source)
        self.assertIn("Review Glossary", app_source)
        self.assertIn("Start with pending glossary terms?", app_source)
        self.assertIn("Rows per page", app_source)
        self.assertIn("Previous", app_source)
        self.assertIn("Next", app_source)
        self.assertIn("Structured JSON output", app_source)
        self.assertIn("structured_output_enabled", app_source)
        self.assertIn("AI QA repair loop", app_source)
        self.assertIn("Auto-generate output title", app_source)
        self.assertIn("onDrop", app_source)
        self.assertIn("Process terminal collapsed", app_source)
        self.assertIn('isIndeterminate={job?.status === "preparing"}', app_source)

    def test_static_asset_resolver_serves_assets_without_path_traversal(self) -> None:
        assets = sorted((ROOT / "src" / "babel_epub" / "static" / "assets").glob("index-*.js"))

        self.assertTrue(assets)
        self.assertEqual(_resolve_static_path(f"/assets/{assets[0].name}"), assets[0])
        self.assertIsNone(_resolve_static_path("/../pyproject.toml"))


    def test_create_job_rejects_missing_content_length_oversize_and_bad_multipart(self) -> None:
        handler = object.__new__(BabelWebHandler)
        captured = []
        handler.send_error = lambda status, message=None: captured.append((status, message))
        handler._send_json = lambda data, status=200: captured.append((status, data))
        handler.headers = {}
        handler.rfile = BytesIO(b"")

        handler._create_job()
        self.assertEqual(captured[-1][0], 411)

        with patch.dict(os.environ, {"BABEL_MAX_UPLOAD_MB": "1"}):
            self.assertEqual(_max_upload_bytes(), 1024 * 1024)
            handler.headers = {"Content-Length": str(1024 * 1024 + 1), "Content-Type": "multipart/form-data; boundary=abc"}
            handler.rfile = BytesIO(b"")
            handler._create_job()
        self.assertEqual(captured[-1][0], 413)

        handler.headers = {"Content-Length": "7", "Content-Type": "multipart/form-data; boundary=abc"}
        handler.rfile = BytesIO(b"notbody")
        handler._create_job()
        self.assertEqual(captured[-1][0], 400)
        self.assertIn("boundary", captured[-1][1])

    def test_raw_upload_streams_to_async_preparation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            input_epub = tmp_path / "input.epub"
            make_minimal_epub(input_epub)
            payload = input_epub.read_bytes()
            engine = BabelJobEngine(tmp_path / "jobs")
            captured = {}
            handler = object.__new__(BabelWebHandler)
            handler.engine = engine
            handler.path = (
                "/api/jobs?filename=book.epub&target_language=Simplified+Chinese"
                "&output_format=epub&adaptive_enabled=true"
            )
            handler.headers = {
                "Content-Length": str(len(payload)),
                "Content-Type": "application/octet-stream",
            }
            handler.rfile = BytesIO(payload)
            handler._send_json = lambda data, status=200: captured.update(data=data, status=status)

            handler._create_job()

            self.assertEqual(captured["status"], 202)
            job_id = captured["data"]["job"]["job_id"]
            deadline = time.time() + 3
            while time.time() < deadline and engine.get_job(job_id).status == "preparing":
                time.sleep(0.01)
            prepared = engine.get_job(job_id)
            self.assertEqual(prepared.status, "prepared")
            self.assertTrue(prepared.adaptive_plan["enabled"])

    def test_api_token_auth_blocks_api_and_download_paths_when_configured(self) -> None:
        handler = object.__new__(BabelWebHandler)
        captured = []
        handler.send_error = lambda status, message=None: captured.append((status, message))
        handler._send_json = lambda data, status=200: captured.append((status, data))
        handler.headers = {}
        handler.path = "/api/jobs/job-1/download/output"
        with patch.dict(os.environ, {"BABEL_WEB_TOKEN": "secret"}):
            self.assertFalse(handler._is_authorized_api_request())
            handler.do_GET()
            self.assertEqual(captured[-1][0], 401)
            handler.headers = {"Authorization": "Bearer secret"}
            self.assertTrue(handler._is_authorized_api_request())
            handler.headers = {"X-Babel-Token": "secret"}
            self.assertTrue(handler._is_authorized_api_request())


    def test_dynamic_batch_form_field_requires_positive_integer(self) -> None:
        self.assertEqual(_field_int({"max_chars": FormPart("max_chars", value="1200")}, "max_chars"), 1200)
        self.assertIsNone(_field_int({}, "max_chars"))
        with self.assertRaisesRegex(ValueError, "max_chars must be a positive integer"):
            _field_int({"max_chars": FormPart("max_chars", value="0")}, "max_chars")
        with self.assertRaisesRegex(ValueError, "max_chars must be a positive integer"):
            _field_int({"max_chars": FormPart("max_chars", value="abc")}, "max_chars")

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

    def test_provider_settings_persist_without_public_key_leak(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp)
            _write_provider_settings(
                data_dir,
                {
                    "provider": "openai-compatible",
                    "base_url": "https://api.openai.com/v1",
                    "model": "gpt-4.1",
                    "api_key": "sk-secret",
                    "max_concurrency": 3,
                    "request_timeout": 300,
                    "max_retries": 1,
                    "structured_output_enabled": True,
                    "memory_enabled": True,
                    "memory_project_id": "series-a",
                    "ai_qa_enabled": True,
                    "auto_title_enabled": True,
                    "max_requests_per_minute": 12,
                    "max_tokens_per_minute": 24000,
                    "budget_limit": 1.25,
                    "input_cost_per_1m_tokens": 2.5,
                    "output_cost_per_1m_tokens": 7.5,
                },
            )

            stored = _read_provider_settings(data_dir)
            public = _public_provider_settings(stored)
            merged = _merge_provider_settings(
                {
                    "provider": "openai-compatible",
                    "base_url": "https://api.openai.com/v1",
                    "model": "gpt-4.1",
                    "api_key": "",
                    "structured_output_enabled": "",
                    "memory_enabled": "",
                    "memory_project_id": "",
                    "max_requests_per_minute": "",
                    "max_tokens_per_minute": "",
                    "budget_limit": "",
                    "input_cost_per_1m_tokens": "",
                    "output_cost_per_1m_tokens": "",
                },
                stored,
            )

            self.assertEqual(stored["api_key"], "sk-secret")
            self.assertTrue(public["has_api_key"])
            self.assertNotIn("api_key", public)
            self.assertEqual(merged["api_key"], "sk-secret")
            self.assertTrue(stored["structured_output_enabled"])
            self.assertTrue(public["structured_output_enabled"])
            self.assertTrue(merged["structured_output_enabled"])
            self.assertTrue(stored["memory_enabled"])
            self.assertTrue(public["memory_enabled"])
            self.assertTrue(merged["memory_enabled"])
            self.assertEqual(public["memory_project_id"], "series-a")
            self.assertEqual(merged["memory_project_id"], "series-a")
            self.assertTrue(public["ai_qa_enabled"])
            self.assertTrue(public["auto_title_enabled"])
            self.assertEqual(public["max_requests_per_minute"], 12)
            self.assertEqual(public["max_tokens_per_minute"], 24000)
            self.assertEqual(public["budget_limit"], 1.25)
            self.assertEqual(public["input_cost_per_1m_tokens"], 2.5)
            self.assertEqual(public["output_cost_per_1m_tokens"], 7.5)
            self.assertEqual(merged["max_requests_per_minute"], 12)
            self.assertEqual(merged["budget_limit"], 1.25)

    def test_glossary_import_and_export_endpoints(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            input_epub = tmp_path / "input.epub"
            make_minimal_epub(input_epub)
            engine = BabelJobEngine(tmp_path / "jobs", provider_factory=lambda _settings: FakeProvider())
            job = engine.create_job(
                JobRequest(filename="input.epub", content=input_epub.read_bytes(), target_language="Simplified Chinese")
            )
            captured = {}
            handler = object.__new__(BabelWebHandler)
            handler.engine = engine
            body = json.dumps(
                {
                    "format": "csv",
                    "content": "source,translation,type,status,confidence,locked\nRook,鲁克,person,approved,0.95,true\n",
                }
            ).encode("utf-8")
            handler.rfile = BytesIO(body)
            handler.headers = {"Content-Length": str(len(body))}
            handler._send_json = lambda data, status=200: captured.update(data=data, status=status)

            handler._import_glossary_terms(job.job_id)
            response = captured["data"]
            self.assertEqual(response["summary"]["imported"], 1)
            self.assertEqual(response["glossary_terms"][0]["translation"], "鲁克")

            export_handler = object.__new__(BabelWebHandler)
            export_handler.engine = engine
            export_handler.path = f"/api/jobs/{job.job_id}/glossary-terms/export?format=csv"
            export_handler.headers_sent = {}
            export_handler.wfile = BytesIO()
            export_handler.send_response = lambda status: None
            export_handler.send_header = lambda key, value: export_handler.headers_sent.update({key: value})
            export_handler.end_headers = lambda: None
            export_handler._export_glossary_terms(job.job_id)
            exported = export_handler.wfile.getvalue().decode("utf-8")
            self.assertEqual(export_handler.headers_sent["Content-Type"], "text/csv; charset=utf-8")
            self.assertIn("source,translation", exported)
            self.assertIn("Rook", exported)

    def test_meta_version_uses_package_version(self) -> None:
        self.assertEqual(_package_version(), __version__)


if __name__ == "__main__":
    unittest.main()
