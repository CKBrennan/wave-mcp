# wave-mcp

MCP server for **WAVE** — World Bank development data joined with Overtone media-quality intelligence.

WAVE pairs:
- **World Bank Data360** indicators (health, gender, economy, education, climate, etc.)
- **Overtone** real-time news annotations (tone, source quality, misinformation flags, concept extraction)

so that agents can answer questions like *"how does HIV prevalence in Southern Africa compare with how the topic is covered in flagged vs clean news?"* in a single conversation.

## Install

```bash
uvx --from git+https://github.com/overtone-ai/frontend_appengine.git@wave-mcp#subdirectory=wave-mcp wave-mcp
```

Or in your `claude_desktop_config.json` / Claude Code MCP config:

```json
{
  "mcpServers": {
    "wave": {
      "command": "uvx",
      "args": [
        "--from",
        "git+https://github.com/overtone-ai/frontend_appengine.git@wave-mcp#subdirectory=wave-mcp",
        "wave-mcp"
      ]
    }
  }
}
```

A free-tier API key is provisioned automatically on first use and cached at `~/.wave/credentials`.

## Tools

| Tool | Use case |
|---|---|
| `wb_search_indicators` | Find World Bank indicators by natural-language topic |
| `wb_get_filters` | Get valid countries + year bounds for an indicator |
| `wb_get_data` | Fetch observations for a specific indicator + countries + year range |
| `media_signals` | Aggregate tone + article counts for a topic over time |
| `media_search_articles` | Fetch the most relevant recent articles for a topic |
| `media_articles` | Flagged articles by signal type (conspiracy/clickbait/brand-safety) |
| `media_quality` | Source profiles + concept-gap analysis combined |
| `media_hopeful` | Retrieve the most hopeful/happy high-depth coverage |
| `media_article_forensics` | Inspect one article with paragraph-level labels + flags |
| `media_narrative_brief` | Synthesize the dominant narratives across top articles |
| `media_article_summary` | Summarize one article through the active research lens |
| `build_chart_spec` | Natural-language → Chart.js spec JSON (let your own renderer draw it) |
| `explain_visualization` | Explain a chart spike or the relationship between charts |

## Configuration

| Env var | Purpose |
|---|---|
| `WAVE_API_URL` | Override the API base URL (default `https://worldbank.overtone.ai`) |
| `WAVE_API_KEY` | Override the auto-provisioned key (paid-tier keys, CI, etc.) |

## License

MIT
