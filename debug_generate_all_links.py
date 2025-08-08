#!/usr/bin/env python3
"""
逐步调试 generate_all_links 函数
"""

import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from topo_gen.core.types import TopologyType, Coordinate
from topo_gen.core.models import TopologyConfig, NetworkConfig, OSPFConfig, BGPConfig
from topo_gen.topology.special import create_dm6_6_sample, get_filtered_grid_neighbors
from topo_gen.links import generate_link_ipv6


def manual_generate_all_links(config):
    """手动实现 generate_all_links 逻辑进行调试"""
    processed_pairs = set()
    links = []
    
    print("=== 手动执行 generate_all_links 逻辑 ===")
    
    print(f"拓扑类型: {config.topology_type}")
    print(f"Special 配置存在: {config.special_config is not None}")

    # 处理字符串和枚举值的比较
    is_special = (config.topology_type == TopologyType.SPECIAL or
                  str(config.topology_type).lower() == 'special')

    if is_special and config.special_config:
        print("处理 Special 拓扑...")
        print(f"include_base_connections: {config.special_config.include_base_connections}")

        # 1. 生成基础拓扑连接（如果启用）- 使用过滤后的邻居
        if config.special_config.include_base_connections:
            print("\n1. 生成基础拓扑连接（过滤后的 grid）")
            
            for row in range(config.size):
                for col in range(config.size):
                    coord = Coordinate(row, col)
                    
                    # Special 拓扑始终使用过滤后的 grid 邻居作为基础
                    neighbors = get_filtered_grid_neighbors(coord, config.size)
                    
                    if neighbors:  # 只有当有邻居时才打印
                        print(f"  节点 {coord}: {len(neighbors)} 个邻居")
                        for direction, neighbor_coord in neighbors.items():
                            pair = tuple(sorted([
                                (coord.row, coord.col),
                                (neighbor_coord.row, neighbor_coord.col)
                            ]))
                            
                            if pair not in processed_pairs:
                                processed_pairs.add(pair)
                                link = generate_link_ipv6(config.size, coord, neighbor_coord)
                                links.append(link)
                                print(f"    ✅ 添加: {pair}")
                            else:
                                print(f"    ⏭️  跳过: {pair}")
        
        # 2. 添加内部桥接连接
        print(f"\n2. 添加内部桥接连接 ({len(config.special_config.internal_bridge_edges)} 条)")
        for edge in config.special_config.internal_bridge_edges:
            pair = tuple(sorted([
                (edge[0].row, edge[0].col),
                (edge[1].row, edge[1].col)
            ]))
            
            if pair not in processed_pairs:
                processed_pairs.add(pair)
                link = generate_link_ipv6(config.size, edge[0], edge[1])
                links.append(link)
                print(f"  ✅ 添加 internal bridge: {pair}")
            else:
                print(f"  ⏭️  跳过 internal bridge: {pair}")
        
        # 3. 添加torus桥接连接
        print(f"\n3. 添加 torus 桥接连接 ({len(config.special_config.torus_bridge_edges)} 条)")
        for edge in config.special_config.torus_bridge_edges:
            pair = tuple(sorted([
                (edge[0].row, edge[0].col),
                (edge[1].row, edge[1].col)
            ]))
            
            if pair not in processed_pairs:
                processed_pairs.add(pair)
                link = generate_link_ipv6(config.size, edge[0], edge[1])
                links.append(link)
                print(f"  ✅ 添加 torus bridge: {pair}")
            else:
                print(f"  ⏭️  跳过 torus bridge: {pair}")
    
    print(f"\n手动生成结果: {len(links)} 条链路")
    return links


def main():
    """主函数"""
    print("开始逐步调试 generate_all_links...\n")
    
    special_config = create_dm6_6_sample()
    
    config = TopologyConfig(
        size=6,
        topology_type=TopologyType.SPECIAL,
        network_config=NetworkConfig(),
        ospf_config=OSPFConfig(),
        bgp_config=BGPConfig(as_number=65000),
        special_config=special_config
    )
    
    # 手动执行
    manual_links = manual_generate_all_links(config)
    
    # 调用实际函数
    from topo_gen.links import generate_all_links
    actual_links = generate_all_links(config)
    
    print(f"\n比较结果:")
    print(f"手动执行: {len(manual_links)} 条链路")
    print(f"实际函数: {len(actual_links)} 条链路")
    
    if len(manual_links) == len(actual_links):
        print("✅ 链路数量一致")
    else:
        print("❌ 链路数量不一致")


if __name__ == "__main__":
    main()
