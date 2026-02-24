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