<<<<<<< HEAD
const messagesDiv = document.getElementById("messages");
const form = document.getElementById("inputForm");
const input = document.getElementById("queryInput");

let chatHistory = [];

form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const text = input.value.trim();
    if (!text) return;

    const userMsg = document.createElement("div");
    userMsg.classList.add("message", "user");
    userMsg.innerText = text;
    messagesDiv.appendChild(userMsg);
    messagesDiv.scrollTop = messagesDiv.scrollHeight;

    chatHistory.push({ role: "user", content: text });
    input.value = "";

    try {
        const resp = await fetch("http://127.0.0.1:8000/chat", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ messages: chatHistory })
        });

        if (!resp.ok) {
            const errorText = await resp.text();
            console.error("Server Error:", errorText);
            alert("Error: " + errorText);
            return;
        }

        const data = await resp.json();

        const botMsg = document.createElement("div");
        botMsg.classList.add("message", "bot");
        botMsg.innerText = data.answer;
        messagesDiv.appendChild(botMsg);
        messagesDiv.scrollTop = messagesDiv.scrollHeight;

        chatHistory.push({ role: "assistant", content: data.answer });

    } catch (err) {
        console.error("Error:", err);
        alert("Connection lost");
    }
});
=======
import { icons } from "./icons.js";

let chats = {};
let currentChatId = localStorage.getItem("currentChatId") || null;
let renameTargetChatId = null;
let activeMenuChatId = null;
let isSending = false;

const ONBOARDING_STORAGE_KEY = "js_onboarding_state";

let onboardingState = JSON.parse(localStorage.getItem(ONBOARDING_STORAGE_KEY)) || {
  completed: false,
  level: null,
  topics: []
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
    headers: {
      "Content-Type": "application/json",
      ...(options.headers || {})
    },
    ...options
  });

  const data = await response.json().catch(() => ({}));

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
  contextRenameBtn.innerHTML = `${icons.rename} <span>Переименовать</span>`;
  contextDeleteBtn.innerHTML = `${icons.delete} <span>Удалить</span>`;
}

function applyTheme(theme) {
  document.documentElement.setAttribute("data-theme", theme);
  localStorage.setItem("theme", theme);
  themeBtn.innerHTML = theme === "dark" ? icons.sun : icons.moon;
}

applyTheme(localStorage.getItem("theme") || "dark");
setupIcons();
resetTextareaHeight();

themeBtn.addEventListener("click", () => {
  const currentTheme = document.documentElement.getAttribute("data-theme");
  applyTheme(currentTheme === "dark" ? "light" : "dark");
});

sidebarToggle.addEventListener("click", () => {
  sidebar.classList.toggle("collapsed");
  hideContextMenu();
});

newChatBtn.addEventListener("click", () => {
  startDraftChat();
  if (canUseChat()) {
    input.focus();
  }
});

document.addEventListener("click", (e) => {
  if (!contextMenu.contains(e.target)) {
    hideContextMenu();
  }
});

window.addEventListener("resize", hideContextMenu);
window.addEventListener("scroll", hideContextMenu, true);

renameCloseBtn.addEventListener("click", closeRenameModal);
renameCancelBtn.addEventListener("click", closeRenameModal);

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
    hideContextMenu();
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
  updateSurveyUI();
});

levelReturningBtn.addEventListener("click", () => {
  onboardingState.level = "returning";
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

  updateSurveyUI();
});

surveyContinueBtn.addEventListener("click", () => {
  if (!onboardingState.level) return;

  onboardingState.completed = true;
  saveOnboardingState();
  closeSurveyModal();
  updateChatAvailability();
  input.focus();
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

  const topicButtons = topicsGrid.querySelectorAll(".topic-chip");
  topicButtons.forEach((btn) => {
    const topic = btn.dataset.topic;
    btn.classList.toggle("active", onboardingState.topics.includes(topic));
  });

  surveyContinueBtn.disabled = !onboardingState.level;
}

function updateChatAvailability() {
  const locked = !canUseChat();

  input.disabled = locked || isSending;
  sendBtn.disabled = locked || isSending;
  form.classList.toggle("is-locked", locked);

  if (locked) {
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
  updateChatAvailability();
  autoResizeTextarea();
}

/* =========================
   INIT
========================= */
async function init() {
  try {
    await loadChatsFromServer();
  } catch (err) {
    console.error(err);
    alert("Не удалось загрузить чаты с сервера.");
    startDraftChat(false);
  }

  render();
  updateSurveyUI();
  updateChatAvailability();
  autoResizeTextarea();

  if (!canUseChat()) {
    openSurveyModal();
  }
}

init();
>>>>>>> 45c438a4eb640a159f22615895478e85747de630
