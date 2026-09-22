/* =========================================================
   小说 Tab - 流式生成、模板、草稿箱
   ========================================================= */

document.addEventListener('DOMContentLoaded', function () {

  // ---- DOM 引用 ----
  const $ = id => document.getElementById(id);
  const startBtn = $('novel-start-btn');
  const statusEl = $('novel-status');
  const progressEl = $('novel-progress');
  const progressFill = $('novel-progress-fill');
  const progressText = $('novel-progress-text');
  const resultPanel = $('novel-result');
  const streamContent = $('novel-stream-content');
  const resultTitle = $('novel-result-title');
  const copyBtn = $('novel-copy-btn');
  const saveBtn = $('novel-save-btn');

  // ---- 状态 ----
  window.currentChapters = [];   // [{chapter, content}], synced for drafts tab
  // 本地引用指向同一数组，方便续写/保存等功能跨 tab 共享
  const currentChapters = window.currentChapters;
  let currentTaskId = '';
  let eventSource = null;
  let isGenerating = false;

  // =============================================================
  //  模板按钮
  // =============================================================
  document.querySelectorAll('.btn-template').forEach(btn => {
    btn.addEventListener('click', async function () {
      const name = this.dataset.template;
      try {
        const resp = await fetch('/api/novel/templates');
        const data = await resp.json();
        const tmpl = data.templates?.[name];
        if (!tmpl) { showToast('模板加载失败', 'error'); return; }

        applyTemplateParams(tmpl);
        showToast(`✅ 已加载「${name}」模板`, 'success');
      } catch (e) {
        showToast('模板加载失败: ' + e.message, 'error');
      }
    });
  });

  // ---- 保存/更新自定义模板 ----
  const saveTemplateBtn = $('save-template-btn');

  // 监听编辑模式事件（来自草稿箱）
  document.addEventListener('template-edit-mode', function (e) {
    saveTemplateBtn.textContent = '💾 更新模板';
  });

  // 点击其他按钮/切换 Tab 时清除编辑模式
  document.querySelectorAll('.tab-btn, .btn-template, .btn-guided').forEach(el => {
    el.addEventListener('click', clearEditMode);
  });
  function clearEditMode() {
    if (window._editingTemplateId) {
      delete window._editingTemplateId;
      delete window._editingTemplateName;
      saveTemplateBtn.textContent = '💾 保存为模板';
    }
  }

  saveTemplateBtn.addEventListener('click', async function () {
    const isEdit = !!window._editingTemplateId;
    const defaultName = isEdit ? window._editingTemplateName : '我的模板';
    const name = prompt(isEdit ? '请输入新名称（留空不修改）：' : '请输入模板名称：', defaultName);
    if (name === null) return; // 取消
    const finalName = name.trim() || defaultName;
    const params = collectTemplateParams();
    if (!params.topic) { showToast('请至少填写小说主题', 'error'); return; }
    try {
      const url = isEdit ? '/api/novel/templates/custom/update' : '/api/novel/templates/custom/save';
      const body = isEdit
        ? JSON.stringify({ template_id: window._editingTemplateId, name: finalName, params })
        : JSON.stringify({ name: finalName, params });
      const resp = await fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body,
      });
      const text = await resp.text();
      if (!resp.ok) {
        throw new Error('HTTP ' + resp.status + ': ' + text.slice(0, 150));
      }
      let data;
      try { data = JSON.parse(text); } catch (_) {
        throw new Error('响应不是合法JSON, 原始内容: ' + text.slice(0, 150));
      }
      if (!data.success) throw new Error(data.detail || '保存失败');
      showToast(isEdit ? `✅ 模板「${finalName}」已更新` : `✅ 模板「${finalName}」已保存`, 'success');
      clearEditMode();
      loadCustomTemplates();
    } catch (e) {
      showToast('保存失败: ' + e.message, 'error');
    }
  });

  // ---- 加载自定义模板按钮 ----
  async function loadCustomTemplates() {
    const bar = document.getElementById('custom-templates-bar');
    if (!bar) return;
    try {
      const resp = await fetch('/api/novel/templates/custom');
      const data = await resp.json();
      const templates = data.templates || [];
      if (templates.length === 0) { bar.innerHTML = ''; return; }
      bar.innerHTML = `<span class="template-label" style="font-size:0.82rem">📂 我的模板：</span>` +
        templates.map(t => `<button class="btn btn-template custom-tpl" data-id="${escapeAttr(t.id)}" title="${escapeAttr(t.name)}">${escapeHtml(t.name)}</button>`).join('');
      bar.querySelectorAll('.custom-tpl').forEach(btn => {
        btn.addEventListener('click', async function () {
          const tid = this.dataset.id;
          try {
            // 从列表数据中查找（列表已返回 params）
            const tpl = templates.find(t => t.id === tid);
            if (tpl && tpl.params) {
              applyTemplateParams(tpl.params);
              // 切换到小说 Tab
              document.querySelector('.tab-btn[data-tab="novel"]')?.click();
              showToast(`✅ 已加载模板「${tpl.name}」`, 'success');
            }
          } catch (e) {
            showToast('加载模板失败', 'error');
          }
        });
      });
    } catch (_) { bar.innerHTML = ''; }
  }

  // ---- 收集当前表单参数（用于保存模板） ----
  function collectTemplateParams() {
    return {
      topic: $('novel-topic').value.trim(),
      genre: $('novel-genre').value.trim(),
      characters_involved: $('novel-characters').value.trim(),
      key_items: $('novel-items').value.trim(),
      scene_location: $('novel-location').value.trim(),
      time_constraint: $('novel-time').value.trim(),
      user_guidance: $('novel-guidance').value.trim(),
      language_style: $('novel-lang-style').value,
      emotional_tone: $('novel-emotion').value,
      content_taboos: $('novel-taboos').value.trim(),
      word_number: parseInt($('novel-wordcount').value) || 2000,
      num_chapters: parseInt($('novel-chapters').value) || 5,
      llm_interface: $('novel-llm-interface').value,
      llm_model: $('novel-llm-model').value.trim() || 'deepseek-v4-flash',
      llm_temperature: parseFloat($('novel-temperature').value) || 0.7,
      llm_max_tokens: parseInt($('novel-max-tokens').value) || 8192,
      embedding_interface: $('novel-emb-interface').value,
      embedding_model: $('novel-emb-model').value.trim() || 'bge-m3',
    };
  }

  // ---- 将模板参数填入表单 ----
  function applyTemplateParams(p) {
    const set = (id, val) => { const el = $(id); if (el && val !== undefined) el.value = val; };
    set('novel-topic', p.topic);
    set('novel-genre', p.genre);
    set('novel-characters', p.characters_involved);
    set('novel-items', p.key_items);
    set('novel-location', p.scene_location);
    set('novel-time', p.time_constraint);
    set('novel-guidance', p.user_guidance);
    set('novel-lang-style', p.language_style);
    set('novel-emotion', p.emotional_tone);
    set('novel-taboos', p.content_taboos);
    set('novel-wordcount', p.word_number);
    set('novel-chapters', p.num_chapters);
    set('novel-llm-interface', p.llm_interface);
    set('novel-llm-model', p.llm_model);
    set('novel-temperature', p.llm_temperature);
    set('novel-max-tokens', p.llm_max_tokens);
    set('novel-emb-interface', p.embedding_interface);
    set('novel-emb-model', p.embedding_model);
  }

  // ---- 加载自定义模板 ----
  loadCustomTemplates();

  // =============================================================
  //  收集参数
  // =============================================================
  function collectParams() {
    return {
      topic: $('novel-topic').value.trim(),
      genre: $('novel-genre').value.trim(),
      num_chapters: parseInt($('novel-chapters').value) || 5,
      word_number: parseInt($('novel-wordcount').value) || 2000,
      user_guidance: $('novel-guidance').value.trim(),
      characters_involved: $('novel-characters').value.trim(),
      key_items: $('novel-items').value.trim(),
      scene_location: $('novel-location').value.trim(),
      time_constraint: $('novel-time').value.trim(),
      language_style: $('novel-lang-style').value,
      emotional_tone: $('novel-emotion').value,
      content_taboos: $('novel-taboos').value.trim(),
      llm_interface: $('novel-llm-interface').value,
      llm_api_key: $('novel-llm-key').value.trim(),
      llm_base_url: $('novel-llm-url').value.trim(),
      llm_model: $('novel-llm-model').value.trim() || 'deepseek-v4-flash',
      llm_temperature: parseFloat($('novel-temperature').value) || 0.7,
      llm_max_tokens: parseInt($('novel-max-tokens').value) || 8192,
      llm_timeout: 600,
      embedding_interface: $('novel-emb-interface').value,
      embedding_api_key: $('novel-emb-key').value.trim(),
      embedding_base_url: $('novel-emb-url').value.trim(),
      embedding_model: $('novel-emb-model').value.trim() || 'bge-m3',
    };
  }

  // =============================================================
  //  流式生成（核心）
  // =============================================================
  async function startStreamingGeneration() {
    const params = collectParams();

    // 验证
    if (!params.llm_api_key) { showToast('请填写 LLM API Key', 'error'); return; }
    if (!params.topic) { showToast('请填写小说主题', 'error'); return; }

    // 重置状态
    if (eventSource) { eventSource.close(); eventSource = null; }
    currentChapters.length = 0;
    currentTaskId = '';
    isGenerating = true;
    startBtn.disabled = true;
    resultPanel.style.display = 'none';
    streamContent.innerHTML = '';
    progressEl.style.display = 'block';
    progressFill.style.width = '0%';
    progressText.textContent = '初始化...';
    statusEl.textContent = '';

    try {
      // 发起流式生成请求
      const resp = await fetch('/api/novel/generate-stream', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(params),
      });
      if (!resp.ok) {
        const err = await resp.json();
        showToast(err.detail || '启动失败', 'error');
        isGenerating = false;
        startBtn.disabled = false;
        return;
      }

      const reader = resp.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';

      // 逐步读取 SSE 流
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';

        for (const line of lines) {
          if (!line.startsWith('data: ')) continue;
          const jsonStr = line.slice(6).trim();
          if (!jsonStr) continue;

          try {
            const msg = JSON.parse(jsonStr);
            handleStreamMessage(msg);
          } catch (e) {
            console.warn('SSE parse error:', e);
          }
        }
      }

      // 处理 buffer 剩余
      if (buffer.startsWith('data: ')) {
        try {
          const msg = JSON.parse(buffer.slice(6).trim());
          handleStreamMessage(msg);
        } catch (e) { /* ignore */ }
      }

    } catch (e) {
      showToast('生成失败: ' + e.message, 'error');
    } finally {
      isGenerating = false;
      startBtn.disabled = false;
      progressEl.style.display = 'none';
    }
  }

  // ---- 处理流式消息 ----
  function handleStreamMessage(msg) {
    const type = msg.type;

    // 任何消息都可能携带 filepath，尽早记录
    if (msg.filepath) currentNovelPath = msg.filepath;

    switch (type) {
      case 'progress':
        progressFill.style.width = (msg.progress_pct || 0) + '%';
        progressText.textContent = msg.progress_msg || '';
        break;

      case 'architecture':
        resultPanel.style.display = 'block';
        resultTitle.textContent = '📖 小说大纲已生成';
        break;

      case 'chapter_start':
        resultTitle.textContent = `📖 正在生成第 ${msg.chapter}/${msg.total} 章...`;
        break;

      case 'chapter_content':
        // 保存章节
        currentChapters.push({
          chapter: msg.chapter,
          content: msg.content || '',
        });
        // 追加显示
        appendChapter(msg.chapter, msg.content);
        statusEl.textContent = `✅ 第 ${msg.chapter} 章完成`;
        break;

      case 'done':
        resultTitle.textContent = `🎉 生成完成！共 ${msg.total_chapters} 章`;
        progressFill.style.width = '100%';
        progressText.textContent = '生成完成！';
        // 记录小说路径
        if (msg.filepath) window.currentNovelPath = msg.filepath;
        showToast(`✅ 小说生成完成，共 ${msg.total_chapters} 章`, 'success');
        break;

      case 'error':
        showToast('❌ ' + (msg.error || '生成出错'), 'error');
        break;
    }
  }

  // ---- 追加章节到页面 ----
  function appendChapter(chapterNum, content) {
    const section = document.createElement('div');
    section.className = 'stream-section collapsible-section';
    section.id = `ch-${chapterNum}`;

    const header = document.createElement('div');
    header.className = 'stream-chapter-title collapsible-header';
    header.onclick = () => {
      section.classList.toggle('collapsed');
      const arrow = header.querySelector('.collapse-arrow');
      if (arrow) arrow.textContent = section.classList.contains('collapsed') ? '▼' : '▲';
    };
    header.setAttribute('role', 'button');
    header.setAttribute('tabindex', '0');
    header.innerHTML = `<span>第 ${chapterNum} 章</span><span class="collapse-arrow">▲</span>`;

    const body = document.createElement('div');
    body.className = 'collapse-body';
    body.innerHTML = nl2br(content);

    section.appendChild(header);
    section.appendChild(body);
    streamContent.appendChild(section);

    // 滚动到最新
    setTimeout(() => {
      section.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }, 100);
  }

  // =============================================================
  //  非流式生成（传统单次请求 → 轮询）
  // =============================================================
  async function startPollingGeneration() {
    const params = collectParams();

    if (!params.llm_api_key) { showToast('请填写 LLM API Key', 'error'); return; }
    if (!params.topic) { showToast('请填写小说主题', 'error'); return; }

    if (eventSource) { eventSource.close(); eventSource = null; }
    currentChapters.length = 0;
    isGenerating = true;
    startBtn.disabled = true;
    resultPanel.style.display = 'none';
    streamContent.innerHTML = '';
    progressEl.style.display = 'block';
    progressFill.style.width = '0%';
    progressText.textContent = '初始化...';
    statusEl.textContent = '';

    try {
      const resp = await fetch('/api/novel/generate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(params),
      });
      const data = await resp.json();
      if (!data.success) { showToast(data.detail || '启动失败', 'error'); return; }

      const taskId = data.task_id;
      currentTaskId = taskId;

      // 开始轮询进度
      pollProgress(taskId);

    } catch (e) {
      showToast('启动失败: ' + e.message, 'error');
      isGenerating = false;
      startBtn.disabled = false;
    }
  }

  function pollProgress(taskId) {
    const evtSource = new EventSource(`/api/novel/progress/${taskId}`);
    eventSource = evtSource;

    evtSource.onmessage = function (e) {
      try {
        const data = JSON.parse(e.data);
        progressFill.style.width = (data.progress_pct || 0) + '%';
        progressText.textContent = data.progress_msg || '';

        if (data.status === 'completed') {
          resultPanel.style.display = 'block';
          resultTitle.textContent = '🎉 生成完成！';
          showToast('✅ 小说生成完成', 'success');
          evtSource.close();
          eventSource = null;
          isGenerating = false;
          startBtn.disabled = false;
          progressEl.style.display = 'none';
          // 加载结果
          loadResult(taskId);
        } else if (data.status === 'error') {
          showToast('❌ ' + (data.error || '生成出错'), 'error');
          evtSource.close();
          eventSource = null;
          isGenerating = false;
          startBtn.disabled = false;
          progressEl.style.display = 'none';
        }
      } catch (err) {
        console.warn('SSE parse error:', err);
      }
    };

    evtSource.onerror = function () {
      // 如果连接关闭但不是完成状态，尝试重新连接（EventSource 会自动重连）
    };
  }

  async function loadResult(taskId) {
    try {
      const resp = await fetch(`/api/novel/result/${taskId}`);
      const data = await resp.json();
      if (data.success && data.data) {
        const result = data.data;
        currentChapters.length = 0;
        streamContent.innerHTML = '';

        if (result.architecture) {
          const sec = document.createElement('div');
          sec.className = 'stream-section collapsible-section collapsed';
          const archHeader = document.createElement('div');
          archHeader.className = 'stream-chapter-title collapsible-header';
          archHeader.onclick = () => {
            sec.classList.toggle('collapsed');
            archHeader.querySelector('.collapse-arrow').textContent = sec.classList.contains('collapsed') ? '▼' : '▲';
          };
          archHeader.setAttribute('role', 'button');
          archHeader.setAttribute('tabindex', '0');
          archHeader.innerHTML = '<span>📖 小说架构</span><span class="collapse-arrow">▼</span>';
          const archBody = document.createElement('div');
          archBody.className = 'collapse-body';
          archBody.innerHTML = nl2br(result.architecture);
          sec.appendChild(archHeader);
          sec.appendChild(archBody);
          streamContent.appendChild(sec);
        }

        (result.chapters || []).forEach((ch, i) => {
          const content = typeof ch === 'string' ? ch : (ch.content || '');
          currentChapters.push({ chapter: i + 1, content });
          appendChapter(i + 1, content);
        });
      }
    } catch (e) {
      console.error('加载结果失败:', e);
    }
  }

  // =============================================================
  //  开始生成按钮
  // =============================================================
  startBtn.addEventListener('click', function () {
    if (isGenerating) {
      // 停止生成（简单处理：关闭连接）
      if (eventSource) { eventSource.close(); eventSource = null; }
      isGenerating = false;
      startBtn.disabled = false;
      statusEl.textContent = '⏹ 已停止';
      showToast('已停止生成', 'info');
      return;
    }
    // 优先流式，若浏览器不支持 ReadableStream 则回退轮询
    if (typeof ReadableStream !== 'undefined' && typeof fetch !== 'undefined') {
      startStreamingGeneration();
    } else {
      startPollingGeneration();
    }
  });

  // =============================================================
  //  复制全文
  // =============================================================
  copyBtn.addEventListener('click', function () {
    const text = currentChapters
      .map(ch => `第 ${ch.chapter} 章\n\n${ch.content}`)
      .join('\n\n---\n\n');

    if (!text) { showToast('没有内容可复制', 'error'); return; }

    navigator.clipboard.writeText(text).then(() => {
      showToast('✅ 已复制全文到剪贴板', 'success');
    }).catch(() => {
      // fallback
      const ta = document.createElement('textarea');
      ta.value = text;
      document.body.appendChild(ta);
      ta.select();
      document.execCommand('copy');
      document.body.removeChild(ta);
      showToast('✅ 已复制全文到剪贴板', 'success');
    });
  });

  // =============================================================
  //  引导式创作（聊天弹窗）
  // =============================================================
  const guidedBtn = $('guided-chat-btn');
  const guidedModal = $('guided-modal');
  const guidedClose = $('guided-modal-close');
  const chatMessages = $('chat-messages');
  const chatInput = $('chat-input');
  const chatSend = $('chat-send-btn');
  const outlineArea = $('chat-outline-area');
  const outlinePreview = $('chat-outline-preview');
  const confirmBtn = $('chat-confirm-btn');
  const retryBtn = $('chat-retry-btn');

  let chatHistory = [];        // {role, content}
  let lastOutlineText = '';    // 最近一次生成的大纲原文
  let isChatWaiting = false;   // 是否在等待 AI 回复

  // 打开弹窗
  guidedBtn.addEventListener('click', function () {
    guidedModal.style.display = 'flex';
    // 如果已经有历史（由 restoreChat 设置），不重置
    if (chatHistory.length === 0) {
      lastOutlineText = '';
      outlineArea.style.display = 'none';
    }
    scrollChat();
  });

  // 保存对话
  $('chat-save-btn').addEventListener('click', async function () {
    if (chatHistory.length === 0) { showToast('没有可保存的对话', 'error'); return; }
    const name = prompt('请输入对话名称：', '新建构思 ' + new Date().toLocaleDateString());
    if (!name) return;
    try {
      const resp = await fetch('/api/novel/chat/save', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name, messages: chatHistory }),
      });
      const text = await resp.text();
      if (!resp.ok) {
        throw new Error('HTTP ' + resp.status + ': ' + text.slice(0, 150));
      }
      let data;
      try { data = JSON.parse(text); } catch (_) {
        throw new Error('响应不是合法JSON, 原始内容: ' + text.slice(0, 150));
      }
      if (!data.success) throw new Error(data.detail || '保存失败');
      showToast(`✅ 对话「${name}」已保存`, 'success');
    } catch (e) {
      showToast('保存失败: ' + e.message, 'error');
    }
  });

  // 加载历史对话（从对话框内）
  $('chat-load-btn').addEventListener('click', async function () {
    try {
      const resp = await fetch('/api/novel/chat/list');
      const text = await resp.text();
      if (!resp.ok) throw new Error('HTTP ' + resp.status + ': ' + text.slice(0, 150));
      let data;
      try { data = JSON.parse(text); } catch (_) {
        throw new Error('响应不是合法JSON: ' + text.slice(0, 150));
      }
      const chats = data.chats || [];
      if (chats.length === 0) { showToast('没有保存的对话记录', 'info'); return; }
      // 用简单的选择列表
      const list = chats.map((c, i) =>
        `${i + 1}. ${c.name} (${c.message_count || 0}条) [${(c.created_at || '').slice(0, 10)}]`
      ).join('\n');
      const idx = prompt(`选择要加载的对话（输入编号 1-${chats.length}）：\n\n${list}`);
      if (!idx) return;
      const n = parseInt(idx);
      if (isNaN(n) || n < 1 || n > chats.length) { showToast('无效编号', 'error'); return; }
      const chat = chats[n - 1];
      const loadResp = await fetch('/api/novel/chat/load', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ chat_id: chat.id }),
      });
      const loadText = await loadResp.text();
      if (!loadResp.ok) {
        throw new Error('HTTP ' + loadResp.status + ': ' + loadText.slice(0, 150));
      }
      let loadData;
      try { loadData = JSON.parse(loadText); } catch (_) {
        throw new Error('响应不是合法JSON, 原始内容: ' + loadText.slice(0, 150));
      }
      if (loadData.success && loadData.data) {
        restoreChat(loadData.data.messages || []);
        showToast(`✅ 已加载对话「${chat.name}」`, 'success');
      }
    } catch (e) {
      showToast('加载失败: ' + e.message, 'error');
    }
  });

  // 全局函数：从草稿箱恢复对话
  window.restoreChat = function (messages) {
    chatHistory = messages.slice(); // 复制
    // 清空并重新渲染
    chatMessages.innerHTML = '';
    outlineArea.style.display = 'none';
    chatHistory.forEach(msg => {
      addChatMessage(msg.role, msg.content);
    });
    // 打开弹窗
    guidedModal.style.display = 'flex';
    scrollChat();
  };

  // 暴露 applyTemplateParams 给草稿箱使用
  window.applyTemplateParams = applyTemplateParams;

  // 关闭弹窗
  guidedClose.addEventListener('click', closeChatModal);
  guidedModal.addEventListener('click', function (e) {
    if (e.target === guidedModal) closeChatModal();
  });

  function closeChatModal() {
    guidedModal.style.display = 'none';
    isChatWaiting = false;
  }

  // 发送消息
  async function sendChatMessage() {
    const text = chatInput.value.trim();
    if (!text || isChatWaiting) return;

    // 添加用户消息到界面
    addChatMessage('user', text);
    chatHistory.push({ role: 'user', content: text });
    chatInput.value = '';
    chatInput.style.height = 'auto';

    // 显示正在输入
    showTypingIndicator();
    isChatWaiting = true;
    chatSend.disabled = true;

    // 隐藏旧的大纲区域
    outlineArea.style.display = 'none';

    try {
      const resp = await fetch('/api/novel/guided-chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          messages: chatHistory,
          llm_interface: $('novel-llm-interface').value,
          llm_api_key: $('novel-llm-key').value.trim(),
          llm_base_url: $('novel-llm-url').value.trim(),
          llm_model: $('novel-llm-model').value.trim() || 'deepseek-v4-flash',
          llm_temperature: parseFloat($('novel-temperature').value) || 0.7,
          llm_max_tokens: parseInt($('novel-max-tokens').value) || 4096,
        }),
      });

      if (!resp.ok) {
        const err = await resp.json();
        throw new Error(err.detail || '请求失败');
      }

      const data = await resp.json();
      const reply = data.reply || '';

      // 移除正在输入指示
      removeTypingIndicator();

      // 添加 AI 回复
      addChatMessage('assistant', reply);
      chatHistory.push({ role: 'assistant', content: reply });

      // 如果包含大纲，显示预览
      if (data.has_outline) {
        lastOutlineText = reply;
        showOutlinePreview(reply);
      }

    } catch (e) {
      removeTypingIndicator();
      addChatMessage('assistant', '❌ 出错了：' + e.message);
      showToast('对话失败: ' + e.message, 'error');
    } finally {
      isChatWaiting = false;
      chatSend.disabled = false;
      scrollChat();
    }
  }

  // 点击发送 / Enter 发送
  chatSend.addEventListener('click', sendChatMessage);
  chatInput.addEventListener('keydown', function (e) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      sendChatMessage();
    }
  });

  // 添加聊天消息
  function addChatMessage(role, content) {
    // 如果是大纲，只显示简要版
    let displayContent = content;
    const outlineMatch = content.match(/【大纲开始】([\s\S]*?)【大纲结束】/);
    if (outlineMatch) {
      // 提取大纲的核心信息（不显示冗长的章节规划）
      const outlineBody = outlineMatch[1].trim();
      const lines = outlineBody.split('\n').filter(l => l.trim());
      const summaryLines = lines.filter(l =>
        !l.trim().startsWith('第') && !l.trim().startsWith('-') && l.trim().length < 50
      );
      displayContent = summaryLines.join('\n') || '📋 大纲已生成（见下方预览区）';
    }

    const div = document.createElement('div');
    div.className = `chat-msg ${role}`;
    div.innerHTML = `
      <div class="msg-avatar">${role === 'user' ? '👤' : '🤖'}</div>
      <div class="msg-bubble">${formatChatMessage(displayContent)}</div>`;
    chatMessages.appendChild(div);
    scrollChat();
  }

  // 格式化聊天消息（支持粗体、代码等）
  function formatChatMessage(text) {
    return text
      .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
      .replace(/`(.+?)`/g, '<code>$1</code>')
      .replace(/\n/g, '<br>');
  }

  // 正在输入指示
  function showTypingIndicator() {
    const div = document.createElement('div');
    div.className = 'chat-msg assistant';
    div.id = 'typing-indicator';
    div.innerHTML = `
      <div class="msg-avatar">🤖</div>
      <div class="typing-indicator"><span></span><span></span><span></span></div>`;
    chatMessages.appendChild(div);
    scrollChat();
  }

  function removeTypingIndicator() {
    const el = document.getElementById('typing-indicator');
    if (el) el.remove();
  }

  function scrollChat() {
    setTimeout(() => {
      chatMessages.scrollTop = chatMessages.scrollHeight;
    }, 50);
  }

  // 显示大纲预览
  function showOutlinePreview(rawText) {
    // 提取【大纲开始】...【大纲结束】之间的内容
    const match = rawText.match(/【大纲开始】([\s\S]*?)【大纲结束】/);
    if (!match) return;

    const outlineBody = match[1].trim();
    outlinePreview.innerHTML = formatOutlinePreview(outlineBody);
    outlineArea.style.display = 'block';
  }

  function formatOutlinePreview(text) {
    const lines = text.split('\n').filter(l => l.trim());
    let html = '';
    for (const line of lines) {
      const trimmed = line.trim();
      if (trimmed.startsWith('标题：') || trimmed.startsWith('标题:')) {
        html += `<h4>📖 ${trimmed}</h4>`;
      } else if (trimmed.startsWith('类型：') || trimmed.startsWith('类型:')) {
        html += `<p><strong>类型：</strong>${trimmed.replace(/^类型[：:]\s*/, '')}</p>`;
      } else if (trimmed.startsWith('核心主题')) {
        html += `<p><strong>${trimmed}</strong></p>`;
      } else if (trimmed.startsWith('角色设定')) {
        html += `<p style="margin-top:8px"><strong>🎭 角色设定</strong></p>`;
      } else if (trimmed.startsWith('世界观') || trimmed.startsWith('背景')) {
        html += `<p><strong>🌍 ${trimmed}</strong></p>`;
      } else if (trimmed.startsWith('章节规划')) {
        html += `<p style="margin-top:8px"><strong>📑 章节规划</strong></p>`;
      } else if (trimmed.startsWith('写作建议')) {
        html += `<p style="margin-top:8px"><strong>✏️ 写作建议</strong></p>`;
      } else if (trimmed.startsWith('-') || trimmed.startsWith('第')) {
        html += `<div style="padding-left:12px;font-size:0.85rem;color:var(--text-secondary)">${trimmed}</div>`;
      } else {
        html += `<p>${trimmed}</p>`;
      }
    }
    return html;
  }

  // 确认大纲 → 填充表单
  confirmBtn.addEventListener('click', function () {
    if (!lastOutlineText) return;

    const match = lastOutlineText.match(/【大纲开始】([\s\S]*?)【大纲结束】/);
    if (!match) { showToast('无法解析大纲', 'error'); return; }

    const text = match[1];
    const lines = text.split('\n').map(l => l.trim()).filter(l => l);

    let title = '';
    let genre = '';
    let characters = '';
    let world = '';
    let guidance = '';

    for (let i = 0; i < lines.length; i++) {
      const line = lines[i];
      if (line.startsWith('标题：') || line.startsWith('标题:')) {
        title = line.replace(/^标题[：:]\s*/, '');
      } else if (line.startsWith('类型：') || line.startsWith('类型:')) {
        genre = line.replace(/^类型[：:]\s*/, '');
      } else if (line.startsWith('角色设定')) {
        // 收集后续以 - 开头的行
        const roleLines = [];
        for (let j = i + 1; j < lines.length && (lines[j].startsWith('-') || lines[j].startsWith('第')); j++) {
          roleLines.push(lines[j]);
          i = j; // skip
        }
        characters = roleLines.join('；');
      } else if (line.startsWith('世界观') || line.startsWith('背景')) {
        world = line.replace(/^[^：:]*[：:]\s*/, '');
      } else if (line.startsWith('写作建议')) {
        const guideLines = [];
        for (let j = i + 1; j < lines.length && lines[j].startsWith('-'); j++) {
          guideLines.push(lines[j].replace(/^-\s*/, ''));
          i = j;
        }
        guidance = guideLines.join('；');
      }
    }

    // 填充表单
    if (title) $(`novel-topic`).value = title;
    if (genre) $(`novel-genre`).value = genre;
    if (characters) $(`novel-characters`).value = characters;
    if (world) $(`novel-location`).value = $(`novel-location`).value + (world ? '；' + world : '');
    if (guidance) $(`novel-guidance`).value = guidance;

    showToast('✅ 大纲已应用到表单，可微调后生成', 'success');
    closeChatModal();
  });

  // 重新生成
  retryBtn.addEventListener('click', function () {
    // 移除最后一条 AI 消息，重新请求
    if (chatHistory.length >= 2 && chatHistory[chatHistory.length - 1].role === 'assistant') {
      chatHistory.pop();
      // 移除最后一条聊天消息
      const msgs = chatMessages.querySelectorAll('.chat-msg');
      if (msgs.length >= 2) {
        msgs[msgs.length - 1].remove();
      }
    }
    outlineArea.style.display = 'none';
    // 重新发送最后一条用户消息
    chatInput.value = chatHistory[chatHistory.length - 1]?.content || '';
    chatHistory.pop();
    // 移除最后一条用户消息
    const msgs = chatMessages.querySelectorAll('.chat-msg');
    if (msgs.length >= 1) {
      msgs[msgs.length - 1].remove();
    }
    sendChatMessage();
  });

  // =============================================================
  //  续写模式
  // =============================================================
  const continueBtn = $('novel-continue-btn');
  const continueModal = $('continue-modal');
  const continueClose = $('continue-modal-close');
  const continueChapters = $('continue-chapters');
  const continueGuidance = $('continue-guidance');
  const continueTaboos = $('continue-taboos');
  const continueStartBtn = $('continue-start-btn');
  const continueStatus = $('continue-status');
  const continueInfo = $('continue-info');
  const continueInsertAfter = $('continue-insert-after');
  const continueChapterList = $('continue-chapter-list');
  const continueSelectAll = $('continue-select-all');
  const continueDeselectAll = $('continue-deselect-all');

  let currentNovelPath = '';  // 当前显示的小说路径

  // 同步函数：确保本地路径与 window 一致（草稿箱加载后调用）
  function syncNovelPath() {
    // 如果 window 上有路径但本地没有，从 window 同步
    if (!currentNovelPath && window.currentNovelPath) {
      currentNovelPath = window.currentNovelPath;
    }
  }

  // 填充章节列表到续写对话框
  function populateContinueChapterList(totalChapters) {
    // 插入位置下拉
    continueInsertAfter.innerHTML = '<option value="-1">追加到末尾</option>';
    for (let i = 1; i <= totalChapters; i++) {
      const opt = document.createElement('option');
      opt.value = i;
      opt.textContent = `第 ${i} 章后`;
      continueInsertAfter.appendChild(opt);
    }

    // 参考章节复选框
    continueChapterList.innerHTML = '';
    for (let i = 1; i <= totalChapters; i++) {
      const label = document.createElement('label');
      label.style.cssText = 'display:flex;align-items:center;gap:8px;padding:4px 6px;cursor:pointer;border-radius:4px';
      label.onmouseover = () => label.style.background = 'rgba(255,255,255,0.05)';
      label.onmouseout = () => label.style.background = '';
      const cb = document.createElement('input');
      cb.type = 'checkbox';
      cb.checked = true;
      cb.value = i;
      cb.id = `chk-ch-${i}`;
      const ch = currentChapters[i - 1] || {};
      const chTitle = typeof ch.title === 'string' ? ch.title : '';
      label.appendChild(cb);
      label.appendChild(document.createTextNode(`第 ${i} 章${chTitle ? '：' + chTitle : ''}`));
      continueChapterList.appendChild(label);
    }
  }

  // 全选/取消全选
  continueSelectAll.addEventListener('click', () => {
    continueChapterList.querySelectorAll('input[type="checkbox"]').forEach(cb => cb.checked = true);
  });
  continueDeselectAll.addEventListener('click', () => {
    continueChapterList.querySelectorAll('input[type="checkbox"]').forEach(cb => cb.checked = false);
  });

  // 续写按钮点击 → 弹出续写对话框
  continueBtn.addEventListener('click', function () {
    syncNovelPath();
    if (!currentNovelPath) {
      showToast('没有可续写的小说（请先生成或加载一部小说）', 'info');
      return;
    }

    const total = currentChapters.length;
    continueInfo.textContent = `当前小说：${total} 章已完成，将在此基础上续写新章节。`;
    continueChapters.value = '3';
    continueGuidance.value = '';
    continueTaboos.value = '';
    continueStatus.textContent = '';
    populateContinueChapterList(total);
    continueModal.style.display = 'flex';
  });

  // 关闭续写对话框
  continueClose.addEventListener('click', () => { continueModal.style.display = 'none'; });
  continueModal.addEventListener('click', function (e) {
    if (e.target === continueModal) continueModal.style.display = 'none';
  });

  // 开始续写
  continueStartBtn.addEventListener('click', async function () {
    syncNovelPath();
    const numChapters = parseInt(continueChapters.value) || 3;
    if (numChapters < 1) { showToast('章节数至少为 1', 'error'); return; }
    if (!currentNovelPath) { showToast('小说路径丢失，请重新加载', 'error'); return; }

    continueStartBtn.disabled = true;
    continueStatus.textContent = '⏳ 正在启动续写...';
    resultPanel.style.display = 'block';
    resultTitle.textContent = '✍️ 续写中...';

    try {
      // 收集选中的参考章节
      const contextChapters = [];
      continueChapterList.querySelectorAll('input[type="checkbox"]:checked').forEach(cb => {
        contextChapters.push(parseInt(cb.value));
      });
      const insertAfter = parseInt(continueInsertAfter.value);

      // POST 请求返回 SSE 流
      const resp = await fetch('/api/novel/continue', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          novel_path: currentNovelPath,
          num_chapters: numChapters,
          insert_after: insertAfter,
          context_chapters: contextChapters,
          user_guidance: continueGuidance.value.trim(),
          content_taboos: continueTaboos.value.trim(),
          llm_interface: $('novel-llm-interface').value,
          llm_api_key: $('novel-llm-key').value.trim(),
          llm_base_url: $('novel-llm-url').value.trim(),
          llm_model: $('novel-llm-model').value.trim() || 'deepseek-v4-flash',
          llm_temperature: parseFloat($('novel-temperature').value) || 0.7,
          llm_max_tokens: parseInt($('novel-max-tokens').value) || 8192,
          embedding_interface: $('novel-emb-interface').value,
          embedding_api_key: $('novel-emb-key').value.trim(),
          embedding_base_url: $('novel-emb-url').value.trim(),
          embedding_model: $('novel-emb-model').value.trim() || 'bge-m3',
        }),
      });

      if (!resp.ok) {
        const err = await resp.json().catch(() => ({}));
        throw new Error(err.detail || '续写启动失败');
      }

      // 关闭对话框
      continueModal.style.display = 'none';

      // 读取 SSE 流
      const reader = resp.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';

        for (const line of lines) {
          if (!line.startsWith('data: ')) continue;
          try {
            const msg = JSON.parse(line.slice(6).trim());
            handleStreamMessage(msg);
          } catch (e) { /* ignore */ }
        }
      }

      showToast(`✅ 续写完成！共追加 ${numChapters} 章`, 'success');

    } catch (e) {
      showToast('续写失败: ' + e.message, 'error');
      continueStatus.textContent = '❌ ' + e.message;
    } finally {
      continueStartBtn.disabled = false;
    }
  });

  // =============================================================
  //  工具函数
  // =============================================================
  function escapeHtml(text) {
    const d = document.createElement('div');
    d.textContent = text;
    return d.innerHTML;
  }

  function escapeAttr(text) {
    return text ? String(text).replace(/"/g, '&quot;').replace(/'/g, '&#39;') : '';
  }

  function nl2br(text) {
    if (!text) return '(空)';
    return escapeHtml(text).replace(/\n/g, '<br>');
  }

  function showToast(message, type = 'info') {
    const container = document.getElementById('toast-container');
    if (!container) return;
    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    toast.textContent = message;
    container.appendChild(toast);
    setTimeout(() => {
      toast.style.opacity = '0';
      toast.style.transition = 'opacity 0.3s';
      setTimeout(() => toast.remove(), 300);
    }, 3000);
  }
});

// 全局函数 - auto resize chat input
function autoResizeChatInput(el) {
  el.style.height = 'auto';
  el.style.height = Math.min(el.scrollHeight, 100) + 'px';
}
