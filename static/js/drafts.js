/* =========================================================
   草稿箱 Tab - 独立管理草稿 + 内容阅览
   ========================================================= */

// 用于区分业务异常和解析异常
class ContinuationError extends Error {}

document.addEventListener('DOMContentLoaded', function () {

  const $ = id => document.getElementById(id);
  const draftsList = $('drafts-list');
  const draftsStats = $('drafts-stats');
  const refreshBtn = $('drafts-refresh-btn');

  const viewer = $('drafts-viewer');
  const viewerTitle = $('drafts-viewer-title');
  const viewerContent = $('drafts-viewer-content');
  const viewerBack = $('drafts-viewer-back');
  const viewerCopy = $('drafts-viewer-copy');
  const viewerContinue = $('drafts-viewer-continue');
  const viewerToggleAll = $('drafts-viewer-toggle-all');

  // 续写对话框元素
  const continueModal = $('continue-modal');
  const continueClose = $('continue-modal-close');
  const continueInfo = $('continue-info');
  const continueInsertAfter = $('continue-insert-after');
  const continueChapterList = $('continue-chapter-list');
  const continueSelectAll = $('continue-select-all');
  const continueDeselectAll = $('continue-deselect-all');
  const continueChapters = $('continue-chapters');
  const continueGuidance = $('continue-guidance');
  const continueTaboos = $('continue-taboos');
  const continueStartBtn = $('continue-start-btn');
  const continueStatus = $('continue-status');

  let _currentDraftPath = '';   // 当前加载的草稿路径
  let _currentDraftChapters = []; // 当前草稿章节（{title?, content} 数组）

  // =============================================================
  //  初始化
  // =============================================================

  // 切换到草稿箱 Tab 时自动刷新（仅当在列表模式）
  const draftsTabBtn = document.querySelector('.tab-btn[data-tab="drafts"]');
  if (draftsTabBtn) {
    const observer = new MutationObserver(() => {
      if (draftsTabBtn.classList.contains('active') && viewer.style.display !== 'block') {
        loadDrafts();
      }
    });
    observer.observe(draftsTabBtn, { attributes: true, attributeFilter: ['class'] });
  }

  refreshBtn.addEventListener('click', () => { hideViewer(); loadDrafts(); });
  const tplRefreshBtn = $('drafts-templates-refresh-btn');
  if (tplRefreshBtn) tplRefreshBtn.addEventListener('click', () => loadTemplatesList());
  const chatRefreshBtn = $('drafts-chats-refresh-btn');
  if (chatRefreshBtn) chatRefreshBtn.addEventListener('click', () => loadChatsList());

  // 返回列表
  viewerBack.addEventListener('click', hideViewer);

  // 复制全文
  viewerCopy.addEventListener('click', copyFullText);

  // 续写按钮
  viewerContinue.addEventListener('click', openContinueModal);

  // 全部展开/折叠
  viewerToggleAll.addEventListener('click', toggleAllChapters);

  // 续写对话框关闭
  continueClose.addEventListener('click', () => { continueModal.style.display = 'none'; });
  continueModal.addEventListener('click', function (e) {
    if (e.target === continueModal) continueModal.style.display = 'none';
  });

  // 全选/取消全选
  continueSelectAll.addEventListener('click', () => {
    continueChapterList.querySelectorAll('input[type="checkbox"]').forEach(cb => cb.checked = true);
  });
  continueDeselectAll.addEventListener('click', () => {
    continueChapterList.querySelectorAll('input[type="checkbox"]').forEach(cb => cb.checked = false);
  });

  // 开始续写
  continueStartBtn.addEventListener('click', startContinuation);

  // =============================================================
  //  草稿箱子标签切换
  // =============================================================
  const subtabBtns = document.querySelectorAll('.drafts-subtab');
  const subtabContents = {
    novels: $('drafts-sub-novels'),
    templates: $('drafts-sub-templates'),
    chats: $('drafts-sub-chats'),
  };
  subtabBtns.forEach(btn => {
    btn.addEventListener('click', function () {
      subtabBtns.forEach(b => b.classList.remove('active'));
      this.classList.add('active');
      const sub = this.dataset.subtab;
      Object.values(subtabContents).forEach(el => { if (el) el.style.display = 'none'; });
      if (subtabContents[sub]) subtabContents[sub].style.display = 'block';
      // 切换时加载对应内容
      if (sub === 'novels') loadDrafts();
      else if (sub === 'templates') loadTemplatesList();
      else if (sub === 'chats') loadChatsList();
    });
  });

  // =============================================================
  //  模板列表
  // =============================================================
  async function loadTemplatesList() {
    const container = $('drafts-templates-list');
    if (!container) return;
    container.innerHTML = '<div style="text-align:center;padding:40px"><span class="spinner"></span> 加载中...</div>';
    try {
      const resp = await fetch('/api/novel/templates/custom');
      const text = await resp.text();
      if (!resp.ok) throw new Error('HTTP ' + resp.status + ': ' + text.slice(0, 150));
      let data;
      try { data = JSON.parse(text); } catch (_) {
        throw new Error('响应不是合法JSON: ' + text.slice(0, 150));
      }
      const templates = data.templates || [];
      if (templates.length === 0) {
        container.innerHTML = `
          <div class="empty-state" style="padding:40px;text-align:center;color:var(--text-muted)">
            <div class="icon" style="font-size:2.5rem">📋</div>
            <p style="margin-top:8px">还没有自定义模板</p>
            <p style="font-size:0.85rem;margin-top:4px">在「生成小说」Tab 填好设置后点击「💾 保存为模板」</p>
          </div>`;
        return;
      }
      container.innerHTML = '';
      templates.forEach(t => {
        const card = document.createElement('div');
        card.className = 'draft-card';
        const date = t.created_at ? t.created_at.slice(0, 10) : '';
        const params = t.params || {};
        const detail = [
          params.topic ? `主题: ${escapeHtml(params.topic)}` : '',
          params.genre ? `类型: ${escapeHtml(params.genre)}` : '',
        ].filter(Boolean).join(' | ');
        card.innerHTML = `
          <div class="draft-card-header">
            <div class="draft-card-title">📋 ${escapeHtml(t.name)}</div>
          </div>
          <div style="font-size:0.8rem;color:var(--text-secondary);line-height:1.5">${escapeHtml(detail)}</div>
          <div class="draft-card-footer">
            <span class="draft-date">${date}</span>
            <div class="draft-card-actions">
              <button class="btn btn-sm btn-primary tpl-load-btn" data-id="${escapeAttr(t.id)}">📂 使用</button>
              <button class="btn btn-sm btn-secondary tpl-edit-btn" data-id="${escapeAttr(t.id)}" data-name="${escapeAttr(t.name)}">✏️ 编辑</button>
              <button class="btn btn-sm btn-danger tpl-del-btn" data-id="${escapeAttr(t.id)}">🗑️</button>
            </div>
          </div>`;
        card.querySelector('.tpl-load-btn').addEventListener('click', (e) => {
          e.stopPropagation();
          loadTemplate(t);
        });
        card.querySelector('.tpl-edit-btn').addEventListener('click', (e) => {
          e.stopPropagation();
          editTemplate(t);
        });
        card.querySelector('.tpl-del-btn').addEventListener('click', (e) => {
          e.stopPropagation();
          deleteTemplate(t.id, t.name);
        });
        card.addEventListener('click', () => loadTemplate(t));
        container.appendChild(card);
      });
    } catch (e) {
      container.innerHTML = `<div style="color:var(--danger);padding:20px">加载失败: ${e.message}</div>`;
    }
  }

  async function loadTemplate(tpl) {
    // 跳转到小说 Tab 并填入参数
    const novelTabBtn = document.querySelector('.tab-btn[data-tab="novel"]');
    if (novelTabBtn) novelTabBtn.click();
    showToast(`⏳ 正在加载模板「${tpl.name}」...`, 'info');
    // 通过 window 上的 applyTemplateParams 来填充
    if (window.applyTemplateParams && tpl.params) {
      window.applyTemplateParams(tpl.params);
      showToast(`✅ 已加载模板「${tpl.name}」`, 'success');
    } else {
      showToast('请刷新页面后重试', 'error');
    }
  }

  async function deleteTemplate(id, name) {
    if (!confirm(`确定要删除模板「${name}」吗？`)) return;
    try {
      const resp = await fetch('/api/novel/templates/custom/delete', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ template_id: id }),
      });
      const text = await resp.text();
      if (!resp.ok) throw new Error('HTTP ' + resp.status + ': ' + text.slice(0, 150));
      let data;
      try { data = JSON.parse(text); } catch (_) {
        throw new Error('响应不是合法JSON: ' + text.slice(0, 150));
      }
      if (!data.success) throw new Error(data.detail || '删除失败');
      showToast(`🗑️ 已删除「${name}」`, 'success');
      loadTemplatesList();
    } catch (e) {
      showToast('删除失败: ' + e.message, 'error');
    }
  }

  async function editTemplate(t) {
    // 跳转到小说 Tab 并填入参数
    const novelTabBtn = document.querySelector('.tab-btn[data-tab="novel"]');
    if (novelTabBtn) novelTabBtn.click();
    // 加载参数到表单
    if (window.applyTemplateParams && t.params) {
      window.applyTemplateParams(t.params);
    }
    // 通知 novel.js 进入编辑模式
    window._editingTemplateId = t.id;
    window._editingTemplateName = t.name;
    // 触发编辑模式 UI 变更（由 novel.js 监听）
    const evt = new CustomEvent('template-edit-mode', { detail: { id: t.id, name: t.name } });
    document.dispatchEvent(evt);
    showToast(`✏️ 正在编辑模板「${t.name}」`, 'info');
  }

  // =============================================================
  //  对话列表
  // =============================================================
  async function loadChatsList() {
    const container = $('drafts-chats-list');
    if (!container) return;
    container.innerHTML = '<div style="text-align:center;padding:40px"><span class="spinner"></span> 加载中...</div>';
    try {
      const resp = await fetch('/api/novel/chat/list');
      const data = await resp.json();
      const chats = data.chats || [];
      if (chats.length === 0) {
        container.innerHTML = `
          <div class="empty-state" style="padding:40px;text-align:center;color:var(--text-muted)">
            <div class="icon" style="font-size:2.5rem">💬</div>
            <p style="margin-top:8px">还没有保存的对话</p>
            <p style="font-size:0.85rem;margin-top:4px">在「AI 帮我想」对话框中可以保存对话记录</p>
          </div>`;
        return;
      }
      container.innerHTML = '';
      chats.forEach(c => {
        const card = document.createElement('div');
        card.className = 'draft-card';
        const date = c.created_at ? c.created_at.slice(0, 10) : '';
        card.innerHTML = `
          <div class="draft-card-header">
            <div class="draft-card-title">💬 ${escapeHtml(c.name)}</div>
          </div>
          <div style="font-size:0.8rem;color:var(--text-secondary)">${c.message_count || 0} 条消息</div>
          <div class="draft-card-footer">
            <span class="draft-date">${date}</span>
            <div class="draft-card-actions">
              <button class="btn btn-sm btn-primary chat-load-btn" data-id="${escapeAttr(c.id)}">💬 继续对话</button>
              <button class="btn btn-sm btn-danger chat-del-btn" data-id="${escapeAttr(c.id)}">🗑️</button>
            </div>
          </div>`;
        card.querySelector('.chat-load-btn').addEventListener('click', (e) => {
          e.stopPropagation();
          continueChat(c.id);
        });
        card.querySelector('.chat-del-btn').addEventListener('click', (e) => {
          e.stopPropagation();
          deleteChat(c.id, c.name);
        });
        card.addEventListener('click', () => continueChat(c.id));
        container.appendChild(card);
      });
    } catch (e) {
      container.innerHTML = `<div style="color:var(--danger);padding:20px">加载失败: ${e.message}</div>`;
    }
  }

  async function continueChat(chatId) {
    try {
      const resp = await fetch('/api/novel/chat/load', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ chat_id: chatId }),
      });
      const data = await resp.json();
      if (!data.success || !data.data) throw new Error('加载失败');
      const chat = data.data;
      // 切换到小说 Tab 并打开引导对话框
      const novelTabBtn = document.querySelector('.tab-btn[data-tab="novel"]');
      if (novelTabBtn) novelTabBtn.click();
      // 延迟等待 Tab 切换后调用全局函数
      setTimeout(() => {
        if (window.restoreChat) {
          window.restoreChat(chat.messages || []);
        } else {
          showToast('页面加载中，请稍候再试', 'error');
        }
      }, 300);
    } catch (e) {
      showToast('加载对话失败: ' + e.message, 'error');
    }
  }

  async function deleteChat(id, name) {
    if (!confirm(`确定要删除对话「${name}」吗？`)) return;
    try {
      const resp = await fetch('/api/novel/chat/delete', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ chat_id: id }),
      });
      const data = await resp.json();
      if (!data.success) throw new Error(data.detail || '删除失败');
      showToast(`🗑️ 已删除「${name}」`, 'success');
      loadChatsList();
    } catch (e) {
      showToast('删除失败: ' + e.message, 'error');
    }
  }

  // =============================================================
  //  视图切换
  // =============================================================
  function showViewer() {
    draftsList.style.display = 'none';
    draftsStats.style.display = 'none';
    refreshBtn.parentElement.style.display = 'none';  // card header
    viewer.style.display = 'block';
  }

  function hideViewer() {
    viewer.style.display = 'none';
    draftsList.style.display = '';
    draftsStats.style.display = '';
    refreshBtn.parentElement.style.display = '';
    viewerContent.innerHTML = '';
    // 自动刷新列表
    loadDrafts();
  }

  // =============================================================
  //  加载草稿列表
  // =============================================================
  async function loadDrafts() {
    draftsList.innerHTML = '<div style="text-align:center;padding:40px"><span class="spinner"></span> 加载中...</div>';
    draftsStats.textContent = '';

    try {
      const resp = await fetch('/api/novel/drafts');
      const data = await resp.json();
      const novels = data.novels || [];

      draftsStats.textContent = novels.length > 0
        ? `共 ${novels.length} 部草稿`
        : '';

      if (novels.length === 0) {
        draftsList.innerHTML = `
          <div class="empty-state" style="padding:60px;text-align:center;color:var(--text-muted)">
            <div class="icon" style="font-size:3rem">📭</div>
            <p style="margin-top:12px;font-size:1.1rem">还没有草稿</p>
            <p style="font-size:0.85rem;margin-top:4px">去「生成小说」Tab 创作你的第一部作品吧</p>
          </div>`;
        return;
      }

      draftsList.innerHTML = '';
      novels.forEach(n => {
        const card = document.createElement('div');
        card.className = 'draft-card';
        card.setAttribute('role', 'button');
        card.setAttribute('tabindex', '0');

        const createdDate = n.created_at ? n.created_at.slice(0, 10) : '未知日期';
        const genreTag = n.genre ? `<span class="badge badge-primary">${escapeHtml(n.genre)}</span>` : '';

        card.innerHTML = `
          <div class="draft-card-header">
            <div class="draft-card-title">${escapeHtml(n.name)}</div>
            ${genreTag}
          </div>
          <div class="draft-card-body">
            <div class="draft-card-stat">
              <span class="stat-value">${n.chapter_count}</span>
              <span class="stat-label">章</span>
            </div>
          </div>
          <div class="draft-card-footer">
            <span class="draft-date">${createdDate}</span>
            <div class="draft-card-actions">
              <button class="btn btn-sm btn-primary draft-load-btn">📂 加载</button>
              <button class="btn btn-sm btn-danger draft-del-btn">🗑️</button>
            </div>
          </div>`;

        card.querySelector('.draft-load-btn').addEventListener('click', (e) => {
          e.stopPropagation();
          loadDraft(n.path, n.name);
        });

        card.querySelector('.draft-del-btn').addEventListener('click', (e) => {
          e.stopPropagation();
          deleteDraft(n.path, n.name);
        });

        card.addEventListener('click', () => loadDraft(n.path, n.name));

        draftsList.appendChild(card);
      });
    } catch (e) {
      draftsList.innerHTML = `<div style="color:var(--danger);padding:20px">加载失败: ${e.message}</div>`;
    }
  }

  // =============================================================
  //  加载草稿 → 显示在草稿箱 Tab 内
  // =============================================================
  async function loadDraft(path, name) {
    try {
      const resp = await fetch('/api/novel/load', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ path }),
      });
      const data = await resp.json();
      if (!data.success) { showToast('加载失败', 'error'); return; }

      const novel = data.data;
      _currentDraftPath = novel.path;
      _currentDraftChapters = (novel.chapters || []).map((ch, i) => {
        const content = typeof ch === 'string' ? ch : (ch.content || '');
        return { chapter: i + 1, content, title: ch.title || '' };
      });

      // 同步到全局，供小说 Tab 续写使用
      window.currentNovelPath = novel.path;
      if (window.currentChapters !== undefined) {
        window.currentChapters.length = 0;
        _currentDraftChapters.forEach(ch => {
          window.currentChapters.push({ chapter: ch.chapter, content: ch.content });
        });
      }

      // 在本 Tab 显示
      loadDraftIntoViewer(path);
    } catch (e) {
      showToast('加载失败: ' + e.message, 'error');
    }
  }

  // 渲染草稿内容到阅览区（也用于续写后刷新）
  async function loadDraftIntoViewer(path) {
    try {
      // 如果传入新路径则重新获取
      if (path && path !== _currentDraftPath) {
        await loadDraft(path, '');
        return;
      }

      showViewer();
      viewerContent.innerHTML = '';
      viewerTitle.textContent = _currentDraftChapters.length > 0
        ? `📖 ${_currentDraftChapters[0]?.title || '已加载'}`
        : '📖 已加载';

      // 从后端获取架构信息（可折叠，默认折叠）
      try {
        const resp = await fetch('/api/novel/load', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ path: _currentDraftPath }),
        });
        const data = await resp.json();
        if (data.success && data.data && data.data.architecture) {
          const sec = document.createElement('div');
          sec.className = 'stream-section collapsible-section collapsed';
          sec.id = 'draft-arch-section';
          const header = document.createElement('div');
          header.className = 'stream-chapter-title collapsible-header';
          header.onclick = () => {
            sec.classList.toggle('collapsed');
            header.querySelector('.collapse-arrow').textContent = sec.classList.contains('collapsed') ? '▼' : '▲';
          };
          header.setAttribute('role', 'button');
          header.setAttribute('tabindex', '0');
          header.innerHTML = '<span>📖 小说架构</span><span class="collapse-arrow">▼</span>';
          const body = document.createElement('div');
          body.className = 'collapse-body';
          body.innerHTML = nl2br(data.data.architecture);
          sec.appendChild(header);
          sec.appendChild(body);
          viewerContent.appendChild(sec);
        }
      } catch (_) {}

      // 显示章节（可折叠）
      _currentDraftChapters.forEach((ch, i) => {
        const section = document.createElement('div');
        section.className = 'stream-section collapsible-section';
        section.id = `draft-ch-${i + 1}`;

        const header = document.createElement('div');
        header.className = 'stream-chapter-title collapsible-header';
        header.onclick = () => toggleChapter(section);
        header.setAttribute('role', 'button');
        header.setAttribute('tabindex', '0');
        header.innerHTML = `
          <span>第 ${ch.chapter} 章</span>
          <span class="collapse-arrow">▲</span>`;

        const body = document.createElement('div');
        body.className = 'collapse-body';
        body.innerHTML = nl2br(ch.content);

        section.appendChild(header);
        section.appendChild(body);
        viewerContent.appendChild(section);
      });

      // 默认只展开第 1 章，其余折叠
      const allSections = viewerContent.querySelectorAll('.collapsible-section');
      allSections.forEach((sec, idx) => {
        if (idx > 0) sec.classList.add('collapsed');
      });

      // 更新折叠按钮文字
      updateToggleAllBtn();

      showToast('✅ 草稿已加载', 'success');
    } catch (e) {
      showToast('显示失败: ' + e.message, 'error');
    }
  }

  // =============================================================
  //  章节折叠/展开
  // =============================================================
  function toggleChapter(sectionEl) {
    sectionEl.classList.toggle('collapsed');
    const arrow = sectionEl.querySelector('.collapse-arrow');
    if (arrow) arrow.textContent = sectionEl.classList.contains('collapsed') ? '▼' : '▲';
    updateToggleAllBtn();
  }

  function toggleAllChapters() {
    const allSec = viewerContent.querySelectorAll('.collapsible-section');
    const isAnyExpanded = Array.from(allSec).some(s => !s.classList.contains('collapsed'));
    // 如果至少有一个展开 → 全部折叠；否则全部展开
    allSec.forEach(sec => {
      if (isAnyExpanded) {
        sec.classList.add('collapsed');
        const arrow = sec.querySelector('.collapse-arrow');
        if (arrow) arrow.textContent = '▼';
      } else {
        sec.classList.remove('collapsed');
        const arrow = sec.querySelector('.collapse-arrow');
        if (arrow) arrow.textContent = '▲';
      }
    });
    updateToggleAllBtn();
  }

  function updateToggleAllBtn() {
    const allSec = viewerContent.querySelectorAll('.collapsible-section');
    const allCollapsed = allSec.length > 0 && Array.from(allSec).every(s => s.classList.contains('collapsed'));
    viewerToggleAll.textContent = allCollapsed ? '📑 全部展开' : '📑 全部折叠';
  }

  // =============================================================
  //  复制全文
  // =============================================================
  function copyFullText() {
    if (!window.currentChapters || window.currentChapters.length === 0) {
      showToast('没有内容可复制', 'error');
      return;
    }
    const text = window.currentChapters
      .map(ch => `第 ${ch.chapter} 章\n\n${ch.content}`)
      .join('\n\n---\n\n');
    const ta = document.createElement('textarea');
    ta.value = text;
    ta.style.position = 'fixed';
    ta.style.left = '-9999px';
    document.body.appendChild(ta);
    ta.select();
    document.execCommand('copy');
    document.body.removeChild(ta);
    showToast('✅ 已复制全文到剪贴板', 'success');
  }

  // =============================================================
  //  续写：打开对话框（填充章节列表）
  // =============================================================
  function openContinueModal() {
    const total = _currentDraftChapters.length;
    if (total === 0) {
      showToast('没有可续写的内容', 'error');
      return;
    }

    // 填充续写位置下拉
    continueInsertAfter.innerHTML = '<option value="-1">追加到末尾</option>';
    for (let i = 1; i <= total; i++) {
      const opt = document.createElement('option');
      opt.value = i;
      opt.textContent = `第 ${i} 章后`;
      continueInsertAfter.appendChild(opt);
    }

    // 填充参考章节复选框
    continueChapterList.innerHTML = '';
    for (let i = 1; i <= total; i++) {
      const label = document.createElement('label');
      label.style.cssText = 'display:flex;align-items:center;gap:8px;padding:4px 6px;cursor:pointer;border-radius:4px';
      label.onmouseover = () => label.style.background = 'rgba(255,255,255,0.05)';
      label.onmouseout = () => label.style.background = '';
      const cb = document.createElement('input');
      cb.type = 'checkbox';
      cb.checked = true;
      cb.value = i;
      const ch = _currentDraftChapters[i - 1] || {};
      const chTitle = typeof ch.title === 'string' ? ch.title : '';
      const labelText = `第 ${i} 章${chTitle ? '：' + chTitle : ''}`;
      label.appendChild(cb);
      label.appendChild(document.createTextNode(labelText));
      continueChapterList.appendChild(label);
    }

    continueInfo.textContent = `当前小说：${total} 章已完成。可在任意位置插入新章节。`;
    continueChapters.value = '3';
    continueGuidance.value = '';
    continueTaboos.value = '';
    continueStatus.textContent = '';
    continueModal.style.display = 'flex';
  }

  // =============================================================
  //  续写：开始生成
  // =============================================================
  async function startContinuation() {
    if (!_currentDraftPath) {
      showToast('草稿路径丢失，请重新加载', 'error');
      return;
    }

    const numChapters = parseInt(continueChapters.value) || 3;
    if (numChapters < 1) { showToast('章节数至少为 1', 'error'); return; }

    const contextChapters = [];
    continueChapterList.querySelectorAll('input[type="checkbox"]:checked').forEach(cb => {
      contextChapters.push(parseInt(cb.value));
    });
    const insertAfter = parseInt(continueInsertAfter.value);

    continueStartBtn.disabled = true;
    continueStatus.textContent = '⏳ 正在启动续写...';
    continueModal.style.display = 'none';

    // 在阅览区显示续写进度
    const originalHtml = viewerContent.innerHTML;
    viewerContent.innerHTML = `
      <div style="text-align:center;padding:40px">
        <div><span class="spinner"></span></div>
        <p style="margin-top:16px;font-size:1.1rem;color:var(--text-secondary)" id="draft-cont-status">⏳ 正在续写...</p>
        <div class="progress-container" style="margin-top:16px">
          <div class="progress-bar">
            <div class="progress-fill" id="draft-cont-progress" style="width:0%"></div>
          </div>
          <div class="progress-text" id="draft-cont-msg">初始化...</div>
        </div>
      </div>`;

    try {
      const resp = await fetch('/api/novel/continue', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          novel_path: _currentDraftPath,
          num_chapters: numChapters,
          insert_after: insertAfter,
          context_chapters: contextChapters,
          user_guidance: continueGuidance.value.trim(),
          content_taboos: continueTaboos.value.trim(),
          llm_interface: 'OpenAI',
          llm_api_key: '',
          llm_base_url: '',
          llm_model: 'deepseek-v4-flash',
          llm_temperature: 0.7,
          llm_max_tokens: 8192,
          embedding_interface: 'OpenAI',
          embedding_api_key: '',
          embedding_base_url: '',
          embedding_model: 'text-embedding-ada-002',
        }),
      });

      if (!resp.ok) {
        const err = await resp.json().catch(() => ({}));
        throw new Error(err.detail || '续写启动失败');
      }

      // 读取 SSE 流
      const reader = resp.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';
      const progressFill = document.getElementById('draft-cont-progress');
      const progressMsg = document.getElementById('draft-cont-msg');
      const statusEl = document.getElementById('draft-cont-status');

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
            if (msg.type === 'progress' && progressFill && progressMsg) {
              progressFill.style.width = (msg.progress_pct || 0) + '%';
              progressMsg.textContent = msg.progress_msg || '';
            }
            if (msg.type === 'chapter_content' && statusEl) {
              statusEl.textContent = `✅ 第 ${msg.chapter} 章完成`;
            }
            if (msg.type === 'done') {
              if (statusEl) statusEl.textContent = `🎉 续写完成！共追加 ${msg.total_chapters || numChapters} 章`;
              showToast('✅ 续写完成！', 'success');
            }
            if (msg.type === 'error') {
              // 抛出到外层 catch（解析异常静默跳过，业务异常往上抛）
              throw new ContinuationError(msg.error || '续写出错');
            }
          } catch (e) {
            if (e instanceof ContinuationError) throw e;
            /* JSON 解析错误静默跳过 */
          }
        }
      }

      // 续写完成，重新加载草稿内容到阅览区
      setTimeout(() => {
        loadDraftIntoViewer(_currentDraftPath);
      }, 500);

    } catch (e) {
      showToast('续写失败: ' + e.message, 'error');
      // 恢复内容
      viewerContent.innerHTML = originalHtml;
    } finally {
      continueStartBtn.disabled = false;
    }
  }

  // =============================================================
  //  删除草稿
  // =============================================================
  async function deleteDraft(path, name) {
    if (!confirm(`确定要删除「${name}」吗？\n章节文件和摘要将永久丢失，此操作不可恢复。`)) return;

    try {
      const resp = await fetch('/api/novel/drafts/delete', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ path }),
      });
      const data = await resp.json();
      if (!data.success) throw new Error(data.detail || '删除失败');
      showToast(`🗑️ 已删除「${name}」`, 'success');
      loadDrafts();
    } catch (e) {
      showToast('删除失败: ' + e.message, 'error');
    }
  }

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

  // 转义 HTML 并将换行转为 <br>（不依赖 white-space CSS）
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
