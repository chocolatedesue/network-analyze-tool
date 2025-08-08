#!/usr/bin/env python3
"""
测试拓扑修复的脚本
验证 torus 和 special 拓扑的正确性
"""

import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from topo_gen.core.types import Coordinate, Direction, TopologyType
from topo_gen.topology.torus import create_torus_topology
from topo_gen.topology.special import (
    create_dm6_6_sample, get_subregion_for_coord, 
    is_cross_region_connection, get_filtered_grid_neighbors
)


def test_torus_topology():
    """测试 torus 拓扑逻辑"""
    print("=== 测试 Torus 拓扑 ===")
    
    topology = create_torus_topology()
    size = 4  # 测试 4x4 torus
    
    # 验证每个节点都有 4 个邻居
    all_coords = [(row, col) for row in range(size) for col in range(size)]
    
    for row, col in all_coords:
        coord = Coordinate(row, col)
        neighbors = topology.get_neighbors(coord, size)
        
        print(f"节点 {coord}: {len(neighbors)} 个邻居")
        for direction, neighbor in neighbors.items():
            print(f"  {direction.name}: {neighbor}")
        
        if len(neighbors) != 4:
            print(f"❌ 错误: 节点 {coord} 应该有 4 个邻居，实际有 {len(neighbors)} 个")
            return False
        
        # 验证环绕连接
        if row == 0:  # 顶部边界
            if Direction.NORTH not in neighbors:
                print(f"❌ 错误: 顶部节点 {coord} 缺少北向环绕连接")
                return False
            north_neighbor = neighbors[Direction.NORTH]
            if north_neighbor.row != size - 1:
                print(f"❌ 错误: 顶部节点 {coord} 的北向邻居应该是 ({size-1}, {col})，实际是 {north_neighbor}")
                return False
        
        if row == size - 1:  # 底部边界
            if Direction.SOUTH not in neighbors:
                print(f"❌ 错误: 底部节点 {coord} 缺少南向环绕连接")
                return False
            south_neighbor = neighbors[Direction.SOUTH]
            if south_neighbor.row != 0:
                print(f"❌ 错误: 底部节点 {coord} 的南向邻居应该是 (0, {col})，实际是 {south_neighbor}")
                return False
        
        if col == 0:  # 左边界
            if Direction.WEST not in neighbors:
                print(f"❌ 错误: 左边节点 {coord} 缺少西向环绕连接")
                return False
            west_neighbor = neighbors[Direction.WEST]
            if west_neighbor.col != size - 1:
                print(f"❌ 错误: 左边节点 {coord} 的西向邻居应该是 ({row}, {size-1})，实际是 {west_neighbor}")
                return False
        
        if col == size - 1:  # 右边界
            if Direction.EAST not in neighbors:
                print(f"❌ 错误: 右边节点 {coord} 缺少东向环绕连接")
                return False
            east_neighbor = neighbors[Direction.EAST]
            if east_neighbor.col != 0:
                print(f"❌ 错误: 右边节点 {coord} 的东向邻居应该是 ({row}, 0)，实际是 {east_neighbor}")
                return False
    
    print("✅ Torus 拓扑测试通过")
    return True


def test_special_topology_subregions():
    """测试 special 拓扑的子区域划分"""
    print("\n=== 测试 Special 拓扑子区域划分 ===")
    
    # 测试子区域划分
    test_cases = [
        # 区域 0: (0,0)-(2,2)
        (Coordinate(0, 0), 0), (Coordinate(1, 1), 0), (Coordinate(2, 2), 0),
        # 区域 1: (0,3)-(2,5)
        (Coordinate(0, 3), 1), (Coordinate(1, 4), 1), (Coordinate(2, 5), 1),
        # 区域 2: (3,0)-(5,2)
        (Coordinate(3, 0), 2), (Coordinate(4, 1), 2), (Coordinate(5, 2), 2),
        # 区域 3: (3,3)-(5,5)
        (Coordinate(3, 3), 3), (Coordinate(4, 4), 3), (Coordinate(5, 5), 3),
    ]
    
    for coord, expected_region in test_cases:
        actual_region = get_subregion_for_coord(coord)
        if actual_region != expected_region:
            print(f"❌ 错误: {coord} 应该属于区域 {expected_region}，实际属于区域 {actual_region}")
            return False
        print(f"✅ {coord} -> 区域 {actual_region}")
    
    # 测试跨区域连接检测
    cross_region_cases = [
        (Coordinate(2, 2), Coordinate(2, 3), True),   # 跨越列边界
        (Coordinate(2, 1), Coordinate(3, 1), True),   # 跨越行边界
        (Coordinate(1, 1), Coordinate(1, 2), False),  # 同区域内
        (Coordinate(4, 4), Coordinate(4, 5), False),  # 同区域内
    ]
    
    for coord1, coord2, expected_cross in cross_region_cases:
        actual_cross = is_cross_region_connection(coord1, coord2)
        if actual_cross != expected_cross:
            print(f"❌ 错误: {coord1} <-> {coord2} 跨区域检测错误，期望 {expected_cross}，实际 {actual_cross}")
            return False
        print(f"✅ {coord1} <-> {coord2}: 跨区域={actual_cross}")
    
    print("✅ Special 拓扑子区域划分测试通过")
    return True


def test_filtered_grid_neighbors():
    """测试过滤后的 grid 邻居"""
    print("\n=== 测试过滤后的 Grid 邻居 ===")
    
    size = 6
    
    # 测试边界节点（应该移除跨区域连接）
    test_cases = [
        # 区域边界节点
        (Coordinate(2, 2), [Direction.NORTH, Direction.WEST]),  # 区域0右下角，应该缺少南向和东向
        (Coordinate(2, 3), [Direction.NORTH, Direction.EAST]),  # 区域1左下角，应该缺少南向和西向
        (Coordinate(3, 2), [Direction.SOUTH, Direction.WEST]),  # 区域2右上角，应该缺少北向和东向
        (Coordinate(3, 3), [Direction.SOUTH, Direction.EAST]),  # 区域3左上角，应该缺少北向和西向
        
        # 内部节点（应该有完整的邻居）
        (Coordinate(1, 1), [Direction.NORTH, Direction.SOUTH, Direction.WEST, Direction.EAST]),
        (Coordinate(4, 4), [Direction.NORTH, Direction.SOUTH, Direction.WEST, Direction.EAST]),
    ]
    
    for coord, expected_directions in test_cases:
        neighbors = get_filtered_grid_neighbors(coord, size)
        actual_directions = set(neighbors.keys())
        expected_directions_set = set(expected_directions)
        
        if actual_directions != expected_directions_set:
            print(f"❌ 错误: {coord} 的邻居方向不正确")
            print(f"   期望: {sorted([d.name for d in expected_directions_set])}")
            print(f"   实际: {sorted([d.name for d in actual_directions])}")
            return False
        
        print(f"✅ {coord}: {sorted([d.name for d in actual_directions])}")
    
    print("✅ 过滤后的 Grid 邻居测试通过")
    return True


def test_special_topology_gateway_interfaces():
    """测试 special 拓扑中 gateway 节点的接口分配"""
    print("\n=== 测试 Special 拓扑 Gateway 接口 ===")

    from topo_gen.topology.special import SpecialTopology
    from topo_gen.core.types import TopologyType

    special_config = create_dm6_6_sample()
    topology = SpecialTopology(TopologyType.SPECIAL)
    size = 6

    # 测试 gateway 节点的接口数量
    gateway_test_cases = [
        # 参与 torus 桥接的 gateway 节点
        (Coordinate(0, 1), 4),  # 过滤grid(3) + torus桥接(1) = 4
        (Coordinate(1, 0), 4),  # 过滤grid(3) + torus桥接(1) = 4
        (Coordinate(1, 2), 4),  # 过滤grid(3) + internal桥接(1) = 4
        (Coordinate(1, 3), 4),  # 过滤grid(3) + internal桥接(1) = 4
    ]

    for coord, expected_min_interfaces in gateway_test_cases:
        neighbors = topology.get_neighbors(coord, size, special_config)
        actual_interfaces = len(neighbors)

        print(f"Gateway {coord}: {actual_interfaces} 个接口")
        for direction, neighbor in neighbors.items():
            print(f"  {direction.name}: {neighbor}")

        if actual_interfaces < expected_min_interfaces:
            print(f"❌ 错误: Gateway {coord} 应该至少有 {expected_min_interfaces} 个接口，实际有 {actual_interfaces} 个")
            return False

    # 测试非 gateway 节点的接口数量
    non_gateway_test_cases = [
        (Coordinate(0, 0), 2),  # 区域角落，只有2个邻居：南、东
        (Coordinate(1, 1), 4),  # 区域内部，有4个邻居：北、南、东、西
        (Coordinate(2, 0), 2),  # 区域边缘，只有2个邻居：北、东（南跨区域，西边界）
    ]

    for coord, expected_interfaces in non_gateway_test_cases:
        neighbors = topology.get_neighbors(coord, size, special_config)
        actual_interfaces = len(neighbors)

        print(f"Non-Gateway {coord}: {actual_interfaces} 个接口")

        if actual_interfaces != expected_interfaces:
            print(f"❌ 错误: Non-Gateway {coord} 应该有 {expected_interfaces} 个接口，实际有 {actual_interfaces} 个")
            return False

    print("✅ Special 拓扑 Gateway 接口测试通过")
    return True


def main():
    """主测试函数"""
    print("开始拓扑修复测试...\n")

    success = True

    # 测试 torus 拓扑
    if not test_torus_topology():
        success = False

    # 测试 special 拓扑
    if not test_special_topology_subregions():
        success = False

    if not test_filtered_grid_neighbors():
        success = False

    if not test_special_topology_gateway_interfaces():
        success = False

    print(f"\n{'='*50}")
    if success:
        print("🎉 所有测试通过！")
    else:
        print("❌ 部分测试失败")

    return success


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
