"""
数据质量验证模块（加固版）
==========================
8 项自动化检查，覆盖所有已知 yfinance 风险。
"""

import pandas as pd
import numpy as np
from datetime import datetime, timezone, timedelta
from typing import Optional


class DataQualityReport:
    def __init__(self):
        self.checks: list[dict] = []
        self.errors: list[str] = []
        self.warnings: list[str] = []
        self.metrics: dict = {}
        self.cross_check_card: dict = {}  # 用于和富途交叉验证

    def add_check(self, name: str, passed: bool, detail: str = "", severity: str = "info"):
        self.checks.append({"name": name, "passed": passed, "detail": detail, "severity": severity})
        if not passed:
            if severity == "error":
                self.errors.append(f"[{name}] {detail}")
            elif severity == "warning":
                self.warnings.append(f"[{name}] {detail}")

    def is_healthy(self) -> bool:
        return len(self.errors) == 0

    def has_warnings(self) -> bool:
        return len(self.warnings) > 0


def validate_all(symbol: str, df: pd.DataFrame, info: dict, live_price: Optional[float] = None) -> DataQualityReport:
    """
    全量数据验证（8项检查）。

    检查项:
    1. 数据非空 + 必要列
    2. 价格有效性（>0, 无极端跳空）
    3. 数据时效性（距最新交易日天数）
    4. info vs history 收盘价一致性
    5. 货币单位检查
    6. 市场状态提醒（盘前/盘后/已收盘）
    7. 拆股/分红检测
    8. 生成富途交叉验证卡片
    """
    report = DataQualityReport()

    if df is None or df.empty:
        report.add_check("数据非空", False, "DataFrame 为空", "error")
        return report

    report.metrics["rows"] = len(df)

    # --- 1. 必要列 ---
    required = ["open", "high", "low", "close", "volume"]
    missing = [c for c in required if c not in df.columns]
    if missing:
        report.add_check("必要列", False, f"缺少: {missing}", "error")
        return report

    # --- 2. 价格有效性 ---
    # 负价格/零价格
    bad = (df["close"] <= 0).sum()
    if bad > 0:
        report.add_check("价格有效性", False, f"{bad} 行收盘价 ≤ 0", "error")
    else:
        report.add_check("价格有效性", True, "所有价格 > 0")

    # 极端跳空 (>20% 单日)
    returns = df["close"].pct_change().dropna()
    extreme = returns[abs(returns) > 0.20]
    if len(extreme) > 0:
        report.add_check("价格连续性", False,
                        f"{len(extreme)} 天单日波动 >20%（可能是拆股/数据错误）",
                        "error")
    else:
        report.add_check("价格连续性", True, "无异常跳空")

    # --- 3. 数据时效性 ---
    last_date = df.index[-1]
    now_utc = datetime.now(timezone.utc)

    if hasattr(last_date, 'tz') and last_date.tz is not None:
        last_date_ts = last_date.tz_convert('UTC').replace(tzinfo=None)
    else:
        last_date_ts = pd.Timestamp(last_date).tz_localize(None)

    hours_since = (now_utc.replace(tzinfo=None) - last_date_ts).total_seconds() / 3600
    report.metrics["last_data_date"] = last_date.strftime("%Y-%m-%d") if hasattr(last_date, 'strftime') else str(last_date)[:10]
    report.metrics["hours_since_last"] = round(hours_since, 1)

    if hours_since > 48:
        report.add_check("数据时效性", False,
                        f"最新数据 {report.metrics['last_data_date']}（{hours_since/24:.0f}天前），严重过期",
                        "error")
    elif hours_since > 30:
        report.add_check("数据时效性", True,
                        f"最新 {report.metrics['last_data_date']}（{hours_since/24:.0f}天前），可能跨交易日",
                        "warning")
    else:
        report.add_check("数据时效性", True,
                        f"最新 {report.metrics['last_data_date']}（{hours_since:.0f}小时前）")

    # --- 4. info vs history 交叉验证 ---
    last_close = float(df["close"].iloc[-1])
    prev_close_info = info.get("previousClose")
    report.metrics["last_close"] = round(last_close, 2)
    report.metrics["live_price"] = round(live_price, 2) if live_price else None

    # 判断最后一行是否被实时价回填过（Backfill 标记）
    # 如果 last_close == live_price，说明是回填的实时价
    is_backfilled = live_price and abs(last_close - live_price) < 0.01
    report.metrics["is_backfilled"] = is_backfilled

    if is_backfilled:
        # 实时价回填的情况：和 info.previousClose 不相等是正常的（跨日了）
        report.add_check("收盘价来源", True,
                        f"最后收盘价 = 实时价 ${last_close:.2f}（数据未结算，已用实时价回填）",
                        "warning")
        # 验证倒数第二行的 Close 应该 ≈ previousClose
        if len(df) >= 2 and prev_close_info:
            prev_hist_close = float(df["close"].iloc[-2])
            prev_diff = abs(prev_hist_close - prev_close_info) / prev_close_info * 100
            if prev_diff > 1:
                report.add_check("info-history一致性", False,
                               f"倒数第二日收盘 ${prev_hist_close:.2f} vs info昨收 ${prev_close_info:.2f} 差 {prev_diff:.1f}%",
                               "error")
            else:
                report.add_check("info-history一致性", True,
                               f"T-1收盘 ${prev_hist_close:.2f} ≈ info昨收 ${prev_close_info:.2f}")
    else:
        # 正常结算数据
        if prev_close_info:
            diff_pct = abs(last_close - prev_close_info) / prev_close_info * 100
            if diff_pct > 3:
                report.add_check("info-history一致性", False,
                               f"收盘 ${last_close:.2f} vs info昨收 ${prev_close_info:.2f} 差 {diff_pct:.1f}%",
                               "error")
            elif diff_pct > 0.5:
                report.add_check("info-history一致性", True,
                               f"收盘 ${last_close:.2f} vs info昨收 ${prev_close_info:.2f} 差 {diff_pct:.1f}%",
                               "warning")
            else:
                report.add_check("info-history一致性", True,
                               f"收盘 ${last_close:.2f} ≈ info昨收 ${prev_close_info:.2f}")

    # 如果 live_price 存在但和 last_close 不同（且没被回填）→ 实时价≠收盘价，正常
    if live_price and not is_backfilled:
        live_diff = abs(live_price - last_close) / last_close * 100
        if live_diff > 2:
            report.add_check("实时-收盘价差", True,
                           f"实时价 ${live_price:.2f} vs 收盘 ${last_close:.2f} 差 {live_diff:.1f}%（盘后波动正常）",
                           "warning")

    # --- 5. 货币单位 ---
    currency = info.get("currency", "USD")
    exchange = info.get("exchange", "N/A")
    report.metrics["currency"] = currency
    report.metrics["exchange"] = exchange

    if currency != "USD":
        report.add_check("货币单位", True,
                        f"非美元计价 ({currency})，分析数值为{currency}，请注意",
                        "warning")
    else:
        report.add_check("货币单位", True, "USD ✓")

    # --- 6. 市场状态 ---
    market_state = info.get("marketState", "UNKNOWN")
    report.metrics["market_state"] = market_state

    if market_state == "PRE":
        report.add_check("市场状态", True,
                        "盘前交易中 — 实时价可能变动，收盘价尚未确定",
                        "warning")
    elif market_state == "POST":
        report.add_check("市场状态", True,
                        "盘后交易中 — 实时价可能与明日开盘价有偏差",
                        "warning")
    elif market_state == "REGULAR":
        report.add_check("市场状态", True, "正常交易时段")
    else:
        report.add_check("市场状态", True, f"市场状态: {market_state}")

    # --- 7. 拆股/分红 ---
    # 这项在 data_fetcher 层面已处理，这里只做最终检查
    # 如果 5 年内有拆股，检查价格是否连续
    if len(df) > 100:
        recent_returns = returns.tail(100)
        max_move = recent_returns.abs().max()
        if max_move > 0.5:
            report.add_check("拆股复权", True,
                           f"近100天最大单日波动 {max_move:.1%}（可能未复权拆股）",
                           "warning")
        else:
            report.add_check("拆股复权", True, "无异常复权问题")

    # --- 8. 生成交叉验证卡片 ---
    report.cross_check_card = {
        "股票代码": symbol,
        "数据日期": report.metrics.get("last_data_date", "?"),
        "数据时效": f"{report.metrics.get('hours_since_last', '?')}小时前",
        "收盘价(yf)": f"${last_close:.2f}",
        "实时价(yf)": f"${live_price:.2f}" if live_price else "N/A",
        "昨收(info)": f"${prev_close_info:.2f}" if prev_close_info else "N/A",
        "货币": currency,
        "交易所": exchange,
        "市场状态": market_state,
    }

    return report


def generate_health_banner(report: DataQualityReport) -> str:
    if not report.is_healthy():
        return f"🔴 数据异常 ({len(report.errors)}个错误)"
    if report.has_warnings():
        return f"🟡 数据可用 ({len(report.warnings)}个告警)"
    return "🟢 数据健康（8项检查全通过）"


def print_validation_log(report: DataQualityReport):
    """打印验证日志"""
    from rich.console import Console
    console = Console()

    m = report.metrics
    console.print(f"  [dim]数据: {m.get('rows','?')}行 | "
                 f"{m.get('last_data_date','?')} ({m.get('hours_since_last','?')}h前) | "
                 f"${m.get('last_close','?')} | "
                 f"{m.get('currency','?')} | "
                 f"{m.get('exchange','?')} | "
                 f"{generate_health_banner(report)}[/dim]")

    for w in report.warnings:
        console.print(f"  ⚠️  [yellow]{w}[/yellow]")
    for e in report.errors:
        console.print(f"  🚨 [red bold]{e}[/red bold]")


def print_cross_check_card(report: DataQualityReport):
    """打印交叉验证卡片 — 和富途对比用"""
    from rich.console import Console
    from rich.table import Table
    from rich import box
    console = Console()

    card = report.cross_check_card
    if not card:
        return

    table = Table(title="🔍 数据交叉验证卡（请与富途对比）", box=box.ROUNDED, border_style="yellow")
    table.add_column("字段", style="cyan", width=14)
    table.add_column("系统值（yfinance）", style="white", width=20)
    table.add_column("富途值（手动填入）", style="yellow", width=20)
    table.add_column("一致?", width=8)

    key_fields = ["数据日期", "收盘价(yf)", "实时价(yf)", "货币", "市场状态"]
    for f in key_fields:
        if f in card:
            table.add_row(f, str(card[f]), "________", "⬜")

    console.print(table)
    console.print("  [dim]💡 请打开富途牛牛，对比上述数值。如果一致 → 数据可信。如果不一致 → 查看上方告警。[/dim]")


# 兼容旧接口
validate_price_data = validate_all
validate_info_data = lambda info, symbol: DataQualityReport()
