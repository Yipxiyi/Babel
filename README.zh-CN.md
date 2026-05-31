<p align="center">
  <img src="docs/assets/brand/babel-icon.svg" alt="Babel icon" width="116" height="116">
</p>

<h1 align="center">Babel</h1>

<p align="center">
  面向 agent 工作流的 EPUB 翻译工具：尽量保留原书结构、排版和阅读体验。
</p>

<p align="center">
  <strong>解包 EPUB。保留 XHTML。分批翻译。严格校验。重新打包。</strong>
</p>

<p align="center">
  <a href="README.md">English</a> | 简体中文
</p>

---

Babel 会把电子书转成结构化翻译批次，在译文 XHTML 片段通过校验后，再重建为有效 EPUB。

它适合这样的工作流：主 agent 维护全局 glossary 和上下文账本，Codex/subagent 并发处理章节批次。核心管线不绑定具体模型；Web/job 层可以调用用户自配置的 OpenAI-compatible endpoint 或 Anthropic Claude。

## 为什么需要 Babel

很多电子书翻译脚本会把书拍平成纯文本，直接毁掉 CSS、章节、链接、锚点、图片、目录和强调格式。Babel 会先把输入规范化为 EPUB，再直接处理 EPUB 内部结构：

- 保留章节文件、spine 顺序、CSS、图片、链接、锚点、ID 和行内强调。
- 只抽取 XHTML 中人类可读的文本块，生成 JSONL 批次。
- 翻译前生成 glossary 脚手架和 worker 指令。
- 每个翻译批次必须先通过校验，才能回写。
- 拒绝 `第 N 段译文` 这类假翻译/占位文本。
- 按 EPUB 要求将 `mimetype` 作为第一个文件且不压缩。
- 审计输出 EPUB 的 manifest、内部链接和锚点。

## 支持的输入格式

Babel 统一输出 EPUB。输入格式按保真度分层：

- 原生支持：`.epub`。
- 内置转换：`.txt`、`.html`、`.htm`、`.xhtml`。
- 基于 Calibre 转换：`.mobi`、`.azw`、`.azw3`、`.kfx`、`.pdf`、`.fb2`、`.docx`、`.rtf`、`.cbz`、`.cbr`，以及 `ebook-convert` 支持的相关格式。

EPUB 的保真度最高，因为 Babel 能直接处理原有 XHTML 结构。其他格式会先转换为 EPUB，再进入同一套校验和回写管线。

## 当前状态

Babel 仍处于早期阶段，但已经可用。当前包含无运行时依赖的 CLI core、自部署 Web UI、Docker 部署、Codex skill 和 Claude MCP server。

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

Web UI 支持上传电子书、查看/编辑 glossary、配置 API provider、查看进度，并下载翻译后的 EPUB 和报告。

Docker 镜像内置 Calibre，可处理 MOBI/AZW3/PDF/DOCX/CBZ 等转换型格式，并把私有任务数据保存在 `babel-data` volume 中。不要在没有认证保护的情况下把这个服务暴露到公网。

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

```bash
babel-server --host 127.0.0.1 --port 7860 --data-dir ./babel-data
```

打开 `http://127.0.0.1:7860`。

MVP 支持的 provider：

- `OpenAI Compatible`：任何兼容 `/v1/chat/completions` 的 endpoint。
- `Anthropic Claude`：Anthropic Messages API。
- `Fake Dry Run`：本地确定性输出，用来测试管线，不消耗 tokens。

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

TXT/HTML 不需要外部工具。MOBI/AZW/PDF/DOCX/CBZ 等格式需要 Calibre `ebook-convert`；使用 Docker 镜像时已内置。

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

回写译文并重建 EPUB：

```bash
babel-epub apply \
  --work-dir ./babel_work/book \
  --output-epub ./output_zh-CN.epub \
  --title "Translated Title" \
  --language zh-CN
```

审计成品 EPUB：

```bash
babel-epub audit \
  --epub ./output_zh-CN.epub \
  --out ./babel_work/book/pipeline/epub_audit.json
```

生成报告：

```bash
babel-epub report \
  --work-dir ./babel_work/book \
  --output-epub ./output_zh-CN.epub \
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
9. 最后扫描输出 EPUB，检查占位符和异常长英文残留。

更多并发 agent 细节见 [docs/CODEX_WORKFLOW.md](docs/CODEX_WORKFLOW.md)。

## Codex Skill

复制 skill 文件即可安装：

```bash
mkdir -p ~/.codex/skills/babel
cp integrations/codex/babel/SKILL.md ~/.codex/skills/babel/SKILL.md
```

之后可以让 Codex 使用 Babel 翻译电子书。这个 skill 会引导 Codex 使用本地 CLI/Web 工作流，并强制 glossary、上下文、校验和 EPUB 结构保留规则。

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
docker compose config  # 可选，需要本机安装 Docker
```

## License

MIT. See [LICENSE](LICENSE).
