#!/usr/bin/env python3
"""Fetch, score, and append relevant credit news to data/news.json.

The updater uses free RSS/Atom feeds, keyword scoring, Claude-driven GP/sector
classification and HyDE query generation, optional PyLate/ColBERTv2 MaxSim semantic
scoring (with a Claude relevance-judge fallback), and Claude Simplified Chinese
translation when the configured dependencies and API key are available.
"""

from __future__ import annotations

import argparse
import datetime as dt
import email.utils
import hashlib
import html
import json
import os
import re
import sys
import textwrap
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DATA_PATH = ROOT / "data" / "news.json"
CONFIG_PATH = ROOT / "config" / "news_sources.json"
GOLDEN_CASES_PATH = ROOT / "data" / "golden_cases.json"
SEMANTIC_PROMPT = """{gp_name} is a multi-strategy alternative asset manager. We ONLY track news
related to its credit / lending / structured-finance strategies (e.g. direct
lending, BDCs, CLOs, asset-based finance) — NOT its private equity, infrastructure,
or real estate equity strategies unless those specifically involve credit or
financing activity.

Write 3 short descriptions (1-2 sentences each) of what a credit-relevant news
article about {gp_name} looks like, and 2 short descriptions of what a
NON-relevant article about {gp_name} looks like (e.g. a PE buyout, an
infrastructure asset sale, unrelated corporate news) — so we can distinguish them.

Output format:
RELEVANT:
1. ...
2. ...
3. ...
NOT RELEVANT:
4. ...
5. ...

PRECEDENTIAL NOT RELEVANT CASES:
{bad_history_logs}
"""
CLASSIFICATION_PROMPT = """You are a classification assistant for an investment-news monitoring system.

The portfolio only holds CREDIT-related exposure to the managers below — never
their private equity, infrastructure, or real estate equity strategies unless
those specifically involve lending, financing, or credit activity.

TRACKED GPs:
{gp_list}

(Note: several of these are multi-strategy mega-funds. Only tag a GP if the
article is about its credit / lending / structured-finance business — a
buyout, infra asset sale, or unrelated corporate news about the SAME firm
name must NOT be tagged.)

TRACKED STRATEGIES (answer with the id in brackets):
{strategy_list}

EVENT TYPES (zero or more may apply):
- lawsuit: litigation, settlements, court rulings, regulatory enforcement.
- financing: loans, credit facilities, acquisition financing, securitizations,
  debt issuance, deal closings, portfolio purchases.
- fundraising: new funds, first or final closes, capital raised, fund launches.

TASK:
Read the article below. Determine:
1. Which tracked GP(s), if any, it is about (credit-relevant activity only).
2. Which tracked strategy id(s), if any, it belongs to.
3. Which event type(s) apply (empty list for ordinary corporate news).
4. importance: 0.0-1.0, how much a credit investor tracking these GPs should
   care. 1.0 = lawsuit, default, downgrade, redemption pressure, final close or
   a major transaction; 0.7 = ordinary financing; 0.5 = routine manager news;
   0.15 = stock price / analyst commentary; 0.1 = law-firm investor alerts.
5. Whether it should be EXCLUDED because it's about a tracked GP's non-credit
   business (equity buyout, infrastructure, sports/media assets, etc.) with no
   credit/financing angle, or about an unrelated entity that shares a name
   (e.g. Apollo 11, Pag-IBIG, Canyon cycling).

HERE ARE SOME PRECEDENTIAL WRONG CASES:
{bad_history_logs}

ARTICLE:
Title: {article_title}
Text: {article_body}

Output valid JSON only, with this shape:
{{
  "gps": ["tracked GP name"],
  "strategies": ["strategy-id"],
  "events": ["financing"],
  "importance": 0.5,
  "exclude": false,
  "reason": "short explanation"
}}
"""
TRANSLATION_PROMPT = """Translate the following investment-news summary into Simplified Chinese.

Rules:
- Preserve company names, fund names, ticker symbols, dates, and monetary figures.
- Keep the meaning precise and suitable for a credit investor.
- Do not add facts, interpretation, markdown, labels, or explanations.
- Output only the translated summary.

English summary:
{summary}
"""
TRANSLATION_BUNDLE_PROMPT = """Translate the fields below into Simplified Chinese for a credit-investment news dashboard.

Rules:
- Preserve company names, fund names, ticker symbols, dates, and monetary figures.
- Keep the meaning precise and suitable for a credit investor.
- Do not add facts, interpretation, markdown, labels, or explanations.
- Keep the title concise, like a news headline.
- Output valid JSON only, with exactly this shape:
{{"title": "...", "summary": "...", "reason": "..."}}

Title: {title}
Summary: {summary}
Reason (why this article was selected): {reason}
"""
MISSING_ZH_SUMMARY = "此条目的中文摘要尚未人工整理；请先参考英文摘要与原文链接。"
RELEVANCE_PROMPT = """You are scoring how well a news article matches a credit-investment mandate.

Below are example descriptions of what a RELEVANT article looks like for this
mandate. Rate how closely the ARTICLE matches those examples on a scale from
0.0 to 1.0:
- 1.0: clearly the same kind of credit / lending / structured-finance story.
- 0.5: partially related (mentions the manager or sector, but the credit angle
  is weak or unclear).
- 0.0: unrelated, or about non-credit business (equity buyout, infrastructure,
  real estate equity, unrelated corporate news).

RELEVANT EXAMPLES:
{examples}

ARTICLE:
{document}

Output valid JSON only, with this shape:
{{"score": 0.0, "reason": "short explanation"}}
"""

DEFAULT_CLAUDE_MODEL = "claude-opus-5-5"
DEFAULT_CLAUDE_API_KEY_ENV = "ANTHROPIC_API_KEY"
DEFAULT_CLAUDE_EFFORT = "low"
DEFAULT_CLAUDE_MAX_TOKENS = 16000
REFUSAL_FALLBACK_BETA = "server-side-fallback-2026-07-01"

# Default GP aliases; config/news_sources.json `gpAliases` overrides this map.
GP_ALIASES = {
    "Blue Owl": ["blue owl", "blueowl", "owl rock", "dyal capital", "dyal", "blue owl technology finance", "nyse: otf", " obdc", " ocic", " orcc"],
    "KKR": ["kkr", "kohlberg kravis roberts", "global atlantic", " fsk ", " fsk's", " kref"],
    "CIFC": ["cifc"],
    "PAG": [" pag ", "pag's", "pacific alliance group"],
    "Pretium": ["pretium", "progress residential", "deephaven", "anchor loans", "selene finance", " pret 20"],
    "Guggenheim": ["guggenheim"],
    "Neuberger": ["neuberger berman", "neuberger", " nb private"],
    "BasePoint": ["basepoint"],
    "Bain Capital": ["bain capital", "baincapital", " bcsf"],
    "Blackstone": ["blackstone", "bcred", " bxsl", " bxmt", " bx trust", " bx commercial mortgage"],
    "Apollo": ["apollo global", "apollo management", "apollo asset", "apollo debt", "apollo credit", "apollo's", "apollo ", "athene", "midcap financial", "redding ridge"],
    "TPG": [" tpg ", "tpg inc", "tpg's", "angelo gordon", "tpg angelo", "twin brook", "northwoods capital", "ag mortgage investment trust", " trtx"],
    "Golub": ["golub", " gbdc"],
    "CVC": ["cvc capital", "cvc credit", " cvc ", "cordatus"],
    "Canyon": ["canyon partners", "canyon capital", "canyon clo"],
}

# Saved items tagged with these legacy GP names are remapped on every run.
GP_RENAMES = {"OTF": "Blue Owl", "NB": "Neuberger", "Basepoint": "BasePoint"}

# Strategy taxonomy shared with the dashboard (src/app.js mirrors ids, names and patterns).
STRATEGIES = [
    {"id": "private-credit", "name": "Private Credit", "cn": "私募信贷", "group": "credit",
     "keywords": ["private credit", "private debt", "direct lend", "bdc", "unitranche", "middle market loan", "senior secured loan"],
     "pattern": r"private credit|private debt|direct lend|\bBDCs?\b|unitranche"},
    {"id": "abf", "name": "ABF", "cn": "资产支持融资", "group": "credit",
     "keywords": ["asset-based", "asset based", "asset-backed", "asset backed", " abf ", "abl ", "receivables", "specialty finance", "equipment finance"],
     "pattern": r"asset.based|asset.backed|\bABF\b|\bABL\b|specialty finance|receivables"},
    {"id": "structured", "name": "Structured Credit", "cn": "结构化信贷", "group": "credit",
     "keywords": ["structured credit", "structured finance", "securitization", "securitisation", " abs "],
     "pattern": r"structured credit|structured finance|securiti[sz]|\bABS\b"},
    {"id": "clo", "name": "CLO", "cn": "抵押贷款债券", "group": "credit",
     "keywords": [" clo ", " clos ", "collateralized loan obligation", "collateralised loan obligation"],
     "pattern": r"\bCLOs?\b|collateralized loan obligation|collateralised loan obligation"},
    {"id": "resi", "name": "Resi Credit", "cn": "住宅信贷", "group": "credit",
     "keywords": ["residential credit", "residential mortgage", "rmbs", "mortgage", "housing credit", "home loan", "msr"],
     "pattern": r"residential credit|mortgage|\bRMBS\b|housing credit|home loans?|\bMSRs?\b"},
    {"id": "triple-net", "name": "Triple Net Lease", "cn": "三净租赁", "group": "real-estate",
     "keywords": ["triple net", "triple-net", "net lease", " nnn "],
     "pattern": r"triple.net|net leas|\bNNN\b"},
    {"id": "sfr", "name": "Single Family Rental", "cn": "独栋住宅出租", "group": "real-estate",
     "keywords": ["single family rental", "single-family rental", "build-to-rent", "build to rent", " sfr "],
     "pattern": r"single.family rental|build.to.rent|\bSFR\b"},
    {"id": "cre", "name": "Commercial Real Estate", "cn": "商业地产", "group": "real-estate",
     "keywords": ["commercial real estate", "commercial property", "commercial mortgage", "cmbs", " cre "],
     "pattern": r"commercial real estate|commercial propert|commercial mortgage|\bCMBS\b|\bCRE\b"},
    {"id": "aircraft", "name": "Aircraft Leasing", "cn": "飞机租赁", "group": "hard-asset",
     "keywords": ["aircraft", "aviation", "airline", "airplane", "jet lease"],
     "pattern": r"aircraft|aviation|airplane|airline"},
    {"id": "data-center", "name": "Data Center", "cn": "数据中心", "group": "hard-asset",
     "keywords": ["data center", "data centre", "datacenter", "数据中心"],
     "pattern": r"data cent(?:er|re)s?|datacenters?|数据中心"},
    {"id": "ai", "name": "AI", "cn": "AI 相关", "group": "ai",
     "keywords": [" ai ", "artificial intelligence", "ai infrastructure", "gpu financing", "compute infrastructure", "chip financing", "人工智能", "算力"],
     "pattern": r"\bAI\b|artificial intelligence|GPU financ|compute infrastructure|chip financ|人工智能|算力"},
    {"id": "gp-stakes", "name": "GP Stakes", "cn": "GP 股权", "group": "other",
     "keywords": ["gp stake", "gp stakes", "general partner stake", "dyal", "gp-led", "continuation vehicle"],
     "pattern": r"GP stakes?|general partner.{0,15}stakes?|Dyal"},
]
STRATEGY_GROUPS = [
    {"id": "credit", "name": "Credit", "cn": "信贷"},
    {"id": "real-estate", "name": "Real Estate", "cn": "房地产"},
    {"id": "hard-asset", "name": "Hard Asset", "cn": "实物资产"},
    {"id": "ai", "name": "AI", "cn": "AI 相关"},
    {"id": "other", "name": "Other", "cn": "其他策略"},
]
STRATEGY_IDS = [strategy["id"] for strategy in STRATEGIES]
STRATEGY_KEYWORDS = {strategy["id"]: strategy["keywords"] for strategy in STRATEGIES}
# Legacy sub-sector labels saved by earlier versions map onto the new taxonomy.
LEGACY_SECTOR_MAP = {
    "software": [],
    "private credit / direct lending": ["private-credit"],
    "GP stakes": ["gp-stakes"],
    "aircraft leasing": ["aircraft"],
    "asset-backed lending": ["abf"],
    "real estate": ["cre"],
    "mortgage": ["resi"],
    "CLO": ["clo"],
}

EVENT_IDS = ["lawsuit", "financing", "fundraising"]
EVENT_PATTERNS = {
    "lawsuit": re.compile(r"lawsuit|litigation|\bsue[sd]?\b|settlement|class.action|\bcourt\b|enforcement action", re.IGNORECASE),
    "financing": re.compile(
        r"financ|\bloans?\b|credit facility|acqui|\bbuy\b|securiti[sz]ation|debt issu|"
        r"invest(?:s|ed|ment)?.{0,35}(?:billion|million)|commit.{0,35}(?:billion|million)|refinanc|\bbond\b",
        re.IGNORECASE,
    ),
    "fundraising": re.compile(
        r"final clos|first clos|fund.{0,35}(?:clos|rais)|rais(?:ed|es).{0,40}(?:fund|billion|million)|fundrais|"
        r"target(?:s|ing)?.{0,40}(?:fund|billion|million)|seek(?:s|ing)?.{0,40}(?:rais|fund)|launch.{0,40}fund|new fund",
        re.IGNORECASE,
    ),
}
MAJOR_SIGNAL_PATTERN = re.compile(
    r"final clos|first clos|complet|acqui|\bbillion\b|\bbn\b|default|downgrade|bankrupt|redemption|withdrawal|liquidity crisis|fraud",
    re.IGNORECASE,
)
STOCK_COMMENTARY_PATTERN = re.compile(
    r"price target|stock price|stock market|shares (rise|fall)|buy or sell|dividend|stock rating|analyst rating|"
    r"\bsells? \d|\bbuys? \d|shares of|\bcall \(|\bput \(|stock price, news, quote",
    re.IGNORECASE,
)
SOLICITATION_PATTERN = re.compile(
    r"investor alert|investor reminder|securities class action notice|law firm|deadline alert|reminds investors|"
    r"shareholder alert|investigation alert|investors.*contact|losses.*contact",
    re.IGNORECASE,
)
SOURCE_TIERS = [
    ("tier_top", 1.0, re.compile(r"^(reuters|bloomberg|financial times|ft\.com|the wall street journal|wall street journal|wsj)(\b|$)", re.IGNORECASE)),
    ("tier_filing", 0.9, re.compile(r"\bsec\b|edgar|company filing|morningstar dbrs|\bdbrs\b", re.IGNORECASE)),
    ("tier_trade", 0.8, re.compile(
        r"private debt investor|9fin|creditflux|structured credit investor|pensions & investments|alternative credit investor|"
        r"\bipe\b|aviation week|airfinance|asset securitization report|abl advisor|private credit daily|commercial observer|"
        r"housingwire|abf journal|inside mortgage finance|private equity wire|connect money|mortgage news daily|"
        r"pere|secondaries investor|buyouts|debtwire|lcd|pitchbook|with intelligence", re.IGNORECASE)),
    ("tier_press_release", 0.4, re.compile(r"business wire|pr newswire|globenewswire|newsfile|accesswire", re.IGNORECASE)),
    ("tier_aggregator", 0.25, re.compile(r"seeking alpha|benzinga|tipranks|stock titan|marketbeat|simply wall st|yahoo|motley fool|investing\.com|stocktwits", re.IGNORECASE)),
]
DEFAULT_RATING_WEIGHTS = {"institution": 18, "strategy": 12, "event": 30, "source": 25, "freshness": 15}

REGION_KEYWORDS = {
    "US": ["united states", " u.s.", " us ", "new york", "sec", "nasdaq", "nyse", "wall street"],
    "Europe": [
        "europe",
        "european",
        "uk",
        "u.k.",
        "london",
        "germany",
        "france",
        "italy",
        "spain",
        "ireland",
    ],
}

CREDIT_CONTEXT = [
    "credit",
    "debt",
    "loan",
    "lending",
    "finance",
    "financing",
    "facility",
    "securitization",
    "securitisation",
    "clo",
    "bdc",
    "mortgage",
    "asset-backed",
    "asset based",
]

MONTH_INDEX = {
    "january": 1,
    "jan": 1,
    "february": 2,
    "feb": 2,
    "march": 3,
    "mar": 3,
    "april": 4,
    "apr": 4,
    "may": 5,
    "june": 6,
    "jun": 6,
    "july": 7,
    "jul": 7,
    "august": 8,
    "aug": 8,
    "september": 9,
    "sep": 9,
    "sept": 9,
    "october": 10,
    "oct": 10,
    "november": 11,
    "nov": 11,
    "december": 12,
    "dec": 12,
}
WARNED_KEYS: set[str] = set()


def warn_once(key: str, message: str) -> None:
    if key in WARNED_KEYS:
        return
    WARNED_KEYS.add(key)
    print(message, file=sys.stderr)


def enable_os_trust_store() -> bool:
    """Validate TLS certificates with the operating system's trust store when truststore is installed.

    Corporate proxies re-sign HTTPS traffic with their own root certificate. Python 3.13+
    verifies certificates in strict mode and rejects such roots when they lack the key-usage
    extension ("CA cert does not include key usage extension") even though the OS trusts
    them. truststore delegates validation to the OS (Windows CryptoAPI, macOS Security,
    OpenSSL system store on Linux) so local runs behave like the browser. Set
    NEWS_OS_TRUST_STORE=0 to keep Python's bundled validation.
    """
    if os.environ.get("NEWS_OS_TRUST_STORE", "1").strip().lower() in {"0", "false", "no"}:
        return False
    try:
        import truststore
    except ImportError:
        return False
    truststore.inject_into_ssl()
    print("TLS: validating certificates with the operating system trust store (truststore).", file=sys.stderr)
    return True


def main() -> int:
    enable_os_trust_store()
    parser = argparse.ArgumentParser(description="Update the private-credit news dashboard.")
    parser.add_argument("--date", default=dt.date.today().isoformat(), help="Digest date, YYYY-MM-DD.")
    parser.add_argument("--dry-run", action="store_true", help="Print selected items without writing.")
    parser.add_argument("--recent-days", type=int, help="Fetch, score, and merge only this many recent calendar days.")
    parser.add_argument(
        "--backfill-only",
        action="store_true",
        help="Skip fetching; only migrate saved items to the current GP list, strategy taxonomy, events, and rating parts.",
    )
    args = parser.parse_args()

    if args.backfill_only:
        changed = backfill_saved_data()
        print(f"Backfilled {changed} saved item(s) in {DATA_PATH}")
        return 0

    result = update_news(args.date, dry_run=args.dry_run, recent_days=args.recent_days)
    if args.dry_run:
        print(json.dumps(result["selectedByDate"], ensure_ascii=False, indent=2))
    else:
        mode = f"recent-{result['recentDays']}-day" if result["recentDays"] else "full-window"
        print(
            f"Ran {mode} update; wrote {result['selectedItemCount']} item(s) across "
            f"{result['selectedDateCount']} published date(s) to {DATA_PATH}; "
            f"backfilled {result['translatedCount']} Chinese summarie(s); "
            f"sanitized {result['sanitizedCount']} saved field(s)"
        )
    return 0


def update_news(date_key: str | None = None, dry_run: bool = False, recent_days: int | None = None) -> dict:
    date_key = date_key or dt.date.today().isoformat()
    if recent_days is not None and recent_days < 1:
        raise ValueError("--recent-days must be at least 1")
    config = load_json(CONFIG_PATH)
    data = load_json(DATA_PATH)
    golden_cases = load_golden_cases()
    translator = make_chinese_translator(config)

    retention_days = int(config.get("retentionDays") or data.get("retentionDays") or 90)
    lookback_days = recent_days if recent_days else int(config.get("lookbackDays", 14))
    classifier = make_article_classifier(config, golden_cases)
    semantic_scorer = make_semantic_scorer(config, golden_cases)
    retrieved_at = dt.datetime.now(dt.timezone.utc)
    selected_by_gp, coverage = select_items_by_gp(
        config,
        date_key,
        lookback_days,
        semantic_scorer,
        translator,
        classifier,
        recent_days=recent_days,
        retrieved_at=retrieved_at,
    )
    selected_by_date = group_selected_by_date(selected_by_gp)
    selected_item_count = sum(len(items) for items in selected_by_gp.values())

    result = {
        "date": date_key,
        "recentDays": recent_days,
        "selectedByDate": selected_by_date,
        "selectedItemCount": selected_item_count,
        "selectedDateCount": len(selected_by_date),
        "coverage": coverage,
        "translatedCount": 0,
        "sanitizedCount": 0,
        "backfilledCount": 0,
        "dataPath": str(DATA_PATH),
    }

    if dry_run:
        return result

    data["scope"] = build_scope(config)
    if recent_days:
        merge_recent_digests(data, date_key, selected_by_date, retention_days)
    else:
        merge_digests_by_published_date(data, date_key, selected_by_date, retention_days)
    result["backfilledCount"] = backfill_saved_items(data, config)
    # Every mode backfills translations and prunes, so the hourly run is self-sufficient.
    result["translatedCount"] = translate_existing_chinese_summaries(data, translator)
    result["sanitizedCount"] = sanitize_saved_news(data)
    data["coverage"] = coverage
    data["checkedAt"] = retrieved_at.isoformat()
    DATA_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result


def backfill_saved_data() -> int:
    """Offline migration of data/news.json: no fetching, no Claude calls."""
    config = load_json(CONFIG_PATH)
    data = load_json(DATA_PATH)
    data["scope"] = build_scope(config)
    changed = backfill_saved_items(data, config)
    changed += sanitize_saved_news(data)
    DATA_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return changed


def build_scope(config: dict) -> dict:
    gps = list(config.get("gps") or GP_ALIASES)
    groups = config.get("gpGroups") or {"invested": gps, "watch": []}
    return {
        "regions": ["US", "Europe"],
        "gps": gps,
        "gpGroups": {
            "invested": [gp for gp in groups.get("invested", []) if gp in gps],
            "watch": [gp for gp in groups.get("watch", []) if gp in gps],
        },
        "strategies": [
            {"id": s["id"], "name": s["name"], "cn": s["cn"], "group": s["group"], "pattern": s["pattern"]}
            for s in STRATEGIES
        ],
        "strategyGroups": STRATEGY_GROUPS,
        "events": EVENT_IDS,
        "ratingWeights": rating_weights(config),
    }


def load_json(path: Path) -> dict:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def load_golden_cases() -> dict:
    if GOLDEN_CASES_PATH.exists():
        return load_json(GOLDEN_CASES_PATH)
    return {"cases": []}


def fetch_google_candidates(queries: list[str], lookback_days: int, stats: dict | None = None) -> list[dict]:
    candidates = []
    for query in queries:
        url = google_news_rss_url(query, lookback_days)
        try:
            with urllib.request.urlopen(url, timeout=20) as response:
                payload = response.read()
        except Exception as exc:
            print(f"Warning: failed to fetch {query!r}: {exc}", file=sys.stderr)
            if stats is not None:
                stats["failed"] = stats.get("failed", 0) + 1
                stats["error"] = str(exc)
            continue
        try:
            candidates.extend(parse_feed(payload, source_hint="Google News"))
            if stats is not None:
                stats["ok"] = stats.get("ok", 0) + 1
        except ET.ParseError as exc:
            print(f"Warning: failed to parse Google News RSS for {query!r}: {exc}", file=sys.stderr)
            if stats is not None:
                stats["failed"] = stats.get("failed", 0) + 1
                stats["error"] = f"parse error: {exc}"
    return dedupe(candidates)


def fetch_rss_candidates(feeds: list[dict]) -> list[dict]:
    candidates = []
    for feed in feeds:
        try:
            with urllib.request.urlopen(request_for(feed["url"]), timeout=20) as response:
                payload = response.read()
        except Exception as exc:
            print(f"Warning: failed to fetch RSS feed {feed.get('name', feed.get('url'))!r}: {exc}", file=sys.stderr)
            continue
        try:
            candidates.extend(parse_feed(payload, source_hint=feed.get("name", "RSS feed")))
        except ET.ParseError as exc:
            print(f"Warning: failed to parse RSS feed {feed.get('name', feed.get('url'))!r}: {exc}", file=sys.stderr)
    return dedupe(candidates)


def fetch_html_candidates(sources: list[dict]) -> list[dict]:
    candidates = []
    for source in sources:
        parser = source.get("parser")
        if parser == "asset_securitization_report":
            candidates.extend(fetch_asset_securitization_report_candidates(source))
        elif parser == "generic_listing":
            candidates.extend(fetch_generic_listing_candidates(source))
        else:
            print(f"Warning: unknown HTML source parser {parser!r} for {source.get('name', source.get('url'))!r}", file=sys.stderr)
    return dedupe(candidates)


def fetch_asset_securitization_report_candidates(source: dict) -> list[dict]:
    try:
        with urllib.request.urlopen(request_for(source["url"]), timeout=20) as response:
            charset = response.headers.get_content_charset() or "utf-8"
            payload = response.read(1_000_000).decode(charset, errors="ignore")
    except Exception as exc:
        print(f"Warning: failed to fetch HTML source {source.get('name', source.get('url'))!r}: {exc}", file=sys.stderr)
        return []
    return parse_asset_securitization_report_html(payload, source)


def fetch_generic_listing_candidates(source: dict) -> list[dict]:
    try:
        with urllib.request.urlopen(request_for(source["url"]), timeout=20) as response:
            charset = response.headers.get_content_charset() or "utf-8"
            payload = response.read(1_500_000).decode(charset, errors="ignore")
    except Exception as exc:
        print(f"Warning: failed to fetch HTML source {source.get('name', source.get('url'))!r}: {exc}", file=sys.stderr)
        return []
    return parse_generic_listing_html(payload, source)


def parse_asset_securitization_report_html(html_payload: str, source: dict) -> list[dict]:
    items = []
    seen = set()
    for match in re.finditer(r'(?is)<a\b[^>]*href=["\']([^"\']+)["\'][^>]*>(.*?)</a>', html_payload):
        href = html.unescape(match.group(1)).strip()
        title = clean_html(match.group(2))
        if not is_probable_asr_article(href, title):
            continue
        url = urllib.parse.urljoin(source["url"], href)
        normalized = normalize_url(url)
        if normalized in seen:
            continue
        seen.add(normalized)
        context = html_payload[match.end() : match.end() + 1800]
        description = extract_asr_description(context, title)
        items.append(
            {
                "title": title,
                "url": url,
                "description": description,
                "source": source.get("name", "Asset Securitization Report"),
                "publishedAt": parse_asr_listing_date(context),
            }
        )
    return items


def parse_generic_listing_html(html_payload: str, source: dict) -> list[dict]:
    items = []
    seen = set()
    for match in re.finditer(r'(?is)<a\b[^>]*href=["\']([^"\']+)["\'][^>]*>(.*?)</a>', html_payload):
        href = html.unescape(match.group(1)).strip()
        title = clean_html(match.group(2))
        url = urllib.parse.urljoin(source["url"], href)
        if not is_probable_listing_article(url, title, source):
            continue
        normalized = normalize_url(url)
        if normalized in seen:
            continue
        seen.add(normalized)
        context_start = max(0, match.start() - 350)
        context = html_payload[context_start : match.end() + 1800]
        description = extract_listing_description(context, title, source.get("name", "HTML source"))
        items.append(
            {
                "title": title,
                "url": url,
                "description": description,
                "source": source.get("name", "HTML source"),
                "publishedAt": parse_listing_date(context),
            }
        )
    return items


def is_probable_listing_article(url: str, title: str, source: dict) -> bool:
    if len(title) < 24:
        return False
    lowered_title = title.lower()
    blocked_title_prefixes = (
        "advertise",
        "article feeds",
        "blog feeds",
        "contact",
        "home",
        "image:",
        "latest news",
        "load more",
        "login",
        "news feeds",
        "privacy",
        "read more",
        "rss",
        "sign in",
        "subscribe",
        "terms",
    )
    if lowered_title.startswith(blocked_title_prefixes):
        return False

    parsed_url = urllib.parse.urlsplit(url)
    parsed_source = urllib.parse.urlsplit(source["url"])
    lowered_path = parsed_url.path.lower()
    lowered_url = url.lower()
    if parsed_url.scheme not in {"http", "https"}:
        return False
    if parsed_url.netloc and parsed_source.netloc and parsed_url.netloc != parsed_source.netloc:
        return False
    if any(token in lowered_url for token in [".jpg", ".jpeg", ".png", ".gif", ".webp", "#", "javascript:", "mailto:"]):
        return False

    source_name = source.get("name", "").lower()
    if "inside mortgage finance" in source_name:
        return bool(re.search(r"/articles/\d+", lowered_path)) and "/articles/topic/" not in lowered_path
    if "abl advisor" in source_name:
        return "/news/" in lowered_path or "readstory.aspx" in lowered_path
    if "structured credit investor" in source_name:
        return "article" in lowered_path and "weeklyissue" not in lowered_path
    return True


def is_probable_asr_article(href: str, title: str) -> bool:
    if len(title) < 24:
        return False
    lowered_title = title.lower()
    if lowered_title.startswith(("image:", "subscribe", "login", "load more")):
        return False
    lowered_href = href.lower()
    if any(token in lowered_href for token in [".jpg", ".jpeg", ".png", "#", "javascript:", "mailto:"]):
        return False
    return "asreport.americanbanker.com" in lowered_href or href.startswith("/")


def extract_asr_description(context: str, title: str) -> str:
    text = clean_html(context)
    text = re.sub(r"\bBy\s+.+?(?:Editor|Reporter|Capital Markets Editor)\b", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"\b\d+h ago\b", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"\b(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2}(?:,\s+\d{4})?\b", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    if text.lower().startswith(title.lower()):
        text = text[len(title) :].strip()
    return textwrap.shorten(text or title, width=520, placeholder="...")


def extract_listing_description(context: str, title: str, source_name: str) -> str:
    text = clean_html(context)
    text = re.sub(r"\bBy\s+[A-Z][A-Za-z .,'-]{2,80}\b", " ", text)
    text = re.sub(r"\bRead\s+More\b", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"\bSubscribe\b.*", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"\b\d+h ago\b", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*\.?\s+\d{1,2}(?:,\s+\d{4})?(?:\s*@\s*\d{1,2}:\d{2}\s*[AP]M)?\b", " ", text)
    text = re.sub(r"\b\d{1,2}/\d{1,2}/\d{2,4}\b", " ", text)
    text = re.sub(re.escape(source_name), " ", text, flags=re.IGNORECASE)
    text = re.sub(r"\s+", " ", text).strip()
    if text.lower().startswith(title.lower()):
        text = text[len(title) :].strip()
    return textwrap.shorten(text or title, width=520, placeholder="...")


def parse_asr_listing_date(context: str) -> str:
    return parse_listing_date(context)


def parse_listing_date(context: str) -> str:
    text = clean_html(context)
    if re.search(r"\b\d+h ago\b", text, flags=re.IGNORECASE):
        return dt.date.today().isoformat()
    if re.search(r"\btoday\b", text, flags=re.IGNORECASE):
        return dt.date.today().isoformat()
    if re.search(r"\byesterday\b", text, flags=re.IGNORECASE):
        return (dt.date.today() - dt.timedelta(days=1)).isoformat()
    match = re.search(
        r"\b(Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:t|tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\.?\s+(\d{1,2})(?:,\s+(\d{4}))?\b",
        text,
        flags=re.IGNORECASE,
    )
    if match:
        month = MONTH_INDEX[match.group(1).lower().rstrip(".")]
        day = int(match.group(2))
        year = int(match.group(3) or dt.date.today().year)
        return normalize_listing_date(year, month, day, has_year=bool(match.group(3)))

    numeric = re.search(r"\b(\d{1,2})/(\d{1,2})/(\d{2,4})\b", text)
    if numeric:
        month = int(numeric.group(1))
        day = int(numeric.group(2))
        year = int(numeric.group(3))
        if year < 100:
            year += 2000
        return normalize_listing_date(year, month, day, has_year=True)
    return dt.date.today().isoformat()


def normalize_listing_date(year: int, month: int, day: int, has_year: bool) -> str:
    try:
        parsed = dt.date(year, month, day)
    except ValueError:
        return dt.date.today().isoformat()
    today = dt.date.today()
    if not has_year and parsed > today + dt.timedelta(days=7):
        parsed = dt.date(year - 1, month, day)
    return parsed.isoformat()


def google_news_rss_url(query: str, lookback_days: int) -> str:
    bounded_query = f"{query} when:{lookback_days}d"
    params = urllib.parse.urlencode({"q": bounded_query, "hl": "en-US", "gl": "US", "ceid": "US:en"})
    return f"https://news.google.com/rss/search?{params}"


def request_for(url: str) -> urllib.request.Request:
    return urllib.request.Request(
        url,
        headers={
            "User-Agent": "credit-news-dashboard/1.0 contact=local",
            "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml, */*",
        },
    )


def parse_feed(payload: bytes, source_hint: str) -> list[dict]:
    root = ET.fromstring(payload)
    if root.tag.endswith("feed"):
        return parse_atom(root, source_hint)
    return parse_rss(root, source_hint)


def parse_rss(root: ET.Element, source_hint: str) -> list[dict]:
    items = []
    for item in root.findall(".//item"):
        title = text_of(item, "title")
        url = text_of(item, "link")
        description = clean_html(text_of(item, "description"))
        source = text_of(item, "source") or extract_source_from_title(title) or source_hint
        published_at = parse_pubdate(text_of(item, "pubDate"))
        if title and url:
            items.append(
                {
                    "title": title,
                    "url": url,
                    "description": description,
                    "source": source,
                    "publishedAt": published_at,
                }
            )
    return items


def parse_atom(root: ET.Element, source_hint: str) -> list[dict]:
    ns = {"atom": "http://www.w3.org/2005/Atom"}
    items = []
    for entry in root.findall("atom:entry", ns) or root.findall(".//entry"):
        title = text_of_ns(entry, "title", ns)
        url = atom_link(entry, ns)
        description = clean_html(text_of_ns(entry, "summary", ns) or text_of_ns(entry, "content", ns))
        source = source_hint
        published_at = parse_iso_date(text_of_ns(entry, "updated", ns) or text_of_ns(entry, "published", ns))
        if title and url:
            items.append(
                {
                    "title": title,
                    "url": url,
                    "description": description,
                    "source": source,
                    "publishedAt": published_at,
                }
            )
    return items


def text_of(node: ET.Element, child_name: str) -> str:
    child = node.find(child_name)
    return (child.text or "").strip() if child is not None else ""


def text_of_ns(node: ET.Element, child_name: str, ns: dict[str, str]) -> str:
    child = node.find(f"atom:{child_name}", ns)
    if child is None:
        child = node.find(child_name)
    return (child.text or "").strip() if child is not None else ""


def atom_link(node: ET.Element, ns: dict[str, str]) -> str:
    for link in node.findall("atom:link", ns) or node.findall("link"):
        href = link.attrib.get("href")
        if href and link.attrib.get("rel", "alternate") == "alternate":
            return href.strip()
    return ""


def clean_html(value: str) -> str:
    value = value or ""
    value = re.sub(r"(?is)&lt;\s*(?:img|picture|source)\b.*?(?:&gt;|$)", " ", value)
    value = re.sub(r"(?is)<\s*(?:img|picture|source)\b.*?(?:>|$)", " ", value)
    value = html.unescape(value)
    value = re.sub(r"(?is)<\s*(?:img|picture|source)\b.*?(?:>|$)", " ", value)
    value = re.sub(r"(?is)<(script|style|noscript|svg|picture).*?</\1>", " ", value)
    value = re.sub(r"<[^>]+>", " ", value)
    value = re.sub(r"\b(?:srcset|src|alt|data-image-size|class)=['\"][^'\"]*['\"]", " ", value, flags=re.IGNORECASE)
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def extract_source_from_title(title: str) -> str:
    if " - " in title:
        return title.rsplit(" - ", 1)[-1].strip()
    return "Google News"


def parse_pubdate(value: str) -> str:
    try:
        parsed = email.utils.parsedate_to_datetime(value)
    except Exception:
        return dt.date.today().isoformat()
    return parsed.date().isoformat()


def parse_iso_date(value: str) -> str:
    if not value:
        return dt.date.today().isoformat()
    try:
        normalized = value.replace("Z", "+00:00")
        return dt.datetime.fromisoformat(normalized).date().isoformat()
    except ValueError:
        return parse_pubdate(value)


def dedupe(items: list[dict]) -> list[dict]:
    seen = set()
    unique = []
    for item in items:
        key = normalize_url(item["url"])
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)
    return unique


def normalize_url(url: str) -> str:
    parsed = urllib.parse.urlsplit(url)
    return urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, parsed.path, "", ""))


def select_items_by_gp(
    config: dict,
    date_key: str,
    lookback_days: int,
    semantic_scorer: "SemanticScorer | None",
    translator: "ChineseTranslator | None",
    classifier: "ArticleClassifier | None",
    recent_days: int | None = None,
    retrieved_at: dt.datetime | None = None,
) -> tuple[dict[str, list[dict]], list[dict]]:
    gp_order = config.get("gps") or list(GP_ALIASES)
    gp_queries = config.get("gpQueries", {})
    max_items = int(config.get("maxItemsPerGp", 6))
    retrieved_at = retrieved_at or dt.datetime.now(dt.timezone.utc)
    selected_by_gp = {}
    coverage: list[dict] = []

    for gp in gp_order:
        queries = gp_queries.get(gp) or [f"{gp} private credit"]
        stats: dict = {}
        candidates = fetch_google_candidates(queries, lookback_days, stats)
        selected_by_gp[gp] = select_items(
            candidates,
            config,
            date_key,
            lookback_days,
            gp,
            max_items,
            semantic_scorer,
            translator,
            classifier,
            recent_days=recent_days,
            retrieved_at=retrieved_at,
        )
        coverage.append(
            {
                "firm": gp,
                "count": len(candidates),
                "selected": len(selected_by_gp[gp]),
                "status": "ok" if stats.get("ok") else "error",
                "query": queries[0],
                "queries": queries,
                "asOf": retrieved_at.isoformat(),
                "errorReason": stats.get("error", "") if not stats.get("ok") else "",
            }
        )

    general_stats: dict = {}
    general_candidates = fetch_google_candidates(config.get("sourceQueries", []), lookback_days, general_stats)
    general_candidates = merge_items(general_candidates, fetch_rss_candidates(config.get("rssFeeds", [])))
    general_candidates = merge_items(general_candidates, fetch_html_candidates(config.get("htmlSources", [])))
    general_selected = select_items(
        general_candidates,
        config,
        date_key,
        lookback_days,
        None,
        max_items,
        semantic_scorer,
        translator,
        classifier,
        recent_days=recent_days,
        retrieved_at=retrieved_at,
    )
    for item in general_selected:
        for gp in item.get("gps", []):
            if gp in selected_by_gp:
                selected_by_gp[gp] = merge_items(selected_by_gp[gp], [item])[:max_items]
    coverage.append(
        {
            "firm": "Portfolio",
            "count": len(general_candidates),
            "selected": len(general_selected),
            "status": "ok" if general_candidates else "error",
            "query": "; ".join(config.get("sourceQueries", [])[:2]),
            "queries": list(config.get("sourceQueries", [])),
            "asOf": retrieved_at.isoformat(),
            "errorReason": general_stats.get("error", "") if not general_candidates else "",
        }
    )

    return selected_by_gp, coverage


def select_items(
    candidates: list[dict],
    config: dict,
    date_key: str,
    lookback_days: int,
    focus_gp: str | None,
    max_items: int,
    semantic_scorer: "SemanticScorer | None",
    translator: "ChineseTranslator | None",
    classifier: "ArticleClassifier | None",
    recent_days: int | None = None,
    retrieved_at: dt.datetime | None = None,
) -> list[dict]:
    scored = []
    target_date = dt.date.fromisoformat(date_key)
    cutoff = target_date - dt.timedelta(days=(recent_days or lookback_days) - 1)
    for item in candidates:
        published = dt.date.fromisoformat(item["publishedAt"])
        if published < cutoff or published > target_date:
            continue
        enriched = enrich_item(item, config, focus_gp, semantic_scorer, translator, classifier, retrieved_at=retrieved_at)
        if enriched.get("excludedByClassifier"):
            continue
        if focus_gp and focus_gp not in enriched["gps"]:
            continue
        threshold = score_threshold(config, semantic_scorer)
        if enriched["score"] >= threshold:
            scored.append(enriched)

    scored.sort(key=lambda item: (item["score"], item["publishedAt"]), reverse=True)
    return [strip_score(item) for item in scored[:max_items]]


def enrich_item(
    item: dict,
    config: dict,
    focus_gp: str | None,
    semantic_scorer: "SemanticScorer | None",
    translator: "ChineseTranslator | None",
    classifier: "ArticleClassifier | None",
    retrieved_at: dt.datetime | None = None,
) -> dict:
    if (semantic_scorer or classifier) and not item.get("articleText"):
        item = dict(item)
        item["articleText"] = fetch_article_text(item["url"])
    gp_order = config.get("gps") or list(GP_ALIASES)
    aliases = gp_alias_map(config)
    title = item["title"]
    blob = f"{title} {item.get('description', '')} {item.get('source', '')}".lower()
    title_gps = match_terms(title.lower(), aliases)
    keyword_gps = match_terms(blob, aliases)
    title_strategies = match_strategies(title)
    keyword_strategies = match_strategies(f"{title} {item.get('description', '')}")
    llm_classification = classifier.classify(item) if classifier else default_classification()
    llm_gps = valid_ordered_labels(llm_classification.get("gps", []), gp_order)
    llm_strategies = valid_ordered_labels(llm_classification.get("strategies", []), STRATEGY_IDS)
    llm_events = [event for event in llm_classification.get("events", []) if event in EVENT_IDS]
    gps = union_ordered(gp_order, keyword_gps, llm_gps)
    strategies = union_ordered(STRATEGY_IDS, keyword_strategies, llm_strategies)
    events = union_ordered(EVENT_IDS, detect_events(f"{title} {item.get('description', '')}"), llm_events)
    region = detect_region(blob)
    source_bonus = source_score(item.get("source", ""), config.get("preferredSources", []))
    keyword_score = source_bonus + len(gps) * 4 + len(strategies) * 3

    if any(term in blob for term in CREDIT_CONTEXT):
        keyword_score += 3
    if gps and not any(term in blob for term in CREDIT_CONTEXT):
        keyword_score -= 5
    if region == "US":
        keyword_score += 2
    elif region == "Europe":
        keyword_score += 1
    if focus_gp:
        if focus_gp in gps:
            keyword_score += 4
        else:
            keyword_score -= 4
    semantic_item = dict(item)
    semantic_item["gps"] = gps
    semantic_score = semantic_scorer.score(semantic_item) if semantic_scorer else 0
    final_score = keyword_score + semantic_score
    semantic_scale = float(config.get("semanticScoring", {}).get("scoreScale", 12))

    rating = compute_rating(
        title=title,
        source=item.get("source") or "Google News",
        published_at=item["publishedAt"],
        gps=gps,
        strategies=strategies,
        events=events,
        title_gps=title_gps,
        llm_gps=llm_gps,
        title_strategies=title_strategies,
        llm_strategies=llm_strategies,
        semantic_score=semantic_score if semantic_scorer and not getattr(semantic_scorer, "failed", False) else None,
        semantic_scale=semantic_scale,
        llm_importance=llm_classification.get("importance"),
        retrieved_at=retrieved_at,
        config=config,
    )

    summary = summarize(item)
    article_excerpt = document_for_semantic_scoring(item)
    llm_reason = llm_classification.get("reason", "")
    translated = translate_bundle(title, summary, llm_reason, translator)
    return {
        "id": stable_id(item),
        "title": title,
        "titleZh": translated["title"],
        "summary": summary,
        "summaryZh": translated["summary"],
        "summaryZhLanguage": translator.target_language if translator else "",
        "url": item["url"],
        "source": item.get("source") or "Google News",
        "publishedAt": item["publishedAt"],
        "lede": item.get("description", ""),
        "articleExcerpt": article_excerpt,
        "contentFingerprint": content_fingerprint(
            {
                "title": title,
                "description": item.get("description", ""),
                "publishedAt": item["publishedAt"],
            }
        ),
        "region": region,
        "gps": gps,
        "strategies": strategies,
        "sectors": strategies,
        "events": events,
        "curation": "rss_filter",
        "excludedByClassifier": bool(llm_classification.get("exclude")),
        "classificationBreakdown": {
            "keywordGps": keyword_gps,
            "titleGps": title_gps,
            "llmGps": llm_gps,
            "keywordStrategies": keyword_strategies,
            "titleStrategies": title_strategies,
            "llmStrategies": llm_strategies,
            "llmEvents": llm_events,
            "llmImportance": llm_classification.get("importance"),
            "llmExclude": bool(llm_classification.get("exclude")),
            "llmReason": llm_reason,
            "llmReasonZh": translated["reason"],
        },
        "rating": rating,
        "score": final_score,
        "scoreBreakdown": {
            "keywordScore": keyword_score,
            "semanticScore": semantic_score,
            "finalScore": final_score,
            "semanticEnabled": bool(semantic_scorer),
        },
    }


def gp_alias_map(config: dict) -> dict[str, list[str]]:
    configured = config.get("gpAliases") if isinstance(config, dict) else None
    aliases = {gp: [alias.lower() for alias in names] for gp, names in (configured or GP_ALIASES).items()}
    for gp in config.get("gps") or []:
        aliases.setdefault(gp, [gp.lower()])
    return aliases


def match_strategies(text: str) -> list[str]:
    """Strategy ids whose keyword list or regex pattern hits the text."""
    lowered = f" {text.lower()} "
    matched = []
    for strategy in STRATEGIES:
        if any(keyword in lowered for keyword in strategy["keywords"]) or re.search(strategy["pattern"], text, flags=re.IGNORECASE):
            matched.append(strategy["id"])
    return matched


def detect_events(text: str) -> list[str]:
    return [event for event in EVENT_IDS if EVENT_PATTERNS[event].search(text)]


def rating_weights(config: dict) -> dict[str, int]:
    weights = dict(DEFAULT_RATING_WEIGHTS)
    for key, value in (config.get("ratingWeights") or {}).items():
        if key in weights:
            try:
                weights[key] = max(0, int(value))
            except (TypeError, ValueError):
                continue
    return weights


def source_tier(source: str) -> tuple[str, float]:
    name = (source or "").strip()
    for code, value, pattern in SOURCE_TIERS:
        if pattern.search(name):
            return code, value
    return "tier_other", 0.35


def event_rule(title: str, events: list[str]) -> tuple[float, str]:
    """Deterministic importance rules, mirrored from the dashboard's explanation table."""
    value, code = 0.2, "routine"
    if "financing" in events:
        value, code = 0.7, "financing"
    if "fundraising" in events:
        value, code = 0.8, "fundraising"
    if MAJOR_SIGNAL_PATTERN.search(title):
        value, code = 0.95, "major_signal"
    if "lawsuit" in events:
        value, code = 1.0, "lawsuit"
    if STOCK_COMMENTARY_PATTERN.search(title) and "lawsuit" not in events and "fundraising" not in events:
        value, code = 0.15, "stock_commentary"
    if SOLICITATION_PATTERN.search(title):
        value, code = 0.1, "solicitation"
    return value, code


def freshness_bucket(days: float) -> tuple[float, str]:
    if days <= 1:
        return 1.0, "within_24h"
    if days <= 7:
        return 0.8, "within_7d"
    if days <= 30:
        return 0.5, "within_30d"
    if days <= 90:
        return 0.2, "within_90d"
    return 0.05, "older"


def weighted_rating_score(parts: dict, weights: dict[str, int]) -> int:
    total_weight = sum(max(0, weights.get(key, 0)) for key in parts)
    if not total_weight:
        return 0
    weighted = sum(float(part.get("value", 0)) * max(0, weights.get(key, 0)) for key, part in parts.items())
    return int(round(weighted / total_weight * 100))


def compute_rating(
    title: str,
    source: str,
    published_at: str,
    gps: list[str],
    strategies: list[str],
    events: list[str],
    title_gps: list[str],
    llm_gps: list[str],
    title_strategies: list[str],
    llm_strategies: list[str],
    semantic_score: float | None,
    semantic_scale: float,
    llm_importance,
    retrieved_at: dt.datetime | None,
    config: dict,
    freshness_override: tuple[float, str] | None = None,
) -> dict:
    """Five 0-1 components computed once at retrieval; the dashboard re-weights them."""
    weights = rating_weights(config)

    if title_gps:
        institution = {"value": 1.0, "code": "title_names_gp", "gps": title_gps}
    elif llm_gps:
        institution = {"value": 0.7, "code": "llm_tagged_gp", "gps": llm_gps}
    elif gps:
        institution = {"value": 0.5, "code": "body_mentions_gp", "gps": gps}
    else:
        institution = {"value": 0.25, "code": "query_only", "gps": []}

    if title_strategies:
        tag_value, strategy_code = 1.0, "title_hits_strategy"
    elif llm_strategies:
        tag_value, strategy_code = 0.7, "llm_strategy"
    elif strategies:
        tag_value, strategy_code = 0.6, "body_strategy"
    else:
        tag_value, strategy_code = 0.0, "no_strategy"
    strategy = {"value": tag_value, "code": strategy_code, "tagValue": tag_value, "strategies": strategies}
    if semantic_score is not None and semantic_scale > 0:
        semantic_value = max(0.0, min(1.0, float(semantic_score) / semantic_scale))
        strategy["semanticValue"] = round(semantic_value, 2)
        strategy["value"] = round((tag_value + semantic_value) / 2, 2)

    rule_value, event_code = event_rule(title, events)
    event = {"value": rule_value, "code": event_code, "ruleValue": rule_value, "events": events}
    try:
        llm_value = None if llm_importance is None else max(0.0, min(1.0, float(llm_importance)))
    except (TypeError, ValueError):
        llm_value = None
    if llm_value is not None and event_code not in {"solicitation", "stock_commentary"}:
        event["llmValue"] = round(llm_value, 2)
        event["value"] = round((rule_value + llm_value) / 2, 2)

    source_code, source_value = source_tier(source)
    source_part = {"value": source_value, "code": source_code, "source": source}

    if freshness_override:
        freshness_value, freshness_code = freshness_override
        days = None
    else:
        retrieved = retrieved_at or dt.datetime.now(dt.timezone.utc)
        try:
            published = dt.datetime.fromisoformat(f"{published_at[:10]}T12:00:00+00:00")
            days = max(0.0, (retrieved - published).total_seconds() / 86400)
        except ValueError:
            days = 0.0
        freshness_value, freshness_code = freshness_bucket(days)
    freshness = {"value": freshness_value, "code": freshness_code}
    if days is not None:
        freshness["days"] = round(days, 1)

    parts = {
        "institution": institution,
        "strategy": strategy,
        "event": event,
        "source": source_part,
        "freshness": freshness,
    }
    return {
        "parts": parts,
        "weights": weights,
        "score": weighted_rating_score(parts, weights),
        "retrievedAt": (retrieved_at or dt.datetime.now(dt.timezone.utc)).isoformat(),
    }


def translate_bundle(title: str, summary: str, reason: str, translator: "ChineseTranslator | None") -> dict:
    if not translator:
        return {"title": title, "summary": MISSING_ZH_SUMMARY, "reason": reason}
    return translator.translate_bundle(title, summary, reason)


def backfill_saved_items(data: dict, config: dict) -> int:
    """Bring saved items up to the current schema without network or Claude calls.

    Remaps legacy GP names, derives strategies and events from keywords, computes
    rating parts for items that lack them, and rebuilds the per-date GP buckets.
    """
    gp_order = list(config.get("gps") or GP_ALIASES)
    aliases = gp_alias_map(config)
    changed = 0
    for date_key, date_digest in data.get("dates", {}).items():
        items_by_key: dict[str, dict] = {}
        for item in iter_digest_items(date_digest):
            key = item.get("id") or item.get("url")
            if key in items_by_key:
                continue
            items_by_key[key] = item
            if backfill_item(item, gp_order, aliases, config):
                changed += 1
        items = list(items_by_key.values())
        by_gp = {gp: [] for gp in gp_order}
        for item in items:
            for gp in item.get("gps", []):
                if gp in by_gp:
                    by_gp[gp] = merge_items(by_gp[gp], [item])
        date_digest["byGp"] = by_gp
        date_digest["items"] = items
    return changed


def backfill_item(item: dict, gp_order: list[str], aliases: dict[str, list[str]], config: dict) -> bool:
    before = json.dumps(item, sort_keys=True, ensure_ascii=False)
    changed = False
    title = item.get("title", "")
    text = f"{title} {item.get('lede') or item.get('summary') or ''}"

    renamed = []
    for gp in item.get("gps", []):
        target = GP_RENAMES.get(gp, gp)
        if target in gp_order and target not in renamed:
            renamed.append(target)
    for gp in match_terms(title.lower(), aliases):
        if gp in gp_order and gp not in renamed:
            renamed.append(gp)
    renamed = union_ordered(gp_order, renamed)
    if renamed != item.get("gps", []):
        item["gps"] = renamed
        changed = True
    breakdown = item.setdefault("classificationBreakdown", {})
    for field in ("keywordGps", "llmGps", "titleGps"):
        values = [GP_RENAMES.get(gp, gp) for gp in breakdown.get(field, [])]
        values = [gp for gp in values if gp in gp_order]
        if values != breakdown.get(field, []):
            breakdown[field] = values
            changed = True

    if not item.get("strategies"):
        legacy = []
        for sector in item.get("sectors", []):
            legacy.extend(LEGACY_SECTOR_MAP.get(sector, [sector] if sector in STRATEGY_IDS else []))
        item["strategies"] = union_ordered(STRATEGY_IDS, legacy, match_strategies(text))
        changed = True
    if item.get("sectors") != item.get("strategies"):
        item["sectors"] = list(item.get("strategies", []))
        changed = True

    if "events" not in item:
        item["events"] = detect_events(text)
        changed = True

    if not isinstance(item.get("rating"), dict) or "parts" not in item.get("rating", {}):
        semantic = item.get("scoreBreakdown", {}).get("semanticScore")
        semantic_enabled = bool(item.get("scoreBreakdown", {}).get("semanticEnabled"))
        item["rating"] = compute_rating(
            title=title,
            source=item.get("source", ""),
            published_at=item.get("publishedAt") or item.get("date") or "",
            gps=item.get("gps", []),
            strategies=item.get("strategies", []),
            events=item.get("events", []),
            title_gps=match_terms(title.lower(), aliases),
            llm_gps=breakdown.get("llmGps", []),
            title_strategies=match_strategies(title),
            llm_strategies=breakdown.get("llmStrategies", []),
            semantic_score=float(semantic) if semantic_enabled and semantic is not None else None,
            semantic_scale=float(config.get("semanticScoring", {}).get("scoreScale", 12)),
            llm_importance=breakdown.get("llmImportance"),
            retrieved_at=None,
            config=config,
            freshness_override=(0.8, "estimated"),
        )
        changed = True
    # Report a change only when the serialized item actually differs.
    return changed and json.dumps(item, sort_keys=True, ensure_ascii=False) != before


def score_threshold(config: dict, semantic_scorer: "SemanticScorer | None") -> int:
    if semantic_scorer and not getattr(semantic_scorer, "failed", False):
        return int(config.get("semanticScoring", {}).get("minimumFinalScore") or config.get("minimumScore", 7))
    return int(config.get("minimumScore", 7))


def translate_summary(summary: str, translator: "ChineseTranslator | None") -> str:
    if not summary:
        return MISSING_ZH_SUMMARY
    if not translator:
        return MISSING_ZH_SUMMARY
    return translator.translate(summary)


def fetch_article_text(url: str) -> str:
    if "news.google.com" in urllib.parse.urlsplit(url).netloc:
        return ""
    try:
        with urllib.request.urlopen(request_for(url), timeout=12) as response:
            content_type = response.headers.get("content-type", "")
            if "html" not in content_type:
                return ""
            html_payload = response.read(750_000).decode(response.headers.get_content_charset() or "utf-8", errors="ignore")
    except Exception:
        return ""
    return extract_first_words_from_html(html_payload, 200)


def extract_first_words_from_html(html_payload: str, limit: int) -> str:
    html_payload = re.sub(r"(?is)<(script|style|noscript|svg).*?</\1>", " ", html_payload)
    for pattern in [
        r'(?is)<meta\s+property=["\']og:description["\']\s+content=["\']([^"\']+)["\']',
        r'(?is)<meta\s+name=["\']description["\']\s+content=["\']([^"\']+)["\']',
    ]:
        match = re.search(pattern, html_payload)
        if match:
            return " ".join(clean_html(match.group(1)).split()[:limit])
    text = clean_html(html_payload)
    return " ".join(text.split()[:limit])


def match_terms(blob: str, mapping: dict[str, list[str]]) -> list[str]:
    matches = []
    padded = f" {blob} "
    for label, needles in mapping.items():
        if any(needle in padded for needle in needles):
            matches.append(label)
    return matches


def detect_region(blob: str) -> str:
    for region, needles in REGION_KEYWORDS.items():
        if any(needle in blob for needle in needles):
            return region
    return "Global"


def source_score(source: str, preferred_sources: list[str]) -> int:
    lowered = source.lower()
    return 3 if any(preferred.lower() in lowered for preferred in preferred_sources) else 0


def summarize(item: dict) -> str:
    base = clean_html(item.get("description") or item["title"])
    base = re.sub(r"\s+", " ", base).strip()
    sentences = re.split(r"(?<=[.!?])\s+", base)
    summary = " ".join(sentences[:3]).strip()
    if not summary:
        summary = item["title"]
    return textwrap.shorten(summary, width=620, placeholder="...")


def stable_id(item: dict) -> str:
    digest = hashlib.sha1(normalize_url(item["url"]).encode("utf-8")).hexdigest()[:12]
    return f"{item['publishedAt']}-{digest}"


def strip_score(item: dict) -> dict:
    item = dict(item)
    item.pop("score", None)
    return item


def group_selected_by_date(selected_by_gp: dict[str, list[dict]]) -> dict[str, dict[str, list[dict]]]:
    grouped: dict[str, dict[str, list[dict]]] = {}
    for gp, items in selected_by_gp.items():
        for item in items:
            published_date = item["publishedAt"]
            grouped.setdefault(published_date, {})
            grouped[published_date].setdefault(gp, [])
            grouped[published_date][gp] = merge_items(grouped[published_date][gp], [item])
    return grouped


def merge_digests_by_published_date(
    data: dict,
    run_date_key: str,
    selected_by_date: dict[str, dict[str, list[dict]]],
    retention_days: int,
) -> None:
    data["retentionDays"] = retention_days
    data["updatedAt"] = dt.datetime.now(dt.timezone.utc).isoformat()
    data.setdefault("dates", {})
    for published_date, selected_by_gp in selected_by_date.items():
        merge_digest_for_date(data, published_date, selected_by_gp)
    ensure_window_date(data, run_date_key)
    prune_old_dates(data, run_date_key, retention_days)


def merge_recent_digests(
    data: dict,
    run_date_key: str,
    selected_by_date: dict[str, dict[str, list[dict]]],
    retention_days: int | None = None,
) -> None:
    data["updatedAt"] = dt.datetime.now(dt.timezone.utc).isoformat()
    data.setdefault("dates", {})
    for published_date, selected_by_gp in selected_by_date.items():
        merge_digest_for_date(data, published_date, selected_by_gp)
    ensure_window_date(data, run_date_key)
    if retention_days:
        data["retentionDays"] = retention_days
        prune_old_dates(data, run_date_key, retention_days)


def merge_digest_for_date(data: dict, date_key: str, selected_by_gp: dict[str, list[dict]]) -> None:
    date_digest = data["dates"].setdefault(date_key, {})
    existing_by_gp = normalize_existing_gp_buckets(date_digest)
    for gp in config_gp_order(data):
        existing_by_gp.setdefault(gp, [])
    for gp, selected in selected_by_gp.items():
        existing_by_gp[gp] = merge_items(existing_by_gp.get(gp, []), selected)
    date_digest["byGp"] = existing_by_gp
    date_digest["items"] = flatten_unique(existing_by_gp)


def ensure_window_date(data: dict, date_key: str) -> None:
    date_digest = data["dates"].setdefault(date_key, {})
    existing_by_gp = normalize_existing_gp_buckets(date_digest)
    for gp in config_gp_order(data):
        existing_by_gp.setdefault(gp, [])
    date_digest["byGp"] = existing_by_gp
    date_digest["items"] = flatten_unique(existing_by_gp)


def normalize_existing_gp_buckets(date_digest: dict) -> dict[str, list[dict]]:
    by_gp = {gp: list(items) for gp, items in date_digest.get("byGp", {}).items()}
    for item in date_digest.get("items", []):
        for gp in item.get("gps", []):
            by_gp.setdefault(gp, [])
            by_gp[gp] = merge_items(by_gp[gp], [item])
    return by_gp


def merge_items(existing: list[dict], incoming: list[dict]) -> list[dict]:
    merged = list(existing)
    for item in incoming:
        duplicate_index = find_duplicate_index(merged, item)
        if duplicate_index is None:
            merged.append(item)
            continue
        if should_replace_duplicate(merged[duplicate_index], item):
            merged[duplicate_index] = merge_duplicate_metadata(merged[duplicate_index], item)
    return merged


def find_duplicate_index(items: list[dict], candidate: dict) -> int | None:
    candidate_url = normalize_url(candidate.get("url", ""))
    candidate_fingerprint = content_fingerprint(candidate)
    candidate_date = candidate.get("publishedAt") or candidate.get("date")

    for index, item in enumerate(items):
        if candidate_url and normalize_url(item.get("url", "")) == candidate_url:
            return index
        if candidate_date and candidate_date != (item.get("publishedAt") or item.get("date")):
            continue
        item_fingerprint = item.get("contentFingerprint") or content_fingerprint(item)
        if candidate_fingerprint and item_fingerprint and candidate_fingerprint == item_fingerprint:
            return index
        if title_similarity(item.get("title", ""), candidate.get("title", "")) >= 0.88:
            return index
    return None


def should_replace_duplicate(existing: dict, candidate: dict) -> bool:
    existing_priority = source_priority(existing.get("source", ""))
    candidate_priority = source_priority(candidate.get("source", ""))
    if candidate_priority != existing_priority:
        return candidate_priority > existing_priority
    existing_score = existing.get("score") or existing.get("scoreBreakdown", {}).get("finalScore", 0)
    candidate_score = candidate.get("score") or candidate.get("scoreBreakdown", {}).get("finalScore", 0)
    return candidate_score > existing_score


def merge_duplicate_metadata(existing: dict, candidate: dict) -> dict:
    merged = dict(candidate)
    alternate_sources = list(existing.get("alternateSources", []))
    alternate = {
        "source": existing.get("source", ""),
        "url": existing.get("url", ""),
        "title": existing.get("title", ""),
    }
    if alternate["url"] and normalize_url(alternate["url"]) != normalize_url(candidate.get("url", "")):
        alternate_sources.append(alternate)
    for source in candidate.get("alternateSources", []):
        if source not in alternate_sources:
            alternate_sources.append(source)
    if alternate_sources:
        merged["alternateSources"] = alternate_sources
    return merged


def content_fingerprint(item: dict) -> str:
    title_tokens = significant_tokens(item.get("title", ""))
    body_tokens = significant_tokens(item.get("description") or item.get("lede") or item.get("summary") or item.get("articleExcerpt") or "")
    tokens = title_tokens[:14] + body_tokens[:18]
    if len(tokens) < 4:
        return ""
    date_key = (item.get("publishedAt") or item.get("date") or "")[:10]
    return hashlib.sha1(f"{date_key}:{' '.join(tokens)}".encode("utf-8")).hexdigest()[:16]


def title_similarity(left: str, right: str) -> float:
    left_tokens = set(significant_tokens(left))
    right_tokens = set(significant_tokens(right))
    if not left_tokens or not right_tokens:
        return 0
    return len(left_tokens & right_tokens) / len(left_tokens | right_tokens)


def significant_tokens(value: str) -> list[str]:
    stopwords = {
        "the",
        "a",
        "an",
        "and",
        "or",
        "of",
        "to",
        "in",
        "for",
        "on",
        "with",
        "by",
        "from",
        "as",
        "at",
        "is",
        "are",
        "its",
        "new",
        "news",
        "says",
        "said",
        "update",
    }
    tokens = re.findall(r"[a-z0-9]+", clean_html(value).lower())
    return [token for token in tokens if len(token) > 2 and token not in stopwords]


def source_priority(source: str) -> int:
    lowered = source.lower()
    priority_groups = [
        ("sec", "edgar", "company filing"),
        ("reuters", "bloomberg", "financial times", "wall street journal"),
        ("asset securitization report", "creditflux", "structured credit investor", "private credit daily", "abl advisor"),
        ("business wire", "pr newswire", "globenewswire"),
        ("yahoo", "marketscreener", "tipranks", "benzinga", "google news"),
    ]
    for index, group in enumerate(priority_groups):
        if any(token in lowered for token in group):
            return len(priority_groups) - index
    return 2


def flatten_unique(by_gp: dict[str, list[dict]]) -> list[dict]:
    return merge_items([], [item for items in by_gp.values() for item in items])


def config_gp_order(data: dict) -> list[str]:
    return data.get("scope", {}).get("gps") or list(GP_ALIASES)


def document_strategy_list() -> str:
    return "\n".join(f"- [{s['id']}] {s['name']} ({', '.join(s['keywords'][:4]).strip()})" for s in STRATEGIES)


def make_article_classifier(config: dict, golden_cases: dict) -> "ArticleClassifier | None":
    classification_config = config.get("classification", {})
    if not classification_config.get("enabled", True):
        return None
    try:
        return ArticleClassifier(config, golden_cases)
    except Exception as exc:
        print(f"Warning: LLM classification unavailable; falling back to keyword tags: {exc}", file=sys.stderr)
        return None


def make_semantic_scorer(config: dict, golden_cases: dict | None = None) -> "SemanticScorer | None":
    semantic_config = config.get("semanticScoring", {})
    if not semantic_config.get("enabled", True):
        return None
    try:
        return SemanticScorer(config, golden_cases or {"cases": []})
    except Exception as exc:
        print(f"Warning: semantic scoring unavailable; falling back to keyword scoring: {exc}", file=sys.stderr)
        return None


def make_chinese_translator(config: dict) -> "ChineseTranslator | None":
    translation_config = config.get("translation", {})
    if not translation_config.get("enabled", True):
        return None
    try:
        return ChineseTranslator(config)
    except Exception as exc:
        print(f"Warning: Chinese translation unavailable; using placeholder summaries: {exc}", file=sys.stderr)
        return None


class ChineseTranslator:
    def __init__(self, config: dict):
        translation_config = config.get("translation", {})
        self.target_language = translation_config.get("targetLanguage", "Simplified Chinese")
        self.llm = make_claude_chat_model(claude_settings(config, translation_config), "Chinese translation")

    def translate(self, summary: str) -> str:
        try:
            translated = self.llm.invoke(TRANSLATION_PROMPT.format(summary=summary)).strip()
            return translated or MISSING_ZH_SUMMARY
        except Exception as exc:
            warn_once("translation_runtime", f"Warning: Chinese translation failed during runtime; using placeholders: {exc}")
            return MISSING_ZH_SUMMARY

    def translate_bundle(self, title: str, summary: str, reason: str) -> dict:
        """Translate title, summary and selection reason in one call; falls back to English."""
        fallback = {"title": title, "summary": MISSING_ZH_SUMMARY, "reason": reason}
        try:
            content = self.llm.invoke(TRANSLATION_BUNDLE_PROMPT.format(title=title, summary=summary or title, reason=reason or "n/a"))
        except Exception as exc:
            warn_once("translation_runtime", f"Warning: Chinese translation failed during runtime; using placeholders: {exc}")
            return fallback
        try:
            payload = parse_json_object(content)
        except ValueError:
            translated = content.strip()
            return {"title": title, "summary": translated or MISSING_ZH_SUMMARY, "reason": reason}
        return {
            "title": str(payload.get("title") or title).strip(),
            "summary": str(payload.get("summary") or MISSING_ZH_SUMMARY).strip(),
            "reason": str(payload.get("reason") or reason).strip(),
        }


class ArticleClassifier:
    def __init__(self, config: dict, golden_cases: dict):
        self.config = config
        self.golden_cases = golden_cases
        classification_config = config.get("classification", {})
        self.llm = make_claude_chat_model(claude_settings(config, classification_config), "GP and sector classification")

    def classify(self, item: dict) -> dict:
        article_body = document_for_semantic_scoring(item)
        prompt = CLASSIFICATION_PROMPT.format(
            gp_list="\n".join(f"- {gp}" for gp in self.config.get("gps", list(GP_ALIASES))),
            strategy_list=document_strategy_list(),
            bad_history_logs=format_golden_cases(self.golden_cases, limit=8),
            article_title=item.get("title", ""),
            article_body=article_body,
        )
        try:
            content = self.llm.invoke(prompt)
        except Exception as exc:
            warn_once("classification_runtime", f"Warning: LLM classification failed during runtime; using keyword tags: {exc}")
            return default_classification(reason="LLM classification unavailable at runtime")
        try:
            payload = parse_json_object(content)
        except ValueError:
            return default_classification(reason="LLM classification returned invalid JSON")

        def as_list(key: str) -> list:
            value = payload.get(key, [])
            return [str(v).strip() for v in value] if isinstance(value, list) else []

        importance = payload.get("importance")
        try:
            importance = None if importance is None else max(0.0, min(1.0, float(importance)))
        except (TypeError, ValueError):
            importance = None
        # Accept the legacy "sectors" key as strategies for backwards compatibility.
        strategies = as_list("strategies") or as_list("sectors")
        return {
            "gps": as_list("gps"),
            "strategies": strategies,
            "sectors": strategies,
            "events": [event for event in as_list("events") if event in EVENT_IDS],
            "importance": importance,
            "exclude": bool(payload.get("exclude")),
            "reason": str(payload.get("reason", "")),
        }


class SemanticScorer:
    def __init__(self, config: dict, golden_cases: dict):
        self.config = config
        self.semantic_config = config.get("semanticScoring", {})
        self.golden_cases = golden_cases
        self.query_cache = self.load_query_cache()
        self.backend = self.load_backend()
        self.failed = False

    def score(self, item: dict) -> float:
        document = document_for_semantic_scoring(item)
        gps = item.get("gps") or []
        try:
            queries = self.queries_for_gps(gps)
        except Exception as exc:
            self.failed = True
            warn_once("semantic_query_runtime", f"Warning: semantic query generation failed during runtime; using keyword score only: {exc}")
            return 0
        if not document or not queries:
            return 0
        try:
            if hasattr(self.backend, "score_many"):
                avg_raw = self.backend.score_many(queries, document)
            else:
                raw_scores = [self.backend.score(query, document) for query in queries]
                avg_raw = sum(raw_scores) / len(raw_scores)
        except Exception as exc:
            self.failed = True
            warn_once("semantic_score_runtime", f"Warning: semantic scoring failed during runtime; using keyword score only: {exc}")
            return 0
        return round(self.normalize_score(avg_raw), 2)

    def normalize_score(self, raw_score: float) -> float:
        raw_min = float(getattr(self.backend, "raw_min", self.semantic_config.get("rawScoreMin", 0)))
        raw_max = float(getattr(self.backend, "raw_max", self.semantic_config.get("rawScoreMax", 30)))
        scale = float(self.semantic_config.get("scoreScale", 12))
        if raw_max <= raw_min:
            return 0
        normalized = (raw_score - raw_min) / (raw_max - raw_min)
        normalized = max(0, min(1, normalized))
        return normalized * scale

    def load_backend(self):
        # SEMANTIC_BACKEND=auto|pylate|claude_judge overrides the config for one run.
        backend_name = os.environ.get("SEMANTIC_BACKEND") or self.semantic_config.get("backend", "auto")
        pylate_error = ""
        if backend_name in {"auto", "pylate"}:
            try:
                backend = PyLateColbertBackend(self.semantic_config)
                print(f"Semantic scoring backend: PyLate ColBERT ({backend.model_name})", file=sys.stderr)
                return backend
            except Exception as exc:
                if backend_name == "pylate":
                    raise
                pylate_error = f"; PyLate unavailable: {exc}"
        if backend_name in {"auto", "claude_judge"}:
            backend = ClaudeRelevanceBackend(self.config, self.semantic_config)
            print(f"Semantic scoring backend: Claude relevance judge ({backend.llm.model}){pylate_error}", file=sys.stderr)
            return backend
        raise RuntimeError(f"Unknown semantic scoring backend: {backend_name}")

    def load_query_cache(self) -> dict:
        cache_path = ROOT / self.semantic_config.get("queryCachePath", "data/semantic_queries.json")
        if cache_path.exists():
            return load_json(cache_path)
        return {}

    def queries_for_gps(self, gps: list[str]) -> list[str]:
        active_gps = gps or ["Portfolio"]
        queries: list[str] = []
        for gp in active_gps:
            queries.extend(self.load_or_generate_hyde_queries(gp))
        return queries

    def load_or_generate_hyde_queries(self, gp: str) -> list[str]:
        cache_path = ROOT / self.semantic_config.get("queryCachePath", "data/semantic_queries.json")
        bad_history_logs = format_golden_cases(self.golden_cases, gp=gp, limit=6)
        prompt = SEMANTIC_PROMPT.format(gp_name=gp, bad_history_logs=bad_history_logs)
        settings = claude_settings(self.config, self.semantic_config)
        # The model name is part of the hash so switching models regenerates the examples.
        prompt_hash = hashlib.sha1(f"{settings['model']}\n{prompt}".encode("utf-8")).hexdigest()
        cached_by_gp = self.query_cache.setdefault("hydeByGp", {})
        cached = cached_by_gp.get(gp, {})
        if cached.get("promptHash") == prompt_hash and cached.get("relevant"):
            return cached["relevant"]

        relevant, not_relevant = generate_hyde_queries_with_claude(prompt, settings)
        cached_by_gp[gp] = {
            "promptHash": prompt_hash,
            "model": settings["model"],
            "relevant": relevant,
            "notRelevant": not_relevant,
        }
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(json.dumps(self.query_cache, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return relevant


def generate_hyde_queries_with_claude(prompt: str, settings: dict) -> tuple[list[str], list[str]]:
    llm = make_claude_chat_model(settings, "semantic query generation")
    content = llm.invoke(prompt)
    relevant, not_relevant = parse_hyde_sections(content)
    if len(relevant) != 3:
        raise RuntimeError(f"Expected 3 Claude HyDE relevant descriptions, got {len(relevant)}")
    return relevant, not_relevant[:2]


def claude_settings(config: dict, section: dict | None = None) -> dict:
    """Merge the top-level `claude` config block with optional per-stage overrides.

    Per-stage keys (`claudeModel`, `claudeEffort`, `claudeApiKeyEnv`, `claudeMaxTokens`)
    live inside `classification`, `semanticScoring`, or `translation`.
    """
    base = config.get("claude", {}) if isinstance(config, dict) else {}
    section = section or {}
    return {
        "model": section.get("claudeModel") or base.get("model") or DEFAULT_CLAUDE_MODEL,
        "apiKeyEnv": section.get("claudeApiKeyEnv") or base.get("apiKeyEnv") or DEFAULT_CLAUDE_API_KEY_ENV,
        "effort": section.get("claudeEffort") or base.get("effort") or DEFAULT_CLAUDE_EFFORT,
        "maxTokens": int(section.get("claudeMaxTokens") or base.get("maxTokens") or DEFAULT_CLAUDE_MAX_TOKENS),
        "refusalFallback": bool(base.get("refusalFallback", True)),
    }


def make_claude_chat_model(settings: dict, purpose: str) -> "ClaudeChat":
    return ClaudeChat(settings, purpose)


class ClaudeChat:
    """Thin wrapper over the Anthropic SDK: one prompt in, the text reply out."""

    def __init__(self, settings: dict, purpose: str):
        api_key_env = settings["apiKeyEnv"]
        api_key = os.environ.get(api_key_env)
        if not api_key:
            raise RuntimeError(f"Set {api_key_env} to use Claude {purpose}")
        try:
            import anthropic
        except Exception as exc:
            raise RuntimeError("Install the anthropic package (pip install -r requirements-semantic.txt) to use Claude") from exc

        self.client = anthropic.Anthropic(api_key=api_key)
        self.model = settings["model"]
        self.effort = settings["effort"]
        self.max_tokens = settings["maxTokens"]
        self.refusal_fallback = settings["refusalFallback"]
        self.purpose = purpose

    def invoke(self, prompt: str) -> str:
        request = {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "output_config": {"effort": self.effort},
            "messages": [{"role": "user", "content": prompt}],
        }
        if self.refusal_fallback:
            # Server-side refusal fallback: if the safety classifier declines, the API
            # re-runs the same request on a fallback model inside the same call.
            response = self.client.beta.messages.create(
                betas=[REFUSAL_FALLBACK_BETA],
                extra_body={"fallbacks": "default"},
                **request,
            )
        else:
            response = self.client.messages.create(**request)

        if response.stop_reason == "refusal":
            details = getattr(response, "stop_details", None)
            explanation = getattr(details, "explanation", "") if details else ""
            raise RuntimeError(f"Claude declined the {self.purpose} request: {explanation or 'no explanation given'}")
        text = "".join(block.text for block in response.content if getattr(block, "type", "") == "text").strip()
        if not text:
            raise RuntimeError(f"Claude returned no text for {self.purpose} (stop_reason={response.stop_reason})")
        return text


def translate_existing_chinese_summaries(data: dict, translator: "ChineseTranslator | None") -> int:
    if not translator:
        return 0
    changed = 0
    translated_by_key: dict[str, dict] = {}
    for date_digest in data.get("dates", {}).values():
        for item in iter_digest_items(date_digest):
            if not needs_chinese_summary(item, translator.target_language) and not needs_chinese_title(item):
                continue
            key = item.get("id") or item.get("url") or item.get("summary")
            if key not in translated_by_key:
                reason = item.get("classificationBreakdown", {}).get("llmReason", "")
                translated_by_key[key] = translator.translate_bundle(item.get("title", ""), item.get("summary", ""), reason)
            bundle = translated_by_key[key]
            item["titleZh"] = bundle["title"]
            item["summaryZh"] = bundle["summary"]
            item["summaryZhLanguage"] = translator.target_language
            item.setdefault("classificationBreakdown", {})["llmReasonZh"] = bundle["reason"]
            changed += 1
    return changed


def needs_chinese_title(item: dict) -> bool:
    title = (item.get("title") or "").strip()
    title_zh = (item.get("titleZh") or "").strip()
    return bool(title) and (not title_zh or title_zh == title)


def sanitize_saved_news(data: dict) -> int:
    changed = 0
    fields = ["summary", "summaryZh", "lede", "articleExcerpt"]
    for date_digest in data.get("dates", {}).values():
        for item in iter_digest_items(date_digest):
            for field in fields:
                value = item.get(field)
                if not isinstance(value, str):
                    continue
                cleaned = clean_html(value)
                if cleaned != value:
                    item[field] = cleaned
                    changed += 1
    return changed


def iter_digest_items(date_digest: dict):
    yielded = set()
    for item in date_digest.get("items", []):
        key = id(item)
        yielded.add(key)
        yield item
    for items in date_digest.get("byGp", {}).values():
        for item in items:
            key = id(item)
            if key in yielded:
                continue
            yielded.add(key)
            yield item


def needs_chinese_summary(item: dict, target_language: str | None = None) -> bool:
    summary_zh = (item.get("summaryZh") or "").strip()
    if not summary_zh or summary_zh == MISSING_ZH_SUMMARY:
        return True
    return bool(target_language and item.get("summaryZhLanguage") != target_language)


class PyLateColbertBackend:
    raw_min = 0

    HUB_PROBE_TIMEOUT = 6

    def __init__(self, semantic_config: dict):
        self.raw_max = float(semantic_config.get("rawScoreMax", 30))
        self.model_name = semantic_config.get("colbertModel", "colbert-ir/colbertv2.0")
        # Probe before importing pylate: the import alone loads torch and transformers
        # (tens of seconds), and huggingface_hub would then retry every model file for
        # minutes when the Hub is unreachable (blocked network, TLS-inspecting proxy).
        if os.environ.get("HF_HUB_OFFLINE") not in {"1", "true", "True"} and not self.hub_reachable():
            if self.model_is_cached():
                os.environ["HF_HUB_OFFLINE"] = "1"
                print(
                    f"Hugging Face unreachable within {self.HUB_PROBE_TIMEOUT}s; loading {self.model_name} from the local cache in offline mode.",
                    file=sys.stderr,
                )
            else:
                raise RuntimeError(
                    f"huggingface.co unreachable within {self.HUB_PROBE_TIMEOUT}s and {self.model_name} is not in the local cache"
                )
        from pylate import models, rank

        self.rank = rank
        self.model = models.ColBERT(model_name_or_path=self.model_name)

    def hub_reachable(self) -> bool:
        url = f"https://huggingface.co/api/models/{self.model_name}"
        try:
            with urllib.request.urlopen(request_for(url), timeout=self.HUB_PROBE_TIMEOUT) as response:
                return 200 <= response.status < 400
        except Exception:
            return False

    def model_is_cached(self) -> bool:
        try:
            from huggingface_hub import try_to_load_from_cache
        except Exception:
            return False
        try:
            return isinstance(try_to_load_from_cache(self.model_name, "config.json"), str)
        except Exception:
            return False

    def score(self, query: str, document: str) -> float:
        queries_embeddings = self.model.encode([query], is_query=True)
        documents_embeddings = self.model.encode([[document]], is_query=False)
        reranked = self.rank.rerank(
            documents_ids=[["candidate"]],
            queries_embeddings=queries_embeddings,
            documents_embeddings=documents_embeddings,
        )
        return extract_pylate_score(reranked)


class ClaudeRelevanceBackend:
    """Fallback semantic backend: Claude rates the article against the HyDE examples (0-1).

    Claude has no embeddings endpoint, so instead of cosine similarity this backend
    makes one judged-relevance call per article covering all HyDE examples at once.
    """

    raw_min = 0
    raw_max = 1

    def __init__(self, config: dict, semantic_config: dict):
        self.llm = make_claude_chat_model(claude_settings(config, semantic_config), "semantic relevance scoring")

    def score(self, query: str, document: str) -> float:
        return self.score_many([query], document)

    def score_many(self, queries: list[str], document: str) -> float:
        examples = "\n".join(f"{index}. {query}" for index, query in enumerate(queries, start=1))
        content = self.llm.invoke(RELEVANCE_PROMPT.format(examples=examples, document=document))
        payload = parse_json_object(content)
        try:
            score = float(payload.get("score", 0))
        except (TypeError, ValueError):
            score = 0.0
        return max(0.0, min(1.0, score))


def default_classification(reason: str = "") -> dict:
    return {"gps": [], "strategies": [], "sectors": [], "events": [], "importance": None, "exclude": False, "reason": reason}


def valid_ordered_labels(labels: list[str], allowed: list[str]) -> list[str]:
    normalized = {str(label).strip().lower(): str(label).strip() for label in allowed}
    matched = []
    for label in labels:
        key = str(label).strip().lower()
        if key in normalized:
            matched.append(normalized[key])
    return union_ordered(allowed, matched)


def union_ordered(order: list[str], *label_lists: list[str]) -> list[str]:
    selected = {label for labels in label_lists for label in labels}
    ordered = [label for label in order if label in selected]
    extras = [label for label in selected if label not in ordered]
    return ordered + sorted(extras)


def parse_json_object(content: str) -> dict:
    cleaned = re.sub(r"^```(?:json)?|```$", "", content.strip(), flags=re.IGNORECASE | re.MULTILINE).strip()
    try:
        payload = json.loads(cleaned)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", cleaned, flags=re.DOTALL)
        if not match:
            raise ValueError("No JSON object found")
        payload = json.loads(match.group(0))
    if not isinstance(payload, dict):
        raise ValueError("JSON payload is not an object")
    return payload


def parse_hyde_sections(content: str) -> tuple[list[str], list[str]]:
    relevant = []
    not_relevant = []
    active = None
    for line in content.splitlines():
        lowered = line.strip().lower()
        if lowered.startswith("relevant"):
            active = "relevant"
            continue
        if lowered.startswith("not relevant"):
            active = "not_relevant"
            continue
        cleaned = re.sub(r"^\s*\d+[\).\s-]+", "", line).strip()
        if not cleaned:
            continue
        if active == "relevant":
            relevant.append(cleaned)
        elif active == "not_relevant":
            not_relevant.append(cleaned)
    return relevant[:3], not_relevant[:2]


def format_golden_cases(golden_cases: dict, gp: str | None = None, limit: int = 8) -> str:
    cases = golden_cases.get("cases", []) if isinstance(golden_cases, dict) else []
    selected = []
    for case in cases:
        if gp and gp != "Portfolio":
            original_gps = case.get("original", {}).get("gps", [])
            corrected_gps = case.get("corrected", {}).get("gps", [])
            if gp not in original_gps and gp not in corrected_gps:
                continue
        selected.append(case)
        if len(selected) >= limit:
            break
    if not selected:
        return "None yet."
    lines = []
    for index, case in enumerate(selected, start=1):
        original = case.get("original", {})
        corrected = case.get("corrected", {})
        lines.append(
            f"{index}. Title: {case.get('title', '')}\n"
            f"   Article excerpt: {textwrap.shorten(case.get('articleText', ''), width=520, placeholder='...')}\n"
            f"   Wrong answer: GP={original.get('gps', [])}; sectors={original.get('sectors', [])}\n"
            f"   Correct answer: GP={corrected.get('gps', [])}; sectors={corrected.get('sectors', [])}; "
            f"exclude={corrected.get('exclude', False)}; reason={case.get('reason', '')}"
        )
    return "\n".join(lines)


def extract_pylate_score(reranked) -> float:
    if not reranked:
        return 0
    first_query = reranked[0] if isinstance(reranked, list) else reranked
    if not first_query:
        return 0
    first_doc = first_query[0] if isinstance(first_query, list) else first_query
    if isinstance(first_doc, dict):
        return float(first_doc.get("score", first_doc.get("similarity", 0)))
    return float(getattr(first_doc, "score", getattr(first_doc, "similarity", 0)))


def document_for_semantic_scoring(item: dict) -> str:
    body = clean_html(item.get("articleText") or item.get("description") or item.get("summary") or "")
    first_words = " ".join(body.split()[:200])
    return f"{item.get('title', '')}. {first_words}".strip()


def prune_old_dates(data: dict, date_key: str, retention_days: int) -> None:
    cutoff = dt.date.fromisoformat(date_key) - dt.timedelta(days=retention_days - 1)
    for date_key in list(data.get("dates", {})):
        try:
            date_value = dt.date.fromisoformat(date_key)
        except ValueError:
            continue
        if date_value < cutoff:
            del data["dates"][date_key]


if __name__ == "__main__":
    raise SystemExit(main())
