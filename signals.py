"""
信号检测模块
============
根据已计算的指标，识别各类买入/卖出信号。
每个信号有：名称、方向(bullish/bearish)、严重程度(weight 1-4)。
"""

import numpy as np
import pandas as pd
from scipy.signal import argrelextrema
from config import DIVERGENCE_LOOKBACK, DIVERGENCE_MIN_DIST


# ============================================================
# 趋势类信号
# ============================================================

def check_ma_signals(df: pd.DataFrame, idx: int) -> list[dict]:
    """
    均线信号：
    - 金叉/死叉（MA5 与 MA20）
    - 价格与 MA50/MA200 的关系
    - 均线排列（多头排列 vs 空头排列）
    """
    signals = []
    row = df.iloc[idx]

    # 1. MA5 与 MA20 的金叉/死叉
    if idx >= 1 and pd.notna(row.get("MA5")) and pd.notna(row.get("MA20")):
        prev = df.iloc[idx - 1]
        if (prev["MA5"] <= prev["MA20"] and row["MA5"] > row["MA20"] and
                pd.notna(prev["MA5"]) and pd.notna(prev["MA20"])):
            signals.append({"name": "MA5 上穿 MA20（金叉）", "type": "bullish", "weight": 3})
        elif (prev["MA5"] >= prev["MA20"] and row["MA5"] < row["MA20"] and
                pd.notna(prev["MA5"]) and pd.notna(prev["MA20"])):
            signals.append({"name": "MA5 下穿 MA20（死叉）", "type": "bearish", "weight": 3})

    # 2. 价格 vs MA50
    if pd.notna(row.get("MA50")):
        if row["close"] > row["MA50"]:
            signals.append({"name": "股价在 MA50 上方（中期多头）", "type": "bullish", "weight": 1})
        else:
            signals.append({"name": "股价跌破 MA50（中期转弱）", "type": "bearish", "weight": 3})

    # 3. 价格 vs MA200
    if pd.notna(row.get("MA200")):
        if row["close"] > row["MA200"]:
            signals.append({"name": "股价在 MA200 上方（长期多头）", "type": "bullish", "weight": 1})
        else:
            signals.append({"name": "股价跌破 MA200（牛熊分界线）", "type": "bearish", "weight": 4})

    # 4. 均线排列
    if pd.notna(row.get("MA5")) and pd.notna(row.get("MA20")) and pd.notna(row.get("MA50")):
        if row["MA5"] > row["MA20"] > row["MA50"]:
            signals.append({"name": "均线多头排列（强势）", "type": "bullish", "weight": 2})
        elif row["MA5"] < row["MA20"] < row["MA50"]:
            signals.append({"name": "均线空头排列（弱势）", "type": "bearish", "weight": 2})

    # 5. 放量跌破 MA20
    if idx >= 0 and pd.notna(row.get("MA20")):
        if (row["close"] < row["MA20"] and
                pd.notna(row.get("VOL_RATIO")) and row["VOL_RATIO"] > 1.5):
            signals.append({"name": "放量跌破 MA20（危险信号）", "type": "bearish", "weight": 3})

    return signals


def check_boll_signals(df: pd.DataFrame, idx: int) -> list[dict]:
    """
    布林带信号：
    - 股价与上/中/下轨的关系
    - 带宽变化
    """
    signals = []
    row = df.iloc[idx]

    if not pd.notna(row.get("BOLL_PCTB")):
        return signals

    pctb = row["BOLL_PCTB"]

    if pctb > 1.0:
        signals.append({"name": "股价突破布林上轨（超强/过热）", "type": "bearish", "weight": 1})
    elif pctb > 0.8:
        signals.append({"name": "股价接近布林上轨（强势）", "type": "bullish", "weight": 1})
    elif pctb < 0:
        signals.append({"name": "股价跌破布林下轨（超跌）", "type": "bullish", "weight": 1})
    elif pctb < 0.2:
        signals.append({"name": "股价接近布林下轨（弱势）", "type": "bearish", "weight": 1})

    # 中轨支撑/压力
    if pd.notna(row.get("BOLL_MID")):
        if row["close"] > row["BOLL_MID"]:
            signals.append({"name": "股价在布林中轨上方", "type": "bullish", "weight": 0})
        else:
            signals.append({"name": "股价在布林中轨下方", "type": "bearish", "weight": 1})

    # 带宽收窄 = 变盘前兆
    if idx >= 5 and pd.notna(row.get("BOLL_WIDTH")):
        boll_width_avg = df["BOLL_WIDTH"].iloc[idx - 5:idx].mean()
        boll_width_prev = df["BOLL_WIDTH"].iloc[idx - 10:idx - 5].mean() if idx >= 10 else boll_width_avg
        if boll_width_avg < boll_width_prev * 0.8:
            signals.append({"name": "布林带收窄（变盘前兆）", "type": "neutral", "weight": 1})

    return signals


# ============================================================
# 动能类信号
# ============================================================

def check_rsi_signals(df: pd.DataFrame, idx: int) -> list[dict]:
    """
    RSI 信号：
    - 超买/超卖
    - 顶背离/底背离
    """
    signals = []
    row = df.iloc[idx]

    if not pd.notna(row.get("RSI")):
        return signals

    rsi = row["RSI"]

    if rsi > 80:
        signals.append({"name": f"RSI = {rsi:.0f}（极度超买）", "type": "bearish", "weight": 3})
    elif rsi > 70:
        signals.append({"name": f"RSI = {rsi:.0f}（超买区）", "type": "bearish", "weight": 1})
    elif rsi < 20:
        signals.append({"name": f"RSI = {rsi:.0f}（极度超卖）", "type": "bullish", "weight": 3})
    elif rsi < 30:
        signals.append({"name": f"RSI = {rsi:.0f}（超卖区）", "type": "bullish", "weight": 1})

    # 顶背离检测
    div = detect_divergence(df, idx, price_col="close", indicator_col="RSI")
    if div:
        signals.append(div)

    return signals


def check_macd_signals(df: pd.DataFrame, idx: int) -> list[dict]:
    """
    MACD 信号：
    - 金叉/死叉
    - 零轴位置
    - 柱状图变化
    - 顶背离/底背离
    """
    signals = []
    row = df.iloc[idx]

    if not pd.notna(row.get("DIF")):
        return signals

    # 1. 金叉/死叉
    if idx >= 1:
        prev = df.iloc[idx - 1]
        if (pd.notna(prev.get("DIF")) and pd.notna(prev.get("DEA")) and
                prev["DIF"] <= prev["DEA"] and row["DIF"] > row["DEA"]):
            if row["DIF"] > 0:
                signals.append({"name": "MACD 零轴上方金叉（强势做多）", "type": "bullish", "weight": 3})
            else:
                signals.append({"name": "MACD 零轴下方金叉（反弹信号）", "type": "bullish", "weight": 2})
        elif (pd.notna(prev.get("DIF")) and pd.notna(prev.get("DEA")) and
                prev["DIF"] >= prev["DEA"] and row["DIF"] < row["DEA"]):
            if row["DIF"] < 0:
                signals.append({"name": "MACD 零轴下方死叉（加速下跌）", "type": "bearish", "weight": 3})
            else:
                signals.append({"name": "MACD 零轴上方死叉（趋势转弱）", "type": "bearish", "weight": 3})

    # 2. 零轴位置
    if row["DIF"] > 0:
        signals.append({"name": "MACD 零轴上方（多头市场）", "type": "bullish", "weight": 0})
    else:
        signals.append({"name": "MACD 零轴下方（空头市场）", "type": "bearish", "weight": 1})

    # 3. 红柱持续缩短（多头动能衰竭）
    if idx >= 3 and pd.notna(row.get("MACD_HIST")):
        recent_hist = df["MACD_HIST"].iloc[idx - 3:idx + 1]
        if all(recent_hist > 0) and recent_hist.is_monotonic_decreasing:
            signals.append({"name": "MACD 红柱持续缩短（动能衰减）", "type": "bearish", "weight": 2})

    # 4. 绿柱持续缩短（空头动能衰竭）
    if idx >= 3 and pd.notna(row.get("MACD_HIST")):
        recent_hist = df["MACD_HIST"].iloc[idx - 3:idx + 1]
        if all(recent_hist < 0) and recent_hist.is_monotonic_increasing:
            signals.append({"name": "MACD 绿柱持续缩短（空头衰竭）", "type": "bullish", "weight": 2})

    # 5. 顶背离
    div = detect_divergence(df, idx, price_col="close", indicator_col="DIF")
    if div:
        signals.append(div)

    return signals


def check_kdj_signals(df: pd.DataFrame, idx: int) -> list[dict]:
    """
    KDJ 信号：
    - 超买/超卖
    - 金叉/死叉
    """
    signals = []
    row = df.iloc[idx]

    if not pd.notna(row.get("K")) or not pd.notna(row.get("J")):
        return signals

    k, d, j = row["K"], row["D"], row["J"]

    # 超买/超卖（以 J 值为准，更敏感）
    if j > 100:
        signals.append({"name": f"KDJ J值={j:.0f}（极度超买）", "type": "bearish", "weight": 2})
    elif j < 0:
        signals.append({"name": f"KDJ J值={j:.0f}（极度超卖）", "type": "bullish", "weight": 2})

    if k > 80:
        signals.append({"name": f"KDJ K值={k:.0f}（超买区）", "type": "bearish", "weight": 1})
    elif k < 20:
        signals.append({"name": f"KDJ K值={k:.0f}（超卖区）", "type": "bullish", "weight": 1})

    # 金叉/死叉
    if idx >= 1:
        prev = df.iloc[idx - 1]
        if (pd.notna(prev.get("K")) and pd.notna(prev.get("D")) and
                prev["K"] <= prev["D"] and row["K"] > row["D"]):
            if k < 30:
                signals.append({"name": "KDJ 低位金叉（买入信号）", "type": "bullish", "weight": 2})
            else:
                signals.append({"name": "KDJ 金叉", "type": "bullish", "weight": 1})
        elif (pd.notna(prev.get("K")) and pd.notna(prev.get("D")) and
                prev["K"] >= prev["D"] and row["K"] < row["D"]):
            if k > 70:
                signals.append({"name": "KDJ 高位死叉（卖出信号）", "type": "bearish", "weight": 3})
            else:
                signals.append({"name": "KDJ 死叉", "type": "bearish", "weight": 1})

    return signals


# ============================================================
# 量价关系信号
# ============================================================

def check_volume_signals(df: pd.DataFrame, idx: int) -> list[dict]:
    """
    成交量信号：
    - 量增价涨 / 量缩价涨
    - 放量下跌
    - 量比异常
    """
    signals = []
    row = df.iloc[idx]

    if idx < 1 or not pd.notna(row.get("VOL_RATIO")):
        return signals

    prev = df.iloc[idx - 1]
    price_change = (row["close"] - prev["close"]) / prev["close"]
    vol_ratio = row["VOL_RATIO"]

    # 量价配合
    if price_change > 0.02 and vol_ratio > 1.5:
        signals.append({"name": "放量上涨（健康上涨）", "type": "bullish", "weight": 2})
    elif price_change > 0.01 and vol_ratio < 0.7:
        signals.append({"name": "缩量上涨（量价背离，涨势不牢）", "type": "bearish", "weight": 2})
    elif price_change < -0.02 and vol_ratio > 1.5:
        signals.append({"name": "放量下跌（资金出逃）", "type": "bearish", "weight": 3})
    elif price_change < -0.02 and vol_ratio < 0.7:
        signals.append({"name": "缩量下跌（抛压减轻）", "type": "bullish", "weight": 1})

    # 天量天价
    if vol_ratio > 3.0:
        if price_change > 0:
            signals.append({"name": "天量！关注是否天价", "type": "bearish", "weight": 2})
        else:
            signals.append({"name": "天量下跌（极度危险）", "type": "bearish", "weight": 4})

    # 高位滞涨（连续几天小涨但量越来越小）
    if idx >= 4:
        recent_changes = [
            (df["close"].iloc[i] - df["close"].iloc[i - 1]) / df["close"].iloc[i - 1]
            for i in range(idx - 3, idx + 1)
        ]
        recent_vols = [df["VOL_RATIO"].iloc[i] for i in range(idx - 3, idx + 1)]
        if (all(0 < c < 0.01 for c in recent_changes) and
                recent_vols[-1] < recent_vols[0] * 0.7):
            signals.append({"name": "高位缩量滞涨（警惕变盘）", "type": "bearish", "weight": 2})

    return signals


# ============================================================
# 背离检测（核心）
# ============================================================

def find_local_extrema(series: pd.Series, order: int = 5) -> tuple[np.ndarray, np.ndarray]:
    """
    找局部极值点。
    返回: (局部高点索引数组, 局部低点索引数组)
    """
    high_idx = argrelextrema(series.values, np.greater, order=order)[0]
    low_idx = argrelextrema(series.values, np.less, order=order)[0]
    return high_idx, low_idx


def detect_divergence(df: pd.DataFrame, idx: int,
                      price_col: str = "close",
                      indicator_col: str = "RSI",
                      lookback: int = DIVERGENCE_LOOKBACK,
                      min_dist: int = DIVERGENCE_MIN_DIST) -> dict | None:
    """
    检测顶背离/底背离。

    顶背离：股价创新高，但指标不创新高 → 卖出信号
    底背离：股价创新低，但指标不创新低 → 买入信号

    参数:
        df: 全量数据
        idx: 当前 K 线的位置
        price_col: 价格列名
        indicator_col: 指标列名
        lookback: 向前搜索范围
        min_dist: 两个极值点的最小间距
    """
    start = max(0, idx - lookback)
    window = df.iloc[start:idx + 1]

    if len(window) < min_dist * 2:
        return None

    price_series = window[price_col]
    indicator_series = window[indicator_col]

    # 找局部高点和低点
    price_highs, price_lows = find_local_extrema(price_series, order=5)
    ind_highs, ind_lows = find_local_extrema(indicator_series, order=5)

    # --- 顶背离检测 ---
    if len(price_highs) >= 2:
        # 取最后两个局部高点
        p1_idx = price_highs[-2]
        p2_idx = price_highs[-1]
        if p2_idx - p1_idx >= min_dist:
            p1_val = price_series.iloc[p1_idx]
            p2_val = price_series.iloc[p2_idx]
            # 找对应的指标高点
            if len(ind_highs) >= 2:
                i1_val = indicator_series.iloc[ind_highs[-2]]
                i2_val = indicator_series.iloc[ind_highs[-1]]
                # 顶背离：价格创新高 + 指标不创新高
                if p2_val > p1_val and i2_val < i1_val:
                    return {
                        "name": f"{indicator_col} 顶背离（股价新高，指标未新高 → 卖出信号）",
                        "type": "bearish",
                        "weight": 4
                    }

    # --- 底背离检测 ---
    if len(price_lows) >= 2:
        p1_idx = price_lows[-2]
        p2_idx = price_lows[-1]
        if p2_idx - p1_idx >= min_dist:
            p1_val = price_series.iloc[p1_idx]
            p2_val = price_series.iloc[p2_idx]
            if len(ind_lows) >= 2:
                i1_val = indicator_series.iloc[ind_lows[-2]]
                i2_val = indicator_series.iloc[ind_lows[-1]]
                # 底背离：价格创新低 + 指标不创新低
                if p2_val < p1_val and i2_val > i1_val:
                    return {
                        "name": f"{indicator_col} 底背离（股价新低，指标未新低 → 买入信号）",
                        "type": "bullish",
                        "weight": 4
                    }

    return None


# ============================================================
# 汇总所有信号
# ============================================================

def detect_all_signals(df: pd.DataFrame) -> list[dict]:
    """
    检测所有技术信号，返回信号列表。
    """
    idx = len(df) - 1  # 只看最新一根 K 线
    all_signals = []

    all_signals.extend(check_ma_signals(df, idx))
    all_signals.extend(check_boll_signals(df, idx))
    all_signals.extend(check_rsi_signals(df, idx))
    all_signals.extend(check_macd_signals(df, idx))
    all_signals.extend(check_kdj_signals(df, idx))
    all_signals.extend(check_volume_signals(df, idx))

    # K 线形态（从 df 中读取已检测的 pattern）
    row = df.iloc[idx]
    if pd.notna(row.get("pattern_name")) and row["pattern_name"]:
        all_signals.append({
            "name": row["pattern_name"],
            "type": row.get("pattern_type", "neutral"),
            "weight": int(row.get("pattern_weight", 1)),
        })

    return all_signals
