/**
 * app.js - Client-Side Interactive Engine for Tunisie Telecom Log AI Suite
 */

let currentReportData = null;
let currentFilter = 'all';
let currentSearchQuery = '';
let selectedFile = null;

// ==========================================
// Tabs & Input Handling
// ==========================================
function switchTab(tab) {
  const uploadBtn = document.getElementById('tab-upload-btn');
  const pasteBtn = document.getElementById('tab-paste-btn');
  const uploadContent = document.getElementById('tab-upload-content');
  const pasteContent = document.getElementById('tab-paste-content');

  if (tab === 'upload') {
    uploadBtn.classList.add('active');
    pasteBtn.classList.remove('active');
    uploadContent.style.display = 'block';
    pasteContent.style.display = 'none';
  } else {
    pasteBtn.classList.add('active');
    uploadBtn.classList.remove('active');
    uploadContent.style.display = 'none';
    pasteContent.style.display = 'block';
  }
}

// Drag & Drop Setup
const dropzone = document.getElementById('dropzone');
const fileInput = document.getElementById('file-input');
const selectedFileDisplay = document.getElementById('selected-file-display');

['dragenter', 'dragover'].forEach(eventName => {
  dropzone.addEventListener(eventName, (e) => {
    e.preventDefault();
    e.stopPropagation();
    dropzone.classList.add('dragover');
  });
});

['dragleave', 'drop'].forEach(eventName => {
  dropzone.addEventListener(eventName, (e) => {
    e.preventDefault();
    e.stopPropagation();
    dropzone.classList.remove('dragover');
  });
});

dropzone.addEventListener('drop', (e) => {
  const dt = e.dataTransfer;
  const files = dt.files;
  if (files && files.length > 0) {
    handleFileSelected(files[0]);
  }
});

fileInput.addEventListener('change', (e) => {
  if (e.target.files && e.target.files.length > 0) {
    handleFileSelected(e.target.files[0]);
  }
});

function handleFileSelected(file) {
  selectedFile = file;
  selectedFileDisplay.style.display = 'block';
  selectedFileDisplay.innerHTML = `
    <div class="selected-file-pill">
      <span>📄 ${escapeHtml(file.name)} (${(file.size / 1024).toFixed(1)} KB)</span>
      <span class="remove-file" onclick="removeSelectedFile(event)">✕</span>
    </div>
  `;
}

function removeSelectedFile(e) {
  if (e) e.stopPropagation();
  selectedFile = null;
  fileInput.value = '';
  selectedFileDisplay.style.display = 'none';
  selectedFileDisplay.innerHTML = '';
}

// ==========================================
// Sample Log Loader
// ==========================================
async function loadSampleLog(engine) {
  try {
    const res = await fetch(`/api/samples/${engine}`);
    if (!res.ok) throw new Error('Impossible de charger le fichier exemple.');
    const data = await res.json();

    // Switch to paste tab and fill textarea
    switchTab('paste');
    document.getElementById('log-text-input').value = data.content;

    // Set engine select to auto or specific engine
    document.getElementById('engine-select').value = engine;

    // Automatically trigger analysis for seamless 1-click demo
    submitAnalysis();
  } catch (err) {
    alert('Erreur lors du chargement de l\'exemple: ' + err.message);
  }
}

// ==========================================
// ==========================================
// Theme (Dark / Light Mode)
// ==========================================
function initTheme() {
  const saved = localStorage.getItem('tt_theme') || (window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light');
  applyTheme(saved);
}

function applyTheme(theme) {
  document.documentElement.setAttribute('data-theme', theme);
  const icon = document.getElementById('theme-icon');
  const text = document.getElementById('theme-text');
  if (icon && text) {
    if (theme === 'dark') {
      icon.textContent = '☀️';
      text.textContent = 'Mode Clair';
    } else {
      icon.textContent = '🌙';
      text.textContent = 'Mode Sombre';
    }
  }
  localStorage.setItem('tt_theme', theme);
}

function toggleTheme() {
  const current = document.documentElement.getAttribute('data-theme') || 'light';
  applyTheme(current === 'dark' ? 'light' : 'dark');
}

// ==========================================
// API Key Management
// ==========================================
function initApiKey() {
  const savedKey = localStorage.getItem('gemini_api_key') || '';
  const input = document.getElementById('api-key-input');
  if (input && savedKey) {
    input.value = savedKey;
  }
}

function saveApiKey(val) {
  if (val && val.trim()) {
    localStorage.setItem('gemini_api_key', val.trim());
  } else {
    localStorage.removeItem('gemini_api_key');
  }
}

function handleModeChange(mode) {
  const apiKeyGroup = document.getElementById('api-key-group');
  if (apiKeyGroup) {
    if (mode === 'gemini' || mode === 'groq') {
      apiKeyGroup.style.border = '1px solid var(--tt-cyan)';
      apiKeyGroup.style.borderRadius = 'var(--radius-md)';
      apiKeyGroup.style.padding = '10px';
    } else {
      apiKeyGroup.style.border = 'none';
      apiKeyGroup.style.padding = '0';
    }
  }
}

// Init on script load
document.addEventListener('DOMContentLoaded', () => {
  initTheme();
  initApiKey();
});

// ==========================================
// Submit Analysis
// ==========================================
async function submitAnalysis() {
  const isUploadTab = document.getElementById('tab-upload-btn').classList.contains('active');
  const engine = document.getElementById('engine-select').value;
  const mode = document.getElementById('mode-select').value;
  const filterInfo = document.getElementById('filter-info-checkbox').checked;
  const apiKeyInput = document.getElementById('api-key-input');
  const apiKey = (apiKeyInput ? apiKeyInput.value.trim() : '') || localStorage.getItem('gemini_api_key') || '';

  const btn = document.getElementById('btn-submit');
  const spinner = document.getElementById('loading-spinner');
  const btnText = document.getElementById('btn-text');

  let logText = '';
  let fileToUpload = null;

  if (isUploadTab) {
    if (!selectedFile) {
      alert('Veuillez sélectionner ou déposer un fichier de log.');
      return;
    }
    fileToUpload = selectedFile;
  } else {
    logText = document.getElementById('log-text-input').value.trim();
    if (!logText) {
      alert('Veuillez coller le contenu d\'un log dans la zone de texte.');
      return;
    }
  }

  // Set Loading State
  btn.disabled = true;
  spinner.style.display = 'inline-block';
  btnText.style.display = 'none';

  try {
    let response;

    if (fileToUpload) {
      const formData = new FormData();
      formData.append('file', fileToUpload);
      formData.append('engine', engine);
      formData.append('mode', mode);
      formData.append('filter_informational', filterInfo);
      if (apiKey) {
        formData.append('api_key', apiKey);
      }

      response = await fetch('/api/analyze/upload', {
        method: 'POST',
        body: formData
      });
    } else {
      response = await fetch('/api/analyze', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          log_text: logText,
          engine: engine,
          mode: mode,
          filter_informational: filterInfo,
          api_key: apiKey || null
        })
      });
    }

    if (!response.ok) {
      let errorMsg = 'Erreur serveur (' + response.status + ')';
      try {
        const errData = await response.json();
        errorMsg = errData.detail || errData.message || errorMsg;
      } catch (_) {
        try {
          const text = await response.text();
          if (text) errorMsg = text.slice(0, 200);
        } catch (_) {}
      }
      throw new Error(errorMsg);
    }

    const data = await response.json();
    currentReportData = data;
    renderResults(data);

    // Smooth scroll down to results
    document.getElementById('results-section').scrollIntoView({ behavior: 'smooth', block: 'start' });

  } catch (err) {
    alert('Erreur: ' + err.message);
  } finally {
    btn.disabled = false;
    spinner.style.display = 'none';
    btnText.style.display = 'inline';
  }
}

// ==========================================
// Render Results Dashboard
// ==========================================
function renderResults(data) {
  const resultsSection = document.getElementById('results-section');
  resultsSection.style.display = 'block';

  // 1. Engine Auto-Detection Banner
  const engine = (data.engine || 'oracle').toLowerCase();
  const banner = document.getElementById('engine-banner');
  const badgeIcon = document.getElementById('engine-badge-icon');
  const bannerTitle = document.getElementById('engine-banner-title');
  const bannerSub = document.getElementById('engine-banner-subtitle');
  const confFill = document.getElementById('confidence-fill');
  const confVal = document.getElementById('confidence-val');

  badgeIcon.className = `engine-icon-badge ${engine}`;
  badgeIcon.textContent = engine === 'oracle' ? 'ORA' : (engine === 'postgres' ? 'PG' : 'MY');

  const engineNames = { oracle: 'Oracle Database', postgres: 'PostgreSQL', mysql: 'MySQL Server' };
  bannerTitle.textContent = `${engineNames[engine] || engine.toUpperCase()} Détecté`;
  const genMode = (data.summary && data.summary.generation_mode) || data.generation_mode || 'mock';
  bannerSub.textContent = `Analysé avec le moteur de règles spécialisé et la base de connaissances (Mode: ${genMode})`;

  const confidence = data.detection_confidence ? Math.round(data.detection_confidence * 100) : 100;
  confFill.style.width = `${confidence}%`;
  confVal.textContent = `${confidence}%`;

  // 2. Summary KPI Metrics
  const totalOcc = (data.summary && data.summary.total_occurrences) || data.total_error_occurrences || 0;
  const uniqueCodes = (data.summary && data.summary.unique_error_codes) || data.unique_error_codes || (data.findings ? data.findings.length : 0);
  const realErrors = (data.summary && data.summary.total_real_errors) !== undefined ? data.summary.total_real_errors : (data.total_real_errors !== undefined ? data.total_real_errors : 0);
  const infoErrors = (data.summary && data.summary.total_informational) !== undefined ? data.summary.total_informational : (data.total_informational !== undefined ? data.total_informational : 0);

  document.getElementById('kpi-total-occurrences').textContent = totalOcc;
  document.getElementById('kpi-unique-codes').textContent = uniqueCodes;
  document.getElementById('kpi-real-errors').textContent = realErrors;
  document.getElementById('kpi-informational').textContent = infoErrors;

  // Filter count tags
  const findings = data.findings || [];
  const realCount = findings.filter(f => !f.classification || f.classification.is_real_error !== false).length;
  const infoCount = findings.length - realCount;

  document.getElementById('count-all').textContent = findings.length;
  document.getElementById('count-real').textContent = realCount;
  document.getElementById('count-info').textContent = infoCount;

  // Reset filters
  currentFilter = 'all';
  currentSearchQuery = '';
  document.getElementById('search-code-input').value = '';

  renderFindingsList();
}

// ==========================================
// Render Error Findings Cards
// ==========================================
function renderFindingsList() {
  const container = document.getElementById('findings-container');
  if (!currentReportData || !currentReportData.findings) {
    container.innerHTML = '<p style="color: var(--text-muted);">Aucune anomalie détectée dans ce log.</p>';
    return;
  }

  let findings = currentReportData.findings;

  // Apply Filter
  if (currentFilter === 'real') {
    findings = findings.filter(f => !f.classification || f.classification.is_real_error !== false);
  } else if (currentFilter === 'info') {
    findings = findings.filter(f => f.classification && f.classification.is_real_error === false);
  }

  // Apply Search
  if (currentSearchQuery.trim()) {
    const q = currentSearchQuery.toLowerCase();
    findings = findings.filter(f =>
      f.code.toLowerCase().includes(q) ||
      (f.explanation && f.explanation.meaning && f.explanation.meaning.toLowerCase().includes(q))
    );
  }

  if (findings.length === 0) {
    container.innerHTML = `
      <div class="card" style="text-align: center; padding: 40px; color: var(--text-muted);">
        <p>Aucune erreur ne correspond à vos critères de recherche.</p>
      </div>
    `;
    return;
  }

  container.innerHTML = findings.map((f, idx) => {
    const isReal = !f.classification || f.classification.is_real_error !== false;
    const exp = f.explanation || {};
    const meaning = exp.meaning || 'Description non disponible';
    const cause = exp.likely_cause || 'Cause racine en cours de détermination';
    const solution = exp.suggested_solution || 'Consulter les logs détaillés de la base.';
    const lines = f.line_numbers ? f.line_numbers.join(', ') : 'N/A';
    const rawContext = f.first_context || '';

    return `
      <div class="finding-card ${isReal ? 'real-error' : 'informational'}">
        <div class="finding-header">
          <div style="display: flex; align-items: center; gap: 10px;">
            <span class="finding-code-badge">${escapeHtml(f.code)}</span>
            <span class="tag tag-count">${f.occurrence_count} occurrence${f.occurrence_count > 1 ? 's' : ''}</span>
          </div>
          <div class="finding-tags">
            <span class="tag ${isReal ? 'tag-real' : 'tag-info'}">
              ${isReal ? '⚠ Incident Réel' : 'ℹ Message Informatif'}
            </span>
            <span style="font-size: 12px; color: var(--text-muted);">Lignes : ${lines}</span>
          </div>
        </div>

        <div class="finding-body">
          <div class="diagnosis-section">
            <div class="diagnosis-label">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"></circle><line x1="12" y1="16" x2="12" y2="12"></line><line x1="12" y1="8" x2="12.01" y2="8"></line></svg>
              Signification
            </div>
            <div class="diagnosis-text">${escapeHtml(meaning)}</div>
          </div>

          <div class="diagnosis-section">
            <div class="diagnosis-label">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"></path><line x1="12" y1="9" x2="12" y2="13"></line><line x1="12" y1="17" x2="12.01" y2="17"></line></svg>
              Cause Probable
            </div>
            <div class="diagnosis-text">${escapeHtml(cause)}</div>
          </div>

          <div class="solution-box">
            <div class="diagnosis-label">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="9 11 12 14 22 4"></polyline><path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11"></path></svg>
              Solution Recommandée & Actions Correctives
            </div>
            <div class="diagnosis-text">${escapeHtml(solution)}</div>
          </div>

          ${rawContext ? `
            <div class="context-toggle">
              <button type="button" class="btn-toggle-context" onclick="toggleContext('ctx-${idx}')">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="6 9 12 15 18 9"></polyline></svg>
                Voir l'extrait brut du log
              </button>
              <pre id="ctx-${idx}" class="raw-log-snippet">${escapeHtml(rawContext)}</pre>
            </div>
          ` : ''}
        </div>
      </div>
    `;
  }).join('');
}

function toggleContext(id) {
  const el = document.getElementById(id);
  if (el) {
    el.style.display = el.style.display === 'block' ? 'none' : 'block';
  }
}

// ==========================================
// Filtering & Search
// ==========================================
function filterFindings(type, btnEl) {
  currentFilter = type;
  document.querySelectorAll('.btn-filter').forEach(b => b.classList.remove('active'));
  btnEl.classList.add('active');
  renderFindingsList();
}

function searchFindings(query) {
  currentSearchQuery = query;
  renderFindingsList();
}

// ==========================================
// Report Download Handlers
// ==========================================
function downloadMarkdownReport() {
  if (!currentReportData || !currentReportData.markdown_report) {
    alert('Aucun rapport à télécharger.');
    return;
  }
  const blob = new Blob([currentReportData.markdown_report], { type: 'text/markdown;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `rapport_triage_tt_${new Date().toISOString().slice(0, 10)}.md`;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

function downloadJsonReport() {
  if (!currentReportData) {
    alert('Aucun rapport à télécharger.');
    return;
  }
  const blob = new Blob([JSON.stringify(currentReportData, null, 2)], { type: 'application/json;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `rapport_triage_tt_${new Date().toISOString().slice(0, 10)}.json`;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

// ==========================================
// Interactive DBA AI Chatbot Client
// ==========================================
let chatSessionHistory = [];

function toggleChatbot() {
  const windowEl = document.getElementById('chatbot-window');
  if (!windowEl) return;
  const isHidden = windowEl.style.display === 'none' || !windowEl.style.display;
  windowEl.style.display = isHidden ? 'flex' : 'none';
  if (isHidden) {
    setTimeout(() => {
      const input = document.getElementById('chat-input');
      if (input) input.focus();
    }, 100);
  }
}

function clearChatHistory() {
  chatSessionHistory = [];
  const container = document.getElementById('chat-messages');
  if (container) {
    container.innerHTML = `
      <div class="chat-msg assistant">
        <div class="msg-bubble">
          Historique réinitialisé. Comment puis-je vous assister sur vos bases de données ou l'analyse de vos logs ?
        </div>
      </div>
    `;
  }
}

function sendQuickPrompt(promptText) {
  const input = document.getElementById('chat-input');
  if (input) {
    input.value = promptText;
    handleChatSubmit(new Event('submit'));
  }
}

function handleChatKeyDown(e) {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault();
    handleChatSubmit(e);
  }
}

async function handleChatSubmit(e) {
  if (e) e.preventDefault();
  const input = document.getElementById('chat-input');
  if (!input) return;
  const message = input.value.trim();
  if (!message) return;

  const modeSelect = document.getElementById('chat-mode-select');
  const chatMode = modeSelect ? modeSelect.value : 'gemini';
  const apiKeyInput = document.getElementById('api-key-input');
  const apiKey = (apiKeyInput ? apiKeyInput.value.trim() : '') || localStorage.getItem('gemini_api_key') || '';

  // Append user message to UI
  appendChatMessage('user', message);
  input.value = '';

  // Show typing indicator
  const typingEl = document.getElementById('chat-typing');
  const sendBtn = document.getElementById('btn-chat-send');
  if (typingEl) typingEl.style.display = 'flex';
  if (sendBtn) sendBtn.disabled = true;

  // Scroll to bottom
  scrollChatToBottom();

  try {
    const payload = {
      message: message,
      history: chatSessionHistory,
      mode: chatMode,
      engine: currentReportData ? currentReportData.engine : null,
      report_context: currentReportData || null,
      api_key: apiKey || null
    };

    const res = await fetch('/api/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });

    if (!res.ok) {
      const errData = await res.json().catch(() => ({}));
      throw new Error(errData.detail || 'Erreur lors de la réponse du chatbot.');
    }

    const data = await res.json();
    const reply = data.reply || 'Désolé, aucune réponse générée.';

    // Append to local history
    chatSessionHistory.push({ role: 'user', content: message });
    chatSessionHistory.push({ role: 'assistant', content: reply });

    // Append assistant response to UI
    appendChatMessage('assistant', reply, data.mode_used);

  } catch (err) {
    appendChatMessage('assistant', `⚠️ Erreur : ${escapeHtml(err.message)}`);
  } finally {
    if (typingEl) typingEl.style.display = 'none';
    if (sendBtn) sendBtn.disabled = false;
    scrollChatToBottom();
  }
}

function appendChatMessage(role, text, modeUsed = '') {
  const container = document.getElementById('chat-messages');
  if (!container) return;

  const msgDiv = document.createElement('div');
  msgDiv.className = `chat-msg ${role}`;

  const modeBadge = modeUsed ? `<div style="font-size: 10px; color: var(--text-muted); margin-bottom: 4px;">Modèle : ${escapeHtml(modeUsed)}</div>` : '';
  const formattedContent = role === 'assistant' ? formatChatMessage(text) : escapeHtml(text);

  msgDiv.innerHTML = `
    <div class="msg-bubble">
      ${modeBadge}
      ${formattedContent}
    </div>
  `;

  container.appendChild(msgDiv);
  scrollChatToBottom();
}

function scrollChatToBottom() {
  const container = document.getElementById('chat-messages');
  if (container) {
    container.scrollTop = container.scrollHeight;
  }
}

function formatChatMessage(text) {
  if (!text) return '';

  // 1. Code blocks: ```sql ... ```
  let formatted = text.replace(/```([a-zA-Z0-9_-]*)\n([\s\S]*?)```/g, (match, lang, code) => {
    const safeCode = escapeHtml(code.trim());
    const id = 'code-' + Math.random().toString(36).substring(2, 9);
    return `
      <pre>
        <button type="button" class="copy-code-btn" onclick="copySnippet('${id}')">Copier</button>
        <code id="${id}" class="language-${lang || 'text'}">${safeCode}</code>
      </pre>
    `;
  });

  // 2. Inline code: `code`
  formatted = formatted.replace(/`([^`]+)`/g, '<code>$1</code>');

  // 3. Bold: **bold** or __bold__
  formatted = formatted.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');

  // 4. Headers: ### Title
  formatted = formatted.replace(/^### (.*$)/gim, '<h5 style="margin: 8px 0 4px 0; color: var(--tt-cyan);">$1</h5>');
  formatted = formatted.replace(/^## (.*$)/gim, '<h4 style="margin: 8px 0 4px 0; color: var(--tt-navy);">$1</h4>');

  // 5. Bullet points: - item or * item
  formatted = formatted.replace(/^\s*[-*]\s+(.*)$/gim, '<div style="margin-left: 12px;">• $1</div>');

  // 6. Newlines to <br> (avoiding pre blocks)
  formatted = formatted.replace(/\n\n/g, '<br><br>').replace(/\n/g, '<br>');

  return formatted;
}

function copySnippet(elementId) {
  const codeEl = document.getElementById(elementId);
  if (!codeEl) return;
  const text = codeEl.innerText;
  navigator.clipboard.writeText(text).then(() => {
    alert('Code SQL / Commande copié dans le presse-papiers !');
  }).catch(() => {});
}

// Utility
function escapeHtml(str) {
  if (!str) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}
