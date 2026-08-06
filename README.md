# 📊 股票多维技术分析系统

## 一句话说明

输入股票代码，自动拉取数据，输出 **八维度综合分析报告**——支撑阻力、买卖信号、估值分位、期权资金、新闻情绪，支持美股/A股/港股。

---

## 快速开始

### 1. 安装依赖

```bash
pip3 install yfinance pandas numpy rich scipy akshare --break-system-packages
```

> 如果报错，换成：`/opt/homebrew/bin/python3.12 -m pip install yfinance pandas numpy rich scipy akshare --break-system-packages`

### 2. 添加你的股票

打开 `config.py`（Finder → Cmd+Shift+G → 粘贴路径 `/Users/kamchiu/PycharmProjects/stock_monitor`）：

```python
SYMBOLS = [
    # === 美股 ===
    "ADBE",         # Adobe
    "MSFT",         # 微软
    "GOOGL",        # 谷歌
    "AAPL",         # 苹果
    "TSLA",         # 特斯拉

    # === A股（上海 .SS / 深圳 .SZ）===
    "600519.SS",    # 贵州茅台
    "300750.SZ",    # 宁德时代

    # === 港股（.HK）===
    "0700.HK",      # 腾讯控股
    "9988.HK",      # 阿里巴巴
]
```

### 3. 运行分析

```bash
cd /Users/kamchiu/PycharmProjects/stock_monitor

# 分析 config.py 中的全部股票
python3.12 main.py

# 只分析指定股票
python3.12 main.py -s MSFT GOOGL

# 每60分钟自动刷新
python3.12 main.py -s MSFT --interval 60
```

---

## 报告解读

### 数据交叉验证卡（每份报告最顶部）

跑完报告后，打开富途牛牛，对比这 5 个字段：

| 字段 | 系统值 | 富途值 |
|------|--------|--------|
| 数据日期 | 2026-08-03 | 看日K最后一天 |
| 收盘价 | $373.51 | 看日K收盘价 |
| 实时价 | $373.51 | 看实时报价 |
| 货币 | USD | 确认币种 |
| 市场状态 | PRE/POST/REGULAR | 盘前/盘后/交易中 |

**5 项都吻合 = 数据正确。不吻合 = 看红色告警。**

### 综合判断

```
██████████████████░░  ← 可视化评分条
评分: 92/100          ← 0-100，越高越好
建议: 🟢 强烈买入     ← 5 档: 强烈买入/偏多/中性/偏空/强烈卖出
趋势: 震荡偏多         ← 三重确认: 价格vs均线 + 均线斜率 + MACD
```

### 关键价位（最重要）

```
现价: $373.51
阻力1: $376.00 (前高，+0.7%)    ← 突破这个才能涨
阻力2: $386.31 (Fib，+3.4%)
支撑1: $372.66 (Fib，-0.2%)     ← 跌破这个要警惕
支撑2: $361.63 (Fib，-3.2%)
支撑3: $355.00 (期权最大痛点，-5.0%)

📈 上涨场景: 突破$376 → 目标$386 → $400
📉 下跌场景: 跌破$373 → 支撑$362 → 再跌到$355
🎲 风险收益比: 1.1:1 (一般，谨慎操作)
```

### 其他维度

| 维度 | 数据来源 | 内容 |
|------|---------|------|
| 📈 技术指标 | 计算得出 | RSI/MACD/KDJ/布林/均线/量比/K线形态 |
| 🏢 基本面 | yfinance | PE/PEG/营收增速/利润率/ROE/分析师评级 |
| 📐 历史估值 | yfinance | 5年价格分位/PE区间/偏离MA200 |
| 📰 新闻情绪 | yfinance+Google RSS | 关键词分析，判断市场情绪方向 |
| 📊 期权资金 | yfinance | P/C比/异常大单/最大痛点 |
| 🌍 市场背景 | yfinance | SPY/QQQ/行业ETF对比，相对强弱 |

### 底部核验清单

每份报告底部有 5 步核验清单，确保数据可信后再看分析结论。

---

## 数据源

| 市场 | 数据源 | 需要注册？ |
|------|--------|:---:|
| 美股 | yfinance (Yahoo Finance) | ❌ |
| A股 | akshare (新浪/东方财富) | ❌ |
| 港股 | akshare (新浪/腾讯) | ❌ |

---

## 常见问题

### Q: 报错 "Too Many Requests. Rate limited"

Yahoo 暂时封了你的 IP（短时间请求太多）。等 15 分钟再跑，或者用 `--local` 模式先测试逻辑：

```bash
python3.12 main.py --local -s MSFT
```

### Q: 数据跟富途对不上

看报告顶部的「数据交叉验证卡」和底部「核验清单」。可能原因：
- 数据未结算（Yahoo 延迟），系统会自动用实时价回填
- 盘后/盘前时段，显示的是实时价而非收盘价
- Yahoo 数据源与富途有微小偏差（正常）

### Q: A股怎么加

代码加 `.SS`（上海）或 `.SZ`（深圳）后缀：

```python
SYMBOLS = [
    "600519.SS",   # 茅台
    "000858.SZ",   # 五粮液
]
```

### Q: 技术指标参数怎么调

编辑 `config.py` 中的参数，比如把 RSI 周期从 14 改成 9：

```python
RSI_PERIOD = 9
```

---

## 免责声明

本系统仅供学习研究使用，**不构成任何投资建议**。

- 数据来自第三方免费 API，不保证 100% 准确
- 技术分析基于历史数据，不预测未来
- 投资有风险，入市需谨慎

---

## 路径

```
/Users/kamchiu/PycharmProjects/stock_monitor/
├── main.py              ← 入口
├── config.py            ← ⭐ 改股票、调参数都在这里
├── README.md            ← 本文件
├── indicators.py        ← MA/BOLL/RSI/MACD/KDJ 计算
├── signals.py           ← 信号检测（金叉死叉/背离）
├── patterns.py          ← K线形态识别
├── analyzer.py          ← 综合评分引擎
├── report.py            ← 报告渲染
├── levels.py            ← 支撑/阻力/场景推演
├── fundamentals.py      ← 基本面分析
├── sentiment.py         ← 新闻情绪
├── options_flow.py      ← 期权资金流
├── market_context.py    ← 大盘/行业对标
├── valuation_history.py ← 历史估值分位
├── data_validator.py    ← 数据健康检查（8项）
├── multi_fetcher.py     ← 多数据源获取（yfinance+akshare）
├── cache.py             ← 本地缓存
└── local_data.py        ← 离线测试数据
```
