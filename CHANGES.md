# 修复记录

## 2026-08-06 重大修复

### P0 严重 Bug 修复

#### 1. 技术面维度完全失效（main.py）
**问题**：`calc_all_indicators()` 和 `detect_all_patterns()` 被 import 但从未调用，导致：
- MA20/MA50/RSI/MACD/KDJ/BOLL 全部为 null
- 趋势判断永远是"横盘震荡"
- 技术信号产出为 0
- 支撑阻力缺少均线维度

**修复**：在 `analyze_symbol()` 函数中，数据获取后立即调用：
```python
# ===== 2. 计算技术指标 + K线形态识别 =====
df = calc_all_indicators(df)
df = detect_all_patterns(df)
```

**验证**：本地模式测试显示 MA20=476.6, RSI=56.2, MACD=3.83，趋势为"强势上涨"

#### 2. A股基本面数据整段坏死（fundamentals_cn.py）
**问题**：`_fetch_cn()` 函数中，子进程（101-128行）正确获取了数据，但 146-254 行残留了重构前的旧版"进程内"实现：
- 引用的 `ak` 变量在当前作用域未定义 → `NameError`
- 被 `except Exception` 静默吞掉
- 子进程结果被整个丢弃
- 所有 A 股基本面字段全是 `None`

**修复**：删除 146-254 行的坏死代码，直接使用子进程返回的结果

### P1 配置矛盾修复

#### 3. PERIOD 配置不足（config.py）
**问题**：`PERIOD = "6mo"`（约 126 个交易日），但 `MA_PERIODS` 包含 MA200 → MA200 永远是 NaN

**修复**：`PERIOD = "2y"`（约 500 个交易日），确保 MA200 可计算

#### 4. 依赖不完整（requirements.txt）
**问题**：缺少 `scipy`、`akshare`、`requests`，安装后直接 ImportError

**修复**：添加完整依赖
```
yfinance>=0.2.40
pandas>=2.0.0
numpy>=1.24.0
rich>=13.0.0
scipy>=1.10.0
akshare>=1.12.0
requests>=2.28.0
```

#### 5. --json 模式输出污染（main.py）
**问题**：`--json` 模式下 Rich 验证卡混入 stdout，管道输出的 JSON 无法被程序解析

**修复**：统一 `verbose = not args.json`，interval 和非 interval 分支都使用这个变量

### 新功能：行业相对比较

#### 6. 行业基准数据模块（industry_benchmarks.py）
**新增**：提供各行业估值和盈利能力的参考基准

**美股 GICS 行业**（11 个）：
- Technology: PE=32, gross_margin=62%, ROE=28%
- Financial Services: PE=15, net_margin=28%, ROE=13%
- Healthcare: PE=22, gross_margin=65%, ROE=22%
- Consumer Cyclical/Defensive
- Energy, Industrials, Real Estate, Utilities, Basic Materials
- Communication Services

**A股行业**（16 个）：
- 白酒: PE=35, gross_margin=75%, ROE=28%
- 银行: PE=6, PB=0.6, ROE=11%
- 医药生物, 电子, 计算机, 食品饮料
- 家电, 房地产, 电力设备, 汽车
- 钢铁, 化工, 建筑装饰, 保险, 证券

**港股**：fallback 到美股基准（通过行业映射）

#### 7. 基本面评估改用行业相对比较

**之前**（固定阈值）：
```python
if pe > 100:  # 极高估值
    signals.append({"type": "bearish", "weight": 2})
elif pe < 15:  # 低估
    signals.append({"type": "bullish", "weight": 2})
```

**现在**（相对行业均值）：
```python
benchmark = get_sector_benchmark(sector, market="us")
comp = compare_to_benchmark(pe, benchmark["PE"], "PE")
# comp["assessment"] = "显著低于行业均值（70%）" → bullish
# comp["assessment"] = "显著高于行业均值（141%）" → bearish
```

**示例**：
- MSFT PE=45 vs 科技行业均值 32 → "显著高于行业均值（141%）" → bearish
- 茅台 PE=35 vs 白酒行业均值 35 → "接近行业均值（100%）" → neutral
- 招商银行 PE=8 vs 银行行业均值 6 → "高于行业均值（133%）" → bearish

### Git 初始化

创建 `.gitignore` 并初始化 git 仓库，完成首次提交（commit d5d5e4f）

### 验证结果

**本地模式测试**（python3.12 main.py --local -s MSFT --json）：

**修复前**：
```json
{
  "snapshot": {
    "MA20": null, "MA50": null, "RSI": null, "MACD_DIF": null,
    "KDJ_K": null, "BOLL_PCTB": null, "pattern": null
  },
  "trend": {"direction": "横盘震荡", "strength": "弱", "details": []},
  "bullish_signals": [],
  "bearish_signals": ["距支撑 $473.23 仅 1.1%"]
}
```

**修复后**：
```json
{
  "snapshot": {
    "MA20": 476.6, "MA50": 453.87, "RSI": 56.2, "MACD_DIF": 3.83,
    "KDJ_K": 44.4, "BOLL_PCTB": 0.54, "pattern": "双顶形态（顶部反转）"
  },
  "trend": {
    "direction": "强势上涨", "strength": "强",
    "details": ["价格 > MA50 ✅", "MA50 向上倾斜 +3.6% ✅", "MACD > 0（多头）✅"]
  },
  "bullish_signals": [
    "股价在 MA50 上方（中期多头）",
    "股价在布林中轨上方",
    "MACD 零轴上方（多头市场）",
    "MACD 绿柱持续缩短（空头衰竭）"
  ],
  "bearish_signals": [
    "双顶形态（顶部反转）",
    "距支撑 $476.60 仅 0.4%（MA20 / BOLL 中轨 / Fib 23.6%）"
  ]
}
```

**行业基准测试**：
```
Technology benchmark: PE=32, gross_margin=62%, ROE=28%
PE comparison (MSFT PE=45 vs 行业 32): 
  assessment="显著高于行业均值（141%）" → bearish

白酒 benchmark: PE=35, gross_margin=75%, ROE=28%
```

### 影响范围

**修复的模块**：
- main.py: 技术指标计算 + --json verbose 修复
- fundamentals_cn.py: A股基本面数据获取
- config.py: PERIOD 配置
- requirements.txt: 依赖完整性

**新增的模块**：
- industry_benchmarks.py: 行业基准数据
- .gitignore: Git 忽略规则

**更新的模块**：
- fundamentals.py: 改用行业相对比较
- fundamentals_cn.py: 改用行业相对比较

### 剩余工作（低优先级）

1. **alert_monitor.py 缺失**：alert_config.py 引用了 alert_monitor.py 但文件不存在（告警系统只有配置没有实现）
2. **背离检测时间对齐**：`detect_divergence()` 比较价格极值和指标极值时未做时间对齐，可能产生假背离
3. **盘中未完成 bar**：盘中运行时最后一根 K 线是未完成的当日 bar，成交量天然偏小，量比类信号系统性失真
4. **A股/港股市场背景**：`market_context.py` 对 A股/港股也用 SPY/QQQ 做基准，应换沪深300/恒指
5. **A股新闻情绪**：`sentiment.py` 用英文 Google News RSS 查 A 股代码，基本是垃圾输入

### 总结

**修复了 2 个 P0 严重 bug**（技术面完全失效 + A股基本面坏死），**3 个 P1 配置问题**，**新增行业相对比较功能**，**初始化 Git 仓库**。

系统现在可以正确计算技术指标，趋势判断正常工作，A股基本面数据可用，估值/盈利能力评估基于行业基准而非固定阈值。

**commit**: d5d5e4f
