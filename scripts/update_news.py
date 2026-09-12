#!/usr/bin/env python3
"""Fetch, score, and append relevant credit news to data/news.json.

The updater uses free RSS/Atom feeds, keyword scoring, semantic scoring through
LangChain + Qwen, optional PyLate/ColBERTv2 MaxSim, and Qwen Traditional Chinese
translation when the configured dependencies and API key are available.
"""

from __future__ import annotations

import argparse
import datetime as dt
import email.utils
import hashlib
import html
import json
import math
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

TRACKED SUB-SECTORS:
- software
- private credit / direct lending
- GP stakes
- aircraft leasing
- asset-backed lending
- real estate (credit/financing angle only, not equity/development)
- mortgage
- CLO

TASK:
Read the article below. Determine:
1. Which tracked GP(s), if any, it is about (credit-relevant activity only).
2. Which tracked sub-sector(s), if any, it belongs to.
3. Whether it should be EXCLUDED because it's about a tracked GP's non-credit
   business (equity buyout, infrastructure, sports/media assets, etc.) with no
   credit/financing angle.

HERE ARE SOME PRECEDENTIAL WRONG CASES:
{bad_history_logs}

ARTICLE:
Title: {article_title}
Text: {article_body}

Output valid JSON only, with this shape:
{{
  "gps": ["tracked GP name"],
  "sectors": ["tracked sub-sector"],
  "exclude": false,
  "reason": "short explanation"
}}
"""
TRANSLATION_PROMPT = """Translate the following investment-news summary into Traditional Chinese.

Rules:
- Preserve company names, fund names, ticker symbols, dates, and monetary figures.
- Keep the meaning precise and suitable for a credit investor.
- Do not add facts, interpretation, markdown, labels, or explanations.
- Output only the translated summary.

English summary:
{summary}
"""
MISSING_ZH_SUMMARY = "此條目的中文摘要尚未人工整理；請先參考英文摘要與原文連結。"

GP_ALIASES = {
    "Blue Owl": ["blue owl", "owl rock"],
    "OTF": ["blue owl technology finance", "nyse: otf", " otf "],
    "Pretium": ["pretium"],
    "KKR": ["kkr", "global atlantic"],
    "PAG": ["pag"],
    "Bayview": ["bayview"],
    "CIFC": ["cifc"],
    "Basepoint": ["basepoint"],
    "NB": ["neuberger berman", " nb "],
    "Apollo": ["apollo"],
    "Bain Capital": ["bain capital"],
    "Guggenheim": ["guggenheim"],
    "HSBC AM": ["hsbc asset management", "hsbc am"],
}

SECTOR_KEYWORDS = {
    "software": ["software", "technology", "tech borrower", "saas", "data center"],
    "private credit / direct lending": [
        "private credit",
        "direct lending",
        "private debt",
        "bdc",
        "senior credit facility",
        "unitranche",
        "middle market loan",
    ],
    "GP stakes": ["gp stake", "gp-led", "continuation vehicle", "secondary", "secondaries"],
    "aircraft leasing": ["aircraft", "aviation", "airline", "leasing", "hangar", "fleet"],
    "asset-backed lending": [
        "asset-backed",
        "asset based",
        "abl",
        "securitization",
        "securitisation",
        "receivables",
        "subscription cash flow",
    ],
    "real estate": ["real estate", "property", "commercial real estate", "developer", "construction", "housing"],
    "mortgage": ["mortgage", "residential loan", "home loan", "servicing", "msr", "manufactured housing"],
    "CLO": ["clo", "collateralized loan obligation", "collateralised loan obligation"],
}

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


def main() -> int:
    parser = argparse.ArgumentParser(description="Update the private-credit news dashboard.")
    parser.add_argument("--date", default=dt.date.today().isoformat(), help="Digest date, YYYY-MM-DD.")
    parser.add_argument("--dry-run", action="store_true", help="Print selected items without writing.")
    parser.add_argument("--recent-days", type=int, help="Fetch, score, and merge only this many recent calendar days.")
    args = parser.parse_args()

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
    selected_by_gp = select_items_by_gp(
        config,
        date_key,
        lookback_days,
        semantic_scorer,
        translator,
        classifier,
        recent_days=recent_days,
    )
    selected_by_date = group_selected_by_date(selected_by_gp)
    selected_item_count = sum(len(items) for items in selected_by_gp.values())

    result = {
        "date": date_key,
        "recentDays": recent_days,
        "selectedByDate": selected_by_date,
        "selectedItemCount": selected_item_count,
        "selectedDateCount": len(selected_by_date),
        "translatedCount": 0,
        "sanitizedCount": 0,
        "dataPath": str(DATA_PATH),
    }

    if dry_run:
        return result

    if recent_days:
        merge_recent_digests(data, date_key, selected_by_date)
    else:
        merge_digests_by_published_date(data, date_key, selected_by_date, retention_days)
        result["translatedCount"] = translate_existing_chinese_summaries(data, translator)
    result["sanitizedCount"] = sanitize_saved_news(data)
    DATA_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result


def load_json(path: Path) -> dict:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def load_golden_cases() -> dict:
    if GOLDEN_CASES_PATH.exists():
        return load_json(GOLDEN_CASES_PATH)
    return {"cases": []}


def fetch_google_candidates(queries: list[str], lookback_days: int) -> list[dict]:
    candidates = []
    for query in queries:
        url = google_news_rss_url(query, lookback_days)
        try:
            with urllib.request.urlopen(url, timeout=20) as response:
                payload = response.read()
        except Exception as exc:
            print(f"Warning: failed to fetch {query!r}: {exc}", file=sys.stderr)
            continue
        try:
            candidates.extend(parse_feed(payload, source_hint="Google News"))
        except ET.ParseError as exc:
            print(f"Warning: failed to parse Google News RSS for {query!r}: {exc}", file=sys.stderr)
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
) -> dict[str, list[dict]]:
    gp_order = config.get("gps") or list(GP_ALIASES)
    gp_queries = config.get("gpQueries", {})
    max_items = int(config.get("maxItemsPerGp", 6))
    selected_by_gp = {}

    for gp in gp_order:
        queries = gp_queries.get(gp) or [f"{gp} private credit"]
        candidates = fetch_google_candidates(queries, lookback_days)
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
        )

    general_candidates = fetch_google_candidates(config.get("sourceQueries", []), lookback_days)
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
    )
    for item in general_selected:
        for gp in item.get("gps", []):
            if gp in selected_by_gp:
                selected_by_gp[gp] = merge_items(selected_by_gp[gp], [item])[:max_items]

    return selected_by_gp


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
) -> list[dict]:
    scored = []
    target_date = dt.date.fromisoformat(date_key)
    cutoff = target_date - dt.timedelta(days=(recent_days or lookback_days) - 1)
    for item in candidates:
        published = dt.date.fromisoformat(item["publishedAt"])
        if published < cutoff or published > target_date:
            continue
        enriched = enrich_item(item, config, focus_gp, semantic_scorer, translator, classifier)
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
) -> dict:
    if (semantic_scorer or classifier) and not item.get("articleText"):
        item = dict(item)
        item["articleText"] = fetch_article_text(item["url"])
    blob = f"{item['title']} {item.get('description', '')} {item.get('source', '')}".lower()
    keyword_gps = match_terms(blob, GP_ALIASES)
    keyword_sectors = match_terms(blob, SECTOR_KEYWORDS)
    llm_classification = classifier.classify(item) if classifier else default_classification()
    llm_gps = valid_ordered_labels(llm_classification.get("gps", []), config.get("gps") or list(GP_ALIASES))
    llm_sectors = valid_ordered_labels(llm_classification.get("sectors", []), list(SECTOR_KEYWORDS))
    gps = union_ordered(config.get("gps") or list(GP_ALIASES), keyword_gps, llm_gps)
    sectors = union_ordered(list(SECTOR_KEYWORDS), keyword_sectors, llm_sectors)
    region = detect_region(blob)
    source_bonus = source_score(item.get("source", ""), config.get("preferredSources", []))
    keyword_score = source_bonus + len(gps) * 4 + len(sectors) * 3

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

    summary = summarize(item)
    article_excerpt = document_for_semantic_scoring(item)
    summary_zh = item.get("summaryZh") or ""
    if not summary_zh.strip() or summary_zh.strip() == MISSING_ZH_SUMMARY:
        summary_zh = translate_summary(summary, translator)
    return {
        "id": stable_id(item),
        "title": item["title"],
        "titleZh": item["title"],
        "summary": summary,
        "summaryZh": summary_zh,
        "url": item["url"],
        "source": item.get("source") or "Google News",
        "publishedAt": item["publishedAt"],
        "lede": item.get("description", ""),
        "articleExcerpt": article_excerpt,
        "contentFingerprint": content_fingerprint(
            {
                "title": item["title"],
                "description": item.get("description", ""),
                "publishedAt": item["publishedAt"],
            }
        ),
        "region": region,
        "gps": gps,
        "sectors": sectors,
        "curation": "rss_filter",
        "excludedByClassifier": bool(llm_classification.get("exclude")),
        "classificationBreakdown": {
            "keywordGps": keyword_gps,
            "llmGps": llm_gps,
            "keywordSectors": keyword_sectors,
            "llmSectors": llm_sectors,
            "llmExclude": bool(llm_classification.get("exclude")),
            "llmReason": llm_classification.get("reason", ""),
        },
        "score": final_score,
        "scoreBreakdown": {
            "keywordScore": keyword_score,
            "semanticScore": semantic_score,
            "finalScore": final_score,
            "semanticEnabled": bool(semantic_scorer),
        },
    }


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


def merge_recent_digests(data: dict, run_date_key: str, selected_by_date: dict[str, dict[str, list[dict]]]) -> None:
    data["updatedAt"] = dt.datetime.now(dt.timezone.utc).isoformat()
    data.setdefault("dates", {})
    for published_date, selected_by_gp in selected_by_date.items():
        merge_digest_for_date(data, published_date, selected_by_gp)
    ensure_window_date(data, run_date_key)


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
        semantic_config = config.get("semanticScoring", {})
        self.qwen_config = {
            "qwenModel": translation_config.get("qwenModel") or semantic_config.get("qwenModel", "qwen-plus"),
            "qwenApiKeyEnv": translation_config.get("qwenApiKeyEnv") or semantic_config.get("qwenApiKeyEnv", "DASHSCOPE_API_KEY"),
        }
        self.llm = make_qwen_chat_model(self.qwen_config, "Chinese translation")

    def translate(self, summary: str) -> str:
        try:
            response = self.llm.invoke(TRANSLATION_PROMPT.format(summary=summary))
            translated = getattr(response, "content", str(response)).strip()
            return translated or MISSING_ZH_SUMMARY
        except Exception as exc:
            warn_once("translation_runtime", f"Warning: Chinese translation failed during runtime; using placeholders: {exc}")
            return MISSING_ZH_SUMMARY


class ArticleClassifier:
    def __init__(self, config: dict, golden_cases: dict):
        self.config = config
        self.golden_cases = golden_cases
        classification_config = config.get("classification", {})
        semantic_config = config.get("semanticScoring", {})
        self.qwen_config = {
            "qwenModel": classification_config.get("qwenModel") or semantic_config.get("qwenModel", "qwen-plus"),
            "qwenApiKeyEnv": classification_config.get("qwenApiKeyEnv") or semantic_config.get("qwenApiKeyEnv", "DASHSCOPE_API_KEY"),
        }
        self.llm = make_qwen_chat_model(self.qwen_config, "GP and sector classification")

    def classify(self, item: dict) -> dict:
        article_body = document_for_semantic_scoring(item)
        prompt = CLASSIFICATION_PROMPT.format(
            gp_list="\n".join(f"- {gp}" for gp in self.config.get("gps", list(GP_ALIASES))),
            bad_history_logs=format_golden_cases(self.golden_cases, limit=8),
            article_title=item.get("title", ""),
            article_body=article_body,
        )
        try:
            response = self.llm.invoke(prompt)
            content = getattr(response, "content", str(response))
        except Exception as exc:
            warn_once("classification_runtime", f"Warning: LLM classification failed during runtime; using keyword tags: {exc}")
            return default_classification(reason="LLM classification unavailable at runtime")
        try:
            payload = parse_json_object(content)
        except ValueError:
            return default_classification(reason="LLM classification returned invalid JSON")
        return {
            "gps": payload.get("gps", []) if isinstance(payload.get("gps", []), list) else [],
            "sectors": payload.get("sectors", []) if isinstance(payload.get("sectors", []), list) else [],
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
            raw_scores = [self.backend.score(query, document) for query in queries]
        except Exception as exc:
            self.failed = True
            warn_once("semantic_score_runtime", f"Warning: semantic scoring failed during runtime; using keyword score only: {exc}")
            return 0
        avg_raw = sum(raw_scores) / len(raw_scores)
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
        backend_name = self.semantic_config.get("backend", "auto")
        if backend_name in {"auto", "pylate"}:
            try:
                return PyLateColbertBackend(self.semantic_config)
            except Exception:
                if backend_name == "pylate":
                    raise
        if backend_name in {"auto", "dashscope_dense"}:
            return DashScopeDenseBackend(self.semantic_config)
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
        prompt_hash = hashlib.sha1(prompt.encode("utf-8")).hexdigest()
        cached_by_gp = self.query_cache.setdefault("hydeByGp", {})
        cached = cached_by_gp.get(gp, {})
        if cached.get("promptHash") == prompt_hash and cached.get("relevant"):
            return cached["relevant"]

        relevant, not_relevant = generate_hyde_queries_with_qwen(prompt, self.semantic_config)
        cached_by_gp[gp] = {
            "promptHash": prompt_hash,
            "relevant": relevant,
            "notRelevant": not_relevant,
        }
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(json.dumps(self.query_cache, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return relevant


def generate_hyde_queries_with_qwen(prompt: str, semantic_config: dict) -> tuple[list[str], list[str]]:
    llm = make_qwen_chat_model(semantic_config, "semantic query generation")
    response = llm.invoke(prompt)
    content = getattr(response, "content", str(response))
    relevant, not_relevant = parse_hyde_sections(content)
    if len(relevant) != 3:
        raise RuntimeError(f"Expected 3 Qwen HyDE relevant descriptions, got {len(relevant)}")
    return relevant, not_relevant[:2]


def make_qwen_chat_model(qwen_config: dict, purpose: str):
    api_key_env = qwen_config.get("qwenApiKeyEnv", "DASHSCOPE_API_KEY")
    api_key = os.environ.get(api_key_env)
    if not api_key:
        raise RuntimeError(f"Set {api_key_env} to use LangChain Qwen {purpose}")

    try:
        from langchain_community.chat_models.tongyi import ChatTongyi
    except Exception as exc:
        raise RuntimeError("Install langchain-community and dashscope to use LangChain Qwen") from exc

    return ChatTongyi(
        model=qwen_config.get("qwenModel", "qwen-plus"),
        api_key=api_key,
        temperature=0,
    )


def translate_existing_chinese_summaries(data: dict, translator: "ChineseTranslator | None") -> int:
    if not translator:
        return 0
    changed = 0
    translated_by_key: dict[str, str] = {}
    for date_digest in data.get("dates", {}).values():
        for item in iter_digest_items(date_digest):
            if not needs_chinese_summary(item):
                continue
            key = item.get("id") or item.get("url") or item.get("summary")
            if key not in translated_by_key:
                translated_by_key[key] = translator.translate(item.get("summary", ""))
            item["summaryZh"] = translated_by_key[key]
            changed += 1
    return changed


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


def needs_chinese_summary(item: dict) -> bool:
    summary_zh = (item.get("summaryZh") or "").strip()
    return not summary_zh or summary_zh == MISSING_ZH_SUMMARY


class PyLateColbertBackend:
    raw_min = 0

    def __init__(self, semantic_config: dict):
        from pylate import models, rank

        self.rank = rank
        self.raw_max = float(semantic_config.get("rawScoreMax", 30))
        model_name = semantic_config.get("colbertModel", "colbert-ir/colbertv2.0")
        self.model = models.ColBERT(model_name_or_path=model_name)

    def score(self, query: str, document: str) -> float:
        queries_embeddings = self.model.encode([query], is_query=True)
        documents_embeddings = self.model.encode([[document]], is_query=False)
        reranked = self.rank.rerank(
            documents_ids=[["candidate"]],
            queries_embeddings=queries_embeddings,
            documents_embeddings=documents_embeddings,
        )
        return extract_pylate_score(reranked)


class DashScopeDenseBackend:
    raw_min = 0
    raw_max = 1

    def __init__(self, semantic_config: dict):
        api_key_env = semantic_config.get("qwenApiKeyEnv", "DASHSCOPE_API_KEY")
        api_key = os.environ.get(api_key_env)
        if not api_key:
            raise RuntimeError(f"Set {api_key_env} to use DashScope dense semantic scoring")
        try:
            from langchain_community.embeddings.dashscope import DashScopeEmbeddings
        except Exception as exc:
            raise RuntimeError("Install langchain-community and dashscope to use DashScope dense semantic scoring") from exc

        self.embeddings = DashScopeEmbeddings(
            model=semantic_config.get("denseEmbeddingModel", "text-embedding-v2"),
            dashscope_api_key=api_key,
        )

    def score(self, query: str, document: str) -> float:
        query_vector = self.embeddings.embed_query(query)
        document_vector = self.embeddings.embed_query(document)
        return cosine_similarity(query_vector, document_vector)


def default_classification(reason: str = "") -> dict:
    return {"gps": [], "sectors": [], "exclude": False, "reason": reason}


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


def cosine_similarity(left: list[float], right: list[float]) -> float:
    numerator = sum(a * b for a, b in zip(left, right))
    left_norm = math.sqrt(sum(a * a for a in left))
    right_norm = math.sqrt(sum(b * b for b in right))
    if not left_norm or not right_norm:
        return 0
    return max(0, min(1, numerator / (left_norm * right_norm)))


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
