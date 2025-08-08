#!/usr/bin/env python3
"""
调试 Torus 拓扑链路生成问题
"""

import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from topo_gen.core.types import TopologyType, Coordinate, Direction
from topo_gen.core.models import TopologyConfig, OSPFConfig, BFDConfig
from topo_gen.links import generate_all_links

def debug_torus_links():
    """调试Torus链路生成"""
    print("=== 调试 Torus 10x10 链路生成 ===")
    
    # 创建10x10 Torus配置
    config = TopologyConfig(
        size=10,
        topology_type=TopologyType.TORUS,
        multi_area=False,
        ospf_config=OSPFConfig(),
        bfd_config=BFDConfig(enabled=False)
    )
    
    print(f"配置: {config.size}x{config.size} {config.topology_type}")
    print(f"预期链路数: {2 * config.size * config.size} = {2 * 10 * 10}")
    
    # 手动模拟链路生成过程
    processed_pairs = set()
    links = []
    duplicate_attempts = []
    
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
                    links.append(pair)
                else:
                    print(f"    ⏭️  跳过重复: {pair}")
                    duplicate_attempts.append((coord, neighbor_coord, direction))
    
    print(f"\n=== 结果统计 ===")
    print(f"处理的节点数: {config.size * config.size}")
    print(f"生成的链路数: {len(links)}")
    print(f"预期链路数: {2 * config.size * config.size}")
    print(f"是否匹配: {'✅' if len(links) == 2 * config.size * config.size else '❌'}")
    print(f"重复尝试次数: {len(duplicate_attempts)}")
    
    # 检查是否有重复
    if len(set(links)) != len(links):
        print("❌ 发现重复链路!")
        duplicates = []
        seen = set()
        for link in links:
            if link in seen:
                duplicates.append(link)
            else:
                seen.add(link)
        print(f"重复链路: {duplicates}")
    else:
        print("✅ 没有重复链路")
    
    # 分析链路类型
    print(f"\n=== 链路类型分析 ===")
    horizontal_links = []
    vertical_links = []
    wrap_horizontal = []
    wrap_vertical = []
    
    for link in links:
        coord1 = Coordinate(link[0][0], link[0][1])
        coord2 = Coordinate(link[1][0], link[1][1])
        
        if coord1.row == coord2.row:  # 水平链路
            if abs(coord1.col - coord2.col) == 1:
                horizontal_links.append(link)
            elif abs(coord1.col - coord2.col) == config.size - 1:
                wrap_horizontal.append(link)
        elif coord1.col == coord2.col:  # 垂直链路
            if abs(coord1.row - coord2.row) == 1:
                vertical_links.append(link)
            elif abs(coord1.row - coord2.row) == config.size - 1:
                wrap_vertical.append(link)
    
    print(f"常规水平链路: {len(horizontal_links)} (预期: {config.size * (config.size - 1)})")
    print(f"常规垂直链路: {len(vertical_links)} (预期: {config.size * (config.size - 1)})")
    print(f"环绕水平链路: {len(wrap_horizontal)} (预期: {config.size})")
    print(f"环绕垂直链路: {len(wrap_vertical)} (预期: {config.size})")
    
    total_expected = 2 * config.size * (config.size - 1) + 2 * config.size
    print(f"总计: {len(links)} (预期: {total_expected})")
    
    # 使用实际的生成函数进行对比
    print(f"\n=== 使用实际生成函数 ===")
    actual_links = generate_all_links(config)
    print(f"实际生成的链路数: {len(actual_links)}")
    
    return len(links), len(actual_links)

def debug_small_torus():
    """调试小规模Torus以便理解问题"""
    print("\n=== 调试 3x3 Torus ===")
    
    config = TopologyConfig(
        size=3,
        topology_type=TopologyType.TORUS,
        multi_area=False,
        ospf_config=OSPFConfig(),
        bfd_config=BFDConfig(enabled=False)
    )
    
    from topo_gen.links import get_torus_neighbors
    
    # 显示每个节点的邻居
    for row in range(3):
        for col in range(3):
            coord = Coordinate(row, col)
            neighbors = get_torus_neighbors(coord, 3)
            print(f"节点 ({row},{col}): {[(d.name, f'({n.row},{n.col})') for d, n in neighbors.items()]}")
    
    # 生成链路
    processed_pairs = set()
    links = []
    
    for row in range(3):
        for col in range(3):
            coord = Coordinate(row, col)
            neighbors = get_torus_neighbors(coord, 3)
            
            for direction, neighbor_coord in neighbors.items():
                pair = tuple(sorted([
                    (coord.row, coord.col),
                    (neighbor_coord.row, neighbor_coord.col)
                ]))
                
                if pair not in processed_pairs:
                    processed_pairs.add(pair)
                    links.append(pair)
    
    print(f"3x3 Torus 链路数: {len(links)} (预期: {2 * 3 * 3} = 18)")
    print("链路列表:")
    for i, link in enumerate(links, 1):
        print(f"  {i:2d}. {link}")

if __name__ == "__main__":
    debug_torus_links()
    debug_small_torus()
