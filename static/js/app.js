/* =========================================================
   StoryDiffusion 小说漫画工作室 - 核心应用逻辑
   ========================================================= */

// =========================================================
// 配置持久化 - 刷新/重启后自动恢复
// =========================================================

// 需要记住的配置控件 ID 列表
const CONFIG_IDS = [
  // 小说 Tab
  'novel-llm-interface', 'novel-llm-model', 'novel-llm-url', 'novel-llm-key',
  'novel-temperature', 'novel-max-tokens',
  'novel-emb-interface', 'novel-emb-model', 'novel-emb-url', 'novel-emb-key',
  'novel-lang-style', 'novel-emotion', 'novel-taboos',
  // 漫画 Tab
  'comic-api-key', 'comic-api-url', 'comic-model', 'comic-style',
  'comic-layout', 'comic-size', 'comic-seed', 'comic-thinking',
  // 流水线 Tab
  'pipe-llm-interface', 'pipe-llm-key', 'pipe-llm-model',
  'pipe-wanxiang-key', 'pipe-style', 'pipe-layout',
  // 小红书 Tab
  'xhs-llm-interface', 'xhs-llm-model', 'xhs-llm-url', 'xhs-llm-key',
  'xhs-wanxiang-key', 'xhs-wanxiang-url', 'xhs-model', 'xhs-style',
  'xhs-layout', 'xhs-size', 'xhs-seed', 'xhs-thinking', 'xhs-economy',
];

// 页面加载时恢复已保存的配置
function loadAllConfig() {
  CONFIG_IDS.forEach(id => {
    const el = document.getElementById(id);
    if (!el) return;
    const saved = localStorage.getItem(`sd_${id}`);
    if (saved === null) return;
    if (el.type === 'checkbox') {
      el.checked = saved === 'true';
    } else {
      el.value = saved;
    }
  });
}

// 监听所有配置控件的变更并自动保存
function watchConfigChanges() {
  CONFIG_IDS.forEach(id => {
    const el = document.getElementById(id);
    if (!el) return;
    const save = () => {
      if (el.type === 'checkbox') {
        localStorage.setItem(`sd_${id}`, el.checked);
      } else {
        localStorage.setItem(`sd_${id}`, el.value);
      }
    };
    el.addEventListener('change', save);
    el.addEventListener('input', save);  // 实时保存
  });
}

// 执行配置恢复和监听
loadAllConfig();
watchConfigChanges();

// 清空配置（可用于"重置"按钮）
function clearSavedConfig() {
  CONFIG_IDS.forEach(id => localStorage.removeItem(`sd_${id}`));
  location.reload();
}

// ----- Tab 切换 -----
document.querySelectorAll('.tab-btn').forEach(btn => {
  btn.addEventListener('click', () => {
    const tab = btn.dataset.tab;
    // 切换按钮状态
    document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    // 切换内容
    document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
    document.getElementById(`tab-${tab}`).classList.add('active');
  });
});

// ----- Toast 通知系统 -----
function showToast(message, type = 'info') {
  const container = document.getElementById('toast-container');
  const toast = document.createElement('div');
  toast.className = `toast toast-${type}`;
  toast.textContent = message;
  container.appendChild(toast);
  setTimeout(() => {
    toast.style.opacity = '0';
    toast.style.transition = 'opacity 0.3s';
    setTimeout(() => toast.remove(), 300);
  }, 4000);
}

// ----- Collapsible 折叠面板 -----
function toggleCollapsible(header) {
  const body = header.nextElementSibling;
  const arrow = header.querySelector('.arrow');
  if (body) {
    body.classList.toggle('open');
    if (arrow) arrow.classList.toggle('open');
  }
}

// 默认展开漫画 Tab 的 API 配置（如果有已保存的 Key）
document.querySelectorAll('.collapsible-body').forEach(b => {
  const header = b.previousElementSibling;
  if (header && header.classList.contains('collapsible-header')) {
    const keyInput = b.querySelector('input[type="password"]');
    if (keyInput && keyInput.value) {
      b.classList.add('open');
      const arrow = header.querySelector('.arrow');
      if (arrow) arrow.classList.add('open');
    }
  }
});

// ----- 通用 API 请求 -----
async function apiPost(url, data) {
  const resp = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  if (!resp.ok) {
    let detail = '';
    try { const j = await resp.json(); detail = j.detail || resp.statusText; }
    catch { detail = resp.statusText; }
    throw new Error(detail);
  }
  return resp.json();
}

async function apiGet(url) {
  const resp = await fetch(url);
  if (!resp.ok) {
    let detail = '';
    try { const j = await resp.json(); detail = j.detail || resp.statusText; }
    catch { detail = resp.statusText; }
    throw new Error(detail);
  }
  return resp.json();
}

// ----- 嵌入接口切换动态提示 -----
document.addEventListener('DOMContentLoaded', function() {
  const embSelect = document.getElementById('novel-emb-interface');
  const embHint = document.getElementById('novel-emb-hint');
  const embModel = document.getElementById('novel-emb-model');
  if (embSelect && embHint && embModel) {
    function updateEmbHint() {
      const val = embSelect.value.trim().toLowerCase();
      if (val === 'local bge') {
        embHint.innerHTML = '本地模型方案：直接加载已有模型文件（支持本地路径或 HuggingFace ID）';
        embModel.placeholder = '本地路径 或 BAAI/bge-large-zh-v1.5';
      } else if (val === 'ollama') {
        embHint.innerHTML = 'Ollama 方案：安装 ollama → 执行 <code>ollama pull bge-m3</code> 即可使用';
        embModel.placeholder = 'bge-m3 / bge-large-zh-v1.5';
      } else {
        embHint.innerHTML = '';
      }
    }
    embSelect.addEventListener('change', updateEmbHint);
    updateEmbHint(); // 初始化
  }
});

// ----- 图片文件转 Base64 -----
function fileToBase64(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result);
    reader.onerror = reject;
    reader.readAsDataURL(file);
  });
}

// ----- HTML 转义（全局） -----
function escapeHtml(text) {
  if (!text) return '';
  const div = document.createElement('div');
  div.textContent = text;
  return div.innerHTML;
}
