"""
新闻情绪分析模块
================
从 yfinance 获取近期新闻，通过关键词分析判断市场情绪方向。
不依赖 NLP 模型，使用财经领域的关键词规则引擎。
"""

import yfinance as yf
import re
from datetime import datetime, timedelta


# ============================================================
# 情绪关键词库（中英双语，覆盖财报、评级、业务、风险四大类）
# ============================================================

BULLISH_PATTERNS = [
    # 财报超预期
    (re.compile(r"beat|exceed|surpass|top.*(?:estimate|expect|forecast|consensus)", re.I), 3),
    (re.compile(r"raise.*(?:guidance|outlook|forecast|target)", re.I), 3),
    (re.compile(r"record.*(?:revenue|profit|sales|quarter|growth)", re.I), 3),
    (re.compile(r"超预期|超出预期|优于预期|创纪录", re.I), 3),
    # 增长信号
    (re.compile(r"(?:strong|robust|solid|impressive|stellar)\s+(?:growth|demand|momentum|quarter|result)", re.I), 2),
    (re.compile(r"(?:accelerating|surging|skyrocketing|booming)\s+(?:growth|revenue|demand)", re.I), 3),
    (re.compile(r"growth\s+(?:accelerated|surged|jumped)", re.I), 2),
    (re.compile(r"AI\s+(?:revenue|business|growth|momentum)", re.I), 2),
    # 评级上调
    (re.compile(r"(?:upgrade|upgraded|upgrades)(?:\s+(?:to|target))?", re.I), 2),
    (re.compile(r"raise.*(?:price\s*target|PT)", re.I), 2),
    (re.compile(r"(?:buy|overweight|outperform)\s+rating", re.I), 1),
    (re.compile(r"上调|看好|买入评级", re.I), 2),
    # 业务进展
    (re.compile(r"(?:launch|unveil|announce|release).*(?:new|AI|product|feature)", re.I), 1),
    (re.compile(r"(?:partnership|acquisition|expansion|deal)", re.I), 2),
    (re.compile(r"(?:billion|million)\s+(?:users|customers|subscribers)", re.I), 2),
    # 回购/分红
    (re.compile(r"(?:buyback|share\s+repurchase|increase\s+dividend)", re.I), 1),
]

BEARISH_PATTERNS = [
    # 财报不及预期
    (re.compile(r"miss|missed|below.*(?:estimate|expect|forecast|consensus)", re.I), 3),
    (re.compile(r"cut|lower.*(?:guidance|outlook|forecast|target)", re.I), 3),
    (re.compile(r"(?:disappoint|weak|soft|sluggish|tepid)\s+(?:quarter|result|revenue|demand)", re.I), 2),
    (re.compile(r"不及预期|低于预期|下调", re.I), 3),
    # 衰退信号
    (re.compile(r"(?:declining|shrinking|slowing|decelerating)\s+(?:growth|revenue|margin)", re.I), 2),
    (re.compile(r"growth\s+(?:slowed|declined|decelerated)", re.I), 2),
    # 评级下调
    (re.compile(r"(?:downgrade|downgraded)(?:\s+(?:to|from))?", re.I), 2),
    (re.compile(r"cut.*(?:price\s*target)", re.I), 2),
    (re.compile(r"(?:sell|underweight|underperform)\s+rating", re.I), 2),
    (re.compile(r"下调评级|看空|卖出评级", re.I), 2),
    # 风险事件
    (re.compile(r"(?:investigation|lawsuit|fine|penalty|regulatory|antitrust)", re.I), 3),
    (re.compile(r"(?:layoff|cut.*jobs|restructuring)", re.I), 1),
    (re.compile(r"(?:security|breach|hack|outage|data\s+leak)", re.I), 3),
    (re.compile(r"(?:tariff|trade\s+war|sanction)", re.I), 2),
]


def _score_text(text: str) -> tuple[int, int, list[str]]:
    """
    对单条文本打分。

    返回: (bullish_score, bearish_score, [匹配到的关键词描述])
    """
    bull = 0
    bear = 0
    matches = []

    for pattern, weight in BULLISH_PATTERNS:
        if pattern.search(text):
            bull += weight
            matches.append(f"🟢 +{weight}")

    for pattern, weight in BEARISH_PATTERNS:
        if pattern.search(text):
            bear += weight
            matches.append(f"🔴 -{weight}")

    return bull, bear, matches


def get_news_sentiment(symbol: str, max_articles: int = 20) -> dict:
    """
    获取股票相关新闻并分析情绪（修复版）。

    数据源优先级:
    1. yfinance .news 属性
    2. ticker.get_news() 方法（部分版本支持）
    3. Google News RSS 爬取（fallback）

    返回:
        {
            "articles": [...],
            "overall_sentiment": str,
            "sentiment_score": float,
            "signals": [...],
            "source": str,           # 数据来源
        }
    """
    ticker = yf.Ticker(symbol)
    news = []
    source = "yfinance.news"

    # 来源 1: .news 属性
    try:
        news = ticker.news
    except Exception:
        news = []

    # 来源 2: get_news() 方法
    if not news:
        try:
            news = ticker.get_news()
            source = "yfinance.get_news"
        except Exception:
            pass

    # 来源 3: Google News RSS
    if not news:
        try:
            import xml.etree.ElementTree as ET
            try:
                import requests as _requests
            except ImportError:
                _requests = None

            if _requests:
                url = f"https://news.google.com/rss/search?q={symbol}+stock&hl=en-US&gl=US&ceid=US:en"
                resp = _requests.get(url, timeout=5, headers={"User-Agent": "Mozilla/5.0"})
                if resp.status_code == 200:
                    root = ET.fromstring(resp.text)
                    for item in root.findall(".//item")[:max_articles]:
                        title = item.findtext("title", "")
                        link = item.findtext("link", "")
                        pub_date = item.findtext("pubDate", "")
                        news.append({
                            "title": title,
                            "link": link,
                            "publisher": "Google News",
                            "providerPublishTime": 0,
                        })
                source = "Google News RSS"
        except Exception:
            pass

    if not news:
        return {
            "articles": [],
            "overall_sentiment": "neutral",
            "sentiment_score": 0,
            "source": "无可用新闻源",
            "signals": [{"name": "⚠️ 所有新闻源均不可用（yfinance + Google News）", "type": "neutral", "weight": 0}],
        }

    articles = []
    total_bull = 0
    total_bear = 0

    for item in news[:max_articles]:
        title = item.get("title", "")
        link = item.get("link", "")
        publisher = item.get("publisher", "")
        # timestamp
        pub_time_raw = item.get("providerPublishTime", 0)
        if pub_time_raw:
            pub_time = datetime.fromtimestamp(pub_time_raw)
        else:
            pub_time = None

        # 合并标题和相关内容用于分析
        content = title
        if "relatedTickers" in item:
            pass  # 不需要额外处理

        bull, bear, matches = _score_text(content)

        # 根据是否有匹配来决定是否记录
        if bull > 0 or bear > 0:
            total_bull += bull
            total_bear += bear
            articles.append({
                "title": title,
                "link": link,
                "publisher": publisher,
                "time": pub_time.strftime("%m/%d %H:%M") if pub_time else "",
                "bull_score": bull,
                "bear_score": bear,
                "net": bull - bear,
                "matches": matches,
            })

    # 计算总体情绪
    if total_bull > total_bear * 1.5:
        overall = "bullish"
        sentiment_score = min(100, (total_bull - total_bear) * 5)
    elif total_bear > total_bull * 1.5:
        overall = "bearish"
        sentiment_score = max(-100, -(total_bear - total_bull) * 5)
    else:
        overall = "neutral"
        sentiment_score = (total_bull - total_bear) * 3

    sentiment_score = max(-100, min(100, sentiment_score))

    # 生成信号
    signals = []
    if sentiment_score > 40:
        signals.append({"name": f"新闻情绪强烈看多 (评分 +{sentiment_score})", "type": "bullish", "weight": 3})
    elif sentiment_score > 15:
        signals.append({"name": f"新闻情绪偏多 (评分 +{sentiment_score})", "type": "bullish", "weight": 2})
    elif sentiment_score < -40:
        signals.append({"name": f"新闻情绪强烈看空 (评分 {sentiment_score})", "type": "bearish", "weight": 3})
    elif sentiment_score < -15:
        signals.append({"name": f"新闻情绪偏空 (评分 {sentiment_score})", "type": "bearish", "weight": 2})
    else:
        signals.append({"name": "新闻情绪中性", "type": "neutral", "weight": 0})

    if len(articles) >= 10:
        signals.append({"name": f"近期新闻活跃 ({len(articles)}条)", "type": "neutral", "weight": 0})

    return {
        "articles": sorted(articles, key=lambda a: abs(a["net"]), reverse=True)[:10],
        "overall_sentiment": overall,
        "sentiment_score": round(sentiment_score),
        "source": source,
        "signals": signals,
    }
