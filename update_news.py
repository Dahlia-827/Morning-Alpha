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
    {"kind": "google", "category": "AI", "query": "DeepSeek 开源 模型 项目 人工智能 大模型 最新消息", "access": "mainland"},
    {"kind": "google", "category": "AI", "query": "通义千问 豆包 混元 文心 大模型 发布 新产品 新项目 商业化", "access": "mainland"},
    {"kind": "google", "category": "美国", "query": "Anthropic 上市 英伟达 黄仁勋 OpenAI 微软 AI 公司 最新消息 中文", "access": "mainland"},
    {"kind": "google", "category": "美国", "query": "美国股市 美联储 英伟达 财报 利率 IPO 公司决策 中文", "access": "mainland"},
    {"kind": "google", "category": "中国", "query": "中国 金融 资本市场 科技产业链 企业 政策 site:gov.cn OR site:stats.gov.cn OR site:csrc.gov.cn OR site:pbc.gov.cn OR site:xinhuanet.com", "access": "mainland"},
    {"kind": "google", "category": "商业", "query": "企业家 CEO 公司 并购 IPO 战略 商业决策 科技 中文 site:36kr.com OR site:jiemian.com OR site:cls.cn OR site:caixin.com", "access": "mainland"},
    {"kind": "google", "category": "全球", "query": "全球市场 经济 商业 央行 公司 最新消息 中文", "access": "mainland"},
]

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

# 重点事件种子：只保留少量高关注事件，避免某个免费源暂时不可用时首页变空。
# 日常更新仍以 SOURCES 抓取结果为主；这些条目会在后续版本中逐步替换。
FOCUS_ITEMS = [
    {"category": "AI", "source": "DeepSeek 官方", "title": "DeepSeek 发布 V4.1 Flash，多模态模型上线并继续支持开源生态", "summary": "DeepSeek 官方介绍新模型已上线 API，并表示将继续支持开源社区进行模型适配。", "link": "https://deepseek.com/news/deepseek-v4-1-flash/", "access": "mainland", "timestamp": stamp("2026-09-14T04:00:00+00:00"), "official": True},
    {"category": "美国", "source": "Anthropic 招股书", "title": "Anthropic 公开提交上市招股书，AI 公司进入资本市场关键阶段", "summary": "Anthropic 已公开提交美国上市相关文件，后续可关注发行规模、估值与算力投入。", "link": "https://ipo.anthropic.com/documents/us/prospectus.pdf", "access": "proxy", "timestamp": stamp("2026-11-10T12:00:00+00:00"), "official": True},
    {"category": "美国", "source": "德国之声中文网", "title": "英伟达宣布黄仁勋辞任 CEO，AI 芯片产业链关注接班与战略延续", "summary": "黄仁勋离任后由 CFO 暂代，市场将继续观察英伟达的产品路线、客户关系与资本市场反应。", "link": "https://amp.dw.com/zh/%E9%BB%84%E4%BB%81%E5%8B%8B%E8%BE%9E%E8%81%8C-%E4%B8%AD%E4%BC%81%E5%BF%A7%E7%BE%8E%E6%94%B6%E7%B4%A7%E7%9B%91%E7%AE%A1-%E5%BF%99%E6%8A%A2%E7%A7%9F%E6%B5%B7%E5%A4%96%E8%8B%B1%E4%BC%9F%E8%BE%BE%E7%AE%97%E5%8A%9B/a-79929183", "access": "proxy", "timestamp": stamp("2026-11-12T12:00:00+00:00"), "official": False},
]


def clean(value: str | None) -> str:
    value = html.unescape(value or "")
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", value)).strip()


def has_chinese(value: str) -> bool:
    return bool(re.search(r"[\u4e00-\u9fff]", value))


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
        if title and link and has_chinese(title):
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
        # 面向中文读者：英文标题不直接进入首页，优先等待国内中文转载或官方中文线索。
        if not has_chinese(title):
            continue
        rows.append({"category": source["category"], "source": source_name, "title": title, "summary": summary[:300], "link": link, "access": source["access"], "timestamp": stamp(published), "official": False})
    return rows


def importance(item: dict) -> int:
    text = f"{item.get('title', '')} {item.get('summary', '')}"
    keywords = ("造假", "处罚", "调查", "起诉", "破产", "裁员", "辞任", "任命", "上市", "IPO", "并购", "收购", "融资", "财报", "业绩", "开源", "发布", "重大", "监管")
    return sum(3 for keyword in keywords if keyword.lower() in text.lower()) + (1 if item.get("official") else 0)


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
    for item in sorted(items, key=lambda row: (importance(row), row["timestamp"]), reverse=True):
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
