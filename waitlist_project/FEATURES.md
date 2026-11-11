# F1–F11 功能對照

| 編號 | 要求 | 實作位置 | 狀態／驗收備註 |
|---|---|---|---|
| F1 | 顧客頁與員工頁放在 GitHub Pages，以網址開啟 | `index.html`、`staff.html`；Pages workflow 發布為 `/waitlist.html`、`/staff.html` | workflow 已準備；需推送並設定 `WAITLIST_API_URL` 才能連線。 |
| F2 | 顧客掃 QR Code 進入候位網頁（手機測試） | `assets/waitlist-qr.png` 由既有 `qrcode_assignment/qr_web.py` 產生，指向顧客頁 | QR 已產生；實體手機掃描尚待驗收。 |
| F3 | 姓名、性別、E-mail 必填；enqueue 進 Queue 並取得候位號碼 | 顧客表單、`POST /api/queue`、SQLite `queue_entries` | 有伺服器端欄位驗證；另要求 1–4 人用餐人數與資料使用同意。 |
| F4 | 顧客看到當前候位組數、前方組數並自動更新 | `/api/queue/summary`、`/api/queue/status`；前端每 5 秒輪詢 | 支援依 2 人桌／4 人桌分流後顯示。 |
| F5 | 員工登入後查看號碼、姓名、性別、人數、E-mail、候位時間、狀態 | `staff.html`、`GET /api/staff/queue` | Queue API 需要有效員工 token。 |
| F6 | 員工按「通知」後端用 Gmail 寄信，狀態改為「已通知」 | `POST /api/staff/entries/{id}/notify`；沿用 `gmail_assignment/gmail_auto.py` 的 `load_config` 與 `create_smtp` | 只有 SMTP 接受郵件後才更新；寄送失敗會恢復「候位中」。尚未寄送實信驗收。 |
| F7 | 員工按「入座」或「取消」將該組移出 Queue，前方組數減少 | 員工操作 API 將狀態設為 `seated` 或 `cancelled`；歷史資料保留 | 公開與員工 Queue 只計算活動中的紀錄。 |
| F8 | 員工密碼錯誤時不能看 Queue、不能操作 | `POST /api/staff/login`、8 小時簽章 token、員工 API 驗證 | 頁面登入前不讀取候位 API；登入錯誤時不顯示 Queue。 |
| F9 | 顧客可自行取消候位 | 顧客進度卡及通知 E-mail 的簽章取消連結；`POST /api/queue/cancel` | 只允許尚未入座的活動候位取消。 |
| F10 | 統計今日總候位、平均等候時間、放棄率等 | `GET /api/staff/stats` | 平均時間取已入座紀錄；放棄率暫定為取消數 ÷ 今日總候位數。 |
| F11 | Queue 可超過 50 組，或依桌型分流 | SQLite 持久資料表、日期＋桌型票號、2 人桌與 4 人桌獨立 Queue | 不設 50 組上限；雲端部署需掛載持久磁碟。 |

## 尚待完成的環境驗收

- [ ] 推送 Pages workflow 並確認公開顧客頁和員工頁能開啟。
- [ ] 設定 `WAITLIST_API_URL`，部署 API 並掛載持久磁碟。
- [ ] 用實體手機掃描 QR Code 完成一筆候位。
- [ ] 以正確與錯誤密碼驗證員工頁存取。
- [ ] 設定 Gmail 應用程式密碼並實際驗證通知信與取消連結。
