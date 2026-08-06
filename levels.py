"""
支撑位/阻力位/目标位分析模块
============================
多维度计算关键价位：均线支撑、前高前低、斐波那契、布林带、
期权关键位、心理整数关口、成交量密集区。

输出"如果跌破 X，下一支撑在 Y"的链条式分析。
"""

import numpy as np
import pandas as pd
from scipy.signal import argrelextrema


def find_support_resistance(df: pd.DataFrame, options_data: dict = None) -> dict:
    """
    综合计算所有支撑位和阻力位。

    返回:
        {
            "current_price": float,
            "supports": [{"price": float, "method": str, "strength": str}],
            "resistances": [{"price": float, "method": str, "strength": str}],
            "key_levels_summary": str,    # 一句话总结
            "break_scenarios": [...],      # 跌破/突破场景
            "risk_reward": {...},          # 风险收益比
            "signals": [...],
        }
    """
    row = df.iloc[-1]
    current_price = float(row["close"])

    # 收集所有候选支撑和阻力
    all_supports = []
    all_resistances = []

    # 1. 均线支撑/阻力
    for period, label, side, strength in [
        (5, "MA5（短线生命线）", "support", "弱"),
        (10, "MA10（短线趋势）", "support", "弱"),
        (20, "MA20（中期生命线）", "support", "中"),
        (50, "MA50（中期分水岭）", "support", "强"),
        (200, "MA200（牛熊分界线）", "support", "极强"),
    ]:
        col = f"MA{period}"
        if col in df.columns and pd.notna(row[col]):
            price = float(row[col])
            entry = {"price": round(price, 2), "method": label, "strength": strength}
            if price < current_price:
                entry["type"] = "support"
                all_supports.append(entry)
            else:
                entry["type"] = "resistance"
                all_resistances.append(entry)

    # 2. 布林带
    if "BOLL_DN" in df.columns and pd.notna(row["BOLL_DN"]):
        all_supports.append({
            "price": round(float(row["BOLL_DN"]), 2),
            "method": "BOLL 下轨",
            "strength": "中",
            "type": "support",
        })
    if "BOLL_MID" in df.columns and pd.notna(row["BOLL_MID"]):
        boll_mid = float(row["BOLL_MID"])
        entry = {"price": round(boll_mid, 2), "method": "BOLL 中轨", "strength": "中"}
        if boll_mid < current_price:
            entry["type"] = "support"
            all_supports.append(entry)
        else:
            entry["type"] = "resistance"
            all_resistances.append(entry)

    # 3. 近期高点和低点（用 scipy 找局部极值）
    lookback = min(60, len(df))
    recent = df.iloc[-lookback:]

    # 局部高点
    local_high_idx = argrelextrema(recent["high"].values, np.greater, order=10)[0]
    for i in local_high_idx[-5:]:
        price = float(recent["high"].iloc[i])
        if price > current_price:
            all_resistances.append({
                "price": round(price, 2),
                "method": "前高（筹码密集区）",
                "strength": "强",
                "type": "resistance",
            })

    # 局部低点
    local_low_idx = argrelextrema(recent["low"].values, np.less, order=10)[0]
    for i in local_low_idx[-5:]:
        price = float(recent["low"].iloc[i])
        if price < current_price:
            all_supports.append({
                "price": round(price, 2),
                "method": "前低（筹码支撑区）",
                "strength": "强",
                "type": "support",
            })

    # 4. 斐波那契回撤（从最近的大级别低点到高点）
    fib_levels = _calc_fibonacci(df, current_price)
    for fib in fib_levels:
        if fib["price"] < current_price:
            fib["type"] = "support"
            all_supports.append(fib)
        else:
            fib["type"] = "resistance"
            all_resistances.append(fib)

    # 5. 心理整数关口
    round_levels = _calc_round_numbers(current_price)
    for rl in round_levels:
        if rl["price"] < current_price:
            rl["type"] = "support"
            all_supports.append(rl)
        else:
            rl["type"] = "resistance"
            all_resistances.append(rl)

    # 6. 期权关键价位（如果可用）
    if options_data and options_data.get("available"):
        if options_data.get("max_pain"):
            mp = options_data["max_pain"]
            entry = {"price": round(mp, 2), "method": "期权最大痛点", "strength": "中"}
            if mp < current_price:
                entry["type"] = "support"
                all_supports.append(entry)
            else:
                entry["type"] = "resistance"
                all_resistances.append(entry)
        for level in options_data.get("key_levels", [])[:3]:
            entry = {
                "price": round(level["strike"], 2),
                "method": f"期权OI密集 (OI={level['total_oi']})",
                "strength": "强" if level["total_oi"] > 10000 else "中",
            }
            if level["strike"] < current_price:
                entry["type"] = "support"
                all_supports.append(entry)
            else:
                entry["type"] = "resistance"
                all_resistances.append(entry)

    # === 去重并排序 ===
    supports = _deduplicate_and_sort(all_supports, reverse=True)   # 支撑从高到低
    resistances = _deduplicate_and_sort(all_resistances, reverse=False)  # 阻力从低到高

    # === 构建突破/跌破场景 ===
    break_scenarios = _build_scenarios(current_price, supports, resistances)

    # === 风险收益比 ===
    risk_reward = _calc_risk_reward(current_price, supports, resistances)

    # === 信号 ===
    signals = _generate_level_signals(current_price, supports, resistances, break_scenarios)

    return {
        "current_price": current_price,
        "supports": supports[:5],
        "resistances": resistances[:5],
        "break_scenarios": break_scenarios,
        "risk_reward": risk_reward,
        "signals": signals,
    }


def _calc_fibonacci(df: pd.DataFrame, current_price: float) -> list[dict]:
    """
    斐波那契回撤位：从最近 60 天的最低点到最高点，
    计算 0.236, 0.382, 0.5, 0.618, 0.786 回撤位。
    """
    lookback = min(60, len(df))
    recent = df.iloc[-lookback:]
    swing_low = float(recent["low"].min())
    swing_high = float(recent["high"].max())
    diff = swing_high - swing_low

    if diff <= 0:
        return []

    fib_ratios = {
        0.236: "Fib 23.6%（浅回撤）",
        0.382: "Fib 38.2%（黄金回撤）",
        0.500: "Fib 50%（半分位）",
        0.618: "Fib 61.8%（黄金分割）",
        0.786: "Fib 78.6%（深回撤）",
    }

    levels = []
    for ratio, label in fib_ratios.items():
        price = swing_high - diff * ratio
        # 扩展到上方（扩展位）
        if ratio <= 0.5:  # 扩展位作为阻力
            ext_price = swing_high + diff * ratio
            if ext_price > current_price * 1.01:
                levels.append({
                    "price": round(ext_price, 2),
                    "method": f"Fib 扩展 {ratio:.1%}",
                    "strength": "中",
                })

        levels.append({
            "price": round(price, 2),
            "method": label,
            "strength": "强" if ratio in (0.382, 0.618) else "中",
        })

    return levels


def _calc_round_numbers(current_price: float) -> list[dict]:
    """心理整数关口：整数位和半整数位"""
    levels = []
    step = _round_step(current_price)

    base = int(current_price / step) * step
    for i in range(-3, 4):
        price = base + i * step
        if abs(price - current_price) / current_price > 0.02:  # 至少差 2%
            levels.append({
                "price": price,
                "method": f"心理关口 ${price:.0f}",
                "strength": "弱",
            })

    return levels


def _round_step(price: float) -> float:
    """根据价位确定整数关口的步长"""
    if price > 1000:
        return 100
    elif price > 500:
        return 50
    elif price > 100:
        return 20
    elif price > 50:
        return 10
    elif price > 10:
        return 5
    else:
        return 1


def _deduplicate_and_sort(levels: list[dict], reverse: bool = False) -> list[dict]:
    """
    去重：相近价位（<1% 差距）合并，取最可靠的方法名。
    排序：支撑位从高到低，阻力位从低到高。
    """
    if not levels:
        return []

    sorted_levels = sorted(levels, key=lambda x: x["price"], reverse=True)
    merged = []

    for level in sorted_levels:
        if not merged:
            merged.append(level)
            continue

        last = merged[-1]
        if abs(level["price"] - last["price"]) / last["price"] < 0.008:
            # 合并：保留更可靠的
            strength_order = {"极强": 4, "强": 3, "中": 2, "弱": 1}
            if strength_order.get(level["strength"], 0) > strength_order.get(last["strength"], 0):
                merged[-1] = level
            elif strength_order.get(level["strength"], 0) == strength_order.get(last["strength"], 0):
                # 合并方法名
                if level["method"] not in last["method"]:
                    merged[-1]["method"] += f" / {level['method']}"
        else:
            merged.append(level)

    return sorted(merged, key=lambda x: x["price"], reverse=reverse)


def _build_scenarios(current_price: float,
                     supports: list[dict],
                     resistances: list[dict]) -> list[dict]:
    """
    构建具体场景：
    "如果跌破 A，下一支撑在 B，再下面是 C"
    "如果突破 D，上方目标 E，然后是 F"
    """
    scenarios = []

    # === 上涨场景 ===
    up_targets = [r for r in resistances if r["price"] > current_price]
    if up_targets:
        r1 = up_targets[0]
        r2 = up_targets[1] if len(up_targets) > 1 else None
        desc = f"突破 ${r1['price']:.2f}（{r1['method']}）"
        if r2:
            desc += f" → 下一目标 ${r2['price']:.2f}（{r2['method']}）"
        else:
            desc += " → 上方无显著阻力，有望延续趋势"

        # 计算距当前价的幅度
        upside = (r1["price"] - current_price) / current_price * 100
        scenarios.append({
            "direction": "📈 上涨",
            "trigger": f"有效站上 ${r1['price']:.2f}",
            "upside_pct": round(upside, 1),
            "description": desc,
        })

    # === 下跌场景 ===
    down_targets = [s for s in supports if s["price"] < current_price]
    if down_targets:
        s1 = down_targets[0]  # 最近支撑
        s2 = down_targets[1] if len(down_targets) > 1 else None
        s3 = down_targets[2] if len(down_targets) > 2 else None

        desc = f"跌破 ${s1['price']:.2f}（{s1['method']}）"
        if s2:
            desc += f" → 下一支撑 ${s2['price']:.2f}（{s2['method']}）"
        if s3:
            desc += f" → 再下探 ${s3['price']:.2f}（{s3['method']}）"

        downside = (current_price - s1["price"]) / current_price * 100
        scenarios.append({
            "direction": "📉 下跌",
            "trigger": f"有效跌破 ${s1['price']:.2f}",
            "downside_pct": round(downside, 1),
            "description": desc,
        })

    return scenarios


def _calc_risk_reward(current_price: float,
                      supports: list[dict],
                      resistances: list[dict]) -> dict:
    """
    计算风险收益比（修复版）。

    规则:
    - 必须用最近支撑和最近阻力
    - 如果最近阻力 < 现价 2%（空间太小无意义），跳到下一个
    - 如果最近支撑 > 现价 -2%（贴太近），跳到下一个
    """
    if not supports or not resistances:
        return {"ratio": None, "assessment": "数据不足"}

    # 找到第一个有意义的支撑（距现价 ≥ 2%）
    nearest_support = None
    for s in supports:
        dist = (current_price - s["price"]) / current_price * 100
        if dist >= 1.5:  # 至少 1.5% 的距离才有意义
            nearest_support = s
            break
    if nearest_support is None:
        nearest_support = supports[0]  # 退而求其次

    # 找到第一个有意义的阻力（距现价 ≥ 2%）
    nearest_resistance = None
    for r in resistances:
        dist = (r["price"] - current_price) / current_price * 100
        if dist >= 1.5:
            nearest_resistance = r
            break
    if nearest_resistance is None:
        nearest_resistance = resistances[0]

    reward = nearest_resistance["price"] - current_price
    risk = current_price - nearest_support["price"]

    if risk <= 0.1:
        return {
            "ratio": None,
            "assessment": "现价低于最近支撑位，风险极高",
            "nearest_support": nearest_support["price"],
            "nearest_resistance": nearest_resistance["price"],
        }

    ratio = reward / risk

    if ratio > 3:
        assessment = f"极佳 (R:R = {ratio:.1f}:1)，盈亏比优秀"
    elif ratio > 2:
        assessment = f"良好 (R:R = {ratio:.1f}:1)，适合入场"
    elif ratio > 1:
        assessment = f"一般 (R:R = {ratio:.1f}:1)，谨慎操作"
    else:
        assessment = f"差 (R:R = {ratio:.1f}:1)，不宜追高"

    return {
        "nearest_support": nearest_support["price"],
        "nearest_resistance": nearest_resistance["price"],
        "risk": round(risk, 2),
        "reward": round(reward, 2),
        "ratio": round(ratio, 2),
        "assessment": assessment,
    }


def _generate_level_signals(current: float,
                            supports: list[dict],
                            resistances: list[dict],
                            scenarios: list[dict]) -> list[dict]:
    """从价位分析生成信号"""
    signals = []

    # 最近支撑
    if supports:
        s = supports[0]
        dist = (current - s["price"]) / current * 100
        if dist < 2:
            signals.append({
                "name": f"距支撑 ${s['price']:.2f} 仅 {dist:.1f}%（{s['method']}），可设止损于此下方",
                "type": "bearish", "weight": 1
            })
        else:
            signals.append({
                "name": f"最近支撑 ${s['price']:.2f}（距现价 {dist:.1f}%）",
                "type": "neutral", "weight": 0
            })

    # 最近阻力
    if resistances:
        r = resistances[0]
        dist = (r["price"] - current) / current * 100
        if dist < 3:
            signals.append({
                "name": f"距阻力 ${r['price']:.2f} 仅 {dist:.1f}%（{r['method']}），突破则打开空间",
                "type": "neutral", "weight": 0
            })

    return signals
