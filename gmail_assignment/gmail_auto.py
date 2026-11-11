#!/usr/bin/env python3
"""Gmail IMAP/SMTP assignment helper. Uses only Python's standard library."""

from __future__ import annotations

import argparse
import datetime as dt
import email
import email.errors
import email.header
import email.message
import email.policy
import email.utils
import imaplib
import json
import os
import re
import smtplib
import socket
import ssl
import sys
import time
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
IMAP_HOST = "imap.gmail.com"
IMAP_PORT = 993
SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 465
NETWORK_TIMEOUT = 20


class AppError(Exception):
    """An expected, user-facing error that should be included in the run log."""


def decode_header_value(value: str | None) -> str:
    if not value:
        return ""
    try:
        pieces = email.header.decode_header(value)
        return str(email.header.make_header(pieces)).replace("\r", " ").replace("\n", " ").strip()
    except (LookupError, UnicodeError, email.errors.HeaderParseError):
        return value.replace("\r", " ").replace("\n", " ").strip()


def load_config(config_path: Path) -> dict[str, str]:
    """Load credentials from JSON, with environment variables taking precedence."""
    raw: dict[str, Any] = {}
    if config_path.exists():
        try:
            parsed = json.loads(config_path.read_text(encoding="utf-8"))
            if not isinstance(parsed, dict):
                raise AppError("設定檔格式錯誤：最外層必須是 JSON 物件。")
            raw = parsed
        except json.JSONDecodeError as exc:
            raise AppError(f"設定檔不是有效 JSON（第 {exc.lineno} 行）。") from None
        except OSError as exc:
            raise AppError(f"無法讀取設定檔：{exc.__class__.__name__}。") from None

    address = os.environ.get("GMAIL_ADDRESS") or raw.get("gmail_address") or raw.get("user", "")
    app_password = os.environ.get("GMAIL_APP_PASSWORD", raw.get("app_password", ""))
    if not isinstance(address, str) or not isinstance(app_password, str):
        raise AppError("設定值格式錯誤；gmail_address 與 app_password 必須是文字。")

    address = address.strip()
    app_password = re.sub(r"\s+", "", app_password)
    if not address or "@" not in address:
        raise AppError("尚未設定有效的 Gmail 地址。請編輯 config.json 或設定 GMAIL_ADDRESS。")
    if len(app_password) != 16:
        raise AppError(
            "應用程式密碼必須是 Google 提供的 16 字元密碼（可含空格）；"
            "請編輯 config.json 或設定 GMAIL_APP_PASSWORD。"
        )
    return {"gmail_address": address, "app_password": app_password}


def redact(text: str, config: dict[str, str] | None) -> str:
    """Keep diagnostics useful while ensuring credentials never enter logs."""
    result = str(text)
    if config:
        for secret in (config.get("app_password", ""), config.get("gmail_address", "")):
            if secret:
                result = result.replace(secret, "[已遮蔽]")
                result = result.replace(secret.replace(" ", ""), "[已遮蔽]")
    return result.replace("\r", " ").replace("\n", " ")


def create_imap(config: dict[str, str]) -> imaplib.IMAP4_SSL:
    client = imaplib.IMAP4_SSL(
        IMAP_HOST,
        IMAP_PORT,
        ssl_context=ssl.create_default_context(),
        timeout=NETWORK_TIMEOUT,
    )
    try:
        client.login(config["gmail_address"], config["app_password"])
    except Exception:
        try:
            client.shutdown()
        except (imaplib.IMAP4.error, OSError):
            pass
        raise
    return client


def create_smtp(config: dict[str, str]) -> smtplib.SMTP_SSL:
    client = smtplib.SMTP_SSL(
        SMTP_HOST,
        SMTP_PORT,
        context=ssl.create_default_context(),
        timeout=NETWORK_TIMEOUT,
    )
    client.ehlo()
    try:
        client.login(config["gmail_address"], config["app_password"])
    except Exception:
        try:
            client.close()
        except (smtplib.SMTPException, OSError):
            pass
        raise
    return client


def _imap_message_numbers(data: list[bytes] | None) -> list[bytes]:
    if not data or not data[0]:
        return []
    return data[0].split()


def _fetch_headers(client: imaplib.IMAP4_SSL, numbers: list[bytes]) -> list[dict[str, str]]:
    messages: list[dict[str, str]] = []
    fields = "(BODY.PEEK[HEADER.FIELDS (DATE FROM SUBJECT MESSAGE-ID)])"
    for number in numbers:
        status, data = client.fetch(number, fields)
        if status != "OK" or not data:
            continue
        raw = next((item[1] for item in data if isinstance(item, tuple) and isinstance(item[1], bytes)), b"")
        if not raw:
            continue
        parsed = email.message_from_bytes(raw, policy=email.policy.default)
        date_value = decode_header_value(parsed.get("Date"))
        sender = decode_header_value(parsed.get("From"))
        subject = decode_header_value(parsed.get("Subject"))
        message_id = decode_header_value(parsed.get("Message-ID"))
        messages.append(
            {
                "_sequence": number.decode("ascii", errors="ignore"),
                "date": date_value,
                "from": sender,
                "subject": subject,
                "message_id": message_id,
            }
        )
    return messages


def _message_date(message: dict[str, str]) -> dt.date | None:
    try:
        parsed = email.utils.parsedate_to_datetime(message.get("date", ""))
        return parsed.date() if parsed else None
    except (TypeError, ValueError, OverflowError):
        return None


def read_inbox(
    config: dict[str, str],
    *,
    limit: int,
    unread: bool = False,
    since: dt.date | None = None,
    subject_filter: str | None = None,
    scan_limit: int = 200,
    save_eml: bool = False,
    run_id: str | None = None,
) -> dict[str, Any]:
    client = create_imap(config)
    try:
        status, data = client.select("INBOX", readonly=True)
        if status != "OK":
            raise AppError("無法開啟 Gmail 收件匣；請確認 IMAP 已啟用。")
        inbox_total = int(data[0]) if data and data[0].isdigit() else 0
        criterion = "UNSEEN" if unread else "ALL"
        status, search_data = client.search(None, criterion)
        if status != "OK":
            raise AppError("IMAP 搜尋失敗。")
        all_numbers = _imap_message_numbers(search_data)
        candidates = all_numbers[-scan_limit:]
        messages = _fetch_headers(client, candidates)

        filtered: list[dict[str, str]] = []
        for message in messages:
            if since and (_message_date(message) is None or _message_date(message) < since):
                continue
            if subject_filter and subject_filter.casefold() not in message["subject"].casefold():
                continue
            filtered.append(message)
        selected = filtered[-limit:]

        saved_files: list[str] = []
        if save_eml and selected:
            eml_dir = ROOT / "results" / "eml"
            eml_dir.mkdir(parents=True, exist_ok=True)
            prefix = run_id or dt.datetime.now().strftime("%Y%m%d_%H%M%S")
            for index, message in enumerate(selected, start=1):
                sequence = message.get("_sequence")
                if not sequence:
                    continue
                fetch_status, raw_data = client.fetch(sequence.encode("ascii"), "(BODY.PEEK[])")
                raw_email = next(
                    (item[1] for item in (raw_data or []) if isinstance(item, tuple) and isinstance(item[1], bytes)),
                    b"",
                )
                if fetch_status == "OK" and raw_email:
                    target = eml_dir / f"{prefix}_{index:02d}.eml"
                    target.write_bytes(raw_email)
                    saved_files.append(str(target.relative_to(ROOT)))
        for message in selected:
            message.pop("_sequence", None)
        return {
            "inbox_total": inbox_total,
            "searched_count": len(all_numbers),
            "scanned_count": len(candidates),
            "matched_count": len(filtered),
            "read_count": len(selected),
            "limit": limit,
            "filters": {
                "unread": unread,
                "since": since.isoformat() if since else None,
                "subject": subject_filter,
            },
            "messages": selected,
            "saved_eml": saved_files,
        }
    finally:
        try:
            client.logout()
        except (imaplib.IMAP4.error, OSError):
            pass


def send_and_verify(
    config: dict[str, str],
    *,
    recipient: str,
    subject: str,
    body: str,
    verify_timeout: int,
    run_id: str,
) -> dict[str, Any]:
    if "@" not in recipient or "\r" in recipient or "\n" in recipient:
        raise AppError("收件者地址格式不正確。")
    if "\r" in subject or "\n" in subject:
        raise AppError("主旨不可包含換行字元。")

    message = email.message.EmailMessage(policy=email.policy.SMTP)
    message["From"] = config["gmail_address"]
    message["To"] = recipient
    message["Subject"] = subject
    message["Date"] = email.utils.formatdate(localtime=True)
    message_id = email.utils.make_msgid(domain="gmail-auto.local")
    message["Message-ID"] = message_id
    message["X-Gmail-Auto-Run-ID"] = run_id
    message.set_content(body)

    smtp = create_smtp(config)
    try:
        refused = smtp.send_message(message)
        sent_at = dt.datetime.now().astimezone().isoformat(timespec="seconds")
        smtp.quit()
    except Exception:
        try:
            smtp.close()
        except OSError:
            pass
        raise
    if refused:
        raise AppError("SMTP 拒收部分收件者；請檢查收件地址。")

    started = time.monotonic()
    deadline = started + max(0, verify_timeout)
    found = False
    while True:
        try:
            read = read_inbox(config, limit=50, scan_limit=500)
            found = any(item.get("message_id", "").strip("<>") == message_id.strip("<>") for item in read["messages"])
        except (AppError, imaplib.IMAP4.error, OSError, ssl.SSLError):
            found = False
        if found or time.monotonic() >= deadline:
            break
        time.sleep(min(3, max(0, deadline - time.monotonic())))

    return {
        "recipient": recipient,
        "subject": subject,
        "sent_at": sent_at,
        "message_id": message_id,
        "smtp_host": f"{SMTP_HOST}:{SMTP_PORT}",
        "verified_in_inbox": found,
        "verification_seconds": round(time.monotonic() - started, 2),
        "verification_note": "驗證信箱為本帳號 INBOX；寄給其他帳號時，請在收件端確認。",
    }


def run_selftest(config: dict[str, str]) -> dict[str, Any]:
    checks: dict[str, str] = {}
    imap_client = None
    smtp_client = None
    try:
        imap_client = create_imap(config)
        checks["IMAP"] = f"登入成功（{IMAP_HOST}:{IMAP_PORT}，SSL）"
    finally:
        if imap_client is not None:
            try:
                imap_client.logout()
            except (imaplib.IMAP4.error, OSError):
                pass
    try:
        smtp_client = create_smtp(config)
        checks["SMTP"] = f"登入成功（{SMTP_HOST}:{SMTP_PORT}，SSL）"
    finally:
        if smtp_client is not None:
            try:
                smtp_client.quit()
            except (smtplib.SMTPException, OSError):
                pass
    return {"checks": checks, "result": "IMAP 與 SMTP 認證皆成功。"}


def write_run_log(result: dict[str, Any]) -> tuple[Path, Path]:
    result_dir = ROOT / "results"
    result_dir.mkdir(parents=True, exist_ok=True)
    stem = f"run_{result['run_id']}"
    json_path = result_dir / f"{stem}.json"
    md_path = result_dir / f"{stem}.md"
    json_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    lines = [
        f"# Gmail 自動讀寫執行紀錄：{result['run_id']}",
        "",
        f"- 指令：`{result['command']}`",
        f"- 開始時間：{result['started_at']}",
        f"- 結束時間：{result['finished_at']}",
        f"- 狀態：{result['status']}",
        f"- 摘要：{result['summary']}",
    ]
    details = result.get("details", {})
    if "inbox_total" in details:
        lines.extend(
            [
                "",
                "## 讀信結果",
                "",
                f"- 收件匣信件總數：{details['inbox_total']}",
                f"- 搜尋到：{details['searched_count']} 封；掃描：{details['scanned_count']} 封；符合篩選：{details['matched_count']} 封；輸出：{details['read_count']} 封",
                "",
                "| 日期 | 寄件者 | 主旨 |",
                "| --- | --- | --- |",
            ]
        )
        for item in details.get("messages", []):
            safe = [item.get(key, "").replace("|", "\\|") for key in ("date", "from", "subject")]
            lines.append("| " + " | ".join(safe) + " |")
        if details.get("saved_eml"):
            lines.extend(["", "儲存的 EML：" + ", ".join(details["saved_eml"])])
    if "recipient" in details:
        lines.extend(
            [
                "",
                "## 寄信與驗證",
                "",
                f"- 收件者：{details['recipient']}",
                f"- 主旨：{details['subject']}",
                f"- 寄出時間：{details['sent_at']}",
                f"- 收件匣驗證：{'成功' if details['verified_in_inbox'] else '未找到'}",
                f"- 驗證耗時：{details['verification_seconds']} 秒",
                f"- 說明：{details['verification_note']}",
            ]
        )
    if "checks" in details:
        lines.extend(["", "## 連線檢查", ""])
        for name, status in details["checks"].items():
            lines.append(f"- {name}：{status}")
    if result.get("error"):
        lines.extend(["", "## 錯誤", "", result["error"]])
    lines.extend(["", "> 本紀錄不包含應用程式密碼或郵件內文。", ""])
    md_path.write_text("\n".join(lines), encoding="utf-8")
    return md_path, json_path


def safe_print(text: Any, file: Any = None) -> None:
    """Print text safely when the active Windows code page cannot encode it."""
    target = file or sys.stdout
    try:
        print(text, file=file)
    except UnicodeEncodeError:
        encoding = getattr(target, "encoding", None) or "utf-8"
        printable = str(text).encode(encoding, errors="backslashreplace").decode(encoding)
        print(printable, file=file)

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="使用 Gmail 應用程式密碼透過 IMAP 讀信、SMTP 寄信。每次執行會寫入 results/ 紀錄。"
    )
    parser.add_argument("--config", default=str(ROOT / "config.json"), help="設定檔路徑（預設：專案內 config.json）")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("selftest", help="登入 IMAP 與 SMTP，檢查設定與連線")

    read_parser = subparsers.add_parser("read", help="讀取收件匣最新信件")
    read_parser.add_argument("--limit", type=int, default=5, help="輸出封數，預設 5")
    read_parser.add_argument("--scan-limit", type=int, default=200, help="最多掃描最近封數，預設 200")
    read_parser.add_argument("--unread", action="store_true", help="只讀未讀信")
    read_parser.add_argument("--since", type=dt.date.fromisoformat, help="只讀此日期之後的信，例如 2026-10-01")
    read_parser.add_argument("--subject", help="只輸出主旨含此關鍵字的信")
    read_parser.add_argument("--save-eml", action="store_true", help="將符合條件的完整郵件存為 EML（可能含私人內容）")

    send_parser = subparsers.add_parser("send", help="寄送一封純文字郵件並嘗試在本帳號收件匣驗證")
    send_parser.add_argument("--to", required=True, help="收件者 Gmail 地址")
    send_parser.add_argument("--subject", required=True, help="郵件主旨")
    send_parser.add_argument("--body", required=True, help="純文字郵件內容")
    send_parser.add_argument("--verify-timeout", type=int, default=30, help="等待收件匣驗證秒數，預設 30")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "read" and (args.limit < 1 or args.scan_limit < 1):
        parser.error("--limit 與 --scan-limit 必須大於 0")
    if args.command == "send" and args.verify_timeout < 0:
        parser.error("--verify-timeout 不可小於 0")

    started = dt.datetime.now().astimezone()
    run_id = started.strftime("%Y%m%d_%H%M%S_%f")
    if args.command == "send":
        command = f"send --to {args.to} --subject {args.subject!r} --body [內文已遮蔽]"
    elif args.command == "read":
        filters = []
        if args.unread:
            filters.append("--unread")
        if args.since:
            filters.extend(["--since", args.since.isoformat()])
        if args.subject:
            filters.extend(["--subject", args.subject])
        if args.save_eml:
            filters.append("--save-eml")
        command = f"read --limit {args.limit} --scan-limit {args.scan_limit} " + " ".join(filters)
    else:
        command = "selftest"
    result: dict[str, Any] = {
        "run_id": run_id,
        "command": command,
        "started_at": started.isoformat(timespec="seconds"),
        "finished_at": "",
        "status": "failure",
        "summary": "執行失敗。",
        "details": {},
        "error": None,
    }
    config: dict[str, str] | None = None
    try:
        config_path = Path(args.config)
        if not config_path.is_absolute():
            config_path = ROOT / config_path
        config = load_config(config_path)
        if args.command == "selftest":
            result["details"] = run_selftest(config)
            result["status"] = "success"
            result["summary"] = "IMAP 與 SMTP 登入檢查成功。"
        elif args.command == "read":
            result["details"] = read_inbox(
                config,
                limit=args.limit,
                unread=args.unread,
                since=args.since,
                subject_filter=args.subject,
                scan_limit=args.scan_limit,
                save_eml=args.save_eml,
                run_id=run_id,
            )
            result["status"] = "success"
            result["summary"] = f"讀取 {result['details']['read_count']} 封信（收件匣共 {result['details']['inbox_total']} 封）。"
        else:
            result["details"] = send_and_verify(
                config,
                recipient=args.to,
                subject=args.subject,
                body=args.body,
                verify_timeout=args.verify_timeout,
                run_id=run_id,
            )
            if result["details"]["verified_in_inbox"]:
                result["status"] = "success"
                result["summary"] = "寄信成功，並在本帳號收件匣找到寄出的郵件。"
            else:
                result["status"] = "partial"
                result["summary"] = "SMTP 寄信成功，但等待期間未在本帳號收件匣找到郵件。"
    except (AppError, imaplib.IMAP4.error, smtplib.SMTPException, OSError, ssl.SSLError, socket.timeout) as exc:
        message = str(exc) if isinstance(exc, AppError) else f"{exc.__class__.__name__}: {exc}"
        result["error"] = redact(message, config)
        result["summary"] = result["error"]
    except Exception as exc:  # Keep unexpected errors visible and recorded rather than crashing silently.
        result["error"] = redact(f"未預期錯誤：{exc.__class__.__name__}: {exc}", config)
        result["summary"] = result["error"]
    finally:
        result["finished_at"] = dt.datetime.now().astimezone().isoformat(timespec="seconds")
        try:
            md_path, json_path = write_run_log(result)
            safe_print(result["summary"])
            if args.command == "read" and result.get("details", {}).get("messages"):
                safe_print("日期 | 寄件者 | 主旨")
                for item in result["details"]["messages"]:
                    safe_print(f"{item.get('date', '')} | {item.get('from', '')} | {item.get('subject', '')}")
            safe_print(f"Markdown 紀錄：{md_path.relative_to(ROOT)}")
            safe_print(f"JSON 紀錄：{json_path.relative_to(ROOT)}")
        except OSError as exc:
            safe_print(f"{result['summary']}；無法寫入執行紀錄：{exc.__class__.__name__}", file=sys.stderr)
    return 0 if result["status"] == "success" else 1


if __name__ == "__main__":
    raise SystemExit(main())
