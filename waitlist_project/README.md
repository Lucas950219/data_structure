# 好好候位

顧客候位與員工管理系統。顧客頁與員工頁由 GitHub Pages 提供入口，互動介面和後端由 Google Apps Script Web App 執行，Queue 資料保存在私有 Google 試算表。Apps Script 透過 google.script.run 呼叫伺服器函式，避免從 GitHub Pages 直接跨網域呼叫 Apps Script API。

## 公開頁面

- 顧客候位頁：https://lucas950219.github.io/data_structure/waitlist.html
- 員工管理頁：https://lucas950219.github.io/data_structure/staff.html
- 顧客 QR 圖：assets/waitlist-qr.png

GitHub Pages 使用外層入口頁載入 Apps Script Web App。Apps Script 部署完成後，請設定 GitHub repository variable GAS_WEB_APP_URL 為 Web App 的 HTTPS /exec 網址，然後重新執行 Pages workflow。若還沒設定，入口頁會顯示部署說明。

## Apps Script 部署

原始碼位於 apps_script/，.clasp.json 已指向作業提供的 Script ID。

1. 安裝 clasp 並登入：npm install -g @google/clasp，接著 clasp login。
2. 在 repo 根目錄執行 cd waitlist_project/apps_script，再執行 clasp push，把這個目錄同步到指定 Apps Script 專案。
3. 開啟老師提供的 Apps Script 專案，在編輯器選取並執行 setupWaitlist_，授權建立私有 Queue 試算表；再執行 authorizeGmail_ 並授權寄信。執行記錄會列出試算表網址與 Gmail 授權狀態。
4. 開啟「專案設定 → 指令碼屬性」，新增：
   - STAFF_PASSWORD：自行設定的員工密碼。
   - PUBLIC_SITE_URL：https://lucas950219.github.io/data_structure/waitlist.html
   - WAIT_MIN_PER_GROUP：例如 10。
   TOKEN_SECRET 與 WAITLIST_SHEET_ID 會由初始化函式建立，不要公開或刪除。
5. 選「部署 → 新增部署作業 → 網頁應用程式」：執行身分選「我」，存取權選「所有人」，部署並完成 Google Sheets 與 Gmail 授權。複製產生的 HTTPS /exec 網址。
6. 到 GitHub repo「Settings → Secrets and variables → Actions → Variables」新增 GAS_WEB_APP_URL，值填剛才的 /exec 網址；再到「Actions → Deploy to GitHub Pages → Run workflow」發布入口頁。

### Gmail 通知

Apps Script 使用 MailApp.sendEmail 從部署者的 Google 帳號寄信，並只要求寄信權限。第一次部署前執行 authorizeGmail_ 完成授權；雲端版不需要把 gmail_assignment/config.json 的 App Password 放進程式碼或 GitHub。config.json 仍可供原本的 Python Gmail 作業使用。

### 資料與安全

- Queue 試算表由初始化函式建立，預設保持私人，不要公開分享。
- 員工密碼只放在 Apps Script 指令碼屬性，不放在 Git。
- 公開摘要只回傳人數；個人資料須使用員工登入 token 才會回傳。顧客進度與取消使用簽章 token。
- 顧客 1–2 位進入 2 人桌 Queue，3–4 位進入 4 人桌 Queue；號碼按日期和桌型分開，不限制 50 組。
- 通知成功後才更新成「已通知」；取消、入座等歷史資料會留在試算表供統計。

## F1–F11

詳細功能對照與待完成的實機驗收見 FEATURES.md。

## Python 本機版本

server.py 保留為原本的本機測試 API，使用標準函式庫與 SQLite；正式雲端入口使用上方 Apps Script 專案。QR 產生沿用 qrcode_assignment/qr_web.py，Python Gmail helper 保留給既有 Gmail 作業使用。
