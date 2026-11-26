const state = {
  user: null,
  authMode: 'login',
  tabs: [],
  activeTabId: null,
  pollTimer: null,
  tickTimer: null,
};

const el = {
  authView: document.getElementById('auth-view'),
  appView: document.getElementById('app-view'),
  authHeading: document.getElementById('auth-heading'),
  authSubtitle: document.getElementById('auth-subtitle'),
  tabLogin: document.getElementById('tab-login'),
  tabRegister: document.getElementById('tab-register'),
  authForm: document.getElementById('auth-form'),
  authUsername: document.getElementById('auth-username'),
  authPassword: document.getElementById('auth-password'),
  togglePassword: document.getElementById('toggle-password'),
  authError: document.getElementById('auth-error'),
  authSubmit: document.getElementById('auth-submit'),

  activeSummary: document.getElementById('active-summary'),
  userDisplay: document.getElementById('user-display'),
  btnLogout: document.getElementById('btn-logout'),
  btnOpenCreate: document.getElementById('btn-open-create'),
  btnEmptyCreate: document.getElementById('btn-empty-create'),
  emptyState: document.getElementById('empty-state'),
  tabsGrid: document.getElementById('tabs-grid'),

  createDialog: document.getElementById('create-dialog'),
  createForm: document.getElementById('create-form'),
  newTabName: document.getElementById('new-tab-name'),
  createError: document.getElementById('create-error'),

  configDialog: document.getElementById('config-dialog'),
  configForm: document.getElementById('config-form'),
  configTitle: document.getElementById('config-dialog-title'),
  configStatusMeta: document.getElementById('config-status-meta'),
  cfgName: document.getElementById('cfg-name'),
  cfgTokens: document.getElementById('cfg-tokens'),
  cfgChannels: document.getElementById('cfg-channels'),
  cfgDelay: document.getElementById('cfg-delay'),
  cfgBurst: document.getElementById('cfg-burst'),
  cfgFile: document.getElementById('cfg-file'),
  cfgMessage: document.getElementById('cfg-message'),
  cfgStats: document.getElementById('cfg-stats'),
  cfgLogs: document.getElementById('cfg-logs'),
  configError: document.getElementById('config-error'),
  btnCfgToggle: document.getElementById('btn-cfg-toggle'),
};

function formatDuration(totalSeconds) {
  const s = Math.max(0, Math.floor(totalSeconds || 0));
  const hrs = String(Math.floor(s / 3600)).padStart(2, '0');
  const mins = String(Math.floor((s % 3600) / 60)).padStart(2, '0');
  const secs = String(s % 60).padStart(2, '0');
  return `${hrs}:${mins}:${secs}`;
}

async function api(url, options = {}) {
  const res = await fetch(url, {
    headers: { 'Content-Type': 'application/json', ...(options.headers || {}) },
    ...options,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    throw new Error(data.error || 'Có lỗi xảy ra');
  }
  return data;
}

// Fallback light-dismiss cho Safari khi closedby="any" chưa hỗ trợ
if (!('closedBy' in HTMLDialogElement.prototype)) {
  const outside = (e, dialog) => {
    const r = dialog.getBoundingClientRect();
    return e.clientX < r.left || e.clientX > r.right || e.clientY < r.top || e.clientY > r.bottom;
  };
  for (const dialog of document.querySelectorAll('dialog[closedby="any"]')) {
    let pressedOutside = false;
    dialog.addEventListener('pointerdown', (e) => {
      pressedOutside = outside(e, dialog);
    });
    dialog.addEventListener('pointerup', (e) => {
      if (pressedOutside && outside(e, dialog)) dialog.close();
    });
  }
}

document.querySelectorAll('[data-close-dialog]').forEach((btn) => {
  btn.addEventListener('click', () => {
    const id = btn.getAttribute('data-close-dialog');
    document.getElementById(id)?.close();
  });
});

function setAuthMode(mode) {
  state.authMode = mode;
  el.authError.textContent = '';
  const isLogin = mode === 'login';
  el.tabLogin.classList.toggle('is-active', isLogin);
  el.tabLogin.setAttribute('aria-selected', String(isLogin));
  el.tabRegister.classList.toggle('is-active', !isLogin);
  el.tabRegister.setAttribute('aria-selected', String(!isLogin));

  el.authHeading.textContent = isLogin ? 'Đăng nhập tài khoản' : 'Đăng ký tài khoản mới';
  el.authSubmit.textContent = isLogin ? 'Đăng nhập' : 'Đăng ký';
  el.authPassword.setAttribute('autocomplete', isLogin ? 'current-password' : 'new-password');
  el.authForm.setAttribute('action', isLogin ? '/api/login' : '/api/register');
}

el.tabLogin.addEventListener('click', () => setAuthMode('login'));
el.tabRegister.addEventListener('click', () => setAuthMode('register'));

el.togglePassword.addEventListener('click', () => {
  const shown = el.authPassword.type === 'text';
  el.authPassword.type = shown ? 'password' : 'text';
  el.togglePassword.setAttribute('aria-pressed', String(!shown));
  el.togglePassword.setAttribute('aria-label', shown ? 'Hiện mật khẩu' : 'Ẩn mật khẩu');
});

el.authForm.addEventListener('submit', async (e) => {
  e.preventDefault();
  el.authError.textContent = '';

  const username = el.authUsername.value.trim();
  const password = el.authPassword.value;
  if (username.length < 3) {
    el.authError.textContent = 'Tên đăng nhập phải từ 3 ký tự trở lên';
    el.authUsername.focus();
    return;
  }
  if (password.length < 4) {
    el.authError.textContent = 'Mật khẩu phải có ít nhất 4 ký tự';
    el.authPassword.focus();
    return;
  }

  el.authSubmit.disabled = true;
  try {
    const endpoint = state.authMode === 'login' ? '/api/login' : '/api/register';
    const data = await api(endpoint, {
      method: 'POST',
      body: JSON.stringify({ username, password }),
    });
    state.user = data.user;
    el.authPassword.value = '';
    enterWorkspace();
  } catch (err) {
    el.authError.textContent = err.message;
  } finally {
    el.authSubmit.disabled = false;
  }
});

el.btnLogout.addEventListener('click', async () => {
  await api('/api/logout', { method: 'POST' }).catch(() => {});
  state.user = null;
  state.tabs = [];
  stopTimers();
  showAuth();
});

function showAuth() {
  el.appView.hidden = true;
  el.authView.hidden = false;
  el.authUsername.focus();
}

async function enterWorkspace() {
  el.authView.hidden = true;
  el.appView.hidden = false;
  el.userDisplay.textContent = state.user.username;
  await fetchTabs();
  startTimers();
}

function startTimers() {
  stopTimers();
  state.pollTimer = setInterval(fetchTabs, 2000);
  state.tickTimer = setInterval(() => {
    for (const tab of state.tabs) {
      if (tab.running) {
        tab.elapsed_seconds = (tab.elapsed_seconds || 0) + 1;
        const timerNode = document.querySelector(`[data-timer-id="${tab.id}"]`);
        if (timerNode) {
          timerNode.textContent = formatDuration(tab.elapsed_seconds);
        }
      }
    }
  }, 1000);
}

function stopTimers() {
  if (state.pollTimer) clearInterval(state.pollTimer);
  if (state.tickTimer) clearInterval(state.tickTimer);
  state.pollTimer = null;
  state.tickTimer = null;
}

async function fetchTabs() {
  try {
    const data = await api('/api/tabs');
    state.tabs = data.tabs || [];
    renderTabs();
    if (el.configDialog.open && state.activeTabId !== null) {
      const active = state.tabs.find((t) => t.id === state.activeTabId);
      if (active) syncConfigRuntime(active);
    }
  } catch (err) {
    if (err.message.includes('đăng nhập')) {
      stopTimers();
      showAuth();
    }
  }
}

function renderTabs() {
  const runningCount = state.tabs.filter((t) => t.running).length;
  el.activeSummary.textContent = `${runningCount} tab đang chạy · ${state.tabs.length} tổng`;

  el.emptyState.hidden = state.tabs.length > 0;
  el.tabsGrid.hidden = state.tabs.length === 0;

  el.tabsGrid.innerHTML = '';
  for (const tab of state.tabs) {
    const card = document.createElement('article');
    card.className = `tab-card${tab.running ? ' is-running' : ''}`;

    const head = document.createElement('div');
    head.className = 'tab-card-head';

    const titleWrap = document.createElement('div');
    titleWrap.className = 'tab-title-wrap';
    const dot = document.createElement('span');
    dot.className = 'status-dot';
    dot.setAttribute('aria-hidden', 'true');
    const title = document.createElement('h2');
    title.className = 'tab-name';
    title.textContent = tab.name;
    titleWrap.append(dot, title);

    const badge = document.createElement('span');
    badge.className = `status-badge${tab.running ? ' is-running' : ''}`;
    badge.textContent = tab.running ? 'Đang treo' : 'Đã dừng';
    head.append(titleWrap, badge);

    const timerBlock = document.createElement('div');
    timerBlock.className = 'tab-timer-block';
    const tLabel = document.createElement('span');
    tLabel.className = 'timer-label';
    tLabel.textContent = 'Thời gian đã chạy';
    const tVal = document.createElement('span');
    tVal.className = 'timer-value mono';
    tVal.setAttribute('data-timer-id', String(tab.id));
    tVal.textContent = formatDuration(tab.elapsed_seconds);
    timerBlock.append(tLabel, tVal);

    const meta = document.createElement('div');
    meta.className = 'tab-meta mono';
    meta.textContent = `${tab.tokens_count} token · ${tab.channels_count} kênh · ${tab.success_count} gửi`;

    const actions = document.createElement('div');
    actions.className = 'tab-actions';

    const btnConfig = document.createElement('button');
    btnConfig.type = 'button';
    btnConfig.className = 'btn btn-secondary btn-config';
    btnConfig.textContent = 'Cấu hình';
    btnConfig.addEventListener('click', () => openConfigDialog(tab.id));

    const btnToggle = document.createElement('button');
    btnToggle.type = 'button';
    btnToggle.className = `btn ${tab.running ? 'btn-stop' : 'btn-run'}`;
    btnToggle.textContent = tab.running ? 'Dừng' : 'Chạy';
    btnToggle.addEventListener('click', () => toggleTab(tab.id, tab.running));

    const btnDel = document.createElement('button');
    btnDel.type = 'button';
    btnDel.className = 'icon-btn btn-danger-ghost';
    btnDel.setAttribute('aria-label', `Xóa tab ${tab.name}`);
    btnDel.innerHTML = `<svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M3 6h18"/><path d="M8 6V4h8v2"/><path d="M19 6l-1 14H6L5 6"/></svg>`;
    btnDel.addEventListener('click', () => deleteTab(tab.id));

    actions.append(btnConfig, btnToggle, btnDel);
    card.append(head, timerBlock, meta, actions);
    el.tabsGrid.appendChild(card);
  }
}

function openCreateDialog() {
  el.createError.textContent = '';
  el.newTabName.value = '';
  el.createDialog.showModal();
  el.newTabName.focus();
}

el.btnOpenCreate.addEventListener('click', openCreateDialog);
el.btnEmptyCreate.addEventListener('click', openCreateDialog);

el.createForm.addEventListener('submit', async (e) => {
  e.preventDefault();
  el.createError.textContent = '';
  const name = el.newTabName.value.trim();
  if (!name) {
    el.createError.textContent = 'Vui lòng nhập tên tab';
    el.newTabName.focus();
    return;
  }

  try {
    await api('/api/tabs', {
      method: 'POST',
      body: JSON.stringify({ name }),
    });
    el.createDialog.close();
    await fetchTabs();
  } catch (err) {
    el.createError.textContent = err.message;
  }
});

function openConfigDialog(tabId) {
  const tab = state.tabs.find((t) => t.id === tabId);
  if (!tab) return;

  state.activeTabId = tabId;
  el.configError.textContent = '';
  el.configTitle.textContent = `Cấu hình: ${tab.name}`;
  el.cfgName.value = tab.name;
  el.cfgTokens.value = tab.tokens_text || '';
  el.cfgChannels.value = tab.channels_text || '';
  el.cfgDelay.value = tab.delay ?? 0;
  el.cfgBurst.value = tab.burst_count ?? 1;
  el.cfgMessage.value = tab.message_text || '';
  el.cfgFile.value = '';

  syncConfigRuntime(tab);
  el.configDialog.showModal();
}

function syncConfigRuntime(tab) {
  el.configStatusMeta.textContent = tab.running ? 'Đang treo' : 'Đã dừng';
  el.configStatusMeta.className = `status-badge${tab.running ? ' is-running' : ''}`;
  el.btnCfgToggle.textContent = tab.running ? 'Dừng treo' : 'Bắt đầu treo';
  el.btnCfgToggle.className = `btn ${tab.running ? 'btn-stop' : 'btn-run'}`;
  el.cfgStats.textContent = `${tab.success_count} thành công · ${tab.fail_count} lỗi`;

  el.cfgLogs.innerHTML = '';
  if (!tab.logs || tab.logs.length === 0) {
    const empty = document.createElement('div');
    empty.className = 'log-empty';
    empty.textContent = 'Chưa có hoạt động nào';
    el.cfgLogs.appendChild(empty);
  } else {
    for (const item of tab.logs) {
      const row = document.createElement('div');
      row.className = `log-item ${item.level || 'info'}`;
      const ts = document.createElement('span');
      ts.className = 'log-ts';
      ts.textContent = item.ts;
      const msg = document.createElement('span');
      msg.className = 'log-msg';
      msg.textContent = item.text;
      row.append(ts, msg);
      el.cfgLogs.appendChild(row);
    }
    el.cfgLogs.scrollTop = el.cfgLogs.scrollHeight;
  }
}

el.cfgFile.addEventListener('change', async (e) => {
  const file = e.target.files?.[0];
  if (!file) return;
  const text = await file.text();
  el.cfgMessage.value = text.trim();
});

async function saveActiveConfig() {
  if (state.activeTabId === null) return null;
  const payload = {
    name: el.cfgName.value.trim(),
    tokens_text: el.cfgTokens.value,
    channels_text: el.cfgChannels.value,
    delay: parseFloat(el.cfgDelay.value || '0'),
    burst_count: parseInt(el.cfgBurst.value || '1', 10),
    message_text: el.cfgMessage.value,
  };
  const data = await api(`/api/tabs/${state.activeTabId}`, {
    method: 'PUT',
    body: JSON.stringify(payload),
  });
  await fetchTabs();
  return data.tab;
}

el.configForm.addEventListener('submit', async (e) => {
  e.preventDefault();
  el.configError.textContent = '';
  try {
    const saved = await saveActiveConfig();
    if (saved) el.configTitle.textContent = `Cấu hình: ${saved.name}`;
  } catch (err) {
    el.configError.textContent = err.message;
  }
});

el.btnCfgToggle.addEventListener('click', async () => {
  if (state.activeTabId === null) return;
  el.configError.textContent = '';
  const tab = state.tabs.find((t) => t.id === state.activeTabId);
  if (!tab) return;

  try {
    if (!tab.running) {
      await saveActiveConfig();
      await api(`/api/tabs/${tab.id}/start`, { method: 'POST' });
    } else {
      await api(`/api/tabs/${tab.id}/stop`, { method: 'POST' });
    }
    await fetchTabs();
  } catch (err) {
    el.configError.textContent = err.message;
  }
});

async function toggleTab(tabId, isRunning) {
  try {
    const action = isRunning ? 'stop' : 'start';
    await api(`/api/tabs/${tabId}/${action}`, { method: 'POST' });
    await fetchTabs();
  } catch (err) {
    openConfigDialog(tabId);
    el.configError.textContent = err.message;
  }
}

async function deleteTab(tabId) {
  try {
    await api(`/api/tabs/${tabId}`, { method: 'DELETE' });
    if (state.activeTabId === tabId) {
      el.configDialog.close();
      state.activeTabId = null;
    }
    await fetchTabs();
  } catch (err) {
    console.error(err);
  }
}

async function bootstrap() {
  try {
    const data = await api('/api/me');
    if (data.user) {
      state.user = data.user;
      enterWorkspace();
      return;
    }
  } catch {
    // ignore
  }
  showAuth();
}

bootstrap();
