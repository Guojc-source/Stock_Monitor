"""
Watchlist Loader
================
Load stock symbols from external configuration files.
Supports JSON (grouped) and plain text formats, with automatic
name-to-ticker resolution via ticker_alias module.

Priority: watchlist.json > watchlist.txt > config.py SYMBOLS
"""

import json
import os
from pathlib import Path


# 默认搜索路径（相对于项目根目录）
_WATCHLIST_FILES = [
    "watchlist.json",
    "watchlist.txt",
]


def _project_root() -> Path:
    """获取项目根目录"""
    return Path(__file__).parent


def load_watchlist(file_path: str = None, resolve_aliases: bool = True, verbose: bool = True) -> list[str]:
    """
    加载自选股列表。

    参数:
        file_path: 指定文件路径。为 None 时自动搜索项目根目录下的
                   watchlist.json → watchlist.txt → 回退到 config.SYMBOLS
        resolve_aliases: 是否将名称（如"微软""腾讯"）自动解析为代码
        verbose: 是否打印别名解析日志

    返回:
        股票代码列表（去重、去空、去注释、别名已解析）
    """
    root = _project_root()

    # 1. 指定路径
    if file_path:
        raw = _load_file(Path(file_path))
    else:
        raw = None
        # 2. 自动搜索
        for fname in _WATCHLIST_FILES:
            fpath = root / fname
            if fpath.exists():
                raw = _load_file(fpath)
                if raw:
                    break

        # 3. 回退到 config.py
        if not raw:
            from config import SYMBOLS
            raw = list(SYMBOLS)

    # 4. 别名解析（名称 → 代码）
    if resolve_aliases and raw:
        from ticker_alias import resolve_symbols
        resolved, mapping = resolve_symbols(raw, verbose=verbose)
        return resolved

    return raw


def _load_file(path: Path) -> list[str]:
    """根据文件扩展名选择解析器"""
    suffix = path.suffix.lower()
    if suffix == ".json":
        return _parse_json(path)
    elif suffix == ".txt":
        return _parse_txt(path)
    else:
        raise ValueError(f"不支持的配置文件格式: {suffix}（仅支持 .json 和 .txt）")


def _parse_json(path: Path) -> list[str]:
    """
    解析 JSON 格式的 watchlist。

    支持两种结构：
    A) 分组式: {"core_index": [...], "satellite": [...], ...}
    B) 扁平式: ["MSFT", "AAPL", ...]
    """
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    symbols = []

    if isinstance(data, list):
        # 扁平式
        symbols = [s.strip() for s in data if isinstance(s, str) and s.strip()]
    elif isinstance(data, dict):
        # 分组式 — 按组展开
        for group_name, group_symbols in data.items():
            if group_name.startswith("_"):
                continue  # 跳过以 _ 开头的元数据字段
            if isinstance(group_symbols, list):
                for s in group_symbols:
                    if isinstance(s, str) and s.strip():
                        symbols.append(s.strip())
    else:
        raise ValueError(f"watchlist.json 格式错误：需要 JSON 数组或对象")

    return _deduplicate(symbols)


def _parse_txt(path: Path) -> list[str]:
    """
    解析纯文本格式的 watchlist。
    每行一个代码，# 开头为注释，空行跳过。
    """
    symbols = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or line.startswith("//"):
                continue
            # 支持行内注释: "MSFT  # 微软"
            code = line.split("#")[0].split("//")[0].strip()
            if code:
                symbols.append(code)
    return _deduplicate(symbols)


def _deduplicate(symbols: list[str]) -> list[str]:
    """去重，保持顺序"""
    seen = set()
    result = []
    for s in symbols:
        upper = s.upper()
        if upper not in seen:
            seen.add(upper)
            result.append(s)
    return result


def get_watchlist_source_info(file_path: str = None) -> dict:
    """
    返回当前 watchlist 的来源信息（用于报告头部展示）。

    返回:
        {"source": "watchlist.json", "path": "/abs/path", "count": 12}
    """
    root = _project_root()

    if file_path:
        p = Path(file_path)
        return {
            "source": p.name,
            "path": str(p.resolve()),
            "count": len(load_watchlist(file_path)),
        }

    for fname in _WATCHLIST_FILES:
        fpath = root / fname
        if fpath.exists():
            return {
                "source": fname,
                "path": str(fpath.resolve()),
                "count": len(load_watchlist()),
            }

    return {
        "source": "config.py SYMBOLS",
        "path": str(root / "config.py"),
        "count": len(load_watchlist()),
    }


def create_example_watchlist(output_path: str = None) -> str:
    """
    生成示例 watchlist.json 文件。
    返回写入的文件路径。
    """
    if output_path is None:
        output_path = str(_project_root() / "watchlist.json")

    example = {
        "_说明": "自选股配置文件 — 支持股票代码或公司名称（中英文均可）",
        "_示例": [
            "代码: MSFT, 0700.HK, 600519.SS",
            "英文名: Microsoft, Apple, Tesla",
            "中文名: 微软, 腾讯, 茅台",
            "混合使用: ['微软', 'NVDA', '腾讯', 0700.HK] 都可以",
        ],
        "_用法": [
            "1. 直接编辑此文件，添加/删除股票代码或名称",
            "2. python3.12 main.py — 分析所有股票",
            "3. python3.12 main.py -s 微软 — 分析单只（名称也行）",
            "4. python3.12 main.py --sector — 行业轮动排名",
            "5. python3.12 main.py --market-status — 大盘状态灯",
        ],
        "core_index": [
            "SPY",
            "QQQ",
            "IWM"
        ],
        "mag7": [
            "微软",
            "苹果",
            "英伟达",
            "谷歌",
            "亚马逊",
            "META",
            "特斯拉"
        ],
        "sector_etf": [
            "XLK",
            "XLF",
            "XLE",
            "XLV",
            "XLY",
            "XLI"
        ],
        "hk": [
            "腾讯",
            "阿里"
        ]
    }

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(example, f, indent=2, ensure_ascii=False)

    return output_path
