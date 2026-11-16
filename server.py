from __future__ import annotations

import json
import re
import time
import urllib.parse
import urllib.request
import webbrowser
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from xml.etree import ElementTree as ET

ROOT = Path(__file__).resolve().parent
CACHE = ROOT / "news_cache.json"
PORT = 8765

FEEDS = [
    ("AI", "https://news.google.com/rss/search?" + urllib.parse.urlencode({"q": "AI artificial intelligence technology", "hl": "en-US", "gl": "US", "ceid": "US:en"})),
    ("美国", "https://news.google.com/rss/search?" + urllib.parse.urlencode({"q": "US stock market Federal Reserve economy", "hl": "en-US", "gl": "US", "ceid": "US:en"})),
    ("中国", "https://news.google.com/rss/search?" + urllib.parse.urlencode({"q": "中国 股市 金融 经济 科技", "hl": "zh-CN", "gl": "CN", "ceid": "CN:zh-Hans"})),
    ("全球", "https://www.federalreserve.gov/feeds/press_all.xml"),
]

FALLBACK = [
    {"category": "AI", "source": "示例内容", "title": "AI 基础设施仍是科技市场的核心叙事", "summary": "关注模型能力提升是否继续转化为云服务、芯片、数据中心和企业软件收入。", "link": "#", "time": ""},
    {"category": "美国", "source": "示例内容", "title": "利率预期与成长股估值继续相互牵动", "summary": "先看利率和债券，再看科技股表现，最后看行业轮动。", "link": "#", "time": ""},
    {"category": "中国", "source": "示例内容", "title": "中国市场重点仍在政策落地、内需修复与科技产业链", "summary": "把政策表述与上市公司订单、利润和现金流放在一起观察。", "link": "#", "time": ""},
]

def clean(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", text or "")).strip()

def parse_date(value: str) -> float:
    try:
        return parsedate_to_datetime(value).timestamp()
    except Exception:
        return 0

def fetch_feed(category: str, url: str) -> list[dict]:
    request = urllib.request.Request(url, headers={"User-Agent": "MorningAlpha/1.0"})
    with urllib.request.urlopen(request, timeout=15) as response:
        root = ET.fromstring(response.read())
    rows = []
    for item in root.findall(".//item")[:12]:
        title = clean(item.findtext("title"))
        link = clean(item.findtext("link"))
        description = clean(item.findtext("description"))
        published = clean(item.findtext("pubDate"))
        if title and link:
            source = "公开资讯"
            match = re.search(r"-\s*([^|]+)$", title)
            if match:
                source = match.group(1).strip()
            rows.append({"category": category, "source": source[:40], "title": title, "summary": description[:240], "link": link, "timestamp": parse_date(published)})
    return rows

def load_items() -> dict:
    now = time.time()
    if CACHE.exists() and now - CACHE.stat().st_mtime < 21600:
        return json.loads(CACHE.read_text(encoding="utf-8"))
    all_items = []
    for category, url in FEEDS:
        try:
            all_items.extend(fetch_feed(category, url))
        except Exception as exc:
            print("feed failed:", type(exc).__name__)
    seen, unique = set(), []
    for item in sorted(all_items, key=lambda x: x.get("timestamp", 0), reverse=True):
        key = re.sub(r"\W", "", item["title"].lower())[:90]
        if key and key not in seen:
            seen.add(key)
            item["time"] = datetime.fromtimestamp(item["timestamp"], tz=timezone.utc).strftime("%m-%d") if item["timestamp"] else ""
            unique.append(item)
    if not unique:
        unique = FALLBACK
    result = {"updated_at": datetime.now().strftime("%Y-%m-%d %H:%M"), "items": unique[:30]}
    CACHE.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result

class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)
    def do_GET(self):
        if self.path == "/api/news":
            body = json.dumps(load_items(), ensure_ascii=False).encode("utf-8")
            self.send_response(200); self.send_header("Content-Type", "application/json; charset=utf-8"); self.send_header("Cache-Control", "no-store"); self.end_headers(); self.wfile.write(body); return
        super().do_GET()

if __name__ == "__main__":
    print(f"Morning Alpha running at http://localhost:{PORT}")
    webbrowser.open(f"http://localhost:{PORT}")
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
