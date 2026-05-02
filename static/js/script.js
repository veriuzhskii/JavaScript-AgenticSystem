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
  { key: "async", title: "Async / Await" },
  { key: "api", title: "Fetch / API" }
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
const topicsSection = document.getElementById("topicsSection");
const topicsGrid = document.getElementById("topicsGrid");
const surveyContinueBtn = document.getElementById("surveyContinueBtn");

const userMenuBtn = document.getElementById("userMenuBtn");
const userDropdown = document.getElementById("userDropdown");
const userDropdownEmail = document.getElementById("userDropdownEmail");
const topicsDropdownBtn = document.getElementById("topicsDropdownBtn");
const logoutBtn = document.getElementById("logoutBtn");

const topicsModal = document.getElementById("topicsModal");
const topicsManagerGrid = document.getElementById("topicsManagerGrid");
const topicsCloseBtn = document.getElementById("topicsCloseBtn");
const devResetSurveyBtn = document.getElementById("devResetSurveyBtn");

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

function scrollMessagesToBottom() {
  requestAnimationFrame(() => {
    chatArea.scrollTop = chatArea.scrollHeight;
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

function resetSurveyForDev() {
  if (!isDevEnvironment()) return;

  onboardingState = {
    completed: false,
    level: null,
    topics: []
  };

  saveOnboardingState();
  localStorage.setItem(DEV_FORCE_SURVEY_RESET_KEY, "1");

  userDropdown.classList.add("hidden");
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
}

function setUnauthorizedState() {
  authUser = null;
  userDropdown.classList.add("hidden");
  userMenuBtn.classList.add("hidden");
  setDevResetButtonVisibility();
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

  const topicCatalog = getTopicCatalog();

  for (const topic of topicCatalog) {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "topic-chip";
    btn.dataset.topic = topic.key;
    btn.textContent = topic.title;

    if (onboardingState.topics.includes(topic.key)) {
      btn.classList.add("active");
    }

    topicsGrid.appendChild(btn);
  }
}

/* =========================
   TOPICS
========================= */
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
}

async function saveSurveyTopicsToServer(topicKeys) {
  const normalizedKeys = normalizeTopicKeys(topicKeys);

  const payload = {
    topic_keys: normalizedKeys
  };

  const data = await api("/topics/me", {
    method: "PUT",
    body: JSON.stringify(payload)
  });

  topicsState.learned = Array.isArray(data.learned_topic_keys)
    ? normalizeTopicKeys(data.learned_topic_keys)
    : [];

  onboardingState.topics = [...topicsState.learned];
  saveOnboardingState();

  renderSurveyTopicsGrid();
  renderTopicsManager();

  return data;
}

function openTopicsModal() {
  renderTopicsManager();
  topicsModal.classList.remove("hidden");
}

function closeTopicsModal() {
  topicsModal.classList.add("hidden");
}

function renderTopicsManager() {
  topicsManagerGrid.innerHTML = "";

  const topicCatalog = getTopicCatalog();

  for (const topic of topicCatalog) {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = `topic-status-chip ${topicsState.learned.includes(topic.key) ? "learned" : "not-learned"}`;
    btn.textContent = topic.title;
    btn.disabled = true;

    topicsManagerGrid.appendChild(btn);
  }
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
  scrollMessagesToBottom();
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
  applyTheme(currentTheme === "dark" ? "light" : "dark");
});

sidebarToggle.addEventListener("click", () => {
  sidebar.classList.toggle("collapsed");
  hideContextMenu();
  userDropdown.classList.add("hidden");
});

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

renameCloseBtn.addEventListener("click", closeRenameModal);
renameCancelBtn.addEventListener("click", closeRenameModal);

topicsCloseBtn.addEventListener("click", closeTopicsModal);

topicsModal.addEventListener("click", (e) => {
  if (e.target === topicsModal) {
    closeTopicsModal();
  }
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
  scrollMessagesToBottom();

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
    scrollMessagesToBottom();
    maybeAnimateGeneratedTitle(data.chat_id, previousDraftTitle, data.title);

    const lastMessageIndex = chats[data.chat_id].messages.length - 1;
    const lastMessage = chats[data.chat_id].messages[lastMessageIndex];

    if (lastMessage && lastMessage.role === "assistant") {
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
    scrollMessagesToBottom();
  } finally {
    setSendingState(false);
  }
});

/* =========================
   ONBOARDING / SURVEY
========================= */
levelBeginnerBtn.addEventListener("click", () => {
  onboardingState.level = "beginner";
  onboardingState.topics = [];
  updateSurveyUI();
});

levelReturningBtn.addEventListener("click", () => {
  onboardingState.level = "returning";
  onboardingState.topics = normalizeTopicKeys(onboardingState.topics);
  updateSurveyUI();
});

topicsGrid.addEventListener("click", (e) => {
  const chip = e.target.closest(".topic-chip");
  if (!chip) return;

  const topic = chip.dataset.topic;
  if (!topic) return;

  const exists = onboardingState.topics.includes(topic);

  if (exists) {
    onboardingState.topics = onboardingState.topics.filter((item) => item !== topic);
  } else {
    onboardingState.topics.push(topic);
  }

  onboardingState.topics = normalizeTopicKeys(onboardingState.topics);
  updateSurveyUI();
});

surveyContinueBtn.addEventListener("click", async () => {
  if (!onboardingState.level) return;

  onboardingState.completed = true;
  onboardingState.topics = onboardingState.level === "returning"
    ? normalizeTopicKeys(onboardingState.topics)
    : [];

  saveOnboardingState();

  try {
    if (authUser) {
      const selectedTopics =
        onboardingState.level === "returning" ? [...onboardingState.topics] : [];

      await saveSurveyTopicsToServer(selectedTopics);
      localStorage.removeItem(DEV_FORCE_SURVEY_RESET_KEY);
    }

    closeSurveyModal();
    updateChatAvailability();

    if (authUser) {
      input.focus();
    }
  } catch (error) {
    alert(error.message || "Не удалось сохранить темы");
  }
});

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
  const isBeginner = onboardingState.level === "beginner";
  const isReturning = onboardingState.level === "returning";

  levelBeginnerBtn.classList.toggle("active", isBeginner);
  levelReturningBtn.classList.toggle("active", isReturning);
  topicsSection.classList.toggle("hidden", !isReturning);

  renderSurveyTopicsGrid();

  const topicButtons = topicsGrid.querySelectorAll(".topic-chip");
  topicButtons.forEach((btn) => {
    const topic = btn.dataset.topic;
    btn.classList.toggle("active", onboardingState.topics.includes(topic));
  });

  surveyContinueBtn.disabled = !onboardingState.level;
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
  scrollMessagesToBottom();
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

  if (authUser && !canUseChat()) {
    openSurveyModal();
  }
}

init();