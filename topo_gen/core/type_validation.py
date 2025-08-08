"""
类型验证和示例模块
展示优化后的 Pydantic 类型系统的功能和验证能力
"""

from __future__ import annotations

from typing import List, Dict, Any
from pydantic import ValidationError
import ipaddress

from .types import (
    Coordinate, Direction, TopologyType, NodeType, ProtocolType,
    RouterName, InterfaceName, IPv6Address, ASNumber, RouterID, AreaID,
    NeighborMap, Link, Success, Failure, ValidationResult,
    IPv6AddressHelper, IPv6NetworkHelper, LinkAddress, TopologyStats,
    InterfaceMapping, DirectionMapping
)
from .models import (
    TopologyConfig, RouterInfo, LinkInfo, NetworkConfig,
    OSPFConfig, BGPConfig, BFDConfig, SpecialTopologyConfig,
    SystemRequirements, GenerationResult
)


class TypeValidationDemo:
    """类型验证演示类"""
    
    @staticmethod
    def demo_coordinate_validation():
        """演示坐标验证功能"""
        print("=== 坐标验证演示 ===")
        
        # 有效坐标
        try:
            coord1 = Coordinate(row=5, col=10)
            coord2 = Coordinate(row=0, col=0)
            print(f"✓ 有效坐标: {coord1}, {coord2}")
            
            # 计算距离
            distance = coord1.manhattan_distance_to(coord2)
            print(f"✓ 曼哈顿距离: {distance}")
            
            # 检查相邻性
            coord3 = Coordinate(row=5, col=11)
            is_adjacent = coord1.is_adjacent_to(coord3)
            print(f"✓ 相邻检查: {coord1} 和 {coord3} 相邻: {is_adjacent}")
            
        except ValidationError as e:
            print(f"✗ 坐标验证失败: {e}")
        
        # 无效坐标
        try:
            invalid_coord = Coordinate(row=-1, col=5)
            print(f"✗ 不应该到达这里: {invalid_coord}")
        except ValidationError as e:
            print(f"✓ 正确捕获无效坐标: {e.errors()[0]['msg']}")
    
    @staticmethod
    def demo_direction_functionality():
        """演示方向功能"""
        print("\n=== 方向功能演示 ===")
        
        direction = Direction.NORTH
        print(f"✓ 方向: {direction}")
        print(f"✓ 相反方向: {direction.opposite}")
        print(f"✓ 角度: {direction.angle_degrees}°")
        print(f"✓ 顺时针旋转: {direction.rotate_clockwise()}")
        print(f"✓ 逆时针旋转: {direction.rotate_counterclockwise()}")
        print(f"✓ 方向向量: {direction.vector}")
    
    @staticmethod
    def demo_ipv6_helpers():
        """演示IPv6地址助手功能"""
        print("\n=== IPv6地址助手演示 ===")
        
        # IPv6地址助手
        try:
            addr_helper = IPv6AddressHelper.from_string("2001:db8::1/64")
            print(f"✓ IPv6地址: {addr_helper.address}")
            print(f"✓ 纯地址: {addr_helper.pure_address}")
            print(f"✓ 带前缀: {addr_helper.with_prefix}")
            print(f"✓ 网络: {addr_helper.network}")
            print(f"✓ 是否全局: {addr_helper.is_global}")
            print(f"✓ 是否链路本地: {addr_helper.is_link_local}")
            
        except ValidationError as e:
            print(f"✗ IPv6地址验证失败: {e}")
        
        # IPv6网络助手
        try:
            net_helper = IPv6NetworkHelper(network="2001:db8::/64")
            print(f"✓ 网络地址: {net_helper.network_address}")
            print(f"✓ 前缀长度: {net_helper.prefix_length}")
            print(f"✓ 地址数量: {net_helper.num_addresses}")
            
            # 获取主机地址
            host_addr = net_helper.get_host_address(0)
            print(f"✓ 第一个主机地址: {host_addr.pure_address}")
            
        except ValidationError as e:
            print(f"✗ IPv6网络验证失败: {e}")
    
    @staticmethod
    def demo_link_validation():
        """演示链路验证功能"""
        print("\n=== 链路验证演示 ===")
        
        try:
            coord1 = Coordinate(row=0, col=0)
            coord2 = Coordinate(row=0, col=1)
            
            link = Link(
                router1=coord1,
                router2=coord2,
                direction1=Direction.EAST,
                direction2=Direction.WEST,
                network="2001:db8:1000::/127"
            )
            
            print(f"✓ 链路创建成功: {link.link_id}")
            print(f"✓ 是否水平: {link.is_horizontal}")
            print(f"✓ 是否垂直: {link.is_vertical}")
            
            # 获取另一端路由器
            other_router = link.get_other_router(coord1)
            print(f"✓ 另一端路由器: {other_router}")
            
        except ValidationError as e:
            print(f"✗ 链路验证失败: {e}")
        
        # 测试无效链路（方向不一致）
        try:
            invalid_link = Link(
                router1=coord1,
                router2=coord2,
                direction1=Direction.EAST,
                direction2=Direction.EAST,  # 错误：应该是WEST
                network="2001:db8:1000::/127"
            )
            print(f"✗ 不应该到达这里: {invalid_link}")
        except ValidationError as e:
            print(f"✓ 正确捕获方向不一致: {e.errors()[0]['msg']}")
    
    @staticmethod
    def demo_router_info():
        """演示路由器信息功能"""
        print("\n=== 路由器信息演示 ===")
        
        try:
            coord = Coordinate(row=1, col=1)
            router = RouterInfo(
                name="router_01_01",
                coordinate=coord,
                node_type=NodeType.INTERNAL,
                router_id="10.1.1.1",
                loopback_ipv6="2001:db8:1000::1:1/128",
                interfaces={
                    "eth1": "2001:db8:2000::1/127",
                    "eth2": "2001:db8:2001::1/127"
                },
                neighbors={
                    Direction.NORTH: Coordinate(row=0, col=1),
                    Direction.SOUTH: Coordinate(row=2, col=1)
                },
                area_id="0.0.0.0",
                as_number=65001,
                description="内部路由器",
                vendor="cisco",
                model="c8000v"
            )
            
            print(f"✓ 路由器: {router.name}")
            print(f"✓ 坐标: {router.coordinate}")
            print(f"✓ 邻居数量: {router.neighbor_count}")
            print(f"✓ 接口数量: {router.interface_count}")
            print(f"✓ 是否边界路由器: {router.is_border_router}")
            print(f"✓ 是否特殊节点: {router.is_special_node}")
            print(f"✓ Loopback助手: {router.loopback_helper.pure_address}")
            
        except ValidationError as e:
            print(f"✗ 路由器信息验证失败: {e}")
    
    @staticmethod
    def demo_topology_config():
        """演示拓扑配置功能"""
        print("\n=== 拓扑配置演示 ===")
        
        try:
            config = TopologyConfig(
                size=6,
                topology_type=TopologyType.GRID,
                multi_area=True,
                area_size=3,
                ospf_config=OSPFConfig(
                    hello_interval=2,
                    dead_interval=8,
                    spf_delay=20,
                    area_id="0.0.0.0"
                ),
                bgp_config=BGPConfig(
                    as_number=65001,
                    local_preference=100,
                    hold_time=180,
                    keepalive_time=60
                ),
                bfd_config=BFDConfig(
                    enabled=True,
                    detect_multiplier=3,
                    receive_interval=300,
                    transmit_interval=300
                )
            )
            
            print(f"✓ 拓扑类型: {config.topology_type}")
            print(f"✓ 网格大小: {config.size}x{config.size}")
            print(f"✓ 总路由器数: {config.total_routers}")
            print(f"✓ 总链路数: {config.total_links}")
            print(f"✓ 启用BFD: {config.enable_bfd}")
            print(f"✓ 启用BGP: {config.enable_bgp}")
            
            # 拓扑统计
            stats = config.topology_stats
            print(f"✓ 拓扑密度: {stats.density:.3f}")
            print(f"✓ 平均度数: {stats.average_degree:.2f}")
            print(f"✓ 节点分布: {stats.node_type_distribution}")
            
        except ValidationError as e:
            print(f"✗ 拓扑配置验证失败: {e}")
    
    @staticmethod
    def run_all_demos():
        """运行所有演示"""
        print("🚀 Pydantic 类型系统优化演示")
        print("=" * 50)
        
        TypeValidationDemo.demo_coordinate_validation()
        TypeValidationDemo.demo_direction_functionality()
        TypeValidationDemo.demo_ipv6_helpers()
        TypeValidationDemo.demo_link_validation()
        TypeValidationDemo.demo_router_info()
        TypeValidationDemo.demo_topology_config()
        
        print("\n" + "=" * 50)
        print("✅ 所有演示完成！")


def validate_type_system():
    """验证类型系统的完整性"""
    print("🔍 验证类型系统完整性...")
    
    validation_results = []
    
    # 验证基础类型
    try:
        coord = Coordinate(row=0, col=0)
        validation_results.append("✓ Coordinate 类型正常")
    except Exception as e:
        validation_results.append(f"✗ Coordinate 类型异常: {e}")
    
    # 验证枚举类型
    try:
        topo_type = TopologyType.GRID
        node_type = NodeType.INTERNAL
        direction = Direction.NORTH
        validation_results.append("✓ 枚举类型正常")
    except Exception as e:
        validation_results.append(f"✗ 枚举类型异常: {e}")
    
    # 验证模型类型
    try:
        config = TopologyConfig(size=4, topology_type=TopologyType.GRID)
        validation_results.append("✓ 模型类型正常")
    except Exception as e:
        validation_results.append(f"✗ 模型类型异常: {e}")
    
    # 输出验证结果
    for result in validation_results:
        print(result)
    
    return all("✓" in result for result in validation_results)


if __name__ == "__main__":
    # 运行类型系统验证
    if validate_type_system():
        print("\n🎉 类型系统验证通过！")
        print("\n开始演示...")
        TypeValidationDemo.run_all_demos()
    else:
        print("\n❌ 类型系统验证失败！")
