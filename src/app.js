const DATA_URL = "data/news.json";
const GITHUB_REPO = "Gallon00920/Credit_bearing_news_updater";
const GITHUB_BRANCH = "main";
const WORKFLOW_FILE = "update-news.yml";
const REPORT_ISSUE_URL = `https://github.com/${GITHUB_REPO}/issues/new`;
const MANUAL_REFRESH_WORKFLOW_URL = `https://github.com/${GITHUB_REPO}/actions/workflows/${WORKFLOW_FILE}`;
const GITHUB_API = `https://api.github.com/repos/${GITHUB_REPO}/actions/workflows/${WORKFLOW_FILE}`;
const RUN_POLL_MS = 20000;
const RUN_TIMEOUT_MS = 40 * 60 * 1000;
const DEPLOY_POLL_MS = 15000;
const DEPLOY_TIMEOUT_MS = 12 * 60 * 1000;
const STORAGE = {
  firms: "credit-radar-firms-v1",
  strategies: "credit-radar-strategies-v1",
  weights: "credit-radar-weights-v1",
  language: "news-dashboard-language",
  reports: "news-dashboard-report-logs",
  githubToken: "credit-radar-github-token-v1",
};
const PAGE_SIZE = 30;
const DEFAULT_WEIGHTS = { institution: 18, strategy: 12, event: 30, source: 25, freshness: 15 };
const WEIGHT_KEYS = ["institution", "strategy", "event", "source", "freshness"];

const DEFAULT_GPS = [
  "Blue Owl", "KKR", "CIFC", "PAG", "Pretium", "Guggenheim", "Neuberger", "BasePoint", "Bain Capital",
  "Blackstone", "Apollo", "TPG", "Golub", "CVC", "Canyon",
];
const DEFAULT_GROUPS = {
  invested: ["Blue Owl", "KKR", "CIFC", "PAG", "Pretium", "Guggenheim", "Neuberger", "BasePoint", "Bain Capital"],
  watch: ["Blackstone", "Apollo", "TPG", "Golub", "CVC", "Canyon"],
};
const DEFAULT_ALIASES = {
  "Blue Owl": ["Blue Owl", "BlueOwl", "Owl Rock", "Dyal Capital", "Dyal", "Blue Owl Technology Finance"],
  KKR: ["KKR", "Kohlberg Kravis Roberts", "Global Atlantic"],
  CIFC: ["CIFC"],
  PAG: ["PAG", "Pacific Alliance Group"],
  Pretium: ["Pretium"],
  Guggenheim: ["Guggenheim"],
  Neuberger: ["Neuberger Berman", "Neuberger"],
  BasePoint: ["BasePoint"],
  "Bain Capital": ["Bain Capital", "BainCapital"],
  Blackstone: ["Blackstone", "BCRED"],
  Apollo: ["Apollo Global", "Apollo Management", "Apollo", "Athene"],
  TPG: ["TPG", "Angelo Gordon"],
  Golub: ["Golub"],
  CVC: ["CVC Capital", "CVC Credit", "CVC"],
  Canyon: ["Canyon Partners", "Canyon Capital"],
};
const BUILTIN_STRATEGIES = [
  { id: "private-credit", name: "Private Credit", cn: "私募信贷", group: "credit", pattern: /private credit|private debt|direct lend|\bBDCs?\b|unitranche/i },
  { id: "abf", name: "ABF", cn: "资产支持融资", group: "credit", pattern: /asset.based|asset.backed|\bABF\b|\bABL\b|specialty finance|receivables/i },
  { id: "structured", name: "Structured Credit", cn: "结构化信贷", group: "credit", pattern: /structured credit|structured finance|securiti[sz]|\bABS\b/i },
  { id: "clo", name: "CLO", cn: "抵押贷款债券", group: "credit", pattern: /\bCLOs?\b|collateralized loan obligation|collateralised loan obligation/i },
  { id: "resi", name: "Resi Credit", cn: "住宅信贷", group: "credit", pattern: /residential credit|mortgage|\bRMBS\b|housing credit|home loans?|\bMSRs?\b/i },
  { id: "triple-net", name: "Triple Net Lease", cn: "三净租赁", group: "real-estate", pattern: /triple.net|net leas|\bNNN\b/i },
  { id: "sfr", name: "Single Family Rental", cn: "独栋住宅出租", group: "real-estate", pattern: /single.family rental|build.to.rent|\bSFR\b/i },
  { id: "cre", name: "Commercial Real Estate", cn: "商业地产", group: "real-estate", pattern: /commercial real estate|commercial propert|commercial mortgage|\bCMBS\b|\bCRE\b/i },
  { id: "aircraft", name: "Aircraft Leasing", cn: "飞机租赁", group: "hard-asset", pattern: /aircraft|aviation|airplane|airline/i },
  { id: "data-center", name: "Data Center", cn: "数据中心", group: "hard-asset", pattern: /data cent(?:er|re)s?|datacenters?|数据中心/i },
  { id: "ai", name: "AI", cn: "AI 相关", group: "ai", pattern: /\bAI\b|artificial intelligence|GPU financ|compute infrastructure|chip financ|人工智能|算力/i },
  { id: "gp-stakes", name: "GP Stakes", cn: "GP 股权", group: "other", pattern: /GP stakes?|general partner.{0,15}stakes?|Dyal/i },
];
const STRATEGY_GROUPS = [
  { id: "credit", name: "Credit", cn: "Credit", ids: ["private-credit", "abf", "structured", "clo", "resi"] },
  { id: "real-estate", name: "Real Estate", cn: "Real Estate", ids: ["triple-net", "sfr", "cre"] },
  { id: "hard-asset", name: "Hard Asset", cn: "Hard Asset", ids: ["aircraft", "data-center"] },
  { id: "ai", name: "AI", cn: "AI 相关", ids: ["ai"] },
  { id: "other", name: "Other strategies", cn: "其他策略", ids: ["gp-stakes"] },
];
const FOCUS_STRATEGY_IDS = ["private-credit", "abf", "clo", "ai", "aircraft", "gp-stakes"];
const LEGACY_SECTOR_MAP = {
  "private credit / direct lending": ["private-credit"],
  "GP stakes": ["gp-stakes"],
  "aircraft leasing": ["aircraft"],
  "asset-backed lending": ["abf"],
  "real estate": ["cre"],
  mortgage: ["resi"],
  CLO: ["clo"],
};
const EVENT_TABS = ["all", "lawsuit", "financing", "fundraising"];
const EVENT_PATTERNS = {
  lawsuit: /lawsuit|litigation|\bsue[sd]?\b|settlement|class.action|\bcourt\b|enforcement action/i,
  financing: /financ|\bloans?\b|credit facility|acqui|\bbuy\b|securiti[sz]ation|debt issu|invest(?:s|ed|ment)?.{0,35}(?:billion|million)|commit.{0,35}(?:billion|million)|refinanc|\bbond\b/i,
  fundraising: /final clos|first clos|fund.{0,35}(?:clos|rais)|rais(?:ed|es).{0,40}(?:fund|billion|million)|fundrais|target(?:s|ing)?.{0,40}(?:fund|billion|million)|seek(?:s|ing)?.{0,40}(?:rais|fund)|launch.{0,40}fund|new fund/i,
};
const MAJOR_SIGNAL = /final clos|first clos|complet|acqui|\bbillion\b|\bbn\b|default|downgrade|bankrupt|redemption|withdrawal|liquidity crisis|fraud/i;
const STOCK_COMMENTARY = /price target|stock price|stock market|shares (rise|fall)|buy or sell|dividend|stock rating|analyst rating|\bsells? \d|\bbuys? \d|shares of|\bcall \(|\bput \(|stock price, news, quote/i;
const SOLICITATION = /investor alert|investor reminder|securities class action notice|law firm|deadline alert|reminds investors|shareholder alert|investigation alert|investors.*contact|losses.*contact/i;
const SOURCE_TIERS = [
  ["tier_top", 1.0, /^(reuters|bloomberg|financial times|ft\.com|the wall street journal|wall street journal|wsj)(\b|$)/i],
  ["tier_filing", 0.9, /\bsec\b|edgar|company filing/i],
  ["tier_trade", 0.8, /private debt investor|9fin|creditflux|structured credit investor|pensions & investments|alternative credit investor|\bipe\b|aviation week|airfinance|asset securitization report|abl advisor|private credit daily|commercial observer|housingwire|abf journal|inside mortgage finance|private equity wire|connect money|mortgage news daily|pere|secondaries investor|buyouts|debtwire|lcd|with intelligence/i],
  ["tier_press_release", 0.4, /business wire|pr newswire|globenewswire|newsfile|accesswire/i],
  ["tier_aggregator", 0.25, /seeking alpha|benzinga|tipranks|stock titan|marketbeat|simply wall st|yahoo|motley fool|investing\.com|stocktwits/i],
];

const ICONS = {
  radio: '<path d="M16.247 7.761a6 6 0 0 1 0 8.478"/><path d="M19.075 4.933a10 10 0 0 1 0 14.134"/><path d="M4.925 19.067a10 10 0 0 1 0-14.134"/><path d="M7.753 16.239a6 6 0 0 1 0-8.478"/><circle cx="12" cy="12" r="2"/>',
  newspaper: '<path d="M15 18h-5"/><path d="M18 14h-8"/><path d="M4 22h16a2 2 0 0 0 2-2V4a2 2 0 0 0-2-2H8a2 2 0 0 0-2 2v16a2 2 0 0 1-4 0v-9a2 2 0 0 1 2-2h2"/><rect width="8" height="4" x="10" y="6" rx="1"/>',
  scale: '<path d="M12 3v18"/><path d="m19 8 3 8a5 5 0 0 1-6 0zV7"/><path d="M3 7h1a17 17 0 0 0 8-2 17 17 0 0 0 8 2h1"/><path d="m5 8 3 8a5 5 0 0 1-6 0zV7"/><path d="M7 21h10"/>',
  landmark: '<path d="M10 18v-7"/><path d="M11.119 2.205a2 2 0 0 1 1.762 0l7.84 3.846A.5.5 0 0 1 20.5 7h-17a.5.5 0 0 1-.22-.949z"/><path d="M14 18v-7"/><path d="M18 18v-7"/><path d="M3 22h18"/><path d="M6 18v-7"/>',
  layers: '<path d="M12.83 2.18a2 2 0 0 0-1.66 0L2.6 6.08a1 1 0 0 0 0 1.83l8.58 3.91a2 2 0 0 0 1.66 0l8.58-3.9a1 1 0 0 0 0-1.83z"/><path d="M2 12a1 1 0 0 0 .58.91l8.6 3.91a2 2 0 0 0 1.65 0l8.58-3.9A1 1 0 0 0 22 12"/><path d="M2 17a1 1 0 0 0 .58.91l8.6 3.91a2 2 0 0 0 1.65 0l8.58-3.9A1 1 0 0 0 22 17"/>',
  search: '<path d="m21 21-4.34-4.34"/><circle cx="11" cy="11" r="8"/>',
  "refresh-cw": '<path d="M3 12a9 9 0 0 1 9-9 9.75 9.75 0 0 1 6.74 2.74L21 8"/><path d="M21 3v5h-5"/><path d="M21 12a9 9 0 0 1-9 9 9.75 9.75 0 0 1-6.74-2.74L3 16"/><path d="M8 16H3v5"/>',
  "sliders-horizontal": '<path d="M10 5H3"/><path d="M12 19H3"/><path d="M14 3v4"/><path d="M16 17v4"/><path d="M21 12h-9"/><path d="M21 19h-5"/><path d="M21 5h-7"/><path d="M8 10v4"/><path d="M8 12H3"/>',
  "arrow-up-right": '<path d="M7 7h10v10"/><path d="M7 17 17 7"/>',
  "chevron-down": '<path d="m6 9 6 6 6-6"/>',
  "circle-alert": '<circle cx="12" cy="12" r="10"/><line x1="12" x2="12" y1="8" y2="12"/><line x1="12" x2="12.01" y1="16" y2="16"/>',
};
function icon(name, size = 16, className = "") {
  return `<svg xmlns="http://www.w3.org/2000/svg" width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="lucide ${className}" aria-hidden="true">${ICONS[name] || ""}</svg>`;
}

const UI = {
  en: {
    brandTag: "Alternatives intel",
    monitoringUniverse: "MONITORING UNIVERSE",
    allFunds: "All funds",
    invested: "Invested funds",
    watch: "Watchlist funds",
    selectGroup: "Select group",
    addFirm: "+ Add institution",
    hideFirmManager: "Hide institution manager",
    firmName: "Institution name",
    firmAliases: "Search aliases (optional)",
    firmGroup: "Group",
    firmNamePlaceholder: "e.g. Ares Management",
    firmAliasPlaceholder: "Comma separated, up to 5",
    firmHint: "Full institution names match best; names and aliases are matched as exact phrases in saved headlines.",
    addAndSearch: "Add and search",
    remove: "Remove",
    firmStored: "Saved in this browser; up to 20 can be added.",
    firmExists: "Institution already exists",
    firmInvalid: "Enter a valid institution name",
    firmStorageFail: "Browser storage unavailable; the institution is kept for this page only.",
    firmReadFail: "The institution list in this browser could not be read; add them again.",
    coverageNotes: "COVERAGE NOTES",
    coverageNoteA: "Public news · English first\nHourly pipeline · Claude classification",
    coverageNoteB: "Blue Owl incl. Dyal\nTPG incl. Angelo Gordon",
    githubSettingsButton: "GitHub connection",
    githubEyebrow: "Live refresh",
    githubTitle: "Connect GitHub to refresh today's news",
    githubIntro: "Refreshing runs the updater in GitHub Actions for today's news (fetch, Claude classification, semantic scoring, translation) and reloads the page when the new data is deployed. The hourly automatic update keeps running on its own.",
    githubSteps: "Create a fine-grained personal access token on GitHub limited to this repository with Actions permission set to Read and write, then paste it below. It is stored only in this browser.",
    githubTokenLabel: "GitHub token",
    githubTokenSaved: "A token is saved in this browser. Leave the field empty to keep it.",
    githubOpenActions: "Open Actions page instead",
    githubForget: "Remove token",
    githubSave: "Save and refresh",
    githubTokenMissing: "Paste a token first, or open the Actions page and run the workflow by hand.",
    refreshPhaseDispatching: "Starting…",
    refreshPhaseQueued: "Queued",
    refreshPhaseRunning: "Updating",
    refreshPhaseDeploying: "Deploying",
    refreshDone: (when) => `Today's news refreshed at ${when}.`,
    refreshFailedRun: "The GitHub Actions run failed. Open the Actions page to read the log.",
    refreshTimeoutRun: "The run is taking longer than expected. The page will show the new data after the next reload.",
    refreshTimeoutDeploy: "The run finished but the new data has not been deployed yet. Reload in a few minutes.",
    refreshAuthError: "GitHub rejected the token (401/403). Check that it has Actions read and write on this repository.",
    refreshNotFound: "Workflow not found (404). Check the repository name and that the workflow file exists on the default branch.",
    refreshNetworkError: (detail) => `Could not reach GitHub: ${detail}`,
    topbarTitle: "AID fund investment tracker",
    topNote: "PUBLIC NEWS INTELLIGENCE",
    eyebrow: "PRIVATE MARKETS / CREDIT",
    heroTitle: "Track capital's next move",
    heroPunct: ".",
    heroSubtitle: "Institution updates, legal events and credit strategies in one search.",
    refreshNews: "Refresh news",
    loadingNews: "Loading",
    eventAll: "Headlines / All",
    eventLawsuit: "Lawsuit",
    eventFinancing: "Financing / Deals",
    eventFundraising: "New funds / Fundraising",
    searchPlaceholder: "Search keywords, e.g. insurance, data center, fund close…",
    searchButton: "Search",
    startDate: "Start date",
    endDate: "End date",
    rangeTo: "to",
    applyDates: "Apply dates",
    rangeHint: "Inclusive of both ends; either end may be left blank.",
    rangeError: "Enter valid dates; the start date cannot be after the end date.",
    exactDate: "Date",
    today: "Today",
    exactHint: (n) => `${n} saved article(s) on this date`,
    dateLabel: "Date",
    days7: "Last 7 days",
    days30: "Last 30 days",
    days90: "Last 90 days",
    days365: "Last year",
    daysAll: "Any time",
    daysExact: "Exact date…",
    daysCustom: "Custom range…",
    minScoreLabel: "Priority filter",
    scoreAll: "All scores",
    score50: "50 and above",
    score65: "65 and above · priority reading",
    score80: "80 and above · high priority",
    weightSettings: "Weighted ranking settings",
    weightIntro: "Total = five indicators × weights, normalised to 100 by the weight sum. The score is a reading priority, not fact-checking or an investment rating.",
    weightNoteA: "Lawsuits, credit stress, final closes and major deals rank first; law-firm solicitations and generic stock commentary are down-weighted. Reuters / Bloomberg / FT / WSJ are preset first, trade press second, press releases separately; the source is matched by its public name.",
    weightNoteB: "Institution relevance scores whether the headline names the firm; strategy relevance combines keyword hits with the semantic (HyDE) match; freshness is bucketed at 1 / 7 / 30 / 90 days from retrieval. Components are fixed at retrieval time; only the weighting is recomputed here.",
    zeroWeights: "All weights are zero, so every article scores 0.",
    resetWeights: "Restore default weights",
    weight: "Weight",
    partInstitution: "GP relevance",
    partStrategy: "Strategy relevance",
    partEvent: "Event importance",
    partSource: "Source priority",
    partFreshness: "Freshness",
    generateSummary: "Generate summary",
    regenerateSummary: "Regenerate summary",
    sortImportance: "Importance first",
    sortRecent: "Newest first",
    sortOldest: "Oldest first",
    sortInstitution: "GP relevance",
    sortStrategy: "Strategy relevance",
    sortEvent: "Event importance",
    sortSource: "Source priority",
    sortFreshness: "Freshness",
    legalNote: "Shows litigation, settlement and court-related news. A headline mention does not mean the institution is a defendant; no result does not mean no litigation exists. Verify cases and progress against the source and court records.",
    resultsAll: "Latest news",
    resultsLawsuit: "Legal events",
    resultsFundraising: "New funds and fundraising",
    resultsFinancing: "Financing and deals",
    fundsSelected: (n) => `${n} fund(s)`,
    noFundSelected: "No fund selected",
    allStrategies: "All strategies",
    earliest: "earliest",
    todayWord: "today",
    scoreAtLeast: (n, total) => `≥${n} points (${total} retrieved)`,
    resetFilters: "Reset filters",
    focusStrategies: "Focus strategies",
    addStrategy: "+ Add strategy",
    hideStrategyManager: "Hide strategy manager",
    strategyGroup: "Group",
    strategyName: "Strategy name",
    strategyKeywords: "Search keywords",
    strategyNamePlaceholder: "e.g. Infrastructure Debt",
    strategyKeywordPlaceholder: "infrastructure debt, infrastructure credit",
    strategyHint: "Enter 1–5 keywords separated by commas. Any keyword hit counts; used for headline tags and relevance. Up to 20 strategies, saved in this browser.",
    strategyExists: "Strategy already exists",
    strategyInvalid: "Enter a valid strategy",
    strategyStorageFail: "Browser storage unavailable; the strategy is kept for this page only.",
    strategyReadFail: "Saved strategies could not be read; add them again.",
    addSubstrategy: "+ Add sub-strategy",
    strategyGroups: "Strategy groups",
    coverageTitle: "Coverage of last run",
    coverageResponded: (n) => `/ ${n} institutions responded`,
    coverageFailed: (n) => `${n} institution queries failed; results are incomplete.`,
    coverageItems: (n) => `${n} items`,
    coverageFailedWord: "failed",
    coverageSelected: (n) => `${n} saved`,
    searching: "searching",
    runAt: "Last run",
    coverageFoot: "Counts are candidates before dedupe; each saved date keeps the top items per firm.",
    notesTitle: "Reading notes",
    notesA: "Event and strategy tags are generated from headline keywords plus Claude classification and are for navigation only.",
    notesB: "Fundraising coverage may refer to target size, first close or final close; confirm amounts and stage in the original article.",
    notesC: "Sources: Google News public index plus publisher feeds. Coverage may be incomplete, duplicated or paywalled; this is not a court-case database.",
    queryToggle: "Search queries & fallback search",
    openGoogleNews: "Open Google News",
    footerNote: "Public information research tool · news dated by publication date",
    feedNote: (updated) => `Showing the saved snapshot updated ${updated}. Scores are computed at retrieval; filters, weights and sorting run in this browser.`,
    tagHeadline: "Headline",
    tagLawsuit: "Lawsuit",
    tagFinancing: "Financing / Deal",
    tagFundraising: "Fund / Raising",
    queryTag: "Query",
    newsSource: "News source",
    highPriority: "High priority",
    priorityReading: "Priority reading",
    readingPriority: "Reading priority",
    viewReason: "view scoring reasons",
    whySelected: "Why this article was selected",
    reasonUnavailable: "Claude classification was unavailable for this item; its tags come from keyword matching and the HyDE semantic score.",
    keywordScore: "Keyword score",
    semanticScore: "Semantic score",
    pipelineTotal: "Pipeline total",
    taggedBy: "Tags",
    byKeyword: "keyword",
    byLlm: "Claude",
    byTitle: "headline",
    reportIssue: "Report classification issue",
    loadMore: "Load more",
    emptyNoFund: "Select at least one fund",
    emptyNoScore: "No articles reach the score threshold",
    emptyNoResults: "No articles match these filters",
    emptyHint: "Select funds across both groups, then set strategy, date and keywords.",
    viewAll: "View all news",
    loadError: "Unable to load dashboard data",
    retry: "Retry",
    summaryTitle: "Filtered news summary",
    collapse: "Collapse",
    allFirmsWord: "All institutions",
    keywordWord: "Keyword",
    minScoreWord: "Minimum score",
    anyTime: "Any time",
    lastNDays: (n) => `Last ${n} days`,
    summaryCounts: (reports, stories, priority) => `The current filter returns <strong>${reports}</strong> articles, <strong>${stories}</strong> distinct headlines after merging duplicates, of which <strong>${priority}</strong> reach the 65-point priority threshold.`,
    summaryDates: (a, b) => ` Dates range from ${a} to ${b}.`,
    synthesisTitle: "Overall read",
    analysisLabel: "Analysis and open points: ",
    evidence: (n) => `View evidence · ${n} representative articles`,
    summaryFootnote: "Generated from every article in the current filter, not only the loaded cards. The analysis uses headline rules on topics and deal stage; it does not read full text or call an AI. A risk-word mention is not confirmation that a risk occurred, and article counts are not event counts.",
    reportEyebrow: "Feedback",
    reportTitle: "Report classification issue",
    reportReason: "Reason",
    wrongGp: "Wrong GP",
    wrongSector: "Wrong strategy",
    notCredit: "Not credit related",
    correctGps: "Correct GP(s)",
    correctSectors: "Correct strategy(ies)",
    reportDetails: "Additional reason",
    cancelReport: "Cancel",
    submitReport: "Submit report",
  },
  zh: {
    brandTag: "另类投资情报",
    monitoringUniverse: "MONITORING UNIVERSE",
    allFunds: "全部基金",
    invested: "已投基金",
    watch: "关注基金",
    selectGroup: "全选本组",
    addFirm: "+ 新增机构",
    hideFirmManager: "收起机构管理",
    firmName: "机构名称",
    firmAliases: "检索别名（可选）",
    firmGroup: "所属分组",
    firmNamePlaceholder: "例如 Ares Management",
    firmAliasPlaceholder: "用逗号分隔，最多 5 个",
    firmHint: "完整机构名称更准确；名称与别名均按精确短语在已保存标题中匹配。",
    addAndSearch: "新增并检索",
    remove: "移除",
    firmStored: "保存在当前浏览器，可新增 20 家。",
    firmExists: "机构已存在",
    firmInvalid: "请输入有效机构名称",
    firmStorageFail: "浏览器存储不可用，新增机构仅在本次页面中保留。",
    firmReadFail: "浏览器中的机构列表无法读取，可重新新增。",
    coverageNotes: "COVERAGE NOTES",
    coverageNoteA: "公开新闻 · 英文优先\n每小时更新 · Claude 分类",
    coverageNoteB: "Blue Owl 含 Dyal\nTPG 含 Angelo Gordon",
    githubSettingsButton: "GitHub 连接",
    githubEyebrow: "实时刷新",
    githubTitle: "连接 GitHub 以刷新今日新闻",
    githubIntro: "刷新会在 GitHub Actions 中运行今日新闻更新（抓取、Claude 分类、语义评分、翻译），并在新数据部署后自动重新加载页面。每小时的自动更新照常运行。",
    githubSteps: "在 GitHub 创建一个仅限本仓库、Actions 权限为 Read and write 的 fine-grained personal access token，粘贴到下方。令牌只保存在当前浏览器。",
    githubTokenLabel: "GitHub 令牌",
    githubTokenSaved: "当前浏览器已保存令牌；留空即沿用。",
    githubOpenActions: "改为打开 Actions 页面",
    githubForget: "移除令牌",
    githubSave: "保存并刷新",
    githubTokenMissing: "请先粘贴令牌，或打开 Actions 页面手动运行。",
    refreshPhaseDispatching: "正在启动…",
    refreshPhaseQueued: "排队中",
    refreshPhaseRunning: "正在更新",
    refreshPhaseDeploying: "正在部署",
    refreshDone: (when) => `今日新闻已于 ${when} 刷新。`,
    refreshFailedRun: "GitHub Actions 运行失败，请打开 Actions 页面查看日志。",
    refreshTimeoutRun: "运行时间超出预期；下次刷新页面时会显示新数据。",
    refreshTimeoutDeploy: "运行已完成但新数据尚未部署，请几分钟后刷新页面。",
    refreshAuthError: "GitHub 拒绝了该令牌（401/403）。请确认它对本仓库拥有 Actions 读写权限。",
    refreshNotFound: "未找到工作流（404）。请检查仓库名称以及默认分支上是否存在该工作流文件。",
    refreshNetworkError: (detail) => `无法连接 GitHub：${detail}`,
    topbarTitle: "AID 基金投资追踪",
    topNote: "PUBLIC NEWS INTELLIGENCE",
    eyebrow: "PRIVATE MARKETS / CREDIT",
    heroTitle: "追踪资本的下一步",
    heroPunct: "。",
    heroSubtitle: "机构动态、法律事件与信用策略，一处检索。",
    refreshNews: "刷新新闻",
    loadingNews: "正在检索",
    eventAll: "头条 / 全部",
    eventLawsuit: "Lawsuit · 诉讼",
    eventFinancing: "融资 / 交易",
    eventFundraising: "新基金 / 募资",
    searchPlaceholder: "搜索关键词，例如 insurance、data center、fund close…",
    searchButton: "搜索",
    startDate: "开始日期",
    endDate: "结束日期",
    rangeTo: "至",
    applyDates: "应用日期",
    rangeHint: "包含起止日期；可只填一端。",
    rangeError: "请填写有效日期，开始日期不能晚于结束日期。",
    exactDate: "指定日期",
    today: "今天",
    exactHint: (n) => `该日期已保存 ${n} 条新闻`,
    dateLabel: "日期",
    days7: "近 7 天",
    days30: "近 30 天",
    days90: "近 90 天",
    days365: "近一年",
    daysAll: "不限时间",
    daysExact: "指定日期…",
    daysCustom: "自定义日期…",
    minScoreLabel: "重要新闻筛选",
    scoreAll: "全部分数",
    score50: "50 分以上",
    score65: "65 分以上 · 优先阅读",
    score80: "80 分以上 · 高优先级",
    weightSettings: "加权排序设置",
    weightIntro: "总分 = 五项指标 × 权重，按权重总和归一化到 100 分。分数是阅读优先级，不是事实核验或投资评级。",
    weightNoteA: "诉讼、信用风险、最终关账、重大交易优先；律师征集与一般股价评论降权。Reuters / Bloomberg / FT / WSJ 预设优先，行业媒体次之，新闻稿另设权重；来源身份由公开来源名称匹配。",
    weightNoteB: "机构相关度按标题是否点名机构评分；策略相关度结合关键词命中与语义（HyDE）匹配；时效按检索时 1 / 7 / 30 / 90 天分档。各项分值在检索时固定，此处只重新加权。",
    zeroWeights: "全部权重为零时，所有新闻得分为 0。",
    resetWeights: "恢复默认权重",
    weight: "权重",
    partInstitution: "机构相关度",
    partStrategy: "策略相关度",
    partEvent: "事件重要性",
    partSource: "来源优先级",
    partFreshness: "时效",
    generateSummary: "生成 Summary 概要",
    regenerateSummary: "重新生成概要",
    sortImportance: "重要性优先",
    sortRecent: "最新优先",
    sortOldest: "最早优先",
    sortInstitution: "机构相关度",
    sortStrategy: "策略相关度",
    sortEvent: "事件重要性",
    sortSource: "来源优先级",
    sortFreshness: "时效",
    legalNote: "检索诉讼、和解和法院相关新闻。标题提及不代表该机构是被告；未检索到报道不代表不存在诉讼。案件与进展请核对原文和法院记录。",
    resultsAll: "最新新闻",
    resultsLawsuit: "法律事件",
    resultsFundraising: "新基金与募资",
    resultsFinancing: "融资与交易",
    fundsSelected: (n) => `${n} 家基金`,
    noFundSelected: "未选择基金",
    allStrategies: "全部策略",
    earliest: "最早",
    todayWord: "今天",
    scoreAtLeast: (n, total) => `≥${n} 分（检索到 ${total} 条）`,
    resetFilters: "重置筛选",
    focusStrategies: "重点策略",
    addStrategy: "+ 新增策略",
    hideStrategyManager: "收起策略管理",
    strategyGroup: "所属分类",
    strategyName: "策略名称",
    strategyKeywords: "检索关键词",
    strategyNamePlaceholder: "例如 Infrastructure Debt",
    strategyKeywordPlaceholder: "infrastructure debt, infrastructure credit",
    strategyHint: "填写 1–5 个关键词，用逗号分隔。任一关键词命中即可；用于标题标签和相关度评分。最多新增 20 个策略，保存在当前浏览器。",
    strategyExists: "策略已存在",
    strategyInvalid: "请填写有效策略",
    strategyStorageFail: "浏览器存储不可用，策略仅在本次页面中保留。",
    strategyReadFail: "保存的策略无法读取，请重新新增。",
    addSubstrategy: "+ 新增子策略",
    strategyGroups: "策略分类",
    coverageTitle: "本次检索覆盖",
    coverageResponded: (n) => `/ ${n} 家机构响应`,
    coverageFailed: (n) => `${n} 家机构查询失败；结果不完整。`,
    coverageItems: (n) => `${n} 条`,
    coverageFailedWord: "失败",
    coverageSelected: (n) => `已存 ${n}`,
    searching: "检索中",
    runAt: "本次查询",
    coverageFoot: "数量为去重前候选；每个日期按机构保留评分最高的新闻。",
    notesTitle: "阅读提示",
    notesA: "事件与策略标签根据标题关键词与 Claude 分类生成，仅供导航。",
    notesB: "募资报道可能涉及目标规模、首关或最终关账，金额与阶段以原文为准。",
    notesC: "来源：Google News 公开索引及行业媒体订阅源。可能有遗漏、重复转载或付费墙；非完整法院案件数据库。",
    queryToggle: "检索式与备用搜索",
    openGoogleNews: "打开 Google News",
    footerNote: "公开信息研究工具 · 新闻日期按发布日期显示",
    feedNote: (updated) => `当前显示 ${updated} 更新的已保存快照。分数在检索时计算；筛选、加权与排序在本浏览器中完成。`,
    tagHeadline: "头条",
    tagLawsuit: "诉讼提及",
    tagFinancing: "融资 / 交易",
    tagFundraising: "基金 / 募资",
    queryTag: "检索词",
    newsSource: "新闻来源",
    highPriority: "高优先级",
    priorityReading: "优先阅读",
    readingPriority: "阅读优先级",
    viewReason: "查看评分理由",
    whySelected: "入选原因",
    reasonUnavailable: "该条目当时未能调用 Claude 分类，标签来自关键词匹配与 HyDE 语义得分。",
    keywordScore: "关键词得分",
    semanticScore: "语义得分",
    pipelineTotal: "流水线总分",
    taggedBy: "标签来源",
    byKeyword: "关键词",
    byLlm: "Claude",
    byTitle: "标题",
    reportIssue: "回报分类问题",
    loadMore: "加载更多",
    emptyNoFund: "请勾选至少一家基金",
    emptyNoScore: "没有达到分数门槛的报道",
    emptyNoResults: "当前条件下未检索到报道",
    emptyHint: "可跨两组多选基金，再设置策略、日期和关键词。",
    viewAll: "查看全部新闻",
    loadError: "无法加载仪表板数据",
    retry: "重新检索",
    summaryTitle: "筛选新闻概要",
    collapse: "收起",
    allFirmsWord: "全部机构",
    keywordWord: "关键词",
    minScoreWord: "最低分数",
    anyTime: "不限时间",
    lastNDays: (n) => `近 ${n} 天`,
    summaryCounts: (reports, stories, priority) => `当前筛选得到 <strong>${reports}</strong> 条报道，合并同标题转载后为 <strong>${stories}</strong> 个标题，其中 <strong>${priority}</strong> 个达到 65 分优先阅读门槛。`,
    summaryDates: (a, b) => `报道日期为 ${a} 至 ${b}。`,
    synthesisTitle: "综合判断",
    analysisLabel: "分析与待核实：",
    evidence: (n) => `查看依据 · ${n} 条代表报道`,
    summaryFootnote: "依据当前筛选后的全部结果生成，不限于已加载的新闻卡片。综合分析基于标题识别的主题与阶段规则，未读取正文、未调用 AI；风险词提及不等于确认风险已发生，新闻数量不代表事件数量。",
    reportEyebrow: "反馈",
    reportTitle: "回报分类问题",
    reportReason: "原因",
    wrongGp: "GP 错误",
    wrongSector: "策略错误",
    notCredit: "非信贷相关",
    correctGps: "正确 GP",
    correctSectors: "正确策略",
    reportDetails: "补充原因",
    cancelReport: "取消",
    submitReport: "提交回报",
  },
};

const REASONS = {
  en: {
    title_names_gp: "headline names the institution",
    llm_tagged_gp: "Claude tagged the institution from the article text",
    body_mentions_gp: "institution appears in the article body only",
    query_only: "institution matched only through the search query",
    title_hits_strategy: "headline hits a focus strategy",
    llm_strategy: "Claude assigned a strategy from the text",
    body_strategy: "strategy keywords appear in the body only",
    no_strategy: "no strategy keyword hit",
    lawsuit: "lawsuit / legal event mention",
    major_signal: "close, major transaction or credit-risk signal",
    fundraising: "fund / fundraising event",
    financing: "financing / deal event",
    stock_commentary: "stock price / dividend commentary down-weighted",
    solicitation: "law-firm solicitation / investor alert down-weighted",
    routine: "routine institution update",
    tier_top: "preset priority financial media",
    tier_filing: "regulatory filing",
    tier_trade: "preset trade press",
    tier_press_release: "press-release channel; verify the issuer",
    tier_aggregator: "investment commentary / aggregator source",
    tier_other: "other source; not individually assessed",
    within_24h: "within 24 hours of retrieval",
    within_7d: "within 7 days of retrieval",
    within_30d: "within 30 days of retrieval",
    within_90d: "within 90 days of retrieval",
    older: "older than 90 days at retrieval",
    estimated: "estimated (migrated from the earlier dashboard)",
    semanticNote: (v) => `semantic match ${v}%`,
    llmNote: (v) => `Claude importance ${v}%`,
    daysAgo: (d) => `${d} day(s) before retrieval`,
  },
  zh: {
    title_names_gp: "标题点名机构",
    llm_tagged_gp: "Claude 依据正文识别出机构",
    body_mentions_gp: "机构仅在正文中出现",
    query_only: "机构仅在检索结果中匹配",
    title_hits_strategy: "标题命中重点策略",
    llm_strategy: "Claude 依据正文判定策略",
    body_strategy: "策略关键词仅在正文中出现",
    no_strategy: "标题未命中策略关键词",
    lawsuit: "诉讼 / 法律事件提及",
    major_signal: "关账、重大交易或信用风险信号",
    fundraising: "基金 / 募资事件",
    financing: "融资 / 交易事件",
    stock_commentary: "股价 / 股息评论降权",
    solicitation: "律师征集 / 投资者提醒降权",
    routine: "常规机构动态",
    tier_top: "预设优先财经媒体",
    tier_filing: "监管文件",
    tier_trade: "预设行业专业媒体",
    tier_press_release: "新闻稿渠道；需核对发行方",
    tier_aggregator: "投资评论 / 聚合来源",
    tier_other: "其他来源；尚未单独评估",
    within_24h: "检索时在 24 小时内",
    within_7d: "检索时在 7 天内",
    within_30d: "检索时在 30 天内",
    within_90d: "检索时在 90 天内",
    older: "检索时已超过 90 天",
    estimated: "估算值（由旧版仪表板迁移）",
    semanticNote: (v) => `语义匹配 ${v}%`,
    llmNote: (v) => `Claude 重要性 ${v}%`,
    daysAgo: (d) => `检索前约 ${d} 天`,
  },
};

const state = {
  language: readStorage(STORAGE.language, "en", (v) => (v === "zh" ? "zh" : "en")),
  firms: [],
  customFirms: [],
  customStrategies: [],
  queryInput: "",
  query: "",
  event: "all",
  dateMode: "30",
  exactDate: todayKey(),
  start: "",
  end: "",
  strategy: "",
  minScore: 0,
  sort: "importance",
  weights: { ...DEFAULT_WEIGHTS },
  visible: PAGE_SIZE,
  showFirmManager: false,
  showStrategyManager: false,
  strategyManagerGroup: "other",
  showQueries: false,
  summary: null,
  loading: true,
  error: "",
  firmError: "",
  strategyError: "",
  reportingItem: null,
  githubToken: readStorage(STORAGE.githubToken, ""),
  refresh: null, // { phase, startedAt, message, runUrl }
};
let data = null;
let allItems = [];

const $ = (selector) => document.querySelector(selector);
const t = () => UI[state.language];
const r = () => REASONS[state.language];

init();

async function init() {
  loadLocalState();
  bindStaticEvents();
  renderStatic();
  await loadData();
}

function readStorage(key, fallback, validate) {
  try {
    const raw = localStorage.getItem(key);
    if (raw === null) return fallback;
    return validate ? validate(raw) : raw;
  } catch {
    return fallback;
  }
}
function writeStorage(key, value) {
  try {
    localStorage.setItem(key, value);
    return true;
  } catch {
    return false;
  }
}

function loadLocalState() {
  try {
    const raw = localStorage.getItem(STORAGE.firms);
    if (raw) state.customFirms = sanitizeCustomFirms(JSON.parse(raw));
  } catch {
    state.firmError = t().firmReadFail;
  }
  try {
    const raw = localStorage.getItem(STORAGE.strategies);
    if (raw) state.customStrategies = sanitizeCustomStrategies(JSON.parse(raw));
  } catch {
    state.strategyError = t().strategyReadFail;
  }
  try {
    const raw = localStorage.getItem(STORAGE.weights);
    if (raw) {
      const parsed = JSON.parse(raw);
      WEIGHT_KEYS.forEach((key) => {
        const value = Number(parsed[key]);
        if (Number.isFinite(value)) state.weights[key] = Math.max(0, Math.min(100, Math.round(value)));
      });
    }
  } catch {
    state.weights = { ...DEFAULT_WEIGHTS };
  }
}

async function loadData() {
  state.loading = true;
  state.error = "";
  renderAll();
  try {
    const response = await fetch(DATA_URL, { cache: "no-store" });
    if (!response.ok) throw new Error(`Unable to load ${DATA_URL} (${response.status})`);
    data = await response.json();
    allItems = flattenItems(data);
    const known = firmList().map((firm) => firm.id);
    state.firms = state.firms.length ? state.firms.filter((id) => known.includes(id)) : known;
    if (!state.firms.length) state.firms = known;
  } catch (error) {
    state.error = error.message;
  } finally {
    state.loading = false;
    state.summary = null;
    renderAll();
  }
}

/* ---------- Data model ---------- */
function scopeGps() {
  return data?.scope?.gps?.length ? data.scope.gps : DEFAULT_GPS;
}
function scopeGroups() {
  const groups = data?.scope?.gpGroups;
  if (groups && (groups.invested?.length || groups.watch?.length)) return groups;
  return DEFAULT_GROUPS;
}
function firmList() {
  const groups = scopeGroups();
  const builtin = scopeGps().map((name) => ({
    id: name,
    name,
    group: groups.watch?.includes(name) ? "watch" : "invested",
    aliases: DEFAULT_ALIASES[name] || [name],
    custom: false,
  }));
  const customs = state.customFirms.map((firm) => ({ ...firm, custom: true, aliases: [firm.name, ...firm.aliases] }));
  return [...builtin, ...customs];
}
function firmById(id) {
  return firmList().find((firm) => firm.id === id);
}
function strategyList() {
  return [...BUILTIN_STRATEGIES, ...state.customStrategies.map(customStrategyEntry)];
}
function strategyById(id) {
  return strategyList().find((strategy) => strategy.id === id);
}
function strategyLabel(strategy) {
  if (!strategy) return "";
  if (strategy.custom) return strategy.name;
  return state.language === "zh" ? strategy.cn : strategy.name;
}
function strategyTitle(strategy) {
  if (!strategy) return "";
  if (strategy.custom) return strategy.keywords.join(" / ");
  return state.language === "zh" ? strategy.name : strategy.cn;
}
function groupLabel(group) {
  return state.language === "zh" ? group.cn : group.name;
}
function customStrategyEntry(strategy) {
  const escaped = strategy.keywords.map((keyword) => keyword.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"));
  return {
    id: strategy.id,
    name: strategy.name,
    cn: strategy.name,
    group: strategy.group || "other",
    custom: true,
    keywords: strategy.keywords,
    pattern: new RegExp(`(?:^|[^\\p{L}\\p{N}])(?:${escaped.join("|")})(?:$|[^\\p{L}\\p{N}])`, "iu"),
  };
}

function flattenItems(payload) {
  const seen = new Set();
  const items = [];
  Object.entries(payload?.dates || {}).forEach(([dateKey, digest]) => {
    const bucket = [...(digest.items || [])];
    Object.values(digest.byGp || {}).forEach((list) => bucket.push(...list));
    bucket.forEach((item) => {
      const key = item.id || item.url;
      if (!key || seen.has(key)) return;
      seen.add(key);
      items.push({ ...item, date: (item.publishedAt || dateKey || "").slice(0, 10) });
    });
  });
  return items;
}

function itemStrategies(item) {
  const stored = item.strategies?.length ? item.strategies : (item.sectors || []).flatMap((sector) => LEGACY_SECTOR_MAP[sector] || []);
  const title = item.title || "";
  const matched = strategyList().filter((strategy) => strategy.pattern.test(title)).map((strategy) => strategy.id);
  return [...new Set([...stored, ...matched])];
}
function itemEvents(item) {
  if (Array.isArray(item.events)) return item.events;
  const text = `${item.title || ""} ${item.lede || item.summary || ""}`;
  return Object.entries(EVENT_PATTERNS).filter(([, pattern]) => pattern.test(text)).map(([id]) => id);
}
function itemFirms(item) {
  const firms = [...(item.gps || [])];
  const haystack = `${item.title || ""} ${item.summary || ""} ${item.lede || ""}`;
  state.customFirms.forEach((firm) => {
    if ([firm.name, ...firm.aliases].some((alias) => phraseRegex(alias).test(haystack))) firms.push(firm.id);
  });
  return firms;
}
function phraseRegex(phrase) {
  return new RegExp(`(?:^|[^\\p{L}\\p{N}])${phrase.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}(?:$|[^\\p{L}\\p{N}])`, "iu");
}

function ratingParts(item) {
  if (item.rating?.parts) return item.rating.parts;
  return deriveParts(item);
}
function deriveParts(item) {
  const title = item.title || "";
  const gps = item.gps || [];
  const titleGps = gps.filter((gp) => (DEFAULT_ALIASES[gp] || [gp]).some((alias) => phraseRegex(alias).test(title)));
  const llmGps = item.classificationBreakdown?.llmGps || [];
  const institution = titleGps.length
    ? { value: 1, code: "title_names_gp", gps: titleGps }
    : llmGps.length
      ? { value: 0.7, code: "llm_tagged_gp", gps: llmGps }
      : gps.length
        ? { value: 0.5, code: "body_mentions_gp", gps }
        : { value: 0.25, code: "query_only", gps: [] };
  const strategies = itemStrategies(item);
  const titleHit = strategyList().some((strategy) => strategies.includes(strategy.id) && strategy.pattern.test(title));
  const tagValue = titleHit ? 1 : strategies.length ? 0.6 : 0;
  const strategy = { value: tagValue, code: titleHit ? "title_hits_strategy" : strategies.length ? "body_strategy" : "no_strategy", tagValue, strategies };
  const breakdown = item.scoreBreakdown || {};
  if (breakdown.semanticEnabled && Number.isFinite(Number(breakdown.semanticScore))) {
    const semantic = Math.max(0, Math.min(1, Number(breakdown.semanticScore) / 12));
    strategy.semanticValue = Math.round(semantic * 100) / 100;
    strategy.value = Math.round(((tagValue + semantic) / 2) * 100) / 100;
  }
  const events = itemEvents(item);
  let eventValue = 0.2;
  let eventCode = "routine";
  if (events.includes("financing")) [eventValue, eventCode] = [0.7, "financing"];
  if (events.includes("fundraising")) [eventValue, eventCode] = [0.8, "fundraising"];
  if (MAJOR_SIGNAL.test(title)) [eventValue, eventCode] = [0.95, "major_signal"];
  if (events.includes("lawsuit")) [eventValue, eventCode] = [1, "lawsuit"];
  if (STOCK_COMMENTARY.test(title) && !events.includes("lawsuit") && !events.includes("fundraising")) [eventValue, eventCode] = [0.15, "stock_commentary"];
  if (SOLICITATION.test(title)) [eventValue, eventCode] = [0.1, "solicitation"];
  const tier = SOURCE_TIERS.find(([, , pattern]) => pattern.test(item.source || ""));
  const source = tier ? { value: tier[1], code: tier[0], source: item.source } : { value: 0.35, code: "tier_other", source: item.source };
  return {
    institution,
    strategy,
    event: { value: eventValue, code: eventCode, ruleValue: eventValue, events },
    source,
    freshness: { value: 0.8, code: "estimated" },
  };
}
function weightedScore(parts, weights = state.weights) {
  const total = WEIGHT_KEYS.reduce((sum, key) => sum + Math.max(0, weights[key] || 0), 0);
  if (!total) return 0;
  const weighted = WEIGHT_KEYS.reduce((sum, key) => sum + Number(parts[key]?.value || 0) * Math.max(0, weights[key] || 0), 0);
  return Math.round((weighted / total) * 100);
}

/* ---------- View computation ---------- */
function dateBounds() {
  const today = parseDate(todayKey());
  if (state.dateMode === "all") return { start: null, end: null };
  if (state.dateMode === "exact") return { start: state.exactDate, end: state.exactDate };
  if (state.dateMode === "custom") return { start: state.start || null, end: state.end || null };
  const days = Number(state.dateMode) || 30;
  return { start: toDateKey(addDays(today, -(days - 1))), end: toDateKey(today) };
}
function computeView() {
  const bounds = dateBounds();
  const query = state.query.trim().toLowerCase();
  const rated = allItems
    .filter((item) => {
      if (bounds.start && item.date < bounds.start) return false;
      if (bounds.end && item.date > bounds.end) return false;
      return true;
    })
    .map((item) => {
      const firms = itemFirms(item);
      const strategies = itemStrategies(item);
      const events = itemEvents(item);
      const parts = ratingParts(item);
      return { item, firms, strategies, events, parts, score: weightedScore(parts) };
    })
    .filter((entry) => entry.firms.some((firm) => state.firms.includes(firm)))
    .filter((entry) => state.event === "all" || entry.events.includes(state.event))
    .filter((entry) => !state.strategy || entry.strategies.includes(state.strategy))
    .filter((entry) => {
      if (!query) return true;
      const item = entry.item;
      return [item.title, item.titleZh, item.summary, item.summaryZh, item.lede, item.source].some((field) => String(field || "").toLowerCase().includes(query));
    });
  const shown = rated.filter((entry) => entry.score >= state.minScore).sort(sorter());
  return { rated, shown };
}
function sorter() {
  const byDateDesc = (a, b) => (b.item.date || "").localeCompare(a.item.date || "");
  if (state.sort === "recent") return (a, b) => byDateDesc(a, b) || b.score - a.score;
  if (state.sort === "oldest") return (a, b) => (a.item.date || "").localeCompare(b.item.date || "") || b.score - a.score;
  if (WEIGHT_KEYS.includes(state.sort)) {
    const key = state.sort;
    return (a, b) => Number(b.parts[key]?.value || 0) - Number(a.parts[key]?.value || 0) || b.score - a.score || byDateDesc(a, b);
  }
  return (a, b) => b.score - a.score || byDateDesc(a, b);
}

/* ---------- Rendering ---------- */
function renderStatic() {
  document.querySelectorAll("[data-icon]").forEach((node) => {
    node.innerHTML = icon(node.dataset.icon, Number(node.dataset.size) || 16);
  });
}
function renderAll() {
  document.documentElement.lang = state.language === "zh" ? "zh-Hans" : "en";
  applyUiText();
  renderSidebar();
  renderTop();
  renderResults();
  renderContext();
}
function applyUiText() {
  document.querySelectorAll("[data-i18n]").forEach((node) => {
    const value = t()[node.dataset.i18n];
    if (typeof value === "string") node.textContent = value;
  });
  $("#searchInput").placeholder = t().searchPlaceholder;
  document.querySelectorAll("[data-lang-pill]").forEach((node) => node.classList.toggle("active", node.dataset.langPill === state.language));
  $("#coverageNoteA").innerHTML = t().coverageNoteA.split("\n").map(escapeHtml).join("<br>");
  $("#coverageNoteB").innerHTML = t().coverageNoteB.split("\n").map(escapeHtml).join("<br>");
  $("#githubSettingsButton").textContent = t().githubSettingsButton;
  $("#githubActionsLink").href = MANUAL_REFRESH_WORKFLOW_URL;
  renderRefreshButton();
}
function renderRefreshButton() {
  const busy = state.loading || (state.refresh && !["done", "error"].includes(state.refresh.phase));
  let label = state.loading ? t().loadingNews : t().refreshNews;
  if (state.refresh && busy) {
    const phases = { dispatching: t().refreshPhaseDispatching, queued: t().refreshPhaseQueued, running: t().refreshPhaseRunning, deploying: t().refreshPhaseDeploying };
    const elapsed = Math.max(0, Math.floor((Date.now() - state.refresh.startedAt) / 1000));
    label = `${phases[state.refresh.phase] || state.refresh.phase} ${String(Math.floor(elapsed / 60)).padStart(2, "0")}:${String(elapsed % 60).padStart(2, "0")}`;
  }
  $("#refreshLabel").textContent = label;
  $("#refreshButton").disabled = Boolean(busy);
  $("#refreshIcon").innerHTML = icon("refresh-cw", 16, busy ? "spin" : "");
}

function renderSidebar() {
  const firms = firmList();
  $("#universeCount").textContent = firms.length;
  $("#allFirmsCount").textContent = `${state.firms.length} / ${firms.length}`;
  $("#allFirms").checked = state.firms.length === firms.length && firms.length > 0;
  const counts = countsByFirm();
  const groups = [
    { id: "invested", name: t().invested },
    { id: "watch", name: t().watch },
  ];
  $("#fundGroups").innerHTML = groups
    .map((group) => {
      const members = firms.filter((firm) => firm.group === group.id);
      const selected = members.filter((firm) => state.firms.includes(firm.id)).length;
      return `
        <fieldset class="fund-group">
          <legend>${escapeHtml(group.name)}</legend>
          <label class="group-select">
            <input type="checkbox" data-group-select="${group.id}" ${selected === members.length && selected > 0 ? "checked" : ""} data-indeterminate="${selected > 0 && selected < members.length}" />
            <span>${t().selectGroup}</span>
            <small>${selected} / ${members.length}</small>
          </label>
          ${members
            .map(
              (firm) => `
            <label class="firm ${state.firms.includes(firm.id) ? "active" : ""}">
              <input type="checkbox" data-firm="${escapeAttribute(firm.id)}" ${state.firms.includes(firm.id) ? "checked" : ""} />
              <span>${escapeHtml(firm.name)}</span>
              <small>${counts[firm.id] ?? "—"}</small>
            </label>`
            )
            .join("")}
        </fieldset>`;
    })
    .join("");
  document.querySelectorAll("[data-indeterminate]").forEach((node) => {
    node.indeterminate = node.dataset.indeterminate === "true";
  });

  $("#addFirmToggle").textContent = state.showFirmManager ? t().hideFirmManager : t().addFirm;
  $("#firmManager").innerHTML = state.showFirmManager
    ? `
      <div class="firm-manager">
        <form id="firmForm">
          <label>${t().firmName}<input name="name" maxlength="80" placeholder="${escapeAttribute(t().firmNamePlaceholder)}" required /></label>
          <label>${t().firmAliases}<input name="aliases" maxlength="400" placeholder="${escapeAttribute(t().firmAliasPlaceholder)}" /></label>
          <label>${t().firmGroup}
            <select name="group">
              <option value="invested">${t().invested}</option>
              <option value="watch" selected>${t().watch}</option>
            </select>
          </label>
          <p>${t().firmHint}</p>
          <button type="submit" ${state.customFirms.length >= 20 ? "disabled" : ""}>${t().addAndSearch}</button>
        </form>
        ${state.customFirms
          .map(
            (firm) => `<div class="custom-item"><span>${escapeHtml(firm.name)}</span><button type="button" data-action="remove-firm" data-firm="${escapeAttribute(firm.id)}" aria-label="${t().remove} ${escapeAttribute(firm.name)}">${t().remove}</button></div>`
          )
          .join("")}
        <small>${t().firmStored}</small>
      </div>`
    : "";
  const firmError = $("#firmError");
  firmError.hidden = !state.firmError;
  firmError.textContent = state.firmError;
}
function countsByFirm() {
  const bounds = dateBounds();
  const counts = {};
  allItems.forEach((item) => {
    if (bounds.start && item.date < bounds.start) return;
    if (bounds.end && item.date > bounds.end) return;
    itemFirms(item).forEach((firm) => {
      counts[firm] = (counts[firm] || 0) + 1;
    });
  });
  firmList().forEach((firm) => {
    counts[firm.id] = counts[firm.id] || 0;
  });
  return counts;
}

function renderTop() {
  const tabIcons = { all: "newspaper", lawsuit: "scale", financing: "landmark", fundraising: "layers" };
  const tabLabels = { all: t().eventAll, lawsuit: t().eventLawsuit, financing: t().eventFinancing, fundraising: t().eventFundraising };
  $("#eventTabs").innerHTML = EVENT_TABS.map(
    (id) => `<button type="button" class="${state.event === id ? "chosen" : ""}" data-action="select-event" data-event="${id}">${icon(tabIcons[id], 17)}${escapeHtml(tabLabels[id])}</button>`
  ).join("");
  if (document.activeElement !== $("#searchInput")) $("#searchInput").value = state.queryInput;
  $("#dateSelect").value = state.dateMode;
  $("#dateRangeForm").hidden = state.dateMode !== "custom";
  $("#rangeStart").value = state.start;
  $("#rangeEnd").value = state.end;
  $("#exactDateBar").hidden = state.dateMode !== "exact";
  $("#exactDateInput").value = state.exactDate;
  $("#exactDateHint").textContent = t().exactHint(allItems.filter((item) => item.date === state.exactDate).length);
  $("#minScoreSelect").value = String(state.minScore);
  $("#sortSelect").value = state.sort;

  const partLabels = { institution: t().partInstitution, strategy: t().partStrategy, event: t().partEvent, source: t().partSource, freshness: t().partFreshness };
  $("#weightControls").innerHTML = WEIGHT_KEYS.map(
    (key) => `
      <label>${escapeHtml(partLabels[key])}<span data-weight-value="${key}">${state.weights[key]}</span>
        <input type="range" min="0" max="100" step="1" value="${state.weights[key]}" data-weight="${key}" aria-label="${escapeAttribute(partLabels[key])} ${t().weight}" />
      </label>`
  ).join("");
  $("#zeroWeightWarning").hidden = !WEIGHT_KEYS.every((key) => state.weights[key] === 0);
  $("#legalNote").hidden = state.event !== "lawsuit";
  renderCounts();
}
function renderCounts() {
  $("#summaryButton").textContent = state.summary ? t().regenerateSummary : t().generateSummary;
  const view = state.loading || state.error ? null : computeView();
  const titles = { all: t().resultsAll, lawsuit: t().resultsLawsuit, financing: t().resultsFinancing, fundraising: t().resultsFundraising };
  $("#resultsTitle").textContent = titles[state.event];
  $("#resultsCount").textContent = view ? view.shown.length : "…";
  $("#summaryButton").disabled = !view || !view.shown.length;

  const selected = strategyById(state.strategy);
  const bits = [
    state.firms.length ? t().fundsSelected(state.firms.length) : t().noFundSelected,
    `<span>/</span>`,
    selected ? escapeHtml(strategyLabel(selected)) : t().allStrategies,
  ];
  if (state.dateMode === "custom") bits.push(`<span>/</span>`, `${escapeHtml(state.start || t().earliest)} – ${escapeHtml(state.end || t().todayWord)}`);
  if (state.dateMode === "exact") bits.push(`<span>/</span>`, escapeHtml(formatDate(state.exactDate)));
  if (state.query) bits.push(`<span>/</span>`, `“${escapeHtml(state.query)}”`);
  if (state.minScore > 0 && view) bits.push(`<span>/</span>`, escapeHtml(t().scoreAtLeast(state.minScore, view.rated.length)));
  bits.push(`<button type="button" data-action="reset-filters">${t().resetFilters}</button>`);
  $("#selectionLine").innerHTML = bits.join(" ");
}

function renderResults() {
  const focus = FOCUS_STRATEGY_IDS.map(strategyById).filter(Boolean);
  $("#focusStrategies").innerHTML =
    focus.map((strategy) => strategyButton(strategy)).join("") +
    `<button type="button" class="add-strategy" data-action="toggle-strategy-manager">${state.showStrategyManager ? t().hideStrategyManager : t().addStrategy}</button>`;

  const feedNote = $("#feedNote");
  if (state.refresh?.message) {
    feedNote.hidden = false;
    feedNote.textContent = state.refresh.message;
  } else if (data?.updatedAt && !state.loading) {
    feedNote.hidden = false;
    feedNote.textContent = t().feedNote(formatDateTime(data.updatedAt));
  } else {
    feedNote.hidden = true;
  }

  const articles = $("#articles");
  if (state.loading) {
    articles.innerHTML = `<div class="loading">${icon("refresh-cw", 25, "spin")}<h3>${t().loadingNews}</h3><p>${t().fundsSelected(state.firms.length || scopeGps().length)}</p><div class="skeleton"></div><div class="skeleton"></div></div>`;
    renderSummary(null);
    return;
  }
  if (state.error) {
    articles.innerHTML = `<div class="empty">${icon("circle-alert", 28)}<h3>${t().loadError}</h3><p>${escapeHtml(state.error)}</p><button type="button" data-action="reload">${t().retry}</button></div>`;
    renderSummary(null);
    return;
  }
  const view = computeView();
  renderSummary(view);
  if (!view.shown.length) {
    const heading = !state.firms.length ? t().emptyNoFund : view.rated.length ? t().emptyNoScore : t().emptyNoResults;
    articles.innerHTML = `<div class="empty">${icon("search", 32)}<h3>${escapeHtml(heading)}</h3><p>${t().emptyHint}</p><button type="button" data-action="reset-filters">${t().viewAll}</button></div>`;
    return;
  }
  const html = view.shown.slice(0, state.visible).map(renderArticle).join("");
  const more = state.visible < view.shown.length ? `<button type="button" class="load-more" data-action="load-more">${t().loadMore} ${icon("chevron-down", 16)}</button>` : "";
  articles.innerHTML = html + more;
}
function strategyButton(strategy) {
  return `<button type="button" title="${escapeAttribute(strategyTitle(strategy))}" class="${state.strategy === strategy.id ? "selected" : ""}" data-action="select-strategy" data-strategy="${escapeAttribute(strategy.id)}">${escapeHtml(strategyLabel(strategy))}</button>`;
}

function renderArticle(entry) {
  const { item, firms, strategies, events, parts, score } = entry;
  const eventLabels = { headline: t().tagHeadline, lawsuit: t().tagLawsuit, financing: t().tagFinancing, fundraising: t().tagFundraising };
  const shownEvents = events.length ? events : ["headline"];
  const title = displayTitle(localized(item, "title"), item.source);
  const rawSummary = localized(item, "summary");
  const summary = isRedundantSummary(rawSummary, title, item.source) ? "" : rawSummary;
  const partLabels = { institution: t().partInstitution, strategy: t().partStrategy, event: t().partEvent, source: t().partSource, freshness: t().partFreshness };
  const level = score >= 80 ? t().highPriority : score >= 65 ? t().priorityReading : t().readingPriority;
  const breakdown = item.classificationBreakdown || {};
  const rawReason = state.language === "zh" ? breakdown.llmReasonZh || breakdown.llmReason : breakdown.llmReason;
  const reason = /^LLM classification (unavailable|returned invalid JSON)/.test(breakdown.llmReason || "") ? t().reasonUnavailable : rawReason;
  const scoreBreakdown = item.scoreBreakdown || {};
  return `
    <article class="article">
      <div class="article-meta">
        <span class="article-source">${escapeHtml(item.source || t().newsSource)}</span>
        <span>·</span>
        <time datetime="${escapeAttribute(item.date)}">${escapeHtml(formatDate(item.date))}</time>
        <div class="article-tags">
          ${firms.map((firm) => `<button type="button" class="entity-tag" data-action="only-firm" data-firm="${escapeAttribute(firm)}">${escapeHtml(firmById(firm)?.name || firm)}</button>`).join("")}
          ${shownEvents.map((event) => `<span class="event-tag ${escapeAttribute(event)}">${escapeHtml(eventLabels[event] || event)}</span>`).join("")}
          ${strategies
            .map(strategyById)
            .filter(Boolean)
            .map((strategy) => `<button type="button" class="topic-tag" data-action="select-strategy" data-strategy="${escapeAttribute(strategy.id)}">${escapeHtml(strategyLabel(strategy))}</button>`)
            .join("")}
        </div>
        ${state.query ? `<span class="query-tag" title="${escapeAttribute(state.query)}">${t().queryTag}: ${escapeHtml(state.query)}</span>` : ""}
      </div>
      <a class="article-title" href="${escapeAttribute(item.url)}" target="_blank" rel="noopener noreferrer">${escapeHtml(title)}${icon("arrow-up-right", 18)}</a>
      ${summary && summary !== title ? `<p class="article-summary">${escapeHtml(summary)}</p>` : ""}
      <details class="score-details">
        <summary><span class="score ${score >= 65 ? "high" : ""}">${score} / 100</span> ${escapeHtml(level)} · ${t().viewReason}</summary>
        <div>
          ${WEIGHT_KEYS.map((key) => {
            const part = parts[key] || { value: 0, code: "" };
            return `<p><strong>${escapeHtml(partLabels[key])} ${Math.round(Number(part.value || 0) * 100)}%</strong><span>${t().weight} ${state.weights[key]} · ${escapeHtml(partReason(key, part))}</span></p>`;
          }).join("")}
          <div class="why-selected">
            <h4>${t().whySelected}</h4>
            ${reason ? `<p>${escapeHtml(reason)}</p>` : ""}
            <p>${t().taggedBy}: ${escapeHtml(tagSources(item))}</p>
            ${Number.isFinite(Number(scoreBreakdown.finalScore)) ? `<p>${t().keywordScore} ${formatNumber(scoreBreakdown.keywordScore)} · ${t().semanticScore} ${formatNumber(scoreBreakdown.semanticScore)} · ${t().pipelineTotal} ${formatNumber(scoreBreakdown.finalScore)}</p>` : ""}
            <button type="button" class="report-link" data-action="report" data-id="${escapeAttribute(item.id || item.url)}">${t().reportIssue}</button>
          </div>
        </div>
      </details>
    </article>`;
}
function partReason(key, part) {
  const text = r()[part.code] || part.code || "";
  const extras = [];
  if (key === "strategy" && Number.isFinite(Number(part.semanticValue))) extras.push(r().semanticNote(Math.round(part.semanticValue * 100)));
  if (key === "event" && Number.isFinite(Number(part.llmValue))) extras.push(r().llmNote(Math.round(part.llmValue * 100)));
  if (key === "freshness" && Number.isFinite(Number(part.days)) && part.code !== "within_24h") extras.push(r().daysAgo(Math.floor(part.days)));
  if (key === "source" && part.source) extras.unshift(part.source);
  return [text, ...extras].filter(Boolean).join(" · ");
}
function tagSources(item) {
  const breakdown = item.classificationBreakdown || {};
  const sources = [];
  if ((breakdown.titleGps || []).length) sources.push(`${t().byTitle}: ${breakdown.titleGps.join(", ")}`);
  if ((breakdown.keywordGps || []).length) sources.push(`${t().byKeyword}: ${breakdown.keywordGps.join(", ")}`);
  if ((breakdown.llmGps || []).length) sources.push(`${t().byLlm}: ${breakdown.llmGps.join(", ")}`);
  const llmStrategies = (breakdown.llmStrategies || breakdown.llmSectors || []).map((id) => strategyLabel(strategyById(id)) || id);
  if (llmStrategies.length) sources.push(`${t().byLlm} ${t().partStrategy.toLowerCase()}: ${llmStrategies.join(", ")}`);
  return sources.join(" · ") || "—";
}

function renderSummary(view) {
  const node = $("#newsSummary");
  if (!view || !state.summary) {
    node.hidden = true;
    node.innerHTML = "";
    return;
  }
  const s = state.summary;
  const selectedStrategy = strategyById(state.strategy);
  const eventLabels = { all: t().eventAll, lawsuit: t().eventLawsuit, financing: t().eventFinancing, fundraising: t().eventFundraising };
  const scope = [
    state.firms.length ? state.firms.map((id) => firmById(id)?.name || id).join(" · ") : t().allFirmsWord,
    selectedStrategy ? strategyLabel(selectedStrategy) : t().allStrategies,
    eventLabels[state.event],
    state.dateMode === "custom"
      ? `${state.start || t().earliest} – ${state.end || t().todayWord}`
      : state.dateMode === "all"
        ? t().anyTime
        : state.dateMode === "exact"
          ? formatDate(state.exactDate)
          : t().lastNDays(state.dateMode),
    state.query ? `${t().keywordWord}: ${state.query}` : "",
    `${t().minScoreWord} ${state.minScore}`,
  ]
    .filter(Boolean)
    .join(" · ");
  node.hidden = false;
  node.innerHTML = `
    <div class="summary-heading"><h3>${t().summaryTitle}</h3><button type="button" data-action="close-summary">${t().collapse}</button></div>
    <p class="summary-scope">${escapeHtml(scope)}</p>
    <p>${t().summaryCounts(s.reports, s.stories, s.priority)}${s.oldest ? t().summaryDates(formatDate(s.oldest), formatDate(s.newest)) : ""}</p>
    <h4>${t().synthesisTitle}</h4>
    <p class="summary-synthesis">${escapeHtml(s.analysis.synthesis)}</p>
    ${s.analysis.sections
      .map(
        (section) => `
      <div class="analysis-section">
        <h4>${escapeHtml(section.title)}</h4>
        <p>${escapeHtml(section.observation)}</p>
        <p><strong>${t().analysisLabel}</strong>${escapeHtml(section.interpretation)}</p>
        <details>
          <summary>${t().evidence(section.evidence.length)}</summary>
          <ul>${section.evidence
            .map((e) => `<li><a href="${escapeAttribute(e.url)}" target="_blank" rel="noopener noreferrer">${escapeHtml(displayTitle(localized(e, "title"), e.source))}</a><small>${escapeHtml(e.source || "")} · ${escapeHtml(formatDate(e.date))}</small></li>`)
            .join("")}</ul>
        </details>
      </div>`
      )
      .join("")}
    <p class="summary-footnote">${t().summaryFootnote}</p>`;
}

function renderContext() {
  $("#allStrategiesButton").textContent = t().allStrategies;
  $("#allStrategiesButton").classList.toggle("selected", !state.strategy);
  const manager = $("#strategyManager");
  manager.hidden = !state.showStrategyManager;
  manager.innerHTML = state.showStrategyManager
    ? `
      <form id="strategyForm">
        <label>${t().strategyGroup}
          <select name="group" aria-label="${t().strategyGroup}">
            ${STRATEGY_GROUPS.map((group) => `<option value="${group.id}" ${group.id === state.strategyManagerGroup ? "selected" : ""}>${escapeHtml(groupLabel(group))}</option>`).join("")}
          </select>
        </label>
        <label>${t().strategyName}<input name="name" maxlength="80" placeholder="${escapeAttribute(t().strategyNamePlaceholder)}" required /></label>
        <label>${t().strategyKeywords}<input name="keywords" maxlength="400" placeholder="${escapeAttribute(t().strategyKeywordPlaceholder)}" required /></label>
        <button type="submit" ${state.customStrategies.length >= 20 ? "disabled" : ""}>${t().addAndSearch}</button>
      </form>
      <p>${t().strategyHint}</p>
      ${state.customStrategies.length
        ? `<div class="custom-strategies">${state.customStrategies
            .map(
              (strategy) => `<div><span><strong>${escapeHtml(strategy.name)}</strong><small>${escapeHtml(groupLabel(STRATEGY_GROUPS.find((g) => g.id === (strategy.group || "other")) || STRATEGY_GROUPS[4]))} · ${escapeHtml(strategy.keywords.join(" / "))}</small></span><button type="button" data-action="remove-strategy" data-strategy="${escapeAttribute(strategy.id)}">${t().remove}</button></div>`
            )
            .join("")}</div>`
        : ""}`
    : "";
  const strategyError = $("#strategyError");
  strategyError.hidden = !state.strategyError;
  strategyError.textContent = state.strategyError;

  $("#strategyCategories").innerHTML = STRATEGY_GROUPS.map((group) => {
    const ids = [...group.ids, ...state.customStrategies.filter((s) => (s.group || "other") === group.id).map((s) => s.id)];
    return `
      <div class="strategy-category">
        <div class="category-heading">
          <h3>${escapeHtml(groupLabel(group))}</h3>
          <button type="button" class="add-substrategy" data-action="add-substrategy" data-group="${group.id}" aria-label="${escapeAttribute(groupLabel(group))} ${t().addSubstrategy}">${t().addSubstrategy}</button>
        </div>
        <div class="strategy-list">${ids.map(strategyById).filter(Boolean).map(strategyButton).join("")}</div>
      </div>`;
  }).join("");

  renderCoverage();
}
function renderCoverage() {
  const firms = firmList().filter((firm) => !firm.custom);
  const coverage = Array.isArray(data?.coverage) ? data.coverage : [];
  const byFirm = Object.fromEntries(coverage.map((entry) => [entry.firm, entry]));
  const counts = countsByFirm();
  const selectedFirms = firms.filter((firm) => state.firms.includes(firm.id));
  const okCount = selectedFirms.filter((firm) => (byFirm[firm.id] ? byFirm[firm.id].status === "ok" : counts[firm.id] > 0)).length;
  $("#coverageOk").textContent = state.loading ? "—" : String(okCount);
  $("#coverageTotal").textContent = t().coverageResponded(selectedFirms.length);
  const failed = selectedFirms.filter((firm) => byFirm[firm.id]?.status === "error").length;
  const warning = $("#coverageWarning");
  warning.hidden = !failed;
  warning.textContent = failed ? t().coverageFailed(failed) : "";
  $("#coverageList").innerHTML = selectedFirms
    .map((firm) => {
      const entry = byFirm[firm.id];
      let status;
      if (state.loading) status = t().searching;
      else if (entry) status = entry.status === "error" ? t().coverageFailedWord : `${t().coverageItems(entry.count ?? 0)} · ${t().coverageSelected(counts[firm.id] || 0)}`;
      else status = t().coverageSelected(counts[firm.id] || 0);
      return `<div><span>${escapeHtml(firm.name)}</span><span class="${entry?.status === "error" ? "warning" : ""}">${escapeHtml(status)}</span></div>`;
    })
    .join("");
  const stamp = data?.checkedAt || data?.updatedAt;
  $("#coverageTimestamp").innerHTML = stamp ? `${t().runAt} ${escapeHtml(formatDateTime(stamp))}<br>${t().coverageFoot}` : "";

  $("#queryList").hidden = !state.showQueries;
  if (state.showQueries) {
    const entries = coverage.length ? coverage.filter((entry) => entry.firm !== "Portfolio") : firms.map((firm) => ({ firm: firm.id, query: `"${firm.name}" credit` }));
    $("#queryList").innerHTML =
      entries
        .map((entry) => {
          const params = new URLSearchParams({ q: entry.query, hl: "en-US", gl: "US", ceid: "US:en" });
          return `<div><a href="https://news.google.com/search?${params.toString()}" target="_blank" rel="noopener noreferrer">${escapeHtml(firmById(entry.firm)?.name || entry.firm)} · Google News</a><code>${escapeHtml(entry.query)}</code></div>`;
        })
        .join("") + `<a href="https://news.google.com" target="_blank" rel="noopener noreferrer">${t().openGoogleNews}</a>`;
  }
}

/* ---------- Summary analysis (ported rules, bilingual) ---------- */
function buildSummary(entries) {
  const names = {
    firms: Object.fromEntries(firmList().map((firm) => [firm.id, firm.name])),
    strategies: Object.fromEntries(strategyList().map((strategy) => [strategy.id, strategyLabel(strategy)])),
  };
  const merged = new Map();
  entries.forEach((entry) => {
    const key = (entry.item.title || "").toLowerCase().replace(/[^\p{L}\p{N}]/gu, "");
    const record = {
      title: entry.item.title || "",
      titleZh: entry.item.titleZh || "",
      url: entry.item.url,
      source: entry.item.source,
      date: entry.item.date,
      firms: entry.firms,
      strategies: entry.strategies,
      events: entry.events,
      score: entry.score,
    };
    const existing = merged.get(key);
    if (existing) {
      merged.set(key, {
        ...(existing.score < record.score ? record : existing),
        firms: [...new Set([...existing.firms, ...record.firms])],
        strategies: [...new Set([...existing.strategies, ...record.strategies])],
        events: [...new Set([...existing.events, ...record.events])],
      });
    } else {
      merged.set(key, record);
    }
  });
  const stories = [...merged.values()].sort((a, b) => b.score - a.score || (b.date || "").localeCompare(a.date || ""));
  const dates = stories.map((s) => s.date).filter(Boolean).sort();
  return {
    analysis: analyzeStories(stories, names),
    reports: entries.length,
    stories: stories.length,
    priority: stories.filter((s) => s.score >= 65).length,
    oldest: dates[0] || "",
    newest: dates[dates.length - 1] || "",
  };
}
function analyzeStories(stories, names) {
  const zh = state.language === "zh";
  const sections = [];
  const pick = (pattern) => stories.filter((s) => pattern.test(s.title));
  const firmsOf = (list) => [...new Set(list.flatMap((s) => s.firms))].map((id) => names.firms[id] || id).slice(0, 4).join(zh ? "、" : ", ");
  const add = (title, observation, interpretation, evidence) => {
    if (evidence.length) sections.push({ title, observation, interpretation, evidence: evidence.slice(0, 3) });
  };

  const closes = pick(/final clos|first clos|fund.{0,35}(?:clos|rais)|rais(?:ed|es).{0,40}(?:fund|billion|million)|fundrais/i);
  const launches = pick(/target(?:s|ing)?.{0,40}(?:fund|billion|million)|seek(?:s|ing)?.{0,40}(?:rais|fund)|launch.{0,40}fund|new fund/i).filter((s) => !closes.includes(s));
  add(
    zh ? "募资与资本供给" : "Fundraising and capital supply",
    zh
      ? `${firmsOf([...closes, ...launches])}的相关标题涉及${closes.length ? `募资或关账进展（${closes.length} 个标题）` : ""}${closes.length && launches.length ? "，以及" : ""}${launches.length ? `新基金或募资计划（${launches.length} 个标题）` : ""}。`
      : `Headlines involving ${firmsOf([...closes, ...launches])} cover ${closes.length ? `fundraising or closing progress (${closes.length} headlines)` : ""}${closes.length && launches.length ? " and " : ""}${launches.length ? `new funds or fundraising plans (${launches.length} headlines)` : ""}.`,
    closes.length && launches.length
      ? zh
        ? "这些报道覆盖从产品推出到资本募集的不同阶段。判断可部署资金时，需要分别核对目标规模、实际承诺金额以及首关 / 最终关账；标题中的金额不宜直接相加。"
        : "These reports span different stages from product launch to capital raised. To judge deployable capital, check target size, actual commitments and first / final close separately; headline amounts should not simply be added together."
      : closes.length
        ? zh
          ? "标题提供了资本募集进展的信号，后续重点是确认关账阶段、投资者承诺是否到账及资金对应的具体策略。多篇报道可能指向同一次募集。"
          : "Headlines signal fundraising progress; next confirm the closing stage, whether investor commitments have funded, and which strategy the capital backs. Several reports may describe the same raise."
        : zh
          ? "当前信号主要来自基金推出或募集计划。后续可追踪首关和最终关账，确认计划何时转化为实际可部署资本。"
          : "Current signals come mainly from fund launches or fundraising plans. Track first and final closes to confirm when plans become deployable capital.",
    [...closes, ...launches]
  );

  const deals = pick(/financ|\bloans?\b|credit facility|acqui|\bbuy\b|securiti[sz]ation|debt issu|invest(?:s|ed|ment)?.{0,35}(?:billion|million)|commit.{0,35}(?:billion|million)/i);
  const done = deals.filter((s) => /complet|clos(?:ed|es)|acquir(?:ed|es)|secured|provided|sign(?:ed|s)/i.test(s.title));
  const planned = deals.filter((s) => /\bto (?:buy|acquire|invest|financ)|plan|seek|consider|talks|eyes|reported|said to/i.test(s.title));
  add(
    zh ? "融资与交易落地" : "Financing and deal execution",
    zh
      ? `${firmsOf(deals)}的报道呈现融资、授信、证券化或收购活动。标题中有 ${done.length} 个带有完成 / 签署措辞，${planned.length} 个带有计划或报道转述措辞；两类可能重叠。`
      : `Reports on ${firmsOf(deals)} show financing, credit facility, securitization or acquisition activity. ${done.length} headlines use completed / signed wording and ${planned.length} use planned or reported wording; the two may overlap.`,
    zh
      ? "这些标题显示机构在资本部署和资产配置上有动作。分析重点是交易是否已完成、资金用途、交易对手及融资结构；收购估值、贷款规模和募资规模属于不同口径，不能合并为资金流入总额。"
      : "These headlines show institutions acting on deployment and asset allocation. Focus on whether the deal has closed, use of proceeds, counterparties and structure; acquisition valuations, loan sizes and fund sizes are different measures and cannot be summed into a single inflow figure.",
    deals
  );

  const liquidity = pick(/redemption|withdrawal|outflow|liquidity|赎回/i);
  const easing = liquidity.filter((s) => /ease|slow|fewer|fall|declin|lower|reduc/i.test(s.title));
  const pressure = liquidity.filter((s) => /\bcaps?\b|limit|surge|above|beyond|jump|rise|ris(?:es|ing)|freeze|halt|suspend/i.test(s.title));
  add(
    zh ? "流动性与信用风险" : "Liquidity and credit risk",
    zh
      ? `${firmsOf(liquidity)}的标题涉及赎回、退出或流动性。${easing.length ? `其中 ${easing.length} 个标题出现缓解 / 减少措辞。` : ""}${pressure.length ? `另有 ${pressure.length} 个标题出现限制、上升或突破门槛措辞。` : ""}`
      : `Headlines on ${firmsOf(liquidity)} involve redemptions, withdrawals or liquidity. ${easing.length ? `${easing.length} use easing / declining wording. ` : ""}${pressure.length ? `${pressure.length} use capping, rising or threshold-breach wording.` : ""}`,
    easing.length && pressure.length
      ? zh
        ? "当前报道同时包含缓解信号与压力信号，可能涉及不同基金、期间或指标。需要按产品核对赎回请求、实际支付、赎回上限和季度变化，才能判断压力是否持续；不能由这些标题直接推断整个行业的方向。"
        : "Coverage carries both easing and pressure signals, possibly for different funds, periods or metrics. Check redemption requests, actual payouts, caps and quarterly change per product before judging whether pressure persists; do not infer the industry direction from these headlines alone."
      : easing.length
        ? zh
          ? "部分标题指向压力缓解，但仍需比较此前基数、实际赎回支付和限制条件，确认改善是否持续。"
          : "Some headlines point to easing pressure, but compare the prior base, actual redemption payouts and gating terms to confirm the improvement is lasting."
        : zh
          ? "需要核对相关基金的实际赎回数据、上限安排与资产流动性。标题提及限制或赎回需求本身不足以确认违约或偿付问题。"
          : "Verify the funds' actual redemption data, cap arrangements and asset liquidity. A headline mention of caps or redemption demand does not by itself confirm default or payment problems.",
    liquidity
  );

  const quality = pick(/default|downgrade|bankrupt|fraud|credit loss|impairment/i);
  add(
    zh ? "信用质量信号" : "Credit quality signals",
    zh ? `${firmsOf(quality)}的相关标题提及违约、降级、破产或损失类词汇。` : `Headlines on ${firmsOf(quality)} mention default, downgrade, bankruptcy or loss terms.`,
    zh
      ? "核对风险对应的是管理机构、具体基金、借款人还是底层资产，并确认是已发生事项、指控还是情景讨论。风险主体不同，影响传导也不同。"
      : "Check whether the risk relates to the manager, a specific fund, a borrower or underlying assets, and whether it is an occurred event, an allegation or a scenario discussion. Different risk subjects transmit differently.",
    quality
  );

  const legal = pick(/lawsuit|litigation|\bsued\b|settlement|class.action|court/i);
  const solicitations = legal.filter((s) => /law firm|investor alert|securities class action notice|reminds investors|deadline alert|shareholder alert/i.test(s.title));
  add(
    zh ? "法律事件与程序阶段" : "Legal events and procedural stage",
    zh
      ? `${firmsOf(legal)}的检索结果出现 ${legal.length} 个法律事件相关标题${solicitations.length ? `，其中 ${solicitations.length} 个含律师征集或投资者提醒措辞` : ""}。`
      : `Results for ${firmsOf(legal)} include ${legal.length} legal-event headlines${solicitations.length ? `, ${solicitations.length} of them law-firm solicitations or investor alerts` : ""}.`,
    zh
      ? "先确认机构在案件中的角色，再区分立案、诉讼进展、和解与判决。律师征集公告可能重复报道同一争议，不能单凭数量判断案件增加；标题也不足以确认责任或损失规模。"
      : "Confirm the institution's role in the case first, then distinguish filing, progress, settlement and judgment. Law-firm notices may repeat the same dispute, so counts do not indicate more cases; headlines also cannot confirm liability or loss size.",
    legal
  );

  const byStrategy = new Map();
  stories.forEach((s) => s.strategies.forEach((id) => byStrategy.set(id, [...(byStrategy.get(id) || []), s])));
  const ranked = [...byStrategy].sort((a, b) => b[1].length - a[1].length);
  if (ranked.length) {
    const top = ranked.slice(0, 3);
    const ai = byStrategy.get("ai") || [];
    add(
      zh ? "策略关注点与交叉信号" : "Strategy focus and cross-signals",
      zh
        ? `在这些标题中，${top.map(([id, list]) => `${names.strategies[id] || id}（${list.length} 个标题）`).join("、")}最常被提及。${ai.length ? "AI 相关报道涉及人工智能或数据中心 / 算力关键词。" : ""}`
        : `Among these headlines, ${top.map(([id, list]) => `${names.strategies[id] || id} (${list.length})`).join(", ")} are mentioned most. ${ai.length ? "AI-related coverage involves artificial intelligence or data center / compute keywords." : ""}`,
      ai.length
        ? zh
          ? "可把 AI 主题进一步拆分为基础设施投资、资产融资及信用敞口，核对合同、交易对手和资金用途；“AI 相关”标签只说明主题相关，尚不足以确认具体融资工具或风险收益特征。"
          : "Split the AI theme into infrastructure investment, asset financing and credit exposure, checking contracts, counterparties and use of proceeds; the AI tag only marks topical relevance and does not identify the financing instrument or its risk-return profile."
        : zh
          ? "这些是当前筛选结果中的主题集中度，受机构选择、关键词和公开新闻覆盖影响。可继续按机构及策略交叉筛选，核对热点对应的是新资金募集、资产部署还是风险管理动作。"
          : "This is the topic concentration of the current filter, shaped by institution selection, keywords and public coverage. Cross-filter by institution and strategy to check whether each theme reflects new fundraising, deployment or risk management.",
      top.flatMap(([, list]) => list)
    );
  }
  if (!sections.length) {
    add(
      zh ? "机构动态" : "Institution updates",
      zh
        ? `当前优先标题主要涉及${firmsOf(stories)}的机构动态，尚未识别到足够明确的募资、交易或风险阶段信号。`
        : `Priority headlines mainly cover institution updates for ${firmsOf(stories)}; no clear fundraising, deal or risk-stage signals were identified.`,
      zh
        ? "这些报道适合作为后续研究线索；先核对具体事项及影响对象，再判断是否改变机构的策略方向。"
        : "Treat these as research leads; verify the specific matter and who is affected before judging whether the institution's strategy direction has changed.",
      stories
    );
  }
  const leads = sections.map((s) => s.title).slice(0, 3);
  const synthesis = stories.length
    ? zh
      ? `当前筛选结果的主要研究线索是${leads.join("、")}。${closes.length && deals.length ? "募资与部署动作同时出现，值得逐家核对两端是否对应同一产品或策略。" : ""}${easing.length && pressure.length ? "流动性报道包含不同方向的信号，需要分产品、分期间判断。" : ""}以下分析基于标题所能支持的事实线索，并将待核实事项与观察结果分开。`
      : `The main research leads in the current filter are ${leads.join(", ")}. ${closes.length && deals.length ? "Fundraising and deployment appear together; check firm by firm whether both ends refer to the same product or strategy. " : ""}${easing.length && pressure.length ? "Liquidity coverage carries signals in both directions and needs per-product, per-period judgement. " : ""}The analysis below rests on what headlines can support and separates open points from observations.`
    : zh
      ? "当前没有可供分析的报道。"
      : "There are no articles to analyse.";
  return { synthesis, sections };
}

/* ---------- Events ---------- */
function bindStaticEvents() {
  document.addEventListener("click", onClick);
  document.addEventListener("change", onChange);
  document.addEventListener("input", onInput);
  document.addEventListener("submit", onSubmit);
  $("#languageToggle").addEventListener("click", () => {
    state.language = state.language === "zh" ? "en" : "zh";
    writeStorage(STORAGE.language, state.language);
    state.summary = state.summary ? buildSummary(computeView().shown) : null;
    renderAll();
  });
  document.querySelectorAll("[data-report-close]").forEach((button) => button.addEventListener("click", () => $("#reportDialog").close()));
  document.querySelectorAll("[data-github-close]").forEach((button) => button.addEventListener("click", () => $("#githubDialog").close()));
  $("#githubForget").addEventListener("click", () => {
    state.githubToken = "";
    try {
      localStorage.removeItem(STORAGE.githubToken);
    } catch {
      /* storage optional */
    }
    $("#githubTokenInput").value = "";
    syncGithubDialog();
  });
}
function onClick(event) {
  const target = event.target.closest("[data-action]");
  if (!target) return;
  const action = target.dataset.action;
  switch (action) {
    case "reload":
      handleRefreshClick();
      break;
    case "github-settings":
      openGithubDialog();
      break;
    case "select-event":
      state.event = target.dataset.event;
      state.visible = PAGE_SIZE;
      invalidateSummary();
      renderAll();
      break;
    case "select-strategy": {
      const id = target.dataset.strategy || "";
      state.strategy = state.strategy === id ? "" : id;
      state.visible = PAGE_SIZE;
      invalidateSummary();
      renderAll();
      break;
    }
    case "only-firm":
      state.firms = [target.dataset.firm];
      state.visible = PAGE_SIZE;
      invalidateSummary();
      renderAll();
      break;
    case "reset-filters":
      resetFilters();
      break;
    case "toggle-firm-manager":
      state.showFirmManager = !state.showFirmManager;
      renderSidebar();
      applyUiText();
      break;
    case "remove-firm":
      state.customFirms = state.customFirms.filter((firm) => firm.id !== target.dataset.firm);
      state.firms = state.firms.filter((id) => id !== target.dataset.firm);
      persistFirms();
      invalidateSummary();
      renderAll();
      break;
    case "toggle-strategy-manager":
      state.showStrategyManager = !state.showStrategyManager;
      renderResults();
      renderContext();
      break;
    case "add-substrategy":
      state.strategyManagerGroup = target.dataset.group || "other";
      state.showStrategyManager = true;
      state.strategyError = "";
      renderResults();
      renderContext();
      break;
    case "remove-strategy":
      state.customStrategies = state.customStrategies.filter((strategy) => strategy.id !== target.dataset.strategy);
      if (state.strategy === target.dataset.strategy) state.strategy = "";
      persistStrategies();
      invalidateSummary();
      renderAll();
      break;
    case "toggle-summary":
      state.summary = buildSummary(computeView().shown);
      renderTop();
      renderResults();
      break;
    case "close-summary":
      state.summary = null;
      renderTop();
      renderResults();
      break;
    case "load-more":
      state.visible += PAGE_SIZE;
      renderResults();
      break;
    case "reset-weights":
      state.weights = { ...DEFAULT_WEIGHTS };
      writeStorage(STORAGE.weights, JSON.stringify(state.weights));
      invalidateSummary();
      renderAll();
      break;
    case "toggle-queries":
      state.showQueries = !state.showQueries;
      renderCoverage();
      break;
    case "exact-prev":
    case "exact-next":
    case "exact-today": {
      const current = parseDate(state.exactDate);
      state.exactDate = action === "exact-today" ? todayKey() : toDateKey(addDays(current, action === "exact-prev" ? -1 : 1));
      state.visible = PAGE_SIZE;
      invalidateSummary();
      renderAll();
      break;
    }
    case "report":
      openReportDialog(target.dataset.id);
      break;
    default:
      break;
  }
}
function onChange(event) {
  const target = event.target;
  if (target.id === "allFirms") {
    const all = firmList().map((firm) => firm.id);
    state.firms = state.firms.length === all.length ? [] : all;
  } else if (target.dataset.groupSelect) {
    const ids = firmList().filter((firm) => firm.group === target.dataset.groupSelect).map((firm) => firm.id);
    state.firms = ids.every((id) => state.firms.includes(id)) ? state.firms.filter((id) => !ids.includes(id)) : [...new Set([...state.firms, ...ids])];
  } else if (target.dataset.firm !== undefined && target.type === "checkbox") {
    const id = target.dataset.firm;
    state.firms = state.firms.includes(id) ? state.firms.filter((f) => f !== id) : [...state.firms, id];
  } else if (target.id === "dateSelect") {
    state.dateMode = target.value;
    state.rangeErrorShown = false;
  } else if (target.id === "exactDateInput") {
    if (/^\d{4}-\d{2}-\d{2}$/.test(target.value)) state.exactDate = target.value;
  } else if (target.id === "minScoreSelect") {
    state.minScore = Number(target.value) || 0;
  } else if (target.id === "sortSelect") {
    state.sort = target.value;
  } else if (target.name === "group" && target.closest("#strategyForm")) {
    state.strategyManagerGroup = target.value;
    return;
  } else {
    return;
  }
  state.visible = PAGE_SIZE;
  invalidateSummary();
  renderAll();
}
function onInput(event) {
  const target = event.target;
  if (target.dataset.weight) {
    state.weights[target.dataset.weight] = Number(target.value);
    writeStorage(STORAGE.weights, JSON.stringify(state.weights));
    const label = document.querySelector(`[data-weight-value="${target.dataset.weight}"]`);
    if (label) label.textContent = String(state.weights[target.dataset.weight]);
    $("#zeroWeightWarning").hidden = !WEIGHT_KEYS.every((key) => state.weights[key] === 0);
    invalidateSummary();
    renderResults();
    renderCounts();
  } else if (target.id === "searchInput") {
    state.queryInput = target.value;
  }
}
function onSubmit(event) {
  const form = event.target;
  if (form.id === "searchForm") {
    event.preventDefault();
    state.query = state.queryInput.trim();
    state.visible = PAGE_SIZE;
    invalidateSummary();
    renderAll();
  } else if (form.id === "dateRangeForm") {
    event.preventDefault();
    const start = $("#rangeStart").value;
    const end = $("#rangeEnd").value;
    const valid = (value) => !value || /^\d{4}-\d{2}-\d{2}$/.test(value);
    const error = $("#rangeError");
    if ((!start && !end) || !valid(start) || !valid(end) || (start && end && start > end)) {
      error.hidden = false;
      error.textContent = t().rangeError;
      return;
    }
    error.hidden = true;
    state.start = start;
    state.end = end;
    state.dateMode = "custom";
    state.visible = PAGE_SIZE;
    invalidateSummary();
    renderAll();
  } else if (form.id === "firmForm") {
    event.preventDefault();
    addCustomFirm(form);
  } else if (form.id === "strategyForm") {
    event.preventDefault();
    addCustomStrategy(form);
  } else if (form.id === "reportForm") {
    submitReport(event);
  } else if (form.id === "githubForm") {
    event.preventDefault();
    const typed = $("#githubTokenInput").value.trim();
    if (typed) {
      state.githubToken = typed;
      writeStorage(STORAGE.githubToken, typed);
      $("#githubTokenInput").value = "";
    }
    if (!state.githubToken) {
      showGithubStatus(t().githubTokenMissing);
      return;
    }
    $("#githubDialog").close();
    startRemoteRefresh();
  }
}
function invalidateSummary() {
  state.summary = null;
}
function resetFilters() {
  state.firms = firmList().map((firm) => firm.id);
  state.strategy = "";
  state.event = "all";
  state.dateMode = "30";
  state.start = "";
  state.end = "";
  state.exactDate = todayKey();
  state.minScore = 0;
  state.query = "";
  state.queryInput = "";
  state.visible = PAGE_SIZE;
  invalidateSummary();
  renderAll();
}

/* ---------- Custom firms and strategies ---------- */
function normalizeName(value) {
  return String(value).normalize("NFKC").toLowerCase().replace(/[^\p{L}\p{N}]/gu, "");
}
function sanitizeCustomFirms(list) {
  if (!Array.isArray(list) || list.length > 20) throw new Error("too many");
  const ids = new Set();
  const builtin = new Set(DEFAULT_GPS.flatMap((gp) => [gp, ...(DEFAULT_ALIASES[gp] || [])]).map(normalizeName));
  return list
    .map((firm) => {
      if (!firm || typeof firm.id !== "string" || !/^custom-[a-z0-9-]{1,50}$/.test(firm.id) || ids.has(firm.id)) throw new Error("bad id");
      ids.add(firm.id);
      const clean = (value) => {
        if (typeof value !== "string" || !value.trim() || value.trim().length > 80 || /["<>\r\n]/.test(value)) throw new Error("bad name");
        return value.trim();
      };
      if (!Array.isArray(firm.aliases) || firm.aliases.length > 5) throw new Error("bad aliases");
      return { id: firm.id, name: clean(firm.name), group: firm.group === "invested" ? "invested" : "watch", aliases: [...new Set(firm.aliases.map(clean))] };
    })
    .filter((firm) => !builtin.has(normalizeName(firm.name)));
}
function sanitizeCustomStrategies(list) {
  if (!Array.isArray(list) || list.length > 20) throw new Error("too many");
  const ids = new Set();
  const names = new Set();
  return list.map((strategy) => {
    if (!strategy || typeof strategy.id !== "string" || !/^strategy-[a-z0-9-]{1,50}$/.test(strategy.id) || ids.has(strategy.id)) throw new Error("bad id");
    ids.add(strategy.id);
    const clean = (value) => {
      if (typeof value !== "string" || !value.trim() || value.trim().length > 80 || /["<>\r\n]/.test(value)) throw new Error("bad value");
      return value.trim();
    };
    const name = clean(strategy.name);
    if (names.has(name.toLowerCase())) throw new Error("dup");
    names.add(name.toLowerCase());
    if (!Array.isArray(strategy.keywords) || !strategy.keywords.length || strategy.keywords.length > 5) throw new Error("bad keywords");
    if (strategy.group !== undefined && !STRATEGY_GROUPS.some((group) => group.id === strategy.group)) throw new Error("bad group");
    return { id: strategy.id, name, group: strategy.group || "other", keywords: [...new Set(strategy.keywords.map(clean))] };
  });
}
function addCustomFirm(form) {
  try {
    const name = form.elements.name.value.trim();
    const aliases = form.elements.aliases.value.split(/[;,，；]/).map((value) => value.trim()).filter(Boolean);
    const group = form.elements.group.value;
    if (firmList().some((firm) => normalizeName(firm.name) === normalizeName(name) || firm.aliases.some((alias) => normalizeName(alias) === normalizeName(name)))) {
      throw new Error(t().firmExists);
    }
    const next = sanitizeCustomFirms([...state.customFirms, { id: `custom-${uuid()}`, name, group, aliases }]);
    state.customFirms = next;
    state.firms = [...state.firms, next[next.length - 1].id];
    state.firmError = "";
    persistFirms();
    invalidateSummary();
    renderAll();
  } catch (error) {
    state.firmError = error instanceof Error && Object.values(t()).includes(error.message) ? error.message : t().firmInvalid;
    renderSidebar();
  }
}
function persistFirms() {
  if (!writeStorage(STORAGE.firms, JSON.stringify(state.customFirms))) state.firmError = t().firmStorageFail;
}
function addCustomStrategy(form) {
  try {
    const name = form.elements.name.value.trim();
    const keywords = form.elements.keywords.value.split(/[;,，；]/).map((value) => value.trim()).filter(Boolean);
    const group = form.elements.group.value;
    if (strategyList().some((strategy) => strategy.name.toLowerCase() === name.toLowerCase())) throw new Error(t().strategyExists);
    const next = sanitizeCustomStrategies([...state.customStrategies, { id: `strategy-${uuid()}`, name, group, keywords }]);
    state.customStrategies = next;
    state.strategy = next[next.length - 1].id;
    state.strategyError = "";
    persistStrategies();
    invalidateSummary();
    renderAll();
  } catch (error) {
    state.strategyError = error instanceof Error && Object.values(t()).includes(error.message) ? error.message : t().strategyInvalid;
    renderContext();
  }
}
function persistStrategies() {
  if (!writeStorage(STORAGE.strategies, JSON.stringify(state.customStrategies))) state.strategyError = t().strategyStorageFail;
}
function uuid() {
  if (typeof crypto !== "undefined" && crypto.randomUUID) return crypto.randomUUID();
  return `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`;
}

/* ---------- Live refresh through GitHub Actions ---------- */
function handleRefreshClick() {
  if (state.loading || (state.refresh && !["done", "error"].includes(state.refresh.phase))) return;
  if (!state.githubToken) {
    openGithubDialog();
    return;
  }
  startRemoteRefresh();
}
function openGithubDialog() {
  syncGithubDialog();
  showGithubStatus("");
  const dialog = $("#githubDialog");
  if (typeof dialog.showModal === "function") dialog.showModal();
  else dialog.setAttribute("open", "");
}
function syncGithubDialog() {
  const hasToken = Boolean(state.githubToken);
  $("#githubForget").hidden = !hasToken;
  $("#githubTokenInput").placeholder = hasToken ? t().githubTokenSaved : "github_pat_…";
}
function showGithubStatus(message) {
  const node = $("#githubStatus");
  node.hidden = !message;
  node.textContent = message;
}
function githubHeaders() {
  return {
    Accept: "application/vnd.github+json",
    Authorization: `Bearer ${state.githubToken}`,
    "X-GitHub-Api-Version": "2022-11-28",
  };
}
function setRefresh(patch) {
  state.refresh = { ...(state.refresh || {}), ...patch };
  renderRefreshButton();
  renderResults();
}
async function startRemoteRefresh() {
  const startedAt = Date.now();
  const baselineUpdatedAt = data?.updatedAt || "";
  setRefresh({ phase: "dispatching", startedAt, message: "", runUrl: "" });
  const ticker = setInterval(renderRefreshButton, 1000);
  try {
    const dispatch = await fetch(`${GITHUB_API}/dispatches`, {
      method: "POST",
      headers: { ...githubHeaders(), "Content-Type": "application/json" },
      body: JSON.stringify({ ref: GITHUB_BRANCH, inputs: { mode: "today" } }),
    });
    if (dispatch.status === 401 || dispatch.status === 403) throw new Error(t().refreshAuthError);
    if (dispatch.status === 404) throw new Error(t().refreshNotFound);
    if (!dispatch.ok) throw new Error(t().refreshNetworkError(`HTTP ${dispatch.status}`));

    setRefresh({ phase: "queued" });
    const run = await waitForRun(startedAt);
    if (run === "timeout") {
      setRefresh({ phase: "done", message: t().refreshTimeoutRun });
      return;
    }
    if (run.conclusion !== "success") {
      setRefresh({ phase: "error", message: t().refreshFailedRun, runUrl: run.html_url || "" });
      return;
    }
    setRefresh({ phase: "deploying" });
    const deployed = await waitForDeploy(baselineUpdatedAt);
    if (!deployed) {
      setRefresh({ phase: "done", message: t().refreshTimeoutDeploy });
      return;
    }
    data = deployed;
    allItems = flattenItems(data);
    state.summary = null;
    setRefresh({ phase: "done", message: t().refreshDone(formatDateTime(data.updatedAt || new Date().toISOString())) });
    renderAll();
  } catch (error) {
    const known = Object.values(t()).includes(error.message);
    setRefresh({ phase: "error", message: known ? error.message : t().refreshNetworkError(error.message || String(error)) });
  } finally {
    clearInterval(ticker);
    renderRefreshButton();
  }
}
async function waitForRun(startedAt) {
  const deadline = startedAt + RUN_TIMEOUT_MS;
  const since = new Date(startedAt - 60000).toISOString();
  while (Date.now() < deadline) {
    await sleep(RUN_POLL_MS);
    let runs;
    try {
      const response = await fetch(`${GITHUB_API}/runs?event=workflow_dispatch&per_page=5&created=${encodeURIComponent(`>=${since}`)}`, { headers: githubHeaders() });
      if (!response.ok) continue;
      runs = (await response.json()).workflow_runs || [];
    } catch {
      continue;
    }
    const run = runs.find((candidate) => Date.parse(candidate.created_at) >= startedAt - 60000);
    if (!run) continue;
    if (run.status === "completed") return run;
    setRefresh({ phase: run.status === "queued" ? "queued" : "running", runUrl: run.html_url || "" });
  }
  return "timeout";
}
async function waitForDeploy(baselineUpdatedAt) {
  const deadline = Date.now() + DEPLOY_TIMEOUT_MS;
  while (Date.now() < deadline) {
    try {
      const response = await fetch(`${DATA_URL}?t=${Date.now()}`, { cache: "no-store" });
      if (response.ok) {
        const payload = await response.json();
        if ((payload.updatedAt || "") !== baselineUpdatedAt) return payload;
      }
    } catch {
      /* retry */
    }
    await sleep(DEPLOY_POLL_MS);
  }
  return null;
}
function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

/* ---------- Dialogs ---------- */
function openReportDialog(id) {
  const item = allItems.find((entry) => (entry.id || entry.url) === id);
  if (!item) return;
  state.reportingItem = item;
  $("#reportArticleTitle").textContent = item.title || "";
  $("#reportDetails").value = "";
  populateSelect($("#correctGps"), scopeGps().map((gp) => [gp, gp]), item.gps || []);
  populateSelect($("#correctSectors"), BUILTIN_STRATEGIES.map((strategy) => [strategy.id, strategyLabel(strategy)]), itemStrategies(item));
  $("#reportForm").elements.reasonType.value = "wrong_gp";
  const dialog = $("#reportDialog");
  if (typeof dialog.showModal === "function") dialog.showModal();
  else dialog.setAttribute("open", "");
}
function populateSelect(select, options, selectedValues) {
  select.innerHTML = "";
  options.forEach(([value, label]) => {
    const node = document.createElement("option");
    node.value = value;
    node.textContent = label;
    node.selected = selectedValues.includes(value);
    select.append(node);
  });
}
function submitReport(event) {
  event.preventDefault();
  const item = state.reportingItem;
  if (!item) return;
  const form = $("#reportForm");
  const reasonType = form.elements.reasonType.value;
  const report = {
    reportedAt: new Date().toISOString(),
    reasonType,
    reason: $("#reportDetails").value.trim(),
    itemId: item.id || "",
    title: item.title || "",
    url: item.url || "",
    source: item.source || "",
    publishedAt: item.publishedAt || "",
    lede: item.lede || "",
    articleText: item.articleExcerpt || `${item.title || ""}. ${item.lede || ""}`.trim(),
    original: { gps: item.gps || [], sectors: itemStrategies(item) },
    corrected: {
      gps: Array.from($("#correctGps").selectedOptions).map((option) => option.value),
      sectors: Array.from($("#correctSectors").selectedOptions).map((option) => option.value),
      exclude: reasonType === "not_credit",
    },
  };
  try {
    const existing = JSON.parse(localStorage.getItem(STORAGE.reports) || "[]");
    existing.push(report);
    localStorage.setItem(STORAGE.reports, JSON.stringify(existing));
  } catch {
    /* storage optional */
  }
  const title = `News classification report: ${report.title}`.slice(0, 160);
  const body = ["Please review this report and, if valid, append it to `data/golden_cases.json`.", "", "```json", JSON.stringify(report, null, 2), "```"].join("\n");
  window.open(`${REPORT_ISSUE_URL}?${new URLSearchParams({ title, body }).toString()}`, "_blank", "noopener,noreferrer");
  $("#reportDialog").close();
}

/* ---------- Helpers ---------- */
function displayTitle(title, source) {
  const text = String(title || "").trim();
  const match = text.match(/^(.*\S)\s+[-–—|]\s+([^-–—|]{2,60})$/);
  if (!match) return text;
  const suffix = match[2].trim();
  const sourceName = String(source || "").trim();
  if (sourceName && (normalizeName(suffix) === normalizeName(sourceName) || normalizeName(sourceName).includes(normalizeName(suffix)) || normalizeName(suffix).includes(normalizeName(sourceName)))) {
    return match[1].trim();
  }
  return text;
}
const MISSING_ZH_SUMMARY = "此条目的中文摘要尚未人工整理；请先参考英文摘要与原文链接。";
function isRedundantSummary(summary, title, source) {
  if (String(summary || "").trim() === MISSING_ZH_SUMMARY) return true;
  const cleaned = normalizeName(displayTitle(summary, source));
  const titleKey = normalizeName(title);
  if (!cleaned) return true;
  return cleaned === titleKey || cleaned.startsWith(titleKey) || titleKey.startsWith(cleaned);
}
function localized(item, field) {
  if (state.language === "zh") return item[`${field}Zh`] || item[field] || "";
  return item[field] || "";
}
function formatNumber(value) {
  const number = Number(value);
  return Number.isFinite(number) ? String(Math.round(number * 100) / 100) : "—";
}
function formatDate(value) {
  if (!value) return "—";
  const date = new Date(`${String(value).slice(0, 10)}T12:00:00Z`);
  if (Number.isNaN(date.getTime())) return String(value);
  return new Intl.DateTimeFormat(state.language === "zh" ? "zh-CN" : "en-US", { year: "numeric", month: "2-digit", day: "2-digit", timeZone: "UTC" }).format(date);
}
function formatDateTime(value) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value);
  return new Intl.DateTimeFormat(state.language === "zh" ? "zh-CN" : "en-US", { year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" }).format(date);
}
function todayKey() {
  return toDateKey(new Date());
}
function parseDate(value) {
  const [year, month, day] = String(value).split("-").map(Number);
  return new Date(year, (month || 1) - 1, day || 1);
}
function toDateKey(date) {
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`;
}
function addDays(date, days) {
  const next = new Date(date);
  next.setDate(next.getDate() + days);
  return next;
}
function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}
function escapeAttribute(value) {
  return escapeHtml(value || "");
}
