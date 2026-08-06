"""
A股/港股基本面分析模块
=====================
通过 akshare 获取 A 股和港股的估值、增长、盈利能力数据。
信号评估基于行业基准的相对比较。

注意: akshare 的 A 股函数和港股函数存在内部状态冲突（HTTP session/cookie 污染）。
解决方案: A 股和港股函数各自独立 import akshare，互不干扰。
"""

import pandas as pd
from industry_benchmarks import get_sector_benchmark, compare_to_benchmark


def get_fundamental_data_cn(symbol: str, market: str) -> dict:
    """
    获取 A 股/港股基本面数据。
    """
    try:
        import akshare
    except ImportError:
        return _empty("akshare 未安装")

    if market == "cn":
        return _fetch_cn(symbol)
    elif market == "hk":
        return _fetch_hk(symbol)
    else:
        return _empty(f"不支持的市场: {market}")


def _fetch_cn(symbol: str) -> dict:
    """A股基本面 — 子进程隔离代理"""
    import subprocess, json, os

    # 把所有 akshare 调用放进子进程（避开代理污染）
    code = symbol.upper().replace(".SS", "").replace(".SZ", "")

    script = f'''
import os, json, warnings
warnings.filterwarnings("ignore")
for k in ["http_proxy","https_proxy","HTTP_PROXY","HTTPS_PROXY","all_proxy","ALL_PROXY","no_proxy"]:
    os.environ.pop(k, None)
import akshare as ak
import pandas as pd

code = "{code}"

# 基本信息
try:
    info_df = ak.stock_individual_info_em(symbol=code)
    info = {{row["item"]: row["value"] for _, row in info_df.iterrows()}}
except:
    info = {{}}

# 财务摘要
try:
    fin_df = ak.stock_financial_abstract(symbol=code)
    fin_df.set_index("指标", inplace=True)
    date_cols = [c for c in fin_df.columns if c != "选项"]
    cols_4q = date_cols[:4]

    def _get_vals(name):
        if name not in fin_df.index: return None
        row = fin_df.loc[name]
        if isinstance(row, pd.DataFrame): row = row.iloc[0]
        v = row[cols_4q] if len(cols_4q) <= len(row) else row
        return pd.to_numeric(v, errors="coerce").tolist()

    np_vals = _get_vals("归母净利润")
    rev_vals = _get_vals("营业总收入")
    eps_vals = _get_vals("基本每股收益")
    bv_vals = _get_vals("每股净资产")
    deduct_vals = _get_vals("扣非净利润")

    # YoY
    rev_growth = None; earn_growth = None
    cur_r = _get_vals("营业总收入")
    if cur_r and len(date_cols) >= 8:
        prev_r = fin_df.loc["营业总收入"]
        if isinstance(prev_r, pd.DataFrame): prev_r = prev_r.iloc[0]
        prev_r_sum = pd.to_numeric(prev_r[date_cols[4:8]], errors="coerce").sum()
        if prev_r_sum > 0:
            rev_growth = (sum(cur_r) - prev_r_sum) / prev_r_sum
    cur_n = _get_vals("归母净利润")
    if cur_n and len(date_cols) >= 8 and "归母净利润" in fin_df.index:
        prev_n = fin_df.loc["归母净利润"]
        if isinstance(prev_n, pd.DataFrame): prev_n = prev_n.iloc[0]
        prev_n_sum = pd.to_numeric(prev_n[date_cols[4:8]], errors="coerce").sum()
        if prev_n_sum > 0:
            earn_growth = (sum(cur_n) - prev_n_sum) / prev_n_sum

    # ROE
    roe_val = None
    equity_row = fin_df.loc["股东权益合计(净资产)"] if "股东权益合计(净资产)" in fin_df.index else None
    if equity_row is not None:
        if isinstance(equity_row, pd.DataFrame): equity_row = equity_row.iloc[0]
        equity = float(pd.to_numeric(equity_row[date_cols[0]], errors="coerce")) if date_cols else 0
        if equity > 0 and np_vals: roe_val = sum(np_vals) / equity

    result = {{
        "company": str(info.get("股票简称", "")),
        "industry": str(info.get("行业", "")),
        "market_cap": float(info.get("总市值", 0) or 0),
        "price": float(info.get("最新", 0) or 0),
        "net_profit_ttm": sum(np_vals) if np_vals else 0,
        "revenue_ttm": sum(rev_vals) if rev_vals else 0,
        "eps": sum(eps_vals) if eps_vals else 0,
        "bvps": float(bv_vals[0]) if bv_vals else 0,
        "roe": float(roe_val or 0),
        "deduct_ttm": sum(deduct_vals) if deduct_vals else 0,
        "rev_growth": float(rev_growth or 0),
        "earn_growth": float(earn_growth or 0),
    }}
except Exception as e:
    result = {{"error": str(e)}}

print(json.dumps(result, default=str))
'''

    try:
        r = subprocess.run(["/opt/homebrew/bin/python3.12", "-c", script],
                          capture_output=True, text=True, timeout=60)
        if r.returncode != 0:
            return _empty(f"A股基本面子进程失败: {r.stderr[:100]}")
        data = json.loads(r.stdout.strip())
    except subprocess.TimeoutExpired:
        return _empty("A股基本面获取超时(60s)")
    except Exception as e:
        return _empty(f"A股基本面异常: {e}")

    if "error" in data:
        return _empty(f"A股基本面: {data['error']}")

    # 映射到标准格式
    mc = data.get("market_cap", 0) or 0
    np_ttm = data.get("net_profit_ttm", 0) or 0
    rev_ttm = data.get("revenue_ttm", 0) or 0
    price = data.get("price", 0) or 0
    bvps = data.get("bvps", 0) or 0
    roe_val = data.get("roe", 0) or 0
    rg = data.get("rev_growth", 0) or 0
    eg = data.get("earn_growth", 0) or 0
    deduct_ttm = data.get("deduct_ttm", 0) or 0

    pe = mc / np_ttm if (mc and np_ttm > 0) else None
    pb = price / bvps if (price and bvps and bvps > 0) else None
    ps = mc / rev_ttm if (mc and rev_ttm and rev_ttm > 0) else None

    quality_ratio = None
    if deduct_ttm and np_ttm and np_ttm > 0:
        quality_ratio = deduct_ttm / np_ttm

    data_out = {
        "company_name": data.get("company", symbol),
        "sector": data.get("industry", "N/A"),
        "industry": data.get("industry", "N/A"),
        "market_cap": mc if mc > 0 else None,
        "valuation": {
            "PE": round(pe, 1) if pe else None, "ForwardPE": None, "PEG": None,
            "PS": round(ps, 1) if ps else None, "PB": round(pb, 1) if pb else None, "EV_EBITDA": None,
        },
        "growth": {
            "RevenueGrowth_YoY": round(rg * 100, 1) if rg else None,
            "EarningsGrowth_YoY": round(eg * 100, 1) if eg else None,
            "EarningsGrowth_QoQ": None,
        },
        "profitability": {
            "GrossMargin": None, "OperatingMargin": None, "NetMargin": None,
            "ROE": round(roe_val * 100, 1) if roe_val else None,
            "FCF": None, "Revenue": f"¥{rev_ttm/1e8:.0f}亿" if rev_ttm > 0 else None,
        },
        "analyst": {"Recommendation": None, "AnalystCount": None, "TargetMean": None, "Upside": None},
    }
    data_out["signals"] = _evaluate_cn(data_out, quality_ratio)
    return data_out


def _fetch_hk(symbol: str) -> dict:
    """港股基本面 — 用子进程隔离 akshare 状态"""
    import subprocess
    import json

    code = symbol.upper().replace(".HK", "")

    script = f"""
import json, os
for k in ['http_proxy','https_proxy','HTTP_PROXY','HTTPS_PROXY','all_proxy']:
    os.environ.pop(k, None)
import akshare as ak
fin = ak.stock_hk_financial_indicator_em(symbol='{code}')
if fin is None or fin.empty:
    print(json.dumps({{"error": "empty"}}))
else:
    row = dict(fin.iloc[0])
    out = {{
        "pe": float(row.get("市盈率", 0)),
        "pb": float(row.get("市净率", 0)),
        "revenue": float(row.get("营业总收入", 0)),
        "net_profit": float(row.get("净利润", 0)),
        "roe": float(row.get("股东权益回报率(%)", 0)),
        "market_cap": float(row.get("总市值(港元)", 0)),
    }}
    print(json.dumps(out))
"""
    try:
        result = subprocess.run(
            ["/opt/homebrew/bin/python3.12", "-c", script],
            capture_output=True, text=True, timeout=30
        )
        if result.returncode != 0:
            return _empty(f"子进程失败: {result.stderr[:100]}")

        data = json.loads(result.stdout.strip())
        if "error" in data:
            return _empty(f"港股数据为空: {data['error']}")

        pe = data.get("pe", 0) or 0
        pb = data.get("pb", 0) or 0
        revenue = data.get("revenue", 0) or 0
        net_profit = data.get("net_profit", 0) or 0
        roe = data.get("roe", 0) or 0
        market_cap = data.get("market_cap", 0) or 0

        data_out = {
            "company_name": symbol,
            "sector": "港股", "industry": "港股",
            "market_cap": market_cap if market_cap > 0 else None,
            "valuation": {
                "PE": round(pe, 1) if pe > 0 else None, "ForwardPE": None, "PEG": None,
                "PS": None, "PB": round(pb, 1) if pb > 0 else None, "EV_EBITDA": None,
            },
            "growth": {"RevenueGrowth_YoY": None, "EarningsGrowth_YoY": None, "EarningsGrowth_QoQ": None},
            "profitability": {
                "GrossMargin": None, "OperatingMargin": None, "NetMargin": None,
                "ROE": round(roe, 1) if roe > 0 else None,
                "FCF": None, "Revenue": f"HK${revenue/1e8:.0f}亿" if revenue > 0 else None,
            },
            "analyst": {"Recommendation": None, "AnalystCount": None, "TargetMean": None, "Upside": None},
        }
        data_out["signals"] = _evaluate_cn(data_out, market="hk")
        return data_out

    except subprocess.TimeoutExpired:
        return _empty("港股数据获取超时(30s)")
    except Exception as e:
        import traceback
        return _empty(f"港股异常: {e} | {traceback.format_exc()[-200:]}")

def _evaluate_cn(data: dict, quality_ratio: float = None, market: str = "cn") -> list[dict]:
    """从 CN/HK 数据生成信号（基于行业基准的相对比较）"""
    signals = []
    val = data["valuation"]
    growth = data["growth"]
    prof = data["profitability"]
    sector = data.get("sector", data.get("industry", ""))

    # 获取行业基准
    benchmark = get_sector_benchmark(sector, market=market)
    benchmark_desc = benchmark["description"] if benchmark else "无行业基准"

    # PE 相对行业基准
    pe = val.get("PE")
    if pe is not None:
        if pe < 0:
            signals.append({"name": "PE为负（亏损）", "type": "bearish", "weight": 2})
        elif benchmark and benchmark.get("PE"):
            pe_bench = benchmark["PE"]
            comp = compare_to_benchmark(pe, pe_bench, "PE")
            signals.append({
                "name": f"PE={pe:.0f} vs 行业均值{pe_bench}（{benchmark_desc}）: {comp['assessment']}",
                "type": comp["signal_type"],
                "weight": 2 if abs(comp["ratio"] - 1) > 0.3 else 1,
            })
        else:
            # 无行业基准时用绝对值
            if pe < 15: signals.append({"name": f"PE={pe:.0f}（低估）", "type": "bullish", "weight": 2})
            elif pe < 25: signals.append({"name": f"PE={pe:.0f}（合理）", "type": "bullish", "weight": 1})
            elif pe > 50: signals.append({"name": f"PE={pe:.0f}（高估）", "type": "bearish", "weight": 2})

    # PB 相对行业基准
    pb = val.get("PB")
    if pb is not None:
        if pb < 1:
            signals.append({"name": f"PB={pb:.2f}（破净）", "type": "bullish", "weight": 2})
        elif benchmark and benchmark.get("PB"):
            pb_bench = benchmark["PB"]
            comp = compare_to_benchmark(pb, pb_bench, "PB")
            signals.append({
                "name": f"PB={pb:.1f} vs 行业均值{pb_bench}: {comp['assessment']}",
                "type": comp["signal_type"],
                "weight": 1,
            })

    # 营收增速相对行业基准
    rg = growth.get("RevenueGrowth_YoY")
    if rg is not None:
        if benchmark and benchmark.get("revenue_growth"):
            rg_bench = benchmark["revenue_growth"]
            comp = compare_to_benchmark(rg, rg_bench, "revenue_growth")
            signals.append({
                "name": f"营收YoY +{rg}% vs 行业均值+{rg_bench}%: {comp['assessment']}",
                "type": comp["signal_type"],
                "weight": 2 if abs(comp["ratio"] - 1) > 0.3 else 1,
            })
        else:
            # 无行业基准时用绝对值
            if rg > 30: signals.append({"name": f"营收YoY +{rg}%（高增长）", "type": "bullish", "weight": 3})
            elif rg > 15: signals.append({"name": f"营收YoY +{rg}%（稳健）", "type": "bullish", "weight": 2})
            elif rg < 0: signals.append({"name": f"营收YoY {rg}%（萎缩）", "type": "bearish", "weight": 3})

    # 盈利增速
    eg = growth.get("EarningsGrowth_YoY")
    if eg is not None:
        if eg > 50: signals.append({"name": f"盈利YoY +{eg}%（爆发）", "type": "bullish", "weight": 3})
        elif eg > 20: signals.append({"name": f"盈利YoY +{eg}%（强劲）", "type": "bullish", "weight": 2})
        elif eg < 0: signals.append({"name": f"盈利YoY {eg}%（下滑）", "type": "bearish", "weight": 3})

    # ROE 相对行业基准
    roe = prof.get("ROE")
    if roe is not None:
        if benchmark and benchmark.get("ROE"):
            roe_bench = benchmark["ROE"]
            comp = compare_to_benchmark(roe, roe_bench, "ROE")
            signals.append({
                "name": f"ROE={roe:.1f}% vs 行业均值{roe_bench}%: {comp['assessment']}",
                "type": comp["signal_type"],
                "weight": 1,
            })
        else:
            # 无行业基准时用绝对值
            if roe > 20: signals.append({"name": f"ROE={roe:.1f}%（优秀）", "type": "bullish", "weight": 2})
            elif roe < 5: signals.append({"name": f"ROE={roe:.1f}%（偏低）", "type": "bearish", "weight": 1})

    # 利润质量（扣非/归母）
    if quality_ratio is not None:
        if quality_ratio > 0.9: signals.append({"name": "扣非/归母>90%（利润质量高）", "type": "bullish", "weight": 1})
        elif quality_ratio < 0.5: signals.append({"name": f"扣非/归母={quality_ratio:.0%}（⚠️大量非经常性损益）", "type": "bearish", "weight": 2})

    if not signals:
        signals.append({"name": "基本面数据正常", "type": "neutral", "weight": 0})
    return signals


def _safe_float(val) -> float | None:
    if val is None: return None
    try: return float(val)
    except (ValueError, TypeError): return None


def _empty(reason: str) -> dict:
    return {
        "company_name": "", "sector": "N/A", "industry": "N/A",
        "valuation": {"PE": None, "ForwardPE": None, "PEG": None, "PS": None, "PB": None, "EV_EBITDA": None},
        "growth": {"RevenueGrowth_YoY": None, "EarningsGrowth_YoY": None, "EarningsGrowth_QoQ": None},
        "profitability": {"GrossMargin": None, "OperatingMargin": None, "NetMargin": None, "ROE": None, "FCF": None, "Revenue": None},
        "analyst": {"Recommendation": None, "AnalystCount": None, "TargetMean": None, "Upside": None},
        "signals": [{"name": f"🔧 基本面不可用: {reason}", "type": "neutral", "weight": 0}],
    }
