const SPREADSHEET_ID_PROPERTY = "QRCODE_LOG_SPREADSHEET_ID";
const LOG_SHEET_NAME = "訪客紀錄";
const LOG_HEADERS = ["伺服器時間", "事件", "頁面網址", "瀏覽器", "姓名", "留言", "來源 IP"];

/** Run once from the Apps Script editor and authorize the new private Sheet. */
function setup() {
  const properties = PropertiesService.getScriptProperties();
  const existingId = properties.getProperty(SPREADSHEET_ID_PROPERTY);
  if (existingId) {
    try {
      return SpreadsheetApp.openById(existingId).getUrl();
    } catch (_error) {
      properties.deleteProperty(SPREADSHEET_ID_PROPERTY);
    }
  }

  const spreadsheet = SpreadsheetApp.create("QR Code 作業紀錄");
  const sheet = spreadsheet.getSheets()[0];
  sheet.setName(LOG_SHEET_NAME);
  sheet.appendRow(LOG_HEADERS);
  sheet.setFrozenRows(1);
  properties.setProperty(SPREADSHEET_ID_PROPERTY, spreadsheet.getId());
  return spreadsheet.getUrl();
}

/** Health endpoint. It does not write a row. */
function doGet() {
  return jsonOutput_({ ok: true, service: "qrcode-assignment-log", ipLogging: true });
}

/** Accept page-view and check-in records from the public GitHub Pages page. */
function doPost(event) {
  try {
    const raw = event && event.parameter && event.parameter.payload
      ? event.parameter.payload
      : event && event.postData && event.postData.contents;
    const payload = JSON.parse(raw || "{}");
    if (!["visit", "checkin"].includes(payload.type)) {
      throw new Error("Unsupported event type.");
    }

    const row = [
      new Date(),
      payload.type,
      safeCell_(payload.pageUrl, 500),
      safeCell_(payload.userAgent, 300),
      payload.type === "checkin" ? safeCell_(payload.name, 50) : "",
      payload.type === "checkin" ? safeCell_(payload.message, 300) : "",
      safeCell_(payload.clientIp, 64)
    ];

    const lock = LockService.getScriptLock();
    lock.waitLock(10000);
    try {
      const sheet = getLogSheet_();
      const ipHeader = sheet.getRange(1, 7).getValue();
      if (ipHeader && ipHeader !== LOG_HEADERS[6]) {
        throw new Error("第七欄已經有其他標題，請先檢查試算表。");
      }
      if (!ipHeader) sheet.getRange(1, 7).setValue(LOG_HEADERS[6]);
      sheet.appendRow(row);
    } finally {
      lock.releaseLock();
    }
    return jsonOutput_({ ok: true, ipLogging: true });
  } catch (error) {
    return jsonOutput_({ ok: false, error: String(error && error.message || error) });
  }
}

function getLogSheet_() {
  const spreadsheetId = PropertiesService.getScriptProperties().getProperty(SPREADSHEET_ID_PROPERTY);
  if (!spreadsheetId) {
    throw new Error("請先在 Apps Script 編輯器執行 setup()。");
  }
  const spreadsheet = SpreadsheetApp.openById(spreadsheetId);
  let sheet = spreadsheet.getSheetByName(LOG_SHEET_NAME);
  if (!sheet) {
    sheet = spreadsheet.insertSheet(LOG_SHEET_NAME);
    sheet.appendRow(LOG_HEADERS);
    sheet.setFrozenRows(1);
  }
  return sheet;
}

function safeCell_(value, maxLength) {
  let text = String(value == null ? "" : value)
    .replace(/[\u0000-\u001f\u007f]/g, " ")
    .trim()
    .slice(0, maxLength);
  if (/^[=+\-@]/.test(text)) text = "'" + text;
  return text;
}

function jsonOutput_(value) {
  return ContentService
    .createTextOutput(JSON.stringify(value))
    .setMimeType(ContentService.MimeType.JSON);
}
