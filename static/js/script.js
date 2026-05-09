import { icons } from "./icons.js";

let chats = {};
let currentChatId = localStorage.getItem("currentChatId") || null;
let renameTargetChatId = null;
let activeMenuChatId = null;
let isSending = false;
let authUser = null;
let currentAuthView = "login";

const ONBOARDING_STORAGE_KEY = "js_onboarding_state";
const DEV_FORCE_SURVEY_RESET_KEY = "js_dev_force_survey_reset";

/* =========================
   STREAK SYSTEM (server-side)
========================= */

// In-memory cache of the last fetched streak state
let _streakCache = null; // { streak_days, last_streak_date, active_today }

async function fetchStreakFromServer() {
  try {
    const data = await api("/streak");
    _streakCache = data;
    return data;
  } catch {
    return _streakCache || { streak_days: 0, last_streak_date: null, active_today: false };
  }
}

async function recordStreakActivity() {
  try {
    const data = await api("/streak/activity", { method: "POST" });
    _streakCache = data;
    return data;
  } catch {
    return _streakCache || { streak_days: 0, last_streak_date: null, active_today: false };
  }
}

function getStreakDisplayState() {
  if (!_streakCache) return { count: 0, active: false };
  return {
    count: _streakCache.streak_days,
    active: _streakCache.active_today,
  };
}

function renderStreakWidget(animate = false) {
  const streakWidget = document.getElementById("streakWidget");
  const streakIcon = document.getElementById("streakIcon");
  const streakCount = document.getElementById("streakCount");

  if (!streakWidget || !streakIcon || !streakCount) return;

  // Only show when user is logged in
  if (!authUser) {
    streakWidget.classList.add("hidden");
    return;
  }

  streakWidget.classList.remove("hidden");

  const { count, active } = getStreakDisplayState();
  streakIcon.innerHTML = icons.flame;
  streakCount.textContent = String(count);

  streakWidget.classList.toggle("streak-active", active);

  if (animate) {
    streakWidget.classList.remove("streak-pop");
    void streakWidget.offsetWidth; // reflow to restart animation
    streakWidget.classList.add("streak-pop");
    streakWidget.addEventListener("animationend", () => {
      streakWidget.classList.remove("streak-pop");
    }, { once: true });
  }
}

const TOPIC_ORDER = [
  "variables",
  "operators",
  "conditions",
  "loops",
  "functions",
  "strings",
  "arrays",
  "objects",
  "dom",
  "events",
  "this",
  "modules",
  "async",
  "api"
];

const FALLBACK_TOPICS = [
  { key: "variables", title: "Переменные и типы данных" },
  { key: "operators", title: "Операторы" },
  { key: "conditions", title: "Условия" },
  { key: "loops", title: "Циклы" },
  { key: "functions", title: "Функции" },
  { key: "strings", title: "Строки" },
  { key: "arrays", title: "Массивы" },
  { key: "objects", title: "Объекты" },
  { key: "dom", title: "DOM" },
  { key: "events", title: "События" },
  { key: "this", title: "Ключевое слово this" },
  { key: "modules", title: "Модули" },
  { key: "async", title: "Async / Await" },
  { key: "api", title: "Fetch / API" }
];

// Grouped topics shown in the onboarding survey (beginner + some intermediate)
// Keys map to roadmap nodeSlug/topicKey so checked items get highlighted in the roadmap
const SURVEY_TOPIC_GROUPS = [
  {
    group: "Основы языка",
    level: "beginner",
    topics: [
      { key: "variables", title: "Переменные и типы данных", hint: "var, let, const, hoisting, области видимости" },
      { key: "operators", title: "Операторы и выражения", hint: "арифметика, сравнение, логические операторы" },
      { key: "conditions", title: "Условные конструкции", hint: "if / else, switch, тернарный оператор" },
      { key: "loops", title: "Циклы и итерации", hint: "for, while, for...of, break / continue" },
      { key: "functions", title: "Функции", hint: "объявление, стрелочные, замыкания, рекурсия" },
      { key: "strings", title: "Строки", hint: "методы строк, шаблонные литералы, RegExp" },
    ]
  },
  {
    group: "Структуры данных",
    level: "beginner",
    topics: [
      { key: "arrays", title: "Массивы", hint: "map, filter, reduce, spread, деструктуризация" },
      { key: "objects", title: "Объекты", hint: "свойства, методы, деструктуризация, spread" },
    ]
  },
  {
    group: "Браузер и взаимодействие",
    level: "intermediate",
    topics: [
      { key: "dom", title: "DOM API", hint: "querySelector, createElement, innerHTML, classList" },
      { key: "events", title: "События", hint: "addEventListener, делегирование, bubbling" },
    ]
  },
  {
    group: "Продвинутые концепции",
    level: "intermediate",
    topics: [
      { key: "this", title: "Ключевое слово this", hint: "в методах, функциях, arrow functions, bind/call/apply" },
      { key: "modules", title: "Модули", hint: "ES Modules, import / export, CommonJS" },
    ]
  },
  {
    group: "Асинхронность и API",
    level: "intermediate",
    topics: [
      { key: "async", title: "Асинхронный JavaScript", hint: "Event Loop, Promise, async / await" },
      { key: "api", title: "Работа с API", hint: "Fetch API, HTTP-запросы, JSON, REST" },
    ]
  }
];

let onboardingState = JSON.parse(localStorage.getItem(ONBOARDING_STORAGE_KEY)) || {
  completed: false,
  level: null,
  topics: []
};

let topicsState = {
  all: sortTopicsByLearningOrder([...FALLBACK_TOPICS]),
  learned: []
};

const chatListEl = document.getElementById("chatList");
const messagesDiv = document.getElementById("messages");
const chatTitleEl = document.getElementById("chatTitle");
const form = document.getElementById("inputForm");
const input = document.getElementById("queryInput");
const sendBtn = document.getElementById("sendBtn");
const themeBtn = document.getElementById("themeToggle");
const sidebar = document.getElementById("sidebar");
const sidebarToggle = document.getElementById("sidebarToggle");
const welcomeScreen = document.getElementById("welcomeScreen");
const newChatBtn = document.getElementById("newChatBtn");
const chatArea = document.getElementById("chatArea");
const mainContent = document.getElementById("mainContent");
const appShell = document.getElementById("appShell");

const renameModal = document.getElementById("renameModal");
const renameForm = document.getElementById("renameForm");
const renameInput = document.getElementById("renameInput");
const renameCloseBtn = document.getElementById("renameCloseBtn");
const renameCancelBtn = document.getElementById("renameCancelBtn");

const contextMenu = document.getElementById("chatContextMenu");
const contextRenameBtn = document.getElementById("contextRenameBtn");
const contextDeleteBtn = document.getElementById("contextDeleteBtn");

const surveyModal = document.getElementById("surveyModal");
const levelBeginnerBtn = document.getElementById("levelBeginnerBtn");
const levelReturningBtn = document.getElementById("levelReturningBtn");
const topicsSection = document.getElementById("topicsSection"); // legacy stub
const topicsGrid = document.getElementById("topicsGrid");
const surveyContinueBtn = document.getElementById("surveyContinueBtn");
const surveyStep1 = document.getElementById("surveyStep1");
const surveyStep2 = document.getElementById("surveyStep2");
const surveyStep1NextBtn = document.getElementById("surveyStep1NextBtn");
const surveyBackBtn = document.getElementById("surveyBackBtn");
const surveyProgressBar = document.getElementById("surveyProgressBar");

const userMenuBtn = document.getElementById("userMenuBtn");
const userDropdown = document.getElementById("userDropdown");
const userDropdownEmail = document.getElementById("userDropdownEmail");
const topicsDropdownBtn = document.getElementById("topicsDropdownBtn");
const logoutBtn = document.getElementById("logoutBtn");

const topicsModal = document.getElementById("topicsModal");
const topicsManagerGrid = document.getElementById("topicsManagerGrid");
const topicsProgressHeader = document.getElementById("topicsProgressHeader");
const topicsCloseBtn = document.getElementById("topicsCloseBtn");
const devResetSurveyBtn = document.getElementById("devResetSurveyBtn");

const guideModal = document.getElementById("guideModal");
const guideBtn = document.getElementById("guideBtn");
const guideCloseBtn = document.getElementById("guideCloseBtn");

const authOverlay = document.getElementById("authOverlay");
const authTabs = document.querySelectorAll("[data-auth-tab]");
const loginAuthForm = document.getElementById("loginAuthForm");
const registerAuthForm = document.getElementById("registerAuthForm");
const resetAuthForm = document.getElementById("resetAuthForm");
const forgotPasswordBtn = document.getElementById("forgotPasswordBtn");
const authMessage = document.getElementById("authMessage");

const DRAFT_CHAT_ID = "__draft__";
const MAX_TEXTAREA_HEIGHT = 220;
const TITLE_TYPING_DELAY_MS = 28;
const ASSISTANT_TYPING_DELAY_MS = 10;

const titleTypingState = {
  activeChatId: null,
  timers: new Map()
};

const assistantTypingState = {
  chatId: null,
  messageIndex: null,
  timer: null,
  fullText: "",
  currentText: "",
  isActive: false
};

const thinkingState = {
  chatId: null,
  isActive: false
};

/* =========================
   API
========================= */
async function api(path, options = {}) {
  const response = await fetch(path, {
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
      ...(options.headers || {})
    },
    ...options
  });

  const data = await response.json().catch(() => ({}));

  if (response.status === 401) {
    setUnauthorizedState();
    throw new Error("Требуется авторизация");
  }

  if (!response.ok) {
    throw new Error(data.detail || "Ошибка запроса к серверу");
  }

  return data;
}

/* =========================
   HELPERS
========================= */
function saveCurrentChatId() {
  if (currentChatId && currentChatId !== DRAFT_CHAT_ID) {
    localStorage.setItem("currentChatId", currentChatId);
  } else {
    localStorage.removeItem("currentChatId");
  }
}

function getSortedChatEntries() {
  return Object.entries(chats).sort((a, b) => {
    const aDate = a[1]?.updated_at || "";
    const bDate = b[1]?.updated_at || "";
    return bDate.localeCompare(aDate);
  });
}

function getCurrentChat() {
  if (!currentChatId) return null;
  return chats[currentChatId] || null;
}

function ensureDraftChat() {
  if (!chats[DRAFT_CHAT_ID]) {
    chats[DRAFT_CHAT_ID] = {
      chat_id: null,
      title: "Новый чат",
      created_at: null,
      updated_at: null,
      messages: []
    };
  }
}

function setSendingState(sending) {
  isSending = sending;
  updateChatAvailability();
}

function autoResizeTextarea() {
  input.style.height = "auto";
  const nextHeight = Math.min(input.scrollHeight, MAX_TEXTAREA_HEIGHT);
  input.style.height = `${nextHeight}px`;
  input.style.overflowY = input.scrollHeight > MAX_TEXTAREA_HEIGHT ? "auto" : "hidden";
}

function resetTextareaHeight() {
  input.style.height = "24px";
  input.style.overflowY = "hidden";
}

const SCROLL_SNAP_THRESHOLD = 80; // px от низа — считаем «у дна»

let userScrolling = false;
let userScrollingTimer = null;

function isUserNearBottom() {
  const { scrollTop, scrollHeight, clientHeight } = chatArea;
  return scrollHeight - scrollTop - clientHeight <= SCROLL_SNAP_THRESHOLD;
}

function scrollMessagesToBottom(force = false) {
  requestAnimationFrame(() => {
    if (force || (!userScrolling && isUserNearBottom())) {
      chatArea.scrollTop = chatArea.scrollHeight;
    }
  });
}

function chatHasMessages(chat) {
  return Boolean(chat && Array.isArray(chat.messages) && chat.messages.length > 0);
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function showAuthMessage(text, type = "error") {
  authMessage.textContent = text;
  authMessage.className = `auth-message ${type}`;
  authMessage.classList.remove("hidden");
}

function hideAuthMessage() {
  authMessage.textContent = "";
  authMessage.className = "auth-message hidden";
}

function isDevEnvironment() {
  const host = window.location.hostname;
  return host === "localhost" || host === "127.0.0.1";
}

function shouldForceSurveyReset() {
  return localStorage.getItem(DEV_FORCE_SURVEY_RESET_KEY) === "1";
}

function setDevResetButtonVisibility() {
  if (!devResetSurveyBtn) return;
  devResetSurveyBtn.classList.toggle("hidden", !isDevEnvironment() || !authUser);
}

async function resetSurveyForDev() {
  if (!isDevEnvironment()) return;

  // 1. Сбросить локальный onboarding state
  onboardingState = { completed: false, level: null, topics: [] };
  saveOnboardingState();
  localStorage.setItem(DEV_FORCE_SURVEY_RESET_KEY, "1");

  // 2. Сбросить выученные темы на сервере
  try {
    await api("/topics/me", {
      method: "PUT",
      body: JSON.stringify({ topic_keys: [] })
    });
    topicsState.learned = [];
  } catch (err) {
    console.warn("Не удалось сбросить темы на сервере:", err);
  }

  // 3. Сбросить прогресс дорожной карты на сервере
  try {
    await api("/roadmap/items", {
      method: "PUT",
      body: JSON.stringify({ item_slugs: [] })
    });
    roadmapItemsState = new Set();
  } catch (err) {
    console.warn("Не удалось сбросить дорожную карту:", err);
  }

  // 4. Перерисовать всё
  userDropdown.classList.add("hidden");
  renderSurveyTopicsGrid();
  renderTopicsManager();
  updateSurveyUI();
  updateChatAvailability();
  openSurveyModal();
}

function setAuthView(view) {
  currentAuthView = view;
  hideAuthMessage();

  authTabs.forEach((tab) => {
    tab.classList.toggle("active", tab.dataset.authTab === view);
  });

  loginAuthForm.classList.toggle("hidden", view !== "login");
  registerAuthForm.classList.toggle("hidden", view !== "register");
  resetAuthForm.classList.toggle("hidden", view !== "reset");

  loginAuthForm.classList.toggle("auth-form-active", view === "login");
  registerAuthForm.classList.toggle("auth-form-active", view === "register");
  resetAuthForm.classList.toggle("auth-form-active", view === "reset");
}

function openAuthOverlay(defaultView = "login") {
  authOverlay.classList.remove("hidden");
  appShell.classList.add("auth-locked");
  setAuthView(defaultView);
}

function closeAuthOverlay() {
  authOverlay.classList.add("hidden");
  appShell.classList.remove("auth-locked");
}

function setAuthorizedState(user) {
  authUser = user;
  userMenuBtn.classList.remove("hidden");
  userDropdownEmail.textContent = user.email || "";
  closeAuthOverlay();
  setDevResetButtonVisibility();
  updateChatAvailability();
  renderStreakWidget();
}

function setUnauthorizedState() {
  authUser = null;
  userDropdown.classList.add("hidden");
  userMenuBtn.classList.add("hidden");
  setDevResetButtonVisibility();
  renderStreakWidget();
  openAuthOverlay("login");
  updateChatAvailability();
}

function sortTopicsByLearningOrder(topics = []) {
  const orderMap = new Map(TOPIC_ORDER.map((key, index) => [key, index]));

  return [...topics].sort((a, b) => {
    const aIndex = orderMap.has(a.key) ? orderMap.get(a.key) : Number.MAX_SAFE_INTEGER;
    const bIndex = orderMap.has(b.key) ? orderMap.get(b.key) : Number.MAX_SAFE_INTEGER;
    return aIndex - bIndex;
  });
}

function getTopicCatalog() {
  if (Array.isArray(topicsState.all) && topicsState.all.length > 0) {
    return sortTopicsByLearningOrder(topicsState.all);
  }

  return sortTopicsByLearningOrder(FALLBACK_TOPICS);
}

function getTopicMap() {
  return new Map(getTopicCatalog().map((topic) => [topic.key, topic]));
}

function normalizeTopicKeys(topicKeys = []) {
  const validKeys = new Set(getTopicCatalog().map((topic) => topic.key));
  return [...new Set(topicKeys.filter((key) => validKeys.has(key)))];
}

function renderSurveyTopicsGrid() {
  topicsGrid.innerHTML = "";

  const LEVEL_LABELS = { beginner: "Базовый", intermediate: "Средний" };

  for (const group of SURVEY_TOPIC_GROUPS) {
    // Group header
    const groupHeader = document.createElement("div");
    groupHeader.className = "survey-group-header";

    const groupTitle = document.createElement("span");
    groupTitle.className = "survey-group-title";
    groupTitle.textContent = group.group;

    const groupLevel = document.createElement("span");
    groupLevel.className = `survey-group-level survey-group-level--${group.level}`;
    groupLevel.textContent = LEVEL_LABELS[group.level] || group.level;

    groupHeader.appendChild(groupTitle);
    groupHeader.appendChild(groupLevel);
    topicsGrid.appendChild(groupHeader);

    // Topic checkboxes
    for (const topic of group.topics) {
      const isChecked = onboardingState.topics.includes(topic.key);

      const label = document.createElement("label");
      label.className = `survey-topic-item ${isChecked ? "checked" : ""}`;
      label.dataset.topic = topic.key;

      const checkbox = document.createElement("input");
      checkbox.type = "checkbox";
      checkbox.className = "survey-topic-checkbox";
      checkbox.checked = isChecked;
      checkbox.dataset.topic = topic.key;

      const checkmark = document.createElement("span");
      checkmark.className = "survey-topic-checkmark";
      checkmark.innerHTML = icons.checkSmall;

      const textBlock = document.createElement("span");
      textBlock.className = "survey-topic-text";

      const titleEl = document.createElement("span");
      titleEl.className = "survey-topic-title";
      titleEl.textContent = topic.title;

      const hintEl = document.createElement("span");
      hintEl.className = "survey-topic-hint";
      hintEl.textContent = topic.hint;

      textBlock.appendChild(titleEl);
      textBlock.appendChild(hintEl);

      label.appendChild(checkbox);
      label.appendChild(checkmark);
      label.appendChild(textBlock);
      topicsGrid.appendChild(label);
    }
  }
}

/* =========================
   TOPICS
========================= */

// Stores slugs of individually completed roadmap items, e.g. "variables__hoisting"
let roadmapItemsState = new Set();

async function loadTopicsFromServer() {
  const data = await api("/topics");

  const serverTopics = Array.isArray(data.topics) && data.topics.length > 0
    ? sortTopicsByLearningOrder(data.topics)
    : sortTopicsByLearningOrder(FALLBACK_TOPICS);

  topicsState.all = serverTopics;
  topicsState.learned = Array.isArray(data.learned_topic_keys)
    ? normalizeTopicKeys(data.learned_topic_keys)
    : [];

  onboardingState.topics = normalizeTopicKeys(onboardingState.topics);

  if (shouldForceSurveyReset()) {
    renderSurveyTopicsGrid();
    return;
  }

  if (topicsState.learned.length > 0) {
    onboardingState.topics = [...topicsState.learned];
    onboardingState.completed = true;
    onboardingState.level = "returning";
    saveOnboardingState();
  }

  renderSurveyTopicsGrid();

  // Load individual roadmap item completions
  try {
    const itemData = await api("/roadmap/items");
    roadmapItemsState = new Set(Array.isArray(itemData.item_slugs) ? itemData.item_slugs : []);
  } catch {
    roadmapItemsState = new Set();
  }
}

async function saveSurveyTopicsToServer(topicKeys) {
  const normalizedKeys = normalizeTopicKeys(topicKeys);

  const data = await api("/topics/me", {
    method: "PUT",
    body: JSON.stringify({ topic_keys: normalizedKeys })
  });

  topicsState.learned = Array.isArray(data.learned_topic_keys)
    ? normalizeTopicKeys(data.learned_topic_keys)
    : [];

  onboardingState.topics = [...topicsState.learned];
  saveOnboardingState();

  // Sync chosen topics into roadmap item completions so the roadmap
  // immediately reflects what the user selected in the survey
  syncSurveyTopicsToRoadmap(normalizedKeys);

  renderSurveyTopicsGrid();
  renderTopicsManager();

  return data;
}

/**
 * For each topic key chosen in the survey, mark all roadmap items
 * belonging to nodes with that topicKey as learned in roadmapItemsState,
 * then persist to the server.
 */
function syncSurveyTopicsToRoadmap(topicKeys) {
  if (!topicKeys || topicKeys.length === 0) return;

  const keySet = new Set(topicKeys);

  // Inline roadmap definition (mirrors renderTopicsManager)
  const roadmap = [
    { nodeSlug: "intro",           topicKey: null,       items: ["Что такое JavaScript", "История JavaScript", "Версии JavaScript", "Как запускать JavaScript"] },
    { nodeSlug: "variables",       topicKey: "variables", items: ["Объявление переменных", "Hoisting", "Правила именования", "Области видимости", "var / let / const"] },
    { nodeSlug: "types",           topicKey: "variables", items: ["Примитивные типы", "Object", "typeof", "Встроенные объекты"] },
    { nodeSlug: "type_conversion", topicKey: "operators", items: ["Явное преобразование", "Неявное преобразование", "Type Conversion vs Coercion"] },
    { nodeSlug: "operators",       topicKey: "operators", items: ["Присваивание", "Сравнение", "Арифметика", "Логические операторы", "Условный оператор"] },
    { nodeSlug: "equality",        topicKey: "operators", items: ["==", "===", "Object.is", "Алгоритмы сравнения"] },
    { nodeSlug: "conditions",      topicKey: "conditions",items: ["if...else", "switch", "throw", "try / catch / finally", "Ошибки"] },
    { nodeSlug: "loops",           topicKey: "loops",     items: ["for", "while", "do...while", "for...in", "for...of", "break / continue"] },
    { nodeSlug: "functions",       topicKey: "functions", items: ["Параметры функций", "Arrow Functions", "IIFE", "arguments", "Default Params", "Rest", "Рекурсия", "Замыкания"] },
    { nodeSlug: "strings",         topicKey: "strings",   items: ["Методы строк", "Шаблонные литералы", "RegExp основы"] },
    { nodeSlug: "arrays",          topicKey: "arrays",    items: ["Методы массивов", "map / filter / reduce", "Spread / Rest", "Деструктуризация"] },
    { nodeSlug: "objects",         topicKey: "objects",   items: ["Свойства и методы", "Деструктуризация", "Spread объектов", "Object.keys / values / entries"] },
    { nodeSlug: "data_structures", topicKey: "objects",   items: ["JSON", "Map", "Set", "WeakMap / WeakSet"] },
    { nodeSlug: "dom",             topicKey: "dom",        items: ["DOM", "querySelector", "createElement", "innerHTML", "classList"] },
    { nodeSlug: "events",          topicKey: "events",    items: ["addEventListener", "Делегирование событий", "Event Bubbling", "preventDefault"] },
    { nodeSlug: "strict",          topicKey: null,        items: ["Использование strict mode"] },
    { nodeSlug: "this",            topicKey: "this",      items: ["В методах", "В функциях", "В обработчиках событий", "В arrow functions"] },
    { nodeSlug: "modules",         topicKey: "modules",   items: ["CommonJS", "ES Modules"] },
    { nodeSlug: "async",           topicKey: "async",     items: ["Event Loop", "setTimeout", "setInterval", "Callbacks", "Promises", "async / await"] },
    { nodeSlug: "api",             topicKey: "api",        items: ["Fetch API", "XMLHTTPRequest", "Обработка ошибок"] },
  ];

  for (const node of roadmap) {
    if (!node.topicKey || !keySet.has(node.topicKey)) continue;
    for (const itemText of node.items) {
      roadmapItemsState.add(makeItemSlug(node.nodeSlug, itemText));
    }
  }

  // Persist updated roadmap state
  scheduleRoadmapSave();
}

async function saveRoadmapItemsToServer() {
  try {
    await api("/roadmap/items", {
      method: "PUT",
      body: JSON.stringify({ item_slugs: [...roadmapItemsState] })
    });
  } catch (err) {
    console.error("Не удалось сохранить прогресс:", err);
  }
}

function openTopicsModal() {
  renderTopicsManager();
  topicsModal.classList.remove("hidden");
}

function closeTopicsModal() {
  topicsModal.classList.add("hidden");
}

// Redraw line segments if window is resized while roadmap is open
window.addEventListener("resize", () => {
  if (topicsModal.classList.contains("hidden")) return;
  const wrapper = topicsManagerGrid.querySelector(".roadmap-tree");
  if (!wrapper) return;
  const allNodeEls = [...wrapper.querySelectorAll(".roadmap-node")].map((el) => ({
    el,
    markerEl: el.querySelector(".roadmap-node-marker"),
    allLearned: el.classList.contains("roadmap-node--learned")
  }));
  requestAnimationFrame(() => drawRoadmapLines(wrapper, allNodeEls));
});

function makeItemSlug(nodeSlug, itemText) {
  // Create a stable slug: "variables__hoisting"
  return `${nodeSlug}__${itemText.toLowerCase().replace(/[^a-zа-яё0-9]+/gi, "_").replace(/^_|_$/g, "")}`;
}

function renderTopicsManager() {
  topicsManagerGrid.innerHTML = "";

  const roadmap = [
    { nodeSlug: "intro",            title: "Введение в JavaScript",    level: "beginner",     topicKey: null,        items: ["Что такое JavaScript", "История JavaScript", "Версии JavaScript", "Как запускать JavaScript"] },
    { nodeSlug: "variables",        title: "Переменные",               level: "beginner",     topicKey: "variables", items: ["Объявление переменных", "Hoisting", "Правила именования", "Области видимости", "var / let / const"] },
    { nodeSlug: "types",            title: "Типы данных",              level: "beginner",     topicKey: "variables", items: ["Примитивные типы", "Object", "typeof", "Встроенные объекты"] },
    { nodeSlug: "type_conversion",  title: "Преобразование типов",     level: "beginner",     topicKey: "operators", items: ["Явное преобразование", "Неявное преобразование", "Type Conversion vs Coercion"] },
    { nodeSlug: "operators",        title: "Операторы и выражения",    level: "beginner",     topicKey: "operators", items: ["Присваивание", "Сравнение", "Арифметика", "Логические операторы", "Условный оператор"] },
    { nodeSlug: "equality",         title: "Сравнение значений",       level: "beginner",     topicKey: "operators", items: ["==", "===", "Object.is", "Алгоритмы сравнения"] },
    { nodeSlug: "conditions",       title: "Условные конструкции",     level: "beginner",     topicKey: "conditions",items: ["if...else", "switch", "throw", "try / catch / finally", "Ошибки"] },
    { nodeSlug: "loops",            title: "Циклы и итерации",         level: "beginner",     topicKey: "loops",     items: ["for", "while", "do...while", "for...in", "for...of", "break / continue"] },
    { nodeSlug: "functions",        title: "Функции",                  level: "beginner",     topicKey: "functions", items: ["Параметры функций", "Arrow Functions", "IIFE", "arguments", "Default Params", "Rest", "Рекурсия", "Замыкания"] },
    { nodeSlug: "strings",          title: "Строки",                   level: "beginner",     topicKey: "strings",   items: ["Методы строк", "Шаблонные литералы", "RegExp основы"] },
    { nodeSlug: "arrays",           title: "Массивы",                  level: "beginner",     topicKey: "arrays",    items: ["Методы массивов", "map / filter / reduce", "Spread / Rest", "Деструктуризация"] },
    { nodeSlug: "objects",          title: "Объекты",                  level: "beginner",     topicKey: "objects",   items: ["Свойства и методы", "Деструктуризация", "Spread объектов", "Object.keys / values / entries"] },
    { nodeSlug: "data_structures",  title: "Структуры данных",         level: "intermediate", topicKey: "objects",   items: ["JSON", "Map", "Set", "WeakMap / WeakSet"] },
    { nodeSlug: "dom",              title: "DOM API",                  level: "intermediate", topicKey: "dom",       items: ["DOM", "querySelector", "createElement", "innerHTML", "classList"] },
    { nodeSlug: "events",           title: "События",                  level: "intermediate", topicKey: "events",    items: ["addEventListener", "Делегирование событий", "Event Bubbling", "preventDefault"] },
    { nodeSlug: "strict",           title: "Strict Mode",              level: "intermediate", topicKey: null,        items: ["Использование strict mode"] },
    { nodeSlug: "this",             title: "Ключевое слово this",      level: "intermediate", topicKey: "this",      items: ["В методах", "В функциях", "В обработчиках событий", "В arrow functions"] },
    { nodeSlug: "modules",          title: "Модули в JavaScript",      level: "intermediate", topicKey: "modules",   items: ["CommonJS", "ES Modules"] },
    { nodeSlug: "async",            title: "Асинхронный JavaScript",   level: "intermediate", topicKey: "async",     items: ["Event Loop", "setTimeout", "setInterval", "Callbacks", "Promises", "async / await"] },
    { nodeSlug: "api",              title: "Работа с API",             level: "intermediate", topicKey: "api",       items: ["Fetch API", "XMLHTTPRequest", "Обработка ошибок"] },
    { nodeSlug: "classes",          title: "Классы",                   level: "advanced",     topicKey: null,        items: ["Классы", "Прототипное наследование", "Object Prototype"] },
    { nodeSlug: "iterators",        title: "Итераторы и генераторы",   level: "advanced",     topicKey: null,        items: ["Итераторы", "Генераторы"] },
    { nodeSlug: "memory",           title: "Управление памятью",       level: "advanced",     topicKey: null,        items: ["Жизненный цикл памяти", "Garbage Collection"] },
    { nodeSlug: "devtools",         title: "Инструменты разработчика", level: "advanced",     topicKey: null,        items: ["Отладка ошибок", "Отладка утечек памяти", "Анализ производительности"] }
  ];

  // ── Progress bar (rendered into the separate fixed header element) ──
  const totalItems = roadmap.reduce((s, n) => s + n.items.length, 0);
  const learnedItemsCount = roadmap.reduce((s, n) =>
    s + n.items.filter((item) => roadmapItemsState.has(makeItemSlug(n.nodeSlug, item))).length, 0);
  const progressPct = totalItems > 0 ? Math.ceil((learnedItemsCount / totalItems) * 100) : 0;

  topicsProgressHeader.innerHTML = `
    <div class="roadmap-progress-text">
      <span class="roadmap-progress-label">Прогресс</span>
      <span class="roadmap-progress-fraction">${progressPct}%</span>
    </div>
    <div class="roadmap-progress-bar-wrap">
      <div class="roadmap-progress-bar-fill" style="width: ${progressPct}%" data-progress="${progressPct}"></div>
    </div>
  `;

  // ── Build node state array ──
  const nodeStates = roadmap.map((section) => {
    const allSlugs = section.items.map((item) => makeItemSlug(section.nodeSlug, item));
    const learnedCount = allSlugs.filter((s) => roadmapItemsState.has(s)).length;
    return {
      allLearned: learnedCount === section.items.length,
      someLearned: learnedCount > 0 && learnedCount < section.items.length
    };
  });

  // ── Wrapper ──
  const wrapper = document.createElement("div");
  wrapper.className = "roadmap-tree";

  // ── Draw line segments between nodes ──
  // We'll insert them after nodes are in the DOM via requestAnimationFrame
  const nodeEls = [];

  roadmap.forEach((section, index) => {
    const { allLearned, someLearned } = nodeStates[index];

    const node = document.createElement("section");
    node.className = [
      "roadmap-node",
      `roadmap-node-${section.level}`,
      allLearned ? "roadmap-node--learned" : "",
      someLearned ? "roadmap-node--partial" : ""
    ].filter(Boolean).join(" ");

    // ── Marker: checkmark if all done, else just the number ──
    const marker = document.createElement("div");
    marker.className = "roadmap-node-marker";
    if (allLearned) {
      marker.innerHTML = icons.checkLarge;
    } else {
      marker.textContent = index + 1;
    }

    // ── Card ──
    const card = document.createElement("div");
    card.className = "roadmap-node-card";

    const topRow = document.createElement("div");
    topRow.className = "roadmap-node-top";

    const titleEl = document.createElement("h3");
    titleEl.textContent = section.title;
    if (authUser) {
      titleEl.classList.add("roadmap-node-title--clickable");
      titleEl.title = allLearned ? "Снять все отметки" : "Отметить всё в этом блоке";
      titleEl.addEventListener("click", () => toggleNodeAllItems(section.nodeSlug, section.items, allLearned));
    }

    const levelBadge = document.createElement("span");
    levelBadge.className = "roadmap-level";
    levelBadge.textContent = getRoadmapLevelLabel(section.level);

    topRow.appendChild(titleEl);
    topRow.appendChild(levelBadge);

    // ── Items ──
    const itemsDiv = document.createElement("div");
    itemsDiv.className = "roadmap-items";
    section.items.forEach((itemText) => {
      const slug = makeItemSlug(section.nodeSlug, itemText);
      const isItemLearned = roadmapItemsState.has(slug);
      const span = document.createElement("span");
      span.textContent = itemText;
      if (isItemLearned) span.classList.add("roadmap-item--learned");
      if (authUser) {
        span.classList.add("roadmap-item--clickable");
        span.title = isItemLearned ? "Снять отметку" : "Отметить как изученное";
        span.addEventListener("click", () => toggleSingleItem(slug, span, section.nodeSlug, section.items, node, marker, index));
      }
      itemsDiv.appendChild(span);
    });

    card.appendChild(topRow);
    card.appendChild(itemsDiv);
    node.appendChild(marker);
    node.appendChild(card);
    wrapper.appendChild(node);
    nodeEls.push({ el: node, markerEl: marker, allLearned });
  });

  topicsManagerGrid.appendChild(wrapper);

  // ── Draw line segments after layout ──
  requestAnimationFrame(() => drawRoadmapLines(wrapper, nodeEls));
}

function drawRoadmapLines(wrapper, nodeEls) {
  // Remove old segments
  wrapper.querySelectorAll(".roadmap-line-segment").forEach((el) => el.remove());

  const wrapperRect = wrapper.getBoundingClientRect();

  for (let i = 0; i < nodeEls.length - 1; i++) {
    const fromMarker = nodeEls[i].markerEl;
    const toMarker   = nodeEls[i + 1].markerEl;

    const fromRect = fromMarker.getBoundingClientRect();
    const toRect   = toMarker.getBoundingClientRect();

    // Segment starts at the bottom edge of the current marker
    const segTop = fromRect.bottom - wrapperRect.top;

    // If current node is learned → green line that reaches INTO the next marker
    // (to toRect.bottom). If next node is not yet learned, stop at toRect.top.
    const currentLearned = nodeEls[i].allLearned;
    const nextLearned    = nodeEls[i + 1].allLearned;

    const segBottom = currentLearned && nextLearned
      ? toRect.bottom - wrapperRect.top   // fully through the next circle
      : currentLearned
        ? toRect.bottom - wrapperRect.top // still draw through — visually cleaner
        : toRect.top - wrapperRect.top;   // stop before the next circle

    const segHeight = segBottom - segTop;
    if (segHeight <= 0) continue;

    const seg = document.createElement("div");
    seg.className = `roadmap-line-segment ${currentLearned ? "roadmap-line-segment--learned" : "roadmap-line-segment--default"}`;
    seg.style.top    = `${segTop}px`;
    seg.style.height = `${segHeight}px`;
    wrapper.appendChild(seg);
  }
}

let roadmapSaveTimer = null;

function scheduleRoadmapSave() {
  clearTimeout(roadmapSaveTimer);
  roadmapSaveTimer = setTimeout(() => saveRoadmapItemsToServer(), 800);
}

function toggleSingleItem(slug, spanEl, nodeSlug, nodeItems, nodeEl, markerEl, nodeIndex) {
  if (roadmapItemsState.has(slug)) {
    roadmapItemsState.delete(slug);
    spanEl.classList.remove("roadmap-item--learned");
    spanEl.title = "Отметить как изученное";
  } else {
    roadmapItemsState.add(slug);
    spanEl.classList.add("roadmap-item--learned");
    spanEl.title = "Снять отметку";
  }

  const allSlugs = nodeItems.map((t) => makeItemSlug(nodeSlug, t));
  const learnedCount = allSlugs.filter((s) => roadmapItemsState.has(s)).length;
  const allLearned = learnedCount === nodeItems.length;
  const someLearned = learnedCount > 0 && !allLearned;

  nodeEl.classList.toggle("roadmap-node--learned", allLearned);
  nodeEl.classList.toggle("roadmap-node--partial", someLearned);

  if (allLearned) {
    markerEl.innerHTML = icons.checkLarge;
  } else {
    markerEl.textContent = nodeIndex + 1;
  }

  // Redraw lines
  const wrapper = nodeEl.closest(".roadmap-tree");
  if (wrapper) {
    const allNodeEls = [...wrapper.querySelectorAll(".roadmap-node")].map((el) => ({
      el,
      markerEl: el.querySelector(".roadmap-node-marker"),
      allLearned: el.classList.contains("roadmap-node--learned")
    }));
    requestAnimationFrame(() => drawRoadmapLines(wrapper, allNodeEls));
  }

  updateRoadmapProgressHeader();
  scheduleRoadmapSave();
}

function toggleNodeAllItems(nodeSlug, nodeItems, currentlyAllLearned) {
  const allSlugs = nodeItems.map((t) => makeItemSlug(nodeSlug, t));

  // Capture current progress before re-render for animation
  const fillElBefore = topicsProgressHeader.querySelector(".roadmap-progress-bar-fill");
  const prevPct = fillElBefore ? (parseFloat(fillElBefore.dataset.progress || fillElBefore.style.width) || 0) : 0;

  if (currentlyAllLearned) {
    allSlugs.forEach((s) => roadmapItemsState.delete(s));
  } else {
    allSlugs.forEach((s) => roadmapItemsState.add(s));
  }
  renderTopicsManager();
  scheduleRoadmapSave();

  // Animate progress bar after re-render
  const fillElAfter = topicsProgressHeader.querySelector(".roadmap-progress-bar-fill");
  const fracEl = topicsProgressHeader.querySelector(".roadmap-progress-fraction");
  if (fillElAfter) {
    const newPct = parseFloat(fillElAfter.dataset.progress || fillElAfter.style.width) || 0;
    fillElAfter.style.width = `${prevPct}%`;
    animateProgressBar(fillElAfter, prevPct, newPct, fracEl);
  }
}

function updateRoadmapProgressHeader(animate = false) {
  const fracEl = topicsProgressHeader.querySelector(".roadmap-progress-fraction");
  const fillEl = topicsProgressHeader.querySelector(".roadmap-progress-bar-fill");
  if (!fracEl || !fillEl) return;

  const allSpans = topicsManagerGrid.querySelectorAll(".roadmap-items span");
  const total = allSpans.length;
  const learned = topicsManagerGrid.querySelectorAll(".roadmap-items .roadmap-item--learned").length;
  const pct = total > 0 ? Math.ceil((learned / total) * 100) : 0;

  fracEl.textContent = `${pct}%`;

  if (animate) {
    const prevPct = parseFloat(fillEl.dataset.progress || fillEl.style.width) || 0;
    fillEl.dataset.progress = pct;
    animateProgressBar(fillEl, prevPct, pct, fracEl);
  } else {
    fillEl.dataset.progress = pct;
  fillEl.style.width = `${pct}%`;
  }
}

function animateProgressBar(fillEl, fromPct, toPct, fracEl) {
  const duration = 600;
  const startTime = performance.now();
  const delta = toPct - fromPct;

  function step(now) {
    const elapsed = now - startTime;
    const progress = Math.min(elapsed / duration, 1);
    const eased = 1 - Math.pow(1 - progress, 3);
    const current = fromPct + delta * eased;
    fillEl.style.width = `${current}%`;
    if (fracEl) fracEl.textContent = `${Math.ceil(current)}%`;
    if (progress < 1) {
      requestAnimationFrame(step);
    } else {
      if (fracEl) fracEl.textContent = `${toPct}%`;
    }
  }

  requestAnimationFrame(step);
}

function getRoadmapLevelLabel(level) {
  const labels = { beginner: "Начальный", intermediate: "Средний", advanced: "Продвинутый" };
  return labels[level] || "Тема";
}

/* =========================
   AUTH
========================= */
async function checkAuthOnMain() {
  try {
    const response = await fetch("/users/me", {
      credentials: "include"
    });

    if (!response.ok) {
      setUnauthorizedState();
      return false;
    }

    const user = await response.json();
    setAuthorizedState(user);
    return true;
  } catch (error) {
    console.error("Auth check error:", error);
    setUnauthorizedState();
    return false;
  }
}

async function logout() {
  const confirmed = window.confirm("Вы точно хотите выйти?");
  if (!confirmed) return;

  try {
    await fetch("/auth/jwt/logout", {
      method: "POST",
      credentials: "include"
    });
  } catch (error) {
    console.error("Logout error:", error);
  } finally {
    chats = {};
    currentChatId = null;
    roadmapItemsState = new Set();
    topicsState = { all: sortTopicsByLearningOrder([...FALLBACK_TOPICS]), learned: [] };
    onboardingState = {
      completed: false,
      level: null,
      topics: []
    };
    saveOnboardingState();
    saveCurrentChatId();
    renderSurveyTopicsGrid();
    startDraftChat(false);
    render();
    setUnauthorizedState();
  }
}

async function handleLoginSubmit(event) {
  event.preventDefault();
  hideAuthMessage();

  const email = document.getElementById("loginEmail").value.trim();
  const password = document.getElementById("loginPassword").value;

  const submitBtn = event.target.querySelector('button[type="submit"]');
  const textEl = submitBtn.querySelector(".button-text");
  const originalText = textEl.textContent;

  textEl.textContent = "Вход...";
  submitBtn.disabled = true;

  try {
    const response = await fetch("/auth/jwt/login", {
      method: "POST",
      headers: {
        "Content-Type": "application/x-www-form-urlencoded"
      },
      body: new URLSearchParams({
        username: email,
        password
      }),
      credentials: "include"
    });

    const data = await response.json().catch(() => ({}));

    if (!response.ok) {
      throw new Error(data.detail || "Ошибка входа. Проверьте email и пароль.");
    }

    const ok = await checkAuthOnMain();
    if (ok) {
      await loadTopicsFromServer();
      await loadChatsFromServer();
      render();
    }
  } catch (error) {
    showAuthMessage(error.message || "Ошибка входа", "error");
  } finally {
    textEl.textContent = originalText;
    submitBtn.disabled = false;
  }
}

async function handleRegisterSubmit(event) {
  event.preventDefault();
  hideAuthMessage();

  const email = document.getElementById("registerEmail").value.trim();
  const password = document.getElementById("registerPassword").value;

  if (password.length < 6) {
    showAuthMessage("Пароль должен содержать минимум 6 символов", "error");
    return;
  }

  const submitBtn = event.target.querySelector('button[type="submit"]');
  const textEl = submitBtn.querySelector(".button-text");
  const originalText = textEl.textContent;

  textEl.textContent = "Создание...";
  submitBtn.disabled = true;

  try {
    const response = await fetch("/auth/register", {
      method: "POST",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify({ email, password }),
      credentials: "include"
    });

    const data = await response.json().catch(() => ({}));

    if (!response.ok) {
      throw new Error(data.detail || "Ошибка регистрации. Возможно, email уже используется.");
    }

    showAuthMessage("Регистрация успешна. Теперь войдите в аккаунт.", "success");
    setAuthView("login");
    document.getElementById("loginEmail").value = email;
    document.getElementById("registerEmail").value = "";
    document.getElementById("registerPassword").value = "";
  } catch (error) {
    showAuthMessage(error.message || "Ошибка регистрации", "error");
  } finally {
    textEl.textContent = originalText;
    submitBtn.disabled = false;
  }
}

async function handleResetSubmit(event) {
  event.preventDefault();
  hideAuthMessage();

  const email = document.getElementById("resetEmail").value.trim();
  const newPassword = document.getElementById("resetNewPassword").value;
  const confirmPassword = document.getElementById("resetConfirmPassword").value;

  if (newPassword !== confirmPassword) {
    showAuthMessage("Пароли не совпадают", "error");
    return;
  }

  if (newPassword.length < 6) {
    showAuthMessage("Пароль должен содержать минимум 6 символов", "error");
    return;
  }

  const submitBtn = event.target.querySelector('button[type="submit"]');
  const textEl = submitBtn.querySelector(".button-text");
  const originalText = textEl.textContent;

  textEl.textContent = "Сброс...";
  submitBtn.disabled = true;

  try {
    const response = await fetch("/auth/simple-reset-password", {
      method: "POST",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify({
        email,
        new_password: newPassword
      }),
      credentials: "include"
    });

    const data = await response.json().catch(() => ({}));

    if (!response.ok) {
      throw new Error(data.detail || "Ошибка сброса пароля");
    }

    showAuthMessage(`✅ ${data.message}`, "success");

    document.getElementById("resetEmail").value = "";
    document.getElementById("resetNewPassword").value = "";
    document.getElementById("resetConfirmPassword").value = "";

    setTimeout(() => {
      setAuthView("login");
      showAuthMessage("Теперь вы можете войти с новым паролем", "success");
    }, 1200);
  } catch (error) {
    showAuthMessage(error.message || "Ошибка сброса пароля", "error");
  } finally {
    textEl.textContent = originalText;
    submitBtn.disabled = false;
  }
}

/* =========================
   THINKING BUBBLE
========================= */
function showThinkingBubble(chatId) {
  thinkingState.chatId = chatId;
  thinkingState.isActive = true;
  render();
  scrollMessagesToBottom(true);
}

function hideThinkingBubble() {
  thinkingState.chatId = null;
  thinkingState.isActive = false;
  render();
}

/* =========================
   TITLE TYPING ANIMATION
========================= */
function clearTitleTyping(chatId) {
  const timer = titleTypingState.timers.get(chatId);

  if (timer) {
    clearTimeout(timer);
    titleTypingState.timers.delete(chatId);
  }

  if (titleTypingState.activeChatId === chatId) {
    titleTypingState.activeChatId = null;
  }
}

function clearAllTitleTyping() {
  for (const [chatId, timer] of titleTypingState.timers.entries()) {
    clearTimeout(timer);
    titleTypingState.timers.delete(chatId);
  }

  titleTypingState.activeChatId = null;
}

function renderTypingTitleChunk(chatId, fullTitle, visibleLength) {
  const titleEl = chatListEl.querySelector(`[data-chat-title-id="${chatId}"]`);
  if (!titleEl) return;

  const visibleText = fullTitle.slice(0, visibleLength);
  titleEl.innerHTML =
    `<span class="chat-title-text">${escapeHtml(visibleText)}</span>` +
    `<span class="chat-title-caret"></span>`;
}

function finalizeTypingTitle(chatId, fullTitle) {
  const titleEl = chatListEl.querySelector(`[data-chat-title-id="${chatId}"]`);
  if (!titleEl) return;

  titleEl.textContent = fullTitle;
  clearTitleTyping(chatId);
}

function animateChatTitle(chatId, fullTitle) {
  clearTitleTyping(chatId);
  titleTypingState.activeChatId = chatId;

  let index = 0;

  function step() {
    const chat = chats[chatId];
    if (!chat) {
      clearTitleTyping(chatId);
      return;
    }

    index += 1;
    renderTypingTitleChunk(chatId, fullTitle, index);

    if (index >= fullTitle.length) {
      finalizeTypingTitle(chatId, fullTitle);
      return;
    }

    const timer = setTimeout(step, TITLE_TYPING_DELAY_MS);
    titleTypingState.timers.set(chatId, timer);
  }

  renderTypingTitleChunk(chatId, fullTitle, 0);
  const timer = setTimeout(step, TITLE_TYPING_DELAY_MS);
  titleTypingState.timers.set(chatId, timer);
}

function maybeAnimateGeneratedTitle(chatId, previousTitle, nextTitle) {
  const normalizedPrev = (previousTitle || "").trim();
  const normalizedNext = (nextTitle || "").trim();

  if (!chatId || !normalizedNext) return;
  if (normalizedPrev !== "Новый чат") return;
  if (normalizedNext === "Новый чат") return;

  render();
  animateChatTitle(chatId, normalizedNext);
}

/* =========================
   ASSISTANT TYPING ANIMATION
========================= */
function clearAssistantTyping() {
  if (assistantTypingState.timer) {
    clearTimeout(assistantTypingState.timer);
  }

  assistantTypingState.chatId = null;
  assistantTypingState.messageIndex = null;
  assistantTypingState.timer = null;
  assistantTypingState.fullText = "";
  assistantTypingState.currentText = "";
  assistantTypingState.isActive = false;
}

function renderAssistantTypingFrame() {
  if (!assistantTypingState.isActive) return;
  if (assistantTypingState.chatId !== currentChatId) return;

  const row = messagesDiv.querySelector(
    `[data-assistant-message-index="${assistantTypingState.messageIndex}"]`
  );
  if (!row) return;

  const bubble = row.querySelector(".message.bot");
  if (!bubble) return;

  const safeText = escapeHtml(assistantTypingState.currentText).replaceAll("\n", "<br>");
  bubble.innerHTML = `${safeText}<span class="assistant-typing-caret"></span>`;
  scrollMessagesToBottom();
}

function finalizeAssistantTyping() {
  const currentChat = chats[assistantTypingState.chatId];

  if (!currentChat) {
    clearAssistantTyping();
    return;
  }

  const message = currentChat.messages[assistantTypingState.messageIndex];

  if (!message) {
    clearAssistantTyping();
    return;
  }

  if (assistantTypingState.chatId === currentChatId) {
    const row = messagesDiv.querySelector(
      `[data-assistant-message-index="${assistantTypingState.messageIndex}"]`
    );

    if (row) {
      const bubble = row.querySelector(".message.bot");

      if (bubble) {
        if (window.marked) {
          bubble.innerHTML = marked.parse(message.content);
          addCopyButtons(bubble);
        } else {
          bubble.textContent = message.content;
        }
      }
    }
  }

  clearAssistantTyping();
  scrollMessagesToBottom();
}

function startAssistantTyping(chatId, messageIndex, fullText) {
  clearAssistantTyping();

  assistantTypingState.chatId = chatId;
  assistantTypingState.messageIndex = messageIndex;
  assistantTypingState.fullText = fullText || "";
  assistantTypingState.currentText = "";
  assistantTypingState.isActive = true;

  let charIndex = 0;

  function step() {
    if (!assistantTypingState.isActive) return;

    const activeChat = chats[chatId];
    if (!activeChat) {
      clearAssistantTyping();
      return;
    }

    charIndex += 1;
    assistantTypingState.currentText = assistantTypingState.fullText.slice(0, charIndex);
    renderAssistantTypingFrame();

    if (charIndex >= assistantTypingState.fullText.length) {
      finalizeAssistantTyping();
      return;
    }

    assistantTypingState.timer = setTimeout(step, ASSISTANT_TYPING_DELAY_MS);
  }

  render();
  renderAssistantTypingFrame();
  assistantTypingState.timer = setTimeout(step, ASSISTANT_TYPING_DELAY_MS);
}

/* =========================
   UI BASICS
========================= */
function setupIcons() {
  sidebarToggle.innerHTML = icons.menu;
  sendBtn.innerHTML = icons.send;
  themeBtn.innerHTML = icons.sun;
  guideBtn.innerHTML = icons.help;
  userMenuBtn.innerHTML = icons.user;
  contextRenameBtn.innerHTML = `${icons.rename} <span>Переименовать</span>`;
  contextDeleteBtn.innerHTML = `${icons.delete} <span>Удалить</span>`;
  const githubBtn = document.getElementById("githubBtn");
  if (githubBtn) githubBtn.innerHTML = icons.github;
}

function applyTheme(theme) {
  document.documentElement.setAttribute("data-theme", theme);
  localStorage.setItem("theme", theme);
  themeBtn.innerHTML = theme === "dark" ? icons.sun : icons.moon;
}

applyTheme(localStorage.getItem("theme") || "dark");
setupIcons();
resetTextareaHeight();
renderSurveyTopicsGrid();

themeBtn.addEventListener("click", () => {
  const currentTheme = document.documentElement.getAttribute("data-theme");

  themeBtn.classList.remove("theme-spin");
  void themeBtn.offsetWidth;
  themeBtn.classList.add("theme-spin");

  applyTheme(currentTheme === "dark" ? "light" : "dark");
});

themeBtn.addEventListener("animationend", () => {
  themeBtn.classList.remove("theme-spin");
});

sidebarToggle.addEventListener("click", () => {
  sidebar.classList.toggle("collapsed");
  hideContextMenu();
  userDropdown.classList.add("hidden");
});

chatArea.addEventListener("wheel", () => {
  userScrolling = true;
  clearTimeout(userScrollingTimer);
  userScrollingTimer = setTimeout(() => {
    userScrolling = false;
  }, 1200);
}, { passive: true });

newChatBtn.addEventListener("click", () => {
  startDraftChat();
  if (canUseChat()) {
    input.focus();
  }
});

document.addEventListener("click", (e) => {
  const clickedInsideContext = contextMenu.contains(e.target);
  if (!clickedInsideContext) {
    hideContextMenu();
  }

  const clickedInsideUserMenu =
    userMenuBtn.contains(e.target) || userDropdown.contains(e.target);

  if (!clickedInsideUserMenu) {
    userDropdown.classList.add("hidden");
  }
});

window.addEventListener("resize", () => {
  hideContextMenu();
  userDropdown.classList.add("hidden");
});

window.addEventListener("scroll", () => {
  hideContextMenu();
  userDropdown.classList.add("hidden");
}, true);

// Flush any pending roadmap save immediately when the tab is closed/hidden
// so progress isn't lost if the user closes within the 800ms debounce window
window.addEventListener("beforeunload", () => {
  if (roadmapSaveTimer !== null && authUser) {
    clearTimeout(roadmapSaveTimer);
    roadmapSaveTimer = null;
    const payload = JSON.stringify({ item_slugs: [...roadmapItemsState] });
    navigator.sendBeacon("/roadmap/items", new Blob([payload], { type: "application/json" }));
  }
});

document.addEventListener("visibilitychange", () => {
  if (document.visibilityState === "hidden" && roadmapSaveTimer !== null && authUser) {
    clearTimeout(roadmapSaveTimer);
    roadmapSaveTimer = null;
    saveRoadmapItemsToServer();
  }
});

renameCloseBtn.addEventListener("click", closeRenameModal);
renameCancelBtn.addEventListener("click", closeRenameModal);

topicsCloseBtn.addEventListener("click", closeTopicsModal);

topicsModal.addEventListener("click", (e) => {
  if (e.target === topicsModal) {
    closeTopicsModal();
  }
});

// Guide
guideBtn.addEventListener("click", () => {
  guideModal.classList.remove("hidden");
});

guideCloseBtn.addEventListener("click", () => {
  guideModal.classList.add("hidden");
});

guideModal.addEventListener("click", (e) => {
  if (e.target === guideModal) {
    guideModal.classList.add("hidden");
  }
});

document.getElementById("guideNav").addEventListener("click", (e) => {
  const btn = e.target.closest(".guide-nav-item");
  if (!btn) return;
  const key = btn.dataset.guide;

  document.querySelectorAll(".guide-nav-item").forEach((b) => b.classList.remove("active"));
  document.querySelectorAll(".guide-section").forEach((s) => s.classList.remove("active"));

  btn.classList.add("active");
  document.querySelector(`.guide-section[data-guide="${key}"]`).classList.add("active");
});

renameModal.addEventListener("click", (e) => {
  if (e.target === renameModal) {
    closeRenameModal();
  }
});

document.addEventListener("keydown", (e) => {
  if (e.key === "Escape") {
    if (!renameModal.classList.contains("hidden")) {
      closeRenameModal();
    }
    if (!topicsModal.classList.contains("hidden")) {
      closeTopicsModal();
    }
    hideContextMenu();
    userDropdown.classList.add("hidden");
  }
});

input.addEventListener("input", autoResizeTextarea);

input.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && e.shiftKey) return;

  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    form.requestSubmit();
  }
});

userMenuBtn.addEventListener("click", (e) => {
  e.stopPropagation();
  userDropdown.classList.toggle("hidden");
});

topicsDropdownBtn.addEventListener("click", () => {
  userDropdown.classList.add("hidden");
  openTopicsModal();
});

devResetSurveyBtn.addEventListener("click", () => {
  resetSurveyForDev();
});

logoutBtn.addEventListener("click", logout);

authTabs.forEach((tab) => {
  tab.addEventListener("click", () => {
    setAuthView(tab.dataset.authTab);
  });
});

forgotPasswordBtn.addEventListener("click", () => setAuthView("reset"));

loginAuthForm.addEventListener("submit", handleLoginSubmit);
registerAuthForm.addEventListener("submit", handleRegisterSubmit);
resetAuthForm.addEventListener("submit", handleResetSubmit);

renameForm.addEventListener("submit", async (e) => {
  e.preventDefault();

  if (!renameTargetChatId || !chats[renameTargetChatId]) {
    closeRenameModal();
    return;
  }

  const newTitle = renameInput.value.trim();
  if (!newTitle) return;

  if (renameTargetChatId === DRAFT_CHAT_ID) {
    chats[renameTargetChatId].title = newTitle;
    clearTitleTyping(renameTargetChatId);
    render();
    closeRenameModal();
    return;
  }

  try {
    const updatedChat = await api(`/chats/${renameTargetChatId}/title`, {
      method: "PATCH",
      body: JSON.stringify({ title: newTitle })
    });

    chats[renameTargetChatId] = {
      ...chats[renameTargetChatId],
      ...updatedChat
    };

    clearTitleTyping(renameTargetChatId);
    render();
    closeRenameModal();
  } catch (err) {
    alert(err.message || "Не удалось переименовать чат");
  }
});

contextRenameBtn.addEventListener("click", () => {
  if (!activeMenuChatId) return;

  const chatId = activeMenuChatId;
  hideContextMenu();
  openRenameModal(chatId);
});

contextDeleteBtn.addEventListener("click", async () => {
  if (!activeMenuChatId) return;

  const chatId = activeMenuChatId;
  hideContextMenu();
  await deleteChat(chatId);
});

form.addEventListener("submit", async (e) => {
  e.preventDefault();

  if (isSending) return;

  if (!authUser) {
    openAuthOverlay("login");
    return;
  }

  if (!canUseChat()) {
    openSurveyModal();
    return;
  }

  const text = input.value.trim();
  if (!text) return;

  let currentChat = getCurrentChat();

  if (!currentChat) {
    startDraftChat();
    currentChat = getCurrentChat();
  }

  currentChat.messages.push({
    role: "user",
    content: text
  });

  input.value = "";
  resetTextareaHeight();
  render();
  setSendingState(true);
  showThinkingBubble(currentChatId);
  scrollMessagesToBottom(true);

  try {
    const previousDraftTitle = currentChat.title || "Новый чат";

    const data = await api("/chat", {
      method: "POST",
      body: JSON.stringify({
        chat_id: currentChatId === DRAFT_CHAT_ID ? null : currentChatId,
        messages: currentChat.messages
      })
    });

    hideThinkingBubble();

    if (currentChatId === DRAFT_CHAT_ID) {
      delete chats[DRAFT_CHAT_ID];
      clearTitleTyping(DRAFT_CHAT_ID);
    }

    chats[data.chat_id] = {
      chat_id: data.chat_id,
      title: data.title || previousDraftTitle,
      created_at: data.created_at,
      updated_at: data.updated_at,
      messages: data.messages
    };

    currentChatId = data.chat_id;
    saveCurrentChatId();

    render();
    scrollMessagesToBottom(true);
    maybeAnimateGeneratedTitle(data.chat_id, previousDraftTitle, data.title);

    const lastMessageIndex = chats[data.chat_id].messages.length - 1;
    const lastMessage = chats[data.chat_id].messages[lastMessageIndex];

    if (lastMessage && lastMessage.role === "assistant") {
      // Record streak only for supported answers
      const isUnsupported = /не могу|не отвечаю|не поддерживается|unsupported|вне моей|не в моей компетенции/i.test(lastMessage.content);
      if (!isUnsupported) {
        const wasActive = getStreakDisplayState().active;
        recordStreakActivity();
        const isNowActive = getStreakDisplayState().active;
        // Animate only when streak counter actually changes (new day)
        renderStreakWidget(!wasActive && isNowActive);
      }

      startAssistantTyping(data.chat_id, lastMessageIndex, lastMessage.content);
    }
  } catch (err) {
    hideThinkingBubble();

    const fallbackChat = getCurrentChat();
    if (fallbackChat) {
      fallbackChat.messages.push({
        role: "assistant",
        content: "Ошибка подключения к серверу."
      });
    }

    render();
    scrollMessagesToBottom(true);
  } finally {
    setSendingState(false);
  }
});

/* =========================
   ONBOARDING / SURVEY
========================= */

// Step 1: level selection
levelBeginnerBtn.addEventListener("click", () => {
  if (onboardingState.level === "beginner") {
    // Deselect
    onboardingState.level = null;
    levelBeginnerBtn.classList.remove("active");
    surveyStep1NextBtn.disabled = true;
  } else {
  onboardingState.level = "beginner";
  levelBeginnerBtn.classList.add("active");
  levelReturningBtn.classList.remove("active");
  surveyStep1NextBtn.disabled = false;
  }
});

levelReturningBtn.addEventListener("click", () => {
  if (onboardingState.level === "returning") {
    // Deselect
    onboardingState.level = null;
    levelReturningBtn.classList.remove("active");
    surveyStep1NextBtn.disabled = true;
  } else {
  onboardingState.level = "returning";
  levelReturningBtn.classList.add("active");
  levelBeginnerBtn.classList.remove("active");
  surveyStep1NextBtn.disabled = false;
  }
});

// Step 1 → Step 2 (or finish directly for beginners)
surveyStep1NextBtn.addEventListener("click", () => {
  if (!onboardingState.level) return;

  if (onboardingState.level === "beginner") {
    // Beginners have nothing to select — finish immediately with empty topics
    onboardingState.topics = [];
    finishSurvey([]);
    return;
  }

  // Returning users go to step 2 to select known topics
  const step2Title = surveyStep2.querySelector("h2");
  const step2Subtitle = surveyStep2.querySelector(".survey-subtitle");

  if (onboardingState.level === "beginner") {
    if (step2Title) step2Title.textContent = "Что планируете изучить?";
    if (step2Subtitle) step2Subtitle.textContent = "Отметьте темы, которые хотите пройти. Это обновит ваш прогресс в дорожной карте.";
    // Clear pre-selected topics for fresh beginners
    if (onboardingState.topics.length === 0) {
      onboardingState.topics = [];
    }
  } else {
    if (step2Title) step2Title.textContent = "Какие темы вам уже знакомы?";
    if (step2Subtitle) step2Subtitle.textContent = "Отметьте всё, что вы уже знаете. Это обновит ваш прогресс в дорожной карте.";
  }

  surveyStep1.classList.add("hidden");
  surveyStep2.classList.remove("hidden");
  surveyProgressBar.style.width = "100%";
  renderSurveyTopicsGrid();
});

// Step 2 → Step 1 (back)
surveyBackBtn.addEventListener("click", () => {
  surveyStep2.classList.add("hidden");
  surveyStep1.classList.remove("hidden");
  surveyProgressBar.style.width = "50%";
});

// Topic checkbox toggle in survey
topicsGrid.addEventListener("change", (e) => {
  const checkbox = e.target.closest(".survey-topic-checkbox");
  if (!checkbox) return;

  const topic = checkbox.dataset.topic;
  if (!topic) return;

  const label = checkbox.closest(".survey-topic-item");

  if (checkbox.checked) {
    if (!onboardingState.topics.includes(topic)) {
      onboardingState.topics.push(topic);
    }
    label?.classList.add("checked");
  } else {
    onboardingState.topics = onboardingState.topics.filter((k) => k !== topic);
    label?.classList.remove("checked");
  }
});

// Finish survey (step 2 continue)
surveyContinueBtn.addEventListener("click", async () => {
  finishSurvey(onboardingState.topics);
});

async function finishSurvey(selectedTopics) {
  onboardingState.completed = true;
  onboardingState.topics = normalizeTopicKeys(selectedTopics);
  saveOnboardingState();

  try {
    if (authUser) {
      await saveSurveyTopicsToServer(onboardingState.topics);
      localStorage.removeItem(DEV_FORCE_SURVEY_RESET_KEY);
    }

    closeSurveyModal();
    updateChatAvailability();
    renderTopicsManager();

    if (authUser) {
      input.focus();
    }
  } catch (error) {
    alert(error.message || "Не удалось сохранить темы");
  }
}

function canUseChat() {
  return Boolean(onboardingState.completed);
}

function saveOnboardingState() {
  localStorage.setItem(ONBOARDING_STORAGE_KEY, JSON.stringify(onboardingState));
}

function openSurveyModal() {
  surveyModal.classList.remove("hidden");
  updateSurveyUI();
}

function closeSurveyModal() {
  surveyModal.classList.add("hidden");
}

function updateSurveyUI() {
  // Reset to step 1
  surveyStep1.classList.remove("hidden");
  surveyStep2.classList.add("hidden");
  surveyProgressBar.style.width = "50%";

  const isBeginner = onboardingState.level === "beginner";
  const isReturning = onboardingState.level === "returning";

  levelBeginnerBtn.classList.toggle("active", isBeginner);
  levelReturningBtn.classList.toggle("active", isReturning);
  surveyStep1NextBtn.disabled = !onboardingState.level;
}

function updateChatAvailability() {
  const lockedBySurvey = !canUseChat();
  const lockedByAuth = !authUser;
  const locked = lockedBySurvey || lockedByAuth;

  input.disabled = locked || isSending;
  sendBtn.disabled = locked || isSending;
  newChatBtn.disabled = lockedByAuth;
  form.classList.toggle("is-locked", locked);

  if (lockedByAuth) {
    input.placeholder = "Войдите или зарегистрируйтесь, чтобы начать работу";
  } else if (lockedBySurvey) {
    input.placeholder = "Сначала пройдите опрос перед началом работы";
  } else {
    input.placeholder = "Спросите что-нибудь...";
  }
}

/* =========================
   CHAT STORAGE / SERVER SYNC
========================= */
async function loadChatsFromServer() {
  const data = await api("/chats");
  const list = data.chats || [];

  chats = {};
  clearAllTitleTyping();
  clearAssistantTyping();
  hideThinkingBubble();

  for (const chat of list) {
    chats[chat.chat_id] = {
      ...chat,
      messages: []
    };
  }

  const chatIds = Object.keys(chats);

  if (chatIds.length === 0) {
    startDraftChat(false);
    return;
  }

  if (!currentChatId || !chats[currentChatId]) {
    currentChatId = chatIds[0];
    saveCurrentChatId();
  }

  await loadChatById(currentChatId);
}

async function loadChatById(chatId) {
  clearAssistantTyping();
  hideThinkingBubble();

  if (chatId === DRAFT_CHAT_ID) {
    currentChatId = DRAFT_CHAT_ID;
    saveCurrentChatId();
    render();
    return;
  }

  const fullChat = await api(`/chats/${chatId}`);
  chats[chatId] = { ...fullChat };
  currentChatId = chatId;
  saveCurrentChatId();
  render();
  scrollMessagesToBottom(true);
}

function startDraftChat(shouldRender = true) {
  ensureDraftChat();
  clearTitleTyping(DRAFT_CHAT_ID);
  clearAssistantTyping();
  hideThinkingBubble();

  chats[DRAFT_CHAT_ID] = {
    chat_id: null,
    title: "Новый чат",
    created_at: null,
    updated_at: new Date().toISOString(),
    messages: []
  };

  currentChatId = DRAFT_CHAT_ID;
  saveCurrentChatId();

  if (shouldRender) {
    render();
    resetTextareaHeight();
  }
}

function openRenameModal(chatId) {
  if (!chats[chatId]) return;

  renameTargetChatId = chatId;
  renameInput.value = chats[chatId].title || "";
  renameModal.classList.remove("hidden");

  requestAnimationFrame(() => {
    renameInput.focus();
    renameInput.select();
  });
}

function closeRenameModal() {
  renameModal.classList.add("hidden");
  renameTargetChatId = null;
  renameInput.value = "";
}

async function deleteChat(chatId) {
  const chat = chats[chatId];
  if (!chat) return;

  const ok = confirm(`Удалить чат «${chat.title}»?`);
  if (!ok) return;

  if (chatId === DRAFT_CHAT_ID) {
    delete chats[chatId];
    clearTitleTyping(chatId);
    clearAssistantTyping();
    hideThinkingBubble();
    startDraftChat();
    return;
  }

  try {
    await api(`/chats/${chatId}`, {
      method: "DELETE"
    });

    delete chats[chatId];
    clearTitleTyping(chatId);
    clearAssistantTyping();
    hideThinkingBubble();

    const ids = Object.keys(chats).filter((id) => id !== DRAFT_CHAT_ID);

    if (ids.length === 0) {
      startDraftChat();
      return;
    }

    if (chatId === currentChatId) {
      currentChatId = getSortedChatEntries()[0][0];
      saveCurrentChatId();
      await loadChatById(currentChatId);
      return;
    }

    render();
  } catch (err) {
    alert(err.message || "Не удалось удалить чат");
  }
}

/* =========================
   CONTEXT MENU
========================= */
function showContextMenu(chatId, buttonEl) {
  activeMenuChatId = chatId;

  const rect = buttonEl.getBoundingClientRect();
  const menuWidth = 200;
  const menuHeight = 116;
  const gap = 8;

  let left = rect.right + gap;
  let top = rect.top;

  if (left + menuWidth > window.innerWidth - 8) {
    left = rect.left - menuWidth - gap;
  }

  if (top + menuHeight > window.innerHeight - 8) {
    top = window.innerHeight - menuHeight - 8;
  }

  if (top < 8) {
    top = 8;
  }

  contextMenu.style.left = `${left}px`;
  contextMenu.style.top = `${top}px`;
  contextMenu.classList.remove("hidden");
}

function hideContextMenu() {
  contextMenu.classList.add("hidden");
  activeMenuChatId = null;
}

/* =========================
   RENDER
========================= */
function renderChatList() {
  chatListEl.innerHTML = "";

  const entries = getSortedChatEntries();

  for (const [id, chat] of entries) {
    if (id === DRAFT_CHAT_ID && !chatHasMessages(chat)) {
      continue;
    }

    const item = document.createElement("div");
    item.className = `chat-list-item ${id === currentChatId ? "active" : ""}`;

    const title = document.createElement("span");
    title.className = "chat-list-title";
    title.dataset.chatTitleId = id;
    title.textContent = chat.title || "Новый чат";

    title.onclick = async () => {
      if (id === currentChatId) return;
      await loadChatById(id);
    };

    title.ondblclick = (e) => {
      e.stopPropagation();
      openRenameModal(id);
    };

    const menuBtn = document.createElement("button");
    menuBtn.className = "chat-menu-btn";
    menuBtn.innerHTML = icons.more;
    menuBtn.title = "Опции";
    menuBtn.type = "button";

    menuBtn.onclick = (e) => {
      e.stopPropagation();

      if (!contextMenu.classList.contains("hidden") && activeMenuChatId === id) {
        hideContextMenu();
        return;
      }

      showContextMenu(id, menuBtn);
    };

    item.appendChild(title);
    item.appendChild(menuBtn);
    chatListEl.appendChild(item);
  }
}

function addCopyButtons(container) {
  container.querySelectorAll("pre").forEach((pre) => {
    if (pre.querySelector(".code-copy-btn")) return;

    const wrapper = document.createElement("div");
    wrapper.className = "code-block-wrapper";
    pre.parentNode.insertBefore(wrapper, pre);
    wrapper.appendChild(pre);

    const btn = document.createElement("button");
    btn.className = "code-copy-btn";
    btn.type = "button";
    btn.title = "Копировать код";
    btn.innerHTML = icons.copy;
    wrapper.appendChild(btn);

    btn.addEventListener("click", () => {
      const code = pre.querySelector("code")?.innerText ?? pre.innerText;
      navigator.clipboard.writeText(code).then(() => {
        btn.innerHTML = icons.check;
        btn.classList.add("copied");
        setTimeout(() => {
          btn.innerHTML = icons.copy;
          btn.classList.remove("copied");
        }, 2000);
      });
    });
  });
}

function renderMessages() {
  messagesDiv.innerHTML = "";

  const currentChat = getCurrentChat();
  const messages = currentChat?.messages || [];
  const isEmpty = messages.length === 0 && !(thinkingState.isActive && thinkingState.chatId === currentChatId);

  mainContent.classList.toggle("empty-state", isEmpty);
  welcomeScreen.style.display = isEmpty ? "flex" : "none";
  messagesDiv.style.display = isEmpty ? "none" : "flex";

  chatTitleEl.textContent = currentChat?.title || "Новый чат";

  messages.forEach((msg, index) => {
    const row = document.createElement("div");
    row.className = `message-row ${msg.role === "user" ? "user-row" : "bot-row"}`;

    if (msg.role === "assistant") {
      row.dataset.assistantMessageIndex = String(index);
    }

    const el = document.createElement("div");
    el.className = `message ${msg.role === "user" ? "user" : "bot"}`;

    const isTypedAssistantMessage =
      msg.role === "assistant" &&
      assistantTypingState.isActive &&
      assistantTypingState.chatId === currentChatId &&
      assistantTypingState.messageIndex === index;

    if (isTypedAssistantMessage) {
      const safeText = escapeHtml(assistantTypingState.currentText).replaceAll("\n", "<br>");
      el.innerHTML = `${safeText}<span class="assistant-typing-caret"></span>`;
    } else if (msg.role === "assistant" && window.marked) {
      el.innerHTML = marked.parse(msg.content);
      addCopyButtons(el);
    } else {
      el.textContent = msg.content;
    }

    row.appendChild(el);
    messagesDiv.appendChild(row);
  });

  if (thinkingState.isActive && thinkingState.chatId === currentChatId) {
    const row = document.createElement("div");
    row.className = "message-row bot-row";

    const bubble = document.createElement("div");
    bubble.className = "message bot thinking";
    bubble.setAttribute("aria-label", "Ассистент думает");
    bubble.innerHTML = `
      <span class="thinking-dot"></span>
      <span class="thinking-dot"></span>
      <span class="thinking-dot"></span>
    `;

    row.appendChild(bubble);
    messagesDiv.appendChild(row);
  }
}

function render() {
  hideContextMenu();
  renderChatList();

  const currentChat = getCurrentChat();
  chatTitleEl.textContent = currentChat?.title || "Новый чат";

  renderMessages();
  renderTopicsManager();
  updateChatAvailability();
  autoResizeTextarea();
}

/* =========================
   INIT
========================= */
async function init() {
  const isAuthorized = await checkAuthOnMain();

  if (isAuthorized) {
    try {
      await loadTopicsFromServer();
      await loadChatsFromServer();
      await fetchStreakFromServer();
    } catch (err) {
      console.error(err);
      topicsState.all = sortTopicsByLearningOrder([...FALLBACK_TOPICS]);
      renderSurveyTopicsGrid();
      startDraftChat(false);
    }
  } else {
    startDraftChat(false);
  }

  render();
  updateSurveyUI();
  setDevResetButtonVisibility();
  updateChatAvailability();
  autoResizeTextarea();
  renderStreakWidget();

  if (authUser && !canUseChat()) {
    openSurveyModal();
  }
}

init();