# 好好候位

顧客候位頁與員工管理頁的輕量候位系統。前端是 GitHub Pages 靜態頁；Python 標準函式庫 API 用 SQLite 保存 Queue。這次直接整合工作區既有的 QR 與 Gmail 作業：QR 產生沿用 `qrcode_assignment/qr_web.py`，SMTP 帳密載入與連線沿用 `gmail_assignment/gmail_auto.py`。

## 頁面

- 顧客候位頁：<https://lucas950219.github.io/data_structure/waitlist.html>
- 員工管理頁：<https://lucas950219.github.io/data_structure/staff.html>
- API 健康檢查：部署後的 API 網址加上 `/health`

Pages 部署 workflow 已加入這兩個頁面與 QR 圖；推送到 `main` 後會發布靜態檔案。要讓表單和 Queue 真正可用，還需把 Python API 部署到支援 HTTPS 與持久磁碟的主機。

## 本機執行

1. 將 `.env.example` 複製成 `.env`，設定 `APP_SECRET` 和 `WAITLIST_ADMIN_PASSWORD`。`APP_SECRET` 請用至少 32 個字元的隨機字串，可用 `python -c "import secrets; print(secrets.token_urlsafe(48))"` 產生。
2. Gmail 可用 `GMAIL_ADDRESS`、`GMAIL_APP_PASSWORD` 環境變數設定；本機也可沿用 `gmail_assignment/config.json`。環境變數優先。不要提交 `.env`、帳號密碼或 SQLite 資料庫。
3. 在 repo 根目錄執行 `python waitlist_project/server.py`。
4. 另開終端機執行 `python -m http.server 5500 --directory waitlist_project`。
5. 開啟 `http://127.0.0.1:5500/index.html`；員工頁為 `http://127.0.0.1:5500/staff.html`。

只有員工在管理頁按下「通知」時才會透過既有 Gmail helper 寄信；寄送成功後狀態才變為「已通知」。此工作階段沒有寄送任何實際郵件。

## 部署設定

Pages workflow 會讀取 GitHub repository variable `WAITLIST_API_URL`，並產生正式版 `config.js`。請將它設為 API 的 HTTPS base URL，例如 `https://waitlist-api.example.com`，不要加 `/api`。後端要設定：

- `APP_SECRET`、`WAITLIST_ADMIN_PASSWORD`
- `GMAIL_ADDRESS`、`GMAIL_APP_PASSWORD`（或部署時提供 Gmail helper 可讀取的設定檔）
- `PUBLIC_SITE_URL=https://lucas950219.github.io/data_structure/waitlist.html`
- `ALLOWED_ORIGINS=https://lucas950219.github.io`
- `DATABASE_PATH` 指向主機的持久磁碟，例如 `/var/data/waitlist.sqlite3`
- 主機要求的 `HOST=0.0.0.0` 與 `PORT`

Pages 不會執行 Python，也不會保存 SQLite，因此 API 與持久磁碟必須另行部署。API 尚未設定時，頁面會顯示連線提示，資料無法跨裝置同步。QR Code 目前指向上方顧客頁；若頁面網址不同，請更新 `.env` 的 `PUBLIC_SITE_URL`，再執行 `qrcode_assignment/.venv/Scripts/python.exe waitlist_project/build_qr.py` 重新產圖。

後端可用 repo 根目錄的 Docker build context 建置：`docker build -f waitlist_project/Dockerfile -t waitlist-api .`。部署時需掛載持久磁碟到 `/var/lib/waitlist`，並設定上述環境變數；容器不含任何密碼或 Gmail 設定檔。

## 資料與分流

- 1–2 位自動進入 2 人桌 Queue；3–4 位進入 4 人桌 Queue。
- SQLite 可保存超過 50 組紀錄；候位號碼依日期和桌型分開遞增。歷史紀錄保留供統計，不會再算入目前 Queue。
- 顧客進度使用簽章 token 查詢，員工登入使用短效 HMAC token；員工 token 放在分頁工作階段，登出時清除。
- 平均等候時間以當日已入座紀錄計算；放棄率目前以當日取消組數除以當日總候位組數計算。
- 通知郵件含顧客自助取消連結；候位頁也可自行取消。個人資料只在受保護的員工 API 回傳，公開摘要不含姓名或 E-mail。

詳細 F1–F11 對照見 [`FEATURES.md`](FEATURES.md)。手機實掃、正式 Pages 發布、雲端 API 與實際 Gmail 寄送仍需在對應裝置和帳號環境完成。
