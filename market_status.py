"""
大盘状态灯模块
==============
基于 SPY/QQQ 的均线交叉、趋势方向、波动率，
输出一个直观的「交通灯」状态 + 仓位建议。

核心逻辑:
  - 🟢 绿灯（牛市）: SPY > MA50 > MA200，MA50 向上 → 满仓进攻
  - 🟡 黄灯（警戒）: SPY > MA200 但 < MA50，或均线纠缠 → 正常仓位
  - 🔴 红灯（熊市）: SPY < MA50 < MA200，MA50 向下 → 防守为主

用法:
    from market_status import get_market_status
    status = get_market_status()
    # status["light"] → "green" | "yellow" | "red"
    # status["position_advice"] → 仓位建议百分比
"""

import yfinance as yf
from yfinance.exceptions import YFRateLimitError
import pandas as pd
import numpy as np
import time
import random
from datetime import datetime


def _fetch_with_retry(symbol: str, period: str = "1y", max_retries: int = 3) -> pd.DataFrame | None:
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


def get_market_status(verbose: bool = True) -> dict:
    """
    获取大盘状态灯。

    返回:
        {
            "light": "green" | "yellow" | "red",
            "light_emoji": "🟢" | "🟡" | "🔴",
            "title": str,           # 一句话标题
            "description": str,     # 详细描述
            "position_advice": int, # 建议股票仓位百分比 (0-100)
            "spy": {...},           # SPY 详细数据
            "qqq": {...},           # QQQ 详细数据
            "cross_status": str,    # 金叉/死叉/纠缠
            "regime": str,          # bull_trend / consolidation / bear_trend
            "checklist": [...],     # 操作清单
            "signals": [...],       # 交易信号
            "timestamp": str,
        }
    """
    if verbose:
        print("\n  ⏳ 正在分析大盘状态…")

    # 拉取 SPY 和 QQQ 数据（需要 >=200 天算 MA200）
    spy_data = _fetch_index_data("SPY", "标普500", verbose)
    time.sleep(random.uniform(0.5, 1.0))
    qqq_data = _fetch_index_data("QQQ", "纳指100", verbose)

    # 核心判断逻辑
    light, title, description, position, regime, cross_status, checklist = \
        _evaluate_status(spy_data, qqq_data)

    # 生成信号
    signals = _generate_status_signals(light, spy_data, qqq_data, regime)

    emoji = {"green": "🟢", "yellow": "🟡", "red": "🔴"}[light]

    return {
        "light": light,
        "light_emoji": emoji,
        "title": f"{emoji} {title}",
        "description": description,
        "position_advice": position,
        "spy": spy_data,
        "qqq": qqq_data,
        "cross_status": cross_status,
        "regime": regime,
        "checklist": checklist,
        "signals": signals,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M"),
    }


def _fetch_index_data(symbol: str, name: str, verbose: bool = True) -> dict:
    """拉取单个指数的数据并计算关键指标"""
    try:
        df = _fetch_with_retry(symbol, period="1y")

        if df is None or df.empty:
            return {"symbol": symbol, "name": name, "error": "数据获取失败"}

        # 标准化列名
        rename = {}
        for col in df.columns:
            cl = col.lower()
            if "close" in cl and "adj" not in cl:
                rename[col] = "close"
            elif "high" in cl:
                rename[col] = "high"
            elif "low" in cl:
                rename[col] = "low"
        df.rename(columns=rename, inplace=True)
        df = df[df["close"].notna()]

        if len(df) < 50:
            return {"symbol": symbol, "name": name, "error": "数据不足（<50天）"}

        price = float(df["close"].iloc[-1])

        # 均线
        ma20 = float(df["close"].rolling(20).mean().iloc[-1]) if len(df) >= 20 else None
        ma50 = float(df["close"].rolling(50).mean().iloc[-1]) if len(df) >= 50 else None
        ma200 = float(df["close"].rolling(200).mean().iloc[-1]) if len(df) >= 200 else None

        # MA50 斜率（10 天变化率）
        ma50_slope = None
        if len(df) >= 60:
            ma50_now = df["close"].rolling(50).mean().iloc[-1]
            ma50_10d = df["close"].rolling(50).mean().iloc[-11]
            if pd.notna(ma50_now) and pd.notna(ma50_10d) and ma50_10d > 0:
                ma50_slope = round((float(ma50_now) - float(ma50_10d)) / float(ma50_10d) * 100, 2)

        # MA200 斜率（20 天变化率）
        ma200_slope = None
        if len(df) >= 220:
            ma200_now = df["close"].rolling(200).mean().iloc[-1]
            ma200_20d = df["close"].rolling(200).mean().iloc[-21]
            if pd.notna(ma200_now) and pd.notna(ma200_20d) and ma200_20d > 0:
                ma200_slope = round((float(ma200_now) - float(ma200_20d)) / float(ma200_20d) * 100, 2)

        # 涨跌幅
        change_5d = _calc_change(df, 5)
        change_20d = _calc_change(df, 20)
        change_60d = _calc_change(df, 60)

        # 距高点回撤
        high_52w = float(df["high"].max()) if "high" in df.columns else price
        drawdown = round((price - high_52w) / high_52w * 100, 2)

        # 波动率（20日年化）
        returns = df["close"].pct_change().dropna()
        volatility_20d = round(float(returns.tail(20).std()) * np.sqrt(252) * 100, 1) if len(returns) >= 20 else None

        # 金叉/死叉检测
        cross = _detect_cross(df)

        result = {
            "symbol": symbol,
            "name": name,
            "price": round(price, 2),
            "ma20": round(ma20, 2) if ma20 else None,
            "ma50": round(ma50, 2) if ma50 else None,
            "ma200": round(ma200, 2) if ma200 else None,
            "ma50_slope": ma50_slope,
            "ma200_slope": ma200_slope,
            "above_ma20": price > ma20 if ma20 else None,
            "above_ma50": price > ma50 if ma50 else None,
            "above_ma200": price > ma200 if ma200 else None,
            "change_5d": change_5d,
            "change_20d": change_20d,
            "change_60d": change_60d,
            "drawdown_from_high": drawdown,
            "volatility_20d": volatility_20d,
            "cross": cross,
            "error": None,
        }

        if verbose:
            chg = f"{change_20d:+.1f}%" if change_20d is not None else "N/A"
            ma_info = f"MA50={ma50:.0f}" if ma50 else ""
            ma_info += f" MA200={ma200:.0f}" if ma200 else ""
            print(f"    ✓ {symbol} ({name}): ${price:.2f}  20日 {chg}  {ma_info}")

        return result

    except Exception as e:
        if verbose:
            print(f"    ✗ {symbol}: {e}")
        return {"symbol": symbol, "name": name, "error": str(e)}


def _calc_change(df: pd.DataFrame, days: int) -> float | None:
    """计算 N 日涨跌幅"""
    if len(df) >= days + 1:
        current = float(df["close"].iloc[-1])
        prev = float(df["close"].iloc[-(days + 1)])
        return round((current - prev) / prev * 100, 2)
    return None


def _detect_cross(df: pd.DataFrame) -> dict:
    """
    检测 MA50/MA200 金叉死叉状态。

    返回:
        {"status": "golden_cross" | "death_cross" | "ma50_above" | "ma50_below" | "entangled",
         "days_ago": int | None,  # 距离最近一次交叉的天数
         "description": str}
    """
    if len(df) < 200:
        return {"status": "insufficient_data", "days_ago": None, "description": "数据不足200天"}

    ma50 = df["close"].rolling(50).mean()
    ma200 = df["close"].rolling(200).mean()

    # 当前状态
    current_diff = float(ma50.iloc[-1] - ma200.iloc[-1])
    prev_diff = float(ma50.iloc[-2] - ma200.iloc[-2]) if len(df) > 200 else 0

    # 找最近的交叉点
    diff_series = ma50 - ma200
    # 交叉 = 差值变号
    signs = np.sign(diff_series.dropna())
    cross_points = []
    for i in range(1, len(signs)):
        if signs.iloc[i] != signs.iloc[i - 1] and signs.iloc[i] != 0:
            cross_points.append(i)

    days_since_cross = None
    if cross_points:
        last_cross_idx = cross_points[-1]
        days_since_cross = len(signs) - 1 - last_cross_idx

    # 判断状态
    if current_diff > 0 and prev_diff <= 0:
        status = "golden_cross"
        desc = f"🟢 金叉！（MA50 刚上穿 MA200，{days_since_cross}天前）" if days_since_cross else "🟢 金叉！"
    elif current_diff < 0 and prev_diff >= 0:
        status = "death_cross"
        desc = f"🔴 死叉！（MA50 刚下穿 MA200，{days_since_cross}天前）" if days_since_cross else "🔴 死叉！"
    elif current_diff > 0:
        pct_above = round(current_diff / float(ma200.iloc[-1]) * 100, 2)
        if days_since_cross and days_since_cross < 30:
            status = "golden_cross"
            desc = f"🟢 近期金叉（{days_since_cross}天前），MA50 在 MA200 上方 {pct_above}%"
        else:
            status = "ma50_above"
            desc = f"MA50 在 MA200 上方 {pct_above}%（多头排列）"
    elif current_diff < 0:
        pct_below = round(abs(current_diff) / float(ma200.iloc[-1]) * 100, 2)
        if days_since_cross and days_since_cross < 30:
            status = "death_cross"
            desc = f"🔴 近期死叉（{days_since_cross}天前），MA50 在 MA200 下方 {pct_below}%"
        else:
            status = "ma50_below"
            desc = f"MA50 在 MA200 下方 {pct_below}%（空头排列）"
    else:
        status = "entangled"
        desc = "均线纠缠，方向不明"

    return {
        "status": status,
        "days_ago": days_since_cross,
        "description": desc,
        "ma50_ma200_diff_pct": round(current_diff / float(ma200.iloc[-1]) * 100, 2) if float(ma200.iloc[-1]) > 0 else 0,
    }


def _evaluate_status(
    spy: dict, qqq: dict
) -> tuple[str, str, str, int, str, str, list[str]]:
    """
    综合评估大盘状态，输出交通灯。

    返回: (light, title, description, position%, regime, cross_status, checklist)
    """
    if spy.get("error") or qqq.get("error"):
        return (
            "yellow", "数据不完整",
            "部分指数数据获取失败，无法完整判断",
            60, "unknown", "unknown",
            ["等待数据恢复后重新评估"],
        )

    score = 0
    details = []
    checklist = []

    # === SPY 评分 ===
    # 1. 价格 vs MA50
    if spy.get("above_ma50") is True:
        score += 2
        details.append("SPY > MA50 ✅")
    elif spy.get("above_ma50") is False:
        score -= 2
        details.append("SPY < MA50 ⚠️")

    # 2. 价格 vs MA200
    if spy.get("above_ma200") is True:
        score += 2
        details.append("SPY > MA200 ✅")
    elif spy.get("above_ma200") is False:
        score -= 2
        details.append("SPY < MA200 ⚠️")

    # 3. MA50 斜率
    if spy.get("ma50_slope") is not None:
        if spy["ma50_slope"] > 0.5:
            score += 1
            details.append(f"SPY MA50 向上 +{spy['ma50_slope']}% ✅")
        elif spy["ma50_slope"] < -0.5:
            score -= 1
            details.append(f"SPY MA50 向下 {spy['ma50_slope']}% ⚠️")

    # 4. MA200 斜率
    if spy.get("ma200_slope") is not None:
        if spy["ma200_slope"] > 0.3:
            score += 1
            details.append(f"SPY MA200 向上 +{spy['ma200_slope']}% ✅")
        elif spy["ma200_slope"] < -0.3:
            score -= 1
            details.append(f"SPY MA200 向下 {spy['ma200_slope']}% ⚠️")

    # === QQQ 评分 ===
    if qqq.get("above_ma50") is True:
        score += 1
        details.append("QQQ > MA50 ✅")
    elif qqq.get("above_ma50") is False:
        score -= 1
        details.append("QQQ < MA50 ⚠️")

    if qqq.get("change_20d") is not None:
        if qqq["change_20d"] > 3:
            score += 1
            details.append(f"QQQ 20日涨 {qqq['change_20d']}% ✅")
        elif qqq["change_20d"] < -3:
            score -= 1
            details.append(f"QQQ 20日跌 {qqq['change_20d']}% ⚠️")

    # === 交叉状态 ===
    cross = spy.get("cross", {})
    cross_status = cross.get("status", "unknown")
    if cross_status in ("golden_cross",):
        score += 1
    elif cross_status in ("death_cross",):
        score -= 1

    # === 回撤幅度 ===
    drawdown = spy.get("drawdown_from_high", 0)
    if drawdown < -15:
        score -= 2
        details.append(f"SPY 距高点回撤 {drawdown}%（深度回调）⚠️")
    elif drawdown < -10:
        score -= 1
        details.append(f"SPY 距高点回撤 {drawdown}%（正常回调）")

    # === 波动率 ===
    vol = spy.get("volatility_20d")
    if vol is not None and vol > 25:
        score -= 1
        details.append(f"波动率 {vol}% 偏高（市场恐慌）")

    # === 综合判断 ===
    if score >= 5:
        light = "green"
        title = "牛市趋势 — 积极做多"
        regime = "bull_trend"
        position = 85
        checklist = [
            "核心仓位满配（指数 ETF 65%）",
            "卫星仓位可加至上限（25%）",
            "逢回调积极加仓科技巨头",
            "止损线设宽一些（-20%），让利润奔跑",
        ]
    elif score >= 2:
        light = "green"
        title = "偏多震荡 — 正常配置"
        regime = "mild_bull"
        position = 75
        checklist = [
            "核心仓位正常配置（65%）",
            "卫星仓位正常（20%）",
            "回调到 MA50 附近可以加仓",
            "止损线 -15%",
        ]
    elif score >= -1:
        light = "yellow"
        title = "方向不明 — 谨慎观望"
        regime = "consolidation"
        position = 60
        checklist = [
            "核心仓位保持（65%），不追加",
            "卫星仓位缩减至 15%",
            "现金比例提高到 10%",
            "等待均线方向明确再加仓",
        ]
    elif score >= -4:
        light = "yellow"
        title = "偏弱震荡 — 防守为主"
        regime = "mild_bear"
        position = 45
        checklist = [
            "核心仓位缩减至 50%",
            "卫星仓位减至 10%，只留最强个股",
            "增加债券/黄金比例",
            "不要抄底，等 MA50 企稳",
        ]
    else:
        light = "red"
        title = "熊市趋势 — 全面防守"
        regime = "bear_trend"
        position = 30
        checklist = [
            "核心仓位减至 35%",
            "清仓卫星仓位",
            "大幅增加债券（30%）和黄金（10%）",
            "保留 15%+ 现金等待底部信号",
            "底部信号: SPY 重新站上 MA200 + MA50 斜率转正",
        ]

    description = " | ".join(details[:4])

    return light, title, description, position, regime, cross_status, checklist


def _generate_status_signals(
    light: str, spy: dict, qqq: dict, regime: str
) -> list[dict]:
    """根据大盘状态生成交易信号"""
    signals = []

    if light == "green":
        signals.append({
            "name": "大盘绿灯：市场趋势向上，适合做多",
            "type": "bullish",
            "weight": 2,
        })
    elif light == "red":
        signals.append({
            "name": "大盘红灯：市场趋势向下，控制仓位",
            "type": "bearish",
            "weight": 3,
        })
    else:
        signals.append({
            "name": "大盘黄灯：方向不明，观望为主",
            "type": "neutral",
            "weight": 1,
        })

    # 金叉/死叉信号
    cross = spy.get("cross", {})
    if cross.get("status") == "golden_cross" and cross.get("days_ago", 999) < 10:
        signals.append({
            "name": "SPY 近期金叉！历史统计胜率较高",
            "type": "bullish",
            "weight": 3,
        })
    elif cross.get("status") == "death_cross" and cross.get("days_ago", 999) < 10:
        signals.append({
            "name": "SPY 近期死叉！注意风险",
            "type": "bearish",
            "weight": 3,
        })

    return signals
