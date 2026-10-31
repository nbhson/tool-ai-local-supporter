// ===== PROJECT WORKSPACE FUNCTIONS =====

let monacoEditor = null;
let monacoLoaded = false;

function initProjectWorkspace() {
    // Project local path open click
    openLocalProjectBtn.addEventListener('click', openLocalProject);
    projectPathInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') openLocalProject();
    });

    // Close project session
    closeProjectBtn.addEventListener('click', closeProjectSession);

    // Reload project session
    if (reloadProjectBtn) {
        reloadProjectBtn.addEventListener('click', async () => {
            const reloadIcon = reloadProjectBtn.querySelector('.material-symbols-rounded');
            if (reloadIcon) reloadIcon.classList.add('spinning');
            reloadProjectBtn.disabled = true;

            try {
                await reloadProjectWorkspace();
                showToast('🔄', state.language === 'vi' ? 'Đã cập nhật dự án.' : 'Project updated.');
            } catch (e) {
                showToast('❌', state.language === 'vi' ? 'Lỗi tải lại: ' + e.message : 'Reload error: ' + e.message);
            } finally {
                if (reloadIcon) reloadIcon.classList.remove('spinning');
                reloadProjectBtn.disabled = false;
            }
        });
    }

    // Save active file click
    saveActiveFileBtn.addEventListener('click', saveActiveFile);

    // Monaco Editor handles scrolling and input change events internally

    // Chat sending
    projectSendBtn.addEventListener('click', sendProjectMessage);
    projectChatInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            sendProjectMessage();
        }
    });

    // Diff controls
    discardDiffBtn.addEventListener('click', () => {
        editorDiffView.style.display = 'none';
        editorActiveView.style.display = 'flex';
    });
    acceptDiffBtn.addEventListener('click', async () => {
        if (state.project.diffProposedContent && state.project.diffFilePath) {
            const proposed = state.project.diffProposedContent;
            const path = state.project.diffFilePath;

            try {
                const res = await fetch(`/api/project/${state.project.sessionId}/write_file`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ path: path, content: proposed })
                });
                const data = await res.json();
                if (data.success) {
                    state.project.openFiles[path] = proposed;
                    if (state.project.activeFile === path && monacoEditor) {
                        monacoEditor.setValue(proposed);
                    }
                    showToast('✅', state.language === 'vi' ? 'Đã áp dụng thay đổi thành công!' : 'Successfully applied changes!');
                    editorDiffView.style.display = 'none';
                    editorActiveView.style.display = 'flex';
                } else {
                    showToast('❌', data.error);
                }
            } catch (e) {
                showToast('❌', 'Error writing file: ' + e.message);
            }
        }
    });
    initAutocompleteDropdown();
    initResizers();
    initDiffViewMode();
}

async function openLocalProject() {
    const path = projectPathInput.value.trim();
    if (!path) {
        showToast('⚠️', state.language === 'vi' ? 'Vui lòng nhập đường dẫn thư mục.' : 'Please enter directory path.');
        return;
    }

    openLocalProjectBtn.disabled = true;
    openLocalProjectBtn.textContent = state.language === 'vi' ? 'Đang mở...' : 'Opening...';

    try {
        const res = await fetch('/api/project/init', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                path: path,
                model: modelSelect.value,
                language: state.language
            })
        });

        const data = await res.json();
        if (!res.ok) throw new Error(data.error || 'Failed to open project');

        state.project.sessionId = data.session_id;
        state.project.path = path;
        state.project.isLocal = true;
        state.project.tree = data.tree;
        state.project.stats = data.stats;
        state.project.openFiles = {};
        state.project.activeFile = null;
        state.project.selectedFiles.clear();
        updateFlatFilesList();

        // UI toggles
        document.querySelector('.project-sidebar-section').style.display = 'none';
        projectExplorerSection.style.display = 'flex';
        projectWelcome.style.display = 'none';
        projectWorkspaceContainer.style.display = 'flex';

        // Render Tree & Dashboard
        renderProjectTree(data.tree, projectTreeContainer);
        renderProjectDashboard(data.stats, path);
        updateContextBar();
        showChatWelcomeMessage();

        showToast('✅', state.language === 'vi' ? 'Đã mở dự án thành công!' : 'Project opened successfully!');
    } catch (err) {
        showToast('❌', err.message);
    } finally {
        openLocalProjectBtn.disabled = false;
        openLocalProjectBtn.innerHTML = `<span class="material-symbols-rounded" style="font-size: 1.1rem !important;">folder</span> ${state.language === 'vi' ? 'Mở cục bộ' : 'Open Local'}`;
    }
}

function closeProjectSession() {
    state.project.sessionId = null;
    state.project.path = null;
    state.project.tree = null;
    state.project.stats = null;
    state.project.openFiles = {};
    state.project.activeFile = null;
    state.project.selectedFiles.clear();

    document.querySelector('.project-sidebar-section').style.display = 'block';
    projectExplorerSection.style.display = 'none';
    projectWorkspaceContainer.style.display = 'none';
    projectWelcome.style.display = 'flex';
    projectPathInput.value = '';
    projectFolderInput.value = '';
    projectChatMessages.innerHTML = '';

    showToast('🔄', state.language === 'vi' ? 'Đã đóng dự án.' : 'Project workspace closed.');
}

// Recursively render VSCode style directory tree
function renderProjectTree(nodes, container, depth = 0) {
    if (depth === 0) container.innerHTML = '';

    if (nodes.length === 0 && depth === 0) {
        container.innerHTML = `<div style="padding: 12px; color: var(--text-muted); font-style: italic; font-size: 0.82rem; text-align: center;">
            ${state.language === 'vi' ? 'Thư mục trống' : 'Empty directory'}
        </div>`;
        return;
    }

    const ul = document.createElement('ul');
    ul.style.listStyle = 'none';
    ul.style.paddingLeft = depth === 0 ? '0' : '10px';

    nodes.forEach(node => {
        const li = document.createElement('li');
        li.style.margin = '2px 0';

        const itemDiv = document.createElement('div');
        itemDiv.className = 'tree-item';
        itemDiv.dataset.path = node.path;

        // Add indent line representation
        itemDiv.style.paddingLeft = `${depth * 6}px`;

        if (node.is_dir) {
            const arrow = document.createElement('span');
            arrow.className = 'material-symbols-rounded tree-arrow';
            arrow.textContent = 'chevron_right';

            const icon = document.createElement('span');
            icon.className = 'material-symbols-rounded tree-icon folder';
            icon.textContent = 'folder';

            const name = document.createElement('span');
            name.textContent = node.name;

            itemDiv.appendChild(arrow);
            itemDiv.appendChild(icon);
            itemDiv.appendChild(name);
            li.appendChild(itemDiv);

            // Children list container
            const childrenContainer = document.createElement('div');
            childrenContainer.className = 'tree-folder-children';

            itemDiv.addEventListener('click', (e) => {
                e.stopPropagation();
                const isExpanded = childrenContainer.classList.toggle('expanded');
                arrow.classList.toggle('expanded', isExpanded);
                icon.textContent = isExpanded ? 'folder_open' : 'folder';
            });

            renderProjectTree(node.children || [], childrenContainer, depth + 1);
            li.appendChild(childrenContainer);
        } else {
            const icon = document.createElement('span');
            icon.className = 'material-symbols-rounded tree-icon file';
            const ext = node.name.split('.').pop().toLowerCase();
            icon.dataset.ext = ext;

            // Assign specific file icon
            if (['py', 'js', 'ts', 'go', 'rs', 'cpp', 'c', 'sh', 'bat'].includes(ext)) {
                icon.textContent = 'code';
            } else if (['json', 'yaml', 'yml', 'xml', 'toml'].includes(ext)) {
                icon.textContent = 'settings';
            } else if (['md', 'txt', 'rtf'].includes(ext)) {
                icon.textContent = 'description';
            } else if (['png', 'jpg', 'jpeg', 'svg', 'gif'].includes(ext)) {
                icon.textContent = 'image';
            } else {
                icon.textContent = 'draft';
            }

            const name = document.createElement('span');
            name.textContent = node.name;

            const actionsDiv = document.createElement('div');
            actionsDiv.className = 'tree-file-actions';

            const addContextBtn = document.createElement('span');
            addContextBtn.className = 'material-symbols-rounded tree-file-action add-context-btn';
            const isSelected = state.project.selectedFiles.has(node.path);
            addContextBtn.textContent = isSelected ? 'check' : 'add';
            addContextBtn.title = isSelected ? (state.language === 'vi' ? 'Xoá khỏi context chat' : 'Remove from chat context') : (state.language === 'vi' ? 'Thêm vào context chat' : 'Add to chat context');
            
            if (isSelected) {
                itemDiv.classList.add('in-context');
            }

            addContextBtn.addEventListener('click', (e) => {
                e.stopPropagation();
                const activeSelected = state.project.selectedFiles.has(node.path);
                if (activeSelected) {
                    state.project.selectedFiles.delete(node.path);
                    const regex = new RegExp(`@${node.path}\\s*`, 'g');
                    projectChatInput.value = projectChatInput.value.replace(regex, '');
                } else {
                    state.project.selectedFiles.add(node.path);
                    const val = projectChatInput.value.trim();
                    projectChatInput.value = val ? `${val} @${node.path} ` : `@${node.path} `;
                    projectChatInput.dispatchEvent(new Event('input'));
                }
                updateContextBar();
                updateTreeItemTags();
                projectChatInput.focus();
            });

            actionsDiv.appendChild(addContextBtn);

            itemDiv.appendChild(icon);
            itemDiv.appendChild(name);
            itemDiv.appendChild(actionsDiv);
            li.appendChild(itemDiv);

            itemDiv.addEventListener('click', (e) => {
                e.stopPropagation();
                openProjectFile(node.path);
            });
        }

        ul.appendChild(li);
    });

    container.appendChild(ul);
}

function renderProjectDashboard(stats, path) {
    dashboardPathLabel.textContent = `Workspace Path: ${path}`;
    statTotalFiles.textContent = stats.total_files;

    // Format size
    const size = stats.total_size;
    if (size > 1024 * 1024) {
        statTotalSize.textContent = (size / (1024 * 1024)).toFixed(2) + ' MB';
    } else {
        statTotalSize.textContent = (size / 1024).toFixed(1) + ' KB';
    }

    // Determine primary language
    let primary = 'None';
    let maxCount = 0;
    let totalCodeFiles = 0;

    Object.entries(stats.lang_stats).forEach(([lang, count]) => {
        totalCodeFiles += count;
        if (count > maxCount) {
            maxCount = count;
            primary = lang.toUpperCase();
        }
    });
    statMainLang.textContent = primary;

    // Render Lang Progress Bar
    langsProgressContainer.innerHTML = '';
    const legendGrid = document.createElement('div');
    legendGrid.className = 'langs-legend';

    const colors = ['#8b5cf6', '#06b6d4', '#10b981', '#f59e0b', '#ef4444', '#ec4899', '#6b7280'];

    if (totalCodeFiles === 0) {
        langsProgressContainer.style.height = 'auto';
        langsProgressContainer.innerHTML = `<div style="font-size:0.75rem; color:var(--text-muted); font-style:italic; width:100%; text-align:center; padding: 4px 0;">
            ${state.language === 'vi' ? 'Không có tệp tin lập trình' : 'No programming files found'}
        </div>`;
        const oldLegend = projectDashboard.querySelector('.langs-legend');
        if (oldLegend) oldLegend.remove();
        return;
    }

    // Sort and get top languages
    const sortedLangs = Object.entries(stats.lang_stats)
        .sort((a, b) => b[1] - a[1]);

    let renderedPct = 0;
    sortedLangs.slice(0, 5).forEach(([lang, count], idx) => {
        const pct = ((count / totalCodeFiles) * 100).toFixed(1);
        renderedPct += parseFloat(pct);
        const color = colors[idx % colors.length];

        const bar = document.createElement('div');
        bar.className = 'lang-bar';
        bar.style.width = `${pct}%`;
        bar.style.background = color;
        bar.title = `${lang.toUpperCase()}: ${pct}%`;
        langsProgressContainer.appendChild(bar);

        // Legend Item
        const item = document.createElement('div');
        item.className = 'legend-item';
        item.innerHTML = `
            <span class="legend-color" style="background: ${color}"></span>
            <span style="font-weight:600">${lang.toUpperCase()}</span>
            <span style="color:var(--text-muted)">${pct}%</span>
        `;
        legendGrid.appendChild(item);
    });

    // Add other category if needed
    if (sortedLangs.length > 5) {
        const otherPct = (100 - renderedPct).toFixed(1);
        if (otherPct > 0) {
            const bar = document.createElement('div');
            bar.className = 'lang-bar';
            bar.style.width = `${otherPct}%`;
            bar.style.background = colors[6];
            bar.title = `Other: ${otherPct}%`;
            langsProgressContainer.appendChild(bar);

            const item = document.createElement('div');
            item.className = 'legend-item';
            item.innerHTML = `
                <span class="legend-color" style="background: ${colors[6]}"></span>
                <span style="font-weight:600">Other</span>
                <span style="color:var(--text-muted)">${otherPct}%</span>
            `;
            legendGrid.appendChild(item);
        }
    }

    const oldLegend = projectDashboard.querySelector('.langs-legend');
    if (oldLegend) oldLegend.remove();
    projectDashboard.querySelector('.dashboard-langs-section').appendChild(legendGrid);
}

function updateContextBar() {
    const count = state.project.selectedFiles.size;
    
    if (count > 0) {
        workspaceContextBar.style.display = 'flex';
        workspaceContextCount.textContent = count === 1 ? '1 file context' : `${count} files context`;
    } else {
        workspaceContextBar.style.display = 'none';
        workspaceContextCount.textContent = '0 file context';
    }

    contextFilesTags.innerHTML = '';
    state.project.selectedFiles.forEach(path => {
        const filename = path.split('/').pop();
        const ext = filename.split('.').pop().toLowerCase();
        
        let iconName = 'draft';
        let iconClass = 'file-generic';
        
        if (['py', 'js', 'ts', 'go', 'rs', 'cpp', 'c', 'sh', 'bat'].includes(ext)) {
            iconName = 'code';
            iconClass = 'file-code';
        } else if (['json', 'yaml', 'yml', 'xml', 'toml'].includes(ext)) {
            iconName = 'settings';
            iconClass = 'file-config';
        } else if (['md', 'txt', 'rtf'].includes(ext)) {
            iconName = 'description';
            iconClass = 'file-doc';
        } else if (['png', 'jpg', 'jpeg', 'svg', 'gif'].includes(ext)) {
            iconName = 'image';
            iconClass = 'file-image';
        }

        const tag = document.createElement('div');
        tag.className = 'context-tag';
        tag.innerHTML = `
            <span class="material-symbols-rounded context-tag-icon ${iconClass}" style="font-size: 0.95rem !important;">${iconName}</span>
            <span class="context-tag-name" title="${path}">${filename}</span>
            <span class="material-symbols-rounded context-tag-remove">close</span>
        `;
        tag.querySelector('.context-tag-remove').addEventListener('click', () => {
            state.project.selectedFiles.delete(path);
            const regex = new RegExp(`@${path}\\s*`, 'g');
            projectChatInput.value = projectChatInput.value.replace(regex, '');
            updateContextBar();
            updateTreeItemTags();
        });
        contextFilesTags.appendChild(tag);
    });

    if (count > 1) {
        const clearBtn = document.createElement('div');
        clearBtn.className = 'context-clear-all';
        clearBtn.innerHTML = `
            <span>Clear all</span>
            <span class="material-symbols-rounded" style="font-size: 0.85rem !important;">delete</span>
        `;
        clearBtn.addEventListener('click', () => {
            state.project.selectedFiles.forEach(path => {
                const regex = new RegExp(`@${path}\\s*`, 'g');
                projectChatInput.value = projectChatInput.value.replace(regex, '');
            });
            state.project.selectedFiles.clear();
            updateContextBar();
            updateTreeItemTags();
            projectChatInput.dispatchEvent(new Event('input'));
        });
        contextFilesTags.appendChild(clearBtn);
    }
}

function loadMonaco(callback) {
    if (monacoLoaded) {
        if (callback) callback();
        return;
    }
    if (window.require) {
        require.config({ paths: { vs: 'https://cdnjs.cloudflare.com/ajax/libs/monaco-editor/0.39.0/min/vs' } });
        require(['vs/editor/editor.main'], function() {
            monacoLoaded = true;
            console.log("Monaco Editor loaded successfully!");
            if (callback) callback();
        });
    }
}

function updateMonacoEditor(content, filepath) {
    const ext = filepath.split('.').pop().toLowerCase();
    let lang = 'plaintext';
    if (ext === 'py') lang = 'python';
    else if (ext === 'js') lang = 'javascript';
    else if (ext === 'ts') lang = 'typescript';
    else if (ext === 'html' || ext === 'htm') lang = 'html';
    else if (ext === 'css') lang = 'css';
    else if (ext === 'json') lang = 'json';
    else if (ext === 'md') lang = 'markdown';
    else if (ext === 'cpp' || ext === 'h') lang = 'cpp';
    else if (ext === 'go') lang = 'go';
    else if (ext === 'rs') lang = 'rust';
    else if (ext === 'sh') lang = 'shell';

    if (!monacoLoaded) {
        loadMonaco(() => {
            updateMonacoEditor(content, filepath);
        });
        return;
    }

    if (!monacoEditor) {
        monacoEditor = monaco.editor.create(document.getElementById('monacoEditorContainer'), {
            value: content,
            language: lang,
            theme: 'vs-dark',
            automaticLayout: true,
            fontSize: 13,
            fontFamily: "'Fira Code', 'JetBrains Mono', monospace",
            lineHeight: 20,
            minimap: { enabled: false }
        });
        
        monacoEditor.onDidChangeModelContent(() => {
            if (state.project.activeFile) {
                state.project.openFiles[state.project.activeFile] = monacoEditor.getValue();
            }
        });
    } else {
        const model = monaco.editor.createModel(content, lang);
        monacoEditor.setModel(model);
    }
}

async function openProjectFile(relPath) {
    // Check if we need to load it
    if (state.project.openFiles[relPath] === undefined) {
        try {
            const res = await fetch(`/api/project/${state.project.sessionId}/file?path=${encodeURIComponent(relPath)}`);
            const data = await res.json();
            if (!res.ok) throw new Error(data.error || 'Failed to read file');
            state.project.openFiles[relPath] = data.content;
        } catch (e) {
            showToast('❌', e.message);
            return;
        }
    }

    state.project.activeFile = relPath;

    // Highlight explorer node
    projectTreeContainer.querySelectorAll('.tree-item').forEach(item => {
        item.classList.toggle('active', item.dataset.path === relPath);
    });

    // Populate editor & tabs
    renderTabs();
    projectDashboard.style.display = 'none';
    editorDiffView.style.display = 'none';
    editorActiveView.style.display = 'flex';

    activeFileTitle.textContent = relPath;
    updateMonacoEditor(state.project.openFiles[relPath], relPath);
}

function renderTabs() {
    editorTabsBar.innerHTML = '';
    const openPaths = Object.keys(state.project.openFiles);

    if (openPaths.length === 0) {
        editorActiveView.style.display = 'none';
        projectDashboard.style.display = 'flex';
        state.project.activeFile = null;
        return;
    }

    openPaths.forEach(path => {
        const tab = document.createElement('div');
        tab.className = `editor-tab ${state.project.activeFile === path ? 'active' : ''}`;

        const nameSpan = document.createElement('span');
        nameSpan.textContent = path.split('/').pop();

        const closeIcon = document.createElement('span');
        closeIcon.className = 'material-symbols-rounded tab-close';
        closeIcon.textContent = 'close';

        tab.appendChild(nameSpan);
        tab.appendChild(closeIcon);

        tab.addEventListener('click', () => openProjectFile(path));
        closeIcon.addEventListener('click', (e) => {
            e.stopPropagation();
            delete state.project.openFiles[path];
            if (state.project.activeFile === path) {
                const keys = Object.keys(state.project.openFiles);
                if (keys.length > 0) {
                    openProjectFile(keys[keys.length - 1]);
                } else {
                    renderTabs();
                }
            } else {
                renderTabs();
            }
        });

        editorTabsBar.appendChild(tab);
    });
}

function updateLineNumbers() {
    // Monaco handles its own line numbers
}

async function saveActiveFile() {
    const path = state.project.activeFile;
    if (!path) return;

    const content = monacoEditor ? monacoEditor.getValue() : '';
    saveActiveFileBtn.disabled = true;
    saveActiveFileBtn.innerHTML = `<span class="material-symbols-rounded spinning" style="font-size:0.95rem !important">progress_activity</span> ${state.language === 'vi' ? 'Đang lưu...' : 'Saving...'}`;

    try {
        const res = await fetch(`/api/project/${state.project.sessionId}/write_file`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                path: path,
                content: content
            })
        });
        const data = await res.json();
        if (data.success) {
            state.project.openFiles[path] = content;
            showToast('✅', state.language === 'vi' ? 'Đã lưu file thành công!' : 'File saved successfully!');
        } else {
            showToast('❌', data.error || 'Error saving file');
        }
    } catch (e) {
        showToast('❌', 'Error: ' + e.message);
    } finally {
        saveActiveFileBtn.disabled = false;
        saveActiveFileBtn.innerHTML = `<span class="material-symbols-rounded" style="font-size:0.95rem !important">save</span> ${state.language === 'vi' ? 'Lưu' : 'Save'}`;
    }
}

// Diff Engine: Optimized Myers line diff using jsdiff library
function diffLinesFallback(oldStr, newStr) {
    const oldLines = oldStr.split(/\r?\n/);
    const newLines = newStr.split(/\r?\n/);
    
    // If the files are large, avoid O(N^2) LCS DP to prevent browser freeze.
    if (oldLines.length > 500 || newLines.length > 500) {
        const result = [];
        let i = 0, j = 0;
        while (i < oldLines.length || j < newLines.length) {
            if (i < oldLines.length && j < newLines.length && oldLines[i] === newLines[j]) {
                result.push({ type: 'unchanged', text: oldLines[i], oldLine: i + 1, newLine: j + 1 });
                i++;
                j++;
            } else {
                if (i < oldLines.length) {
                    result.push({ type: 'removed', text: oldLines[i], oldLine: i + 1 });
                    i++;
                }
                if (j < newLines.length) {
                    result.push({ type: 'added', text: newLines[j], newLine: j + 1 });
                    j++;
                }
            }
        }
        return result;
    }

    const m = oldLines.length;
    const n = newLines.length;
    const dp = Array.from({ length: m + 1 }, () => Array(n + 1).fill(0));
    
    for (let i = 1; i <= m; i++) {
        for (let j = 1; j <= n; j++) {
            if (oldLines[i - 1] === newLines[j - 1]) {
                dp[i][j] = dp[i - 1][j - 1] + 1;
            } else {
                dp[i][j] = Math.max(dp[i - 1][j], dp[i][j - 1]);
            }
        }
    }
    
    let i = m, j = n;
    const tempResult = [];
    while (i > 0 || j > 0) {
        if (i > 0 && j > 0 && oldLines[i - 1] === newLines[j - 1]) {
            tempResult.push({ type: 'unchanged', text: oldLines[i - 1], oldLine: i, newLine: j });
            i--;
            j--;
        } else if (j > 0 && (i === 0 || dp[i][j - 1] >= dp[i - 1][j])) {
            tempResult.push({ type: 'added', text: newLines[j - 1], newLine: j });
            j--;
        } else {
            tempResult.push({ type: 'removed', text: oldLines[i - 1], oldLine: i });
            i--;
        }
    }
    return tempResult.reverse();
}

function diffLines(oldStr, newStr) {
    if (typeof Diff === 'undefined') {
        console.warn("jsdiff library not loaded, using fallback.");
        return diffLinesFallback(oldStr, newStr);
    }
    
    const diff = Diff.diffLines(oldStr, newStr);
    const result = [];
    let oldLineNum = 1;
    let newLineNum = 1;

    diff.forEach(part => {
        const lines = part.value.split('\n');
        if (lines.length > 1 && lines[lines.length - 1] === '') {
            lines.pop();
        }

        lines.forEach(lineText => {
            if (part.added) {
                result.push({
                    type: 'added',
                    text: lineText,
                    newLine: newLineNum
                });
                newLineNum++;
            } else if (part.removed) {
                result.push({
                    type: 'removed',
                    text: lineText,
                    oldLine: oldLineNum
                });
                oldLineNum++;
            } else {
                result.push({
                    type: 'unchanged',
                    text: lineText,
                    oldLine: oldLineNum,
                    newLine: newLineNum
                });
                oldLineNum++;
                newLineNum++;
            }
        });
    });

    return result;
}

// Markdown parser & Proposed Code block extractor for Project Chat
let proposedBlocks = [];
let _pendingAutoApplies = [];
let _processedAutoApplyKeys = new Set();

function processPendingAutoApplies() {
    const items = [..._pendingAutoApplies];
    _pendingAutoApplies = [];
    items.forEach(item => {
        const key = `${item.action}:${item.index}`;
        if (_processedAutoApplyKeys.has(key)) return; // Skip already processed
        _processedAutoApplyKeys.add(key);
        setTimeout(() => {
            if (item.action === 'create') {
                createProposedFile(item.index);
            } else {
                applyProposedCode(item.index);
            }
        }, 150);
    });
}

function formatProjectMessage(text) {
    if (!text) return "";
    proposedBlocks = [];
    _pendingAutoApplies = [];

    let formatted = text;

    // 1. Extract thought process first
    formatted = formatted.replace(/<think>([\s\S]*?)<\/think>/g, '<div class="thought-process"><div class="thought-header"><span class="material-symbols-rounded">psychology</span> Thought Process</div><div class="thought-content">$1</div></div>');
    if (formatted.includes('<think>') && !formatted.includes('</think>')) {
        formatted = formatted.replace(/<think>([\s\S]*)/, '<div class="thought-process"><div class="thought-header"><span class="material-symbols-rounded spinning">progress_activity</span> Thinking...</div><div class="thought-content">$1</div></div>');
    }

    const snapshotActiveFile = state.project.activeFile;

    // Helpers for file detection
    const getAllProjectFiles = (nodes = state.project.tree) => {
        if (!nodes) return [];
        let files = [];
        nodes.forEach(node => {
            if (node.is_dir) {
                files = files.concat(getAllProjectFiles(node.children));
            } else {
                files.push(node.path);
            }
        });
        return files;
    };

    const resolveNewFilePath = (candidate, allFiles, activeFilePath) => {
        if (candidate.includes('/') || candidate.includes('\\')) {
            return candidate.replace(/\\/g, '/');
        }

        const extMatch = candidate.match(/^([\w\-]+)/);
        if (extMatch) {
            const prefix = extMatch[1].toLowerCase();
            const similarFile = allFiles.find(f => f.toLowerCase().includes('/' + prefix + '/') || f.split('/').pop().toLowerCase().startsWith(prefix));
            if (similarFile) {
                const dir = similarFile.substring(0, similarFile.lastIndexOf('/'));
                return dir ? `${dir}/${candidate}` : candidate;
            }
        }

        if (activeFilePath) {
            const activeDir = activeFilePath.substring(0, activeFilePath.lastIndexOf('/'));
            if (activeDir) {
                const parts = activeDir.split('/');
                const lastDir = parts[parts.length - 1];
                const extMatch = candidate.match(/^([\w\-]+)/);
                if (extMatch && lastDir) {
                    const prefix = extMatch[1];
                    const shareNamingConvention = (lastDir.includes('-') && prefix.includes('-')) ||
                                                 (lastDir.includes('_') && prefix.includes('_')) ||
                                                 (/[a-z][A-Z]/.test(lastDir) && /[a-z][A-Z]/.test(prefix));
                    if (shareNamingConvention) {
                        parts[parts.length - 1] = prefix;
                        const newDir = parts.join('/');
                        return `${newDir}/${candidate}`;
                    }
                }
                return `${activeDir}/${candidate}`;
            }
        }
        return candidate;
    };

    const isLanguageCompatible = (lang, filepath) => {
        if (!filepath) return false;
        if (!lang) return true; // If no lang is specified, assume it matches

        const ext = filepath.split('.').pop().toLowerCase();
        const l = lang.toLowerCase();

        const groups = {
            'ts': ['ts', 'tsx'],
            'typescript': ['ts', 'tsx'],
            'js': ['js', 'jsx'],
            'javascript': ['js', 'jsx'],
            'json': ['json'],
            'scss': ['scss', 'sass', 'css'],
            'sass': ['scss', 'sass', 'css'],
            'css': ['scss', 'sass', 'css'],
            'html': ['html', 'htm', 'xml'],
            'py': ['py'],
            'python': ['py'],
            'sh': ['sh', 'bash'],
            'bash': ['sh', 'bash'],
            'shell': ['sh', 'bash'],
            'yaml': ['yaml', 'yml'],
            'yml': ['yaml', 'yml'],
            'sql': ['sql'],
            'md': ['md', 'markdown'],
            'markdown': ['md', 'markdown']
        };

        if (groups[l]) {
            return groups[l].includes(ext);
        }
        return ext === l;
    };

    const detectFilepathFromText = (textBeforeCode, blockLang) => {
        if (!textBeforeCode) return null;
        const allFiles = getAllProjectFiles();
        if (allFiles.length === 0) return null;

        const textLower = textBeforeCode.toLowerCase();
        let bestMatch = null;
        let lastIndex = -1;

        // 1. Find the occurrence of any file path in the text
        for (const filepath of allFiles) {
            const filepathLower = filepath.toLowerCase();
            const index = textLower.lastIndexOf(filepathLower);
            if (index !== -1 && index > lastIndex) {
                if (isLanguageCompatible(blockLang, filepath)) {
                    lastIndex = index;
                    bestMatch = { path: filepath, exists: true };
                }
            }
        }

        // 2. Also check filenames (without full path)
        for (const filepath of allFiles) {
            const filename = filepath.split('/').pop().toLowerCase();
            const escapedName = filename.replace(/[-\/\\^$*+?.()|[\]{}]/g, '\\$&');
            const regex = new RegExp(`(\\b|[\`"'])${escapedName}(\\b|[\`"'])`, 'gi');
            let match;
            while ((match = regex.exec(textBeforeCode)) !== null) {
                const index = match.index;
                if (index > lastIndex) {
                    if (isLanguageCompatible(blockLang, filepath)) {
                        lastIndex = index;
                        bestMatch = { path: filepath, exists: true };
                    }
                }
            }
        }

        // If we found a compatible match in existing files, return it
        if (bestMatch) {
            return bestMatch;
        }

        // 3. Try to match mentioned filenames with common programming extensions (even if they don't exist yet)
        const filePatternRegex = /(?:\b|[\`"'])([\w\-./\\]+\.(?:ts|js|tsx|jsx|html|css|scss|sass|less|json|py|md|sh|yaml|yml|sql|txt|go|rs|c|cpp|h|java|kt|gradle|properties|xml|conf|cfg|ini|dockerfile|gitignore))(?:\b|[\`"'])/gi;
        let match;
        let lastCandidate = null;
        let lastCandidateIndex = -1;
        while ((match = filePatternRegex.exec(textBeforeCode)) !== null) {
            const candidate = match[1];
            const index = match.index;
            if (index > lastCandidateIndex) {
                if (isLanguageCompatible(blockLang, candidate)) {
                    lastCandidateIndex = index;
                    lastCandidate = candidate;
                }
            }
        }

        if (lastCandidate) {
            const candidateLower = lastCandidate.toLowerCase();
            const existingMatch = allFiles.find(f => 
                f.toLowerCase() === candidateLower || 
                f.toLowerCase().endsWith('/' + candidateLower) || 
                f.toLowerCase().endsWith('\\' + candidateLower)
            );
            if (existingMatch) {
                return { path: existingMatch, exists: true };
            }

            const resolvedPath = resolveNewFilePath(lastCandidate, allFiles, snapshotActiveFile);
            return { path: resolvedPath, exists: false };
        }

        return null;
    };

    // 2. Parse and extract all code blocks sequentially using placeholders
    const placeholders = [];
    const codeBlockRegex = /(?:\[(CREATE_FILE|MODIFY_FILE):\s*([^\s\]]+)\]\s*)?```(\w*)\n([\s\S]*?)```/g;

    formatted = formatted.replace(codeBlockRegex, (match, tagType, tagPath, lang, code, offset) => {
        const placeholderId = `__CODE_BLOCK_PLACEHOLDER_${placeholders.length}__`;

        let action = 'modify';
        let targetPath = null;

        if (tagType) {
            action = tagType.toLowerCase();
            targetPath = tagPath;
        } else {
            // Auto detect from preceding text
            const textBefore = formatted.substring(Math.max(0, offset - 350), offset);
            const detected = detectFilepathFromText(textBefore, lang);
            if (detected) {
                targetPath = detected.path;
                action = detected.exists ? 'modify' : 'create';
            } else {
                if (isLanguageCompatible(lang, snapshotActiveFile)) {
                    targetPath = snapshotActiveFile;
                    action = 'modify';
                } else {
                    targetPath = null;
                    action = 'modify';
                }
            }
        }

        const blockIndex = proposedBlocks.length;
        proposedBlocks.push({ action: action, path: targetPath, content: code });

        const escapedCode = code
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#39;');

        // Check if agent mode is enabled (auto-apply mode)
        const agentModeCheckbox = document.getElementById('agentModeCheckbox');
        const isAgentMode = agentModeCheckbox ? agentModeCheckbox.checked : true;
        
        let actionHtml = "";
        let htmlBlock = "";

        if (isAgentMode) {
            if (action === 'create') {
                // New files: auto-create without confirmation
                const icon = 'add_circle';
                const label = state.language === 'vi' ? 'Tạo file:' : 'Created file:';
                const pathDisplay = targetPath || '?';
                const lineCount = code.split('\n').length;

                actionHtml = `<div class="ai-code-action-bar auto-apply">
                    <span class="ai-code-tag-title create">
                        <span class="material-symbols-rounded">${icon}</span> ${label} <code>${pathDisplay}</code>
                        <span style="color: var(--text-muted); font-weight: 400; font-size: 0.65rem; margin-left: 4px;">${lineCount} lines</span>
                    </span>
                    <span class="material-symbols-rounded" style="font-size: 1rem; color: var(--success);">check_circle</span>
                </div>`;

                htmlBlock = `<div class="code-block-wrapper agent-compact" style="margin-top: 6px; margin-bottom: 6px;">
                    ${actionHtml}
                </div>`;

                // Queue auto-apply for new files
                _pendingAutoApplies.push({ action: 'create', index: blockIndex });
            } else {
                // Existing files: show full code block with Compare/Apply for user review
                actionHtml = targetPath ? `
                    <div class="ai-code-action-bar">
                        <span class="ai-code-tag-title modify">
                            <span class="material-symbols-rounded">edit</span> ${state.language === 'vi' ? 'Sửa file:' : 'Modify file:'} <code>${targetPath.split('/').pop()}</code>
                            <span style="color: var(--text-muted); font-weight: 400; font-size: 0.65rem; margin-left: 4px;">${code.split('\n').length} lines</span>
                        </span>
                        <div style="display: flex; gap: 6px;">
                            <button class="btn-code-action" onclick="compareProposedCode(${blockIndex})">
                                <span class="material-symbols-rounded">compare</span> ${state.language === 'vi' ? 'So sánh' : 'Compare'}
                            </button>
                            <button class="btn-code-action btn-apply-direct" onclick="applyProposedCode(${blockIndex})">
                                <span class="material-symbols-rounded">check</span> ${state.language === 'vi' ? 'Áp dụng' : 'Apply'}
                            </button>
                        </div>
                    </div>
                ` : `
                    <div class="ai-code-action-bar">
                        <span style="font-size: 0.72rem; color: var(--text-muted); font-style: italic;">
                            ${state.language === 'vi' ? 'Chưa chọn file áp dụng' : 'No target file selected'}
                        </span>
                    </div>
                `;

                htmlBlock = `<div class="code-block-wrapper" style="margin-top: 10px;">
                    ${actionHtml}
                    <div class="code-header">
                        <span>${lang || 'code'}</span>
                        <button class="copy-code-btn" onclick="copyCodeToClipboard(this)" data-code="${escapedCode}" title="Copy Code">
                            <span class="material-symbols-rounded">content_copy</span>
                        </button>
                    </div>
                    <pre><code class="language-${lang || 'text'}">${escapedCode}</code></pre>
                </div>`;
            }
        } else {
            // Non-agent mode: full code block with Compare/Apply buttons
            if (action === 'create') {
                actionHtml = `<div class="ai-code-action-bar">
                    <span class="ai-code-tag-title create">
                        <span class="material-symbols-rounded">add_circle</span> ${state.language === 'vi' ? 'Tạo file:' : 'Create file:'} <code>${targetPath}</code>
                    </span>
                    <button class="btn-code-action btn-apply-direct" onclick="createProposedFile(${blockIndex})">
                        <span class="material-symbols-rounded">create_new_folder</span> ${state.language === 'vi' ? 'Tạo file' : 'Create'}
                    </button>
                </div>`;
            } else {
                actionHtml = targetPath ? `
                    <div class="ai-code-action-bar">
                        <span class="ai-code-tag-title modify">
                            <span class="material-symbols-rounded">edit</span> ${state.language === 'vi' ? 'Sửa file:' : 'Modify file:'} <code>${targetPath.split('/').pop()}</code>
                        </span>
                        <div style="display: flex; gap: 6px;">
                            <button class="btn-code-action" onclick="compareProposedCode(${blockIndex})">
                                <span class="material-symbols-rounded">compare</span> ${state.language === 'vi' ? 'So sánh' : 'Compare'}
                            </button>
                            <button class="btn-code-action btn-apply-direct" onclick="applyProposedCode(${blockIndex})">
                                <span class="material-symbols-rounded">check</span> ${state.language === 'vi' ? 'Áp dụng' : 'Apply'}
                            </button>
                        </div>
                    </div>
                ` : `
                    <div class="ai-code-action-bar">
                        <span style="font-size: 0.72rem; color: var(--text-muted); font-style: italic;">
                            ${state.language === 'vi' ? 'Chưa chọn file áp dụng' : 'No target file selected'}
                        </span>
                    </div>
                `;
            }

            htmlBlock = `<div class="code-block-wrapper" style="margin-top: 10px;">
                ${actionHtml}
                <div class="code-header">
                    <span>${lang || 'code'}</span>
                    <button class="copy-code-btn" onclick="copyCodeToClipboard(this)" data-code="${escapedCode}" title="Copy Code">
                        <span class="material-symbols-rounded">content_copy</span>
                    </button>
                </div>
                <pre><code class="language-${lang || 'text'}">${escapedCode}</code></pre>
            </div>`;
        }

        placeholders.push({ id: placeholderId, html: htmlBlock });
        return placeholderId;
    });

    // 3. Apply standard markdown formatting using marked.js if available
    if (typeof marked !== 'undefined') {
        // marked.parse renders complete GitHub Flavored Markdown (GFM)
        formatted = marked.parse(formatted);
    } else {
        // Fallback standard markdown formatting safely
        formatted = formatted
            .replace(/`(.*?)`/g, '<code>$1</code>')
            .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
            .replace(/\*(.*?)\*/g, '<em>$1</em>')
            .replace(/\n/g, '<br>');
    }

    // 4. Restore original code blocks
    placeholders.forEach(placeholder => {
        // If marked.js wrapped our block-level placeholder in a <p> tag, strip it
        const pWrapped = `<p>${placeholder.id}</p>`;
        if (formatted.includes(pWrapped)) {
            formatted = formatted.replace(pWrapped, placeholder.html);
        } else {
            formatted = formatted.replace(placeholder.id, placeholder.html);
        }
    });

    return formatted;
}

window.compareProposedCode = async (index) => {
    const item = proposedBlocks[index];
    if (!item || !item.path) {
        showToast('⚠️', state.language === 'vi' ? 'Không xác định được tệp tin cần so sánh.' : 'Could not identify target file.');
        return;
    }
    const filepath = item.path;

    // If file content is not loaded yet, fetch it from server
    if (!state.project.openFiles[filepath]) {
        try {
            const res = await fetch(`/api/project/${state.project.sessionId}/file?path=${encodeURIComponent(filepath)}`);
            const data = await res.json();
            if (res.ok) {
                state.project.openFiles[filepath] = data.content;
            } else {
                state.project.openFiles[filepath] = "";
            }
        } catch (e) {
            state.project.openFiles[filepath] = "";
        }
    }

    // Auto-open target file as active in Editor
    await openProjectFile(filepath);

    const original = state.project.openFiles[filepath] || "";
    const proposed = item.content;

    state.project.diffOriginalContent = original;
    state.project.diffProposedContent = proposed;
    state.project.diffFilePath = filepath;

    renderSideBySideDiff(original, proposed, filepath);

    editorActiveView.style.display = 'none';
    projectDashboard.style.display = 'none';
    editorDiffView.style.display = 'flex';
};

window.applyProposedCode = async (index) => {
    const item = proposedBlocks[index];
    if (!item || !item.path) {
        showToast('⚠️', state.language === 'vi' ? 'Không xác định được tệp tin cần áp dụng.' : 'Could not identify target file.');
        return;
    }
    const filepath = item.path;
    const proposed = item.content;

    try {
        const res = await fetch(`/api/project/${state.project.sessionId}/write_file`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                path: filepath,
                content: proposed
            })
        });
        const data = await res.json();
        if (data.success) {
            state.project.openFiles[filepath] = proposed;

            // Auto open file in Editor to show changes
            await openProjectFile(filepath);

            showToast('✅', state.language === 'vi' ? `Đã áp dụng thay đổi cho file ${filepath}!` : `Applied changes to ${filepath} successfully!`);
        } else {
            showToast('❌', data.error || 'Error writing file');
        }
    } catch (e) {
        showToast('❌', 'Error writing file: ' + e.message);
    }
};

window.createProposedFile = async (index) => {
    const item = proposedBlocks[index];
    if (!item || item.action !== 'create') return;

    try {
        const res = await fetch(`/api/project/${state.project.sessionId}/write_file`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                path: item.path,
                content: item.content
            })
        });
        const data = await res.json();
        if (data.success) {
            showToast('✅', state.language === 'vi' ? `Đã tạo file ${item.path} thành công!` : `File ${item.path} created successfully!`);

            // Reload project tree & stats
            await reloadProjectWorkspace();

            // Open the new file
            await openProjectFile(item.path);
        } else {
            showToast('❌', data.error || 'Error creating file');
        }
    } catch (e) {
        showToast('❌', 'Error: ' + e.message);
    }
};

async function reloadProjectWorkspace() {
    if (!state.project.sessionId) return;
    try {
        const res = await fetch(`/api/project/${state.project.sessionId}/scan`);
        const data = await res.json();
        if (res.ok) {
            state.project.tree = data.tree;
            state.project.stats = data.stats;
            updateFlatFilesList();
            renderProjectTree(data.tree, projectTreeContainer);
            renderProjectDashboard(data.stats, state.project.path);
        }
    } catch (e) {
        console.error("Error reloading workspace:", e);
    }
}

function addProjectChatMessage(role, content) {
    if (projectChatMessages.querySelector('.chat-welcome-container')) {
        projectChatMessages.innerHTML = '';
    }
    const msgDiv = document.createElement('div');
    msgDiv.className = `message ${role}`;
    msgDiv.innerHTML = `
        <div class="message-avatar"><span class="material-symbols-rounded">${role === 'assistant' ? 'smart_toy' : 'person'}</span></div>
        <div class="message-bubble">${formatProjectMessage(content)}</div>
    `;
    projectChatMessages.appendChild(msgDiv);
    projectChatMessages.scrollTop = projectChatMessages.scrollHeight;
    processPendingAutoApplies();
}

// Send streaming message for Project Workspace Chat
function cleanToolCallsFromText(text) {
    return text.replace(/\[(?:READ_FILE|WRITE_FILE|LIST_DIR|SEARCH_FILES|RUN_COMMAND|FINISH)[^\]]*?\]/g, '').trim();
}

function updateAgentStatus(bubble, statusText) {
    let statusLabel = bubble.querySelector('.agent-status-label');
    if (!statusLabel) {
        statusLabel = document.createElement('div');
        statusLabel.className = 'agent-status-label';
        bubble.appendChild(statusLabel);
    }
    statusLabel.innerHTML = `<span class="material-symbols-rounded spinning" style="font-size: 0.9rem !important;">progress_activity</span> <span>${statusText}</span>`;
    
    if (statusText.toLowerCase().includes('hoàn thành') || statusText.toLowerCase().includes('finished') || statusText.toLowerCase().includes('thành công') || statusText.toLowerCase().includes('successfully')) {
        statusLabel.innerHTML = `<span class="material-symbols-rounded" style="font-size: 0.9rem !important; color: var(--success);">check_circle</span> <span>${statusText}</span>`;
    }
}

function updateAgentText(bubble, fullText) {
    let textDiv = bubble.querySelector('.agent-thought-area');
    if (!textDiv) {
        textDiv = document.createElement('div');
        textDiv.className = 'agent-thought-area';
        bubble.insertBefore(textDiv, bubble.firstChild);
    }
    textDiv.innerHTML = formatProjectMessage(cleanToolCallsFromText(fullText));
    processPendingAutoApplies();
}

function addAgentTimelineStep(bubble, toolName, args) {
    let timeline = bubble.querySelector('.agent-timeline');
    if (!timeline) {
        timeline = document.createElement('div');
        timeline.className = 'agent-timeline';
        // Place timeline right after thoughts
        const statusLabel = bubble.querySelector('.agent-status-label');
        if (statusLabel) {
            bubble.insertBefore(timeline, statusLabel);
        } else {
            bubble.appendChild(timeline);
        }
    }
    
    const stepId = 'step_' + Math.random().toString(36).substring(2, 9);
    const stepDiv = document.createElement('div');
    stepDiv.className = 'agent-step running';
    stepDiv.id = stepId;
    
    let icon = 'progress_activity';
    let titleText = '';
    
    if (toolName === 'READ_FILE') {
        icon = 'book';
        titleText = state.language === 'vi' ? `Đọc file: ${args.path}` : `Read file: ${args.path}`;
    } else if (toolName === 'WRITE_FILE') {
        icon = 'edit';
        titleText = state.language === 'vi' ? `Ghi file: ${args.path}` : `Write file: ${args.path}`;
    } else if (toolName === 'LIST_DIR') {
        icon = 'folder_open';
        titleText = state.language === 'vi' ? `Duyệt thư mục: ${args.path || '.'}` : `List folder: ${args.path || '.'}`;
    } else if (toolName === 'SEARCH_FILES') {
        icon = 'search';
        titleText = state.language === 'vi' ? `Tìm kiếm: "${args.query}"` : `Search: "${args.query}"`;
    } else if (toolName === 'RUN_COMMAND') {
        icon = 'terminal';
        titleText = state.language === 'vi' ? `Chạy lệnh: ${args.command}` : `Run command: ${args.command}`;
    } else if (toolName === 'FINISH') {
        icon = 'check_circle';
        titleText = state.language === 'vi' ? `Hoàn thành tác vụ` : `Finished task`;
    }
    
    stepDiv.innerHTML = `
        <div class="agent-step-header">
            <span class="material-symbols-rounded step-icon spinning">${icon}</span>
            <span class="step-title">${titleText}</span>
            <span class="material-symbols-rounded step-toggle" style="display:none;">keyboard_arrow_down</span>
        </div>
        <div class="agent-step-body" style="display:none;"></div>
    `;
    
    timeline.appendChild(stepDiv);
    projectChatMessages.scrollTop = projectChatMessages.scrollHeight;
    return stepId;
}

async function updateAgentTimelineStep(stepId, status, result, toolName, args) {
    const stepDiv = document.getElementById(stepId);
    if (!stepDiv) return;
    
    stepDiv.classList.remove('running');
    stepDiv.classList.add(status);
    
    const iconSpan = stepDiv.querySelector('.step-icon');
    iconSpan.classList.remove('spinning');
    
    if (status === 'success') {
        iconSpan.textContent = toolName === 'WRITE_FILE' ? 'edit_square' : 'check_circle';
        iconSpan.style.color = 'var(--success)';
    } else {
        iconSpan.textContent = 'error';
        iconSpan.style.color = 'var(--error)';
    }
    
    const toggleIcon = stepDiv.querySelector('.step-toggle');
    const bodyDiv = stepDiv.querySelector('.agent-step-body');
    
    if (result) {
        toggleIcon.style.display = 'block';
        
        // Clean result for printing
        const escapedResult = result.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
        
        let codeClass = 'text';
        if (toolName === 'READ_FILE' && args && args.path) {
            const ext = args.path.split('.').pop().toLowerCase();
            codeClass = ext;
        } else if (toolName === 'RUN_COMMAND') {
            codeClass = 'bash';
        }
        
        bodyDiv.innerHTML = `<pre><code class="language-${codeClass}">${escapedResult}</code></pre>`;
        
        if (typeof Prism !== 'undefined') {
            const codeEl = bodyDiv.querySelector('pre code');
            if (codeEl) {
                Prism.highlightElement(codeEl);
            }
        }
        
        const header = stepDiv.querySelector('.agent-step-header');
        header.addEventListener('click', () => {
            const isCollapsed = bodyDiv.style.display === 'none';
            bodyDiv.style.display = isCollapsed ? 'block' : 'none';
            toggleIcon.textContent = isCollapsed ? 'keyboard_arrow_up' : 'keyboard_arrow_down';
        });
    }
    
    // Auto-reload workspace if WRITE_FILE succeeded
    if (toolName === 'WRITE_FILE' && status === 'success') {
        await reloadProjectWorkspace();
        const path = args.path;
        if (path) {
            if (state.project.openFiles[path] !== undefined) {
                try {
                    const res = await fetch(`/api/project/${state.project.sessionId}/file?path=${encodeURIComponent(path)}`);
                    const data = await res.json();
                    if (res.ok) {
                        state.project.openFiles[path] = data.content;
                        if (state.project.activeFile === path && monacoEditor) {
                            monacoEditor.setValue(data.content);
                        }
                    }
                } catch (e) {
                    console.error("Error reloading file content:", e);
                }
            }
        }
    }
    projectChatMessages.scrollTop = projectChatMessages.scrollHeight;
}

async function sendProjectMessage() {
    const question = projectChatInput.value.trim();
    if (!question || state.project.isProcessing || !state.project.sessionId) return;

    // Reset dedup tracking for auto-apply operations for this new message
    _processedAutoApplyKeys.clear();

    state.project.isProcessing = true;
    projectChatInput.disabled = true;
    projectSendBtn.disabled = true;

    addProjectChatMessage('user', question);
    projectChatInput.value = '';
    projectChatInput.style.height = 'auto'; // Reset text area size

    showTypingIndicator(projectChatMessages);

    const agentModeCheckbox = document.getElementById('agentModeCheckbox');
    const agentMode = agentModeCheckbox ? agentModeCheckbox.checked : true;

    try {
        const res = await fetch(`/api/project/${state.project.sessionId}/chat`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                question: question,
                model: modelSelect.value,
                language: state.language,
                context_files: Array.from(state.project.selectedFiles),
                agent_mode: agentMode
            })
        });

        removeTypingIndicator();

        if (!res.ok) {
            const data = await res.json();
            throw new Error(data.error || 'Chat failed');
        }

        const msgDiv = document.createElement('div');
        msgDiv.className = `message assistant`;
        msgDiv.innerHTML = `
            <div class="message-avatar"><span class="material-symbols-rounded">smart_toy</span></div>
            <div class="message-bubble"></div>
        `;
        projectChatMessages.appendChild(msgDiv);
        const bubble = msgDiv.querySelector('.message-bubble');

        const reader = res.body.getReader();
        const decoder = new TextDecoder("utf-8");
        let fullText = "";
        let currentStepId = null;
        let stepMap = {};
        let buffer = "";

        while (true) {
            const { value, done } = await reader.read();
            if (done) {
                if (typeof Prism !== 'undefined') {
                    bubble.querySelectorAll('pre code').forEach(el => {
                        Prism.highlightElement(el);
                    });
                }
                break;
            }

            const wasAtBottom = projectChatMessages.scrollHeight - projectChatMessages.scrollTop - projectChatMessages.clientHeight < 150;
            buffer += decoder.decode(value, { stream: true });
            const lines = buffer.split('\n');
            buffer = lines.pop();

            for (const line of lines) {
                const trimmedLine = line.trim();
                if (!trimmedLine) continue;
                
                if (trimmedLine.startsWith('data: ')) {
                    const dataStr = trimmedLine.slice(6).trim();
                    if (dataStr === '[DONE]') break;

                    try {
                        const data = JSON.parse(dataStr);
                        if (data.type === 'agent_status') {
                            updateAgentStatus(bubble, data.status);
                        } else if (data.type === 'content') {
                            fullText += data.content;
                            updateAgentText(bubble, fullText);
                        } else if (data.type === 'tool_call') {
                            const stepId = addAgentTimelineStep(bubble, data.tool, data.args);
                            currentStepId = stepId;
                            if (data.call_id) {
                                stepMap[data.call_id] = stepId;
                            }
                        } else if (data.type === 'tool_result') {
                            const stepId = (data.call_id && stepMap[data.call_id]) ? stepMap[data.call_id] : currentStepId;
                            const status = data.result.startsWith('Error') ? 'error' : 'success';
                            await updateAgentTimelineStep(stepId, status, data.result, data.tool, data.args);
                        } else if (data.error) {
                            const errorLabel = state.language === 'vi' ? '❌ **Lỗi:**' : '❌ **Error:**';
                            updateAgentText(bubble, `${errorLabel} ${data.error}`);
                        }
                    } catch (e) {
                        console.warn("Failed to parse JSON chunk:", dataStr, e);
                    }
                }
            }

            if (wasAtBottom) {
                projectChatMessages.scrollTop = projectChatMessages.scrollHeight;
            }
        }

        projectChatMessages.scrollTop = projectChatMessages.scrollHeight;
    } catch (err) {
        removeTypingIndicator();
        const errorLabel = state.language === 'vi' ? '❌ **Lỗi:**' : '❌ **Error:**';
        const msgDiv = document.createElement('div');
        msgDiv.className = `message assistant`;
        msgDiv.innerHTML = `
            <div class="message-avatar"><span class="material-symbols-rounded">smart_toy</span></div>
            <div class="message-bubble">${formatProjectMessage(`${errorLabel} ${err.message}`)}</div>
        `;
        projectChatMessages.appendChild(msgDiv);
        showToast('❌', err.message);
    } finally {
        state.project.isProcessing = false;
        projectChatInput.disabled = false;
        projectSendBtn.disabled = false;
        projectChatInput.focus();
    }
}

// Flat file list helpers, autocomplete and text syncing logic
function updateTreeItemTags() {
    const fileItems = projectTreeContainer.querySelectorAll('.tree-item[data-path]');
    fileItems.forEach(itemDiv => {
        const path = itemDiv.getAttribute('data-path');
        const addBtn = itemDiv.querySelector('.add-context-btn');
        if (addBtn) {
            const isSelected = state.project.selectedFiles.has(path);
            if (isSelected) {
                itemDiv.classList.add('in-context');
                addBtn.textContent = 'check';
                addBtn.title = state.language === 'vi' ? 'Xoá khỏi context chat' : 'Remove from chat context';
            } else {
                itemDiv.classList.remove('in-context');
                addBtn.textContent = 'add';
                addBtn.title = state.language === 'vi' ? 'Thêm vào context chat' : 'Add to chat context';
            }
        }
    });
}

function updateFlatFilesList() {
    if (!state.project.tree) {
        state.project.flatFiles = [];
        return;
    }
    const files = [];
    function traverse(nodes) {
        for (const node of nodes) {
            if (node.is_dir) {
                traverse(node.children || []);
            } else {
                files.push(node);
            }
        }
    }
    traverse(state.project.tree);
    state.project.flatFiles = files;
}

function showChatWelcomeMessage() {
    projectChatMessages.innerHTML = `
        <div class="chat-welcome-container">
            <div class="chat-welcome-icon">
                <span class="material-symbols-rounded">chat_spark</span>
            </div>
            <h4>AI Workspace Assistant</h4>
            <p>${state.language === 'vi' ? 'Hỏi bất kỳ điều gì về dự án này hoặc yêu cầu viết code. Sử dụng @ để đính kèm file làm ngữ cảnh.' : 'Ask anything about this project or request code changes. Use @ to attach files to context.'}</p>
            <div class="chat-welcome-suggestions">
                <div class="suggestion-chip" data-text="Giải thích cấu trúc dự án này">
                    <span>${state.language === 'vi' ? 'Giải thích cấu trúc dự án này' : 'Explain this project structure'}</span>
                    <span class="material-symbols-rounded" style="font-size: 0.95rem; color: var(--primary-color);">north_east</span>
                </div>
                <div class="suggestion-chip" data-text="Tìm các file cấu hình và giải thích">
                    <span>${state.language === 'vi' ? 'Tìm các file cấu hình và giải thích' : 'Find configuration files'}</span>
                    <span class="material-symbols-rounded" style="font-size: 0.95rem; color: var(--primary-color);">north_east</span>
                </div>
            </div>
        </div>
    `;
    
    projectChatMessages.querySelectorAll('.suggestion-chip').forEach(chip => {
        chip.addEventListener('click', () => {
            projectChatInput.value = chip.dataset.text;
            projectChatInput.focus();
            projectChatInput.dispatchEvent(new Event('input'));
        });
    });
}

let activeAutocompleteIndex = -1;
let autocompleteFilteredFiles = [];

function initAutocompleteDropdown() {
    const dropdown = document.createElement('div');
    dropdown.id = 'projectAutocompleteDropdown';
    dropdown.className = 'autocomplete-dropdown';
    
    const container = document.querySelector('.project-chat-input-container');
    if (container) {
        container.appendChild(dropdown);
    }
    
    projectChatInput.addEventListener('input', handleChatInputEvent);
    projectChatInput.addEventListener('keydown', handleChatInputKeydown, true);
    
    document.addEventListener('click', (e) => {
        if (!dropdown.contains(e.target) && e.target !== projectChatInput) {
            hideAutocompleteDropdown();
        }
    });
}

function handleChatInputEvent(e) {
    projectChatInput.style.height = 'auto';
    projectChatInput.style.height = (projectChatInput.scrollHeight) + 'px';
    
    syncSelectedFilesFromInput();
    
    const text = projectChatInput.value;
    const cursor = projectChatInput.selectionStart;
    const lastAtIdx = text.lastIndexOf('@', cursor - 1);
    
    if (lastAtIdx !== -1) {
        const textBetween = text.substring(lastAtIdx + 1, cursor);
        if (!/\s/.test(textBetween)) {
            showAutocompleteDropdown(textBetween, lastAtIdx);
            return;
        }
    }
    
    hideAutocompleteDropdown();
}

function syncSelectedFilesFromInput() {
    if (!state.project.flatFiles) return;
    
    const text = projectChatInput.value;
    const matches = text.match(/@[^\s]+/g) || [];
    
    const mentionedPaths = new Set();
    for (let match of matches) {
        const path = match.slice(1);
        const matchedFile = state.project.flatFiles.find(f => f.path === path) || 
                            (state.project.flatFiles.filter(f => f.name === path).length === 1 ? state.project.flatFiles.find(f => f.name === path) : null);
        if (matchedFile) {
            mentionedPaths.add(matchedFile.path);
        }
    }
    
    let changed = false;
    state.project.selectedFiles.forEach(path => {
        if (!mentionedPaths.has(path)) {
            state.project.selectedFiles.delete(path);
            changed = true;
        }
    });
    
    mentionedPaths.forEach(path => {
        if (!state.project.selectedFiles.has(path)) {
            state.project.selectedFiles.add(path);
            changed = true;
        }
    });
    
    if (changed) {
        updateContextBar();
        updateTreeItemTags();
    }
}

function showAutocompleteDropdown(query, atIndex) {
    const dropdown = $('projectAutocompleteDropdown');
    if (!dropdown || !state.project.flatFiles) return;
    
    const lowerQuery = query.toLowerCase();
    autocompleteFilteredFiles = state.project.flatFiles.filter(file => 
        file.name.toLowerCase().includes(lowerQuery) || 
        file.path.toLowerCase().includes(lowerQuery)
    ).slice(0, 10);
    
    if (autocompleteFilteredFiles.length === 0) {
        hideAutocompleteDropdown();
        return;
    }
    
    dropdown.innerHTML = '';
    activeAutocompleteIndex = 0;
    
    autocompleteFilteredFiles.forEach((file, index) => {
        const item = document.createElement('div');
        item.className = `autocomplete-item${index === 0 ? ' active' : ''}`;
        
        const ext = file.name.split('.').pop().toLowerCase();
        let iconName = 'draft';
        let iconClass = 'file-generic';
        
        if (['py', 'js', 'ts', 'go', 'rs', 'cpp', 'c', 'sh', 'bat'].includes(ext)) {
            iconName = 'code';
            iconClass = 'file-code';
        } else if (['json', 'yaml', 'yml', 'xml', 'toml'].includes(ext)) {
            iconName = 'settings';
            iconClass = 'file-config';
        } else if (['md', 'txt', 'rtf'].includes(ext)) {
            iconName = 'description';
            iconClass = 'file-doc';
        } else if (['png', 'jpg', 'jpeg', 'svg', 'gif'].includes(ext)) {
            iconName = 'image';
            iconClass = 'file-image';
        }
        
        item.innerHTML = `
            <span class="material-symbols-rounded autocomplete-item-icon ${iconClass}">${iconName}</span>
            <div class="autocomplete-item-info">
                <span class="autocomplete-item-name">${file.name}</span>
                <span class="autocomplete-item-path">${file.path}</span>
            </div>
        `;
        
        item.addEventListener('click', () => {
            selectAutocompleteItem(file, atIndex);
        });
        
        dropdown.appendChild(item);
    });
    
    dropdown.style.display = 'block';
}

function hideAutocompleteDropdown() {
    const dropdown = $('projectAutocompleteDropdown');
    if (dropdown) {
        dropdown.style.display = 'none';
    }
    activeAutocompleteIndex = -1;
    autocompleteFilteredFiles = [];
}

function selectAutocompleteItem(file, atIndex) {
    const text = projectChatInput.value;
    const cursor = projectChatInput.selectionStart;
    
    state.project.selectedFiles.add(file.path);
    updateContextBar();
    updateTreeItemTags();
    
    const beforeAt = text.substring(0, atIndex);
    const afterCursor = text.substring(cursor);
    
    projectChatInput.value = `${beforeAt}@${file.path} ${afterCursor}`;
    const newCursorPos = atIndex + file.path.length + 2;
    projectChatInput.focus();
    projectChatInput.setSelectionRange(newCursorPos, newCursorPos);
    
    hideAutocompleteDropdown();
    projectChatInput.dispatchEvent(new Event('input'));
}

function handleChatInputKeydown(e) {
    const dropdown = $('projectAutocompleteDropdown');
    if (!dropdown || dropdown.style.display === 'none') return;
    
    if (e.key === 'ArrowDown') {
        e.preventDefault();
        e.stopPropagation();
        navigateAutocomplete(1);
    } else if (e.key === 'ArrowUp') {
        e.preventDefault();
        e.stopPropagation();
        navigateAutocomplete(-1);
    } else if (e.key === 'Enter' || e.key === 'Tab') {
        e.preventDefault();
        e.stopPropagation();
        if (activeAutocompleteIndex !== -1 && autocompleteFilteredFiles[activeAutocompleteIndex]) {
            const text = projectChatInput.value;
            const cursor = projectChatInput.selectionStart;
            const lastAtIdx = text.lastIndexOf('@', cursor - 1);
            if (lastAtIdx !== -1) {
                selectAutocompleteItem(autocompleteFilteredFiles[activeAutocompleteIndex], lastAtIdx);
            }
        }
    } else if (e.key === 'Escape') {
        e.preventDefault();
        e.stopPropagation();
        hideAutocompleteDropdown();
    }
}

function navigateAutocomplete(direction) {
    const dropdown = $('projectAutocompleteDropdown');
    const items = dropdown.querySelectorAll('.autocomplete-item');
    if (items.length === 0) return;
    
    if (activeAutocompleteIndex !== -1 && items[activeAutocompleteIndex]) {
        items[activeAutocompleteIndex].classList.remove('active');
    }
    
    activeAutocompleteIndex = (activeAutocompleteIndex + direction + items.length) % items.length;
    
    const activeItem = items[activeAutocompleteIndex];
    activeItem.classList.add('active');
    activeItem.scrollIntoView({ block: 'nearest' });
}

// ===== SIDE-BY-SIDE DIFF VIEW =====
let _diffViewMode = 'split'; // 'split' or 'unified'

function initDiffViewMode() {
    // Add toggle button to diff control panel
    const panel = document.querySelector('.diff-control-panel');
    if (!panel) return;

    // Check if toggle already exists
    if (panel.querySelector('.diff-mode-toggle')) return;

    const toggle = document.createElement('div');
    toggle.className = 'diff-mode-toggle';
    toggle.innerHTML = `
        <button class="diff-mode-btn active" data-mode="split" title="Side by side view">
            <span class="material-symbols-rounded" style="font-size: 1rem;">view_column</span> Split
        </button>
        <button class="diff-mode-btn" data-mode="unified" title="Unified view">
            <span class="material-symbols-rounded" style="font-size: 1rem;">view_agenda</span> Unified
        </button>
    `;
    toggle.style.cssText = 'display: flex; gap: 4px;';

    // Insert before the accept/discard buttons
    const btnGroup = panel.querySelector('div:last-child');
    if (btnGroup) {
        panel.insertBefore(toggle, btnGroup);
    } else {
        panel.appendChild(toggle);
    }

    toggle.querySelectorAll('.diff-mode-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            toggle.querySelectorAll('.diff-mode-btn').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            _diffViewMode = btn.dataset.mode;

            // Re-render if we have data
            if (state.project.diffOriginalContent !== undefined && state.project.diffFilePath) {
                renderSideBySideDiff(
                    state.project.diffOriginalContent,
                    state.project.diffProposedContent,
                    state.project.diffFilePath
                );
            }
        });
    });
}

function renderSideBySideDiff(original, proposed, filepath) {
    if (_diffViewMode === 'split') {
        renderSplitDiff(original, proposed, filepath);
    } else {
        renderUnifiedDiff(original, proposed, filepath);
    }
}

function renderSplitDiff(original, proposed, filepath) {
    const oldLines = original.split(/\r?\n/);
    const newLines = proposed.split(/\r?\n/);

    // Use jsdiff to get structured diff
    let diffParts;
    if (typeof Diff !== 'undefined') {
        diffParts = Diff.diffArrays(oldLines, newLines);
    } else {
        // Simple fallback: treat as separate lines
        const unified = diffLines(original, proposed);
        diffParts = unified.map(part => ({
            added: part.type === 'added',
            removed: part.type === 'removed',
            value: [part.text]
        }));
    }

    // Build paired rows
    const rows = [];
    let oldIdx = 0, newIdx = 0;

    for (const part of diffParts) {
        if (!part.added && !part.removed) {
            // Unchanged lines
            for (const line of part.value) {
                rows.push({ oldNum: ++oldIdx, newNum: ++newIdx, oldText: line, newText: line, type: 'unchanged' });
            }
        } else if (part.removed) {
            for (const line of part.value) {
                rows.push({ oldNum: ++oldIdx, newNum: null, oldText: line, newText: null, type: 'removed' });
            }
        } else if (part.added) {
            for (const line of part.value) {
                rows.push({ oldNum: null, newNum: ++newIdx, oldText: null, newText: line, type: 'added' });
            }
        }
    }

    // Pair up removed and added rows for side-by-side display
    const pairedRows = pairDiffRows(rows);

    diffContainerViewport.innerHTML = '';
    diffContainerViewport.className = 'diff-container-viewport split-mode';

    // Header
    const header = document.createElement('div');
    header.className = 'diff-split-header';
    header.innerHTML = `
        <div class="diff-split-pane-header old">
            <span class="material-symbols-rounded" style="font-size:0.85rem;color:#f87171;">remove_circle</span>
            ${state.language === 'vi' ? 'File gốc (trước khi sửa)' : 'Original (before)'}
        </div>
        <div class="diff-split-pane-header new">
            <span class="material-symbols-rounded" style="font-size:0.85rem;color:#34d399;">add_circle</span>
            ${state.language === 'vi' ? 'File mới (sau khi sửa)' : 'Modified (after)'}
        </div>
    `;
    diffContainerViewport.appendChild(header);

    // Render each pair
    for (const pair of pairedRows) {
        const rowDiv = document.createElement('div');
        rowDiv.className = `diff-split-row ${pair.type || ''}`;

        const leftNum = pair.oldNum !== null && pair.oldNum !== undefined ? pair.oldNum : '';
        const rightNum = pair.newNum !== null && pair.newNum !== undefined ? pair.newNum : '';
        const leftText = pair.oldText !== null && pair.oldText !== undefined ? pair.oldText : '';
        const rightText = pair.newText !== null && pair.newText !== undefined ? pair.newText : '';

        rowDiv.innerHTML = `
            <span class="diff-split-num old">${leftNum}</span>
            <span class="diff-split-code old ${pair.type === 'removed' ? 'hl' : ''}">${escapeHtml(leftText)}</span>
            <span class="diff-split-num new">${rightNum}</span>
            <span class="diff-split-code new ${pair.type === 'added' ? 'hl' : ''}">${escapeHtml(rightText)}</span>
        `;
        diffContainerViewport.appendChild(rowDiv);
    }

    // Stats
    const stats = document.createElement('div');
    stats.className = 'diff-stats';
    const addedCount = rows.filter(r => r.type === 'added').length;
    const removedCount = rows.filter(r => r.type === 'removed').length;
    stats.innerHTML = `<span class="diff-stat added">+${addedCount}</span> <span class="diff-stat removed">-${removedCount}</span>`;
    diffContainerViewport.appendChild(stats);
}

function renderUnifiedDiff(original, proposed, filepath) {
    const diffResult = diffLines(original, proposed);

    diffContainerViewport.innerHTML = '';
    diffContainerViewport.className = 'diff-container-viewport unified-mode';

    let lastUnchangedCount = 0;
    const UNCHANGED_COLLAPSE_THRESHOLD = 5;

    diffResult.forEach((line, idx) => {
        if (line.type === 'unchanged') {
            lastUnchangedCount++;
            if (lastUnchangedCount > UNCHANGED_COLLAPSE_THRESHOLD) {
                // Show collapse indicator only once
                if (lastUnchangedCount === UNCHANGED_COLLAPSE_THRESHOLD + 1) {
                    const collapseDiv = document.createElement('div');
                    collapseDiv.className = 'diff-collapse-indicator';
                    collapseDiv.innerHTML = `<span class="material-symbols-rounded" style="font-size:0.8rem;">unfold_more</span> ...`;
                    collapseDiv.title = state.language === 'vi' ? 'Lines unchanged (ẩn bớt)' : 'Lines unchanged (hidden)';
                    diffContainerViewport.appendChild(collapseDiv);
                }
                return; // Skip redundant unchanged lines
            }
        } else {
            lastUnchangedCount = 0;
        }

        const lineDiv = document.createElement('div');
        lineDiv.className = `diff-line ${line.type}`;

        const numSpan = document.createElement('span');
        numSpan.className = 'diff-line-num';
        if (line.type === 'added') {
            numSpan.textContent = `+${line.newLine || ''}`;
        } else if (line.type === 'removed') {
            numSpan.textContent = `-${line.oldLine || ''}`;
        } else {
            numSpan.textContent = line.oldLine || '';
        }

        const contentSpan = document.createElement('span');
        contentSpan.className = 'diff-line-content';
        contentSpan.textContent = line.text;

        lineDiv.appendChild(numSpan);
        lineDiv.appendChild(contentSpan);
        diffContainerViewport.appendChild(lineDiv);
    });

    // Stats
    const addedCount = diffResult.filter(r => r.type === 'added').length;
    const removedCount = diffResult.filter(r => r.type === 'removed').length;
    const stats = document.createElement('div');
    stats.className = 'diff-stats';
    stats.innerHTML = `<span class="diff-stat added">+${addedCount}</span> <span class="diff-stat removed">-${removedCount}</span>`;
    diffContainerViewport.appendChild(stats);
}

function pairDiffRows(rows) {
    const result = [];
    let i = 0;

    while (i < rows.length) {
        if (rows[i].type === 'unchanged') {
            result.push(rows[i]);
            i++;
        } else if (rows[i].type === 'removed') {
            // Collect consecutive removed lines
            const removed = [];
            while (i < rows.length && rows[i].type === 'removed') {
                removed.push(rows[i]);
                i++;
            }
            // Collect consecutive added lines
            const added = [];
            while (i < rows.length && rows[i].type === 'added') {
                added.push(rows[i]);
                i++;
            }
            // Pair them
            const maxLen = Math.max(removed.length, added.length);
            for (let j = 0; j < maxLen; j++) {
                const oldRow = removed[j] || { oldNum: '', oldText: '', type: 'blank' };
                const newRow = added[j] || { newNum: '', newText: '', type: 'blank' };
                result.push({
                    oldNum: oldRow.oldNum,
                    newNum: newRow.newNum,
                    oldText: oldRow.oldText,
                    newText: newRow.newText,
                    type: j < removed.length && j < added.length ? 'changed' : (j < removed.length ? 'removed' : 'added')
                });
            }
        } else if (rows[i].type === 'added') {
            // Added without preceding removed
            result.push({
                oldNum: null,
                newNum: rows[i].newNum,
                oldText: '',
                newText: rows[i].newText,
                type: 'added'
            });
            i++;
        } else {
            result.push(rows[i]);
            i++;
        }
    }

    return result;
}

function escapeHtml(str) {
    if (!str) return '';
    return str.replace(/&/g, '&').replace(/</g, '<').replace(/>/g, '>').replace(/"/g, '"');
}

// Interactive divider resizing logic for sidebar and assistant panel
function initResizers() {
    const sidebar = document.querySelector('.sidebar');
    const sidebarResizer = $('sidebarResizer');
    
    if (sidebar && sidebarResizer) {
        sidebarResizer.addEventListener('mousedown', (e) => {
            e.preventDefault();
            document.body.style.cursor = 'col-resize';
            sidebarResizer.classList.add('dragging');
            
            function onMouseMove(moveEvent) {
                const newWidth = moveEvent.clientX;
                if (newWidth > 200 && newWidth < 600) {
                    sidebar.style.width = `${newWidth}px`;
                    sidebar.style.minWidth = `${newWidth}px`;
                }
            }
            
            function onMouseUp() {
                document.body.style.cursor = '';
                sidebarResizer.classList.remove('dragging');
                document.removeEventListener('mousemove', onMouseMove);
                document.removeEventListener('mouseup', onMouseUp);
                
                if (window.monacoEditor) {
                    window.monacoEditor.layout();
                }
            }
            
            document.addEventListener('mousemove', onMouseMove);
            document.addEventListener('mouseup', onMouseUp);
        });
    }

    const chatPane = document.querySelector('.workspace-chat-pane');
    const chatResizer = $('chatResizer');
    const workspaceContainer = document.querySelector('.project-workspace-container');

    if (chatPane && chatResizer && workspaceContainer) {
        chatResizer.addEventListener('mousedown', (e) => {
            e.preventDefault();
            document.body.style.cursor = 'col-resize';
            chatResizer.classList.add('dragging');

            const editorContainer = $('monacoEditorContainer');
            if (editorContainer) editorContainer.style.pointerEvents = 'none';
            
            const initialPaneWidth = chatPane.getBoundingClientRect().width;
            const startX = e.clientX;

            function onMouseMove(moveEvent) {
                const deltaX = moveEvent.clientX - startX;
                const newWidth = initialPaneWidth - deltaX;
                const containerWidth = workspaceContainer.getBoundingClientRect().width;
                
                if (newWidth > 280 && newWidth < containerWidth - 300) {
                    chatPane.style.width = `${newWidth}px`;
                    
                    if (window.monacoEditor) {
                        window.monacoEditor.layout();
                    }
                }
            }
            
            function onMouseUp() {
                document.body.style.cursor = '';
                chatResizer.classList.remove('dragging');
                if (editorContainer) editorContainer.style.pointerEvents = 'auto';
                
                document.removeEventListener('mousemove', onMouseMove);
                document.removeEventListener('mouseup', onMouseUp);
                
                if (window.monacoEditor) {
                    window.monacoEditor.layout();
                }
            }
            
            document.addEventListener('mousemove', onMouseMove);
            document.addEventListener('mouseup', onMouseUp);
        });
    }
}
