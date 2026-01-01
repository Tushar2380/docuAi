const API = 'https://docuchat-ai-bgjh.onrender.com';

let sessionId = null;
let userId = null;

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

function saveSession() {
    if (sessionId) localStorage.setItem('docuchat_session', sessionId);
}

function loadSession() {
    sessionId = localStorage.getItem('docuchat_session');
}

function updateBadge() {
    const badge = document.getElementById('badge');
    badge.textContent = sessionId ? 'In Chat' : 'Ready';
    badge.className = sessionId 
        ? 'ml-auto px-3 py-1 text-xs font-medium rounded-full bg-green-500 text-white'
        : 'ml-auto px-3 py-1 text-xs font-medium rounded-full bg-gray-200 dark:bg-gray-700 text-gray-700 dark:text-gray-300';
}

window.onload = () => {
    getUserId();
    loadSession();
    loadFiles();
    loadHistory();
    setupUpload();
    updateBadge();
};

function toggleTheme() {
    const html = document.documentElement;
    const icon = document.getElementById('themeIcon');
    const text = document.getElementById('themeText');
    
    if (html.classList.contains('dark')) {
        html.classList.remove('dark');
        icon.textContent = '🌙';
        text.textContent = 'Dark Mode';
    } else {
        html.classList.add('dark');
        icon.textContent = '☀️';
        text.textContent = 'Light Mode';
    }
}

function setupUpload() {
    const box = document.getElementById('uploadBox');
    const input = document.getElementById('fileInput');
    
    box.onclick = () => input.click();
    
    box.ondragover = (e) => {
        e.preventDefault();
        box.classList.add('border-primary', 'bg-primary/10');
    };
    
    box.ondragleave = () => {
        box.classList.remove('border-primary', 'bg-primary/10');
    };
    
    box.ondrop = (e) => {
        e.preventDefault();
        box.classList.remove('border-primary', 'bg-primary/10');
        upload(e.dataTransfer.files);
    };
    
    input.onchange = (e) => upload(e.target.files);
}

async function upload(files) {
    if (!files.length) return;
    
    toast('Uploading files...', 'info');
    let ok = 0;
    
    for (let file of files) {
        if (!file.name.match(/\.(pdf|docx|doc)$/i)) continue;
        
        const form = new FormData();
        form.append('file', file);
        
        try {
            const res = await fetch(`${API}/upload`, {
                method: 'POST',
                headers: { 'user-id': getUserId() },
                body: form
            });
            
            if (res.ok) ok++;
        } catch (e) {
            console.error(e);
        }
    }
    
    document.getElementById('fileInput').value = '';
    
    if (ok > 0) {
        toast(`${ok} file(s) uploaded successfully`, 'success');
        setTimeout(loadFiles, 500);
    } else {
        toast('Upload failed', 'error');
    }
}

async function loadFiles() {
    try {
        const res = await fetch(`${API}/files`, {
            headers: { 'user-id': getUserId() }
        });
        const data = await res.json();
        
        const list = document.getElementById('fileList');
        const count = document.getElementById('fileCount');
        const clearBtn = document.getElementById('clearBtn');
        
        count.textContent = data.total || 0;
        
        if (data.files && data.files.length > 0) {
            list.innerHTML = data.files.map(f => `
                <div class="flex items-center justify-between p-3 bg-gray-50 dark:bg-gray-700 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-600 transition-colors">
                    <span class="text-sm truncate flex-1">${f.filename.endsWith('.pdf') ? '📄' : '📝'} ${f.filename}</span>
                    <button onclick="delFile('${f.file_id}')" class="ml-2 text-red-500 hover:text-red-700 font-bold">×</button>
                </div>
            `).join('');
            clearBtn.classList.remove('hidden');
        } else {
            list.innerHTML = '<div class="text-center py-8 text-sm text-gray-500">No files uploaded</div>';
            clearBtn.classList.add('hidden');
        }
    } catch (e) {
        console.error(e);
    }
}

async function delFile(fid) {
    if (!confirm('Delete this file?')) return;
    
    try {
        await fetch(`${API}/files/${fid}`, {
            method: 'DELETE',
            headers: { 'user-id': getUserId() }
        });
        toast('File deleted', 'success');
        loadFiles();
    } catch (e) {
        toast('Error deleting file', 'error');
    }
}

async function clearAll() {
    if (!confirm('Clear all files?')) return;
    
    try {
        await fetch(`${API}/clear`, {
            method: 'DELETE',
            headers: { 'user-id': getUserId() }
        });
        toast('All files cleared', 'success');
        loadFiles();
    } catch (e) {
        toast('Error', 'error');
    }
}

async function loadHistory() {
    try {
        const res = await fetch(`${API}/sessions`, {
            headers: { 'user-id': getUserId() }
        });
        const data = await res.json();
        
        const list = document.getElementById('historyList');
        
        if (data.sessions && data.sessions.length > 0) {
            list.innerHTML = data.sessions.map(s => `
                <div class="flex items-center justify-between p-3 bg-gray-50 dark:bg-gray-700 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-600 transition-colors ${s.id === sessionId ? 'ring-2 ring-primary' : ''}">
                    <button onclick="loadChatSession('${s.id}')" class="text-sm truncate flex-1 text-left">${s.title}</button>
                    <button onclick="delSession('${s.id}', event)" class="ml-2 text-red-500 hover:text-red-700 font-bold">×</button>
                </div>
            `).join('');
        } else {
            list.innerHTML = '<div class="text-center py-8 text-sm text-gray-500">No chat history</div>';
        }
    } catch (e) {
        console.error(e);
    }
}

async function loadChatSession(sid) {
    try {
        const res = await fetch(`${API}/sessions/${sid}`, {
            headers: { 'user-id': getUserId() }
        });
        
        if (!res.ok) return;
        
        const data = await res.json();
        sessionId = sid;
        saveSession();
        updateBadge();
        
        const chat = document.getElementById('chat');
        chat.innerHTML = '<div class="max-w-4xl mx-auto space-y-4"></div>';
        const container = chat.querySelector('div');
        
        if (data.messages && data.messages.length > 0) {
            data.messages.forEach(m => {
                addMsg(m.content, m.role === 'user' ? 'user' : 'ai', false, m.sources);
            });
        }
        
        chat.scrollTop = chat.scrollHeight;
        loadHistory();
        
        if (window.innerWidth < 1024) toggleSidebar();
    } catch (e) {
        toast('Error loading chat', 'error');
    }
}

async function newChat() {
    try {
        const res = await fetch(`${API}/sessions/new`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ user_id: getUserId(), question: "", session_id: null })
        });
        
        const data = await res.json();
        sessionId = data.session_id;
        saveSession();
        updateBadge();
        
        document.getElementById('chat').innerHTML = `
            <div class="max-w-4xl mx-auto h-full flex items-center justify-center">
                <div class="text-center">
                    <div class="text-6xl mb-4">✨</div>
                    <h2 class="text-2xl font-bold text-gray-800 dark:text-white mb-2">New Chat Started</h2>
                    <p class="text-gray-600 dark:text-gray-400">Ask me anything about your documents</p>
                </div>
            </div>
        `;
        
        loadHistory();
        toast('New chat created', 'success');
        
        if (window.innerWidth < 1024) toggleSidebar();
    } catch (e) {
        toast('Error creating chat', 'error');
    }
}

async function delSession(sid, e) {
    e.stopPropagation();
    if (!confirm('Delete this chat?')) return;
    
    try {
        await fetch(`${API}/sessions/${sid}`, {
            method: 'DELETE',
            headers: { 'user-id': getUserId() }
        });
        
        if (sessionId === sid) {
            sessionId = null;
            localStorage.removeItem('docuchat_session');
            updateBadge();
            
            document.getElementById('chat').innerHTML = `
                <div class="max-w-4xl mx-auto h-full flex items-center justify-center">
                    <div class="text-center">
                        <div class="text-6xl mb-4">💬</div>
                        <h2 class="text-2xl font-bold text-gray-800 dark:text-white mb-2">Welcome Back</h2>
                        <p class="text-gray-600 dark:text-gray-400">Upload documents and start chatting</p>
                    </div>
                </div>
            `;
        }
        
        toast('Chat deleted', 'success');
        loadHistory();
    } catch (e) {
        toast('Error', 'error');
    }
}

async function send() {
    const input = document.getElementById('input');
    const q = input.value.trim();
    
    if (!q) return;
    
    const chat = document.getElementById('chat');
    if (!chat.querySelector('.space-y-4')) {
        chat.innerHTML = '<div class="max-w-4xl mx-auto space-y-4"></div>';
    }
    
    addMsg(q, 'user', true);
    input.value = '';
    
    const tid = addTyping();
    const btn = document.getElementById('sendBtn');
    btn.disabled = true;
    
    try {
        const res = await fetch(`${API}/ask`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ question: q, user_id: getUserId(), session_id: sessionId })
        });
        
        if (!res.ok) throw new Error('Request failed');
        
        const data = await res.json();
        
        removeTyping(tid);
        
        if (data.session_id) {
            sessionId = data.session_id;
            saveSession();
            updateBadge();
        }
        
        addMsg(data.answer, 'ai', true, data.sources);
        loadHistory();
    } catch (e) {
        removeTyping(tid);
        toast('Error getting response', 'error');
    } finally {
        btn.disabled = false;
    }
}

function addMsg(text, type, scroll, sources) {
    const chat = document.getElementById('chat');
    const container = chat.querySelector('.space-y-4') || chat;
    
    const div = document.createElement('div');
    div.className = `flex gap-3 ${type === 'user' ? 'flex-row-reverse' : ''}`;
    
    const avatar = document.createElement('div');
    avatar.className = `w-10 h-10 rounded-full flex items-center justify-center text-xl flex-shrink-0 ${
        type === 'ai' ? 'bg-primary text-white' : 'bg-gray-300 dark:bg-gray-600'
    }`;
    avatar.textContent = type === 'ai' ? '🤖' : '👤';
    
    const content = document.createElement('div');
    content.className = `max-w-2xl p-4 rounded-2xl ${
        type === 'ai' 
            ? 'bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700' 
            : 'bg-primary text-white'
    }`;
    
    if (type === 'ai') {
        content.innerHTML = formatAI(text);
        
        if (sources && sources.length) {
            const srcDiv = document.createElement('div');
            srcDiv.className = 'mt-3 flex flex-wrap gap-2';
            sources.forEach(s => {
                const tag = document.createElement('span');
                tag.className = 'px-2 py-1 text-xs bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-300 rounded-full';
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
    container.appendChild(div);
    
    if (scroll) chat.scrollTop = chat.scrollHeight;
}

function formatAI(text) {
    return text.split('\n\n').map(p => {
        p = p.trim();
        if (!p) return '';
        
        if (p.includes('\n- ')) {
            const items = p.split('\n- ').filter(x => x.trim());
            return '<ul class="list-disc ml-4 space-y-1">' + items.map(i => `<li>${i.trim()}</li>`).join('') + '</ul>';
        } else if (/^\d+\./.test(p)) {
            const items = p.split(/\n\d+\.\s+/).filter(x => x.trim());
            return '<ol class="list-decimal ml-4 space-y-1">' + items.map(i => `<li>${i.trim()}</li>`).join('') + '</ol>';
        }
        return `<p class="mb-3">${p}</p>`;
    }).join('');
}

function addTyping() {
    const chat = document.getElementById('chat');
    const container = chat.querySelector('.space-y-4') || chat;
    
    const div = document.createElement('div');
    div.className = 'flex gap-3';
    div.id = 't' + Date.now();
    
    div.innerHTML = `
        <div class="w-10 h-10 rounded-full bg-primary text-white flex items-center justify-center text-xl">🤖</div>
        <div class="flex gap-1 p-4 bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-2xl">
            <div class="w-2 h-2 bg-gray-400 rounded-full animate-bounce"></div>
            <div class="w-2 h-2 bg-gray-400 rounded-full animate-bounce" style="animation-delay: 0.2s"></div>
            <div class="w-2 h-2 bg-gray-400 rounded-full animate-bounce" style="animation-delay: 0.4s"></div>
        </div>
    `;
    
    container.appendChild(div);
    chat.scrollTop = chat.scrollHeight;
    return div.id;
}

function removeTyping(id) {
    document.getElementById(id)?.remove();
}

function toast(msg, type) {
    const t = document.getElementById('toast');
    const colors = {
        success: 'bg-green-500',
        error: 'bg-red-500',
        info: 'bg-blue-500'
    };
    
    t.textContent = msg;
    t.className = `fixed top-4 right-4 px-6 py-3 rounded-lg shadow-lg text-white z-50 ${colors[type]} transform transition-transform duration-300`;
    t.style.transform = 'translateX(0)';
    
    setTimeout(() => {
        t.style.transform = 'translateX(500px)';
    }, 3000);
}

function toggleSidebar() {
    const sidebar = document.getElementById('sidebar');
    sidebar.classList.toggle('-translate-x-full');
}