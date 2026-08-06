"""
本地数据源（测试/离线模式）
===========================
当 yfinance 不可用时，从本地 CSV 加载 K 线数据。
CSV 必须包含: Date, open, high, low, close, volume
"""

import pandas as pd
from pathlib import Path

FIXTURE_DIR = Path(__file__).parent / ".cache"


def _generate_realistic_fixture(symbol: str, current_price: float,
                                price_range: tuple, trend: str = "up",
                                periods: int = 124) -> pd.DataFrame:
    """
    生成逼真的测试数据（带趋势、波动率聚集、量价关系）。

    参数:
        symbol: 股票代码
        current_price: 最新价格
        price_range: (最低, 最高) 范围
        trend: "up" | "down" | "sideways"
        periods: 数据条数
    """
    import numpy as np
    np.random.seed(abs(hash(symbol)) % (2**31))

    # 趋势基础
    if trend == "up":
        drift = 0.0015
    elif trend == "down":
        drift = -0.0015
    else:
        drift = 0.0002

    # 生成带波动率聚集的回报序列
    returns = []
    vol = 0.015
    for _ in range(periods):
        vol = 0.85 * vol + 0.15 * np.random.uniform(0.01, 0.025)
        ret = np.random.normal(drift, vol)
        returns.append(ret)

    # 从最新价反推
    returns = returns[::-1]
    prices = current_price * np.exp(-np.cumsum(returns[::-1]))[::-1]
    prices = np.clip(prices, price_range[0] * 0.8, price_range[1] * 1.2)

    # OHLC
    opens = np.zeros(periods)
    highs = np.zeros(periods)
    lows = np.zeros(periods)
    closes = prices
    volumes = np.zeros(periods, dtype=int)

    base_vol = 5_000_000

    for i in range(periods):
        if i == 0:
            opens[i] = closes[i] * np.random.uniform(0.998, 1.002)
        else:
            opens[i] = closes[i-1] * np.random.uniform(0.998, 1.002)

        body = abs(closes[i] - opens[i])
        wick = body * np.random.uniform(0.3, 2.0)
        highs[i] = max(opens[i], closes[i]) + wick * np.random.uniform(0.3, 1.0)
        lows[i] = min(opens[i], closes[i]) - wick * np.random.uniform(0.3, 1.0)

        # 量价关系: 上涨放量、下跌缩量
        vol_factor = np.random.uniform(0.6, 1.5)
        if closes[i] > opens[i]:
            vol_factor *= 1.3
        volumes[i] = int(base_vol * vol_factor)

    dates = pd.date_range(end=pd.Timestamp.now().strftime("%Y-%m-%d"),
                          periods=periods, freq="B")

    df = pd.DataFrame({
        "open": opens, "high": highs, "low": lows,
        "close": closes, "volume": volumes,
    }, index=dates)

    return df


# 预定义的股票配置（近似真实价格区间）
STOCK_CONFIGS = {
    "TSLA":  {"price": 260, "range": (180, 350), "trend": "sideways"},
    "ADBE":  {"price": 250, "range": (200, 280), "trend": "down"},
    "AAPL":  {"price": 270, "range": (240, 300), "trend": "up"},
    "NFLX":  {"price": 1100, "range": (950, 1200), "trend": "up"},
    "GOOGL": {"price": 374, "range": (310, 380), "trend": "up"},
    "MSFT":  {"price": 488, "range": (420, 500), "trend": "up"},
}


def load_local_data(symbol: str) -> pd.DataFrame:
    """
    加载本地数据。优先读 CSV，不存在则自动生成逼真 fixture。

    返回标准化的 DataFrame，列名: open, high, low, close, volume
    """
    csv_path = FIXTURE_DIR / f"{symbol}.csv"

    # 1. 尝试读 CSV
    if csv_path.exists():
        df = pd.read_csv(csv_path, index_col=0, parse_dates=True)
        required = ["open", "high", "low", "close", "volume"]
        if all(c in df.columns for c in required):
            return df

    # 2. 自动生成 fixture
    config = STOCK_CONFIGS.get(symbol, {"price": 100, "range": (80, 120), "trend": "up"})
    df = _generate_realistic_fixture(symbol, config["price"], config["range"], config["trend"])

    # 保存 CSV
    FIXTURE_DIR.mkdir(exist_ok=True)
    df.to_csv(csv_path)
    print(f"  📝 已生成本地测试数据: {csv_path.name}")

    return df
