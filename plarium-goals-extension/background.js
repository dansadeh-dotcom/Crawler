// ─── Message router ───────────────────────────────────────────────────────────

const ALLOWED_ORIGIN  = 'https://plarium.rocks';
const ALLOWED_PATH_RE = /^\/cabinet\/up\/goals\/subdivisions\//;
const MAX_TSV_BYTES   = 512_000; // 512 KB
const MAX_TITLE_LEN   = 200;

chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
  // ── Schema validation ────────────────────────────────────────────────────
  if (
    typeof request !== 'object' || request === null ||
    request.action !== 'openAndPaste' ||
    typeof request.tsv   !== 'string' ||
    typeof request.title !== 'string' ||
    request.tsv.length   > MAX_TSV_BYTES ||
    request.title.length > MAX_TITLE_LEN
  ) {
    return; // silently ignore malformed messages
  }

  // ── Sender / origin validation ───────────────────────────────────────────
  // Messages from content scripts include a sender.url; reject anything that
  // doesn't come from the expected Plarium Rocks subdivisions path.
  const senderUrl = sender?.url ?? '';
  let senderOriginOk = false;
  try {
    const u = new URL(senderUrl);
    senderOriginOk =
      u.origin === ALLOWED_ORIGIN && ALLOWED_PATH_RE.test(u.pathname);
  } catch (_) { /* invalid URL — reject */ }

  if (!senderOriginOk) {
    sendResponse({ error: 'Unauthorized sender.' });
    return true;
  }

  openSheetAndPaste(request.tsv, request.title)
    .then(()  => sendResponse({ success: true }))
    .catch(err => sendResponse({ error: err.message }));
  return true; // keep port open for async
});

// ─── Core flow ────────────────────────────────────────────────────────────────

async function openSheetAndPaste(tsv, title) {
  // Open a brand-new Google Sheet (sheets.new redirects to docs.google.com/spreadsheets/...)
  const tab = await chrome.tabs.create({ url: 'https://sheets.new' });

  // Wait until the tab has navigated to the actual spreadsheet URL and is fully loaded
  await waitForSheetReady(tab.id);

  // Inject the paste + rename script directly into the Sheets tab
  await chrome.scripting.executeScript({
    target: { tabId: tab.id },
    func: pasteAndRename,
    args: [tsv, title],
  });
}

// Resolves once the tab is on docs.google.com/spreadsheets and status === 'complete'
function waitForSheetReady(tabId) {
  return new Promise((resolve, reject) => {
    const timeout = setTimeout(() => {
      chrome.tabs.onUpdated.removeListener(listener);
      reject(new Error('Timed out waiting for Google Sheets to load.'));
    }, 30_000);

    function listener(updatedTabId, info, tab) {
      if (
        updatedTabId === tabId &&
        info.status === 'complete' &&
        tab.url?.includes('docs.google.com/spreadsheets')
      ) {
        chrome.tabs.onUpdated.removeListener(listener);
        clearTimeout(timeout);
        // Extra buffer for Sheets JS to initialise the grid
        setTimeout(resolve, 2500);
      }
    }

    chrome.tabs.onUpdated.addListener(listener);
  });
}

// ─── Injected into the Google Sheets tab ─────────────────────────────────────
// (runs as a plain function in the page context — no chrome.* APIs available here)

async function pasteAndRename(tsv, title) {
  const sleep = ms => new Promise(r => setTimeout(r, ms));

  // ── 1. Write TSV to clipboard ────────────────────────────────────────────
  await navigator.clipboard.writeText(tsv);

  // ── 2. Navigate to cell A1 via the Name Box ──────────────────────────────
  // Google Sheets name box has class "waffle-name-box" or aria-label "Name Box"
  const nameBox =
    document.querySelector('.waffle-name-box') ||
    document.querySelector('[aria-label="Name Box"]') ||
    document.querySelector('input[aria-label]');

  if (nameBox) {
    nameBox.focus();
    nameBox.select();
    // Use native setter so React/Closure Compiler picks up the change
    const nativeSetter = Object.getOwnPropertyDescriptor(
      window.HTMLInputElement.prototype, 'value'
    ).set;
    nativeSetter.call(nameBox, 'A1');
    nameBox.dispatchEvent(new Event('input', { bubbles: true }));
    nameBox.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', keyCode: 13, bubbles: true }));
    nameBox.dispatchEvent(new KeyboardEvent('keyup',  { key: 'Enter', keyCode: 13, bubbles: true }));
    await sleep(400);
  }

  // ── 3. Paste ─────────────────────────────────────────────────────────────
  // Try execCommand first (works when an editable area has focus)
  const pasted = document.execCommand('paste');

  if (!pasted) {
    // Fallback: dispatch a synthetic paste ClipboardEvent onto the active element
    const dt = new DataTransfer();
    dt.setData('text/plain', tsv);
    const ev = new ClipboardEvent('paste', { bubbles: true, cancelable: true, clipboardData: dt });
    (document.activeElement || document.body).dispatchEvent(ev);
  }

  await sleep(800);

  // ── 4. Rename the spreadsheet ─────────────────────────────────────────────
  // The title input is the first <input type="text"> in the Sheets toolbar
  const titleInput = document.querySelector('input[type="text"]');
  if (titleInput) {
    titleInput.focus();
    titleInput.click();
    await sleep(200);

    // Replace existing value using native setter (bypasses React)
    const nativeSetter = Object.getOwnPropertyDescriptor(
      window.HTMLInputElement.prototype, 'value'
    ).set;
    nativeSetter.call(titleInput, title);
    titleInput.dispatchEvent(new Event('input',  { bubbles: true }));
    titleInput.dispatchEvent(new Event('change', { bubbles: true }));
    titleInput.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', keyCode: 13, bubbles: true }));
    titleInput.dispatchEvent(new KeyboardEvent('keyup',   { key: 'Enter', keyCode: 13, bubbles: true }));
    await sleep(300);
    titleInput.blur();
  }
}
