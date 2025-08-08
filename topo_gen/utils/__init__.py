"""
简化的工具模块初始化
导出基本的函数式编程工具
"""

from .functional import (
    # 基础函数
    pipe, compose, memoize,

    # 映射和过滤
    map_values, map_keys, filter_dict,

    # 列表操作
    flatten, unique, groupby, partition,

    # 批处理和工具
    batched, safe_get, deep_merge, when, try_call
)

__all__ = [
    # 基础函数
    'pipe', 'compose', 'memoize',

    # 映射和过滤
    'map_values', 'map_keys', 'filter_dict',

    # 列表操作
    'flatten', 'unique', 'groupby', 'partition',

    # 批处理和工具
    'batched', 'safe_get', 'deep_merge', 'when', 'try_call'
]
