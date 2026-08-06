"""
多维综合分析模块
=================
融合六大维度：技术面、基本面、新闻情绪、期权资金、市场背景、关键价位，
输出统一的综合评分和场景化操作建议。
"""

import numpy as np
import pandas as pd
from config import THRESHOLDS


# ============================================================
# 维度权重（总和 1.0）
# ============================================================
DIMENSION_WEIGHTS = {
    "technical": 0.30,     # 技术面（MA/BOLL/RSI/MACD/KDJ/K线）
    "fundamental": 0.25,   # 基本面（估值/增长/盈利/分析师）
    "sentiment": 0.15,     # 新闻情绪
    "options": 0.10,       # 期权资金流
    "context": 0.10,       # 市场背景（大盘/板块）
    "levels": 0.10,        # 关键价位（支撑/阻力/盈亏比）
}


def calculate_composite_score(all_signals: list[dict]) -> dict:
    """
    根据所有信号计算综合评分（0-100）。

    评分逻辑：
    - 基础分 50
    - 看涨信号加分，看跌信号减分
    - weight 0-4，每点 weight 贡献 3 分
    """
    bullish = [s for s in all_signals if s["type"] == "bullish"]
    bearish = [s for s in all_signals if s["type"] == "bearish"]
    neutral = [s for s in all_signals if s["type"] == "neutral"]

    total_bull = sum(s["weight"] for s in bullish)
    total_bear = sum(s["weight"] for s in bearish)

    net = total_bull - total_bear
    score = 50 + net * 3
    score = max(0, min(100, int(score)))

    return {
        "score": score,
        "bullish_signals": bullish,
        "bearish_signals": bearish,
        "neutral_signals": neutral,
        "total_bullish_weight": total_bull,
        "total_bearish_weight": total_bear,
    }


def get_recommendation(score: int) -> tuple[str, str, str]:
    """评分 → 建议"""
    if score >= THRESHOLDS["strong_buy"]:
        return "STRONG_BUY", "🟢 强烈买入 / 坚定持有", "green"
    elif score >= THRESHOLDS["buy"]:
        return "BUY", "🟢 偏多 / 可以持有", "green"
    elif score >= THRESHOLDS["hold"]:
        return "HOLD", "🟡 中性 / 观望", "yellow"
    elif score >= THRESHOLDS["sell"]:
        return "SELL", "🔴 偏空 / 考虑减仓", "red"
    else:
        return "STRONG_SELL", "🔴 强烈卖出 / 清仓", "red"


def detect_signal_conflicts(all_signals: list[dict]) -> list[dict]:
    """
    检测信号矛盾——这是最有价值的部分：
    当不同维度给出相反的高权重信号时，说明市场存在不确定性。
    """
    conflicts = []
    high_bull = [s for s in all_signals if s["type"] == "bullish" and s["weight"] >= 3]
    high_bear = [s for s in all_signals if s["type"] == "bearish" and s["weight"] >= 3]

    if high_bull and high_bear:
        conflicts.append({
            "severity": "high",
            "message": "⚠️ 多空信号严重冲突，多个高权重信号指向相反方向",
            "bull_signals": [s["name"] for s in high_bull],
            "bear_signals": [s["name"] for s in high_bear],
            "advice": "建议减仓观望，等待方向明朗后再操作",
        })

    return conflicts


def analyze_trend(df: pd.DataFrame) -> dict:
    """
    技术面趋势判断（修复版）

    三重确认（不依赖短期均线排列，避免急涨急跌时失真）：
    1. 价格 vs MA50 — 中期多空分界
    2. MA50 斜率方向 — 中期趋势是否在朝正确方向移动
    3. MACD 零轴 — 动能方向
    辅助: BOLL 中轨位置
    """
    row = df.iloc[-1]
    ups = 0
    downs = 0
    details = []

    # 1. 价格 vs MA50（最重要）
    if pd.notna(row.get("MA50")):
        if row["close"] > row["MA50"]:
            ups += 2  # 权重加倍
            details.append("价格 > MA50 ✅")
        else:
            downs += 2
            details.append("价格 < MA50 ⚠️")

    # 2. MA50 斜率（MA50 近 10 天变化方向）
    if len(df) >= 30 and pd.notna(row.get("MA50")):
        ma50_now = row["MA50"]
        ma50_10d_ago = df["MA50"].iloc[-11] if len(df) > 11 and pd.notna(df["MA50"].iloc[-11]) else ma50_now
        ma50_slope = (ma50_now - float(ma50_10d_ago)) / float(ma50_10d_ago) * 100

        if ma50_slope > 0.5:
            ups += 1
            details.append(f"MA50 向上倾斜 +{ma50_slope:.1f}% ✅")
        elif ma50_slope < -0.5:
            downs += 1
            details.append(f"MA50 向下倾斜 {ma50_slope:.1f}% ⚠️")
        else:
            details.append(f"MA50 走平 {ma50_slope:+.1f}%")

    # 3. MACD 零轴位置
    if pd.notna(row.get("DIF")):
        if row["DIF"] > 0:
            ups += 1
            details.append("MACD > 0（多头）✅")
        else:
            downs += 1
            details.append("MACD < 0（空头）⚠️")

    # 辅助: BOLL 中轨
    if pd.notna(row.get("BOLL_MID")):
        if row["close"] > row["BOLL_MID"]:
            details.append("BOLL 中轨上方")
        else:
            details.append("BOLL 中轨下方")

    # 综合判断
    if ups >= 3:
        direction = "强势上涨"
        strength = "强"
    elif ups >= 2:
        direction = "震荡偏多"
        strength = "中"
    elif downs >= 3:
        direction = "强势下跌"
        strength = "强"
    elif downs >= 2:
        direction = "震荡偏空"
        strength = "中"
    else:
        direction = "横盘震荡"
        strength = "弱"

    return {
        "direction": direction,
        "strength": strength,
        "details": details,
    }


def full_analysis(
    symbol: str,
    df: pd.DataFrame,
    fundamental_data: dict = None,
    sentiment_data: dict = None,
    options_data: dict = None,
    context_data: dict = None,
    levels_data: dict = None,
    valuation_data: dict = None,
    technical_signals: list[dict] = None,
) -> dict:
    """
    ===== 核心分析引擎 =====
    融合六大维度，输出统一评分和操作建议。
    """

    # === 收集所有信号 ===
    all_signals = []

    # 技术面信号
    if technical_signals:
        for s in technical_signals:
            s["dimension"] = "技术面"
            all_signals.append(s)

    # 基本面信号
    if fundamental_data and fundamental_data.get("signals"):
        for s in fundamental_data["signals"]:
            s["dimension"] = "基本面"
            all_signals.append(s)

    # 新闻情绪信号
    if sentiment_data and sentiment_data.get("signals"):
        for s in sentiment_data["signals"]:
            s["dimension"] = "新闻情绪"
            all_signals.append(s)

    # 期权信号
    if options_data and options_data.get("signals"):
        for s in options_data["signals"]:
            s["dimension"] = "期权资金"
            all_signals.append(s)

    # 市场背景信号
    if context_data and context_data.get("signals"):
        for s in context_data["signals"]:
            s["dimension"] = "市场背景"
            all_signals.append(s)

    # 关键价位信号
    if levels_data and levels_data.get("signals"):
        for s in levels_data["signals"]:
            s["dimension"] = "关键价位"
            all_signals.append(s)

    # 历史估值信号
    if valuation_data and valuation_data.get("signals"):
        for s in valuation_data["signals"]:
            s["dimension"] = "历史估值"
            all_signals.append(s)

    # === 信号冲突检测 ===
    conflicts = detect_signal_conflicts(all_signals)

    # === 综合评分 ===
    score_result = calculate_composite_score(all_signals)
    # 当存在严重信号冲突时，向 50 收缩评分（不确定性高 → 不宜极端判断）
    if conflicts:
        raw_score = score_result["score"]
        adjusted = 50 + (raw_score - 50) * 0.4  # 向中性收缩 60%
        score_result["score"] = max(0, min(100, int(adjusted)))
        score_result["conflict_adjusted"] = True
        score_result["raw_score"] = raw_score

    # === 趋势约束：下跌趋势中分数上限锁定 ===
    # 逻辑：无论基本面多好，只要技术面确认下跌趋势，不建议买入
    trend = analyze_trend(df)
    if "下跌" in trend["direction"]:
        cap = 45 if "强势" in trend["direction"] else 55
        if score_result["score"] > cap:
            score_result["raw_score"] = score_result.get("raw_score", score_result["score"])
            score_result["score"] = cap
            score_result["trend_capped"] = True
            score_result["trend_cap_reason"] = f"趋势为「{trend['direction']}」，评分上限锁定在 {cap}"

    recommendation = get_recommendation(score_result["score"])

    # === 关键指标快照 ===
    row = df.iloc[-1]
    snapshot = {
        "price": round(float(row["close"]), 2),
        "change_5d": _calc_change(df, 5),
        "change_20d": _calc_change(df, 20),
        "MA20": _safe(row, "MA20"),
        "MA50": _safe(row, "MA50"),
        "MA200": _safe(row, "MA200"),
        "RSI": _safe(row, "RSI", 1),
        "MACD_DIF": _safe(row, "DIF", 4),
        "MACD_DEA": _safe(row, "DEA", 4),
        "MACD_HIST": _safe(row, "MACD_HIST", 4),
        "KDJ_K": _safe(row, "K", 1),
        "KDJ_D": _safe(row, "D", 1),
        "KDJ_J": _safe(row, "J", 1),
        "BOLL_PCTB": _safe(row, "BOLL_PCTB", 2),
        "VOL_RATIO": _safe(row, "VOL_RATIO", 2),
        "pattern": row.get("pattern_name"),
    }

    # === 按维度分组 ===
    signals_by_dimension = {}
    for s in all_signals:
        dim = s.get("dimension", "其他")
        if dim not in signals_by_dimension:
            signals_by_dimension[dim] = {"bullish": [], "bearish": [], "neutral": []}
        signals_by_dimension[dim][s["type"]].append(s)

    return {
        "symbol": symbol,
        "score": score_result["score"],
        "raw_score": score_result.get("raw_score", score_result["score"]),
        "conflict_adjusted": score_result.get("conflict_adjusted", False),
        "trend_capped": score_result.get("trend_capped", False),
        "trend_cap_reason": score_result.get("trend_cap_reason", ""),
        "recommendation": recommendation,
        "trend": trend,
        "snapshot": snapshot,
        "conflicts": conflicts,
        "signals_by_dimension": signals_by_dimension,
        "all_signals": all_signals,
        "bullish_signals": score_result["bullish_signals"],
        "bearish_signals": score_result["bearish_signals"],
        "neutral_signals": score_result["neutral_signals"],
        # 附加数据（传给 report 展示）
        "fundamental_data": fundamental_data,
        "sentiment_data": sentiment_data,
        "options_data": options_data,
        "context_data": context_data,
        "levels_data": levels_data,
    }


def _safe(row, col: str, precision: int = 2):
    """安全取整数值"""
    val = row.get(col)
    if pd.notna(val):
        return round(float(val), precision)
    return None


def _calc_change(df, days: int) -> float | None:
    """计算 N 日涨跌幅"""
    if len(df) >= days + 1:
        return round(float((df["close"].iloc[-1] - df["close"].iloc[-(days+1)]) / df["close"].iloc[-(days+1)] * 100), 2)
    return None
