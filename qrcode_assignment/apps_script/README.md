# Google Apps Script 紀錄後端

這個後端把 GitHub Pages 的瀏覽事件與簽到資料寫入你的 Google 試算表。加上 `cloudflare-worker.js` 並完成部署後，會記錄公網 IP、伺服器時間、頁面網址、瀏覽器 User-Agent 和簽到內容。試算表留在你的 Google 帳號；Apps Script 的公開網址可接收新增資料，因此直接呼叫者可以偽造資料，IP 紀錄不可當成身分認證。

## 部署

1. 用你的 Google 帳號開啟 [Google Apps Script](https://script.google.com/home/start)，建立獨立專案。
2. 將 `Code.gs` 內容貼入編輯器；在「專案設定」啟用顯示 `appsscript.json`，並以本目錄的 manifest 取代它。
3. 在編輯器選擇 `setup` 並按「執行」。首次執行時授權建立私人試算表；完成後可在 Google 雲端硬碟搜尋「QR Code 作業紀錄」找到試算表。
4. 選「部署 → 新增部署 → 網頁應用程式」；執行身分選「我」，存取權選「任何人」。完成後複製以 `/exec` 結尾的網址。
5. 將 `cloudflare-worker.js` 複製到 Cloudflare Workers，確認其中的 Apps Script `/exec` 網址與本專案相同，並部署 Worker。
6. 將 Worker 的 `https://...workers.dev` 網址填入 `qrcode_assignment/config.json` 的 `backend_url`，重新產生 `site/index.html` 並部署 Pages。

如果試算表和 Apps Script 已經存在，更新 `Code.gs` 後，在「部署 → 管理部署」編輯原本的部署，選擇「新版本」再部署，可繼續使用原網址；不需要重新執行 `setup`。程式會保留原有六欄，並在第七欄新增「來源 IP」。如果第七欄已有其他標題，程式會回報錯誤以避免覆蓋。

Apps Script 的 `doGet` 是健康檢查；`doPost` 接收 `visit` 和 `checkin`。公開頁會在顯示告知後，記錄每次頁面瀏覽和簽到。若 Google 帳戶的管理政策不允許「任何人」使用網頁應用程式，匿名 GitHub Pages 訪客就無法送入紀錄。
