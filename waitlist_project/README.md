# 好好候位

顧客與員工介面由 GitHub Pages 提供；Google Apps Script 處理候位、員工登入及 Gmail 通知，Queue 資料存放在私人 Google 試算表。

- 顧客頁：https://lucas950219.github.io/data_structure/waitlist.html
- 員工頁：https://lucas950219.github.io/data_structure/staff.html
- QR Code：`assets/waitlist-qr.png`

GitHub Pages 發布 `waitlist.html`、`staff.html`、`styles.css`、`app.js`、`staff.js`、`api.js` 與 `config.js`。`index.html` 會導向顧客頁；頁面透過 Apps Script Web App 與後端通訊。`apps_script` 裡的其他 HTML 檔是舊版備份；目前只需把 `Code.gs` 貼到 Apps Script。

## 設定 Google Apps Script

1. 開啟自己的 Apps Script 專案，將 `apps_script/Code.gs` 全部內容貼進 `Code.gs` 並儲存。
2. 在上方函式選單選擇 `setupWaitlist`，按執行並授權，建立私人 Queue 試算表與簽章金鑰。
3. 選擇 `authorizeGmail`，執行並依畫面授權寄信；通知會由部署者的 Google 帳號寄出。
4. 到「專案設定」的「指令碼屬性」新增：
   - `STAFF_PASSWORD`：自行設定的員工密碼。
   - `PUBLIC_SITE_URL`：`https://lucas950219.github.io/data_structure/waitlist.html`。
   - `WAIT_MIN_PER_GROUP`：每組預估等待分鐘，例如 `10`。
5. 在「部署 → 管理部署作業」編輯現有網頁應用程式，版本選「新版本」並部署；執行身分選「我」，存取權選「所有人」。若尚未部署，先新增網頁應用程式部署。每次修改程式後都要更新部署版本。
6. 開啟部署網址並加上 `?action=count`。初始化成功時會看到 `{"waiting":0}`（若已有候位，數字會不同）。還需要使用顧客及員工頁確認完整流程。

目前 `config.js` 已填入提供的 `/exec` 網址。若更新部署後網址改變，更新 `config.js` 再重新發布 Pages；若 `config.js` 未設定網址，workflow 才會使用 GitHub repository variable `GAS_WEB_APP_URL`。

## 補充

- `STAFF_PASSWORD` 留在 Apps Script 指令碼屬性，請勿放入 GitHub。雲端版使用 `MailApp`，不需上傳 Gmail App Password。
- 員工登入及操作由後端驗證；顧客以簽章 token 查詢或取消自己的候位。
- 1–2 位和 3–4 位分別進入 2 人桌、4 人桌的 Queue。F1–F11 對照見 `FEATURES.md`。
- 部署後需用手機掃 QR Code，並檢查加入、錯誤密碼、寄信、入座、取消與統計。
