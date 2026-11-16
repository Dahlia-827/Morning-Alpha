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
    {"kind": "google", "category": "商业", "query": "企业家 CEO 上市公司 并购 收购 融资 财报 处罚 财务造假 产品发布 中文", "access": "mainland"},
    {"kind": "google", "category": "全球", "query": "全球公司 并购 财报 IPO AI 企业家 产品发布 最新消息 中文", "access": "mainland"},
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

"""旧版固定示例，仅作历史记录，不参与抓取和展示。
FOCUS_ITEMS = [
    {"category": "AI", "source": "DeepSeek 官方", "title": "DeepSeek 发布 V4.1 Flash，多模态模型上线并继续支持开源生态", "summary": "DeepSeek 官方介绍新模型已上线 API，并表示将继续支持开源社区进行模型适配。", "link": "https://deepseek.com/news/deepseek-v4-1-flash/", "access": "mainland", "timestamp": stamp("2026-09-14T04:00:00+00:00"), "official": True},
    {"category": "美国", "source": "Anthropic 招股书", "title": "Anthropic 公开提交上市招股书，AI 公司进入资本市场关键阶段", "summary": "Anthropic 已公开提交美国上市相关文件，后续可关注发行规模、估值与算力投入。", "link": "https://ipo.anthropic.com/documents/us/prospectus.pdf", "access": "proxy", "timestamp": stamp("2026-11-10T12:00:00+00:00"), "official": True},
    {"category": "美国", "source": "德国之声中文网", "title": "英伟达宣布黄仁勋辞任 CEO，AI 芯片产业链关注接班与战略延续", "summary": "黄仁勋离任后由 CFO 暂代，市场将继续观察英伟达的产品路线、客户关系与资本市场反应。", "link": "https://amp.dw.com/zh/%E9%BB%84%E4%BB%81%E5%8B%8B%E8%BE%9E%E8%81%8C-%E4%B8%AD%E4%BC%81%E5%BF%A7%E7%BE%8E%E6%94%B6%E7%B4%A7%E7%9B%91%E7%AE%A1-%E5%BF%99%E6%8A%A2%E7%A7%9F%E6%B5%B7%E5%A4%96%E8%8B%B1%E4%BC%9F%E8%BE%BE%E7%AE%97%E5%8A%9B/a-79929183", "access": "proxy", "timestamp": stamp("2026-11-12T12:00:00+00:00"), "official": False},
]
"""


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


def is_useful(item: dict) -> bool:
    text = f"{item.get('title', '')} {item.get('summary', '')}"
    macro_only = ("国民经济运行", "采购经理指数", "创新指数", "固定资产投资", "房地产市场", "能源生产", "社会消费品零售", "商品住宅", "工业生产者出厂价格", "居民消费价格", "CPI和PPI", "规模以上工业增加值", "价格变动", "国民经济和社会发展", "民生统计", "农业经济", "工业经济", "服务业平稳增长", "流通领域", "投资数据", "消费市场")
    company_signals = ("公司", "企业", "上市", "并购", "收购", "融资", "财报", "公告", "产品", "模型", "开源", "CEO", "创始人", "董事长", "处罚", "造假")
    title = item.get("title", "")
    return not (item.get("category") == "中国" and any(word in title for word in macro_only) and not any(word in title for word in company_signals))


BOOTSTRAP_ITEMS = [
    {"category": "AI", "source": "DeepSeek 官方", "title": "DeepSeek 发布 V4.1 Flash，多模态模型上线并继续支持开源生态", "summary": "模型上线 API，并继续支持开源社区进行模型适配，关注模型能力如何转化为开发者和企业应用。", "link": "https://deepseek.com/news/deepseek-v4-1-flash/", "access": "mainland", "timestamp": datetime.fromisoformat("2026-09-14T04:00:00+00:00").timestamp(), "official": True},
    {"category": "AI", "source": "人民日报·百度世界", "title": "百度发布文心大模型新版本，智能体和企业 AI 应用继续加速", "summary": "百度世界大会集中发布模型、智能体和云计算产品，重点观察 AI 能力如何进入企业场景。", "link": "https://paper.people.com.cn/rmrb/pc/attachement/202611/13/7a72920f-904c-4dd3-a044-30f014d8a60d.pdf", "access": "mainland", "timestamp": datetime.fromisoformat("2026-11-13T04:00:00+00:00").timestamp(), "official": True},
    {"category": "美国", "source": "Anthropic 招股书", "title": "Anthropic 公开提交上市招股书，AI 公司进入资本市场关键阶段", "summary": "关注发行规模、估值、收入增长以及未来算力和数据中心投入。", "link": "https://ipo.anthropic.com/documents/us/prospectus.pdf", "access": "proxy", "timestamp": datetime.fromisoformat("2026-11-10T12:00:00+00:00").timestamp(), "official": True},
    {"category": "美国", "source": "德国之声中文网", "title": "英伟达宣布黄仁勋辞任 CEO，市场关注接班与 AI 芯片战略延续", "summary": "管理层变化可能影响产品路线、客户关系和资本市场预期，先看公司公告与后续安排。", "link": "https://amp.dw.com/zh/%E9%BB%84%E4%BB%81%E5%8B%8B%E8%BE%9E%E8%81%8C-%E4%B8%AD%E4%BC%81%E5%BF%A7%E7%BE%8E%E6%94%B6%E7%B4%A7%E7%9B%91%E7%AE%A1-%E5%BF%99%E6%8A%A2%E7%A7%9F%E6%B5%B7%E5%A4%96%E8%8B%B1%E4%BC%9A%E8%BE%BE%E7%AE%97%E5%8A%9B/a-79929183", "access": "proxy", "timestamp": datetime.fromisoformat("2026-11-12T12:00:00+00:00").timestamp(), "official": False},
    {"category": "商业", "source": "36氪", "title": "AI 科创企业完成新一轮融资，资金继续流向物理 AI 与企业服务", "summary": "企业融资是观察技术商业化的重要窗口，重点看融资规模、投资方和资金用途。", "link": "https://pitchhub.36kr.com/financing-flash", "access": "mainland", "timestamp": datetime.fromisoformat("2026-11-13T03:00:00+00:00").timestamp(), "official": False},
    {"category": "全球", "source": "36氪融资快报", "title": "全球 AI 创业公司融资与产品发布仍在加速，资本继续寻找可落地场景", "summary": "从融资、产品和客户落地三个角度观察 AI 企业是否真正形成商业收入。", "link": "https://pitchhub.36kr.com/financing-flash", "access": "mainland", "timestamp": datetime.fromisoformat("2026-11-13T03:00:00+00:00").timestamp(), "official": False},
]


def main() -> None:
    items: list[dict] = []
    for source in SOURCES:
        try:
            items.extend(fetch_rss(source) if source["kind"] == "rss" else fetch_google(source))
            print(f"ok: {source['name'] if source['kind'] == 'rss' else source['category']}")
        except Exception as exc:
            print(f"unavailable: {source.get('name', source.get('category'))} ({type(exc).__name__})")

    # 某个免费源临时失败时，给空栏目保留少量可点击内容；有实时内容的栏目不使用兜底。
    live_categories = {item["category"] for item in items}
    items.extend(item for item in BOOTSTRAP_ITEMS if item["category"] not in live_categories)

    seen: set[str] = set()
    unique: list[dict] = []
    for item in sorted(items, key=lambda row: (importance(row), row["timestamp"]), reverse=True):
        if not is_useful(item):
            continue
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
