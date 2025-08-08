#!/usr/bin/env python3
"""
调试 Torus 拓扑链路生成
"""

import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from topo_gen.core.types import TopologyType, Coordinate
from topo_gen.core.models import TopologyConfig, NetworkConfig, OSPFConfig
from topo_gen.links import generate_all_links, get_torus_neighbors


def debug_torus_neighbors():
    """调试 torus 邻居生成"""
    print("=== 调试 Torus 邻居生成 ===")
    
    size = 4
    all_neighbors = {}
    
    for row in range(size):
        for col in range(size):
            coord = Coordinate(row, col)
            neighbors = get_torus_neighbors(coord, size)
            all_neighbors[coord] = neighbors
            
            print(f"节点 {coord}: {len(neighbors)} 个邻居")
            for direction, neighbor in neighbors.items():
                print(f"  {direction.name}: {neighbor}")
    
    # 计算总的连接数
    all_connections = set()
    for coord, neighbors in all_neighbors.items():
        for neighbor_coord in neighbors.values():
            pair = tuple(sorted([
                (coord.row, coord.col),
                (neighbor_coord.row, neighbor_coord.col)
            ]))
            all_connections.add(pair)
    
    print(f"\n总连接数: {len(all_connections)}")
    print(f"期望连接数: {2 * size * size}")
    
    return len(all_connections)


def debug_torus_links():
    """调试 torus 链路生成"""
    print("\n=== 调试 Torus 链路生成 ===")

    config = TopologyConfig(
        size=4,
        topology_type=TopologyType.TORUS,
        network_config=NetworkConfig(),
        ospf_config=OSPFConfig()
    )

    links = generate_all_links(config)
    print(f"生成了 {len(links)} 条链路")

    # 转换为坐标对集合进行比较
    generated_pairs = set()
    for link in links:
        # 从路由器名称提取坐标
        r1_parts = link.router1_name.split('_')
        r2_parts = link.router2_name.split('_')
        coord1 = (int(r1_parts[1]), int(r1_parts[2]))
        coord2 = (int(r2_parts[1]), int(r2_parts[2]))
        pair = tuple(sorted([coord1, coord2]))
        generated_pairs.add(pair)

    # 检查缺少的环绕连接
    print("\n检查环绕连接:")
    wrap_around_pairs = [
        ((0, 0), (0, 3)), ((0, 1), (0, 0)), ((0, 2), (0, 3)), ((0, 3), (0, 0)),  # 水平环绕
        ((0, 0), (3, 0)), ((1, 0), (0, 0)), ((2, 0), (3, 0)), ((3, 0), (0, 0)),  # 垂直环绕
    ]

    missing_wraps = []
    for pair in wrap_around_pairs:
        sorted_pair = tuple(sorted(pair))
        if sorted_pair not in generated_pairs:
            missing_wraps.append(sorted_pair)
            print(f"❌ 缺少环绕连接: {sorted_pair}")
        else:
            print(f"✅ 找到环绕连接: {sorted_pair}")

    print(f"\n缺少 {len(missing_wraps)} 个环绕连接")

    return len(links)


def debug_link_generation_process():
    """调试链路生成过程"""
    print("\n=== 调试链路生成过程 ===")

    from topo_gen.links import get_neighbors_func

    config = TopologyConfig(
        size=4,
        topology_type=TopologyType.TORUS,
        network_config=NetworkConfig(),
        ospf_config=OSPFConfig()
    )

    neighbors_func = get_neighbors_func(config.topology_type, config.size, config.special_config)
    processed_pairs = set()

    print("逐步处理每个节点:")
    for row in range(config.size):
        for col in range(config.size):
            coord = Coordinate(row, col)
            # 直接调用 get_torus_neighbors 进行测试
            neighbors = get_torus_neighbors(coord, config.size)

            print(f"\n节点 {coord}:")
            print(f"  邻居: {[(d.name, n) for d, n in neighbors.items()]}")
            for direction, neighbor_coord in neighbors.items():
                pair = tuple(sorted([
                    (coord.row, coord.col),
                    (neighbor_coord.row, neighbor_coord.col)
                ]))

                if pair not in processed_pairs:
                    processed_pairs.add(pair)
                    print(f"  ✅ 添加链路: {pair}")
                else:
                    print(f"  ⏭️  跳过重复: {pair}")

    print(f"\n总共处理了 {len(processed_pairs)} 个唯一链路")
    return len(processed_pairs)


def main():
    """主函数"""
    print("开始调试 Torus 拓扑...\n")

    neighbor_connections = debug_torus_neighbors()
    link_connections = debug_torus_links()
    process_connections = debug_link_generation_process()

    print(f"\n总结:")
    print(f"邻居计算得到的连接数: {neighbor_connections}")
    print(f"链路生成得到的连接数: {link_connections}")
    print(f"逐步处理得到的连接数: {process_connections}")

    if neighbor_connections == link_connections == process_connections:
        print("✅ 所有连接数一致")
    else:
        print("❌ 连接数不一致")


if __name__ == "__main__":
    main()
