"""
拓扑基础接口和抽象类
定义拓扑生成的统一接口
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Dict, List, Set, Callable, Optional, Protocol, runtime_checkable
from dataclasses import dataclass
from functools import lru_cache

from ..core.types import (
    Coordinate, Direction, TopologyType, NodeType, NeighborMap,
    RouterName, Link, IPv6Network
)
from ..core.models import TopologyConfig, RouterInfo
from ..utils.functional import pipe, memoize

@runtime_checkable
class TopologyGenerator(Protocol):
    """拓扑生成器协议"""
    
    def get_neighbors(self, coord: Coordinate, size: int) -> NeighborMap:
        """获取指定坐标的邻居节点"""
        ...
    
    def get_node_type(self, coord: Coordinate, size: int) -> NodeType:
        """获取节点类型"""
        ...
    
    def calculate_total_links(self, size: int) -> int:
        """计算总链路数"""
        ...
    
    def validate_coordinate(self, coord: Coordinate, size: int) -> bool:
        """验证坐标是否有效"""
        ...

class BaseTopology(ABC):
    """拓扑基类"""
    
    def __init__(self, topology_type: TopologyType):
        self.topology_type = topology_type
    
    @abstractmethod
    def get_neighbors(self, coord: Coordinate, size: int) -> NeighborMap:
        """获取邻居节点 - 子类必须实现"""
        pass
    
    @abstractmethod
    def get_node_type(self, coord: Coordinate, size: int) -> NodeType:
        """获取节点类型 - 子类必须实现"""
        pass
    
    @abstractmethod
    def calculate_total_links(self, size: int) -> int:
        """计算总链路数 - 子类必须实现"""
        pass
    
    def validate_coordinate(self, coord: Coordinate, size: int) -> bool:
        """验证坐标是否在有效范围内"""
        return 0 <= coord.row < size and 0 <= coord.col < size
    
    @memoize
    def get_all_coordinates(self, size: int) -> List[Coordinate]:
        """获取所有有效坐标"""
        return [
            Coordinate(row=row, col=col)
            for row in range(size)
            for col in range(size)
        ]
    
    @memoize
    def get_boundary_coordinates(self, size: int) -> Set[Coordinate]:
        """获取边界坐标"""
        boundary = set()
        for i in range(size):
            boundary.add(Coordinate(row=0, col=i))      # 上边界
            boundary.add(Coordinate(row=size-1, col=i)) # 下边界
            boundary.add(Coordinate(row=i, col=0))      # 左边界
            boundary.add(Coordinate(row=i, col=size-1)) # 右边界
        return boundary
    
    @memoize
    def get_corner_coordinates(self, size: int) -> Set[Coordinate]:
        """获取角点坐标"""
        return {
            Coordinate(row=0, col=0),
            Coordinate(row=0, col=size-1),
            Coordinate(row=size-1, col=0),
            Coordinate(row=size-1, col=size-1)
        }
    
    def get_internal_coordinates(self, size: int) -> Set[Coordinate]:
        """获取内部坐标"""
        all_coords = set(self.get_all_coordinates(size))
        boundary_coords = self.get_boundary_coordinates(size)
        return all_coords - boundary_coords
    
    def get_edge_coordinates(self, size: int) -> Set[Coordinate]:
        """获取边缘坐标（非角点的边界点）"""
        boundary_coords = self.get_boundary_coordinates(size)
        corner_coords = self.get_corner_coordinates(size)
        return boundary_coords - corner_coords

# 方向计算工具函数
def calculate_direction(from_coord: Coordinate, to_coord: Coordinate) -> Optional[Direction]:
    """计算从一个坐标到另一个坐标的方向"""
    row_diff = to_coord.row - from_coord.row
    col_diff = to_coord.col - from_coord.col

    # 只处理相邻的坐标
    if abs(row_diff) + abs(col_diff) != 1:
        return None

    if row_diff == -1:
        return Direction.NORTH
    elif row_diff == 1:
        return Direction.SOUTH
    elif col_diff == -1:
        return Direction.WEST
    elif col_diff == 1:
        return Direction.EAST

    return None

def get_neighbor_in_direction(coord: Coordinate, direction: Direction, size: int) -> Optional[Coordinate]:
    """获取指定方向的邻居坐标"""
    # 直接计算新坐标，避免创建可能无效的中间坐标
    vector = direction.vector
    new_row = coord.row + vector.row
    new_col = coord.col + vector.col

    # 检查边界
    if 0 <= new_row < size and 0 <= new_col < size:
        return Coordinate(new_row, new_col)

    return None

def get_torus_neighbor_in_direction(coord: Coordinate, direction: Direction, size: int) -> Coordinate:
    """获取Torus拓扑中指定方向的邻居坐标（环绕）"""
    # 直接计算新坐标，避免创建可能无效的中间坐标
    vector = direction.vector
    new_row = coord.row + vector.row
    new_col = coord.col + vector.col

    # Torus环绕 - 处理负值
    wrapped_row = new_row % size
    wrapped_col = new_col % size

    return Coordinate(wrapped_row, wrapped_col)

# 链路生成工具
@dataclass(frozen=True)
class LinkBuilder:
    """链路构建器"""
    
    @staticmethod
    def create_link(
        coord1: Coordinate,
        coord2: Coordinate,
        direction1: Direction,
        direction2: Direction,
        network: IPv6Network
    ) -> Link:
        """创建链路"""
        return Link(
            router1=coord1,
            router2=coord2,
            direction1=direction1,
            direction2=direction2,
            network=network
        )
    
    @staticmethod
    def create_bidirectional_links(
        coord1: Coordinate,
        coord2: Coordinate,
        network: IPv6Network
    ) -> Optional[Link]:
        """创建双向链路"""
        direction1 = calculate_direction(coord1, coord2)
        direction2 = calculate_direction(coord2, coord1)
        
        if direction1 is None or direction2 is None:
            return None
        
        return LinkBuilder.create_link(coord1, coord2, direction1, direction2, network)

# 邻居映射工具
class NeighborMapper:
    """邻居映射工具类"""
    
    @staticmethod
    def build_neighbor_map(
        coord: Coordinate,
        size: int,
        neighbor_func: Callable[[Coordinate, Direction, int], Optional[Coordinate]]
    ) -> NeighborMap:
        """构建邻居映射"""
        neighbors = {}
        
        for direction in Direction:
            neighbor_coord = neighbor_func(coord, direction, size)
            if neighbor_coord is not None:
                neighbors[direction] = neighbor_coord
        
        return neighbors
    
    @staticmethod
    def filter_valid_neighbors(
        neighbors: NeighborMap,
        validator: Callable[[Coordinate], bool]
    ) -> NeighborMap:
        """过滤有效邻居"""
        return {
            direction: coord
            for direction, coord in neighbors.items()
            if validator(coord)
        }

# 节点类型判断工具
class NodeTypeClassifier:
    """节点类型分类器"""
    
    @staticmethod
    def classify_grid_node(coord: Coordinate, size: int) -> NodeType:
        """分类Grid节点类型"""
        if coord in {Coordinate(0, 0), Coordinate(0, size-1), 
                     Coordinate(size-1, 0), Coordinate(size-1, size-1)}:
            return NodeType.CORNER
        elif (coord.row == 0 or coord.row == size-1 or 
              coord.col == 0 or coord.col == size-1):
            return NodeType.EDGE
        else:
            return NodeType.INTERNAL
    
    @staticmethod
    def classify_torus_node(coord: Coordinate, size: int) -> NodeType:
        """分类Torus节点类型（所有节点都是内部节点）"""
        return NodeType.INTERNAL
    
    @staticmethod
    def classify_special_node(
        coord: Coordinate,
        source_node: Coordinate,
        dest_node: Coordinate,
        gateway_nodes: Set[Coordinate]
    ) -> NodeType:
        """分类Special节点类型"""
        if coord == source_node:
            return NodeType.SOURCE
        elif coord == dest_node:
            return NodeType.DESTINATION
        elif coord in gateway_nodes:
            return NodeType.GATEWAY
        else:
            return NodeType.INTERNAL

# 拓扑验证器
class TopologyValidator:
    """拓扑验证器"""
    
    @staticmethod
    def validate_size(size: int) -> bool:
        """验证网格大小"""
        return 2 <= size <= 100
    
    @staticmethod
    def validate_coordinates(coords: List[Coordinate], size: int) -> bool:
        """验证坐标列表"""
        return all(
            0 <= coord.row < size and 0 <= coord.col < size
            for coord in coords
        )
    
    @staticmethod
    def validate_neighbor_map(neighbors: NeighborMap, size: int) -> bool:
        """验证邻居映射"""
        return TopologyValidator.validate_coordinates(list(neighbors.values()), size)
    
    @staticmethod
    def validate_topology_config(config: TopologyConfig) -> List[str]:
        """验证拓扑配置"""
        errors = []
        
        if not TopologyValidator.validate_size(config.size):
            errors.append(f"无效的网格大小: {config.size}")
        
        if config.special_config:
            special = config.special_config
            coords_to_check = [special.source_node, special.dest_node] + list(special.gateway_nodes)
            
            if not TopologyValidator.validate_coordinates(coords_to_check, config.size):
                errors.append("Special配置中包含无效坐标")
        
        return errors

# 拓扑工厂
class TopologyFactory:
    """拓扑工厂"""
    
    _registry: Dict[TopologyType, type] = {}
    
    @classmethod
    def register(cls, topology_type: TopologyType, topology_class: type):
        """注册拓扑类型"""
        cls._registry[topology_type] = topology_class
    
    @classmethod
    def create(cls, topology_type: TopologyType) -> BaseTopology:
        """创建拓扑实例"""
        if topology_type not in cls._registry:
            raise ValueError(f"未注册的拓扑类型: {topology_type}")
        
        topology_class = cls._registry[topology_type]
        return topology_class(topology_type)
