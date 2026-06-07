from __future__ import annotations

import unittest
import tempfile
from pathlib import Path

from babel_epub.web import (
    _merge_provider_settings,
    _package_version,
    _parse_multipart_form,
    _public_provider_settings,
    _read_provider_settings,
    _resolve_static_path,
    _write_provider_settings,
    render_index_html,
)


ROOT = Path(__file__).resolve().parents[1]


class WebTests(unittest.TestCase):
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
        self.assertIn("glossary-terms", app_source)
        self.assertIn("Rows per page", app_source)
        self.assertIn("Previous", app_source)
        self.assertIn("Next", app_source)
        self.assertIn("AI QA repair loop", app_source)
        self.assertIn("Auto-generate output title", app_source)
        self.assertIn("onDrop", app_source)
        self.assertIn("Process terminal collapsed", app_source)
        self.assertIn("progress-track", app_source)

    def test_static_asset_resolver_serves_assets_without_path_traversal(self) -> None:
        assets = sorted((ROOT / "src" / "babel_epub" / "static" / "assets").glob("index-*.js"))

        self.assertTrue(assets)
        self.assertEqual(_resolve_static_path(f"/assets/{assets[0].name}"), assets[0])
        self.assertIsNone(_resolve_static_path("/../pyproject.toml"))

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
                    "ai_qa_enabled": True,
                    "auto_title_enabled": True,
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
                },
                stored,
            )

            self.assertEqual(stored["api_key"], "sk-secret")
            self.assertTrue(public["has_api_key"])
            self.assertNotIn("api_key", public)
            self.assertEqual(merged["api_key"], "sk-secret")
            self.assertTrue(public["ai_qa_enabled"])
            self.assertTrue(public["auto_title_enabled"])

    def test_meta_version_uses_package_version(self) -> None:
        self.assertEqual(_package_version(), "0.7.0")


if __name__ == "__main__":
    unittest.main()
