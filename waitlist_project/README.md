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

## 報告與繳交資料

- `報告.md` 是依老師 3.1–3.12 項目整理的草稿。請填入實際設備資料，並補上真實截圖與操作紀錄；不要寫入員工密碼。
- 貼上並部署新版 `Code.gs` 後，在自己的 Apps Script `/exec` 網址後加入 `?action=log&key=員工密碼`，可查看加入、通知、入座與取消的事件。紀錄從試算表中已保存的時間戳記重建，不含顧客姓名或 E-mail；網址中的密碼不應出現在截圖或繳交檔案。
- `action=reset` 已加入本機 `Code.gs`；貼上並更新 Apps Script 部署後才會生效。作業及評分結束且確定不再需要紀錄後，可以在相同網址加上 `?action=reset&key=員工密碼&confirm=RESET` 清空試算表中的候位資料與事件紀錄。此動作無法復原；僅提供密碼但沒有 `confirm=RESET` 時不會清除。完成後再封存 Apps Script 部署。
- 將完整 JSON 輸出存為 `操作紀錄.json`，實際截圖放入 `證據/` 並完成報告後，可執行：

  ```powershell
  python waitlist_project/package_submission.py --student-id 學號 --name 姓名 --log waitlist_project/操作紀錄.json --screenshots waitlist_project/證據
  ```

  程式會檢查紀錄至少包含三次加入、一次通知與一次入座，並在 ZIP 中把前端 API 網址改成假值。仍須自行確認是三組不同顧客、截圖完整且已遮蔽個資。
