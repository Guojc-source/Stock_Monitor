"""
Ticker Alias Resolution
========================
Resolve company names (Chinese / English) to standard ticker symbols.

Coverage:
  - US:    "微软" / "Microsoft" → MSFT
  - HK:    "腾讯" → 0700.HK
  - A-share: "茅台" / "贵州茅台" → 600519.SS

Usage:
    from ticker_alias import resolve_name, is_ticker
    resolve_name("微软")      # → "MSFT"
    resolve_name("腾讯")      # → "0700.HK"
    is_ticker("MSFT")         # → True
"""

import re


# ═══════════════════════════════════════════════════════════════
#  别名字典（英文 key 全部小写，中文 key 保持原文）
# ═══════════════════════════════════════════════════════════════

_ALIAS_US = {
    # ── 七巨头 Mag 7 ──
    "microsoft":       "MSFT",   "微软":         "MSFT",
    "apple":           "AAPL",   "苹果":         "AAPL",
    "nvidia":          "NVDA",   "英伟达":       "NVDA",
    "alphabet":        "GOOGL",  "谷歌":         "GOOGL",
    "google":          "GOOGL",
    "amazon":          "AMZN",   "亚马逊":       "AMZN",
    "meta":            "META",   "脸书":         "META",
    "facebook":        "META",
    "tesla":           "TSLA",   "特斯拉":       "TSLA",

    # ── 半导体 ──
    "amd":             "AMD",    "超威":         "AMD",
    "超威半导体":      "AMD",
    "intel":           "INTC",   "英特尔":       "INTC",
    "qualcomm":        "QCOM",   "高通":         "QCOM",
    "broadcom":        "AVGO",   "博通":         "AVGO",
    "tsmc":            "TSM",    "台积电":       "TSM",
    "asml":            "ASML",
    "arm":             "ARM",
    "marvell":         "MRVL",
    "arm holdings":    "ARM",

    # ── 软件 / 云 / AI ──
    "adobe":           "ADBE",
    "salesforce":      "CRM",
    "oracle":          "ORCL",   "甲骨文":       "ORCL",
    "ibm":             "IBM",
    "servicenow":      "NOW",    "service now":  "NOW",
    "snowflake":       "SNOW",
    "palantir":        "PLTR",
    "crowdstrike":     "CRWD",
    "mongodb":         "MDB",
    "datadog":         "DDOG",
    "workday":         "WDAY",
    "intuit":          "INTU",
    "sap":             "SAP",
    "sap se":          "SAP",

    # ── 金融 ──
    "jpmorgan":        "JPM",    "摩根大通":     "JPM",
    "摩根":            "JPM",
    "goldman":         "GS",     "高盛":         "GS",
    "goldman sachs":   "GS",
    "berkshire":       "BRK-B",  "伯克希尔":     "BRK-B",
    "visa":            "V",
    "mastercard":      "MA",     "万事达":       "MA",
    "bank of america": "BAC",    "美国银行":     "BAC",
    "morgan stanley":  "MS",     "摩根士丹利":   "MS",
    "大摩":            "MS",
    "paypal":          "PYPL",
    "square":          "SQ",     "block":        "SQ",

    # ── 消费 ──
    "netflix":         "NFLX",   "奈飞":         "NFLX",
    "disney":          "DIS",    "迪士尼":       "DIS",
    "nike":            "NKE",    "耐克":         "NKE",
    "starbucks":       "SBUX",   "星巴克":       "SBUX",
    "coca-cola":       "KO",     "可口可乐":     "KO",
    "cocacola":        "KO",     "cola":         "KO",
    "pepsi":           "PEP",    "百事":         "PEP",
    "pepsico":         "PEP",
    "mcdonalds":       "MCD",    "麦当劳":       "MCD",
    "mcdonald's":      "MCD",
    "costco":          "COST",   "好市多":       "COST",
    "walmart":         "WMT",    "沃尔玛":       "WMT",
    "home depot":      "HD",
    "lululemon":       "LULU",

    # ── 医疗 ──
    "johnson":         "JNJ",    "强生":         "JNJ",
    "johnson & johnson": "JNJ",
    "unitedhealth":    "UNH",
    "eli lilly":       "LLY",    "礼来":         "LLY",
    "pfizer":          "PFE",    "辉瑞":         "PFE",
    "merck":           "MRK",    "默沙东":       "MRK",
    "abbvie":          "ABBV",
    "moderna":         "MRNA",

    # ── 能源 ──
    "exxon":           "XOM",    "埃克森":       "XOM",
    "埃克森美孚":      "XOM",
    "chevron":         "CVX",    "雪佛龙":       "CVX",
    "conocophillips":  "COP",
    "schlumberger":    "SLB",    "斯伦贝谢":     "SLB",

    # ── 工业 ──
    "caterpillar":     "CAT",    "卡特彼勒":     "CAT",
    "deere":           "DE",     "迪尔":         "DE",
    "ge":              "GE",     "通用电气":     "GE",
    "honeywell":       "HON",    "霍尼韦尔":     "HON",
    "boeing":          "BA",     "波音":         "BA",

    # ── 电信 / 媒体 ──
    "at&t":            "T",      "美国电话电报":  "T",
    "verizon":         "VZ",
    "t-mobile":        "TMUS",
    "comcast":         "CMCSA",

    # ── 交通 / 出行 ──
    "uber":            "UBER",   "优步":         "UBER",
    "lyft":            "LYFT",
    "airbnb":          "ABNB",

    # ── EV / 汽车 ──
    "rivian":          "RIVN",
    "lucid":           "LCID",
    "nio":             "NIO",    "蔚来美股":     "NIO",
    "xpeng":           "XPEV",   "小鹏美股":     "XPEV",
    "li auto":         "LI",     "理想美股":     "LI",
    "byd us":          "BYDDY",  "比亚迪美股":   "BYDDY",
}

_ALIAS_HK = {
    "腾讯":            "0700.HK",
    "腾讯控股":        "0700.HK",
    "阿里巴巴":        "9988.HK",
    "阿里":            "9988.HK",
    "美团":            "3690.HK",
    "小米":            "1810.HK",
    "小米集团":        "1810.HK",
    "京东":            "9618.HK",
    "京东集团":        "9618.HK",
    "网易":            "9999.HK",
    "百度":            "9888.HK",
    "百度集团":        "9888.HK",
    "哔哩哔哩":        "9626.HK",
    "b站":             "9626.HK",
    "理想汽车":        "2015.HK",
    "理想":            "2015.HK",
    "蔚来":            "9866.HK",
    "小鹏":            "9868.HK",
    "小鹏汽车":        "9868.HK",
    "商汤":            "0020.HK",
    "商汤科技":        "0020.HK",
    "中国移动":        "0941.HK",
    "中国平安":        "2318.HK",
    "平安":            "2318.HK",
    "招商银行":        "3968.HK",
    "建设银行":        "0939.HK",
    "工商银行":        "1398.HK",
    "汇丰":            "0005.HK",
    "汇丰控股":        "0005.HK",
    "友邦":            "1299.HK",
    "aia":             "1299.HK",
    "港交所":          "0388.HK",
    "快手":            "1024.HK",
    "携程":            "9961.HK",
    "李宁":            "2331.HK",
    "安踏":            "2020.HK",
    "安踏体育":        "2020.HK",
    "农夫山泉":        "9633.HK",
}

_ALIAS_CN = {
    "茅台":            "600519.SS",
    "贵州茅台":        "600519.SS",
    "五粮液":          "000858.SZ",
    "宁德时代":        "300750.SZ",
    "宁德":            "300750.SZ",
    "比亚迪":          "002594.SZ",
    "比亚迪a":         "002594.SZ",
    "中国平安a":       "601318.SS",
    "招商银行a":       "600036.SS",
    "隆基":            "601012.SS",
    "隆基绿能":        "601012.SS",
    "中芯国际":        "688981.SS",
    "海康威视":        "002415.SZ",
    "恒瑞医药":        "600276.SS",
    "药明康德":        "603259.SS",
    "迈瑞医疗":        "300760.SZ",
    "美的集团":        "000333.SZ",
    "美的":            "000333.SZ",
    "格力电器":        "000651.SZ",
    "格力":            "000651.SZ",
    "立讯精密":        "002475.SZ",
}

# ETF 别名（常用名称 → 代码）
_ALIAS_ETF = {
    "标普500":         "SPY",
    "标普":            "SPY",
    "纳指":            "QQQ",
    "纳指100":         "QQQ",
    "纳斯达克":        "QQQ",
    "道琼斯":          "DIA",
    "罗素2000":        "IWM",
    "黄金etf":         "GLD",
    "黄金":            "GLD",
    "白银etf":         "SLV",
    "长期国债":        "TLT",
    "国债etf":         "TLT",
    "半导体etf":       "SOXX",
    "半导体":          "SOXX",
    "方舟":            "ARKK",
    "方舟创新":        "ARKK",
    "恐慌指数":        "VIXY",
    "vix":             "VIXY",
}


# ═══════════════════════════════════════════════════════════════
#  构建查找表
# ═══════════════════════════════════════════════════════════════

def _build_lookup() -> dict[str, str]:
    """合并所有别名字典，英文 key 统一小写"""
    merged = {}
    for d in (_ALIAS_US, _ALIAS_HK, _ALIAS_CN, _ALIAS_ETF):
        for key, ticker in d.items():
            lookup_key = key.lower() if key.isascii() else key
            merged[lookup_key] = ticker
    return merged


_LOOKUP: dict[str, str] = _build_lookup()

# 反向索引: ticker → 所有别名（用于错误提示）
_REVERSE: dict[str, list[str]] = {}
for _k, _v in _LOOKUP.items():
    _REVERSE.setdefault(_v, []).append(_k)


# ═══════════════════════════════════════════════════════════════
#  公共 API
# ═══════════════════════════════════════════════════════════════

# 标准代码正则
_TICKER_RE = re.compile(r"^[A-Z]{1,5}$")                    # 美股: MSFT, V, BRK-B 不支持（用 BRK.B）
_TICKER_DOT_RE = re.compile(r"^[A-Z]{1,4}\.[A-Z]$")        # BRK.B
_TICKER_SUFFIX_RE = re.compile(r"^\d{4,6}\.(SS|SZ|HK)$", re.I)  # 600519.SS, 0700.HK


def is_ticker(s: str) -> bool:
    """判断字符串是否已经是标准股票代码（无需解析）"""
    s = s.strip()
    return bool(
        _TICKER_RE.match(s)
        or _TICKER_DOT_RE.match(s)
        or _TICKER_SUFFIX_RE.match(s)
    )


def resolve_name(name: str) -> str | None:
    """
    将公司名称解析为股票代码。

    参数:
        name: 公司名称（英文/中文均可）或代码

    返回:
        标准股票代码，或 None（未找到）

    示例:
        resolve_name("微软")       # → "MSFT"
        resolve_name("Microsoft")  # → "MSFT"
        resolve_name("MSFT")       # → "MSFT"
        resolve_name("腾讯")       # → "0700.HK"
        resolve_name("茅台")       # → "600519.SS"
        resolve_name("unknown")    # → None
    """
    name = name.strip()
    if not name:
        return None

    # 已经是代码，直接返回（统一大写）
    if is_ticker(name):
        return name.upper() if name.isascii() else name

    # 英文：小写查找
    if name.isascii():
        result = _LOOKUP.get(name.lower())
        if result:
            return result
        # 尝试大写后当作代码（用户可能输入了小写代码如 "msft"）
        upper = name.upper()
        if is_ticker(upper):
            return upper
        return None

    # 中文：精确查找
    result = _LOOKUP.get(name)
    if result:
        return result

    # 中文：模糊查找（输入是某个别名的一部分）
    candidates = []
    for key, ticker in _LOOKUP.items():
        if not key.isascii() and len(key) >= 2 and name in key:
            candidates.append((key, ticker))

    if len(candidates) == 1:
        return candidates[0][1]
    if len(candidates) > 1:
        # 多个匹配 → 歧义，返回第一个完全匹配或最短的
        # 优先返回最短的（最精确）
        candidates.sort(key=lambda x: len(x[0]))
        return candidates[0][1]

    return None


def resolve_symbols(symbols: list[str], verbose: bool = True) -> tuple[list[str], dict[str, str]]:
    """
    批量解析符号列表（代码+名称混合）。

    参数:
        symbols: 原始输入列表，可混合代码和名称
        verbose: 是否打印解析日志

    返回:
        (resolved_tickers, mapping)
        resolved_tickers: 解析后的代码列表（去重、保持顺序）
        mapping: {原始输入: 解析后代码} 仅包含发生了转换的条目
    """
    resolved = []
    mapping = {}

    for raw in symbols:
        if is_ticker(raw):
            resolved.append(raw)
            continue

        ticker = resolve_name(raw)
        if ticker:
            resolved.append(ticker)
            mapping[raw] = ticker
            if verbose:
                print(f"  📛 '{raw}' → {ticker}")
        else:
            # 宽松模式：保留原文，下游报错
            resolved.append(raw)
            if verbose:
                print(f"  ⚠️ 无法识别: '{raw}'（将作为代码直接使用）")

    # 解析后去重（防止 ["MSFT", "微软"] 变成两个 MSFT）
    seen = set()
    deduped = []
    for s in resolved:
        key = s.upper() if s.isascii() else s
        if key not in seen:
            seen.add(key)
            deduped.append(s)

    return deduped, mapping


def get_all_aliases() -> dict[str, str]:
    """返回完整的别名映射表（用于调试/展示）"""
    return dict(_LOOKUP)


def get_alias_count() -> int:
    """返回别名总数"""
    return len(_LOOKUP)


def add_alias(name: str, ticker: str) -> None:
    """运行时添加别名（用于用户自定义扩展）"""
    global _LOOKUP
    key = name.lower() if name.isascii() else name
    _LOOKUP[key] = ticker
    _REVERSE.setdefault(ticker, []).append(key)


def list_aliases_for(ticker: str) -> list[str]:
    """查看某个代码的所有别名"""
    return _REVERSE.get(ticker, [])
