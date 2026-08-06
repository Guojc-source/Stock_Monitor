"""
技术指标计算模块
================
纯 Python/NumPy 实现，不依赖 TA-Lib。
涵盖：MA, BOLL, RSI, MACD, KDJ, 成交量指标。
"""

import numpy as np
import pandas as pd
from config import (
    MA_PERIODS, BOLL_PERIOD, BOLL_STD,
    RSI_PERIOD, MACD_FAST, MACD_SLOW, MACD_SIGNAL,
    KDJ_PERIOD, KDJ_K, KDJ_D, VOL_MA_PERIOD,
)


def calc_ma(df: pd.DataFrame, periods: list[int] = None) -> pd.DataFrame:
    """
    计算移动平均线。

    返回:
        在 df 上新增 MA5, MA10, MA20, MA50, MA200 列
    """
    if periods is None:
        periods = MA_PERIODS
    for p in periods:
        df[f"MA{p}"] = df["close"].rolling(window=p).mean()
    return df


def calc_boll(df: pd.DataFrame, period: int = BOLL_PERIOD, std: float = BOLL_STD) -> pd.DataFrame:
    """
    计算布林带。

    返回:
        新增 BOLL_MID(中轨/MA20), BOLL_UP(上轨), BOLL_DN(下轨), BOLL_WIDTH(带宽), BOLL_PCTB(位置百分比)
    """
    df["BOLL_MID"] = df["close"].rolling(window=period).mean()
    rolling_std = df["close"].rolling(window=period).std()
    df["BOLL_UP"] = df["BOLL_MID"] + std * rolling_std
    df["BOLL_DN"] = df["BOLL_MID"] - std * rolling_std
    # 带宽 = (上轨 - 下轨) / 中轨，反映波动率
    df["BOLL_WIDTH"] = (df["BOLL_UP"] - df["BOLL_DN"]) / df["BOLL_MID"] * 100
    # %B = (收盘价 - 下轨) / (上轨 - 下轨)，0-1之间，>1 突破上轨，<0 跌破下轨
    df["BOLL_PCTB"] = (df["close"] - df["BOLL_DN"]) / (df["BOLL_UP"] - df["BOLL_DN"])
    return df


def calc_rsi(df: pd.DataFrame, period: int = RSI_PERIOD) -> pd.DataFrame:
    """
    计算 RSI 相对强弱指标（Wilder 平滑法）。

    返回:
        新增 RSI 列
    """
    delta = df["close"].diff()
    gain = delta.clip(lower=0)
    loss = (-delta).clip(lower=0)

    avg_gain = gain.ewm(alpha=1 / period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, adjust=False).mean()

    rs = avg_gain / avg_loss.replace(0, np.nan)
    df["RSI"] = 100 - (100 / (1 + rs))
    return df


def calc_macd(df: pd.DataFrame,
              fast: int = MACD_FAST,
              slow: int = MACD_SLOW,
              signal: int = MACD_SIGNAL) -> pd.DataFrame:
    """
    计算 MACD。

    返回:
        新增 DIF(快线), DEA(慢线/信号线), MACD_HIST(柱状图= DIF - DEA)
    """
    ema_fast = df["close"].ewm(span=fast, adjust=False).mean()
    ema_slow = df["close"].ewm(span=slow, adjust=False).mean()
    df["DIF"] = ema_fast - ema_slow
    df["DEA"] = df["DIF"].ewm(span=signal, adjust=False).mean()
    df["MACD_HIST"] = 2 * (df["DIF"] - df["DEA"])  # 中国习惯×2，A股和美股的常规差异，不影响信号判断
    return df


def calc_kdj(df: pd.DataFrame,
             period: int = KDJ_PERIOD,
             k_smooth: int = KDJ_K,
             d_smooth: int = KDJ_D) -> pd.DataFrame:
    """
    计算 KDJ 随机指标。

    逻辑:
        RSV = (收盘价 - N日最低) / (N日最高 - N日最低) * 100
        K = RSV 的 EMA 平滑
        D = K 的 EMA 平滑
        J = 3K - 2D

    返回:
        新增 K, D, J 列
    """
    low_n = df["low"].rolling(window=period).min()
    high_n = df["high"].rolling(window=period).max()

    rsv = (df["close"] - low_n) / (high_n - low_n).replace(0, np.nan) * 100

    # 使用递归平滑：K_t = (k_smooth-1)/k_smooth * K_{t-1} + 1/k_smooth * RSV_t
    # 这里用 ewm 近似
    df["K"] = rsv.ewm(alpha=1 / k_smooth, adjust=False).mean()
    df["D"] = df["K"].ewm(alpha=1 / d_smooth, adjust=False).mean()
    df["J"] = 3 * df["K"] - 2 * df["D"]
    return df


def calc_volume_ma(df: pd.DataFrame, period: int = VOL_MA_PERIOD) -> pd.DataFrame:
    """
    计算成交量均线和量比。

    返回:
        新增 VOL_MA(成交量均线), VOL_RATIO(量比 = 当日量/均量)
    """
    df["VOL_MA"] = df["volume"].rolling(window=period).mean()
    df["VOL_RATIO"] = df["volume"] / df["VOL_MA"].replace(0, np.nan)
    return df


def calc_all_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """
    一次性计算所有技术指标。
    """
    df = df.copy()
    df = calc_ma(df)
    df = calc_boll(df)
    df = calc_rsi(df)
    df = calc_macd(df)
    df = calc_kdj(df)
    df = calc_volume_ma(df)
    return df
