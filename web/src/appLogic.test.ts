import test from "node:test";
import assert from "node:assert/strict";

import {
  buildPrepareFormData,
  canUseProvider,
  glossaryStats,
  hasGlossaryWarnings,
  settingsPayloadFromProvider,
  shouldOpenGlossaryModal,
  startPayloadFromProvider,
} from "./appLogic.ts";

const provider = {
  provider: "openai-compatible",
  base_url: "https://api.example.test/v1",
  api_key: "",
  model: "demo-model",
  max_concurrency: "4",
  request_timeout: "450",
  max_retries: "3",
  structured_output_enabled: true,
  memory_enabled: true,
  memory_project_id: " series-a ",
  max_requests_per_minute: "12",
  max_tokens_per_minute: "24000",
  budget_limit: "1.25",
  input_cost_per_1m_tokens: "2.5",
  output_cost_per_1m_tokens: "7.5",
  ai_qa_enabled: true,
  auto_title_enabled: true,
};

test("prepare upload form includes ebook metadata and optional max_chars", async () => {
  const body = buildPrepareFormData(
    {
      target_language: "Simplified Chinese",
      title: "示例书",
      language: "zh-CN",
      output_format: "epub",
      max_chars: " 1800 ",
    },
    new Blob(["epub-bytes"], { type: "application/epub+zip" }),
    "sample.epub",
  );

  assert.equal(body.get("target_language"), "Simplified Chinese");
  assert.equal(body.get("title"), "示例书");
  assert.equal(body.get("language"), "zh-CN");
  assert.equal(body.get("output_format"), "epub");
  assert.equal(body.get("max_chars"), "1800");
  const uploaded = body.get("epub");
  assert.ok(uploaded instanceof File);
  assert.equal(uploaded.name, "sample.epub");
});

test("prepare upload form omits blank max_chars", () => {
  const body = buildPrepareFormData(
    { target_language: "English", title: "", language: "en", output_format: "pdf", max_chars: "   " },
    new Blob(["book"]),
  );

  assert.equal(body.has("max_chars"), false);
});

test("settings payload normalizes provider controls and preserves structured output", () => {
  const payload = settingsPayloadFromProvider(provider, true);

  assert.equal(payload.max_concurrency, 4);
  assert.equal(payload.request_timeout, 450);
  assert.equal(payload.max_retries, 3);
  assert.equal(payload.structured_output_enabled, true);
  assert.equal(payload.memory_enabled, true);
  assert.equal(payload.memory_project_id, "series-a");
  assert.equal(payload.max_requests_per_minute, 12);
  assert.equal(payload.max_tokens_per_minute, 24000);
  assert.equal(payload.budget_limit, 1.25);
  assert.equal(payload.input_cost_per_1m_tokens, 2.5);
  assert.equal(payload.output_cost_per_1m_tokens, 7.5);
  assert.equal(payload.auto_title_enabled, true);
});

test("settings payload disables title automation when provider cannot run", () => {
  const payload = settingsPayloadFromProvider({ ...provider, model: "", api_key: "" }, false);

  assert.equal(canUseProvider({ ...provider, model: "", api_key: "" }, false), false);
  assert.equal(payload.auto_title_enabled, false);
});

test("DeepL and Google Translate do not require a model", () => {
  assert.equal(canUseProvider({ ...provider, provider: "deepl", model: "", api_key: "secret" }, false), true);
  assert.equal(canUseProvider({ ...provider, provider: "google-translate", model: "", api_key: "" }, true), true);
  assert.equal(canUseProvider({ ...provider, provider: "deepl", model: "", api_key: "" }, false), false);
});

test("local providers do not require an API key", () => {
  assert.equal(canUseProvider({ ...provider, provider: "ollama", api_key: "" }, false), true);
  assert.equal(
    canUseProvider({ ...provider, provider: "openai-compatible", base_url: "http://localhost:8000/v1", api_key: "" }, false),
    true,
  );
  assert.equal(canUseProvider({ ...provider, provider: "openai-compatible", base_url: "https://api.openai.com/v1", api_key: "" }, false), false);
});

test("start payload carries resume flag and target language", () => {
  const payload = startPayloadFromProvider(provider, true, "Japanese", true);

  assert.equal(payload.target_language, "Japanese");
  assert.equal(payload.resume, true);
  assert.equal(payload.max_concurrency, 4);
});

test("glossary warnings and modal visibility match review workflow", () => {
  const terms = [
    { status: "approved", translation: "鲁克", locked: true },
    { status: "pending", translation: "" },
    { status: "ignored", translation: "" },
  ];

  assert.deepEqual(glossaryStats(terms), { total: 3, approved: 1, pending: 1, empty: 1, ignored: 1 });
  assert.equal(hasGlossaryWarnings(terms), true);
  assert.equal(shouldOpenGlossaryModal(terms), true);
  assert.equal(shouldOpenGlossaryModal([]), false);
});
