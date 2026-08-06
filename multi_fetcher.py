"""
多数据源获取模块
================
根据股票代码自动选择数据源：
- 美股 (.SS/.SZ/.HK 之外的) → yfinance
- A股 (.SS 上海 / .SZ 深圳) → akshare
- 港股 (.HK) → akshare
"""

import pandas as pd
import numpy as np
import time
import random
from datetime import datetime, timedelta


def detect_market(symbol: str) -> str:
    """
    根据代码后缀判断市场。

    返回: "us" | "cn" | "hk"
    """
    upper = symbol.upper()
    if upper.endswith(".SS"):
        return "cn"  # 上海A股
    elif upper.endswith(".SZ"):
        return "cn"  # 深圳A股
    elif upper.endswith(".HK"):
        return "hk"  # 港股
    else:
        return "us"  # 美股（默认）


def _fetch_yfinance(symbol: str, period: str = "6mo") -> pd.DataFrame:
    """yfinance 获取美股数据（延迟导入）"""
    try:
        import yfinance as yf
        from yfinance.exceptions import YFRateLimitError
    except ImportError:
        raise ImportError("yfinance 未安装。美股数据需要 yfinance。\n安装: pip install yfinance")

    ticker = yf.Ticker(symbol)
    for attempt in range(3):
        try:
            df = ticker.history(period=period, interval="1d")
            break
        except YFRateLimitError:
            delay = 15 * (2 ** attempt) + random.uniform(0, 5)
            print(f"  ⚠️ Yahoo限流，{delay:.0f}秒后重试({attempt+1}/3)...")
            time.sleep(delay)
    else:
        raise RuntimeError("yfinance 限流，请等15分钟后再试")

    if df.empty:
        raise ValueError(f"{symbol}: yfinance 返回空数据")

    # 列名标准化
    rename = {}
    for col in df.columns:
        cl = col.lower()
        if "open" in cl: rename[col] = "open"
        elif "high" in cl: rename[col] = "high"
        elif "low" in cl: rename[col] = "low"
        elif "close" in cl and "adj" not in cl: rename[col] = "close"
        elif "volume" in cl: rename[col] = "volume"
    df.rename(columns=rename, inplace=True)

    # NaN 处理 & 时区
    if df["close"].isna().any():
        last_idx = df.index[-1]
        if pd.isna(df.at[last_idx, "close"]):
            try:
                info = ticker.info
                lp = info.get("regularMarketPrice") or info.get("currentPrice")
                if lp:
                    df.at[last_idx, "close"] = float(lp)
                    if pd.isna(df.at[last_idx, "open"]):
                        df.at[last_idx, "open"] = float(info.get("regularMarketOpen", lp))
                        df.at[last_idx, "high"] = float(info.get("regularMarketDayHigh", lp))
                        df.at[last_idx, "low"] = float(info.get("regularMarketDayLow", lp))
            except Exception:
                pass
    df = df[df["close"].notna()].copy()

    if df.index.tz is not None:
        df.index = df.index.tz_localize(None)

    return df[["open", "high", "low", "close", "volume"]]


def _fetch_akshare(symbol: str, market: str, lookback_days: int = 180) -> pd.DataFrame:
    """akshare 获取 A 股/港股 K 线数据 —— 用子进程隔离代理"""
    import subprocess, json, os, tempfile

    code = symbol.upper().replace(".SS", "").replace(".SZ", "").replace(".HK", "")
    start = (datetime.now() - timedelta(days=lookback_days)).strftime("%Y%m%d")
    end = datetime.now().strftime("%Y%m%d")
    adjust = "qfq"
    market_type = "cn" if market == "cn" else "hk"

    script = f'''
import os, json, warnings
warnings.filterwarnings("ignore")
for k in ["http_proxy","https_proxy","HTTP_PROXY","HTTPS_PROXY","all_proxy","ALL_PROXY","no_proxy"]:
    os.environ.pop(k, None)
import akshare as ak
import pandas as pd

code = "{code}"
start = "{start}"
end = "{end}"
market_type = "{market_type}"

if market_type == "cn":
    df = ak.stock_zh_a_hist(symbol=code, period="daily", start_date=start, end_date=end, adjust="{adjust}")
else:
    df = ak.stock_hk_hist(symbol=code, period="daily", start_date=start, end_date=end, adjust="{adjust}")

if df is None or df.empty:
    print(json.dumps({{"error": "empty"}}))
else:
    # 标准化列名
    df.rename(columns={{"日期":"date","开盘":"open","收盘":"close","最高":"high","最低":"low","成交量":"volume"}}, inplace=True)
    df["date"] = df["date"].astype(str)
    print(df[["date","open","high","low","close","volume"]].to_json(orient="records"))
'''

    try:
        result = subprocess.run(
            ["/opt/homebrew/bin/python3.12", "-c", script],
            capture_output=True, text=True, timeout=60
        )
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"{symbol}: akshare 数据获取超时(60s)，请检查网络")
    except FileNotFoundError:
        raise RuntimeError(f"找不到 Python 解释器: /opt/homebrew/bin/python3.12")

    if result.returncode != 0:
        stderr = result.stderr.strip()
        if "ProxyError" in stderr or "proxy" in stderr.lower():
            raise RuntimeError(
                f"{symbol}: 代理拦截了国内数据源。请在代理软件中添加规则:\n"
                f"  DOMAIN-SUFFIX,eastmoney.com,DIRECT\n"
                f"  DOMAIN-SUFFIX,sina.com.cn,DIRECT\n"
                f"  或关闭代理后重试。\n  原始错误: {stderr[:200]}"
            )
        raise RuntimeError(f"{symbol}: akshare 数据获取失败: {stderr[:200]}")

    try:
        data = json.loads(result.stdout.strip())
    except json.JSONDecodeError:
        raise RuntimeError(f"{symbol}: 数据解析失败")

    if isinstance(data, dict) and "error" in data:
        raise RuntimeError(f"{symbol}: {data['error']}")

    df = pd.DataFrame(data)
    if df.empty:
        raise RuntimeError(f"{symbol}: 数据为空")

    df["date"] = pd.to_datetime(df["date"])
    df.set_index("date", inplace=True)

    for c in ["open", "high", "low", "close", "volume"]:
        if c not in df.columns:
            df[c] = np.nan

    df = df[["open", "high", "low", "close", "volume"]].astype(float)
    df.dropna(subset=["close"], inplace=True)

    return df


def fetch_stock_data_multi(symbol: str, period: str = "6mo") -> pd.DataFrame:
    """
    统一入口：根据代码后缀自动选数据源。

    示例:
        fetch_stock_data_multi("MSFT")       → yfinance
        fetch_stock_data_multi("600519.SS")  → akshare (茅台)
        fetch_stock_data_multi("00700.HK")   → akshare (腾讯)
    """
    market = detect_market(symbol)

    lookback_days = {
        "1mo": 30, "3mo": 90, "6mo": 180, "1y": 365, "2y": 730, "5y": 1825,
    }.get(period, 180)

    if market == "us":
        df = _fetch_yfinance(symbol, period)
        source = "yfinance"
    else:
        df = _fetch_akshare(symbol, market, lookback_days)
        source = "akshare"

    if df.empty:
        raise ValueError(f"{symbol}: 无有效数据")

    print(f"  ✓ {symbol} [{source}] {len(df)}行, "
          f"{df.index[0].strftime('%Y-%m-%d') if hasattr(df.index[0], 'strftime') else str(df.index[0])[:10]} → "
          f"{df.index[-1].strftime('%Y-%m-%d') if hasattr(df.index[-1], 'strftime') else str(df.index[-1])[:10]}, "
          f"最新 ¥{float(df['close'].iloc[-1]):.2f}" if market in ("cn", "hk")
          else f"最新 ${float(df['close'].iloc[-1]):.2f}")

    return df
