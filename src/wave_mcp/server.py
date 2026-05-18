"""WAVE MCP server.

Exposes the WAVE backend (World Bank development indicators + Overtone media
intelligence) as MCP tools. Auto-registers a free-tier API key on first use
and caches it at ~/.wave/credentials so the MCP server and the matching
Claude skill share credentials.

Tools:
  wb_search_indicators  — find World Bank indicators by natural-language topic
  wb_get_data           — fetch observations for a specific indicator
  media_signals         — aggregated tone + article volume for a topic
  media_articles        — flagged articles by signal type (conspiracy/clickbait/brandsafety)
  media_quality         — combined source profiles + concept-gap analysis
  build_chart_spec      — natural-language → Chart.js spec JSON
"""

from __future__ import annotations

import getpass
import hashlib
import os
import platform
import socket
import subprocess
from pathlib import Path
from typing import Annotated, Any, Literal

import httpx
from mcp.server.fastmcp import FastMCP
from pydantic import Field

API_URL = os.environ.get(
    "WAVE_API_URL",
    "https://worldbank.overtone.ai",
)
# Fallback if the custom domain isn't routing yet
API_URL_FALLBACK = "https://wave-dot-overtone-dev.uc.r.appspot.com"

CREDS_FILE = Path.home() / ".wave" / "credentials"
HTTP_TIMEOUT = 30.0

mcp = FastMCP("wave")


# ── Auth helpers ──────────────────────────────────────────────────────


def _machine_id() -> str:
    raw = f"{socket.gethostname()}-{getpass.getuser()}-{platform.machine()}"
    return hashlib.sha256(raw.encode()).hexdigest()


def _git_identity() -> tuple[str | None, str | None]:
    try:
        name = subprocess.check_output(
            ["git", "config", "--global", "user.name"], text=True, timeout=3
        ).strip() or None
    except Exception:
        name = None
    try:
        email = subprocess.check_output(
            ["git", "config", "--global", "user.email"], text=True, timeout=3
        ).strip() or None
    except Exception:
        email = None
    return name, email


def _save_creds(api_key: str, tier: str) -> None:
    CREDS_FILE.parent.mkdir(parents=True, exist_ok=True)
    CREDS_FILE.write_text(f"api_key={api_key}\ntier={tier}\n")
    try:
        CREDS_FILE.chmod(0o600)
    except OSError:
        pass


def _register(base_url: str) -> str:
    username, email = _git_identity()
    with httpx.Client(timeout=HTTP_TIMEOUT) as client:
        resp = client.post(
            f"{base_url}/register",
            json={
                "machine_id": _machine_id(),
                "github_username": username,
                "github_email": email,
            },
        )
        resp.raise_for_status()
        data = resp.json()
    api_key = data.get("api_key")
    if not api_key:
        raise RuntimeError("WAVE /register returned no api_key")
    _save_creds(api_key, data.get("tier", "free"))
    return api_key


def _load_api_key(base_url: str) -> str:
    env_key = os.environ.get("WAVE_API_KEY")
    if env_key:
        return env_key
    if CREDS_FILE.exists():
        for line in CREDS_FILE.read_text().splitlines():
            if line.startswith("api_key="):
                return line.split("=", 1)[1].strip()
    return _register(base_url)


# ── HTTP wrapper ──────────────────────────────────────────────────────


def _request(method: str, path: str, **kwargs) -> Any:
    """Issue an authenticated request; on first call, register a key.

    Tries the primary API_URL; on connection failure falls back to the
    direct App Engine URL.
    """
    for base_url in (API_URL, API_URL_FALLBACK):
        api_key = _load_api_key(base_url)
        headers = {"Authorization": f"Bearer {api_key}", **kwargs.pop("headers", {})}
        try:
            with httpx.Client(timeout=HTTP_TIMEOUT) as client:
                resp = client.request(method, f"{base_url}{path}", headers=headers, **kwargs)
        except httpx.RequestError:
            if base_url == API_URL_FALLBACK:
                raise
            continue
        if resp.status_code == 401:
            # Stale key — wipe and re-register once
            if CREDS_FILE.exists():
                CREDS_FILE.unlink()
            api_key = _register(base_url)
            headers["Authorization"] = f"Bearer {api_key}"
            with httpx.Client(timeout=HTTP_TIMEOUT) as client:
                resp = client.request(method, f"{base_url}{path}", headers=headers, **kwargs)
        if resp.status_code == 404 and base_url == API_URL:
            # Custom domain may not be routing yet — try fallback
            continue
        resp.raise_for_status()
        return resp.json()
    raise RuntimeError("WAVE API unreachable")


# ── MCP tools ─────────────────────────────────────────────────────────


@mcp.tool()
def wb_search_indicators(
    query: Annotated[
        str,
        Field(
            description=(
                "Natural-language question about a development topic — e.g. "
                "'female labor force participation in Southeast Asia 2010-2022' "
                "or 'HIV prevalence in Africa'. WAVE will pick the right World "
                "Bank topic and return matching indicators."
            )
        ),
    ],
) -> dict[str, Any]:
    """Search World Bank indicators by natural-language topic.

    Returns the resolved World Bank topic, matching Overtone media category,
    extracted geography/year hints, and up to 20 candidate indicators with
    their IDs and names. Use the indicator_id from this result to call
    wb_get_data.
    """
    return _request("POST", "/api/query", json={"message": query})


@mcp.tool()
def wb_get_data(
    indicator_id: Annotated[
        str,
        Field(description="The indicator ID returned by wb_search_indicators (e.g. 'WB_HNP_SH_DYN_AIDS_DH')."),
    ],
    ref_area: Annotated[
        str | None,
        Field(description="ISO 3-letter country code (e.g. 'KEN', 'BRA'). Omit for all countries.", default=None),
    ] = None,
    from_year: Annotated[
        str | None,
        Field(description="Earliest year (inclusive), e.g. '2010'. Omit for the full range.", default=None),
    ] = None,
    to_year: Annotated[
        str | None,
        Field(description="Latest year (inclusive), e.g. '2022'. Omit for the full range.", default=None),
    ] = None,
) -> dict[str, Any]:
    """Fetch World Bank observations for a single indicator.

    Returns time-period rows with obs_value, plus indicator metadata
    (name, unit, definition). Pair with media_signals for the same
    geography/period to compare data against media coverage.
    """
    params = {"indicatorId": indicator_id}
    if ref_area:
        params["refArea"] = ref_area
    if from_year:
        params["fromYear"] = from_year
    if to_year:
        params["toYear"] = to_year
    return _request("GET", "/api/wb/data", params=params)


@mcp.tool()
def media_signals(
    overtone_category: Annotated[
        str,
        Field(description="Overtone news category (e.g. 'news/Health', 'news/Business'). Use the value returned by wb_search_indicators."),
    ],
    from_month: Annotated[
        str | None,
        Field(description="Earliest month (YYYY-MM). Defaults to last 3 months.", default=None),
    ] = None,
    to_month: Annotated[
        str | None,
        Field(description="Latest month (YYYY-MM). Defaults to the present.", default=None),
    ] = None,
    keywords: Annotated[
        list[str] | None,
        Field(description="Optional keyword filters that must appear in article headline or concept tags.", default=None),
    ] = None,
) -> list[dict[str, Any]]:
    """Aggregate daily tone + article counts for a topic.

    Returns one row per day in the date range with article_count, type
    breakdown (news/opinion/feature/other), and tone averages
    (happy_avg, angry_avg, fearful_avg, sad_avg, hopeful_avg, informational_avg).
    Use this to chart sentiment trajectories or spot escalation events.
    """
    params: dict[str, Any] = {"overtoneCategory": overtone_category}
    if from_month:
        params["fromMonth"] = from_month
    if to_month:
        params["toMonth"] = to_month
    if keywords:
        params["keywords"] = keywords
    return _request("GET", "/api/media/signals", params=params)


@mcp.tool()
def media_articles(
    overtone_category: Annotated[
        str,
        Field(description="Overtone news category to scope the search."),
    ],
    signal_type: Annotated[
        Literal["conspiracy", "clickbait", "brandsafety_high", "brandsafety_medium"],
        Field(description="Which low-quality signal to filter by."),
    ],
    limit: Annotated[
        int,
        Field(description="Maximum number of articles to return.", default=15, ge=1, le=100),
    ] = 15,
    from_month: Annotated[
        str | None,
        Field(description="Earliest month (YYYY-MM). Defaults to last 3 months.", default=None),
    ] = None,
    to_month: Annotated[
        str | None,
        Field(description="Latest month (YYYY-MM).", default=None),
    ] = None,
    keywords: Annotated[
        list[str] | None,
        Field(description="Optional keyword filters.", default=None),
    ] = None,
) -> list[dict[str, Any]]:
    """Fetch articles flagged with a specific misinformation/quality signal.

    Returns headlines, source, date, URL, and per-article flag context.
    Useful for journalists investigating low-quality coverage of a topic.
    """
    params: dict[str, Any] = {
        "overtoneCategory": overtone_category,
        "signalType": signal_type,
        "limit": limit,
    }
    if from_month:
        params["fromMonth"] = from_month
    if to_month:
        params["toMonth"] = to_month
    if keywords:
        params["keywords"] = keywords
    return _request("GET", "/api/media/flagged", params=params)


@mcp.tool()
def media_quality(
    overtone_category: Annotated[
        str,
        Field(description="Overtone news category to analyse."),
    ],
    source_limit: Annotated[
        int,
        Field(description="Number of top sources to profile.", default=15, ge=1, le=100),
    ] = 15,
    top_concepts: Annotated[
        int,
        Field(description="Top N concepts to compare between flagged and clean coverage.", default=12, ge=1, le=50),
    ] = 12,
    from_month: Annotated[
        str | None,
        Field(description="Earliest month (YYYY-MM).", default=None),
    ] = None,
    to_month: Annotated[
        str | None,
        Field(description="Latest month (YYYY-MM).", default=None),
    ] = None,
    keywords: Annotated[
        list[str] | None,
        Field(description="Optional keyword filters.", default=None),
    ] = None,
) -> dict[str, Any]:
    """Combined source profiles + concept-gap analysis for a topic.

    Returns:
      sources: per-source aggregates (article_count, flagged_pct,
        bs_high_pct, informational_avg, etc.)
      concepts: { flagged: [...], clean: [...] } showing which concepts
        appear disproportionately in flagged vs clean coverage.

    Use this to identify which outlets push narrative manipulation
    and which framings differentiate quality coverage.
    """
    params: dict[str, Any] = {
        "overtoneCategory": overtone_category,
        "limit": source_limit,
        "topN": top_concepts,
    }
    if from_month:
        params["fromMonth"] = from_month
    if to_month:
        params["toMonth"] = to_month
    if keywords:
        params["keywords"] = keywords

    sources = _request("GET", "/api/media/sources", params={k: v for k, v in params.items() if k != "topN"})
    concepts = _request("GET", "/api/media/concepts", params={k: v for k, v in params.items() if k != "limit"})
    return {"sources": sources, "concepts": concepts}


@mcp.tool()
def build_chart_spec(
    request: Annotated[
        str,
        Field(description="Natural-language description of the chart you want — e.g. 'GDP for KEN and ZAF as a line chart 2000-2022' or 'pie chart of article types in Politics'."),
    ],
    context: Annotated[
        dict[str, Any] | None,
        Field(description="Optional active filters to inherit: indicatorId, refAreas, fromYear, toYear, overtoneCategory, keywords.", default=None),
    ] = None,
) -> dict[str, Any]:
    """Produce a Chart.js-compatible spec JSON from a natural-language request.

    Returns { type, title, description, dataSource, params, plot } that
    downstream renderers (Claude, the WAVE web app, your own client)
    can use directly. Supports 8 chart types across 6 data sources
    (line, area, stackedArea, bar, stackedBar, groupedBar, horizontalBar,
    pie, doughnut).
    """
    return _request(
        "POST",
        "/api/visualize/build",
        json={"message": request, "context": context or {}, "history": []},
    )
