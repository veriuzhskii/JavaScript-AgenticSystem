import { icons } from "./icons.js";

let chats = JSON.parse(localStorage.getItem("chats")) || {};
let currentChatId = localStorage.getItem("currentChatId");
let renameTargetChatId = null;
let activeMenuChatId = null;

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

const renameModal = document.getElementById("renameModal");
const renameForm = document.getElementById("renameForm");
const renameInput = document.getElementById("renameInput");
const renameCloseBtn = document.getElementById("renameCloseBtn");
const renameCancelBtn = document.getElementById("renameCancelBtn");

const contextMenu = document.getElementById("chatContextMenu");
const contextRenameBtn = document.getElementById("contextRenameBtn");
const contextDeleteBtn = document.getElementById("contextDeleteBtn");

if (Object.keys(chats).length === 0) {
  createNewChat();
} else if (!currentChatId || !chats[currentChatId]) {
  currentChatId = Object.keys(chats)[0];
}

function setupIcons() {
  sidebarToggle.innerHTML = icons.menu;
  sendBtn.innerHTML = icons.send;

  contextRenameBtn.innerHTML = `
    ${icons.rename}
    <span>Переименовать</span>
  `;

  contextDeleteBtn.innerHTML = `
    ${icons.delete}
    <span>Удалить</span>
  `;
}

function applyTheme(theme) {
  document.documentElement.setAttribute("data-theme", theme);
  localStorage.setItem("theme", theme);
  themeBtn.innerHTML = theme === "dark" ? icons.sun : icons.moon;
}

applyTheme(localStorage.getItem("theme") || "dark");
setupIcons();

themeBtn.addEventListener("click", () => {
  const currentTheme = document.documentElement.getAttribute("data-theme");
  applyTheme(currentTheme === "dark" ? "light" : "dark");
});

sidebarToggle.addEventListener("click", () => {
  sidebar.classList.toggle("collapsed");
  hideContextMenu();
});

newChatBtn.addEventListener("click", () => {
  createNewChat();
  input.focus();
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

renameForm.addEventListener("submit", (e) => {
  e.preventDefault();

  if (!renameTargetChatId || !chats[renameTargetChatId]) {
    closeRenameModal();
    return;
  }

  const newTitle = renameInput.value.trim();
  if (!newTitle) return;

  chats[renameTargetChatId].title = newTitle;
  save();
  render();
  closeRenameModal();
});

contextRenameBtn.addEventListener("click", () => {
  if (!activeMenuChatId) return;

  const chatId = activeMenuChatId;
  hideContextMenu();
  openRenameModal(chatId);
});

contextDeleteBtn.addEventListener("click", () => {
  if (!activeMenuChatId) return;

  const chatId = activeMenuChatId;
  hideContextMenu();
  deleteChat(chatId);
});

form.addEventListener("submit", async (e) => {
  e.preventDefault();

  const text = input.value.trim();
  if (!text) return;

  chats[currentChatId].messages.push({
    role: "user",
    content: text
  });

  input.value = "";
  save();
  render();

  try {
    const res = await fetch("/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        messages: chats[currentChatId].messages
      })
    });

    const data = await res.json();

    chats[currentChatId].messages.push({
      role: "assistant",
      content: data.answer
    });

    save();
    render();
  } catch (err) {
    chats[currentChatId].messages.push({
      role: "assistant",
      content: "Ошибка подключения к серверу."
    });

    save();
    render();
  }
});

function createNewChat() {
  const id = Date.now().toString();
  chats[id] = {
    title: "Новый чат",
    messages: []
  };
  currentChatId = id;
  save();
  render();
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

function deleteChat(chatId) {
  const ok = confirm(`Удалить чат «${chats[chatId].title}»?`);
  if (!ok) return;

  delete chats[chatId];

  const ids = Object.keys(chats);
  if (ids.length === 0) {
    createNewChat();
    return;
  }

  if (chatId === currentChatId) {
    currentChatId = ids[0];
  }

  save();
  render();
}

function showContextMenu(chatId, buttonEl) {
  activeMenuChatId = chatId;

  const rect = buttonEl.getBoundingClientRect();
  const menuWidth = 180;
  const menuHeight = 96;
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

function renderChatList() {
  chatListEl.innerHTML = "";

  const entries = Object.entries(chats).reverse();

  for (const [id, chat] of entries) {
    const item = document.createElement("div");
    item.className = `chat-list-item ${id === currentChatId ? "active" : ""}`;

    const title = document.createElement("span");
    title.className = "chat-list-title";
    title.textContent = chat.title;

    title.onclick = () => {
      currentChatId = id;
      save();
      render();
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

  const messages = chats[currentChatId].messages || [];
  const isEmpty = messages.length === 0;

  welcomeScreen.style.display = isEmpty ? "flex" : "none";
  messagesDiv.style.display = isEmpty ? "none" : "flex";
  chatTitleEl.style.display = isEmpty ? "block" : "none";

  messages.forEach((msg) => {
    const row = document.createElement("div");
    row.className = `message-row ${msg.role === "user" ? "user-row" : "bot-row"}`;

    const el = document.createElement("div");
    el.className = `message ${msg.role === "user" ? "user" : "bot"}`;

    if (msg.role === "assistant" && window.marked) {
      el.innerHTML = marked.parse(msg.content);
    } else {
      el.textContent = msg.content;
    }

    row.appendChild(el);
    messagesDiv.appendChild(row);
  });

  messagesDiv.scrollTop = messagesDiv.scrollHeight;
}

function render() {
  hideContextMenu();
  renderChatList();
  chatTitleEl.textContent = chats[currentChatId].title;
  renderMessages();
}

function save() {
  localStorage.setItem("chats", JSON.stringify(chats));
  localStorage.setItem("currentChatId", currentChatId);
}

render();