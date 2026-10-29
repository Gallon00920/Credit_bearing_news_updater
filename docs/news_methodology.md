# Update And Filtering Notes

## Update model

The dashboard is static and reads from `data/news.json`. It does not refresh by itself in the browser.

News updates are automated through GitHub Actions:

```bash
python3 scripts/update_news.py --recent-days 3
python3 scripts/update_news.py
```

The hourly job runs `--recent-days 3`, which fetches current sources but only admits articles published in the latest three calendar days; it also prunes dates outside the 90-day window and translates any saved item still missing Chinese text. The dashboard's `Refresh news` button dispatches the same workflow with `--recent-days 1` through the GitHub API and reloads once GitHub Pages has deployed the result. The full command without `--recent-days` remains available locally but is no longer wired to the workflow. `--backfill-only` migrates saved items to the current schema without fetching. Each date contains separate buckets for every tracked institution: nine invested funds (Blue Owl, KKR, CIFC, PAG, Pretium, Guggenheim, Neuberger, BasePoint, Bain Capital) and six watchlist funds (Blackstone, Apollo, TPG, Golub, CVC, Canyon).

## Sources

The current script uses Google News RSS searches because they require no paid API key and work well for a lightweight local monitor. The query list in `config/news_sources.json` now includes GP-specific queries for every required manager, plus broader sector queries for market context:

- Private credit, direct lending, BDCs, software-credit stress, and financing transactions.
- Asset-backed lending, securitization, mortgage, real estate credit, aircraft / aviation finance, and CLOs.
- The tracked institution list: Blue Owl (incl. Dyal), KKR, CIFC, PAG, Pretium, Guggenheim, Neuberger Berman, BasePoint, Bain Capital, Blackstone, Apollo, TPG (incl. Angelo Gordon), Golub, CVC, and Canyon.
- A US-first mix with standing Europe queries. The interface no longer shows a US / Europe percentage box; the region remains visible on each article card.
- Direct RSS / Atom feeds include SEC EDGAR Atom for Blue Owl Technology Finance, PR Newswire, Business Wire, ABF Journal, HousingWire, Private Equity Wire, Connect Money topic feeds for private debt / CLOs / business lending / alternatives / real estate, and Mortgage News Daily mortgage / MBS feeds.
- HTML source parsers cover Asset Securitization Report, ABL Advisor, Structured Credit Investor, and Inside Mortgage Finance. ASR uses a dedicated parser because its configured `/feed` URL returns HTML rather than valid RSS/XML; the others use a generic public listing-page extractor.

The seeded first digest was manually curated from recent source material including WSJ, Reuters / MarketScreener, SEC filings, manager press releases, Business Wire, Private Credit Daily, easyJet investor announcements, and ABC News Australia for the PAG-linked Bathla item.

## Relevance logic

Each fetched item is classified before scoring. The system first runs keyword matching and, when Claude is available, an LLM classifier. The saved institution, strategy and event tags are the union of keyword-detected tags and LLM-detected tags. Strategies follow the dashboard taxonomy (Private Credit, ABF, Structured Credit, CLO, Resi Credit, Triple Net Lease, Single Family Rental, Commercial Real Estate, Aircraft Leasing, Data Center, AI, GP Stakes); events are lawsuit, financing and fundraising.

The LLM classifier also receives precedential wrong cases from `data/golden_cases.json`. It can exclude an article before scoring when the article is about a tracked GP's non-credit business, such as private equity, infrastructure, sports/media, or corporate news with no credit or financing angle, or about an unrelated namesake (Apollo 11, Pag-IBIG, Canyon cycling).

After classification, each item is scored using transparent keyword rules:

- GP match: strong positive score.
- Sub-sector match: positive score for each matched tracked sector.
- Credit context: positive score for words such as credit, debt, lending, facility, securitization, CLO, BDC, mortgage, and asset-backed.
- Preferred source: positive score for sources such as Reuters, Bloomberg, FT, WSJ, Creditflux, Structured Credit Investor, ABL Advisor, Business Wire, PR Newswire, SEC, and manager-owned news pages.
- Region: US gets a modest positive score; Europe gets a smaller positive score to preserve roughly 80% / 20% coverage.
- Mega-manager guardrail: a manager name without credit, lending, financing, collateral, or tracked-sector context is penalized so unrelated private-equity, sports, infrastructure, or corporate news does not crowd out credit-relevant items.

Semantic scoring uses a HyDE-style query set. Claude generates three credit-relevant example article descriptions for each tracked GP, plus non-relevant examples for contrast. The updater scores each article against the relevant examples for its fused GP tags (PyLate / ColBERTv2 MaxSim when installed, otherwise a Claude relevance judge) and normalizes that semantic score onto the same point scale as the keyword score. The script then sorts by score and date inside each GP bucket. This avoids compressing a day into one short global list and lets the selected date show different sources for each manager on the same screen.

## Dashboard rating

Besides the selection score, every saved item carries five 0-1 rating components computed once at retrieval: GP relevance (does the headline name the institution), strategy relevance (keyword hit blended with the semantic match), event importance (rules for lawsuits, closes, major deals, financing, fundraising, with stock commentary and law-firm solicitations down-weighted, averaged with Claude's importance estimate), source priority (media tier) and freshness (days between publication and retrieval). The dashboard recomputes the 0-100 total from these fixed components with user-adjustable weights, filters by score threshold, and can sort by any single component. The scoring-reasons panel on each card lists the components, the weights, the Claude selection reason and the tag provenance, so readers can see why an article was selected.

## Feedback Loop

Each news card includes a Report button. Reports capture the article excerpt, original tags, proposed corrected tags, and reason. On the static public site, reports open a prefilled GitHub Issue because GitHub Pages cannot write directly into repository files. Reviewed reports can be copied into `data/golden_cases.json`, and future updater runs include those cases in both the classification and HyDE prompts.

## Limitations And Next Steps

This is a practical first version, not a full institutional news system.

- Google News RSS and free publisher feeds can miss paywalled trade publications, alter source links, or surface duplicate syndications.
- The updater creates English summaries from article titles and RSS snippets. Claude translates missing Chinese summaries when `ANTHROPIC_API_KEY` is available.
- Keyword + LLM classification is stronger than keyword matching alone, but still depends on available RSS/article text and prompt quality.
- No article full-text extraction is included, so paywalled or JavaScript-heavy pages are summarized only from available metadata.
- No alerting, email delivery, authentication, or central analyst approval queue is included.

With more time, I would add licensed APIs for Bloomberg, LCD, Creditflux, Private Debt Investor, Debtwire, and manager IR pages; add a central analyst review screen; add bilingual summarization with source citations; track recurring borrowers and funds; and store more detailed provenance / relevance scores per item for auditability.
