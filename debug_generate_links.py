#!/usr/bin/env python3
"""
直接调试 generate_all_links 函数
"""

import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from topo_gen.core.types import TopologyType, Coordinate
from topo_gen.core.models import TopologyConfig, NetworkConfig, OSPFConfig
from topo_gen.links import generate_all_links, get_neighbors_func


def debug_generate_all_links():
    """直接调试 generate_all_links 函数"""
    print("=== 直接调试 generate_all_links 函数 ===")
    
    config = TopologyConfig(
        size=4,
        topology_type=TopologyType.TORUS,
        network_config=NetworkConfig(),
        ospf_config=OSPFConfig()
    )
    
    # 手动复制 generate_all_links 的逻辑进行调试
    neighbors_func = get_neighbors_func(config.topology_type, config.size, config.special_config)
    processed_pairs = set()
    links = []
    
    print("手动执行 generate_all_links 逻辑:")
    
    for row in range(config.size):
        for col in range(config.size):
            coord = Coordinate(row, col)
            # 直接调用 get_torus_neighbors 进行测试
            from topo_gen.links import get_torus_neighbors
            neighbors = get_torus_neighbors(coord, config.size)
            
            print(f"\n节点 {coord}: {len(neighbors)} 个邻居")
            for direction, neighbor_coord in neighbors.items():
                print(f"  {direction.name}: {neighbor_coord}")
                
                pair = tuple(sorted([
                    (coord.row, coord.col),
                    (neighbor_coord.row, neighbor_coord.col)
                ]))
                
                if pair not in processed_pairs:
                    processed_pairs.add(pair)
                    print(f"    ✅ 添加链路: {pair}")
                    # 这里我们不实际生成链路对象，只计数
                    links.append(pair)
                else:
                    print(f"    ⏭️  跳过重复: {pair}")
    
    print(f"\n手动执行结果: {len(links)} 个链路")
    
    # 现在调用实际的 generate_all_links 函数
    actual_links = generate_all_links(config)
    print(f"实际函数结果: {len(actual_links)} 个链路")
    
    return len(links), len(actual_links)


def main():
    """主函数"""
    print("开始调试 generate_all_links 函数...\n")
    
    manual_count, actual_count = debug_generate_all_links()
    
    print(f"\n总结:")
    print(f"手动执行得到的链路数: {manual_count}")
    print(f"实际函数得到的链路数: {actual_count}")
    
    if manual_count == actual_count:
        print("✅ 结果一致")
    else:
        print("❌ 结果不一致")


if __name__ == "__main__":
    main()
