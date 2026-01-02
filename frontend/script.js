const API = 'https://docuchat-ai-bgjh.onrender.com';

let sessionId = null;
let userId = null;

// --- USER IDENTITY ---
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

// --- SESSION MANAGEMENT ---
function saveSession() {
    if (sessionId) localStorage.setItem('docuchat_session', sessionId);
}

function loadSession() {
    sessionId = localStorage.getItem('docuchat_session');
}

function updateBadge() {
    const badge = document.getElementById('badge');
    if (!badge) return; // Safety check
    
    badge.textContent = sessionId ? 'Online' : 'Ready';
    badge.className = sessionId 
        ? 'ml-auto px-3 py-1 text-xs font-medium rounded-full bg-green-500 text-white shadow-sm'
        : 'ml-auto px-3 py-1 text-xs font-medium rounded-full bg-gray-200 dark:bg-gray-700 text-gray-700 dark:text-gray-300';
}

// --- INITIALIZATION ---
window.onload = () => {
    getUserId();
    loadSession();
    loadFiles();
    loadHistory();
    setupUpload();
    updateBadge();
    
    // Check if we are in a fresh state and welcome the user
    if (!sessionId) {
        const chat = document.getElementById('chat');
        // Keep the welcome screen in HTML, but ensure badge is correct
        updateBadge();
    }
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

// --- UPLOAD LOGIC (FIXED) ---
function setupUpload() {
    const box = document.getElementById('fileInput'); // The hidden input
    // We bind the button in HTML via onclick, so we just need drag/drop if you add a drop zone later
    // For now, the input change event is key
    const input = document.getElementById('fileInput');
    input.onchange = (e) => upload(e.target.files);
}

async function upload(files) {
    if (!files || !files.length) return;
    
    // 1. SHOW THE PROGRESS BAR (This was missing!)
    const progress = document.getElementById('uploadProgress');
    const status = document.getElementById('uploadStatus');
    
    if (progress) {
        progress.classList.remove('hidden');
        status.textContent = `Uploading ${files.length} file(s)...`;
    }
    
    toast('Starting upload...', 'info');

    let ok = 0;
    
    for (let file of files) {
        if (!file.name.match(/\.(pdf|docx|doc)$/i)) {
            toast(`Skipped ${file.name} (not a PDF/DOCX)`, 'error');
            continue;
        }
        
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
    
    // 2. RESET INPUT & HIDE PROGRESS
    document.getElementById('fileInput').value = '';
    if (progress) progress.classList.add('hidden');
    
    // 3. SUCCESS MESSAGE & GREETING
    if (ok > 0) {
        toast(`${ok} file(s) uploaded successfully!`, 'success');
        setTimeout(loadFiles, 500);
        
        // ✨ INTERACTIVE: AI Greets you after upload
        if (!sessionId) {
            await newChat(true); // Start chat but don't clear history yet
        }
        // Send a system message into the chat
        addMsg(`✅ I have processed ${ok} file(s). You can now ask me questions about them!`, 'ai', true);
    } else {
        toast('Upload failed. Please check your connection.', 'error');
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
                <div class="flex items-center justify-between p-2 bg-gray-50 dark:bg-gray-700/50 rounded-lg group">
                    <div class="flex items-center gap-2 overflow-hidden">
                        <span class="text-lg">${f.filename.endsWith('.pdf') ? '📄' : '📝'}</span>
                        <span class="text-sm text-gray-700 dark:text-gray-300 truncate">${f.filename}</span>
                    </div>
                    <button onclick="delFile('${f.file_id}')" class="text-gray-400 hover:text-red-500 opacity-0 group-hover:opacity-100 transition-opacity">
                        <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"/></svg>
                    </button>
                </div>
            `).join('');
            clearBtn.classList.remove('hidden');
        } else {
            list.innerHTML = '<div class="text-center py-4 text-xs text-gray-400 italic">No files yet</div>';
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
    if (!confirm('Clear all files? This cannot be undone.')) return;
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

// --- CHAT LOGIC ---

async function loadHistory() {
    try {
        const res = await fetch(`${API}/sessions`, {
            headers: { 'user-id': getUserId() }
        });
        const data = await res.json();
        
        const list = document.getElementById('historyList');
        
        if (data.sessions && data.sessions.length > 0) {
            list.innerHTML = data.sessions.map(s => `
                <button onclick="loadChatSession('${s.id}')" class="w-full text-left p-3 rounded-lg text-sm transition-colors ${s.id === sessionId ? 'bg-primary/10 text-primary font-medium' : 'text-gray-600 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-700'}">
                    <div class="truncate">${s.title || 'New Chat'}</div>
                    <div class="text-[10px] opacity-60 mt-1">${s.created || ''}</div>
                </button>
            `).join('');
        } else {
            list.innerHTML = '<div class="text-center py-4 text-xs text-gray-400 italic">No history</div>';
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
        // Reset chat container
        chat.innerHTML = '<div class="max-w-4xl mx-auto space-y-4"></div>';
        
        if (data.messages && data.messages.length > 0) {
            data.messages.forEach(m => {
                addMsg(m.content, m.role === 'user' ? 'user' : 'ai', false, m.sources);
            });
        }
        
        chat.scrollTop = chat.scrollHeight;
        loadHistory();
        
        // Mobile: auto-close sidebar on select
        if (window.innerWidth < 1024) {
            const sidebar = document.getElementById('sidebar');
            sidebar.classList.add('-translate-x-full');
        }
    } catch (e) {
        toast('Error loading chat', 'error');
    }
}

async function newChat(silent = false) {
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
        
        const chat = document.getElementById('chat');
        // Clear the "Welcome" screen and prepare for messages
        chat.innerHTML = '<div class="max-w-4xl mx-auto space-y-4 pt-4"></div>';
        
        if (!silent) {
            // ✨ INTERACTIVE: Immediate Greeting
            addMsg("Hello! 👋 I am your Document Assistant.\n\nUpload a PDF or DOCX file, and I can summarize it or answer your questions.", 'ai', false);
        }
        
        loadHistory();
        if (!silent) toast('New chat started', 'success');
        
        // Mobile: close sidebar
        if (window.innerWidth < 1024) {
            document.getElementById('sidebar').classList.add('-translate-x-full');
        }
    } catch (e) {
        toast('Error creating chat', 'error');
    }
}

async function send() {
    const input = document.getElementById('input');
    const q = input.value.trim();
    
    if (!q) return;
    
    // Ensure chat container exists (if sending from empty state)
    const chat = document.getElementById('chat');
    if (!chat.querySelector('.space-y-4')) {
        chat.innerHTML = '<div class="max-w-4xl mx-auto space-y-4 pt-4"></div>';
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
        // Keep focus on input for rapid chatting
        setTimeout(() => input.focus(), 100);
    }
}

// --- UI HELPERS ---

function addMsg(text, type, scroll, sources) {
    const chat = document.getElementById('chat');
    const container = chat.querySelector('.space-y-4') || chat;
    
    const div = document.createElement('div');
    div.className = `flex gap-4 ${type === 'user' ? 'flex-row-reverse' : ''} animate-fade-in`;
    
    // Avatar
    const avatar = document.createElement('div');
    avatar.className = `w-8 h-8 rounded-full flex items-center justify-center text-sm flex-shrink-0 shadow-sm ${
        type === 'ai' ? 'bg-gradient-to-br from-indigo-500 to-purple-600 text-white' : 'bg-gray-200 dark:bg-gray-700 text-gray-600'
    }`;
    avatar.innerHTML = type === 'ai' ? '🤖' : '👤';
    
    // Content Bubble
    const content = document.createElement('div');
    content.className = `max-w-[85%] lg:max-w-[75%] p-4 rounded-2xl shadow-sm text-sm leading-relaxed ${
        type === 'ai' 
            ? 'bg-white dark:bg-gray-800 border border-gray-100 dark:border-gray-700 text-gray-800 dark:text-gray-200 rounded-tl-none' 
            : 'bg-primary text-white rounded-tr-none'
    }`;
    
    if (type === 'ai') {
        content.innerHTML = formatAI(text);
        
        if (sources && sources.length) {
            const srcDiv = document.createElement('div');
            srcDiv.className = 'mt-3 pt-3 border-t border-gray-100 dark:border-gray-700 flex flex-wrap gap-2';
            sources.forEach(s => {
                srcDiv.innerHTML += `<span class="inline-flex items-center px-2 py-1 rounded text-[10px] font-medium bg-gray-100 dark:bg-gray-700/50 text-gray-600 dark:text-gray-400">📄 ${s}</span>`;
            });
            content.appendChild(srcDiv);
        }
    } else {
        content.textContent = text;
    }
    
    div.appendChild(avatar);
    div.appendChild(content);
    container.appendChild(div);
    
    if (scroll) {
        setTimeout(() => {
            chat.scrollTo({ top: chat.scrollHeight, behavior: 'smooth' });
        }, 100);
    }
}

function formatAI(text) {
    // Basic Markdown-ish parsing
    let formatted = text
        .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>') // Bold
        .replace(/`([^`]+)`/g, '<code class="bg-gray-100 dark:bg-gray-900 px-1 rounded text-pink-500">$1</code>'); // Code inline

    return formatted.split('\n\n').map(p => {
        p = p.trim();
        if (!p) return '';
        
        if (p.startsWith('- ') || p.startsWith('• ')) {
            const items = p.split(/\n[-•]\s/).filter(x => x.trim());
            return '<ul class="list-disc ml-4 space-y-1 mb-2">' + items.map(i => `<li>${i.replace(/^[-•]\s/, '')}</li>`).join('') + '</ul>';
        } else if (/^\d+\./.test(p)) {
            // Try to catch numbered lists
            return `<div class="mb-3">${p.replace(/\n/g, '<br>')}</div>`;
        }
        return `<p class="mb-3 last:mb-0">${p}</p>`;
    }).join('');
}

function addTyping() {
    const chat = document.getElementById('chat');
    const container = chat.querySelector('.space-y-4') || chat;
    
    const div = document.createElement('div');
    div.className = 'flex gap-4 animate-pulse';
    div.id = 'typingIndicator';
    
    div.innerHTML = `
        <div class="w-8 h-8 rounded-full bg-gradient-to-br from-indigo-500 to-purple-600 text-white flex items-center justify-center text-sm">🤖</div>
        <div class="bg-white dark:bg-gray-800 border border-gray-100 dark:border-gray-700 p-4 rounded-2xl rounded-tl-none flex gap-1 items-center h-10">
            <div class="w-1.5 h-1.5 bg-gray-400 rounded-full animate-bounce"></div>
            <div class="w-1.5 h-1.5 bg-gray-400 rounded-full animate-bounce" style="animation-delay: 0.1s"></div>
            <div class="w-1.5 h-1.5 bg-gray-400 rounded-full animate-bounce" style="animation-delay: 0.2s"></div>
        </div>
    `;
    
    container.appendChild(div);
    chat.scrollTo({ top: chat.scrollHeight, behavior: 'smooth' });
    return div.id;
}

function removeTyping(id) {
    const el = document.getElementById(id);
    if (el) el.remove();
}

function toast(msg, type = 'info') {
    const t = document.getElementById('toast');
    if (!t) return;
    
    const colors = {
        success: 'bg-emerald-500',
        error: 'bg-red-500',
        info: 'bg-blue-500'
    };
    
    t.textContent = msg;
    t.className = `fixed top-4 right-4 px-6 py-3 rounded-lg shadow-xl text-white z-[60] transform transition-all duration-300 ${colors[type] || colors.info}`;
    
    // Slight delay to ensure transition works
    requestAnimationFrame(() => {
        t.style.transform = 'translateX(0)';
    });
    
    // Hide after 3 seconds
    setTimeout(() => {
        t.style.transform = 'translateX(120%)';
    }, 3000);
}

function toggleSidebar() {
    const sidebar = document.getElementById('sidebar');
    if (sidebar.classList.contains('-translate-x-full')) {
        sidebar.classList.remove('-translate-x-full'); // Show
    } else {
        sidebar.classList.add('-translate-x-full'); // Hide
    }
}