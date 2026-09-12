# Credit News Dashboard

A small web-based dashboard for monitoring private-credit news by digest date and by GP. It opens on today by default, lets users pick any date inside the rolling 90-day calendar window, shows every required GP as its own same-day section, and supports English / Traditional Chinese page switching.

## Run locally

```bash
python3 -m http.server 4173
```

Then open `http://127.0.0.1:4173`. If that port is already busy, use another port, for example `python3 -m http.server 4174`.

## Public Link
https://gallon00920.github.io/Credit_bearing_news_updater/

## Update news

```bash
python3 scripts/update_news.py
```

The updater fetches Google News RSS search feeds for each required GP plus broader sector queries, scores articles against the configured GP / sub-sector scope with both keyword and semantic scoring, translates missing Chinese summaries, appends selected items into GP-specific buckets under each article's actual publication date, and prunes dates older than the rolling retention window.

To preview without writing:

```bash
python3 scripts/update_news.py --dry-run
```

For the hourly same-day update:

```bash
python3 scripts/update_news.py --today-only
```

Set your Qwen / DashScope key before running the full pipeline:

```bash
export DASHSCOPE_API_KEY="YOUR_API_KEYS"
export HF_TOKEN="YOUR_API_KEYS"
python3 scripts/update_news.py
```

Chinese abstracts:

- New items use the English summary first.
- If `summaryZh` is missing, the updater translates the English summary into Traditional Chinese with the same DashScope Qwen model configured for semantic scoring, currently `qwen-plus`.
- The API key is read from `DASHSCOPE_API_KEY` by default.
- Existing manually written Chinese abstracts are preserved.
- Existing saved items with missing or placeholder Chinese abstracts are backfilled during the full `python3 scripts/update_news.py` run.
- If the API key is not available, the updater keeps a placeholder Chinese summary and continues.

The visible calendar always covers the latest 90 calendar days ending today. The stored data follows the same rolling window: a run on September 11, 2026 keeps June 14, 2026 through September 11, 2026; a run on September 12, 2026 keeps June 15, 2026 through September 12, 2026. Fetched stories are saved under their actual `publishedAt` date, not under the date the updater was run.

## Automated Refresh

The public site is intended to stay fully static. News updates are handled by `.github/workflows/update-news.yml`, which runs the Python updater in GitHub Actions and commits changed JSON data back to the repository.

- Hourly: runs `python3 scripts/update_news.py --today-only`. This fetches current sources, admits only articles whose `publishedAt` date is today, dedupes by normalized URL, applies keyword + semantic scoring, translates new Chinese summaries, and merges only into today's bucket.
- Full-window updates can still be run manually with `python3 scripts/update_news.py` when you want to refresh the rolling 90-day archive, backfill missing Chinese summaries, or capture late-indexed older articles.
- The workflow uses repository secrets named `DASHSCOPE_API_KEY` and optional `HF_TOKEN`.
- Cloudflare Pages, GitHub Pages, or another static host can redeploy automatically from GitHub after the workflow commits changed `data/news.json` or `data/semantic_queries.json`.

Duplicate handling uses two layers:

- Layer 1: normalized URL dedupe strips query strings and fragments, then treats exact canonical URL matches as the same article.
- Layer 2: same-day content dedupe compares a stable title/lede fingerprint and high title-token similarity, so syndicated versions of the same story from different URLs can collapse into one item.
- If duplicates are found, the updater keeps the higher-priority source where possible: SEC/company filings first, then Reuters/Bloomberg/FT/WSJ, then specialist credit trade press, then wires, then aggregators/syndications.
- Replaced duplicates retain the lower-priority copy under `alternateSources` for auditability.

## Source And Update Tools

The current updater is primarily a free RSS / Atom ingestion script, not a browser scraper. It uses `urllib.request` to call RSS, Atom, and Google News RSS search URLs, parses XML with `xml.etree.ElementTree`, scores the returned metadata, and writes selected items into `data/news.json`.

Current source method:

- Google News RSS search: API-like RSS feed calls generated from `config/news_sources.json`.
- GP-specific feeds: one or more search feeds for every required GP: Blue Owl, OTF, Pretium, KKR, PAG, Bayview, CIFC, Basepoint, NB, Apollo, Bain Capital, Guggenheim, and HSBC AM.
- Sector/context feeds: broader searches for private credit, direct lending, CLO, mortgage, real estate credit, asset-backed lending, aircraft / aviation finance, software credit, and GP-stakes topics.
- Direct RSS / Atom feeds: SEC EDGAR Atom for Blue Owl Technology Finance, PR Newswire financial services RSS, Business Wire finance RSS, ABF Journal RSS, HousingWire RSS, and Private Equity Wire RSS.
- HTML source parser: Asset Securitization Report is fetched as a normal HTML page from `https://asreport.americanbanker.com/feed` and parsed with a dedicated listing-page extractor because that URL does not return valid RSS/XML.
- Direct article-page scraping: not used for routine ingestion. If semantic scoring is enabled, the updater may make a simple free HTML fetch of an article URL to extract a meta description or first text words for scoring only; it does not bypass paywalls, submit forms, or run a headless browser.
- Paid/news API integrations: not used in this version.
- Full article extraction: limited. Automated summaries are still based mainly on RSS title/source/snippet metadata; semantic scoring uses title + lede + first available 200 free article words when fetchable.

Preferred sources are configured in `config/news_sources.json` and include Reuters, Bloomberg, Financial Times, Wall Street Journal, Private Credit Daily, Creditflux, Structured Credit Investor, ABL Advisor, Asset Securitization Report, PR Newswire, Business Wire, SEC, and manager-owned press/IR pages when surfaced by RSS.

## News Selection Criteria

The updater decides whether an item aligns with the mandate using keyword scoring first, then semantic scoring when the configured model dependencies and API key are available.

GP and sub-sector categorization now combines keyword detection and LLM classification:

- Keyword detection still scans `title + RSS description/lede + source` against `GP_ALIASES` and `SECTOR_KEYWORDS` in `scripts/update_news.py`.
- Qwen also classifies the article into tracked GP(s), tracked sub-sector(s), and a possible non-credit exclusion flag.
- The saved GP list is the union of keyword-detected GPs and LLM-detected GPs.
- The saved sub-sector list is the union of keyword-detected sub-sectors and LLM-detected sub-sectors.
- If Qwen says the article is about a tracked GP's non-credit business with no lending, financing, or structured-finance angle, the item is excluded before threshold scoring.
- If Qwen is unavailable, the updater falls back to keyword-only tags.

Keyword scoring remains in place after classification:

- GP coverage: each required GP has its own bucket. An item can enter a GP bucket only if the GP or one of its aliases is detected in the title, source, or RSS snippet.
- Credit relevance: items score higher when they mention credit, debt, loans, lending, financing, facilities, securitization, CLOs, BDCs, mortgages, or asset-backed finance.
- Sub-sector fit: items score higher when they match software, private credit / direct lending, GP stakes, aircraft leasing, asset-backed lending, real estate, mortgage, or CLO keywords.
- Mega-manager guardrail: for broad platforms such as KKR, Apollo, Bain Capital, Guggenheim, and HSBC AM, manager-name-only stories are penalized unless the RSS metadata also contains credit, lending, financing, collateral, or tracked-sector context.
- Region fit: US items receive a small preference, Europe items remain eligible through dedicated Europe queries, and other regions are included only when a required GP and credit theme make the item relevant.
- Source quality: preferred institutional, trade, filing, wire, and manager sources receive a score bonus.
- Recency: searches are bounded by the configured lookback window, currently 90 days, and storage/display is bounded by the rolling 90-day window.

Items below `minimumScore` are excluded. Within each GP bucket, the script sorts by relevance score and publication date, then keeps up to `maxItemsPerGp`.

Semantic scoring:

- Semantic scoring is part of the default `python3 scripts/update_news.py` pipeline.
- LangChain calls Qwen through the `ChatTongyi` / DashScope integration, configured as `qwen-plus` by default, to generate HyDE-style examples for each tracked GP: three short descriptions of credit-relevant news and two short descriptions of non-relevant non-credit news.
- The updater scores the article against the three generated credit-relevant examples for its fused GP tags.
- The HyDE prompt template is embedded in `scripts/update_news.py` and cached in `data/semantic_queries.json` so it does not regenerate unless the prompt or precedent data changes.
- With `semanticScoring.backend: "auto"`, the updater first tries PyLate / ColBERTv2 for MaxSim-style late-interaction scoring. If PyLate cannot be imported, it falls back to LangChain DashScope dense embeddings, which install cleanly on Python 3.13.
- The candidate document is `title + lede + first ~200 free article words`.
- The three raw semantic scores are averaged into `semanticScore`.
- `semanticScore` is normalized from the backend's raw range onto the same approximate point scale as the keyword score, currently up to 12 points.
- The final decision score is `finalScore = keywordScore + semanticScore`.
- If semantic scoring is active, the item must clear `semanticScoring.minimumFinalScore`; otherwise it uses `minimumScore`.
- Each saved item includes `scoreBreakdown.keywordScore`, `scoreBreakdown.semanticScore`, and `scoreBreakdown.finalScore` for auditability.

## Report Feedback

Each news card includes a Report button for classification feedback.

- Readers can report wrong GP, wrong sub-sector, or not credit related.
- The report captures the article title, URL, source, publication date, lede/excerpt, original GP/sub-sector tags, corrected GP/sub-sector tags, and the reader's reason.
- Because the public site is static, the browser cannot write directly to `data/golden_cases.json`. Instead, the report is stored in browser local storage and opens a prefilled GitHub Issue containing structured JSON.
- After review, valid reports should be copied into `data/golden_cases.json`.
- To append a reviewed report JSON locally, save the report body to a temporary JSON file and run `python3 scripts/add_golden_case.py path/to/report.json`, then commit `data/golden_cases.json`.
- Future updater runs include those golden cases in the Qwen classification and HyDE prompts under precedential wrong/non-relevant cases.

Semantic dependencies are optional because the base dashboard should still run without model infrastructure. For the full semantic and translation pipeline:

```bash
pip install -r requirements-semantic.txt
export DASHSCOPE_API_KEY="your_api_key_here"
python3 scripts/update_news.py
```

For token-wise ColBERT-style MaxSim scoring, install the PyLate backend:

```bash
pip install -r requirements-colbert.txt
```

You can change the backend, model name, or API-key environment variable in `config/news_sources.json` under `semanticScoring.backend`, `semanticScoring.qwenModel`, and `semanticScoring.qwenApiKeyEnv`.

## Files

- `index.html`, `styles.css`, `src/app.js`: static dashboard UI.
- `data/news.json`: retained daily news digests.
- `data/golden_cases.json`: reviewed feedback cases used in future LLM classification and HyDE prompts.
- `config/news_sources.json`: RSS search queries, source preferences, thresholds, and retention settings.
- `scripts/update_news.py`: manual or scheduled update script.
- `scripts/add_golden_case.py`: helper for appending reviewed report JSON into the golden-case file.
- `requirements-semantic.txt`: Python 3.13-safe LangChain + DashScope dependencies for semantic scoring.
- `requirements-colbert.txt`: optional PyLate / ColBERT dependency for token-wise semantic scoring.
- `docs/news_methodology.md`: filtering logic, limitations, and next steps.
