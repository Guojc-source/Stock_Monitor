"""
历史估值分析模块
================
拉取 5 年数据，计算 PE/PS 的历史分位和 PE Band，
回答"当前估值在历史上处于什么位置"。
"""

import yfinance as yf
import pandas as pd
import numpy as np


def get_historical_valuation(symbol: str) -> dict:
    """
    获取历史估值数据并计算当前分位。

    方法:
    - 用 yfinance 拉 5 年日线
    - 计算每日的 PE（市值/TTM盈利，但 yfinance 不直接提供历史 PE）
    - 替代方案：从 quarterly financials 提取历史 EPS，计算历史 PE 带
    - 最终方案：拉 5 年价格数据 + info 中的当前估值，至少给出价格分位

    返回:
        {
            "current_price": float,
            "price_percentile_1y": float,   # 1年价格分位
            "price_percentile_3y": float,   # 3年价格分位
            "price_percentile_5y": float,   # 5年价格分位
            "price_vs_ma200": float,        # 价格 vs MA200 (%)
            "current_pe": float,            # 当前 PE
            "pe_estimate": str,             # PE 估值判断
            "signals": [...],
        }
    """
    ticker = yf.Ticker(symbol)
    info = ticker.info or {}

    current_pe = info.get("trailingPE")
    forward_pe = info.get("forwardPE")
    current_price = info.get("regularMarketPrice") or info.get("currentPrice")
    if not current_price:
        # fallback: 从历史数据取
        try:
            hist = ticker.history(period="5d")
            current_price = float(hist["Close"].dropna().iloc[-1])
        except Exception:
            current_price = None

    result = {
        "current_price": round(current_price, 2) if current_price else None,
        "current_pe": round(current_pe, 1) if current_pe else None,
        "forward_pe": round(forward_pe, 1) if forward_pe else None,
        "price_percentile_1y": None,
        "price_percentile_3y": None,
        "price_percentile_5y": None,
        "price_vs_ma200": None,
        "pe_assessment": None,
        "signals": [],
    }

    # 拉 5 年价格数据
    try:
        df_5y = ticker.history(period="5y")
        if df_5y.empty or len(df_5y) < 200:
            result["signals"].append({"name": "历史数据不足（<200天），无法计算分位", "type": "neutral", "weight": 0})
            return result

        df_5y = df_5y[df_5y["Close"].notna()]

        # 价格分位
        close_series = df_5y["Close"]
        now = pd.Timestamp.now(tz=df_5y.index.tz) if df_5y.index.tz else pd.Timestamp.now()

        for period_name, period_months in [("1y", 12), ("3y", 36), ("5y", 60)]:
            cutoff = now - pd.DateOffset(months=period_months)
            period_data = close_series[close_series.index >= cutoff]
            if len(period_data) >= 50 and current_price:
                pct = (period_data < current_price).sum() / len(period_data) * 100
                result[f"price_percentile_{period_name}"] = round(float(pct), 1)

        # 价格 vs MA200
        if len(close_series) >= 200:
            ma200 = float(close_series.rolling(200).mean().iloc[-1])
            if current_price and ma200 > 0:
                result["price_vs_ma200"] = round((current_price - ma200) / ma200 * 100, 1)

        # PE 估值判断
        if current_pe:
            if current_pe < 15:
                result["pe_assessment"] = "低估值区间（PE < 15）"
                result["signals"].append({"name": f"PE={current_pe:.0f} 处于绝对低估值区间", "type": "bullish", "weight": 2})
            elif current_pe < 20:
                result["pe_assessment"] = "合理偏低（PE 15-20）"
                result["signals"].append({"name": f"PE={current_pe:.0f} 估值合理偏低", "type": "bullish", "weight": 1})
            elif current_pe < 30:
                result["pe_assessment"] = "合理偏高（PE 20-30）"
            elif current_pe < 50:
                result["pe_assessment"] = "高估值区间（PE 30-50）"
                result["signals"].append({"name": f"PE={current_pe:.0f} 估值偏高", "type": "bearish", "weight": 1})
            else:
                result["pe_assessment"] = "极高估值（PE > 50）"
                result["signals"].append({"name": f"PE={current_pe:.0f} 估值极高", "type": "bearish", "weight": 2})

        # 价格分位信号
        if result.get("price_percentile_5y"):
            pct = result["price_percentile_5y"]
            if pct > 90:
                result["signals"].append({"name": f"5年价格分位 {pct}%（接近历史高位）", "type": "bearish", "weight": 1})
            elif pct < 20:
                result["signals"].append({"name": f"5年价格分位 {pct}%（接近历史低位）", "type": "bullish", "weight": 2})

        # MA200 偏离
        if result.get("price_vs_ma200") is not None:
            dev = result["price_vs_ma200"]
            if dev > 30:
                result["signals"].append({"name": f"价格高于 MA200 {dev:.0f}%（大幅偏离均值，警惕均值回归）", "type": "bearish", "weight": 2})
            elif dev < -20:
                result["signals"].append({"name": f"价格低于 MA200 {abs(dev):.0f}%（深度折价）", "type": "bullish", "weight": 2})

    except Exception as e:
        result["signals"].append({"name": f"历史估值计算异常: {e}", "type": "neutral", "weight": 0})

    if not result["signals"]:
        result["signals"].append({"name": "历史估值数据正常", "type": "neutral", "weight": 0})

    return result


def get_historical_valuation_cn_hk(symbol,market,df):
    """CN/HK historical valuation using already-fetched DataFrame."""
    result={"current_price":None,"current_pe":None,"forward_pe":None,
        "price_percentile_1y":None,"price_percentile_3y":None,"price_percentile_5y":None,
        "price_vs_ma200":None,"pe_assessment":None,"signals":[]}
    if df is None or df.empty:
        result["signals"].append({"name":"无历史数据","type":"neutral","weight":0})
        return result
    close=df["close"]
    cur=float(close.iloc[-1])
    result["current_price"]=round(cur,2)
    now=pd.Timestamp.now()
    for pn,pm in [("1y",12),("3y",36)]:
        cutoff=now-pd.DateOffset(months=pm)
        pdata=close[close.index>=cutoff]
        if len(pdata)>=50:
            result[f"price_percentile_{pn}"]=round(float((pdata<cur).sum()/len(pdata)*100),1)
    if len(close)>=200:
        ma200=float(close.rolling(200).mean().iloc[-1])
        if ma200>0: result["price_vs_ma200"]=round((cur-ma200)/ma200*100,1)
    p5y=result.get("price_percentile_3y")
    if p5y and p5y>90: result["signals"].append({"name":f"3年价格分位{p5y}%（高位）","type":"bearish","weight":1})
    elif p5y and p5y<20: result["signals"].append({"name":f"3年价格分位{p5y}%（低位）","type":"bullish","weight":2})
    dev=result.get("price_vs_ma200")
    if dev and dev>30: result["signals"].append({"name":f"价格高于MA200 {dev:.0f}%","type":"bearish","weight":2})
    elif dev and dev<-20: result["signals"].append({"name":f"价格低于MA200 {abs(dev):.0f}%","type":"bullish","weight":2})
    if not result["signals"]: result["signals"].append({"name":"历史估值数据正常","type":"neutral","weight":0})
    return result
