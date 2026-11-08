# -*- coding: utf-8 -*-
"""Create, decode, and serve QR codes for the QR Code course assignment."""

from __future__ import annotations

import argparse
import html
import json
import platform
import socket
import sys
import threading
import time
import urllib.parse
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from importlib.metadata import PackageNotFoundError, version
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

BASE_DIR = Path(__file__).resolve().parent
SITE_DIR = BASE_DIR / "site"
RESULTS_DIR = BASE_DIR / "results"
DATA_DIR = BASE_DIR / "data"
OUTPUT_DIR = BASE_DIR / "output"
TAIPEI = timezone(timedelta(hours=8), name="Asia/Taipei")
EC_LEVELS = {
    "L": ("ERROR_CORRECT_L", "約 7%"),
    "M": ("ERROR_CORRECT_M", "約 15%"),
    "Q": ("ERROR_CORRECT_Q", "約 25%"),
    "H": ("ERROR_CORRECT_H", "約 30%"),
}


def now_iso() -> str:
    return datetime.now(TAIPEI).isoformat(timespec="seconds")


def project_path(value: str | Path) -> Path:
    path = Path(value).expanduser()
    return path if path.is_absolute() else BASE_DIR / path


@dataclass
class RunResult:
    mode: str
    started_at: str = field(default_factory=now_iso)
    finished_at: str = ""
    environment: dict[str, str] = field(default_factory=dict)
    steps: list[dict[str, Any]] = field(default_factory=list)
    qr_info: dict[str, Any] = field(default_factory=dict)
    visits: list[dict[str, str]] = field(default_factory=list)
    checkins: list[dict[str, str]] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.environment = {
            "Python": sys.version.split()[0],
            "作業系統": f"{platform.system()} {platform.release()}",
        }
        for package, distribution in (
            ("qrcode", "qrcode"),
            ("Pillow", "Pillow"),
            ("OpenCV", "opencv-python-headless"),
        ):
            try:
                self.environment[package] = version(distribution)
            except PackageNotFoundError:
                self.environment[package] = "未安裝"

    def step(self, name: str, ok: bool, detail: str, seconds: float = 0.0) -> None:
        self.steps.append({"name": name, "ok": ok, "detail": detail, "seconds": round(seconds, 3)})
        print(f"[{'OK' if ok else '錯誤'}] {name}：{detail}")
        if not ok:
            self.errors.append(f"{name}：{detail}")


def result_markdown(result: RunResult) -> str:
    lines = [
        f"# 執行紀錄：{result.mode}",
        "",
        f"- 開始時間（Asia/Taipei）：{result.started_at}",
        f"- 結束時間（Asia/Taipei）：{result.finished_at}",
        "",
        "## 執行環境",
        "",
        *[f"- {key}：{value}" for key, value in result.environment.items()],
        "",
    ]
    if result.qr_info:
        lines += ["## QR Code 數值", "", "| 項目 | 實際值 |", "|---|---|"]
        lines.extend(f"| {key} | {value} |" for key, value in result.qr_info.items())
        lines.append("")
    lines += ["## 執行步驟", "", "| # | 步驟 | 結果 | 說明 | 耗時（秒） |", "|---:|---|---|---|---:|"]
    lines.extend(
        f"| {i} | {step['name']} | {'成功' if step['ok'] else '失敗'} | {step['detail']} | {step['seconds']} |"
        for i, step in enumerate(result.steps, 1)
    )
    lines.append("")
    if result.visits:
        lines += ["## 網站連線紀錄", "", "| # | 時間（Asia/Taipei） | 來源 IP | 路徑 | User-Agent |", "|---:|---|---|---|---|"]
        lines.extend(
            f"| {i} | {visit['time']} | {visit['ip']} | {visit['path']} | {visit['user_agent'][:120]} |"
            for i, visit in enumerate(result.visits, 1)
        )
        lines.append("")
    if result.checkins:
        lines += ["## 簽到紀錄", "", "| # | 時間（Asia/Taipei） | 暱稱 | 回覆 |", "|---:|---|---|---|"]
        lines.extend(
            f"| {i} | {item['time']} | {item['name']} | {item['message'].replace('|', '\\|')} |"
            for i, item in enumerate(result.checkins, 1)
        )
        lines.append("")
    if result.errors:
        lines += ["## 錯誤", "", *[f"- {error}" for error in result.errors], ""]
    return "\n".join(lines)


def save_result(result: RunResult) -> Path:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(TAIPEI).strftime("%Y%m%d_%H%M%S_%f")
    stem = f"qr_{result.mode}_{stamp}"
    md_path = RESULTS_DIR / f"{stem}.md"
    md_path.write_text(result_markdown(result), encoding="utf-8")
    (RESULTS_DIR / f"{stem}.json").write_text(
        json.dumps(asdict(result), ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return md_path


def validate_url(url: str) -> None:
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("網址需以 http:// 或 https:// 開頭，並包含網域或 IP。")


def make_qr(
    payload: str,
    out_path: Path,
    label: str | None,
    logo_path: Path | None,
    ec: str,
    box_size: int,
    result: RunResult,
) -> Path:
    import qrcode
    from PIL import Image, ImageDraw, ImageFont

    ec = ec.upper()
    if ec not in EC_LEVELS:
        raise ValueError("容錯等級必須是 L、M、Q 或 H。")
    if box_size < 2:
        raise ValueError("--box 至少要是 2。")
    if logo_path and not logo_path.is_file():
        raise FileNotFoundError(f"Logo 圖片不存在：{logo_path}")
    if logo_path and ec != "H":
        ec = "H"
        result.step("Logo 容錯設定", True, "加入中央 Logo，容錯等級自動提高為 H。")

    started = time.perf_counter()
    error_constant = getattr(qrcode.constants, EC_LEVELS[ec][0])
    qr = qrcode.QRCode(error_correction=error_constant, box_size=box_size, border=4)
    qr.add_data(payload)
    qr.make(fit=True)
    image = qr.make_image(fill_color="black", back_color="white").convert("RGB")

    if logo_path:
        logo = Image.open(logo_path).convert("RGBA")
        max_side = max(1, image.width // 6)
        logo.thumbnail((max_side, max_side))
        x = (image.width - logo.width) // 2
        y = (image.height - logo.height) // 2
        backing = Image.new("RGB", (logo.width + 16, logo.height + 16), "white")
        image.paste(backing, (x - 8, y - 8))
        image.paste(logo, (x, y), logo)

    if label:
        font: ImageFont.ImageFont = ImageFont.load_default()
        font_candidates = [
            Path("C:/Windows/Fonts/msyh.ttc"),
            Path("C:/Windows/Fonts/msjh.ttc"),
            Path("/System/Library/Fonts/PingFang.ttc"),
            Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"),
        ]
        for candidate in font_candidates:
            if candidate.is_file():
                try:
                    font = ImageFont.truetype(str(candidate), max(16, image.width // 18))
                    break
                except OSError:
                    continue
        drawer = ImageDraw.Draw(image)
        try:
            bounds = drawer.textbbox((0, 0), label, font=font)
            label_width = bounds[2] - bounds[0]
            label_height = bounds[3] - bounds[1]
            canvas = Image.new("RGB", (image.width, image.height + label_height + 22), "white")
            canvas.paste(image, (0, 0))
            ImageDraw.Draw(canvas).text(((canvas.width - label_width) // 2, image.height + 8), label, fill="black", font=font)
            image = canvas
        except (UnicodeEncodeError, ValueError):
            result.step("文字標籤", False, "目前系統沒有可顯示標籤文字的字型；QR 圖仍已產生。")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    image.save(out_path, format="PNG")
    result.qr_info.update({
        "內容": payload,
        "圖片檔": str(out_path.relative_to(BASE_DIR)) if out_path.is_relative_to(BASE_DIR) else str(out_path),
        "QR 版本（version）": qr.version,
        "矩陣模組數": f"{qr.modules_count} × {qr.modules_count}",
        "含四格靜區的總格數": f"{qr.modules_count + 8} × {qr.modules_count + 8}",
        "容錯等級": f"{ec}（{EC_LEVELS[ec][1]}）",
        "每模組像素（box size）": box_size,
        "圖片像素": f"{image.width} × {image.height}",
        "PNG 檔案大小（bytes）": out_path.stat().st_size,
        "文字標籤": label or "無",
        "中央 Logo": str(logo_path) if logo_path else "無",
    })
    result.step(
        "產生 QR Code", True,
        f"{out_path.name}，version {qr.version}，{qr.modules_count} × {qr.modules_count} 模組，容錯 {ec}。",
        time.perf_counter() - started,
    )
    return out_path


def decode_qr(image_path: Path, result: RunResult) -> str | None:
    import cv2

    started = time.perf_counter()
    image = cv2.imread(str(image_path))
    if image is None:
        result.step("讀取 QR 圖片", False, f"無法讀取圖片：{image_path}。", time.perf_counter() - started)
        return None
    value, _points, _straight = cv2.QRCodeDetector().detectAndDecode(image)
    if value:
        result.qr_info["解碼內容"] = value
        result.step("OpenCV 解碼", True, f"解碼結果：{value}。", time.perf_counter() - started)
        return value
    result.step("OpenCV 解碼", False, "圖片中沒有找到可解碼的 QR Code。", time.perf_counter() - started)
    return None


def detect_lan_ip() -> str:
    """Choose the active outbound IPv4 address without sending a data packet."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect(("8.8.8.8", 80))
        address = sock.getsockname()[0]
        return address if not address.startswith("127.") else "127.0.0.1"
    except OSError:
        candidates = socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET)
        for candidate in candidates:
            address = candidate[4][0]
            if not address.startswith(("127.", "169.254.")):
                return address
        return "127.0.0.1"
    finally:
        sock.close()


def render_site(student_id: str, student_name: str) -> Path:
    template_path = SITE_DIR / "index.template.html"
    if not template_path.is_file():
        raise FileNotFoundError(f"找不到網站樣板：{template_path}")
    template = template_path.read_text(encoding="utf-8")
    page = template.replace("{{STUDENT_ID}}", html.escape(student_id))
    page = page.replace("{{STUDENT_NAME}}", html.escape(student_name))
    page_path = SITE_DIR / "index.html"
    page_path.write_text(page, encoding="utf-8")
    return page_path


def append_checkin(item: dict[str, str]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    path = DATA_DIR / "checkins.json"
    try:
        items = json.loads(path.read_text(encoding="utf-8")) if path.exists() else []
        if not isinstance(items, list):
            items = []
    except (json.JSONDecodeError, OSError):
        items = []
    items.append(item)
    path.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")


def serve(args: argparse.Namespace, result: RunResult) -> None:
    config_path = BASE_DIR / "config.json"
    config: dict[str, Any] = {}
    if config_path.is_file():
        config = json.loads(config_path.read_text(encoding="utf-8"))
        if not isinstance(config, dict):
            raise ValueError("config.json 頂層內容必須是 JSON 物件。")
    student_id = args.student_id or config.get("student_id") or "請填寫學號"
    student_name = args.student_name or config.get("student_name") or "請填寫姓名"
    port = int(args.port if args.port is not None else config.get("port", 8000))
    if args.duration < 0:
        raise ValueError("--duration 不可小於 0。")
    page_path = render_site(student_id, student_name)
    host_ip = args.host_ip or detect_lan_ip()
    if not 1 <= port <= 65535:
        raise ValueError("連接埠需介於 1 到 65535。")
    local_url = f"http://{host_ip}:{port}/"
    qr_url = args.qr_url or config.get("qr_url") or local_url
    validate_url(qr_url)
    qr_path = project_path(args.out)
    make_qr(qr_url, qr_path, f"掃描開啟：{qr_url}", None, "M", 10, result)
    decoded = decode_qr(qr_path, result)
    result.step("QR 網址比對", decoded == qr_url, "解碼內容與 QR 網址相同。" if decoded == qr_url else "解碼內容與 QR 網址不相同。")
    result.qr_info.update({
        "QR Code 網址": qr_url,
        "本機測試伺服器": local_url,
        "學號欄位": student_id,
        "姓名欄位": student_name,
        "網站檔案": str(page_path.relative_to(BASE_DIR)),
    })

    visits = result.visits
    checkins = result.checkins

    class Handler(BaseHTTPRequestHandler):
        server_version = "QRAssignmentHTTP/1.0"

        def log_message(self, _format: str, *_args: Any) -> None:
            return

        def _record_visit(self) -> None:
            if self.path.split("?", 1)[0].endswith("favicon.ico"):
                return
            entry = {
                "time": now_iso(),
                "ip": self.client_address[0],
                "path": self.path,
                "user_agent": self.headers.get("User-Agent", "未提供"),
            }
            visits.append(entry)
            print(f"  [連線 #{len(visits)}] {entry['time']} {entry['ip']} {entry['path']} {entry['user_agent'][:70]}")

        def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API name
            self._record_visit()
            if self.path.split("?", 1)[0] not in {"/", "/index.html"}:
                body = "找不到頁面。".encode("utf-8")
                self.send_response(404)
                self.send_header("Content-Type", "text/plain; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            body = page_path.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_POST(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API name
            if self.path != "/checkin":
                self.send_error(404, "Not Found")
                return
            self._record_visit()
            try:
                length = min(int(self.headers.get("Content-Length", "0")), 8_192)
                form = urllib.parse.parse_qs(self.rfile.read(length).decode("utf-8", errors="replace"))
                name = form.get("name", [""])[0].strip()[:50] or "匿名同學"
                message = form.get("message", [""])[0].strip()[:300]
            except (ValueError, OSError):
                self.send_error(400, "無效的簽到資料")
                return
            item = {"time": now_iso(), "name": name, "message": message}
            checkins.append(item)
            append_checkin(item)
            safe_name = html.escape(name)
            body = (
                "<!doctype html><html lang='zh-Hant'><meta charset='utf-8'>"
                "<meta name='viewport' content='width=device-width,initial-scale=1'>"
                "<title>簽到完成</title><body style='font:16px system-ui;max-width:620px;margin:10vh auto;padding:24px'>"
                f"<h1>簽到完成，{safe_name}！</h1><p>回覆已記錄於這台執行伺服器的 data/checkins.json。</p>"
                "<p><a href='/'>返回作業首頁</a></p></body></html>"
            ).encode("utf-8")
            self.send_response(303)
            self.send_header("Location", "/")
            self.send_header("Content-Length", "0")
            self.end_headers()

    class QRHTTPServer(ThreadingHTTPServer):
        allow_reuse_address = False
        allow_reuse_port = False

    try:
        server = QRHTTPServer(("0.0.0.0", port), Handler)
    except OSError as exc:
        raise OSError(f"無法在 port {port} 啟動網站：{exc}") from exc

    result.step("網站伺服器啟動", True, f"本機測試網址 {local_url}；QR Code 指向 {qr_url}。")
    print(f"\n本機測試伺服器：{local_url}")
    print(f"QR Code 網址：{qr_url}")
    print(f"QR Code 圖片：{qr_path}")
    if args.duration:
        print(f"伺服器將於 {args.duration:g} 秒後自動關閉。\n")
    else:
        print("掃描後會開啟 QR Code 網址；本機伺服器供電腦測試使用。按 Ctrl+C 關閉並輸出紀錄。\n")
    server_thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.2}, daemon=True)
    server_thread.start()
    deadline = time.monotonic() + args.duration if args.duration else None
    try:
        while server_thread.is_alive():
            if deadline is not None and time.monotonic() >= deadline:
                break
            server_thread.join(timeout=0.5)
    except KeyboardInterrupt:
        print("\n收到 Ctrl+C，正在關閉網站並整理紀錄……")
    finally:
        server.shutdown()
        server.server_close()
        server_thread.join(timeout=2)
        result.step(
            "網站連線統計", True,
            f"記錄 {len(visits)} 次 HTTP 請求、{len({v['ip'] for v in visits})} 個來源 IP、{len(checkins)} 筆簽到。",
        )


def add_common_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--no-save", action="store_true", help="不輸出 results/ 執行紀錄。")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="QR Code 網址產生、解碼與本機網站工具")
    subparsers = parser.add_subparsers(dest="mode", required=True)

    make_parser = subparsers.add_parser("make", help="網址產生 PNG QR Code 並自動解碼比對")
    add_common_args(make_parser)
    make_parser.add_argument("--url", required=True, help="要寫入 QR Code 的網址。")
    make_parser.add_argument("--out", default="output/qr.png", help="輸出 PNG 路徑。")
    make_parser.add_argument("--label", help="圖片下方的文字標籤。")
    make_parser.add_argument("--logo", help="可選的中央 Logo 圖片。")
    make_parser.add_argument("--ec", choices=list(EC_LEVELS), default="M", help="容錯等級，預設 M。")
    make_parser.add_argument("--box", type=int, default=10, help="每個 QR 模組的像素邊長，預設 10。")

    decode_parser = subparsers.add_parser("decode", help="解碼現有 PNG QR Code 圖片")
    add_common_args(decode_parser)
    decode_parser.add_argument("image", help="QR Code 圖片路徑。")

    serve_parser = subparsers.add_parser("serve", help="啟動本機網站並產生指向網站的 QR Code")
    add_common_args(serve_parser)
    serve_parser.add_argument("--port", type=int, help="HTTP 連接埠，預設採用 config.json 的設定或 8000。")
    serve_parser.add_argument("--host-ip", help="覆寫自動偵測的區網 IPv4 位址。")
    serve_parser.add_argument("--qr-url", help="覆寫 QR Code 內容；預設採用 config.json 的 qr_url，否則使用本機伺服器網址。")
    serve_parser.add_argument("--duration", type=float, default=0, help="指定伺服器執行秒數；預設 0 表示直到 Ctrl+C。")
    serve_parser.add_argument("--out", default="output/qr_site.png", help="網站 QR Code 輸出路徑。")
    serve_parser.add_argument("--student-id", help="覆寫 config.json 中顯示於作業網頁的學號。")
    serve_parser.add_argument("--student-name", help="覆寫 config.json 中顯示於作業網頁的姓名。")

    compare_parser = subparsers.add_parser("compare", help="以 L/M/Q/H 四種等級各產生一張 QR Code")
    add_common_args(compare_parser)
    compare_parser.add_argument("--url", required=True, help="要比較的網址。")
    compare_parser.add_argument("--out-dir", default="output/compare", help="比較圖片輸出目錄。")
    compare_parser.add_argument("--box", type=int, default=8, help="每個 QR 模組的像素邊長。")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    result = RunResult(mode=args.mode)
    try:
        if args.mode == "make":
            validate_url(args.url)
            out = project_path(args.out)
            logo = project_path(args.logo) if args.logo else None
            make_qr(args.url, out, args.label, logo, args.ec, args.box, result)
            decoded = decode_qr(out, result)
            result.step("原網址內容比對", decoded == args.url, "解碼內容與原網址完全相同。" if decoded == args.url else "解碼內容與原網址不同。")
        elif args.mode == "decode":
            image_path = project_path(args.image)
            decoded = decode_qr(image_path, result)
            if decoded is None:
                result.errors.append("QR Code 圖片解碼失敗。")
        elif args.mode == "serve":
            serve(args, result)
        elif args.mode == "compare":
            validate_url(args.url)
            out_dir = project_path(args.out_dir)
            comparison: list[dict[str, Any]] = []
            for level in EC_LEVELS:
                image_path = out_dir / f"qr_{level}.png"
                make_qr(args.url, image_path, f"Error correction {level}", None, level, args.box, result)
                decoded = decode_qr(image_path, result)
                comparison.append({
                    "等級": level,
                    "估計容錯": EC_LEVELS[level][1],
                    "version": result.qr_info["QR 版本（version）"],
                    "模組數": result.qr_info["矩陣模組數"],
                    "圖片像素": result.qr_info["圖片像素"],
                    "檔案大小 bytes": result.qr_info["PNG 檔案大小（bytes）"],
                    "解碼一致": decoded == args.url,
                    "圖片": str(image_path.relative_to(BASE_DIR)),
                })
            result.qr_info = {"比較內容": args.url, "容錯比較": comparison}
            result.step("四種容錯等級比較", all(row["解碼一致"] for row in comparison), "已產生 L、M、Q、H 四張圖片並逐一解碼。")
    except Exception as exc:  # Keep a failed run visible in the assignment record.
        result.step("執行失敗", False, f"{type(exc).__name__}：{exc}")
    finally:
        result.finished_at = now_iso()
        if not args.no_save:
            record_path = save_result(result)
            print(f"執行紀錄：{record_path.relative_to(BASE_DIR)}")
    return 1 if result.errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
