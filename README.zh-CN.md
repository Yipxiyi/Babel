<p align="center">
  <img src="docs/assets/brand/babel-icon.png" alt="Babel icon" width="116" height="116">
</p>

<h1 align="center">Babel</h1>

<p align="center">
  面向 agent 工作流的 EPUB 翻译工具：尽量保留原书结构、排版和阅读体验。
</p>

<p align="center">
  <strong>规范化为 EPUB。保留 XHTML。分批翻译。自选输出格式。</strong>
</p>

<p align="center">
  <a href="README.md">English</a> | 简体中文
</p>

---

Babel 会把电子书转成结构化翻译批次，在译文 XHTML 片段通过校验后，先重建有效 EPUB 中间件，再导出用户选择的最终格式。

它适合这样的工作流：主 agent 维护全局 glossary 和上下文账本，Codex/subagent 并发处理章节批次。自部署 Web/job runtime 也可以自动并发调用 provider 翻译批次。核心管线不绑定具体模型；Web/job 层可以调用用户自配置的 OpenAI-compatible endpoint 或 Anthropic Claude。

## 为什么需要 Babel

很多电子书翻译脚本会把书拍平成纯文本，直接毁掉 CSS、章节、链接、锚点、图片、目录和强调格式。Babel 会先把输入规范化为 EPUB，再直接处理 EPUB 内部结构：

- 保留章节文件、spine 顺序、CSS、图片、链接、锚点、ID 和行内强调。
- 只抽取 XHTML 中人类可读的文本块，生成 JSONL 批次。
- 翻译前生成 glossary 脚手架；可选用 glossary preset 预置已知人名/术语决策；并生成 worker 指令。
- 每个翻译批次必须先通过校验，才能回写。
- Web 翻译支持可配置批次并发、请求超时、重试和失败任务继续。
- 拒绝 `第 N 段译文` 这类假翻译/占位文本。
- 按 EPUB 要求重建经过校验的 EPUB 中间件，且将 `mimetype` 作为第一个文件并保持不压缩。
- 将最终译本导出为 EPUB 或基于 Calibre 的目标格式。
- 审计输出 EPUB 的 manifest、内部链接和锚点。

## 支持的输入格式

Babel 会先把所有输入规范化为 EPUB 工作区，再进入翻译流程。输入格式按保真度分层：

- 原生支持：`.epub`。
- 内置转换：`.txt`、`.html`、`.htm`、`.xhtml`。
- 基于 Calibre 转换：`.mobi`、`.azw`、`.azw3`、`.kfx`、`.pdf`、`.fb2`、`.docx`、`.rtf`、`.cbz`、`.cbr`，以及 `ebook-convert` 支持的相关格式。

EPUB 的保真度最高，因为 Babel 能直接处理原有 XHTML 结构。其他格式会先转换为 EPUB，再进入同一套校验和回写管线。

## 支持的输出格式

- 原生支持：`.epub`。
- 基于 Calibre 导出：`.mobi`、`.azw3`、`.pdf`、`.docx`、`.txt`、`.html`、`.htmlz`、`.kepub`、`.rtf`、`.fb2`。

EPUB 输出不需要外部工具。非 EPUB 输出会从校验后的 EPUB 中间件导出，需要 Calibre `ebook-convert`；使用 Docker 镜像时已内置。

`--output-epub` 仍然作为兼容别名保留，但新流程建议使用 `--output-book` 加 `--output-format`。

`--output-book` 路径必须带上所选扩展名，例如 `--output-format pdf` 对应 `output_zh-CN.pdf`。

## 当前状态

Babel 仍处于早期阶段，但已经可用。当前包含无运行时依赖的 CLI core、React/Vite 自部署 Web UI、Docker 部署、Codex skill 和 Claude MCP server。

## 最简单方式：Docker Web UI

```bash
git clone https://github.com/Yipxiyi/Babel.git
cd Babel
docker compose up --build
```

打开：

```txt
http://127.0.0.1:7860
```

Web UI 支持上传电子书、选择最终输出格式、查看/编辑 glossary、在术语表弹窗中导入/导出术语、配置 API provider、选择并发/超时/重试设置、查看终端式进度、失败后继续任务，并下载翻译后的电子书和报告。

右上角 `Guide` 按钮会弹出推荐操作流程。语言切换支持英文和简体中文，并会保存到 `localStorage`。

Docker 镜像内置 Calibre，可处理 MOBI/AZW3/PDF/DOCX/CBZ 等输入转换和非 EPUB 输出导出，并把私有任务数据保存在 `babel-data` volume 中。不要在没有 `BABEL_WEB_TOKEN`、HTTPS 或其他可信认证层保护的情况下把这个服务暴露到公网。Web 上传默认限制为 200 MB，可通过 `BABEL_MAX_UPLOAD_MB` 调整。

## 从源码安装

```bash
git clone https://github.com/Yipxiyi/Babel.git
cd Babel
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -e .
```

验证 CLI：

```bash
babel-epub --help
babel-server --help
python3 -m unittest discover -s tests -v
```

## 从源码启动 Web UI

先把 React UI 构建到 Python 包的静态目录：

```bash
npm install --prefix web
npm test --prefix web
npm run build --prefix web
```

启动内置 Web UI：

```bash
babel-server --host 127.0.0.1 --port 7860 --data-dir ./babel-data
```

打开 `http://127.0.0.1:7860`。

前端开发时，可以分别启动后端和 Vite dev server：

```bash
babel-server --host 127.0.0.1 --port 7860 --data-dir ./babel-data
npm run dev --prefix web
```

Vite 运行在 `http://127.0.0.1:5173`，并把 `/api` 代理到本地 Babel server。

MVP 支持的 provider：

- `OpenAI Compatible`：任何兼容 `/v1/chat/completions` 的 endpoint。
- `Anthropic Claude`：Anthropic Messages API。
- `Fake Dry Run`：本地确定性输出，用来测试管线，不消耗 tokens。

OpenAI-compatible provider 可通过 Web 设置里的 `结构化 JSON 输出` 或 MCP 的 `structured_output_enabled` 字段请求 JSON Schema 响应。Anthropic 仍使用 prompt 约束；返回文本仍会交给 Babel 的宽容解析器兜底。

翻译记忆库可在 Web 设置中开启，也可通过 MCP 传入 `memory_enabled` 和稳定的 `memory_project_id`。Babel 会把完全匹配的源文片段存到 `BABEL_DATA_DIR/translation_memory/<project>.json`，每次命中仍会按当前 source row 做结构校验；有效命中会跳过 provider 调用，成功译文会写回项目记忆库。

质量报告会把 locked glossary 修复和确定性 QA 汇总到一起，包含未翻译比例、长段源文残留、标点/引号漂移、人名漂移和按章节聚合的问题。Web 校验面板会展示摘要，完整 JSON 可通过 `AI QA JSON` 下载。

运行参数：

- `Concurrency`：默认 `3`，后端强制限制为 `1..8`。
- `Request timeout`：默认 `300` 秒。
- `Retries`：默认 `1`；仅 timeout、HTTP 429、HTTP 5xx 会重试。HTTP 400/401 不会重试。
- 单个批次失败后，其他批次会继续执行。所有 worker 结束后，如果仍有失败批次，点击 `Resume Translation` 只重跑缺失、损坏或未通过校验的批次。

安全与上传控制：

- `BABEL_WEB_TOKEN`：可选的 API bearer token，启用后所有 `/api/*` 路由和下载接口都必须携带 `Authorization: Bearer <token>` 或 `X-Babel-Token: <token>`。该 token 不会出现在 `/api/meta` 或 provider settings 响应中。
- `BABEL_MAX_UPLOAD_MB`：上传大小上限，单位 MB，默认 `200`。超限请求会在 multipart 解析前返回 HTTP 413。
- `BABEL_CONVERSION_TIMEOUT`：Calibre `ebook-convert` 转换超时，单位秒，用于需要转换的输入或输出，默认 `600`。

## CLI 快速开始

从电子书准备私有工作目录：

```bash
babel-epub prepare \
  --input-book ./input.epub \
  --work-dir ./babel_work/book \
  --glossary ./translation_glossary.md \
  --target-language "Simplified Chinese" \
  --max-blocks 120
```

可加 `--glossary-preset edge-chronicles` 使用内置 Edge Chronicles 词表 preset，也可以传入兼容 JSON preset 的文件路径。不传 preset 时，Babel 会保持通用抽取，只把项目专有词留给人工 review。

`prepare` 可加 `--max-chars` 或 `--max-tokens`，在旧的 `--max-blocks` 块数上限之外按近似源文大小切分批次，避免长段落让 provider prompt 超出上下文。

如果需要在 Web UI 之外管理翻译记忆库，可使用 CLI 导入、导出或查看统计：

```bash
babel-epub memory stats --project-id my-series --data-dir ./babel-data
babel-epub memory export --project-id my-series --data-dir ./babel-data --file ./my-series-memory.json
babel-epub memory import --project-id my-series --data-dir ./babel-data --file ./my-series-memory.json
```

结构化术语库也可以用 CSV、TBX、Markdown preset 或 JSON 导入/导出。导入会保留 `approved` / `pending` / `ignored` 状态和 `locked` 决策，并重新生成 worker 使用的紧凑 Markdown prompt：

```bash
babel-epub import-glossary --work-dir ./babel_work/book --file ./glossary.csv --mode upsert
babel-epub export-glossary --work-dir ./babel_work/book --file ./glossary.tbx
```

Babel 会生成：

```txt
babel_work/book/
  source/                    # 解包后的 EPUB 目录，私有
  pipeline/
    blocks.jsonl             # 所有可翻译 XHTML 块
    batches/                 # 翻译输入批次
    translated/              # 翻译输出批次放这里
    batch_manifest.json
    chapters.json
    name_candidates.json
    translation_context.md
    WORKER_INSTRUCTIONS.md
translation_glossary.md
```

非 EPUB 输入示例：

```bash
babel-epub prepare --input-book ./input.azw3 --work-dir ./babel_work/book
```

TXT/HTML 不需要外部工具。MOBI/AZW/PDF/DOCX/CBZ 等格式需要 Calibre `ebook-convert`；使用 Docker 镜像时已内置。可用 `--conversion-timeout` 或 `BABEL_CONVERSION_TIMEOUT` 限制长时间转换。

每个批次的译文需要写成匹配的 JSONL 行，放入 `pipeline/translated/`。

输入行：

```json
{"id":"OEBPS/chapter1.xhtml::0001","source_html":"<p>Hello <em>world</em>.</p>"}
```

输出行：

```json
{"id":"OEBPS/chapter1.xhtml::0001","translated_html":"<p>你好，<em>世界</em>。</p>"}
```

校验单个批次：

```bash
babel-epub validate-batch \
  --pipeline-dir ./babel_work/book/pipeline \
  --batch batches/batch_001_chapter1_01.jsonl \
  --output translated/batch_001_chapter1_01.translated.jsonl
```

校验全部批次：

```bash
babel-epub validate-batches --pipeline-dir ./babel_work/book/pipeline
```

回写译文并导出 EPUB：

```bash
babel-epub apply \
  --work-dir ./babel_work/book \
  --output-book ./output_zh-CN.epub \
  --output-format epub \
  --title "Translated Title" \
  --language zh-CN
```

导出其他格式，例如 PDF：

```bash
babel-epub apply \
  --work-dir ./babel_work/book \
  --output-book ./output_zh-CN.pdf \
  --output-format pdf \
  --title "Translated Title" \
  --language zh-CN
```

审计校验后的 EPUB 包。若最终输出不是 EPUB，则审计工作目录中的 EPUB 中间件：

```bash
babel-epub audit \
  --epub ./babel_work/book/output.epub \
  --out ./babel_work/book/pipeline/epub_audit.json
```

生成报告：

```bash
babel-epub report \
  --work-dir ./babel_work/book \
  --output-book ./output_zh-CN.epub \
  --glossary ./translation_glossary.md \
  --report ./translation_report.md
```

## 推荐 Agent 工作流

1. 运行 `prepare`。
2. 查看 `name_candidates.json`。
3. 在 `translation_glossary.md` 中固定人名、地名、称呼和术语。
4. 主 agent 维护 `translation_context.md`。
5. 将 `WORKER_INSTRUCTIONS.md`、glossary 和必要上下文发给 batch worker。
6. 要求每个 worker 运行 `validate-batch`。
7. 主 agent 运行 `validate-batches`。
8. 运行 `apply`，再运行 `audit`。
9. 最后扫描最终电子书和 EPUB 中间件，检查占位符和异常长英文残留。

更多并发 agent 细节见 [docs/CODEX_WORKFLOW.md](docs/CODEX_WORKFLOW.md)。

## Codex Skill

复制 skill 文件即可安装：

```bash
mkdir -p ~/.codex/skills/babel
cp integrations/codex/babel/SKILL.md ~/.codex/skills/babel/SKILL.md
```

之后可以让 Codex 使用 Babel 翻译电子书。这个 skill 会引导 Codex 使用本地 CLI/Web 工作流，并强制 glossary、上下文、校验、自选输出格式和 EPUB 结构保留规则。

## Claude Desktop MCP

安装 Babel 后，在 Claude Desktop 的 MCP 配置中加入：

```json
{
  "mcpServers": {
    "babel": {
      "command": "babel-mcp",
      "env": {
        "BABEL_DATA_DIR": "/absolute/path/to/babel-data"
      }
    }
  }
}
```

详见 [integrations/claude](integrations/claude)。

`start_translation` MCP tool 支持可选字段：`resume`、`batch_filter`、`max_concurrency`、`request_timeout`、`max_retries`、`structured_output_enabled`、`memory_enabled`、`memory_project_id`、`memory_path`、`ai_qa_enabled`、`auto_title_enabled`、provider 速率限制和预算/成本字段，默认值与 Web UI 一致。MCP 也提供 `list_jobs`、`artifact_path`、`read_glossary_terms`、`update_glossary_terms`、`import_glossary`、`export_glossary`、`resume_failed_job`、`retry_batch`；`retry_batch` 会清除选中批次的 translated JSONL，并用单批过滤恢复。

## Plugin 还是 Skill？

Babel 有意做成带 CLI/Web/MCP adapter 的独立包，而不是 Codex plugin。

原因很直接：EPUB 抽取、校验和打包是通用能力，应该能被终端、Web server、Docker、CI、Codex、Claude 共同复用。Codex 和 Claude 集成都调用同一套 core，不重复实现 EPUB 逻辑。

## 仓库结构

```txt
src/babel_epub/              # 无运行时依赖的 core、job engine、Web server、MCP server
integrations/codex/babel/    # Codex skill
integrations/claude/         # Claude Desktop MCP 文档/配置
tests/                       # EPUB/job/Web 最小测试
docs/                        # OpenArc 产品、设计、品牌、架构文档
docs/assets/brand/           # 图标和品牌资产
```

## 法律和安全说明

Babel 是格式保留工具，不提供版权授权。请只翻译你拥有、已获授权，或法律允许转换的电子书/文档。不要把私有书籍、译后 EPUB 或生成工作区提交到公开仓库。

默认 `.gitignore` 已排除 `*.epub`、JSONL 批次、生成报告和本地工作目录。如果使用其他私有电子书格式，也应避免提交到 git。

## 开发

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -e .
PYTHONPATH=src python3 -m unittest discover -s tests -v
python3 -m py_compile src/babel_epub/*.py
npm test --prefix web
npm run build --prefix web
docker compose config  # 可选，需要本机安装 Docker
```

## License

MIT. See [LICENSE](LICENSE).
