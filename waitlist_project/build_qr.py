"""Generate the public waitlist QR using the existing QR Code assignment."""

from __future__ import annotations

import os
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent
REPOSITORY_ROOT = ROOT.parent
QR_ASSIGNMENT = REPOSITORY_ROOT / "qrcode_assignment"
DEFAULT_PUBLIC_URL = "https://lucas950219.github.io/data_structure/waitlist.html"


def project_setting(name: str, default: str) -> str:
    if os.environ.get(name):
        return os.environ[name]
    env_file = ROOT / ".env"
    if env_file.exists():
        for raw in env_file.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if line.startswith(f"{name}="):
                return line.split("=", 1)[1].strip().strip("\"'")
    return default


def main() -> None:
    sys.path.insert(0, str(QR_ASSIGNMENT))
    import qr_web

    public_url = project_setting("PUBLIC_SITE_URL", DEFAULT_PUBLIC_URL)
    output = ROOT / "assets" / "waitlist-qr.png"
    result = qr_web.RunResult("waitlist")
    qr_web.make_qr(public_url, output, "掃描加入候位", None, "M", 12, result)
    print(f"QR Code 已產生：{output}")
    print(f"指向網址：{public_url}")


if __name__ == "__main__":
    main()
