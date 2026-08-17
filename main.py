#!/opt/homebrew/bin/python3.12
"""
股票多维分析系统 — 主入口
===========================

维度覆盖：
  1.  技术指标 — MA / BOLL / RSI / MACD / KDJ / 量价 / K线形态
  2.  基本面   — 估值 / 增长 / 盈利 / 分析师评级
  3.  新闻情绪 — 财经新闻关键词分析
  4.  期权资金 — P/C 比率 / 异常大单 / 最大痛点
  5.  市场背景 — 大盘 / 行业对标（GICS 自动匹配 ETF）
  6.  关键价位 — 支撑 / 阻力 / Fibonacci / 场景推演
  7.  历史估值 — PE 分位 / 价格分位 / PE Band
  8.  数据验证 — 全链路质量检查 + 交叉验证
  9.  行业轮动 — 11 个 SPDR 行业 ETF 多周期动量排名 + 资金流向判定
  10. 大盘状态 — SPY/QQQ MA50/MA200 交叉信号 + 仓位建议
  11. 自选股配置 — JSON/TXT 外部文件 + 中英文名称自动解析

Usage:
    python3.12 main.py                         # analyze all stocks in watchlist.json
    python3.12 main.py -s MSFT                 # single stock
    python3.12 main.py -s ADBE MSFT CRM        # multiple stocks
    python3.12 main.py -s MSFT --json          # JSON output
    python3.12 main.py -s MSFT --interval 60   # refresh every 60 min
    python3.12 main.py --sector                # sector rotation ranking
    python3.12 main.py --market-status         # market regime indicator
    python3.12 main.py --watchlist mylist.json # custom watchlist file
    python3.12 main.py --init-watchlist        # generate example watchlist.json
"""

import argparse
import json
import time
from datetime import datetime

from config import SYMBOLS
import yfinance as yf
from data_fetcher import fetch_all_data, fetch_stock_data, get_live_info
from multi_fetcher import fetch_stock_data_multi, detect_market
from local_data import load_local_data
from indicators import calc_all_indicators
from patterns import detect_all_patterns
from signals import detect_all_signals as detect_technical_signals
from fundamentals import get_fundamental_data
from fundamentals_cn import get_fundamental_data_cn
from sentiment import get_news_sentiment
from options_flow import get_options_analysis
from market_context import get_market_context, get_market_context_cn_hk
from levels import find_support_resistance
from valuation_history import get_historical_valuation, get_historical_valuation_cn_hk
from data_validator import validate_all, print_validation_log, print_cross_check_card, DataQualityReport, generate_health_banner
from analyzer import full_analysis
from report import (
    generate_report, generate_summary_table, console,
    print_sector_rotation_report, print_market_status_report, print_watchlist_header,
)
from watchlist_loader import load_watchlist, get_watchlist_source_info, create_example_watchlist
from sector_rotation import get_sector_rotation
from market_status import get_market_status


def analyze_symbol(symbol: str, verbose: bool = True, use_local: bool = False) -> dict:
    """
    分析单只股票 — 八维全量分析 + 数据验证。
    """
    # ===== 0. 判断市场 & 选择数据源 =====
    market = detect_market(symbol)

    if use_local:
        df = load_local_data(symbol)
        live_info = {"symbol": symbol, "market_state": "LOCAL",
                     "live_price": float(df["close"].iloc[-1]),
                     "previous_close": float(df["close"].iloc[-2]) if len(df) > 1 else None,
                     "exchange": "LOCAL", "currency": "USD"}
        live_price = live_info["live_price"]
        market_state = "LOCAL"
        source = "本地"
    else:
        # 实时信息：美股用 yfinance，A股/港股用 akshare
        source = {"us": "Yahoo Finance", "cn": "akshare(东方财富)", "hk": "akshare(新浪)"}.get(market, "?")

        if market == "us":
            live_info = get_live_info(symbol)  # yfinance
        else:
            # A股/港股：从 akshare 取最新价
            live_info = {"symbol": symbol, "market_state": "?", "live_price": None,
                         "previous_close": None, "exchange": market, "currency": "CNY" if market == "cn" else "HKD"}

        live_price = live_info.get("live_price")
        market_state = live_info.get("market_state", "?")

        try:
            df = fetch_stock_data_multi(symbol)
            if market != "us" and not df.empty:
                live_info["live_price"] = float(df["close"].iloc[-1])
                live_info["market_state"] = "REGULAR"
                live_price = live_info["live_price"]
                market_state = "REGULAR"
        except Exception as e:
            raise ValueError(f"无法获取 {symbol} 的数据（{market}市场）: {e}")

    # ===== 2. 计算技术指标 + K线形态识别 =====
    df = calc_all_indicators(df)
    df = detect_all_patterns(df)

    if verbose:
        console.print(f"\n[dim]⏳ 正在分析 {symbol}…（数据源: {source} | {market}市场）[/dim]")

    # ===== 1.5 数据质量验证（8项检查 + 交叉验证卡）=====
    ticker_info = {}
    if not use_local:
        if market == "us":
            try:
                ticker_info = yf.Ticker(symbol).info or {}
            except Exception:
                pass
        # CN/HK: skip yfinance ticker_info (unsupported suffixes)

    quality_report = validate_all(symbol, df, ticker_info, live_price)

    if verbose:
        print_validation_log(quality_report)
        print_cross_check_card(quality_report)
        _cur = "¥" if market == "cn" else ("HK$" if market == "hk" else "$")
        console.print(f"  [dim]市场状态: {market_state} | 实时价: {_cur}{live_price or 'N/A'}[/dim]")

    # ===== 4. 技术面信号 =====
    tech_signals = detect_technical_signals(df)

    # ===== 5-N. 外部数据模块（本地模式下跳过 yfinance 依赖）=====
    if use_local:
        fundamental_data = {"signals": [{"name": "🔧 本地模式：跳过基本面（需联网）", "type": "neutral", "weight": 0}]}
        sentiment_data = {"signals": [{"name": "🔧 本地模式：跳过新闻（需联网）", "type": "neutral", "weight": 0}]}
        options_data = {"available": False, "signals": [{"name": "🔧 本地模式：跳过期权（需联网）", "type": "neutral", "weight": 0}]}
        context_data = {"signals": [{"name": "🔧 本地模式：跳过市场背景（需联网）", "type": "neutral", "weight": 0}]}
        valuation_data = {"signals": [{"name": "🔧 本地模式：跳过历史估值（需联网）", "type": "neutral", "weight": 0}]}
    else:
        # ===== 5. 基本面分析 =====
        try:
            # 根据市场选择基本面数据源
            if market in ("cn", "hk"):
                fundamental_data = get_fundamental_data_cn(symbol, market)
            else:
                fundamental_data = get_fundamental_data(symbol)
        except Exception as e:
            fundamental_data = {"signals": [{"name": f"基本面数据获取失败: {e}", "type": "neutral", "weight": 0}]}

        # ===== 6. 新闻情绪 =====
        try:
            if market in ("cn", "hk"):
                sentiment_data = {"signals": [{"name": "🔧 新闻情绪: A股/港股暂不支持自动新闻分析", "type": "neutral", "weight": 0}], "articles": [], "overall_sentiment": "neutral", "sentiment_score": 0, "source": "N/A"}
            else:
                sentiment_data = get_news_sentiment(symbol)
        except Exception as e:
            sentiment_data = {"signals": [{"name": f"新闻数据获取失败: {e}", "type": "neutral", "weight": 0}]}

        # ===== 7. 期权分析 =====
        try:
            if market in ("cn", "hk"):
                options_data = {"available": False, "signals": [{"name": "🔧 期权分析: A股/港股无期权数据", "type": "neutral", "weight": 0}]}
            else:
                options_data = get_options_analysis(symbol)
        except Exception as e:
            options_data = {"available": False, "signals": [{"name": f"期权数据获取失败: {e}", "type": "neutral", "weight": 0}]}

        # ===== 8. 市场背景 =====
        try:
            if market in ("cn", "hk"):
                context_data = get_market_context_cn_hk(symbol, market)
            else:
                context_data = get_market_context(symbol)
        except Exception as e:
            context_data = {"signals": [{"name": f"市场背景获取失败: {e}", "type": "neutral", "weight": 0}]}

        # ===== 10. 历史估值分位 =====
        try:
            if market in ("cn", "hk"):
                valuation_data = get_historical_valuation_cn_hk(symbol, market, df)
            else:
                valuation_data = get_historical_valuation(symbol)
        except Exception as e:
            valuation_data = {"signals": [{"name": f"历史估值数据获取失败: {e}", "type": "neutral", "weight": 0}]}

    # ===== 9. 关键价位（本地模式也可用）=====
    try:
        levels_data = find_support_resistance(df, options_data)
    except Exception as e:
        levels_data = None

    # ===== 11. 综合评分 =====
    analysis = full_analysis(
        symbol=symbol,
        df=df,
        fundamental_data=fundamental_data,
        sentiment_data=sentiment_data,
        options_data=options_data,
        context_data=context_data,
        levels_data=levels_data,
        valuation_data=valuation_data,
        technical_signals=tech_signals,
    )

    # 附加验证和历史估值数据
    analysis["quality_report"] = quality_report
    analysis["live_info"] = live_info
    analysis["valuation_data"] = valuation_data
    analysis["market"] = market

    return analysis


def run(symbols: list[str], verbose: bool = True, json_output: bool = False, use_local: bool = False) -> dict:
    """批量运行"""
    results = {}

    if verbose and not json_output:
        if use_local:
            source = "本地测试模式"
        else:
            markets = set(detect_market(s) for s in symbols)
            src_map = {"us": "Yahoo Finance", "cn": "akshare(东方财富)", "hk": "akshare(新浪)"}
            source = " / ".join(src_map.get(m, "?") for m in sorted(markets))
        console.print(f"\n[bold cyan]╔══════════════════════════════════════════════════════════╗[/bold cyan]")
        console.print(f"[bold cyan]║[/bold cyan]   📊 股票多维分析系统  |  标的: {', '.join(symbols):<30s} [bold cyan]║[/bold cyan]")
        console.print(f"[bold cyan]║[/bold cyan]   数据源: {source:<44s} [bold cyan]║[/bold cyan]")
        console.print(f"[bold cyan]╚══════════════════════════════════════════════════════════╝[/bold cyan]")

    for symbol in symbols:
        try:
            analysis = analyze_symbol(symbol, verbose=verbose, use_local=use_local)
            results[symbol] = analysis
        except Exception as e:
            if verbose:
                console.print(f"[red]✗ {symbol}: {e}[/red]")
            results[symbol] = {"error": str(e), "symbol": symbol}

    if json_output:
        print(json.dumps(_to_json(results), indent=2, ensure_ascii=False))
    else:
        for symbol, analysis in results.items():
            if "error" in analysis:
                console.print(f"[red]{symbol}: {analysis['error']}[/red]")
                continue
            generate_report(analysis)

        valid = {s: a for s, a in results.items() if "error" not in a}
        if len(valid) > 1:
            generate_summary_table(valid)

    return results


def _to_json(results: dict) -> dict:
    """转 JSON"""
    out = {}
    for sym, a in results.items():
        if "error" in a:
            out[sym] = {"error": a["error"]}
            continue
        out[sym] = {
            "price": a["snapshot"]["price"],
            "score": a["score"],
            "recommendation": a["recommendation"][1],
            "trend": a["trend"],
            "snapshot": a["snapshot"],
            "bearish_signals": [s["name"] for s in a.get("bearish_signals", [])],
            "bullish_signals": [s["name"] for s in a.get("bullish_signals", [])],
            "levels": {
                "supports": a.get("levels_data", {}).get("supports", []) if a.get("levels_data") else [],
                "resistances": a.get("levels_data", {}).get("resistances", []) if a.get("levels_data") else [],
                "scenarios": a.get("levels_data", {}).get("break_scenarios", []) if a.get("levels_data") else [],
            } if a.get("levels_data") else None,
        }
    return out


def run_sector_rotation(verbose: bool = True, json_output: bool = False):
    """运行行业轮动排名分析"""
    result = get_sector_rotation(verbose=verbose)

    if json_output:
        # JSON 模式：简化输出
        out = {
            "timestamp": result["timestamp"],
            "flow": result["flow"],
            "flow_description": result["flow_description"],
            "rankings_20d": result["rankings"].get("20d", []),
            "leaders": [{"symbol": l["symbol"], "name": l["name"], "change_20d": l["change_20d"]} for l in result["leaders"]],
            "laggards": [{"symbol": l["symbol"], "name": l["name"], "change_20d": l["change_20d"]} for l in result["laggards"]],
            "sectors": [{k: v for k, v in s.items()} for s in result["sectors"]],
        }
        print(json.dumps(out, indent=2, ensure_ascii=False))
    else:
        print_sector_rotation_report(result)

    return result


def run_market_status(verbose: bool = True, json_output: bool = False):
    """运行大盘状态灯分析"""
    status = get_market_status(verbose=verbose)

    if json_output:
        print(json.dumps(status, indent=2, ensure_ascii=False, default=str))
    else:
        print_market_status_report(status)

    return status


def main():
    parser = argparse.ArgumentParser(
        description="股票多维分析系统 — 十维度覆盖",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python3.12 main.py                         # 分析 watchlist.json 中全部股票
  python3.12 main.py -s MSFT                 # 单只深度分析
  python3.12 main.py -s ADBE MSFT --json     # JSON 输出
  python3.12 main.py -s MSFT --interval 60   # 每小时刷新
  python3.12 main.py --sector                # 行业轮动排名
  python3.12 main.py --market-status         # 大盘状态灯
  python3.12 main.py --watchlist mylist.json # 指定自选股文件
  python3.12 main.py --init-watchlist        # 生成示例 watchlist.json
  python3.12 main.py --all                   # 全部跑一遍（大盘+行业+个股）
        """,
    )
    # === 个股分析 ===
    parser.add_argument("-s", "--symbols", nargs="+", help="股票代码")
    parser.add_argument("-i", "--interval", type=int, default=0, help="定时间隔（分钟）")
    parser.add_argument("--json", action="store_true", help="JSON 输出")
    parser.add_argument("--no-fundamentals", action="store_true", help="跳过基本面")
    parser.add_argument("--no-options", action="store_true", help="跳过期权分析")
    parser.add_argument("--local", action="store_true", help="使用本地测试数据（不联网）")

    # Watchlist configuration
    parser.add_argument("--watchlist", type=str, default=None,
                        help="指定自选股配置文件路径（.json 或 .txt）")
    parser.add_argument("--init-watchlist", action="store_true",
                        help="生成示例 watchlist.json 文件")

    # Sector rotation analysis
    parser.add_argument("--sector", action="store_true",
                        help="运行行业轮动排名分析")

    # Market regime indicator
    parser.add_argument("--market-status", action="store_true",
                        help="运行大盘状态灯分析")

    # Full analysis: market + sector + individual stocks
    parser.add_argument("--all", action="store_true",
                        help="全部运行：大盘状态 + 行业轮动 + 个股分析")

    args = parser.parse_args()

    # === 处理 --init-watchlist ===
    if args.init_watchlist:
        path = create_example_watchlist()
        console.print(f"\n[green]✅ 已生成示例配置文件: {path}[/green]")
        console.print(f"[dim]   编辑该文件添加/删除股票，然后运行 python3.12 main.py[/dim]\n")
        return

    # === 确定股票列表 ===
    if args.symbols:
        symbols = args.symbols
        watchlist_file = None
    elif args.watchlist:
        symbols = load_watchlist(args.watchlist)
        watchlist_file = args.watchlist
    else:
        symbols = load_watchlist()  # 自动搜索 watchlist.json → .txt → config.SYMBOLS
        watchlist_file = None

    # Ticker alias resolution for -s arguments
    if args.symbols:
        from ticker_alias import resolve_symbols
        verbose_pre = not args.json
        symbols, _mapping = resolve_symbols(symbols, verbose=verbose_pre)

    verbose = not args.json

    # === 显示 watchlist 来源 ===
    if verbose and not args.sector and not args.market_status:
        source_info = get_watchlist_source_info(watchlist_file)
        print_watchlist_header(source_info)

    # === 处理 --sector ===
    if args.sector:
        run_sector_rotation(verbose=verbose, json_output=args.json)
        return

    # === 处理 --market-status ===
    if args.market_status:
        run_market_status(verbose=verbose, json_output=args.json)
        return

    # === 处理 --all（大盘 + 行业 + 个股）===
    if args.all:
        if verbose:
            console.print(f"\n[bold cyan]{'═'*60}[/bold cyan]")
            console.print(f"[bold cyan]  🚀 全量分析模式：大盘状态 → 行业轮动 → 个股分析[/bold cyan]")
            console.print(f"[bold cyan]{'═'*60}[/bold cyan]")

        # Step 1: 大盘状态
        if verbose:
            console.print(f"\n[bold]━━━ Step 1/3: 大盘状态灯 ━━━[/bold]")
        status = run_market_status(verbose=verbose, json_output=args.json)

        # Step 2: 行业轮动
        if verbose:
            console.print(f"\n[bold]━━━ Step 2/3: 行业轮动排名 ━━━[/bold]")
        rotation = run_sector_rotation(verbose=verbose, json_output=args.json)

        # Step 3: 个股分析（排除 ETF 代码，只分析个股）
        if verbose:
            console.print(f"\n[bold]━━━ Step 3/3: 个股分析 ━━━[/bold]")

        # 过滤掉 ETF 代码（SPY/QQQ/IWM/XLK 等），只保留个股
        etf_codes = {
            "SPY", "QQQ", "IWM", "DIA",
            "XLK", "XLF", "XLE", "XLV", "XLY", "XLP", "XLI", "XLB", "XLRE", "XLU", "XLC",
            "IGV", "SOXX", "ARKK",
        }
        individual_symbols = [s for s in symbols if s.upper() not in etf_codes]

        if individual_symbols:
            if args.interval > 0:
                _run_interval(individual_symbols, args.interval, verbose, args.json, args.local)
            else:
                run(individual_symbols, verbose=verbose, json_output=args.json, use_local=args.local)
        else:
            if verbose:
                console.print("[yellow]⚠️ watchlist 中没有个股代码，跳过个股分析[/yellow]")

        return

    # === 默认模式：个股分析 ===
    if args.interval > 0:
        _run_interval(symbols, args.interval, verbose, args.json, args.local)
    else:
        run(symbols, verbose=verbose, json_output=args.json, use_local=args.local)


def _run_interval(symbols: list[str], interval: int, verbose: bool, json_output: bool, use_local: bool):
    """定时刷新模式"""
    if verbose:
        console.print(f"[dim]⏰ 定时模式：每 {interval} 分钟刷新一次，Ctrl+C 退出[/dim]")
    while True:
        try:
            run(symbols, verbose=verbose, json_output=json_output, use_local=use_local)
            if verbose:
                console.print(f"\n[dim]⏰ 下次刷新: {interval} 分钟后[/dim]")
            time.sleep(interval * 60)
        except KeyboardInterrupt:
            if verbose:
                console.print("\n[yellow]👋 已退出[/yellow]")
            break


if __name__ == "__main__":
    main()
