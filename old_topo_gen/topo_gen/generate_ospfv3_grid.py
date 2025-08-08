#!/usr/bin/env python3
"""
OSPFv3 Grid 拓扑生成器
支持生成任意规模的方形 Grid 网络拓扑配置，使用 OSPFv3 路由协议
支持最大 4000 节点 (约 63x63)，支持单区域和多区域配置

Grid 拓扑特点：
- 边缘节点不环绕连接（与 Torus 的主要区别）
- 内部节点有4个邻居，边缘节点有2-3个邻居，角落节点有2个邻居
- 更符合实际网络部署场景

使用方法:
    python3 generate_ospfv3_grid.py --size 10                     # 生成 10x10 单区域拓扑
    python3 generate_ospfv3_grid.py --size 40 --multi-area        # 生成 40x40 多区域拓扑
    python3 generate_ospfv3_grid.py --size 20 --area-size 10      # 每10x10划分一个区域

作者: Augment Agent
日期: 2025-08-02
"""

import os
import sys
import shutil
import yaml
import argparse
import time
import math
from pathlib import Path
from joblib import Parallel, delayed
import threading
import ipaddress

class OSPFv3GridGenerator:
    """OSPFv3 Grid 拓扑生成器"""
    
    def __init__(self, size, source_dir="normal_test", multi_area=False, area_size=None, enable_bfd=False, enable_bgp=False, bgp_as=65000):
        self.size = size
        self.source_dir = source_dir
        self.target_dir = f"ospfv3_grid{size}x{size}_test"
        self.template_router = "router1"
        self.total_routers = size * size

        # 计算 Grid 拓扑的总连接数
        # 水平连接: (size-1) * size
        # 垂直连接: size * (size-1)
        self.total_links = 2 * size * (size - 1)

        # OSPFv3 特定配置
        self.multi_area = multi_area
        self.area_size = area_size or (10 if multi_area else size)  # 默认区域大小
        self.enable_bfd = enable_bfd  # BFD 支持

        # BGP 配置
        self.enable_bgp = enable_bgp
        self.bgp_as = bgp_as
        
        # IPv6 地址分配配置 - 符合 RFC 标准的层次化地址规划
        self.ipv6_global_prefix = "2001:db8::"  # 全局单播地址前缀 /32
        self.loopback_prefix = "2001:db8:1000::"  # 环回地址空间 /48
        self.link_prefix = "2001:db8:2000::"  # 点对点链路地址空间 /48
        self.mgmt_prefix = "2001:db8:3000::"  # 管理网络地址空间 /48
        
        # 线程锁
        self.print_lock = threading.Lock()
        
        # 验证和预警
        self._validate_parameters()
        self._check_system_requirements()
        self._calculate_area_layout()
    
    def _validate_parameters(self):
        """验证参数有效性"""
        if self.size <= 0:
            raise ValueError("网格大小必须大于0")
        
        if self.total_routers > 4000:
            raise ValueError(f"节点数 ({self.total_routers}) 超过4000的限制")
        
        if self.multi_area and self.area_size > self.size:
            raise ValueError(f"区域大小 ({self.area_size}) 不能大于网格大小 ({self.size})")
    
    def _check_system_requirements(self):
        """检查系统资源要求并给出警告"""
        memory_gb = (self.total_routers * 45) / 1024  # OSPFv3 比 BGP 稍微轻量
        
        print(f"=== {self.size}x{self.size} OSPFv3 Grid 拓扑信息 ===")
        print(f"节点数: {self.total_routers}")
        print(f"连接数: {self.total_links}")
        print(f"路由协议: OSPFv3")
        print(f"拓扑类型: Grid (非环绕)")
        print(f"区域模式: {'多区域' if self.multi_area else '单区域'}")
        print(f"BFD支持: {'启用' if self.enable_bfd else '禁用'}")
        print(f"预估内存需求: {memory_gb:.1f}GB")
        
        if self.total_routers > 100:
            print("⚠️  中大规模拓扑提醒:")
            print(f"   建议系统配置: {max(4, memory_gb):.0f}GB+ RAM, {max(2, self.total_routers//200)}+ CPU核心")
    
    def _calculate_area_layout(self):
        """计算区域布局"""
        if not self.multi_area:
            self.areas = {0: [(r, c) for r in range(self.size) for c in range(self.size)]}
            self.total_areas = 1
        else:
            self.areas = {}
            area_id = 0
            
            # 按区域大小划分网格
            for start_row in range(0, self.size, self.area_size):
                for start_col in range(0, self.size, self.area_size):
                    area_routers = []
                    for r in range(start_row, min(start_row + self.area_size, self.size)):
                        for c in range(start_col, min(start_col + self.area_size, self.size)):
                            area_routers.append((r, c))
                    
                    if area_routers:  # 确保区域不为空
                        self.areas[area_id] = area_routers
                        area_id += 1
            
            self.total_areas = len(self.areas)
            print(f"区域划分: {self.total_areas} 个区域，每区域最多 {self.area_size}x{self.area_size} 节点")
    
    def get_area_id(self, row, col):
        """获取指定位置的区域ID"""
        for area_id, routers in self.areas.items():
            if (row, col) in routers:
                return area_id
        return 0  # 默认区域
    
    def is_area_border_router(self, row, col):
        """判断是否为区域边界路由器 (ABR)"""
        if not self.multi_area:
            return False
        
        current_area = self.get_area_id(row, col)
        neighbors = self.get_valid_neighbors(row, col)
        
        for _, (n_row, n_col) in neighbors.items():
            neighbor_area = self.get_area_id(n_row, n_col)
            if neighbor_area != current_area:
                return True
        
        return False
    
    def is_edge_router(self, row, col):
        """判断是否为边缘路由器（在网格边缘的路由器）"""
        return row == 0 or row == self.size - 1 or col == 0 or col == self.size - 1
    
    def is_corner_router(self, row, col):
        """判断是否为角落路由器"""
        return ((row == 0 or row == self.size - 1) and 
                (col == 0 or col == self.size - 1))
    
    def get_valid_neighbors(self, row, col):
        """计算给定位置的有效邻居坐标 (Grid 拓扑 - 不环绕)"""
        neighbors = {}
        
        # 北邻居
        if row > 0:
            neighbors['north'] = (row - 1, col)
        
        # 南邻居
        if row < self.size - 1:
            neighbors['south'] = (row + 1, col)
        
        # 西邻居
        if col > 0:
            neighbors['west'] = (row, col - 1)
        
        # 东邻居
        if col < self.size - 1:
            neighbors['east'] = (row, col + 1)
        
        return neighbors
    
    def count_neighbors(self, row, col):
        """计算节点的邻居数量"""
        return len(self.get_valid_neighbors(row, col))
    
    def get_node_type(self, row, col):
        """获取节点类型"""
        if self.is_corner_router(row, col):
            return "corner"
        elif self.is_edge_router(row, col):
            return "edge"
        else:
            return "internal"
    
    def generate_router_id(self, row, col):
        """生成 OSPFv3 Router ID (IPv4 格式)"""
        if self.size <= 255:
            # 小规模网络: 10.row.col.1
            return f"10.{row}.{col}.1"
        else:
            # 大规模网络: 分层地址
            node_id = row * self.size + col
            subnet = node_id // 65534
            host_in_subnet = node_id % 65534
            
            high_byte = (host_in_subnet // 254) + 1
            low_byte = (host_in_subnet % 254) + 1
            
            return f"10.{subnet}.{high_byte}.{low_byte}"
    
    def generate_loopback_ipv6(self, row, col):
        """生成 IPv6 环回地址 - 符合 RFC 标准"""
        # 格式: 2001:db8:1000:area:row:col::1/128
        area_id = self.get_area_id(row, col)
        return f"2001:db8:1000:{area_id:04x}:{row:04x}:{col:04x}::1/128"
    
    def generate_link_ipv6(self, row1, col1, row2, col2):
        """为两个相邻路由器生成链路 IPv6 地址对 - 使用/127网络，避免网络地址"""
        # 确保节点顺序一致性
        node1_id = row1 * self.size + col1
        node2_id = row2 * self.size + col2

        if node1_id > node2_id:
            node1_id, node2_id = node2_id, node1_id
            row1, col1, row2, col2 = row2, col2, row1, col1

        # 生成全局唯一的链路标识符
        # 使用更大的地址空间确保唯一性
        link_id = (row1 * self.size + col1) * (self.size * self.size) + (row2 * self.size + col2)

        # 使用链路ID直接作为网络段标识，确保全局唯一
        network_segment = link_id & 0xFFFFFFFF  # 32位段标识

        # 构建/127网络地址
        # 格式: 2001:db8:2000:xxxx:yyyy:zzzz::/127
        high_16 = (network_segment >> 16) & 0xFFFF
        low_16 = network_segment & 0xFFFF

        network_base = f"2001:db8:2000:{high_16:04x}:{low_16:04x}:0::"
        network = f"{network_base}0/127"

        # 在/127网络中，可用地址是 ::1 和 ::2 (避免::0网络地址)
        addr1 = f"{network_base}1/127"  # 第一个路由器
        addr2 = f"{network_base}2/127"  # 第二个路由器

        return {
            'network': network,
            f'router_{row1:02d}_{col1:02d}': addr1,
            f'router_{row2:02d}_{col2:02d}': addr2
        }
    
    def safe_print(self, message):
        """线程安全的打印"""
        with self.print_lock:
            print(message)
    
    def track_progress(self, description, total_tasks):
        """创建进度跟踪器"""
        def track_function(func):
            """包装函数以提供进度反馈"""
            counter = [0]  # 使用列表以便在嵌套函数中修改
            
            def wrapper(*args, **kwargs):
                result = func(*args, **kwargs)
                counter[0] += 1
                if counter[0] % max(1, total_tasks // 20) == 0 or counter[0] == total_tasks:
                    self.safe_print(f"{description}: {counter[0]}/{total_tasks}")
                return result
            return wrapper
        return track_function

    def create_directory_structure(self):
        """创建目录结构"""
        self.safe_print("创建目录结构...")

        base_dir = Path(self.target_dir)
        base_dir.mkdir(exist_ok=True)
        etc_dir = base_dir / "etc"
        etc_dir.mkdir(exist_ok=True)

        def create_router_dir(row, col):
            router_dir = etc_dir / f"router_{row:02d}_{col:02d}"
            router_dir.mkdir(exist_ok=True)

            # 创建子目录
            for subdir in ["conf", "log"]:
                (router_dir / subdir).mkdir(exist_ok=True)

            # 创建日志文件
            log_dir = router_dir / "log"
            log_files = ["ospf6d.log", "zebra.log", "log.log", "route.log","fping.log"]
            if self.enable_bfd:
                log_files.append("bfdd.log")
            
            for log_name in log_files:
                log_file = log_dir / log_name
                log_file.touch()
                log_file.chmod(0o777)

        # 批量创建 - 使用joblib并行处理
        max_workers = min(10, max(1, self.total_routers // 50))
        
        # 创建所有任务参数
        tasks = [(row, col) for row in range(self.size) for col in range(self.size)]
        
        # 添加进度跟踪
        tracked_create_router_dir = self.track_progress("目录创建进度", len(tasks))(create_router_dir)
        
        # 使用joblib并行执行
        Parallel(n_jobs=max_workers, backend='threading')(
            delayed(tracked_create_router_dir)(row, col) for row, col in tasks
        )

        self.safe_print(f"创建了 {self.total_routers} 个路由器目录")
        return base_dir

    def copy_template_files(self):
        """复制模板文件"""
        self.safe_print("复制模板文件...")

        source_path = Path(self.source_dir) / "etc" / self.template_router
        if not source_path.exists():
            raise FileNotFoundError(f"模板目录不存在: {source_path}")

        target_base = Path(self.target_dir) / "etc"
        # 只复制基础模板文件，不包括 daemons (OSPFv3 需要专门的 daemons 配置)
        template_files = ["zebra.conf", "staticd.conf", "mgmtd.conf"]

        def copy_for_router(row, col):
            router_conf_dir = target_base / f"router_{row:02d}_{col:02d}" / "conf"
            for file_name in template_files:
                source_file = source_path / file_name
                if source_file.exists():
                    shutil.copy2(source_file, router_conf_dir / file_name)

        # 并行复制
        max_workers = min(8, max(1, self.total_routers // 100))
        
        # 创建所有任务参数
        tasks = [(row, col) for row in range(self.size) for col in range(self.size)]
        
        # 添加进度跟踪
        tracked_copy_for_router = self.track_progress("模板复制进度", len(tasks))(copy_for_router)
        
        # 使用joblib并行执行
        Parallel(n_jobs=max_workers, backend='threading')(
            delayed(tracked_copy_for_router)(row, col) for row, col in tasks
        )

        self.safe_print("模板文件复制完成")

    def generate_daemons_conf(self, row, col):
        """生成 OSPFv3 专用的 daemons 配置文件"""
        hostname = f"r{row:02d}_{col:02d}"

        return f"""# This file tells the frr package which daemons to start.
# OSPFv3 Grid configuration for {hostname}
#
# The watchfrr, zebra and staticd daemons are always started.
#
zebra=yes
bgpd={'yes' if self.enable_bgp else 'no'}
ospfd=no
ospf6d=yes
ripd=no
ripngd=no
isisd=no
pimd=no
ldpd=no
nhrpd=no
eigrpd=no
babeld=no
sharpd=no
pbrd=no
bfdd={'yes' if self.enable_bfd else 'no'}
fabricd=no
vrrpd=no

#
# If this option is set the /etc/init.d/frr script automatically loads
# the config via "vtysh -b" when the servers are started.
# Check /etc/pam.d/frr if you intend to use "vtysh"!
#
vtysh_enable=yes
zebra_options="  -A 127.0.0.1 -s 90000000"
bgpd_options="   -A 127.0.0.1"
ospfd_options="  -A 127.0.0.1"
ospf6d_options=" -A 127.0.0.1"
ripd_options="   -A 127.0.0.1"
ripngd_options=" -A 127.0.0.1"
isisd_options="  -A 127.0.0.1"
pimd_options="   -A 127.0.0.1"
ldpd_options="   -A 127.0.0.1"
nhrpd_options="  -A 127.0.0.1"
eigrpd_options=" -A 127.0.0.1"
babeld_options=" -A 127.0.0.1"
sharpd_options=" -A 127.0.0.1"
pbrd_options="   -A 127.0.0.1"
staticd_options="-A 127.0.0.1"
bfdd_options="   -A 127.0.0.1"
fabricd_options="-A 127.0.0.1"
vrrpd_options="  -A 127.0.0.1"

# The list of daemons to watch is automatically generated by the init script.
#watchfrr_options=""

# for debugging purposes, you can specify a "wrap" command to start instead
# of starting the daemon directly, e.g. to use valgrind on ospf6d:
#   ospf6d_wrap="/usr/bin/valgrind"
# or you can use "all_wrap" for all daemons, e.g. to use perf record:
#   all_wrap="/usr/bin/perf record --call-graph -"
# the normal daemon command is added to this at the end.
"""

    def generate_interface_addresses(self):
        """生成所有接口地址映射 - 使用固定的方向到接口映射"""
        self.safe_print("计算接口地址分配...")

        self.interface_addresses = {}  # {router_name: {interface: ipv6_addr}}
        self.link_networks = {}  # 存储链路网络信息

        processed_pairs = set()
        
        # 固定的方向到接口映射 - 与Torus保持一致
        direction_to_interface = {
            'north': 'eth1',
            'south': 'eth2', 
            'west': 'eth3',
            'east': 'eth4'
        }
        
        # 反向映射
        reverse_direction = {
            'north': 'south',
            'south': 'north', 
            'west': 'east',
            'east': 'west'
        }

        for row in range(self.size):
            for col in range(self.size):
                router_name = f"router_{row:02d}_{col:02d}"
                if router_name not in self.interface_addresses:
                    self.interface_addresses[router_name] = {}

                neighbors = self.get_valid_neighbors(row, col)

                for direction, (n_row, n_col) in neighbors.items():
                    neighbor_name = f"router_{n_row:02d}_{n_col:02d}"

                    pair = tuple(sorted([router_name, neighbor_name]))
                    if pair not in processed_pairs:
                        processed_pairs.add(pair)

                        # 生成链路地址
                        link_info = self.generate_link_ipv6(row, col, n_row, n_col)
                        self.link_networks[pair] = link_info

                        # 使用固定的方向到接口映射
                        current_intf = direction_to_interface[direction]
                        neighbor_direction = reverse_direction[direction]
                        neighbor_intf = direction_to_interface[neighbor_direction]

                        self.interface_addresses[router_name][current_intf] = link_info[router_name]

                        if neighbor_name not in self.interface_addresses:
                            self.interface_addresses[neighbor_name] = {}
                        self.interface_addresses[neighbor_name][neighbor_intf] = link_info[neighbor_name]

        self.safe_print(f"生成了 {len(self.link_networks)} 条链路的地址分配")

    def generate_bfd_profile_config(self):
        """生成 BFD Profile 配置"""
        if not self.enable_bfd:
            return ""
        
        return """bfd
 profile production
  detect-multiplier 2
  receive-interval 200
  transmit-interval 200

 !
 
 profile fast-convergence
  detect-multiplier 2
  receive-interval 100
  transmit-interval 100

 !

 profile edge-link
  detect-multiplier 3
  receive-interval 200
  transmit-interval 200

 !
!
"""

    def generate_ospf6d_conf(self, row, col):
        """生成 ospf6d.conf 配置"""
        hostname = f"r{row:02d}_{col:02d}"
        router_name = f"router_{row:02d}_{col:02d}"
        router_id = self.generate_router_id(row, col)
        loopback_ipv6 = self.generate_loopback_ipv6(row, col)
        area_id = self.get_area_id(row, col)
        is_abr = self.is_area_border_router(row, col)
        node_type = self.get_node_type(row, col)
        neighbor_count = self.count_neighbors(row, col)

        # 获取接口地址
        interfaces = self.interface_addresses.get(router_name, {})

        config = f"""!
! OSPFv3 configuration for {hostname} in {self.size}x{self.size} Grid
! Node type: {node_type} ({neighbor_count} neighbors)
! BFD enabled: {self.enable_bfd}
!
frr version 7.5.1_git
frr defaults traditional
!
hostname {hostname}
log file /var/log/frr/ospf6d.log
!
debug ospf6 neighbor state
debug ospf6 lsa unknown
debug ospf6 zebra
"""
        
        # 添加BFD调试信息
        if self.enable_bfd:
            config += """debug bfd peer
debug bfd network
!
"""
        
        config += "!\n"
        
        # 配置环回接口
        config += f"""interface lo
    ipv6 address {loopback_ipv6}
    ipv6 ospf6 area {area_id}.0.0.0
!
"""

        # 配置物理接口
        interface_names = sorted(interfaces.keys())
        for i, (intf, ipv6_addr) in enumerate(sorted(interfaces.items())):
            # 统一使用 fast-convergence BFD profile
            if self.enable_bfd:
                bfd_config = f"    ipv6 ospf6 bfd profile fast-convergence"
            else:
                bfd_config = ""
            
            # 根据接口方向设置OSPF cost
            # 东西向接口 (eth3=west, eth4=east): cost 40
            # 南北向接口 (eth1=north, eth2=south): cost 20
            if intf in ['eth3', 'eth4']:  # 东西向
                ospf_cost = 40
            elif intf in ['eth1', 'eth2']:  # 南北向
                ospf_cost = 20
            else:
                ospf_cost = 10  # 默认cost
            
            # 使用统一的OSPF参数 - 所有节点保持一致
            hello_interval = 1
            dead_interval = 10
            retransmit_interval = 5
            config += f"""interface {intf}
    ipv6 address {ipv6_addr}
    ipv6 ospf6 area {area_id}.0.0.0
    ipv6 ospf6 hello-interval {hello_interval}
    ipv6 ospf6 dead-interval {dead_interval}
    ipv6 ospf6 retransmit-interval {retransmit_interval}
    ipv6 ospf6 cost {ospf_cost}
    ipv6 ospf6 p2p-p2mp connected-prefixes exclude
    ipv6 ospf6 network point-to-point{f'''
{bfd_config}''' if bfd_config else ''}
!
"""

        # OSPFv3 路由器配置 - 使用统一的SPF参数
        spf_delay, spf_holdtime, spf_max_holdtime = 20 ,30, 100
        max_multipath = 3

        config += f"""router ospf6
    ospf6 router-id {router_id}
    area {area_id}.0.0.0 range {self.loopback_prefix}{row:04x}:{col:04x}::/128
    timers throttle spf {spf_delay} {spf_holdtime} {spf_max_holdtime}
    timers lsa min-arrival 0
    max_multipath {max_multipath}
"""

        # 如果是区域边界路由器，添加额外配置
        if is_abr:
            config += f"""    ! Area Border Router (ABR) configuration
    area {area_id}.0.0.0 export-list EXPORT_TO_BACKBONE
    area {area_id}.0.0.0 import-list IMPORT_FROM_BACKBONE
"""

        config += """!
line vty
!
"""

        return config

    def generate_zebra_conf(self, row, col):
        """生成 zebra.conf 配置"""
        hostname = f"r{row:02d}_{col:02d}"
        router_name = f"router_{row:02d}_{col:02d}"
        loopback_ipv6 = self.generate_loopback_ipv6(row, col)

        # 获取接口地址
        interfaces = self.interface_addresses.get(router_name, {})

        config = f"""!
! Zebra configuration for {hostname}
!
frr version 7.5.1_git
frr defaults traditional
!
hostname {hostname}
!
interface lo
    ipv6 address {loopback_ipv6}
!
"""

        # 配置物理接口
        for intf, ipv6_addr in sorted(interfaces.items()):
            config += f"""interface {intf}
    ipv6 address {ipv6_addr}
!
"""

        config += """line vty
!
ip forwarding
ipv6 forwarding
"""

        return config

    def generate_bfdd_conf(self, row, col):
        """生成 bfdd.conf 配置文件"""
        if not self.enable_bfd:
            return ""
        
        hostname = f"r{row:02d}_{col:02d}"
        router_name = f"router_{row:02d}_{col:02d}"
        
        config = f"""!
! BFD configuration for {hostname}
!
frr version 7.5.1_git
frr defaults traditional
!
hostname {hostname}
log file /var/log/frr/bfdd.log
!
debug bfd peer
debug bfd network
debug bfd zebra
!
"""
        
        # 添加BFD Profile配置 (全局配置，每个路由器都有)
        config += self.generate_bfd_profile_config()
        
        # 获取接口地址并配置BFD会话
        interfaces = self.interface_addresses.get(router_name, {})
        neighbors = self.get_valid_neighbors(row, col)
        
        config += "! BFD peer configurations\n"
        
        # 固定的方向到接口映射
        direction_to_interface = {
            'north': 'eth1',
            'south': 'eth2', 
            'west': 'eth3',
            'east': 'eth4'
        }
        
        # 反向映射
        reverse_direction = {
            'north': 'south',
            'south': 'north', 
            'west': 'east',
            'east': 'west'
        }
        
        interface_counter = 1
        for direction, (n_row, n_col) in neighbors.items():
            intf_name = direction_to_interface[direction]
            if intf_name in interfaces:
                neighbor_router = f"router_{n_row:02d}_{n_col:02d}"
                neighbor_interfaces = self.interface_addresses.get(neighbor_router, {})
                
                # 找到对应的邻居接口
                neighbor_direction = reverse_direction[direction]
                neighbor_intf = direction_to_interface[neighbor_direction]
                
                if neighbor_intf in neighbor_interfaces:
                    # 提取邻居的IPv6地址（去掉前缀长度）
                    neighbor_ipv6 = neighbor_interfaces[neighbor_intf].split('/')[0]
                    
                    # 选择BFD profile - 与torus保持一致，都使用fast-convergence
                    profile = "fast-convergence"
                    
                    config += f"""peer {neighbor_ipv6} interface {intf_name}
 profile {profile}
!
"""
            interface_counter += 1
        
        config += """line vty
!
"""
        
        return config

    def generate_staticd_conf(self, row, col):
        """生成 staticd.conf 配置"""
        hostname = f"r{row:02d}_{col:02d}"

        return f"""!
! Static routing configuration for {hostname}
!
frr version 7.5.1_git
frr defaults traditional
!
hostname {hostname}
!
line vty
!
"""

    def get_router_as_number(self, row, col):
        """根据路由器坐标确定其所属的AS号（Grid拓扑简化版）

        对于Grid拓扑，我们使用简单的域分割：
        - 所有路由器都在同一个AS中
        """
        return self.bgp_as

    def generate_bgpd_conf(self, row, col):
        """生成 bgpd.conf 配置（Grid拓扑版本）"""
        if not self.enable_bgp:
            return ""

        hostname = f"r{row:02d}_{col:02d}"
        router_name = f"router_{row:02d}_{col:02d}"
        router_id = self.generate_router_id(row, col)
        loopback_ipv6 = self.generate_loopback_ipv6(row, col)
        router_as = self.get_router_as_number(row, col)

        # 获取接口地址
        interfaces = self.interface_addresses.get(router_name, {})

        config = f"""!
! BGP configuration for {hostname} (Grid Node)
!
frr version 7.5.1_git
frr defaults traditional
!
hostname {hostname}
log file /var/log/frr/bgpd.log
!
debug bgp neighbor-events
debug bgp updates
debug bgp zebra
!
router bgp {router_as}
    bgp router-id {router_id}
    bgp log-neighbor-changes
    bgp bestpath as-path multipath-relax
    no bgp default ipv4-unicast
"""

        # 对于Grid拓扑，我们可以配置所有边界路由器为eBGP邻居
        # 或者配置所有路由器为iBGP邻居
        # 这里我们选择简单的iBGP全连接方案

        # 添加iBGP邻居（所有其他路由器）
        for other_row in range(self.size):
            for other_col in range(self.size):
                if other_row == row and other_col == col:
                    continue  # 跳过自己

                other_loopback = self.generate_loopback_ipv6(other_row, other_col)
                other_loopback_addr = other_loopback.split('/')[0]  # 去掉前缀长度

                config += f"""    neighbor {other_loopback_addr} remote-as {router_as}
    neighbor {other_loopback_addr} update-source lo
    neighbor {other_loopback_addr} next-hop-self
"""

        config += """!
    address-family ipv6 unicast
        network """ + loopback_ipv6 + """
"""

        # 激活所有iBGP邻居
        for other_row in range(self.size):
            for other_col in range(self.size):
                if other_row == row and other_col == col:
                    continue  # 跳过自己

                other_loopback = self.generate_loopback_ipv6(other_row, other_col)
                other_loopback_addr = other_loopback.split('/')[0]  # 去掉前缀长度

                config += f"""        neighbor {other_loopback_addr} activate
"""

        config += """        redistribute ospf6
        redistribute connected
    exit-address-family
!
line vty
!
"""

        return config

    def generate_router_configs(self):
        """生成所有路由器配置"""
        self.safe_print("生成路由器配置文件...")

        # 首先生成接口地址分配
        self.generate_interface_addresses()

        target_base = Path(self.target_dir) / "etc"

        def generate_configs_for_router(row, col):
            router_conf_dir = target_base / f"router_{row:02d}_{col:02d}" / "conf"

            configs = {
                "daemons": self.generate_daemons_conf(row, col),
                "ospf6d.conf": self.generate_ospf6d_conf(row, col),
                "zebra.conf": self.generate_zebra_conf(row, col),
                "staticd.conf": self.generate_staticd_conf(row, col)
            }

            # 如果启用了BFD，则生成bfdd.conf文件
            if self.enable_bfd:
                configs["bfdd.conf"] = self.generate_bfdd_conf(row, col)

            # 如果启用了BGP，则生成bgpd.conf文件
            if self.enable_bgp:
                configs["bgpd.conf"] = self.generate_bgpd_conf(row, col)

            for filename, content in configs.items():
                with open(router_conf_dir / filename, "w") as f:
                    f.write(content)

        # 并行生成配置
        max_workers = min(6, max(1, self.total_routers // 150))
        
        # 创建所有任务参数
        tasks = [(row, col) for row in range(self.size) for col in range(self.size)]
        
        # 添加进度跟踪
        tracked_generate_configs = self.track_progress("配置生成进度", len(tasks))(generate_configs_for_router)
        
        # 使用joblib并行执行
        Parallel(n_jobs=max_workers, backend='threading')(
            delayed(tracked_generate_configs)(row, col) for row, col in tasks
        )

        self.safe_print("路由器配置生成完成")

    def generate_mgmt_network(self):
        """生成管理网络配置 - 使用专用的管理地址空间"""
        # 根据规模选择合适的管理网络
        if self.total_routers <= 254:
            return {
                "ipv4-subnet": "192.168.200.0/24",
                "ipv6-subnet": "2001:db8:3000:0::/64"
            }
        elif self.total_routers <= 65534:
            return {
                "ipv4-subnet": "10.100.0.0/16",
                "ipv6-subnet": "2001:db8:3000::/56"
            }
        else:
            return {
                "ipv4-subnet": "10.100.0.0/12",
                "ipv6-subnet": "2001:db8:3000::/48"
            }

    def generate_clab_yaml(self):
        """生成 ContainerLab YAML 配置"""
        self.safe_print("生成 ContainerLab 配置...")

        # 节点配置
        nodes = {}
        for row in range(self.size):
            for col in range(self.size):
                router_name = f"router_{row:02d}_{col:02d}"
                nodes[router_name] = {
                    "kind": "linux",
                    "image": "docker.cnb.cool/jmncnic/frrbgpls/origin:latest",
                    "binds": [
                        f"etc/{router_name}/conf:/etc/frr",
                        f"etc/{router_name}/log:/var/log/frr",
                    ]
                }

        # 连接配置 - Grid 拓扑，使用固定的方向到接口映射
        self.safe_print("计算网络连接...")
        links = []
        processed_pairs = set()
        
        # 固定的方向到接口映射 - 与接口地址分配保持一致
        direction_to_interface = {
            'north': 'eth1',
            'south': 'eth2', 
            'west': 'eth3',
            'east': 'eth4'
        }
        
        # 反向映射
        reverse_direction = {
            'north': 'south',
            'south': 'north', 
            'west': 'east',
            'east': 'west'
        }

        for row in range(self.size):
            for col in range(self.size):
                current_router = f"router_{row:02d}_{col:02d}"
                neighbors = self.get_valid_neighbors(row, col)

                for direction, (n_row, n_col) in neighbors.items():
                    neighbor_router = f"router_{n_row:02d}_{n_col:02d}"

                    pair = tuple(sorted([current_router, neighbor_router]))
                    if pair not in processed_pairs:
                        processed_pairs.add(pair)

                        # 使用固定的方向到接口映射
                        current_intf = direction_to_interface[direction]
                        neighbor_direction = reverse_direction[direction]
                        neighbor_intf = direction_to_interface[neighbor_direction]

                        links.append({
                            "endpoints": [
                                f"{current_router}:{current_intf}",
                                f"{neighbor_router}:{neighbor_intf}"
                            ]
                        })

            # 显示进度
            if (row + 1) % max(1, self.size // 10) == 0 or row == self.size - 1:
                self.safe_print(f"连接计算进度: {row + 1}/{self.size} 行")

        # 生成完整配置
        mgmt_config = self.generate_mgmt_network()
        config = {
            "name": f"ospfv3-grid{self.size}x{self.size}",
            "mgmt": {
                "network": f"ospfv3_grid_mgmt_{self.size}x{self.size}",
                **mgmt_config
            },
            "topology": {
                "nodes": nodes,
                "links": links
            }
        }

        # 写入文件
        yaml_file = Path(self.target_dir) / f"ospfv3_grid{self.size}x{self.size}.clab.yaml"
        with open(yaml_file, "w") as f:
            yaml.dump(config, f, default_flow_style=False, indent=2)

        self.safe_print(f"生成拓扑文件: {yaml_file}")
        self.safe_print(f"节点数: {len(nodes)}, 连接数: {len(links)}")

    def print_topology_stats(self):
        """打印拓扑统计信息"""
        corner_count = 4 if self.size > 1 else 1
        edge_count = max(0, 4 * (self.size - 2)) if self.size > 2 else 0
        internal_count = max(0, (self.size - 2) ** 2) if self.size > 2 else 0
        
        print(f"\n=== Grid 拓扑节点分布 ===")
        print(f"角落节点: {corner_count} (2个邻居)")
        print(f"边缘节点: {edge_count} (3个邻居)")
        print(f"内部节点: {internal_count} (4个邻居)")
        print(f"总节点数: {corner_count + edge_count + internal_count}")
        
        # 验证计算
        assert corner_count + edge_count + internal_count == self.total_routers

    def print_summary(self):
        """打印摘要信息"""
        print(f"\n=== {self.size}x{self.size} OSPFv3 Grid 拓扑摘要 ===")
        print(f"总节点数: {self.total_routers}")
        print(f"总连接数: {self.total_links}")
        print(f"路由协议: OSPFv3")
        print(f"拓扑类型: Grid (非环绕)")
        print(f"BFD支持: {'启用' if self.enable_bfd else '禁用'}")
        print(f"区域模式: {'多区域' if self.multi_area else '单区域'}")
        if self.multi_area:
            print(f"区域数量: {self.total_areas}")
            print(f"区域大小: {self.area_size}x{self.area_size}")
        
        # 打印拓扑统计
        self.print_topology_stats()
        
        if self.enable_bfd:
            print(f"\n=== BFD 配置摘要 ===")
            print("BFD Profiles:")
            print("  - production: 200ms 间隔, 2倍检测")
            print("  - fast-convergence: 100ms 间隔, 2倍检测")
            print("  - edge-link: 200ms 间隔, 3倍检测")
            print("Profile 分配策略:")
            print("  - ospf6d.conf 中所有接口: fast-convergence")
            print("  - bfdd.conf 中所有连接: fast-convergence")

        print(f"\n=== OSPF Cost 配置 ===")
        print("接口Cost分配:")
        print("  - 南北向接口 (eth1=north, eth2=south): cost 20")
        print("  - 东西向接口 (eth3=west, eth4=east): cost 40")
        print("  - 其他接口: cost 10 (默认)")
        print("说明: 南北向路径成本更低，优先选择南北向路由")

        # 地址示例
        corners = [(0, 0), (0, self.size-1), (self.size-1, 0), (self.size-1, self.size-1)]
        print(f"\n=== 地址分配示例 (四个角) ===")
        for row, col in corners:
            router_name = f"router_{row:02d}_{col:02d}"
            router_id = self.generate_router_id(row, col)
            loopback = self.generate_loopback_ipv6(row, col)
            area_id = self.get_area_id(row, col)
            is_abr = self.is_area_border_router(row, col)
            node_type = self.get_node_type(row, col)
            neighbor_count = self.count_neighbors(row, col)
            abr_status = " (ABR)" if is_abr else ""
            print(f"{router_name}: RouterID {router_id}, Area {area_id}.0.0.0{abr_status}")
            print(f"  类型: {node_type} ({neighbor_count} 邻居)")
            print(f"  环回地址: {loopback}")

        # 部署命令
        yaml_file = f"{self.target_dir}/ospfv3_grid{self.size}x{self.size}.clab.yaml"
        print(f"\n=== 部署命令 ===")
        print(f"部署: sudo containerlab deploy -t {yaml_file}")
        print(f"销毁: sudo containerlab destroy -t {yaml_file}")
        print(f"检查: sudo containerlab inspect -t ospfv3-grid{self.size}x{self.size}")
        print(f"连接: sudo docker exec -it clab-ospfv3-grid{self.size}x{self.size}-router_00_00 vtysh")

        # 验证命令
        print(f"\n=== OSPFv3 验证命令 ===")
        print("查看邻居: show ipv6 ospf6 neighbor")
        print("查看路由表: show ipv6 route ospf6")
        print("查看LSA: show ipv6 ospf6 database")
        print("查看接口: show ipv6 ospf6 interface")
        
        if self.enable_bfd:
            print(f"\n=== BFD 验证命令 ===")
            print("查看BFD会话: show bfd peers")
            print("查看BFD详情: show bfd peers detail")
            print("查看BFD计数器: show bfd peers counters")
            print("查看BFD profile: show bfd profile")
            print("BFD调试: debug bfd peer")
            print("BFD网络调试: debug bfd network")

        # 资源提醒
        memory_gb = (self.total_routers * 45) / 1024
        if memory_gb > 2:
            print(f"\n⚠️  资源提醒:")
            print(f"预估内存需求: {memory_gb:.1f}GB")
            if self.total_routers > 500:
                print("建议分批部署，每批50-100个容器")

    def generate(self):
        """执行完整生成流程"""
        start_time = time.time()

        print(f"开始生成 {self.size}x{self.size} OSPFv3 Grid 拓扑...")

        try:
            self.create_directory_structure()
            self.copy_template_files()
            self.generate_router_configs()
            self.generate_clab_yaml()

            self.print_summary()

            elapsed = time.time() - start_time
            print(f"\n✅ 生成完成！耗时: {elapsed:.2f}秒")
            print(f"配置位置: {self.target_dir}/")

        except Exception as e:
            print(f"\n❌ 生成失败: {e}")
            raise

def main():
    parser = argparse.ArgumentParser(
        description="OSPFv3 Grid 网络拓扑生成器 (支持最大4000节点)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Grid 拓扑特点:
  - 边缘节点不环绕连接（与 Torus 的主要区别）
  - 角落节点: 2个邻居
  - 边缘节点: 3个邻居  
  - 内部节点: 4个邻居
  - 更符合实际网络部署场景

示例用法:
  %(prog)s --size 10                           # 生成 10x10 单区域拓扑
  %(prog)s --size 40 --multi-area              # 生成 40x40 多区域拓扑
  %(prog)s --size 20 --area-size 10            # 每10x10划分一个区域
  %(prog)s --size 5 --enable-bfd               # 启用BFD支持
  %(prog)s --size 5 --yes                      # 跳过确认直接生成
        """
    )

    parser.add_argument("--size", type=int, required=True,
                       help="方形网格的边长 (生成 size x size 的拓扑)")
    parser.add_argument("--multi-area", action="store_true",
                       help="启用多区域模式")
    parser.add_argument("--area-size", type=int, default=None,
                       help="区域大小 (仅在多区域模式下有效，默认为10)")
    parser.add_argument("--enable-bfd", action="store_true",
                       help="启用BFD (Bidirectional Forwarding Detection) 支持")
    parser.add_argument("--source", type=str, default="normal_test",
                       help="模板源目录 (默认: normal_test)")
    parser.add_argument("--yes", action="store_true",
                       help="跳过确认，直接生成")

    args = parser.parse_args()

    # 验证参数
    if args.size <= 0:
        print("❌ 错误: size 必须大于 0")
        sys.exit(1)

    total_nodes = args.size * args.size
    if total_nodes > 4000:
        print(f"❌ 错误: 节点数 ({total_nodes}) 超过 4000 的限制")
        max_size = int(math.sqrt(4000))
        print(f"建议: 最大支持 {max_size}x{max_size} = {max_size**2} 节点")
        sys.exit(1)

    if not os.path.exists(args.source):
        print(f"❌ 错误: 源目录 {args.source} 不存在")
        sys.exit(1)

    if args.multi_area and args.area_size and args.area_size > args.size:
        print(f"❌ 错误: 区域大小 ({args.area_size}) 不能大于网格大小 ({args.size})")
        sys.exit(1)

    # 创建生成器
    try:
        generator = OSPFv3GridGenerator(
            args.size,
            args.source,
            args.multi_area,
            args.area_size,
            args.enable_bfd
        )
    except ValueError as e:
        print(f"❌ 参数错误: {e}")
        sys.exit(1)

    # 用户确认
    if not args.yes:
        if total_nodes > 100:
            print(f"\n即将生成大规模网络:")
            print(f"  规模: {args.size}x{args.size}")
            print(f"  节点数: {total_nodes}")
            print(f"  协议: OSPFv3")
            print(f"  拓扑: Grid (非环绕)")
            print(f"  BFD支持: {'启用' if args.enable_bfd else '禁用'}")
            print(f"  区域模式: {'多区域' if args.multi_area else '单区域'}")
            if args.multi_area:
                print(f"  区域大小: {args.area_size or 10}x{args.area_size or 10}")
            print(f"  这可能需要较多系统资源")

        response = input(f"\n确认生成 {args.size}x{args.size} OSPFv3 Grid 拓扑? (y/N): ")
        if response.lower() not in ['y', 'yes']:
            print("已取消")
            return

    # 执行生成
    generator.generate()

if __name__ == "__main__":
    main()
