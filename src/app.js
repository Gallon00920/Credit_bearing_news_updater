const DATA_URL = "data/news.json";
const REPORT_ISSUE_URL = "https://github.com/Gallon00920/Credit_bearing_news_updater/issues/new";
const MANUAL_REFRESH_WORKFLOW_URL = "https://github.com/Gallon00920/Credit_bearing_news_updater/actions/workflows/update-news.yml";
const REPORT_STORAGE_KEY = "news-dashboard-report-logs";
const GROUP_MODE_STORAGE_KEY = "news-dashboard-group-mode";
const TRACKED_SECTORS = [
  "software",
  "private credit / direct lending",
  "GP stakes",
  "aircraft leasing",
  "asset-backed lending",
  "real estate",
  "mortgage",
  "CLO",
];

const uiText = {
  en: {
    eyebrow: "Private credit daily monitor",
    title: "Credit News Dashboard",
    subtitle:
      "US-led coverage with a Europe watchlist for credit strategies, asset-based finance, CLOs, software lending, real estate, mortgage, aircraft leasing, and GP stakes.",
    lastUpdated: "Updated",
    todayRefreshButton: "Refresh Today",
    fullRefreshButton: "Full 90-Day Refresh",
    viewDay: "Day",
    viewWeek: "Week Top 20",
    viewMonth: "Month Top 20",
    groupBySector: "Group by sub-sector",
    groupByGp: "Group by GP",
    unclassified: "Unclassified",
    calendar: "Calendar",
    selectedDate: "Selected date",
    stories: "stories",
    gpCoverage: "GP sections",
    emptyTitle: "No news saved for this date",
    emptyBody: "Run the updater to fetch and score new items, then refresh this page.",
    noGpNews: "No qualifying credit news found for this group in the selected view.",
    hasNews: "Saved news",
    noNews: "No saved news",
    month: "Month",
    year: "Year",
    retention: (days) => `${days}-day rolling window`,
    readOriginal: "Read original article",
    published: "Published",
    source: "Source",
    noDate: "No date",
    report: "Report",
    reportEyebrow: "Feedback",
    reportTitle: "Report classification issue",
    reportReason: "Reason",
    wrongGp: "Wrong GP",
    wrongSector: "Wrong sub-sector",
    notCredit: "Not credit related",
    correctGps: "Correct GP(s)",
    correctSectors: "Correct sub-sector(s)",
    reportDetails: "Additional reason",
    cancelReport: "Cancel",
    submitReport: "Submit report",
    refreshEyebrow: "Manual update",
    todayRefreshTitle: "Refresh today's news?",
    todayRefreshWarning:
      "This manual run refreshes only today's news and dedupes against the saved dashboard data. It does not replace the automatic hourly recent-window refresh; if another update is already running, GitHub Actions will queue this run.",
    fullRefreshTitle: "Run full 90-day refresh?",
    fullRefreshWarning:
      "This may take more than 45 minutes. During that time, the public dashboard will keep showing the current saved news, and you will not be able to read the newly refreshed 90-day results until the update finishes and GitHub Pages redeploys. Please only continue if you are sure.",
    cancelRefresh: "Cancel",
    confirmRefresh: "Continue to GitHub Actions",
  },
  zh: {
    eyebrow: "私募信贷每日监测",
    title: "信贷新闻仪表板",
    subtitle:
      "以美国市场为主，并追踪欧洲动态，涵盖信贷策略、资产支持融资、CLO、软件贷款、房地产、按揭、飞机租赁及 GP stakes。",
    lastUpdated: "更新时间",
    todayRefreshButton: "更新今日",
    fullRefreshButton: "完整更新 90 日",
    viewDay: "单日",
    viewWeek: "本周 Top 20",
    viewMonth: "本月 Top 20",
    groupBySector: "按子行业分组",
    groupByGp: "按 GP 分组",
    unclassified: "未分类",
    calendar: "日历",
    selectedDate: "所选日期",
    stories: "则新闻",
    gpCoverage: "GP 分组",
    emptyTitle: "此视图尚未储存新闻",
    emptyBody: "请先执行更新脚本抓取并评分新闻，然后刷新页面。",
    noGpNews: "此分组在当前视图中未找到符合条件的信贷新闻。",
    hasNews: "已储存新闻",
    noNews: "未储存新闻",
    month: "月份",
    year: "年份",
    retention: (days) => `保留最近 ${days} 日`,
    readOriginal: "阅读原文",
    published: "发布",
    source: "来源",
    noDate: "无日期",
    report: "回报",
    reportEyebrow: "反馈",
    reportTitle: "回报分类问题",
    reportReason: "原因",
    wrongGp: "GP 错误",
    wrongSector: "子行业错误",
    notCredit: "非信贷相关",
    correctGps: "正确 GP",
    correctSectors: "正确子行业",
    reportDetails: "补充原因",
    cancelReport: "取消",
    submitReport: "提交回报",
    refreshEyebrow: "手动更新",
    todayRefreshTitle: "更新今日新闻？",
    todayRefreshWarning:
      "此手动执行只会更新今日新闻，并会与已储存的仪表板数据去重。它不会取代每小时自动执行的最近日期更新；如果已有其他更新正在执行，GitHub Actions 会将此执行排入队列。",
    fullRefreshTitle: "执行完整 90 日更新？",
    fullRefreshWarning:
      "此更新可能需要超过 45 分钟。在此期间，公开仪表板仍会显示目前已储存的新闻；你需要等到更新完成并由 GitHub Pages 重新部署后，才能阅读新的 90 日更新结果。请确认你真的要继续。",
    cancelRefresh: "取消",
    confirmRefresh: "前往 GitHub Actions",
  },
};

let dashboardData = null;
let selectedDate = null;
let calendarMonth = null;
let language = localStorage.getItem("news-dashboard-language") || "en";
let reportingItem = null;
let pendingRefreshMode = "full";
let groupMode = localStorage.getItem(GROUP_MODE_STORAGE_KEY) || "gp";
let viewMode = "day";

const calendar = document.querySelector("#calendar");
const newsList = document.querySelector("#newsList");
const emptyState = document.querySelector("#emptyState");
const selectedDateLabel = document.querySelector("#selectedDateLabel");
const lastUpdated = document.querySelector("#lastUpdated");
const itemCount = document.querySelector("#itemCount");
const retentionLabel = document.querySelector("#retentionLabel");
const todayRefreshButton = document.querySelector("#todayRefreshButton");
const fullRefreshButton = document.querySelector("#fullRefreshButton");
const groupModeToggle = document.querySelector("#groupModeToggle");
const viewModeButtons = document.querySelectorAll("[data-view-mode]");
const languageToggle = document.querySelector("#languageToggle");
const reportDialog = document.querySelector("#reportDialog");
const reportForm = document.querySelector("#reportForm");
const reportArticleTitle = document.querySelector("#reportArticleTitle");
const correctGps = document.querySelector("#correctGps");
const correctSectors = document.querySelector("#correctSectors");
const reportDetails = document.querySelector("#reportDetails");
const refreshDialog = document.querySelector("#refreshDialog");
const refreshDialogTitle = document.querySelector("#refreshDialogTitle");
const refreshDialogBody = document.querySelector("#refreshDialogBody");
const confirmManualRefresh = document.querySelector("#confirmManualRefresh");

async function init() {
  bindEvents();
  dashboardData = await loadData();
  selectedDate = chooseInitialDate(dashboardData);
  calendarMonth = selectedDate.slice(0, 7);
  render();
}

async function loadData() {
  const response = await fetch(DATA_URL, { cache: "no-store" });
  if (!response.ok) {
    throw new Error(`Unable to load ${DATA_URL}`);
  }
  return response.json();
}

function chooseInitialDate(data) {
  return todayKey();
}

function bindEvents() {
  if (languageToggle) {
    languageToggle.addEventListener("click", () => {
      language = language === "en" ? "zh" : "en";
      localStorage.setItem("news-dashboard-language", language);
      if (dashboardData) render();
    });
  }

  viewModeButtons.forEach((button) => {
    button.addEventListener("click", () => {
      viewMode = button.dataset.viewMode || "day";
      render();
    });
  });

  if (groupModeToggle) {
    groupModeToggle.addEventListener("click", () => {
      groupMode = groupMode === "gp" ? "sector" : "gp";
      localStorage.setItem(GROUP_MODE_STORAGE_KEY, groupMode);
      render();
    });
  }

  if (todayRefreshButton) {
    todayRefreshButton.addEventListener("click", () => openRefreshDialog("today"));
  }
  if (fullRefreshButton) {
    fullRefreshButton.addEventListener("click", () => openRefreshDialog("full"));
  }
  if (confirmManualRefresh) {
    confirmManualRefresh.addEventListener("click", openManualRefreshWorkflow);
  }
  document.querySelectorAll("[data-refresh-close]").forEach((button) => {
    button.addEventListener("click", () => refreshDialog?.close());
  });

  if (reportForm) {
    reportForm.addEventListener("submit", submitReport);
  }
  document.querySelectorAll("[data-report-close]").forEach((button) => {
    button.addEventListener("click", () => reportDialog?.close());
  });
}

function openRefreshDialog(mode) {
  pendingRefreshMode = mode;
  syncRefreshDialogText();
  if (refreshDialog && typeof refreshDialog.showModal === "function") {
    try {
      refreshDialog.showModal();
      return;
    } catch (error) {
      console.warn("Unable to open refresh dialog; using browser confirm instead.", error);
    }
  }
  if (refreshDialog) {
    refreshDialog.setAttribute("open", "");
    return;
  }
  confirmManualRefreshWithBrowserDialog();
}

function syncRefreshDialogText() {
  if (!refreshDialogTitle || !refreshDialogBody) return;
  const modePrefix = pendingRefreshMode === "today" ? "todayRefresh" : "fullRefresh";
  refreshDialogTitle.textContent = uiText[language][`${modePrefix}Title`];
  refreshDialogBody.textContent = uiText[language][`${modePrefix}Warning`];
}

function openManualRefreshWorkflow() {
  window.open(MANUAL_REFRESH_WORKFLOW_URL, "_blank", "noopener,noreferrer");
  refreshDialog?.close();
}

function confirmManualRefreshWithBrowserDialog() {
  const modePrefix = pendingRefreshMode === "today" ? "todayRefresh" : "fullRefresh";
  const confirmed = window.confirm(`${uiText[language][`${modePrefix}Title`]}\n\n${uiText[language][`${modePrefix}Warning`]}`);
  if (confirmed) {
    openManualRefreshWorkflow();
  }
}

function render() {
  document.documentElement.lang = language === "zh" ? "zh-Hans" : "en";
  applyUiText();
  syncRefreshDialogText();
  renderHeader();
  renderCalendar();
  renderNews();
  renderViewControls();
  renderLanguageToggle();
}

function applyUiText() {
  document.querySelectorAll("[data-i18n]").forEach((node) => {
    const key = node.dataset.i18n;
    const value = uiText[language][key];
    if (typeof value === "string") {
      node.textContent = value;
    }
  });
}

function renderHeader() {
  const updated = dashboardData.updatedAt ? formatDateTime(dashboardData.updatedAt) : "--";
  lastUpdated.textContent = updated;
  retentionLabel.textContent = uiText[language].retention(dashboardData.retentionDays || 90);
}

function renderCalendar() {
  const windowInfo = getWindowInfo();
  const monthDate = parseDate(`${calendarMonth}-01`);
  const years = getSelectableYears(windowInfo.start, windowInfo.end);
  const monthNames = getMonthNames();
  const activeYear = monthDate.getFullYear();
  const activeMonth = monthDate.getMonth();
  const canGoPrev = addMonths(monthDate, -1) >= startOfMonth(windowInfo.start);
  const canGoNext = addMonths(monthDate, 1) <= startOfMonth(windowInfo.end);

  calendar.innerHTML = `
    <div class="calendar-controls">
      <button class="calendar-nav" type="button" data-calendar-prev aria-label="Previous month" ${canGoPrev ? "" : "disabled"}>&lt;</button>
      <label>
        <span>${uiText[language].year}</span>
        <select data-calendar-year>
          ${years.map((year) => `<option value="${year}" ${year === activeYear ? "selected" : ""}>${year}</option>`).join("")}
        </select>
      </label>
      <label>
        <span>${uiText[language].month}</span>
        <select data-calendar-month>
          ${monthNames.map((month, index) => {
            const optionMonth = new Date(activeYear, index, 1);
            const inRange = optionMonth >= startOfMonth(windowInfo.start) && optionMonth <= startOfMonth(windowInfo.end);
            return `<option value="${index}" ${index === activeMonth ? "selected" : ""} ${inRange ? "" : "disabled"}>${month}</option>`;
          }).join("")}
        </select>
      </label>
      <button class="calendar-nav" type="button" data-calendar-next aria-label="Next month" ${canGoNext ? "" : "disabled"}>&gt;</button>
    </div>
    <div class="calendar-weekdays">
      ${getWeekdays().map((day) => `<span>${day}</span>`).join("")}
    </div>
    <div class="calendar-grid"></div>
  `;

  calendar.querySelector("[data-calendar-prev]").addEventListener("click", () => setCalendarMonth(addMonths(monthDate, -1)));
  calendar.querySelector("[data-calendar-next]").addEventListener("click", () => setCalendarMonth(addMonths(monthDate, 1)));
  calendar.querySelector("[data-calendar-year]").addEventListener("change", (event) => {
    setCalendarMonth(new Date(Number(event.target.value), activeMonth, 1));
  });
  calendar.querySelector("[data-calendar-month]").addEventListener("change", (event) => {
    setCalendarMonth(new Date(activeYear, Number(event.target.value), 1));
  });

  const grid = calendar.querySelector(".calendar-grid");
  buildCalendarDays(monthDate).forEach((date) => {
    const dateKey = toDateKey(date);
    const inMonth = date.getMonth() === activeMonth;
    const inWindow = date >= windowInfo.start && date <= windowInfo.end;
    const items = collectItemsForDate(dashboardData.dates?.[dateKey]);
    const button = document.createElement("button");
    button.className = [
      "calendar-day",
      inMonth ? "" : "outside-month",
      dateKey === selectedDate ? "active" : "",
      items.length ? "has-news" : "",
    ].filter(Boolean).join(" ");
    button.type = "button";
    button.disabled = !inWindow;
    button.title = items.length ? `${items.length} ${uiText[language].stories}` : uiText[language].noNews;
    button.innerHTML = `<span>${date.getDate()}</span>${items.length ? `<small>${items.length}</small>` : ""}`;
    button.addEventListener("click", () => {
      selectedDate = dateKey;
      calendarMonth = dateKey.slice(0, 7);
      render();
    });
    grid.append(button);
  });
}

function setCalendarMonth(date) {
  const windowInfo = getWindowInfo();
  const clamped = clampDate(startOfMonth(date), startOfMonth(windowInfo.start), startOfMonth(windowInfo.end));
  calendarMonth = toDateKey(clamped).slice(0, 7);
  render();
}

function renderNews() {
  const view = getActiveView();
  const groups = buildGroupsForItems(view.items);
  selectedDateLabel.textContent = view.label;
  itemCount.textContent = view.items.length;
  emptyState.hidden = view.items.length > 0;
  newsList.innerHTML = "";

  groups.forEach((group) => {
    const section = document.createElement("section");
    section.className = "gp-section";
    section.innerHTML = `
      <div class="gp-section-header">
        <h3>${escapeHtml(group.label)}</h3>
        <span>${group.items.length} ${uiText[language].stories}</span>
      </div>
      <div class="gp-section-body"></div>
    `;

    const body = section.querySelector(".gp-section-body");
    if (group.items.length) {
      group.items.forEach((item) => body.append(renderNewsCard(item)));
    } else {
      const empty = document.createElement("p");
      empty.className = "gp-empty fine-print";
      empty.textContent = uiText[language].noGpNews;
      body.append(empty);
    }

    newsList.append(section);
  });
}

function getActiveView() {
  if (viewMode === "week") {
    const range = getWeekRange(parseDate(selectedDate));
    const items = topScoredItems(collectItemsBetween(range.start, range.end), 20);
    return {
      items: sortItemsByDate(items),
      label: `${formatDate(toDateKey(range.start))} - ${formatDate(toDateKey(range.end))}`,
    };
  }

  if (viewMode === "month") {
    const current = parseDate(selectedDate);
    const start = startOfMonth(current);
    const end = new Date(current.getFullYear(), current.getMonth() + 1, 0);
    const items = topScoredItems(collectItemsBetween(start, end), 20);
    return {
      items: sortItemsByDate(items),
      label: new Intl.DateTimeFormat(language === "zh" ? "zh-Hans-CN" : "en-US", { year: "numeric", month: "long" }).format(current),
    };
  }

  const dateData = dashboardData.dates?.[selectedDate];
  return {
    items: collectItemsForDate(dateData),
    label: selectedDate ? formatDate(selectedDate) : uiText[language].noDate,
  };
}

function buildGroupsForItems(items) {
  const order = groupMode === "sector" ? TRACKED_SECTORS : dashboardData.scope?.gps || [];
  const field = groupMode === "sector" ? "sectors" : "gps";
  const groups = order.map((label) => ({
    label,
    items: dedupeItems(items.filter((item) => (item[field] || []).includes(label))),
  }));
  const unclassified = dedupeItems(items.filter((item) => !(item[field] || []).length));
  if (unclassified.length) {
    groups.push({ label: uiText[language].unclassified, items: unclassified });
  }
  return groups;
}

function collectItemsBetween(start, end) {
  const items = [];
  Object.entries(dashboardData.dates || {}).forEach(([dateKey, dateData]) => {
    const date = parseDate(dateKey);
    if (date >= start && date <= end) {
      items.push(...collectItemsForDate(dateData));
    }
  });
  return dedupeItems(items);
}

function topScoredItems(items, limit) {
  return [...dedupeItems(items)]
    .sort((a, b) => getItemScore(b) - getItemScore(a) || compareItemDates(b, a))
    .slice(0, limit);
}

function sortItemsByDate(items) {
  return [...items].sort((a, b) => compareItemDates(b, a) || getItemScore(b) - getItemScore(a));
}

function compareItemDates(a, b) {
  return String(a.publishedAt || a.date || "").localeCompare(String(b.publishedAt || b.date || ""));
}

function getItemScore(item) {
  const breakdown = item.scoreBreakdown || {};
  return Number(breakdown.finalScore ?? item.score ?? (Number(breakdown.keywordScore || 0) + Number(breakdown.semanticScore || 0))) || 0;
}

function getWeekRange(date) {
  const start = addDays(date, -((date.getDay() + 6) % 7));
  const end = addDays(start, 6);
  return { start, end };
}

function renderNewsCard(item) {
  const card = document.createElement("article");
  card.className = "news-card";
  const regionClass = (item.region || "global").toLowerCase();
  card.innerHTML = `
    <div class="news-card-header">
      <h3 class="news-title">${escapeHtml(localized(item, "title"))}</h3>
      <span class="region-pill ${escapeHtml(regionClass)}">${escapeHtml(item.region || "Global")}</span>
    </div>
    <p class="summary">${escapeHtml(localized(item, "summary"))}</p>
    <div class="source-row">
      <a class="article-link" href="${escapeAttribute(item.url)}" target="_blank" rel="noopener noreferrer">${uiText[language].readOriginal}</a>
      <span class="source-meta">${uiText[language].source}: ${escapeHtml(item.source || "Unknown")}</span>
      <span class="source-meta">${uiText[language].published}: ${formatDate(item.publishedAt || item.date || selectedDate)}</span>
    </div>
    <div class="tags">${renderTags(item)}</div>
    <button class="report-button" type="button">${uiText[language].report}</button>
  `;
  card.querySelector(".report-button").addEventListener("click", () => openReportDialog(item));
  return card;
}

function openReportDialog(item) {
  reportingItem = item;
  reportArticleTitle.textContent = item.title || "";
  reportDetails.value = "";
  populateReportSelect(correctGps, dashboardData.scope?.gps || [], item.gps || []);
  populateReportSelect(correctSectors, TRACKED_SECTORS, item.sectors || []);
  reportForm.elements.reasonType.value = "wrong_gp";
  if (typeof reportDialog.showModal === "function") {
    reportDialog.showModal();
  } else {
    reportDialog.setAttribute("open", "");
  }
}

function populateReportSelect(select, options, selectedValues) {
  select.innerHTML = "";
  options.forEach((option) => {
    const node = document.createElement("option");
    node.value = option;
    node.textContent = option;
    node.selected = selectedValues.includes(option);
    select.append(node);
  });
}

function submitReport(event) {
  event.preventDefault();
  if (!reportingItem) return;

  const reasonType = reportForm.elements.reasonType.value;
  const report = {
    reportedAt: new Date().toISOString(),
    reasonType,
    reason: reportDetails.value.trim(),
    itemId: reportingItem.id || "",
    title: reportingItem.title || "",
    url: reportingItem.url || "",
    source: reportingItem.source || "",
    publishedAt: reportingItem.publishedAt || "",
    lede: reportingItem.lede || "",
    articleText: reportingItem.articleExcerpt || `${reportingItem.title || ""}. ${reportingItem.lede || ""}`.trim(),
    original: {
      gps: reportingItem.gps || [],
      sectors: reportingItem.sectors || [],
    },
    corrected: {
      gps: selectedOptions(correctGps),
      sectors: selectedOptions(correctSectors),
      exclude: reasonType === "not_credit",
    },
  };

  saveReportLocally(report);
  window.open(githubIssueUrl(report), "_blank", "noopener,noreferrer");
  reportDialog.close();
}

function selectedOptions(select) {
  return Array.from(select.selectedOptions).map((option) => option.value);
}

function saveReportLocally(report) {
  const existing = JSON.parse(localStorage.getItem(REPORT_STORAGE_KEY) || "[]");
  existing.push(report);
  localStorage.setItem(REPORT_STORAGE_KEY, JSON.stringify(existing));
}

function githubIssueUrl(report) {
  const title = `News classification report: ${report.title}`.slice(0, 160);
  const body = [
    "Please review this report and, if valid, append it to `data/golden_cases.json`.",
    "",
    "```json",
    JSON.stringify(report, null, 2),
    "```",
  ].join("\n");
  const params = new URLSearchParams({ title, body });
  return `${REPORT_ISSUE_URL}?${params.toString()}`;
}

function collectItemsForDate(dateData) {
  if (!dateData) return [];
  const items = [...(dateData.items || [])];
  Object.values(dateData.byGp || {}).forEach((groupItems) => items.push(...groupItems));
  return dedupeItems(items);
}

function dedupeItems(items) {
  const seen = new Set();
  return items.filter((item) => {
    const key = item.id || item.url;
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

function renderTags(item) {
  const gpTags = (item.gps || []).map((tag) => `<span class="tag gp">GP: ${escapeHtml(tag)}</span>`);
  const sectorTags = (item.sectors || []).map((tag) => `<span class="tag sector">${escapeHtml(tag)}</span>`);
  return [...gpTags, ...sectorTags].join("");
}

function renderViewControls() {
  viewModeButtons.forEach((button) => {
    button.classList.toggle("active", button.dataset.viewMode === viewMode);
  });
  if (groupModeToggle) {
    groupModeToggle.textContent = groupMode === "gp" ? uiText[language].groupBySector : uiText[language].groupByGp;
  }
}

function renderLanguageToggle() {
  document.querySelectorAll("[data-lang-pill]").forEach((node) => {
    node.classList.toggle("active", node.dataset.langPill === language);
  });
}

function localized(item, field) {
  if (language === "zh") {
    return item[`${field}Zh`] || item[field] || "";
  }
  return item[field] || "";
}

function formatDate(value) {
  if (!value) return "--";
  const date = new Date(`${value.slice(0, 10)}T12:00:00Z`);
  return new Intl.DateTimeFormat(language === "zh" ? "zh-Hans-CN" : "en-US", {
    year: "numeric",
    month: "short",
    day: "numeric",
    weekday: "short",
  }).format(date);
}

function formatDateTime(value) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat(language === "zh" ? "zh-Hans-CN" : "en-US", {
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

function todayKey() {
  return toDateKey(new Date());
}

function getWindowInfo() {
  const end = parseDate(todayKey());
  const start = addDays(end, -((dashboardData.retentionDays || 90) - 1));
  return { start, end };
}

function getSelectableYears(start, end) {
  const years = [];
  for (let year = start.getFullYear(); year <= end.getFullYear(); year += 1) {
    years.push(year);
  }
  return years;
}

function getMonthNames() {
  return Array.from({ length: 12 }, (_, month) =>
    new Intl.DateTimeFormat(language === "zh" ? "zh-Hans-CN" : "en-US", { month: "short" }).format(new Date(2026, month, 1))
  );
}

function getWeekdays() {
  const base = new Date(2026, 0, 4);
  return Array.from({ length: 7 }, (_, index) =>
    new Intl.DateTimeFormat(language === "zh" ? "zh-Hans-CN" : "en-US", { weekday: "short" }).format(addDays(base, index))
  );
}

function buildCalendarDays(monthDate) {
  const first = startOfMonth(monthDate);
  const start = addDays(first, -first.getDay());
  return Array.from({ length: 42 }, (_, index) => addDays(start, index));
}

function parseDate(value) {
  const [year, month, day] = value.split("-").map(Number);
  return new Date(year, month - 1, day);
}

function toDateKey(date) {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function addDays(date, days) {
  const next = new Date(date);
  next.setDate(next.getDate() + days);
  return next;
}

function addMonths(date, months) {
  return new Date(date.getFullYear(), date.getMonth() + months, 1);
}

function startOfMonth(date) {
  return new Date(date.getFullYear(), date.getMonth(), 1);
}

function clampDate(date, min, max) {
  if (date < min) return min;
  if (date > max) return max;
  return date;
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function escapeAttribute(value) {
  return escapeHtml(value || "#");
}

init().catch((error) => {
  newsList.innerHTML = `<div class="empty-state"><h3>Unable to load dashboard data</h3><p>${escapeHtml(error.message)}</p></div>`;
});
