/* =========================================================
   StoryDiffusion - 小红书带货 Tab
   ========================================================= */

// ----- 状态 -----
let xhsProductInfo = null;
let xhsGeneratedContent = null;
let xhsScenes = [];
let xhsComicImages = [];

// 调试：在控制台输出加载状态
console.log('[xhs.js] 脚本已加载, 版本 v2');

// ----- 初始化选项 -----
async function initXhsOptions() {
  try {
    console.log('[xhs.js] 开始初始化...');
    const [styles, layouts, publishCheck] = await Promise.all([
      apiGet('/api/comic/styles'),
      apiGet('/api/comic/layouts'),
      apiGet('/api/xhs/publish/check'),
    ]);

    // 风格下拉
    const styleSelect = document.getElementById('xhs-style');
    (styles.styles || []).forEach(s => {
      const opt = document.createElement('option');
      opt.value = s; opt.textContent = s;
      if (s === 'Japanese Anime') opt.selected = true;
      styleSelect.appendChild(opt);
    });

    // 排版下拉
    const layoutSelect = document.getElementById('xhs-layout');
    (layouts.layouts || []).forEach(l => {
      const opt = document.createElement('option');
      opt.value = l; opt.textContent = l;
      layoutSelect.appendChild(opt);
    });

    // 发布状态提示
    await updateLoginStatusUI(publishCheck);
  } catch (e) {
    console.error('初始化小红书选项失败:', e);
  }
}
initXhsOptions();

// 用 try-catch 包裹后续的事件注册，避免单个异常导致全部失效
try {
  console.log('[xhs.js] 开始注册事件监听...');

// ----- 登录小红书（在当前浏览器中登录 + 提取 Cookies）-----
const xhsLoginBtn = document.getElementById('xhs-login-btn');
if (xhsLoginBtn) {
  xhsLoginBtn.addEventListener('click', async () => {
    await showCookieDialog();
  });
}

async function showCookieDialog() {
  const overlay = document.getElementById('xhs-cookie-overlay');
  const modal = document.getElementById('xhs-cookie-modal');
  if (overlay && modal) {
    overlay.style.display = 'flex';
    modal.style.display = 'block';
  }
}

function hideCookieDialog() {
  const overlay = document.getElementById('xhs-cookie-overlay');
  const modal = document.getElementById('xhs-cookie-modal');
  if (overlay) overlay.style.display = 'none';
  if (modal) modal.style.display = 'none';
}

// 关闭弹窗（点击遮罩层）
document.addEventListener('click', (e) => {
  const overlay = document.getElementById('xhs-cookie-overlay');
  if (e.target === overlay) hideCookieDialog();
});

// 在默认浏览器中打开小红书
const xhsOpenBtn = document.getElementById('xhs-open-browser-btn');
if (xhsOpenBtn) {
  xhsOpenBtn.addEventListener('click', async () => {
  const btn = document.getElementById('xhs-open-browser-btn');
  const msg = document.getElementById('xhs-cookie-msg');
  btn.disabled = true;
  btn.innerHTML = '<span class="spinner"></span> 打开中...';

  try {
    const resp = await apiPost('/api/xhs/publish/login', {});
    if (resp.success) {
      msg.innerHTML = `<div class="alert alert-success">✅ 已在新窗口中打开小红书登录页。<br>请登录后回来点击「一键提取」</div>`;
      showToast(resp.hint || '浏览器已打开', 'info');
    } else {
      msg.innerHTML = `<div class="alert alert-error">❌ ${resp.message}</div>`;
    }
  } catch (e) {
    msg.innerHTML = `<div class="alert alert-error">❌ ${e.message}</div>`;
  }

  btn.disabled = false;
  btn.innerHTML = '🌐 打开小红书登录页';
  });
}

// 一键提取 Cookies
const xhsExtractBtn = document.getElementById('xhs-extract-btn');
if (xhsExtractBtn) {
  xhsExtractBtn.addEventListener('click', async () => {
  const btn = document.getElementById('xhs-extract-btn');
  const msg = document.getElementById('xhs-cookie-msg');
  const textarea = document.getElementById('xhs-cookie-textarea');

  btn.disabled = true;
  btn.innerHTML = '<span class="spinner"></span> 提取中...';

  try {
    const resp = await apiGet('/api/xhs/publish/extract-cookies');
    if (resp.success && resp.count > 0) {
      msg.innerHTML = `<div class="alert alert-success">✅ ${resp.message}<br><small>提取 ${resp.count} 个 cookies${resp.has_session ? '，登录态有效 ✅' : '，⚠️ 缺少 session'}</small></div>`;
      textarea.value = JSON.stringify(resp.session_keys || [], null, 2);
      showToast('Cookies 提取成功！', 'success');
      // 刷新登录状态
      updateLoginStatusUI();
      // 延迟关闭弹窗
      setTimeout(hideCookieDialog, 1500);
    } else {
      msg.innerHTML = `<div class="alert alert-error">❌ ${resp.message || '提取失败'}<br><small>💡 方式二：手动导出 Cookies 粘贴到下方文本框</small></div>`;
    }
  } catch (e) {
    msg.innerHTML = `<div class="alert alert-error">❌ ${e.message}<br><small>💡 请尝试手动导出：F12 → Application → Cookies</small></div>`;
  }

  btn.disabled = false;
  btn.innerHTML = '⚡ 一键提取 Cookies';
  });
}

// 手动保存 Cookies
const xhsSaveCookieBtn = document.getElementById('xhs-save-cookie-btn');
if (xhsSaveCookieBtn) {
  xhsSaveCookieBtn.addEventListener('click', async () => {
  const textarea = document.getElementById('xhs-cookie-textarea');
  const msg = document.getElementById('xhs-cookie-msg');
  const raw = textarea.value.trim();

  if (!raw) {
    msg.innerHTML = '<div class="alert alert-error">❌ 请先粘贴 Cookies JSON</div>';
    return;
  }

  let cookies;
  try {
    cookies = JSON.parse(raw);
  } catch {
    msg.innerHTML = '<div class="alert alert-error">❌ JSON 格式错误，请检查粘贴内容<br><small>应为 [{name, value, domain, path, expires, httpOnly, secure}, ...]</small></div>';
    return;
  }

  if (!Array.isArray(cookies) || cookies.length === 0) {
    msg.innerHTML = '<div class="alert alert-error">❌ cookies 应为非空数组</div>';
    return;
  }

  const btn = document.getElementById('xhs-save-cookie-btn');
  btn.disabled = true;
  btn.innerHTML = '<span class="spinner"></span> 保存中...';

  try {
    const resp = await apiPost('/api/xhs/publish/cookies', cookies);
    if (resp.success) {
      msg.innerHTML = `<div class="alert alert-success">✅ ${resp.message}</div>`;
      showToast('Cookies 已保存！', 'success');
      updateLoginStatusUI();
      setTimeout(hideCookieDialog, 1500);
    } else {
      msg.innerHTML = `<div class="alert alert-error">❌ ${resp.message}</div>`;
    }
  } catch (e) {
    msg.innerHTML = `<div class="alert alert-error">❌ ${e.message}</div>`;
  }

  btn.disabled = false;
  btn.innerHTML = '💾 保存 Cookies';
  });
}

// ----- 更新登录状态 UI -----
async function updateLoginStatusUI(initialData) {
  const statusEl = document.getElementById('xhs-publish-status');
  const loginBtn = document.getElementById('xhs-login-btn');

  let data = initialData;
  if (!data) {
    try {
      data = await apiGet('/api/xhs/publish/check');
    } catch {
      statusEl.innerHTML = '<span style="color:var(--danger)">❌ 检查状态失败</span>';
      return;
    }
  }

  if (data.mcp_available) {
    if (data.logged_in) {
      statusEl.innerHTML = '<span style="color:var(--success)">✅ 已登录小红书，可直接发布</span>';
      loginBtn.style.display = 'none';
    } else {
      statusEl.innerHTML = '<span style="color:var(--warning)">⚠️ 未登录小红书</span>';
      loginBtn.style.display = '';
    }
  } else {
    statusEl.innerHTML = '<span style="color:var(--danger)">❌ MCP 未就绪</span>';
    loginBtn.style.display = 'none';
  }
}

// ----- 输入模式切换 (图片/文字) -----
let xhsInputMode = 'image'; // 'image' | 'text'

document.querySelectorAll('.xhs-input-mode').forEach(btn => {
  btn.addEventListener('click', () => {
    const mode = btn.dataset.mode;
    if (mode === xhsInputMode) return;
    xhsInputMode = mode;

    // 切换按钮样式
    document.querySelectorAll('.xhs-input-mode').forEach(b => {
      b.style.background = 'transparent';
      b.style.color = 'var(--text-secondary)';
    });
    btn.style.background = 'var(--accent-1)';
    btn.style.color = '#fff';

    // 切换输入区域
    document.getElementById('xhs-input-image').style.display = mode === 'image' ? 'block' : 'none';
    document.getElementById('xhs-input-text').style.display = mode === 'text' ? 'block' : 'none';
  });
});

// ----- AI 智能填写（文字模式） -----
document.getElementById('xhs-smart-fill-btn').addEventListener('click', async () => {
  const btn = document.getElementById('xhs-smart-fill-btn');
  const status = document.getElementById('xhs-smart-status');
  const input = document.getElementById('xhs-smart-input').value.trim();

  if (!input) { showToast('请先粘贴商品描述', 'error'); return; }

  const apiKey = document.getElementById('xhs-llm-key').value.trim();
  if (!apiKey) { showToast('请填写 LLM API Key', 'error'); return; }

  btn.disabled = true;
  btn.innerHTML = '<span class="spinner"></span> 分析中...';
  status.innerHTML = '⏳ AI 正在提取商品信息...';

  try {
    const resp = await apiPost('/api/xhs/analyze-text', {
      product_description: input,
      llm: {
        llm_interface: document.getElementById('xhs-llm-interface').value,
        llm_api_key: apiKey,
        llm_base_url: document.getElementById('xhs-llm-url').value.trim(),
        llm_model: document.getElementById('xhs-llm-model').value.trim() || 'deepseek-v4-flash',
      },
    });

    if (resp.success && resp.product) {
      const p = resp.product;

      // 填充表单字段
      setVal('xhs-prod-name', p.name || '');
      setVal('xhs-prod-category', p.category || '');
      setVal('xhs-prod-features', (p.features || []).join('\n'));
      setVal('xhs-prod-scenarios', (p.usage_scenarios || []).join('、'));
      setVal('xhs-prod-style', [p.style, (p.colors || []).join('/')].filter(Boolean).join(' | '));
      setVal('xhs-prod-audience', p.target_audience || '');
      setVal('xhs-prod-extra', (p.keywords || []).join('、'));

      // 同时保存为已分析结果（跳过后续点击"分析商品"）
      xhsProductInfo = p;

      status.innerHTML = `<span style="color:var(--success)">✅ 已自动填写！商品名称：${escapeHtml(p.name || '')}</span>`;
      showToast('AI 已自动填写表单，请检查后继续', 'success');
    } else {
      // 显示详细错误指导
      const msg = resp.message || '提取失败';
      let guide = '';
      if (msg.includes('为空') || msg.includes('API')) {
        guide = '<div style="font-size:0.8rem;margin-top:4px;color:var(--warning)">💡 请检查上方 LLM 配置：<br>'
          + '① API Key 是否正确<br>'
          + '② 模型名是否正确（DeepSeek 用 deepseek-v4-flash，OpenAI 用 gpt-4o）<br>'
          + '③ API 地址是否填写（DeepSeek: https://api.deepseek.com）</div>';
      }
      status.innerHTML = `<span style="color:var(--danger)">❌ ${msg}</span>${guide}`;
    }
  } catch (e) {
    status.innerHTML = `<span style="color:var(--danger)">❌ ${e.message}</span>`;
  }

  btn.disabled = false;
  btn.innerHTML = '🤖 AI 智能填写';
});

function setVal(id, val) {
  const el = document.getElementById(id);
  if (el) el.value = val;
}

// ----- 商品图上传 -----
const xhsDropzone = document.getElementById('xhs-dropzone');
const xhsRefInput = document.getElementById('xhs-ref-input');
const xhsPreview = document.getElementById('xhs-preview');
let xhsProductImage = null;

xhsDropzone.addEventListener('click', () => xhsRefInput.click());
xhsDropzone.addEventListener('dragover', (e) => {
  e.preventDefault();
  xhsDropzone.classList.add('dragover');
});
xhsDropzone.addEventListener('dragleave', () => {
  xhsDropzone.classList.remove('dragover');
});
xhsDropzone.addEventListener('drop', (e) => {
  e.preventDefault();
  xhsDropzone.classList.remove('dragover');
  if (e.dataTransfer.files.length > 0) {
    handleXhsImage(e.dataTransfer.files[0]);
  }
});
xhsRefInput.addEventListener('change', () => {
  if (xhsRefInput.files.length > 0) {
    handleXhsImage(xhsRefInput.files[0]);
  }
});

async function handleXhsImage(file) {
  if (!file.type.startsWith('image/')) {
    showToast('请上传图片文件', 'error');
    return;
  }
  try {
    xhsProductImage = await fileToBase64(file);
    xhsPreview.src = xhsProductImage;
    xhsPreview.classList.add('show');
    xhsDropzone.querySelector('div').textContent = file.name;
  } catch (e) {
    showToast('图片读取失败', 'error');
  }
}

// ----- 商品参考图上传（用于漫画角色一致性） -----
const xhsRefDropzone = document.getElementById('xhs-ref-dropzone');
const xhsRefFileInput = document.getElementById('xhs-ref-file-input');
const xhsRefPreview = document.getElementById('xhs-ref-preview');
let xhsRefImage = null;

xhsRefDropzone.addEventListener('click', () => xhsRefFileInput.click());
xhsRefDropzone.addEventListener('dragover', (e) => {
  e.preventDefault();
  xhsRefDropzone.classList.add('dragover');
});
xhsRefDropzone.addEventListener('dragleave', () => {
  xhsRefDropzone.classList.remove('dragover');
});
xhsRefDropzone.addEventListener('drop', (e) => {
  e.preventDefault();
  xhsRefDropzone.classList.remove('dragover');
  if (e.dataTransfer.files.length > 0) {
    handleXhsRefImage(e.dataTransfer.files[0]);
  }
});
xhsRefFileInput.addEventListener('change', () => {
  if (xhsRefFileInput.files.length > 0) {
    handleXhsRefImage(xhsRefFileInput.files[0]);
  }
});

async function handleXhsRefImage(file) {
  if (!file.type.startsWith('image/')) {
    showToast('请上传图片文件', 'error');
    return;
  }
  try {
    xhsRefImage = await fileToBase64(file);
    xhsRefPreview.src = xhsRefImage;
    xhsRefPreview.classList.add('show');
    xhsRefDropzone.querySelector('div').textContent = file.name;
  } catch (e) {
    showToast('图片读取失败', 'error');
  }
}

// ----- Step 1: 分析商品 -----
document.getElementById('xhs-analyze-btn').addEventListener('click', analyzeProduct);

async function analyzeProduct() {
  const btn = document.getElementById('xhs-analyze-btn');
  const resultEl = document.getElementById('xhs-product-result');

  const apiKey = document.getElementById('xhs-llm-key').value.trim();
  const model = document.getElementById('xhs-llm-model').value.trim() || 'gpt-4o';

  if (!apiKey) { showToast('请填写 LLM API Key', 'error'); return; }

  // 根据模式准备请求
  let endpoint, payload;

  if (xhsInputMode === 'image') {
    if (!xhsProductImage) { showToast('请先上传商品图片', 'error'); return; }
    endpoint = '/api/xhs/analyze';
    payload = {
      image_data_uri: xhsProductImage,
      llm: {
        llm_interface: document.getElementById('xhs-llm-interface').value,
        llm_api_key: apiKey,
        llm_base_url: document.getElementById('xhs-llm-url').value.trim(),
        llm_model: model,
      },
    };
  } else {
    // 文字模式 — 收集表单数据
    const name = document.getElementById('xhs-prod-name').value.trim();
    if (!name) { showToast('请填写商品名称', 'error'); return; }

    const category = document.getElementById('xhs-prod-category').value.trim();
    const featuresText = document.getElementById('xhs-prod-features').value.trim();
    const scenarios = document.getElementById('xhs-prod-scenarios').value.trim();
    const style = document.getElementById('xhs-prod-style').value.trim();
    const audience = document.getElementById('xhs-prod-audience').value.trim();
    const extra = document.getElementById('xhs-prod-extra').value.trim();

    // 组装商品描述
    let desc = `商品名称：${name}`;
    if (category) desc += `\n商品类别：${category}`;
    if (featuresText) desc += `\n核心卖点：\n${featuresText}`;
    if (scenarios) desc += `\n使用场景：${scenarios}`;
    if (style) desc += `\n颜色/风格：${style}`;
    if (audience) desc += `\n目标人群：${audience}`;
    if (extra) desc += `\n补充描述：${extra}`;

    endpoint = '/api/xhs/analyze-text';
    payload = {
      product_description: desc,
      llm: {
        llm_interface: document.getElementById('xhs-llm-interface').value,
        llm_api_key: apiKey,
        llm_base_url: document.getElementById('xhs-llm-url').value.trim(),
        llm_model: model,
      },
    };
  }

  btn.disabled = true;
  btn.innerHTML = '<span class="spinner"></span> 分析中...';
  resultEl.innerHTML = '<div style="color:var(--text-secondary);padding:12px">⏳ AI 正在分析商品...</div>';

  try {
    const resp = await apiPost(endpoint, payload);

    if (resp.success && resp.product) {
      xhsProductInfo = resp.product;
      const p = resp.product;
      let html = `<div class="alert alert-success">✅ ${resp.message}</div>`;
      html += `<div style="background:var(--bg-card);padding:16px;border-radius:8px">`;
      html += `<div style="font-size:1.2rem;font-weight:700;margin-bottom:8px">🛍️ ${escapeHtml(p.name || '未知商品')}</div>`;
      html += `<div style="color:var(--text-muted);margin-bottom:8px">类别：${escapeHtml(p.category || '-')}</div>`;

      if (p.features && p.features.length) {
        html += `<div style="margin:8px 0"><strong>卖点：</strong>`;
        p.features.forEach(f => { html += `<span class="tag tag-accent">${escapeHtml(f)}</span>`; });
        html += `</div>`;
      }
      if (p.colors && p.colors.length) {
        html += `<div style="margin:8px 0"><strong>配色：</strong>`;
        p.colors.forEach(c => { html += `<span class="tag">${escapeHtml(c)}</span>`; });
        html += `</div>`;
      }
      if (p.usage_scenarios && p.usage_scenarios.length) {
        html += `<div style="margin:8px 0"><strong>使用场景：</strong>${p.usage_scenarios.join('、')}</div>`;
      }
      if (p.style) {
        html += `<div style="margin:8px 0"><strong>设计风格：</strong>${escapeHtml(p.style)}</div>`;
      }
      if (p.keywords && p.keywords.length) {
        html += `<div style="margin:8px 0"><strong>关键词：</strong>`;
        p.keywords.forEach(k => { html += `<span class="tag tag-secondary">${escapeHtml(k)}</span>`; });
        html += `</div>`;
      }
      html += `</div>`;
      resultEl.innerHTML = html;
      showToast('商品分析完成', 'success');

      // 自动滚动到第二步
      document.getElementById('xhs-step2').scrollIntoView({ behavior: 'smooth' });
    } else {
      resultEl.innerHTML = `<div class="alert alert-error">❌ ${resp.message || '分析失败'}</div>`;
    }
  } catch (e) {
    resultEl.innerHTML = `<div class="alert alert-error">❌ ${e.message}</div>`;
  }

  btn.disabled = false;
  btn.innerHTML = '🔍 分析商品';
  updateProjectStatus();
}

// ----- Step 2: 生成带货内容 -----
document.getElementById('xhs-generate-btn').addEventListener('click', generateXhsContent);

async function generateXhsContent() {
  const btn = document.getElementById('xhs-generate-btn');
  const resultEl = document.getElementById('xhs-content-result');

  const apiKey = document.getElementById('xhs-llm-key').value.trim();
  const model = document.getElementById('xhs-llm-model').value.trim() || 'deepseek-v4-flash';

  if (!xhsProductInfo) { showToast('请先分析商品', 'error'); return; }
  if (!apiKey) { showToast('请填写 LLM API Key', 'error'); return; }

  btn.disabled = true;
  btn.innerHTML = '<span class="spinner"></span> 生成中...';
  resultEl.innerHTML = '<div style="color:var(--text-secondary);padding:12px">⏳ AI 正在创作带货内容...</div>';

  try {
    const resp = await apiPost('/api/xhs/generate-content', {
      product_info: xhsProductInfo,
      llm: {
        llm_interface: document.getElementById('xhs-llm-interface').value,
        llm_api_key: apiKey,
        llm_base_url: document.getElementById('xhs-llm-url').value.trim(),
        llm_model: model,
      },
    });

    if (resp.success) {
      xhsGeneratedContent = resp;
      xhsScenes = resp.scenes || [];

      // 显示标题 + 文案
      let html = `<div class="alert alert-success">✅ ${resp.message}</div>`;

      if (resp.title) {
        html += `<div style="background:var(--bg-card);padding:16px;border-radius:8px;margin-bottom:12px">`;
        html += `<div style="font-size:1.1rem;font-weight:700;margin-bottom:8px">📌 标题</div>`;
        html += `<div style="font-size:1.3rem;color:var(--accent-1)">${escapeHtml(resp.title)}</div>`;
        html += `</div>`;
      }

      if (resp.content) {
        html += `<div style="background:var(--bg-card);padding:16px;border-radius:8px;margin-bottom:12px">`;
        html += `<div style="font-size:1rem;font-weight:700;margin-bottom:8px">📝 正文</div>`;
        html += `<div style="white-space:pre-wrap;line-height:1.6">${escapeHtml(resp.content)}</div>`;
        html += `</div>`;
      }

      if (resp.tags && resp.tags.length) {
        html += `<div style="margin-bottom:12px">`;
        resp.tags.forEach(t => { html += `<span class="tag tag-accent">${escapeHtml(t)}</span>`; });
        html += `</div>`;
      }

      // 显示场景分镜
      if (xhsScenes.length) {
        html += `<div style="font-size:1rem;font-weight:700;margin:16px 0 8px">🎬 漫画分镜 (${xhsScenes.length}格)</div>`;
        html += '<div class="gallery-grid">';
        xhsScenes.forEach((s, i) => {
          html += `<div class="gallery-item" style="padding:12px">
            <div style="font-weight:700;color:var(--accent-2);margin-bottom:4px">🎬 ${i + 1}. ${escapeHtml(s.title || `场景 ${i+1}`)}</div>
            <div style="font-size:0.85rem;color:var(--text-secondary);margin-bottom:4px">${escapeHtml(s.description || '')}</div>
            <div style="font-size:0.75rem;color:var(--text-muted);background:rgba(0,0,0,0.3);padding:6px;border-radius:4px;word-break:break-all">
              <em>prompt:</em> ${escapeHtml(s.prompt || '')}
            </div>
            <div style="margin-top:6px">
              <button class="btn btn-sm btn-secondary" onclick="editXhsScene(${i})">✏️ 编辑</button>
            </div>
          </div>`;
        });
        html += '</div>';
      }

      resultEl.innerHTML = html;
      showToast('带货内容生成成功', 'success');
      document.getElementById('xhs-step3').scrollIntoView({ behavior: 'smooth' });
    } else {
      resultEl.innerHTML = `<div class="alert alert-error">❌ ${resp.message || '生成失败'}</div>`;
    }
  } catch (e) {
    resultEl.innerHTML = `<div class="alert alert-error">❌ ${e.message}</div>`;
  }

  btn.disabled = false;
  btn.innerHTML = '📝 生成带货内容';
  updateProjectStatus();
}

// ----- 编辑场景 -----
function editXhsScene(index) {
  const scene = xhsScenes[index];
  if (!scene) return;

  const newTitle = prompt('场景标题:', scene.title || '');
  if (newTitle === null) return;
  const newDesc = prompt('场景描述:', scene.description || '');
  if (newDesc === null) return;
  const newPrompt = prompt('AI 绘图 Prompt (英文):', scene.prompt || '');
  if (newPrompt === null) return;

  xhsScenes[index] = {
    title: newTitle,
    description: newDesc,
    prompt: newPrompt,
  };
  showToast('场景已更新', 'success');
  refreshXhsScenesDisplay();
}

function refreshXhsScenesDisplay() {
  const scenesDiv = document.getElementById('xhs-scenes-display');
  if (!scenesDiv) return;
  let html = `<div class="alert alert-success">✅ 已编辑 ${xhsScenes.length} 个场景</div>`;
  html += '<div class="gallery-grid">';
  xhsScenes.forEach((s, i) => {
    html += `<div class="gallery-item" style="padding:12px">
      <div style="font-weight:700;color:var(--accent-2);margin-bottom:4px">🎬 ${i + 1}. ${escapeHtml(s.title || `场景 ${i+1}`)}</div>
      <div style="font-size:0.85rem;color:var(--text-secondary);margin-bottom:4px">${escapeHtml(s.description || '')}</div>
      <div style="font-size:0.75rem;color:var(--text-muted);background:rgba(0,0,0,0.3);padding:6px;border-radius:4px;word-break:break-all">
        <em>prompt:</em> ${escapeHtml(s.prompt || '')}
      </div>
      <div style="margin-top:6px">
        <button class="btn btn-sm btn-secondary" onclick="editXhsScene(${i})">✏️ 编辑</button>
      </div>
    </div>`;
  });
  html += '</div>';
  scenesDiv.innerHTML = html;
}

// ----- Step 3: 生成漫画 -----
document.getElementById('xhs-comic-btn').addEventListener('click', generateXhsComic);

async function generateXhsComic() {
  const btn = document.getElementById('xhs-comic-btn');
  const gallery = document.getElementById('xhs-comic-gallery');
  const status = document.getElementById('xhs-comic-status');

  const apiKey = document.getElementById('xhs-wanxiang-key').value.trim();

  if (!xhsScenes || xhsScenes.length < 2) {
    showToast('请先生成带货内容（至少2个场景）', 'error');
    return;
  }
  if (!apiKey) { showToast('请填写万相 API Key', 'error'); return; }

  btn.disabled = true;
  btn.innerHTML = '<span class="spinner"></span> 生成中...';
  status.textContent = '⏳ 正在生成漫画（经济模式，每次调用生成多格）...';
  gallery.innerHTML = '';

  try {
    const resp = await apiPost('/api/xhs/generate-comic', {
      scenes: xhsScenes,
      wanxiang: {
        api_key: apiKey,
        model: document.getElementById('xhs-model').value,
        api_url: document.getElementById('xhs-wanxiang-url').value.trim(),
        style_name: document.getElementById('xhs-style').value,
        comic_layout: document.getElementById('xhs-layout').value,
        size: document.getElementById('xhs-size').value,
        seed: parseInt(document.getElementById('xhs-seed').value) || -1,
        thinking_mode: document.getElementById('xhs-thinking').checked,
        batch_size: document.getElementById('xhs-economy').checked ? 2 : 1,
        ref_image: xhsRefImage,
      },
    });

    if (resp.success && resp.images && resp.images.length > 0) {
      xhsComicImages = resp.images;
      let html = '<div class="gallery-grid">';
      resp.images.forEach((img, i) => {
        const title = (resp.titles && resp.titles[i]) || `场景 ${i + 1}`;
        html += `<div class="gallery-item">
          <img src="${img}" alt="${title}">
          <div class="caption">${escapeHtml(title)}</div>
        </div>`;
      });
      html += '</div>';
      gallery.innerHTML = html;
      status.innerHTML = `<span style="color:var(--success)">✅ ${resp.message}</span>`;
      if (resp.api_calls) {
        status.innerHTML += `<br><small style="color:var(--text-secondary)">API调用 ${resp.api_calls} 次</small>`;
      }
      showToast('漫画生成成功！', 'success');
      document.getElementById('xhs-step4').scrollIntoView({ behavior: 'smooth' });
    } else {
      gallery.innerHTML = `<div class="alert alert-error">❌ ${resp.message || '生成失败'}</div>`;
      status.textContent = '';
    }
  } catch (e) {
    gallery.innerHTML = `<div class="alert alert-error">❌ ${e.message}</div>`;
    status.textContent = '';
  }

  btn.disabled = false;
  btn.innerHTML = '🎨 生成漫画';
  updateProjectStatus();
}

// ----- Step 4: 发布到小红书 -----
document.getElementById('xhs-publish-btn').addEventListener('click', publishToXhs);

async function publishToXhs() {
  const btn = document.getElementById('xhs-publish-btn');
  const status = document.getElementById('xhs-publish-result');

  if (!xhsComicImages || xhsComicImages.length === 0) {
    showToast('请先生成漫画', 'error');
    return;
  }

  btn.disabled = true;
  btn.innerHTML = '<span class="spinner"></span> 发布中...';

  const setStatus = (msg, type = 'info') => {
    const icons = { info: '⏳', success: '✅', error: '❌', warning: '⚠️' };
    status.innerHTML = `<div class="alert alert-${type}">${icons[type] || '⏳'} ${msg}</div>`;
  };

  setStatus('正在发布到小红书...', 'info');

  try {
    const resp = await apiPost('/api/xhs/publish', {
      title: xhsGeneratedContent?.title || '',
      content: xhsGeneratedContent?.content || '',
      images: xhsComicImages,
      tags: xhsGeneratedContent?.tags || [],
    });

    if (resp.success) {
      setStatus(resp.message + (resp.note ? `<br><small>${resp.note}</small>` : ''), 'success');
      showToast('发布成功！', 'success');
    } else if (resp.need_login) {
      setStatus(resp.message + '<br><small>请先点击「登录小红书」按钮扫码登录</small>', 'warning');
      document.getElementById('xhs-login-btn').style.display = '';
      showToast('需要先登录小红书', 'warning');
    } else {
      setStatus(resp.message, 'error');
      showToast(resp.message, 'error');
    }
  } catch (e) {
    setStatus(e.message, 'error');
    showToast(e.message, 'error');
  }

  btn.disabled = false;
  btn.innerHTML = '📤 发布到小红书';
}

// ----- 一键复制 -----
document.getElementById('xhs-copy-btn').addEventListener('click', async () => {
  if (!xhsGeneratedContent) {
    showToast('请先生成带货内容', 'error');
    return;
  }
  let text = '';
  if (xhsGeneratedContent.title) text += xhsGeneratedContent.title + '\n\n';
  if (xhsGeneratedContent.content) text += xhsGeneratedContent.content + '\n';
  if (xhsGeneratedContent.tags) text += '\n' + xhsGeneratedContent.tags.join(' ');

  try {
    await navigator.clipboard.writeText(text);
    showToast('文案已复制到剪贴板', 'success');
  } catch {
    showToast('复制失败，请手动复制', 'error');
  }
});

// ----- 项目保存/导入 -----

function updateProjectStatus() {
  const el = document.getElementById('xhs-project-status');
  const saveBtn = document.getElementById('xhs-save-btn');
  const hasData = xhsProductInfo || xhsGeneratedContent || xhsComicImages.length > 0;
  saveBtn.disabled = !hasData;

  if (xhsProductInfo && xhsGeneratedContent && xhsComicImages.length > 0) {
    el.innerHTML = '✅ 完整项目（分析+内容+漫画）';
  } else if (xhsProductInfo && xhsGeneratedContent) {
    el.innerHTML = '📝 进行中（已生成内容）';
  } else if (xhsProductInfo) {
    el.innerHTML = '🔍 进行中（已分析商品）';
  } else {
    el.innerHTML = '暂无项目';
  }
}

// 保存项目
document.getElementById('xhs-save-btn').addEventListener('click', () => {
  const state = {
    version: 2,
    timestamp: Date.now(),
    productInfo: xhsProductInfo,
    generatedContent: xhsGeneratedContent,
    scenes: xhsScenes,
    comicImages: xhsComicImages,
    refImage: xhsRefImage,
    productImage: xhsProductImage,
    inputMode: xhsInputMode,
  };

  // 生成文件名（用商品名或时间）
  const name = xhsProductInfo?.name || '小红书项目';
  const safe = name.replace(/[\\/:*?"<>|]/g, '_').substring(0, 20);
  const date = new Date().toISOString().slice(0, 10);

  const blob = new Blob([JSON.stringify(state, null, 2)], { type: 'application/json' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `${safe}_${date}.xhs.json`;
  a.click();
  URL.revokeObjectURL(url);
  showToast(`项目已保存：${safe}`, 'success');
});

// 导入项目
document.getElementById('xhs-load-btn').addEventListener('click', () => {
  document.getElementById('xhs-load-input').click();
});

document.getElementById('xhs-load-input').addEventListener('change', (e) => {
  const file = e.target.files[0];
  if (!file) return;

  const reader = new FileReader();
  reader.onload = (ev) => {
    try {
      const state = JSON.parse(ev.target.result);

      // 恢复状态
      xhsProductInfo = state.productInfo || null;
      xhsGeneratedContent = state.generatedContent || null;
      xhsScenes = state.scenes || [];
      xhsComicImages = state.comicImages || [];
      xhsRefImage = state.refImage || null;
      xhsProductImage = state.productImage || null;

      // 恢复预览图
      if (xhsProductImage) {
        document.getElementById('xhs-preview').src = xhsProductImage;
        document.getElementById('xhs-preview').classList.add('show');
        document.getElementById('xhs-dropzone').querySelector('div').textContent = '已导入';
      }
      if (xhsRefImage) {
        document.getElementById('xhs-ref-preview').src = xhsRefImage;
        document.getElementById('xhs-ref-preview').classList.add('show');
        document.getElementById('xhs-ref-dropzone').querySelector('div').textContent = '已导入';
      }

      // 恢复分析结果显示
      const productResult = document.getElementById('xhs-product-result');
      if (xhsProductInfo) {
        const p = xhsProductInfo;
        let html = `<div class="alert alert-success">✅ 已导入商品：${escapeHtml(p.name || '')}</div>`;
        html += `<div style="background:var(--bg-card);padding:16px;border-radius:8px">`;
        html += `<div style="font-size:1.2rem;font-weight:700;margin-bottom:8px">🛍️ ${escapeHtml(p.name || '未知商品')}</div>`;
        if (p.features?.length) {
          html += `<div style="margin:8px 0"><strong>卖点：</strong>`;
          p.features.forEach(f => { html += `<span class="tag tag-accent">${escapeHtml(f)}</span>`; });
          html += `</div>`;
        }
        if (p.colors?.length) {
          html += `<div style="margin:8px 0"><strong>配色：</strong>`;
          p.colors.forEach(c => { html += `<span class="tag">${escapeHtml(c)}</span>`; });
          html += `</div>`;
        }
        html += `</div>`;
        productResult.innerHTML = html;
      }

      // 恢复内容显示
      if (xhsGeneratedContent) {
        const gc = xhsGeneratedContent;
        let html = `<div class="alert alert-success">✅ 已导入内容：${escapeHtml(gc.title || '')}</div>`;
        if (gc.content) {
          html += `<div style="background:var(--bg-card);padding:16px;border-radius:8px;margin-bottom:12px">`;
          html += `<div style="white-space:pre-wrap;line-height:1.6">${escapeHtml(gc.content)}</div></div>`;
        }
        if (gc.tags?.length) {
          html += `<div style="margin-bottom:12px">`;
          gc.tags.forEach(t => { html += `<span class="tag tag-accent">${escapeHtml(t)}</span>`; });
          html += `</div>`;
        }
        document.getElementById('xhs-content-result').innerHTML = html;
      }

      // 恢复场景显示
      if (xhsScenes.length > 0) {
        refreshXhsScenesDisplay();
      }

      // 恢复漫画
      if (xhsComicImages.length > 0) {
        let html = '<div class="gallery-grid">';
        xhsComicImages.forEach((img, i) => {
          const title = (xhsGeneratedContent?.titles?.[i]) || (xhsScenes[i]?.title) || `图 ${i+1}`;
          html += `<div class="gallery-item"><img src="${img}" alt="${title}"><div class="caption">${escapeHtml(title)}</div></div>`;
        });
        html += '</div>';
        document.getElementById('xhs-comic-gallery').innerHTML = html;
        document.getElementById('xhs-comic-status').innerHTML = '<span style="color:var(--success)">✅ 已导入漫画</span>';
      }

      updateProjectStatus();
      showToast(`项目已导入：${state.productInfo?.name || '小红书项目'}`, 'success');
    } catch (err) {
      showToast('导入失败：文件格式错误', 'error');
    }
  };
  reader.readAsText(file);

  // 重置 input 以便重复导入同一文件
  e.target.value = '';
});

// 初始化项目状态
updateProjectStatus();

} catch (e) {
  console.error('[xhs.js] 事件注册出错:', e);
  // 部分按钮可能无法使用，但不影响其他功能
}
