"""
简化的拓扑生成引擎
使用anyio和简单的异步编程模式
"""

from __future__ import annotations

from typing import List
from pathlib import Path
import anyio

from .core.types import Coordinate, Direction, NeighborMap, Failure
from .core.models import (
    TopologyConfig, RouterInfo, SystemRequirements, GenerationResult,
    NetworkConfig, NodeType
)
from .filesystem import (
    create_all_directories, create_all_template_files,
    generate_all_config_files, generate_clab_yaml
)
from .links import generate_interface_mappings, convert_links_to_clab_format, generate_loopback_ipv6
from .topology.special import filter_routers_for_special_topology
from .utils.topo import get_topology_type_str


class TopologyEngine:
    """拓扑生成引擎"""
    
    def __init__(self):
        self.network_config = NetworkConfig()
    
    async def generate_topology(self, config: TopologyConfig) -> GenerationResult:
        """生成完整拓扑"""
        try:
            # 1. 生成路由器信息
            routers = self._generate_routers(config)

            # 对于Special拓扑，只保留有连接的路由器
            topo_type = get_topology_type_str(config.topology_type)
            if topo_type == "special" and config.special_config:
                routers = filter_routers_for_special_topology(routers, config.special_config)
            
            # 2. 计算系统需求
            requirements = SystemRequirements.calculate_for_topology(config)
            
            # 3. 创建目录结构
            base_dir = self._get_output_dir(config)
            dir_result = await create_all_directories(config, routers, requirements)
            if isinstance(dir_result, Failure):
                return GenerationResult(
                    success=False,
                    message=f"目录创建失败: {dir_result.error}"
                )
            
            # 4. 创建模板文件
            template_result = await create_all_template_files(routers, requirements, base_dir, config)
            if isinstance(template_result, Failure):
                return GenerationResult(
                    success=False,
                    message=f"模板创建失败: {template_result.error}"
                )
            
            # 5. 生成接口地址映射
            interface_mappings = generate_interface_mappings(config, routers)
            
            # 6. 生成配置文件
            config_result = await generate_all_config_files(
                config, routers, interface_mappings, requirements, base_dir
            )
            if isinstance(config_result, Failure):
                return GenerationResult(
                    success=False,
                    message=f"配置生成失败: {config_result.error}"
                )
            
            # 7. 生成ContainerLab YAML
            links = convert_links_to_clab_format(config, routers)
            yaml_result = await generate_clab_yaml(config, routers, links, base_dir)
            if isinstance(yaml_result, Failure):
                return GenerationResult(
                    success=False,
                    message=f"YAML生成失败: {yaml_result.error}"
                )
            
            return GenerationResult(
                success=True,
                message="拓扑生成成功",
                output_dir=base_dir,
                stats={
                    "total_routers": len(routers),
                    "total_links": len(links),
                    "topology_type": get_topology_type_str(config.topology_type),
                    "size": config.size
                }
            )
            
        except Exception as e:
            return GenerationResult(
                success=False,
                message=f"生成失败: {str(e)}",
                error_details=str(e)
            )
    
    def _generate_routers(self, config: TopologyConfig) -> List[RouterInfo]:
        """生成路由器信息"""
        routers = []
        
        for row in range(config.size):
            for col in range(config.size):
                coord = Coordinate(row, col)
                router = self._create_router_info(coord, config)
                routers.append(router)
        
        return routers
    
    def _create_router_info(self, coord: Coordinate, config: TopologyConfig) -> RouterInfo:
        """创建单个路由器信息"""
        router_name = f"router_{coord.row:02d}_{coord.col:02d}"
        router_id = f"10.{coord.row}.{coord.col}.1"

        # 计算区域ID
        area_id = self._calculate_area_id(coord, config)
        area_id_int = int(area_id.split('.')[0]) if area_id != "0.0.0.0" else 0

        loopback_ipv6 = generate_loopback_ipv6(area_id_int, coord)
        
        # 确定节点类型
        node_type = self._get_node_type(coord, config)
        
        # 获取邻居信息
        neighbors = self._get_neighbors(coord, config)
        
        # 确定区域ID
        area_id = self._calculate_area_id(coord, config)
        
        # 确定AS号（如果启用BGP）
        as_number = None
        if config.enable_bgp and config.bgp_config:
            as_number = self._calculate_as_number(coord, config)
        
        return RouterInfo(
            name=router_name,
            coordinate=coord,
            node_type=node_type,
            router_id=router_id,
            loopback_ipv6=loopback_ipv6,
            interfaces={},  # 稍后填充
            neighbors=neighbors,
            area_id=area_id,
            as_number=as_number
        )
    
    def _get_node_type(self, coord: Coordinate, config: TopologyConfig) -> NodeType:
        """获取节点类型"""
        topo_type = get_topology_type_str(config.topology_type)
        if topo_type == "grid":
            return self._get_grid_node_type(coord, config.size)
        elif topo_type == "torus":
            return NodeType.INTERNAL  # Torus中所有节点都是内部节点
        elif topo_type == "special" and config.special_config:
            return self._get_special_node_type(coord, config.special_config)
        else:
            return NodeType.INTERNAL

    def _get_special_node_type(self, coord: Coordinate, special_config) -> NodeType:
        """获取Special拓扑的节点类型"""
        if coord == special_config.source_node:
            return NodeType.SOURCE
        elif coord == special_config.dest_node:
            return NodeType.DESTINATION
        elif coord in special_config.gateway_nodes:
            return NodeType.GATEWAY
        else:
            return NodeType.INTERNAL
    
    def _get_grid_node_type(self, coord: Coordinate, size: int) -> NodeType:
        """获取Grid节点类型"""
        row, col = coord.row, coord.col
        
        # 角点
        if (row, col) in [(0, 0), (0, size-1), (size-1, 0), (size-1, size-1)]:
            return NodeType.CORNER
        # 边缘
        elif row == 0 or row == size-1 or col == 0 or col == size-1:
            return NodeType.EDGE
        # 内部
        else:
            return NodeType.INTERNAL
    
    def _get_neighbors(self, coord: Coordinate, config: TopologyConfig) -> NeighborMap:
        """获取邻居节点"""
        topo_type = get_topology_type_str(config.topology_type)
        if topo_type == "grid":
            return self._get_grid_neighbors(coord, config.size)
        elif topo_type == "torus":
            return self._get_torus_neighbors(coord, config.size)
        else:
            return {}
    
    def _get_grid_neighbors(self, coord: Coordinate, size: int) -> NeighborMap:
        """获取Grid邻居"""
        neighbors = {}
        row, col = coord.row, coord.col
        
        if row > 0:
            neighbors[Direction.NORTH] = Coordinate(row - 1, col)
        if row < size - 1:
            neighbors[Direction.SOUTH] = Coordinate(row + 1, col)
        if col > 0:
            neighbors[Direction.WEST] = Coordinate(row, col - 1)
        if col < size - 1:
            neighbors[Direction.EAST] = Coordinate(row, col + 1)
        
        return neighbors
    
    def _get_torus_neighbors(self, coord: Coordinate, size: int) -> NeighborMap:
        """获取Torus邻居"""
        row, col = coord.row, coord.col
        return {
            Direction.NORTH: Coordinate((row - 1 + size) % size, col),
            Direction.SOUTH: Coordinate((row + 1) % size, col),
            Direction.WEST: Coordinate(row, (col - 1 + size) % size),
            Direction.EAST: Coordinate(row, (col + 1) % size)
        }
    
    def _calculate_area_id(self, coord: Coordinate, config: TopologyConfig) -> str:
        """计算区域ID"""
        if config.multi_area and config.area_size:
            area_row = coord.row // config.area_size
            area_col = coord.col // config.area_size
            return f"{area_row}.{area_col}.0.0"
        else:
            return "0.0.0.0"
    

    
    def _calculate_as_number(self, coord: Coordinate, config: TopologyConfig) -> int:
        """计算AS号"""
        topo_type = get_topology_type_str(config.topology_type)
        if topo_type == "special" and config.special_config:
            # Special拓扑的AS分配逻辑（基于dm6_6_sample）
            return self._get_special_as_number(coord, config.bgp_config.as_number)
        else:
            # Grid/Torus拓扑使用统一AS
            return config.bgp_config.as_number

    def _get_special_as_number(self, coord: Coordinate, base_as: int) -> int:
        """获取Special拓扑的AS号

        域分割规则（基于 dm6_6_sample）：
        - 域1 (AS base+1): (0,0) 到 (2,2) - 左上角
        - 域2 (AS base+2): (0,3) 到 (2,5) - 右上角
        - 域3 (AS base+3): (3,0) 到 (5,2) - 左下角
        - 域4 (AS base+4): (3,3) 到 (5,5) - 右下角
        """
        row, col = coord.row, coord.col

        if 0 <= row <= 2 and 0 <= col <= 2:
            return base_as + 1  # 域1
        elif 0 <= row <= 2 and 3 <= col <= 5:
            return base_as + 2  # 域2
        elif 3 <= row <= 5 and 0 <= col <= 2:
            return base_as + 3  # 域3
        elif 3 <= row <= 5 and 3 <= col <= 5:
            return base_as + 4  # 域4
        else:
            return base_as  # 默认AS（不应该发生）

    def _get_output_dir(self, config: TopologyConfig) -> Path:
        """获取输出目录（优先使用配置中的 output_dir）"""
        if getattr(config, "output_dir", None):
            return Path(str(config.output_dir))
        topo_type = get_topology_type_str(config.topology_type)
        return Path(f"ospfv3_{topo_type}{config.size}x{config.size}")


# 便利函数
async def generate_topology(config: TopologyConfig) -> GenerationResult:
    """生成拓扑的便利函数"""
    engine = TopologyEngine()
    return await engine.generate_topology(config)
