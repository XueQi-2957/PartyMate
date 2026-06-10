/* =========================================================
   PartyMate — 党务智能助手 Web UI (客户端逻辑 v1.3)
   ========================================================= */

// ==================== 工具函数 ====================

function escapeHtml(text) {
  const map = {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;'};
  return text.replace(/[&<>"']/g, m => map[m]);
}

function formatAIOutput(text) {
  const safe = escapeHtml(text);
  // 将 **xxx** 转为 <strong>xxx</strong>
  const bolded = safe.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
  // 将 ### xxx 转为 <h4>xxx</h4>
  const headered = bolded.replace(/^### (.+)$/gm, '<h4 style="margin:10px 0 4px;color:var(--red);font-size:14px">$1</h4>');
  const paragraphs = headered.replace(/^## (.+)$/gm, '<h3 style="margin:12px 0 6px;color:var(--red);font-size:15px">$1</h3>');
  return paragraphs.replace(/\n\n/g, '</p><p>').replace(/\n/g, '<br>').replace(/\|/g, '│');
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
    text.textContent = '运行中 · ' + ollamaStatus;
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

async function callAPI(endpoint, body) {
  const resp = await fetch('/api/' + endpoint, {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(body),
  });
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

// ==================== 会议整理 ====================

async function runMeeting(opts) {
  let raw = document.getElementById('meetingInput').value.trim();
  if (!raw) { alert('请粘贴会议记录或上传文件'); return; }
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
    incrementStat('meetings');
  } catch (e) {
    document.getElementById('meetingBody').textContent = '❌ 请求失败: ' + e.message;
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

async function sendChat() {
  const input = document.getElementById('chatInput');
  let msg = input.value.trim();
  const messagesEl = document.getElementById('chatMessages');
  const statusEl = document.getElementById('chatStatus');

  // 如果有文件内容且没有消息，默认询问
  if (!msg && window._chatFileContent) {
    msg = '请检查这份文件的内容是否符合规范';
  }
  if (!msg) return;

  // 组装消息：文件内容 + 用户输入
  let fullMsg = msg;
  if (window._chatFileContent) {
    fullMsg = `[文件: ${window._chatFileName}]\n\`\`\`\n${window._chatFileContent.substring(0, 8000)}\n\`\`\`\n\n用户提问: ${msg}`;
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
    const data = await callAPI('chat', {message: fullMsg});
    const aiDiv = document.createElement('div');
    aiDiv.className = 'msg msg-ai';
    aiDiv.innerHTML = '<div class="msg-avatar">🤖</div><div class="msg-bubble">' + formatAIOutput(data.result || '无响应') + '</div>';
    messagesEl.appendChild(aiDiv);
    statusEl.textContent = '';
  } catch (e) {
    const errDiv = document.createElement('div');
    errDiv.className = 'msg msg-ai';
    errDiv.innerHTML = '<div class="msg-avatar">🤖</div><div class="msg-bubble">❌ 请求失败: ' + escapeHtml(e.message) + '</div>';
    messagesEl.appendChild(errDiv);
    statusEl.textContent = '';
  }
  messagesEl.scrollTop = messagesEl.scrollHeight;
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

// ==================== 初始化 ====================

document.addEventListener('DOMContentLoaded', function() {
  setDate();
  checkStatus();
  updateDashboardStats();
  updateRecentFiles();
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

// ── Hook into tab switching ────────────────────────────────────────
// Save original switchTab to call after
const _origSwitchTab = window.switchTab;
window.switchTab = function(tabId) {
  _origSwitchTab(tabId);
  if (tabId === 'kanban') {
    loadKanban();
  }
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
