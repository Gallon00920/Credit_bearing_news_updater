# Junson AID Credit Radar

A static, bilingual (English / Simplified Chinese) dashboard for monitoring private-credit news across 15 tracked institutions. The layout follows the AID Credit Radar design: a left sidebar for selecting invested and watchlist funds, event tabs (headlines / lawsuits / financing / fundraising), keyword search, date filters including an exact-date picker, a five-part weighted score with adjustable weights, per-component sorting, a strategy-group browser, search coverage, and an on-page summary of the filtered news. Every article keeps an explanation of why it was selected.

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

The updater fetches Google News RSS search feeds for each tracked institution plus broader sector queries and publisher feeds, classifies and scores articles with keyword rules, Claude classification and HyDE semantic scoring, computes the five rating components used by the dashboard, translates titles, summaries and selection reasons into Simplified Chinese, appends selected items into institution buckets under each article's actual publication date, and prunes dates older than the rolling retention window.

To preview without writing:

```bash
python3 scripts/update_news.py --dry-run
```

For the hourly recent-window update:

```bash
python3 scripts/update_news.py --recent-days 3
```

To migrate saved data to the current institution list, strategy taxonomy, event tags and rating components without fetching anything or calling Claude:

```bash
python3 scripts/update_news.py --backfill-only
```

Set your Claude (Anthropic) API key before running the full pipeline. Never commit real keys to this file:

```bash
export ANTHROPIC_API_KEY="your_anthropic_api_key"
export HF_TOKEN="your_optional_hugging_face_token"
python3 scripts/update_news.py
```

Chinese content:

- New items translate the title, the English summary and the Claude selection reason in one call with the Claude model configured under `claude.model` in `config/news_sources.json`, currently `claude-opus-5-5`.
- The API key is read from `ANTHROPIC_API_KEY` by default.
- Existing manually written Chinese abstracts are preserved.
- Existing saved items with missing or placeholder Chinese abstracts, or with an untranslated title, are backfilled during the full `python3 scripts/update_news.py` run.
- If the API key is not available, the updater keeps the English title, a placeholder Chinese summary, and continues.

The stored data follows a rolling 90-day window: a run on September 11, 2026 keeps June 14, 2026 through September 11, 2026. Fetched stories are saved under their actual `publishedAt` date, not under the date the updater was run.

## Dashboard

The page reads `data/news.json` only; every filter, weight and sort runs in the browser.

- Left sidebar: `All funds`, then `Invested funds` (Blue Owl, KKR, CIFC, PAG, Pretium, Guggenheim, Neuberger, BasePoint, Bain Capital) and `Watchlist funds` (Blackstone, Apollo, TPG, Golub, CVC, Canyon), each with a group checkbox and per-fund article counts for the active date range. `+ Add institution` adds a browser-local institution matched by name or aliases in saved headlines. `GitHub connection` at the bottom manages the token used by the live refresh.
- `Refresh news` (top right) runs a real refresh of today's news: it dispatches the GitHub Actions workflow in `today` mode through the GitHub API, shows the run phase and elapsed time on the button, waits for the run to finish and for GitHub Pages to deploy the new `data/news.json`, then reloads the data in place. It needs a fine-grained personal access token for this repository with Actions permission `Read and write`; the token is kept only in the browser's local storage. Without a token the button opens a dialog to paste one or to open the Actions page instead.
- Event tabs: `Headlines / All`, `Lawsuit`, `Financing / Deals`, `New funds / Fundraising`. Event tags come from headline rules plus Claude classification.
- Keyword search over titles, summaries and sources in both languages.
- Date filter: last 7 / 30 / 90 / 365 days, any time, `Exact date…` (single-day picker with previous / next / today), or a custom range.
- Priority filter: all scores, 50+, 65+ (priority reading), 80+ (high priority).
- Weighted ranking settings: five sliders (GP relevance, strategy relevance, event importance, source priority, freshness). Each article stores the five component values computed at retrieval; the browser recomputes the 0-100 total as the weighted average with the current weights. Weights persist in the browser; `Restore default weights` resets to 18 / 12 / 30 / 25 / 15.
- Sorting: importance first, newest first, oldest first, or by any single component.
- Strategy groups: Credit (Private Credit, ABF, Structured Credit, CLO, Resi Credit), Real Estate (Triple Net Lease, Single Family Rental, Commercial Real Estate), Hard Asset (Aircraft Leasing, Data Center), AI, Other (GP Stakes). `+ Add strategy` / `+ Add sub-strategy` creates a browser-local keyword strategy.
- `Generate summary` builds a rule-based brief of the filtered articles (fundraising, deals, liquidity, credit quality, legal events, strategy concentration) in the active language. It reads headlines only and does not call an AI.
- Each card shows source, date, institution / event / strategy tags, the title (Chinese when the page language is Chinese), a summary when it adds to the title, and `score / 100` with `view scoring reasons`: the five components with weights and reasons, the Claude selection reason, tag provenance, and the pipeline keyword / semantic scores. `Report classification issue` opens the feedback dialog.
- Search coverage lists, per institution, the candidate count and status of the last pipeline run from `coverage` in `data/news.json`, plus the Google News queries used.
- The `EN / 中文` toggle in the top bar switches every label and every article field.

## Automated Refresh

The public site is intended to stay fully static. News updates are handled by `.github/workflows/update-news.yml`, which runs the Python updater in GitHub Actions and commits changed JSON data back to the repository.

- Hourly: runs `python3 scripts/update_news.py --recent-days 3`. This fetches current sources, admits only articles whose `publishedAt` date is within the latest three calendar days, dedupes by normalized URL, classifies, scores, translates, and merges only into those recent date buckets. Every run also backfills saved items that predate the current schema, translates any saved item still missing a Chinese title or summary, and prunes dates outside the 90-day window.
- Today refresh: the dashboard's `Refresh news` button dispatches the workflow with mode `today`, which runs `python3 scripts/update_news.py --recent-days 1`. The same mode can be started by hand from the Actions page with `Run workflow`.
- There is no full 90-day mode in the workflow any more. A full-window run is still possible locally with `python3 scripts/update_news.py` if you ever need to re-fetch the whole archive.
- GitHub Actions uses `concurrency.cancel-in-progress: false`, so a today run does not cancel or overwrite the automatic hourly recent-window job. If another refresh is already running, GitHub queues the next run; the dashboard keeps polling until its run completes.
- The workflow uses repository secrets named `ANTHROPIC_API_KEY` and optional `HF_TOKEN`.
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
- Institution feeds: two search queries per tracked institution (a name / alias query and a credit-focused query) for Blue Owl, KKR, CIFC, PAG, Pretium, Guggenheim, Neuberger, BasePoint, Bain Capital, Blackstone, Apollo, TPG, Golub, CVC, and Canyon. Blue Owl includes Dyal; TPG includes Angelo Gordon. Institution aliases in `gpAliases` also cover credit vehicles and tickers so rating actions and fund pages that name the vehicle rather than the sponsor still tag the manager: for example Owl Rock / OBDC / OCIC (Blue Owl), FS KKR / KREF (KKR), Progress Residential / Deephaven / Anchor Loans / PRET shelf (Pretium), BCRED / BXSL / BXMT / BX Trust (Blackstone), MidCap Financial / Redding Ridge / Athene (Apollo), Twin Brook / Northwoods / AG Mortgage Investment Trust (TPG), GBDC (Golub), BCSF (Bain Capital) and Cordatus (CVC).
- Sector/context feeds: broader searches for private credit, direct lending, CLO, mortgage, real estate credit, asset-based finance, aircraft / aviation finance, data center and AI infrastructure financing, and GP-stakes topics, plus Google News site searches that pull Morningstar DBRS rating actions (CLO, BDC, private credit, SFR, mortgage, net lease, aircraft) and PitchBook / LCD coverage of private credit, direct lending, CLOs and leveraged loans. DBRS items name the rated vehicle rather than the sponsor, so they are only kept when the vehicle name or article text maps to a tracked institution.
- Direct RSS / Atom feeds: SEC EDGAR Atom for Blue Owl Technology Finance, PR Newswire financial services RSS, Business Wire finance RSS, ABF Journal RSS, HousingWire RSS, Private Equity Wire RSS, Connect Money topic feeds for private debt / CLOs / business lending / alternatives / real estate, and Mortgage News Daily RSS feeds for mortgage industry news, MBS commentary, and full news.
- HTML source parsers: Asset Securitization Report is fetched as a normal HTML page from `https://asreport.americanbanker.com/feed` and parsed with a dedicated listing-page extractor because that URL does not return valid RSS/XML. A generic listing-page extractor also reads public article indexes from ABL Advisor, Structured Credit Investor, and Inside Mortgage Finance.
- Direct article-page scraping: not used for routine ingestion. If semantic scoring is enabled, the updater may make a simple free HTML fetch of an article URL to extract a meta description or first text words for scoring only; it does not bypass paywalls, submit forms, or run a headless browser.
- Paid/news API integrations: not used in this version.
- Full article extraction: limited. Automated summaries are still based mainly on RSS title/source/snippet metadata; semantic scoring uses title + lede + first available 200 free article words when fetchable.

Preferred sources are configured in `config/news_sources.json` and include Reuters, Bloomberg, Financial Times, Wall Street Journal, Private Credit Daily, Creditflux, Structured Credit Investor, ABL Advisor, Asset Securitization Report, PR Newswire, Business Wire, SEC, Morningstar DBRS, PitchBook, and manager-owned press/IR pages when surfaced by RSS.

## News Selection Criteria

The updater decides whether an item aligns with the mandate using keyword scoring first, then semantic scoring when the configured model dependencies and API key are available.

Institution, strategy and event categorization combines keyword detection and Claude classification:

- Keyword detection scans `title + RSS description/lede + source` against `gpAliases` in `config/news_sources.json` and the `STRATEGIES` keyword / regex table in `scripts/update_news.py`.
- Claude classifies the article into tracked institution(s), strategy id(s), event type(s) (`lawsuit`, `financing`, `fundraising`), an importance estimate from 0 to 1, and a possible non-credit exclusion flag.
- The saved institution, strategy and event lists are the unions of the keyword results and the Claude results.
- If Claude says the article is about a tracked institution's non-credit business with no lending, financing, or structured-finance angle, or about an unrelated namesake, the item is excluded before threshold scoring.
- If Claude is unavailable, the updater falls back to keyword-only tags and the dashboard says so in the scoring reasons.

Keyword scoring remains in place after classification:

- Institution coverage: each tracked institution has its own bucket. An item can enter a bucket only if the institution or one of its aliases is detected in the title, source, or RSS snippet, or Claude tags it.
- Credit relevance: items score higher when they mention credit, debt, loans, lending, financing, facilities, securitization, CLOs, BDCs, mortgages, or asset-backed finance.
- Strategy fit: items score higher for each matched strategy.
- Mega-manager guardrail: manager-name-only stories are penalized unless the RSS metadata also contains credit, lending, financing, collateral, or strategy context.
- Region fit: US items receive a small preference, Europe items remain eligible through dedicated Europe queries.
- Source quality: preferred institutional, trade, filing, wire, and manager sources receive a score bonus.
- Recency: searches are bounded by the configured lookback window, currently 90 days, and storage/display is bounded by the rolling 90-day window.

Items below `minimumScore`, currently `5`, are excluded when semantic scoring is unavailable. Within each institution bucket, the script sorts by relevance score and publication date, then keeps up to `maxItemsPerGp`.

Semantic scoring:

- The updater calls Claude through the official `anthropic` Python SDK, configured as `claude-opus-5-5` by default, to generate HyDE-style examples for each tracked institution: three short descriptions of credit-relevant news and two short descriptions of non-relevant news.
- The updater scores the article against the three generated credit-relevant examples for its fused institution tags.
- The HyDE prompt template is embedded in `scripts/update_news.py` and cached in `data/semantic_queries.json` so it does not regenerate unless the prompt, the configured Claude model, or precedent data changes.
- With `semanticScoring.backend: "auto"`, the updater first tries PyLate / ColBERTv2 for MaxSim-style late-interaction scoring. If PyLate cannot be imported, it falls back to a Claude relevance judge (`claude_judge`): one Claude call per article that rates the article against the three HyDE examples on a 0-1 scale. The log line `Semantic scoring backend:` names the backend that was used.
- `semanticScore` is normalized from the backend's raw range onto the same approximate point scale as the keyword score, currently up to 12 points, and `finalScore = keywordScore + semanticScore` must clear `semanticScoring.minimumFinalScore`, currently `7`.

Rating components for the dashboard (stored under `rating.parts`, each 0-1, computed once at retrieval):

- `institution` (GP relevance): 1.0 when the headline names the institution, 0.7 when Claude tagged it from the text, 0.5 when only the body mentions it, 0.25 otherwise.
- `strategy` (strategy relevance): 1.0 for a headline keyword hit, 0.7 for a Claude strategy, 0.6 for a body hit, 0 otherwise; when semantic scoring ran, the value is the average of that tag value and the normalized semantic score.
- `event` (event importance): rule value from the headline and event tags (lawsuit 1.0, close / major transaction / credit-risk signal 0.95, fundraising 0.8, financing 0.7, routine 0.2, stock commentary 0.15, law-firm solicitation 0.1), averaged with Claude's importance estimate when available, except that the two down-weighting rules always win.
- `source` (source priority): Reuters / Bloomberg / FT / WSJ 1.0, regulatory filings 0.9, trade press 0.8, press-release wires 0.4, aggregators 0.25, other 0.35.
- `freshness`: days between publication and retrieval, bucketed 1.0 / 0.8 / 0.5 / 0.2 / 0.05 at 1 / 7 / 30 / 90 days. Items migrated from the earlier dashboard carry an estimated 0.8.

Default weights live under `ratingWeights` in `config/news_sources.json` and are written to `scope.ratingWeights` in `data/news.json`. The dashboard total is `sum(value × weight) / sum(weight) × 100`.

## Report Feedback

Each news card includes a `Report classification issue` link inside the scoring reasons.

- Readers can report wrong GP, wrong strategy, or not credit related.
- The report captures the article title, URL, source, publication date, lede/excerpt, original institution / strategy tags, corrected tags, and the reader's reason.
- Because the public site is static, the browser cannot write directly to `data/golden_cases.json`. Instead, the report is stored in browser local storage and opens a prefilled GitHub Issue containing structured JSON.
- After review, valid reports should be copied into `data/golden_cases.json`.
- To append a reviewed report JSON locally, save the report body to a temporary JSON file and run `python3 scripts/add_golden_case.py path/to/report.json`, then commit `data/golden_cases.json`.
- Future updater runs include those golden cases in the Claude classification and HyDE prompts under precedential wrong/non-relevant cases.

Semantic dependencies are optional because the base dashboard should still run without model infrastructure. For the full semantic and translation pipeline:

```bash
pip install -r requirements-semantic.txt
export ANTHROPIC_API_KEY="your_api_key_here"
python3 scripts/update_news.py
```

For token-wise ColBERT-style MaxSim scoring, install the PyLate backend (it needs a CPython version that `fast-plaid` publishes wheels for, currently 3.10 to 3.14):

```bash
pip install -r requirements-colbert.txt
```

If `huggingface.co` is blocked or slow (corporate proxies, offline machines), the updater probes it once with a 6-second timeout. When the ColBERT model is already in the local Hugging Face cache it loads in offline mode; otherwise it skips PyLate immediately and uses the Claude relevance judge instead of waiting through the Hub client's retries. Set `SEMANTIC_BACKEND=claude_judge` (or `pylate` / `auto`) in the environment to force a backend for one run without editing the config.

Behind a TLS-inspecting corporate proxy, Python 3.13+ rejects the proxy's root certificate (`CERTIFICATE_VERIFY_FAILED: CA cert does not include key usage extension`) even though the browser accepts it. The updater therefore calls `truststore.inject_into_ssl()` at startup when the `truststore` package is installed (it is in `requirements-semantic.txt`), so certificate validation is delegated to the operating system's trust store. Install it into whichever interpreter runs the script, for example `python3 -m pip install truststore`, and set `NEWS_OS_TRUST_STORE=0` to disable the behaviour.

Claude settings live in `config/news_sources.json` under the top-level `claude` block: `model`, `apiKeyEnv`, `effort` (`low` / `medium` / `high`), `maxTokens`, and `refusalFallback` (server-side fallback to another Claude model if a safety classifier declines a request). Any stage can override the model or effort with `claudeModel` / `claudeEffort` inside `classification`, `semanticScoring`, or `translation`. The semantic backend is chosen with `semanticScoring.backend` (`auto`, `pylate`, or `claude_judge`).

## Files

- `index.html`, `styles.css`, `src/app.js`: static dashboard UI (layout, filters, weights, sorting, summary, bilingual text).
- `data/news.json`: retained daily news digests, plus `scope` (institutions, groups, strategies, weights) and `coverage` from the last run.
- `data/golden_cases.json`: reviewed feedback cases used in future LLM classification and HyDE prompts.
- `config/news_sources.json`: institution list and groups, aliases, RSS search queries, source preferences, rating weights, thresholds, and retention settings.
- `scripts/update_news.py`: manual or scheduled update script, including `--backfill-only` migration.
- `scripts/add_golden_case.py`: helper for appending reviewed report JSON into the golden-case file.
- `requirements-semantic.txt`: the `anthropic` SDK used for Claude classification, HyDE generation, relevance judging, and translation.
- `requirements-colbert.txt`: optional PyLate / ColBERT dependency for token-wise semantic scoring.
- `docs/news_methodology.md`: filtering logic, limitations, and next steps.
