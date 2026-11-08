# QR Code 網址導引作業

這個專案使用 Python 產生網址 QR Code、以 OpenCV 解碼驗證，並把正式網站部署到 GitHub Pages：`https://lucas950219.github.io/data_structure/qrcode.html`。GitHub Pages 是靜態主機；公開頁的簽到表單只存在訪客自己的瀏覽器，不會回傳到 repo。`serve` 則提供本機測試後端，會記錄本機 HTTP 連線並將簽到寫入 `data/checkins.json`。

## 環境需求

- Python 3.10 或更新版本
- Windows、macOS 或 Linux
- 手機與電腦需連到相同 Wi-Fi，才能測試本機 `serve`；開啟 GitHub Pages 不需同網路

## 安裝

在 `qrcode_assignment` 目錄執行：

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

macOS / Linux 的虛擬環境啟用方式是 `source .venv/bin/activate`。

## 產生並解碼 QR Code

```powershell
python qr_web.py make --url https://www.google.com --out output/qr_google.png --label "Google" --ec M
python qr_web.py decode output/qr_google.png
```

`make` 會記錄 QR 版本、模組數、容錯等級、圖片尺寸與檔案大小，並用 OpenCV 比對解碼結果和原網址。可用 `--ec L|M|Q|H` 設定容錯等級；`--logo logo.png` 可加入中央 Logo，並自動改用 H 級容錯。

## 啟動本機網站

先在 `config.json` 填入自己的學號與姓名（本份專案已依你提供的資料填好），再啟動伺服器：

```powershell
python qr_web.py serve --port 8000
```

程式會自動偵測區網 IP 啟動本機測試伺服器，並產生 `output/qr_site.png`。QR Code 預設使用 `config.json` 的 `qr_url`，也就是正式 GitHub Pages 網址。若要覆寫 QR Code 內容，可以指定：

```powershell
python qr_web.py serve --port 8000 --host-ip 192.168.1.23 --qr-url https://example.com --student-id "你的學號" --student-name "你的姓名"
```

終端機會同時顯示本機測試網址與 QR Code 內容網址。掃描 QR Code 會開啟 GitHub Pages，因此網站上線前請先設定 repo 的 Pages Source 為 **GitHub Actions**。`site/index.html` 會在啟動時依設定更新。也可用 `--duration 20` 讓本機測試伺服器在 20 秒後自動關閉。

正式頁面來源為 `site/index.template.html`；部署時會將 `site/index.html` 複製成 repo 網站根目錄的 `qrcode.html`。

## 容錯等級比較（加分）

```powershell
python qr_web.py compare --url https://www.google.com
```

會在 `output/compare/` 產生 L、M、Q、H 四張 QR Code，並將各圖的版本、模組數、像素、檔案大小和解碼結果寫入執行紀錄。

## 功能測試

```powershell
.\.venv\Scripts\python.exe tests\test_feature_matrix.py
```

測試 F1、F3、F5、F6、F7、F8，並以公開網址檢查 F4 的 GitHub Pages 部署。F5 的時間、IP、路徑與瀏覽器紀錄，以及伺服器端簽到，需在本機 `serve` 中驗證；靜態 Pages 不提供這類伺服器紀錄。F2 與 F6/F7 的手機相機可讀性仍需實機驗證，請依 `feature_check.md` 記錄結果。

## 目錄

```text
qr_web.py             CLI：make、decode、serve、compare
site/                 GitHub Pages 網頁及本機 serve 樣板
output/               QR Code PNG 圖片
results/              每次執行的 JSON 與 Markdown 紀錄
data/                 網站互動簽到資料
evidence/             手機實際掃描截圖
report.md             作業報告草稿
feature_check.md      F1–F8 測試矩陣與剩餘工作
tests/                本機功能整合測試
package_submission.py  完成實掃證據後產生繳交 ZIP
```

## 交作業前

1. 把實際學號、姓名帶入 `serve` 命令，再確認 `site/index.html` 顯示正確。
2. 在同一個 Wi-Fi 環境以至少兩台裝置掃描 `output/qr_site.png`，確認兩台都能打開網頁。
3. 將手機開啟網站的畫面截圖放進 `evidence/`，在 `report.md` 補上手機型號及掃描結果。
4. 確認 `results/` 有實際執行產生的一次 `make` 與一次 `serve` 紀錄。
5. 執行 `python package_submission.py` 產生「學號_姓名_qrcode作業.zip」。打包程式會在兩台手機截圖與報告待填欄位補齊前阻止建立正式 ZIP，並自動排除 `.venv`。

手機掃描需要使用你的區網與實體裝置；本專案不會把本機 HTTP 請求偽裝成手機掃描證據。
