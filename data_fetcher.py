"""
数据获取模块（加固版）
=====================
- 时区安全：统一转为 tz-naive，避免比较崩溃
- NaN 智能处理：最新一行用实时价补全，历史行当作非交易日删除
- 限流重试：遇到 Rate Limit 自动退避重试（最多3次）
"""

import yfinance as yf
from yfinance.exceptions import YFRateLimitError
import pandas as pd
import time
import random
from cache import get_cached, set_cache, cache_status
import numpy as np
from datetime import datetime, timezone
from typing import Optional
from config import SYMBOLS, PERIOD, INTERVAL


def _retry_fetch(func, max_retries=5, base_delay=30):
    """限流自动重试——指数退避（base=30s，最长等8分钟）"""
    for attempt in range(max_retries):
        try:
            return func()
        except YFRateLimitError:
            delay = base_delay * (2 ** attempt) + random.uniform(0, 5)
            print(f"  ⚠️ Yahoo限流，{delay:.0f}秒后重试 (第{attempt+1}/{max_retries}次)...")
            time.sleep(delay)
        except Exception as e:
            msg = str(e).lower()
            if "rate limit" in msg or "too many requests" in msg:
                delay = base_delay * (2 ** attempt) + random.uniform(0, 5)
                print(f"  ⚠️ 疑似限流，{delay:.0f}秒后重试 (第{attempt+1}/{max_retries}次)...")
                time.sleep(delay)
            else:
                raise
    # 最后一次尝试
    return func()


def fetch_stock_data(symbol: str, period: str = PERIOD, interval: str = INTERVAL) -> pd.DataFrame:
    """
    获取单只股票 OHLCV 数据（加固版 + 限流重试）。

    时间线处理：
    - yfinance 返回 tz-aware index (America/New_York)
    - 我们统一 strip 时区，避免后续所有比较崩溃

    NaN 处理：
    - 最后一行：可能是当日未结算数据 → 用 ticker.info 实时价补全
    - 历史行：真正非交易日 → 删除
    """
    # === 尝试缓存 ===
    cache_ttl = 600 if interval in ("1h", "30m", "15m", "5m", "1m") else 1800  # 日内10分钟，日线30分钟
    cached = get_cached("history", symbol, period, interval, max_age_seconds=cache_ttl)
    if cached and "_df_json" in cached:
        try:
            df = pd.read_json(cached["_df_json"])
            if not df.empty and "close" in df.columns:
                return df
        except Exception:
            pass

    ticker = yf.Ticker(symbol)
    df = _retry_fetch(lambda: ticker.history(period=period, interval=interval))

    if df.empty:
        raise ValueError(f"无法获取 {symbol} 的数据，请检查代码是否正确")

    # ===== 步骤 1: 处理 MultiIndex columns =====
    if isinstance(df.columns, pd.MultiIndex):
        df = df.xs(symbol, axis=1, level=1)

    # ===== 步骤 2: 列名标准化为小写 =====
    rename_map = {}
    for col in df.columns:
        col_lower = col.lower()
        if "open" in col_lower:
            rename_map[col] = "open"
        elif "high" in col_lower:
            rename_map[col] = "high"
        elif "low" in col_lower:
            rename_map[col] = "low"
        elif "close" in col_lower and "adj" not in col_lower:
            rename_map[col] = "close"
        elif "volume" in col_lower:
            rename_map[col] = "volume"
    df.rename(columns=rename_map, inplace=True)

    # 确保必要列
    required = ["open", "high", "low", "close", "volume"]
    for col in required:
        if col not in df.columns:
            cap = col.capitalize()
            if cap in df.columns:
                df.rename(columns={cap: col}, inplace=True)
            else:
                raise ValueError(f"数据中缺少必要列: {col}，实际列名: {list(df.columns)}")

    # ===== 步骤 3: NaN 智能处理 =====
    # 3a. 如果最后一行 close 是 NaN → 用实时价补全
    last_idx = df.index[-1]
    if pd.isna(df.at[last_idx, "close"]):
        try:
            info = ticker.info
            live_price = info.get("regularMarketPrice") or info.get("currentPrice")
            if live_price:
                df.at[last_idx, "close"] = float(live_price)
                # 补全 OHLC（如果都是 NaN）
                if pd.isna(df.at[last_idx, "open"]):
                    df.at[last_idx, "open"] = float(info.get("regularMarketOpen", live_price))
                    df.at[last_idx, "high"] = float(info.get("regularMarketDayHigh", live_price))
                    df.at[last_idx, "low"] = float(info.get("regularMarketDayLow", live_price))
        except Exception:
            pass  # 补全失败也只能继续

    # 3b. 历史行 close 是 NaN → 真正非交易日，删除（保留最后一行）
    for i in range(len(df) - 2, -1, -1):  # 从倒数第二行往前
        if pd.isna(df["close"].iloc[i]):
            df = df.drop(df.index[i])

    # 3c. 最终检查
    df = df.copy()
    if df.empty:
        raise ValueError(f"{symbol} 所有数据无效")
    if pd.isna(df["close"].iloc[-1]):
        raise ValueError(f"{symbol} 最新价无法获取，Yahoo Finance 可能暂不可用")

    # ===== 步骤 4: 时区安全 —— strip timezone =====
    # yfinance 返回 America/New_York tz-aware index
    # 后续所有 pandas 操作如果混用 naive/aware datetime 会崩溃
    # 统一转为 tz-naive，保留日期时间
    if df.index.tz is not None:
        df.index = df.index.tz_localize(None)

    # === 写入缓存 ===
    try:
        set_cache("history", {"_df_json": df.to_json()}, symbol, period, interval)
    except Exception:
        pass

    return df


def get_live_info(symbol: str) -> dict:
    """
    获取实时信息（用于交叉验证）—— 带缓存+重试。
    缓存 5 分钟，避免重复请求。
    """
    cached = get_cached("live_info", symbol, max_age_seconds=300)
    if cached:
        return {k: v for k, v in cached.items() if not k.startswith("_")}

    ticker = yf.Ticker(symbol)

    def _fetch():
        return ticker.info or {}

    info = _retry_fetch(_fetch, max_retries=2, base_delay=10)

    result = {
        "symbol": symbol,
        "market_state": info.get("marketState", "UNKNOWN"),
        "live_price": info.get("regularMarketPrice") or info.get("currentPrice"),
        "previous_close": info.get("previousClose"),
        "day_high": info.get("regularMarketDayHigh"),
        "day_low": info.get("regularMarketDayLow"),
        "day_open": info.get("regularMarketOpen"),
        "volume": info.get("regularMarketVolume"),
        "exchange": info.get("exchange", "N/A"),
        "currency": info.get("currency", "USD"),
    }

    try:
        set_cache("live_info", result, symbol)
    except Exception:
        pass

    return result


def fetch_all_data(symbols: list[str] = None) -> dict[str, pd.DataFrame]:
    """批量获取数据"""
    if symbols is None:
        symbols = SYMBOLS

    results = {}
    cs = cache_status()
    from_cache_count = 0

    for i, sym in enumerate(symbols):
        if i > 0:
            time.sleep(random.uniform(2, 4))
        try:
            # 检查是否命中缓存
            cached = get_cached("history", sym, PERIOD, INTERVAL, max_age_seconds=1800)
            was_cached = cached is not None
            if was_cached:
                from_cache_count += 1

            results[sym] = fetch_stock_data(sym)
            source = "📦缓存" if was_cached else "🌐实时"
            print(f"  ✓ {sym}: {len(results[sym])} 条K线, 最新 ${float(results[sym]['close'].iloc[-1]):.2f} [{source}]")
        except Exception as e:
            print(f"  ✗ {sym}: {e}")

    if cs["files"] > 0:
        print(f"  [dim]缓存: {cs['files']}文件/{cs['size_kb']}KB, 本次命中{from_cache_count}/{len(symbols)}[/dim]")

    return results
