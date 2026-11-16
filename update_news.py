from __future__ import annotations

import html
import json
import os
import re
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from xml.etree import ElementTree as ET

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "news_cache.json"
USER_AGENT = "MorningAlpha/1.1 (+https://dahlia-827.github.io/Morning-Alpha/)"

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# 官方 RSS 是主干；主题检索用于补充 AI、企业决策和跨市场线索。
# access=mainland 表示来源本身通常可在中国大陆直接访问；proxy 表示可能需要代理。
SOURCES = [
    {"kind": "rss", "category": "中国", "name": "国家统计局", "url": "https://www.stats.gov.cn/sj/zxfb/rss.xml", "access": "mainland"},
    {"kind": "rss", "category": "中国", "name": "国家统计局·数据解读", "url": "https://www.stats.gov.cn/sj/sjjd/rss.xml", "access": "mainland"},
    {"kind": "rss", "category": "美国", "name": "Federal Reserve", "url": "https://www.federalreserve.gov/feeds/press_all.xml", "access": "proxy"},
    {"kind": "rss", "category": "美国", "name": "U.S. SEC", "url": "https://www.sec.gov/rss/news/press.xml", "access": "proxy"},
    {"kind": "google", "category": "AI", "query": "AI artificial intelligence model chip cloud enterprise business", "access": "proxy"},
    {"kind": "google", "category": "美国", "query": "US stock market Federal Reserve Nvidia earnings IPO business", "access": "proxy"},
    {"kind": "google", "category": "中国", "query": "中国 金融 资本市场 科技产业链 企业 政策 site:gov.cn OR site:stats.gov.cn OR site:csrc.gov.cn OR site:pbc.gov.cn OR site:xinhuanet.com", "access": "mainland"},
    {"kind": "google", "category": "商业", "query": "企业家 CEO 公司 并购 IPO 战略 商业决策 科技", "access": "mainland"},
    {"kind": "google", "category": "全球", "query": "global markets economy business central bank companies", "access": "proxy"},
]


def clean(value: str | None) -> str:
    value = html.unescape(value or "")
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", value)).strip()


def stamp(value: str | None) -> float:
    if not value:
        return 0
    try:
        return parsedate_to_datetime(value).timestamp()
    except (TypeError, ValueError, OverflowError):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
        except (TypeError, ValueError, OverflowError):
            return 0


def request_xml(url: str) -> ET.Element:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/rss+xml, application/xml, text/xml"})
    with urllib.request.urlopen(request, timeout=25) as response:
        return ET.fromstring(response.read())


def text_from(element: ET.Element, names: tuple[str, ...]) -> str:
    for name in names:
        node = element.find(name)
        if node is not None and node.text:
            return clean(node.text)
    return ""


def fetch_rss(source: dict) -> list[dict]:
    root = request_xml(source["url"])
    entries = root.findall(".//item") or root.findall(".//{http://www.w3.org/2005/Atom}entry")
    rows = []
    for entry in entries[:15]:
        title = text_from(entry, ("title", "{http://www.w3.org/2005/Atom}title"))
        link = text_from(entry, ("link", "{http://www.w3.org/2005/Atom}link"))
        if not link:
            link_node = entry.find("{http://www.w3.org/2005/Atom}link")
            link = clean(link_node.attrib.get("href")) if link_node is not None else ""
        summary = text_from(entry, ("description", "summary", "{http://www.w3.org/2005/Atom}summary", "{http://purl.org/rss/1.0/modules/content/}encoded"))
        published = text_from(entry, ("pubDate", "published", "updated", "{http://www.w3.org/2005/Atom}published", "{http://www.w3.org/2005/Atom}updated"))
        if title and link:
            rows.append({"category": source["category"], "source": source["name"], "title": title, "summary": summary[:300], "link": link, "access": source["access"], "timestamp": stamp(published), "official": True})
    return rows


def fetch_google(source: dict) -> list[dict]:
    params = {"q": source["query"], "hl": "zh-CN" if source["category"] in {"中国", "商业"} else "en-US", "gl": "CN" if source["category"] in {"中国", "商业"} else "US", "ceid": "CN:zh-Hans" if source["category"] in {"中国", "商业"} else "US:en"}
    root = request_xml("https://news.google.com/rss/search?" + urllib.parse.urlencode(params))
    rows = []
    for item in root.findall(".//item")[:12]:
        title = text_from(item, ("title",))
        link = text_from(item, ("link",))
        summary = text_from(item, ("description",))
        published = text_from(item, ("pubDate",))
        if not title or not link:
            continue
        match = re.search(r"\s-\s([^|]+)$", title)
        source_name = match.group(1).strip()[:50] if match else "公开资讯聚合"
        rows.append({"category": source["category"], "source": source_name, "title": title, "summary": summary[:300], "link": link, "access": source["access"], "timestamp": stamp(published), "official": False})
    return rows


def main() -> None:
    items: list[dict] = []
    for source in SOURCES:
        try:
            items.extend(fetch_rss(source) if source["kind"] == "rss" else fetch_google(source))
            print(f"ok: {source['name'] if source['kind'] == 'rss' else source['category']}")
        except Exception as exc:
            print(f"unavailable: {source.get('name', source.get('category'))} ({type(exc).__name__})")

    seen: set[str] = set()
    unique: list[dict] = []
    for item in sorted(items, key=lambda row: row["timestamp"], reverse=True):
        key = re.sub(r"\W", "", item["title"].lower())[:120]
        if not key or key in seen:
            continue
        seen.add(key)
        item["time"] = datetime.fromtimestamp(item["timestamp"], tz=timezone.utc).strftime("%m-%d") if item["timestamp"] else ""
        unique.append(item)

    if not unique:
        print("No fresh feed items; keeping existing cache.")
        return
    result = {"updated_at": datetime.now().strftime("%Y-%m-%d %H:%M"), "items": unique[:60], "source_count": len(SOURCES)}
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote {len(result['items'])} items from {len(SOURCES)} sources")


if __name__ == "__main__":
    main()
