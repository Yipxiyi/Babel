import type * as React from "react";
import { forwardRef, useEffect, useRef, useState } from "react";
import {
  ArrowClockwise,
  BookOpenText,
  CaretRight,
  CheckCircle,
  ClockCounterClockwise,
  DownloadSimple,
  FileArrowUp,
  FileText,
  FloppyDisk,
  GearSix,
  Globe,
  LockKey,
  MagnifyingGlass,
  Play,
  Question,
  TerminalWindow,
  WarningCircle,
  X,
} from "@phosphor-icons/react";
import babelIconUrl from "../../docs/assets/brand/babel-icon.png";

type Locale = "en" | "zh";
type JobStatus = "prepared" | "running" | "failed" | "completed" | string;
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
  input?: string;
  output?: string;
};

type JobEvent = {
  ts?: string;
  type: string;
  message: string;
  batch?: BatchSummary;
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
};

type JobResponse = {
  job: BabelJob;
  glossary?: string;
};

type JobsResponse = {
  jobs: BabelJob[];
};

type FormState = {
  target_language: string;
  title: string;
  language: string;
  output_format: string;
};

type ProviderState = {
  provider: string;
  base_url: string;
  api_key: string;
  model: string;
  max_concurrency: string;
  request_timeout: string;
  max_retries: string;
};

type Notice = {
  kind: "info" | "error" | "success";
  text: string;
} | null;

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

const dictionaries = {
  en: {
    localeName: "English",
    otherLocale: "中文",
    appTitle: "Babel",
    appSubtitle: "Structure-preserving ebook translation workbench",
    statusBadge: "Self-hosted",
    guide: "Guide",
    repo: "GitHub",
    docs: "Docs",
    inputHeading: "1. Input & Settings",
    uploadTitle: "Upload Book",
    dropTitle: "Drop ebook here",
    dropHint: "or click to browse",
    fileLocal: "The file remains on this server.",
    noFile: "No file selected",
    targetLanguage: "Target language",
    outputTitle: "Output title",
    languageCode: "Language code",
    outputFormat: "Output format",
    prepare: "Prepare Workspace",
    providerTitle: "API Provider",
    provider: "Provider",
    baseUrl: "Base URL",
    apiKey: "API key",
    model: "Model",
    concurrency: "Concurrency",
    requestTimeout: "Request timeout",
    retries: "Retries",
    start: "Start Translation",
    resume: "Resume Translation",
    providerHint:
      "Keys are sent only to this local server process. Add authentication before exposing Babel beyond your machine.",
    glossaryHeading: "2. Glossary & Progress",
    glossaryTitle: "Glossary Review",
    glossaryHint: "Review character names, places, forms of address, and recurring terms before spending tokens.",
    searchPlaceholder: "Search terms...",
    saveGlossary: "Save Glossary",
    jobProgress: "Job Progress",
    terminalTitle: "Process terminal",
    terminalIdle: "waiting for a job...",
    currentBatch: "Current batch",
    activeBatches: "Active batches",
    failedBatch: "Failed batch",
    failedBatches: "Failed batches",
    failedBatchList: "Failed batch list",
    updated: "Updated",
    completed: "completed",
    batches: "batches",
    blocks: "blocks",
    noJob: "No job prepared.",
    outputHeading: "3. Output & Validation",
    downloads: "Downloads",
    downloadBook: "Download Book",
    downloadGlossary: "Download Glossary",
    downloadReport: "Download Report",
    downloadAudit: "Download Audit JSON",
    unavailable: "Not ready yet",
    validation: "Validation",
    validationHint:
      "Babel validates batch row IDs, root tags, structural attributes, links, anchors, placeholder text, ZIP integrity, and EPUB references before exposing final artifacts.",
    validationReady: "Validation passed",
    validationPending: "Waiting for translated output",
    validationFailed: "Needs attention",
    guideTitle: "How to run a Babel job",
    guideIntro: "Follow this order to avoid wasted provider calls and unclear failed states.",
    close: "Close",
    startWithUpload: "Start with upload",
    viewCurrentJob: "View current job",
    noticePrepared: "Workspace prepared. Review the glossary before starting.",
    noticeGlossary: "Glossary saved.",
    noticeStarted: "Translation started.",
    noticeResume: "Resume requested.",
    noticeLoaded: "Latest job loaded.",
    openProvider: "OpenAI Compatible",
    anthropic: "Anthropic Claude",
    fake: "Fake Dry Run",
    formatHelper: "EPUB is native. Other formats use Calibre when available.",
    source: "Source",
    action: "Action",
    state: "State",
    refreshJob: "Refresh Job",
    preparing: "Preparing...",
    preparingWorkspace: "Preparing workspace...",
    starting: "Starting...",
    saving: "Saving...",
    ready: "Ready",
    preparePrompt: "Prepare a workspace to begin.",
    blankLine: "blank line",
    validationPassed: "passed",
    validationBlocked: "blocked",
    validationPendingShort: "pending",
    translatedTitlePlaceholder: "Translated title",
    glossaryPlaceholder: "Prepare a job to review glossary candidates.",
    noBatch: "none",
    notRecorded: "not recorded",
    licenseLine: "Babel is open source software licensed under the MIT License.",
    builtWithBabel: "Built with Babel",
    guideSteps: [
      ["Upload", "Choose an ebook, target language, and final output format."],
      ["Prepare", "Generate a private workspace, batch manifest, and glossary scaffold."],
      ["Review glossary", "Check names, places, titles, nicknames, and repeated terms."],
      ["Configure provider", "Enter provider, base URL, API key, and model for this run."],
      ["Start or resume", "Start translation, or resume a failed job from the first invalid batch."],
      ["Monitor and download", "Watch the terminal log, then download the book, report, and audit."],
    ],
    validationItems: [
      "Batch row IDs",
      "XHTML structure",
      "Internal links",
      "Images and resources",
      "Output package",
    ],
  },
  zh: {
    localeName: "简体中文",
    otherLocale: "EN",
    appTitle: "Babel",
    appSubtitle: "保留结构的电子书翻译工作台",
    statusBadge: "本地自部署",
    guide: "引导",
    repo: "GitHub",
    docs: "文档",
    inputHeading: "1. 输入与设置",
    uploadTitle: "上传电子书",
    dropTitle: "将电子书拖到这里",
    dropHint: "或点击选择文件",
    fileLocal: "文件只保存在当前服务器。",
    noFile: "尚未选择文件",
    targetLanguage: "目标语言",
    outputTitle: "输出标题",
    languageCode: "语言代码",
    outputFormat: "输出格式",
    prepare: "准备工作区",
    providerTitle: "API Provider",
    provider: "Provider",
    baseUrl: "Base URL",
    apiKey: "API Key",
    model: "Model",
    concurrency: "并发数",
    requestTimeout: "请求超时",
    retries: "重试次数",
    start: "开始翻译",
    resume: "继续翻译",
    providerHint: "密钥只发送到本地服务进程。若要公网部署，必须先增加认证保护。",
    glossaryHeading: "2. 术语表与进度",
    glossaryTitle: "Glossary 审查",
    glossaryHint: "在消耗 tokens 前，先确认人物名、地名、称呼、昵称和高频术语。",
    searchPlaceholder: "搜索术语...",
    saveGlossary: "保存 Glossary",
    jobProgress: "任务进度",
    terminalTitle: "过程终端",
    terminalIdle: "等待任务...",
    currentBatch: "当前批次",
    activeBatches: "活跃批次",
    failedBatch: "失败批次",
    failedBatches: "失败批次数",
    failedBatchList: "失败批次列表",
    updated: "更新于",
    completed: "已完成",
    batches: "批次",
    blocks: "文本块",
    noJob: "尚未准备任务。",
    outputHeading: "3. 输出与校验",
    downloads: "下载",
    downloadBook: "下载译本",
    downloadGlossary: "下载 Glossary",
    downloadReport: "下载报告",
    downloadAudit: "下载 Audit JSON",
    unavailable: "尚未就绪",
    validation: "校验",
    validationHint:
      "Babel 会在开放最终产物前校验批次 ID、根标签、结构属性、链接、锚点、占位译文、ZIP 完整性和 EPUB 内部引用。",
    validationReady: "校验通过",
    validationPending: "等待翻译输出",
    validationFailed: "需要处理",
    guideTitle: "如何执行 Babel 任务",
    guideIntro: "按这个顺序操作，可以减少 token 浪费，也能更清楚地处理失败状态。",
    close: "关闭",
    startWithUpload: "从上传开始",
    viewCurrentJob: "查看当前任务",
    noticePrepared: "工作区已准备。开始前请先审查 glossary。",
    noticeGlossary: "Glossary 已保存。",
    noticeStarted: "翻译已开始。",
    noticeResume: "已请求继续翻译。",
    noticeLoaded: "已载入最近任务。",
    openProvider: "OpenAI Compatible",
    anthropic: "Anthropic Claude",
    fake: "Fake Dry Run",
    formatHelper: "EPUB 为原生输出。其他格式在可用时通过 Calibre 导出。",
    source: "来源",
    action: "操作",
    state: "状态",
    refreshJob: "刷新任务",
    preparing: "准备中...",
    preparingWorkspace: "正在准备工作区...",
    starting: "启动中...",
    saving: "保存中...",
    ready: "已就绪",
    preparePrompt: "先准备工作区。",
    blankLine: "空行",
    validationPassed: "通过",
    validationBlocked: "阻塞",
    validationPendingShort: "等待",
    translatedTitlePlaceholder: "译本标题",
    glossaryPlaceholder: "准备任务后可审查 glossary 候选项。",
    noBatch: "无",
    notRecorded: "未记录",
    licenseLine: "Babel 是采用 MIT License 的开源软件。",
    builtWithBabel: "Built with Babel",
    guideSteps: [
      ["Upload", "选择电子书、目标语言和最终输出格式。"],
      ["Prepare", "生成私有工作区、批次清单和 glossary 脚手架。"],
      ["Review glossary", "检查人物名、地名、称呼、昵称和重复术语。"],
      ["Configure provider", "填写 provider、base URL、API key 和 model。"],
      ["Start or resume", "开始翻译；失败后从第一个无效批次继续。"],
      ["Monitor and download", "观察终端日志，完成后下载译本、报告和 audit。"],
    ],
    validationItems: ["批次行 ID", "XHTML 结构", "内部链接", "图片与资源", "输出包"],
  },
} as const;

function cn(...parts: Array<string | false | null | undefined>): string {
  return parts.filter(Boolean).join(" ");
}

function normalizeError(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

async function fetchJson<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, init);
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || response.statusText);
  }
  return (await response.json()) as T;
}

function formatTimestamp(value?: string, fallback = "not recorded"): string {
  if (!value) {
    return fallback;
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return date.toLocaleString([], {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    month: "short",
    day: "numeric",
  });
}

function eventTime(value?: string): string {
  if (!value) {
    return "00:00:00";
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value.replace("T", " ").replace("Z", "");
  }
  return date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

function batchLabel(batch?: BatchSummary | null, fallback = "none"): string {
  if (!batch) {
    return fallback;
  }
  const parts = [`#${batch.batch ?? "?"}`];
  if (batch.chapter_label) {
    parts.push(batch.chapter_label);
  } else if (batch.file) {
    parts.push(batch.file);
  }
  return parts.join(" · ");
}

function progressPercent(job: BabelJob | null): number {
  if (!job || !job.total_batches) {
    return 0;
  }
  return Math.round((job.completed_batches / job.total_batches) * 100);
}

function integerOption(value: string, fallback: number, min: number): number {
  const parsed = Number.parseInt(value, 10);
  if (!Number.isFinite(parsed) || parsed < min) {
    return fallback;
  }
  return parsed;
}

function activeBatchCount(job: BabelJob | null): number {
  if (!job) {
    return 0;
  }
  if (job.active_batches) {
    return job.active_batches.length;
  }
  return job.current_batch ? 1 : 0;
}

function failedBatchesForJob(job: BabelJob | null): BatchSummary[] {
  if (!job) {
    return [];
  }
  if (job.failed_batches?.length) {
    return job.failed_batches;
  }
  return job.failed_batch ? [job.failed_batch] : [];
}

function statusTone(status?: JobStatus): "idle" | "running" | "failed" | "completed" | "prepared" {
  if (status === "running") {
    return "running";
  }
  if (status === "failed") {
    return "failed";
  }
  if (status === "completed") {
    return "completed";
  }
  if (status === "prepared") {
    return "prepared";
  }
  return "idle";
}

function loadLocale(): Locale {
  return localStorage.getItem("babel_locale") === "zh" ? "zh" : "en";
}

function App() {
  const [locale, setLocale] = useState<Locale>(loadLocale);
  const [job, setJob] = useState<BabelJob | null>(null);
  const [currentJobId, setCurrentJobId] = useState<string>("");
  const [glossary, setGlossary] = useState("");
  const [selectedFileName, setSelectedFileName] = useState("");
  const [notice, setNotice] = useState<Notice>(null);
  const [guideOpen, setGuideOpen] = useState(false);
  const [search, setSearch] = useState("");
  const [isPreparing, setIsPreparing] = useState(false);
  const [isSavingGlossary, setIsSavingGlossary] = useState(false);
  const [isStarting, setIsStarting] = useState(false);
  const [form, setForm] = useState<FormState>({
    target_language: "Simplified Chinese",
    title: "",
    language: "zh-CN",
    output_format: "epub",
  });
  const [provider, setProvider] = useState<ProviderState>({
    provider: "openai-compatible",
    base_url: "https://api.openai.com/v1",
    api_key: "",
    model: "gpt-4.1",
    max_concurrency: "3",
    request_timeout: "300",
    max_retries: "1",
  });
  const fileInputRef = useRef<HTMLInputElement>(null);
  const jobProgressRef = useRef<HTMLElement>(null);
  const terminalRef = useRef<HTMLDivElement>(null);
  const guideReturnRef = useRef<HTMLElement | null>(null);
  const t = dictionaries[locale];

  useEffect(() => {
    localStorage.setItem("babel_locale", locale);
    document.documentElement.lang = locale === "zh" ? "zh-CN" : "en";
  }, [locale]);

  useEffect(() => {
    void loadLatestJob();
  }, []);

  useEffect(() => {
    if (!currentJobId || job?.status !== "running") {
      return;
    }
    const timer = window.setInterval(() => {
      void loadJob(currentJobId, false);
    }, 1500);
    return () => window.clearInterval(timer);
  }, [currentJobId, job?.status]);

  useEffect(() => {
    if (terminalRef.current) {
      terminalRef.current.scrollTop = terminalRef.current.scrollHeight;
    }
  }, [job?.events?.length, job?.status]);

  async function loadLatestJob() {
    try {
      const data = await fetchJson<JobsResponse>("/api/jobs");
      const latest = data.jobs?.[0];
      if (!latest) {
        setNotice(null);
        return;
      }
      await loadJob(latest.job_id, false);
    } catch (error) {
      setNotice({ kind: "error", text: normalizeError(error) });
    }
  }

  async function loadJob(jobId: string, announce = true) {
    const data = await fetchJson<JobResponse>(`/api/jobs/${jobId}`);
    setCurrentJobId(data.job.job_id);
    setJob(data.job);
    if (typeof data.glossary === "string") {
      setGlossary(data.glossary);
    }
    if (announce) {
      setNotice({ kind: "info", text: data.job.message || t.noticeLoaded });
    }
  }

  async function handlePrepare(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const file = fileInputRef.current?.files?.[0];
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
      const data = await fetchJson<JobResponse>("/api/jobs", { method: "POST", body });
      setCurrentJobId(data.job.job_id);
      setJob(data.job);
      setGlossary(data.glossary || "");
      setNotice({ kind: "success", text: t.noticePrepared });
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
      const data = await fetchJson<JobResponse>(`/api/jobs/${currentJobId}/glossary`, {
        method: "POST",
        body: glossary,
      });
      setJob(data.job);
      setGlossary(data.glossary || glossary);
      setNotice({ kind: "success", text: t.noticeGlossary });
    } catch (error) {
      setNotice({ kind: "error", text: normalizeError(error) });
    } finally {
      setIsSavingGlossary(false);
    }
  }

  async function handleStart(resume: boolean) {
    if (!currentJobId) {
      return;
    }
    setIsStarting(true);
    setNotice({ kind: "info", text: resume ? t.noticeResume : t.noticeStarted });
    try {
      const maxConcurrency = integerOption(provider.max_concurrency, 3, 1);
      const requestTimeout = integerOption(provider.request_timeout, 300, 1);
      const maxRetries = integerOption(provider.max_retries, 1, 0);
      const data = await fetchJson<{ job: BabelJob }>(`/api/jobs/${currentJobId}/start`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          ...provider,
          max_concurrency: maxConcurrency,
          request_timeout: requestTimeout,
          max_retries: maxRetries,
          target_language: form.target_language,
          resume,
        }),
      });
      setJob(data.job);
      window.setTimeout(() => {
        void loadJob(currentJobId, false);
      }, 700);
    } catch (error) {
      setNotice({ kind: "error", text: normalizeError(error) });
    } finally {
      setIsStarting(false);
    }
  }

  function updateForm<K extends keyof FormState>(key: K, value: FormState[K]) {
    setForm((previous) => ({ ...previous, [key]: value }));
  }

  function updateProvider<K extends keyof ProviderState>(key: K, value: ProviderState[K]) {
    setProvider((previous) => ({ ...previous, [key]: value }));
  }

  function openGuideDialog() {
    guideReturnRef.current = document.activeElement as HTMLElement | null;
    setGuideOpen(true);
  }

  function closeGuideDialog() {
    setGuideOpen(false);
    window.setTimeout(() => guideReturnRef.current?.focus(), 0);
  }

  function focusUploadFromGuide() {
    closeGuideDialog();
    window.setTimeout(() => fileInputRef.current?.focus(), 80);
  }

  function viewCurrentJobFromGuide() {
    closeGuideDialog();
    window.setTimeout(() => jobProgressRef.current?.scrollIntoView({ behavior: "smooth", block: "start" }), 80);
  }

  const percent = progressPercent(job);
  const tone = statusTone(job?.status);
  const canStart = Boolean(currentJobId) && job?.status !== "running";
  const canResume = Boolean(currentJobId) && job?.status === "failed";
  const canDownloadOutput = job?.status === "completed";
  const canDownloadGlossary = Boolean(currentJobId);
  const terminalEvents: JobEvent[] = job?.events?.length ? job.events : [{ type: "idle", message: t.terminalIdle }];

  return (
    <div className="min-h-[100dvh] overflow-x-hidden bg-paper text-ink">
      <div className="fixed inset-0 pointer-events-none -z-10 bg-atmosphere" />
      <AppHeader
        locale={locale}
        t={t}
        onToggleLocale={() => setLocale(locale === "en" ? "zh" : "en")}
        onOpenGuide={openGuideDialog}
      />
      <main className="mx-auto grid w-full max-w-[1480px] grid-cols-1 gap-6 px-4 pb-10 pt-5 md:px-6 xl:grid-cols-[380px_minmax(480px,1fr)_360px]">
        <Panel title={t.inputHeading} className="xl:sticky xl:top-5 xl:self-start">
          <UploadPanel
            t={t}
            form={form}
            selectedFileName={selectedFileName}
            isPreparing={isPreparing}
            fileInputRef={fileInputRef}
            onFileChange={(name) => setSelectedFileName(name)}
            onPrepare={handlePrepare}
            onUpdateForm={updateForm}
          />
          <ProviderPanel
            t={t}
            provider={provider}
            canStart={canStart}
            isStarting={isStarting}
            onUpdateProvider={updateProvider}
            onStart={() => void handleStart(false)}
          />
        </Panel>

        <div className="space-y-6">
          <Panel title={t.glossaryHeading}>
            <GlossaryEditor
              t={t}
              glossary={glossary}
              search={search}
              canSave={Boolean(currentJobId)}
              isSaving={isSavingGlossary}
              onSearch={setSearch}
              onChange={setGlossary}
              onSave={() => void handleSaveGlossary()}
            />
          </Panel>
          <Panel title={t.jobProgress} ref={jobProgressRef}>
            <JobSummary t={t} job={job} tone={tone} percent={percent} notice={notice} />
            <TerminalLog t={t} events={terminalEvents} status={job?.status} terminalRef={terminalRef} />
            <div className="mt-4 flex flex-col gap-3 sm:flex-row">
              <Button
                type="button"
                variant="secondary"
                disabled={!canResume || isStarting}
                onClick={() => void handleStart(true)}
                id="resumeBtn"
              >
                <ArrowClockwise size={18} weight="bold" />
                {t.resume}
              </Button>
              <Button type="button" variant="ghost" disabled={!currentJobId} onClick={() => void loadJob(currentJobId)}>
                <ClockCounterClockwise size={18} weight="bold" />
                {t.refreshJob}
              </Button>
            </div>
          </Panel>
        </div>

        <Panel title={t.outputHeading} className="xl:sticky xl:top-5 xl:self-start">
          <DownloadsPanel
            t={t}
            jobId={currentJobId}
            canDownloadOutput={canDownloadOutput}
            canDownloadGlossary={canDownloadGlossary}
          />
          <ValidationPanel t={t} tone={tone} />
        </Panel>
      </main>
      <footer className="mx-auto flex w-full max-w-[1480px] flex-col gap-3 border-t border-ink/15 px-4 py-6 text-xs text-muted md:px-6 lg:flex-row lg:items-center lg:justify-between">
        <span>{t.licenseLine}</span>
        <span className="inline-flex items-center gap-2 font-mono uppercase tracking-[0.28em]">
          <BookOpenText size={18} weight="bold" />
          {t.builtWithBabel}
        </span>
      </footer>
      {guideOpen ? (
        <GuideModal
          t={t}
          onClose={closeGuideDialog}
          onStartWithUpload={focusUploadFromGuide}
          onViewCurrentJob={viewCurrentJobFromGuide}
        />
      ) : null}
    </div>
  );
}

function AppHeader({
  locale,
  t,
  onToggleLocale,
  onOpenGuide,
}: {
  locale: Locale;
  t: (typeof dictionaries)[Locale];
  onToggleLocale: () => void;
  onOpenGuide: () => void;
}) {
  return (
    <header className="mx-auto flex w-full max-w-[1480px] flex-col gap-5 border-b border-ink/20 px-4 py-5 md:px-6 lg:flex-row lg:items-center lg:justify-between">
      <div className="flex min-w-0 items-center gap-4">
        <img
          className="size-16 shrink-0 rounded-[1.35rem] border border-ink/15 object-cover shadow-brand"
          src={babelIconUrl}
          alt="Babel project icon"
        />
        <div className="min-w-0">
          <div className="flex flex-wrap items-end gap-3">
            <h1 className="font-sans text-5xl font-black leading-none tracking-[-0.035em] md:text-6xl">{t.appTitle}</h1>
            <div className="hidden pb-2 font-mono text-[0.68rem] uppercase tracking-[0.24em] text-muted sm:block">
              {t.appSubtitle}
            </div>
          </div>
          <div className="mt-2 flex flex-wrap items-center gap-2 text-xs text-muted">
            <span className="rounded-full border border-clay/40 bg-clay/10 px-3 py-1 font-mono uppercase tracking-[0.18em] text-clay">
              {t.statusBadge}
            </span>
            <span>v0.6.0</span>
          </div>
        </div>
      </div>
      <nav className="flex flex-wrap items-center gap-2">
        <HeaderLink href="https://github.com/Yipxiyi/Babel" label={t.repo} icon={BookOpenText} />
        <HeaderLink href="https://github.com/Yipxiyi/Babel#readme" label={t.docs} icon={FileText} />
        <Button type="button" variant="ghost" onClick={onToggleLocale} aria-label={`Switch language from ${locale}`}>
          <Globe size={18} weight="bold" />
          {t.otherLocale}
        </Button>
        <Button type="button" variant="secondary" onClick={onOpenGuide}>
          <Question size={18} weight="bold" />
          {t.guide}
        </Button>
      </nav>
    </header>
  );
}

function HeaderLink({ href, label, icon: Icon }: { href: string; label: string; icon: IconComponent }) {
  return (
    <a
      className="inline-flex items-center justify-center gap-2 rounded-full border border-ink/15 bg-surface/70 px-4 py-2 text-sm font-semibold text-ink transition hover:-translate-y-0.5 hover:border-ink/30 hover:bg-surface focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-clay"
      href={href}
      target="_blank"
      rel="noreferrer"
    >
      <Icon size={18} weight="bold" />
      {label}
    </a>
  );
}

type PanelProps = {
  title: string;
  className?: string;
  children: React.ReactNode;
} & React.HTMLAttributes<HTMLElement>;

const Panel = forwardRef<HTMLElement, PanelProps>(function PanelComponent(
  {
    title,
    className,
    children,
  },
  ref,
) {
  return (
    <section ref={ref} className={cn("rounded-[1.7rem] border border-ink/15 bg-surface/82 p-5 shadow-panel backdrop-blur", className)}>
      <h2 className="mb-4 font-mono text-sm font-bold uppercase tracking-[0.18em] text-ink">{title}</h2>
      {children}
    </section>
  );
});

function UploadPanel({
  t,
  form,
  selectedFileName,
  isPreparing,
  fileInputRef,
  onFileChange,
  onPrepare,
  onUpdateForm,
}: {
  t: (typeof dictionaries)[Locale];
  form: FormState;
  selectedFileName: string;
  isPreparing: boolean;
  fileInputRef: React.RefObject<HTMLInputElement | null>;
  onFileChange: (name: string) => void;
  onPrepare: (event: React.FormEvent<HTMLFormElement>) => void;
  onUpdateForm: <K extends keyof FormState>(key: K, value: FormState[K]) => void;
}) {
  return (
    <form className="space-y-4" onSubmit={onPrepare}>
      <div>
        <h3 className="mb-3 text-lg font-bold tracking-tight">{t.uploadTitle}</h3>
        <label className="group flex cursor-pointer flex-col items-center justify-center rounded-[1.4rem] border border-dashed border-clay/55 bg-paper/70 px-5 py-8 text-center transition hover:-translate-y-0.5 hover:bg-clay/8">
          <input
            ref={fileInputRef}
            className="sr-only"
            required
            name="epub"
            type="file"
            accept={ACCEPT_EXTENSIONS}
            onChange={(event) => onFileChange(event.target.files?.[0]?.name || "")}
          />
          <FileArrowUp size={42} className="mb-4 text-clay transition group-hover:scale-105" weight="duotone" />
          <span className="text-base font-bold">{t.dropTitle}</span>
          <span className="mt-1 text-sm text-muted">{t.dropHint}</span>
          <span className="mt-4 text-xs text-muted">{t.fileLocal}</span>
        </label>
        <div className="mt-3 flex items-center justify-between rounded-2xl border border-ink/12 bg-surface px-4 py-3">
          <span className="min-w-0 truncate text-sm font-semibold">{selectedFileName || t.noFile}</span>
          <X size={17} className="text-muted" weight="bold" />
        </div>
      </div>
      <Field label={t.targetLanguage}>
        <Input
          name="target_language"
          value={form.target_language}
          onChange={(event) => onUpdateForm("target_language", event.target.value)}
        />
      </Field>
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-1 2xl:grid-cols-2">
        <Field label={t.outputTitle}>
          <Input
            name="title"
            value={form.title}
            placeholder={t.translatedTitlePlaceholder}
            onChange={(event) => onUpdateForm("title", event.target.value)}
          />
        </Field>
        <Field label={t.languageCode}>
          <Input name="language" value={form.language} onChange={(event) => onUpdateForm("language", event.target.value)} />
        </Field>
      </div>
      <Field label={t.outputFormat} helper={t.formatHelper}>
        <Select
          name="output_format"
          value={form.output_format}
          onChange={(event) => onUpdateForm("output_format", event.target.value)}
        >
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

function ProviderPanel({
  t,
  provider,
  canStart,
  isStarting,
  onUpdateProvider,
  onStart,
}: {
  t: (typeof dictionaries)[Locale];
  provider: ProviderState;
  canStart: boolean;
  isStarting: boolean;
  onUpdateProvider: <K extends keyof ProviderState>(key: K, value: ProviderState[K]) => void;
  onStart: () => void;
}) {
  return (
    <div className="mt-7 border-t border-ink/12 pt-5">
      <h3 className="mb-3 text-lg font-bold tracking-tight">{t.providerTitle}</h3>
      <div className="space-y-4">
        <Field label={t.provider}>
          <Select value={provider.provider} onChange={(event) => onUpdateProvider("provider", event.target.value)}>
            <option value="openai-compatible">{t.openProvider}</option>
            <option value="anthropic">{t.anthropic}</option>
            <option value="fake">{t.fake}</option>
          </Select>
        </Field>
        <Field label={t.baseUrl}>
          <Input value={provider.base_url} onChange={(event) => onUpdateProvider("base_url", event.target.value)} />
        </Field>
        <Field label={t.apiKey}>
          <div className="relative">
            <Input
              className="pr-10"
              type="password"
              autoComplete="off"
              value={provider.api_key}
              onChange={(event) => onUpdateProvider("api_key", event.target.value)}
            />
            <LockKey size={18} className="absolute right-3 top-1/2 -translate-y-1/2 text-muted" weight="bold" />
          </div>
        </Field>
        <Field label={t.model}>
          <Input value={provider.model} onChange={(event) => onUpdateProvider("model", event.target.value)} />
        </Field>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-3 xl:grid-cols-1 2xl:grid-cols-3">
          <Field label={t.concurrency}>
            <Input
              type="number"
              min={1}
              step={1}
              inputMode="numeric"
              value={provider.max_concurrency}
              onChange={(event) => onUpdateProvider("max_concurrency", event.target.value)}
            />
          </Field>
          <Field label={t.requestTimeout}>
            <Input
              type="number"
              min={1}
              step={1}
              inputMode="numeric"
              value={provider.request_timeout}
              onChange={(event) => onUpdateProvider("request_timeout", event.target.value)}
            />
          </Field>
          <Field label={t.retries}>
            <Input
              type="number"
              min={0}
              step={1}
              inputMode="numeric"
              value={provider.max_retries}
              onChange={(event) => onUpdateProvider("max_retries", event.target.value)}
            />
          </Field>
        </div>
        <Button type="button" disabled={!canStart || isStarting} onClick={onStart}>
          <Play size={18} weight="bold" />
          {isStarting ? t.starting : t.start}
        </Button>
        <p className="text-sm leading-relaxed text-muted">{t.providerHint}</p>
      </div>
    </div>
  );
}

function GlossaryEditor({
  t,
  glossary,
  search,
  canSave,
  isSaving,
  onSearch,
  onChange,
  onSave,
}: {
  t: (typeof dictionaries)[Locale];
  glossary: string;
  search: string;
  canSave: boolean;
  isSaving: boolean;
  onSearch: (value: string) => void;
  onChange: (value: string) => void;
  onSave: () => void;
}) {
  const filteredPreview = glossary
    .split("\n")
    .filter((line) => !search || line.toLowerCase().includes(search.toLowerCase()))
    .slice(0, 6);

  return (
    <div>
      <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
        <div>
          <h3 className="text-lg font-bold tracking-tight">{t.glossaryTitle}</h3>
          <p className="mt-1 max-w-[62ch] text-sm leading-relaxed text-muted">{t.glossaryHint}</p>
        </div>
        <div className="relative min-w-0 lg:w-64">
          <Input
            className="pl-10"
            value={search}
            placeholder={t.searchPlaceholder}
            onChange={(event) => onSearch(event.target.value)}
          />
          <MagnifyingGlass size={18} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted" weight="bold" />
        </div>
      </div>
      <div className="mt-5 grid gap-4 lg:grid-cols-[minmax(0,1fr)_230px]">
        <textarea
          className="min-h-72 w-full resize-y rounded-[1.25rem] border border-ink/12 bg-paper/70 p-4 font-mono text-sm leading-relaxed text-ink outline-none transition placeholder:text-muted focus:border-clay focus:ring-2 focus:ring-clay/20"
          value={glossary}
          placeholder={t.glossaryPlaceholder}
          onChange={(event) => onChange(event.target.value)}
        />
        <div className="rounded-[1.25rem] border border-ink/12 bg-surface p-4">
          <div className="mb-3 flex items-center justify-between text-xs font-bold uppercase tracking-[0.14em] text-muted">
            <span>{t.source}</span>
            <span>{t.state}</span>
          </div>
          <div className="space-y-2">
            {filteredPreview.length ? (
              filteredPreview.map((line, index) => (
                <div key={`${line}-${index}`} className="rounded-xl border border-ink/10 bg-paper/70 px-3 py-2 text-xs">
                  <div className="truncate font-mono text-ink">{line || t.blankLine}</div>
                </div>
              ))
            ) : (
              <div className="rounded-xl border border-dashed border-ink/15 bg-paper/70 px-3 py-6 text-center text-sm text-muted">
                {t.noJob}
              </div>
            )}
          </div>
        </div>
      </div>
      <div className="mt-4 flex justify-end">
        <Button type="button" variant="secondary" disabled={!canSave || isSaving} onClick={onSave}>
          <FloppyDisk size={18} weight="bold" />
          {isSaving ? t.saving : t.saveGlossary}
        </Button>
      </div>
    </div>
  );
}

function JobSummary({
  t,
  job,
  tone,
  percent,
  notice,
}: {
  t: (typeof dictionaries)[Locale];
  job: BabelJob | null;
  tone: ReturnType<typeof statusTone>;
  percent: number;
  notice: Notice;
}) {
  const activeCount = activeBatchCount(job);
  const failedBatches = failedBatchesForJob(job);
  const maxConcurrencySuffix = typeof job?.max_concurrency === "number" ? `/${job.max_concurrency}` : "";

  return (
    <div className="rounded-[1.5rem] border border-ink/12 bg-surface p-4">
      <div className="grid gap-5 lg:grid-cols-[150px_minmax(0,1fr)]">
        <div className="relative mx-auto flex size-32 items-center justify-center rounded-full bg-paper">
          <div
            className="absolute inset-0 rounded-full"
            style={{
              background: `conic-gradient(var(--clay) ${percent * 3.6}deg, var(--line) 0deg)`,
            }}
          />
          <div className="relative flex size-24 flex-col items-center justify-center rounded-full bg-surface shadow-inner">
            <span className="text-3xl font-black tracking-tight">{percent}%</span>
            <span className="font-mono text-[0.62rem] uppercase tracking-[0.18em] text-muted">{t.completed}</span>
          </div>
        </div>
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <StatusPill status={job?.status || "idle"} tone={tone} />
            {job?.input_format ? <span className="rounded-full border border-ink/10 px-3 py-1 text-xs text-muted">{job.input_format}</span> : null}
            {job?.output_format ? <span className="rounded-full border border-ink/10 px-3 py-1 text-xs text-muted">{job.output_format}</span> : null}
          </div>
          <h3 className="mt-3 truncate text-xl font-bold tracking-tight">{job?.filename || t.noJob}</h3>
          <p className="mt-1 min-h-5 text-sm leading-relaxed text-muted">{job?.message || t.preparePrompt}</p>
          <div className="mt-4 h-3 overflow-hidden rounded-full bg-line">
            <div className="h-full rounded-full bg-clay transition-[width] duration-200" style={{ width: `${percent}%` }} />
          </div>
          <div className="mt-4 grid grid-cols-2 gap-3 md:grid-cols-3 2xl:grid-cols-6">
            <Metric label={t.batches} value={job ? `${job.completed_batches}/${job.total_batches}` : "0/0"} />
            <Metric label={t.blocks} value={job?.block_count ? String(job.block_count) : "0"} />
            <Metric label={t.activeBatches} value={`${activeCount}${maxConcurrencySuffix}`} />
            <Metric label={t.failedBatches} value={String(failedBatches.length)} />
            <Metric label={t.currentBatch} value={batchLabel(job?.current_batch, t.noBatch)} />
            <Metric label={t.updated} value={formatTimestamp(job?.last_active_at, t.notRecorded)} />
          </div>
          {failedBatches.length ? (
            <div className="mt-4 rounded-2xl border border-danger/35 bg-danger/8 p-3 text-sm text-danger">
              <strong>{t.failedBatchList}:</strong>
              <ul className="mt-2 space-y-1">
                {failedBatches.map((batch, index) => (
                  <li key={`${batch.batch ?? "batch"}-${batch.file ?? "file"}-${index}`}>{batchLabel(batch, t.noBatch)}</li>
                ))}
              </ul>
            </div>
          ) : null}
          {notice ? <NoticeBar notice={notice} /> : null}
        </div>
      </div>
    </div>
  );
}

function TerminalLog({
  t,
  events,
  status,
  terminalRef,
}: {
  t: (typeof dictionaries)[Locale];
  events: JobEvent[];
  status?: JobStatus;
  terminalRef: React.RefObject<HTMLDivElement | null>;
}) {
  return (
    <div className="mt-5 overflow-hidden rounded-[1.35rem] border border-terminal-line bg-terminal text-terminal-ink shadow-terminal">
      <div className="flex items-center justify-between border-b border-terminal-line px-4 py-3">
        <div className="inline-flex items-center gap-2 font-mono text-xs font-bold uppercase tracking-[0.18em]">
          <TerminalWindow size={17} weight="bold" />
          {t.terminalTitle}
        </div>
        <span className={cn("status-light", status === "running" && "is-running")} aria-label={status || "idle"} />
      </div>
      <div
        ref={terminalRef}
        id="terminalLog"
        data-api-loader="loadLatestJob"
        className="max-h-80 min-h-64 overflow-y-auto px-4 py-3 font-mono text-[0.8rem] leading-relaxed"
      >
        {events.map((event, index) => (
          <div key={`${event.ts || "event"}-${index}`} className={cn("terminal-line", `event-${event.type}`)}>
            <span className="mr-3 text-terminal-muted">{eventTime(event.ts)}</span>
            <span className="mr-3 text-terminal-accent">{event.type}</span>
            {event.batch ? <span className="mr-3 text-terminal-info">batch={event.batch.batch}</span> : null}
            <span>{event.message}</span>
          </div>
        ))}
        {status === "running" ? (
          <div className="terminal-line">
            <span className="terminal-cursor" />
          </div>
        ) : null}
      </div>
    </div>
  );
}

function DownloadsPanel({
  t,
  jobId,
  canDownloadOutput,
  canDownloadGlossary,
}: {
  t: (typeof dictionaries)[Locale];
  jobId: string;
  canDownloadOutput: boolean;
  canDownloadGlossary: boolean;
}) {
  const rows = [
    { label: t.downloadBook, path: "output", icon: BookOpenText, enabled: canDownloadOutput },
    { label: t.downloadGlossary, path: "glossary", icon: FileText, enabled: canDownloadGlossary },
    { label: t.downloadReport, path: "report", icon: FileText, enabled: canDownloadOutput },
    { label: t.downloadAudit, path: "audit", icon: GearSix, enabled: canDownloadOutput },
  ];
  return (
    <div>
      <h3 className="mb-3 text-lg font-bold tracking-tight">{t.downloads}</h3>
      <div className="space-y-3">
        {rows.map((row) => {
          const Icon = row.icon;
          const href = row.enabled && jobId ? `/api/jobs/${jobId}/download/${row.path}` : undefined;
          return (
            <a
              key={row.path}
              className={cn(
                "flex items-center gap-3 rounded-2xl border border-ink/12 bg-surface px-4 py-4 text-ink transition",
                row.enabled ? "hover:-translate-y-0.5 hover:border-clay/45" : "pointer-events-none opacity-55",
              )}
              href={href}
              aria-disabled={!row.enabled}
            >
              <Icon size={25} className="text-clay" weight="duotone" />
              <span className="min-w-0 flex-1">
                <span className="block truncate text-sm font-bold">{row.label}</span>
                <span className="text-xs text-muted">{row.enabled ? t.ready : t.unavailable}</span>
              </span>
              <DownloadSimple size={20} weight="bold" />
            </a>
          );
        })}
      </div>
    </div>
  );
}

function ValidationPanel({ t, tone }: { t: (typeof dictionaries)[Locale]; tone: ReturnType<typeof statusTone> }) {
  const stateLabel = tone === "completed" ? t.validationReady : tone === "failed" ? t.validationFailed : t.validationPending;
  const stateIcon = tone === "failed" ? WarningCircle : CheckCircle;
  const StateIcon = stateIcon;
  return (
    <div className="mt-6 border-t border-ink/12 pt-5">
      <h3 className="mb-3 text-lg font-bold tracking-tight">{t.validation}</h3>
      <div className="rounded-[1.35rem] border border-ink/12 bg-surface p-4">
        <div className="flex items-center gap-4">
          <div className={cn("grid size-16 place-items-center rounded-full border", tone === "failed" ? "border-danger text-danger" : "border-success text-success")}>
            <StateIcon size={36} weight="bold" />
          </div>
          <div>
            <div className="font-bold">{stateLabel}</div>
            <p className="mt-1 text-sm leading-relaxed text-muted">{t.validationHint}</p>
          </div>
        </div>
        <div className="mt-4 divide-y divide-ink/10 rounded-2xl border border-ink/10">
          {t.validationItems.map((item) => (
            <div key={item} className="flex items-center justify-between px-4 py-3 text-sm">
              <span>{item}</span>
              <span className={cn("font-mono text-xs", tone === "completed" ? "text-success" : tone === "failed" ? "text-danger" : "text-muted")}>
                {tone === "completed" ? t.validationPassed : tone === "failed" ? t.validationBlocked : t.validationPendingShort}
              </span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

function GuideModal({
  t,
  onClose,
  onStartWithUpload,
  onViewCurrentJob,
}: {
  t: (typeof dictionaries)[Locale];
  onClose: () => void;
  onStartWithUpload: () => void;
  onViewCurrentJob: () => void;
}) {
  const closeRef = useRef<HTMLButtonElement>(null);
  const dialogRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    closeRef.current?.focus();

    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        onClose();
      }
      if (event.key !== "Tab" || !dialogRef.current) {
        return;
      }
      const focusables = Array.from(
        dialogRef.current.querySelectorAll<HTMLElement>("button, [href], input, select, textarea, [tabindex]:not([tabindex='-1'])"),
      ).filter((element) => !element.hasAttribute("disabled"));
      const first = focusables[0];
      const last = focusables[focusables.length - 1];
      if (!first || !last) {
        return;
      }
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    }

    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("keydown", onKeyDown);
      document.body.style.overflow = previousOverflow;
    };
  }, [onClose]);

  return (
    <div className="fixed inset-0 z-40 flex items-center justify-center bg-ink/45 px-4 py-6 backdrop-blur-sm" onMouseDown={onClose}>
      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="guide-title"
        className="max-h-[88dvh] w-full max-w-2xl overflow-y-auto rounded-[2rem] border border-ink/15 bg-paper p-5 shadow-modal"
        onMouseDown={(event) => event.stopPropagation()}
      >
        <div className="flex items-start justify-between gap-4">
          <div>
            <h2 id="guide-title" className="text-2xl font-black tracking-tight">
              {t.guideTitle}
            </h2>
            <p className="mt-2 max-w-[58ch] text-sm leading-relaxed text-muted">{t.guideIntro}</p>
          </div>
          <button
            ref={closeRef}
            type="button"
            className="grid size-10 shrink-0 place-items-center rounded-full border border-ink/15 bg-surface text-ink transition hover:-translate-y-0.5 hover:border-clay/45 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-clay"
            onClick={onClose}
            aria-label={t.close}
          >
            <X size={18} weight="bold" />
          </button>
        </div>
        <ol className="mt-6 grid gap-3">
          {t.guideSteps.map(([title, description], index) => (
            <li key={title} className="grid grid-cols-[44px_minmax(0,1fr)] gap-3 rounded-2xl border border-ink/12 bg-surface/80 p-4">
              <div className="grid size-11 place-items-center rounded-full bg-ink font-mono text-sm font-bold text-paper">
                {index + 1}
              </div>
              <div>
                <div className="font-bold">{title}</div>
                <p className="mt-1 text-sm leading-relaxed text-muted">{description}</p>
              </div>
            </li>
          ))}
        </ol>
        <div className="mt-6 flex flex-col gap-3 border-t border-ink/12 pt-5 sm:flex-row sm:justify-end">
          <Button type="button" variant="secondary" onClick={onStartWithUpload}>
            <FileArrowUp size={18} weight="bold" />
            {t.startWithUpload}
          </Button>
          <Button type="button" onClick={onViewCurrentJob}>
            <TerminalWindow size={18} weight="bold" />
            {t.viewCurrentJob}
          </Button>
        </div>
      </div>
    </div>
  );
}

function StatusPill({ status, tone }: { status: JobStatus; tone: ReturnType<typeof statusTone> }) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-2 rounded-full border px-3 py-1 font-mono text-xs font-bold uppercase tracking-[0.14em]",
        tone === "running" && "border-info/35 bg-info/10 text-info",
        tone === "failed" && "border-danger/35 bg-danger/10 text-danger",
        tone === "completed" && "border-success/35 bg-success/10 text-success",
        tone === "prepared" && "border-clay/35 bg-clay/10 text-clay",
        tone === "idle" && "border-ink/15 bg-surface text-muted",
      )}
    >
      <span className={cn("size-2 rounded-full", tone === "running" ? "animate-pulse bg-info" : "bg-current")} />
      {status}
    </span>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="min-w-0 border-l border-ink/12 pl-3">
      <div className="font-mono text-[0.66rem] uppercase tracking-[0.16em] text-muted">{label}</div>
      <div className="mt-1 truncate text-sm font-bold text-ink">{value}</div>
    </div>
  );
}

function NoticeBar({ notice }: { notice: NonNullable<Notice> }) {
  return (
    <div
      className={cn(
        "mt-4 rounded-2xl border px-3 py-2 text-sm",
        notice.kind === "error" && "border-danger/35 bg-danger/8 text-danger",
        notice.kind === "success" && "border-success/35 bg-success/8 text-success",
        notice.kind === "info" && "border-info/30 bg-info/8 text-info",
      )}
    >
      {notice.text}
    </div>
  );
}

function Field({ label, helper, children }: { label: string; helper?: string; children: React.ReactNode }) {
  return (
    <label className="block">
      <span className="mb-2 block font-mono text-[0.68rem] font-bold uppercase tracking-[0.14em] text-muted">{label}</span>
      {children}
      {helper ? <span className="mt-2 block text-xs leading-relaxed text-muted">{helper}</span> : null}
    </label>
  );
}

function Input({ className, ...props }: React.InputHTMLAttributes<HTMLInputElement>) {
  return (
    <input
      className={cn(
        "w-full rounded-xl border border-ink/14 bg-surface px-3 py-2.5 text-sm text-ink outline-none transition placeholder:text-muted focus:border-clay focus:ring-2 focus:ring-clay/20",
        className,
      )}
      {...props}
    />
  );
}

function Select({ className, children, ...props }: React.SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <div className="relative">
      <select
        className={cn(
          "w-full appearance-none rounded-xl border border-ink/14 bg-surface px-3 py-2.5 pr-10 text-sm text-ink outline-none transition focus:border-clay focus:ring-2 focus:ring-clay/20",
          className,
        )}
        {...props}
      >
        {children}
      </select>
      <CaretRight size={17} className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 rotate-90 text-muted" weight="bold" />
    </div>
  );
}

function Button({
  variant = "primary",
  className,
  children,
  ...props
}: React.ButtonHTMLAttributes<HTMLButtonElement> & { variant?: "primary" | "secondary" | "ghost" }) {
  return (
    <button
      className={cn(
        "inline-flex min-h-11 items-center justify-center gap-2 rounded-xl px-4 py-2.5 text-sm font-bold transition duration-200 active:translate-y-px disabled:pointer-events-none disabled:opacity-50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-clay",
        variant === "primary" && "bg-ink text-paper shadow-action hover:-translate-y-0.5 hover:bg-ink-soft",
        variant === "secondary" && "border border-clay/45 bg-clay text-paper shadow-action hover:-translate-y-0.5 hover:bg-clay-dark",
        variant === "ghost" && "border border-ink/15 bg-surface/70 text-ink hover:-translate-y-0.5 hover:bg-surface",
        className,
      )}
      {...props}
    >
      {children}
    </button>
  );
}

export default App;
