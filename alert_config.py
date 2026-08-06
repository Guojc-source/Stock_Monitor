"""
告警规则配置文件
================
每只股票独立配置监控规则。
修改后重启 alert_monitor.py 即可生效。

三种告警类型：
  1. trailing_stop  — 动态止盈：从监控期间最高点回落 X%
  2. ma_break       — 均线突破：价格跌破/升破某条均线
  3. bollinger      — 布林线信号：触及上下轨、带宽变化
"""

# ============================================================
# Telegram 推送配置
# ============================================================
# 获取方式：
#   1. 在 Telegram 搜 @BotFather，发送 /newbot，拿到 TOKEN
#   2. 搜 @userinfobot，发送 /start，拿到你的 CHAT_ID
# ============================================================
TELEGRAM_BOT_TOKEN = ""      # 填你的 bot token，例如 "123456:ABC..."
TELEGRAM_CHAT_ID = ""         # 填你的 chat ID，例如 "987654321"

# ============================================================
# 全局默认参数（所有股票共用，可在单只股票规则中覆盖）
# ============================================================
DEFAULT_POLL_INTERVAL = 60        # 轮询间隔（秒），免费 API 建议 >= 30s
DEFAULT_COOLDOWN_MINUTES = 30     # 同一信号最小间隔（分钟），防止频繁推送

# ============================================================
# 单只股票告警规则
# ============================================================
# 每只股票一个 dict，key = 股票代码
# 规则项可以同时开启多个，满足任一条件即告警
#
# 规则字段说明：
#   trailing_stop:
#       pct         — 从最高点回落多少百分比触发（正数，如 8 表示 -8%）
#       enabled     — true/false
#
#   ma_break:
#       ma_period   — 参考哪条均线（10, 20, 50, 200）
#       direction   — "below"（跌破均线）或 "above"（升破均线）
#       enabled     — true/false
#
#   bollinger:
#       signal      — "touch_upper"（触及上轨）
#                     "touch_lower"（触及下轨）
#                     "back_inside_upper"（从上轨外回到内 = 动量衰竭）
#                     "back_inside_lower"（从下轨外回到内 = 反弹信号）
#                     "band_squeeze"（带宽收缩到近期低点 = 变盘前兆）
#       enabled     — true/false
#
#   hard_stop:
#       pct         — 从入场价算，跌多少无条件告警（如 -15%）
#       entry_price — 你的买入均价
#       enabled     — true/false
# ============================================================

ALERTS = {
    "MSFT": {
        "trailing_stop": {"enabled": True, "pct": 8},
        "ma_break": {"enabled": True, "ma_period": 20, "direction": "below"},
        "bollinger": {"enabled": False, "signal": "back_inside_upper"},
        "hard_stop": {"enabled": False, "entry_price": None, "pct": 15},
    },
    "ADBE": {
        "trailing_stop": {"enabled": True, "pct": 10},
        "ma_break": {"enabled": True, "ma_period": 20, "direction": "below"},
        "bollinger": {"enabled": False, "signal": "back_inside_upper"},
        "hard_stop": {"enabled": False, "entry_price": None, "pct": 15},
    },
    # 示例：更复杂的配置
    # "AAPL": {
    #     "trailing_stop": {"enabled": True, "pct": 6},
    #     "ma_break": {"enabled": True, "ma_period": 50, "direction": "below"},
    #     "bollinger": {"enabled": True, "signal": "back_inside_upper"},
    #     "hard_stop": {"enabled": True, "entry_price": 195.0, "pct": 15},
    # },
}

# ============================================================
# 轮询间隔覆盖（可选）
# ============================================================
# 某些股票波动大，需要更频繁检查（会占用更多 API 配额）
# POLL_INTERVAL_OVERRIDE = {"TSLA": 30}

# ============================================================
# 冷却时间覆盖（可选）
# ============================================================
# COOLDOWN_OVERRIDE = {"TSLA": 60}  # TSLA 同一信号至少隔 60 分钟
