const chatBox = document.getElementById('chat-box');
const chatList = document.getElementById('chat-list');
const questionField = document.getElementById('question');
const flash = document.getElementById('flash');
let chat_id = localStorage.getItem('chat_id') || '';
const previewContainer = document.getElementById('preview-container');
  const fileInput = document.getElementById('images');
  let selectedFiles = [];

  const modelMap = {

  "openai/gpt-4.1": {
    name: "😶‍🌫️ Chatgpt 4.1 – Smartest (Github)",
    image: false
  },
  "meta-llama/llama-4-maverick-17b-128e-instruct": {
    name: "🦙 LLaMA 4 Maverick – Groq",
    image: true
  },
  "llama-3.3-70b-versatile": {
    name: "🧠 LLaMA 3.3 70B – Groq"
  },
  "qwen/qwen3-30b-a3b:free": {
    name: "📘 Qwen 30B – OpenRouter"
  },
  "qwen/qwen2.5-vl-32b-instruct:free": {
    name: "🌟 Qwen 2.5 VL 32B – OpenRouter (🖼️ Image)"
  },
  "llama3-70b-8192": {
    name: "^_~ LLaMA 3 70B – Groq"
  },
  "llama3-8b-8192": {
    name: "O_O LLaMA 3 8B – Groq"
  },
  "deepseek-r1-distill-llama-70b": {
    name: "🔥 DeepSeek R1 Distill – Groq"
  },
  "nvidia/llama-3.3-nemotron-super-49b-v1:free": {
    name: "⚙️ Nvidia Nemotron 49B – OpenRouter (🖼️ Image)"
  },
  "meta-llama/llama-4-scout-17b-16e-instruct": {
    name: "🦾 LLaMA 4 Scout – Groq (🖼️ Image)"
  },
  "qwen/qwen3-32b": {
    name: "🌍 Qwen 32B – Groq"
  },
  "deepseek/deepseek-r1-0528-qwen3-8b:free": {
    name: "🧠 DeepSeek R1 Qwen 8B – OpenRouter"
  },
  "gemma2-9b-it": {
    name: "🔬 Gemma 2 9B IT – Groq"
  },
  "mistral-saba-24b": {
    name: "✨ Mistral SABA 24B – Groq"
  },
  "compound-beta": {
    name: "🧪 Compound Beta – Groq"
  },
  "qwen/qwen3-8b:free": {
    name: "🌐 Qwen 8B – OpenRouter"
  },
  "thudm/glm-4-32b:free": {
    name: "🗣️ GLM 4 – OpenRouter"
  },
  "meta-llama/llama-prompt-guard-2-86m": {
    name: "🛡️ LLaMA Prompt Guard – Groq"
  },
  "google/gemma-3-27b-it:free": {
    name: "📄 Gemma 3 27B IT – OpenRouter"
  }
};

async function withRetry(fn, retries = 3, delay = 500) {
  for (let i = 0; i < retries; i++) {
    try {
      return await fn();
    } catch (e) {
      console.warn(`Retry ${i + 1} failed`, e);
      if (i < retries - 1) await new Promise(res => setTimeout(res, delay * (i + 1)));
    }
  }
  throw new Error("All retries failed.");
}

function toggleSidebar() {
  const sidebar = document.getElementById("sidebar");
  const main = document.querySelector(".main");

  sidebar.classList.toggle("collapsed");

  if (window.innerWidth > 768) {
    main.classList.toggle("shifted");  // triggers margin-left: 0
  }
}

function autoResize(textarea) {
  textarea.style.height = 'auto';
  textarea.style.height = (textarea.scrollHeight) + 'px';
}

questionField.addEventListener('keydown', function (e) {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault();
    askQuestion();
  }
});

function previewImages(input) {
  const newFiles = Array.from(input.files);
  if (newFiles.length === 0) return; // 🛑 Prevent clearing if user cancels file dialog

  selectedFiles = newFiles;
  previewContainer.innerHTML = "";

  selectedFiles.forEach((file, index) => {
    const reader = new FileReader();
    reader.onload = e => {
      const wrapper = document.createElement("div");
      wrapper.className = "preview-wrapper";
      wrapper.style.position = "relative";

      const img = document.createElement("img");
      img.src = e.target.result;
      img.style.maxHeight = "60px";
      img.style.borderRadius = "6px";

      const closeBtn = document.createElement("span");
      closeBtn.textContent = "x";
      closeBtn.style = `
        position: absolute;
        top: -10px;
        right: -10px;
        background: red;
        color: white;
        border-radius: 50%;
        width: 20px;
        height: 20px;
        display: flex;
        align-items: center;
        justify-content: center;
        cursor: pointer;
        font-size: 12px;
      `;
      closeBtn.onclick = () => {
        selectedFiles.splice(index, 1);
        refreshPreviews();  // ✅ safe now
      };

      wrapper.appendChild(img);
      wrapper.appendChild(closeBtn);
      previewContainer.appendChild(wrapper);
    };
    reader.readAsDataURL(file);
  });
}

function refreshPreviews() {
  const dt = new DataTransfer();
  selectedFiles.forEach(file => dt.items.add(file));
  fileInput.files = dt.files;
  previewContainer.innerHTML = "";
  previewImages(fileInput);
}

function clearImages() {
    fileInput.value = '';
    selectedFiles = [];
    previewContainer.innerHTML = '';
  }

// 🟢 Replaces handleDragOver
function handleDragOver(e) {
  e.preventDefault();
  previewContainer.style.outline = "3px dashed #0ff";
  previewContainer.style.background = "rgba(0, 255, 255, 0.05)";
}

// 🟢 Replaces handleDrop
function handleDrop(e) {
  e.preventDefault();
  previewContainer.style.outline = "";
  previewContainer.style.background = "";

  const droppedFiles = Array.from(e.dataTransfer.files).filter(f => f.type.startsWith("image/"));
  if (!droppedFiles.length) {
    showFlash("Only image files are supported.");
    return;
  }

  selectedFiles.push(...droppedFiles);
  refreshPreviews();
}

async function askQuestion() {
  const question = questionField.value.trim();
  if (!question && selectedFiles.length === 0) return;

  // ✅ Fallback for missing chat_id
  if (!chat_id || chat_id.length < 10) {
    try {
      const res = await fetch("/new_chat", { method: "POST" });
      const data = await res.json();
      chat_id = data.chat_id;
      localStorage.setItem("chat_id", chat_id);
      const inputField = document.getElementById("chat_id");
      if (inputField) inputField.value = chat_id;
      setActiveChat(chat_id);
    } catch (e) {
      showFlash("Something went wrong");
      console.warn("Fetch failed", e);
      return;  // stop execution
    }
  }


    // chat_id = data.chat_id;
    // localStorage.setItem("chat_id", chat_id);
    // const inputField = document.getElementById("chat_id");
    // if (inputField) inputField.value = chat_id;
    // setActiveChat(chat_id);

  const formData = new FormData();
  formData.append("question", question);
  formData.append("ai_model", document.getElementById("ai_model").value);
  formData.append("temperature", document.getElementById("temperature").value);
  formData.append("web_search_enabled", document.getElementById("web_search_enabled").value);
  formData.append("chat_id", chat_id);

  for (const file of selectedFiles) {
    formData.append("images", file);
  }

  // Show user message with image previews
  addChatMessage("user", [
    ...(question ? [{ type: "text", text: question }] : []),
    ...selectedFiles.map(file => ({
      type: "image_url",
      image_url: { url: URL.createObjectURL(file) }
    }))
  ]);

  questionField.value = "";

  const placeholder = addChatMessage("assistant", "💬 Thinking...");

  try {
    const res = await fetch("/ask", { method: "POST", body: formData });
    const data = await res.json();

    if (data && typeof data === "object" && data.error) {
      showFlash(data.error || "Something went wrong while getting response.");
      placeholder.remove();
      return;
    }

    // ✅ Server may return updated chat_id (important for guests!)
    if (data.chat_id) {
      chat_id = data.chat_id;
      setActiveChat(chat_id);
      localStorage.setItem("chat_id", chat_id);
      const inputField = document.getElementById("chat_id");
      if (inputField) inputField.value = chat_id;
      refreshChatList();
    }

    const contentDiv = placeholder.querySelector(".content");
    contentDiv.innerHTML = "";

    if (data.answer && data.answer.trim()) {
      renderMessageWithCode(contentDiv, data.answer);
    } else {
      renderMessageWithCode(contentDiv, "🤖 The model didn't return a response. Try rephrasing or check if the image was understood.");
    }

    // Add copy button
    const copyBtn = document.createElement("button");
    copyBtn.className = "copy-btn";
    copyBtn.innerHTML = "📋";
    copyBtn.onclick = () => {
      let textToCopy = '';
      const clone = contentDiv.cloneNode(true);
      clone.querySelectorAll(".copy-btn").forEach(btn => btn.remove());
      textToCopy = clone.innerText.trim();
      navigator.clipboard.writeText(textToCopy).then(() => {
        copyBtn.innerText = '✅';
        setTimeout(() => copyBtn.innerText = '📋', 1200);
      });
    };
    contentDiv.appendChild(copyBtn);

    clearImages();
  } catch (e) {
    showFlash("Something went wrong while getting response.");
    placeholder.remove();
  }
}
  
function addChatMessage(role, content) {
  const msg = document.createElement('div');
  msg.className = `chat-msg ${role}`;

  const roleLabel = document.createElement("div");
  roleLabel.className = "role-label";
  roleLabel.innerText = role === "user" ? "👤 You:" : "🤖 AI:";
  msg.appendChild(roleLabel);

  const contentBox = document.createElement("div");
  contentBox.className = "content hover-copy";

  if (typeof content === "string") {
    renderMessageWithCode(contentBox, content);
  } else if (Array.isArray(content)) {
    for (const item of content) {
      if (item.type === "text") {
        renderMessageWithCode(contentBox, item.text);
      } else if (item.type === "image_url") {
        const img = document.createElement("img");
        img.src = item.image_url.url;
        img.style.maxWidth = "200px";
        img.style.display = "block";
        img.style.marginTop = "8px";
        contentBox.appendChild(img);
      }
    }
  }

  // Add copy button
    const copyBtn = document.createElement("button");
    copyBtn.className = "copy-btn";
    copyBtn.innerHTML = "📋";
    copyBtn.onclick = () => {
        let textToCopy = '';
        const clone = contentBox.cloneNode(true);
        clone.querySelectorAll("button.copy-btn").forEach(btn => btn.remove());
        textToCopy = clone.innerText.trim();
        navigator.clipboard.writeText(textToCopy).then(() => {
            copyBtn.innerText = '✅';
            setTimeout(() => copyBtn.innerText = '📋', 1200);
        });
    };
    contentBox.appendChild(copyBtn);

  msg.appendChild(contentBox);
  chatBox.appendChild(msg);
  // scrollToBottom();
  chatBox.scrollTop = chatBox.scrollHeight;

  return msg;
}

function renderMessageWithCode(container, text) {
  const codeBlockRegex = /```([\s\S]*?)```/g;
  let lastIndex = 0;
  let match;

  while ((match = codeBlockRegex.exec(text)) !== null) {
    // Add text before code
    const preText = text.slice(lastIndex, match.index);
    if (preText.trim()) {
      const p = document.createElement("p");
      p.innerText = preText.trim();
      container.appendChild(p);
    }

    // Add code block
    const codeText = match[1].trim();
    const pre = document.createElement("pre");
    pre.className = "code-block";

    const code = document.createElement("code");
    code.innerText = codeText;
    pre.appendChild(code);

    const copyBtn = document.createElement("button");
    copyBtn.className = "copy-btn";
    copyBtn.innerHTML = "📋";
    copyBtn.onclick = () => {
  navigator.clipboard.writeText(codeText).then(() => {
    copyBtn.innerText = "✅";
    setTimeout(() => copyBtn.innerText = "📋", 1200);
  }).catch(err => {
    console.error("❌ Failed to copy code block:", err);
    copyBtn.innerText = "❌";
    setTimeout(() => copyBtn.innerText = "📋", 1200);
  });
};

    pre.appendChild(copyBtn);

    container.appendChild(pre);
    lastIndex = match.index + match[0].length;
  }

  // Add remaining text
  const remaining = text.slice(lastIndex).trim();
  if (remaining) {
    const p = document.createElement("p");
    p.innerText = remaining;
    container.appendChild(p);
  }
}

async function startNewChat() {
  const res = await fetch("/new_chat", { method: "POST" });
  const data = await res.json();
  chat_id = data.chat_id;

  setActiveChat(chat_id);
  localStorage.setItem("chat_id", chat_id);

  const inputField = document.getElementById("chat_id");
  if (inputField) inputField.value = chat_id;

  chatBox.innerHTML = "";
  refreshChatList();
  loadChat(chat_id);
}


async function refreshChatList() {
  chatList.innerHTML = "";
  try {
    const res = await fetch(`/all_chats`);
    const data = await res.json();

    if (!Array.isArray(data)) throw new Error("Invalid chat list response");

    if (data.length === 0) {
      chatList.innerHTML = "<p style='padding:10px; font-size:13px; color:gray;'>Login to save your chats permanently.</p>";
      return;
    }

    for (const item of data) {
      if (!item.id) continue;

      const chatItem = document.createElement("div");
      chatItem.className = "chat-item";
      chatItem.setAttribute("data-id", item.id);  // ✅ Store chatId here

      const titleSpan = document.createElement("span");
      titleSpan.textContent = item.title || `Chat ${item.id.slice(0, 8)}...`;
      titleSpan.onclick = () => {
        loadChat(item.id);
        setActiveChat(item.id);
      };

      const delBtn = document.createElement("button");
      delBtn.textContent = "x";
      delBtn.onclick = (e) => {
        e.stopPropagation();
        deleteChat(item.id);
      };

      chatItem.appendChild(titleSpan);
      chatItem.appendChild(delBtn);
      chatList.appendChild(chatItem);
    }

    // Restore active chat UI if chat_id exists
    const savedChatId = localStorage.getItem("chat_id");
    if (savedChatId) {
      setActiveChat(savedChatId);
    }

  } catch (err) {
    console.error("refreshChatList failed", err);
    showFlash("⚠️ Could not load chat list.");
  }
}


async function deleteChat(chatId) {
  if (!confirm("Delete this chat?")) return;

  try {
    const res = await withRetry(() =>
      fetch(`/delete_chat/${chatId}`, { method: "DELETE" })
    );
    const data = await res.json();

    if (data.success) {
      const activeId = document.getElementById("chat_id")?.value || localStorage.getItem("chat_id") || '';

      if (chatId === activeId) {
        localStorage.removeItem("chat_id");

        const input = document.getElementById("chat_id");
        if (input) input.value = "";

        const chatBox = document.getElementById("chat-box");
        if (chatBox) chatBox.innerHTML = "";
      }

      await refreshChatList();

      // 🔄 Optional: auto-select another chat if any left
      const remainingItems = document.querySelectorAll(".chat-item[data-id]");
      if (remainingItems.length > 0) {
        const nextId = remainingItems[0].dataset.id;
        loadChat(nextId);
        setActiveChat(nextId);
      }
    } else {
      showFlash?.("❌ Failed to delete chat.");
    }
  } catch (err) {
    console.error("Delete chat failed", err);
    showFlash?.("❌ Error deleting chat.");
  }
}


async function loadChat(id) {
  clearImages();  // ✅ Clear image previews if any

  try {
    const res = await fetch(`/chat/${id}`, {
      credentials: "same-origin",  // ✅ FIXED
    });
    if (!res.ok) throw new Error("Bad response from server");

    const data = await res.json();

    // ✅ Use correct key: messages (not history)
    const messages = data.messages || data.history;
    if (!messages || !Array.isArray(messages)) {
      throw new Error("Invalid chat data");
    }

    const chatBox = document.getElementById("chat-box");
    if (!chatBox) throw new Error("chatBox element not found");

    chatBox.innerHTML = "";

    for (const entry of messages) {
      addChatMessage(entry.role, entry.content);
    }

    // ✅ Update both localStorage and hidden input
    chat_id = id;
    localStorage.setItem("chat_id", id);
    const inputField = document.getElementById("chat_id");
    if (inputField) inputField.value = id;

    setActiveChat(id);

    // ✅ Scroll to bottom (if function defined)
    scrollToBottom();

  } catch (err) {
    console.warn("Failed to load chat", err);
    showFlash("⚠️ Could not load chat.");
    throw err;
  }
}

function showFlash(msg) {
  flash.innerText = msg;
  flash.style.display = 'block';
  setTimeout(() => flash.style.display = 'none', 5000);
}

let isChatLoading = false;

window.onload = async () => {
  if (isChatLoading) return;
  isChatLoading = true;

  // Mobile layout shift fix
  if (window.innerWidth <= 768) {
    sidebar.classList.add("collapsed");
    document.querySelector(".main").classList.add("shifted");
  }

  // ✅ Restore model + temperature from localStorage
  const savedModel = localStorage.getItem("selected_model");
  if (savedModel && modelMap[savedModel]) {
    document.getElementById('ai_model').value = savedModel;
    document.getElementById('selected-model-button').innerText = modelMap[savedModel].name;
  }

  const savedTemp = localStorage.getItem("selected_temp");
  if (savedTemp) {
    document.getElementById("temperature").value = savedTemp;
    const labelMap = {
      "0.2": "🧠 Precise",
      "0.5": "🎯 Balanced",
      "0.8": "💡 Creative",
      "1.0": "🔥 Wild"
    };
    document.getElementById("temp-button").innerText = (labelMap[savedTemp] || "🎯 Balanced") + " ▼";
  }

  // Refresh chat list with retry
  await withRetry(() => refreshChatList(), 3, 600);

let chat_id = document.getElementById("chat_id")?.value || localStorage.getItem("chat_id") || '';
let lastChatId = chat_id || localStorage.getItem("active_chat_id");

async function ensureValidChat() {
  if (!lastChatId || lastChatId.length < 10) {
    // No existing chat, create one
    const res = await fetch("/new_chat", { method: "POST" });
    const data = await res.json();
    lastChatId = data.chat_id;
    localStorage.setItem("chat_id", lastChatId);
    document.getElementById("chat_id").value = lastChatId;
    setActiveChat(lastChatId);
    return;
  }

  // Test if the chat_id is valid (403 fix)
  const res = await fetch(`/chat/${lastChatId}`, { credentials: "same-origin" });
  if (res.status === 403 || res.status === 404) {
    const newChat = await fetch("/new_chat", { method: "POST" });
    const data = await newChat.json();
    lastChatId = data.chat_id;
    localStorage.setItem("chat_id", lastChatId);
    document.getElementById("chat_id").value = lastChatId;
    setActiveChat(lastChatId);
  }
}

await ensureValidChat();

try {
  await withRetry(() => loadChat(lastChatId), 3, 700);
} catch (err) {
  console.warn("Failed to load last chat");
  showFlash("⚠️ Could not restore last session.");
  localStorage.removeItem("chat_id");
  localStorage.removeItem("active_chat_id");
}
  isChatLoading = false;
};

function toggleTempOptions() {
  document.getElementById('temp-options').classList.toggle('hidden');
}

document.querySelectorAll('#temp-options li').forEach(item => {
  item.addEventListener('click', () => {
    const value = item.getAttribute('data-value');
    const label = item.innerText;
    document.getElementById('temperature').value = value;
    document.getElementById('temp-button').innerText = label + ' ▼';
    document.getElementById('temp-options').classList.add('hidden');
  });
});

// Optional: Close if clicked outside
document.addEventListener('click', function (e) {
  const sidebar = document.getElementById("sidebar");
  const toggleBtn = document.querySelector(".toggle-sidebar");
  const modelMenu = document.getElementById("modelMenu");
  const tempOptions = document.getElementById("temp-options");

  // Prevent sidebar toggle from interfering with open menus
  if (
    modelMenu.contains(e.target) ||
    tempOptions.contains(e.target) ||
    toggleBtn.contains(e.target)
  ) return;

  // Collapse sidebar on mobile if clicked outside
  if (
    window.innerWidth <= 768 &&
    !sidebar.contains(e.target)
  ) {
    sidebar.classList.add("collapsed");
    document.querySelector(".main").classList.add("shifted");
  }
});


function toggleModelMenu() {
  const menu = document.getElementById("modelMenu");
  menu.style.display = (menu.style.display === "block") ? "none" : "block";
  document.getElementById("model-info-box").style.display = "none";
}

function selectModel(value) {
  localStorage.setItem("selected_model", value);

  document.getElementById('ai_model').value = value;

  const displayName = modelMap[value]?.name || value;
  document.getElementById('selected-model-button').innerText = displayName;

  document.getElementById('modelMenu').style.display = 'none';
}



function showModelInfo(title, description) {
  const infoBox = document.getElementById("model-info-box");
  infoBox.innerHTML = `<strong>${title}</strong><br>${description}`;
  infoBox.style.display = "block";
}

// Save selected chat
function setActiveChat(chatId) {
  localStorage.setItem("chat_id", chatId);
  document.querySelectorAll(".chat-item").forEach(item => {
    const itemId = item.getAttribute("data-id");
    if (itemId === chatId) {
      item.classList.add("active");
    } else {
      item.classList.remove("active");
    }
  });
}



// Load the last active chat on page load
// window.addEventListener("DOMContentLoaded", function () {
//   const lastChatId = localStorage.getItem("active_chat_id");
//   if (lastChatId) {
//     loadChatById(lastChatId);  // <- your function to render chat window
//   } else {
//     createNewChat(); // or show blank state
//   }
// });

document.addEventListener('click', function (e) {
    const sidebar = document.querySelector('.sidebar');
    const toggleBtn = document.querySelector('.toggle-sidebar');

    // Do nothing if sidebar isn't visible (desktop or already collapsed)
    if (!sidebar || window.innerWidth > 768) return;

    // If sidebar is open and click is outside it and outside toggle button
    if (sidebar.classList.contains('collapsed')) return;

    if (!sidebar.contains(e.target) && !toggleBtn.contains(e.target)) {
      sidebar.classList.remove('collapsed');
    }
  });

document.addEventListener('click', function (e) {
  const tempMenu = document.getElementById('temp-options');
  const tempBtn = document.getElementById('temp-button');
  if (!tempMenu.contains(e.target) && !tempBtn.contains(e.target)) {
    tempMenu.classList.add('hidden');
  }
});

  window.addEventListener('DOMContentLoaded', () => {
  const sidebar = document.getElementById('sidebar');

  // Collapse sidebar on small screens only
  if (window.innerWidth <= 768) {
    sidebar.classList.add('collapsed');
    document.querySelector(".main").classList.add("shifted");
  }

  // Optional: Auto-collapse again on resize if mobile
  window.addEventListener('resize', () => {
  const sidebar = document.getElementById("sidebar");
  const main = document.querySelector(".main");

  if (window.innerWidth <= 768) {
    sidebar.classList.add("collapsed");
    main.classList.add("shifted");
  } else {
    sidebar.classList.remove("collapsed");
    main.classList.remove("shifted");
  }
});
});

if (window.innerWidth <= 768) {
  document.getElementById("sidebar").classList.add("collapsed");
}

// 🧠 When model is changed
// document.getElementById("modelSelect").addEventListener("change", function () {
//   const selectedModel = this.value;
//   localStorage.setItem("selected_model", selectedModel); // 💾 Save model
//   sendSettingsToServer();
// });

// 🌡️ When temperature is changed
// document.querySelectorAll("#temp-options button").forEach((btn) => {
//   btn.addEventListener("click", () => {
//     const temp = parseFloat(btn.getAttribute("data-temp"));
//     localStorage.setItem("selected_temp", temp); // 💾 Save temp
//     setTemperature(temp);
//     sendSettingsToServer();
//   });
// });

let dragCounter = 0;

window.addEventListener("dragenter", e => {
  dragCounter++;
  handleDragOver(e);
});

window.addEventListener("dragleave", e => {
  dragCounter--;
  if (dragCounter === 0) {
    previewContainer.style.outline = "";
    previewContainer.style.background = "";
  }
});

window.addEventListener("dragover", e => {
  e.preventDefault(); // prevent browser from opening file
});

window.addEventListener("drop", e => {
  handleDrop(e);
  dragCounter = 0;
});

function toggleWebSearch() {
  const button = document.getElementById('web-search-toggle');
  const hiddenInput = document.getElementById('web_search_enabled');
  const isActive = hiddenInput.value === 'true';
  hiddenInput.value = isActive ? 'false' : 'true';

  if (isActive) {
    button.classList.remove('active');
  } else {
    button.classList.add('active');
  }

  // Save state
  localStorage.setItem('web_search_enabled', hiddenInput.value);
}
// Restore web search toggle
const savedSearch = localStorage.getItem('web_search_enabled');
// let webToggle = document.getElementById('web-search-toggle');
const webInput = document.getElementById('web_search_enabled');

// if (savedSearch === 'true') {
//   webToggle.classList.add('active');
//   webInput.value = 'true';
// } else {
//   webToggle.classList.remove('active');
//   webInput.value = 'false';
// }

// ✅ Scroll-to-bottom logic
const scrollBtn = document.getElementById("scrollToBottom");
const chatDisplay = document.getElementById("chat-box");

chatDisplay.addEventListener("scroll", () => {
  const nearBottom = chatDisplay.scrollTop + chatDisplay.clientHeight >= chatDisplay.scrollHeight - 200;
  scrollBtn.style.display = nearBottom ? "none" : "block";
});

scrollBtn.addEventListener("click", () => {
  chatDisplay.scrollTo({
    top: chatDisplay.scrollHeight,
    behavior: 'smooth'
  });
});

// const toggle = document.getElementById("web-search-toggle");
// if (toggle) {
//   toggle.classList.add("active");
// }

const webToggle = document.getElementById('web-search-toggle');
if (webToggle) {
  if (savedSearch === 'true') {
    webToggle.classList.add('active');
    webInput.value = 'true';
  } else {
    webToggle.classList.remove('active');
    webInput.value = 'false';
  }
}

function scrollToBottom() {
  const chatContainer = document.getElementById("chat-container");
  if (chatContainer) {
    chatContainer.scrollTop = chatContainer.scrollHeight;
  }
}
