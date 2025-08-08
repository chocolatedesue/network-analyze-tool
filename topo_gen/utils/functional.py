"""
简化的工具函数
提供基本的函数式编程特性，不依赖第三方库
"""

from __future__ import annotations

from typing import TypeVar, Callable, Iterable, Dict, List, Optional, Any
from functools import wraps, partial, reduce
from itertools import chain
import itertools

T = TypeVar('T')
U = TypeVar('U')

# 基本的管道操作
def pipe(value: T, *functions: Callable[[Any], Any]) -> Any:
    """管道操作：将值通过一系列函数传递"""
    result = value
    for func in functions:
        result = func(result)
    return result

# 简单的函数组合
def compose(*functions: Callable[[Any], Any]) -> Callable[[Any], Any]:
    """函数组合：从右到左组合函数"""
    def composed(x):
        result = x
        for func in reversed(functions):
            result = func(result)
        return result
    return composed

# 简化的记忆化装饰器
def memoize(func: Callable[..., T]) -> Callable[..., T]:
    """记忆化装饰器"""
    cache: Dict[Any, T] = {}

    @wraps(func)
    def memoized(*args, **kwargs):
        # 简单的缓存键
        key = str(args) + str(sorted(kwargs.items()))
        if key not in cache:
            cache[key] = func(*args, **kwargs)
        return cache[key]

    return memoized

# 分组函数
def groupby(key_func: Callable[[T], U], iterable: Iterable[T]) -> Dict[U, List[T]]:
    """按键函数分组"""
    result: Dict[U, List[T]] = {}
    for item in iterable:
        key = key_func(item)
        if key not in result:
            result[key] = []
        result[key].append(item)
    return result

# 映射函数
def map_values(func: Callable[[T], U], mapping: Dict[Any, T]) -> Dict[Any, U]:
    """对字典的值应用函数"""
    return {k: func(v) for k, v in mapping.items()}

def map_keys(func: Callable[[T], U], mapping: Dict[T, Any]) -> Dict[U, Any]:
    """对字典的键应用函数"""
    return {func(k): v for k, v in mapping.items()}

# 过滤函数
def filter_dict(predicate: Callable[[Any, Any], bool], mapping: Dict[Any, Any]) -> Dict[Any, Any]:
    """过滤字典"""
    return {k: v for k, v in mapping.items() if predicate(k, v)}

# 扁平化函数
def flatten(nested_iterable: Iterable[Iterable[T]]) -> List[T]:
    """扁平化嵌套可迭代对象"""
    return list(chain.from_iterable(nested_iterable))

# 分区函数
def partition(predicate: Callable[[T], bool], iterable: Iterable[T]) -> tuple[List[T], List[T]]:
    """根据谓词分区"""
    true_items, false_items = [], []
    for item in iterable:
        (true_items if predicate(item) else false_items).append(item)
    return true_items, false_items

# 唯一化函数
def unique(iterable: Iterable[T], key: Optional[Callable[[T], Any]] = None) -> List[T]:
    """去重，保持顺序"""
    seen = set()
    result = []
    for item in iterable:
        k = key(item) if key else item
        if k not in seen:
            seen.add(k)
            result.append(item)
    return result

# 批处理函数
def batched(iterable: Iterable[T], batch_size: int) -> List[List[T]]:
    """将可迭代对象分批"""
    iterator = iter(iterable)
    result = []
    while True:
        batch = list(itertools.islice(iterator, batch_size))
        if not batch:
            break
        result.append(batch)
    return result

# 安全获取函数
def safe_get(mapping: Dict[Any, T], key: Any, default: Optional[T] = None) -> Optional[T]:
    """安全获取字典值"""
    return mapping.get(key, default)

# 深度合并字典
def deep_merge(dict1: Dict[Any, Any], dict2: Dict[Any, Any]) -> Dict[Any, Any]:
    """深度合并两个字典"""
    result = dict1.copy()
    for key, value in dict2.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = value
    return result

# 条件执行
def when(condition: bool, func: Callable[[T], U], value: T) -> T | U:
    """条件执行函数"""
    return func(value) if condition else value

# 尝试执行
def try_call(func: Callable[[], T], default: T) -> T:
    """尝试调用函数，失败时返回默认值"""
    try:
        return func()
    except Exception:
        return default


