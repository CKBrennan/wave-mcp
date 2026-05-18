# wave-mcp

MCP server for **WAVE** — World Bank development data joined with Overtone media-quality intelligence.

WAVE pairs:
- **World Bank Data360** indicators (health, gender, economy, education, climate, etc.)
- **Overtone** real-time news annotations (tone, source quality, misinformation flags, concept extraction)

so that agents can answer questions like *"how does HIV prevalence in Southern Africa compare with how the topic is covered in flagged vs clean news?"* in a single conversation.

## Install

```bash
uvx wave-mcp
```

Or in your `claude_desktop_config.json` / Claude Code MCP config:

```json
{
  "mcpServers": {
    "wave": {
      "command": "uvx",
      "args": ["wave-mcp"]
    }
  }
}
```

A free-tier API key is provisioned automatically on first use and cached at `~/.wave/credentials`.

## Tools

| Tool | Use case |
|---|---|
| `wb_search_indicators` | Find World Bank indicators by natural-language topic |
| `wb_get_data` | Fetch observations for a specific indicator + countries + year range |
| `media_signals` | Aggregate tone + article counts for a topic over time |
| `media_articles` | Flagged articles by signal type (conspiracy/clickbait/brand-safety) |
| `media_quality` | Source profiles + concept-gap analysis combined |
| `build_chart_spec` | Natural-language → Chart.js spec JSON (let your own renderer draw it) |

## Configuration

| Env var | Purpose |
|---|---|
| `WAVE_API_URL` | Override the API base URL (default `https://worldbank.overtone.ai`) |
| `WAVE_API_KEY` | Override the auto-provisioned key (paid-tier keys, CI, etc.) |

## License

MIT
