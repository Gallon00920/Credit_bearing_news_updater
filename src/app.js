const DATA_URL = "data/news.json";

const uiText = {
  en: {
    eyebrow: "Private credit daily monitor",
    title: "Credit News Dashboard",
    subtitle:
      "US-led coverage with a Europe watchlist for credit strategies, asset-based finance, CLOs, software lending, real estate, mortgage, aircraft leasing, and GP stakes.",
    lastUpdated: "Updated",
    calendar: "Calendar",
    selectedDate: "Selected date",
    stories: "stories",
    gpCoverage: "GP sections",
    emptyTitle: "No news saved for this date",
    emptyBody: "Run the updater to fetch and score new items, then refresh this page.",
    noGpNews: "No qualifying credit news found for this GP on the selected date.",
    hasNews: "Saved news",
    noNews: "No saved news",
    month: "Month",
    year: "Year",
    retention: (days) => `${days}-day rolling window`,
    readOriginal: "Read original article",
    published: "Published",
    source: "Source",
    noDate: "No date",
  },
  zh: {
    eyebrow: "私人信貸每日監察",
    title: "信貸新聞儀表板",
    subtitle:
      "以美國市場為主，並追蹤歐洲動態，涵蓋信貸策略、資產支持融資、CLO、軟件貸款、房地產、按揭、飛機租賃及 GP stakes。",
    lastUpdated: "更新時間",
    calendar: "日曆",
    selectedDate: "所選日期",
    stories: "則新聞",
    gpCoverage: "GP 分組",
    emptyTitle: "此日期尚未儲存新聞",
    emptyBody: "請先執行更新腳本抓取並評分新聞，然後重新整理頁面。",
    noGpNews: "此 GP 在所選日期未找到符合條件的信貸新聞。",
    hasNews: "已儲存新聞",
    noNews: "未儲存新聞",
    month: "月份",
    year: "年份",
    retention: (days) => `保留最近 ${days} 日`,
    readOriginal: "閱讀原文",
    published: "發布",
    source: "來源",
    noDate: "無日期",
  },
};

let dashboardData = null;
let selectedDate = null;
let calendarMonth = null;
let language = localStorage.getItem("news-dashboard-language") || "en";

const calendar = document.querySelector("#calendar");
const newsList = document.querySelector("#newsList");
const emptyState = document.querySelector("#emptyState");
const selectedDateLabel = document.querySelector("#selectedDateLabel");
const lastUpdated = document.querySelector("#lastUpdated");
const itemCount = document.querySelector("#itemCount");
const retentionLabel = document.querySelector("#retentionLabel");
const languageToggle = document.querySelector("#languageToggle");

async function init() {
  dashboardData = await loadData();
  selectedDate = chooseInitialDate(dashboardData);
  calendarMonth = selectedDate.slice(0, 7);
  bindEvents();
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
  languageToggle.addEventListener("click", () => {
    language = language === "en" ? "zh" : "en";
    localStorage.setItem("news-dashboard-language", language);
    render();
  });
}

function render() {
  document.documentElement.lang = language === "zh" ? "zh-Hant" : "en";
  applyUiText();
  renderHeader();
  renderCalendar();
  renderNews();
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
  const dateData = dashboardData.dates?.[selectedDate];
  const groups = buildGpGroups(dateData);
  const items = collectItemsForDate(dateData);
  selectedDateLabel.textContent = selectedDate ? formatDate(selectedDate) : uiText[language].noDate;
  itemCount.textContent = items.length;
  emptyState.hidden = items.length > 0;
  newsList.innerHTML = "";

  groups.forEach((group) => {
    const section = document.createElement("section");
    section.className = "gp-section";
    section.innerHTML = `
      <div class="gp-section-header">
        <h3>${escapeHtml(group.gp)}</h3>
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
  `;
  return card;
}

function buildGpGroups(dateData) {
  const gpOrder = dashboardData.scope?.gps || [];
  const items = dateData?.items || [];
  const byGp = dateData?.byGp || {};

  return gpOrder.map((gp) => {
    const groupedItems = byGp[gp] || items.filter((item) => (item.gps || []).includes(gp));
    return {
      gp,
      items: dedupeItems(groupedItems),
    };
  });
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
  return new Intl.DateTimeFormat(language === "zh" ? "zh-Hant-HK" : "en-US", {
    year: "numeric",
    month: "short",
    day: "numeric",
    weekday: "short",
  }).format(date);
}

function formatDateTime(value) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat(language === "zh" ? "zh-Hant-HK" : "en-US", {
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
    new Intl.DateTimeFormat(language === "zh" ? "zh-Hant-HK" : "en-US", { month: "short" }).format(new Date(2026, month, 1))
  );
}

function getWeekdays() {
  const base = new Date(2026, 0, 4);
  return Array.from({ length: 7 }, (_, index) =>
    new Intl.DateTimeFormat(language === "zh" ? "zh-Hant-HK" : "en-US", { weekday: "short" }).format(addDays(base, index))
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
