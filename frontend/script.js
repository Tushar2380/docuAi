// YOUR RENDER URL
const API = 'https://docuchat-ai-bgjh.onrender.com';

let sessionId = null;
let theme = 'light';
let userId = null;

// ========== USER ID MANAGEMENT ==========
function getUserId() {
    if (userId) return userId;
    
    let stored = localStorage.getItem('docuchat_user_id');
    if (!stored) {
        stored = 'user_' + Date.now() + '_' + Math.random().toString(36).substr(2, 9);
        localStorage.setItem('docuchat_user_id', stored);
    }
    userId = stored;
    return userId;
}

// ========== SESSION MANAGEMENT ==========
function loadSavedSession() {
    try {
        const saved = localStorage.getItem('docuchat_session');
        if (saved) {
            sessionId = saved;
        }
    } catch (e) {
        console.log('No saved session');
    }
}

function saveSessionToStorage() {
    if (sessionId) {
        localStorage.setItem('docuchat_session', sessionId);
    }
}

function clearSavedSession() {
    localStorage.removeItem('docuchat_session');
}

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
    getUserId(); // Initialize user ID
    loadSavedSession();
    loadFiles();
    loadHistory();
    setupUpload();
    updateSessionIndicator();
    checkHealth();
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
    
    for (let file of files) {
        if (!file.name.match(/\.(pdf|docx|doc)$/i)) continue;
        
        const form = new FormData();
        form.append('file', file);
        
        try {
            const res = await fetch(`${API}/upload`, {
                method: 'POST',
                headers: {
                    'user-id': getUserId()
                },
                body: form
            });
            
            if (res.ok) {
                ok++;
            } else {
                const err = await res.json();
                console.error('Upload failed:', err);
            }
        } catch (e) {
            console.error('Upload error:', e);
        }
    }
    
    document.getElementById('fileInput').value = '';
    
    if (ok > 0) {
        toast(`${ok} file(s) uploaded`, 'success');
        setTimeout(() => loadFiles(), 500);
    } else {
        toast('Upload failed', 'error');
    }
}

// ========== FILES ==========
async function loadFiles() {
    try {
        const res = await fetch(`${API}/files`, {
            headers: {
                'user-id': getUserId()
            }
        });
        
        const data = await res.json();
        
        const list = document.getElementById('fileList');
        const count = document.getElementById('fileCount');
        const clearBtn = document.getElementById('clearBtn');
        
        count.textContent = data.total || 0;
        
        if (data.files && data.files.length > 0) {
            list.innerHTML = '';
            data.files.forEach(f => {
                const div = document.createElement('div');
                div.className = 'item';
                div.innerHTML = `
                    <span class="item-text">${f.filename.endsWith('.pdf') ? '📄' : '📝'} ${f.filename}</span>
                    <span class="item-del" onclick="delFile('${f.file_id}')">×</span>
                `;
                list.appendChild(div);
            });
            clearBtn.style.display = 'block';
        } else {
            list.innerHTML = '<div style="text-align:center;padding:20px;color:var(--text-light);font-size:0.9em">No files</div>';
            clearBtn.style.display = 'none';
        }
    } catch (e) {
        console.error('Load files error:', e);
        toast('Backend offline', 'error');
    }
}

async function delFile(fid) {
    if (!confirm('Delete this file?')) return;
    
    try {
        await fetch(`${API}/files/${fid}`, {
            method: 'DELETE',
            headers: {
                'user-id': getUserId()
            }
        });
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
        await fetch(`${API}/clear`, {
            method: 'DELETE',
            headers: {
                'user-id': getUserId()
            }
        });
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
        const res = await fetch(`${API}/sessions`, {
            headers: {
                'user-id': getUserId()
            }
        });
        
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
        const res = await fetch(`${API}/sessions/${sid}`, {
            headers: {
                'user-id': getUserId()
            }
        });
        
        if (!res.ok) throw new Error('Session not found');
        
        const data = await res.json();
        
        sessionId = sid;
        saveSessionToStorage();
        updateSessionIndicator();
        
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
        }
        
        chat.scrollTop = chat.scrollHeight;
        loadHistory();
        
        // Close sidebar on mobile after loading
        if (window.innerWidth <= 768) {
            document.getElementById('sidebar').classList.remove('open');
        }
    } catch (e) {
        console.error('Load session error:', e);
        toast('Error loading chat', 'error');
    }
}

async function newChat() {
    try {
        const res = await fetch(`${API}/sessions/new`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                user_id: getUserId(),
                question: "",
                session_id: null
            })
        });
        
        const data = await res.json();
        
        sessionId = data.session_id;
        saveSessionToStorage();
        updateSessionIndicator();
        
        const chat = document.getElementById('chat');
        chat.innerHTML = `
            <div class="empty">
                <h2>New Chat Started</h2>
                <p>Ask me anything about your documents</p>
            </div>
        `;
        
        loadHistory();
        toast('New chat created', 'success');
        
        // Close sidebar on mobile
        if (window.innerWidth <= 768) {
            document.getElementById('sidebar').classList.remove('open');
        }
    } catch (e) {
        console.error('New chat error:', e);
        toast('Error creating chat', 'error');
    }
}

async function delSession(sid, e) {
    e.stopPropagation();
    if (!confirm('Delete this chat?')) return;
    
    try {
        await fetch(`${API}/sessions/${sid}`, {
            method: 'DELETE',
            headers: {
                'user-id': getUserId()
            }
        });
        
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
        const requestBody = {
            question: q,
            user_id: getUserId(),
            session_id: sessionId
        };
        
        const res = await fetch(`${API}/ask`, {
            method: 'POST',
            headers: { 
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(requestBody)
        });
        
        if (!res.ok) {
            const errorData = await res.json();
            throw new Error(errorData.detail || 'Request failed');
        }
        
        const data = await res.json();
        
        removeTyping(tid);
        
        if (data.session_id) {
            sessionId = data.session_id;
            saveSessionToStorage();
            updateSessionIndicator();
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

// ========== HEALTH CHECK ==========
async function checkHealth() {
    try {
        const res = await fetch(`${API}/`);
        const data = await res.json();
        
        if (data.status === 'online') {
            console.log('Backend online:', data);
        }
    } catch (e) {
        console.error('Health check failed:', e);
        toast('Backend offline - may take a minute to wake up', 'error');
    }
}