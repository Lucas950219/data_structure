# F1–F11 功能對照

| 編號 | 要求 | 實作位置 | 狀態／驗收備註 |
|---|---|---|---|
| F1 | 顧客頁與員工頁放在 GitHub Pages，以網址開啟 | waitlist.html、staff.html；Pages workflow 發布公開入口；Apps Script Web App 顯示互動介面 | Pages workflow 已部署；設定 GAS_WEB_APP_URL 後入口才會載入 Apps Script。 |
| F2 | 顧客掃 QR Code 進入候位網頁（手機測試） | assets/waitlist-qr.png 由既有 qrcode_assignment/qr_web.py 產生，指向顧客頁 | QR 圖已產生；需以手機實際掃描驗收。 |
| F3 | 姓名、性別、E-mail 必填；enqueue 進 Queue 並取得候位號碼 | Apps Script apiRpc、queueJoin_；Google 試算表 Queue | 伺服器端驗證欄位、同意與 1–4 人用餐人數；初始化後產生候位號碼與顧客 token。 |
| F4 | 顧客看到目前候位組數、前方組數並自動更新 | queueSummary_、queueStatus_；顧客頁每 5 秒透過 google.script.run 更新 | 支援 2 人桌／4 人桌分流。 |
| F5 | 員工登入後查看號碼、姓名、性別、人數、E-mail、候位時間、狀態 | staffLogin_、staffQueue_；Staff.html | API 每次讀取員工資料都驗證 8 小時簽章 token。 |
| F6 | 員工按「通知」後端用 Gmail 寄信，狀態改為「已通知」 | staffNotify_、MailApp.sendEmail | 寄送成功才更新狀態；失敗會回復「候位中」。需由 Apps Script 部署者授權寄信。 |
| F7 | 員工按「入座」或「取消」將該組移出 Queue，前方組數減少 | staffChangeStatus_；狀態設為 seated 或 cancelled | 保留歷史資料，活動 Queue 不再計入完成或取消項目。 |
| F8 | 員工密碼錯誤時不能看到 Queue、不能操作 | staffLogin_、requireStaff_ | 前端登入前不載入員工清單；所有員工資料與操作都須有效 token。 |
| F9 | 顧客可自行取消候位 | queueCancel_；顧客頁取消按鈕及通知信連結 | 使用簽章 token；已入座或通知寄送中不可取消。 |
| F10 | 統計今日總候位、平均等候時間、放棄率等 | staffStats_ | 平均等候時間取今日已入座紀錄；放棄率為今日取消組數 ÷ 今日總候位組數。 |
| F11 | Queue 可超過 50 組，或依桌型分流 | queueJoin_、Google 試算表、LockService | 無 50 組上限；依日期與桌型分開編號，1–2 位及 3–4 位分流，鎖定寫入避免重號。 |

## 部署與實機驗收

- [x] GitHub Pages workflow 已發布顧客與員工入口頁。
- [ ] 將 apps_script/ 推送到老師提供的 Apps Script 專案。
- [ ] 執行 setupWaitlist_、設定 STAFF_PASSWORD，並部署 Web App。
- [ ] 將 Apps Script /exec 網址設為 GitHub repository variable GAS_WEB_APP_URL，重新部署 Pages。
- [ ] 用手機掃描 QR Code 完成候位，並驗證顧客取消。
- [ ] 驗證錯誤／正確員工密碼、通知、入座、取消和統計。
