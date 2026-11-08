# data_structure

這個 repo 部署 QR Code 課程網站。網站來源是 `qrcode_assignment/site/index.html`，GitHub Pages 上的頁面名稱為 `qrcode.html`。

## GitHub Pages

1. 在 GitHub 的 `Lucas950219/data_structure` repo 開啟 **Settings → Pages**。
2. 將 **Build and deployment → Source** 設為 **GitHub Actions**。
3. 推送到 `main` 後，`.github/workflows/deploy-pages.yml` 會自動部署；也可以從 Actions 手動執行。

網址：<https://lucas950219.github.io/data_structure/qrcode.html>

repo 根目錄的 `index.html` 會導向作業頁。工作流程只發布這兩個 HTML 檔案。
