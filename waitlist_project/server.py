"""Small standard-library API for the GitHub Pages waitlist front end."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import re
import smtplib
import sqlite3
import sys
import threading
import time
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, quote, urlsplit


ROOT = Path(__file__).resolve().parent
REPOSITORY_ROOT = ROOT.parent
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))
try:
    from gmail_assignment import gmail_auto
except ImportError as exc:  # Keep the integration failure clear when copied without its sibling assignment.
    raise SystemExit("找不到 gmail_assignment/gmail_auto.py；請保留原 Gmail 作業資料夾。") from exc

TAIPEI = timezone(timedelta(hours=8))
ACTIVE_STATUSES = ("waiting", "notifying", "notified")
VALID_GENDERS = {"女", "男", "其他", "不透露"}
MAX_BODY_BYTES = 16 * 1024


def load_env_file() -> None:
    """Load a local .env file without overriding real environment variables."""
    env_path = ROOT / ".env"
    if not env_path.exists():
        return
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        name = name.strip()
        value = value.strip().strip("\"'")
        if name and name not in os.environ:
            os.environ[name] = value


load_env_file()

DB_PATH = Path(os.environ.get("DATABASE_PATH", str(ROOT / "data" / "waitlist.sqlite3")))
GMAIL_CONFIG_PATH = REPOSITORY_ROOT / "gmail_assignment" / "config.json"
APP_SECRET = os.environ.get("APP_SECRET", "")
ADMIN_PASSWORD = os.environ.get("WAITLIST_ADMIN_PASSWORD", "")
PUBLIC_SITE_URL = os.environ.get(
    "PUBLIC_SITE_URL",
    "https://lucas950219.github.io/data_structure/waitlist.html",
).rstrip("/")
ALLOWED_ORIGINS = {
    origin.strip().rstrip("/")
    for origin in os.environ.get(
        "ALLOWED_ORIGINS",
        "https://lucas950219.github.io,http://localhost:5500,http://127.0.0.1:5500",
    ).split(",")
    if origin.strip()
}
DEFAULT_WAIT_PER_GROUP = max(1, int(os.environ.get("DEFAULT_WAIT_PER_GROUP_MINUTES", "10")))


class APIError(Exception):
    def __init__(self, status: int, code: str, message: str):
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message


def now_local() -> datetime:
    return datetime.now(TAIPEI).replace(microsecond=0)


def iso_now() -> str:
    return now_local().isoformat()


def date_today() -> str:
    return now_local().date().isoformat()


def get_db() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DB_PATH, timeout=15)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA busy_timeout = 15000")
    return connection


def init_db() -> None:
    with get_db() as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS queue_entries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                queue_day TEXT NOT NULL,
                ticket TEXT NOT NULL,
                name TEXT NOT NULL,
                gender TEXT NOT NULL,
                email TEXT NOT NULL,
                party_size INTEGER NOT NULL CHECK (party_size BETWEEN 1 AND 4),
                table_type TEXT NOT NULL CHECK (table_type IN ('2p', '4p')),
                created_at TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'waiting'
                    CHECK (status IN ('waiting', 'notifying', 'notified', 'seated', 'cancelled')),
                notified_at TEXT,
                seated_at TEXT,
                cancelled_at TEXT,
                UNIQUE(queue_day, ticket)
            );
            CREATE INDEX IF NOT EXISTS idx_queue_active
                ON queue_entries(queue_day, table_type, status, created_at, id);
            CREATE INDEX IF NOT EXISTS idx_queue_day_status
                ON queue_entries(queue_day, status);
            """
        )
        # A process restart cannot safely resume an SMTP transaction that was
        # interrupted after claiming a row, so return today's stale claim to waiting.
        connection.execute(
            "UPDATE queue_entries SET status='waiting' WHERE status='notifying' AND queue_day=?",
            (date_today(),),
        )
        # Old active entries are retained for reports but closed out of today's queue.
        connection.execute(
            "UPDATE queue_entries SET status='cancelled', cancelled_at=? "
            "WHERE queue_day<? AND status IN ('waiting','notifying','notified')",
            (iso_now(), date_today()),
        )


def _b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _unb64url(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def sign_token(payload: dict[str, Any]) -> str:
    raw = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    encoded = _b64url(raw)
    signature = hmac.new(APP_SECRET.encode("utf-8"), encoded.encode("ascii"), hashlib.sha256).digest()
    return f"{encoded}.{_b64url(signature)}"


def verify_token(token: str, scope: str) -> dict[str, Any]:
    if not APP_SECRET or "." not in token:
        raise APIError(401, "invalid_token", "登入或候位連結已失效，請重新操作。")
    encoded, supplied_signature = token.rsplit(".", 1)
    expected_signature = _b64url(
        hmac.new(APP_SECRET.encode("utf-8"), encoded.encode("ascii"), hashlib.sha256).digest()
    )
    if not hmac.compare_digest(supplied_signature, expected_signature):
        raise APIError(401, "invalid_token", "登入或候位連結已失效，請重新操作。")
    try:
        payload = json.loads(_unb64url(encoded))
    except (ValueError, json.JSONDecodeError):
        raise APIError(401, "invalid_token", "登入或候位連結已失效，請重新操作。") from None
    if payload.get("scope") != scope or int(payload.get("exp", 0)) < int(time.time()):
        raise APIError(401, "expired_token", "登入或候位連結已失效，請重新操作。")
    return payload


def customer_token(entry_id: int, created_at: str) -> str:
    created = datetime.fromisoformat(created_at)
    expiry = int((created + timedelta(days=90)).timestamp())
    return sign_token({"scope": "customer", "id": entry_id, "exp": expiry})


def staff_token() -> str:
    return sign_token({"scope": "staff", "exp": int(time.time()) + 8 * 60 * 60})


def require_staff(handler: "WaitlistHandler") -> None:
    authorization = handler.headers.get("Authorization", "")
    if not authorization.startswith("Bearer "):
        raise APIError(401, "staff_login_required", "請先登入員工帳號。")
    verify_token(authorization[7:].strip(), "staff")


def _counts_for_day(connection: sqlite3.Connection, queue_day: str) -> dict[str, int]:
    counts = {"2p": 0, "4p": 0}
    rows = connection.execute(
        "SELECT table_type, COUNT(*) AS total FROM queue_entries "
        "WHERE queue_day=? AND status IN ('waiting','notifying','notified') GROUP BY table_type",
        (queue_day,),
    ).fetchall()
    for row in rows:
        counts[row["table_type"]] = int(row["total"])
    return counts


def _customer_status(connection: sqlite3.Connection, entry: sqlite3.Row) -> dict[str, Any]:
    active = connection.execute(
        "SELECT id, created_at FROM queue_entries WHERE queue_day=? AND table_type=? "
        "AND status IN ('waiting','notifying','notified') ORDER BY created_at, id",
        (entry["queue_day"], entry["table_type"]),
    ).fetchall()
    ahead = 0
    for row in active:
        if int(row["id"]) == int(entry["id"]):
            break
        ahead += 1
    counts = _counts_for_day(connection, entry["queue_day"])
    avg_per_party = DEFAULT_WAIT_PER_GROUP
    status = entry["status"]
    minutes = max(0, round(ahead * avg_per_party)) if status in ACTIVE_STATUSES else 0
    return {
        "ticket": entry["ticket"],
        "tableType": entry["table_type"],
        "partySize": int(entry["party_size"]),
        "status": status,
        "createdAt": entry["created_at"],
        "queueSize": counts[entry["table_type"]],
        "groupsAhead": ahead if status in ACTIVE_STATUSES else 0,
        "estimatedWaitMinutes": minutes,
        "updatedAt": iso_now(),
    }


def _parse_email(value: Any) -> str:
    email_address = str(value or "").strip().lower()
    if len(email_address) > 254 or not re.fullmatch(r"[^\s@<>]+@[^\s@<>]+\.[^\s@<>]+", email_address):
        raise APIError(400, "invalid_email", "請輸入有效的 E-mail 地址。")
    return email_address


def _format_status(row: sqlite3.Row) -> dict[str, Any]:
    created = datetime.fromisoformat(row["created_at"])
    end_value = row["seated_at"] or (iso_now() if row["status"] in ACTIVE_STATUSES else row["cancelled_at"])
    elapsed = 0
    if end_value:
        elapsed = max(0, int((datetime.fromisoformat(end_value) - created).total_seconds() // 60))
    return {
        "id": int(row["id"]),
        "ticket": row["ticket"],
        "name": row["name"],
        "gender": row["gender"],
        "email": row["email"],
        "partySize": int(row["party_size"]),
        "tableType": row["table_type"],
        "createdAt": row["created_at"],
        "status": row["status"],
        "notifiedAt": row["notified_at"],
        "seatedAt": row["seated_at"],
        "waitMinutes": elapsed,
    }


def _stats(connection: sqlite3.Connection) -> dict[str, Any]:
    today = date_today()
    total = int(connection.execute(
        "SELECT COUNT(*) FROM queue_entries WHERE queue_day=?", (today,)
    ).fetchone()[0])
    counts = {row["status"]: int(row["total"]) for row in connection.execute(
        "SELECT status, COUNT(*) AS total FROM queue_entries WHERE queue_day=? GROUP BY status", (today,)
    ).fetchall()}
    active_by_lane = _counts_for_day(connection, today)
    wait = connection.execute(
        "SELECT AVG((julianday(seated_at)-julianday(created_at))*1440.0) AS average "
        "FROM queue_entries WHERE queue_day=? AND status='seated' AND seated_at IS NOT NULL",
        (today,),
    ).fetchone()["average"]
    cancelled = counts.get("cancelled", 0)
    return {
        "date": today,
        "totalToday": total,
        "activeTotal": sum(active_by_lane.values()),
        "waiting": counts.get("waiting", 0),
        "notifying": counts.get("notifying", 0),
        "notified": counts.get("notified", 0),
        "seated": counts.get("seated", 0),
        "cancelled": cancelled,
        "averageWaitMinutes": round(float(wait), 1) if wait is not None else None,
        "abandonmentRate": round((cancelled / total * 100), 1) if total else 0.0,
        "lanes": {
            "2p": {"active": active_by_lane["2p"]},
            "4p": {"active": active_by_lane["4p"]},
        },
    }


def _send_notification(row: sqlite3.Row) -> None:
    try:
        # Reuse the Gmail assignment's environment/config loader and SMTP setup.
        # Environment variables take precedence over the ignored local config.json.
        mail_config = gmail_auto.load_config(GMAIL_CONFIG_PATH)
    except gmail_auto.AppError as exc:
        raise APIError(503, "email_not_configured", "Gmail 尚未設定；請先設定 Gmail 應用程式密碼。") from exc
    token = customer_token(int(row["id"]), row["created_at"])
    cancel_link = f"{PUBLIC_SITE_URL}#cancel={quote(token)}"
    lane_text = "2 人桌候位" if row["table_type"] == "2p" else "4 人桌候位"
    message = EmailMessage()
    message["From"] = mail_config["gmail_address"]
    message["To"] = row["email"]
    message["Subject"] = "您的候位已通知"
    message.set_content(
        f"{row['name']} 您好：\n\n"
        f"您的候位（{row['ticket']}，{lane_text}，{row['party_size']} 位）已輪到，請前往櫃檯。\n"
        "若已不需要候位，可使用以下連結取消：\n"
        f"{cancel_link}\n\n"
        "此通知由候位系統寄出。"
    )
    smtp = None
    try:
        smtp = gmail_auto.create_smtp(mail_config)
        refused = smtp.send_message(message)
        if refused:
            raise smtplib.SMTPRecipientsRefused(refused)
        # An accepted send is complete even if the courtesy QUIT is interrupted.
        try:
            smtp.quit()
            smtp = None
        except (smtplib.SMTPException, OSError):
            try:
                smtp.close()
            except (smtplib.SMTPException, OSError):
                pass
            smtp = None
    except (gmail_auto.AppError, smtplib.SMTPException, OSError, TimeoutError) as exc:
        if smtp is not None:
            try:
                smtp.close()
            except (smtplib.SMTPException, OSError):
                pass
        # Do not put the address, credentials, or SMTP server response in the client response.
        raise APIError(502, "email_send_failed", "Gmail 寄送失敗，候位狀態已保留；請確認寄件設定後重試。") from exc


_RATE_LOCK = threading.Lock()
_RATE_EVENTS: dict[str, list[float]] = {}
_LOGIN_FAILURES: dict[str, list[float]] = {}


def _rate_check(store: dict[str, list[float]], key: str, limit: int, window: int) -> bool:
    now = time.monotonic()
    with _RATE_LOCK:
        recent = [stamp for stamp in store.get(key, []) if now - stamp < window]
        if len(recent) >= limit:
            store[key] = recent
            return False
        recent.append(now)
        store[key] = recent
        return True


def _clear_rate(store: dict[str, list[float]], key: str) -> None:
    with _RATE_LOCK:
        store.pop(key, None)


class WaitlistHandler(BaseHTTPRequestHandler):
    server_version = "WaitlistAPI/1.0"

    def log_message(self, _format: str, *_args: Any) -> None:
        # Keep request logs free of query strings and personal data.
        path = urlsplit(self.path).path
        print(f"{self.command} {path}")

    def _origin_allowed(self) -> bool:
        origin = self.headers.get("Origin", "").rstrip("/")
        return not origin or origin in ALLOWED_ORIGINS

    def _add_cors_headers(self) -> None:
        origin = self.headers.get("Origin", "").rstrip("/")
        if origin and origin in ALLOWED_ORIGINS:
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Vary", "Origin")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Authorization, Content-Type")
        self.send_header("Access-Control-Max-Age", "600")

    def _json(self, status: int, value: dict[str, Any]) -> None:
        body = json.dumps(value, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self._add_cors_headers()
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self) -> dict[str, Any]:
        raw_length = self.headers.get("Content-Length", "0")
        try:
            length = int(raw_length)
        except ValueError:
            raise APIError(400, "invalid_request", "請求格式錯誤。") from None
        if length <= 0 or length > MAX_BODY_BYTES:
            raise APIError(413 if length > MAX_BODY_BYTES else 400, "invalid_request", "請求資料大小不正確。")
        try:
            value = json.loads(self.rfile.read(length))
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise APIError(400, "invalid_json", "請求內容必須是有效的 JSON。") from None
        if not isinstance(value, dict):
            raise APIError(400, "invalid_json", "請求內容格式錯誤。")
        return value

    def _check_origin(self) -> None:
        if not self._origin_allowed():
            raise APIError(403, "origin_denied", "此網頁來源未列入後端允許清單。")

    def _handle_errors(self, action: Any) -> None:
        try:
            if not self._origin_allowed():
                raise APIError(403, "origin_denied", "此網頁來源未列入後端允許清單。")
            action()
        except APIError as exc:
            self._json(exc.status, {"error": exc.code, "message": exc.message})
        except (sqlite3.Error, OSError, ValueError, TypeError):
            print(f"request failed: {self.command} {urlsplit(self.path).path}")
            self._json(500, {"error": "server_error", "message": "服務暫時無法完成請求，請稍後再試。"})

    def do_OPTIONS(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        if not self._origin_allowed():
            self._json(403, {"error": "origin_denied", "message": "此網頁來源未列入後端允許清單。"})
            return
        self.send_response(204)
        self._add_cors_headers()
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        self._handle_errors(self._get)

    def _get(self) -> None:
        parts = urlsplit(self.path)
        if parts.path == "/health":
            self._json(200, {"ok": True, "service": "waitlist-api"})
            return
        if parts.path == "/api/queue/summary":
            with get_db() as connection:
                counts = _counts_for_day(connection, date_today())
                self._json(200, {"queueSize": sum(counts.values()), "lanes": counts, "updatedAt": iso_now()})
            return
        if parts.path == "/api/queue/status":
            authorization = self.headers.get("Authorization", "")
            token = authorization[7:].strip() if authorization.startswith("Bearer ") else ""
            payload = verify_token(token, "customer")
            with get_db() as connection:
                entry = connection.execute("SELECT * FROM queue_entries WHERE id=?", (int(payload["id"]),)).fetchone()
                if entry is None:
                    raise APIError(404, "entry_not_found", "找不到這筆候位資料。")
                self._json(200, _customer_status(connection, entry))
            return
        if parts.path == "/api/staff/queue":
            require_staff(self)
            lane = parse_qs(parts.query).get("lane", ["all"])[0]
            if lane not in {"all", "2p", "4p"}:
                raise APIError(400, "invalid_lane", "桌型篩選不正確。")
            with get_db() as connection:
                params: list[Any] = [date_today(), *ACTIVE_STATUSES]
                lane_sql = ""
                if lane != "all":
                    lane_sql = " AND table_type=?"
                    params.append(lane)
                rows = connection.execute(
                    "SELECT * FROM queue_entries WHERE queue_day=? AND status IN (?,?,?)" + lane_sql +
                    " ORDER BY CASE table_type WHEN '2p' THEN 0 ELSE 1 END, created_at, id",
                    params,
                ).fetchall()
                self._json(200, {"entries": [_format_status(row) for row in rows], "updatedAt": iso_now()})
            return
        if parts.path == "/api/staff/stats":
            require_staff(self)
            with get_db() as connection:
                self._json(200, _stats(connection))
            return
        raise APIError(404, "not_found", "找不到這個 API 路徑。")

    def do_POST(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        self._handle_errors(self._post)

    def _post(self) -> None:
        path = urlsplit(self.path).path
        if path == "/api/queue":
            self._create_entry()
            return
        if path == "/api/queue/cancel":
            self._customer_cancel()
            return
        if path == "/api/staff/login":
            self._staff_login()
            return
        match = re.fullmatch(r"/api/staff/entries/(\d+)/(notify|seat|cancel)", path)
        if match:
            require_staff(self)
            entry_id = int(match.group(1))
            action = match.group(2)
            if action == "notify":
                self._staff_notify(entry_id)
            else:
                self._staff_change_status(entry_id, action)
            return
        raise APIError(404, "not_found", "找不到這個 API 路徑。")

    def _create_entry(self) -> None:
        ip = self.client_address[0]
        if not _rate_check(_RATE_EVENTS, f"join:{ip}", 20, 3600):
            raise APIError(429, "too_many_requests", "操作太頻繁，請稍後再試。")
        body = self._read_json()
        name = str(body.get("name", "")).strip()
        gender = str(body.get("gender", "")).strip()
        email_address = _parse_email(body.get("email"))
        party_size = body.get("partySize")
        if not name or len(name) > 60:
            raise APIError(400, "invalid_name", "姓名為必填，最多 60 個字。")
        if gender not in VALID_GENDERS:
            raise APIError(400, "invalid_gender", "請選擇性別欄位。")
        if isinstance(party_size, bool) or not isinstance(party_size, int) or not 1 <= party_size <= 4:
            raise APIError(400, "invalid_party_size", "用餐人數請選擇 1 至 4 人。")
        if body.get("consent") is not True:
            raise APIError(400, "consent_required", "請先確認候位資料的使用方式。")
        table_type = "2p" if party_size <= 2 else "4p"
        created_at = iso_now()
        queue_day = date_today()
        with get_db() as connection:
            connection.execute("BEGIN IMMEDIATE")
            count = connection.execute(
                "SELECT COUNT(*) FROM queue_entries WHERE queue_day=? AND table_type=?",
                (queue_day, table_type),
            ).fetchone()[0]
            sequence = int(count) + 1
            ticket = f"{table_type[:1].upper()}-{sequence:03d}"
            cursor = connection.execute(
                "INSERT INTO queue_entries(queue_day,ticket,name,gender,email,party_size,table_type,created_at,status) "
                "VALUES(?,?,?,?,?,?,?,?, 'waiting')",
                (queue_day, ticket, name, gender, email_address, party_size, table_type, created_at),
            )
            entry_id = int(cursor.lastrowid)
            entry = connection.execute("SELECT * FROM queue_entries WHERE id=?", (entry_id,)).fetchone()
            result = _customer_status(connection, entry)
        result["token"] = customer_token(entry_id, created_at)
        self._json(201, result)

    def _customer_cancel(self) -> None:
        body = self._read_json()
        token = str(body.get("token", ""))
        payload = verify_token(token, "customer")
        with get_db() as connection:
            connection.execute("BEGIN IMMEDIATE")
            entry = connection.execute("SELECT * FROM queue_entries WHERE id=?", (int(payload["id"]),)).fetchone()
            if entry is None:
                raise APIError(404, "entry_not_found", "找不到這筆候位資料。")
            if entry["status"] == "notifying":
                raise APIError(409, "notification_pending", "通知寄送中，請稍後再取消。")
            if entry["status"] not in {"waiting", "notified"}:
                raise APIError(409, "not_cancellable", "這筆候位目前無法取消。")
            connection.execute(
                "UPDATE queue_entries SET status='cancelled', cancelled_at=? WHERE id=?",
                (iso_now(), int(payload["id"])),
            )
            updated = connection.execute("SELECT * FROM queue_entries WHERE id=?", (int(payload["id"]),)).fetchone()
            result = _customer_status(connection, updated)
        self._json(200, result)

    def _staff_login(self) -> None:
        ip = self.client_address[0]
        if not _rate_check(_LOGIN_FAILURES, f"staff:{ip}", 5, 300):
            raise APIError(429, "login_rate_limited", "登入嘗試過多，請 5 分鐘後再試。")
        body = self._read_json()
        password = str(body.get("password", ""))
        if not ADMIN_PASSWORD or not hmac.compare_digest(password, ADMIN_PASSWORD):
            raise APIError(401, "invalid_password", "密碼錯誤，無法查看候位清單。")
        _clear_rate(_LOGIN_FAILURES, f"staff:{ip}")
        self._json(200, {"token": staff_token(), "expiresInSeconds": 8 * 60 * 60})

    def _staff_notify(self, entry_id: int) -> None:
        with get_db() as connection:
            connection.execute("BEGIN IMMEDIATE")
            entry = connection.execute("SELECT * FROM queue_entries WHERE id=? AND queue_day=?", (entry_id, date_today())).fetchone()
            if entry is None:
                raise APIError(404, "entry_not_found", "找不到這筆候位資料。")
            if entry["status"] != "waiting":
                raise APIError(409, "invalid_status", "只有候位中的客人可以寄送通知。")
            connection.execute("UPDATE queue_entries SET status='notifying' WHERE id=? AND status='waiting'", (entry_id,))
        try:
            _send_notification(entry)
        except Exception as exc:
            with get_db() as connection:
                connection.execute(
                    "UPDATE queue_entries SET status='waiting' WHERE id=? AND status='notifying'",
                    (entry_id,),
                )
            if isinstance(exc, APIError):
                raise
            raise APIError(502, "email_send_failed", "Gmail 寄送失敗，候位狀態已保留；請確認寄件設定後重試。") from exc
        with get_db() as connection:
            connection.execute(
                "UPDATE queue_entries SET status='notified', notified_at=? WHERE id=? AND status='notifying'",
                (iso_now(), entry_id),
            )
        self._json(200, {"ok": True, "status": "notified", "message": "通知郵件已寄出。"})

    def _staff_change_status(self, entry_id: int, action: str) -> None:
        new_status = "seated" if action == "seat" else "cancelled"
        timestamp_column = "seated_at" if action == "seat" else "cancelled_at"
        with get_db() as connection:
            connection.execute("BEGIN IMMEDIATE")
            entry = connection.execute(
                "SELECT status FROM queue_entries WHERE id=? AND queue_day=?",
                (entry_id, date_today()),
            ).fetchone()
            if entry is None:
                raise APIError(404, "entry_not_found", "找不到這筆候位資料。")
            if entry["status"] not in {"waiting", "notified"}:
                raise APIError(409, "invalid_status", "這筆候位目前無法變更。")
            connection.execute(
                f"UPDATE queue_entries SET status=?, {timestamp_column}=? WHERE id=?",
                (new_status, iso_now(), entry_id),
            )
        self._json(200, {"ok": True, "status": new_status})


def validate_startup() -> None:
    if not APP_SECRET or len(APP_SECRET) < 32 or APP_SECRET.startswith("replace-with-"):
        raise SystemExit("請在 .env 設定 APP_SECRET（至少 32 個字元的隨機字串）。")
    if not ADMIN_PASSWORD or ADMIN_PASSWORD.startswith("replace-with-"):
        raise SystemExit("請在 .env 設定 WAITLIST_ADMIN_PASSWORD。")


def main() -> None:
    validate_startup()
    init_db()
    host = os.environ.get("HOST", "127.0.0.1")
    port = int(os.environ.get("PORT", "8765"))
    server = ThreadingHTTPServer((host, port), WaitlistHandler)
    print(f"Waitlist API ready on {host}:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
