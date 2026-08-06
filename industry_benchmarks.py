"""
行业基准数据模块
================
提供各行业估值和盈利能力的参考基准，用于行业相对比较。

数据来源：基于历史统计的行业均值（近似值），定期更新。
最后更新：2026-08-06

用法：
    from industry_benchmarks import get_sector_benchmark, get_cn_sector_benchmark
    benchmark = get_sector_benchmark("Technology")
    # benchmark = {"PE": 32, "gross_margin": 60, "net_margin": 22, "ROE": 28, ...}
"""


# ============================================================
# 美股行业基准（GICS 分类）
# ============================================================
# 数据基于 2020-2025 年历史统计中位数（近似值）
# 参考来源：Damodaran Online, S&P Capital IQ, Bloomberg

US_SECTOR_BENCHMARKS = {
    "Technology": {
        "PE": 32,           # 科技股 PE 通常较高（成长溢价）
        "ForwardPE": 28,
        "PS": 6.5,
        "PB": 8.5,
        "gross_margin": 62,  # 软件/半导体毛利率高
        "operating_margin": 28,
        "net_margin": 23,
        "ROE": 28,
        "revenue_growth": 12,
        "description": "科技（软件/硬件/半导体）",
    },
    "Communication Services": {
        "PE": 22,
        "ForwardPE": 19,
        "PS": 3.2,
        "PB": 5.5,
        "gross_margin": 48,
        "operating_margin": 22,
        "net_margin": 16,
        "ROE": 22,
        "revenue_growth": 8,
        "description": "通信服务（媒体/互联网/电信）",
    },
    "Financial Services": {
        "PE": 15,           # 金融股 PE 通常较低
        "ForwardPE": 13,
        "PS": 3.8,
        "PB": 1.8,          # 银行 PB 接近 1
        "gross_margin": None,  # 金融不用毛利率
        "operating_margin": 35,
        "net_margin": 28,
        "ROE": 13,
        "revenue_growth": 6,
        "description": "金融（银行/保险/资管）",
    },
    "Healthcare": {
        "PE": 22,
        "ForwardPE": 19,
        "PS": 4.5,
        "PB": 6.0,
        "gross_margin": 65,  # 制药/医疗器械毛利高
        "operating_margin": 22,
        "net_margin": 18,
        "ROE": 22,
        "revenue_growth": 10,
        "description": "医疗健康（制药/器械/服务）",
    },
    "Consumer Cyclical": {
        "PE": 22,
        "ForwardPE": 19,
        "PS": 1.8,
        "PB": 6.5,
        "gross_margin": 40,
        "operating_margin": 12,
        "net_margin": 8,
        "ROE": 28,          # 零售 ROE 高（杠杆）
        "revenue_growth": 8,
        "description": "非必需消费（零售/汽车/奢侈品）",
    },
    "Consumer Defensive": {
        "PE": 20,
        "ForwardPE": 18,
        "PS": 2.2,
        "PB": 8.0,
        "gross_margin": 45,
        "operating_margin": 18,
        "net_margin": 12,
        "ROE": 25,
        "revenue_growth": 5,
        "description": "必需消费（食品/饮料/日用品）",
    },
    "Energy": {
        "PE": 12,           # 能源股 PE 低（周期性）
        "ForwardPE": 11,
        "PS": 1.2,
        "PB": 2.2,
        "gross_margin": 35,
        "operating_margin": 18,
        "net_margin": 10,
        "ROE": 16,
        "revenue_growth": 6,
        "description": "能源（石油/天然气/煤炭）",
    },
    "Industrials": {
        "PE": 20,
        "ForwardPE": 18,
        "PS": 1.8,
        "PB": 5.5,
        "gross_margin": 35,
        "operating_margin": 15,
        "net_margin": 10,
        "ROE": 22,
        "revenue_growth": 7,
        "description": "工业（制造/航空/建筑）",
    },
    "Real Estate": {
        "PE": 35,           # REITs PE 高（折旧影响）
        "ForwardPE": 30,
        "PS": 5.5,
        "PB": 2.5,
        "gross_margin": 65,  # 物业毛利高
        "operating_margin": 35,
        "net_margin": 25,
        "ROE": 12,
        "revenue_growth": 6,
        "description": "房地产（REITs/开发）",
    },
    "Utilities": {
        "PE": 17,           # 公用事业 PE 低（稳定）
        "ForwardPE": 16,
        "PS": 2.5,
        "PB": 2.2,
        "gross_margin": 45,
        "operating_margin": 22,
        "net_margin": 14,
        "ROE": 11,          # ROE 低（重资产）
        "revenue_growth": 4,
        "description": "公用事业（电力/水务/燃气）",
    },
    "Basic Materials": {
        "PE": 17,
        "ForwardPE": 15,
        "PS": 1.5,
        "PB": 2.8,
        "gross_margin": 35,
        "operating_margin": 15,
        "net_margin": 11,
        "ROE": 15,
        "revenue_growth": 6,
        "description": "原材料（化工/金属/矿业）",
    },
}


# ============================================================
# A股/港股行业基准（近似值）
# ============================================================
# A股估值普遍高于美股，行业分类也有所不同

CN_SECTOR_BENCHMARKS = {
    # A股常见行业
    "白酒": {
        "PE": 35,
        "PB": 8.0,
        "gross_margin": 75,
        "net_margin": 35,
        "ROE": 28,
        "revenue_growth": 12,
        "description": "白酒（高端消费品）",
    },
    "银行": {
        "PE": 6,            # A股银行 PE 极低
        "PB": 0.6,          # 大面积破净
        "gross_margin": None,
        "net_margin": 35,
        "ROE": 11,
        "revenue_growth": 5,
        "description": "银行",
    },
    "保险": {
        "PE": 12,
        "PB": 1.5,
        "gross_margin": None,
        "net_margin": 12,
        "ROE": 13,
        "revenue_growth": 8,
        "description": "保险",
    },
    "证券": {
        "PE": 25,
        "PB": 2.0,
        "gross_margin": None,
        "net_margin": 30,
        "ROE": 8,
        "revenue_growth": 15,
        "description": "券商",
    },
    "医药生物": {
        "PE": 30,
        "PB": 4.5,
        "gross_margin": 70,
        "net_margin": 15,
        "ROE": 15,
        "revenue_growth": 15,
        "description": "医药生物",
    },
    "电子": {
        "PE": 35,
        "PB": 5.0,
        "gross_margin": 28,
        "net_margin": 10,
        "ROE": 14,
        "revenue_growth": 18,
        "description": "电子（半导体/消费电子）",
    },
    "计算机": {
        "PE": 50,           # 软件/IT服务 PE 高
        "PB": 6.0,
        "gross_margin": 55,
        "net_margin": 8,
        "ROE": 12,
        "revenue_growth": 20,
        "description": "计算机（软件/IT服务）",
    },
    "食品饮料": {
        "PE": 30,
        "PB": 6.5,
        "gross_margin": 45,
        "net_margin": 18,
        "ROE": 22,
        "revenue_growth": 10,
        "description": "食品饮料",
    },
    "家用电器": {
        "PE": 18,
        "PB": 3.5,
        "gross_margin": 30,
        "net_margin": 10,
        "ROE": 20,
        "revenue_growth": 8,
        "description": "家用电器",
    },
    "房地产": {
        "PE": 10,           # 地产股 PE 低（风险溢价）
        "PB": 0.8,          # 大面积破净
        "gross_margin": 30,
        "net_margin": 10,
        "ROE": 8,
        "revenue_growth": 5,
        "description": "房地产",
    },
    "电力设备": {
        "PE": 28,
        "PB": 4.0,
        "gross_margin": 28,
        "net_margin": 10,
        "ROE": 14,
        "revenue_growth": 20,
        "description": "电力设备（新能源/电池）",
    },
    "汽车": {
        "PE": 20,
        "PB": 3.0,
        "gross_margin": 22,
        "net_margin": 6,
        "ROE": 15,
        "revenue_growth": 12,
        "description": "汽车",
    },
    "钢铁": {
        "PE": 12,
        "PB": 1.2,
        "gross_margin": 15,
        "net_margin": 5,
        "ROE": 10,
        "revenue_growth": 5,
        "description": "钢铁",
    },
    "化工": {
        "PE": 18,
        "PB": 2.5,
        "gross_margin": 25,
        "net_margin": 10,
        "ROE": 14,
        "revenue_growth": 10,
        "description": "化工",
    },
    "建筑装饰": {
        "PE": 12,
        "PB": 1.5,
        "gross_margin": 18,
        "net_margin": 5,
        "ROE": 12,
        "revenue_growth": 8,
        "description": "建筑装饰",
    },
    # 港股默认用美股基准（因为港股多为大型蓝筹）
    "港股": {
        "PE": 15,
        "PB": 1.8,
        "gross_margin": 40,
        "net_margin": 15,
        "ROE": 14,
        "revenue_growth": 8,
        "description": "港股（综合）",
    },
}


def get_sector_benchmark(sector: str, market: str = "us") -> dict | None:
    """
    获取行业基准数据。

    参数:
        sector: 行业名称（GICS 英文 for US，中文 for CN）
        market: "us" | "cn" | "hk"

    返回:
        行业基准 dict，未找到返回 None
    """
    if market in ("cn", "hk"):
        # A股/港股：先尝试精确匹配，再尝试模糊匹配
        if sector in CN_SECTOR_BENCHMARKS:
            return CN_SECTOR_BENCHMARKS[sector]
        # 模糊匹配：如果 industry 包含关键词
        for key, benchmark in CN_SECTOR_BENCHMARKS.items():
            if key in sector or sector in key:
                return benchmark
        # 港股用美股基准作为 fallback
        if market == "hk":
            return _map_cn_to_us_sector(sector)
        return None
    else:
        # 美股：GICS 分类
        if sector in US_SECTOR_BENCHMARKS:
            return US_SECTOR_BENCHMARKS[sector]
        return None


def _map_cn_to_us_sector(cn_sector: str) -> dict | None:
    """将 A股行业映射到美股 GICS 基准（用于港股 fallback）"""
    mapping = {
        "银行": "Financial Services",
        "保险": "Financial Services",
        "证券": "Financial Services",
        "医药": "Healthcare",
        "生物": "Healthcare",
        "电子": "Technology",
        "计算机": "Technology",
        "软件": "Technology",
        "白酒": "Consumer Defensive",
        "食品": "Consumer Defensive",
        "饮料": "Consumer Defensive",
        "家电": "Consumer Cyclical",
        "汽车": "Consumer Cyclical",
        "房地产": "Real Estate",
        "电力": "Utilities",
        "钢铁": "Basic Materials",
        "化工": "Basic Materials",
        "建筑": "Industrials",
    }
    for key, us_sector in mapping.items():
        if key in cn_sector:
            return US_SECTOR_BENCHMARKS.get(us_sector)
    return None


def compare_to_benchmark(value: float, benchmark: float, metric_name: str) -> dict:
    """
    将个股指标与行业基准比较。

    返回:
        {
            "value": float,           # 个股值
            "benchmark": float,       # 行业基准
            "ratio": float,           # 个股/基准
            "assessment": str,        # 评价
            "signal_type": str,       # "bullish" | "bearish" | "neutral"
        }
    """
    if value is None or benchmark is None:
        return {
            "value": value,
            "benchmark": benchmark,
            "ratio": None,
            "assessment": "无法比较",
            "signal_type": "neutral",
        }

    ratio = value / benchmark

    # PE/ForwardPE/PS/PB: 低好（相对行业）
    if metric_name in ("PE", "ForwardPE", "PS", "PB"):
        if ratio < 0.7:
            assessment = f"显著低于行业均值（{ratio:.0%}）"
            signal_type = "bullish"
        elif ratio < 0.9:
            assessment = f"低于行业均值（{ratio:.0%}）"
            signal_type = "bullish"
        elif ratio < 1.1:
            assessment = f"接近行业均值（{ratio:.0%}）"
            signal_type = "neutral"
        elif ratio < 1.3:
            assessment = f"高于行业均值（{ratio:.0%}）"
            signal_type = "bearish"
        else:
            assessment = f"显著高于行业均值（{ratio:.0%}）"
            signal_type = "bearish"

    # 毛利率/净利率/ROE/营收增速: 高好
    elif metric_name in ("gross_margin", "operating_margin", "net_margin", "ROE", "revenue_growth"):
        if ratio > 1.3:
            assessment = f"显著高于行业均值（{ratio:.0%}）"
            signal_type = "bullish"
        elif ratio > 1.1:
            assessment = f"高于行业均值（{ratio:.0%}）"
            signal_type = "bullish"
        elif ratio > 0.9:
            assessment = f"接近行业均值（{ratio:.0%}）"
            signal_type = "neutral"
        elif ratio > 0.7:
            assessment = f"低于行业均值（{ratio:.0%}）"
            signal_type = "bearish"
        else:
            assessment = f"显著低于行业均值（{ratio:.0%}）"
            signal_type = "bearish"
    else:
        assessment = f"vs 行业 {ratio:.0%}"
        signal_type = "neutral"

    return {
        "value": value,
        "benchmark": benchmark,
        "ratio": ratio,
        "assessment": assessment,
        "signal_type": signal_type,
    }
