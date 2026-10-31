// ===== INIT =====
async function init() {
    await loadModels();
    setupEventListeners();
    initProjectWorkspace();
    updateUILanguage(); // Set default language on page load
}

async function loadModels() {
    try {
        const res = await fetch('/api/models');
        const data = await res.json();
        if (data.models && data.models.length > 0) {
            modelSelect.innerHTML = data.models.map(m => {
                const lowerM = m.toLowerCase();
                const isEmbedding = lowerM.includes('embed') || lowerM.includes('minilm') || lowerM.includes('bge-');
                return `<option value="${m}" ${isEmbedding ? 'disabled style="color: #888; font-style: italic; background-color: #222;"' : ''}>${m}${isEmbedding ? ' (embedding)' : ''}</option>`;
            }).join('');

            // Select the first non-disabled option by default
            const enabledOptions = Array.from(modelSelect.options).filter(opt => !opt.disabled);
            if (enabledOptions.length > 0) {
                modelSelect.value = enabledOptions[0].value;
                if (!state.doc.model) state.doc.model = modelSelect.value;
                if (!state.chat.model) state.chat.model = modelSelect.value;
            }
        }
    } catch (e) {
        console.warn('Could not load models:', e);
    }
}

// ===== TAB SWITCHING =====
async function switchTab(tab) {
    state.activeTab = tab;

    // Sidebar tabs
    document.querySelectorAll('.tab-btn').forEach(b => b.classList.toggle('active', b.dataset.tab === tab));
    document.querySelectorAll('.sidebar .tab-content').forEach(c => c.classList.toggle('active', c.id === `tab-${tab}`));

    // Main content tabs
    document.querySelectorAll('.main-tab').forEach(c => c.classList.toggle('active', c.id === `main-tab-${tab}`));

    // Close mobile sidebar on tab change
    const sidebar = document.querySelector('.sidebar');
    const overlay = $('sidebarOverlay');
    if (sidebar && overlay) {
        sidebar.classList.remove('open');
        overlay.classList.remove('show');
    }

    // Auto initialize chat session if switching to chat and no session exists
    if (tab === 'chat' && !state.chat.sessionId) {
        await initChatSession();
    }

    // Update chat input
    updateChatInput();
}

function updateChatInput() {
    const tab = state.activeTab;
    if (tab === 'project') {
        chatInputContainer.style.display = 'none';
        return;
    }
    const isDoc = tab === 'doc';
    const s = isDoc ? state.doc : state.chat;
    const hasSession = isDoc ? !!state.doc.sessionId : !!state.chat.sessionId;
    const t = translations[state.language];

    if (hasSession) {
        chatInputContainer.style.display = 'block';
        chatInput.disabled = false;
        sendBtn.disabled = false;
        if (tab === 'chat') {
            chatInput.placeholder = t.chatPlaceholder;
        } else {
            chatInput.placeholder = t.docChatPlaceholder;
        }
        chatInput.focus();
    } else {
        chatInputContainer.style.display = 'none';
        chatInput.disabled = true;
        sendBtn.disabled = true;
    }
}

// ===== EVENT LISTENERS =====
function setupEventListeners() {
    // Mobile sidebar toggle
    const toggleBtn = $('mobileSidebarToggle');
    const sidebarOverlay = $('sidebarOverlay');
    const sidebar = document.querySelector('.sidebar');

    if (toggleBtn && sidebarOverlay && sidebar) {
        toggleBtn.addEventListener('click', () => {
            sidebar.classList.toggle('open');
            sidebarOverlay.classList.toggle('show');
        });

        sidebarOverlay.addEventListener('click', () => {
            sidebar.classList.remove('open');
            sidebarOverlay.classList.remove('show');
        });
    }

    // Tab switching
    document.querySelectorAll('.tab-btn').forEach(btn => {
        btn.addEventListener('click', () => switchTab(btn.dataset.tab));
    });

    // Language change
    languageSelect.addEventListener('change', (e) => {
        state.language = e.target.value;
        updateUILanguage();
    });

    // Upload
    uploadArea.addEventListener('click', () => fileInput.click());
    uploadArea.addEventListener('dragover', (e) => { e.preventDefault(); uploadArea.classList.add('dragover'); });
    uploadArea.addEventListener('dragleave', () => uploadArea.classList.remove('dragover'));
    uploadArea.addEventListener('drop', (e) => {
        e.preventDefault();
        uploadArea.classList.remove('dragover');
        if (e.dataTransfer.files.length > 0) handleFileUploads(e.dataTransfer.files);
    });
    fileInput.addEventListener('change', (e) => {
        if (e.target.files.length > 0) handleFileUploads(e.target.files);
    });

    // Chat
    sendBtn.addEventListener('click', sendMessage);
    chatInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendMessage(); }
    });
    chatInput.addEventListener('input', autoResizeTextarea);

    // Clear sessions
    clearSessionBtn.addEventListener('click', clearDocSession);
    clearChatSessionBtn.addEventListener('click', clearChatSession);

    // Quick actions - doc
    document.querySelectorAll('#tab-doc .quick-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            chatInput.value = btn.dataset.question;
            sendMessage();
        });
    });

    // Quick actions - chat
    document.querySelectorAll('#chatQuickActions .quick-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            chatInput.value = btn.dataset.chatQuestion;
            sendMessage();
        });
    });
}

// ===== SEND MESSAGE =====
async function sendMessage() {
    const question = chatInput.value.trim();
    if (!question) return;

    const tab = state.activeTab;
    const isDoc = tab === 'doc';
    const s = isDoc ? state.doc : state.chat;

    if (s.isProcessing || !s.sessionId) return;
    s.isProcessing = true;

    chatInput.disabled = true;
    sendBtn.disabled = true;

    const targetMessages = isDoc ? docChatMessages : chatChatMessages;
    const addMsg = isDoc ? addDocMessage : addChatMessage;

    addMsg('user', question);
    chatInput.value = '';
    autoResizeTextarea();
    showTypingIndicator(targetMessages);

    try {
        const endpoint = isDoc ? '/api/doc/chat' : '/api/chat/chat';
        const res = await fetch(endpoint, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                session_id: s.sessionId,
                question: question,
                model: modelSelect.value,
                language: state.language
            })
        });

        removeTypingIndicator();

        if (!res.ok) {
            const data = await res.json();
            throw new Error(data.error || 'Chat failed');
        }

        // create bubble for assistant
        const msgDiv = document.createElement('div');
        msgDiv.className = `message assistant`;
        msgDiv.innerHTML = `
            <div class="message-avatar"><span class="material-symbols-rounded">smart_toy</span></div>
            <div class="message-bubble"></div>
        `;
        targetMessages.appendChild(msgDiv);
        const bubble = msgDiv.querySelector('.message-bubble');

        await readStream(res, bubble, '');
    } catch (err) {
        removeTypingIndicator();
        const errorLabel = state.language === 'vi' ? '❌ **Lỗi:**' : '❌ **Error:**';
        const msgDiv = document.createElement('div');
        msgDiv.className = `message assistant`;
        msgDiv.innerHTML = `
            <div class="message-avatar"><span class="material-symbols-rounded">smart_toy</span></div>
            <div class="message-bubble">${formatMessage(`${errorLabel} ${err.message}`)}</div>
        `;
        targetMessages.appendChild(msgDiv);
        showToast('❌', err.message);
    } finally {
        s.isProcessing = false;
        chatInput.disabled = false;
        sendBtn.disabled = false;
        chatInput.focus();
    }
}

// ===== LANGUAGE MANAGEMENT =====
const translations = {
    en: {
        uploadText: 'Drag & drop files here',
        uploadSubtext: 'or click to select files',
        uploadFormats: 'PDF, DOCX, TXT, MD, PNG, JPG, ...',
        processing: 'Processing...',
        analyzing: 'Analyzing with AI...',
        completed: '✅ Complete!',
        analyzed: '✅ Analyzed',
        docTab: 'Documents',
        chatTab: 'Chat',
        projectTab: 'Projects',
        chatPlaceholder: 'Type your question...',
        docChatPlaceholder: 'Ask about the document...',
        uploadError: 'File too large. Limit 50MB.',
        selectFileError: 'Please select a file first!',
        clearSession: 'Cleared. Upload new file.',
        clearChatSession: 'Cleared chat history.',
        welcomeDoc: 'Document Analysis',
        welcomeDocDesc: 'Upload files to analyze and ask questions',
        welcomeChat: 'Free Chat',
        welcomeChatDesc: 'Ask anything you want with AI',
        welcomeProject: 'Project Workspace',
        welcomeProjectDesc: 'Open or upload a folder to browse and generate code',
        agentMode: 'Agent Mode (ReAct)'
    },
    vi: {
        uploadText: 'Kéo thả file vào đây',
        uploadSubtext: 'hoặc click để chọn file',
        uploadFormats: 'PDF, DOCX, TXT, MD, PNG, JPG, ...',
        processing: 'Đang xử lý...',
        analyzing: 'Đang phân tích với AI...',
        completed: '✅ Hoàn tất!',
        analyzed: '✅ Đã phân tích',
        docTab: 'Tài liệu',
        chatTab: 'Trò chuyện',
        projectTab: 'Dự án',
        chatPlaceholder: 'Nhập câu hỏi...',
        docChatPlaceholder: 'Nhập câu hỏi về tài liệu...',
        uploadError: 'File quá lớn. Giới hạn 50MB.',
        selectFileError: 'Vui lòng chọn file trước!',
        clearSession: 'Đã xóa. Upload file mới.',
        clearChatSession: 'Đã xóa lịch sử chat.',
        welcomeDoc: 'Phân tích tài liệu',
        welcomeDocDesc: 'Upload file để phân tích và đặt câu hỏi',
        welcomeChat: 'Trò chuyện tự do',
        welcomeChatDesc: 'Hỏi bất cứ điều gì bạn muốn với AI',
        welcomeProject: 'Không gian Dự án',
        welcomeProjectDesc: 'Mở hoặc upload một thư mục để duyệt code và sinh code',
        agentMode: 'Chế độ Agent (Tự động)'
    }
};

function updateUILanguage() {
    const lang = state.language;
    const t = translations[lang];

    // Update upload area
    if (document.querySelector('.upload-text')) document.querySelector('.upload-text').textContent = t.uploadText;
    if (document.querySelector('.upload-subtext')) document.querySelector('.upload-subtext').textContent = t.uploadSubtext;
    if (document.querySelector('.upload-formats')) document.querySelector('.upload-formats').textContent = t.uploadFormats;

    // Update tab labels
    const docTabBtn = document.querySelector('[data-tab="doc"] .tab-label');
    if (docTabBtn) docTabBtn.textContent = t.docTab;
    const chatTabBtn = document.querySelector('[data-tab="chat"] .tab-label');
    if (chatTabBtn) chatTabBtn.textContent = t.chatTab;
    const projectTabBtn = document.querySelector('[data-tab="project"] .tab-label');
    if (projectTabBtn) projectTabBtn.textContent = t.projectTab;



    // Update welcome screens
    const docWelcomeH2 = document.querySelector('#docWelcome h2');
    const docWelcomeP = document.querySelector('#docWelcome p');
    if (docWelcomeH2) docWelcomeH2.textContent = t.welcomeDoc;
    if (docWelcomeP) docWelcomeP.textContent = t.welcomeDocDesc;

    const chatWelcomeH2 = document.querySelector('#chatWelcome h2');
    const chatWelcomeP = document.querySelector('#chatWelcome p');
    if (chatWelcomeH2) chatWelcomeH2.textContent = t.welcomeChat;
    if (chatWelcomeP) chatWelcomeP.textContent = t.welcomeChatDesc;

    const projWelcomeH2 = document.querySelector('#projectWelcome h2');
    const projWelcomeP = document.querySelector('#projectWelcome p');
    if (projWelcomeH2) projWelcomeH2.textContent = t.welcomeProject;
    if (projWelcomeP) projWelcomeP.textContent = t.welcomeProjectDesc;

    const agentModeLabel = document.getElementById('agentModeLabel');
    if (agentModeLabel) {
        agentModeLabel.textContent = t.agentMode;
        agentModeLabel.title = lang === 'vi' ? 'Chế độ tự động chạy các công cụ (đọc, ghi file, chạy lệnh). Tắt đi để chat nhanh hơn.' : 'Automatically execute tools (read/write files, run commands). Turn off for faster chat.';
    }

    // Update chat input placeholder
    updateChatInput();
}

// ===== UTILITIES =====
async function readStream(response, messageBubbleElement, prefixText = "") {
    const reader = response.body.getReader();
    const decoder = new TextDecoder("utf-8");
    let fullText = "";
    let buffer = "";
    let pendingUpdate = false;

    // Batch DOM updates with requestAnimationFrame to avoid layout thrashing
    function scheduleDOMUpdate(container, wasAtBottom) {
        if (pendingUpdate) return; // already scheduled
        pendingUpdate = true;
        requestAnimationFrame(() => {
            messageBubbleElement.innerHTML = formatMessage(prefixText + fullText);
            if (container && wasAtBottom) {
                container.scrollTop = container.scrollHeight;
            }
            pendingUpdate = false;
        });
    }

    while (true) {
        const { value, done } = await reader.read();
        if (done) {
            // Final flush
            if (!pendingUpdate) {
                messageBubbleElement.innerHTML = formatMessage(prefixText + fullText);
            }
            if (typeof Prism !== 'undefined') {
                messageBubbleElement.querySelectorAll('pre code').forEach(el => {
                    Prism.highlightElement(el);
                });
            }
            break;
        }

        const container = messageBubbleElement.closest('.chat-messages');
        const threshold = 150;
        const wasAtBottom = container ? (container.scrollHeight - container.scrollTop - container.clientHeight < threshold) : false;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        
        // Save the incomplete line to process in the next chunk
        buffer = lines.pop();

        for (const line of lines) {
            const cleanLine = line.trim();
            if (cleanLine.startsWith('data: ')) {
                const dataStr = cleanLine.slice(6).trim();
                if (dataStr === '[DONE]') break;

                try {
                    const data = JSON.parse(dataStr);
                    if (data.content) {
                        fullText += data.content;
                        scheduleDOMUpdate(container, wasAtBottom);
                    } else if (data.error) {
                        const errorLabel = state.language === 'vi' ? '❌ **Lỗi:**' : '❌ **Error:**';
                        fullText += `\n${errorLabel} ${data.error}`;
                        scheduleDOMUpdate(container, wasAtBottom);
                    }
                } catch (e) {
                    // Ignore parsing errors for partial or malformed lines
                }
            }
        }

        // Fallback for non-batched environments
        if (!pendingUpdate && container && wasAtBottom) {
            container.scrollTop = container.scrollHeight;
        }
    }
}

let _autoResizeRafId = null;
function autoResizeTextarea() {
    // Debounce with requestAnimationFrame to avoid layout thrashing on rapid input
    if (_autoResizeRafId) cancelAnimationFrame(_autoResizeRafId);
    _autoResizeRafId = requestAnimationFrame(() => {
        chatInput.style.height = 'auto';
        chatInput.style.height = Math.min(chatInput.scrollHeight, 150) + 'px';
        _autoResizeRafId = null;
    });
}

function showToast(icon, message) {
    toastIcon.textContent = icon;
    toastMessage.textContent = message;
    toast.classList.add('show');
    setTimeout(() => toast.classList.remove('show'), 4000);
}

// ===== IMAGE MODAL =====
const imageModal = $('imageModal');
const modalImg = $('modalImg');
const modalCaption = $('modalCaption');
const closeImageModal = $('closeImageModal');
console.log("Modal elements initialized:", { imageModal, modalImg, modalCaption, closeImageModal });

function openModal(imgUrl, caption) {
    console.log("openModal called with:", imgUrl, caption, "elements status:", { modalImg, modalCaption, imageModal });
    if (modalImg && modalCaption && imageModal) {
        modalImg.src = imgUrl;
        modalCaption.textContent = caption;
        imageModal.classList.add('show');
    }
}

function closeModal() {
    if (imageModal && modalImg) {
        imageModal.classList.remove('show');
        modalImg.src = '';
    }
}

if (closeImageModal) {
    closeImageModal.addEventListener('click', closeModal);
}
if (imageModal) {
    imageModal.addEventListener('click', (e) => {
        if (e.target === imageModal) closeModal();
    });
}
document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && imageModal && imageModal.classList.contains('show')) {
        closeModal();
    }
});

if (typeof marked !== 'undefined') {
    marked.use({
        breaks: true,
        gfm: true,
        renderer: {
            code(code, language) {
                const lang = (language || '').match(/\S*/)?.[0] || 'code';
                const escapedCode = code
                    .replace(/&/g, '&amp;')
                    .replace(/</g, '&lt;')
                    .replace(/>/g, '&gt;')
                    .replace(/"/g, '&quot;')
                    .replace(/'/g, '&#39;');
                
                return `<div class="code-block-wrapper">
                    <div class="code-header">
                        <span>${lang}</span>
                        <button class="copy-code-btn" onclick="copyCodeToClipboard(this)" data-code="${escapedCode}" title="Copy Code">
                            <span class="material-symbols-rounded">content_copy</span>
                        </button>
                    </div>
                    <pre><code class="language-${lang}">${escapedCode}</code></pre>
                </div>`;
            }
        }
    });
}

function formatMessage(text) {
    if (!text) return "";

    // Handle DeepSeek <think> tag
    let formatted = text.replace(/<think>([\s\S]*?)<\/think>/g, '<div class="thought-process"><div class="thought-header"><span class="material-symbols-rounded">psychology</span> Thought Process</div><div class="thought-content">$1</div></div>');

    // Handle unclosed <think> tag during streaming
    if (formatted.includes('<think>') && !formatted.includes('</think>')) {
        formatted = formatted.replace(/<think>([\s\S]*)/, '<div class="thought-process"><div class="thought-header"><span class="material-symbols-rounded spinning">progress_activity</span> Thinking...</div><div class="thought-content">$1</div></div>');
    }

    formatted = fixNestedMarkdown(formatted);

    if (typeof marked !== 'undefined') {
        return marked.parse(formatted);
    }

    // Fallback if marked is not available
    formatted = formatted.replace(/```(\w*)\n([\s\S]*?)```/g, (match, lang, code) => {
        const escapedCode = code
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#39;');
        return `<div class="code-block-wrapper">
            <div class="code-header">
                <span>${lang || 'code'}</span>
                <button class="copy-code-btn" onclick="copyCodeToClipboard(this)" data-code="${escapedCode}" title="Copy Code">
                    <span class="material-symbols-rounded">content_copy</span>
                </button>
            </div>
            <pre><code>${code}</code></pre>
        </div>`;
    });

    return formatted
        .replace(/`(.*?)`/g, '<code>$1</code>')
        .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
        .replace(/\*(.*?)\*/g, '<em>$1</em>')
        .replace(/\n/g, '<br>');
}

function fixNestedMarkdown(text) {
    if (!text.includes('```markdown') && !text.includes('```md')) return text;

    const lines = text.split('\n');
    let out = [];
    let inMd = false;
    let innerDepth = 0;
    
    for (let i = 0; i < lines.length; i++) {
        let line = lines[i];
        let trimmed = line.trim();
        
        if (!inMd) {
            if (trimmed.startsWith('```markdown') || trimmed.startsWith('```md')) {
                inMd = true;
                innerDepth = 0;
                out.push(line.replace(/^```/, '`````'));
            } else {
                out.push(line);
            }
            continue;
        }
        
        // Inside markdown block
        if (trimmed.startsWith('```') && !trimmed.startsWith('`````')) {
            if (trimmed.match(/^```[a-zA-Z0-9_+-]+$/)) {
                // Opening inner block with language
                innerDepth++;
                out.push(line);
            } else if (trimmed === '```') {
                if (innerDepth > 0) {
                    innerDepth--;
                    out.push(line);
                } else {
                    // Close outer markdown block
                    inMd = false;
                    out.push(line.replace(/^```/, '`````'));
                }
            } else {
                out.push(line);
            }
        } else {
            out.push(line);
        }
    }
    
    // If stream ends while still in md block, it's fine, marked.js handles unclosed 5-backtick blocks
    return out.join('\n');
}

// Global copy to clipboard function
window.copyCodeToClipboard = (btn) => {
    const code = btn.getAttribute('data-code');
    const txt = document.createElement('textarea');
    txt.innerHTML = code;
    const decodedCode = txt.value;

    navigator.clipboard.writeText(decodedCode).then(() => {
        const icon = btn.querySelector('.material-symbols-rounded');
        icon.textContent = 'check';
        btn.classList.add('copied');
        showToast('✅', state.language === 'vi' ? 'Đã copy code vào clipboard!' : 'Copied code to clipboard!');
        setTimeout(() => {
            icon.textContent = 'content_copy';
            btn.classList.remove('copied');
        }, 2000);
    }).catch(err => {
        showToast('❌', 'Failed to copy: ' + err);
    });
};

function showTypingIndicator(target) {
    const el = document.createElement('div');
    el.className = 'message assistant typing';
    el.id = 'typingIndicator';
    el.innerHTML = `
        <div class="message-avatar"><span class="material-symbols-rounded">smart_toy</span></div>
        <div class="message-bubble typing-bubble">
            <span class="dot"></span><span class="dot"></span><span class="dot"></span>
        </div>
    `;
    target.appendChild(el);
    target.scrollTop = target.scrollHeight;
}

function removeTypingIndicator() {
    const el = document.getElementById('typingIndicator');
    if (el) el.remove();
}

// ===== START =====
init();
