# Update And Filtering Notes

## Update model

The dashboard is static and reads from `data/news.json`. It does not refresh by itself in the browser.

News updates are automated through GitHub Actions:

```bash
python3 scripts/update_news.py --today-only
python3 scripts/update_news.py
```

The hourly job runs `--today-only`, which fetches current sources but only admits articles published today. The daily night job runs the full command, refreshes the rolling 90-day window, backfills missing Chinese summaries, and prunes old dates. Each date contains separate buckets for every required GP: Blue Owl, OTF, Pretium, KKR, PAG, Bayview, CIFC, Basepoint, NB, Apollo, Bain Capital, Guggenheim, and HSBC AM.

## Sources

The current script uses Google News RSS searches because they require no paid API key and work well for a lightweight local monitor. The query list in `config/news_sources.json` now includes GP-specific queries for every required manager, plus broader sector queries for market context:

- Private credit, direct lending, BDCs, software-credit stress, and financing transactions.
- Asset-backed lending, securitization, mortgage, real estate credit, aircraft / aviation finance, and CLOs.
- The requested GP list: Blue Owl, OTF, Pretium, KKR, PAG, Bayview, CIFC, Basepoint, Neuberger Berman / NB, Apollo, Bain Capital, Guggenheim, and HSBC Asset Management.
- A US-first mix with standing Europe queries. The interface no longer shows a US / Europe percentage box; the region remains visible on each article card.
- Asset Securitization Report is handled by a dedicated HTML listing-page parser because its configured `/feed` URL returns HTML rather than valid RSS/XML.

The seeded first digest was manually curated from recent source material including WSJ, Reuters / MarketScreener, SEC filings, manager press releases, Business Wire, Private Credit Daily, easyJet investor announcements, and ABC News Australia for the PAG-linked Bathla item.

## Relevance logic

Each fetched item is classified before scoring. The system first runs keyword matching and, when Qwen is available, an LLM classifier. The saved GP and sub-sector tags are the union of keyword-detected tags and LLM-detected tags.

The LLM classifier also receives precedential wrong cases from `data/golden_cases.json`. It can exclude an article before scoring when the article is about a tracked GP's non-credit business, such as private equity, infrastructure, sports/media, or corporate news with no credit or financing angle.

After classification, each item is scored using transparent keyword rules:

- GP match: strong positive score.
- Sub-sector match: positive score for each matched tracked sector.
- Credit context: positive score for words such as credit, debt, lending, facility, securitization, CLO, BDC, mortgage, and asset-backed.
- Preferred source: positive score for sources such as Reuters, Bloomberg, FT, WSJ, Creditflux, Structured Credit Investor, ABL Advisor, Business Wire, PR Newswire, SEC, and manager-owned news pages.
- Region: US gets a modest positive score; Europe gets a smaller positive score to preserve roughly 80% / 20% coverage.
- Mega-manager guardrail: a manager name without credit, lending, financing, collateral, or tracked-sector context is penalized so unrelated private-equity, sports, infrastructure, or corporate news does not crowd out credit-relevant items.

Semantic scoring uses a HyDE-style query set. Qwen generates three credit-relevant example article descriptions for each tracked GP, plus non-relevant examples for contrast. The updater scores each article against the relevant examples for its fused GP tags and normalizes that semantic score onto the same point scale as the keyword score. The script then sorts by score and date inside each GP bucket. This avoids compressing a day into one short global list and lets the selected date show different sources for each manager on the same screen.

## Feedback Loop

Each news card includes a Report button. Reports capture the article excerpt, original tags, proposed corrected tags, and reason. On the static public site, reports open a prefilled GitHub Issue because GitHub Pages cannot write directly into repository files. Reviewed reports can be copied into `data/golden_cases.json`, and future updater runs include those cases in both the classification and HyDE prompts.

## Limitations And Next Steps

This is a practical first version, not a full institutional news system.

- Google News RSS can miss paywalled trade publications, alter source links, or surface duplicate syndications.
- The updater creates English summaries from article titles and RSS snippets. Qwen translates missing Chinese summaries when `DASHSCOPE_API_KEY` is available.
- Keyword + LLM classification is stronger than keyword matching alone, but still depends on available RSS/article text and prompt quality.
- No article full-text extraction is included, so paywalled or JavaScript-heavy pages are summarized only from available metadata.
- No alerting, email delivery, authentication, or central analyst approval queue is included.

With more time, I would add direct feeds or licensed APIs for Bloomberg, LCD, Creditflux, Private Debt Investor, Debtwire, SCI, ABL Advisor, SEC EDGAR company feeds, and manager IR pages; add a central analyst review screen; add bilingual summarization with source citations; track recurring borrowers and funds; and store more detailed provenance / relevance scores per item for auditability.
