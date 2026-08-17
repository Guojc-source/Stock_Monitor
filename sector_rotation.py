"""
Sector Rotation Ranking
=======================
Fetch 11 SPDR sector ETFs + benchmark indices, compute multi-period
returns, and rank sectors by momentum to detect capital flow direction.

Usage:
    from sector_rotation import get_sector_rotation
    result = get_sector_rotation()
    # result["rankings"] → ranked by 20-day return
    # result["leaders"]  → top-performing sectors
    # result["laggards"] → underperforming sectors
    # result["signals"]  → rotation signals
"""

import yfinance as yf
from yfinance.exceptions import YFRateLimitError
import pandas as pd
import numpy as np
import time
import random
from datetime import datetime


# ============================================================
# 限流重试工具
# ============================================================

def _fetch_with_retry(symbol: str, period: str = "6mo", max_retries: int = 3) -> pd.DataFrame | None:
    """带限流重试的数据获取（指数退避）"""
    ticker = yf.Ticker(symbol)
    for attempt in range(max_retries):
        try:
            df = ticker.history(period=period, interval="1d")
            return df
        except (YFRateLimitError, Exception) as e:
            msg = str(e).lower()
            if "rate limit" in msg or "too many requests" in msg or isinstance(e, YFRateLimitError):
                delay = 30 * (2 ** attempt) + random.uniform(0, 5)
                print(f"    ⚠️ {symbol} 限流，{delay:.0f}秒后重试 ({attempt+1}/{max_retries})…")
                time.sleep(delay)
            else:
                raise
    return None


# ============================================================
# 11 个 SPDR 行业 ETF（覆盖 GICS 全部板块）
# ============================================================
SECTOR_ETFS = {
    "XLK": "科技",
    "XLF": "金融",
    "XLE": "能源",
    "XLV": "医疗",
    "XLY": "消费周期",
    "XLP": "必需消费",
    "XLI": "工业",
    "XLB": "原材料",
    "XLRE": "房地产",
    "XLU": "公用事业",
    "XLC": "通信服务",
}

# 基准指数（用于对比）
BENCHMARK_ETFS = {
    "SPY": "标普500",
    "QQQ": "纳指100",
}


def get_sector_rotation(verbose: bool = True) -> dict:
    """
    获取行业轮动数据。

    返回:
        {
            "sectors": [{symbol, name, price, change_5d, change_20d, change_60d,
                         ma20_above, ma50_above, momentum_score}, ...],
            "benchmarks": [{symbol, name, price, change_5d, change_20d, change_60d}, ...],
            "rankings": {
                "5d":  [按5日涨幅排名的 symbol 列表],
                "20d": [按20日涨幅排名的 symbol 列表],
                "60d": [按60日涨幅排名的 symbol 列表],
            },
            "leaders":  [领涨板块 top 3],
            "laggards": [领跌板块 bottom 3],
            "flow": "risk_on" | "risk_off" | "rotation" | "neutral",
            "flow_description": str,
            "signals": [...],
            "timestamp": str,
        }
    """
    all_etfs = {**SECTOR_ETFS, **BENCHMARK_ETFS}

    if verbose:
        print(f"\n  ⏳ 正在拉取 {len(all_etfs)} 个 ETF 数据…")

    # 拉取所有 ETF 数据（带限流重试）
    data = {}
    for symbol, name in all_etfs.items():
        try:
            df = _fetch_with_retry(symbol, period="6mo")
            if df is None or df.empty or len(df) < 20:
                continue

            # 标准化列名
            rename = {}
            for col in df.columns:
                cl = col.lower()
                if "close" in cl and "adj" not in cl:
                    rename[col] = "close"
            df.rename(columns=rename, inplace=True)
            df = df[df["close"].notna()]

            if len(df) < 5:
                continue

            price = float(df["close"].iloc[-1])

            # 多周期涨幅
            change_5d = _calc_change(df, 5)
            change_20d = _calc_change(df, 20)
            change_60d = _calc_change(df, 60)

            # 均线位置
            ma20 = float(df["close"].rolling(20).mean().iloc[-1]) if len(df) >= 20 else None
            ma50 = float(df["close"].rolling(50).mean().iloc[-1]) if len(df) >= 50 else None

            # 动量得分: 5d*3 + 20d*2 + 60d*1（短期权重更大）
            momentum = 0
            if change_5d is not None:
                momentum += change_5d * 3
            if change_20d is not None:
                momentum += change_20d * 2
            if change_60d is not None:
                momentum += change_60d * 1

            entry = {
                "symbol": symbol,
                "name": name,
                "price": round(price, 2),
                "change_5d": change_5d,
                "change_20d": change_20d,
                "change_60d": change_60d,
                "ma20_above": price > ma20 if ma20 else None,
                "ma50_above": price > ma50 if ma50 else None,
                "momentum_score": round(momentum, 2),
                "is_benchmark": symbol in BENCHMARK_ETFS,
            }

            data[symbol] = entry

            if verbose:
                chg = f"{change_20d:+.1f}%" if change_20d is not None else "N/A"
                print(f"    ✓ {symbol} ({name}): ${price:.2f}  20日 {chg}")

            # 避免限流（间隔 2-4 秒）
            time.sleep(random.uniform(2, 4))

        except Exception as e:
            if verbose:
                print(f"    ✗ {symbol}: {e}")
            continue

    # 分离行业 vs 基准
    sectors = [v for v in data.values() if not v["is_benchmark"]]
    benchmarks = [v for v in data.values() if v["is_benchmark"]]

    # 排名
    rankings = {}
    for period in ["5d", "20d", "60d"]:
        key = f"change_{period}"
        sorted_sectors = sorted(
            [s for s in sectors if s.get(key) is not None],
            key=lambda x: x[key],
            reverse=True,
        )
        rankings[period] = [s["symbol"] for s in sorted_sectors]

    # 领涨/领跌（按 20 日）
    sorted_20d = sorted(
        [s for s in sectors if s.get("change_20d") is not None],
        key=lambda x: x["change_20d"],
        reverse=True,
    )
    leaders = sorted_20d[:3] if len(sorted_20d) >= 3 else sorted_20d
    laggards = sorted_20d[-3:][::-1] if len(sorted_20d) >= 3 else sorted_20d

    # 资金流向判断
    flow, flow_desc = _determine_flow(sectors, benchmarks)

    # 生成信号
    signals = _generate_signals(sectors, benchmarks, leaders, laggards, flow)

    return {
        "sectors": sectors,
        "benchmarks": benchmarks,
        "rankings": rankings,
        "leaders": leaders,
        "laggards": laggards,
        "flow": flow,
        "flow_description": flow_desc,
        "signals": signals,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M"),
    }


def _calc_change(df: pd.DataFrame, days: int) -> float | None:
    """计算 N 日涨跌幅"""
    if len(df) >= days + 1:
        current = float(df["close"].iloc[-1])
        prev = float(df["close"].iloc[-(days + 1)])
        return round((current - prev) / prev * 100, 2)
    return None


def _determine_flow(sectors: list[dict], benchmarks: list[dict]) -> tuple[str, str]:
    """
    判断资金流向模式:
    - risk_on: 多数板块上涨，周期股领涨
    - risk_off: 多数板块下跌，防御板块抗跌
    - rotation: 板块分化明显（部分大涨部分大跌）
    - neutral: 横盘，无明显方向
    """
    if not sectors:
        return "neutral", "数据不足，无法判断"

    changes_20d = [s["change_20d"] for s in sectors if s.get("change_20d") is not None]
    if not changes_20d:
        return "neutral", "数据不足"

    up_count = sum(1 for c in changes_20d if c > 0)
    down_count = sum(1 for c in changes_20d if c < 0)
    total = len(changes_20d)
    avg_change = np.mean(changes_20d)
    std_change = np.std(changes_20d)

    # 防御板块
    defensive_symbols = {"XLP", "XLV", "XLU"}
    cyclical_symbols = {"XLY", "XLI", "XLE", "XLB"}

    def avg_change_for(symbols):
        vals = [s["change_20d"] for s in sectors if s["symbol"] in symbols and s.get("change_20d") is not None]
        return np.mean(vals) if vals else 0

    defensive_avg = avg_change_for(defensive_symbols)
    cyclical_avg = avg_change_for(cyclical_symbols)

    if up_count >= total * 0.7 and avg_change > 2:
        return "risk_on", "🟢 风险偏好 — 多数板块上涨，市场做多情绪强"
    elif down_count >= total * 0.7 and avg_change < -2:
        return "risk_off", "🔴 风险规避 — 多数板块下跌，市场避险情绪强"
    elif std_change > 4 and (cyclical_avg - defensive_avg) > 3:
        return "rotation_to_cyclical", "🔄 板块轮动 → 周期股 — 资金从防御转向进攻"
    elif std_change > 4 and (defensive_avg - cyclical_avg) > 3:
        return "rotation_to_defensive", "🔄 板块轮动 → 防御股 — 资金从进攻转向防守"
    elif std_change > 4:
        return "rotation", "🔄 板块分化 — 资金在板块间快速轮动"
    else:
        return "neutral", "🟡 市场中性 — 各板块涨跌幅接近，方向不明"


def _generate_signals(
    sectors: list[dict],
    benchmarks: list[dict],
    leaders: list[dict],
    laggards: list[dict],
    flow: str,
) -> list[dict]:
    """生成行业轮动相关的交易信号"""
    signals = []

    # 1. 大盘环境
    spy = next((b for b in benchmarks if b["symbol"] == "SPY"), None)
    if spy and spy.get("change_20d") is not None:
        if spy["change_20d"] > 5:
            signals.append({
                "name": f"SPY 20日涨 {spy['change_20d']:.1f}%，大盘强势",
                "type": "bullish",
                "weight": 2,
            })
        elif spy["change_20d"] < -5:
            signals.append({
                "name": f"SPY 20日跌 {spy['change_20d']:.1f}%，大盘弱势",
                "type": "bearish",
                "weight": 2,
            })

    # 2. 领涨板块 = 你的股票所在板块 → 顺势
    if leaders:
        leader_names = "、".join(f"{l['name']}({l['change_20d']:+.1f}%)" for l in leaders if l.get("change_20d"))
        signals.append({
            "name": f"领涨板块: {leader_names}",
            "type": "neutral",
            "weight": 0,
        })

    # 3. 资金流向信号
    if flow == "risk_on":
        signals.append({
            "name": "资金流入风险资产，适合加仓成长股",
            "type": "bullish",
            "weight": 1,
        })
    elif flow == "risk_off":
        signals.append({
            "name": "资金流出风险资产，建议减仓或转向防御",
            "type": "bearish",
            "weight": 2,
        })
    elif flow.startswith("rotation_to_defensive"):
        signals.append({
            "name": "资金转向防御板块，市场可能见顶回调",
            "type": "bearish",
            "weight": 1,
        })
    elif flow.startswith("rotation_to_cyclical"):
        signals.append({
            "name": "资金转向周期板块，经济复苏信号",
            "type": "bullish",
            "weight": 1,
        })

    return signals
