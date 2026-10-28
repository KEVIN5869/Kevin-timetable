"""拉取 TimeEdit 的 ics，生成 _site/index.html。

用法：python build.py
链接从环境变量 ICS_URL 读取；本地没有设置时，从 .env 文件读取。
拉取失败时直接报错退出，不会覆盖已经上线的网页。
"""

from __future__ import annotations

import os
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from timetable import build_page

ROOT = Path(__file__).parent
OUTPUT = ROOT / "_site" / "index.html"


def load_ics_url(env_file: Path = ROOT / ".env") -> str:
    url = os.environ.get("ICS_URL", "").strip()
    if not url and env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            key, _, value = line.partition("=")
            if key.strip() == "ICS_URL":
                url = value.strip().strip('"').strip("'")
    if not url:
        raise SystemExit("没有找到 ICS_URL：请在 .env 文件或环境变量里设置。")
    return url


def fetch_ics(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(request, timeout=30) as response:
        data = response.read()
    if b"BEGIN:VCALENDAR" not in data[:1000]:
        raise ValueError("拉取到的内容不是 ics 课表，可能链接失效了。")
    return data


def main() -> None:
    now = datetime.now(timezone.utc)
    html = build_page(fetch_ics(load_ics_url()), now)
    OUTPUT.parent.mkdir(exist_ok=True)
    OUTPUT.write_text(html, encoding="utf-8")
    print(f"已生成 {OUTPUT.relative_to(ROOT)}")


if __name__ == "__main__":
    sys.exit(main())
