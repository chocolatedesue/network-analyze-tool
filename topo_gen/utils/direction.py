from __future__ import annotations

from typing import Optional

from ..core.types import Coordinate, Direction


def calculate_direction(from_coord: Coordinate, to_coord: Coordinate, size: int = 6) -> Optional[Direction]:
    """计算从一个坐标到另一个坐标的方向。
    扩展支持：
    - 标准相邻方向
    - Torus 环绕方向（基于 size）
    - 非相邻（桥接）时选择主导方向
    """
    row_diff = to_coord.row - from_coord.row
    col_diff = to_coord.col - from_coord.col

    # 标准相邻方向
    if row_diff == -1 and col_diff == 0:
        return Direction.NORTH
    elif row_diff == 1 and col_diff == 0:
        return Direction.SOUTH
    elif row_diff == 0 and col_diff == -1:
        return Direction.WEST
    elif row_diff == 0 and col_diff == 1:
        return Direction.EAST

    # Torus环绕（动态处理任意大小网格）
    wrap_distance = size - 1

    # 北-南环绕：选择更短的路径
    if row_diff == wrap_distance and col_diff == 0:
        return Direction.NORTH
    elif row_diff == -wrap_distance and col_diff == 0:
        return Direction.SOUTH

    # 东-西环绕：选择更短的路径
    if row_diff == 0 and col_diff == wrap_distance:
        return Direction.WEST
    elif row_diff == 0 and col_diff == -wrap_distance:
        return Direction.EAST

    # 对角连接（Torus桥接或特殊连接），选择主导方向
    if abs(row_diff) > 1 or abs(col_diff) > 1:
        if abs(row_diff) >= abs(col_diff):
            return Direction.NORTH if row_diff < 0 else Direction.SOUTH
        else:
            return Direction.WEST if col_diff < 0 else Direction.EAST

    return None

