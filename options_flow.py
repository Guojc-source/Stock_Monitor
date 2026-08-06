"""
期权资金流分析模块
==================
分析期权链数据：Put/Call 比率、未平仓合约分布、异常大单检测。
"""

import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta


def get_options_analysis(symbol: str) -> dict:
    """
    获取期权链数据并分析。

    返回:
        {
            "available": bool,          # 是否有期权数据
            "put_call_ratio": float,    # P/C 比率
            "max_pain": float,          # 最大痛点
            "key_levels": [...],        # 关键行权价（OI 集中区）
            "unusual_activity": [...],  # 异常大单
            "signals": [...],           # 期权信号
        }
    """
    ticker = yf.Ticker(symbol)

    try:
        expirations = ticker.options
    except Exception:
        return _empty_result("无法获取期权到期日")

    if not expirations:
        return _empty_result("该股票无期权链")

    # 取最近两个到期日
    near_exp = expirations[0]
    # 找月期权（第三个周五附近）
    monthly_exp = _find_monthly(expirations)

    try:
        near_chain = ticker.option_chain(near_exp)
        calls_near = near_chain.calls
        puts_near = near_chain.puts
    except Exception:
        return _empty_result("无法获取近期期权链")

    # 如果月期权不同，也获取
    calls_monthly = None
    puts_monthly = None
    if monthly_exp and monthly_exp != near_exp:
        try:
            monthly_chain = ticker.option_chain(monthly_exp)
            calls_monthly = monthly_chain.calls
            puts_monthly = monthly_chain.puts
        except Exception:
            pass

    # === 1. P/C 比率 ===
    near_pcr = _calc_put_call_ratio(calls_near, puts_near)
    monthly_pcr = _calc_put_call_ratio(calls_monthly, puts_monthly) if calls_monthly is not None else None

    # === 2. 最大痛点 ===
    try:
        max_pain = _calc_max_pain(calls_near, puts_near)
    except Exception:
        max_pain = None

    # === 3. OI 集中区 ===
    key_levels = _find_key_levels(calls_near, puts_near)

    # === 4. 异常成交量检测 ===
    unusual = _detect_unusual_activity(calls_near, puts_near, symbol)

    # === 5. 生成信号 ===
    # 获取当前价格用于 max pain 验证
    current_price = None
    try:
        info = ticker.info
        current_price = info.get("regularMarketPrice") or info.get("currentPrice") or info.get("previousClose")
    except Exception:
        pass

    signals = _generate_options_signals(near_pcr, monthly_pcr, max_pain, unusual, current_price)

    # 如果 max pain 无效，从返回中移除
    if max_pain is not None and current_price and abs(max_pain - current_price) / current_price > 0.15:
        max_pain = None  # 抑制无效 max pain

    return {
        "available": True,
        "near_expiration": near_exp,
        "monthly_expiration": monthly_exp,
        "put_call_ratio_near": near_pcr,
        "put_call_ratio_monthly": monthly_pcr,
        "max_pain": max_pain,
        "key_levels": key_levels,
        "unusual_activity": unusual,
        "signals": signals,
    }


def _find_monthly(expirations: list[str]) -> str | None:
    """从到期日列表中找到月期权（通常是第三个周五）"""
    for exp in expirations:
        dt = datetime.strptime(exp, "%Y-%m-%d")
        # 月期权通常在 15-21 号之间
        if 14 <= dt.day <= 22:
            return exp
    # 退而求其次，取 30 天后的
    now = datetime.now()
    target = now + timedelta(days=30)
    for exp in expirations:
        dt = datetime.strptime(exp, "%Y-%m-%d")
        if dt >= target:
            return exp
    return None


def _calc_put_call_ratio(calls_df: pd.DataFrame, puts_df: pd.DataFrame) -> dict | None:
    """计算 Put/Call 比率（成交量和持仓量两个维度）"""
    if calls_df is None or puts_df is None:
        return None

    total_call_vol = calls_df["volume"].sum()
    total_put_vol = puts_df["volume"].sum()
    total_call_oi = calls_df["openInterest"].sum()
    total_put_oi = puts_df["openInterest"].sum()

    return {
        "volume_pcr": round(total_put_vol / total_call_vol, 3) if total_call_vol > 0 else None,
        "oi_pcr": round(total_put_oi / total_call_oi, 3) if total_call_oi > 0 else None,
        "total_call_volume": int(total_call_vol),
        "total_put_volume": int(total_put_vol),
    }


def _calc_max_pain(calls_df: pd.DataFrame, puts_df: pd.DataFrame) -> float | None:
    """
    计算最大痛点（期权买方总体亏损最大的价位）。

    逻辑：在每个行权价上，计算所有 call 和 put 买方的总亏损，
    亏损最小的那个价位就是最大痛点。
    """
    all_strikes = sorted(set(calls_df["strike"].tolist() + puts_df["strike"].tolist()))
    if not all_strikes:
        return None

    min_pain = float("inf")
    max_pain_strike = all_strikes[0]

    for strike in all_strikes:
        pain = 0
        # Call 买方亏损 = max(标的价 - 行权价, 0) - 权利金（简化用 OI 代替权利金）
        for _, row in calls_df.iterrows():
            if row["strike"] <= strike:
                pain += (strike - row["strike"]) * row["openInterest"]
        # Put 买方亏损 = max(行权价 - 标的价, 0)
        for _, row in puts_df.iterrows():
            if row["strike"] >= strike:
                pain += (row["strike"] - strike) * row["openInterest"]

        if pain < min_pain:
            min_pain = pain
            max_pain_strike = strike

    return float(max_pain_strike)


def _find_key_levels(calls_df: pd.DataFrame, puts_df: pd.DataFrame) -> list[dict]:
    """找出 OI 集中度最高的几个行权价"""
    all_strikes = []
    for _, row in calls_df.iterrows():
        all_strikes.append({
            "strike": row["strike"],
            "call_oi": int(row["openInterest"]),
            "put_oi": 0,
            "total_oi": int(row["openInterest"]),
            "direction": "阻力位（大量 Call OI）",
        })
    for _, row in puts_df.iterrows():
        # 查找是否已有这个 strike
        existing = next((s for s in all_strikes if s["strike"] == row["strike"]), None)
        if existing:
            existing["put_oi"] = int(row["openInterest"])
            existing["total_oi"] += int(row["openInterest"])
            existing["direction"] = "多空争夺区" if existing["call_oi"] > 0 and existing["put_oi"] > 0 else existing["direction"]
        else:
            all_strikes.append({
                "strike": row["strike"],
                "call_oi": 0,
                "put_oi": int(row["openInterest"]),
                "total_oi": int(row["openInterest"]),
                "direction": "支撑位（大量 Put OI）",
            })

    all_strikes.sort(key=lambda s: s["total_oi"], reverse=True)
    return all_strikes[:5]


def _detect_unusual_activity(calls_df: pd.DataFrame, puts_df: pd.DataFrame, symbol: str) -> list[dict]:
    """
    检测异常期权大单：
    - 成交量远超未平仓数（新建大量头寸）
    - 单笔成交额巨大
    """
    unusual = []

    for _, row in calls_df.iterrows():
        oi = row.get("openInterest", 0)
        vol = row.get("volume", 0)
        if oi > 0 and vol > oi * 3 and vol > 500:
            premium = row["lastPrice"] * vol * 100
            unusual.append({
                "type": "CALL",
                "strike": float(row["strike"]),
                "volume": int(vol),
                "open_interest": int(oi),
                "premium": f"${premium/1e6:.1f}M" if premium > 1e6 else f"${premium/1e3:.0f}K",
                "signal": "🟢 大量新建看涨头寸",
            })

    for _, row in puts_df.iterrows():
        oi = row.get("openInterest", 0)
        vol = row.get("volume", 0)
        if oi > 0 and vol > oi * 3 and vol > 500:
            premium = row["lastPrice"] * vol * 100
            unusual.append({
                "type": "PUT",
                "strike": float(row["strike"]),
                "volume": int(vol),
                "open_interest": int(oi),
                "premium": f"${premium/1e6:.1f}M" if premium > 1e6 else f"${premium/1e3:.0f}K",
                "signal": "🔴 大量新建看跌头寸（对冲或做空）",
            })

    unusual.sort(key=lambda u: abs(u["volume"]), reverse=True)
    return unusual[:8]


def _generate_options_signals(
    near_pcr: dict | None,
    monthly_pcr: dict | None,
    max_pain: float | None,
    unusual: list[dict],
    current_price: float | None = None,
) -> list[dict]:
    """从期权数据生成信号"""
    signals = []

    # P/C 比率信号
    if near_pcr and near_pcr.get("volume_pcr") is not None:
        vpcr = near_pcr["volume_pcr"]
        if vpcr < 0.5:
            signals.append({"name": f"P/C 成交量比 = {vpcr}（极度看涨，Call 成交量远大于 Put）", "type": "bullish", "weight": 3})
        elif vpcr < 0.7:
            signals.append({"name": f"P/C 成交量比 = {vpcr}（偏看涨）", "type": "bullish", "weight": 2})
        elif vpcr > 1.5:
            signals.append({"name": f"P/C 成交量比 = {vpcr}（偏看空，Put 成交活跃）", "type": "bearish", "weight": 2})
        elif vpcr > 2.0:
            signals.append({"name": f"P/C 成交量比 = {vpcr}（极度看空）", "type": "bearish", "weight": 3})

    if near_pcr and near_pcr.get("oi_pcr") is not None:
        oipcr = near_pcr["oi_pcr"]
        if oipcr < 0.5:
            signals.append({"name": f"P/C 持仓比 = {oipcr}（市场持仓偏多）", "type": "bullish", "weight": 1})

    # 最大痛点（带有效性过滤）
    if max_pain is not None:
        if current_price and abs(max_pain - current_price) / current_price > 0.15:
            # 差距 >15%，无参考价值，但记录在案
            pass  # 信号不添加，报告中也不展示
        else:
            signals.append({"name": f"最大痛点 = ${max_pain:.0f}（期权到期日有引力）", "type": "neutral", "weight": 0})

    if max_pain is None and current_price:
        signals.append({"name": "最大痛点距现价过远（>15%），已自动隐藏", "type": "neutral", "weight": 0})

    # 异常大单
    bull_unusual = [u for u in unusual if u["type"] == "CALL"]
    bear_unusual = [u for u in unusual if u["type"] == "PUT"]

    if bull_unusual:
        largest = bull_unusual[0]
        signals.append({
            "name": f"期权异动: CALL ${largest['strike']:.0f} 成交{largest['volume']}张 涉资{largest['premium']}",
            "type": "bullish", "weight": 3
        })

    if bear_unusual:
        largest = bear_unusual[0]
        signals.append({
            "name": f"期权异动: PUT ${largest['strike']:.0f} 成交{largest['volume']}张 涉资{largest['premium']}",
            "type": "bearish", "weight": 3
        })

    if not signals:
        signals.append({"name": "期权市场无明显异常", "type": "neutral", "weight": 0})

    return signals


def _empty_result(reason: str) -> dict:
    return {
        "available": False,
        "reason": reason,
        "signals": [{"name": f"期权数据不可用: {reason}", "type": "neutral", "weight": 0}],
    }
