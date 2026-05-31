# Plan: Self-hosted Web And Agent MVP

## Objective

Make Babel easier to use without discarding the CLI core:

- Self-hosted Web UI for uploading EPUBs, configuring an API provider, tracking translation progress, and downloading outputs.
- Docker deployment.
- User-configurable translation providers.
- Codex skill installation material.
- Claude MCP server entrypoint.
- Release update after implementation.

## Decision

Use one core pipeline and expose it through multiple adapters:

- `babel_epub.pipeline`: existing EPUB extract/validate/apply/audit core.
- `babel_epub.jobs`: local job engine for prepared workspaces, state, progress, retry, provider execution.
- `babel_epub.providers`: configurable model-provider adapters.
- `babel_epub.web`: local Web UI and HTTP API.
- `babel_epub.mcp_server`: stdio MCP bridge for Claude.
- `integrations/codex/babel/SKILL.md`: Codex installation/use guide.

## Scope

MVP is single-user self-hosted. It does not include authentication, cloud storage, billing, collaborative editing, or a hosted SaaS.

## Implementation Steps

1. Add tests for job engine, provider prompt/response handling, and Web shell output.
2. Implement provider adapters with an OpenAI-compatible endpoint first and a deterministic fake provider for tests.
3. Implement job engine that can prepare, translate, validate, apply, audit, and report a job.
4. Implement a dependency-free local Web server with upload, start, status, glossary update, and download routes.
5. Add Dockerfile and Compose file.
6. Add Codex skill and Claude MCP integration docs/server.
7. Update README, PRD, architecture, changelog, version, and release notes.
8. Verify tests, OpenArc scan, Docker build if available, git push, and GitHub release.

## Testing Strategy

- Unit tests generate miniature EPUB fixtures; no copyrighted content.
- Job engine test uses a fake provider and verifies output EPUB/audit/report exist.
- Provider tests validate OpenAI-compatible request/response conversion without network.
- Web tests verify the HTML shell and API route helpers expose expected commands.
- Existing pipeline tests continue to pass.

## Risks

- Full automatic high-quality literary translation still depends on model quality and prompt discipline.
- Storing API keys in a self-hosted app is sensitive; MVP keeps them in process/job state and does not write them to durable job files.
- A dependency-free Web server is less feature-rich than FastAPI, but keeps install/Docker friction low.

## Rollback

The CLI core remains intact. If Web/MCP integrations fail, users can continue using `babel-epub` commands.
