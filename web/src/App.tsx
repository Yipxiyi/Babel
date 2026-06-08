import type * as React from "react";
import { forwardRef, useEffect, useRef, useState } from "react";
import {
  ArrowClockwise,
  CaretDown,
  CheckCircle,
  ClockCounterClockwise,
  DownloadSimple,
  FileArrowUp,
  FileText,
  FloppyDisk,
  GearSix,
  GithubLogo,
  Globe,
  LockKey,
  MagnifyingGlass,
  Play,
  Plus,
  Question,
  Table,
  TerminalWindow,
  WarningCircle,
  X,
} from "@phosphor-icons/react";
import babelIconUrl from "../../docs/assets/brand/babel-icon.png";

type Locale = "en" | "zh";
type JobStatus = "prepared" | "running" | "failed" | "completed" | string;
type Tone = "idle" | "prepared" | "running" | "failed" | "completed";
type IconComponent = React.ComponentType<{
  size?: number;
  weight?: "thin" | "light" | "regular" | "bold" | "fill" | "duotone";
  className?: string;
}>;

type BatchSummary = {
  batch?: number;
  file?: string;
  chapter_label?: string;
  block_count?: number;
};

type JobEvent = {
  ts?: string;
  type: string;
  message: string;
  batch?: BatchSummary;
};

type GlossaryTerm = {
  source: string;
  translation: string;
  type: string;
  aliases: string[];
  frequency: number;
  evidence: string[];
  status: string;
  confidence: number;
  locked: boolean;
};

type BabelJob = {
  job_id: string;
  status: JobStatus;
  filename: string;
  input_format?: string;
  output_format?: string;
  target_language: string;
  title?: string;
  language?: string;
  total_batches: number;
  completed_batches: number;
  block_count?: number;
  message?: string;
  current_batch?: BatchSummary | null;
  failed_batch?: BatchSummary | null;
  active_batches?: BatchSummary[];
  failed_batches?: BatchSummary[];
  max_concurrency?: number;
  last_active_at?: string;
  events?: JobEvent[];
  errors?: string[];
  ai_qa_status?: string;
  ai_qa_summary?: {
    detected?: number;
    remaining?: number;
    blocking_remaining?: number;
    nonblocking_remaining?: number;
  };
  ai_fix_summary?: { fixed?: number; rounds?: number };
  glossary_summary?: { total?: number; approved?: number; pending?: number; ignored?: number };
  usage_summary?: {
    requests?: number;
    prompt_tokens?: number;
    completion_tokens?: number;
    total_tokens?: number;
  };
  generated_title?: string;
  title_source?: string;
};

type ProviderSettings = {
  provider: string;
  base_url: string;
  api_key: string;
  model: string;
  max_concurrency: string;
  request_timeout: string;
  max_retries: string;
  ai_qa_enabled: boolean;
  auto_title_enabled: boolean;
};

type FormState = {
  target_language: string;
  title: string;
  language: string;
  output_format: string;
};

type Notice = { kind: "info" | "error" | "success"; text: string } | null;

type Meta = {
  version: string;
  github_url: string;
  supported_input_formats: string[];
  supported_output_formats: string[];
};

const ACCEPT_EXTENSIONS = [
  ".epub",
  ".txt",
  ".html",
  ".htm",
  ".xhtml",
  ".mobi",
  ".azw",
  ".azw3",
  ".kfx",
  ".pdf",
  ".fb2",
  ".docx",
  ".rtf",
  ".cbz",
  ".cbr",
].join(",");

const outputFormats = [
  { value: "epub", label: "EPUB" },
  { value: "mobi", label: "MOBI" },
  { value: "azw3", label: "AZW3" },
  { value: "pdf", label: "PDF" },
  { value: "docx", label: "DOCX" },
  { value: "txt", label: "TXT" },
  { value: "html", label: "HTML" },
  { value: "htmlz", label: "HTMLZ" },
  { value: "kepub", label: "KEPUB" },
  { value: "rtf", label: "RTF" },
  { value: "fb2", label: "FB2" },
] as const;

const languages = [
  { label: "Simplified Chinese", code: "zh-CN", zh: "简体中文" },
  { label: "Traditional Chinese", code: "zh-TW", zh: "繁体中文" },
  { label: "English", code: "en", zh: "英语" },
  { label: "Japanese", code: "ja", zh: "日语" },
  { label: "Korean", code: "ko", zh: "韩语" },
  { label: "French", code: "fr", zh: "法语" },
  { label: "German", code: "de", zh: "德语" },
  { label: "Spanish", code: "es", zh: "西班牙语" },
  { label: "Portuguese", code: "pt", zh: "葡萄牙语" },
  { label: "Italian", code: "it", zh: "意大利语" },
  { label: "Russian", code: "ru", zh: "俄语" },
  { label: "Arabic", code: "ar", zh: "阿拉伯语" },
  { label: "Hindi", code: "hi", zh: "印地语" },
  { label: "Vietnamese", code: "vi", zh: "越南语" },
  { label: "Thai", code: "th", zh: "泰语" },
  { label: "Indonesian", code: "id", zh: "印尼语" },
];

const dictionaries = {
  en: {
    otherLocale: "中文",
    appSubtitle: "Structure-preserving ebook translation workbench",
    statusBadge: "Self-hosted",
    guide: "Guide",
    settings: "Settings",
    inputHeading: "1. Input & Book",
    uploadTitle: "Upload Book",
    dropTitle: "Drop ebook here",
    dropHint: "or click to browse",
    dropActive: "Release to attach this ebook",
    fileLocal: "The file remains on this server.",
    noFile: "No file selected",
    targetLanguage: "Target language",
    metadataLanguage: "Output metadata language",
    metadataHelp: "Reader metadata, usually a BCP-47 code such as zh-CN.",
    outputTitle: "Output title",
    titleState: "Title mode",
    suffixTitle: "Original title + suffix",
    generatedTitle: "Generated by provider",
    outputFormat: "Output format",
    prepare: "Prepare Workspace",
    preparing: "Preparing...",
    preparingWorkspace: "Preparing workspace...",
    formatHelper: "EPUB is native. Other formats use Calibre when available.",
    glossaryHeading: "2. Glossary & Progress",
    glossaryTitle: "Glossary Review",
    glossaryHint: "Review locked names and terms before spending tokens.",
    searchTerms: "Search glossary terms...",
    typeFilter: "Type",
    statusFilter: "Status",
    all: "All",
    source: "Source term",
    translation: "Translation",
    type: "Type",
    aliases: "Aliases",
    frequency: "Frequency",
    evidence: "Evidence",
    state: "State",
    saveGlossary: "Save glossary table",
    addTerm: "Add term",
    approveAllTerms: "Approve all",
    noTerms: "Prepare a job to review glossary candidates.",
    reviewGlossary: "Review Glossary",
    aiFillTranslations: "AI Fill Translations",
    aiFillingTranslations: "AI filling...",
    aiFillingProgress: "Drafting glossary translations with the configured provider.",
    estimateTitle: "Rough time estimate",
    glossaryEstimate: "Glossary AI drafts",
    translationEstimate: "Translation remaining",
    usageTitle: "Provider usage",
    totalTokens: "Total tokens",
    promptTokens: "Prompt tokens",
    completionTokens: "Completion tokens",
    providerCalls: "Provider calls",
    tokenUsageUnavailable: "Token usage unavailable from provider.",
    estimateDone: "Done",
    estimateUnavailable: "Not enough data",
    minuteUnit: "min",
    glossarySummaryTitle: "Glossary readiness",
    glossarySummaryHint: "AI drafts fill blank pending translations first; approve the terms you want locked before translation.",
    approved: "Approved",
    pending: "Pending",
    emptyDrafts: "Empty drafts",
    ignored: "Ignored",
    showing: "Showing",
    of: "of",
    page: "Page",
    rowsPerPage: "Rows per page",
    previousPage: "Previous",
    nextPage: "Next",
    jobProgress: "Job Progress",
    terminalTitle: "Process terminal",
    terminalCollapsed: "Process terminal collapsed",
    expand: "Expand",
    collapse: "Collapse",
    terminalIdle: "waiting for a job...",
    currentBatch: "Current batch",
    activeBatches: "Active batches",
    failedBatches: "Failed batches",
    updated: "Updated",
    completed: "completed",
    batches: "Batches",
    blocks: "Blocks",
    noJob: "No job prepared.",
    outputHeading: "3. Output & Validation",
    downloads: "Downloads",
    downloadBook: "Download Book",
    downloadGlossary: "Download Glossary",
    downloadReport: "Download Report",
    downloadAudit: "Download Audit JSON",
    downloadAiReport: "Download AI QA JSON",
    unavailable: "Not ready yet",
    validation: "Validation",
    structuralValidation: "Structural validation",
    aiQuality: "AI quality repair",
    validationHint: "Structure checks protect EPUB links, anchors, XHTML shape, images, and package integrity.",
    validationReady: "Validation passed",
    validationPending: "Waiting for translated output",
    validationFailed: "Needs attention",
    fixedRows: "Fixed rows",
    remainingIssues: "Blocking issues",
    start: "Start Translation",
    resume: "Resume Translation",
    refreshJob: "Refresh Job",
    noticePrepared: "Workspace prepared. Review the glossary table before starting.",
    noticeGlossary: "Glossary table saved.",
    noticeAutofillNeedsProvider: "Workspace prepared. Configure a provider, then use AI Fill Translations to draft glossary names.",
    noticeAutofillFilling: "Drafting glossary translations...",
    noticeAutofillDone: "AI filled glossary draft translations.",
    noticeAutofillNone: "No empty pending glossary terms needed AI draft translations.",
    noticeStarted: "Translation started.",
    noticeResume: "Resume requested.",
    noticeSettings: "Settings saved.",
    startPendingTitle: "Start with pending glossary terms?",
    startPendingBody: "Some glossary terms are still pending or missing draft translations. You can continue, but terminology may be less consistent.",
    openProvider: "OpenAI Compatible",
    anthropic: "Anthropic Claude",
    fake: "Fake Dry Run",
    providerTitle: "API Provider",
    provider: "Provider",
    baseUrl: "Base URL",
    apiKey: "API key",
    savedApiKey: "Saved API key available. Leave blank to reuse it.",
    model: "Model",
    concurrency: "Concurrency",
    requestTimeout: "Request timeout",
    retries: "Retries",
    qualityAutomation: "Quality Automation",
    aiQaToggle: "AI QA repair loop",
    aiQaHelp: "Default on. Babel repairs untranslated locked terms, then shows a fix summary.",
    autoTitleToggle: "Auto-generate output title",
    autoTitleHelp: "Requires a configured provider. When off, Babel uses the original title with a suffix.",
    version: "Version",
    github: "GitHub",
    saveSettings: "Save Settings",
    close: "Close",
    guideTitle: "How to run a Babel job",
    guideIntro: "Follow this order to avoid wasted provider calls and unclear failed states.",
    startWithUpload: "Start with upload",
    viewCurrentJob: "View current job",
    guideSteps: [
      ["Upload", "Choose an ebook, target language, metadata language, and output format."],
      ["Prepare", "Generate a private workspace, batch manifest, and structured glossary, then draft missing term translations with AI when a provider is configured."],
      ["Review glossary", "Open the glossary modal, review AI drafts, then approve names, places, titles, nicknames, species, and recurring terms."],
      ["Configure settings", "Open Settings for provider, model, concurrency, AI QA, and title automation."],
      ["Start or resume", "Start translation, or resume a failed job from valid translated batches."],
      ["Monitor and download", "Watch progress, expand the terminal if needed, then download artifacts."],
    ],
  },
  zh: {
    otherLocale: "EN",
    appSubtitle: "保留结构的电子书翻译工作台",
    statusBadge: "本地自部署",
    guide: "引导",
    settings: "设置",
    inputHeading: "1. 输入与书籍设置",
    uploadTitle: "上传电子书",
    dropTitle: "将电子书拖到这里",
    dropHint: "或点击选择文件",
    dropActive: "松开后添加这本电子书",
    fileLocal: "文件只保存在当前服务器。",
    noFile: "尚未选择文件",
    targetLanguage: "目标语言",
    metadataLanguage: "输出元数据语言",
    metadataHelp: "写入电子书阅读器的语言信息，通常是 zh-CN 这类代码。",
    outputTitle: "输出标题",
    titleState: "标题模式",
    suffixTitle: "原标题 + 后缀",
    generatedTitle: "由 provider 生成",
    outputFormat: "输出格式",
    prepare: "准备工作区",
    preparing: "准备中...",
    preparingWorkspace: "正在准备工作区...",
    formatHelper: "EPUB 为原生输出。其他格式在可用时通过 Calibre 导出。",
    glossaryHeading: "2. 术语表与进度",
    glossaryTitle: "术语表审查",
    glossaryHint: "开始消耗 tokens 前，先确认锁定的人名、地名、称呼和高频术语。",
    searchTerms: "搜索术语...",
    typeFilter: "类型",
    statusFilter: "状态",
    all: "全部",
    source: "原文术语",
    translation: "译名",
    type: "类型",
    aliases: "别名",
    frequency: "频次",
    evidence: "出处",
    state: "状态",
    saveGlossary: "保存术语表",
    addTerm: "新增术语",
    approveAllTerms: "一键全部审查",
    noTerms: "准备任务后可审查术语候选项。",
    reviewGlossary: "审查术语表",
    aiFillTranslations: "AI 补全译名",
    aiFillingTranslations: "AI 补全中...",
    aiFillingProgress: "正在调用已配置的 provider 生成术语译名草稿。",
    estimateTitle: "粗略耗时预估",
    glossaryEstimate: "术语表 AI 草稿",
    translationEstimate: "翻译剩余",
    usageTitle: "Provider 用量",
    totalTokens: "总 Token",
    promptTokens: "输入 Token",
    completionTokens: "输出 Token",
    providerCalls: "Provider 调用",
    tokenUsageUnavailable: "当前 provider 未返回 token 用量。",
    estimateDone: "已完成",
    estimateUnavailable: "数据不足",
    minuteUnit: "分钟",
    glossarySummaryTitle: "术语表就绪状态",
    glossarySummaryHint: "AI 会先补齐 pending 空译名；真正需要全书一致的术语，请审查后设为 approved。",
    approved: "已确认",
    pending: "待审",
    emptyDrafts: "空草稿",
    ignored: "已忽略",
    showing: "显示",
    of: "共",
    page: "第",
    rowsPerPage: "每页行数",
    previousPage: "上一页",
    nextPage: "下一页",
    jobProgress: "任务进度",
    terminalTitle: "过程终端",
    terminalCollapsed: "过程终端已折叠",
    expand: "展开",
    collapse: "折叠",
    terminalIdle: "等待任务...",
    currentBatch: "当前批次",
    activeBatches: "活跃批次",
    failedBatches: "失败批次",
    updated: "更新于",
    completed: "已完成",
    batches: "批次",
    blocks: "文本块",
    noJob: "尚未准备任务。",
    outputHeading: "3. 输出与校验",
    downloads: "下载",
    downloadBook: "下载译本",
    downloadGlossary: "下载术语表",
    downloadReport: "下载报告",
    downloadAudit: "下载 Audit JSON",
    downloadAiReport: "下载 AI QA JSON",
    unavailable: "尚未就绪",
    validation: "校验",
    structuralValidation: "结构校验",
    aiQuality: "AI 质量修复",
    validationHint: "结构校验保护 EPUB 链接、锚点、XHTML 结构、图片和打包完整性。",
    validationReady: "校验通过",
    validationPending: "等待翻译输出",
    validationFailed: "需要处理",
    fixedRows: "已修复行数",
    remainingIssues: "阻塞问题",
    start: "开始翻译",
    resume: "继续翻译",
    refreshJob: "刷新任务",
    noticePrepared: "工作区已准备。开始前请先审查术语表。",
    noticeGlossary: "术语表已保存。",
    noticeAutofillNeedsProvider: "工作区已准备。请先配置 provider，然后用 AI 补全译名生成术语草稿。",
    noticeAutofillFilling: "正在生成术语译名草稿...",
    noticeAutofillDone: "AI 已补全术语译名草稿。",
    noticeAutofillNone: "没有需要 AI 补全的 pending 空译名。",
    noticeStarted: "翻译已开始。",
    noticeResume: "已请求继续翻译。",
    noticeSettings: "设置已保存。",
    startPendingTitle: "术语表未完全审完，仍然开始翻译？",
    startPendingBody: "还有 pending 或空译名术语。可以继续，但全书术语一致性风险会更高。",
    openProvider: "OpenAI Compatible",
    anthropic: "Anthropic Claude",
    fake: "Fake Dry Run",
    providerTitle: "API Provider",
    provider: "Provider",
    baseUrl: "Base URL",
    apiKey: "API Key",
    savedApiKey: "已保存 API Key，可留空复用。",
    model: "Model",
    concurrency: "并发数",
    requestTimeout: "请求超时",
    retries: "重试次数",
    qualityAutomation: "质量自动化",
    aiQaToggle: "AI QA 修复循环",
    aiQaHelp: "默认开启。Babel 会修复未翻译的锁定术语，并展示修复摘要。",
    autoTitleToggle: "自动生成输出标题",
    autoTitleHelp: "需要先配置 provider。关闭时使用原标题并添加后缀。",
    version: "版本",
    github: "GitHub",
    saveSettings: "保存设置",
    close: "关闭",
    guideTitle: "如何执行 Babel 任务",
    guideIntro: "按这个顺序操作，可以减少 token 浪费，也能更清楚地处理失败状态。",
    startWithUpload: "从上传开始",
    viewCurrentJob: "查看当前任务",
    guideSteps: [
      ["上传", "选择电子书、目标语言和输出格式。"],
      ["准备工作区", "生成私有工作区、批次清单和结构化术语表；provider 已配置时自动生成缺失译名草稿。"],
      ["审查术语表", "打开术语表弹窗，审查 AI 草稿，再锁定人物名、地名、称呼、昵称、物种和高频术语。"],
      ["配置设置", "在设置中填写 provider、model、并发、AI QA 和标题自动化。"],
      ["开始或继续", "开始翻译；失败后从有效批次继续。"],
      ["监控与下载", "查看进度，必要时展开终端，完成后下载产物。"],
    ],
  },
} as const;

function App() {
  const [locale, setLocale] = useState<Locale>(() => (localStorage.getItem("babel_locale") === "zh" ? "zh" : "en"));
  const [meta, setMeta] = useState<Meta>({ version: "0.7.2", github_url: "https://github.com/Yipxiyi/Babel", supported_input_formats: [], supported_output_formats: [] });
  const [job, setJob] = useState<BabelJob | null>(null);
  const [currentJobId, setCurrentJobId] = useState("");
  const [terms, setTerms] = useState<GlossaryTerm[]>([]);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [isDragging, setIsDragging] = useState(false);
  const [notice, setNotice] = useState<Notice>(null);
  const [guideOpen, setGuideOpen] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [glossaryOpen, setGlossaryOpen] = useState(false);
  const [terminalOpen, setTerminalOpen] = useState(false);
  const [search, setSearch] = useState("");
  const [typeFilter, setTypeFilter] = useState("all");
  const [statusFilter, setStatusFilter] = useState("all");
  const [isPreparing, setIsPreparing] = useState(false);
  const [isAutofillingGlossary, setIsAutofillingGlossary] = useState(false);
  const [isSavingGlossary, setIsSavingGlossary] = useState(false);
  const [isSavingSettings, setIsSavingSettings] = useState(false);
  const [isStarting, setIsStarting] = useState(false);
  const [hasSavedApiKey, setHasSavedApiKey] = useState(false);
  const [form, setForm] = useState<FormState>({
    target_language: "Simplified Chinese",
    title: "",
    language: "zh-CN",
    output_format: "epub",
  });
  const [provider, setProvider] = useState<ProviderSettings>({
    provider: "openai-compatible",
    base_url: "https://api.openai.com/v1",
    api_key: "",
    model: "gpt-4.1",
    max_concurrency: "3",
    request_timeout: "300",
    max_retries: "2",
    ai_qa_enabled: true,
    auto_title_enabled: false,
  });

  const fileInputRef = useRef<HTMLInputElement>(null);
  const terminalRef = useRef<HTMLDivElement>(null);
  const jobProgressRef = useRef<HTMLElement>(null);
  const guideReturnRef = useRef<HTMLElement | null>(null);
  const settingsReturnRef = useRef<HTMLElement | null>(null);
  const glossaryReturnRef = useRef<HTMLElement | null>(null);
  const t = dictionaries[locale];

  useEffect(() => {
    localStorage.setItem("babel_locale", locale);
    document.documentElement.lang = locale === "zh" ? "zh-CN" : "en";
  }, [locale]);

  useEffect(() => {
    void loadMeta();
    void loadProviderSettings();
    void loadLatestJob();
  }, []);

  useEffect(() => {
    if (!currentJobId || job?.status !== "running") {
      return;
    }
    const timer = window.setInterval(() => void loadJob(currentJobId, false), 1500);
    return () => window.clearInterval(timer);
  }, [currentJobId, job?.status]);

  useEffect(() => {
    if (terminalOpen && terminalRef.current) {
      terminalRef.current.scrollTop = terminalRef.current.scrollHeight;
    }
  }, [terminalOpen, job?.events?.length, job?.status]);

  async function loadMeta() {
    try {
      setMeta(await fetchJson<Meta>("/api/meta"));
    } catch {
      setMeta((previous) => previous);
    }
  }

  async function loadLatestJob() {
    try {
      const data = await fetchJson<{ jobs: BabelJob[] }>("/api/jobs");
      const latest = data.jobs?.[0];
      if (latest) {
        await loadJob(latest.job_id, false);
      }
    } catch (error) {
      setNotice({ kind: "error", text: normalizeError(error) });
    }
  }

  async function loadProviderSettings() {
    try {
      const data = await fetchJson<{ provider_settings: Record<string, unknown> }>("/api/provider-settings");
      const settings = data.provider_settings;
      setHasSavedApiKey(Boolean(settings.has_api_key));
      setProvider((previous) => ({
        ...previous,
        provider: String(settings.provider || previous.provider),
        base_url: String(settings.base_url || previous.base_url),
        model: String(settings.model || previous.model),
        api_key: "",
        max_concurrency: String(settings.max_concurrency ?? previous.max_concurrency),
        request_timeout: String(settings.request_timeout ?? previous.request_timeout),
        max_retries: String(settings.max_retries ?? previous.max_retries),
        ai_qa_enabled: settings.ai_qa_enabled !== false,
        auto_title_enabled: settings.auto_title_enabled === true,
      }));
    } catch {
      setHasSavedApiKey(false);
    }
  }

  async function loadJob(jobId: string, announce = true) {
    const data = await fetchJson<{ job: BabelJob; glossary?: string }>(`/api/jobs/${jobId}`);
    setCurrentJobId(data.job.job_id);
    setJob(data.job);
    setForm((previous) => ({
      ...previous,
      target_language: data.job.target_language || previous.target_language,
      title: data.job.title || previous.title,
      language: data.job.language || previous.language,
      output_format: (data.job.output_format || previous.output_format).replace(/^\./, ""),
    }));
    await loadGlossaryTerms(data.job.job_id);
    if (announce) {
      setNotice({ kind: "info", text: data.job.message || "Job loaded." });
    }
  }

  async function loadGlossaryTerms(jobId: string) {
    const data = await fetchJson<{ glossary_terms: GlossaryTerm[] }>(`/api/jobs/${jobId}/glossary-terms`);
    setTerms(data.glossary_terms || []);
  }

  function acceptFile(file: File | undefined | null) {
    if (!file) {
      return;
    }
    setSelectedFile(file);
    setNotice(null);
  }

  async function handlePrepare(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const file = selectedFile || fileInputRef.current?.files?.[0];
    if (!file) {
      setNotice({ kind: "error", text: t.noFile });
      fileInputRef.current?.focus();
      return;
    }
    setIsPreparing(true);
    setNotice({ kind: "info", text: t.preparingWorkspace });
    const body = new FormData();
    body.append("epub", file);
    body.append("target_language", form.target_language);
    body.append("title", form.title);
    body.append("language", form.language);
    body.append("output_format", form.output_format);
    try {
      const data = await fetchJson<{ job: BabelJob }>("/api/jobs", { method: "POST", body });
      setCurrentJobId(data.job.job_id);
      setJob(data.job);
      setForm((previous) => ({ ...previous, title: data.job.title || previous.title }));
      await loadGlossaryTerms(data.job.job_id);
      setNotice({ kind: "success", text: t.noticePrepared });
      void handleAutofillGlossary(data.job.job_id, true);
    } catch (error) {
      setNotice({ kind: "error", text: normalizeError(error) });
    } finally {
      setIsPreparing(false);
    }
  }

  async function handleSaveGlossary() {
    if (!currentJobId) {
      return;
    }
    setIsSavingGlossary(true);
    try {
      const data = await fetchJson<{ job: BabelJob; glossary_terms: GlossaryTerm[] }>(
        `/api/jobs/${currentJobId}/glossary-terms`,
        {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ glossary_terms: terms }),
        },
      );
      setJob(data.job);
      setTerms(data.glossary_terms || terms);
      setNotice({ kind: "success", text: t.noticeGlossary });
    } catch (error) {
      setNotice({ kind: "error", text: normalizeError(error) });
    } finally {
      setIsSavingGlossary(false);
    }
  }

  async function handleAutofillGlossary(jobId = currentJobId, automatic = false) {
    if (!jobId) {
      return;
    }
    if (!canUseProvider(provider, hasSavedApiKey)) {
      setNotice({ kind: "info", text: t.noticeAutofillNeedsProvider });
      return;
    }
    setIsAutofillingGlossary(true);
    if (!automatic) {
      setNotice({ kind: "info", text: t.noticeAutofillFilling });
    }
    try {
      const data = await fetchJson<{ job: BabelJob; glossary_terms: GlossaryTerm[]; filled: number }>(
        `/api/jobs/${jobId}/glossary-terms/autofill`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            ...settingsPayload(),
            target_language: form.target_language,
          }),
        },
      );
      setJob(data.job);
      setTerms(data.glossary_terms || []);
      setNotice({ kind: "success", text: data.filled > 0 ? t.noticeAutofillDone : t.noticeAutofillNone });
    } catch (error) {
      setNotice({ kind: "error", text: normalizeError(error) });
    } finally {
      setIsAutofillingGlossary(false);
    }
  }

  async function handleSaveSettings() {
    setIsSavingSettings(true);
    try {
      const payload = settingsPayload();
      const data = await fetchJson<{ provider_settings: Record<string, unknown> }>("/api/provider-settings", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      setHasSavedApiKey(Boolean(data.provider_settings.has_api_key));
      setProvider((previous) => ({
        ...previous,
        api_key: "",
        auto_title_enabled: data.provider_settings.auto_title_enabled === true,
      }));
      setNotice({ kind: "success", text: t.noticeSettings });
      closeSettingsDialog();
    } catch (error) {
      setNotice({ kind: "error", text: normalizeError(error) });
    } finally {
      setIsSavingSettings(false);
    }
  }

  async function handleStart(resume: boolean) {
    if (!currentJobId) {
      return;
    }
    if (!resume && hasGlossaryWarnings(terms)) {
      const stats = glossaryStats(terms);
      const confirmed = window.confirm(
        `${t.startPendingTitle}\n\n${t.startPendingBody}\n\n${t.pending}: ${stats.pending} · ${t.emptyDrafts}: ${stats.empty}`,
      );
      if (!confirmed) {
        return;
      }
    }
    setIsStarting(true);
    setNotice({ kind: "info", text: resume ? t.noticeResume : t.noticeStarted });
    try {
      const data = await fetchJson<{ job: BabelJob; provider_settings?: Record<string, unknown> }>(
        `/api/jobs/${currentJobId}/start`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            ...settingsPayload(),
            target_language: form.target_language,
            resume,
          }),
        },
      );
      setJob(data.job);
      setForm((previous) => ({ ...previous, title: data.job.title || previous.title }));
      if (data.provider_settings) {
        setHasSavedApiKey(Boolean(data.provider_settings.has_api_key));
        setProvider((previous) => ({ ...previous, api_key: "" }));
      }
      window.setTimeout(() => void loadJob(currentJobId, false), 700);
    } catch (error) {
      setNotice({ kind: "error", text: normalizeError(error) });
    } finally {
      setIsStarting(false);
    }
  }

  function settingsPayload() {
    return {
      ...provider,
      max_concurrency: integerOption(provider.max_concurrency, 3, 1),
      request_timeout: integerOption(provider.request_timeout, 300, 1),
      max_retries: integerOption(provider.max_retries, 2, 0),
      auto_title_enabled: canUseProvider(provider, hasSavedApiKey) && provider.auto_title_enabled,
    };
  }

  function updateForm<K extends keyof FormState>(key: K, value: FormState[K]) {
    if (key === "target_language") {
      const match = findLanguage(value);
      setForm((previous) => ({
        ...previous,
        target_language: match?.label || value,
        language: match?.code || previous.language,
      }));
      return;
    }
    setForm((previous) => ({ ...previous, [key]: value }));
  }

  function updateProvider<K extends keyof ProviderSettings>(key: K, value: ProviderSettings[K]) {
    setProvider((previous) => ({ ...previous, [key]: value }));
  }

  function updateTerm(index: number, patch: Partial<GlossaryTerm>) {
    setTerms((previous) => previous.map((term, current) => (current === index ? { ...term, ...patch } : term)));
  }

  function approveAllTerms() {
    setTerms((previous) =>
      previous.map((term) =>
        term.status === "ignored" ? term : { ...term, status: "approved", locked: true },
      ),
    );
  }

  function addTerm() {
    setTerms((previous) => [
      {
        source: "",
        translation: "",
        type: "special",
        aliases: [],
        frequency: 0,
        evidence: [],
        status: "pending",
        confidence: 0,
        locked: false,
      },
      ...previous,
    ]);
  }

  function openGuideDialog() {
    guideReturnRef.current = document.activeElement as HTMLElement | null;
    setGuideOpen(true);
  }

  function closeGuideDialog() {
    setGuideOpen(false);
    window.setTimeout(() => guideReturnRef.current?.focus(), 0);
  }

  function openSettingsDialog() {
    settingsReturnRef.current = document.activeElement as HTMLElement | null;
    setSettingsOpen(true);
  }

  function closeSettingsDialog() {
    setSettingsOpen(false);
    window.setTimeout(() => settingsReturnRef.current?.focus(), 0);
  }

  function openGlossaryDialog() {
    glossaryReturnRef.current = document.activeElement as HTMLElement | null;
    setGlossaryOpen(true);
  }

  function closeGlossaryDialog() {
    setGlossaryOpen(false);
    window.setTimeout(() => glossaryReturnRef.current?.focus(), 0);
  }

  const tone = statusTone(job?.status);
  const percent = progressPercent(job);
  const canStart = Boolean(currentJobId) && job?.status !== "running";
  const canResume = Boolean(currentJobId) && job?.status === "failed";
  const canDownloadOutput = job?.status === "completed";
  const canDownloadGlossary = Boolean(currentJobId);
  const canAutofillGlossary = Boolean(currentJobId) && canUseProvider(provider, hasSavedApiKey);
  const terminalEvents: JobEvent[] = job?.events?.length ? job.events : [{ type: "idle", message: t.terminalIdle }];
  const titleMode = provider.auto_title_enabled && canUseProvider(provider, hasSavedApiKey) ? t.generatedTitle : t.suffixTitle;

  return (
    <div className="min-h-[100dvh] overflow-x-hidden bg-paper text-ink">
      <div className="pointer-events-none fixed inset-0 -z-10 bg-atmosphere" />
      <AppHeader
        locale={locale}
        meta={meta}
        t={t}
        onToggleLocale={() => setLocale(locale === "en" ? "zh" : "en")}
        onOpenGuide={openGuideDialog}
        onOpenSettings={openSettingsDialog}
      />
      <main className="mx-auto grid w-full max-w-[1480px] grid-cols-1 gap-6 px-4 pb-10 pt-5 md:px-6 xl:grid-cols-[360px_minmax(520px,1fr)_340px]">
        <Panel title={t.inputHeading} className="xl:sticky xl:top-5 xl:self-start">
          <UploadPanel
            t={t}
            form={form}
            selectedFileName={selectedFile?.name || ""}
            titleMode={titleMode}
            isPreparing={isPreparing}
            isDragging={isDragging}
            fileInputRef={fileInputRef}
            onAcceptFile={acceptFile}
            onDragState={setIsDragging}
            onPrepare={handlePrepare}
            onUpdateForm={updateForm}
          />
        </Panel>

        <div className="space-y-6">
          <Panel title={t.glossaryHeading}>
            <GlossarySummary
              t={t}
              terms={terms}
              canReview={Boolean(currentJobId)}
              canAutofill={canAutofillGlossary}
              isAutofilling={isAutofillingGlossary}
              onReview={openGlossaryDialog}
              onAutofill={() => void handleAutofillGlossary()}
            />
          </Panel>
          <Panel title={t.jobProgress} ref={jobProgressRef}>
            <JobSummary t={t} job={job} tone={tone} percent={percent} notice={notice} />
            <TerminalLog
              t={t}
              events={terminalEvents}
              status={job?.status}
              terminalRef={terminalRef}
              open={terminalOpen}
              onToggle={() => setTerminalOpen((value) => !value)}
            />
            <div className="mt-4 flex flex-col gap-3 sm:flex-row">
              <Button type="button" variant="secondary" disabled={!canResume || isStarting} onClick={() => void handleStart(true)} id="resumeBtn">
                <ArrowClockwise size={18} weight="bold" />
                {t.resume}
              </Button>
              <Button type="button" variant="ghost" disabled={!currentJobId} onClick={() => void loadJob(currentJobId)}>
                <ClockCounterClockwise size={18} weight="bold" />
                {t.refreshJob}
              </Button>
              <Button type="button" disabled={!canStart || isStarting} onClick={() => void handleStart(false)}>
                <Play size={18} weight="bold" />
                {isStarting ? `${t.start}...` : t.start}
              </Button>
            </div>
          </Panel>
        </div>

        <Panel title={t.outputHeading} className="xl:sticky xl:top-5 xl:self-start">
          <DownloadsPanel t={t} jobId={currentJobId} canDownloadOutput={canDownloadOutput} canDownloadGlossary={canDownloadGlossary} />
          <ValidationPanel t={t} job={job} tone={tone} />
        </Panel>
      </main>
      <footer className="mx-auto flex w-full max-w-[1480px] flex-col gap-3 border-t border-ink/15 px-4 py-6 text-xs text-muted md:px-6 lg:flex-row lg:items-center lg:justify-between">
        <span>Babel is open source software licensed under the MIT License.</span>
        <span className="inline-flex items-center gap-2 font-mono uppercase tracking-[0.22em]">Built with Babel</span>
      </footer>
      {guideOpen ? (
        <GuideModal
          t={t}
          onClose={closeGuideDialog}
          onStartWithUpload={() => {
            closeGuideDialog();
            window.setTimeout(() => fileInputRef.current?.focus(), 80);
          }}
          onViewCurrentJob={() => {
            closeGuideDialog();
            window.setTimeout(() => jobProgressRef.current?.scrollIntoView({ behavior: "smooth", block: "start" }), 80);
          }}
        />
      ) : null}
      {settingsOpen ? (
        <SettingsModal
          t={t}
          provider={provider}
          meta={meta}
          hasSavedApiKey={hasSavedApiKey}
          canUseProvider={canUseProvider(provider, hasSavedApiKey)}
          isSaving={isSavingSettings}
          onClose={closeSettingsDialog}
          onUpdateProvider={updateProvider}
          onSave={() => void handleSaveSettings()}
        />
      ) : null}
      {glossaryOpen ? (
        <GlossaryModal
          t={t}
          terms={terms}
          search={search}
          typeFilter={typeFilter}
          statusFilter={statusFilter}
          canSave={Boolean(currentJobId)}
          isSaving={isSavingGlossary}
          onClose={closeGlossaryDialog}
          onSearch={setSearch}
          onTypeFilter={setTypeFilter}
          onStatusFilter={setStatusFilter}
          onUpdateTerm={updateTerm}
          onAddTerm={addTerm}
          onApproveAll={approveAllTerms}
          onSave={() => void handleSaveGlossary()}
        />
      ) : null}
    </div>
  );
}

function AppHeader({
  locale,
  meta,
  t,
  onToggleLocale,
  onOpenGuide,
  onOpenSettings,
}: {
  locale: Locale;
  meta: Meta;
  t: (typeof dictionaries)[Locale];
  onToggleLocale: () => void;
  onOpenGuide: () => void;
  onOpenSettings: () => void;
}) {
  return (
    <header className="mx-auto flex w-full max-w-[1480px] flex-col gap-5 border-b border-ink/20 px-4 py-5 md:px-6 lg:flex-row lg:items-center lg:justify-between">
      <div className="flex min-w-0 items-center gap-4">
        <img className="size-16 shrink-0 rounded-2xl border border-ink/15 object-cover shadow-brand" src={babelIconUrl} alt="Babel project icon" />
        <div className="min-w-0">
          <div className="flex flex-wrap items-end gap-3">
            <h1 className="text-5xl font-black leading-none tracking-[-0.035em] md:text-6xl">Babel</h1>
            <div className="hidden pb-2 font-mono text-[0.68rem] uppercase tracking-[0.22em] text-muted sm:block">{t.appSubtitle}</div>
          </div>
          <div className="mt-2 flex flex-wrap items-center gap-2 text-xs text-muted">
            <span className="rounded-full border border-clay/40 bg-clay/10 px-3 py-1 font-mono uppercase tracking-[0.16em] text-clay">{t.statusBadge}</span>
            <span>v{meta.version}</span>
          </div>
        </div>
      </div>
      <nav className="flex flex-wrap items-center gap-2">
        <HeaderAction onClick={onToggleLocale} ariaLabel={`Switch language from ${locale}`} icon={Globe} label={t.otherLocale} />
        <HeaderAction onClick={onOpenGuide} icon={Question} label={t.guide} />
        <HeaderAction onClick={onOpenSettings} icon={GearSix} label={t.settings} />
      </nav>
    </header>
  );
}

function HeaderAction({ onClick, icon: Icon, label, ariaLabel }: { onClick: () => void; icon: IconComponent; label: string; ariaLabel?: string }) {
  return (
    <button
      type="button"
      className="inline-flex min-h-11 min-w-28 items-center justify-center gap-2 rounded-xl border border-ink/15 bg-surface/80 px-4 py-2.5 text-sm font-bold text-ink transition duration-200 hover:-translate-y-0.5 hover:border-clay/45 hover:bg-surface active:translate-y-px focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-clay"
      onClick={onClick}
      aria-label={ariaLabel}
    >
      <Icon size={18} weight="bold" />
      {label}
    </button>
  );
}

type PanelProps = { title: string; className?: string; children: React.ReactNode } & React.HTMLAttributes<HTMLElement>;

const Panel = forwardRef<HTMLElement, PanelProps>(function PanelComponent({ title, className, children }, ref) {
  return (
    <section ref={ref} className={cn("rounded-2xl border border-ink/15 bg-surface/82 p-5 shadow-panel backdrop-blur", className)}>
      <h2 className="mb-4 font-mono text-sm font-bold uppercase tracking-[0.16em] text-ink">{title}</h2>
      {children}
    </section>
  );
});

function UploadPanel({
  t,
  form,
  selectedFileName,
  titleMode,
  isPreparing,
  isDragging,
  fileInputRef,
  onAcceptFile,
  onDragState,
  onPrepare,
  onUpdateForm,
}: {
  t: (typeof dictionaries)[Locale];
  form: FormState;
  selectedFileName: string;
  titleMode: string;
  isPreparing: boolean;
  isDragging: boolean;
  fileInputRef: React.RefObject<HTMLInputElement | null>;
  onAcceptFile: (file: File | undefined | null) => void;
  onDragState: (dragging: boolean) => void;
  onPrepare: (event: React.FormEvent<HTMLFormElement>) => void;
  onUpdateForm: <K extends keyof FormState>(key: K, value: FormState[K]) => void;
}) {
  return (
    <form className="space-y-4" onSubmit={onPrepare}>
      <div>
        <h3 className="mb-3 text-lg font-bold tracking-tight">{t.uploadTitle}</h3>
        <label
          className={cn(
            "group flex cursor-pointer flex-col items-center justify-center rounded-2xl border border-dashed px-5 py-8 text-center transition",
            isDragging ? "border-clay bg-clay/8" : "border-clay/55 bg-paper/70 hover:-translate-y-0.5 hover:bg-clay/8",
          )}
          onDragEnter={(event) => {
            event.preventDefault();
            onDragState(true);
          }}
          onDragOver={(event) => {
            event.preventDefault();
            onDragState(true);
          }}
          onDragLeave={(event) => {
            event.preventDefault();
            onDragState(false);
          }}
          onDrop={(event) => {
            event.preventDefault();
            onDragState(false);
            onAcceptFile(event.dataTransfer.files?.[0]);
          }}
        >
          <input
            ref={fileInputRef}
            className="sr-only"
            name="epub"
            type="file"
            accept={ACCEPT_EXTENSIONS}
            onChange={(event) => onAcceptFile(event.target.files?.[0])}
          />
          <FileArrowUp size={42} className="mb-4 text-clay transition group-hover:scale-105" weight="duotone" />
          <span className="text-base font-bold">{isDragging ? t.dropActive : t.dropTitle}</span>
          <span className="mt-1 text-sm text-muted">{t.dropHint}</span>
          <span className="mt-4 text-xs text-muted">{t.fileLocal}</span>
        </label>
        <div className="mt-3 flex items-center justify-between rounded-xl border border-ink/12 bg-surface px-4 py-3">
          <span className="min-w-0 truncate text-sm font-semibold">{selectedFileName || t.noFile}</span>
          <X size={17} className="text-muted" weight="bold" />
        </div>
      </div>
      <LanguageSelect label={t.targetLanguage} value={form.target_language} onChange={(value) => onUpdateForm("target_language", value)} />
      <Field label={t.outputTitle} helper={`${t.titleState}: ${titleMode}`}>
        <Input name="title" value={form.title} placeholder={titleMode} onChange={(event) => onUpdateForm("title", event.target.value)} />
      </Field>
      <Field label={t.outputFormat} helper={t.formatHelper}>
        <Select name="output_format" value={form.output_format} onChange={(event) => onUpdateForm("output_format", event.target.value)}>
          {outputFormats.map((format) => (
            <option key={format.value} value={format.value}>
              {format.label}
            </option>
          ))}
        </Select>
      </Field>
      <Button type="submit" disabled={isPreparing}>
        <FileArrowUp size={18} weight="bold" />
        {isPreparing ? t.preparing : t.prepare}
      </Button>
    </form>
  );
}

function LanguageSelect({ label, value, onChange }: { label: string; value: string; onChange: (value: string) => void }) {
  const hasKnownValue = Boolean(findLanguage(value));
  return (
    <Field label={label}>
      <Select name="target_language" value={value} onChange={(event) => onChange(event.target.value)}>
        {!hasKnownValue && value ? <option value={value}>{value}</option> : null}
        {languages.map((language) => (
          <option key={language.code} value={language.label}>
            {language.zh} / {language.label}
          </option>
        ))}
      </Select>
    </Field>
  );
}

function GlossarySummary({
  t,
  terms,
  canReview,
  canAutofill,
  isAutofilling,
  onReview,
  onAutofill,
}: {
  t: (typeof dictionaries)[Locale];
  terms: GlossaryTerm[];
  canReview: boolean;
  canAutofill: boolean;
  isAutofilling: boolean;
  onReview: () => void;
  onAutofill: () => void;
}) {
  const stats = glossaryStats(terms);
  const glossaryEstimate = stats.empty
    ? formatEstimateRange(Math.ceil(stats.empty / 40), 1, 45, 120, t)
    : t.estimateDone;
  return (
    <div>
      <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
        <div>
          <h3 className="flex items-center gap-2 text-lg font-bold tracking-tight">
            <Table size={20} weight="bold" />
            {t.glossarySummaryTitle}
          </h3>
          <p className="mt-1 max-w-[62ch] text-sm leading-relaxed text-muted">{t.glossarySummaryHint}</p>
        </div>
        <div className="flex w-full flex-col gap-2 sm:w-56">
          <Button className="w-full whitespace-nowrap" type="button" variant="ghost" disabled={!canReview} onClick={onReview}>
            <Table size={18} weight="bold" />
            {t.reviewGlossary}
          </Button>
          <Button className="w-full whitespace-nowrap" type="button" variant="secondary" disabled={!canAutofill || isAutofilling} onClick={onAutofill}>
            <ArrowClockwise className={cn(isAutofilling && "animate-spin")} size={18} weight="bold" />
            {isAutofilling ? t.aiFillingTranslations : t.aiFillTranslations}
          </Button>
        </div>
      </div>
      {isAutofilling ? (
        <div className="mt-4 rounded-2xl border border-clay/30 bg-clay/8 px-4 py-3" role="status" aria-live="polite">
          <div className="flex items-center justify-between gap-4 text-sm">
            <span className="font-bold text-ink">{t.aiFillingTranslations}</span>
            <span className="font-mono text-[0.68rem] uppercase tracking-[0.14em] text-clay">working</span>
          </div>
          <div className="autofill-progress mt-3 h-2 overflow-hidden rounded-full bg-paper" aria-label={t.aiFillingProgress}>
            <div className="autofill-progress-fill h-full rounded-full bg-clay" />
          </div>
          <p className="mt-2 text-xs leading-relaxed text-muted">{t.aiFillingProgress}</p>
        </div>
      ) : null}
      <EstimatePanel title={t.estimateTitle} label={t.glossaryEstimate} value={terms.length ? glossaryEstimate : t.estimateUnavailable} />
      <div className="mt-4 grid grid-cols-2 gap-3 md:grid-cols-5">
        <Metric label="Total" value={String(stats.total)} />
        <Metric label={t.approved} value={String(stats.approved)} />
        <Metric label={t.pending} value={String(stats.pending)} />
        <Metric label={t.emptyDrafts} value={String(stats.empty)} />
        <Metric label={t.ignored} value={String(stats.ignored)} />
      </div>
    </div>
  );
}

function GlossaryModal({
  t,
  terms,
  search,
  typeFilter,
  statusFilter,
  canSave,
  isSaving,
  onClose,
  onSearch,
  onTypeFilter,
  onStatusFilter,
  onUpdateTerm,
  onAddTerm,
  onApproveAll,
  onSave,
}: {
  t: (typeof dictionaries)[Locale];
  terms: GlossaryTerm[];
  search: string;
  typeFilter: string;
  statusFilter: string;
  canSave: boolean;
  isSaving: boolean;
  onClose: () => void;
  onSearch: (value: string) => void;
  onTypeFilter: (value: string) => void;
  onStatusFilter: (value: string) => void;
  onUpdateTerm: (index: number, patch: Partial<GlossaryTerm>) => void;
  onAddTerm: () => void;
  onApproveAll: () => void;
  onSave: () => void;
}) {
  const closeRef = useRef<HTMLButtonElement>(null);
  useModalBehavior(onClose, closeRef);
  return (
    <div className="fixed inset-0 z-40 flex items-center justify-center bg-ink/45 px-4 py-6 backdrop-blur-sm" onMouseDown={onClose}>
      <div role="dialog" aria-modal="true" aria-labelledby="glossary-title" className="max-h-[88dvh] w-full max-w-6xl overflow-y-auto rounded-2xl border border-ink/15 bg-paper p-5 shadow-modal" onMouseDown={(event) => event.stopPropagation()}>
        <GlossaryTable
          t={t}
          terms={terms}
          search={search}
          typeFilter={typeFilter}
          statusFilter={statusFilter}
          canSave={canSave}
          isSaving={isSaving}
          closeRef={closeRef}
          onClose={onClose}
          onSearch={onSearch}
          onTypeFilter={onTypeFilter}
          onStatusFilter={onStatusFilter}
          onUpdateTerm={onUpdateTerm}
          onAddTerm={onAddTerm}
          onApproveAll={onApproveAll}
          onSave={onSave}
        />
      </div>
    </div>
  );
}

function GlossaryTable({
  t,
  terms,
  search,
  typeFilter,
  statusFilter,
  canSave,
  isSaving,
  closeRef,
  onClose,
  onSearch,
  onTypeFilter,
  onStatusFilter,
  onUpdateTerm,
  onAddTerm,
  onApproveAll,
  onSave,
}: {
  t: (typeof dictionaries)[Locale];
  terms: GlossaryTerm[];
  search: string;
  typeFilter: string;
  statusFilter: string;
  canSave: boolean;
  isSaving: boolean;
  closeRef: React.RefObject<HTMLButtonElement | null>;
  onClose: () => void;
  onSearch: (value: string) => void;
  onTypeFilter: (value: string) => void;
  onStatusFilter: (value: string) => void;
  onUpdateTerm: (index: number, patch: Partial<GlossaryTerm>) => void;
  onAddTerm: () => void;
  onApproveAll: () => void;
  onSave: () => void;
}) {
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(25);
  const filtered = terms.map((term, index) => ({ term, index })).filter(({ term }) => {
    const text = `${term.source} ${term.translation} ${term.aliases.join(" ")} ${term.type} ${term.status}`.toLowerCase();
    return (
      (!search || text.includes(search.toLowerCase())) &&
      (typeFilter === "all" || term.type === typeFilter) &&
      (statusFilter === "all" || term.status === statusFilter)
    );
  });
  const types = Array.from(new Set(terms.map((term) => term.type).filter(Boolean))).sort();
  const statuses = Array.from(new Set(terms.map((term) => term.status).filter(Boolean))).sort();
  const totalPages = Math.max(1, Math.ceil(filtered.length / pageSize));
  const currentPage = Math.min(page, totalPages);
  const startIndex = (currentPage - 1) * pageSize;
  const pageRows = filtered.slice(startIndex, startIndex + pageSize);
  const endIndex = Math.min(startIndex + pageRows.length, filtered.length);

  useEffect(() => {
    setPage(1);
  }, [search, typeFilter, statusFilter, pageSize, terms.length]);

  useEffect(() => {
    setPage((value) => Math.min(value, totalPages));
  }, [totalPages]);

  return (
    <div>
      <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
        <div>
          <h2 id="glossary-title" className="flex items-center gap-2 text-lg font-bold tracking-tight">
            <Table size={20} weight="bold" />
            {t.glossaryTitle}
          </h2>
          <p className="mt-1 max-w-[62ch] text-sm leading-relaxed text-muted">{t.glossaryHint}</p>
        </div>
        <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
          <div className="relative min-w-0 sm:w-64">
            <Input className="pl-10" value={search} placeholder={t.searchTerms} onChange={(event) => onSearch(event.target.value)} />
            <MagnifyingGlass size={18} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted" weight="bold" />
          </div>
          <Select value={typeFilter} onChange={(event) => onTypeFilter(event.target.value)}>
            <option value="all">{t.typeFilter}: {t.all}</option>
            {types.map((type) => (
              <option key={type} value={type}>{type}</option>
            ))}
          </Select>
          <Select value={statusFilter} onChange={(event) => onStatusFilter(event.target.value)}>
            <option value="all">{t.statusFilter}: {t.all}</option>
            {statuses.map((status) => (
              <option key={status} value={status}>{status}</option>
            ))}
          </Select>
          <button ref={closeRef} type="button" className="grid size-10 shrink-0 place-items-center rounded-xl border border-ink/15 bg-surface text-ink transition hover:-translate-y-0.5 hover:border-clay/45 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-clay" onClick={onClose} aria-label={t.close}>
            <X size={18} weight="bold" />
          </button>
        </div>
      </div>
      <div className="mt-4 flex flex-col gap-3 rounded-2xl border border-ink/10 bg-surface/70 px-4 py-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="font-mono text-[0.72rem] uppercase tracking-[0.13em] text-muted">
          {filtered.length
            ? `${t.showing} ${startIndex + 1}-${endIndex} ${t.of} ${filtered.length} · ${t.page} ${currentPage}/${totalPages}`
            : `${t.showing} 0 ${t.of} 0`}
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <label className="flex items-center gap-2 text-xs font-bold text-muted">
            <span>{t.rowsPerPage}</span>
            <Select value={String(pageSize)} onChange={(event) => setPageSize(Number.parseInt(event.target.value, 10))}>
              {[10, 25, 50, 100].map((size) => (
                <option key={size} value={size}>{size}</option>
              ))}
            </Select>
          </label>
          <Button type="button" variant="ghost" disabled={currentPage <= 1} onClick={() => setPage((value) => Math.max(1, value - 1))}>
            {t.previousPage}
          </Button>
          <Button type="button" variant="ghost" disabled={currentPage >= totalPages || !filtered.length} onClick={() => setPage((value) => Math.min(totalPages, value + 1))}>
            {t.nextPage}
          </Button>
        </div>
      </div>
      <div className="mt-5 overflow-x-auto rounded-2xl border border-ink/12 bg-paper/70">
        {filtered.length ? (
          <table className="min-w-[980px] w-full border-collapse text-left text-sm">
            <thead className="border-b border-ink/12 bg-surface">
              <tr className="font-mono text-[0.68rem] uppercase tracking-[0.13em] text-muted">
                <th className="px-3 py-3">{t.source}</th>
                <th className="px-3 py-3">{t.translation}</th>
                <th className="px-3 py-3">{t.type}</th>
                <th className="px-3 py-3">{t.aliases}</th>
                <th className="px-3 py-3">{t.frequency}</th>
                <th className="px-3 py-3">{t.evidence}</th>
                <th className="px-3 py-3">{t.state}</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-ink/10">
              {pageRows.map(({ term, index: originalIndex }) => {
                return (
                  <tr key={`${term.source}-${originalIndex}`} className="align-top">
                    <td className="px-3 py-3"><TableInput value={term.source} onChange={(value) => onUpdateTerm(originalIndex, { source: value })} /></td>
                    <td className="px-3 py-3"><TableInput value={term.translation} onChange={(value) => onUpdateTerm(originalIndex, { translation: value })} /></td>
                    <td className="px-3 py-3"><TableInput value={term.type} onChange={(value) => onUpdateTerm(originalIndex, { type: value })} /></td>
                    <td className="px-3 py-3">
                      <TableInput value={term.aliases.join(", ")} onChange={(value) => onUpdateTerm(originalIndex, { aliases: value.split(",").map((item) => item.trim()).filter(Boolean) })} />
                    </td>
                    <td className="px-3 py-3 font-mono text-xs text-muted">{term.frequency}</td>
                    <td className="max-w-[280px] px-3 py-3 text-xs leading-relaxed text-muted">{term.evidence?.[0] || ""}</td>
                    <td className="px-3 py-3">
                      <Select
                        value={term.status}
                        onChange={(event) => onUpdateTerm(originalIndex, { status: event.target.value, locked: event.target.value === "approved" })}
                      >
                        <option value="approved">approved</option>
                        <option value="pending">pending</option>
                        <option value="ignored">ignored</option>
                      </Select>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        ) : (
          <div className="px-5 py-12 text-center text-sm text-muted">{t.noTerms}</div>
        )}
      </div>
      <div className="mt-4 flex flex-col gap-3 sm:flex-row sm:justify-end">
        <Button type="button" variant="ghost" disabled={!canSave || !terms.length} onClick={onApproveAll}>
          <CheckCircle size={18} weight="bold" />
          {t.approveAllTerms}
        </Button>
        <Button type="button" variant="ghost" disabled={!canSave} onClick={onAddTerm}>
          <Plus size={18} weight="bold" />
          {t.addTerm}
        </Button>
        <Button type="button" variant="secondary" disabled={!canSave || isSaving} onClick={onSave}>
          <FloppyDisk size={18} weight="bold" />
          {isSaving ? `${t.saveGlossary}...` : t.saveGlossary}
        </Button>
      </div>
    </div>
  );
}

function JobSummary({ t, job, tone, percent, notice }: { t: (typeof dictionaries)[Locale]; job: BabelJob | null; tone: Tone; percent: number; notice: Notice }) {
  const failedBatches = failedBatchesForJob(job);
  const activeCount = job?.active_batches?.length || (job?.current_batch ? 1 : 0);
  const remainingBatches = job ? Math.max(0, job.total_batches - job.completed_batches) : 0;
  const concurrency = typeof job?.max_concurrency === "number" ? job.max_concurrency : 3;
  const translationEstimate = job
    ? remainingBatches > 0
      ? formatEstimateRange(remainingBatches, concurrency, 90, 240, t)
      : t.estimateDone
    : t.estimateUnavailable;
  return (
    <div className="rounded-2xl border border-ink/12 bg-surface p-4">
      <div className="flex flex-col gap-5 lg:flex-row lg:items-start">
        <div className="relative flex h-20 shrink-0 items-center rounded-2xl border border-ink/10 bg-paper px-5 lg:h-32 lg:w-40 lg:justify-center">
          <div className="text-4xl font-black tracking-tight">{percent}%</div>
          <div className="ml-3 font-mono text-[0.62rem] uppercase tracking-[0.16em] text-muted lg:absolute lg:bottom-5 lg:ml-0">{t.completed}</div>
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <StatusPill status={job?.status || "idle"} tone={tone} />
          </div>
          <h3 className="mt-3 text-xl font-bold tracking-tight [text-wrap:balance]">{job?.filename || t.noJob}</h3>
          <p className="mt-1 min-h-5 text-sm leading-relaxed text-muted">{job?.message || "Prepare a workspace to begin."}</p>
          <div className={cn("progress-track mt-4 h-3 overflow-hidden rounded-full bg-line", tone === "running" && "is-running")}>
            <div className="progress-fill h-full rounded-full bg-clay transition-[width] duration-300" style={{ width: `${percent}%` }} />
          </div>
          <EstimatePanel title={t.estimateTitle} label={t.translationEstimate} value={translationEstimate} />
          {job?.status === "completed" ? <UsagePanel t={t} usage={job.usage_summary} /> : null}
          <div className="mt-4 grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-3">
            <Metric label={t.batches} value={job ? `${job.completed_batches}/${job.total_batches}` : "0/0"} />
            <Metric label={t.blocks} value={job?.block_count ? String(job.block_count) : "0"} />
            <Metric label={t.outputFormat} value={formatLabel(job?.output_format)} />
            <Metric label={t.activeBatches} value={`${activeCount}${typeof job?.max_concurrency === "number" ? `/${job.max_concurrency}` : ""}`} />
            <Metric label={t.failedBatches} value={failedBatches.length ? failedBatches.map((batch) => batchLabel(batch)).join(", ") : "0"} />
            <Metric label={t.currentBatch} value={batchLabel(job?.current_batch)} />
            <Metric label={t.updated} value={formatTimestamp(job?.last_active_at)} />
          </div>
          {notice ? <NoticeBar notice={notice} /> : null}
        </div>
      </div>
    </div>
  );
}

function TerminalLog({ t, events, status, terminalRef, open, onToggle }: { t: (typeof dictionaries)[Locale]; events: JobEvent[]; status?: JobStatus; terminalRef: React.RefObject<HTMLDivElement | null>; open: boolean; onToggle: () => void }) {
  return (
    <div className="mt-5 overflow-hidden rounded-2xl border border-terminal-line bg-terminal text-terminal-ink shadow-terminal">
      <button type="button" className="flex w-full items-center justify-between border-b border-terminal-line px-4 py-3 text-left" onClick={onToggle}>
        <span className="inline-flex items-center gap-2 font-mono text-xs font-bold uppercase tracking-[0.16em]">
          <TerminalWindow size={17} weight="bold" />
          {open ? t.terminalTitle : `${t.terminalCollapsed} · ${events.length} events`}
        </span>
        <span className="inline-flex items-center gap-3">
          <span className={cn("status-light", status === "running" && "is-running")} aria-label={status || "idle"} />
          <span className="font-mono text-xs text-terminal-muted">{open ? t.collapse : t.expand}</span>
          <CaretDown className={cn("text-terminal-muted transition", open && "rotate-180")} size={16} weight="bold" />
        </span>
      </button>
      {open ? (
        <div ref={terminalRef} id="terminalLog" data-api-loader="loadLatestJob" className="max-h-80 min-h-64 overflow-y-auto px-4 py-3 font-mono text-[0.8rem] leading-relaxed">
          {events.map((event, index) => (
            <div key={`${event.ts || "event"}-${index}`} className={cn("terminal-line", `event-${event.type}`)}>
              <span className="mr-3 text-terminal-muted">{eventTime(event.ts)}</span>
              <span className="mr-3 text-terminal-accent">{event.type}</span>
              {event.batch ? <span className="mr-3 text-terminal-info">batch={event.batch.batch}</span> : null}
              <span>{event.message}</span>
            </div>
          ))}
          {status === "running" ? (
            <div className="terminal-line"><span className="terminal-cursor" /></div>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}

function DownloadsPanel({ t, jobId, canDownloadOutput, canDownloadGlossary }: { t: (typeof dictionaries)[Locale]; jobId: string; canDownloadOutput: boolean; canDownloadGlossary: boolean }) {
  const downloads = [
    { label: t.downloadBook, path: "output", icon: DownloadSimple, enabled: canDownloadOutput },
    { label: t.downloadGlossary, path: "glossary", icon: FileText, enabled: canDownloadGlossary },
    { label: t.downloadReport, path: "report", icon: FileText, enabled: canDownloadOutput },
    { label: t.downloadAudit, path: "audit", icon: FileText, enabled: canDownloadOutput },
    { label: t.downloadAiReport, path: "ai-report", icon: FileText, enabled: canDownloadOutput },
  ];
  return (
    <div>
      <h3 className="mb-3 text-lg font-bold tracking-tight">{t.downloads}</h3>
      <div className="space-y-3">
        {downloads.map((download) => {
          const Icon = download.icon;
          return (
            <a
              key={download.path}
              className={cn("flex items-center gap-3 rounded-xl border border-ink/12 bg-surface px-4 py-4 text-ink transition", download.enabled ? "hover:-translate-y-0.5 hover:border-clay/45" : "pointer-events-none opacity-55")}
              href={download.enabled && jobId ? `/api/jobs/${jobId}/download/${download.path}` : undefined}
              aria-disabled={!download.enabled}
            >
              <Icon size={24} className="text-clay" weight="duotone" />
              <span className="min-w-0 flex-1">
                <span className="block truncate text-sm font-bold">{download.label}</span>
                <span className="text-xs text-muted">{download.enabled ? "Ready" : t.unavailable}</span>
              </span>
            </a>
          );
        })}
      </div>
    </div>
  );
}

function ValidationPanel({ t, job, tone }: { t: (typeof dictionaries)[Locale]; job: BabelJob | null; tone: Tone }) {
  const Icon = tone === "failed" ? WarningCircle : CheckCircle;
  const fixed = job?.ai_fix_summary?.fixed ?? 0;
  const blockingRemaining = job?.ai_qa_summary?.blocking_remaining ?? job?.ai_qa_summary?.remaining ?? 0;
  return (
    <div className="mt-6 border-t border-ink/12 pt-5">
      <h3 className="mb-3 text-lg font-bold tracking-tight">{t.validation}</h3>
      <div className="rounded-2xl border border-ink/12 bg-surface p-4">
        <div className="flex items-center gap-4">
          <div className={cn("grid size-14 place-items-center rounded-full", tone === "failed" ? "bg-danger/10 text-danger" : "bg-success/10 text-success")}>
            <Icon size={32} weight="bold" />
          </div>
          <div>
            <div className="font-bold">{tone === "completed" ? t.validationReady : tone === "failed" ? t.validationFailed : t.validationPending}</div>
            <p className="mt-1 text-sm leading-relaxed text-muted">{t.validationHint}</p>
          </div>
        </div>
        <div className="mt-4 divide-y divide-ink/10 rounded-xl border border-ink/10">
          <ValidationRow label={t.structuralValidation} value={tone === "completed" ? t.validationReady : tone === "failed" ? t.validationFailed : t.validationPending} tone={tone} />
          <ValidationRow label={t.aiQuality} value={job?.ai_qa_status || "pending"} tone={job?.ai_qa_status === "failed" ? "failed" : tone === "completed" ? "completed" : "idle"} />
          <ValidationRow label={t.fixedRows} value={String(fixed)} tone={fixed > 0 ? "completed" : "idle"} />
          <ValidationRow
            label={t.remainingIssues}
            value={String(blockingRemaining)}
            tone={blockingRemaining > 0 ? "failed" : "completed"}
          />
        </div>
      </div>
    </div>
  );
}

function SettingsModal({
  t,
  provider,
  meta,
  hasSavedApiKey,
  canUseProvider,
  isSaving,
  onClose,
  onUpdateProvider,
  onSave,
}: {
  t: (typeof dictionaries)[Locale];
  provider: ProviderSettings;
  meta: Meta;
  hasSavedApiKey: boolean;
  canUseProvider: boolean;
  isSaving: boolean;
  onClose: () => void;
  onUpdateProvider: <K extends keyof ProviderSettings>(key: K, value: ProviderSettings[K]) => void;
  onSave: () => void;
}) {
  const closeRef = useRef<HTMLButtonElement>(null);
  useModalBehavior(onClose, closeRef);
  return (
    <div className="fixed inset-0 z-40 flex items-center justify-center bg-ink/45 px-4 py-6 backdrop-blur-sm" onMouseDown={onClose}>
      <div role="dialog" aria-modal="true" aria-labelledby="settings-title" className="max-h-[88dvh] w-full max-w-3xl overflow-y-auto rounded-2xl border border-ink/15 bg-paper p-5 shadow-modal" onMouseDown={(event) => event.stopPropagation()}>
        <ModalHeader id="settings-title" title={t.settings} closeLabel={t.close} closeRef={closeRef} onClose={onClose} />
        <div className="mt-5 grid gap-5 lg:grid-cols-[minmax(0,1fr)_260px]">
          <div className="space-y-4">
            <h3 className="text-lg font-bold">{t.providerTitle}</h3>
            <Field label={t.provider}>
              <Select value={provider.provider} onChange={(event) => onUpdateProvider("provider", event.target.value)}>
                <option value="openai-compatible">{t.openProvider}</option>
                <option value="anthropic">{t.anthropic}</option>
                <option value="fake">{t.fake}</option>
              </Select>
            </Field>
            <Field label={t.baseUrl}><Input value={provider.base_url} onChange={(event) => onUpdateProvider("base_url", event.target.value)} /></Field>
            <Field label={t.apiKey} helper={hasSavedApiKey ? t.savedApiKey : undefined}>
              <div className="relative">
                <Input className="pr-10" type="password" autoComplete="off" value={provider.api_key} onChange={(event) => onUpdateProvider("api_key", event.target.value)} />
                <LockKey size={18} className="absolute right-3 top-1/2 -translate-y-1/2 text-muted" weight="bold" />
              </div>
            </Field>
            <Field label={t.model}><Input value={provider.model} onChange={(event) => onUpdateProvider("model", event.target.value)} /></Field>
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
              <Field label={t.concurrency}><Input type="number" min={1} step={1} value={provider.max_concurrency} onChange={(event) => onUpdateProvider("max_concurrency", event.target.value)} /></Field>
              <Field label={t.requestTimeout}><Input type="number" min={1} step={1} value={provider.request_timeout} onChange={(event) => onUpdateProvider("request_timeout", event.target.value)} /></Field>
              <Field label={t.retries}><Input type="number" min={0} step={1} value={provider.max_retries} onChange={(event) => onUpdateProvider("max_retries", event.target.value)} /></Field>
            </div>
          </div>
          <div className="space-y-4 rounded-2xl border border-ink/12 bg-surface p-4">
            <h3 className="text-lg font-bold">{t.qualityAutomation}</h3>
            <SwitchRow label={t.aiQaToggle} helper={t.aiQaHelp} checked={provider.ai_qa_enabled} onChange={(checked) => onUpdateProvider("ai_qa_enabled", checked)} />
            <SwitchRow label={t.autoTitleToggle} helper={t.autoTitleHelp} checked={provider.auto_title_enabled && canUseProvider} disabled={!canUseProvider} onChange={(checked) => onUpdateProvider("auto_title_enabled", checked)} />
            <div className="rounded-xl border border-ink/10 bg-paper/70 p-3 text-sm">
              <div className="font-mono text-xs uppercase tracking-[0.14em] text-muted">{t.version}</div>
              <div className="mt-1 font-bold">v{meta.version}</div>
            </div>
            <a className="inline-flex w-full items-center justify-center gap-2 rounded-xl border border-ink/15 bg-paper px-4 py-3 text-sm font-bold transition hover:border-clay/45" href={meta.github_url} target="_blank" rel="noreferrer">
              <GithubLogo size={18} weight="bold" />
              {t.github}
            </a>
          </div>
        </div>
        <div className="mt-6 flex flex-col gap-3 border-t border-ink/12 pt-5 sm:flex-row sm:justify-end">
          <Button type="button" variant="ghost" onClick={onClose}>{t.close}</Button>
          <Button type="button" onClick={onSave} disabled={isSaving}>
            <FloppyDisk size={18} weight="bold" />
            {isSaving ? `${t.saveSettings}...` : t.saveSettings}
          </Button>
        </div>
      </div>
    </div>
  );
}

function GuideModal({ t, onClose, onStartWithUpload, onViewCurrentJob }: { t: (typeof dictionaries)[Locale]; onClose: () => void; onStartWithUpload: () => void; onViewCurrentJob: () => void }) {
  const closeRef = useRef<HTMLButtonElement>(null);
  useModalBehavior(onClose, closeRef);
  return (
    <div className="fixed inset-0 z-40 flex items-center justify-center bg-ink/45 px-4 py-6 backdrop-blur-sm" onMouseDown={onClose}>
      <div role="dialog" aria-modal="true" aria-labelledby="guide-title" className="max-h-[88dvh] w-full max-w-2xl overflow-y-auto rounded-2xl border border-ink/15 bg-paper p-5 shadow-modal" onMouseDown={(event) => event.stopPropagation()}>
        <ModalHeader id="guide-title" title={t.guideTitle} subtitle={t.guideIntro} closeLabel={t.close} closeRef={closeRef} onClose={onClose} />
        <ol className="mt-6 grid gap-3">
          {t.guideSteps.map(([title, body], index) => (
            <li key={title} className="grid grid-cols-[42px_minmax(0,1fr)] gap-3 rounded-xl border border-ink/12 bg-surface/80 p-4">
              <div className="grid size-10 place-items-center rounded-full bg-ink font-mono text-sm font-bold text-paper">{index + 1}</div>
              <div>
                <div className="font-bold">{title}</div>
                <p className="mt-1 text-sm leading-relaxed text-muted">{body}</p>
              </div>
            </li>
          ))}
        </ol>
        <div className="mt-6 flex flex-col gap-3 border-t border-ink/12 pt-5 sm:flex-row sm:justify-end">
          <Button type="button" variant="secondary" onClick={onStartWithUpload}><FileArrowUp size={18} weight="bold" />{t.startWithUpload}</Button>
          <Button type="button" onClick={onViewCurrentJob}><TerminalWindow size={18} weight="bold" />{t.viewCurrentJob}</Button>
        </div>
      </div>
    </div>
  );
}

function ModalHeader({ id, title, subtitle, closeLabel, closeRef, onClose }: { id: string; title: string; subtitle?: string; closeLabel: string; closeRef: React.RefObject<HTMLButtonElement | null>; onClose: () => void }) {
  return (
    <div className="flex items-start justify-between gap-4">
      <div>
        <h2 id={id} className="text-2xl font-black tracking-tight">{title}</h2>
        {subtitle ? <p className="mt-2 max-w-[58ch] text-sm leading-relaxed text-muted">{subtitle}</p> : null}
      </div>
      <button ref={closeRef} type="button" className="grid size-10 shrink-0 place-items-center rounded-xl border border-ink/15 bg-surface text-ink transition hover:-translate-y-0.5 hover:border-clay/45 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-clay" onClick={onClose} aria-label={closeLabel}>
        <X size={18} weight="bold" />
      </button>
    </div>
  );
}

function useModalBehavior(onClose: () => void, focusRef: React.RefObject<HTMLElement | null>) {
  useEffect(() => {
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    window.setTimeout(() => focusRef.current?.focus(), 0);
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        onClose();
      }
    }
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.body.style.overflow = previousOverflow;
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [focusRef, onClose]);
}

function SwitchRow({ label, helper, checked, disabled, onChange }: { label: string; helper: string; checked: boolean; disabled?: boolean; onChange: (checked: boolean) => void }) {
  return (
    <label className={cn("block rounded-xl border border-ink/10 bg-paper/70 p-3", disabled && "opacity-55")}>
      <span className="flex items-center justify-between gap-3">
        <span className="font-bold">{label}</span>
        <input className="peer sr-only" type="checkbox" checked={checked} disabled={disabled} onChange={(event) => onChange(event.target.checked)} />
        <span className={cn("relative h-7 w-12 rounded-full border border-ink/15 transition", checked ? "bg-clay" : "bg-line")}>
          <span className={cn("absolute left-1 top-1 size-5 rounded-full bg-surface shadow transition", checked && "translate-x-5")} />
        </span>
      </span>
      <span className="mt-2 block text-xs leading-relaxed text-muted">{helper}</span>
    </label>
  );
}

function ValidationRow({ label, value, tone }: { label: string; value: string; tone: Tone }) {
  return (
    <div className="flex items-center justify-between gap-3 px-3 py-3 text-sm">
      <span>{label}</span>
      <span className={cn("font-mono text-xs", tone === "completed" ? "text-success" : tone === "failed" ? "text-danger" : "text-muted")}>{value}</span>
    </div>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="min-w-0 rounded-xl border border-ink/10 bg-paper/70 px-3 py-3">
      <div className="font-mono text-[0.66rem] uppercase tracking-[0.14em] text-muted">{label}</div>
      <div className="mt-1 break-words text-sm font-bold leading-snug text-ink">{value}</div>
    </div>
  );
}

function StatusPill({ status, tone }: { status: string; tone: Tone }) {
  return (
    <span className={cn("inline-flex items-center gap-2 rounded-full border px-3 py-1 font-mono text-xs font-bold uppercase tracking-[0.12em]", tone === "running" && "border-info/35 bg-info/10 text-info", tone === "failed" && "border-danger/35 bg-danger/10 text-danger", tone === "completed" && "border-success/35 bg-success/10 text-success", tone === "prepared" && "border-clay/35 bg-clay/10 text-clay", tone === "idle" && "border-ink/15 bg-surface text-muted")}>
      <span className={cn("size-2 rounded-full", tone === "running" ? "animate-pulse bg-info" : "bg-current")} />
      {status}
    </span>
  );
}

function NoticeBar({ notice }: { notice: NonNullable<Notice> }) {
  return (
    <div className={cn("mt-4 rounded-xl border px-3 py-2 text-sm", notice.kind === "error" && "border-danger/35 bg-danger/8 text-danger", notice.kind === "success" && "border-success/35 bg-success/8 text-success", notice.kind === "info" && "border-info/30 bg-info/8 text-info")}>
      {notice.text}
    </div>
  );
}

function EstimatePanel({ title, label, value }: { title: string; label: string; value: string }) {
  return (
    <div className="mt-4 flex flex-col gap-1 rounded-xl border border-ink/10 bg-paper/70 px-3 py-3 text-sm sm:flex-row sm:items-center sm:justify-between">
      <span className="font-mono text-[0.66rem] font-bold uppercase tracking-[0.14em] text-muted">{title}</span>
      <span className="font-semibold text-ink">
        {label}: {value}
      </span>
    </div>
  );
}

function UsagePanel({ t, usage }: { t: (typeof dictionaries)[Locale]; usage?: BabelJob["usage_summary"] }) {
  const totalTokens = usage?.total_tokens || 0;
  const promptTokens = usage?.prompt_tokens || 0;
  const completionTokens = usage?.completion_tokens || 0;
  const requests = usage?.requests || 0;
  return (
    <div className="mt-4 rounded-2xl border border-ink/10 bg-paper/70 p-3">
      <div className="font-mono text-[0.66rem] font-bold uppercase tracking-[0.14em] text-muted">{t.usageTitle}</div>
      {totalTokens ? (
        <div className="mt-3 grid grid-cols-2 gap-3 lg:grid-cols-4">
          <Metric label={t.totalTokens} value={formatNumber(totalTokens)} />
          <Metric label={t.promptTokens} value={formatNumber(promptTokens)} />
          <Metric label={t.completionTokens} value={formatNumber(completionTokens)} />
          <Metric label={t.providerCalls} value={formatNumber(requests)} />
        </div>
      ) : (
        <div className="mt-2 text-sm text-muted">
          {t.tokenUsageUnavailable}
          {requests ? ` ${t.providerCalls}: ${formatNumber(requests)}` : ""}
        </div>
      )}
    </div>
  );
}

function Field({ label, helper, children }: { label: string; helper?: string; children: React.ReactNode }) {
  return (
    <label className="block">
      <span className="mb-2 block font-mono text-[0.68rem] font-bold uppercase tracking-[0.13em] text-muted">{label}</span>
      {children}
      {helper ? <span className="mt-2 block text-xs leading-relaxed text-muted">{helper}</span> : null}
    </label>
  );
}

function Input({ className, ...props }: React.InputHTMLAttributes<HTMLInputElement>) {
  return <input className={cn("w-full rounded-xl border border-ink/14 bg-surface px-3 py-2.5 text-sm text-ink outline-none transition placeholder:text-muted focus:border-clay focus:ring-2 focus:ring-clay/20", className)} {...props} />;
}

function TableInput({ value, onChange }: { value: string; onChange: (value: string) => void }) {
  return <input className="w-full min-w-24 rounded-lg border border-transparent bg-transparent px-2 py-1.5 text-sm text-ink outline-none transition hover:border-ink/12 hover:bg-surface focus:border-clay focus:bg-surface focus:ring-2 focus:ring-clay/20" value={value} onChange={(event) => onChange(event.target.value)} />;
}

function Select({ className, children, ...props }: React.SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <div className="relative">
      <select className={cn("w-full appearance-none rounded-xl border border-ink/14 bg-surface px-3 py-2.5 pr-10 text-sm text-ink outline-none transition focus:border-clay focus:ring-2 focus:ring-clay/20", className)} {...props}>
        {children}
      </select>
      <CaretDown size={17} className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-muted" weight="bold" />
    </div>
  );
}

function Button({ variant = "primary", className, children, ...props }: React.ButtonHTMLAttributes<HTMLButtonElement> & { variant?: "primary" | "secondary" | "ghost" }) {
  return (
    <button className={cn("inline-flex min-h-11 items-center justify-center gap-2 rounded-xl px-4 py-2.5 text-sm font-bold transition duration-200 active:translate-y-px disabled:pointer-events-none disabled:opacity-50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-clay", variant === "primary" && "bg-ink text-paper shadow-action hover:-translate-y-0.5 hover:bg-ink-soft", variant === "secondary" && "border border-clay/45 bg-clay text-paper shadow-action hover:-translate-y-0.5 hover:bg-clay-dark", variant === "ghost" && "border border-ink/15 bg-surface/70 text-ink hover:-translate-y-0.5 hover:bg-surface", className)} {...props}>
      {children}
    </button>
  );
}

function glossaryStats(terms: GlossaryTerm[]) {
  return terms.reduce(
    (stats, term) => {
      const status = term.status || "pending";
      const translation = term.translation.trim();
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

function findLanguage(value: string) {
  return languages.find((language) => language.label === value || language.zh === value || language.code === value);
}

function formatEstimateRange(workUnits: number, parallelism: number, fastSeconds: number, slowSeconds: number, t: (typeof dictionaries)[Locale]): string {
  if (!Number.isFinite(workUnits) || workUnits <= 0) {
    return t.estimateDone;
  }
  const safeParallelism = Math.max(1, Math.floor(parallelism || 1));
  const minMinutes = Math.max(1, Math.ceil((workUnits * fastSeconds) / safeParallelism / 60));
  const maxMinutes = Math.max(minMinutes, Math.ceil((workUnits * slowSeconds) / safeParallelism / 60));
  const joiner = t.minuteUnit === "分钟" ? "" : " ";
  return minMinutes === maxMinutes
    ? `~${minMinutes}${joiner}${t.minuteUnit}`
    : `~${minMinutes}-${maxMinutes}${joiner}${t.minuteUnit}`;
}

function hasGlossaryWarnings(terms: GlossaryTerm[]): boolean {
  const stats = glossaryStats(terms);
  return stats.pending > 0 || stats.empty > 0;
}

function canUseProvider(provider: ProviderSettings, hasSavedApiKey: boolean): boolean {
  if (provider.provider === "fake") {
    return true;
  }
  return Boolean(provider.model.trim() && (provider.api_key.trim() || hasSavedApiKey));
}

function statusTone(status?: string): Tone {
  if (status === "running") return "running";
  if (status === "failed") return "failed";
  if (status === "completed") return "completed";
  if (status === "prepared") return "prepared";
  return "idle";
}

function progressPercent(job: BabelJob | null): number {
  if (!job || !job.total_batches) return 0;
  return Math.round((job.completed_batches / job.total_batches) * 100);
}

function failedBatchesForJob(job: BabelJob | null): BatchSummary[] {
  if (!job) return [];
  return job.failed_batches?.length ? job.failed_batches : job.failed_batch ? [job.failed_batch] : [];
}

function batchLabel(batch?: BatchSummary | null): string {
  if (!batch) return "none";
  const parts = [`#${batch.batch ?? "?"}`];
  if (batch.chapter_label) parts.push(batch.chapter_label);
  else if (batch.file) parts.push(batch.file);
  return parts.join(" · ");
}

function formatLabel(value?: string): string {
  if (!value) return "not selected";
  return value.replace(/^\./, "").toUpperCase();
}

function formatTimestamp(value?: string): string {
  if (!value) return "not recorded";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString([], { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

function formatNumber(value: number): string {
  return new Intl.NumberFormat().format(value);
}

function eventTime(value?: string): string {
  if (!value) return "00:00:00";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value.replace("T", " ").replace("Z", "");
  return date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

function integerOption(value: string, fallback: number, minimum: number): number {
  const parsed = Number.parseInt(value, 10);
  return Number.isFinite(parsed) && parsed >= minimum ? parsed : fallback;
}

async function fetchJson<T>(url: string, options?: RequestInit): Promise<T> {
  const response = await fetch(url, options);
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || response.statusText);
  }
  return (await response.json()) as T;
}

function normalizeError(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

function cn(...parts: Array<string | false | undefined | null>) {
  return parts.filter(Boolean).join(" ");
}

export default App;
