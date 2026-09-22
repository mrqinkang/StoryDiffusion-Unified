/* =========================================================
   StoryDiffusion - 流水线 Tab (小说→漫画)
   ========================================================= */

let extractedScenes = [];

// ----- 同步漫画选项 -----
async function initPipeOptions() {
  try {
    const [styles, layouts] = await Promise.all([
      apiGet('/api/comic/styles'),
      apiGet('/api/comic/layouts'),
    ]);

    const styleSelect = document.getElementById('pipe-style');
    (styles.styles || []).forEach(s => {
      const opt = document.createElement('option');
      opt.value = s; opt.textContent = s;
      if (s === 'Japanese Anime') opt.selected = true;
      styleSelect.appendChild(opt);
    });

    const layoutSelect = document.getElementById('pipe-layout');
    (layouts.layouts || []).forEach(l => {
      const opt = document.createElement('option');
      opt.value = l; opt.textContent = l;
      layoutSelect.appendChild(opt);
    });
  } catch (e) {
    console.error('初始化流水线选项失败:', e);
  }
}
initPipeOptions();

// ----- 加载已有小说 -----
document.getElementById('pipe-load-novel').addEventListener('click', async () => {
  try {
    const resp = await apiGet('/api/novel/list');
    if (!resp.success || !resp.novels || resp.novels.length === 0) {
      showToast('没有已保存的小说', 'info');
      return;
    }

    // 弹出一个简易选择器
    const choices = resp.novels.map(n =>
      `${n.name} (${n.chapter_count}章)`
    );
    const choice = prompt(
      `可选小说:\n${choices.map((c, i) => `${i + 1}. ${c}`).join('\n')}\n\n输入编号加载:`,
      '1'
    );
    if (!choice) return;

    const idx = parseInt(choice) - 1;
    if (idx < 0 || idx >= resp.novels.length) {
      showToast('无效选择', 'error');
      return;
    }

    const novel = resp.novels[idx];
    const loadResp = await apiPost('/api/novel/load', { path: novel.path });

    if (loadResp.success && loadResp.data) {
      // 将所有章节合并到文本框
      const chapters = loadResp.data.chapters || [];
      let fullText = '';
      // 优先使用架构文本
      if (loadResp.data.architecture) {
        fullText += loadResp.data.architecture + '\n\n';
      }
      if (loadResp.data.directory) {
        fullText += loadResp.data.directory + '\n\n';
      }
      chapters.forEach((ch, i) => {
        fullText += `第 ${i + 1} 章\n${ch.content}\n\n`;
      });

      document.getElementById('pipe-novel-text').value = fullText.trim();
      showToast(`已加载: ${novel.name}`, 'success');
    }
  } catch (e) {
    showToast(`加载失败: ${e.message}`, 'error');
  }
});

// ----- 提取场景 -----
document.getElementById('pipe-extract-btn').addEventListener('click', extractScenes);

async function extractScenes() {
  const btn = document.getElementById('pipe-extract-btn');
  const status = document.getElementById('pipe-extract-status');
  const scenesDiv = document.getElementById('pipe-scenes');
  const novelText = document.getElementById('pipe-novel-text').value.trim();
  const llmKey = document.getElementById('pipe-llm-key').value.trim();
  const llmModel = document.getElementById('pipe-llm-model').value;

  if (!novelText) { showToast('请先输入或加载小说文本', 'error'); return; }
  if (!llmKey) { showToast('请填写 LLM API Key 用于场景提取', 'error'); return; }

  btn.disabled = true;
  btn.innerHTML = '<span class="spinner"></span> 提取中...';
  status.textContent = '⏳ AI 正在分析小说，提取关键场景...';
  scenesDiv.innerHTML = '';

  // 更新步骤指示器
  updateStep(2, 'active');

  try {
    const resp = await apiPost('/api/pipeline/extract', {
      chapter_text: novelText.substring(0, 8000),
      llm_api_key: llmKey,
      llm_model: llmModel,
      llm_interface: document.getElementById('pipe-llm-interface').value,
      max_scenes: 6,
    });

    if (resp.success && resp.scenes && resp.scenes.length > 0) {
      extractedScenes = resp.scenes;
      let html = `<div class="alert alert-success">✅ ${resp.message}</div>`;
      html += '<div class="gallery-grid">';
      resp.scenes.forEach((s, i) => {
        html += `<div class="gallery-item" style="padding:12px">
          <div style="font-weight:700;color:var(--accent-2);margin-bottom:4px">
            🎬 ${i + 1}. ${escapeHtml(s.title || `场景 ${i + 1}`)}
          </div>
          <div style="font-size:0.85rem;color:var(--text-secondary);margin-bottom:4px">
            ${escapeHtml(s.description || '')}
          </div>
          <div style="font-size:0.75rem;color:var(--text-muted);background:rgba(0,0,0,0.3);padding:6px;border-radius:4px;word-break:break-all">
            <em>prompt:</em> ${escapeHtml(s.prompt || '')}
          </div>
          <div style="margin-top:6px">
            <button class="btn btn-sm btn-secondary" onclick="editScene(${i})">✏️ 编辑</button>
          </div>
        </div>`;
      });
      html += '</div>';
      scenesDiv.innerHTML = html;
      status.innerHTML = `<span style="color:var(--success)">✅ 提取完成，${resp.scenes.length} 个场景</span>`;

      // 更新步骤
      updateStep(2, 'done');
      updateStep(3, 'active');

      showToast(`成功提取 ${resp.scenes.length} 个场景`, 'success');
    } else {
      scenesDiv.innerHTML = `<div class="alert alert-error">❌ ${resp.message || '提取失败'}</div>`;
      status.textContent = '';
      showToast(resp.message || '提取失败', 'error');
    }
  } catch (e) {
    scenesDiv.innerHTML = `<div class="alert alert-error">❌ ${e.message}</div>`;
    status.textContent = '';
    showToast(`提取失败: ${e.message}`, 'error');
  }

  btn.disabled = false;
  btn.innerHTML = '🔍 提取场景';
}

// ----- 编辑场景 (原地替换) -----
function editScene(index) {
  const scene = extractedScenes[index];
  if (!scene) return;

  const newTitle = prompt('场景标题:', scene.title || '');
  if (newTitle === null) return;
  const newDesc = prompt('场景描述:', scene.description || '');
  if (newDesc === null) return;
  const newPrompt = prompt('AI 绘图 Prompt (英文):', scene.prompt || '');
  if (newPrompt === null) return;

  extractedScenes[index] = {
    title: newTitle,
    description: newDesc,
    prompt: newPrompt,
  };

  showToast('场景已更新', 'success');
  // 刷新显示
  refreshScenesDisplay();
}

function refreshScenesDisplay() {
  const scenesDiv = document.getElementById('pipe-scenes');
  let html = `<div class="alert alert-success">✅ 已编辑 ${extractedScenes.length} 个场景</div>`;
  html += '<div class="gallery-grid">';
  extractedScenes.forEach((s, i) => {
    html += `<div class="gallery-item" style="padding:12px">
      <div style="font-weight:700;color:var(--accent-2);margin-bottom:4px">
        🎬 ${i + 1}. ${escapeHtml(s.title || `场景 ${i + 1}`)}
      </div>
      <div style="font-size:0.85rem;color:var(--text-secondary);margin-bottom:4px">
        ${escapeHtml(s.description || '')}
      </div>
      <div style="font-size:0.75rem;color:var(--text-muted);background:rgba(0,0,0,0.3);padding:6px;border-radius:4px;word-break:break-all">
        <em>prompt:</em> ${escapeHtml(s.prompt || '')}
      </div>
      <div style="margin-top:6px">
        <button class="btn btn-sm btn-secondary" onclick="editScene(${i})">✏️ 编辑</button>
      </div>
    </div>`;
  });
  html += '</div>';
  scenesDiv.innerHTML = html;
}

// ----- 从场景生成漫画 -----
document.getElementById('pipe-generate-btn').addEventListener('click', generateFromScenes);

async function generateFromScenes() {
  const btn = document.getElementById('pipe-generate-btn');
  const gallery = document.getElementById('pipe-gallery');
  const status = document.getElementById('pipe-status');

  if (!extractedScenes || extractedScenes.length < 2) {
    showToast('请先提取至少 2 个场景', 'error');
    return;
  }

  const wanxiangKey = document.getElementById('pipe-wanxiang-key').value.trim();
  if (!wanxiangKey) { showToast('请填写万相 API Key', 'error'); return; }

  btn.disabled = true;
  btn.innerHTML = '<span class="spinner"></span> 生成中...';
  status.textContent = '⏳ 正在生成漫画...';
  gallery.innerHTML = '';

  try {
    const resp = await apiPost('/api/pipeline/generate', {
      scenes: extractedScenes,
      api_key: wanxiangKey,
      style_name: document.getElementById('pipe-style').value,
      comic_layout: document.getElementById('pipe-layout').value,
    });

    if (resp.success && resp.images && resp.images.length > 0) {
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
      updateStep(3, 'done');
      showToast('漫画生成成功！', 'success');
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
  btn.innerHTML = '🚀 从场景生成漫画';
}

// ----- 步骤指示器 -----
function updateStep(step, state) {
  document.querySelectorAll('#pipeline-steps .step').forEach(el => {
    const num = parseInt(el.dataset.step);
    el.classList.remove('active', 'done');
    if (num < step) el.classList.add('done');
    else if (num === step) el.classList.add(state || 'active');
  });
}
