"""
K 线形态识别模块
=================
识别经典的顶部反转和底部反转形态。
"""

import pandas as pd
import numpy as np


def _body(row: pd.Series) -> float:
    """实体长度 = |收盘 - 开盘|"""
    return abs(row["close"] - row["open"])


def _upper_shadow(row: pd.Series) -> float:
    """上影线长度"""
    return row["high"] - max(row["close"], row["open"])


def _lower_shadow(row: pd.Series) -> float:
    """下影线长度"""
    return min(row["close"], row["open"]) - row["low"]


def _total_range(row: pd.Series) -> float:
    """总振幅"""
    return row["high"] - row["low"]


def detect_hammer(df: pd.DataFrame, idx: int) -> dict | None:
    """
    锤子线（底部反转信号）：
    - 下影线 >= 实体 × 2
    - 上影线很短（< 实体 × 0.3）
    - 出现在下跌趋势中
    """
    row = df.iloc[idx]
    body = _body(row)
    total = _total_range(row)
    if total == 0 or body == 0:
        return None

    lower = _lower_shadow(row)
    upper = _upper_shadow(row)

    if lower >= body * 2 and upper <= body * 0.3:
        # 确认处于下跌趋势（前几天的收盘价更高）
        if idx >= 5:
            prev_close_avg = df["close"].iloc[idx - 5:idx].mean()
            if row["close"] < prev_close_avg:
                return {"name": "锤子线（底部反转）", "type": "bullish", "weight": 1}
    return None


def detect_shooting_star(df: pd.DataFrame, idx: int) -> dict | None:
    """
    射击之星（顶部反转信号）：
    - 上影线 >= 实体 × 2
    - 下影线很短（< 实体 × 0.3）
    - 出现在上涨趋势中
    """
    row = df.iloc[idx]
    body = _body(row)
    total = _total_range(row)
    if total == 0 or body == 0:
        return None

    upper = _upper_shadow(row)
    lower = _lower_shadow(row)

    if upper >= body * 2 and lower <= body * 0.3:
        if idx >= 5:
            prev_close_avg = df["close"].iloc[idx - 5:idx].mean()
            if row["close"] > prev_close_avg:
                return {"name": "射击之星（顶部反转）", "type": "bearish", "weight": 2}
    return None


def detect_engulfing(df: pd.DataFrame, idx: int) -> dict | None:
    """
    吞没形态：
    - 看涨吞没：阴线后接阳线，阳线实体完全吞没阴线实体
    - 看跌吞没：阳线后接阴线，阴线实体完全吞没阳线实体
    """
    if idx < 1:
        return None

    prev = df.iloc[idx - 1]
    curr = df.iloc[idx]

    prev_body = _body(prev)
    curr_body = _body(curr)
    if prev_body == 0 or curr_body == 0:
        return None

    # 看涨吞没
    if (prev["close"] < prev["open"] and  # 前一根是阴线
            curr["close"] > curr["open"] and  # 当前是阳线
            curr["open"] <= prev["close"] and  # 当前开盘 <= 前收盘
            curr["close"] >= prev["open"]):    # 当前收盘 >= 前开盘
        return {"name": "看涨吞没", "type": "bullish", "weight": 2}

    # 看跌吞没
    if (prev["close"] > prev["open"] and  # 前一根是阳线
            curr["close"] < curr["open"] and  # 当前是阴线
            curr["open"] >= prev["close"] and  # 当前开盘 >= 前收盘
            curr["close"] <= prev["open"]):    # 当前收盘 <= 前开盘
        return {"name": "看跌吞没", "type": "bearish", "weight": 2}

    return None


def detect_three_crows(df: pd.DataFrame, idx: int) -> dict | None:
    """
    三只乌鸦（顶部反转）：
    - 连续三根阴线
    - 每根都是实体较长（> 振幅的 60%）
    - 每根收盘价低于前一根
    """
    if idx < 2:
        return None

    r1, r2, r3 = df.iloc[idx - 2], df.iloc[idx - 1], df.iloc[idx]

    conditions = [
        r1["close"] < r1["open"] and _body(r1) > _total_range(r1) * 0.5,
        r2["close"] < r2["open"] and _body(r2) > _total_range(r2) * 0.5,
        r3["close"] < r3["open"] and _body(r3) > _total_range(r3) * 0.5,
        r1["close"] > r2["close"] > r3["close"],
    ]

    if all(conditions):
        return {"name": "三只乌鸦（强烈卖出）", "type": "bearish", "weight": 3}
    return None


def detect_three_soldiers(df: pd.DataFrame, idx: int) -> dict | None:
    """
    三白兵（底部反转）：
    - 连续三根阳线
    - 每根实体较长
    - 每根收盘价高于前一根
    """
    if idx < 2:
        return None

    r1, r2, r3 = df.iloc[idx - 2], df.iloc[idx - 1], df.iloc[idx]

    conditions = [
        r1["close"] > r1["open"] and _body(r1) > _total_range(r1) * 0.5,
        r2["close"] > r2["open"] and _body(r2) > _total_range(r2) * 0.5,
        r3["close"] > r3["open"] and _body(r3) > _total_range(r3) * 0.5,
        r1["close"] < r2["close"] < r3["close"],
    ]

    if all(conditions):
        return {"name": "三白兵（强烈买入）", "type": "bullish", "weight": 3}
    return None


def detect_doji(df: pd.DataFrame, idx: int) -> dict | None:
    """
    十字星（变盘信号）：
    - 实体极小（< 振幅 × 10%）
    - 上下影线都较长
    - 高位十字星 = 变盘向下；低位十字星 = 变盘向上
    """
    row = df.iloc[idx]
    body = _body(row)
    total = _total_range(row)
    if total == 0:
        return None

    if body < total * 0.1:
        upper = _upper_shadow(row)
        lower = _lower_shadow(row)
        if upper > body * 2 and lower > body * 2:
            # 看趋势方向
            if idx >= 5:
                prev_avg = df["close"].iloc[idx - 5:idx].mean()
                if row["close"] > prev_avg:
                    return {"name": "高位十字星（警惕变盘）", "type": "bearish", "weight": 1}
                else:
                    return {"name": "低位十字星（可能反转）", "type": "bullish", "weight": 1}
    return None


def detect_double_top(df: pd.DataFrame, idx: int, lookback: int = 40) -> dict | None:
    """
    双顶形态（顶部反转）：
    - 当前处于局部高点
    - 在过去若干天内有一个接近的高点
    - 两个高点之间有一个明显的低谷
    """
    if idx < lookback:
        return None

    recent = df["high"].iloc[idx - lookback:idx + 1]
    curr_high = recent.iloc[-1]

    # 找局部极大值
    from scipy.signal import argrelextrema
    local_max_idx = argrelextrema(recent.values, np.greater, order=5)[0]

    if len(local_max_idx) < 2:
        return None

    # 最近的两个局部高点
    top1_val = recent.iloc[local_max_idx[-2]]
    top2_val = recent.iloc[local_max_idx[-1]]

    # 两个顶部价格差在 3% 以内
    if abs(top1_val - top2_val) / top1_val < 0.03:
        between = recent.iloc[local_max_idx[-2]:local_max_idx[-1]]
        valley = between.min()
        # 中间有超过 5% 的回调
        if (top1_val - valley) / top1_val > 0.05:
            return {"name": "双顶形态（顶部反转）", "type": "bearish", "weight": 3}

    return None


def detect_double_bottom(df: pd.DataFrame, idx: int, lookback: int = 40) -> dict | None:
    """
    双底形态（底部反转）：
    - 和双顶相反
    """
    if idx < lookback:
        return None

    recent = df["low"].iloc[idx - lookback:idx + 1]
    curr_low = recent.iloc[-1]

    from scipy.signal import argrelextrema
    local_min_idx = argrelextrema(recent.values, np.less, order=5)[0]

    if len(local_min_idx) < 2:
        return None

    bottom1_val = recent.iloc[local_min_idx[-2]]
    bottom2_val = recent.iloc[local_min_idx[-1]]

    if abs(bottom1_val - bottom2_val) / bottom1_val < 0.03:
        between = recent.iloc[local_min_idx[-2]:local_min_idx[-1]]
        peak = between.max()
        if (peak - bottom1_val) / bottom1_val > 0.05:
            return {"name": "双底形态（底部反转）", "type": "bullish", "weight": 3}

    return None


def detect_all_patterns(df: pd.DataFrame) -> pd.DataFrame:
    """
    扫描最近 3 根 K 线，识别所有形态。
    在 df 上新增 pattern_name, pattern_type, pattern_weight 列。
    """
    df = df.copy()
    df["pattern_name"] = None
    df["pattern_type"] = None
    df["pattern_weight"] = 0

    detectors = [
        detect_hammer,
        detect_shooting_star,
        detect_engulfing,
        detect_three_crows,
        detect_three_soldiers,
        detect_doji,
        detect_double_top,
        detect_double_bottom,
    ]

    # 只检测最近 5 根 K 线（最关键的位置）
    start = max(0, len(df) - 5)
    for i in range(start, len(df)):
        for detector in detectors:
            result = detector(df, i)
            if result:
                df.at[df.index[i], "pattern_name"] = result["name"]
                df.at[df.index[i], "pattern_type"] = result["type"]
                df.at[df.index[i], "pattern_weight"] = result["weight"]
                break  # 一天只取第一个匹配的形态

    return df
