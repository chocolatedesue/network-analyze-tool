#!/usr/bin/env python3
"""
调试接口分配问题
"""

import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from topo_gen.core.types import TopologyType, Coordinate, Direction, INTERFACE_MAPPING
from topo_gen.core.models import TopologyConfig, OSPFConfig, BFDConfig
from topo_gen.links import calculate_direction, generate_interface_mappings
from topo_gen.engine import TopologyEngine

def debug_interface_assignment():
    """调试接口分配问题"""
    print("=== 调试接口分配问题 ===")
    
    # 创建10x10 Torus配置
    config = TopologyConfig(
        size=10,
        topology_type=TopologyType.TORUS,
        multi_area=False,
        ospf_config=OSPFConfig(),
        bfd_config=BFDConfig(enabled=False)
    )
    
    # 生成路由器信息
    generator = TopologyEngine()
    routers = generator._generate_routers(config)
    
    print(f"生成了 {len(routers)} 个路由器")
    
    # 生成接口映射
    interface_mappings = generate_interface_mappings(config, routers)
    
    # 检查特定路由器的接口分配
    test_routers = ["router_08_09", "router_09_09", "router_09_00"]
    
    for router_name in test_routers:
        if router_name in interface_mappings:
            print(f"\n{router_name} 的接口分配:")
            interfaces = interface_mappings[router_name]
            for intf, addr in interfaces.items():
                print(f"  {intf}: {addr}")
        else:
            print(f"\n{router_name} 不存在")
    
    # 检查是否有重复的接口分配
    print(f"\n=== 检查接口重复 ===")
    interface_usage = {}  # {router_name: {interface: count}}
    
    for router_name, interfaces in interface_mappings.items():
        interface_usage[router_name] = {}
        for intf in interfaces.keys():
            if intf not in interface_usage[router_name]:
                interface_usage[router_name][intf] = 0
            interface_usage[router_name][intf] += 1
    
    # 查找重复使用的接口
    duplicates_found = False
    for router_name, interfaces in interface_usage.items():
        for intf, count in interfaces.items():
            if count > 1:
                print(f"❌ {router_name}:{intf} 被使用了 {count} 次")
                duplicates_found = True
    
    if not duplicates_found:
        print("✅ 没有发现接口重复使用")
    
    # 检查特定的环绕连接
    print(f"\n=== 检查环绕连接的方向计算 ===")
    
    # 测试一些环绕连接
    test_cases = [
        # 水平环绕
        (Coordinate(0, 0), Coordinate(0, 9)),  # 左边界到右边界
        (Coordinate(0, 9), Coordinate(0, 0)),  # 右边界到左边界
        (Coordinate(5, 0), Coordinate(5, 9)),  # 中间行的环绕
        # 垂直环绕
        (Coordinate(0, 0), Coordinate(9, 0)),  # 上边界到下边界
        (Coordinate(9, 0), Coordinate(0, 0)),  # 下边界到上边界
        (Coordinate(0, 5), Coordinate(9, 5)),  # 中间列的环绕
    ]
    
    for from_coord, to_coord in test_cases:
        direction = calculate_direction(from_coord, to_coord, config.size)
        interface = INTERFACE_MAPPING.get(direction, "未知") if direction else "None"
        
        row_diff = to_coord.row - from_coord.row
        col_diff = to_coord.col - from_coord.col
        
        print(f"从 {from_coord} 到 {to_coord}:")
        print(f"  坐标差: row_diff={row_diff}, col_diff={col_diff}")
        print(f"  计算方向: {direction}")
        print(f"  分配接口: {interface}")
        print()

def debug_specific_router():
    """调试特定路由器的连接"""
    print("=== 调试 router_08_09 的连接 ===")
    
    config = TopologyConfig(
        size=10,
        topology_type=TopologyType.TORUS,
        multi_area=False,
        ospf_config=OSPFConfig(),
        bfd_config=BFDConfig(enabled=False)
    )
    
    # router_08_09 的坐标
    router_coord = Coordinate(8, 9)
    
    # 获取它的邻居
    from topo_gen.links import get_torus_neighbors
    neighbors = get_torus_neighbors(router_coord, config.size)
    
    print(f"router_08_09 ({router_coord}) 的邻居:")
    for direction, neighbor_coord in neighbors.items():
        calculated_direction = calculate_direction(router_coord, neighbor_coord, config.size)
        interface = INTERFACE_MAPPING.get(calculated_direction, "未知") if calculated_direction else "None"
        
        row_diff = neighbor_coord.row - router_coord.row
        col_diff = neighbor_coord.col - router_coord.col
        
        print(f"  {direction.name}: {neighbor_coord}")
        print(f"    坐标差: row_diff={row_diff}, col_diff={col_diff}")
        print(f"    计算方向: {calculated_direction}")
        print(f"    分配接口: {interface}")
        
        # 检查是否与预期方向一致
        if calculated_direction != direction:
            print(f"    ⚠️  方向不一致! 预期: {direction}, 计算: {calculated_direction}")
        print()

if __name__ == "__main__":
    debug_interface_assignment()
    debug_specific_router()
