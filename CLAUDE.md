# Stock Monitor — Agent 操作手册

## 项目概述

股票多维技术分析系统。输入股票代码 → 自动拉取数据 → 输出八维度综合分析报告。
支持美股(yfinance)、A股/港股(akshare)。
**这个系统是"风险过滤器"，不是"买卖决策机器"。**

## 环境

- **Python**: `/opt/homebrew/bin/python3.12` (macOS Homebrew)
- **工作目录**: `/Users/kamchiu/PycharmProjects/stock_monitor`
- **数据源**: Yahoo Finance (免费/无需注册/有频率限制), akshare (免费/无需注册)
- **无数据库** — 全部基于文件缓存 (`.cache/` 目录)

## 快速开始（每次新 session 的第一步）

```bash
# 1. 确保依赖安装
/opt/homebrew/bin/python3.12 -m pip install yfinance pandas numpy rich scipy akshare --break-system-packages -q 2>&1 | tail -3

# 2. 验证依赖
python3.12 -c "import yfinance; import pandas; import numpy; import rich; import scipy; print('OK')"

# 3. 跑一次分析
cd /Users/kamchiu/PycharmProjects/stock_monitor && python3.12 main.py
```

## 命令参考

```bash
# 分析 config.py 中的全部股票
python3.12 main.py

# 只分析指定股票
python3.12 main.py -s MSFT GOOGL AAPL

# JSON 输出（给程序用）
python3.12 main.py -s MSFT --json

# 每 N 分钟自动刷新
python3.12 main.py -s MSFT --interval 60

# 离线模式（不联网，用本地测试数据）
python3.12 main.py --local -s MSFT
```

## 股票代码格式

| 市场 | 格式 | 示例 |
|------|------|------|
| 美股 | 直接代码 | `MSFT`, `AAPL` |
| A股上海 | `.SS` 后缀 | `600519.SS` (茅台) |
| A股深圳 | `.SZ` 后缀 | `300750.SZ` (宁德) |
| 港股 | `.HK` 后缀 | `0700.HK` (腾讯) |

修改 `config.py` 中的 `SYMBOLS` 列表来添加/删除标的。

## 错误处理指南

### Rate Limit (`Too Many Requests`)
**原因**: Yahoo 短时间请求太多封 IP。
**处理**: 等 15 分钟后重试，或先用 `--local` 模式测试。
```bash
# 等待 15 分钟
sleep 900 && python3.12 main.py -s MSFT
```

### 数据源失败
- 美股: yfinance 偶尔不稳定，自动重试 3 次（已内置指数退避）
- A股/港股: akshare 没有内置重试，失败即中止该标的
- **应对**: 单只股票失败不影响其他标的，继续分析剩余的

### 数据不准
- 看报告顶部「数据交叉验证卡」+ 底部「核验清单」
- 盘后/盘前数据可能用实时价回填（正常行为）
- Yahoo 数据有 T+1 延迟

## 文件结构

```
main.py              ← 入口，命令行解析
config.py            ← ⭐ 股票列表、指标参数、评分权重
indicators.py        ← MA/BOLL/RSI/MACD/KDJ 计算
signals.py           ← 金叉死叉/背离检测
patterns.py          ← K线形态识别
analyzer.py          ← 综合评分引擎
report.py            ← Rich 终端报告渲染
levels.py            ← 支撑/阻力/情景推演
fundamentals.py      ← 美股基本面
fundamentals_cn.py   ← A股/港股基本面
sentiment.py         ← 新闻情绪
options_flow.py      ← 期权资金流
market_context.py    ← 大盘/行业对标
valuation_history.py ← 历史估值分位
data_validator.py    ← 数据质量检查(8项)
multi_fetcher.py     ← 多数据源分发
cache.py             ← 本地缓存
local_data.py        ← 离线测试数据
```

## 自主运行策略

### 24h 持续监控模式
```bash
# 内建定时刷新
python3.12 main.py -s MSFT GOOGL AAPL --interval 60
```

### 遇到 rate limit 后自动恢复
当 Yahoo 返回 rate limit 错误时:
1. 等 15 分钟（900秒）
2. 重试一次
3. 如果还是失败，切换到 `--local` 模式先跑本地数据
4. 再等 15 分钟重试

### 输出管理
- 报告直接输出到终端
- 如需保存: `python3.12 main.py --json > reports/$(date +%Y%m%d_%H%M%S).json`
- 缓存自动管理: `.cache/` 目录，30min 有效期（日线数据）

## 评分解读

- **不要只看评分数字** — 评分是主观权重，45 和 55 没有统计差异
- 先看数据交叉验证卡 → 关键价位 → 趋势 → 多空信号冲突
- AUDIT.md 有完整的数据可靠性审计

## 免责

仅供学习研究，不构成投资建议。数据来自第三方免费 API，不保证 100% 准确。
