// ─── Constants ───────────────────────────────────────────────────────────────

const GOAL_NAME_SELECTOR = '.sc-gfu49y-0.sc-BQMaI';
const BTN_ID = 'plarium-goals-download-btn';

// ─── Button injection ─────────────────────────────────────────────────────────

function injectButton() {
  if (document.getElementById(BTN_ID)) return;

  // Wait for the Statistics nav tab — it's the last tab before our button's target spot
  const observer = new MutationObserver(() => {
    const statsLink = Array.from(document.querySelectorAll('a'))
      .find(a => a.href?.includes('cabinet/up/statistics'));

    if (statsLink && !document.getElementById(BTN_ID)) {
      observer.disconnect();
      insertButton(statsLink);
    }
  });

  observer.observe(document.body, { childList: true, subtree: true });
}

function insertButton(statsLink) {
  const btn = document.createElement('button');
  btn.id = BTN_ID;
  btn.textContent = '📊 Download to Sheet';
  btn.style.cssText = `
    background: #1a73e8;
    color: #fff;
    border: none;
    padding: 6px 14px;
    border-radius: 20px;
    cursor: pointer;
    font-size: 13px;
    font-family: inherit;
    font-weight: 500;
    margin-left: 16px;
    white-space: nowrap;
    transition: background 0.2s;
    align-self: center;
  `;
  btn.addEventListener('mouseenter', () => (btn.style.background = '#1558b0'));
  btn.addEventListener('mouseleave', () => (btn.style.background = '#1a73e8'));
  btn.addEventListener('click', handleDownload);

  // Walk up from the Statistics <a> to find its tab item — the direct child
  // of the tabs row that also contains "Evaluation", "Subdivision goals", etc.
  let tabItem = statsLink;
  for (let i = 0; i < 8; i++) {
    tabItem = tabItem.parentElement;
    if (!tabItem) break;
    const parent = tabItem.parentElement;
    if (parent?.innerText?.includes('Evaluation') && parent?.innerText?.includes('Statistics')) {
      // tabItem is the Statistics tab element; parent is the tabs row container
      parent.insertBefore(btn, tabItem.nextSibling);
      return;
    }
  }

  // Fallback: append near "Add goals" if the nav structure changes
  const addGoalsEl = Array.from(document.querySelectorAll('button, div'))
    .find(el => el.innerText?.trim() === 'Add goals');
  if (addGoalsEl) addGoalsEl.parentElement.appendChild(btn);
}

// Re-inject if React re-renders remove the button (e.g. on filter changes)
const pageObserver = new MutationObserver(() => {
  if (!document.getElementById(BTN_ID)) injectButton();
});
pageObserver.observe(document.body, { childList: true, subtree: true });

// ─── Goal extraction ──────────────────────────────────────────────────────────

function findRowForGoalEl(goalEl) {
  let node = goalEl;
  for (let i = 0; i < 10; i++) {
    node = node.parentElement;
    if (!node) break;
    if (node.getBoundingClientRect().width > 800) return node;
  }
  return null;
}

async function waitForPanel(expectedSubstring, timeoutMs = 5000) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    for (const div of document.querySelectorAll('div')) {
      const text = div.innerText || '';
      if (
        text.includes('Expected results or KPIs') &&
        text.includes(expectedSubstring) &&
        text.length < 4000
      ) {
        return text.trim();
      }
    }
    await sleep(200);
  }
  return null;
}

function parsePanel(raw) {
  const lines = raw.split('\n').map(l => l.trim()).filter(Boolean);
  const goal = lines[1] || '';

  const kpiStart  = lines.findIndex(l => l === 'Expected results or KPIs');
  const coreStart = lines.findIndex(l => l === 'Core initiatives');
  const statusIdx = lines.findIndex((l, i) =>
    i > Math.max(kpiStart, coreStart) &&
    ['Plan', 'Delayed', 'Done', 'In Progress', 'On Hold'].includes(l)
  );
  const dueDateIdx = lines.findIndex(l => l === 'Due date');

  const kpis = kpiStart >= 0
    ? lines.slice(kpiStart + 1, coreStart >= 0 ? coreStart : statusIdx).join('\n')
    : '';
  const initiatives = coreStart >= 0
    ? lines.slice(coreStart + 1, statusIdx >= 0 ? statusIdx : dueDateIdx).join('\n')
    : '';
  const status  = statusIdx  >= 0 ? lines[statusIdx]      : '';
  const dueDate = dueDateIdx >= 0 ? lines[dueDateIdx + 1] : '';

  return { goal, dueDate, status, kpis, initiatives };
}

async function extractAllGoals(onProgress) {
  const goalEls = Array.from(document.querySelectorAll(GOAL_NAME_SELECTOR));
  const results = [];

  for (let i = 0; i < goalEls.length; i++) {
    onProgress(`Extracting goal ${i + 1} / ${goalEls.length}…`);

    const row = findRowForGoalEl(goalEls[i]);
    if (!row) continue;

    row.scrollIntoView({ behavior: 'smooth', block: 'center' });
    await sleep(300);

    row.querySelector('svg')?.parentElement?.click();

    const firstWords = goalEls[i].innerText.substring(0, 25);
    const rawPanel = await waitForPanel(firstWords);

    results.push(rawPanel ? parsePanel(rawPanel) : {
      goal: goalEls[i].innerText.trim(),
      dueDate: '', status: '', kpis: '', initiatives: '',
    });
  }

  // Close the last open panel
  Array.from(document.querySelectorAll('button'))
    .find(b => b.innerText?.trim() === 'Close')?.click();

  return results;
}

// ─── TSV builder ──────────────────────────────────────────────────────────────

function buildTsv(goals) {
  // Neutralize spreadsheet formula injection: if a value starts with =, +, -, or @
  // (ignoring leading whitespace/tabs), prepend an apostrophe so Sheets treats it as text.
  const neutralize = s => /^[\s\t]*[=+\-@]/.test(s) ? "'" + s : s;

  const esc = s => {
    const safe = neutralize(String(s == null ? '' : s));
    return (safe.includes('\t') || safe.includes('\n') || safe.includes('"'))
      ? '"' + safe.replace(/"/g, '""') + '"'
      : safe;
  };

  const rows = [
    ['#', 'Goal Name', 'Due Date', 'Status', 'KPIs / Expected Results', 'Core Initiatives'],
    ...goals.map((g, i) => [String(i + 1), g.goal, g.dueDate, g.status, g.kpis, g.initiatives]),
  ];

  return rows.map(r => r.map(esc).join('\t')).join('\n');
}

// ─── Download handler ─────────────────────────────────────────────────────────

async function handleDownload() {
  const btn = document.getElementById(BTN_ID);
  if (!btn) return;

  const setStatus = (msg, color = '#1a73e8') => {
    btn.textContent = msg;
    btn.style.background = color;
    btn.disabled = true;
  };

  try {
    setStatus('⏳ Extracting goals…');

    const goals = await extractAllGoals(msg => setStatus(`⏳ ${msg}`));
    if (!goals.length) throw new Error('No goals found on this page.');

    setStatus('📤 Opening Google Sheet…');

    const tsv = buildTsv(goals);

    const sheetTitle =
      document.title.replace('– Plarium UP – Workroom – Plarium Rocks', '').trim() ||
      'Subdivision Goals';

    const response = await chrome.runtime.sendMessage({
      action: 'openAndPaste',
      tsv,
      title: `${sheetTitle} ${new Date().getFullYear()}`,
    });

    if (response?.success) {
      setStatus('✅ Sheet opened!', '#188038');
      setTimeout(resetButton, 4000);
    } else {
      throw new Error(response?.error || 'Unknown error.');
    }
  } catch (err) {
    console.error('[Plarium Goals]', err);
    setStatus('❌ ' + err.message.substring(0, 60), '#c5221f');
    setTimeout(resetButton, 5000);
  }
}

function resetButton() {
  const btn = document.getElementById(BTN_ID);
  if (!btn) return;
  btn.textContent = '📊 Download to Google Sheet';
  btn.style.background = '#1a73e8';
  btn.disabled = false;
}

// ─── Helpers ──────────────────────────────────────────────────────────────────

const sleep = ms => new Promise(r => setTimeout(r, ms));

// ─── Init ─────────────────────────────────────────────────────────────────────

injectButton();
