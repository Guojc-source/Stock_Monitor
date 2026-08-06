"""
基本面分析模块
==============
通过 yfinance 获取估值、增长、盈利能力、分析师评级等数据，
将原始数字转化为可比较的信号（基于行业基准的相对比较）。
"""

import yfinance as yf
import numpy as np
from industry_benchmarks import get_sector_benchmark, compare_to_benchmark


def get_fundamental_data(symbol: str) -> dict:
    """
    获取基本面核心数据。

    返回:
        {
            "valuation": {...},    # 估值数据
            "growth": {...},       # 增长数据
            "profitability": {...},# 盈利能力
            "analyst": {...},      # 分析师评级
            "signals": [...]       # 基本面信号列表
        }
    """
    ticker = yf.Ticker(symbol)
    info = ticker.info or {}

    data = {
        "company_name": info.get("longName", info.get("shortName", symbol)),
        "sector": info.get("sector", "N/A"),
        "industry": info.get("industry", "N/A"),
        "market_cap": info.get("marketCap"),
        "valuation": _extract_valuation(info),
        "growth": _extract_growth(info),
        "profitability": _extract_profitability(info),
        "analyst": _extract_analyst(info),
    }

    data["signals"] = _evaluate_fundamentals(data)
    return data


def _safe_float(info: dict, *keys) -> float | None:
    """从 info dict 中安全提取数值"""
    for k in keys:
        v = info.get(k)
        if v is not None:
            try:
                return float(v)
            except (ValueError, TypeError):
                continue
    return None


def _extract_valuation(info: dict) -> dict:
    """提取估值指标"""
    pe = _safe_float(info, "trailingPE", "forwardPE")
    forward_pe = _safe_float(info, "forwardPE")
    peg = _safe_float(info, "pegRatio")
    ps = _safe_float(info, "priceToSalesTrailing12Months", "priceToSales")
    pb = _safe_float(info, "priceToBook")
    ev_to_ebitda = _safe_float(info, "enterpriseToEbitda")
    ev_to_revenue = _safe_float(info, "enterpriseToRevenue")

    return {
        "PE": round(pe, 1) if pe else None,
        "ForwardPE": round(forward_pe, 1) if forward_pe else None,
        "PEG": round(peg, 2) if peg else None,
        "PS": round(ps, 1) if ps else None,
        "PB": round(pb, 1) if pb else None,
        "EV_EBITDA": round(ev_to_ebitda, 1) if ev_to_ebitda else None,
    }


def _extract_growth(info: dict) -> dict:
    """提取增长指标"""
    rev_growth = _safe_float(info, "revenueGrowth")
    earnings_growth = _safe_float(info, "earningsGrowth")
    earnings_quarterly_growth = _safe_float(info, "earningsQuarterlyGrowth")

    return {
        "RevenueGrowth_YoY": round(rev_growth * 100, 1) if rev_growth else None,
        "EarningsGrowth_YoY": round(earnings_growth * 100, 1) if earnings_growth else None,
        "EarningsGrowth_QoQ": round(earnings_quarterly_growth * 100, 1) if earnings_quarterly_growth else None,
    }


def _extract_profitability(info: dict) -> dict:
    """提取盈利能力指标"""
    gross_margin = _safe_float(info, "grossMargins")
    operating_margin = _safe_float(info, "operatingMargins")
    net_margin = _safe_float(info, "profitMargins")
    roe = _safe_float(info, "returnOnEquity")
    roa = _safe_float(info, "returnOnAssets")
    fcf = _safe_float(info, "freeCashflow")
    revenue = _safe_float(info, "totalRevenue")

    return {
        "GrossMargin": round(gross_margin * 100, 1) if gross_margin else None,
        "OperatingMargin": round(operating_margin * 100, 1) if operating_margin else None,
        "NetMargin": round(net_margin * 100, 1) if net_margin else None,
        "ROE": round(roe * 100, 1) if roe else None,
        "ROA": round(roa * 100, 1) if roa else None,
        "FCF": f"${fcf/1e9:.1f}B" if fcf else None,
        "Revenue": f"${revenue/1e9:.1f}B" if revenue else None,
    }


def _extract_analyst(info: dict) -> dict:
    """提取分析师评级"""
    target_low = _safe_float(info, "targetLowPrice")
    target_high = _safe_float(info, "targetHighPrice")
    target_mean = _safe_float(info, "targetMeanPrice")
    current = _safe_float(info, "currentPrice",
                          "regularMarketPrice",
                          "previousClose")
    recommendation = info.get("recommendationKey", "N/A")
    num_analysts = info.get("numberOfAnalystOpinions")

    upside = None
    if target_mean and current and current > 0:
        upside = round((target_mean / current - 1) * 100, 1)

    return {
        "Recommendation": recommendation,
        "AnalystCount": num_analysts,
        "TargetMean": round(target_mean, 2) if target_mean else None,
        "TargetLow": round(target_low, 2) if target_low else None,
        "TargetHigh": round(target_high, 2) if target_high else None,
        "Upside": upside,
    }


def _evaluate_fundamentals(data: dict) -> list[dict]:
    """
    将基本面数据转化为买卖信号（基于行业基准的相对比较）。

    判断逻辑：
    - 估值相对行业均值：PE/PS/PB vs 行业基准 → bullish/bearish
    - 增长相对行业均值：营收/盈利增速 vs 行业基准 → bullish/bearish
    - 盈利能力相对行业均值：毛利率/净利率/ROE vs 行业基准 → bullish/bearish
    - 分析师看多（Buy rating + 上行空间 > 10%）→ bullish
    """
    signals = []
    val = data["valuation"]
    growth = data["growth"]
    prof = data["profitability"]
    analyst = data["analyst"]
    sector = data.get("sector", "")

    # 获取行业基准
    benchmark = get_sector_benchmark(sector, market="us")
    benchmark_desc = benchmark["description"] if benchmark else "无行业基准"

    # === 估值信号（相对行业基准）===
    if val.get("PEG") is not None:
        peg = val["PEG"]
        # 检查盈利是否异常（可能扭曲 PEG）
        eg = growth.get("EarningsGrowth_YoY")
        abnormal_earnings = eg and abs(eg) > 100

        if abnormal_earnings:
            signals.append({"name": f"PEG={peg:.2f}（⚠️ 盈利异常致 PEG 失真，参考价值有限）", "type": "neutral", "weight": 0})
        elif peg < 1.0:
            signals.append({"name": f"PEG={peg:.2f}（低估，成长股合理 < 1）", "type": "bullish", "weight": 3})
        elif peg < 2.0:
            signals.append({"name": f"PEG={peg:.2f}（估值合理）", "type": "bullish", "weight": 1})
        elif peg > 4.0:
            signals.append({"name": f"PEG={peg:.2f}（估值偏高）", "type": "bearish", "weight": 2})
        else:
            signals.append({"name": f"PEG={peg:.2f}（估值略高）", "type": "bearish", "weight": 1})

    # PE 相对行业基准
    if val.get("PE") is not None and benchmark and benchmark.get("PE"):
        pe = val["PE"]
        pe_bench = benchmark["PE"]
        comp = compare_to_benchmark(pe, pe_bench, "PE")
        signals.append({
            "name": f"PE={pe:.0f} vs 行业均值{pe_bench}（{benchmark_desc}）: {comp['assessment']}",
            "type": comp["signal_type"],
            "weight": 2 if abs(comp["ratio"] - 1) > 0.3 else 1,
        })
    elif val.get("PE") is not None:
        pe = val["PE"]
        # 无行业基准时用绝对值判断
        if pe > 100:
            signals.append({"name": f"PE={pe:.0f}（极高估值）", "type": "bearish", "weight": 2})
        elif pe < 0:
            signals.append({"name": "PE 为负（当前亏损）", "type": "bearish", "weight": 2})

    # Forward PE vs Trailing PE 交叉验证
    if val.get("PE") and val.get("ForwardPE"):
        pe = val["PE"]
        fpe = val["ForwardPE"]
        if fpe > pe * 1.3:
            signals.append({
                "name": f"Forward PE({fpe:.0f}) > Trailing PE({pe:.0f})，分析师预期盈利下降或历史盈利含一次性项目",
                "type": "neutral", "weight": 0
            })
        elif pe > fpe * 2:
            signals.append({
                "name": f"Forward PE({fpe:.0f}) 远低于 Trailing PE({pe:.0f})，预期盈利高增长",
                "type": "bullish", "weight": 1
            })

    # PS 相对行业基准
    if val.get("PS") is not None and benchmark and benchmark.get("PS"):
        ps = val["PS"]
        ps_bench = benchmark["PS"]
        comp = compare_to_benchmark(ps, ps_bench, "PS")
        signals.append({
            "name": f"PS={ps:.1f} vs 行业均值{ps_bench}: {comp['assessment']}",
            "type": comp["signal_type"],
            "weight": 1,
        })

    # === 增长信号（相对行业基准）===
    if growth.get("RevenueGrowth_YoY") is not None:
        rg = growth["RevenueGrowth_YoY"]
        if benchmark and benchmark.get("revenue_growth"):
            rg_bench = benchmark["revenue_growth"]
            comp = compare_to_benchmark(rg, rg_bench, "revenue_growth")
            signals.append({
                "name": f"营收 YoY +{rg}% vs 行业均值+{rg_bench}%: {comp['assessment']}",
                "type": comp["signal_type"],
                "weight": 2 if abs(comp["ratio"] - 1) > 0.3 else 1,
            })
        else:
            # 无行业基准时用绝对值
            if rg > 30:
                signals.append({"name": f"营收 YoY +{rg}%（高速增长）", "type": "bullish", "weight": 3})
            elif rg > 15:
                signals.append({"name": f"营收 YoY +{rg}%（稳健增长）", "type": "bullish", "weight": 2})
            elif rg > 5:
                signals.append({"name": f"营收 YoY +{rg}%（温和增长）", "type": "bullish", "weight": 1})
            elif rg < 0:
                signals.append({"name": f"营收 YoY {rg}%（营收萎缩）", "type": "bearish", "weight": 3})

    if growth.get("EarningsGrowth_YoY") is not None:
        eg = growth["EarningsGrowth_YoY"]
        if eg > 100:
            # 异常高增长通常是一次性基数效应，标注但不给过高权重
            signals.append({"name": f"盈利 YoY +{eg}%（⚠️ 异常高，可能是一次性基数效应，已降权）", "type": "bullish", "weight": 1})
        elif eg > 50:
            signals.append({"name": f"盈利 YoY +{eg}%（爆发增长）", "type": "bullish", "weight": 3})
        elif eg > 20:
            signals.append({"name": f"盈利 YoY +{eg}%（强劲增长）", "type": "bullish", "weight": 2})
        elif eg < 0:
            signals.append({"name": f"盈利 YoY {eg}%（盈利下滑）", "type": "bearish", "weight": 3})

    # === 盈利能力信号（相对行业基准）===
    if prof.get("GrossMargin") is not None and benchmark and benchmark.get("gross_margin"):
        gm = prof["GrossMargin"]
        gm_bench = benchmark["gross_margin"]
        comp = compare_to_benchmark(gm, gm_bench, "gross_margin")
        signals.append({
            "name": f"毛利率 {gm}% vs 行业均值{gm_bench}%: {comp['assessment']}",
            "type": comp["signal_type"],
            "weight": 2 if abs(comp["ratio"] - 1) > 0.3 else 1,
        })
    elif prof.get("GrossMargin") is not None:
        gm = prof["GrossMargin"]
        # 无行业基准时用绝对值
        if gm > 70:
            signals.append({"name": f"毛利率 {gm}%（极高，有护城河）", "type": "bullish", "weight": 2})
        elif gm > 50:
            signals.append({"name": f"毛利率 {gm}%（良好）", "type": "bullish", "weight": 1})
        elif gm < 20:
            signals.append({"name": f"毛利率 {gm}%（盈利薄弱）", "type": "bearish", "weight": 2})

    if prof.get("NetMargin") is not None and benchmark and benchmark.get("net_margin"):
        nm = prof["NetMargin"]
        nm_bench = benchmark["net_margin"]
        comp = compare_to_benchmark(nm, nm_bench, "net_margin")
        signals.append({
            "name": f"净利率 {nm}% vs 行业均值{nm_bench}%: {comp['assessment']}",
            "type": comp["signal_type"],
            "weight": 1,
        })
    elif prof.get("NetMargin") is not None:
        nm = prof["NetMargin"]
        if nm > 25:
            signals.append({"name": f"净利率 {nm}%（优秀）", "type": "bullish", "weight": 2})
        elif nm < 5:
            signals.append({"name": f"净利率 {nm}%（微利）", "type": "bearish", "weight": 1})

    if prof.get("ROE") is not None and benchmark and benchmark.get("ROE"):
        roe = prof["ROE"]
        roe_bench = benchmark["ROE"]
        comp = compare_to_benchmark(roe, roe_bench, "ROE")
        signals.append({
            "name": f"ROE {roe}% vs 行业均值{roe_bench}%: {comp['assessment']}",
            "type": comp["signal_type"],
            "weight": 1,
        })

    # === 分析师信号 ===
    if analyst.get("Recommendation"):
        rec = analyst["Recommendation"]
        if rec in ("buy", "strong_buy"):
            signals.append({"name": f"分析师评级: 买入 ({analyst.get('AnalystCount', '?')}位分析师)", "type": "bullish", "weight": 2})
        elif rec == "hold":
            signals.append({"name": "分析师评级: 持有", "type": "neutral", "weight": 0})
        elif rec in ("sell", "underperform"):
            signals.append({"name": "分析师评级: 卖出 ⚠️", "type": "bearish", "weight": 3})

    if analyst.get("Upside") is not None:
        up = analyst["Upside"]
        if up > 20:
            signals.append({"name": f"分析师目标价上行空间 +{up}%", "type": "bullish", "weight": 2})
        elif up > 0:
            signals.append({"name": f"分析师目标价上行空间 +{up}%", "type": "bullish", "weight": 1})
        elif up < -10:
            signals.append({"name": f"分析师目标价下行空间 {up}%（高于现价）", "type": "bearish", "weight": 2})

    return signals
