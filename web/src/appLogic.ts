export type ProviderSettingsLike = {
  provider: string;
  model: string;
  api_key: string;
  max_concurrency: string;
  request_timeout: string;
  max_retries: string;
  adaptive_enabled: boolean;
  batch_char_limit: string;
  ai_qa_enabled: boolean;
  auto_title_enabled: boolean;
  structured_output_enabled?: boolean;
  memory_enabled?: boolean;
  memory_project_id?: string;
  max_requests_per_minute?: string;
  max_tokens_per_minute?: string;
  budget_limit?: string;
  input_cost_per_1m_tokens?: string;
  output_cost_per_1m_tokens?: string;
  [key: string]: unknown;
};

export type PrepareFormLike = {
  target_language: string;
  title: string;
  language: string;
  output_format: string;
};

export type GlossaryTermLike = {
  translation?: string;
  status?: string;
  locked?: boolean;
};

export function integerOption(value: string, fallback: number, minimum: number): number {
  const parsed = Number.parseInt(value, 10);
  return Number.isFinite(parsed) && parsed >= minimum ? parsed : fallback;
}

export function canUseProvider(provider: ProviderSettingsLike, hasSavedApiKey: boolean): boolean {
  const providerName = provider.provider.trim().toLowerCase();
  if (["fake", "dry-run", "dry_run"].includes(providerName)) {
    return true;
  }
  const hasApiKey = Boolean(provider.api_key.trim() || hasSavedApiKey);
  if (["deepl", "deep-l", "google", "google-translate", "google_translate"].includes(providerName)) {
    return hasApiKey;
  }
  const hasModel = Boolean(provider.model.trim());
  if (["ollama", "local", "local-openai", "local_openai"].includes(providerName)) {
    return hasModel;
  }
  if (["openai", "openai-compatible", "openai_compatible", "compatible", "openai-responses", "openai_responses", "responses"].includes(providerName)) {
    const baseUrl = String(provider.base_url || "").trim();
    return Boolean(hasModel && baseUrl && (!baseUrl.toLowerCase().includes("api.openai.com") || hasApiKey));
  }
  if (["anthropic", "claude"].includes(providerName)) {
    return hasModel && hasApiKey;
  }
  return false;
}

export function settingsPayloadFromProvider(provider: ProviderSettingsLike, hasSavedApiKey: boolean) {
  return {
    ...provider,
    max_concurrency: integerOption(provider.max_concurrency, 3, 1),
    request_timeout: integerOption(provider.request_timeout, 300, 1),
    max_retries: integerOption(provider.max_retries, 2, 0),
    adaptive_enabled: provider.adaptive_enabled,
    batch_char_limit: integerOption(provider.batch_char_limit, 6000, 1000),
    memory_project_id: String(provider.memory_project_id || "").trim(),
    max_requests_per_minute: integerOption(String(provider.max_requests_per_minute || "0"), 0, 0),
    max_tokens_per_minute: integerOption(String(provider.max_tokens_per_minute || "0"), 0, 0),
    budget_limit: Math.max(0, Number.parseFloat(String(provider.budget_limit || "0")) || 0),
    input_cost_per_1m_tokens: Math.max(0, Number.parseFloat(String(provider.input_cost_per_1m_tokens || "0")) || 0),
    output_cost_per_1m_tokens: Math.max(0, Number.parseFloat(String(provider.output_cost_per_1m_tokens || "0")) || 0),
    auto_title_enabled: canUseProvider(provider, hasSavedApiKey) && provider.auto_title_enabled,
  };
}

export function startPayloadFromProvider(
  provider: ProviderSettingsLike,
  hasSavedApiKey: boolean,
  targetLanguage: string,
  resume: boolean,
) {
  return {
    ...settingsPayloadFromProvider(provider, hasSavedApiKey),
    target_language: targetLanguage,
    resume,
  };
}

export function buildPrepareUploadUrl(
  form: PrepareFormLike,
  provider: Pick<ProviderSettingsLike, "adaptive_enabled" | "batch_char_limit">,
  filename = "book.epub",
): string {
  const query = new URLSearchParams({
    filename,
    target_language: form.target_language,
    title: form.title,
    language: form.language,
    output_format: form.output_format,
    adaptive_enabled: String(provider.adaptive_enabled),
  });
  if (!provider.adaptive_enabled) {
    query.set("max_chars", String(integerOption(provider.batch_char_limit, 6000, 1000)));
  }
  return `/api/jobs?${query.toString()}`;
}

export function glossaryStats(terms: GlossaryTermLike[]) {
  return terms.reduce(
    (stats, term) => {
      const status = term.status || "pending";
      const translation = (term.translation || "").trim();
      stats.total += 1;
      if (status === "ignored") {
        stats.ignored += 1;
      } else if (status === "approved" || term.locked) {
        stats.approved += 1;
      } else if (status === "pending") {
        stats.pending += 1;
        if (!translation) {
          stats.empty += 1;
        }
      }
      return stats;
    },
    { total: 0, approved: 0, pending: 0, empty: 0, ignored: 0 },
  );
}

export function hasGlossaryWarnings(terms: GlossaryTermLike[]): boolean {
  const stats = glossaryStats(terms);
  return stats.pending > 0 || stats.empty > 0;
}

export function shouldOpenGlossaryModal(terms: GlossaryTermLike[]): boolean {
  return terms.length > 0;
}
