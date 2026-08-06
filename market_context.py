"""
市场背景分析模块
================
分析个股相对大盘/板块的强弱，以及大盘本身的趋势状态。
"""

import yfinance as yf
import pandas as pd
import numpy as np
from config import PERIOD, INTERVAL


# 基准 ETF（始终拉取）
BASE_BENCHMARKS = {
    "SPY": "标普500（大盘）",
    "QQQ": "纳斯达克100（科技股）",
}

# 行业 → 对标 ETF 映射
SECTOR_ETF_MAP = {
    "Technology": "IGV",                    # 软件/科技 → 软件ETF
    "Communication Services": "XLC",        # 通信服务 → 通信ETF
    "Financial Services": "XLF",            # 金融 → 金融ETF
    "Healthcare": "XLV",                    # 医疗 → 医疗ETF
    "Consumer Cyclical": "XLY",            # 消费周期 → 消费ETF
    "Consumer Defensive": "XLP",           # 必需消费 → 必需消费ETF
    "Energy": "XLE",                        # 能源 → 能源ETF
    "Industrials": "XLI",                   # 工业 → 工业ETF
    "Real Estate": "XLRE",                  # 房地产 → 房地产ETF
    "Utilities": "XLU",                     # 公用事业 → 公用事业ETF
    "Basic Materials": "XLB",              # 原材料 → 原材料ETF
}

SECTOR_ETF_NAMES = {
    "IGV": "软件板块 ETF",
    "XLC": "通信服务 ETF",
    "XLF": "金融板块 ETF",
    "XLV": "医疗板块 ETF",
    "XLY": "消费周期 ETF",
    "XLP": "必需消费 ETF",
    "XLE": "能源 ETF",
    "XLI": "工业 ETF",
    "XLRE": "房地产 ETF",
    "XLU": "公用事业 ETF",
    "XLB": "原材料 ETF",
}


def _get_sector_etf(symbol: str) -> tuple[str, str]:
    """
    根据股票的 GICS 行业分类，自动选择最合适的行业 ETF。
    返回: (ETF代码, ETF名称)
    """
    try:
        ticker = yf.Ticker(symbol)
        info = ticker.info or {}
        sector = info.get("sector", "")
        etf = SECTOR_ETF_MAP.get(sector, "QQQ")
        name = SECTOR_ETF_NAMES.get(etf, "行业 ETF")
        return etf, name
    except Exception:
        return "QQQ", "纳斯达克100（科技股）"


def get_market_context(symbol: str) -> dict:
    """
    获取市场背景数据（修复版）。

    - 始终拉取 SPY + QQQ 作为大盘基准
    - 根据个股行业自动选择对标 ETF
    - 计算个股 vs 各基准的相对强弱

    返回:
        {
            "benchmarks": {...},
            "sector_etf": str,         # 选中的行业ETF
            "relative_strength": {},
            "market_regime": str,
            "signals": [...],
        }
        }
    """
    # 动态选择行业 ETF
    sector_etf, sector_etf_name = _get_sector_etf(symbol)

    # 拉取基准 ETF + 行业 ETF
    all_etfs = {**BASE_BENCHMARKS, sector_etf: sector_etf_name}

    benchmark_data = {}
    for etf, name in all_etfs.items():
        try:
            etf_ticker = yf.Ticker(etf)
            df = etf_ticker.history(period=PERIOD, interval=INTERVAL)
            if not df.empty:
                df = df[df["Close"].notna()]
                if len(df) >= 2:
                    current = float(df["Close"].iloc[-1])
                    prev_5d = float(df["Close"].iloc[-6]) if len(df) >= 6 else float(df["Close"].iloc[0])
                    prev_20d = float(df["Close"].iloc[-21]) if len(df) >= 21 else float(df["Close"].iloc[0])
                    change_5d = (current - prev_5d) / prev_5d * 100
                    change_20d = (current - prev_20d) / prev_20d * 100
                    ma50 = float(df["Close"].rolling(50).mean().iloc[-1]) if len(df) >= 50 else None
                    above_ma50 = current > ma50 if ma50 else None

                    benchmark_data[etf] = {
                        "name": name,
                        "price": round(current, 2),
                        "change_5d": round(change_5d, 2),
                        "change_20d": round(change_20d, 2),
                        "above_ma50": above_ma50,
                    }
        except Exception:
            continue

    # 获取个股数据用于相对强弱比较
    try:
        stock_ticker = yf.Ticker(symbol)
        stock_df = stock_ticker.history(period=PERIOD, interval=INTERVAL)
        stock_df = stock_df[stock_df["Close"].notna()]
    except Exception:
        stock_df = pd.DataFrame()

    # 计算相对强弱（个股涨幅 / 基准涨幅）
    relative_strength = {}
    if len(stock_df) >= 20 and "SPY" in benchmark_data:
        stock_20d = (float(stock_df["Close"].iloc[-1]) - float(stock_df["Close"].iloc[-21])) / float(stock_df["Close"].iloc[-21]) * 100
        spy_20d = benchmark_data["SPY"]["change_20d"]
        rs_20d = stock_20d - spy_20d  # 超额收益
        relative_strength["vs_SPY_20d"] = {
            "stock_change": round(stock_20d, 2),
            "benchmark_change": round(spy_20d, 2),
            "excess_return": round(rs_20d, 2),
        }

    if len(stock_df) >= 5 and "QQQ" in benchmark_data:
        stock_5d = (float(stock_df["Close"].iloc[-1]) - float(stock_df["Close"].iloc[-6])) / float(stock_df["Close"].iloc[-6]) * 100
        qqq_5d = benchmark_data["QQQ"]["change_5d"]
        rs_5d = stock_5d - qqq_5d
        relative_strength["vs_QQQ_5d"] = {
            "stock_change": round(stock_5d, 2),
            "benchmark_change": round(qqq_5d, 2),
            "excess_return": round(rs_5d, 2),
        }

    # 判断市场状态
    regime = _determine_market_regime(benchmark_data, stock_df)

    # 生成信号
    signals = _generate_context_signals(benchmark_data, relative_strength, regime)

    return {
        "benchmarks": benchmark_data,
        "sector_etf": sector_etf,
        "sector_etf_name": sector_etf_name,
        "relative_strength": relative_strength,
        "market_regime": regime,
        "signals": signals,
    }


def _determine_market_regime(benchmark_data: dict, stock_df: pd.DataFrame) -> dict:
    """判断市场大环境"""
    spy = benchmark_data.get("SPY", {})
    qqq = benchmark_data.get("QQQ", {})

    score = 0

    # SPY 是否在 MA50 上方
    if spy.get("above_ma50"):
        score += 1
    elif spy.get("above_ma50") is False:
        score -= 1

    # QQQ 20日趋势
    if qqq.get("change_20d", 0) > 3:
        score += 1
    elif qqq.get("change_20d", 0) < -3:
        score -= 1

    if score >= 2:
        label = "risk_on"
        desc = "🟢 市场风险偏好（大盘强势，利于做多）"
    elif score <= -2:
        label = "risk_off"
        desc = "🔴 市场避险情绪（大盘弱势，控制仓位）"
    else:
        label = "neutral"
        desc = "🟡 市场中性（大盘方向不明）"

    return {"label": label, "description": desc, "score": score}


def _generate_context_signals(benchmarks: dict, relative_strength: dict, regime: dict) -> list[dict]:
    """生成市场背景相关的信号"""
    signals = []

    # 大盘环境信号
    if regime["label"] == "risk_on":
        signals.append({"name": "大盘环境: 强势，做多胜率较高", "type": "bullish", "weight": 1})
    elif regime["label"] == "risk_off":
        signals.append({"name": "大盘环境: 弱势，注意控制风险", "type": "bearish", "weight": 2})

    # 个股相对强弱
    if "vs_SPY_20d" in relative_strength:
        excess = relative_strength["vs_SPY_20d"]["excess_return"]
        if excess > 10:
            signals.append({"name": f"20日跑赢标普 {excess}%（显著强势）", "type": "bullish", "weight": 2})
        elif excess > 3:
            signals.append({"name": f"20日跑赢标普 {excess}%（相对强势）", "type": "bullish", "weight": 1})
        elif excess < -10:
            signals.append({"name": f"20日跑输标普 {excess}%（显著弱势）", "type": "bearish", "weight": 2})
        elif excess < -3:
            signals.append({"name": f"20日跑输标普 {excess}%（相对弱势）", "type": "bearish", "weight": 1})

    return signals
