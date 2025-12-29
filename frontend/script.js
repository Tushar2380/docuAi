const API_URL = 'http://localhost:8000';
let currentSessionId = null;

// --- Initialization ---
document.addEventListener('DOMContentLoaded', () => {
    // 1. Initialize Theme from Storage
    const savedTheme = localStorage.getItem('theme') || 'dark';
    document.documentElement.setAttribute('data-theme', savedTheme);
    updateThemeIcon(savedTheme);

    // 2. Load Data
    checkStatus();
    loadSessions();
    loadFiles();
    setupEventListeners();
});

// --- Theme Logic ---
function updateThemeIcon(theme) {
    const icon = document.getElementById('themeIcon');
    const text = document.getElementById('themeText');
    if (theme === 'dark') {
        icon.className = 'ri-moon-line';
        text.innerText = 'Dark Mode';
    } else {
        icon.className = 'ri-sun-line';
        text.innerText = 'Light Mode';
    }
}

// --- Event Listeners ---
function setupEventListeners() {
    // Theme Toggle
    document.getElementById('themeToggle').addEventListener('click', () => {
        const current = document.documentElement.getAttribute('data-theme');
        const next = current === 'dark' ? 'light' : 'dark';
        document.documentElement.setAttribute('data-theme', next);
        localStorage.setItem('theme', next); 
        updateThemeIcon(next);
    });

    // File Upload
    const heroDrop = document.getElementById('heroDropZone');
    const fileInput = document.getElementById('fileInput');

    if (heroDrop) {
        heroDrop.addEventListener('click', () => fileInput.click());
        heroDrop.addEventListener('dragover', (e) => {
            e.preventDefault();
            heroDrop.classList.add('dragover');
        });
        heroDrop.addEventListener('dragleave', () => heroDrop.classList.remove('dragover'));
        heroDrop.addEventListener('drop', (e) => {
            e.preventDefault();
            heroDrop.classList.remove('dragover');
            validateAndUpload(e.dataTransfer.files);
        });
    }

    fileInput.addEventListener('change', (e) => validateAndUpload(e.target.files));
}

// --- UI Helpers ---
function showToast(message, type = 'info') {
    const container = document.getElementById('toastContainer');
    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    let icon = 'ri-information-line';
    if(type === 'success') icon = 'ri-checkbox-circle-line';
    if(type === 'error') icon = 'ri-error-warning-line';
    toast.innerHTML = `<i class="${icon}"></i> <span>${message}</span>`;
    container.appendChild(toast);
    setTimeout(() => {
        toast.style.opacity = '0';
        toast.style.transform = 'translateX(100%)';
        setTimeout(() => toast.remove(), 300);
    }, 3000);
}

let confirmCallback = null;
function showConfirmModal(title, message, callback) {
    document.getElementById('modalTitle').innerText = title;
    document.getElementById('modalMessage').innerText = message;
    document.getElementById('modalOverlay').classList.remove('hidden');
    confirmCallback = callback;
}
function closeModal() {
    document.getElementById('modalOverlay').classList.add('hidden');
    confirmCallback = null;
}
document.getElementById('modalConfirmBtn').addEventListener('click', () => {
    if (confirmCallback) confirmCallback();
    closeModal();
});

// --- Sidebar Logic ---
function toggleSidebar() {
    const sidebar = document.getElementById('sidebar');
    const expandBtn = document.getElementById('expandBtn');
    if (window.innerWidth <= 768) {
        sidebar.classList.toggle('active');
    } else {
        sidebar.classList.toggle('collapsed');
        if (sidebar.classList.contains('collapsed')) {
            expandBtn.classList.remove('hidden');
        } else {
            expandBtn.classList.add('hidden');
        }
    }
}

function autoResize(textarea) {
    textarea.style.height = 'auto';
    textarea.style.height = textarea.scrollHeight + 'px';
}

// --- Backend Logic ---
async function checkStatus() {
    try {
        const res = await fetch(`${API_URL}/status`);
        const data = await res.json();
        if (data.current_session) {
            loadSession(data.current_session);
        }
    } catch (e) {
        showToast("Backend disconnected", "error");
    }
}

async function validateAndUpload(files) {
    if (!files.length) return;
    for (let file of files) {
        const ext = file.name.split('.').pop().toLowerCase();
        if (!['pdf', 'docx'].includes(ext)) {
            showToast(`Skipped ${file.name}: Only PDF/DOCX allowed.`, 'error');
            continue;
        }
        const formData = new FormData();
        formData.append('file', file);
        try {
            showToast(`Uploading ${file.name}...`, 'info');
            const res = await fetch(`${API_URL}/upload`, { method: 'POST', body: formData });
            const data = await res.json();
            if (res.ok) {
                showToast(`${file.name} uploaded!`, 'success');
                loadFiles();
            } else {
                showToast(`Failed: ${data.detail || 'Unknown error'}`, 'error');
            }
        } catch (err) {
            showToast(`Network error uploading ${file.name}`, 'error');
        }
    }
}

async function loadFiles() {
    try {
        const res = await fetch(`${API_URL}/files`);
        const data = await res.json();
        const list = document.getElementById('fileList');
        const count = document.getElementById('fileCount');
        list.innerHTML = '';
        count.innerText = data.files ? data.files.length : 0;
        if (data.files) {
            data.files.forEach(file => {
                const div = document.createElement('div');
                div.className = 'file-item';
                div.innerHTML = `
                    <i class="ri-file-pdf-line"></i>
                    <span style="flex:1; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;">${file.filename}</span>
                    <i class="ri-close-line text-danger" onclick="deleteFile('${file.file_id}')"></i>
                `;
                list.appendChild(div);
            });
        }
    } catch (e) { console.error("Error loading files"); }
}

async function deleteFile(fileId) {
    showConfirmModal("Delete File", "Remove this file from knowledge base?", async () => {
        await fetch(`${API_URL}/files/${fileId}`, { method: 'DELETE' });
        showToast("File deleted", "success");
        loadFiles();
    });
}

// --- Chat & Session Logic ---

async function createNewSession() {
    const res = await fetch(`${API_URL}/sessions/new`, { method: 'POST' });
    const data = await res.json();
    currentSessionId = data.session_id;
    
    document.getElementById('messagesList').innerHTML = '';
    document.getElementById('emptyState').classList.remove('hidden');
    document.getElementById('chatTitle').innerText = "New Conversation";
    
    loadSessions();
}

async function deleteSession(sessionId) {
    showConfirmModal("Delete Chat", "Delete this conversation?", async () => {
        try {
            const res = await fetch(`${API_URL}/sessions/${sessionId}`, { method: 'DELETE' });
            if (res.ok) {
                showToast("Chat deleted", "success");
                if (currentSessionId === sessionId) {
                    createNewSession();
                } else {
                    loadSessions();
                }
            }
        } catch (e) { showToast("Error deleting session", "error"); }
    });
}

async function loadSessions() {
    try {
        const res = await fetch(`${API_URL}/sessions`);
        const data = await res.json();
        const list = document.getElementById('sessionList');
        list.innerHTML = '';
        data.sessions.forEach(session => {
            const div = document.createElement('div');
            div.className = `session-item ${session.id === currentSessionId ? 'active' : ''}`;
            div.innerHTML = `
                <i class="ri-message-3-line"></i>
                <span style="flex:1; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;">${session.title}</span>
            `;
            const delBtn = document.createElement('i');
            delBtn.className = 'ri-delete-bin-line text-danger';
            delBtn.style.marginLeft = 'auto';
            delBtn.style.opacity = '0.6';
            delBtn.style.fontSize = '0.9em';
            delBtn.onclick = (e) => {
                e.stopPropagation();
                deleteSession(session.id);
            };
            div.appendChild(delBtn);
            div.onclick = () => loadSession(session.id);
            list.appendChild(div);
        });
    } catch (e) { console.error("Error loading sessions"); }
}

async function loadSession(sessionId) {
    currentSessionId = sessionId;
    const res = await fetch(`${API_URL}/sessions/${sessionId}`);
    if (!res.ok) {
        createNewSession();
        return;
    }
    const data = await res.json();
    document.getElementById('chatTitle').innerText = data.title;
    document.getElementById('emptyState').classList.add('hidden');
    const container = document.getElementById('messagesList');
    container.innerHTML = '';
    if (data.messages) {
        data.messages.forEach(msg => {
            appendMessage(msg.role === 'assistant' ? 'ai' : 'user', msg.content, msg.sources);
        });
    }
    loadSessions();
}

function handleEnter(e) {
    if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        sendMessage();
    }
}

async function sendMessage() {
    const input = document.getElementById('userInput');
    const text = input.value.trim();
    if (!text) return;

    if (!currentSessionId) await createNewSession();

    document.getElementById('emptyState').classList.add('hidden');
    appendMessage('user', text);
    input.value = '';
    input.style.height = 'auto';

    const loadingId = 'loading-' + Date.now();
    const container = document.getElementById('messagesList');
    const loadDiv = document.createElement('div');
    loadDiv.className = 'message ai';
    loadDiv.id = loadingId;
    loadDiv.innerHTML = `
        <div class="message-avatar"><i class="ri-robot-2-line"></i></div>
        <div class="message-content">
            <div class="typing-indicator">Thinking...</div>
        </div>
    `;
    container.appendChild(loadDiv);
    container.parentElement.scrollTop = container.parentElement.scrollHeight;

    try {
        const res = await fetch(`${API_URL}/ask`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ question: text, session_id: currentSessionId })
        });
        
        const data = await res.json();
        document.getElementById(loadingId).remove();
        
        if (res.ok) {
            // FIX: Ensure we stay on the same session ID returned by backend
            if (data.session_id && data.session_id !== currentSessionId) {
                currentSessionId = data.session_id;
            }
            appendMessage('ai', data.answer, data.sources);
            loadSessions();
        } else {
            showToast(data.detail || "Error getting answer", "error");
        }
    } catch (e) {
        document.getElementById(loadingId).remove();
        showToast("Connection failed", "error");
    }
}

function appendMessage(role, text, sources = []) {
    const container = document.getElementById('messagesList');
    const div = document.createElement('div');
    div.className = `message ${role}`;
    
    const htmlContent = marked.parse(text);
    
    let sourceHtml = '';
    if (sources && sources.length) {
        sourceHtml = `<div class="message-sources" style="margin-top:10px; font-size:0.8em; opacity:0.7; border-top:1px solid rgba(255,255,255,0.1); padding-top:5px;">
            <i class="ri-book-open-line"></i> Sources: ${sources.join(', ')}
        </div>`;
    }

    const icon = role === 'ai' ? 'ri-robot-2-line' : 'ri-user-smile-line';
    
    div.innerHTML = `
        <div class="message-avatar"><i class="${icon}"></i></div>
        <div class="message-content">
            ${htmlContent}
            ${sourceHtml}
        </div>
    `;
    
    container.appendChild(div);
    const scrollArea = document.getElementById('chatContainer');
    scrollArea.scrollTop = scrollArea.scrollHeight;
}

function confirmClearAll() {
    showConfirmModal("Clear All Data", "Are you sure? This deletes ALL uploaded files AND chat history.", async () => {
        await fetch(`${API_URL}/clear`, { method: 'DELETE' });
        showToast("System reset complete", "success");
        setTimeout(() => location.reload(), 1000);
    });
}