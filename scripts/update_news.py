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
SEMANTIC_PROMPT = """You are helping build a semantic search filter for an investment-news monitoring
system. Below is a canonical description of a topic we track for private credit
investors. Rewrite it into 3 alternative versions that describe the SAME topic
using different vocabulary, framing, and level of technicality a financial
journalist might use — so we can catch articles worded differently than our
keyword list.

Rules:

- Do not introduce new topics or broaden scope beyond what is described.
- Vary between: (a) a plain-English framing, (b) an industry/trade-press framing,
  (c) a deal-flow / transaction framing.
- Keep each version to 1-2 sentences.
- Output as a numbered list, nothing else.

Canonical description:
"{keyword_rule_in_prose}"
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


def main() -> int:
    parser = argparse.ArgumentParser(description="Update the private-credit news dashboard.")
    parser.add_argument("--date", default=dt.date.today().isoformat(), help="Digest date, YYYY-MM-DD.")
    parser.add_argument("--dry-run", action="store_true", help="Print selected items without writing.")
    parser.add_argument("--today-only", action="store_true", help="Fetch, score, and merge only same-day news.")
    args = parser.parse_args()

    result = update_news(args.date, dry_run=args.dry_run, today_only=args.today_only)
    if args.dry_run:
        print(json.dumps(result["selectedByDate"], ensure_ascii=False, indent=2))
    else:
        mode = "today-only" if result["todayOnly"] else "full-window"
        print(
            f"Ran {mode} update; wrote {result['selectedItemCount']} item(s) across "
            f"{result['selectedDateCount']} published date(s) to {DATA_PATH}; "
            f"backfilled {result['translatedCount']} Chinese summarie(s)"
        )
    return 0


def update_news(date_key: str | None = None, dry_run: bool = False, today_only: bool = False) -> dict:
    date_key = date_key or dt.date.today().isoformat()
    config = load_json(CONFIG_PATH)
    data = load_json(DATA_PATH)
    translator = make_chinese_translator(config)

    retention_days = int(config.get("retentionDays") or data.get("retentionDays") or 90)
    lookback_days = 1 if today_only else int(config.get("lookbackDays", 14))
    semantic_scorer = make_semantic_scorer(config)
    selected_by_gp = select_items_by_gp(
        config,
        date_key,
        lookback_days,
        semantic_scorer,
        translator,
        same_day_only=today_only,
    )
    selected_by_date = group_selected_by_date(selected_by_gp)
    selected_item_count = sum(len(items) for items in selected_by_gp.values())

    result = {
        "date": date_key,
        "todayOnly": today_only,
        "selectedByDate": selected_by_date,
        "selectedItemCount": selected_item_count,
        "selectedDateCount": len(selected_by_date),
        "translatedCount": 0,
        "dataPath": str(DATA_PATH),
    }

    if dry_run:
        return result

    if today_only:
        merge_today_digest(data, date_key, selected_by_date.get(date_key, {}))
    else:
        merge_digests_by_published_date(data, date_key, selected_by_date, retention_days)
        result["translatedCount"] = translate_existing_chinese_summaries(data, translator)
    DATA_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result


def load_json(path: Path) -> dict:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


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
    value = html.unescape(value or "")
    value = re.sub(r"<[^>]+>", " ", value)
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
    same_day_only: bool = False,
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
            same_day_only=same_day_only,
        )

    general_candidates = fetch_google_candidates(config.get("sourceQueries", []), lookback_days)
    general_candidates = merge_items(general_candidates, fetch_rss_candidates(config.get("rssFeeds", [])))
    general_selected = select_items(
        general_candidates,
        config,
        date_key,
        lookback_days,
        None,
        max_items,
        semantic_scorer,
        translator,
        same_day_only=same_day_only,
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
    same_day_only: bool = False,
) -> list[dict]:
    scored = []
    target_date = dt.date.fromisoformat(date_key)
    cutoff = target_date - dt.timedelta(days=lookback_days)
    tomorrow = target_date + dt.timedelta(days=1)
    for item in candidates:
        published = dt.date.fromisoformat(item["publishedAt"])
        if same_day_only and published != target_date:
            continue
        if not same_day_only and (published < cutoff or published > tomorrow):
            continue
        enriched = enrich_item(item, config, focus_gp, semantic_scorer, translator)
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
) -> dict:
    if semantic_scorer and not item.get("articleText"):
        item = dict(item)
        item["articleText"] = fetch_article_text(item["url"])
    blob = f"{item['title']} {item.get('description', '')} {item.get('source', '')}".lower()
    gps = match_terms(blob, GP_ALIASES)
    sectors = match_terms(blob, SECTOR_KEYWORDS)
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
    semantic_score = semantic_scorer.score(item) if semantic_scorer else 0
    final_score = keyword_score + semantic_score

    summary = summarize(item)
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
        "region": region,
        "gps": gps,
        "sectors": sectors,
        "curation": "rss_filter",
        "score": final_score,
        "scoreBreakdown": {
            "keywordScore": keyword_score,
            "semanticScore": semantic_score,
            "finalScore": final_score,
            "semanticEnabled": bool(semantic_scorer),
        },
    }


def score_threshold(config: dict, semantic_scorer: "SemanticScorer | None") -> int:
    if semantic_scorer:
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


def merge_today_digest(data: dict, date_key: str, selected_by_gp: dict[str, list[dict]]) -> None:
    data["updatedAt"] = dt.datetime.now(dt.timezone.utc).isoformat()
    data.setdefault("dates", {})
    merge_digest_for_date(data, date_key, selected_by_gp)


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
    existing_urls = {normalize_url(item["url"]) for item in merged}
    for item in incoming:
        url = normalize_url(item["url"])
        if url not in existing_urls:
            merged.append(item)
            existing_urls.add(url)
    return merged


def flatten_unique(by_gp: dict[str, list[dict]]) -> list[dict]:
    return merge_items([], [item for items in by_gp.values() for item in items])


def config_gp_order(data: dict) -> list[str]:
    return data.get("scope", {}).get("gps") or list(GP_ALIASES)


def make_semantic_scorer(config: dict) -> "SemanticScorer | None":
    semantic_config = config.get("semanticScoring", {})
    if not semantic_config.get("enabled", True):
        return None
    try:
        return SemanticScorer(config)
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
        response = self.llm.invoke(TRANSLATION_PROMPT.format(summary=summary))
        translated = getattr(response, "content", str(response)).strip()
        return translated or MISSING_ZH_SUMMARY


class SemanticScorer:
    def __init__(self, config: dict):
        self.config = config
        self.semantic_config = config.get("semanticScoring", {})
        self.queries = self.load_or_generate_queries()
        self.backend = self.load_backend()

    def score(self, item: dict) -> float:
        document = document_for_semantic_scoring(item)
        if not document or not self.queries:
            return 0
        raw_scores = [self.backend.score(query, document) for query in self.queries]
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

    def load_or_generate_queries(self) -> list[str]:
        cache_path = ROOT / self.semantic_config.get("queryCachePath", "data/semantic_queries.json")
        canonical = canonical_requirement_text(self.config)
        canonical_hash = hashlib.sha1(canonical.encode("utf-8")).hexdigest()
        cached = load_json(cache_path) if cache_path.exists() else {}
        if cached.get("canonicalHash") == canonical_hash and cached.get("queries"):
            return cached["queries"]

        queries = generate_semantic_queries_with_qwen(canonical, self.semantic_config)
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(
            json.dumps({"canonicalHash": canonical_hash, "queries": queries}, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        return queries


def canonical_requirement_text(config: dict) -> str:
    gps = ", ".join(config.get("gps") or list(GP_ALIASES))
    sectors = ", ".join(SECTOR_KEYWORDS)
    return (
        "Investment news for private credit investors with a primarily US focus and selective Europe coverage. "
        f"Track only credit-related activity involving these GPs or their credit platforms: {gps}. "
        f"Relevant sub-sectors are {sectors}. Relevant articles include direct lending, private debt, BDC activity, "
        "CLOs, asset-backed lending or securitization, mortgage and real estate credit, aircraft or aviation finance, "
        "software borrower credit stress, GP stakes or GP-led liquidity solutions, financing transactions, fund raises, "
        "portfolio stress, valuation marks, defaults, restructurings, or material manager strategy changes."
    )


def generate_semantic_queries_with_qwen(canonical: str, semantic_config: dict) -> list[str]:
    prompt = SEMANTIC_PROMPT.format(keyword_rule_in_prose=canonical)
    llm = make_qwen_chat_model(semantic_config, "semantic query generation")
    response = llm.invoke(prompt)
    content = getattr(response, "content", str(response))
    queries = parse_numbered_list(content)
    if len(queries) != 3:
        raise RuntimeError(f"Expected 3 Qwen semantic query rewrites, got {len(queries)}")
    return queries


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


def parse_numbered_list(content: str) -> list[str]:
    queries = []
    for line in content.splitlines():
        cleaned = re.sub(r"^\s*\d+[\).\s-]+", "", line).strip()
        if cleaned:
            queries.append(cleaned)
    return queries[:3]


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
