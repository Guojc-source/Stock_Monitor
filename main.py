#!/opt/homebrew/bin/python3.12
"""
股票多维分析系统 — 主入口
===========================

维度覆盖：
  1. 技术面 — MA/BOLL/RSI/MACD/KDJ/量价/K线形态
  2. 基本面 — 估值/增长/盈利/分析师评级
  3. 新闻情绪 — 财经新闻关键词分析（yfinance + Google News fallback）
  4. 期权资金 — P/C比率/异常大单/最大痛点（自动过滤无效数据）
  5. 市场背景 — 大盘/行业对标（根据GICS自动选ETF）
  6. 关键价位 — 支撑位/阻力位/斐波那契/场景推演
  7. 🆕 历史估值 — PE分位/价格分位/PE Band
  8. 🆕 数据验证 — 全链路质量检查 + 肉眼交叉验证日志

用法:
    python3.12 main.py                     # 分析 config.py 中全部股票
    python3.12 main.py -s MSFT             # 单只股票
    python3.12 main.py -s ADBE MSFT CRM    # 多只股票
    python3.12 main.py -s MSFT --json      # JSON 输出
    python3.12 main.py -s MSFT --interval 60   # 每60分钟刷新
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
from market_context import get_market_context
from levels import find_support_resistance
from valuation_history import get_historical_valuation
from data_validator import validate_all, print_validation_log, print_cross_check_card, DataQualityReport, generate_health_banner
from analyzer import full_analysis
from report import generate_report, generate_summary_table, console


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
        try:
            ticker_info = yf.Ticker(symbol).info or {}
        except Exception:
            pass

    quality_report = validate_all(symbol, df, ticker_info, live_price)

    if verbose:
        print_validation_log(quality_report)
        print_cross_check_card(quality_report)
        console.print(f"  [dim]市场状态: {market_state} | 实时价: ${live_price or 'N/A'}[/dim]")

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
            sentiment_data = get_news_sentiment(symbol)
        except Exception as e:
            sentiment_data = {"signals": [{"name": f"新闻数据获取失败: {e}", "type": "neutral", "weight": 0}]}

        # ===== 7. 期权分析 =====
        try:
            options_data = get_options_analysis(symbol)
        except Exception as e:
            options_data = {"available": False, "signals": [{"name": f"期权数据获取失败: {e}", "type": "neutral", "weight": 0}]}

        # ===== 8. 市场背景 =====
        try:
            context_data = get_market_context(symbol)
        except Exception as e:
            context_data = {"signals": [{"name": f"市场背景获取失败: {e}", "type": "neutral", "weight": 0}]}

        # ===== 10. 历史估值分位 =====
        try:
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

    return analysis


def run(symbols: list[str], verbose: bool = True, json_output: bool = False, use_local: bool = False) -> dict:
    """批量运行"""
    results = {}

    if verbose and not json_output:
        source = "本地测试模式" if use_local else "Yahoo Finance"
        console.print(f"\n[bold cyan]╔══════════════════════════════════════════════════════════╗[/bold cyan]")
        console.print(f"[bold cyan]║[/bold cyan]   📊 美股多维分析系统  |  标的: {', '.join(symbols):<30s} [bold cyan]║[/bold cyan]")
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


def main():
    parser = argparse.ArgumentParser(
        description="美股多维分析系统 — 六维度覆盖",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python3.12 main.py                      # 分析全部配置股票
  python3.12 main.py -s MSFT              # 单只深度分析
  python3.12 main.py -s ADBE MSFT --json  # JSON 输出
  python3.12 main.py -s MSFT --interval 60 # 每小时刷新
        """,
    )
    parser.add_argument("-s", "--symbols", nargs="+", help="股票代码")
    parser.add_argument("-i", "--interval", type=int, default=0, help="定时间隔（分钟）")
    parser.add_argument("--json", action="store_true", help="JSON 输出")
    parser.add_argument("--no-fundamentals", action="store_true", help="跳过基本面")
    parser.add_argument("--no-options", action="store_true", help="跳过期权分析")
    parser.add_argument("--local", action="store_true", help="使用本地测试数据（不联网）")

    args = parser.parse_args()
    symbols = args.symbols if args.symbols else SYMBOLS

    verbose = not args.json
    if args.interval > 0:
        if verbose:
            console.print(f"[dim]⏰ 定时模式：每 {args.interval} 分钟刷新一次，Ctrl+C 退出[/dim]")
        while True:
            try:
                run(symbols, verbose=verbose, json_output=args.json, use_local=args.local)
                if verbose:
                    console.print(f"\n[dim]⏰ 下次刷新: {args.interval} 分钟后[/dim]")
                time.sleep(args.interval * 60)
            except KeyboardInterrupt:
                if verbose:
                    console.print("\n[yellow]👋 已退出[/yellow]")
                break
    else:
        run(symbols, verbose=verbose, json_output=args.json, use_local=args.local)


if __name__ == "__main__":
    main()
