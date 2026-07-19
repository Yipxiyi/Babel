import * as React from "react";
import { forwardRef, useEffect, useRef, useState } from "react";
import {
  Alert,
  AlertDialog,
  Button as HeroButton,
  Card as HeroCard,
  Chip,
  CloseButton,
  Description,
  Disclosure,
  FieldError,
  Form,
  Input as HeroInput,
  Label,
  Link as HeroLink,
  ListBox,
  Modal,
  NumberField,
  Pagination,
  ProgressBar,
  SearchField,
  Select as HeroSelect,
  Switch as HeroSwitch,
  Table as HeroTable,
  TextField,
} from "@heroui/react";
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
  Table as TableIcon,
  TerminalWindow,
  WarningCircle,
  X,
} from "@phosphor-icons/react";
import babelIconUrl from "../../docs/assets/brand/babel-icon.png";
import {
  buildPrepareUploadUrl,
  canUseProvider as canUseProviderForSettings,
  glossaryStats as computeGlossaryStats,
  hasGlossaryWarnings as hasGlossaryReviewWarnings,
  settingsPayloadFromProvider,
  startPayloadFromProvider,
} from "./appLogic";

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
    untranslated_ratio?: number;
    long_untranslated_segments?: number;
    punctuation_quote_drift?: number;
    person_name_drift?: number;
  };
  ai_fix_summary?: { fixed?: number; rounds?: number };
  glossary_summary?: { total?: number; approved?: number; pending?: number; ignored?: number };
  usage_summary?: {
    requests?: number;
    prompt_tokens?: number;
    completion_tokens?: number;
    total_tokens?: number;
    estimated_requests?: number;
    estimated_total_tokens?: number;
    estimated_cost?: number;
    actual_cost?: number;
    budget_spent?: number;
    budget_limit?: number;
  };
  generated_title?: string;
  title_source?: string;
  adaptive_enabled?: boolean;
  adaptive_plan?: {
    preparation?: { batch_char_limit?: number; estimated_batches?: number; oversized_block_count?: number };
    execution?: { max_concurrency?: number; request_timeout?: number; max_retries?: number; reason?: string };
    reasons?: string[];
    warnings?: Array<{ code: string; message: string; guidance?: string[] }>;
  };
  diagnostics?: JobDiagnostic[];
};

type JobDiagnostic = {
  code: string;
  stage: string;
  owner: "source_file" | "environment" | "api" | "babel" | "unknown";
  title: string;
  message: string;
  guidance?: string[];
  technical_detail?: string;
};

type ProviderSettings = {
  provider: string;
  base_url: string;
  api_key: string;
  model: string;
  max_concurrency: string;
  request_timeout: string;
  max_retries: string;
  adaptive_enabled: boolean;
  batch_char_limit: string;
  structured_output_enabled: boolean;
  memory_enabled: boolean;
  memory_project_id: string;
  max_requests_per_minute: string;
  max_tokens_per_minute: string;
  budget_limit: string;
  input_cost_per_1m_tokens: string;
  output_cost_per_1m_tokens: string;
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
    unlockTitle: "Unlock Babel",
    unlockHelp: "Enter the access token configured by the server administrator.",
    accessToken: "Access token",
    unlock: "Unlock",
    invalidToken: "The access token is invalid.",
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
    batchChars: "Batch character limit",
    batchCharsHelp: "Used only in custom mode. Smaller batches are safer but make more API calls.",
    adaptiveTitle: "Adaptive processing",
    adaptiveToggle: "Automatically optimize this book",
    adaptiveHelp: "Recommended. Babel analyzes the original file and chooses safe batch size, concurrency, timeout, retries, and fallback splitting.",
    advancedProcessing: "Advanced processing",
    advancedProcessingHelp: "Turn off adaptive processing to edit these values manually.",
    issueSource: "Issue source",
    issueGuidance: "What to do next",
    technicalDetails: "Technical details",
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
    importGlossary: "Import",
    importingGlossary: "Importing...",
    exportGlossary: "Export",
    glossaryFormat: "Format",
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
    estimatedCost: "Estimated cost",
    actualCost: "Actual cost",
    budgetSpent: "Budget spent",
    budgetLimitMetric: "Budget limit",
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
    nonblockingIssues: "Non-blocking issues",
    untranslatedRatio: "Untranslated ratio",
    longUntranslated: "Long untranslated",
    punctuationDrift: "Punctuation drift",
    personNameDrift: "Person name drift",
    start: "Start Translation",
    resume: "Resume Translation",
    refreshJob: "Refresh Job",
    noticePrepared: "Workspace prepared. Review the glossary table before starting.",
    noticeGlossary: "Glossary table saved.",
    noticeGlossaryImport: "Glossary terms imported.",
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
    rpmLimit: "Requests / min",
    tpmLimit: "Tokens / min",
    budgetLimit: "Budget limit",
    inputTokenCost: "Input $ / 1M",
    outputTokenCost: "Output $ / 1M",
    qualityAutomation: "Quality Automation",
    structuredOutputToggle: "Structured JSON output",
    structuredOutputHelp: "OpenAI-compatible providers can request JSON Schema responses before falling back to Babel's parser.",
    memoryToggle: "Translation Memory",
    memoryHelp: "Reuse exact matching source snippets across books in the same project.",
    memoryProject: "Memory project",
    memoryProjectHelp: "Use the same project or series id for books that should share reusable translations.",
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
    unlockTitle: "解锁 Babel",
    unlockHelp: "请输入服务器管理员配置的访问 token。",
    accessToken: "访问 Token",
    unlock: "解锁",
    invalidToken: "访问 token 无效。",
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
    batchChars: "批次字符上限",
    batchCharsHelp: "仅在自定义模式下使用。批次越小越稳，但 API 调用次数会增加。",
    adaptiveTitle: "自适应处理",
    adaptiveToggle: "自动为这本书优化参数",
    adaptiveHelp: "推荐开启。Babel 会分析原始文件，自动选择批次大小、并发、超时、重试和失败拆分策略。",
    advancedProcessing: "进阶处理参数",
    advancedProcessingHelp: "关闭自适应后，可以手动调整这些参数。",
    issueSource: "问题来源",
    issueGuidance: "建议这样处理",
    technicalDetails: "技术详情",
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
    importGlossary: "导入",
    importingGlossary: "导入中...",
    exportGlossary: "导出",
    glossaryFormat: "格式",
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
    estimatedCost: "预估成本",
    actualCost: "实际成本",
    budgetSpent: "预算消耗",
    budgetLimitMetric: "预算上限",
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
    nonblockingIssues: "非阻塞问题",
    untranslatedRatio: "未翻译比例",
    longUntranslated: "长段未翻译",
    punctuationDrift: "标点漂移",
    personNameDrift: "人名漂移",
    start: "开始翻译",
    resume: "继续翻译",
    refreshJob: "刷新任务",
    noticePrepared: "工作区已准备。开始前请先审查术语表。",
    noticeGlossary: "术语表已保存。",
    noticeGlossaryImport: "术语表已导入。",
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
    rpmLimit: "每分钟请求",
    tpmLimit: "每分钟 token",
    budgetLimit: "预算上限",
    inputTokenCost: "输入 $ / 1M",
    outputTokenCost: "输出 $ / 1M",
    qualityAutomation: "质量自动化",
    structuredOutputToggle: "结构化 JSON 输出",
    structuredOutputHelp: "OpenAI-compatible provider 可请求 JSON Schema 响应；失败时仍由 Babel 解析器兜底。",
    memoryToggle: "翻译记忆库",
    memoryHelp: "在同一项目内复用完全匹配的源文片段译文。",
    memoryProject: "记忆库项目",
    memoryProjectHelp: "同一系列或项目使用相同 id，即可共享可复用译文。",
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
  const [meta, setMeta] = useState<Meta>({ version: "0.8.1", github_url: "https://github.com/Yipxiyi/Babel", supported_input_formats: [], supported_output_formats: [] });
  const [job, setJob] = useState<BabelJob | null>(null);
  const [currentJobId, setCurrentJobId] = useState("");
  const [terms, setTerms] = useState<GlossaryTerm[]>([]);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [isDragging, setIsDragging] = useState(false);
  const [notice, setNotice] = useState<Notice>(null);
  const [guideOpen, setGuideOpen] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [authOpen, setAuthOpen] = useState(false);
  const [glossaryOpen, setGlossaryOpen] = useState(false);
  const [startWarningOpen, setStartWarningOpen] = useState(false);
  const [terminalOpen, setTerminalOpen] = useState(false);
  const [search, setSearch] = useState("");
  const [typeFilter, setTypeFilter] = useState("all");
  const [statusFilter, setStatusFilter] = useState("all");
  const [isPreparing, setIsPreparing] = useState(false);
  const [isAutofillingGlossary, setIsAutofillingGlossary] = useState(false);
  const [isImportingGlossary, setIsImportingGlossary] = useState(false);
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
    adaptive_enabled: true,
    batch_char_limit: "6000",
    structured_output_enabled: false,
    memory_enabled: false,
    memory_project_id: "",
    max_requests_per_minute: "0",
    max_tokens_per_minute: "0",
    budget_limit: "0",
    input_cost_per_1m_tokens: "0",
    output_cost_per_1m_tokens: "0",
    ai_qa_enabled: true,
    auto_title_enabled: false,
  });

  const fileInputRef = useRef<HTMLInputElement>(null);
  const terminalRef = useRef<HTMLDivElement>(null);
  const jobProgressRef = useRef<HTMLElement>(null);
  const guideReturnRef = useRef<HTMLElement | null>(null);
  const settingsReturnRef = useRef<HTMLElement | null>(null);
  const glossaryReturnRef = useRef<HTMLElement | null>(null);
  const pendingPreparationRef = useRef("");
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
    const requireAuthentication = () => setAuthOpen(true);
    window.addEventListener(AUTH_REQUIRED_EVENT, requireAuthentication);
    return () => window.removeEventListener(AUTH_REQUIRED_EVENT, requireAuthentication);
  }, []);

  useEffect(() => {
    if (!currentJobId || !["preparing", "running"].includes(job?.status || "")) {
      return;
    }
    const timer = window.setInterval(() => void loadJob(currentJobId, false), 1500);
    return () => window.clearInterval(timer);
  }, [currentJobId, job?.status]);

  useEffect(() => {
    if (job?.status !== "prepared" || pendingPreparationRef.current !== job.job_id) return;
    pendingPreparationRef.current = "";
    void (async () => {
      await loadGlossaryTerms(job.job_id);
      setNotice({ kind: "success", text: t.noticePrepared });
      void handleAutofillGlossary(job.job_id, true);
    })();
  }, [job?.job_id, job?.status]);

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
        adaptive_enabled: settings.adaptive_enabled !== false,
        batch_char_limit: String(settings.batch_char_limit ?? previous.batch_char_limit),
        structured_output_enabled: settings.structured_output_enabled === true,
        memory_enabled: settings.memory_enabled === true,
        memory_project_id: String(settings.memory_project_id || ""),
        max_requests_per_minute: String(settings.max_requests_per_minute ?? previous.max_requests_per_minute),
        max_tokens_per_minute: String(settings.max_tokens_per_minute ?? previous.max_tokens_per_minute),
        budget_limit: String(settings.budget_limit ?? previous.budget_limit),
        input_cost_per_1m_tokens: String(settings.input_cost_per_1m_tokens ?? previous.input_cost_per_1m_tokens),
        output_cost_per_1m_tokens: String(settings.output_cost_per_1m_tokens ?? previous.output_cost_per_1m_tokens),
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
    if (data.job.status !== "preparing" && (data.job.block_count || 0) > 0) {
      await loadGlossaryTerms(data.job.job_id);
    }
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
    try {
      const uploadUrl = buildPrepareUploadUrl(form, provider, file.name);
      const data = await fetchJson<{ job: BabelJob }>(uploadUrl, {
        method: "POST",
        headers: { "Content-Type": "application/octet-stream" },
        body: file,
      });
      pendingPreparationRef.current = data.job.job_id;
      setCurrentJobId(data.job.job_id);
      setJob(data.job);
      setForm((previous) => ({ ...previous, title: data.job.title || previous.title }));
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

  async function handleImportGlossary(file: File, format: string) {
    if (!currentJobId) {
      return;
    }
    setIsImportingGlossary(true);
    try {
      const content = await file.text();
      const data = await fetchJson<{ job: BabelJob; glossary_terms: GlossaryTerm[] }>(
        `/api/jobs/${currentJobId}/glossary-terms/import`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ content, format, mode: "upsert", default_status: "pending" }),
        },
      );
      setJob(data.job);
      setTerms(data.glossary_terms || terms);
      setNotice({ kind: "success", text: t.noticeGlossaryImport });
    } catch (error) {
      setNotice({ kind: "error", text: normalizeError(error) });
    } finally {
      setIsImportingGlossary(false);
    }
  }

  function handleExportGlossary(format: string) {
    if (!currentJobId) {
      return;
    }
    void handleDownload(`/api/jobs/${currentJobId}/glossary-terms/export?format=${encodeURIComponent(format)}`);
  }

  async function handleDownload(url: string) {
    try {
      await downloadApiFile(url);
    } catch (error) {
      setNotice({ kind: "error", text: normalizeError(error) });
    }
  }

  async function handleUnlock(token: string): Promise<boolean> {
    sessionStorage.setItem(API_TOKEN_STORAGE_KEY, token.trim());
    try {
      setMeta(await fetchJson<Meta>("/api/meta"));
      setAuthOpen(false);
      await Promise.all([loadProviderSettings(), loadLatestJob()]);
      setNotice(null);
      return true;
    } catch {
      sessionStorage.removeItem(API_TOKEN_STORAGE_KEY);
      setAuthOpen(true);
      return false;
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
        adaptive_enabled: data.provider_settings.adaptive_enabled !== false,
        batch_char_limit: String(data.provider_settings.batch_char_limit ?? previous.batch_char_limit),
        structured_output_enabled: data.provider_settings.structured_output_enabled === true,
        memory_enabled: data.provider_settings.memory_enabled === true,
        memory_project_id: String(data.provider_settings.memory_project_id || previous.memory_project_id),
        max_requests_per_minute: String(data.provider_settings.max_requests_per_minute ?? previous.max_requests_per_minute),
        max_tokens_per_minute: String(data.provider_settings.max_tokens_per_minute ?? previous.max_tokens_per_minute),
        budget_limit: String(data.provider_settings.budget_limit ?? previous.budget_limit),
        input_cost_per_1m_tokens: String(data.provider_settings.input_cost_per_1m_tokens ?? previous.input_cost_per_1m_tokens),
        output_cost_per_1m_tokens: String(data.provider_settings.output_cost_per_1m_tokens ?? previous.output_cost_per_1m_tokens),
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

  async function handleStart(resume: boolean, skipGlossaryWarning = false) {
    if (!currentJobId) {
      return;
    }
    if (!resume && !skipGlossaryWarning && hasGlossaryWarnings(terms)) {
      setStartWarningOpen(true);
      return;
    }
    setIsStarting(true);
    setNotice({ kind: "info", text: resume ? t.noticeResume : t.noticeStarted });
    try {
      const data = await fetchJson<{ job: BabelJob; provider_settings?: Record<string, unknown> }>(
        `/api/jobs/${currentJobId}/start`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(startPayloadFromProvider(provider, hasSavedApiKey, form.target_language, resume)),
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
    return settingsPayloadFromProvider(provider, hasSavedApiKey);
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
  const hasPreparedBlocks = (job?.block_count || 0) > 0;
  const canStart = Boolean(currentJobId) && hasPreparedBlocks && ["prepared", "failed"].includes(job?.status || "");
  const canResume = Boolean(currentJobId) && hasPreparedBlocks && job?.status === "failed";
  const canDownloadOutput = job?.status === "completed";
  const canDownloadGlossary = Boolean(currentJobId) && hasPreparedBlocks && job?.status !== "preparing";
  const canAutofillGlossary = Boolean(currentJobId) && hasPreparedBlocks && job?.status !== "preparing" && canUseProvider(provider, hasSavedApiKey);
  const terminalEvents: JobEvent[] = job?.events?.length ? job.events : [{ type: "idle", message: t.terminalIdle }];
  const titleMode = provider.auto_title_enabled && canUseProvider(provider, hasSavedApiKey) ? t.generatedTitle : t.suffixTitle;

  return (
    <div className="min-h-[100dvh] overflow-x-hidden bg-background text-foreground">
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
              canReview={Boolean(currentJobId) && hasPreparedBlocks}
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
          <DownloadsPanel t={t} jobId={currentJobId} canDownloadOutput={canDownloadOutput} canDownloadGlossary={canDownloadGlossary} onDownload={(url) => void handleDownload(url)} />
          <ValidationPanel t={t} job={job} tone={tone} />
        </Panel>
      </main>
      <footer className="mx-auto flex w-full max-w-[1480px] flex-col gap-3 border-t border-border px-4 py-6 text-xs text-muted md:px-6 lg:flex-row lg:items-center lg:justify-between">
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
          isImporting={isImportingGlossary}
          onClose={closeGlossaryDialog}
          onSearch={setSearch}
          onTypeFilter={setTypeFilter}
          onStatusFilter={setStatusFilter}
          onUpdateTerm={updateTerm}
          onAddTerm={addTerm}
          onApproveAll={approveAllTerms}
          onImport={(file, format) => void handleImportGlossary(file, format)}
          onExport={handleExportGlossary}
          onSave={() => void handleSaveGlossary()}
        />
      ) : null}
      {authOpen ? <AuthModal t={t} onUnlock={handleUnlock} /> : null}
      {startWarningOpen ? (
        <StartWarningModal
          t={t}
          stats={glossaryStats(terms)}
          onClose={() => setStartWarningOpen(false)}
          onConfirm={() => {
            setStartWarningOpen(false);
            void handleStart(false, true);
          }}
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
    <header className="mx-auto flex w-full max-w-[1480px] flex-col gap-5 border-b border-border px-4 py-5 md:px-6 lg:flex-row lg:items-center lg:justify-between">
      <div className="flex min-w-0 items-center gap-4">
        <img className="size-16 shrink-0 rounded-3xl object-cover shadow-surface" src={babelIconUrl} alt="Babel project icon" />
        <div className="min-w-0">
          <div className="flex flex-wrap items-end gap-3">
            <h1 className="text-5xl font-black leading-none tracking-[-0.035em] md:text-6xl">Babel</h1>
            <div className="hidden pb-2 font-mono text-[0.68rem] uppercase tracking-[0.22em] text-muted sm:block">{t.appSubtitle}</div>
          </div>
          <div className="mt-2 flex flex-wrap items-center gap-2 text-xs text-muted">
            <Chip color="accent" size="sm" variant="soft">{t.statusBadge}</Chip>
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
    <Button
      type="button"
      className="min-w-28"
      onClick={onClick}
      aria-label={ariaLabel}
      variant="ghost"
    >
      <Icon size={18} weight="bold" />
      {label}
    </Button>
  );
}

type PanelProps = { title: string; className?: string; children: React.ReactNode } & React.HTMLAttributes<HTMLElement>;

const Panel = forwardRef<HTMLElement, PanelProps>(function PanelComponent({ title, className, children }, ref) {
  return (
    <HeroCard
      ref={ref as React.Ref<HTMLDivElement>}
      variant="default"
      className={className}
    >
      <HeroCard.Header>
        <HeroCard.Title>{title}</HeroCard.Title>
      </HeroCard.Header>
      <HeroCard.Content>{children}</HeroCard.Content>
    </HeroCard>
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
    <Form className="space-y-4" onSubmit={onPrepare}>
      <div>
        <h3 className="mb-3 text-lg font-bold tracking-tight">{t.uploadTitle}</h3>
        <label
          className={cn(
            "group flex cursor-pointer flex-col items-center justify-center rounded-3xl border border-dashed px-5 py-8 text-center transition",
            isDragging ? "border-accent bg-accent-soft" : "border-accent/55 bg-default/70 hover:bg-accent-soft",
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
          <FileArrowUp size={42} className="mb-4 text-accent transition group-hover:scale-105" weight="duotone" />
          <span className="text-base font-bold">{isDragging ? t.dropActive : t.dropTitle}</span>
          <span className="mt-1 text-sm text-muted">{t.dropHint}</span>
          <span className="mt-4 text-xs text-muted">{t.fileLocal}</span>
        </label>
        <div className="mt-3 rounded-2xl bg-default px-4 py-3">
          <span className="min-w-0 truncate text-sm font-semibold">{selectedFileName || t.noFile}</span>
        </div>
      </div>
      <LanguageSelect label={t.targetLanguage} value={form.target_language} onChange={(value) => onUpdateForm("target_language", value)} />
      <Field label={t.outputTitle} helper={`${t.titleState}: ${titleMode}`}>
        <Input name="title" value={form.title} placeholder={titleMode} onChange={(event) => onUpdateForm("title", event.target.value)} />
      </Field>
      <Select label={t.outputFormat} helper={t.formatHelper} name="output_format" value={form.output_format} onChange={(event) => onUpdateForm("output_format", event.target.value)}>
          {outputFormats.map((format) => (
            <option key={format.value} value={format.value}>
              {format.label}
            </option>
          ))}
      </Select>
      <Button type="submit" disabled={isPreparing}>
        <FileArrowUp size={18} weight="bold" />
        {isPreparing ? t.preparing : t.prepare}
      </Button>
    </Form>
  );
}

function LanguageSelect({ label, value, onChange }: { label: string; value: string; onChange: (value: string) => void }) {
  const hasKnownValue = Boolean(findLanguage(value));
  return (
    <Select label={label} name="target_language" value={value} onChange={(event) => onChange(event.target.value)}>
        {!hasKnownValue && value ? <option value={value}>{value}</option> : null}
        {languages.map((language) => (
          <option key={language.code} value={language.label}>
            {language.zh} / {language.label}
          </option>
        ))}
    </Select>
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
            <TableIcon size={20} weight="bold" />
            {t.glossarySummaryTitle}
          </h3>
          <p className="mt-1 max-w-[62ch] text-sm leading-relaxed text-muted">{t.glossarySummaryHint}</p>
        </div>
        <div className="flex w-full flex-col gap-2 sm:w-56">
          <Button className="w-full whitespace-nowrap" type="button" variant="ghost" disabled={!canReview} onClick={onReview}>
            <TableIcon size={18} weight="bold" />
            {t.reviewGlossary}
          </Button>
          <Button className="w-full whitespace-nowrap" type="button" variant="secondary" disabled={!canAutofill || isAutofilling} onClick={onAutofill}>
            <ArrowClockwise className={cn(isAutofilling && "animate-spin")} size={18} weight="bold" />
            {isAutofilling ? t.aiFillingTranslations : t.aiFillTranslations}
          </Button>
        </div>
      </div>
      {isAutofilling ? (
        <Alert status="accent" className="mt-4" role="status" aria-live="polite">
          <Alert.Indicator />
          <Alert.Content>
            <Alert.Title>{t.aiFillingTranslations}</Alert.Title>
            <ProgressBar isIndeterminate color="accent" size="sm" aria-label={t.aiFillingProgress} className="mt-3">
              <ProgressBar.Track><ProgressBar.Fill /></ProgressBar.Track>
            </ProgressBar>
            <Alert.Description className="mt-2">{t.aiFillingProgress}</Alert.Description>
          </Alert.Content>
        </Alert>
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
  isImporting,
  onClose,
  onSearch,
  onTypeFilter,
  onStatusFilter,
  onUpdateTerm,
  onAddTerm,
  onApproveAll,
  onImport,
  onExport,
  onSave,
}: {
  t: (typeof dictionaries)[Locale];
  terms: GlossaryTerm[];
  search: string;
  typeFilter: string;
  statusFilter: string;
  canSave: boolean;
  isSaving: boolean;
  isImporting: boolean;
  onClose: () => void;
  onSearch: (value: string) => void;
  onTypeFilter: (value: string) => void;
  onStatusFilter: (value: string) => void;
  onUpdateTerm: (index: number, patch: Partial<GlossaryTerm>) => void;
  onAddTerm: () => void;
  onApproveAll: () => void;
  onImport: (file: File, format: string) => void;
  onExport: (format: string) => void;
  onSave: () => void;
}) {
  const closeRef = useRef<HTMLButtonElement>(null);
  return (
    <>
      <Modal.Backdrop isOpen onOpenChange={(isOpen) => !isOpen && onClose()} variant="blur">
        <Modal.Container size="full" scroll="inside" className="p-4 md:p-6">
          <Modal.Dialog aria-labelledby="glossary-title" className="mx-auto max-h-[88dvh] w-full max-w-6xl overflow-y-auto">
            <Modal.Body className="p-0">
              <GlossaryTable
                t={t}
                terms={terms}
                search={search}
                typeFilter={typeFilter}
                statusFilter={statusFilter}
                canSave={canSave}
                isSaving={isSaving}
                isImporting={isImporting}
                closeRef={closeRef}
                onClose={onClose}
                onSearch={onSearch}
                onTypeFilter={onTypeFilter}
                onStatusFilter={onStatusFilter}
                onUpdateTerm={onUpdateTerm}
                onAddTerm={onAddTerm}
                onApproveAll={onApproveAll}
                onImport={onImport}
                onExport={onExport}
                onSave={onSave}
              />
            </Modal.Body>
          </Modal.Dialog>
        </Modal.Container>
      </Modal.Backdrop>
    </>
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
  isImporting,
  closeRef,
  onClose,
  onSearch,
  onTypeFilter,
  onStatusFilter,
  onUpdateTerm,
  onAddTerm,
  onApproveAll,
  onImport,
  onExport,
  onSave,
}: {
  t: (typeof dictionaries)[Locale];
  terms: GlossaryTerm[];
  search: string;
  typeFilter: string;
  statusFilter: string;
  canSave: boolean;
  isSaving: boolean;
  isImporting: boolean;
  closeRef: React.RefObject<HTMLButtonElement | null>;
  onClose: () => void;
  onSearch: (value: string) => void;
  onTypeFilter: (value: string) => void;
  onStatusFilter: (value: string) => void;
  onUpdateTerm: (index: number, patch: Partial<GlossaryTerm>) => void;
  onAddTerm: () => void;
  onApproveAll: () => void;
  onImport: (file: File, format: string) => void;
  onExport: (format: string) => void;
  onSave: () => void;
}) {
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(25);
  const [glossaryFormat, setGlossaryFormat] = useState("csv");
  const importInputRef = useRef<HTMLInputElement>(null);
  const filtered = terms.map((term, index) => ({ id: `${term.source}-${index}`, term, index })).filter(({ term }) => {
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

  function handleImportFile(event: React.ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (file) {
      onImport(file, glossaryFormat);
    }
  }

  return (
    <div>
      <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
        <div>
          <h2 id="glossary-title" className="flex items-center gap-2 text-lg font-bold tracking-tight">
            <TableIcon size={20} weight="bold" />
            {t.glossaryTitle}
          </h2>
          <p className="mt-1 max-w-[62ch] text-sm leading-relaxed text-muted">{t.glossaryHint}</p>
        </div>
        <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
          <SearchField className="min-w-0 sm:w-64" value={search} onChange={onSearch} aria-label={t.searchTerms}>
            <SearchField.Group>
              <SearchField.SearchIcon><MagnifyingGlass size={18} weight="bold" /></SearchField.SearchIcon>
              <SearchField.Input placeholder={t.searchTerms} />
              <SearchField.ClearButton aria-label={t.close} />
            </SearchField.Group>
          </SearchField>
          <Select aria-label={t.typeFilter} value={typeFilter} onChange={(event) => onTypeFilter(event.target.value)}>
            <option value="all">{t.typeFilter}: {t.all}</option>
            {types.map((type) => (
              <option key={type} value={type}>{type}</option>
            ))}
          </Select>
          <Select aria-label={t.statusFilter} value={statusFilter} onChange={(event) => onStatusFilter(event.target.value)}>
            <option value="all">{t.statusFilter}: {t.all}</option>
            {statuses.map((status) => (
              <option key={status} value={status}>{status}</option>
            ))}
          </Select>
          <CloseButton ref={closeRef} onPress={onClose} aria-label={t.close}>
            <X size={18} weight="bold" />
          </CloseButton>
        </div>
      </div>
      <Pagination className="mt-4 flex flex-col gap-3 rounded-3xl bg-surface-secondary px-4 py-3 sm:flex-row sm:items-center sm:justify-between" aria-label={t.page}>
        <Pagination.Summary className="font-mono text-[0.72rem] uppercase tracking-[0.13em] text-muted">
          {filtered.length
            ? `${t.showing} ${startIndex + 1}-${endIndex} ${t.of} ${filtered.length} · ${t.page} ${currentPage}/${totalPages}`
            : `${t.showing} 0 ${t.of} 0`}
        </Pagination.Summary>
        <Pagination.Content className="flex flex-wrap items-center gap-2">
          <div className="flex items-center gap-2 text-xs font-bold text-muted">
            <span>{t.rowsPerPage}</span>
            <Select aria-label={t.rowsPerPage} value={String(pageSize)} onChange={(event) => setPageSize(Number.parseInt(event.target.value, 10))}>
              {[10, 25, 50, 100].map((size) => (
                <option key={size} value={size}>{size}</option>
              ))}
            </Select>
          </div>
          <Pagination.Item>
            <Pagination.Previous isDisabled={currentPage <= 1} onPress={() => setPage((value) => Math.max(1, value - 1))}>{t.previousPage}</Pagination.Previous>
          </Pagination.Item>
          <Pagination.Item>
            <Pagination.Next isDisabled={currentPage >= totalPages || !filtered.length} onPress={() => setPage((value) => Math.min(totalPages, value + 1))}>{t.nextPage}</Pagination.Next>
          </Pagination.Item>
        </Pagination.Content>
      </Pagination>
      <HeroTable variant="primary" className="mt-5">
        {filtered.length ? (
          <HeroTable.ScrollContainer className="overflow-x-auto">
            <HeroTable.Content aria-label={t.glossaryTitle} className="min-w-[980px] w-full border-collapse text-left text-sm">
              <HeroTable.Header>
                <HeroTable.Column isRowHeader>{t.source}</HeroTable.Column>
                <HeroTable.Column>{t.translation}</HeroTable.Column>
                <HeroTable.Column>{t.type}</HeroTable.Column>
                <HeroTable.Column>{t.aliases}</HeroTable.Column>
                <HeroTable.Column>{t.frequency}</HeroTable.Column>
                <HeroTable.Column>{t.evidence}</HeroTable.Column>
                <HeroTable.Column>{t.state}</HeroTable.Column>
              </HeroTable.Header>
              <HeroTable.Body items={pageRows}>
              {({ id, term, index: originalIndex }) => (
                  <HeroTable.Row id={id} className="align-top">
                    <HeroTable.Cell><TableInput ariaLabel={`${t.source}: ${term.source}`} value={term.source} onChange={(value) => onUpdateTerm(originalIndex, { source: value })} /></HeroTable.Cell>
                    <HeroTable.Cell><TableInput ariaLabel={`${t.translation}: ${term.source}`} value={term.translation} onChange={(value) => onUpdateTerm(originalIndex, { translation: value })} /></HeroTable.Cell>
                    <HeroTable.Cell><TableInput ariaLabel={`${t.type}: ${term.source}`} value={term.type} onChange={(value) => onUpdateTerm(originalIndex, { type: value })} /></HeroTable.Cell>
                    <HeroTable.Cell>
                      <TableInput ariaLabel={`${t.aliases}: ${term.source}`} value={term.aliases.join(", ")} onChange={(value) => onUpdateTerm(originalIndex, { aliases: value.split(",").map((item) => item.trim()).filter(Boolean) })} />
                    </HeroTable.Cell>
                    <HeroTable.Cell className="font-mono text-xs text-muted">{term.frequency}</HeroTable.Cell>
                    <HeroTable.Cell className="max-w-[280px] text-xs leading-relaxed text-muted">{term.evidence?.[0] || ""}</HeroTable.Cell>
                    <HeroTable.Cell>
                      <Select
                        aria-label={`${t.state}: ${term.source}`}
                        value={term.status}
                        onChange={(event) => onUpdateTerm(originalIndex, { status: event.target.value, locked: event.target.value === "approved" })}
                      >
                        <option value="approved">approved</option>
                        <option value="pending">pending</option>
                        <option value="ignored">ignored</option>
                      </Select>
                    </HeroTable.Cell>
                  </HeroTable.Row>
              )}
              </HeroTable.Body>
            </HeroTable.Content>
          </HeroTable.ScrollContainer>
        ) : (
          <div className="px-5 py-12 text-center text-sm text-muted">{t.noTerms}</div>
        )}
      </HeroTable>
      <div className="mt-4 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex flex-wrap items-center gap-2">
          <div className="flex items-center gap-2 text-xs font-bold text-muted">
            <Select label={t.glossaryFormat} value={glossaryFormat} onChange={(event) => setGlossaryFormat(event.target.value)}>
              <option value="csv">CSV</option>
              <option value="tbx">TBX</option>
              <option value="md">Markdown</option>
              <option value="json">JSON</option>
            </Select>
          </div>
          <input ref={importInputRef} className="sr-only" type="file" accept=".csv,.tbx,.xml,.md,.markdown,.json,text/csv,text/markdown,application/json,application/xml" onChange={handleImportFile} />
          <Button type="button" variant="ghost" disabled={!canSave || isImporting} onClick={() => importInputRef.current?.click()}>
            <FileArrowUp size={18} weight="bold" />
            {isImporting ? t.importingGlossary : t.importGlossary}
          </Button>
          <Button type="button" variant="ghost" disabled={!canSave || !terms.length} onClick={() => onExport(glossaryFormat)}>
            <DownloadSimple size={18} weight="bold" />
            {t.exportGlossary}
          </Button>
        </div>
        <div className="flex flex-wrap items-center justify-end gap-2">
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
    <HeroCard variant="secondary">
      <div className="flex flex-col gap-5 lg:flex-row lg:items-start">
        <HeroCard variant="tertiary" className="relative flex h-20 shrink-0 items-center px-5 lg:h-32 lg:w-40 lg:justify-center">
          <div className="text-4xl font-black tracking-tight">{percent}%</div>
          <div className="ml-3 font-mono text-[0.62rem] uppercase tracking-[0.16em] text-muted lg:absolute lg:bottom-5 lg:ml-0">{t.completed}</div>
        </HeroCard>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <StatusPill status={job?.status || "idle"} tone={tone} />
            {job?.adaptive_enabled ? <Chip color="accent" size="sm" variant="soft">{t.adaptiveTitle}</Chip> : null}
          </div>
          <h3 className="mt-3 text-xl font-bold tracking-tight [text-wrap:balance]">{job?.filename || t.noJob}</h3>
          <p className="mt-1 min-h-5 text-sm leading-relaxed text-muted">{job?.message || "Prepare a workspace to begin."}</p>
          <ProgressBar isIndeterminate={job?.status === "preparing"} value={percent} minValue={0} maxValue={100} color="accent" size="lg" aria-label={t.jobProgress} className="mt-4">
            <ProgressBar.Track>
              <ProgressBar.Fill />
            </ProgressBar.Track>
          </ProgressBar>
          <EstimatePanel title={t.estimateTitle} label={t.translationEstimate} value={translationEstimate} />
          {job?.adaptive_plan?.warnings?.length ? <PreflightWarnings warnings={job.adaptive_plan.warnings} /> : null}
          {job?.diagnostics?.length ? <DiagnosticPanel t={t} diagnostic={job.diagnostics[job.diagnostics.length - 1]} /> : null}
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
    </HeroCard>
  );
}

function PreflightWarnings({ warnings }: { warnings: NonNullable<NonNullable<BabelJob["adaptive_plan"]>["warnings"]> }) {
  return (
    <Alert status="warning" className="mt-4">
      <Alert.Indicator />
      <Alert.Content>
        {warnings.map((warning) => (
          <div key={warning.code} className="mb-2 last:mb-0">
            <Alert.Description>{warning.message}</Alert.Description>
            {warning.guidance?.length ? <div className="mt-1 text-xs">{warning.guidance.join(" · ")}</div> : null}
          </div>
        ))}
      </Alert.Content>
    </Alert>
  );
}

function DiagnosticPanel({ t, diagnostic }: { t: (typeof dictionaries)[Locale]; diagnostic: JobDiagnostic }) {
  const ownerLabels: Record<JobDiagnostic["owner"], string> = {
    source_file: "Source file",
    environment: "Babel environment",
    api: "Translation API",
    babel: "Babel",
    unknown: "Needs inspection",
  };
  return (
    <Alert status="danger" className="mt-4">
      <Alert.Indicator />
      <Alert.Content>
        <Alert.Title>{diagnostic.title}</Alert.Title>
        <Alert.Description>{diagnostic.message}</Alert.Description>
        <div className="mt-3 text-sm"><strong>{t.issueSource}:</strong> {ownerLabels[diagnostic.owner]}</div>
        {diagnostic.guidance?.length ? (
          <div className="mt-3">
            <div className="text-sm font-bold">{t.issueGuidance}</div>
            <ul className="mt-1 list-disc space-y-1 pl-5 text-sm">
              {diagnostic.guidance.map((item) => <li key={item}>{item}</li>)}
            </ul>
          </div>
        ) : null}
        {diagnostic.technical_detail ? (
          <details className="mt-3 text-xs">
            <summary className="cursor-pointer font-bold">{t.technicalDetails}</summary>
            <pre className="mt-2 whitespace-pre-wrap break-words font-mono">{diagnostic.technical_detail}</pre>
          </details>
        ) : null}
      </Alert.Content>
    </Alert>
  );
}

function TerminalLog({ t, events, status, terminalRef, open, onToggle }: { t: (typeof dictionaries)[Locale]; events: JobEvent[]; status?: JobStatus; terminalRef: React.RefObject<HTMLDivElement | null>; open: boolean; onToggle: () => void }) {
  return (
    <Disclosure isExpanded={open} onExpandedChange={(isExpanded) => isExpanded !== open && onToggle()} className="mt-5 overflow-hidden rounded-3xl border text-[var(--babel-terminal-ink)] shadow-overlay [background:var(--babel-terminal)] [border-color:var(--babel-terminal-line)]">
      <Disclosure.Heading>
        <Disclosure.Trigger className="flex w-full items-center justify-between border-b px-4 py-3 text-left [border-color:var(--babel-terminal-line)] hover:bg-[color-mix(in_oklab,var(--babel-terminal-line)_40%,transparent)]">
          <span className="inline-flex items-center gap-2 font-mono text-xs font-bold uppercase tracking-[0.16em]">
            <TerminalWindow size={17} weight="bold" />
            {open ? t.terminalTitle : `${t.terminalCollapsed} · ${events.length} events`}
          </span>
          <span className="inline-flex items-center gap-3">
            <span className={cn("status-light", status === "running" && "is-running")} aria-label={status || "idle"} />
            <span className="font-mono text-xs text-[var(--babel-terminal-muted)]">{open ? t.collapse : t.expand}</span>
            <Disclosure.Indicator><CaretDown size={16} weight="bold" /></Disclosure.Indicator>
          </span>
        </Disclosure.Trigger>
      </Disclosure.Heading>
      <Disclosure.Content>
        <Disclosure.Body ref={terminalRef} id="terminalLog" data-api-loader="loadLatestJob" className="max-h-80 min-h-64 overflow-y-auto px-4 py-3 font-mono text-[0.8rem] leading-relaxed">
          {events.map((event, index) => (
            <div key={`${event.ts || "event"}-${index}`} className={cn("terminal-line", `event-${event.type}`)}>
              <span className="mr-3 text-[var(--babel-terminal-muted)]">{eventTime(event.ts)}</span>
              <span className="mr-3 text-[var(--babel-terminal-accent)]">{event.type}</span>
              {event.batch ? <span className="mr-3 text-[var(--babel-terminal-info)]">batch={event.batch.batch}</span> : null}
              <span>{event.message}</span>
            </div>
          ))}
          {status === "running" ? (
            <div className="terminal-line"><span className="terminal-cursor" /></div>
          ) : null}
        </Disclosure.Body>
      </Disclosure.Content>
    </Disclosure>
  );
}

function DownloadsPanel({ t, jobId, canDownloadOutput, canDownloadGlossary, onDownload }: { t: (typeof dictionaries)[Locale]; jobId: string; canDownloadOutput: boolean; canDownloadGlossary: boolean; onDownload: (url: string) => void }) {
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
            <HeroButton
              key={download.path}
              className="h-auto w-full justify-start px-4 py-4"
              variant="ghost"
              isDisabled={!download.enabled}
              onPress={() => {
                if (download.enabled && jobId) {
                  onDownload(`/api/jobs/${jobId}/download/${download.path}`);
                }
              }}
            >
              <Icon size={24} className="text-accent" weight="duotone" />
              <span className="min-w-0 flex-1">
                <span className="block truncate text-sm font-bold">{download.label}</span>
                <span className="text-xs text-muted">{download.enabled ? "Ready" : t.unavailable}</span>
              </span>
            </HeroButton>
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
  const nonblockingRemaining = job?.ai_qa_summary?.nonblocking_remaining ?? 0;
  const untranslatedRatio = job?.ai_qa_summary?.untranslated_ratio;
  const untranslatedRatioLabel = typeof untranslatedRatio === "number" ? `${(untranslatedRatio * 100).toFixed(1)}%` : "0.0%";
  return (
    <div className="mt-6 border-t border-border pt-5">
      <h3 className="mb-3 text-lg font-bold tracking-tight">{t.validation}</h3>
      <HeroCard variant="secondary">
        <div className="flex items-center gap-4">
          <div className={cn("grid size-14 place-items-center rounded-full", tone === "failed" ? "bg-danger-soft text-danger-soft-foreground" : "bg-success-soft text-success-soft-foreground")}>
            <Icon size={32} weight="bold" />
          </div>
          <div>
            <div className="font-bold">{tone === "completed" ? t.validationReady : tone === "failed" ? t.validationFailed : t.validationPending}</div>
            <p className="mt-1 text-sm leading-relaxed text-muted">{t.validationHint}</p>
          </div>
        </div>
        <div className="mt-4 divide-y divide-separator rounded-2xl bg-default">
          <ValidationRow label={t.structuralValidation} value={tone === "completed" ? t.validationReady : tone === "failed" ? t.validationFailed : t.validationPending} tone={tone} />
          <ValidationRow label={t.aiQuality} value={job?.ai_qa_status || "pending"} tone={job?.ai_qa_status === "failed" ? "failed" : tone === "completed" ? "completed" : "idle"} />
          <ValidationRow label={t.fixedRows} value={String(fixed)} tone={fixed > 0 ? "completed" : "idle"} />
          <ValidationRow
            label={t.remainingIssues}
            value={String(blockingRemaining)}
            tone={blockingRemaining > 0 ? "failed" : "completed"}
          />
          <ValidationRow label={t.nonblockingIssues} value={String(nonblockingRemaining)} tone={nonblockingRemaining > 0 ? "idle" : "completed"} />
          <ValidationRow label={t.untranslatedRatio} value={untranslatedRatioLabel} tone={(untranslatedRatio ?? 0) > 0.1 ? "failed" : "idle"} />
          <ValidationRow label={t.longUntranslated} value={String(job?.ai_qa_summary?.long_untranslated_segments ?? 0)} tone={(job?.ai_qa_summary?.long_untranslated_segments ?? 0) > 0 ? "failed" : "completed"} />
          <ValidationRow label={t.punctuationDrift} value={String(job?.ai_qa_summary?.punctuation_quote_drift ?? 0)} tone={(job?.ai_qa_summary?.punctuation_quote_drift ?? 0) > 0 ? "idle" : "completed"} />
          <ValidationRow label={t.personNameDrift} value={String(job?.ai_qa_summary?.person_name_drift ?? 0)} tone={(job?.ai_qa_summary?.person_name_drift ?? 0) > 0 ? "idle" : "completed"} />
        </div>
      </HeroCard>
    </div>
  );
}

function StartWarningModal({
  t,
  stats,
  onClose,
  onConfirm,
}: {
  t: (typeof dictionaries)[Locale];
  stats: ReturnType<typeof glossaryStats>;
  onClose: () => void;
  onConfirm: () => void;
}) {
  return (
    <>
      <AlertDialog.Backdrop isOpen onOpenChange={(isOpen) => !isOpen && onClose()} variant="blur">
        <AlertDialog.Container size="md" className="w-full max-w-xl">
          <AlertDialog.Dialog aria-labelledby="start-warning-title">
            <AlertDialog.Header>
              <AlertDialog.Icon status="warning"><WarningCircle size={22} weight="bold" /></AlertDialog.Icon>
              <AlertDialog.Heading id="start-warning-title">{t.startPendingTitle}</AlertDialog.Heading>
            </AlertDialog.Header>
            <AlertDialog.Body>
              <p className="mt-4 text-sm leading-relaxed text-muted">{t.startPendingBody}</p>
              <div className="mt-4 grid grid-cols-2 gap-3">
                <Metric label={t.pending} value={String(stats.pending)} />
                <Metric label={t.emptyDrafts} value={String(stats.empty)} />
              </div>
            </AlertDialog.Body>
            <AlertDialog.Footer className="mt-6 flex flex-col gap-3 border-t border-border pt-5 sm:flex-row sm:justify-end">
              <Button type="button" variant="ghost" onClick={onClose}>{t.close}</Button>
              <Button type="button" onClick={onConfirm}>
                <Play size={18} weight="bold" />
                {t.start}
              </Button>
            </AlertDialog.Footer>
          </AlertDialog.Dialog>
        </AlertDialog.Container>
      </AlertDialog.Backdrop>
    </>
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
  return (
    <>
      <Modal.Backdrop isOpen onOpenChange={(isOpen) => !isOpen && onClose()} variant="blur">
        <Modal.Container size="lg" scroll="inside" className="w-full max-w-3xl">
          <Modal.Dialog aria-labelledby="settings-title" className="max-h-[88dvh] overflow-y-auto">
            <ModalHeader id="settings-title" title={t.settings} closeLabel={t.close} closeRef={closeRef} onClose={onClose} />
            <Modal.Body className="mt-5 grid gap-5 p-0 lg:grid-cols-[minmax(0,1fr)_260px]">
              <div className="space-y-4">
                <HeroCard variant="secondary" className="space-y-3">
                  <h3 className="text-lg font-bold">{t.adaptiveTitle}</h3>
                  <SwitchRow
                    label={t.adaptiveToggle}
                    helper={t.adaptiveHelp}
                    checked={provider.adaptive_enabled}
                    onChange={(checked) => onUpdateProvider("adaptive_enabled", checked)}
                  />
                </HeroCard>
                <h3 className="text-lg font-bold">{t.providerTitle}</h3>
                <Select label={t.provider} value={provider.provider} onChange={(event) => onUpdateProvider("provider", event.target.value)}>
                    <option value="openai-compatible">{t.openProvider}</option>
                    <option value="openai-responses">OpenAI Responses</option>
                    <option value="anthropic">{t.anthropic}</option>
                    <option value="ollama">Ollama</option>
                    <option value="deepl">DeepL</option>
                    <option value="google-translate">Google Translate</option>
                    <option value="fake">{t.fake}</option>
                </Select>
                <Field label={t.baseUrl}><Input value={provider.base_url} onChange={(event) => onUpdateProvider("base_url", event.target.value)} /></Field>
                <Field label={t.apiKey} helper={hasSavedApiKey ? t.savedApiKey : undefined}>
                  <div className="relative">
                    <Input className="pr-10" type="password" autoComplete="off" value={provider.api_key} onChange={(event) => onUpdateProvider("api_key", event.target.value)} />
                    <LockKey size={18} className="absolute right-3 top-1/2 -translate-y-1/2 text-muted" weight="bold" />
                  </div>
                </Field>
                <Field label={t.model}><Input value={provider.model} onChange={(event) => onUpdateProvider("model", event.target.value)} /></Field>
                <div className="pt-2">
                  <h4 className="font-bold">{t.advancedProcessing}</h4>
                  <p className="mt-1 text-xs leading-relaxed text-muted">{t.advancedProcessingHelp}</p>
                </div>
                <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                  <NumberInputField disabled={provider.adaptive_enabled} label={t.batchChars} helper={t.batchCharsHelp} minValue={1000} step={500} value={provider.batch_char_limit} onChange={(value) => onUpdateProvider("batch_char_limit", value)} />
                  <NumberInputField disabled={provider.adaptive_enabled} label={t.concurrency} minValue={1} step={1} value={provider.max_concurrency} onChange={(value) => onUpdateProvider("max_concurrency", value)} />
                  <NumberInputField disabled={provider.adaptive_enabled} label={t.requestTimeout} minValue={1} step={1} value={provider.request_timeout} onChange={(value) => onUpdateProvider("request_timeout", value)} />
                  <NumberInputField disabled={provider.adaptive_enabled} label={t.retries} minValue={0} step={1} value={provider.max_retries} onChange={(value) => onUpdateProvider("max_retries", value)} />
                </div>
                <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
                  <NumberInputField label={t.rpmLimit} minValue={0} step={1} value={provider.max_requests_per_minute} onChange={(value) => onUpdateProvider("max_requests_per_minute", value)} />
                  <NumberInputField label={t.tpmLimit} minValue={0} step={1} value={provider.max_tokens_per_minute} onChange={(value) => onUpdateProvider("max_tokens_per_minute", value)} />
                  <NumberInputField label={t.budgetLimit} minValue={0} step={0.000001} value={provider.budget_limit} onChange={(value) => onUpdateProvider("budget_limit", value)} />
                </div>
                <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                  <NumberInputField label={t.inputTokenCost} minValue={0} step={0.000001} value={provider.input_cost_per_1m_tokens} onChange={(value) => onUpdateProvider("input_cost_per_1m_tokens", value)} />
                  <NumberInputField label={t.outputTokenCost} minValue={0} step={0.000001} value={provider.output_cost_per_1m_tokens} onChange={(value) => onUpdateProvider("output_cost_per_1m_tokens", value)} />
                </div>
              </div>
              <HeroCard variant="secondary" className="space-y-4">
                <h3 className="text-lg font-bold">{t.qualityAutomation}</h3>
                <SwitchRow label={t.structuredOutputToggle} helper={t.structuredOutputHelp} checked={provider.structured_output_enabled} onChange={(checked) => onUpdateProvider("structured_output_enabled", checked)} />
                <SwitchRow label={t.memoryToggle} helper={t.memoryHelp} checked={provider.memory_enabled} onChange={(checked) => onUpdateProvider("memory_enabled", checked)} />
                <Field label={t.memoryProject} helper={t.memoryProjectHelp}>
                  <Input value={provider.memory_project_id} onChange={(event) => onUpdateProvider("memory_project_id", event.target.value)} placeholder="default" />
                </Field>
                <SwitchRow label={t.aiQaToggle} helper={t.aiQaHelp} checked={provider.ai_qa_enabled} onChange={(checked) => onUpdateProvider("ai_qa_enabled", checked)} />
                <SwitchRow label={t.autoTitleToggle} helper={t.autoTitleHelp} checked={provider.auto_title_enabled && canUseProvider} disabled={!canUseProvider} onChange={(checked) => onUpdateProvider("auto_title_enabled", checked)} />
                <div className="rounded-2xl bg-default p-3 text-sm">
                  <div className="font-mono text-xs uppercase tracking-[0.14em] text-muted">{t.version}</div>
                  <div className="mt-1 font-bold">v{meta.version}</div>
                </div>
                <HeroLink className="w-full justify-center" href={meta.github_url} target="_blank" rel="noreferrer">
                  <GithubLogo size={18} weight="bold" />
                  {t.github}
                  <HeroLink.Icon />
                </HeroLink>
              </HeroCard>
            </Modal.Body>
            <Modal.Footer className="mt-6 flex flex-col gap-3 border-t border-border p-0 pt-5 sm:flex-row sm:justify-end">
              <Button type="button" variant="ghost" onClick={onClose}>{t.close}</Button>
              <Button type="button" onClick={onSave} disabled={isSaving}>
                <FloppyDisk size={18} weight="bold" />
                {isSaving ? `${t.saveSettings}...` : t.saveSettings}
              </Button>
            </Modal.Footer>
          </Modal.Dialog>
        </Modal.Container>
      </Modal.Backdrop>
    </>
  );
}

function GuideModal({ t, onClose, onStartWithUpload, onViewCurrentJob }: { t: (typeof dictionaries)[Locale]; onClose: () => void; onStartWithUpload: () => void; onViewCurrentJob: () => void }) {
  const closeRef = useRef<HTMLButtonElement>(null);
  return (
    <>
      <Modal.Backdrop isOpen onOpenChange={(isOpen) => !isOpen && onClose()} variant="blur">
        <Modal.Container size="lg" scroll="inside" className="w-full max-w-2xl">
          <Modal.Dialog aria-labelledby="guide-title" className="max-h-[88dvh] overflow-y-auto">
            <ModalHeader id="guide-title" title={t.guideTitle} subtitle={t.guideIntro} closeLabel={t.close} closeRef={closeRef} onClose={onClose} />
            <Modal.Body className="p-0">
              <ol className="mt-6 grid gap-3">
                {t.guideSteps.map(([title, body], index) => (
                  <li key={title} className="grid grid-cols-[42px_minmax(0,1fr)] gap-3 rounded-3xl bg-surface-secondary p-4">
                    <div className="grid size-10 place-items-center rounded-full bg-accent font-mono text-sm font-bold text-accent-foreground">{index + 1}</div>
                    <div>
                      <div className="font-bold">{title}</div>
                      <p className="mt-1 text-sm leading-relaxed text-muted">{body}</p>
                    </div>
                  </li>
                ))}
              </ol>
            </Modal.Body>
            <Modal.Footer className="mt-6 flex flex-col gap-3 border-t border-border p-0 pt-5 sm:flex-row sm:justify-end">
              <Button type="button" variant="secondary" onClick={onStartWithUpload}><FileArrowUp size={18} weight="bold" />{t.startWithUpload}</Button>
              <Button type="button" onClick={onViewCurrentJob}><TerminalWindow size={18} weight="bold" />{t.viewCurrentJob}</Button>
            </Modal.Footer>
          </Modal.Dialog>
        </Modal.Container>
      </Modal.Backdrop>
    </>
  );
}

function AuthModal({ t, onUnlock }: { t: (typeof dictionaries)[Locale]; onUnlock: (token: string) => Promise<boolean> }) {
  const [token, setToken] = useState("");
  const [invalid, setInvalid] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!token.trim()) return;
    setSubmitting(true);
    setInvalid(!(await onUnlock(token)));
    setSubmitting(false);
  }

  return (
    <>
      <Modal.Backdrop isOpen isDismissable={false} variant="blur">
        <Modal.Container size="sm">
          <Modal.Dialog aria-labelledby="auth-title">
            <Form onSubmit={submit}>
              <Modal.Header className="flex items-start gap-3 p-0">
                <div className="grid size-11 shrink-0 place-items-center rounded-2xl bg-accent text-accent-foreground"><LockKey size={22} weight="bold" /></div>
                <div>
                  <Modal.Heading id="auth-title" className="text-2xl font-black tracking-tight">{t.unlockTitle}</Modal.Heading>
                  <p className="mt-1 text-sm leading-relaxed text-muted">{t.unlockHelp}</p>
                </div>
              </Modal.Header>
              <Modal.Body className="p-0 pt-5">
                <TextField fullWidth isInvalid={invalid}>
                  <Label className="mb-2 block font-mono text-[0.68rem] font-bold uppercase tracking-[0.13em] text-muted">{t.accessToken}</Label>
                  <HeroInput autoFocus fullWidth variant="primary" type="password" autoComplete="current-password" value={token} onChange={(event) => { setToken(event.target.value); setInvalid(false); }} />
                  {invalid ? <FieldError>{t.invalidToken}</FieldError> : null}
                </TextField>
              </Modal.Body>
              <Modal.Footer className="p-0 pt-5">
                <Button className="w-full" type="submit" disabled={!token.trim() || submitting}>
                  <LockKey size={18} weight="bold" />
                  {submitting ? `${t.unlock}...` : t.unlock}
                </Button>
              </Modal.Footer>
            </Form>
          </Modal.Dialog>
        </Modal.Container>
      </Modal.Backdrop>
    </>
  );
}

function ModalHeader({ id, title, subtitle, closeLabel, closeRef, onClose }: { id: string; title: string; subtitle?: string; closeLabel: string; closeRef: React.RefObject<HTMLButtonElement | null>; onClose: () => void }) {
  return (
    <Modal.Header className="flex items-start justify-between gap-4 p-0">
      <div>
        <Modal.Heading id={id} className="text-2xl font-black tracking-tight">{title}</Modal.Heading>
        {subtitle ? <p className="mt-2 max-w-[58ch] text-sm leading-relaxed text-muted">{subtitle}</p> : null}
      </div>
      <Modal.CloseTrigger ref={closeRef} onPress={onClose} aria-label={closeLabel}>
        <X size={18} weight="bold" />
      </Modal.CloseTrigger>
    </Modal.Header>
  );
}

function SwitchRow({ label, helper, checked, disabled, onChange }: { label: string; helper: string; checked: boolean; disabled?: boolean; onChange: (checked: boolean) => void }) {
  return (
    <HeroSwitch
      className={cn("block rounded-3xl bg-default p-3", disabled && "opacity-55")}
      isDisabled={disabled}
      isSelected={checked}
      onChange={onChange}
    >
      <span className="flex items-center justify-between gap-3">
        <HeroSwitch.Content className="font-bold">{label}</HeroSwitch.Content>
        <HeroSwitch.Control />
      </span>
      <span className="mt-2 block text-xs leading-relaxed text-muted">{helper}</span>
    </HeroSwitch>
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
    <HeroCard variant="secondary" className="min-w-0">
      <HeroCard.Content>
        <div className="font-mono text-[0.66rem] uppercase tracking-[0.14em] text-muted">{label}</div>
        <div className="mt-1 break-words text-sm font-bold leading-snug text-foreground">{value}</div>
      </HeroCard.Content>
    </HeroCard>
  );
}

function StatusPill({ status, tone }: { status: string; tone: Tone }) {
  const color = tone === "completed" ? "success" : tone === "failed" ? "danger" : tone === "idle" ? "default" : "accent";
  return (
    <Chip color={color} size="sm" variant="soft" className="font-mono uppercase tracking-[0.12em]">
      <span className={cn("size-2 rounded-full bg-current", tone === "running" && "animate-pulse")} />
      {status}
    </Chip>
  );
}

function NoticeBar({ notice }: { notice: NonNullable<Notice> }) {
  const status = notice.kind === "error" ? "danger" : notice.kind === "success" ? "success" : "accent";
  return (
    <Alert status={status} className="mt-4">
      <Alert.Indicator />
      <Alert.Content>
        <Alert.Description>{notice.text}</Alert.Description>
      </Alert.Content>
    </Alert>
  );
}

function EstimatePanel({ title, label, value }: { title: string; label: string; value: string }) {
  return (
    <div className="mt-4 flex flex-col gap-1 rounded-2xl bg-default px-3 py-3 text-sm sm:flex-row sm:items-center sm:justify-between">
      <span className="font-mono text-[0.66rem] font-bold uppercase tracking-[0.14em] text-muted">{title}</span>
      <span className="font-semibold text-foreground">
        {label}: {value}
      </span>
    </div>
  );
}

function UsagePanel({ t, usage }: { t: (typeof dictionaries)[Locale]; usage?: BabelJob["usage_summary"] }) {
  const totalTokens = usage?.total_tokens || 0;
  const promptTokens = usage?.prompt_tokens || 0;
  const completionTokens = usage?.completion_tokens || 0;
  const estimatedTokens = usage?.estimated_total_tokens || 0;
  const requests = usage?.requests || usage?.estimated_requests || 0;
  const estimatedCost = usage?.estimated_cost || 0;
  const actualCost = usage?.actual_cost || 0;
  const budgetSpent = usage?.budget_spent || 0;
  const budgetLimit = usage?.budget_limit || 0;
  const hasUsage = totalTokens || estimatedTokens || estimatedCost || actualCost || budgetLimit;
  return (
    <HeroCard variant="secondary" className="mt-4">
      <div className="font-mono text-[0.66rem] font-bold uppercase tracking-[0.14em] text-muted">{t.usageTitle}</div>
      {hasUsage ? (
        <div className="mt-3 grid grid-cols-2 gap-3 lg:grid-cols-4">
          <Metric label={t.totalTokens} value={formatNumber(totalTokens || estimatedTokens)} />
          <Metric label={t.promptTokens} value={formatNumber(promptTokens)} />
          <Metric label={t.completionTokens} value={formatNumber(completionTokens)} />
          <Metric label={t.providerCalls} value={formatNumber(requests)} />
          <Metric label={t.estimatedCost} value={formatCurrency(estimatedCost)} />
          <Metric label={t.actualCost} value={formatCurrency(actualCost)} />
          <Metric label={t.budgetSpent} value={formatCurrency(budgetSpent)} />
          <Metric label={t.budgetLimitMetric} value={budgetLimit ? formatCurrency(budgetLimit) : "off"} />
        </div>
      ) : (
        <div className="mt-2 text-sm text-muted">
          {t.tokenUsageUnavailable}
          {requests ? ` ${t.providerCalls}: ${formatNumber(requests)}` : ""}
        </div>
      )}
    </HeroCard>
  );
}

function Field({ label, helper, children }: { label: string; helper?: string; children: React.ReactNode }) {
  return (
    <TextField fullWidth className="block">
      <Label className="mb-2 block font-mono text-[0.68rem] font-bold uppercase tracking-[0.13em] text-muted">{label}</Label>
      {children}
      {helper ? <Description className="mt-2 block text-xs leading-relaxed text-muted">{helper}</Description> : null}
    </TextField>
  );
}

function NumberInputField({ label, helper, name, minValue, step, value, disabled = false, onChange }: { label: string; helper?: string; name?: string; minValue?: number; step?: number; value: string; disabled?: boolean; onChange: (value: string) => void }) {
  const numericValue = value.trim() === "" ? undefined : Number(value);
  return (
    <NumberField fullWidth isDisabled={disabled} name={name} minValue={minValue} step={step} value={numericValue} onChange={(nextValue) => onChange(Number.isNaN(nextValue) ? "" : String(nextValue))}>
      <Label className="mb-2 block font-mono text-[0.68rem] font-bold uppercase tracking-[0.13em] text-muted">{label}</Label>
      <NumberField.Group>
        <NumberField.Input />
        <NumberField.DecrementButton aria-label={`Decrease ${label}`}>−</NumberField.DecrementButton>
        <NumberField.IncrementButton aria-label={`Increase ${label}`}>+</NumberField.IncrementButton>
      </NumberField.Group>
      {helper ? <Description className="mt-2 block text-xs leading-relaxed text-muted">{helper}</Description> : null}
    </NumberField>
  );
}

function Input({ className, ...props }: React.InputHTMLAttributes<HTMLInputElement>) {
  return <HeroInput fullWidth variant="primary" className={className} {...(props as React.ComponentProps<typeof HeroInput>)} />;
}

function TableInput({ ariaLabel, value, onChange }: { ariaLabel: string; value: string; onChange: (value: string) => void }) {
  return <HeroInput aria-label={ariaLabel} fullWidth variant="secondary" className="min-w-24" value={value} onChange={(event) => onChange(event.target.value)} />;
}

function Select({ className, children, label, helper, ...props }: React.SelectHTMLAttributes<HTMLSelectElement> & { label?: string; helper?: string }) {
  const options = React.Children.toArray(children)
    .filter(React.isValidElement)
    .map((child) => {
      const option = child as React.ReactElement<React.OptionHTMLAttributes<HTMLOptionElement>>;
      return {
        value: String(option.props.value ?? option.props.children ?? ""),
        label: option.props.children,
        disabled: option.props.disabled,
      };
    });
  const selectedKey = props.value === undefined ? undefined : String(props.value);
  return (
    <HeroSelect
      className={cn("w-full", className)}
      fullWidth
      aria-label={props["aria-label"]}
      name={props.name}
      isRequired={props.required}
      isDisabled={props.disabled}
      variant="primary"
      selectedKey={selectedKey}
      onSelectionChange={(key) => {
        if (key === null) {
          return;
        }
        props.onChange?.({ target: { value: String(key) } } as React.ChangeEvent<HTMLSelectElement>);
      }}
    >
      {label ? <Label className="mb-2 block font-mono text-[0.68rem] font-bold uppercase tracking-[0.13em] text-muted">{label}</Label> : null}
      <HeroSelect.Trigger>
        <HeroSelect.Value />
        <HeroSelect.Indicator>
          <CaretDown size={17} weight="bold" />
        </HeroSelect.Indicator>
      </HeroSelect.Trigger>
      <HeroSelect.Popover>
        <ListBox>
          {options.map((option) => (
            <ListBox.Item
              key={option.value}
              id={option.value}
              isDisabled={option.disabled}
            >
              {option.label}
              <ListBox.ItemIndicator>
                <CheckCircle size={16} weight="bold" />
              </ListBox.ItemIndicator>
            </ListBox.Item>
          ))}
        </ListBox>
      </HeroSelect.Popover>
      {helper ? <Description className="mt-2 block text-xs leading-relaxed text-muted">{helper}</Description> : null}
    </HeroSelect>
  );
}

function Button({ variant = "primary", className, children, disabled, onClick, ...props }: React.ButtonHTMLAttributes<HTMLButtonElement> & { variant?: "primary" | "secondary" | "ghost" }) {
  return (
    <HeroButton
      className={className}
      isDisabled={disabled}
      onPress={(event) => onClick?.(event as unknown as React.MouseEvent<HTMLButtonElement>)}
      variant={variant}
      {...(props as Omit<React.ComponentProps<typeof HeroButton>, "className" | "children" | "isDisabled" | "onPress">)}
    >
      {children}
    </HeroButton>
  );
}

function glossaryStats(terms: GlossaryTerm[]) {
  return computeGlossaryStats(terms);
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
  return hasGlossaryReviewWarnings(terms);
}

function canUseProvider(provider: ProviderSettings, hasSavedApiKey: boolean): boolean {
  return canUseProviderForSettings(provider, hasSavedApiKey);
}

function statusTone(status?: string): Tone {
  if (status === "running" || status === "preparing") return "running";
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

function formatCurrency(value: number): string {
  return `$${value.toFixed(6)}`;
}

function eventTime(value?: string): string {
  if (!value) return "00:00:00";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value.replace("T", " ").replace("Z", "");
  return date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}


const API_TOKEN_STORAGE_KEY = "babel_api_token";
const AUTH_REQUIRED_EVENT = "babel-auth-required";

async function authenticatedFetch(url: string, options?: RequestInit): Promise<Response> {
  const headers = new Headers(options?.headers);
  const token = sessionStorage.getItem(API_TOKEN_STORAGE_KEY)?.trim();
  if (token) headers.set("X-Babel-Token", token);
  const response = await fetch(url, { ...options, headers });
  if (response.status === 401) window.dispatchEvent(new Event(AUTH_REQUIRED_EVENT));
  return response;
}

async function fetchJson<T>(url: string, options?: RequestInit): Promise<T> {
  const response = await authenticatedFetch(url, options);
  if (!response.ok) {
    const text = await response.text();
    try {
      const problem = JSON.parse(text) as { error?: string; diagnostic?: { title?: string; message?: string; guidance?: string[] } };
      const diagnostic = problem.diagnostic;
      const explanation = [diagnostic?.title, diagnostic?.message, ...(diagnostic?.guidance || [])].filter(Boolean).join(" · ");
      throw new Error(explanation || problem.error || response.statusText);
    } catch (error) {
      if (error instanceof SyntaxError) throw new Error(text || response.statusText);
      throw error;
    }
  }
  return (await response.json()) as T;
}

async function downloadApiFile(url: string): Promise<void> {
  const response = await authenticatedFetch(url);
  if (!response.ok) throw new Error((await response.text()) || response.statusText);
  const disposition = response.headers.get("Content-Disposition") || "";
  const filename = disposition.match(/filename="?([^";]+)"?/i)?.[1] || "babel-download";
  const objectUrl = URL.createObjectURL(await response.blob());
  const anchor = document.createElement("a");
  anchor.href = objectUrl;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(objectUrl);
}

function normalizeError(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

function cn(...parts: Array<string | false | undefined | null>) {
  return parts.filter(Boolean).join(" ");
}

export default App;
