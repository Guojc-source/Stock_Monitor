"""
综合报告输出模块
=================
仿富途牛牛的多维分区报告：热点事件、交易情况、财报分析、技术指标、关键价位。
"""

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.text import Text
from rich import box
from rich.columns import Columns
from datetime import datetime

console = Console()


def _score_color(score: int) -> str:
    if score >= 80: return "bright_green"
    elif score >= 60: return "green"
    elif score >= 40: return "yellow"
    elif score >= 20: return "red"
    return "bright_red"


def _score_bar(score: int) -> str:
    filled = score // 5
    empty = 20 - filled
    return f"[{_score_color(score)}]{'█' * filled}{'░' * empty}[/{_score_color(score)}]"


def _sig_type_icon(t: str) -> str:
    return {"bullish": "🟢", "bearish": "🔴", "neutral": "🟡"}.get(t, "⚪")


def _sig_type_color(t: str) -> str:
    return {"bullish": "green", "bearish": "red", "neutral": "yellow"}.get(t, "white")


# ═══════════════════════════════════════════════════════════════
#  主报告入口
# ═══════════════════════════════════════════════════════════════

def generate_report(analysis: dict):
    """生成完整的六维分析报告"""
    symbol = analysis["symbol"]

    # 大标题
    _print_banner(symbol, analysis)

    # 0. 数据交叉验证卡（跑完立刻可以跟富途对比）
    qr = analysis.get("quality_report")
    if qr and qr.cross_check_card:
        _print_cross_check_card(qr)

    # 1. 综合评分 + 建议（最重要）
    _print_verdict(analysis)

    # 1.5 数据完整度一览
    _print_data_completeness(analysis)

    # 2. 关键价位（支撑/阻力/场景）
    _print_key_levels(analysis.get("levels_data"))

    # 3. 热点事件（新闻情绪）
    _print_news_section(analysis.get("sentiment_data"))

    # 4. 技术指标快照
    _print_technical_snapshot(analysis["snapshot"])

    # 5. 基本面（估值/增长/盈利/分析师）
    _print_fundamental_section(analysis.get("fundamental_data"))

    # 6. 期权资金
    _print_options_section(analysis.get("options_data"))

    # 7. 市场背景
    _print_market_context(analysis.get("context_data"))

    # 7.5 历史估值分位
    _print_valuation_history(analysis.get("valuation_data"))

    # 8. 多空信号汇总
    _print_signals_by_dimension(analysis.get("signals_by_dimension", {}))

    # 9. 信号冲突警告
    _print_conflicts(analysis.get("conflicts", []))

    # 10. 风险提示
    _print_risk_warning(analysis)

    # 11. 手工核验清单
    _print_verification_checklist(analysis)

    _print_footer()


def generate_summary_table(results: dict[str, dict]):
    """持仓汇总对比"""
    table = Table(title="\n📊 持仓汇总对比", box=box.ROUNDED, border_style="cyan")
    table.add_column("代码", style="bold cyan", width=8)
    table.add_column("价格", width=10)
    table.add_column("5日", width=8)
    table.add_column("评分", width=7)
    table.add_column("趋势", width=10)
    table.add_column("建议", width=20)
    table.add_column("关键信号", width=35)

    for sym, a in results.items():
        s = a["snapshot"]
        score = a["score"]

        high_sigs = [sig for sig in a.get("all_signals", []) if sig["weight"] >= 3]
        key = high_sigs[0]["name"] if high_sigs else "—"

        table.add_row(
            sym,
            f"${s['price']}" if s.get("price") else "N/A",
            f"{s.get('change_5d', 0):+.1f}%" if s.get("change_5d") else "—",
            f"[{_score_color(score)} bold]{score}[/{_score_color(score)} bold]",
            a["trend"]["direction"],
            a["recommendation"][1],
            key[:32] + ("…" if len(key) > 32 else ""),
        )

    console.print(table)


# ═══════════════════════════════════════════════════════════════
#  各分区
# ═══════════════════════════════════════════════════════════════

def _print_banner(symbol: str, analysis: dict):
    name = (analysis.get("fundamental_data") or {}).get("company_name", symbol)
    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    # 数据健康横幅
    qr = analysis.get("quality_report")
    from data_validator import generate_health_banner
    health = generate_health_banner(qr) if qr else "⚪ 未验证"

    live_info = analysis.get("live_info", {})
    market_state = live_info.get("market_state", "?")
    live_price = live_info.get("live_price")

    text = Text()
    text.append("╔", style="bold cyan")
    text.append("═" * 68, style="bold cyan")
    text.append("╗\n", style="bold cyan")
    text.append(f"║  📊 {name} ({symbol})", style="bold white")
    text.append(f"   {now}", style="dim")
    text.append(" " * max(1, 38 - len(name) - len(symbol)), style="")
    text.append("║\n", style="bold cyan")

    # 数据质量行
    health_color = "green" if "健康" in health else "yellow" if "可用" in health else "red"
    text.append(f"║  [{health_color}]{health}[/{health_color}]", style="")
    text.append(f" | 市场: {market_state}", style="dim")
    if live_price:
        text.append(f" | 实时: ${live_price:.2f}", style="dim")
    text.append(" " * max(1, 20 - len(health)), style="")
    text.append("║\n", style="bold cyan")

    text.append("╚", style="bold cyan")
    text.append("═" * 68, style="bold cyan")
    text.append("╝", style="bold cyan")
    console.print(text)


def _print_verdict(analysis: dict):
    s = analysis["score"]
    level, label, color = analysis["recommendation"]
    trend = analysis["trend"]
    conflicts = analysis.get("conflicts", [])

    # 评分线
    content = f"\n  {_score_bar(s)}\n\n"
    content += f"  综合评分: [{_score_color(s)} bold]{s}/100[/{_score_color(s)} bold]\n"

    # 如果有信号冲突，显示原始评分和调整说明
    if conflicts:
        raw = analysis.get("raw_score", s)
        content += f"  [dim]（原始评分: {raw}/100，因多空冲突向中性调整）[/dim]\n"

    # 如果被趋势上限锁定
    if analysis.get("trend_capped"):
        content += f"  [dim]（{analysis.get('trend_cap_reason', '趋势下跌，评分受限')}）[/dim]\n"

    content += f"  操作建议: [{color} bold]{label}[/{color} bold]\n"
    content += f"  趋势状态: [{color}]{trend['direction']}（{trend['strength']}度趋势）[/{color}]\n"
    # 展示趋势判断依据
    if trend.get("details"):
        for d in trend["details"][:3]:
            content += f"    [dim]↳ {d}[/dim]\n"

    panel = Panel(
        content,
        title="🎯 综合判断",
        border_style=color,
        padding=(0, 3),
    )
    console.print(panel)


def _print_key_levels(levels_data: dict):
    """打印关键价位——用户最关心的支撑位/阻力位/目标位"""
    if not levels_data:
        return

    current = levels_data.get("current_price", 0)
    supports = levels_data.get("supports", [])[:3]
    resistances = levels_data.get("resistances", [])[:3]
    scenarios = levels_data.get("break_scenarios", [])
    rr = levels_data.get("risk_reward", {})

    # 价位表格
    table = Table(title="📍 关键价位分析", box=box.ROUNDED, border_style="magenta")
    table.add_column("类型", width=8, style="bold")
    table.add_column("价位", width=12)
    table.add_column("来源", width=28)
    table.add_column("强度", width=8)

    # 当前价
    table.add_row("💰 现价", f"[bold white]${current:.2f}[/bold white]", "—", "—")

    # 阻力位（从近到远）
    for i, r in enumerate(resistances):
        dist = (r["price"] - current) / current * 100
        icon = "🔴" if i == 0 else "⬆️"
        table.add_row(
            f"{icon} 阻力{i+1}",
            f"[red]${r['price']:.2f}[/red] (+{dist:.1f}%)",
            r["method"],
            r["strength"],
        )

    # 支撑位（从近到远）
    for i, s in enumerate(supports):
        dist = (current - s["price"]) / current * 100
        icon = "🟢" if i == 0 else "⬇️"
        table.add_row(
            f"{icon} 支撑{i+1}",
            f"[green]${s['price']:.2f}[/green] (-{dist:.1f}%)",
            s["method"],
            s["strength"],
        )

    console.print(table)

    # 场景推演
    if scenarios:
        for sc in scenarios:
            icon = "📈" if "上涨" in sc["direction"] else "📉"
            console.print(f"  {icon} [bold]{sc['direction']}场景[/bold]: {sc['description']}")

    # 风险收益比
    if rr.get("ratio"):
        r_color = "green" if rr["ratio"] > 2 else "yellow" if rr["ratio"] > 1 else "red"
        console.print(f"  🎲 [bold]风险收益比[/bold]: [{r_color}]{rr['assessment']}[/{r_color}]")

    console.print()


def _print_news_section(sentiment_data: dict):
    """热点事件——仿富途的新闻聚合区"""
    if not sentiment_data:
        return

    articles = sentiment_data.get("articles", [])
    overall = sentiment_data.get("overall_sentiment", "neutral")
    score = sentiment_data.get("sentiment_score", 0)

    emoji = {"bullish": "🟢", "bearish": "🔴", "neutral": "🟡"}.get(overall, "⚪")
    label = {"bullish": "看好", "bearish": "看空", "neutral": "中性"}.get(overall, "—")
    source = sentiment_data.get("source", "未知来源")

    title_text = f"📰 热点事件 · 情绪{label} {emoji} (评分: {score:+d}) · 源: {source}"

    if not articles:
        console.print(Panel(f"[dim]暂无相关新闻（数据源: {source}）[/dim]", title=title_text, border_style="cyan"))
        return

    # 展示前 5 条
    lines = []
    for a in articles[:5]:
        sentiment_icon = "🟢" if a["net"] > 0 else "🔴" if a["net"] < 0 else "⚪"
        time_str = f"[dim]{a.get('time', '')}[/dim] " if a.get("time") else ""
        lines.append(f"{sentiment_icon} {time_str}{a['title'][:80]}")
        if a.get("publisher"):
            lines[-1] += f" [dim]({a['publisher']})[/dim]"

    console.print(Panel("\n".join(lines), title=title_text, border_style="cyan"))


def _print_technical_snapshot(snapshot: dict):
    """技术指标一览"""
    table = Table(title="📈 技术指标快照", box=box.ROUNDED, border_style="blue")
    table.add_column("指标", style="cyan", width=14)
    table.add_column("数值", width=14)
    table.add_column("状态", width=28)

    def _add(label, value, status="", warn=False):
        style = "bold red" if warn else "white"
        table.add_row(label, f"[{style}]{value}[/{style}]", status)

    s = snapshot

    # 价格
    chg = f"{s.get('change_5d', 0):+.2f}%" if s.get("change_5d") else "—"
    _add("最新价", f"${s.get('price', 'N/A')}", f"5日涨跌: {chg}")

    # 均线
    if s.get("MA50"):
        above = s["price"] and s["price"] > s["MA50"]
        _add("MA50（中期）", f"${s['MA50']}", "股价在上方 ✅" if above else "股价跌破 ⚠️", warn=not above)
    if s.get("MA200"):
        above = s["price"] and s["price"] > s["MA200"]
        _add("MA200（牛熊线）", f"${s['MA200']}", "股价在上方 ✅" if above else "股价跌破 🚨", warn=not above)

    # RSI
    if s.get("RSI") is not None:
        rsi = s["RSI"]
        if rsi > 80:
            _add("RSI (14)", f"{rsi}", "极度超买 🚨", warn=True)
        elif rsi > 70:
            _add("RSI (14)", f"{rsi}", "超买区 ⚠️", warn=True)
        elif rsi < 20:
            _add("RSI (14)", f"{rsi}", "极度超卖")
        elif rsi < 30:
            _add("RSI (14)", f"{rsi}", "超卖区")
        else:
            _add("RSI (14)", f"{rsi}", "正常区间")

    # MACD
    if s.get("MACD_HIST") is not None:
        h = s["MACD_HIST"]
        _add("MACD 柱", f"{h:.4f}", "多头动能" if h > 0 else "空头动能")

    # KDJ
    if s.get("KDJ_J") is not None:
        j = s["KDJ_J"]
        if j > 100:
            _add("KDJ J值", f"{j:.1f}", "极度超买 🚨", warn=True)
        elif j < 0:
            _add("KDJ J值", f"{j:.1f}", "极度超卖")
        else:
            _add("KDJ J值", f"{j:.1f}", "")

    # BOLL
    if s.get("BOLL_PCTB") is not None:
        pctb = s["BOLL_PCTB"]
        if pctb > 1.0:
            _add("布林 %B", f"{pctb}", "突破上轨（过热）", warn=True)
        elif pctb < 0:
            _add("布林 %B", f"{pctb}", "跌破下轨（超跌）")
        else:
            _add("布林 %B", f"{pctb}", "通道内")

    # 量比
    if s.get("VOL_RATIO") is not None:
        vr = s["VOL_RATIO"]
        if vr > 2:
            _add("量比", f"{vr:.1f}x", "巨量🔥")
        elif vr > 1.5:
            _add("量比", f"{vr:.1f}x", "放量")
        elif vr < 0.5:
            _add("量比", f"{vr:.1f}x", "极度缩量")
        else:
            _add("量比", f"{vr:.1f}x", "正常")

    # K线形态
    if s.get("pattern"):
        _add("K线形态", s["pattern"], "")

    console.print(table)


def _print_fundamental_section(fd: dict):
    """基本面——仿富途财报分析区"""
    if not fd:
        return

    # 公司信息
    info_table = Table(title="🏢 基本面 · 估值与增长", box=box.ROUNDED, border_style="green")
    info_table.add_column("指标", style="cyan", width=18)
    info_table.add_column("数值", width=16)
    info_table.add_column("指标", style="cyan", width=18)
    info_table.add_column("数值", width=16)

    val = fd.get("valuation", {})
    growth = fd.get("growth", {})
    prof = fd.get("profitability", {})
    analyst = fd.get("analyst", {})
    company = fd.get("company_name", "")
    sector = fd.get("sector", "")

    # 公司概况
    if company or sector:
        name_short = company[:25] + ("…" if len(company) > 25 else "")
        console.print(f"  [bold]{name_short}[/bold] · {sector} · {fd.get('industry', 'N/A')}")

    # 两列估值+增长
    rows = [
        ("PE (TTM)", f"{val.get('PE', 'N/A')}", "Forward PE", f"{val.get('ForwardPE', 'N/A')}"),
        ("PEG", f"{val.get('PEG', 'N/A')}", "PS", f"{val.get('PS', 'N/A')}"),
        ("营收 YoY", f"{growth.get('RevenueGrowth_YoY', 'N/A')}%", "盈利 YoY", f"{growth.get('EarningsGrowth_YoY', 'N/A')}%"),
        ("毛利率", f"{prof.get('GrossMargin', 'N/A')}%", "净利率", f"{prof.get('NetMargin', 'N/A')}%"),
        ("ROE", f"{prof.get('ROE', 'N/A')}%", "FCF", f"{prof.get('FCF', 'N/A')}"),
        ("分析师评级", f"{analyst.get('Recommendation', 'N/A')}", "上行空间", f"{analyst.get('Upside', 'N/A')}%"),
    ]
    for r in rows:
        info_table.add_row(r[0], r[1], r[2], r[3])

    console.print(info_table)


def _print_options_section(od: dict):
    """期权资金流——仿富途期权异动区"""
    if not od or not od.get("available"):
        return

    table = Table(title="📊 期权资金流", box=box.ROUNDED, border_style="yellow")
    table.add_column("指标", style="cyan", width=18)
    table.add_column("数值", width=40)

    pcr_near = od.get("put_call_ratio_near") or {}
    pcr_monthly = od.get("put_call_ratio_monthly") or {}
    max_pain = od.get("max_pain")
    unusual = od.get("unusual_activity", [])

    if pcr_near.get("volume_pcr"):
        vpcr = pcr_near["volume_pcr"]
        sentiment = "🟢 极度看涨" if vpcr < 0.5 else "🟢 偏看涨" if vpcr < 0.7 else "🔴 偏看空" if vpcr > 1.5 else "🟡 中性"
        table.add_row("P/C 成交量比 (近期)", f"{vpcr}  ({sentiment})")

    if pcr_near.get("oi_pcr"):
        table.add_row("P/C 持仓比 (近期)", f"{pcr_near['oi_pcr']}")

    if max_pain:
        table.add_row("最大痛点", f"${max_pain:.0f}")

    if pcr_near.get("total_call_volume"):
        table.add_row("Call 总成交量", f"{pcr_near['total_call_volume']:,}张")
        table.add_row("Put 总成交量", f"{pcr_near['total_put_volume']:,}张")

    console.print(table)

    # 异常大单
    if unusual:
        u_table = Table(title="⚠️ 期权异动大单", box=box.SIMPLE, border_style="yellow")
        u_table.add_column("方向", width=6)
        u_table.add_column("行权价", width=8)
        u_table.add_column("成交量", width=8)
        u_table.add_column("持仓量", width=8)
        u_table.add_column("涉资", width=10)
        u_table.add_column("信号", width=30)

        for u in unusual[:4]:
            icon = "🟢" if u["type"] == "CALL" else "🔴"
            u_table.add_row(
                f"{icon} {u['type']}",
                f"${u['strike']:.0f}",
                f"{u['volume']:,}",
                f"{u['open_interest']:,}",
                u["premium"],
                u["signal"],
            )
        console.print(u_table)


def _print_market_context(cd: dict):
    """市场背景（含行业对标信息）"""
    if not cd:
        return

    regime = cd.get("market_regime", {})
    benchmarks = cd.get("benchmarks", {})
    rs = cd.get("relative_strength", {})
    sector_etf = cd.get("sector_etf", "")
    sector_name = cd.get("sector_etf_name", "")

    title = f"🌍 市场背景"
    if sector_etf:
        title += f" · 行业对标: {sector_etf}（{sector_name}）"

    table = Table(title=title, box=box.ROUNDED, border_style="blue")
    table.add_column("指数", style="bold", width=20)
    table.add_column("点位", width=10)
    table.add_column("5日", width=8)
    table.add_column("20日", width=8)

    for etf, data in benchmarks.items():
        table.add_row(
            f"{etf} ({data['name']})",
            f"${data['price']:.2f}" if data.get("price") else "N/A",
            f"{data.get('change_5d', 0):+.1f}%" if data.get("change_5d") else "—",
            f"{data.get('change_20d', 0):+.1f}%" if data.get("change_20d") else "—",
        )

    console.print(table)

    # 相对强弱
    if rs:
        for key, val in rs.items():
            excess = val["excess_return"]
            icon = "🟢" if excess > 0 else "🔴"
            console.print(f"  {icon} {key}: 个股 {val['stock_change']:+.1f}% vs 基准 {val['benchmark_change']:+.1f}% （超额 {excess:+.1f}%）")

    # 市场状态
    if regime.get("description"):
        console.print(f"  [bold]市场状态[/bold]: {regime['description']}")
    console.print()


def _print_valuation_history(vd: dict):
    """历史估值分位"""
    if not vd:
        return

    table = Table(title="📐 历史估值分位", box=box.ROUNDED, border_style="magenta")
    table.add_column("指标", style="cyan", width=20)
    table.add_column("数值", width=18)
    table.add_column("判断", width=30)

    # PE
    pe = vd.get("current_pe")
    fpe = vd.get("forward_pe")
    if pe:
        table.add_row("当前 PE (TTM)", f"{pe}", vd.get("pe_assessment", ""))
    if fpe:
        table.add_row("Forward PE", f"{fpe}", "")

    # 价格分位
    for period in ["1y", "3y", "5y"]:
        pct = vd.get(f"price_percentile_{period}")
        if pct is not None:
            bar = "▓" * int(pct / 10) + "░" * (10 - int(pct / 10))
            if pct > 80:
                assessment = "接近历史高位 ⚠️"
            elif pct < 20:
                assessment = "接近历史低位 💡"
            else:
                assessment = "正常区间"
            table.add_row(f"价格分位 ({period})", f"{bar} {pct}%", assessment)

    # vs MA200
    vs200 = vd.get("price_vs_ma200")
    if vs200 is not None:
        if abs(vs200) > 30:
            note = "大幅偏离均值，警惕回归 🚨"
        elif abs(vs200) > 15:
            note = "偏离均值"
        else:
            note = "正常"
        table.add_row(f"偏离 MA200", f"{vs200:+.1f}%", note)

    console.print(table)
    console.print()


def _print_signals_by_dimension(signals_by_dim: dict):
    """按维度分组展示多空信号"""
    if not signals_by_dim:
        return

    dim_order = ["技术面", "基本面", "历史估值", "新闻情绪", "期权资金", "市场背景", "关键价位"]
    rows = []

    for dim in dim_order:
        if dim not in signals_by_dim:
            continue
        d = signals_by_dim[dim]
        bull_count = len(d["bullish"])
        bear_count = len(d["bearish"])
        neutral_count = len(d["neutral"])

        # 找出最高权重信号
        all_in_dim = d["bullish"] + d["bearish"] + d["neutral"]
        top = max(all_in_dim, key=lambda s: s["weight"]) if all_in_dim else None

        bull_str = f"[green]🟢 ×{bull_count}[/green]" if bull_count else ""
        bear_str = f"[red]🔴 ×{bear_count}[/red]" if bear_count else ""
        neu_str = f"[yellow]🟡 ×{neutral_count}[/yellow]" if neutral_count else ""

        row = f"  [bold]{dim}[/bold]: {bull_str} {bear_str} {neu_str}"
        if top:
            row += f"  →  [dim]{top['name'][:40]}[/dim]"
        rows.append(row)

    console.print(Panel("\n".join(rows), title="📶 多维度信号汇总", border_style="cyan"))


def _print_conflicts(conflicts: list):
    """信号冲突警告"""
    if not conflicts:
        return

    for c in conflicts:
        lines = [
            f"[bold red]{c['message']}[/bold red]",
            "",
            f"看涨: {'; '.join(c['bull_signals'][:3])}",
            f"看空: {'; '.join(c['bear_signals'][:3])}",
            "",
            f"[bold yellow]💡 {c['advice']}[/bold yellow]",
        ]
        console.print(Panel("\n".join(lines), title="⚠️ 信号冲突", border_style="red"))


def _print_risk_warning(analysis: dict):
    """风险提示"""
    bearish = [s for s in analysis.get("all_signals", []) if s["type"] == "bearish" and s["weight"] >= 3]
    score = analysis["score"]
    conflicts = analysis.get("conflicts", [])

    warnings = []
    if score < 40:
        warnings.append("⚠️ 综合评分偏低，建议减仓或观望")
    if score > 80:
        warnings.append("💡 综合评分优秀，但请始终设置止损")
    if bearish:
        warnings.append(f"🚨 高危看空信号: {bearish[0]['name'][:50]}")
    if conflicts:
        warnings.append("⚠️ 多空信号冲突，等待方向明朗")

    if warnings:
        console.print(Panel("\n".join(warnings), title="⚠️ 风险提示", border_style="red"))


def _print_cross_check_card(report):
    """打印数据交叉验证卡 — 跑完立刻跟富途对比"""
    from data_validator import generate_health_banner
    card = report.cross_check_card
    if not card:
        return

    health = generate_health_banner(report)

    table = Table(title=f"🔍 数据交叉验证（{health}）", box=box.ROUNDED, border_style="yellow")
    table.add_column("字段", style="cyan", width=14)
    table.add_column("系统值（yfinance）", width=22)
    table.add_column("富途值（手动填入）", style="yellow", width=22)
    table.add_column("✓?", width=6)

    for f in ["数据日期", "收盘价(yf)", "实时价(yf)", "货币", "交易所", "市场状态"]:
        if f in card:
            table.add_row(f, str(card[f]), "________", "⬜")

    console.print(table)

    # 如果有告警，直接标出来
    for e in report.errors:
        console.print(f"  🚨 [red bold]{e}[/red bold]")
    for w in report.warnings:
        console.print(f"  ⚠️  [yellow]{w}[/yellow]")

    console.print("  [dim]👆 请打开富途对比。一致=数据可信。不一致=看上方告警。[/dim]\n")


def _print_data_completeness(analysis: dict):
    """数据完整度一览 — 一眼看出哪些维度有数据、哪些缺失"""
    dims = {
        "技术指标": analysis["snapshot"].get("RSI") is not None,
        "基本面": bool(analysis.get("fundamental_data", {}).get("valuation")),
        "历史估值": bool(analysis.get("valuation_data", {}).get("current_pe")),
        "新闻情绪": bool(analysis.get("sentiment_data", {}).get("articles")),
        "期权数据": bool(analysis.get("options_data", {}).get("available")),
        "大盘对标": bool(analysis.get("context_data", {}).get("benchmarks")),
        "关键价位": bool(analysis.get("levels_data", {}).get("supports")),
    }

    bars = []
    for name, ok in dims.items():
        bars.append(f"[{'green' if ok else 'red'}]{'●' if ok else '○'} {name}[/{'green' if ok else 'red'}]")

    console.print(f"  [dim]数据完整度: {' · '.join(bars)}[/dim]\n")


def _print_verification_checklist(analysis: dict):
    """手工核验清单 — 跑完报告后你该做的 5 件事"""
    qr = analysis.get("quality_report")
    is_backfilled = qr.metrics.get("is_backfilled") if qr else False
    market_state = (analysis.get("live_info") or {}).get("market_state", "?")

    items = [
        "对比富途最新价：系统显示 $" + f"{analysis['snapshot']['price']:.2f}" if analysis['snapshot'].get('price') else "对比富途最新价",
        "对比富途昨收价：交叉验证卡里的「收盘价(yf)」vs 富途昨收",
        "检查数据日期：交叉验证卡里的「数据日期」是否 = 最近交易日",
        ("⚠️ 数据是实时回填的（yahoo未结算），和富途盘后价对比" if is_backfilled else "✅ 数据是已结算收盘价，和富途日K收盘价对比"),
        f"市场状态: {market_state}（PRE=盘前 POST=盘后 REGULAR=正常 CLOSED=已收盘）",
    ]

    lines = "\n".join(f"  {i+1}. {item}" for i, item in enumerate(items))

    console.print(Panel(lines, title="📋 核验清单（手动——确保数据可信）", border_style="dim"))


def _print_footer():
    ver = "N/A"
    try:
        import yfinance
        ver = yfinance.__version__
    except Exception:
        pass
    console.print(f"\n[dim]{'─'*70}[/dim]")
    console.print(f"[dim]yfinance v{ver} | 数据来源: Yahoo Finance | 仅供参考，不构成投资建议 | 投资有风险，入市需谨慎[/dim]")
    console.print(f"[dim]{'─'*70}[/dim]\n")
