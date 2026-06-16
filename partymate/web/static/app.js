/* =========================================================
   PartyMate — 党务智能助手 Web UI (客户端逻辑 v1.3)
   ========================================================= */

// ==================== 工具函数 ====================

function escapeHtml(text) {
  const map = {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;'};
  return text.replace(/[&<>"']/g, m => map[m]);
}

const TOOL_NAMES = {
  'search_knowledge': '检索知识库',
  'web_search': '🌐 联网搜索',
  'get_dashboard_summary': '获取系统概况',
  'query_member': '查询成员信息',
  'query_materials': '检查成员材料',
  'create_reminder': '创建待办提醒',
  'add_member_memory': '记录成员变动',
  'generate_meeting_plan': '生成会议方案'
};

window.globalRagSources = {};

function showCitation(el, id) {
  const source = window.globalRagSources[id];
  if (!source) return;
  
  let popover = document.getElementById('citationPopover');
  if (!popover) {
    popover = document.createElement('div');
    popover.id = 'citationPopover';
    popover.className = 'citation-popover';
    document.body.appendChild(popover);
  }
  
  let contentHtml = `<strong>${escapeHtml(source.title)}</strong><br>`;
  if (source.href) {
    contentHtml += `<a href="${escapeHtml(source.href)}" target="_blank" style="color:var(--gold);font-size:12px;">🔗 查看原文</a><br>`;
  }
  contentHtml += `<div style="margin-top:4px; font-size:12px; opacity:0.9;">${escapeHtml(source.content)}</div>`;
  
  popover.innerHTML = contentHtml;
  popover.style.display = 'block';
  
  const rect = el.getBoundingClientRect();
  popover.style.left = (rect.left + window.scrollX) + 'px';
  popover.style.top = (rect.bottom + window.scrollY + 8) + 'px';
}

function hideCitation() {
  const popover = document.getElementById('citationPopover');
  if (popover) {
    popover.style.display = 'none';
  }
}

function formatAIOutput(text) {
  let html = '';
  if (typeof marked !== 'undefined') {
    html = marked.parse(text);
  } else {
    // Fallback
    const safe = escapeHtml(text);
    const bolded = safe.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
    const headered = bolded.replace(/^### (.+)$/gm, '<h4 style="margin:10px 0 4px;color:var(--red);font-size:14px">$1</h4>');
    const paragraphs = headered.replace(/^## (.+)$/gm, '<h3 style="margin:12px 0 6px;color:var(--red);font-size:15px">$1</h3>');
    html = paragraphs.replace(/\n\n/g, '</p><p>').replace(/\n/g, '<br>').replace(/\|/g, '│');
  }
  
  // 替换 [1], [W1] 等标号为互动组件
  html = html.replace(/\[([Ww]?\d+)\]/g, '<sup class="rag-citation" onmouseenter="showCitation(this, \'$1\')" onmouseleave="hideCitation()">$1</sup>');
  return html;
}

function getTimestamp() {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')} ${String(d.getHours()).padStart(2,'0')}:${String(d.getMinutes()).padStart(2,'0')}`;
}

function showLoadingOn(element) {
  if (!element) return;
  element.innerHTML = '<div class="loading" style="padding:20px;text-align:center">处理中</div>';
}

// ==================== Tab 切换 ====================

function switchTab(tabId) {
  document.querySelectorAll('.tab-pane').forEach(el => el.classList.remove('active'));
  document.querySelectorAll('.nav-btn').forEach(el => el.classList.remove('active'));
  document.getElementById('pane-' + tabId).classList.add('active');
  const btn = document.querySelector(`[data-tab="${tabId}"]`);
  if (btn) btn.classList.add('active');
}

// ==================== 状态检查 ====================

async function checkStatus() {
  const dot = document.getElementById('statusDot');
  const text = document.getElementById('statusText');
  try {
    const resp = await fetch('/api/status');
    const data = await resp.json();
    dot.className = 'status-dot online';
    const ollamaStatus = data.ollama ? 'AI 在线' : 'AI 未连接';
    const ragStatus = data.rag && data.rag.ready ? 'RAG ✓' : 'RAG ✗';
    text.textContent = '运行中 · ' + ollamaStatus + ' · ' + ragStatus;
    if (data.version) {
      const vEl = document.getElementById('versionDisplay');
      if (vEl) vEl.textContent = data.version;
    }
    return data;
  } catch {
    dot.className = 'status-dot offline';
    text.textContent = '无法连接';
    return null;
  }
}

// ==================== 日期 ====================

function setDate() {
  const now = new Date();
  const weekdays = ['日','一','二','三','四','五','六'];
  document.getElementById('headerDate').textContent =
    `${now.getFullYear()}年${String(now.getMonth()+1).padStart(2,'0')}月${String(now.getDate()).padStart(2,'0')}日 周${weekdays[now.getDay()]}`;
}

// ==================== API 调用 ====================

async function callAPI(endpoint, body, method) {
  method = method || (body ? 'POST' : 'GET');
  const options = {
    method: method,
    headers: {'Content-Type': 'application/json'}
  };
  if (body) {
    options.body = JSON.stringify(body);
  }
  const resp = await fetch('/api/' + endpoint, options);
  return await resp.json();
}

async function uploadFile(file) {
  const formData = new FormData();
  formData.append('file', file);
  const resp = await fetch('/api/upload', {
    method: 'POST',
    body: formData,
  });
  return await resp.json();
}

// ==================== 文件上传 - 材料检查 ====================

async function handleCheckDrop(e) {
  e.preventDefault();
  document.getElementById('checkDropzone').classList.remove('dragover');
  const file = e.dataTransfer.files[0];
  if (file) await processCheckFile(file);
}

async function handleCheckFileSelect(e) {
  const file = e.target.files[0];
  if (file) await processCheckFile(file);
  e.target.value = '';
}

async function processCheckFile(file) {
  const validExts = ['.pdf','.docx','.doc','.png','.jpg','.jpeg','.bmp','.tiff'];
  const ext = '.' + file.name.split('.').pop().toLowerCase();
  if (!validExts.includes(ext)) {
    alert('不支持的文件格式。支持: ' + validExts.join(', '));
    return;
  }

  // 显示文件信息
  const fileInfo = document.getElementById('checkFileInfo');
  fileInfo.style.display = 'block';
  fileInfo.innerHTML = `
    <div class="file-preview-bar">
      <span class="file-icon">📄</span>
      <div class="file-info">
        <div class="file-name">${escapeHtml(file.name)}</div>
        <div class="file-meta">${(file.size / 1024).toFixed(1)} KB · 上传解析中...</div>
      </div>
      <button class="file-remove" onclick="clearCheckFile()">&times;</button>
    </div>`;

  // 上传 + 解析
  try {
    const data = await uploadFile(file);
    if (data.error) {
      fileInfo.innerHTML = `<div style="color:var(--red);padding:8px">❌ ${escapeHtml(data.error)}</div>`;
      return;
    }
    if (data.text.length > 50000) {
      fileInfo.innerHTML = `<div style="color:var(--red);padding:8px">❌ 文件内容过长 (${data.text.length} 字)，请分段处理</div>`;
      return;
    }

    // 更新预览
    fileInfo.innerHTML = `
      <div class="file-preview-bar">
        <span class="file-icon">📄</span>
        <div class="file-info">
          <div class="file-name">${escapeHtml(data.filename)}</div>
          <div class="file-meta">${data.pages} 页 · ${data.text.length} 字 · ${data.type.toUpperCase()}</div>
        </div>
        <button class="file-remove" onclick="clearCheckFile()">&times;</button>
      </div>`;

    // 显示双栏
    const splitResult = document.getElementById('checkSplitResult');
    splitResult.style.display = 'grid';
    document.getElementById('checkPreviewBody').textContent = data.preview + '\n\n[全文 ' + data.text.length + ' 字，请查看右侧检查结果]';
    document.getElementById('checkPreviewMeta').textContent = data.filename;

    // 保存文本以供后续
    window._checkRawText = data.text;
    window._checkFileName = data.filename;

    // 自动执行检查
    await runCheckDocWithFile(data.text, data.filename);
  } catch (e) {
    fileInfo.innerHTML = `<div style="color:var(--red);padding:8px">❌ 上传失败: ${escapeHtml(e.message)}</div>`;
  }
}

function clearCheckFile() {
  document.getElementById('checkFileInfo').style.display = 'none';
  document.getElementById('checkFileInfo').innerHTML = '';
  document.getElementById('checkSplitResult').style.display = 'none';
  document.getElementById('checkDocResult').style.display = 'none';
  window._checkRawText = null;
  window._checkFileName = null;
}

// ==================== 材料检查 ====================

async function runCheckDoc() {
  const raw = document.getElementById('checkDocInput').value.trim();
  if (!raw) { alert('请粘贴材料内容或上传文件'); return; }
  await runCheckDocWithFile(raw, '粘贴文本');
}

async function runCheckDocWithFile(text, sourceName) {
  const resultEl = document.getElementById('checkDocResult');
  const splitResult = document.getElementById('checkSplitResult');
  const resultsBody = document.getElementById('checkResultsBody');

  // 显示双栏
  splitResult.style.display = 'grid';
  document.getElementById('checkPreviewBody').textContent = text.substring(0, 1000) + '\n\n... [共 ' + text.length + ' 字]';
  document.getElementById('checkPreviewMeta').textContent = sourceName + ' · ' + text.length + ' 字';

  showLoadingOn(resultsBody);

  try {
    const data = await callAPI('check-doc', {raw: text});
    if (data.error) {
      resultsBody.innerHTML = `<div style="color:var(--red)">❌ ${escapeHtml(data.error)}</div>`;
      return;
    }

    // 结构化渲染结果
    renderCheckResults(resultsBody, data, text);
    addToRecentFiles(sourceName, 'check-doc', text.length);

    // 同步更新旧式结果（备用）
    resultEl.style.display = 'block';
    let fullResult = data.result;
    if (data.citations) fullResult += '\n\n' + data.citations;
    document.getElementById('checkDocBody').textContent = fullResult;

    // 统计
    incrementStat('checks');
  } catch (e) {
    resultsBody.innerHTML = `<div style="color:var(--red)">❌ 请求失败: ${escapeHtml(e.message)}</div>`;
  }
}

function renderCheckResults(container, data, rawText) {
  const result = data.result || '';
  const citations = data.citations || '';
  const docType = data.doc_type || '未知';

  let html = `<div style="margin-bottom:10px">
    <span style="display:inline-block;background:var(--gold);color:#fff;padding:2px 10px;border-radius:4px;font-size:11px">
      材料类型: ${escapeHtml(docType)}
    </span>
    <span style="margin-left:8px;color:var(--text-dim);font-size:11px">
      ${data.word_count || 0} 字
    </span>
  </div>`;

  // 解析结果中的检查项（按行分割）
  const lines = result.split('\n').filter(l => l.trim());
  let inIssue = false;
  let currentIssue = '';
  let issueCount = 0;

  for (const line of lines) {
    const trimmed = line.trim();

    // 问题标记
    if (/^[❌⚠️❓]\s*/.test(trimmed) || /^[-•]\s*/.test(trimmed) || /^\d+[.、]/.test(trimmed)) {
      if (currentIssue) {
        html += renderIssueItem(currentIssue);
        issueCount++;
        currentIssue = '';
      }
      inIssue = true;
      currentIssue = trimmed;
    } else if (trimmed.startsWith('✅') || trimmed.startsWith('✓') || trimmed.startsWith('✔')) {
      if (currentIssue) {
        html += renderIssueItem(currentIssue);
        issueCount++;
        currentIssue = '';
      }
      // 通过项 - 绿色显示
      html += `<div style="color:#2e7d32;padding:6px 0;font-size:13px">✅ ${escapeHtml(trimmed.replace(/^[✅✓✔]\s*/, ''))}</div>`;
    } else if (inIssue && trimmed) {
      currentIssue += '\n' + trimmed;
    } else if (trimmed.startsWith('【')) {
      // 段落标题
      html += `<div style="font-weight:600;margin:10px 0 4px;color:var(--text);font-size:13px">${escapeHtml(trimmed)}</div>`;
    } else if (trimmed) {
      html += `<div style="padding:4px 0;font-size:13px;color:var(--text-muted)">${escapeHtml(trimmed)}</div>`;
    }
  }
  if (currentIssue) {
    html += renderIssueItem(currentIssue);
    issueCount++;
  }

  // 数量统计
  html = `<div style="display:flex;gap:12px;margin-bottom:12px">
    <span style="background:var(--red-light);color:var(--red);padding:4px 12px;border-radius:6px;font-size:12px;font-weight:600">
      ⚠️ ${issueCount} 个问题
    </span>
    <span style="background:#f0faf0;color:#2e7d32;padding:4px 12px;border-radius:6px;font-size:12px;font-weight:600">
      ✅ ${(result.match(/[✅✓✔]/g) || []).length} 项通过
    </span>
  </div>` + html;

  // 规程引用
  if (citations) {
    html += `<div class="citation-box">
      <div class="citation-title">📖 规程引用</div>
      <div class="citation-text">${formatAIOutput(citations)}</div>
    </div>`;
  }

  container.innerHTML = html;
}

function renderIssueItem(text) {
  const firstLine = text.split('\n')[0];
  // 提取标签（如果有）
  const tagMatch = firstLine.match(/^[❌⚠️❓]\s*\[?([^\]]+)\]?\s*/);
  const tag = tagMatch ? tagMatch[1].trim().substring(0, 20) : '问题';
  const body = text.replace(/^[❌⚠️❓]\s*(\[?[^\]]+\]?\s*)?/, '').trim();

  return `<div class="issue-item">
    <div class="issue-tag">${escapeHtml(tag)}</div>
    <div class="issue-text">${escapeHtml(body || firstLine)}</div>
  </div>`;
}

// ==================== 文件上传 - 会议整理 ====================

async function handleMeetingDrop(e) {
  e.preventDefault();
  document.getElementById('meetingDropzone').classList.remove('dragover');
  const file = e.dataTransfer.files[0];
  if (file) await processMeetingFile(file);
}

async function handleMeetingFileSelect(e) {
  const file = e.target.files[0];
  if (file) await processMeetingFile(file);
  e.target.value = '';
}

async function processMeetingFile(file) {
  const validExts = ['.pdf','.docx','.doc','.png','.jpg','.jpeg','.bmp','.tiff'];
  const ext = '.' + file.name.split('.').pop().toLowerCase();
  if (!validExts.includes(ext)) {
    alert('不支持的文件格式');
    return;
  }

  const fileInfo = document.getElementById('meetingFileInfo');
  fileInfo.style.display = 'block';
  fileInfo.innerHTML = `<div class="file-preview-bar">
    <span class="file-icon">📄</span>
    <div class="file-info">
      <div class="file-name">${escapeHtml(file.name)}</div>
      <div class="file-meta">解析中...</div>
    </div>
    <button class="file-remove" onclick="clearMeetingFile()">&times;</button>
  </div>`;

  try {
    const data = await uploadFile(file);
    if (data.error) {
      fileInfo.innerHTML = `<div style="color:var(--red);padding:8px">❌ ${escapeHtml(data.error)}</div>`;
      return;
    }
    // 填充到文本域
    document.getElementById('meetingInput').value = data.text;
    fileInfo.innerHTML = `<div class="file-preview-bar">
      <span class="file-icon">📄</span>
      <div class="file-info">
        <div class="file-name">${escapeHtml(data.filename)}</div>
        <div class="file-meta">${data.text.length} 字 · 已填入下方编辑框</div>
      </div>
      <button class="file-remove" onclick="clearMeetingFile()">&times;</button>
    </div>`;
    addToRecentFiles(file.name, 'meeting', data.text.length);
  } catch (e) {
    fileInfo.innerHTML = `<div style="color:var(--red);padding:8px">❌ 上传失败: ${escapeHtml(e.message)}</div>`;
  }
}

function clearMeetingFile() {
  document.getElementById('meetingFileInfo').style.display = 'none';
  document.getElementById('meetingFileInfo').innerHTML = '';
}

// ==================== 会议整理（续） ====================

let _lastMeetingRaw = '';

async function runMeeting(opts) {
  let raw = document.getElementById('meetingInput').value.trim();
  if (!raw) { alert('请粘贴会议记录或上传文件'); return; }
  _lastMeetingRaw = raw;
  const resultEl = document.getElementById('meetingResult');
  resultEl.style.display = 'block';
  showLoadingOn(document.getElementById('meetingBody'));
  const body = {raw, export_docx: opts?.exportDocx || false};
  try {
    const data = await callAPI('meeting', body);
    document.getElementById('meetingBody').textContent = data.result || '无结果';
    const dlBtn = document.getElementById('meetingDownloadBtn');
    if (data.docx_path) {
      dlBtn.style.display = 'inline-flex';
      dlBtn.dataset.path = data.docx_path;
    } else {
      dlBtn.style.display = 'none';
    }
    // Show parse actions button
    const parseBtn = document.getElementById('meetingParseActionsBtn');
    parseBtn.style.display = 'inline-flex';
    incrementStat('meetings');
  } catch (e) {
    document.getElementById('meetingBody').textContent = '❌ 请求失败: ' + e.message;
  }
}

async function parseMeetingActions() {
  if (!_lastMeetingRaw) { alert('请先整理会议记录'); return; }
  const parseBtn = document.getElementById('meetingParseActionsBtn');
  parseBtn.textContent = '⏳ 解析中...';
  parseBtn.disabled = true;
  try {
    const data = await callAPI('meeting/parse-actions', {
      raw: _lastMeetingRaw,
      meeting_title: (new Date().toISOString().slice(0, 10)) + ' 会议待办',
      member_id: window._chatMemberId || null,
    });
    if (data.workflow) {
      const count = data.workflow.written_count || 0;
      alert(`✅ 已自动解析并写入 ${count} 条待办事项到提醒系统`);
    }
  } catch (e) {
    alert('❌ 解析失败: ' + e.message);
  } finally {
    parseBtn.textContent = '📌 解析待办并写入提醒';
    parseBtn.disabled = false;
  }
}

// ==================== 内容生成 ====================

async function runContent(opts) {
  const topic = document.getElementById('contentTopic').value.trim();
  if (!topic) { alert('请输入学习主题'); return; }
  const resultEl = document.getElementById('contentResult');
  resultEl.style.display = 'block';
  showLoadingOn(document.getElementById('contentBody'));
  const body = {topic, export_pptx: opts?.exportPptx || false};
  try {
    const data = await callAPI('content', body);
    document.getElementById('contentBody').textContent = data.result || '无结果';
    const dlBtn = document.getElementById('contentDownloadBtn');
    if (data.pptx_path) {
      dlBtn.style.display = 'inline-flex';
      dlBtn.dataset.path = data.pptx_path;
    } else {
      dlBtn.style.display = 'none';
    }
    // 显示规程引用
    const citEl = document.getElementById('contentCitations');
    if (data.citations) {
      citEl.style.display = 'block';
      document.getElementById('contentCitationsBody').textContent = data.citations;
    } else {
      citEl.style.display = 'none';
    }
  } catch (e) {
    document.getElementById('contentBody').textContent = '❌ 请求失败: ' + e.message;
  }
}

// ==================== AI 对话（带文件上传） ====================

async function handleChatFileSelect(e) {
  const file = e.target.files[0];
  if (!file) return;
  e.target.value = '';

  const label = document.getElementById('chatFileLabel');
  label.textContent = '⏳ 解析中...';

  try {
    const data = await uploadFile(file);
    if (data.error) {
      label.textContent = '❌ ' + data.error;
      return;
    }
    label.innerHTML = `📎 ${escapeHtml(data.filename)} (${data.text.length}字)`;
    // 保存到 window 中，用户发消息时自动带上
    window._chatFileContent = data.text;
    window._chatFileName = data.filename;

    // 自动在输入框提示
    document.getElementById('chatInput').placeholder = `已上传 ${data.filename}，输入你的问题... (文件解析为上下文)`;
  } catch (e) {
    label.textContent = '❌ 上传失败';
  }
}

function updateChatMemberContextBar() {
  const el = document.getElementById('chatMemberContextBar');
  if (!el) return;
  if (window._chatMemberId) {
    el.innerHTML = `
      <span>🎯 当前成员上下文: <strong>${escapeHtml(String(window._chatMemberName || ''))}</strong></span>
      <button class="btn btn-sm" onclick="clearChatMemberContext()">清除</button>
    `;
    return;
  }
  el.textContent = '当前未绑定成员上下文，AI 对话为通用模式';
}

function bindMemberChatContext(memberId, memberName) {
  window._chatMemberId = memberId;
  window._chatMemberName = memberName || '';
  updateChatMemberContextBar();
  switchTab('chat');
}

function clearChatMemberContext() {
  window._chatMemberId = null;
  window._chatMemberName = '';
  updateChatMemberContextBar();
}

window._currentChatSessionId = null;

async function loadChatSessions() {
  try {
    const data = await callAPI('chat/sessions');
    const list = document.getElementById('chatSessionsList');
    if (!data.sessions || data.sessions.length === 0) {
      list.innerHTML = '<div style="color:var(--text-muted);font-size:12px;text-align:center;padding:10px">暂无会话</div>';
      return;
    }
    let html = '';
    for (const session of data.sessions) {
      const isActive = session.id === window._currentChatSessionId ? 'active' : '';
      html += `
        <div class="chat-session-item ${isActive}" onclick="switchChatSession('${session.id}')" id="sess-${session.id}">
          <div class="chat-session-title">${escapeHtml(session.title || '新对话')}</div>
          <div class="chat-session-del" onclick="deleteChatSession('${session.id}', event)">✕</div>
        </div>
      `;
    }
    list.innerHTML = html;
  } catch (e) {
    console.error('加载会话列表失败', e);
  }
}

function prepareNewSession() {
  window._currentChatSessionId = null;
  const messagesEl = document.getElementById('chatMessages');
  if (messagesEl) {
    messagesEl.innerHTML = `
      <div class="msg msg-ai">
        <div class="msg-avatar">🤖</div>
        <div class="msg-bubble">
          <div style="font-size: 13px; line-height: 1.6; color: var(--text);">
            <p>您好！我是 <strong>PartyMate</strong> (党务智能助手)。我可以帮助您：</p>
            <ul style="padding-left:20px; color:var(--text-dim); margin:8px 0;">
              <li>检索党务知识、规章制度</li>
              <li>查询党员状态，审核发展材料</li>
              <li>解答日常党务工作问题</li>
            </ul>
            <p style="color:var(--text-dim);">请在下方输入您的问题，或点击左下角上传相关文档。</p>
          </div>
        </div>
      </div>
    `;
  }
  const list = document.getElementById('chatSessionsList');
  if (list) {
    list.querySelectorAll('.chat-session-item').forEach(el => el.classList.remove('active'));
  }
}

async function createNewSession(firstMessage) {
  try {
    const title = firstMessage ? firstMessage.substring(0, 15) : ('新对话 ' + new Date().toLocaleTimeString());
    const data = await callAPI('chat/sessions', { title: title, member_id: window._chatMemberId }, 'POST');
    window._currentChatSessionId = data.id;
    window._sessionRenamed = false;  // 新对话：尚未命名
    await loadChatSessions();
  } catch (e) {
    alert('创建会话失败: ' + e.message);
  }
}

async function switchChatSession(id) {
  window._currentChatSessionId = id;
  window._sessionRenamed = true;  // 已有会话：不自动重命名
  await loadChatSessions();
  await loadChatMessages(id);
}

async function deleteChatSession(id, e) {
  if(e) e.stopPropagation();
  // 使用自定义确认对话框
  showDeleteConfirm('确定要删除此对话吗？删除后无法恢复。', async () => {
    try {
      await fetch('/api/chat/sessions/' + id, { method: 'DELETE' });
      if (window._currentChatSessionId === id) {
        window._currentChatSessionId = null;
        document.getElementById('chatMessages').innerHTML = '';
      }
      await loadChatSessions();
    } catch (err) {
      showToast('删除失败: ' + err.message, 'error');
    }
  });
}

// ── 自定义确认框 ──────────────────────────────────────────────────

function showDeleteConfirm(message, onConfirm) {
  let overlay = document.getElementById('deleteConfirmOverlay');
  if (!overlay) {
    overlay = document.createElement('div');
    overlay.id = 'deleteConfirmOverlay';
    overlay.style.cssText = [
      'position:fixed', 'inset:0', 'z-index:9999',
      'display:flex', 'align-items:center', 'justify-content:center',
      'background:rgba(0,0,0,0.45)', 'backdrop-filter:blur(3px)'
    ].join(';');
    document.body.appendChild(overlay);
  }
  overlay.innerHTML = `
    <div style="
      background:var(--surface,#1e1e2e);
      border:1px solid var(--border,rgba(255,255,255,0.1));
      border-radius:14px;
      padding:28px 32px;
      min-width:300px;
      max-width:420px;
      box-shadow:0 20px 60px rgba(0,0,0,0.5);
      animation:fadeInScale .15s ease;
    ">
      <div style="font-size:22px;margin-bottom:10px;text-align:center">🗑️</div>
      <div style="font-size:14px;color:var(--text,#e0e0e0);text-align:center;margin-bottom:22px;line-height:1.6">${escapeHtml(message)}</div>
      <div style="display:flex;gap:10px;justify-content:center">
        <button id="deleteConfirmCancel" class="btn btn-sm" style="flex:1;padding:9px 0;border-radius:8px">取消</button>
        <button id="deleteConfirmOk" class="btn btn-sm" style="flex:1;padding:9px 0;border-radius:8px;background:var(--red,#e53935);color:#fff;border-color:transparent">删除</button>
      </div>
    </div>
  `;
  overlay.style.display = 'flex';

  const close = () => { overlay.style.display = 'none'; };
  document.getElementById('deleteConfirmCancel').onclick = close;
  overlay.addEventListener('click', (ev) => { if (ev.target === overlay) close(); }, { once: true });
  document.getElementById('deleteConfirmOk').onclick = () => {
    close();
    onConfirm();
  };
}

// ── 轻提示 Toast ──────────────────────────────────────────────────

function showToast(message, type) {
  let toast = document.getElementById('appToast');
  if (!toast) {
    toast = document.createElement('div');
    toast.id = 'appToast';
    toast.style.cssText = [
      'position:fixed', 'bottom:24px', 'left:50%', 'transform:translateX(-50%)',
      'padding:10px 22px', 'border-radius:8px', 'font-size:13px',
      'z-index:10000', 'pointer-events:none', 'transition:opacity .3s'
    ].join(';');
    document.body.appendChild(toast);
  }
  toast.textContent = message;
  toast.style.background = type === 'error' ? 'var(--red,#e53935)' : '#2e7d32';
  toast.style.color = '#fff';
  toast.style.opacity = '1';
  clearTimeout(toast._timer);
  toast._timer = setTimeout(() => { toast.style.opacity = '0'; }, 2500);
}

async function loadChatMessages(id) {
  try {
    const data = await fetch('/api/chat/sessions/' + id + '/messages').then(r => r.json());
    const messagesEl = document.getElementById('chatMessages');
    messagesEl.innerHTML = '';
    if (data.messages) {
      for (const msg of data.messages) {
        const div = document.createElement('div');
        div.className = 'msg ' + (msg.role === 'user' ? 'msg-user' : 'msg-ai');
        const avatar = msg.role === 'user' ? '🧑' : '🤖';
        let html = `<div class="msg-avatar">${avatar}</div><div class="msg-bubble">${formatAIOutput(msg.content)}</div>`;
        div.innerHTML = html;
        messagesEl.appendChild(div);
      }
      messagesEl.scrollTop = messagesEl.scrollHeight;
    }
  } catch (e) {
    console.error('加载消息失败', e);
  }
}

async function sendChat() {
  const input = document.getElementById('chatInput');
  let msg = input.value.trim();
  const messagesEl = document.getElementById('chatMessages');
  const statusEl = document.getElementById('chatStatus');
  const sendBtn = document.getElementById('chatSendBtn');

  if (!window._currentChatSessionId) {
    // Lazy creation: only create session when sending the first message
    let firstMsgTitle = msg || (window._chatFileName ? `上传文件: ${window._chatFileName}` : '新对话');
    await createNewSession(firstMsgTitle);
    
    // Clear the greeting message before appending user's message
    const messagesEl = document.getElementById('chatMessages');
    const hasGreeting = messagesEl.innerHTML.includes('PartyMate');
    if (hasGreeting) {
        messagesEl.innerHTML = '';
    }
  }

  // 如果有文件内容且没有消息，默认询问
  if (!msg && window._chatFileContent) {
    msg = '请检查这份文件的内容是否符合规范';
  }
  if (!msg) return;

  // 组装消息：文件内容 + 用户输入
  let fullMsg = msg;
  if (window._chatFileContent) {
    fullMsg = `[文件: ${window._chatFileName}]\n\`\`\`\n${window._chatFileContent.substring(0, 8000)}\n\`\`\`\n\n用户提问: ${msg}`;
    // 发送后清空文件上下文
    window._chatFileContent = null;
    window._chatFileName = null;
    document.getElementById('chatFileLabel').textContent = '';
    input.placeholder = "输入你的问题...";
  }

  // 添加用户消息
  const userDiv = document.createElement('div');
  userDiv.className = 'msg msg-user';
  userDiv.innerHTML = '<div class="msg-avatar">🧑</div><div class="msg-bubble">' + escapeHtml(msg) + '</div>';
  messagesEl.appendChild(userDiv);
  messagesEl.scrollTop = messagesEl.scrollHeight;
  input.value = '';
  statusEl.textContent = '⏳ 思考中...';

  try {
    const aiDiv = document.createElement('div');
    aiDiv.className = 'msg msg-ai';
    aiDiv.innerHTML = '<div class="msg-avatar">🤖</div><div class="msg-bubble"></div>';
    messagesEl.appendChild(aiDiv);
    const bubble = aiDiv.querySelector('.msg-bubble');
    
    let currentContent = '';
    
    const response = await fetch('/api/chat/stream', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        message: fullMsg, 
        member_id: window._chatMemberId || null,
        session_id: window._currentChatSessionId
      })
    });
    
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }
    
    const reader = response.body.getReader();
    const decoder = new TextDecoder("utf-8");
    let buffer = '';
    let currentEvent = null;
    
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n');
      buffer = lines.pop(); // last partial line
      
      for (const line of lines) {
        if (line.startsWith('event: ')) {
          currentEvent = line.substring(7).trim();
        } else if (line.startsWith('data: ')) {
          const dataStr = line.substring(6).trim();
          if (!dataStr) continue;
          
          let data;
          try { data = JSON.parse(dataStr); } catch(e) { continue; }
          
          if (currentEvent === 'thinking') {
            let thinkEl = bubble.querySelector('.msg-thinking');
            if (!thinkEl) {
              thinkEl = document.createElement('div');
              thinkEl.className = 'msg-thinking';
              bubble.insertBefore(thinkEl, bubble.firstChild);
            }
            thinkEl.textContent += data;
          } else if (currentEvent === 'tool_call') {
            const toolHumanName = TOOL_NAMES[data.name] || data.name;
            const toolEl = document.createElement('div');
            toolEl.id = 'tool-' + data.name + '-' + Date.now();
            toolEl.dataset.toolname = data.name;
            
            if (data.name === 'create_reminder' || data.name === 'add_member_memory' || data.name === 'run_python_code') {
              let args = {};
              try { args = JSON.parse(data.args); } catch(e) {}
              
              let typeLabel = '';
              let textContent = '';
              if (data.name === 'create_reminder') { typeLabel = '待办提醒'; textContent = args.title; }
              else if (data.name === 'add_member_memory') { typeLabel = '成员记忆'; textContent = args.content; }
              else if (data.name === 'run_python_code') { typeLabel = '执行Python代码'; textContent = args.code; }
              
              toolEl.className = 'confirmation-card';
              toolEl.innerHTML = `
                <p>⚠️ 待确认: ${typeLabel}</p>
                <div style="font-size:13px; margin-bottom:8px; white-space:pre-wrap; font-family:monospace;">${escapeHtml(textContent)}</div>
                <div class="btn-group">
                  <button class="btn btn-sm btn-gold" onclick="confirmAgentAction('${data.name}', '${escapeHtml(data.args.replace(/'/g, "\\'"))}', this)">确认执行</button>
                  <button class="btn btn-sm" onclick="this.parentElement.parentElement.innerHTML='<i>已取消</i>'">取消</button>
                </div>
              `;
            } else {
              toolEl.className = 'tool-details-wrapper';
              toolEl.innerHTML = `
                <details class="tool-details" open>
                  <summary>🛠️ 系统操作：${toolHumanName} <span class="tool-spinner">🔄</span></summary>
                  <div class="tool-content">
                    <div class="tool-args"><strong>参数:</strong> ${escapeHtml(data.args)}</div>
                    <div class="tool-result-container" style="display:none;"></div>
                  </div>
                </details>
              `;
            }
            bubble.appendChild(toolEl);
          } else if (currentEvent === 'tool_result') {
            const toolHumanName = TOOL_NAMES[data.name] || data.name;
            
            // 缓存检索结果到 globalRagSources 以供悬浮气泡使用
            if (data.name === 'search_knowledge' || data.name === 'web_search') {
                try {
                    let res = JSON.parse(data.result);
                    let arr = res.knowledge || res.web_results || [];
                    arr.forEach(item => {
                        window.globalRagSources[item.id] = item;
                    });
                } catch(e) {}
            }

            // Find the last tool-details of this tool name and append result
            const toolWrappers = bubble.querySelectorAll('.tool-details-wrapper');
            const lastWrapper = Array.from(toolWrappers).filter(el => el.dataset.toolname === data.name).pop();
            if (lastWrapper) {
              const spinner = lastWrapper.querySelector('.tool-spinner');
              if (spinner) spinner.style.display = 'none';
              const resultContainer = lastWrapper.querySelector('.tool-result-container');
              if (resultContainer) {
                resultContainer.style.display = 'block';
                resultContainer.innerHTML = `<strong>结果:</strong> <pre style="margin:4px 0 0; white-space:pre-wrap; font-size:12px; color:#555;">${escapeHtml(data.result)}</pre>`;
              }
            }
          } else if (currentEvent === 'content') {
            // 首次收到内容时，异步触发 LLM 自动命名（仅新会话、仅一次）
            if (!window._sessionRenamed && window._currentChatSessionId) {
              autoRenameSession(window._currentChatSessionId, msg);
            }
            currentContent += data;
            let contentEl = bubble.querySelector('.msg-content-acc');
            if (!contentEl) {
              contentEl = document.createElement('div');
              contentEl.className = 'msg-content-acc';
              bubble.appendChild(contentEl);
            }
            contentEl.innerHTML = formatAIOutput(currentContent);
          } else if (currentEvent === 'error') {
            statusEl.textContent = '❌ 错误: ' + data;
          }
          messagesEl.scrollTop = messagesEl.scrollHeight;
        }
      }
    }
    statusEl.textContent = '';
  } catch (e) {
    const errDiv = document.createElement('div');
    errDiv.className = 'msg msg-ai';
    errDiv.innerHTML = '<div class="msg-avatar">❌</div><div class="msg-bubble" style="color:var(--red)">' + escapeHtml(e.message) + '</div>';
    messagesEl.appendChild(errDiv);
    statusEl.textContent = '';
  } finally {
    if (sendBtn) sendBtn.disabled = false;
    await loadChatSessions(); // Update session list metadata
  }
}

// ── 首次自动命名会话 ──────────────────────────────────────────────

async function autoRenameSession(sessionId, userQuestion) {
  if (window._sessionRenamed) return;  // 已命名则跳过
  window._sessionRenamed = true;       // 立即锁定，防止并发
  try {
    const resp = await fetch('/api/chat/sessions/' + sessionId + '/rename-title', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ question: userQuestion })
    });
    const result = await resp.json();
    if (result.ok) {
      // 更新侧边栏中该会话的标题（不重新加载整个列表，响应更快）
      const titleEl = document.querySelector('#sess-' + sessionId + ' .chat-session-title');
      if (titleEl) titleEl.textContent = result.title;
      await loadChatSessions();
    }
  } catch (_) {}
}

async function confirmAgentAction(name, argsStr, btn) {
  btn.disabled = true;
  btn.textContent = '执行中...';
  try {
    const args = JSON.parse(argsStr);
    if (name === 'create_reminder') {
      await callAPI('reminders', args, 'POST');
      btn.parentElement.parentElement.innerHTML = '✅ <b>已确认并写入成功</b>';
    } else if (name === 'add_member_memory') {
      const memberId = args.member_id;
      if(!memberId) throw new Error("缺少 member_id");
      await callAPI(`members/${memberId}/memories`, args, 'POST');
      btn.parentElement.parentElement.innerHTML = '✅ <b>已确认并写入成功</b>';
    } else if (name === 'run_python_code') {
      const result = await callAPI(`tools/run-python`, args, 'POST');
      btn.parentElement.parentElement.innerHTML = `✅ <b>执行完毕:</b><pre style="margin-top:8px;background:#1e1e1e;color:#d4d4d4;padding:8px;border-radius:4px;font-size:12px;overflow-x:auto;">${escapeHtml(result.output || '无输出')}</pre>`;
    }
  } catch(e) {
    btn.textContent = '❌ 执行失败: ' + e.message;
    btn.disabled = false;
  }
}

// ==================== 复制 & 下载 ====================

function copyResult(elId) {
  const el = document.getElementById(elId);
  const body = el.querySelector('.result-body') || el.querySelector('.split-panel-body');
  const text = body ? body.textContent : '';
  if (!text) return;
  navigator.clipboard.writeText(text).then(() => {
    const btn = event.target;
    const orig = btn.textContent;
    btn.textContent = '✅ 已复制';
    setTimeout(() => btn.textContent = orig, 1500);
  }).catch(() => {
    // fallback
    const range = document.createRange();
    range.selectNode(body);
    window.getSelection().removeAllRanges();
    window.getSelection().addRange(range);
    document.execCommand('copy');
  });
}

function downloadFile(path) {
  if (path) window.open('/api/download?path=' + encodeURIComponent(path), '_blank');
}

// ==================== 本地统计 + 最近文件 ====================

function getLocalData(key, def) {
  try {
    const val = localStorage.getItem('partymate_' + key);
    return val ? JSON.parse(val) : def;
  } catch { return def; }
}

function setLocalData(key, val) {
  try { localStorage.setItem('partymate_' + key, JSON.stringify(val)); } catch {}
}

function incrementStat(type) {
  const stats = getLocalData('stats', {checks: 0, meetings: 0, files: 0});
  if (type === 'checks') stats.checks = (stats.checks || 0) + 1;
  if (type === 'meetings') stats.meetings = (stats.meetings || 0) + 1;
  setLocalData('stats', stats);
  updateDashboardStats();
}

function addToRecentFiles(name, tool, chars) {
  const files = getLocalData('recent_files', []);
  files.unshift({
    name: name,
    tool: tool,
    chars: chars,
    time: getTimestamp(),
  });
  // 只保留最近 20 条
  if (files.length > 20) files.length = 20;
  setLocalData('recent_files', files);
  updateRecentFiles();
}

function updateDashboardStats() {
  const stats = getLocalData('stats', {checks: 0, meetings: 0, files: 0});
  const recentFiles = getLocalData('recent_files', []);

  const statChecks = document.getElementById('statChecks');
  const statMeetings = document.getElementById('statMeetings');
  const statFiles = document.getElementById('statFiles');

  if (statChecks) statChecks.textContent = stats.checks || 0;
  if (statMeetings) statMeetings.textContent = stats.meetings || 0;
  if (statFiles) statFiles.textContent = recentFiles.length || 0;
}

function updateRecentFiles() {
  const files = getLocalData('recent_files', []);
  const body = document.getElementById('recentFilesBody');
  const count = document.getElementById('recentCount');
  if (!body) return;

  if (count) count.textContent = files.length + ' 条';

  if (files.length === 0) {
    body.innerHTML = '<div class="recent-file-empty">暂无文件记录，开始使用后会自动保存</div>';
    return;
  }

  const toolNames = {'check-doc': '材料检查', 'meeting': '会议整理', 'content': '内容生成', 'chat': 'AI对话'};
  body.innerHTML = files.map(f =>
    `<div class="recent-file-item">
      <span>📄</span>
      <span class="file-name">${escapeHtml(f.name || '未知文件')}</span>
      <span style="font-size:11px;color:var(--text-muted)">${toolNames[f.tool] || f.tool}</span>
      <span class="file-size">${f.chars || 0}字 · ${f.time || ''}</span>
    </div>`
  ).join('');
}

// ==================== 右侧信息面板 ====================

/**
 * 根据当前 tab 加载右侧面板内容
 */
async function loadRightPanel(tabName) {
  const container = document.getElementById('rightPanelContent');
  if (!container) return;

  // 每个 tab 加载不同的数据
  switch (tabName) {
    case 'dashboard':
      await loadDashboardRightPanel(container);
      break;
    case 'check-doc':
      await loadCheckDocRightPanel(container);
      break;
    case 'meeting':
      await loadMeetingRightPanel(container);
      break;
    case 'content':
      await loadContentRightPanel(container);
      break;
    case 'chat':
      await loadChatRightPanel(container);
      break;
    case 'kanban':
      await loadKanbanRightPanel(container);
      break;
    case 'trace':
      await loadTraceRightPanel(container);
      break;
    case 'settings':
      await loadSettingsRightPanel(container);
      break;
    default:
      loadDefaultRightPanel(container);
  }
}

function loadDefaultRightPanel(container) {
  container.innerHTML = `
    <div class="rp-card">
      <div class="rp-header">📡 系统状态</div>
      <div class="rp-body">
        <div class="rp-status-item">
          <span class="rp-status-label">服务状态</span>
          <span class="rp-status-value" id="rpStatusValue">—</span>
        </div>
        <div class="rp-status-item">
          <span class="rp-status-label">版本</span>
          <span class="rp-status-value" id="rpVersionValue">—</span>
        </div>
      </div>
    </div>`;
}

async function loadDashboardRightPanel(container) {
  container.innerHTML = `<div style="color:var(--text-dim);padding:8px;text-align:center;font-size:12px">⏳ 加载中...</div>`;

  let statusData = null;
  let ragData = null;
  try {
    const [sResp, rResp] = await Promise.all([
      fetch('/api/status').then(r => r.json()).catch(() => null),
      fetch('/api/rag/status').then(r => r.json()).catch(() => null),
    ]);
    statusData = sResp;
    ragData = rResp;
  } catch (e) {}

  const ollamaStatus = statusData?.ollama ? '🟢 在线' : '🔴 未连接';
  const ocrStatus = statusData?.ocr ? '🟢 可用' : '⛔ 不可用';
  const version = statusData?.version || '—';
  const tools = statusData?.tools || [];
  const ragReady = ragData?.ready || statusData?.rag?.ready;
  const ragChunks = ragData?.chunks || statusData?.rag?.chunks || 0;

  let toolsHtml = '';
  if (tools.length > 0) {
    toolsHtml = tools.map(t => `<span class="rp-action-btn" style="padding:4px 8px;font-size:11px">🛠️ ${escapeHtml(t)}</span>`).join('');
  }

  container.innerHTML = `
    <!-- 知识库状态 -->
    <div class="rp-card">
      <div class="rp-header">📚 知识库状态</div>
      <div class="rp-body">
        <div class="rp-status-item">
          <span class="rp-status-label">RAG 就绪</span>
          <span class="rp-status-value ${ragReady ? 'ready' : 'not-ready'}">${ragReady ? '✅ 已就绪' : '⏳ 未就绪'}</span>
        </div>
        <div class="rp-chunks">
          <div class="rp-chunk-stat">
            <span class="num">${ragChunks}</span>
            <span class="lbl">知识片段</span>
          </div>
          <div class="rp-chunk-stat">
            <span class="num">${tools.length}</span>
            <span class="lbl">可用工具</span>
          </div>
          <div class="rp-chunk-stat">
            <span class="num">${ragReady ? '✓' : '✗'}</span>
            <span class="lbl">OCR</span>
          </div>
        </div>
      </div>
    </div>

    <!-- 系统状态 -->
    <div class="rp-card">
      <div class="rp-header">🖥️ 系统状态</div>
      <div class="rp-body">
        <div class="rp-status-item">
          <span class="rp-status-label">Ollama AI</span>
          <span class="rp-status-value ${statusData?.ollama ? 'ready' : 'offline'}">${ollamaStatus}</span>
        </div>
        <div class="rp-status-item">
          <span class="rp-status-label">OCR 服务</span>
          <span class="rp-status-value ${statusData?.ocr ? 'ready' : 'offline'}">${ocrStatus}</span>
        </div>
        <div class="rp-status-item">
          <span class="rp-status-label">版本</span>
          <span class="rp-status-value" style="font-family:var(--mono);font-size:11px">${escapeHtml(version)}</span>
        </div>
        ${toolsHtml ? `<div style="display:flex;flex-wrap:wrap;gap:4px;margin-top:6px">${toolsHtml}</div>` : ''}
      </div>
    </div>

    <!-- 快速操作 -->
    <div class="rp-card">
      <div class="rp-header">⚡ 快速操作</div>
      <div class="rp-body" style="display:flex;flex-direction:column;gap:6px">
        <button class="rp-action-btn" onclick="switchTab('check-doc')">
          <span class="rp-action-icon">📋</span> 材料合规检查
        </button>
        <button class="rp-action-btn" onclick="switchTab('meeting')">
          <span class="rp-action-icon">📝</span> 整理会议记录
        </button>
        <button class="rp-action-btn" onclick="switchTab('content')">
          <span class="rp-action-icon">📚</span> 生成党课内容
        </button>
        <button class="rp-action-btn" onclick="switchTab('chat')">
          <span class="rp-action-icon">💬</span> AI 智能对话
        </button>
      </div>
    </div>`;
}

async function loadCheckDocRightPanel(container) {
  container.innerHTML = `<div style="color:var(--text-dim);padding:8px;text-align:center;font-size:12px">⏳ 加载中...</div>`;

  let ragData = null;
  let statusData = null;
  try {
    const [rResp, sResp] = await Promise.all([
      fetch('/api/rag/status').then(r => r.json()).catch(() => null),
      fetch('/api/status').then(r => r.json()).catch(() => null),
    ]);
    ragData = rResp;
    statusData = sResp;
  } catch (e) {}

  const ragReady = ragData?.ready || statusData?.rag?.ready;
  const ragChunks = ragData?.chunks || statusData?.rag?.chunks || 0;

  container.innerHTML = `
    <!-- 规程引用 -->
    <div class="rp-card">
      <div class="rp-header">📖 规程知识库</div>
      <div class="rp-body">
        <div class="rp-status-item">
          <span class="rp-status-label">RAG 状态</span>
          <span class="rp-status-value ${ragReady ? 'ready' : 'not-ready'}">${ragReady ? '✅ 已就绪' : '⏳ 未就绪'}</span>
        </div>
        <div class="rp-status-item">
          <span class="rp-status-label">知识片段</span>
          <span class="rp-status-value" style="font-weight:700;color:var(--red)">${ragChunks}</span>
        </div>
        <div style="font-size:11px;color:var(--text-muted);margin-top:8px;line-height:1.5">
          系统内置《中国共产党发展党员工作细则》等规程文档，自动比对材料合规性。
        </div>
      </div>
    </div>

    <!-- 检查指引 -->
    <div class="rp-card">
      <div class="rp-header">💡 检查指引</div>
      <div class="rp-body">
        <div style="font-size:11px;color:var(--text-muted);line-height:1.6">
          支持检查的文档类型：
        </div>
        <div style="margin-top:6px;display:flex;flex-direction:column;gap:4px">
          <span style="font-size:11px;padding:3px 8px;background:var(--red-light);border-radius:4px;color:var(--red)">📄 入党申请书</span>
          <span style="font-size:11px;padding:3px 8px;background:var(--red-light);border-radius:4px;color:var(--red)">📄 思想汇报</span>
          <span style="font-size:11px;padding:3px 8px;background:var(--red-light);border-radius:4px;color:var(--red)">📄 转正申请</span>
          <span style="font-size:11px;padding:3px 8px;background:var(--red-light);border-radius:4px;color:var(--red)">📄 自传</span>
        </div>
      </div>
    </div>`;
}

async function loadMeetingRightPanel(container) {
  container.innerHTML = `
    <div class="rp-card">
      <div class="rp-header">📝 会议整理工具</div>
      <div class="rp-body">
        <div style="font-size:11px;color:var(--text-muted);line-height:1.6">
          上传或粘贴会议记录，AI 自动整理为结构化纪要，支持导出 Word 文档。
        </div>
        <div style="margin-top:10px;display:flex;flex-direction:column;gap:6px">
          <button class="rp-action-btn" onclick="document.getElementById('meetingFileInput').click()">
            <span class="rp-action-icon">📄</span> 上传会议文件
          </button>
          <button class="rp-action-btn" onclick="document.getElementById('meetingInput').focus()">
            <span class="rp-action-icon">✏️</span> 直接粘贴文本
          </button>
          <button class="rp-action-btn" onclick="runMeeting({exportDocx:true})" id="rpMeetingExport">
            <span class="rp-action-icon">📝</span> 整理 + 导出 Word
          </button>
        </div>
      </div>
    </div>

    <div class="rp-card">
      <div class="rp-header">💡 使用建议</div>
      <div class="rp-body">
        <div style="font-size:11px;color:var(--text-muted);line-height:1.6">
          建议在会议记录中包含：时间、地点、主持人、参会人员、议题、决议内容、下一步工作等要素。
        </div>
      </div>
    </div>`;
}

async function loadContentRightPanel(container) {
  container.innerHTML = `
    <div class="rp-card">
      <div class="rp-header">📚 内容生成</div>
      <div class="rp-body">
        <div style="font-size:11px;color:var(--text-muted);line-height:1.6">
          根据主题自动生成"三会一课"学习材料，包含PPT大纲、讨论题目和文件依据。
        </div>
        <div style="margin-top:10px;display:flex;flex-direction:column;gap:6px">
          <button class="rp-action-btn" onclick="document.getElementById('contentTopic').focus()">
            <span class="rp-action-icon">✏️</span> 输入主题
          </button>
          <button class="rp-action-btn" onclick="runContent({exportPptx:true})" id="rpContentExport">
            <span class="rp-action-icon">📊</span> 生成 + 导出 PPT
          </button>
        </div>
      </div>
    </div>

    <div class="rp-card">
      <div class="rp-header">💡 推荐主题</div>
      <div class="rp-body">
        <div style="display:flex;flex-direction:column;gap:4px">
          <span style="font-size:11px;padding:3px 8px;background:var(--gold-light);border-radius:4px;color:#8b6914;cursor:pointer" onclick="document.getElementById('contentTopic').value='党纪学习教育'">党纪学习教育</span>
          <span style="font-size:11px;padding:3px 8px;background:var(--gold-light);border-radius:4px;color:#8b6914;cursor:pointer" onclick="document.getElementById('contentTopic').value='学习二十大精神'">学习二十大精神</span>
          <span style="font-size:11px;padding:3px 8px;background:var(--gold-light);border-radius:4px;color:#8b6914;cursor:pointer" onclick="document.getElementById('contentTopic').value='新质生产力'">新质生产力</span>
          <span style="font-size:11px;padding:3px 8px;background:var(--gold-light);border-radius:4px;color:#8b6914;cursor:pointer" onclick="document.getElementById('contentTopic').value='中央八项规定'">中央八项规定</span>
        </div>
      </div>
    </div>`;
}

async function loadChatRightPanel(container) {
  const memberName = window._chatMemberName || '';
  const hasFile = !!window._chatFileContent;

  container.innerHTML = `
    <div class="rp-card">
      <div class="rp-header">💬 对话上下文</div>
      <div class="rp-body">
        <div class="rp-status-item">
          <span class="rp-status-label">成员绑定</span>
          <span class="rp-status-value ${window._chatMemberId ? 'ready' : 'not-ready'}">
            ${window._chatMemberId ? escapeHtml(memberName) : '未绑定'}
          </span>
        </div>
        <div class="rp-status-item">
          <span class="rp-status-label">文件上传</span>
          <span class="rp-status-value ${hasFile ? 'ready' : 'not-ready'}">
            ${hasFile ? '✅ 已上传' : '未上传'}
          </span>
        </div>
        ${hasFile ? `<div style="font-size:11px;color:var(--text-muted);margin-top:4px">📎 ${escapeHtml(window._chatFileName || '')}</div>` : ''}
      </div>
    </div>

    <div class="rp-card">
      <div class="rp-header">💡 功能提示</div>
      <div class="rp-body">
        <div style="font-size:11px;color:var(--text-muted);line-height:1.6">
          <p>• 上传文件后自动作为对话上下文</p>
          <p>• 可从看板绑定成员，AI 将了解该成员情况</p>
          <p>• 支持 PDF/Word/图片等格式</p>
        </div>
      </div>
    </div>`;
}

async function loadKanbanRightPanel(container) {
  container.innerHTML = `<div style="color:var(--text-dim);padding:8px;text-align:center;font-size:12px">⏳ 加载提醒...</div>`;

  try {
    const resp = await fetch('/api/reminders');
    const data = await resp.json();
    const reminders = data.reminders || [];

    let remindersHtml = '';
    if (reminders.length === 0) {
      remindersHtml = '<div class="rp-reminder-empty">✅ 暂无待办提醒</div>';
    } else {
      for (const r of reminders) {
        const icon = r.type === 'material_pending' ? '📦' : '⏰';
        remindersHtml += `<div class="rp-reminder-item" onclick="selectMember(${r.member_id})">
          <span class="rp-reminder-icon">${icon}</span>
          <div class="rp-reminder-content">
            <div class="rp-reminder-title">${escapeHtml(r.member_name || '')} · ${escapeHtml(r.title || '')}</div>
            <div class="rp-reminder-desc">${escapeHtml(r.detail || '')}</div>
          </div>
        </div>`;
      }
    }

    container.innerHTML = `
      <div class="rp-card">
        <div class="rp-header">🔔 待办提醒 (${reminders.length})</div>
        <div class="rp-body" style="padding:8px 10px">
          ${remindersHtml}
        </div>
      </div>

      <div class="rp-card">
        <div class="rp-header">📊 阶段概览</div>
        <div class="rp-body">
          <div class="rp-info-row">
            <span class="rp-info-label">📋 申请入党</span>
            <span class="rp-info-value" id="rpStageApplicant">—</span>
          </div>
          <div class="rp-info-row">
            <span class="rp-info-label">🌟 积极分子</span>
            <span class="rp-info-value" id="rpStageActivist">—</span>
          </div>
          <div class="rp-info-row">
            <span class="rp-info-label">🎯 发展对象</span>
            <span class="rp-info-value" id="rpStageCandidate">—</span>
          </div>
          <div class="rp-info-row">
            <span class="rp-info-label">🔜 预备党员</span>
            <span class="rp-info-value" id="rpStageProbationary">—</span>
          </div>
          <div class="rp-info-row">
            <span class="rp-info-label">✅ 正式党员</span>
            <span class="rp-info-value" id="rpStageFull">—</span>
          </div>
        </div>
      </div>`;

    // Try to load stage counts from dashboard
    try {
      const dashResp = await fetch('/api/dashboard');
      const dashData = await dashResp.json();
      if (dashData && dashData.stages) {
        const stages = dashData.stages;
        const map = {
          'rpStageApplicant': 'applicant',
          'rpStageActivist': 'activist',
          'rpStageCandidate': 'candidate',
          'rpStageProbationary': 'probationary',
          'rpStageFull': 'full_member'
        };
        for (const [elId, key] of Object.entries(map)) {
          const el = document.getElementById(elId);
          if (el && stages[key]) el.textContent = stages[key].count + '人';
        }
      }
    } catch (e) {}
  } catch (e) {
    container.innerHTML = `
      <div class="rp-card">
        <div class="rp-header">🔔 待办提醒</div>
        <div class="rp-body">
          <div style="color:var(--text-dim);font-size:12px;text-align:center">加载失败</div>
        </div>
      </div>`;
  }
}

async function loadTraceRightPanel(container) {
  container.innerHTML = `
    <div class="rp-card">
      <div class="rp-header">🔄 执行记录</div>
      <div class="rp-body">
        <div style="font-size:11px;color:var(--text-muted);line-height:1.6">
          查看 AI 对话中的工具调用历史。每次对话生成一条执行记录，包含调用链和耗时。
        </div>
        <button class="rp-action-btn" style="margin-top:8px" onclick="loadAgentRuns()">
          <span class="rp-action-icon">🔄</span> 刷新记录
        </button>
      </div>
    </div>

    <div class="rp-card">
      <div class="rp-header">💡 说明</div>
      <div class="rp-body">
        <div style="font-size:11px;color:var(--text-muted);line-height:1.6">
          <p>• 工具调用记录自动保存</p>
          <p>• 点击条目查看详细调用参数</p>
          <p>• 可用于排查和审计 AI 行为</p>
        </div>
      </div>
    </div>`;
}

async function loadSettingsRightPanel(container) {
  container.innerHTML = `<div style="color:var(--text-dim);padding:8px;text-align:center;font-size:12px">⏳ 加载中...</div>`;

  let statusData = null;
  try {
    statusData = await fetch('/api/status').then(r => r.json()).catch(() => null);
  } catch (e) {}

  const version = statusData?.version || '—';
  const ollamaOk = statusData?.ollama ? '🟢 在线' : '🔴 离线';
  const ocrOk = statusData?.ocr ? '🟢 可用' : '⛔ 不可用';

  let toolsHtml = '';
  if (statusData?.tools && statusData.tools.length > 0) {
    toolsHtml = statusData.tools.map(t => `<span style="display:inline-block;padding:2px 8px;background:var(--red-light);border-radius:4px;font-size:10px;color:var(--red);margin:2px">${escapeHtml(t)}</span>`).join('');
  }

  container.innerHTML = `
    <div class="rp-card">
      <div class="rp-header">🤖 模型信息</div>
      <div class="rp-body">
        <div class="rp-info-row">
          <span class="rp-info-label">版本</span>
          <span class="rp-info-value" style="font-family:var(--mono);font-size:11px">${escapeHtml(version)}</span>
        </div>
        <div class="rp-info-row">
          <span class="rp-info-label">Ollama</span>
          <span class="rp-info-value">${ollamaOk}</span>
        </div>
        <div class="rp-info-row">
          <span class="rp-info-label">OCR</span>
          <span class="rp-info-value">${ocrOk}</span>
        </div>
      </div>
    </div>

    <div class="rp-card">
      <div class="rp-header">🛠️ 可用工具</div>
      <div class="rp-body">
        ${toolsHtml || '<div style="font-size:11px;color:var(--text-dim)">暂无工具信息</div>'}
      </div>
    </div>

    <div class="rp-card">
      <div class="rp-header">📊 使用统计</div>
      <div class="rp-body">
        <div class="rp-info-row">
          <span class="rp-info-label">📋 材料检查</span>
          <span class="rp-info-value" id="rpStatChecks">${getLocalData('stats', {checks:0}).checks || 0}</span>
        </div>
        <div class="rp-info-row">
          <span class="rp-info-label">📝 会议整理</span>
          <span class="rp-info-value" id="rpStatMeetings">${getLocalData('stats', {meetings:0}).meetings || 0}</span>
        </div>
        <div class="rp-info-row">
          <span class="rp-info-label">📄 处理文件</span>
          <span class="rp-info-value" id="rpStatFiles">${getLocalData('recent_files', []).length}</span>
        </div>
      </div>
    </div>`;
}

// ==================== 初始化 ====================

document.addEventListener('DOMContentLoaded', function() {
  window._chatMemberId = null;
  window._chatMemberName = '';
  window._selectedMemoryMergeIds = [];
  setDate();
  checkStatus();
  updateDashboardStats();
  updateRecentFiles();
  updateChatMemberContextBar();
  loadRightPanel('dashboard');
  loadChatSessions(); // <-- Add this
  setInterval(checkStatus, 30000);
});

// ==================== 📊 发展看板 Kanban ====================

const STAGE_LABELS = {
  'applicant': '申请入党',
  'activist': '入党积极分子',
  'candidate': '发展对象',
  'probationary': '预备党员',
  'full_member': '正式党员'
};

const STAGE_CLASSES = {
  'applicant': 'stage-applicant',
  'activist': 'stage-activist',
  'candidate': 'stage-candidate',
  'probationary': 'stage-probationary',
  'full_member': 'stage-full_member'
};

let _selectedMemberId = null;
let _selectedOCRTaskId = null;
let _kanbanRefreshInterval = null;

function openMemberArchivePicker(memberId) {
  _selectedMemberId = memberId;
  document.getElementById('memberArchiveInput').click();
}

async function handleMemberArchiveSelected(event) {
  const file = event.target.files[0];
  if (!file || !_selectedMemberId) return;

  const formData = new FormData();
  formData.append('member_id', String(_selectedMemberId));
  formData.append('file', file);

  const detailEl = document.getElementById('kanbanMemberDetail');
  detailEl.insertAdjacentHTML(
    'afterbegin',
    '<div class="loading" id="memberImportLoading">导入材料包中...</div>'
  );

  try {
    const resp = await fetch('/api/materials/archive/import', {
      method: 'POST',
      body: formData,
    });
    const data = await resp.json();
    if (data.error) {
      showKanbanError(data.error);
      return;
    }
    await renderMemberDetail(_selectedMemberId);
    await loadDashboard();
  } catch (e) {
    showKanbanError('材料包导入失败: ' + e.message);
  } finally {
    document.getElementById('memberImportLoading')?.remove();
    event.target.value = '';
  }
}

async function runMemberMaterialCheck(memberId, batchId) {
  try {
    const resp = await fetch('/api/members/' + memberId + '/materials/check', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(batchId ? {batch_id: batchId} : {}),
    });
    const data = await resp.json();
    if (data.error) {
      showKanbanError(data.error);
      return;
    }
    await renderMemberDetail(memberId);
  } catch (e) {
    showKanbanError('整套核查失败: ' + e.message);
  }
}

function closeOCRReviewPanel() {
  _selectedOCRTaskId = null;
  const panel = document.getElementById('ocrReviewPanel');
  if (!panel) return;
  panel.style.display = 'none';
  panel.innerHTML = `
    <div style="color:var(--text-dim);padding:20px;text-align:center;font-size:13px">
      选择待复核 OCR 任务后在此处查看和确认文本
    </div>`;
}

async function openOCRReviewTask(taskId) {
  _selectedOCRTaskId = taskId;
  const panel = document.getElementById('ocrReviewPanel');
  if (!panel) return;
  panel.style.display = 'block';
  panel.innerHTML = '<div class="loading" style="padding:20px;text-align:center">加载 OCR 复核任务...</div>';

  try {
    const resp = await fetch('/api/ocr/tasks/' + taskId);
    const data = await resp.json();
    if (data.error) {
      panel.innerHTML = '<div style="color:var(--red);padding:20px">❌ ' + escapeHtml(String(data.error)) + '</div>';
      return;
    }
    renderOCRReviewPanel(data);
  } catch (e) {
    panel.innerHTML = '<div style="color:var(--red);padding:20px">❌ 加载 OCR 任务失败: ' + escapeHtml(String(e.message)) + '</div>';
  }
}

function renderOCRReviewPanel(data) {
  const panel = document.getElementById('ocrReviewPanel');
  if (!panel) return;

  const task = data.task || {};
  const file = data.file || {};
  const summary = data.confidence_summary || {};
  const lowSegments = data.low_confidence_segments || [];
  const confirmedText = data.confirmed_text || data.raw_text || '';

  let lowSegmentHtml = '<div class="timeline-empty">暂无低置信度片段</div>';
  if (lowSegments.length > 0) {
    lowSegmentHtml = lowSegments.map(item => `
      <div class="issue-item">
        <div class="issue-tag">置信度 ${(Number(item.confidence || 0) * 100).toFixed(0)}%</div>
        <div class="issue-text">${escapeHtml(String(item.text || ''))}</div>
      </div>`).join('');
  }

  panel.innerHTML = `
    <div class="member-detail">
      <div class="detail-header">
        <div class="detail-name">🔎 OCR 复核</div>
        <span class="stage-badge" style="font-size:12px;padding:3px 12px;background:var(--gold-light);color:#8b6914">
          ${escapeHtml(String(task.status || 'review_required'))}
        </span>
      </div>
      <div class="detail-meta">
        <span>📄 文件: ${escapeHtml(String(file.original_name || ''))}</span>
        <span>⚠️ 低置信度片段: ${summary.low_confidence_count || 0}</span>
        <span>📊 平均置信度: ${summary.average_confidence || 0}</span>
      </div>
      <div class="detail-actions">
        <button class="btn btn-primary" onclick="confirmOCRReviewTask(${task.id})">✅ 确认入库</button>
        <button class="btn btn-secondary" onclick="closeOCRReviewPanel()">关闭</button>
      </div>
      <div class="detail-section">
        <div class="detail-section-title">⚠️ 低置信度片段</div>
        ${lowSegmentHtml}
      </div>
      <div class="split-layout" style="margin-top:12px">
        <div class="split-panel">
          <div class="split-panel-header">
            <span>📄 OCR 原始草稿</span>
          </div>
          <div class="split-panel-body">
            <pre style="white-space:pre-wrap">${escapeHtml(String(data.raw_text || ''))}</pre>
          </div>
        </div>
        <div class="split-panel">
          <div class="split-panel-header">
            <span>✍️ 人工确认文本</span>
          </div>
          <div class="split-panel-body">
            <textarea class="field-textarea" id="ocrConfirmedText" rows="14">${escapeHtml(String(confirmedText))}</textarea>
            <label class="field-label" style="margin-top:12px">复核备注</label>
            <textarea class="field-textarea" id="ocrReviewNotes" rows="3" placeholder="可选：记录修正点或风险说明"></textarea>
          </div>
        </div>
      </div>
    </div>`;
}

async function confirmOCRReviewTask(taskId) {
  const textEl = document.getElementById('ocrConfirmedText');
  const notesEl = document.getElementById('ocrReviewNotes');
  const confirmedText = textEl ? textEl.value.trim() : '';
  const reviewNotes = notesEl ? notesEl.value.trim() : '';

  if (!confirmedText) {
    showKanbanError('请先填写确认后的 OCR 文本');
    return;
  }

  try {
    const resp = await fetch('/api/ocr/confirm', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({
        task_id: taskId,
        confirmed_text: confirmedText,
        review_notes: reviewNotes,
      }),
    });
    const data = await resp.json();
    if (data.error) {
      showKanbanError(data.error);
      return;
    }
    closeOCRReviewPanel();
    if (_selectedMemberId) {
      await renderMemberDetail(_selectedMemberId);
      await loadDashboard();
    }
  } catch (e) {
    showKanbanError('OCR 确认失败: ' + e.message);
  }
}

async function loadKanban() {
  // Load dashboard + reminders on tab switch
  await loadDashboard();
  await renderReminders();

  // Auto-refresh reminders every 60s
  if (_kanbanRefreshInterval) clearInterval(_kanbanRefreshInterval);
  _kanbanRefreshInterval = setInterval(renderReminders, 60000);
}

async function loadDashboard() {
  const listEl = document.getElementById('kanbanMemberList');
  const summaryEl = document.getElementById('stageSummary');
  showKanbanError(false);

  try {
    const resp = await fetch('/api/dashboard');
    const data = await resp.json();
    if (data.error) { showKanbanError(data.error); return; }

    // Render stage summary bar
    renderStageSummary(summaryEl, data);

    // Render member list grouped by stage
    renderMemberList(listEl, data.stages);
  } catch (e) {
    showKanbanError('加载看板失败: ' + e.message);
  }
}

function renderStageSummary(container, data) {
  const stages = data.stages || {};
  let html = '';
  const stageKeys = ['applicant', 'activist', 'candidate', 'probationary', 'full_member'];
  for (const key of stageKeys) {
    const s = stages[key];
    if (!s) continue;
    const cls = STAGE_CLASSES[key] || '';
    const pct = data.total > 0 ? Math.round((s.count / data.total) * 100) : 0;
    html += `<div class="stage-summary-item ${cls}">
      <div class="stage-summary-label">${STAGE_LABELS[key] || key}</div>
      <div class="stage-summary-count">${s.count}人</div>
      <div class="stage-summary-bar"><div class="stage-summary-fill" style="width:${pct}%"></div></div>
    </div>`;
  }
  container.innerHTML = html || '<div style="color:var(--text-dim)">暂无成员</div>';
}

function renderMemberList(container, stages) {
  const stageKeys = ['applicant', 'activist', 'candidate', 'probationary', 'full_member'];
  let html = '';

  for (const key of stageKeys) {
    const group = stages[key];
    if (!group) continue;
    const members = group.members || [];
    const cls = STAGE_CLASSES[key] || '';
    const label = STAGE_LABELS[key] || key;

    html += `<div class="stage-group">
      <div class="stage-group-header ${cls}">
        <span>${label}</span>
        <span class="stage-count">${members.length}</span>
      </div>`;

    if (members.length === 0) {
      html += `<div class="stage-group-empty">暂无成员</div>`;
    } else {
      for (const m of members) {
        const unsubmitted = (m.materials || []).filter(mat => !mat.submitted).length;
        const totalMats = (m.materials || []).length;
        const pct = totalMats > 0 ? Math.round(((totalMats - unsubmitted) / totalMats) * 100) : 0;
        const isSelected = _selectedMemberId === m.id;

        html += `<div class="member-card ${isSelected ? 'selected' : ''}" onclick="selectMember(${m.id})" data-id="${m.id}">
          <div class="member-card-top">
            <span class="member-name">${escapeHtml(m.name)}</span>
            <span class="stage-badge ${cls}">${label}</span>
          </div>
          <div class="member-progress">
            <div class="member-progress-bar">
              <div class="member-progress-fill" style="width:${pct}%"></div>
            </div>
            <span class="member-progress-text">${totalMats - unsubmitted}/${totalMats}</span>
          </div>
          ${renderCountdown(m)}
        </div>`;
      }
    }

    html += `</div>`;
  }

  container.innerHTML = html;
}

function renderCountdown(member) {
  // Check for deadlines in timeline
  const timeline = member.timeline || [];
  let html = '';
  for (const evt of timeline) {
    if (evt.date && evt.type === 'deadline') {
      const days = daysUntil(evt.date);
      if (days <= 7) {
        const cls = days <= 0 ? 'countdown-danger' : 'countdown-warning';
        html += `<div class="countdown-badge ${cls}">${days <= 0 ? '⚠️ 逾期' : '⏰ ' + days + '天'}</div>`;
      }
    }
  }
  // If no deadline events, show a default "created" countdown placeholder
  if (!html && member.created_at) {
    const days = daysUntil(member.created_at.split(' ')[0]) + 30; // 30-day window from creation
    // Only show for non-full_member with old creation
  }
  return html;
}

function daysUntil(dateStr) {
  if (!dateStr) return 999;
  const today = new Date();
  today.setHours(0,0,0,0);
  const target = new Date(dateStr);
  target.setHours(0,0,0,0);
  return Math.round((target - today) / (1000 * 60 * 60 * 24));
}

async function selectMember(memberId) {
  _selectedMemberId = memberId;
  window._selectedMemoryMergeIds = [];
  closeOCRReviewPanel();
  // Update selected class on cards
  document.querySelectorAll('.member-card').forEach(el => {
    el.classList.toggle('selected', parseInt(el.dataset.id) === memberId);
  });
  await renderMemberDetail(memberId);
}

async function renderMemberDetail(memberId) {
  const detailEl = document.getElementById('kanbanMemberDetail');
  detailEl.innerHTML = '<div class="loading" style="padding:20px;text-align:center">加载中...</div>';

  try {
    const resp = await fetch('/api/members/' + memberId);
    const data = await resp.json();
    if (data.error) { detailEl.innerHTML = '<div style="color:var(--red);padding:20px">❌ ' + escapeHtml(data.error) + '</div>'; return; }

    const m = data.member;
    const cls = STAGE_CLASSES[m.stage] || '';
    const label = STAGE_LABELS[m.stage] || m.stage;
    const hasNext = m.stage !== 'full_member';

    let html = `<div class="member-detail">
      <div class="detail-header">
        <div class="detail-name">${escapeHtml(m.name)}</div>
        <span class="stage-badge ${cls}" style="font-size:13px;padding:3px 12px">${label}</span>
      </div>
      <div class="detail-meta">
        <span>📅 创建: ${escapeHtml(m.created_at || '-')}</span>
        <span>🔄 更新: ${escapeHtml(m.updated_at || '-')}</span>
      </div>`;

    // Notes
    if (m.notes) {
      html += `<div class="detail-notes"><strong>📝 备注:</strong> ${escapeHtml(m.notes)}</div>`;
    }

    const latestBatch = m.latest_import_batch || {};
    const latestCheck = m.latest_material_check || {};

    // Advance button
    if (hasNext) {
      html += `<div class="detail-actions">
        <button class="btn btn-primary" onclick="advanceStage(${m.id})">➡️ 推进到下一阶段</button>
      </div>`;
    } else {
      html += `<div class="detail-actions">
        <span style="color:var(--gold);font-weight:600">✅ 已完成全部阶段</span>
      </div>`;
    }

    html += `<div class="detail-actions">
      <button class="btn btn-secondary" onclick="openMemberArchivePicker(${m.id})">📦 导入材料包</button>
      <button class="btn btn-primary" onclick="runMemberMaterialCheck(${m.id}, ${latestBatch.id || 'null'})">🔍 整套核查</button>
      <button class="btn btn-sm" onclick="bindMemberChatContext(${m.id}, ${JSON.stringify(String(m.name || ''))})">💬 绑定到AI对话</button>
    </div>`;

    html += `<div class="detail-section">
      <div class="detail-section-title">📦 最近导入</div>
      <div>${escapeHtml(latestBatch.archive_name || '暂无导入记录')}</div>
      <div>${latestBatch.total_files || 0} 文件 · ${latestBatch.recognized_files || 0} 已识别 · ${latestBatch.needs_review_files || 0} 待复核</div>
    </div>`;

    html += `<div class="detail-section">
      <div class="detail-section-title">🧾 最近整套核查</div>
      <div>错误 ${latestCheck.summary?.error_count || 0} · 警告 ${latestCheck.summary?.warning_count || 0} · 待确认 ${latestCheck.summary?.review_count || 0}</div>
    </div>`;

    const pendingOCRTasks = m.pending_ocr_tasks || [];
    html += `<div class="detail-section">
      <div class="detail-section-title">🧠 OCR 待复核 (${m.pending_ocr_task_count || 0})</div>`;
    if (pendingOCRTasks.length === 0) {
      html += `<div class="timeline-empty">暂无 OCR 待复核任务</div>`;
    } else {
      html += `<div class="material-list">`;
      for (const task of pendingOCRTasks) {
        const summary = task.confidence_summary || {};
        html += `<div class="material-item material-pending">
          <span class="material-check">📝</span>
          <span class="material-name">${escapeHtml(String(task.original_name || ''))}</span>
          <span class="material-status badge-pending">低置信度 ${summary.low_confidence_count || 0}</span>
          <button class="btn btn-sm" onclick="openOCRReviewTask(${task.task_id})">开始复核</button>
        </div>`;
      }
      html += `</div>`;
    }
    html += `</div>`;

    const memories = m.memories || [];
    html += `<div class="detail-section">
      <div class="detail-section-title">🧠 成员记忆 (${m.memory_count || 0}，置顶 ${m.pinned_memory_count || 0})</div>
      <div class="memory-editor-grid">
        <select class="field-input" id="memoryKindInput-${m.id}">
          <option value="note">一般记录</option>
          <option value="summary">结论摘要</option>
          <option value="risk">风险提醒</option>
          <option value="instruction">工作指令</option>
          <option value="correction">修订结论</option>
        </select>
        <input class="field-input" id="memoryTitleInput-${m.id}" type="text" placeholder="记忆标题（可选）">
        <textarea class="field-textarea" id="memoryContentInput-${m.id}" rows="3" placeholder="输入需要长期保留的成员信息、风险、结论或偏好"></textarea>
        <label style="font-size:12px;color:var(--text-dim);display:flex;align-items:center;gap:6px">
          <input type="checkbox" id="memoryPinnedInput-${m.id}"> 设为置顶
        </label>
        <div class="detail-actions">
          <button class="btn btn-primary" onclick="saveMemberMemory(${m.id})">保存记忆</button>
          <button class="btn btn-secondary" onclick="mergeSelectedMemories(${m.id})">合并选中记忆</button>
        </div>
      </div>`;
    if (memories.length === 0) {
      html += `<div class="timeline-empty">暂无成员记忆</div>`;
    } else {
      html += `<div class="material-list">`;
      for (const memory of memories) {
        const checked = (window._selectedMemoryMergeIds || []).includes(memory.id) ? 'checked' : '';
        html += `<div class="material-item">
          <span>
            <input type="checkbox" ${checked} onchange="toggleMemoryMergeSelection(${memory.id}, this.checked)">
          </span>
          <span class="material-name">
            ${memory.pinned ? '📌 ' : ''}${escapeHtml(String(memory.title || memory.kind || '记忆'))}
            <div style="font-size:12px;color:var(--text-dim);margin-top:4px">${escapeHtml(String(memory.content || ''))}</div>
          </span>
          <span class="material-status badge-pending">${escapeHtml(String(memory.kind || ''))}</span>
          <button class="btn btn-sm" onclick="toggleMemberMemoryPinned(${m.id}, ${memory.id}, ${memory.pinned ? 'false' : 'true'})">${memory.pinned ? '取消置顶' : '置顶'}</button>
          <button class="btn btn-sm" onclick="deleteMemberMemory(${m.id}, ${memory.id})">删除</button>
        </div>`;
      }
      html += `</div>`;
    }
    html += `</div>`;

    // Material progress bar
    const allMats = m.materials || [];
    const totalReq = allMats.filter(mat => mat.is_required !== false).length;
    const submittedCount = allMats.filter(mat => mat.submitted).length;
    const pct = totalReq > 0 ? Math.round(submittedCount / totalReq * 100) : 0;
    const barFill = Math.min(pct, 100);
    html += `<div class="detail-section">
      <div class="detail-section-title">📊 材料进度</div>
      <div class="progress-bar-container">
        <div class="progress-bar-bg">
          <div class="progress-bar-fill" style="width:${barFill}%"></div>
        </div>
        <span class="progress-bar-label">${submittedCount}/${totalReq} (${pct}%)</span>
      </div>
    </div>`;

    // Timeline
    html += `<div class="detail-section">
      <div class="detail-section-title">📅 时间线</div>
      <div class="timeline" id="timeline-${m.id}">`;
    const timeline = m.timeline || [];
    if (timeline.length === 0) {
      html += `<div class="timeline-empty">暂无事件记录</div>`;
    } else {
      // Sort newest first
      const sorted = [...timeline].sort((a, b) => (b.date || '').localeCompare(a.date || ''));
      for (const evt of sorted) {
        html += `<div class="timeline-item">
          <div class="timeline-dot ${evt.type === 'stage_advance' ? 'dot-advance' : 'dot-event'}"></div>
          <div class="timeline-content">
            <div class="timeline-date">${escapeHtml(evt.date || '')}</div>
            <div class="timeline-title">${escapeHtml(evt.title || '')}</div>
            ${evt.description ? '<div class="timeline-desc">' + escapeHtml(evt.description) + '</div>' : ''}
          </div>
        </div>`;
      }
    }
    html += `</div></div>`;

    // Materials checklist
    html += `<div class="detail-section">
      <div class="detail-section-title">📋 材料清单 (${(m.materials || []).length}项)</div>
      <div class="material-list">`;
    const materials = m.materials || [];
    if (materials.length === 0) {
      html += `<div class="timeline-empty">暂无材料要求</div>`;
    } else {
      for (const mat of materials) {
        const submitted = mat.submitted;
        html += `<div class="material-item ${submitted ? 'material-done' : 'material-pending'}">
          <span class="material-check">${submitted ? '✅' : '⬜'}</span>
          <span class="material-name">${escapeHtml(mat.name)}</span>
          <span class="material-status ${submitted ? 'badge-completed' : 'badge-pending'}">${submitted ? '已完成' : '待提交'}</span>
          ${!submitted ? `<button class="btn btn-sm" onclick="submitMaterial(${m.id}, ${mat.id})">提交</button>` : ''}
        </div>`;
      }
    }
    html += `</div></div>`;

    html += `</div>`;
    detailEl.innerHTML = html;
  } catch (e) {
    detailEl.innerHTML = '<div style="color:var(--red);padding:20px">❌ 加载详情失败: ' + escapeHtml(e.message) + '</div>';
  }
}

function toggleMemoryMergeSelection(memoryId, checked) {
  const current = new Set(window._selectedMemoryMergeIds || []);
  if (checked) current.add(memoryId);
  else current.delete(memoryId);
  window._selectedMemoryMergeIds = Array.from(current);
}

async function saveMemberMemory(memberId) {
  const kindEl = document.getElementById(`memoryKindInput-${memberId}`);
  const titleEl = document.getElementById(`memoryTitleInput-${memberId}`);
  const contentEl = document.getElementById(`memoryContentInput-${memberId}`);
  const pinnedEl = document.getElementById(`memoryPinnedInput-${memberId}`);
  const content = contentEl ? contentEl.value.trim() : '';
  if (!content) {
    showKanbanError('请输入记忆内容');
    return;
  }
  try {
    const resp = await fetch(`/api/members/${memberId}/memories`, {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({
        kind: kindEl ? kindEl.value : 'note',
        title: titleEl ? titleEl.value.trim() : '',
        content,
        pinned: pinnedEl ? pinnedEl.checked : false,
        source: 'manual',
      }),
    });
    const data = await resp.json();
    if (data.error) {
      showKanbanError(data.error);
      return;
    }
    window._selectedMemoryMergeIds = [];
    await renderMemberDetail(memberId);
  } catch (e) {
    showKanbanError('保存记忆失败: ' + e.message);
  }
}

async function toggleMemberMemoryPinned(memberId, memoryId, pinned) {
  try {
    const resp = await fetch(`/api/members/${memberId}/memories/${memoryId}`, {
      method: 'PATCH',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({pinned}),
    });
    const data = await resp.json();
    if (data.error) {
      showKanbanError(data.error);
      return;
    }
    await renderMemberDetail(memberId);
  } catch (e) {
    showKanbanError('更新记忆失败: ' + e.message);
  }
}

async function deleteMemberMemory(memberId, memoryId) {
  if (!confirm('确认删除这条成员记忆？')) return;
  try {
    const resp = await fetch(`/api/members/${memberId}/memories/${memoryId}`, {
      method: 'DELETE',
    });
    const data = await resp.json();
    if (data.error) {
      showKanbanError(data.error);
      return;
    }
    window._selectedMemoryMergeIds = (window._selectedMemoryMergeIds || []).filter(id => id !== memoryId);
    await renderMemberDetail(memberId);
  } catch (e) {
    showKanbanError('删除记忆失败: ' + e.message);
  }
}

async function mergeSelectedMemories(memberId) {
  const memoryIds = (window._selectedMemoryMergeIds || []).slice();
  if (memoryIds.length < 2) {
    showKanbanError('请至少选择两条记忆进行合并');
    return;
  }
  const kindEl = document.getElementById(`memoryKindInput-${memberId}`);
  const titleEl = document.getElementById(`memoryTitleInput-${memberId}`);
  const contentEl = document.getElementById(`memoryContentInput-${memberId}`);
  const pinnedEl = document.getElementById(`memoryPinnedInput-${memberId}`);
  const content = contentEl ? contentEl.value.trim() : '';
  if (!content) {
    showKanbanError('请填写合并后的记忆内容');
    return;
  }
  try {
    const resp = await fetch(`/api/members/${memberId}/memories/merge`, {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({
        memory_ids: memoryIds,
        kind: kindEl ? kindEl.value : 'summary',
        title: titleEl ? titleEl.value.trim() : '',
        content,
        pinned: pinnedEl ? pinnedEl.checked : false,
        importance: 3,
      }),
    });
    const data = await resp.json();
    if (data.error) {
      showKanbanError(data.error);
      return;
    }
    window._selectedMemoryMergeIds = [];
    await renderMemberDetail(memberId);
  } catch (e) {
    showKanbanError('合并记忆失败: ' + e.message);
  }
}

async function advanceStage(memberId) {
  if (!confirm('确认将该成员推进到下一阶段？')) return;
  try {
    const resp = await fetch('/api/members/' + memberId + '/advance', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({}),
    });
    const data = await resp.json();
    if (data.error) { showKanbanError(data.error); return; }
    // Refresh both dashboard and detail
    await loadDashboard();
    if (_selectedMemberId) await renderMemberDetail(_selectedMemberId);
  } catch (e) {
    showKanbanError('推进失败: ' + e.message);
  }
}

async function submitMaterial(memberId, materialId) {
  try {
    const resp = await fetch('/api/members/' + memberId + '/materials', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({material_id: materialId, file_path: ''}),
    });
    const data = await resp.json();
    if (data.error) { showKanbanError(data.error); return; }
    // Refresh detail and dashboard
    await loadDashboard();
    if (_selectedMemberId) await renderMemberDetail(_selectedMemberId);
  } catch (e) {
    showKanbanError('提交失败: ' + e.message);
  }
}

async function renderReminders() {
  const el = document.getElementById('kanbanReminders');
  try {
    const resp = await fetch('/api/reminders');
    const data = await resp.json();
    if (data.error) { el.innerHTML = '<div style="color:var(--red);padding:12px">❌ ' + escapeHtml(data.error) + '</div>'; return; }

    const reminders = data.reminders || [];
    if (reminders.length === 0) {
      el.innerHTML = '<div style="color:var(--text-dim);padding:20px;text-align:center">✅ 暂无待办提醒</div>';
      return;
    }

    // Group by type
    const pending = reminders.filter(r => r.type === 'material_pending');
    const delayed = reminders.filter(r => r.type === 'stage_delayed');

    let html = '';
    if (pending.length > 0) {
      html += `<div class="reminder-group">
        <div class="reminder-group-title badge-pending">📦 待提交材料 (${pending.length})</div>`;
      for (const r of pending) {
        html += `<div class="reminder-item reminder-pending" onclick="selectMember(${r.member_id})">
          <div class="reminder-member">${escapeHtml(r.member_name)}</div>
          <div class="reminder-title">${escapeHtml(r.title)}</div>
          <div class="reminder-detail">${escapeHtml(r.detail)}</div>
        </div>`;
      }
      html += `</div>`;
    }

    if (delayed.length > 0) {
      html += `<div class="reminder-group">
        <div class="reminder-group-title badge-overdue">⏰ 阶段提醒 (${delayed.length})</div>`;
      for (const r of delayed) {
        html += `<div class="reminder-item reminder-overdue" onclick="selectMember(${r.member_id})">
          <div class="reminder-member">${escapeHtml(r.member_name)}</div>
          <div class="reminder-title">${escapeHtml(r.title)}</div>
          <div class="reminder-detail">${escapeHtml(r.detail)}</div>
        </div>`;
      }
      html += `</div>`;
    }

    el.innerHTML = html;
  } catch (e) {
    el.innerHTML = '<div style="color:var(--red);padding:12px">❌ 加载提醒失败</div>';
  }
}

// ── Add Member Modal ───────────────────────────────────────────────

function showAddMemberModal() {
  document.getElementById('addMemberModal').style.display = 'flex';
  document.getElementById('newMemberName').value = '';
  document.getElementById('newMemberStage').value = 'applicant';
  document.getElementById('newMemberNotes').value = '';
  document.getElementById('newMemberName').focus();
}

function hideAddMemberModal() {
  document.getElementById('addMemberModal').style.display = 'none';
}

async function addMember() {
  const name = document.getElementById('newMemberName').value.trim();
  if (!name) { alert('请输入姓名'); return; }
  const stage = document.getElementById('newMemberStage').value;
  const notes = document.getElementById('newMemberNotes').value.trim();

  try {
    const resp = await fetch('/api/members', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({name, stage, notes}),
    });
    const data = await resp.json();
    if (data.error) { showKanbanError(data.error); return; }
    hideAddMemberModal();
    await loadDashboard();
    // Select the new member
    if (data.member && data.member.id) {
      await selectMember(data.member.id);
    }
  } catch (e) {
    showKanbanError('添加失败: ' + e.message);
  }
}

// ── Helpers ────────────────────────────────────────────────────────

function showKanbanError(msg) {
  const el = document.getElementById('kanbanError');
  if (!msg) {
    el.style.display = 'none';
    return;
  }
  el.textContent = '❌ ' + msg;
  el.style.display = 'block';
  setTimeout(() => { el.style.display = 'none'; }, 5000);
}

// ==================== 🔄 Agent 执行记录 ====================

let _agentRunsLoaded = false;

  async function loadAgentRuns() {
  const listEl = document.getElementById('agentRunsList');
    listEl.innerHTML = '<div class="loading" style="padding:20px;text-align:center">加载中...</div>';
    try {
      const resp = await fetch('/api/agent/runs');
      const data = await resp.json();
      if (data.error) {
        listEl.innerHTML = '<div style="color:var(--red)">❌ ' + escapeHtml(data.error) + '</div>';
        return;
      }
      const runs = data.runs || [];
      if (runs.length === 0) {
        listEl.innerHTML = '<div style="color:var(--text-dim);padding:20px;text-align:center">暂无执行记录，使用 AI 对话后会自动生成</div>';
        return;
      }
      let html = '<div style="display:flex;flex-direction:column;gap:8px">';
      for (const run of runs) {
        const toolCount = run.tool_calls_json ? JSON.parse(run.tool_calls_json).length : 0;
        const dur = run.duration_ms ? (run.duration_ms / 1000).toFixed(1) + 's' : '-';
        const statusClass = run.status === 'completed' ? 'badge-completed' : 'badge-pending';
        html += `<div class="member-card" onclick="openAgentRunDetail('${escapeHtml(run.run_id)}')" style="cursor:pointer">
          <div style="flex:1">
            <div style="font-weight:600;font-size:13px;margin-bottom:4px">${escapeHtml(run.user_input || '').substring(0, 60)}</div>
            <div style="display:flex;gap:12px;font-size:11px;color:var(--text-dim)">
              <span>🛠️ ${toolCount} 次调用</span>
              <span>⏱️ ${dur}</span>
              <span>🤖 ${escapeHtml(run.model_used || '-')}</span>
            </div>
          </div>
          <span class="material-status ${statusClass}">${run.status}</span>
        </div>`;
      }
      html += '</div>';
      listEl.innerHTML = html;
      _agentRunsLoaded = true;
    } catch (e) {
      listEl.innerHTML = '<div style="color:var(--red)">❌ 加载失败: ' + escapeHtml(e.message) + '</div>';
    }
  }

  async function openAgentRunDetail(runId) {
    const detailEl = document.getElementById('agentRunDetail');
    const titleEl = document.getElementById('agentRunDetailTitle');
    const bodyEl = document.getElementById('agentRunDetailBody');
    detailEl.style.display = 'block';
    titleEl.textContent = '⏳ 加载中...';
    bodyEl.textContent = '';

    try {
      const resp = await fetch('/api/agent/runs/' + encodeURIComponent(runId));
      const data = await resp.json();
      if (data.error) {
        bodyEl.textContent = '❌ ' + data.error;
        return;
      }
      const run = data.run || {};
      titleEl.textContent = '🔄 执行详情: ' + escapeHtml(run.user_input || '').substring(0, 40);

      let text = '';
      text += '用户输入: ' + (run.user_input || '') + '\n';
      text += '状态: ' + (run.status || '') + '\n';
      text += '模型: ' + (run.model_used || '-') + '\n';
      text += '耗时: ' + (run.duration_ms ? (run.duration_ms / 1000).toFixed(1) + 's' : '-') + '\n';
      text += '时间: ' + (run.created_at || '') + '\n';
      text += '\n' + '='.repeat(40) + '\n';
      text += '工具调用:\n' + '='.repeat(40) + '\n\n';

      const toolCalls = run.tool_calls || [];
      if (toolCalls.length === 0) {
        text += '（无工具调用）\n';
      } else {
        for (const tc of toolCalls) {
          text += `[${tc.call_order || '?'}] ${tc.tool_name}\n`;
          text += `  参数: ${tc.arguments_json || '{}'}\n`;
          text += `  耗时: ${tc.duration_ms ? (tc.duration_ms / 1000).toFixed(1) + 's' : '-'}\n`;
          text += `  结果摘要: ${tc.result_summary || ''}\n\n`;
        }
      }

      text += '\n' + '='.repeat(40) + '\n';
      text += '回复摘要:\n' + '='.repeat(40) + '\n';
      text += (run.result_summary || '（无）').substring(0, 500);

      bodyEl.textContent = text;
    } catch (e) {
      bodyEl.textContent = '❌ 加载详情失败: ' + e.message;
    }
  }

  function closeAgentRunDetail() {
    document.getElementById('agentRunDetail').style.display = 'none';
  }

    // ==================== ⚙️ 设置 ====================

    async function loadSettings() {
        const statusEl = document.getElementById('settingsStatus');
        statusEl.textContent = '⏳ 加载中...';
        try {
          const resp = await fetch('/api/settings');
          const data = await resp.json();
          document.getElementById('setApiBase').value = data.api_base || data.api_base_default || '';
          document.getElementById('setApiKey').value = data.api_key || '';
          document.getElementById('setModel').value = data.model || data.model_default || '';

          // Update right panel summary
          document.getElementById('settingsSummaryBase').textContent = data.api_base || data.api_base_default || '-';
          document.getElementById('settingsSummaryModel').textContent = data.model || data.model_default || '-';
          const isLocal = (data.api_base || '').includes('127.0.0.1') || (data.api_base || '').includes('localhost');
          document.getElementById('settingsStatusInfo').textContent = isLocal ? '🟢 本地 Ollama' : '🟡 外部 API';

          statusEl.textContent = '✅ 已加载';
          statusEl.style.color = 'var(--green)';
        } catch (e) {
          statusEl.textContent = '❌ 加载失败: ' + e.message;
          statusEl.style.color = 'var(--red)';
        }
        setTimeout(() => { statusEl.textContent = ''; }, 3000);
        }

        async function saveSettings() {
            const statusEl = document.getElementById('settingsStatus');
            const data = {
                api_base: document.getElementById('setApiBase').value.trim(),
                api_key: document.getElementById('setApiKey').value.trim(),
                model: document.getElementById('setModel').value.trim(),
            };
            statusEl.textContent = '⏳ 保存中...';
            statusEl.style.color = '';
            try {
                const resp = await fetch('/api/settings', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify(data),
                });
                const result = await resp.json();
                if (result.error) {
                    statusEl.textContent = '❌ ' + result.error;
                    statusEl.style.color = 'var(--red)';
                } else {
                    statusEl.textContent = '✅ ' + (result.message || '已保存');
                    statusEl.style.color = 'var(--green)';
                }
            } catch (e) {
                statusEl.textContent = '❌ 保存失败: ' + e.message;
                statusEl.style.color = 'var(--red)';
            }
            setTimeout(() => { statusEl.textContent = ''; }, 5000);
        }

        async function scanOllamaModels() {
            const btn = document.getElementById('btnScanModels');
            const listEl = document.getElementById('localModelsList');
            btn.textContent = '⏳ 扫描中...';
            btn.disabled = true;
            listEl.style.display = 'none';
            try {
                const resp = await fetch('/api/settings/ollama-models');
                const result = await resp.json();
                if (result.error) {
                    listEl.innerHTML = '<p style="color:var(--red);font-size:13px">❌ ' + result.error + '</p>';
                } else if (result.models && result.models.length > 0) {
                    const isLocalApi = (result.current_api === '' || result.current_api.includes('127.0.0.1') || result.current_api.includes('localhost'));
                    let html = '<p style="font-size:13px;color:var(--text-secondary);margin:0 0 6px">📦 本地已安装模型：</p><div style="display:flex;flex-wrap:wrap;gap:6px">';
                    for (const m of result.models) {
                        html += '<span class="model-chip" onclick="document.getElementById(\'setModel\').value=\'' + m.replace(/'/g, "\\'") + '\'">' + m + '</span>';
                    }
                    html += '</div>';
                    if (!isLocalApi) {
                        html += '<p style="font-size:12px;color:var(--orange);margin:6px 0 0">⚠️ 当前 API 地址不是本地 Ollama，扫描的模型可能不适用</p>';
                    }
                    listEl.innerHTML = html;
                } else {
                    listEl.innerHTML = '<p style="color:var(--text-secondary);font-size:13px">未检测到本地模型，请确认 Ollama 已启动并安装了模型</p>';
                }
                listEl.style.display = 'block';
            } catch (e) {
                listEl.innerHTML = '<p style="color:var(--red);font-size:13px">❌ 扫描失败: ' + e.message + '</p>';
                listEl.style.display = 'block';
            }
            btn.textContent = '📡 扫描';
            btn.disabled = false;
        }

        function resetSettingsForm() {
            document.getElementById('setApiBase').value = '';
            document.getElementById('setApiKey').value = '';
            document.getElementById('setModel').value = '';
            document.getElementById('localModelsList').style.display = 'none';
        }

    // ── Hook into tab switching ────────────────────────────────────────
    const _origSwitchTab = window.switchTab;
    window.switchTab = function(tabId) {
      _origSwitchTab(tabId);
      if (tabId === 'kanban') {
        loadKanban();
      }
      if (tabId === 'trace') {
        loadAgentRuns();
      }
      if (tabId === 'settings') {
        loadSettings();
      }
      if (tabId === 'chat') {
        loadChatSessions();
      }
      loadRightPanel(tabId);
    };

// ── CSV 批量导入 ──────────────────────────────────────────────────

async function handleCsvImport(event) {
  const file = event.target.files[0];
  if (!file) return;

  const formData = new FormData();
  formData.append('file', file);

  try {
    const resp = await fetch('/api/members/import', {
      method: 'POST',
      body: formData,
    });
    const result = await resp.json();

    if (result.error) {
      showKanbanError('导入失败: ' + result.error);
      return;
    }

    const imported = result.imported || 0;
    const errCount = (result.errors || []).length;
    let msg = `✅ 成功导入 ${imported} 人`;
    if (errCount > 0) {
      msg += `，${errCount} 行跳过`;
      console.warn('CSV 导入错误:', result.errors);
    }

    // Show success message
    const detailEl = document.getElementById('kanbanMemberDetail');
    detailEl.innerHTML = `<div style="color:var(--green);padding:20px;font-size:14px;text-align:center">${msg}</div>`;

    // Refresh kanban
    await loadKanban();
  } catch (e) {
    showKanbanError('导入请求失败: ' + e.message);
  }

  // Reset file input so the same file can be re-imported
  event.target.value = '';
}
