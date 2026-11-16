from __future__ import annotations

import json
import re
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from xml.etree import ElementTree as ET

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "news_cache.json"

FEEDS = [
    ("AI", "AI artificial intelligence business technology", "proxy"),
    ("美国", "US stock market Federal Reserve Nvidia business", "proxy"),
    ("中国", "中国 经济 股市 AI 企业 site:gov.cn OR site:stats.gov.cn OR site:csrc.gov.cn OR site:xinhuanet.com", "mainland"),
    ("全球", "global markets business economy", "proxy"),
]

def clean(value: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", value or "")).strip()

def stamp(value: str) -> float:
    try:
        return parsedate_to_datetime(value).timestamp()
    except Exception:
        return 0

def fetch(category: str, query: str, default_access: str) -> list[dict]:
    params = {"q": query, "hl": "zh-CN" if category == "中国" else "en-US", "gl": "CN" if category == "中国" else "US", "ceid": "CN:zh-Hans" if category == "中国" else "US:en"}
    url = "https://news.google.com/rss/search?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": "MorningAlpha/1.0"})
    with urllib.request.urlopen(req, timeout=20) as response:
        root = ET.fromstring(response.read())
    rows = []
    for item in root.findall(".//item")[:12]:
        title = clean(item.findtext("title")); link = clean(item.findtext("link")); desc = clean(item.findtext("description")); pub = clean(item.findtext("pubDate"))
        if not title or not link: continue
        source = "公开资讯"
        match = re.search(r"-\s*([^|]+)$", title)
        if match: source = match.group(1).strip()[:40]
        rows.append({"category": category, "source": source, "title": title, "summary": desc[:260] or "打开原文了解详情。", "link": link, "access": default_access, "timestamp": stamp(pub)})
    return rows

def main() -> None:
    items = []
    for category, query, access in FEEDS:
        try: items.extend(fetch(category, query, access))
        except Exception as exc: print(f"source unavailable: {type(exc).__name__}")
    seen, unique = set(), []
    for item in sorted(items, key=lambda x: x["timestamp"], reverse=True):
        key = re.sub(r"\W", "", item["title"].lower())[:100]
        if key and key not in seen:
            seen.add(key); item["time"] = datetime.fromtimestamp(item["timestamp"], tz=timezone.utc).strftime("%m-%d") if item["timestamp"] else ""; unique.append(item)
    if not unique:
        print("No fresh feed items; keeping existing cache.")
        return
    result = {"updated_at": datetime.now().strftime("%Y-%m-%d %H:%M"), "items": unique[:40]}
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote {len(unique[:40])} items")

if __name__ == "__main__": main()
