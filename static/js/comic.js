/* =========================================================
   StoryDiffusion - 漫画生成 Tab
   ========================================================= */

// ----- 初始化下拉菜单 -----
async function initComicOptions() {
  try {
    const [styles, layouts, models] = await Promise.all([
      apiGet('/api/comic/styles'),
      apiGet('/api/comic/layouts'),
      apiGet('/api/comic/models'),
    ]);

    const styleSelect = document.getElementById('comic-style');
    (styles.styles || []).forEach(s => {
      const opt = document.createElement('option');
      opt.value = s; opt.textContent = s;
      if (s === 'Japanese Anime') opt.selected = true;
      styleSelect.appendChild(opt);
    });

    const layoutSelect = document.getElementById('comic-layout');
    (layouts.layouts || []).forEach(l => {
      const opt = document.createElement('option');
      opt.value = l; opt.textContent = l;
      layoutSelect.appendChild(opt);
    });

    const modelSelect = document.getElementById('comic-model');
    (models.models || []).forEach(m => {
      const opt = document.createElement('option');
      opt.value = m; opt.textContent = m;
      if (m === 'wan2.7-image-pro') opt.selected = true;
      modelSelect.appendChild(opt);
    });
  } catch (e) {
    console.error('初始化漫画选项失败:', e);
  }
}
initComicOptions();

// ----- 参考图上传 -----
const dropzone = document.getElementById('comic-dropzone');
const refInput = document.getElementById('comic-ref-input');
const preview = document.getElementById('comic-preview');
let comicRefBase64 = null;

dropzone.addEventListener('click', () => refInput.click());

dropzone.addEventListener('dragover', (e) => {
  e.preventDefault();
  dropzone.classList.add('dragover');
});

dropzone.addEventListener('dragleave', () => {
  dropzone.classList.remove('dragover');
});

dropzone.addEventListener('drop', (e) => {
  e.preventDefault();
  dropzone.classList.remove('dragover');
  if (e.dataTransfer.files.length > 0) {
    handleRefFile(e.dataTransfer.files[0]);
  }
});

refInput.addEventListener('change', () => {
  if (refInput.files.length > 0) {
    handleRefFile(refInput.files[0]);
  }
});

async function handleRefFile(file) {
  if (!file.type.startsWith('image/')) {
    showToast('请上传图片文件', 'error');
    return;
  }
  try {
    comicRefBase64 = await fileToBase64(file);
    preview.src = comicRefBase64;
    preview.classList.add('show');
    dropzone.querySelector('div').textContent = file.name;
  } catch (e) {
    showToast('图片读取失败', 'error');
  }
}

// ----- 测试连接 -----
document.getElementById('comic-test-btn').addEventListener('click', async () => {
  const apiKey = document.getElementById('comic-api-key').value.trim();
  const model = document.getElementById('comic-model').value;
  const apiUrl = document.getElementById('comic-api-url').value.trim();
  const resultEl = document.getElementById('comic-test-result');

  if (!apiKey) {
    resultEl.textContent = '❌ 请填写 API Key';
    return;
  }

  resultEl.textContent = '⏳ 测试中...';
  try {
    const resp = await apiPost('/api/comic/test', { api_key: apiKey, model, api_url: apiUrl });
    resultEl.textContent = resp.success ? '✅ 连接成功' : `❌ ${resp.message}`;
    resultEl.style.color = resp.success ? 'var(--success)' : 'var(--danger)';
  } catch (e) {
    resultEl.textContent = `❌ ${e.message}`;
    resultEl.style.color = 'var(--danger)';
  }
});

// ----- 生成漫画 -----
document.getElementById('comic-start-btn').addEventListener('click', generateComic);

async function generateComic() {
  const btn = document.getElementById('comic-start-btn');
  const gallery = document.getElementById('comic-gallery');
  const status = document.getElementById('comic-status');

  const apiKey = document.getElementById('comic-api-key').value.trim();
  const model = document.getElementById('comic-model').value;
  const apiUrl = document.getElementById('comic-api-url').value.trim();
  const style = document.getElementById('comic-style').value;
  const layout = document.getElementById('comic-layout').value;
  const size = document.getElementById('comic-size').value;
  const seed = parseInt(document.getElementById('comic-seed').value) || -1;
  const thinking = document.getElementById('comic-thinking').checked;
  const economy = document.getElementById('comic-economy')?.checked;
  const batchSize = economy ? 3 : 1;
  const promptsText = document.getElementById('comic-prompts').value.trim();

  const prompts = promptsText.split('\n').map(p => p.trim()).filter(p => p);

  if (!apiKey) { showToast('请填写 API Key', 'error'); return; }
  if (prompts.length < 2) { showToast('至少需要 2 个分镜描述', 'error'); return; }

  btn.disabled = true;
  btn.innerHTML = '<span class="spinner"></span> 生成中...';
  status.textContent = '⏳ 正在生成漫画...';
  gallery.innerHTML = '';

  try {
    const resp = await apiPost('/api/comic/generate', {
      api_key: apiKey,
      model,
      api_url: apiUrl,
      style_name: style,
      comic_layout: layout,
      size,
      seed,
      thinking_mode: thinking,
      batch_size: batchSize,
      prompts,
      ref_image: comicRefBase64,
    });

    if (resp.success && resp.images && resp.images.length > 0) {
      let html = '<div class="gallery-grid">';
      resp.images.forEach((img, i) => {
        const caption = prompts[i] || `图 ${i + 1}`;
        html += `<div class="gallery-item">
          <img src="${img}" alt="${caption}">
          <div class="caption">${escapeHtml(caption.substring(0, 60))}</div>
        </div>`;
      });
      html += '</div>';
      gallery.innerHTML = html;
      status.innerHTML = `<span style="color:var(--success)">✅ ${resp.message} | Seed: ${resp.seed || seed}</span>`;
      if (resp.api_calls) {
        status.innerHTML += `<br><small style="color:var(--text-secondary)">API调用 ${resp.api_calls} 次，省 ${resp.panels - resp.api_calls} 次</small>`;
      }
      showToast(`漫画生成成功！共 ${resp.images.length} 格`, 'success');
    } else {
      gallery.innerHTML = `<div class="alert alert-error">❌ ${resp.message || '生成失败'}</div>`;
      status.textContent = '';
      showToast(resp.message || '生成失败', 'error');
    }
  } catch (e) {
    gallery.innerHTML = `<div class="alert alert-error">❌ ${e.message}</div>`;
    status.textContent = '';
    showToast(`生成失败: ${e.message}`, 'error');
  }

  btn.disabled = false;
  btn.innerHTML = '🎨 生成漫画';
}
