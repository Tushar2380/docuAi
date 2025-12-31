// CHANGE THIS TO YOUR RENDER URL AFTER DEPLOYMENT
const API = 'https://docuchat-ai-bgjh.onrender.com';

let sessionId = null;
let theme = 'light';

// ========== SESSION MANAGEMENT ==========

// Load session from localStorage
function loadSavedSession() {
    try {
        const saved = localStorage.getItem('docuchat_session');
        if (saved) {
            sessionId = saved;
            console.log('Loaded session from localStorage:', sessionId);
        }
    } catch (e) {
        console.log('No saved session found');
    }
}

// Save session to localStorage
function saveSessionToStorage() {
    if (sessionId) {
        localStorage.setItem('docuchat_session', sessionId);
    }
}

// Clear saved session
function clearSavedSession() {
    localStorage.removeItem('docuchat_session');
}

// Update UI to show active session
function updateSessionIndicator() {
    const badge = document.getElementById('badge');
    if (sessionId) {
        badge.textContent = 'In Chat';
        badge.classList.add('active');
    } else {
        badge.textContent = 'Ready';
        badge.classList.remove('active');
    }
}

// ========== INIT ==========
window.onload = () => {
    loadSavedSession();
    loadFiles();
    loadHistory();
    setupUpload();
    updateSessionIndicator();
};

// ========== THEME ==========
function toggleTheme() {
    theme = theme === 'light' ? 'dark' : 'light';
    document.documentElement.setAttribute('data-theme', theme);
    document.getElementById('themeIcon').textContent = theme === 'light' ? '🌙' : '☀️';
}

// ========== UPLOAD ==========
function setupUpload() {
    const box = document.getElementById('uploadBox');
    const input = document.getElementById('fileInput');
    
    box.onclick = () => input.click();
    
    box.ondragover = (e) => {
        e.preventDefault();
        box.style.borderColor = 'var(--primary)';
    };
    
    box.ondragleave = () => {
        box.style.borderColor = '';
    };
    
    box.ondrop = (e) => {
        e.preventDefault();
        box.style.borderColor = '';
        upload(e.dataTransfer.files);
    };
    
    input.onchange = (e) => upload(e.target.files);
}

async function upload(files) {
    if (!files.length) return;
    
    toast('Uploading...', 'info');
    let ok = 0;
    
    // CRITICAL: Save current session state
    const originalSessionId = sessionId;
    console.log('Upload starting. Current session:', originalSessionId);
    
    for (let file of files) {
        if (!file.name.match(/\.(pdf|docx|doc)$/i)) continue;
        
        const form = new FormData();
        form.append('file', file);
        
        try {
            const res = await fetch(`${API}/upload`, {
                method: 'POST',
                body: form
            });
            
            if (res.ok) {
                const data = await res.json();
                console.log('Upload response:', data);
                ok++;
            }
        } catch (e) {
            console.error('Upload error:', e);
        }
    }
    
    document.getElementById('fileInput').value = '';
    
    if (ok > 0) {
        toast(`${ok} file(s) uploaded`, 'success');
        loadFiles();
        
        // CRITICAL: Restore original session - DO NOT create new chat
        if (originalSessionId) {
            sessionId = originalSessionId;
            saveSessionToStorage();
            updateSessionIndicator();
            console.log('Restored original session after upload:', sessionId);
            
            // If we have an active chat, make sure it's still visible
            const chat = document.getElementById('chat');
            const hasMessages = chat.querySelectorAll('.msg').length > 0;
            
            if (!hasMessages && originalSessionId) {
                // Try to load the session messages if chat is empty
                loadSession(originalSessionId);
            }
        }
    } else {
        toast('No files were uploaded', 'error');
    }
}

// ========== FILES ==========
async function loadFiles() {
    try {
        const res = await fetch(`${API}/files`);
        const data = await res.json();
        
        const list = document.getElementById('fileList');
        const count = document.getElementById('fileCount');
        const clearBtn = document.getElementById('clearBtn');
        const badge = document.getElementById('badge');
        
        count.textContent = data.files.length;
        
        if (data.files.length > 0) {
            list.innerHTML = '';
            data.files.forEach(f => {
                const div = document.createElement('div');
                div.className = 'item';
                div.innerHTML = `
                    <span class="item-text">${f.filename.endsWith('.pdf') ? '📄' : '📝'} ${f.filename}</span>
                    <span class="item-del" onclick="delFile('${f.fid}')">×</span>
                `;
                list.appendChild(div);
            });
            clearBtn.style.display = 'block';
            badge.textContent = `${data.files.length} docs`;
            badge.classList.add('active');
        } else {
            list.innerHTML = '<div style="text-align:center;padding:20px;color:var(--text-light);font-size:0.9em">No files</div>';
            clearBtn.style.display = 'none';
            badge.textContent = 'Ready';
            badge.classList.remove('active');
        }
    } catch (e) {
        console.error('Load files error:', e);
        toast('Backend offline', 'error');
    }
}

async function delFile(fid) {
    if (!confirm('Delete this file?')) return;
    
    try {
        await fetch(`${API}/files/${fid}`, { method: 'DELETE' });
        toast('File deleted', 'success');
        loadFiles();
    } catch (e) {
        console.error('Delete error:', e);
        toast('Error deleting file', 'error');
    }
}

async function clearAll() {
    if (!confirm('Clear all files?')) return;
    
    try {
        await fetch(`${API}/clear`, { method: 'DELETE' });
        toast('All files cleared', 'success');
        loadFiles();
    } catch (e) {
        console.error('Clear error:', e);
        toast('Error clearing files', 'error');
    }
}

// ========== HISTORY ==========
async function loadHistory() {
    try {
        const res = await fetch(`${API}/sessions`);
        const data = await res.json();
        
        const list = document.getElementById('historyList');
        
        if (data.sessions && data.sessions.length > 0) {
            list.innerHTML = '';
            data.sessions.forEach(s => {
                const div = document.createElement('div');
                div.className = 'item';
                if (s.id === sessionId) div.classList.add('active');
                div.innerHTML = `
                    <span class="item-text" onclick="loadSession('${s.id}')">${s.title}</span>
                    <span class="item-del" onclick="delSession('${s.id}', event)">×</span>
                `;
                list.appendChild(div);
            });
        } else {
            list.innerHTML = '<div style="text-align:center;padding:20px;color:var(--text-light);font-size:0.9em">No history</div>';
        }
    } catch (e) {
        console.error('Load history error:', e);
    }
}

async function loadSession(sid) {
    try {
        const res = await fetch(`${API}/sessions/${sid}`);
        if (!res.ok) throw new Error('Session not found');
        
        const data = await res.json();
        
        // Update session
        sessionId = sid;
        saveSessionToStorage();
        updateSessionIndicator();
        
        console.log('Loaded session:', sessionId);
        
        // Clear and load messages
        const chat = document.getElementById('chat');
        chat.innerHTML = '';
        
        if (data.messages && data.messages.length > 0) {
            data.messages.forEach(m => {
                if (m.role === 'user') {
                    addMsg(m.content, 'user', false);
                } else {
                    addMsg(m.content, 'ai', false, m.sources);
                }
            });
        } else {
            chat.innerHTML = `
                <div class="empty">
                    <h2>Chat Loaded</h2>
                    <p>No messages yet. Start asking questions!</p>
                </div>
            `;
        }
        
        // Scroll to bottom
        chat.scrollTop = chat.scrollHeight;
        
        loadHistory();
    } catch (e) {
        console.error('Load session error:', e);
        toast('Error loading chat', 'error');
    }
}

async function newChat() {
    try {
        const res = await fetch(`${API}/sessions/new`, { method: 'POST' });
        const data = await res.json();
        
        // Update session
        sessionId = data.session_id;
        saveSessionToStorage();
        updateSessionIndicator();
        
        console.log('New chat created with session:', sessionId);
        
        // Clear current chat display
        const chat = document.getElementById('chat');
        chat.innerHTML = `
            <div class="empty">
                <h2>New Chat Started</h2>
                <p>Ask me anything about your documents</p>
            </div>
        `;
        
        loadHistory();
        toast('New chat created', 'success');
    } catch (e) {
        console.error('New chat error:', e);
        toast('Error creating chat', 'error');
    }
}

async function delSession(sid, e) {
    e.stopPropagation();
    if (!confirm('Delete this chat?')) return;
    
    try {
        await fetch(`${API}/sessions/${sid}`, { method: 'DELETE' });
        
        if (sessionId === sid) {
            sessionId = null;
            clearSavedSession();
            updateSessionIndicator();
            
            const chat = document.getElementById('chat');
            chat.innerHTML = `
                <div class="empty">
                    <h2>Welcome to DocuChat AI</h2>
                    <p>Upload documents and ask questions</p>
                </div>
            `;
        }
        
        toast('Chat deleted', 'success');
        loadHistory();
    } catch (e) {
        console.error('Delete session error:', e);
        toast('Error deleting chat', 'error');
    }
}

// ========== CHAT ==========
async function send() {
    const input = document.getElementById('input');
    const q = input.value.trim();
    
    if (!q) return;
    
    const chat = document.getElementById('chat');
    const empty = chat.querySelector('.empty');
    if (empty) empty.remove();
    
    addMsg(q, 'user', true);
    input.value = '';
    
    const tid = addTyping();
    
    const btn = document.getElementById('sendBtn');
    btn.disabled = true;
    
    try {
        console.log('Sending question:', q, 'Session:', sessionId);
        
        const requestBody = {
            question: q
        };
        
        if (sessionId) {
            requestBody.session_id = sessionId;
        }
        
        const res = await fetch(`${API}/ask`, {
            method: 'POST',
            headers: { 
                'Content-Type': 'application/json',
                'Accept': 'application/json'
            },
            body: JSON.stringify(requestBody)
        });
        
        if (!res.ok) {
            let errorMsg = 'Request failed';
            try {
                const errorData = await res.json();
                errorMsg = errorData.detail || errorData.message || `Server error: ${res.status}`;
            } catch (parseError) {
                errorMsg = `Server error: ${res.status}`;
            }
            throw new Error(errorMsg);
        }
        
        const data = await res.json();
        console.log('API Response - Session ID:', data.session_id);
        
        removeTyping(tid);
        
        // Update sessionId from response
        if (data.session_id) {
            sessionId = data.session_id;
            saveSessionToStorage();
            updateSessionIndicator();
            console.log('Updated sessionId to:', sessionId);
        }
        
        addMsg(data.answer, 'ai', true, data.sources);
        loadHistory();
        
    } catch (e) {
        removeTyping(tid);
        console.error('Send error:', e);
        toast(e.message || 'Connection error', 'error');
    } finally {
        btn.disabled = false;
    }
}

function addMsg(text, type, scroll, sources) {
    const chat = document.getElementById('chat');
    const div = document.createElement('div');
    div.className = `msg ${type}`;
    
    const avatar = document.createElement('div');
    avatar.className = `avatar ${type}`;
    avatar.textContent = type === 'ai' ? '🤖' : '👤';
    
    const content = document.createElement('div');
    content.className = 'msg-content';
    
    if (type === 'ai') {
        content.innerHTML = formatAI(text);
        
        if (sources && sources.length) {
            const srcDiv = document.createElement('div');
            srcDiv.style.marginTop = '8px';
            sources.forEach(s => {
                const tag = document.createElement('span');
                tag.className = 'source';
                tag.textContent = `📄 ${s}`;
                srcDiv.appendChild(tag);
            });
            content.appendChild(srcDiv);
        }
    } else {
        content.textContent = text;
    }
    
    div.appendChild(avatar);
    div.appendChild(content);
    chat.appendChild(div);
    
    if (scroll) {
        chat.scrollTop = chat.scrollHeight;
    }
}

function formatAI(text) {
    let paras = text.split('\n\n');
    let html = '';
    
    paras.forEach(p => {
        p = p.trim();
        if (!p) return;
        
        if (p.includes('\n- ')) {
            const items = p.split('\n- ').filter(x => x.trim());
            html += '<ul>';
            items.forEach(i => {
                if (i.trim()) html += `<li>${i.trim()}</li>`;
            });
            html += '</ul>';
        } else if (/^\d+\./.test(p)) {
            const items = p.split(/\n\d+\.\s+/).filter(x => x.trim());
            html += '<ol>';
            items.forEach(i => {
                if (i.trim()) html += `<li>${i.trim()}</li>`;
            });
            html += '</ol>';
        } else {
            html += `<p>${p}</p>`;
        }
    });
    
    return html || `<p>${text}</p>`;
}

function addTyping() {
    const chat = document.getElementById('chat');
    const div = document.createElement('div');
    div.className = 'msg ai';
    const id = 't' + Date.now();
    div.id = id;
    
    const avatar = document.createElement('div');
    avatar.className = 'avatar ai';
    avatar.textContent = '🤖';
    
    const typing = document.createElement('div');
    typing.className = 'typing';
    typing.innerHTML = '<div class="dot"></div><div class="dot"></div><div class="dot"></div>';
    
    div.appendChild(avatar);
    div.appendChild(typing);
    chat.appendChild(div);
    chat.scrollTop = chat.scrollHeight;
    
    return id;
}

function removeTyping(id) {
    const el = document.getElementById(id);
    if (el) el.remove();
}

// ========== TOAST ==========
function toast(msg, type) {
    const t = document.getElementById('toast');
    const message = typeof msg === 'string' ? msg : JSON.stringify(msg);
    t.textContent = message;
    t.className = type;
    t.style.display = 'block';
    
    setTimeout(() => {
        t.style.display = 'none';
    }, 3000);
}

// ========== SIDEBAR ==========
function toggleSidebar() {
    document.getElementById('sidebar').classList.toggle('open');
}

// ✅ ADD THIS TO THE BOTTOM OF script.js
async function checkHealth() {
    const badge = document.getElementById('badge');
    try {
        console.log("Checking health of:", API);
        const res = await fetch(`${API}/`); // Fetches root endpoint
        const data = await res.json();
        
        if (data.status === 'online') {
            badge.textContent = 'Online';
            badge.style.backgroundColor = '#4caf50'; // Green
            badge.classList.add('active');
        }
    } catch (e) {
        console.error("Health Check Failed:", e);
        badge.textContent = 'Offline';
        badge.style.backgroundColor = '#f44336'; // Red
        badge.classList.remove('active');
    }
}

// ✅ UPDATE window.onload to run the check
const originalOnload = window.onload;
window.onload = () => {
    if (originalOnload) originalOnload(); // Run existing setup
    checkHealth(); // Run our new check
};