# data_structure

GitHub Pages 網站包含 QR Code 作業與餐廳候位系統。

## 網站

- [QR Code 作業](https://lucas950219.github.io/data_structure/qrcode.html)
- [顧客候位頁](https://lucas950219.github.io/data_structure/waitlist.html)
- [員工候位管理](https://lucas950219.github.io/data_structure/staff.html)

## 候位系統

F1–F11 對照與 Apps Script 部署步驟見 [waitlist_project/README.md](waitlist_project/README.md) 和 [waitlist_project/FEATURES.md](waitlist_project/FEATURES.md)。GitHub Pages 提供公開入口；Google Apps Script Web App 執行候位功能，使用私有 Google 試算表保存資料並透過 MailApp 寄送通知。

Pages workflow 優先讀取 GitHub repository variable GAS_WEB_APP_URL；若未設定，會使用 waitlist_project/config.js 的 gasWebAppUrl。完成 Apps Script Web App 部署後更新其中一處，再重新執行 Deploy to GitHub Pages workflow。

## GitHub Pages 設定

在 repo 的 Settings → Pages 將來源設為 GitHub Actions。推送到 main 後，.github/workflows/deploy-pages.yml 會發布 QR Code 與候位頁面。
