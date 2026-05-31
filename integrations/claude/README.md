# Claude Desktop Integration

Babel ships a small stdio MCP server so Claude can prepare ebook translation jobs, update the glossary, start translation, and check job status through local tools.

## Install

From the Babel repository:

```bash
python3 -m pip install -e .
```

## Claude Desktop Config

Add an entry like this to your Claude Desktop MCP config:

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

See `claude_desktop_config.example.json`.

## Tools

- `prepare_epub`
- `start_translation`
- `job_status`
- `update_glossary`

The MCP server is local-first. Book content and translated outputs remain in `BABEL_DATA_DIR`. EPUB is handled directly; TXT/HTML are converted internally; MOBI/AZW/PDF/DOCX/CBZ and similar formats require Calibre `ebook-convert`.
