const APP_TZ = 'Asia/Taipei';
const QUEUE_SHEET_NAME = 'Queue';
const QUEUE_HEADERS = [
  'id', 'queueDay', 'ticket', 'name', 'gender', 'email', 'partySize',
  'tableType', 'createdAt', 'status', 'notifiedAt', 'seatedAt', 'cancelledAt'
];
const ACTIVE_STATUSES = ['waiting', 'notifying', 'notified'];

function doGet(e) {
  const view = e && e.parameter && e.parameter.view === 'staff' ? 'Staff' : 'Customer';
  const title = view === 'Staff' ? '員工候位管理｜好好候位' : '好好候位｜線上候位';
  return HtmlService.createTemplateFromFile(view)
    .evaluate()
    .setTitle(title)
    .setXFrameOptionsMode(HtmlService.XFrameOptionsMode.ALLOWALL);
}

function include_(fileName) {
  return HtmlService.createHtmlOutputFromFile(fileName).getContent();
}

/** Run once from the Apps Script editor. It creates the private queue spreadsheet and signing key. */
function setupWaitlist_() {
  const props = PropertiesService.getScriptProperties();
  let sheetId = props.getProperty('WAITLIST_SHEET_ID');
  if (!sheetId) {
    const spreadsheet = SpreadsheetApp.create('好好候位 Queue 資料');
    const sheet = spreadsheet.getSheets()[0];
    sheet.setName(QUEUE_SHEET_NAME);
    sheet.getRange(1, 1, 1, QUEUE_HEADERS.length).setValues([QUEUE_HEADERS]);
    sheet.setFrozenRows(1);
    sheetId = spreadsheet.getId();
    props.setProperty('WAITLIST_SHEET_ID', sheetId);
  }
  if (!props.getProperty('TOKEN_SECRET')) {
    props.setProperty('TOKEN_SECRET', Utilities.getUuid() + Utilities.getUuid());
  }
  const spreadsheetUrl = SpreadsheetApp.openById(sheetId).getUrl();
  console.log('Waitlist is ready. Queue spreadsheet: ' + spreadsheetUrl);
  return spreadsheetUrl;
}

/** Run once from the Apps Script editor to grant this project permission to send mail. */
function authorizeGmail_() {
  const remaining = MailApp.getRemainingDailyQuota();
  console.log('Mail authorization is ready. Daily recipients remaining: ' + remaining);
}

/** RPC entry point. Every route is validated here; private helpers end in an underscore. */
function apiRpc(request) {
  try {
    return { ok: true, data: route_(request || {}) };
  } catch (error) {
    return {
      ok: false,
      status: Number(error.httpStatus) || 500,
      error: error.code || 'server_error',
      message: error.message || '系統發生錯誤，請稍後再試。'
    };
  }
}

function route_(request) {
  const method = String(request.method || 'GET').toUpperCase();
  const fullPath = String(request.path || '/');
  const queryAt = fullPath.indexOf('?');
  const path = queryAt < 0 ? fullPath : fullPath.slice(0, queryAt);
  const params = queryAt < 0 ? {} : parseQuery_(fullPath.slice(queryAt + 1));
  const body = request.body && typeof request.body === 'object' ? request.body : {};
  const auth = String(request.authorization || '');

  if (method === 'GET' && path === '/api/queue/summary') return queueSummary_();
  if (method === 'POST' && path === '/api/queue') return queueJoin_(body);
  if (method === 'GET' && path === '/api/queue/status') return queueStatus_(auth);
  if (method === 'POST' && path === '/api/queue/cancel') return queueCancel_(String(body.token || auth));
  if (method === 'POST' && path === '/api/staff/login') return staffLogin_(String(body.password || ''));

  if (path === '/api/staff/queue' && method === 'GET') {
    requireStaff_(auth);
    return staffQueue_(params.lane || 'all');
  }
  if (path === '/api/staff/stats' && method === 'GET') {
    requireStaff_(auth);
    return staffStats_();
  }

  const action = path.match(/^\/api\/staff\/entries\/([^/]+)\/(notify|seat|cancel)$/);
  if (action && method === 'POST') {
    requireStaff_(auth);
    if (action[2] === 'notify') return staffNotify_(action[1]);
    return staffChangeStatus_(action[1], action[2]);
  }
  throw apiError_(404, 'not_found', '找不到這個候位功能。');
}

function queueJoin_(body) {
  const name = String(body.name || '').trim();
  const gender = String(body.gender || '').trim();
  const email = String(body.email || '').trim().toLowerCase();
  const partySize = Number(body.partySize);
  if (!name || name.length > 60) throw apiError_(400, 'invalid_name', '姓名必填，且不可超過 60 個字。');
  if (['女', '男', '其他', '不透露'].indexOf(gender) < 0) {
    throw apiError_(400, 'invalid_gender', '請選擇有效的性別選項。');
  }
  if (!Number.isInteger(partySize) || partySize < 1 || partySize > 4) {
    throw apiError_(400, 'invalid_party_size', '用餐人數請選擇 1 到 4 位。');
  }
  if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email) || email.length > 254) {
    throw apiError_(400, 'invalid_email', '請輸入有效的 E-mail。');
  }
  if (body.consent !== true) throw apiError_(400, 'consent_required', '請先同意使用候位資料。');

  const lock = LockService.getScriptLock();
  lock.waitLock(10000);
  try {
    const entries = getEntries_();
    const day = today_();
    const tableType = partySize <= 2 ? '2p' : '4p';
    const sequence = entries.filter(entry => entry.queueDay === day && entry.tableType === tableType).length + 1;
    const ticket = (tableType === '2p' ? 'T-' : 'F-') + String(sequence).padStart(3, '0');
    const entry = {
      id: Utilities.getUuid(), queueDay: day, ticket, name, gender, email, partySize,
      tableType, createdAt: new Date().toISOString(), status: 'waiting',
      notifiedAt: '', seatedAt: '', cancelledAt: ''
    };
    appendEntry_(entry);
    entry.token = makeToken_('customer', { id: entry.id, exp: Date.now() + 30 * 24 * 60 * 60 * 1000 });
    return customerStatusFor_(entry, getEntries_());
  } finally {
    lock.releaseLock();
  }
}

function queueSummary_() {
  const active = getEntries_().filter(entry => entry.queueDay === today_() && ACTIVE_STATUSES.indexOf(entry.status) >= 0);
  const lanes = {
    '2p': active.filter(entry => entry.tableType === '2p').length,
    '4p': active.filter(entry => entry.tableType === '4p').length
  };
  return { lanes, queueSize: lanes['2p'] + lanes['4p'], updatedAt: new Date().toISOString() };
}

function queueStatus_(authorization) {
  const payload = verifyToken_(bearer_(authorization), 'customer');
  const entries = getEntries_();
  const entry = entries.find(item => item.id === String(payload.id));
  if (!entry) throw apiError_(404, 'entry_not_found', '找不到這筆候位資料。');
  return customerStatusFor_(entry, entries);
}

function customerStatusFor_(entry, entries) {
  const laneEntries = entries
    .filter(item => item.queueDay === entry.queueDay && item.tableType === entry.tableType && ACTIVE_STATUSES.indexOf(item.status) >= 0)
    .sort((a, b) => String(a.createdAt).localeCompare(String(b.createdAt)));
  const groupsAhead = entry.status === 'waiting' || entry.status === 'notifying' || entry.status === 'notified'
    ? laneEntries.filter(item => String(item.createdAt) < String(entry.createdAt)).length
    : 0;
  const result = {
    id: entry.id, ticket: entry.ticket, status: entry.status, tableType: entry.tableType,
    partySize: entry.partySize, queueSize: laneEntries.length, groupsAhead,
    estimatedWaitMinutes: groupsAhead * Number(PropertiesService.getScriptProperties().getProperty('WAIT_MIN_PER_GROUP') || 10),
    updatedAt: new Date().toISOString()
  };
  if (entry.token) result.token = entry.token;
  return result;
}

function queueCancel_(token) {
  const payload = verifyToken_(token, 'customer');
  const lock = LockService.getScriptLock();
  lock.waitLock(10000);
  try {
    const entries = getEntries_();
    const entry = entries.find(item => item.id === String(payload.id));
    if (!entry) throw apiError_(404, 'entry_not_found', '找不到這筆候位資料。');
    if (entry.status === 'notifying') throw apiError_(409, 'notification_pending', '通知信正在寄送，請稍後再取消。');
    if (entry.status !== 'waiting' && entry.status !== 'notified' && entry.status !== 'cancelled') {
      throw apiError_(409, 'not_cancellable', '這筆候位已結束，無法取消。');
    }
    if (entry.status !== 'cancelled') updateEntry_(entry.id, { status: 'cancelled', cancelledAt: new Date().toISOString() });
    const updated = Object.assign({}, entry, { status: 'cancelled', cancelledAt: new Date().toISOString() });
    return customerStatusFor_(updated, getEntries_());
  } finally {
    lock.releaseLock();
  }
}

function staffLogin_(password) {
  const props = PropertiesService.getScriptProperties();
  const expected = props.getProperty('STAFF_PASSWORD') || '';
  if (!expected) throw apiError_(503, 'staff_password_missing', '請先在 Apps Script 專案設定中設定 STAFF_PASSWORD。');
  if (!constantTimeEquals_(password, expected)) throw apiError_(401, 'invalid_password', '員工密碼錯誤。');
  return { token: makeToken_('staff', { role: 'staff', exp: Date.now() + 8 * 60 * 60 * 1000 }), expiresInSeconds: 8 * 60 * 60 };
}

function requireStaff_(authorization) {
  verifyToken_(bearer_(authorization), 'staff');
}

function staffQueue_(lane) {
  if (['all', '2p', '4p'].indexOf(lane) < 0) lane = 'all';
  const entries = getEntries_()
    .filter(entry => entry.queueDay === today_() && ACTIVE_STATUSES.indexOf(entry.status) >= 0)
    .filter(entry => lane === 'all' || entry.tableType === lane)
    .sort((a, b) => String(a.createdAt).localeCompare(String(b.createdAt)))
    .map(entry => Object.assign({}, entry, {
      waitMinutes: Math.max(0, Math.floor((Date.now() - new Date(entry.createdAt).getTime()) / 60000))
    }));
  return { entries, updatedAt: new Date().toISOString() };
}

function staffStats_() {
  const todayEntries = getEntries_().filter(entry => entry.queueDay === today_());
  const seated = todayEntries.filter(entry => entry.status === 'seated' && entry.seatedAt);
  const waits = seated.map(entry => Math.max(0, (new Date(entry.seatedAt).getTime() - new Date(entry.createdAt).getTime()) / 60000));
  const cancelled = todayEntries.filter(entry => entry.status === 'cancelled').length;
  return {
    totalToday: todayEntries.length,
    activeTotal: todayEntries.filter(entry => ACTIVE_STATUSES.indexOf(entry.status) >= 0).length,
    averageWaitMinutes: waits.length ? Math.round(waits.reduce((sum, value) => sum + value, 0) / waits.length) : null,
    abandonmentRate: todayEntries.length ? Math.round(cancelled * 1000 / todayEntries.length) / 10 : 0,
    cancelled
  };
}

function staffNotify_(id) {
  let entry;
  const lock = LockService.getScriptLock();
  lock.waitLock(10000);
  try {
    const entries = getEntries_();
    entry = entries.find(item => item.id === String(id) && item.queueDay === today_());
    if (!entry) throw apiError_(404, 'entry_not_found', '找不到這筆候位資料。');
    if (entry.status !== 'waiting') throw apiError_(409, 'invalid_status', '只有候位中的顧客可以通知。');
    updateEntry_(entry.id, { status: 'notifying' });
  } finally {
    lock.releaseLock();
  }

  try {
    const props = PropertiesService.getScriptProperties();
    const publicUrl = props.getProperty('PUBLIC_SITE_URL') || 'https://lucas950219.github.io/data_structure/waitlist.html';
    const cancelUrl = publicUrl + '#cancel=' + encodeURIComponent(makeToken_('customer', { id: entry.id, exp: Date.now() + 30 * 24 * 60 * 60 * 1000 }));
    const subject = '候位通知：' + entry.ticket + ' 即將安排入座';
    const plain = entry.name + ' 您好，候位號碼 ' + entry.ticket + ' 即將安排入座，請盡快回到櫃檯。若不再候位，可使用此連結取消：' + cancelUrl;
    const html = '<p>' + escapeHtml_(entry.name) + ' 您好，</p><p>候位號碼 <strong>' + escapeHtml_(entry.ticket) + '</strong> 即將安排入座，請盡快回到櫃檯。</p><p>若不再候位，可<a href="' + escapeHtml_(cancelUrl) + '">點此取消候位</a>。</p>';
    MailApp.sendEmail(entry.email, subject, plain, { htmlBody: html, name: '好好候位' });
  } catch (error) {
    updateEntry_(entry.id, { status: 'waiting' });
    throw apiError_(502, 'email_send_failed', 'Gmail 寄送失敗，候位狀態已恢復；請檢查 Apps Script Gmail 授權。');
  }

  const notifyLock = LockService.getScriptLock();
  notifyLock.waitLock(10000);
  try {
    updateEntry_(entry.id, { status: 'notified', notifiedAt: new Date().toISOString() });
  } finally {
    notifyLock.releaseLock();
  }
  return { ok: true, status: 'notified', message: '通知郵件已寄出。' };
}

function staffChangeStatus_(id, action) {
  const status = action === 'seat' ? 'seated' : 'cancelled';
  const timestampField = action === 'seat' ? 'seatedAt' : 'cancelledAt';
  const lock = LockService.getScriptLock();
  lock.waitLock(10000);
  try {
    const entry = getEntries_().find(item => item.id === String(id) && item.queueDay === today_());
    if (!entry) throw apiError_(404, 'entry_not_found', '找不到這筆候位資料。');
    if (entry.status !== 'waiting' && entry.status !== 'notified') {
      throw apiError_(409, 'invalid_status', '這筆候位目前無法執行該操作。');
    }
    const changedAt = new Date().toISOString();
    const patch = { status };
    patch[timestampField] = changedAt;
    updateEntry_(entry.id, patch);
    return { ok: true, status };
  } finally {
    lock.releaseLock();
  }
}

function getQueueSheet_() {
  const id = PropertiesService.getScriptProperties().getProperty('WAITLIST_SHEET_ID');
  if (!id) throw apiError_(503, 'setup_required', '請先在 Apps Script 編輯器執行 setupWaitlist_。');
  const spreadsheet = SpreadsheetApp.openById(id);
  let sheet = spreadsheet.getSheetByName(QUEUE_SHEET_NAME);
  if (!sheet) {
    sheet = spreadsheet.insertSheet(QUEUE_SHEET_NAME);
    sheet.getRange(1, 1, 1, QUEUE_HEADERS.length).setValues([QUEUE_HEADERS]);
    sheet.setFrozenRows(1);
  }
  return sheet;
}

function getEntries_() {
  const sheet = getQueueSheet_();
  const lastRow = sheet.getLastRow();
  if (lastRow < 2) return [];
  const values = sheet.getRange(1, 1, lastRow, QUEUE_HEADERS.length).getValues();
  const headers = values[0].map(String);
  const index = {};
  headers.forEach((name, i) => index[name] = i);
  return values.slice(1).map(row => {
    const item = {};
    QUEUE_HEADERS.forEach(key => item[key] = cellString_(row[index[key]]));
    item.partySize = Number(item.partySize) || 0;
    return item;
  }).filter(item => item.id);
}

function appendEntry_(entry) {
  const sheet = getQueueSheet_();
  sheet.appendRow(QUEUE_HEADERS.map(key => entry[key] == null ? '' : entry[key]));
}

function updateEntry_(id, patch) {
  const sheet = getQueueSheet_();
  const lastRow = sheet.getLastRow();
  if (lastRow < 2) throw apiError_(404, 'entry_not_found', '找不到這筆候位資料。');
  const ids = sheet.getRange(2, 1, lastRow - 1, 1).getDisplayValues();
  const offset = ids.findIndex(row => String(row[0]) === String(id));
  if (offset < 0) throw apiError_(404, 'entry_not_found', '找不到這筆候位資料。');
  const rowNumber = offset + 2;
  const current = sheet.getRange(rowNumber, 1, 1, QUEUE_HEADERS.length).getValues()[0];
  QUEUE_HEADERS.forEach((key, index) => {
    if (Object.prototype.hasOwnProperty.call(patch, key)) current[index] = patch[key];
  });
  sheet.getRange(rowNumber, 1, 1, QUEUE_HEADERS.length).setValues([current]);
}

function makeToken_(type, payload) {
  const secret = PropertiesService.getScriptProperties().getProperty('TOKEN_SECRET');
  if (!secret) throw apiError_(503, 'setup_required', '請先執行 setupWaitlist_ 初始化簽章金鑰。');
  const body = base64Url_(JSON.stringify(Object.assign({ typ: type }, payload)));
  return body + '.' + hmac_(body, secret);
}

function verifyToken_(token, expectedType) {
  const parts = String(token || '').split('.');
  if (parts.length !== 2) throw apiError_(401, 'invalid_token', '登入或候位連結已失效，請重新操作。');
  const secret = PropertiesService.getScriptProperties().getProperty('TOKEN_SECRET') || '';
  if (!secret || !constantTimeEquals_(parts[1], hmac_(parts[0], secret))) {
    throw apiError_(401, 'invalid_token', '登入或候位連結已失效，請重新操作。');
  }
  let payload;
  try { payload = JSON.parse(Utilities.newBlob(decodeBase64Url_(parts[0])).getDataAsString()); }
  catch (error) { throw apiError_(401, 'invalid_token', '登入或候位連結已失效，請重新操作。'); }
  if (payload.typ !== expectedType || !payload.exp || Number(payload.exp) < Date.now()) {
    throw apiError_(401, 'invalid_token', '登入或候位連結已失效，請重新操作。');
  }
  return payload;
}

function base64Url_(value) {
  return Utilities.base64EncodeWebSafe(value, Utilities.Charset.UTF_8).replace(/=+$/, '');
}

function decodeBase64Url_(value) {
  const padding = '='.repeat((4 - (value.length % 4)) % 4);
  return Utilities.base64DecodeWebSafe(value + padding);
}

function hmac_(value, secret) {
  return Utilities.base64EncodeWebSafe(Utilities.computeHmacSha256Signature(value, secret)).replace(/=+$/, '');
}

function parseQuery_(query) {
  const result = {};
  query.split('&').forEach(pair => {
    if (!pair) return;
    const parts = pair.split('=');
    const key = decodeURIComponent(parts.shift().replace(/\+/g, ' '));
    result[key] = decodeURIComponent(parts.join('=').replace(/\+/g, ' '));
  });
  return result;
}

function bearer_(authorization) {
  return String(authorization || '').replace(/^Bearer\s+/i, '').trim();
}

function today_() {
  return Utilities.formatDate(new Date(), APP_TZ, 'yyyy-MM-dd');
}

function cellString_(value) {
  if (value instanceof Date) return value.toISOString();
  return value == null ? '' : String(value);
}

function constantTimeEquals_(left, right) {
  left = String(left || '');
  right = String(right || '');
  let difference = left.length ^ right.length;
  const length = Math.max(left.length, right.length);
  for (let i = 0; i < length; i++) difference |= (left.charCodeAt(i) || 0) ^ (right.charCodeAt(i) || 0);
  return difference === 0;
}

function escapeHtml_(value) {
  return String(value).replace(/[&<>"']/g, character => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[character]);
}

function apiError_(status, code, message) {
  const error = new Error(message);
  error.httpStatus = status;
  error.code = code;
  return error;
}
