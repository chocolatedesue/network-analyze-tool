#!/usr/bin/env python3
"""
调试 Special 拓扑链路生成
"""

import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from topo_gen.core.types import TopologyType, Coordinate
from topo_gen.core.models import TopologyConfig, NetworkConfig, OSPFConfig, BGPConfig
from topo_gen.topology.special import create_dm6_6_sample
from topo_gen.links import generate_all_links


def debug_special_topology():
    """调试 special 拓扑链路生成"""
    print("=== 调试 Special 拓扑链路生成 ===")
    
    special_config = create_dm6_6_sample()
    
    config = TopologyConfig(
        size=6,
        topology_type=TopologyType.SPECIAL,
        network_config=NetworkConfig(),
        ospf_config=OSPFConfig(),
        bgp_config=BGPConfig(as_number=65000),
        special_config=special_config
    )
    
    print("Special 配置:")
    print(f"  Internal bridge edges: {len(special_config.internal_bridge_edges)}")
    for edge in special_config.internal_bridge_edges:
        print(f"    {edge[0]} <-> {edge[1]}")
    
    print(f"  Torus bridge edges: {len(special_config.torus_bridge_edges)}")
    for edge in special_config.torus_bridge_edges:
        print(f"    {edge[0]} <-> {edge[1]}")
    
    # 生成链路
    links = generate_all_links(config)
    print(f"\n生成了 {len(links)} 条链路")

    # 显示前几条链路作为示例
    print("\n前 10 条链路:")
    for i, link in enumerate(links[:10]):
        print(f"  {i+1}: {link.router1_name} <-> {link.router2_name}")

    if len(links) > 10:
        print("  ...")
        print(f"\n后 5 条链路:")
        for i, link in enumerate(links[-5:], len(links)-4):
            print(f"  {i}: {link.router1_name} <-> {link.router2_name}")
    
    # 转换为坐标对集合
    generated_pairs = set()
    for link in links:
        # 从路由器名称提取坐标
        r1_parts = link.router1_name.split('_')
        r2_parts = link.router2_name.split('_')
        coord1 = (int(r1_parts[1]), int(r1_parts[2]))
        coord2 = (int(r2_parts[1]), int(r2_parts[2]))
        pair = tuple(sorted([coord1, coord2]))
        generated_pairs.add(pair)
    
    # 检查 internal bridge 连接
    print("\n检查 Internal Bridge 连接:")
    for edge in special_config.internal_bridge_edges:
        pair = tuple(sorted([
            (edge[0].row, edge[0].col),
            (edge[1].row, edge[1].col)
        ]))
        if pair in generated_pairs:
            print(f"  ✅ 找到: {pair}")
        else:
            print(f"  ❌ 缺少: {pair}")
    
    # 检查 torus bridge 连接
    print("\n检查 Torus Bridge 连接:")
    for edge in special_config.torus_bridge_edges:
        pair = tuple(sorted([
            (edge[0].row, edge[0].col),
            (edge[1].row, edge[1].col)
        ]))
        if pair in generated_pairs:
            print(f"  ✅ 找到: {pair}")
        else:
            print(f"  ❌ 缺少: {pair}")
    
    # 分析链路类型
    print(f"\n链路分析:")
    
    # 计算每个 3x3 子区域的内部链路
    subregion_links = 0
    for region_row in range(2):  # 0, 1
        for region_col in range(2):  # 0, 1
            region_links = 0
            for row in range(3):
                for col in range(3):
                    coord = (region_row * 3 + row, region_col * 3 + col)
                    # 检查右邻居
                    if col < 2:
                        right_coord = (region_row * 3 + row, region_col * 3 + col + 1)
                        pair = tuple(sorted([coord, right_coord]))
                        if pair in generated_pairs:
                            region_links += 1
                    # 检查下邻居
                    if row < 2:
                        down_coord = (region_row * 3 + row + 1, region_col * 3 + col)
                        pair = tuple(sorted([coord, down_coord]))
                        if pair in generated_pairs:
                            region_links += 1
            print(f"  区域 {region_row * 2 + region_col}: {region_links} 条内部链路")
            subregion_links += region_links
    
    internal_bridge_found = sum(1 for edge in special_config.internal_bridge_edges 
                               if tuple(sorted([(edge[0].row, edge[0].col), (edge[1].row, edge[1].col)])) in generated_pairs)
    
    torus_bridge_found = sum(1 for edge in special_config.torus_bridge_edges 
                            if tuple(sorted([(edge[0].row, edge[0].col), (edge[1].row, edge[1].col)])) in generated_pairs)
    
    print(f"  子区域内部链路: {subregion_links}")
    print(f"  Internal bridge 链路: {internal_bridge_found}/{len(special_config.internal_bridge_edges)}")
    print(f"  Torus bridge 链路: {torus_bridge_found}/{len(special_config.torus_bridge_edges)}")
    print(f"  总计: {subregion_links + internal_bridge_found + torus_bridge_found}")
    
    return len(links)


def test_filtered_neighbors():
    """测试过滤后的邻居函数"""
    print("\n=== 测试过滤后的邻居函数 ===")

    from topo_gen.topology.special import get_filtered_grid_neighbors

    # 测试跨区域边界的节点
    test_coords = [
        Coordinate(0, 2),  # 区域0右边界
        Coordinate(0, 3),  # 区域1左边界
        Coordinate(2, 2),  # 区域0右下角
        Coordinate(2, 3),  # 区域1左下角
    ]

    for coord in test_coords:
        neighbors = get_filtered_grid_neighbors(coord, 6)
        print(f"节点 {coord}: {len(neighbors)} 个邻居")
        for direction, neighbor in neighbors.items():
            print(f"  {direction.name}: {neighbor}")


def main():
    """主函数"""
    print("开始调试 Special 拓扑...\n")

    link_count = debug_special_topology()
    test_filtered_neighbors()

    print(f"\n总结:")
    print(f"实际生成的链路数: {link_count}")


if __name__ == "__main__":
    main()
