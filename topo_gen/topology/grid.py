"""
Grid拓扑实现
规则的网格拓扑，节点只与相邻的节点连接
"""

from __future__ import annotations

from typing import Dict, List, Set, Optional
from functools import lru_cache

from ..core.types import Coordinate, Direction, NodeType, NeighborMap
from ..utils.functional import pipe, memoize
from .base import (
    BaseTopology, TopologyFactory, NeighborMapper, NodeTypeClassifier,
    get_neighbor_in_direction, calculate_direction
)

class GridTopology(BaseTopology):
    """Grid拓扑实现"""
    
    def __init__(self, topology_type):
        super().__init__(topology_type)
    
    @memoize
    def get_neighbors(self, coord: Coordinate, size: int) -> NeighborMap:
        """获取Grid拓扑中的邻居节点
        
        Grid拓扑中，每个节点只与上下左右相邻的节点连接
        边界节点的邻居数量会减少
        """
        return NeighborMapper.build_neighbor_map(
            coord,
            size,
            get_neighbor_in_direction
        )
    
    def get_node_type(self, coord: Coordinate, size: int) -> NodeType:
        """获取Grid节点类型
        
        - 角点: 4个角落的节点
        - 边缘: 边界上的非角点节点
        - 内部: 其他所有节点
        """
        return NodeTypeClassifier.classify_grid_node(coord, size)
    
    def calculate_total_links(self, size: int) -> int:
        """计算Grid拓扑的总链路数
        
        公式: 2 * size * (size - 1)
        - 水平链路: (size - 1) * size
        - 垂直链路: size * (size - 1)
        """
        return 2 * size * (size - 1)
    
    @lru_cache(maxsize=128)
    def get_neighbor_count(self, coord: Coordinate, size: int) -> int:
        """获取指定坐标的邻居数量"""
        return len(self.get_neighbors(coord, size))
    
    def get_nodes_by_type(self, size: int) -> Dict[NodeType, Set[Coordinate]]:
        """按类型分组获取所有节点"""
        nodes_by_type = {
            NodeType.CORNER: set(),
            NodeType.EDGE: set(),
            NodeType.INTERNAL: set()
        }
        
        for row in range(size):
            for col in range(size):
                coord = Coordinate(row=row, col=col)
                node_type = self.get_node_type(coord, size)
                nodes_by_type[node_type].add(coord)
        
        return nodes_by_type
    
    def get_connectivity_stats(self, size: int) -> Dict[str, int]:
        """获取连通性统计信息"""
        nodes_by_type = self.get_nodes_by_type(size)
        
        return {
            'total_nodes': size * size,
            'total_links': self.calculate_total_links(size),
            'corner_nodes': len(nodes_by_type[NodeType.CORNER]),
            'edge_nodes': len(nodes_by_type[NodeType.EDGE]),
            'internal_nodes': len(nodes_by_type[NodeType.INTERNAL]),
            'avg_degree': self.calculate_total_links(size) * 2 / (size * size),
            'max_degree': 4,  # Grid中最大度数为4
            'min_degree': 2 if size > 1 else 0,  # 角点的度数为2
        }
    
    def is_connected(self, size: int) -> bool:
        """检查拓扑是否连通"""
        # Grid拓扑在size >= 1时总是连通的
        return size >= 1
    
    def get_diameter(self, size: int) -> int:
        """获取网络直径（最短路径的最大值）"""
        # Grid拓扑的直径是从一个角到对角的距离
        return 2 * (size - 1)
    
    def get_shortest_path_length(self, coord1: Coordinate, coord2: Coordinate) -> int:
        """计算两点间的最短路径长度（曼哈顿距离）"""
        return abs(coord1.row - coord2.row) + abs(coord1.col - coord2.col)
    
    def get_all_shortest_paths(
        self, 
        coord1: Coordinate, 
        coord2: Coordinate
    ) -> List[List[Coordinate]]:
        """获取两点间的所有最短路径"""
        if coord1 == coord2:
            return [[coord1]]
        
        paths = []
        row_diff = coord2.row - coord1.row
        col_diff = coord2.col - coord1.col
        
        def generate_paths(current: Coordinate, target: Coordinate, path: List[Coordinate]):
            if current == target:
                paths.append(path + [current])
                return
            
            # 只向目标方向移动
            if current.row < target.row:
                generate_paths(
                    Coordinate(row=current.row + 1, col=current.col),
                    target,
                    path + [current]
                )
            if current.row > target.row:
                generate_paths(
                    Coordinate(row=current.row - 1, col=current.col),
                    target,
                    path + [current]
                )
            if current.col < target.col:
                generate_paths(
                    Coordinate(row=current.row, col=current.col + 1),
                    target,
                    path + [current]
                )
            if current.col > target.col:
                generate_paths(
                    Coordinate(row=current.row, col=current.col - 1),
                    target,
                    path + [current]
                )
        
        generate_paths(coord1, coord2, [])
        return paths
    
    def get_boundary_links(self, size: int) -> List[tuple[Coordinate, Coordinate]]:
        """获取所有边界链路"""
        boundary_links = []
        
        # 水平边界链路
        for row in [0, size - 1]:
            for col in range(size - 1):
                coord1 = Coordinate(row=row, col=col)
                coord2 = Coordinate(row=row, col=col + 1)
                boundary_links.append((coord1, coord2))

        # 垂直边界链路
        for col in [0, size - 1]:
            for row in range(size - 1):
                coord1 = Coordinate(row=row, col=col)
                coord2 = Coordinate(row=row + 1, col=col)
                boundary_links.append((coord1, coord2))
        
        return boundary_links
    
    def get_internal_links(self, size: int) -> List[tuple[Coordinate, Coordinate]]:
        """获取所有内部链路"""
        internal_links = []
        
        # 水平内部链路
        for row in range(1, size - 1):
            for col in range(size - 1):
                coord1 = Coordinate(row=row, col=col)
                coord2 = Coordinate(row=row, col=col + 1)
                internal_links.append((coord1, coord2))

        # 垂直内部链路
        for col in range(1, size - 1):
            for row in range(size - 1):
                coord1 = Coordinate(row=row, col=col)
                coord2 = Coordinate(row=row + 1, col=col)
                internal_links.append((coord1, coord2))
        
        return internal_links
    
    def validate_grid_properties(self, size: int) -> List[str]:
        """验证Grid拓扑的属性"""
        errors = []
        
        # 验证节点数量
        expected_nodes = size * size
        actual_nodes = len(self.get_all_coordinates(size))
        if actual_nodes != expected_nodes:
            errors.append(f"节点数量不匹配: 期望{expected_nodes}, 实际{actual_nodes}")
        
        # 验证链路数量
        expected_links = self.calculate_total_links(size)
        actual_links = 0
        for coord in self.get_all_coordinates(size):
            actual_links += len(self.get_neighbors(coord, size))
        actual_links //= 2  # 每条链路被计算了两次
        
        if actual_links != expected_links:
            errors.append(f"链路数量不匹配: 期望{expected_links}, 实际{actual_links}")
        
        # 验证连通性
        if not self.is_connected(size):
            errors.append("拓扑不连通")
        
        return errors

# 注册Grid拓扑
TopologyFactory.register('grid', GridTopology)

# 导出Grid拓扑相关的工具函数
def create_grid_topology() -> GridTopology:
    """创建Grid拓扑实例"""
    return GridTopology('grid')

def get_grid_neighbors(size: int):
    """获取Grid邻居计算函数"""
    topology = create_grid_topology()
    return lambda coord: topology.get_neighbors(coord, size)

def get_grid_node_type(size: int):
    """获取Grid节点类型判断函数"""
    topology = create_grid_topology()
    return lambda coord: topology.get_node_type(coord, size)

def calculate_grid_stats(size: int) -> Dict[str, int]:
    """计算Grid拓扑统计信息"""
    topology = create_grid_topology()
    return topology.get_connectivity_stats(size)

def validate_grid_topology(size: int) -> List[str]:
    """验证Grid拓扑"""
    topology = create_grid_topology()
    return topology.validate_grid_properties(size)
