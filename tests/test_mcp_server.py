from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from babel_epub.jobs import BabelJobEngine, JobRequest
from babel_epub.mcp_server import TOOLS, BabelMCP
from test_pipeline import make_minimal_epub


class MCPServerTests(unittest.TestCase):
    def test_start_translation_schema_exposes_structured_output_flag(self) -> None:
        start_tool = next(tool for tool in TOOLS if tool["name"] == "start_translation")
        properties = start_tool["inputSchema"]["properties"]

        self.assertIn("structured_output_enabled", properties)
        self.assertEqual(properties["structured_output_enabled"]["default"], False)
        self.assertIn("memory_enabled", properties)
        self.assertEqual(properties["memory_enabled"]["default"], False)
        self.assertIn("memory_project_id", properties)
        self.assertIn("memory_path", properties)
        self.assertIn("batch_filter", properties)
        self.assertEqual(properties["batch_filter"]["items"]["type"], "integer")
        self.assertIn("max_requests_per_minute", properties)
        self.assertIn("max_tokens_per_minute", properties)
        self.assertIn("budget_limit", properties)
        self.assertIn("input_cost_per_1m_tokens", properties)
        self.assertIn("output_cost_per_1m_tokens", properties)
        self.assertNotIn("model", start_tool["inputSchema"]["required"])

    def test_extended_tool_list_is_exposed(self) -> None:
        names = {tool["name"] for tool in TOOLS}
        for name in {
            "list_jobs",
            "artifact_path",
            "read_glossary_terms",
            "update_glossary_terms",
            "import_glossary",
            "export_glossary",
            "resume_failed_job",
            "retry_batch",
        }:
            self.assertIn(name, names)

    def test_extended_glossary_and_artifact_tools_return_structured_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            input_epub = tmp_path / "input.epub"
            make_minimal_epub(input_epub)
            server = BabelMCP()
            server.engine = BabelJobEngine(tmp_path / "jobs")
            job = server.engine.create_job(
                JobRequest(filename="input.epub", content=input_epub.read_bytes(), target_language="Simplified Chinese")
            )

            listed = server.call_tool("list_jobs", {})
            self.assertEqual(listed["jobs"][0]["job_id"], job.job_id)

            artifact = server.call_tool("artifact_path", {"job_id": job.job_id, "artifact": "glossary"})
            self.assertEqual(artifact["path"], str(job.glossary_path))

            updated = server.call_tool(
                "update_glossary_terms",
                {
                    "job_id": job.job_id,
                    "glossary_terms": [
                        {
                            "source": "Rook",
                            "translation": "鲁克",
                            "type": "person",
                            "status": "approved",
                            "locked": True,
                        }
                    ],
                },
            )
            self.assertEqual(updated["glossary_terms"][0]["translation"], "鲁克")

            read_back = server.call_tool("read_glossary_terms", {"job_id": job.job_id})
            self.assertEqual(read_back["glossary_terms"][0]["source"], "Rook")

            exported = server.call_tool("export_glossary", {"job_id": job.job_id, "format": "csv"})
            self.assertIn("Rook", exported["content"])

            imported = server.call_tool(
                "import_glossary",
                {
                    "job_id": job.job_id,
                    "format": "csv",
                    "content": "source,translation,type,status,locked\nDeepwoods,深林,place,approved,true\n",
                },
            )
            self.assertEqual(imported["summary"]["imported"], 1)
            self.assertTrue(any(term["source"] == "Deepwoods" for term in imported["glossary_terms"]))

    def test_retry_batch_does_not_delete_output_for_running_job(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            input_epub = tmp_path / "input.epub"
            make_minimal_epub(input_epub)
            server = BabelMCP()
            server.engine = BabelJobEngine(tmp_path / "jobs")
            job = server.engine.create_job(
                JobRequest(filename="input.epub", content=input_epub.read_bytes(), target_language="Simplified Chinese")
            )
            manifest = json.loads(
                (job.work_dir / "pipeline" / "batch_manifest.json").read_text(encoding="utf-8")
            )
            output = job.work_dir / "pipeline" / manifest[0]["output"]
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text("translated", encoding="utf-8")
            server.engine._mutate_job(job.job_id, lambda current: setattr(current, "status", "running"))

            with self.assertRaisesRegex(ValueError, "while the job is running"):
                server.call_tool(
                    "retry_batch",
                    {"job_id": job.job_id, "batch": 1, "provider": "fake", "model": "fake-model"},
                )

            self.assertTrue(output.exists())


if __name__ == "__main__":
    unittest.main()
