"""Build a submission ZIP after collecting real evidence and an Apps Script log."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import zipfile

ROOT = Path(__file__).resolve().parent
FRONTEND = ["index.html", "waitlist.html", "staff.html", "styles.css", "api.js", "app.js", "staff.js"]
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp"}


def main() -> None:
    parser = argparse.ArgumentParser(description="Package the waitlist assignment without the live API URL.")
    parser.add_argument("--student-id", required=True)
    parser.add_argument("--name", required=True)
    parser.add_argument("--log", required=True, type=Path, help="Actual JSON response from action=log")
    parser.add_argument("--screenshots", required=True, type=Path, help="Directory containing real evidence images")
    parser.add_argument("--report", type=Path, default=ROOT / "報告.md")
    args = parser.parse_args()

    for label, value in (("student ID", args.student_id), ("name", args.name)):
        if not value.strip() or re.search(r'[\\/:*?"<>|]', value) or value.strip() in {".", ".."}:
            parser.error(f"Invalid {label}")

    report = args.report.read_text(encoding="utf-8")
    if any(marker in report for marker in ("［待補", "［請填寫", "＿＿")):
        parser.error("Complete the report placeholders with real details and evidence before packaging.")

    raw_log = args.log.read_text(encoding="utf-8-sig")
    log = json.loads(raw_log)
    events = log.get("events")
    counts = log.get("counts")
    if not isinstance(events, list) or not isinstance(counts, dict):
        parser.error("The log must be the JSON response returned by action=log.")
    allowed = {"join", "notify", "seat", "cancel"}
    actual = {key: 0 for key in allowed}
    for event in events:
        if not isinstance(event, dict) or set(event) != {"time", "action", "ticket", "tableType"} or event.get("action") not in allowed:
            parser.error("The event log contains unexpected fields; inspect it before packaging.")
        actual[event["action"]] += 1
    if any(counts.get(key) != actual[key] for key in allowed):
        parser.error("The event counts do not match the event log.")
    if actual["join"] < 3 or actual["notify"] < 1 or actual["seat"] < 1:
        parser.error("The log needs at least 3 joins, 1 notification and 1 seated entry.")

    if not args.screenshots.is_dir():
        parser.error("The screenshots directory does not exist.")
    images = sorted(p for p in args.screenshots.rglob("*") if p.is_file() and p.suffix.lower() in IMAGE_SUFFIXES)
    if not images:
        parser.error("Add the actual test screenshots before packaging.")

    config = {
        "gasWebAppUrl": "https://script.google.com/macros/s/EXAMPLE_DEPLOYMENT_ID/exec",
        "publicPageUrl": "https://example.github.io/waitlist/",
        "staffPageUrl": "https://example.github.io/waitlist/staff.html",
        "pollIntervalMs": 5000,
    }
    output = ROOT / f"{args.student_id}_{args.name}_候位系統.zip"
    if output.exists():
        parser.error(f"Output already exists: {output}; move it before creating another package.")
    with zipfile.ZipFile(output, "x", compression=zipfile.ZIP_DEFLATED) as archive:
        for name in FRONTEND:
            archive.write(ROOT / name, f"waitlist/{name}")
        archive.write(ROOT / "assets" / "waitlist-qr.png", "waitlist/assets/waitlist-qr.png")
        archive.writestr("waitlist/config.js", "window.WAITLIST_CONFIG = " + json.dumps(config, ensure_ascii=False) + ";\n")
        archive.write(ROOT / "apps_script" / "Code.gs", "Code.gs")
        archive.writestr("報告.md", report)
        archive.writestr("操作紀錄.txt", raw_log)
        for image in images:
            archive.write(image, "證據/" + image.relative_to(args.screenshots).as_posix())
    print(f"Created: {output}")
    print("Verify the screenshots contain no passwords or unwanted personal data before submitting.")


if __name__ == "__main__":
    main()
