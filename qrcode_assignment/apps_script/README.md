# Google Apps Script 紀錄後端

這個小型後端把 GitHub Pages 的瀏覽事件與簽到資料集中寫入你的 Google 試算表。它記錄伺服器時間、頁面網址、瀏覽器 User-Agent，以及表單中的暱稱和留言；**不收集 IP**。試算表留在你的 Google 帳號，公開網頁只有新增資料的權限。

## 部署

1. 用你的 Google 帳號開啟 [Google Apps Script](https://script.google.com/home/start)，建立獨立專案。
2. 將 `Code.gs` 內容貼入編輯器；在「專案設定」啟用顯示 `appsscript.json`，並以本目錄的 manifest 取代它。
3. 在編輯器選擇 `setup` 並按「執行」。首次執行時授權建立私人試算表；完成後可在 Google 雲端硬碟搜尋「QR Code 作業紀錄」找到試算表。
4. 選「部署 → 新增部署 → 網頁應用程式」；執行身分選「我」，存取權選「任何人」。完成後複製以 `/exec` 結尾的網址。
5. 將 `/exec` 網址填入 `qrcode_assignment/config.json` 的 `backend_url`，重新產生 `site/index.html` 並部署 Pages。

Apps Script 的 `doGet` 是健康檢查；`doPost` 接收 `visit` 和 `checkin`。公開頁會在顯示告知後，記錄每次頁面瀏覽和簽到。若 Google 帳戶的管理政策不允許「任何人」使用網頁應用程式，匿名 GitHub Pages 訪客就無法送入紀錄。
