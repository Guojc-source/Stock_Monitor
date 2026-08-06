"""
数据缓存模块
============
将 yfinance 拉取的数据缓存到本地，避免重复请求触发限流。

策略：
- 日线数据：缓存 30 分钟（日线不会实时变化）
- 实时信息（info）：缓存 5 分钟
- 基本面数据：缓存 24 小时（财报数据不会频繁变）
"""

import json
import os
import time
import hashlib
from pathlib import Path

CACHE_DIR = Path(__file__).parent / ".cache"


def _ensure_cache_dir():
    CACHE_DIR.mkdir(exist_ok=True)


def _cache_key(prefix: str, *args) -> str:
    """生成缓存键"""
    raw = prefix + "|" + "|".join(str(a) for a in args)
    return hashlib.md5(raw.encode()).hexdigest()[:16]


def get_cached(cache_type: str, *keys, max_age_seconds: int = 1800) -> dict | None:
    """
    读取缓存。

    参数:
        cache_type: 缓存类型（如 "history", "info", "fundamentals"）
        keys: 标识键（如 symbol, period, interval）
        max_age_seconds: 最大有效期（秒）

    返回:
        None = 缓存未命中，dict = 缓存数据
    """
    _ensure_cache_dir()
    key = _cache_key(cache_type, *keys)
    cache_file = CACHE_DIR / f"{key}.json"

    if not cache_file.exists():
        return None

    try:
        with open(cache_file) as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        return None

    age = time.time() - data.get("_cached_at", 0)
    if age > max_age_seconds:
        return None

    return data


def set_cache(cache_type: str, data: dict, *keys) -> None:
    """写入缓存"""
    _ensure_cache_dir()
    key = _cache_key(cache_type, *keys)
    cache_file = CACHE_DIR / f"{key}.json"

    # 只缓存可序列化的字段
    cacheable = {}
    for k, v in data.items():
        try:
            json.dumps({k: v})  # 测试可序列化
            cacheable[k] = v
        except (TypeError, ValueError):
            cacheable[k] = str(v)

    cacheable["_cached_at"] = time.time()

    try:
        with open(cache_file, "w") as f:
            json.dump(cacheable, f, indent=2)
    except OSError:
        pass


def clear_expired_cache():
    """清理过期缓存文件"""
    _ensure_cache_dir()
    now = time.time()
    for f in CACHE_DIR.glob("*.json"):
        try:
            age = now - f.stat().st_mtime
            if age > 86400 * 7:  # 7天前的缓存
                f.unlink()
        except OSError:
            pass


def cache_status() -> dict:
    """缓存状态"""
    _ensure_cache_dir()
    files = list(CACHE_DIR.glob("*.json"))
    total_size = sum(f.stat().st_size for f in files)
    return {
        "files": len(files),
        "size_kb": round(total_size / 1024, 1),
    }
