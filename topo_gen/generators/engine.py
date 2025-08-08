"""
简化的生成器引擎
使用anyio和简单的异步编程模式
"""

from __future__ import annotations

from typing import Dict, List, Optional, Any
from pathlib import Path
from dataclasses import dataclass, field
import anyio
from anyio import Path as AsyncPath
import ipaddress

from ..core.types import (
    Coordinate, Direction, RouterName, InterfaceName,
    IPv6Address, Link, Success, Failure, Result
)
from ..core.models import (
    TopologyConfig, RouterInfo, LinkInfo, SystemRequirements, GenerationResult
)
from ..topology.base import TopologyFactory
from ..topology.grid import create_grid_topology
from ..topology.torus import create_torus_topology
from ..generators.config import ConfigGeneratorFactory
from ..utils.functional import pipe, memoize

@dataclass
class GenerationContext:
    """生成上下文"""
    config: TopologyConfig
    output_dir: Path
    routers: List[RouterInfo] = field(default_factory=list)
    links: List[LinkInfo] = field(default_factory=list)
    interface_mappings: Dict[RouterName, Dict[InterfaceName, IPv6Address]] = field(default_factory=dict)
    requirements: Optional[SystemRequirements] = None
    
    def __post_init__(self):
        if self.requirements is None:
            self.requirements = SystemRequirements.calculate_for_topology(self.config)

class ModernTopologyGenerator:
    """现代化拓扑生成器"""
    
    def __init__(self):
        self.topology_factory = TopologyFactory()
        self.config_factory = ConfigGeneratorFactory()
    
    async def generate_topology(self, config: TopologyConfig, output_dir: Path) -> GenerationResult:
        """异步生成拓扑"""
        try:
            # 创建生成上下文
            context = GenerationContext(config=config, output_dir=output_dir)

            # 执行生成管道（手动异步链式调用）
            result = await self._validate_config(context)
            if isinstance(result, Failure):
                return self._create_error_result(result)

            result = await self._generate_routers(result.unwrap())
            if isinstance(result, Failure):
                return self._create_error_result(result)

            result = await self._generate_links(result.unwrap())
            if isinstance(result, Failure):
                return self._create_error_result(result)

            result = await self._create_directories(result.unwrap())
            if isinstance(result, Failure):
                return self._create_error_result(result)

            result = await self._generate_configs(result.unwrap())
            if isinstance(result, Failure):
                return self._create_error_result(result)

            result = await self._generate_containerlab_yaml(result.unwrap())
            if isinstance(result, Failure):
                return self._create_error_result(result)

            result = await self._finalize_generation(result.unwrap())
            if isinstance(result, Failure):
                return self._create_error_result(result)
            
            # 如果到这里，说明所有步骤都成功了
            return GenerationResult(
                success=True,
                message="拓扑生成成功",
                output_dir=output_dir,
                stats=self._calculate_stats(result.unwrap())
            )
                
        except Exception as e:
            return GenerationResult(
                success=False,
                message=f"生成过程中发生错误: {str(e)}",
                error_details=str(e)
            )

    def _create_error_result(self, failure_result) -> GenerationResult:
        """创建错误结果"""
        error_msg = getattr(failure_result, 'error', str(failure_result))
        return GenerationResult(
            success=False,
            message=f"生成失败: {error_msg}",
            error_details=error_msg
        )
    
    async def _validate_config(self, context: GenerationContext) -> Result[GenerationContext, str]:
        """验证配置"""
        try:
            # 验证基本参数
            if not (2 <= context.config.size <= 100):
                return Failure("网格大小必须在2-100之间")

            # 验证拓扑特定参数
            topology_type_str = context.config.topology_type if isinstance(context.config.topology_type, str) else context.config.topology_type.value
            if topology_type_str == "special":
                if not context.config.special_config:
                    return Failure("Special拓扑必须提供special_config")

            # 验证系统资源
            if context.requirements.min_memory_gb > 32:
                return Failure(f"所需内存过大: {context.requirements.min_memory_gb:.1f}GB")

            return Success(context)
            
        except Exception as e:
            return Failure(error=f"配置验证失败: {str(e)}")
    
    async def _generate_routers(self, context: GenerationContext) -> Result[GenerationContext, str]:
        """生成路由器信息"""
        try:
            # 获取拓扑生成器
            topology = self._get_topology_generator(context.config.topology_type)
            
            # 生成所有路由器
            routers = []
            for row in range(context.config.size):
                for col in range(context.config.size):
                    coord = Coordinate(row, col)
                    router = await self._create_router_info(coord, context.config, topology)
                    routers.append(router)
            
            context.routers = routers
            return Success(value=context)

        except Exception as e:
            return Failure(error=f"路由器生成失败: {str(e)}")
    
    async def _generate_links(self, context: GenerationContext) -> Result[GenerationContext, str]:
        """生成链路信息"""
        try:
            # 生成所有链路，避免重复
            links = []
            link_id_counter = 0
            processed_pairs = set()

            # 获取拓扑生成器
            topology = self._get_topology_generator(context.config.topology_type)

            for router in context.routers:
                neighbors = topology.get_neighbors(router.coordinate, context.config.size)

                for direction, neighbor_coord in neighbors.items():
                    # 创建标准化的坐标对，避免重复链路
                    coord_pair = tuple(sorted([
                        (router.coordinate.row, router.coordinate.col),
                        (neighbor_coord.row, neighbor_coord.col)
                    ]))

                    if coord_pair not in processed_pairs:
                        processed_pairs.add(coord_pair)

                        # 确定链路的方向（从坐标较小的节点到较大的节点）
                        if (router.coordinate.row, router.coordinate.col) < (neighbor_coord.row, neighbor_coord.col):
                            coord1, coord2 = router.coordinate, neighbor_coord
                            link_direction = direction
                        else:
                            coord1, coord2 = neighbor_coord, router.coordinate
                            link_direction = direction.opposite

                        link = await self._create_link_info(
                            coord1,
                            coord2,
                            link_direction,
                            link_id_counter,
                            context.config
                        )
                        links.append(link)
                        link_id_counter += 1

            context.links = links

            # 生成接口映射
            await self._generate_interface_mappings(context)

            return Success(value=context)

        except Exception as e:
            return Failure(error=f"链路生成失败: {str(e)}")
    
    async def _create_directories(self, context: GenerationContext) -> Result[GenerationContext, str]:
        """创建目录结构"""
        try:
            # 创建主目录
            context.output_dir.mkdir(parents=True, exist_ok=True)
            
            # 并行创建路由器目录
            async def create_router_dir(router: RouterInfo):
                router_dir = context.output_dir / "etc" / router.name / "conf"
                router_dir.mkdir(parents=True, exist_ok=True)
            
            await async_map(create_router_dir, context.routers)
            
            return Success(value=context)

        except Exception as e:
            return Failure(error=f"目录创建失败: {str(e)}")
    
    async def _generate_configs(self, context: GenerationContext) -> Result[GenerationContext, str]:
        """生成配置文件"""
        try:
            # 获取配置类型
            config_types = self._get_config_types(context.config)
            
            # 并行生成所有路由器的配置
            async def generate_router_configs(router: RouterInfo):
                router_dir = context.output_dir / "etc" / router.name / "conf"

                for config_type in config_types:
                    generator = self.config_factory.create(config_type)

                    # 对于BGP配置，需要传递所有路由器信息
                    if config_type == "bgpd.conf":
                        config_content = generator.generate(router, context.config, context.routers)
                    else:
                        config_content = generator.generate(router, context.config)

                    config_file = router_dir / config_type
                    async with aiofiles.open(config_file, 'w') as f:
                        await f.write(config_content)
            
            await async_map(generate_router_configs, context.routers)
            
            return Success(value=context)

        except Exception as e:
            return Failure(error=f"配置生成失败: {str(e)}")
    
    async def _generate_containerlab_yaml(self, context: GenerationContext) -> Result[GenerationContext, str]:
        """生成ContainerLab YAML"""
        try:
            yaml_content = await self._create_containerlab_yaml(context)
            
            yaml_file = context.output_dir / "clab.yaml"
            async with aiofiles.open(yaml_file, 'w') as f:
                await f.write(yaml_content)
            
            return Success(value=context)

        except Exception as e:
            return Failure(error=f"ContainerLab YAML生成失败: {str(e)}")
    
    async def _finalize_generation(self, context: GenerationContext) -> Result[GenerationContext, str]:
        """完成生成"""
        try:
            # 生成统计信息
            stats_content = self._generate_stats_report(context)
            
            stats_file = context.output_dir / "topology_stats.txt"
            async with aiofiles.open(stats_file, 'w') as f:
                await f.write(stats_content)
            
            return Success(value=context)

        except Exception as e:
            return Failure(error=f"生成完成失败: {str(e)}")
    
    def _get_topology_generator(self, topology_type):
        """获取拓扑生成器"""
        topology_type_str = topology_type if isinstance(topology_type, str) else topology_type.value
        if topology_type_str == "grid":
            return create_grid_topology()
        elif topology_type_str == "torus":
            return create_torus_topology()
        else:
            raise ValueError(f"不支持的拓扑类型: {topology_type_str}")
    
    async def _create_router_info(self, coord: Coordinate, config: TopologyConfig, topology) -> RouterInfo:
        """创建路由器信息"""
        router_name = f"router_{coord.row:02d}_{coord.col:02d}"
        router_id = self._generate_router_id(coord, config.size)
        loopback_ipv6 = self._generate_loopback_ipv6(coord, config)
        node_type = topology.get_node_type(coord, config.size)
        neighbors = topology.get_neighbors(coord, config.size)
        
        # 计算AS号（如果启用BGP）
        as_number = None
        if config.enable_bgp:
            as_number = self._calculate_as_number(coord, config)
        
        return RouterInfo(
            name=router_name,
            coordinate=coord,
            node_type=node_type,
            router_id=router_id,
            loopback_ipv6=loopback_ipv6,
            neighbors=neighbors,
            as_number=as_number
        )
    
    async def _create_link_info(
        self,
        coord1: Coordinate,
        coord2: Coordinate,
        direction: Direction,
        link_id: int,
        config: TopologyConfig
    ) -> LinkInfo:
        """创建链路信息"""
        router1_name = f"router_{coord1.row:02d}_{coord1.col:02d}"
        router2_name = f"router_{coord2.row:02d}_{coord2.col:02d}"

        # 重新计算正确的方向，特别是对于torus拓扑
        actual_direction1 = self._calculate_actual_direction(coord1, coord2, config.size, config.topology_type)
        actual_direction2 = actual_direction1.opposite

        # 计算接口名称
        router1_interface = self._direction_to_interface(actual_direction1)
        router2_interface = self._direction_to_interface(actual_direction2)

        # 生成IPv6地址
        network, router1_ipv6, router2_ipv6 = self._generate_link_ipv6(link_id, config)

        return LinkInfo(
            router1_name=router1_name,
            router2_name=router2_name,
            router1_coord=coord1,
            router2_coord=coord2,
            router1_interface=router1_interface,
            router2_interface=router2_interface,
            router1_ipv6=router1_ipv6,
            router2_ipv6=router2_ipv6,
            network=network
        )
    
    def _should_create_link(self, coord1: Coordinate, coord2: Coordinate) -> bool:
        """判断是否应该创建链路（避免重复）"""
        return (coord1.row, coord1.col) < (coord2.row, coord2.col)
    
    def _direction_to_interface(self, direction: Direction) -> str:
        """方向到接口名称的映射"""
        mapping = {
            Direction.NORTH: "eth1",
            Direction.SOUTH: "eth2",
            Direction.WEST: "eth3",
            Direction.EAST: "eth4"
        }
        return mapping[direction]

    def _calculate_actual_direction(self, coord1: Coordinate, coord2: Coordinate, size: int, topology_type) -> Direction:
        """计算实际的方向，特别处理torus拓扑的环绕连接"""
        row_diff = coord2.row - coord1.row
        col_diff = coord2.col - coord1.col

        # 标准相邻方向
        if row_diff == -1 and col_diff == 0:
            return Direction.NORTH
        elif row_diff == 1 and col_diff == 0:
            return Direction.SOUTH
        elif row_diff == 0 and col_diff == -1:
            return Direction.WEST
        elif row_diff == 0 and col_diff == 1:
            return Direction.EAST

        # 对于torus拓扑，处理环绕连接
        if str(topology_type).lower() == 'torus' or (hasattr(topology_type, 'value') and topology_type.value.lower() == 'torus'):
            # 北-南环绕：从(0,x)到(size-1,x)应该是向北，从(size-1,x)到(0,x)应该是向南
            if row_diff == size - 1 and col_diff == 0:  # (0,x) -> (size-1,x) - 向北环绕
                return Direction.NORTH
            elif row_diff == -(size - 1) and col_diff == 0:  # (size-1,x) -> (0,x) - 向南环绕
                return Direction.SOUTH

            # 东-西环绕：从(x,0)到(x,size-1)应该是向西，从(x,size-1)到(x,0)应该是向东
            if row_diff == 0 and col_diff == size - 1:  # (x,0) -> (x,size-1) - 向西环绕
                return Direction.WEST
            elif row_diff == 0 and col_diff == -(size - 1):  # (x,size-1) -> (x,0) - 向东环绕
                return Direction.EAST

        # 默认情况：选择一个合适的方向
        if abs(row_diff) >= abs(col_diff):
            return Direction.NORTH if row_diff < 0 else Direction.SOUTH
        else:
            return Direction.WEST if col_diff < 0 else Direction.EAST
    
    def _generate_router_id(self, coord: Coordinate, size: int) -> str:
        """生成路由器ID"""
        return f"10.{coord.row}.{coord.col}.1"
    
    def _generate_loopback_ipv6(self, coord: Coordinate, config: TopologyConfig) -> IPv6Address:
        """生成Loopback IPv6地址"""
        prefix = config.network_config.loopback_prefix.rstrip(":")
        # 使用灵活的十六进制格式，避免超过4位的限制
        row_hex = f"{coord.row:x}" if coord.row <= 0xFFFF else f"{coord.row >> 16:x}:{coord.row & 0xFFFF:04x}"
        col_hex = f"{coord.col:x}" if coord.col <= 0xFFFF else f"{coord.col >> 16:x}:{coord.col & 0xFFFF:04x}"
        return ipaddress.IPv6Address(f"{prefix}:0000:{row_hex}:{col_hex}::1")
    
    def _generate_link_ipv6(self, link_id: int, config: TopologyConfig) -> tuple:
        """生成链路IPv6地址 - 使用/126网络选择地址，/127前缀配置"""
        prefix = config.network_config.link_prefix.rstrip(":")

        # 将 link_id 分解为多个段，避免单个段超过 4 位十六进制
        # 使用层次化地址分配：高16位作为第一段，低16位作为第二段
        segment1 = (link_id >> 16) & 0xFFFF  # 高16位
        segment2 = link_id & 0xFFFF          # 低16位

        # 构建IPv6地址，确保每个段都不超过4位十六进制
        if segment1 > 0:
            # 如果有高位段，使用两段格式
            ipv6_suffix = f"{segment1:x}:{segment2:04x}"
        else:
            # 如果没有高位段，使用单段格式
            ipv6_suffix = f"{segment2:04x}"

        # 使用/126网络选择地址，避免::0和::3
        network_126 = ipaddress.IPv6Network(f"{prefix}:{ipv6_suffix}::/126")
        network_addr = network_126.network_address

        # 选择::1和::2地址，避免::0（网络地址）和::3（看起来像广播地址）
        addr1 = network_addr + 1  # ::1
        addr2 = network_addr + 2  # ::2

        # 返回/127网络用于配置（点对点链路标准）
        network = ipaddress.IPv6Network(f"{prefix}:{ipv6_suffix}::/127")

        return network, addr1, addr2
    
    def _calculate_as_number(self, coord: Coordinate, config: TopologyConfig) -> int:
        """计算AS号"""
        topology_type_str = config.topology_type if isinstance(config.topology_type, str) else config.topology_type.value
        if topology_type_str == "special" and config.special_config:
            # Special拓扑的AS分配逻辑
            return self._get_special_as_number(coord, config.bgp_config.as_number)
        else:
            # Grid/Torus拓扑使用统一AS
            return config.bgp_config.as_number
    
    def _get_special_as_number(self, coord: Coordinate, base_as: int) -> int:
        """获取Special拓扑的AS号"""
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
            return base_as
    
    async def _generate_interface_mappings(self, context: GenerationContext):
        """生成接口映射"""
        # 为每个路由器创建接口映射
        for router in context.routers:
            interfaces = {}
            
            # 从链路信息中提取接口
            for link in context.links:
                if link.router1_name == router.name:
                    interfaces[link.router1_interface] = link.router1_ipv6
                elif link.router2_name == router.name:
                    interfaces[link.router2_interface] = link.router2_ipv6
            
            router.interfaces = interfaces
            context.interface_mappings[router.name] = interfaces
    
    def _get_config_types(self, config: TopologyConfig) -> List[str]:
        """获取需要生成的配置类型"""
        config_types = ["daemons", "zebra.conf", "ospf6d.conf", "staticd.conf"]

        if config.bgp_config is not None:
            config_types.append("bgpd.conf")

        if config.bfd_config and config.bfd_config.enabled:
            config_types.append("bfdd.conf")

        return config_types
    
    async def _create_containerlab_yaml(self, context: GenerationContext) -> str:
        """创建ContainerLab YAML内容"""
        # 简化的YAML生成逻辑
        yaml_lines = [
            "name: ospfv3-topology",
            "topology:",
            "  nodes:"
        ]
        
        # 添加节点
        for router in context.routers:
            yaml_lines.extend([
                f"    {router.name}:",
                "      kind: linux",
                "      image: frrouting/frr:latest",
                f"      binds:",
                f"        - ./etc/{router.name}/conf:/etc/frr"
            ])
        
        yaml_lines.append("  links:")
        
        # 添加链路
        for link in context.links:
            yaml_lines.append(
                f"    - endpoints: [\"{link.router1_name}:{link.router1_interface}\", "
                f"\"{link.router2_name}:{link.router2_interface}\"]"
            )
        
        return "\n".join(yaml_lines)
    
    def _generate_stats_report(self, context: GenerationContext) -> str:
        """生成统计报告"""
        topology_type_str = context.config.topology_type if isinstance(context.config.topology_type, str) else context.config.topology_type.value
        lines = [
            f"拓扑生成统计报告",
            f"=" * 50,
            f"拓扑类型: {topology_type_str.upper()}",
            f"网格大小: {context.config.size}x{context.config.size}",
            f"总路由器数: {len(context.routers)}",
            f"总链路数: {len(context.links)}",
            f"启用BGP: {'是' if context.config.enable_bgp else '否'}",
            f"启用BFD: {'是' if context.config.enable_bfd else '否'}",
            f"",
            f"系统需求:",
            f"  最小内存: {context.requirements.min_memory_gb:.1f} GB",
            f"  推荐内存: {context.requirements.recommended_memory_gb:.1f} GB",
        ]
        
        return "\n".join(lines)
    
    def _calculate_stats(self, context: GenerationContext) -> Dict[str, Any]:
        """计算统计信息"""
        topology_type_str = context.config.topology_type if isinstance(context.config.topology_type, str) else context.config.topology_type.value
        return {
            "total_routers": len(context.routers),
            "total_links": len(context.links),
            "topology_type": topology_type_str,
            "size": context.config.size,
            "enable_bgp": context.config.enable_bgp,
            "enable_bfd": context.config.enable_bfd
        }

# 创建全局生成器实例
generator = ModernTopologyGenerator()

# 导出主要函数
async def generate_topology(config: TopologyConfig, output_dir: Path) -> GenerationResult:
    """生成拓扑的主入口函数"""
    return await generator.generate_topology(config, output_dir)
