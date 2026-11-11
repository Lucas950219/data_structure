# data_structure

GitHub Pages 網站包含 QR Code 作業與餐廳候位系統。

## 網站

- [QR Code 作業](https://lucas950219.github.io/data_structure/qrcode.html)
- [顧客候位頁](https://lucas950219.github.io/data_structure/waitlist.html)
- [員工候位管理](https://lucas950219.github.io/data_structure/staff.html)

## 候位系統

前端與 F1–F11 對照見 [`waitlist_project/README.md`](waitlist_project/README.md) 和 [`waitlist_project/FEATURES.md`](waitlist_project/FEATURES.md)。候位 API 使用 Python 標準函式庫和 SQLite，Gmail 與 QR Code 功能沿用既有作業中的 helper。

GitHub Actions workflow 會部署靜態頁面。請在 repository variable 設定 `WAITLIST_API_URL` 指向已部署的 HTTPS API；Pages 本身不會執行 Python 或保存 SQLite。API 的管理密碼、`APP_SECRET`、Gmail 應用程式密碼及資料庫持久磁碟需在後端主機設定。

## GitHub Pages 設定

在 GitHub repo 的 **Settings → Pages** 將來源設為 **GitHub Actions**。推送到 `main` 後，`.github/workflows/deploy-pages.yml` 會更新 QR Code、候位頁和員工頁。
