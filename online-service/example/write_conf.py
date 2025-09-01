import shutil
import os
from pathlib import Path
import argparse
import zipfile
import os

def del_dir():
    conf_root = Path("conf")
    if not conf_root.exists():
        return
    for child in conf_root.iterdir():
        if child.is_dir() and child.name.startswith("Sat"):
            try:
                shutil.rmtree(child)
            except Exception as e:
                print(f"删除 {child} 时出错: {str(e)}")

def divide_area(i,m,n):  # m条轨道, 每条轨道n个卫星
    k=3 #每个域k条轨道
    area =i // (n*k)   # 域编号
    orbit = i // n   # 轨道编号
    number = i % n   # 轨道内卫星编号

    location = orbit % k  # 域内位置, location=0 左边界, location=k-1 右边界
    border_router=-1  #border_router=0 左边界, border_router=1 右边界
    if(location==0 and number==5):
        border_router=0
    elif(location==k-1 and number==5):
        border_router=1

    return area, orbit, number, k, location, border_router

#zebra 配置
def write_zebra_conf(m,n):
    for i in range(m*n):
        area, orbit, number, k, location, border_router = divide_area(i,m,n)
        zebra_conf = f"""!
hostname Sat{i}
!
interface lo
  ipv6 address fd00::{area}:{orbit}:{number}/128
  ip forwarding
  ipv6 forwarding
!
log timestamp precision 6
log file /var/log/frr/zebra.log
!
"""
        os.makedirs(f"conf/Sat{i}/frr_conf", exist_ok=True)
        with open(f"conf/Sat{i}/frr_conf/zebra.conf", "w") as f:
            f.write(zebra_conf)

#ospf6 配置
def write_ospf6_conf(m,n):
    for i in range(m*n):
        area, orbit, number, k, location, border_router = divide_area(i,m,n)
        if location == 0: #左边界
            ospf6_conf = f"""!
frr version 8.4-my-manual-build
frr defaults traditional
hostname Sat{i}
!
interface eth0
  ipv6 ospf6 area 0.0.0.0
  ipv6 ospf6 hello-interval 60
  ipv6 ospf6 dead-interval 180
!
interface eth1
  ipv6 ospf6 area 0.0.0.0
  ipv6 ospf6 hello-interval 60
  ipv6 ospf6 dead-interval 180
!
interface eth3
  ipv6 ospf6 area 0.0.0.0
  ipv6 ospf6 hello-interval 60
  ipv6 ospf6 dead-interval 180
!
router ospf6
  ospf6 router-id 10.{area}.{orbit}.{number}
  redistribute connected
  redistribute bgp
!
""" 
        elif 1 <= location and location <= k-2: #域内部
            ospf6_conf = f"""!
frr version 8.4-my-manual-build
frr defaults traditional
hostname Sat{i}
!
interface eth0
  ipv6 ospf6 area 0.0.0.0
  ipv6 ospf6 hello-interval 60
  ipv6 ospf6 dead-interval 180
!
interface eth1
  ipv6 ospf6 area 0.0.0.0
  ipv6 ospf6 hello-interval 60
  ipv6 ospf6 dead-interval 180
!
interface eth2
  ipv6 ospf6 area 0.0.0.0
  ipv6 ospf6 hello-interval 60
  ipv6 ospf6 dead-interval 180
!
interface eth3
  ipv6 ospf6 area 0.0.0.0
  ipv6 ospf6 hello-interval 60
  ipv6 ospf6 dead-interval 180
!
router ospf6
  ospf6 router-id 10.{area}.{orbit}.{number}
  redistribute connected
  redistribute bgp
!
"""
        elif location == k-1:  #右边界
            ospf6_conf = f"""!
frr version 8.4-my-manual-build
frr defaults traditional
hostname Sat{i}
!
interface eth0
  ipv6 ospf6 area 0.0.0.0
  ipv6 ospf6 hello-interval 60
  ipv6 ospf6 dead-interval 180
!
interface eth1
  ipv6 ospf6 area 0.0.0.0
  ipv6 ospf6 hello-interval 60
  ipv6 ospf6 dead-interval 180
!
interface eth2
  ipv6 ospf6 area 0.0.0.0
  ipv6 ospf6 hello-interval 60
  ipv6 ospf6 dead-interval 180
!
router ospf6
  ospf6 router-id 10.{area}.{orbit}.{number}
  redistribute connected
  redistribute bgp
!
"""
        # 确保目录存在
        os.makedirs(f"conf/Sat{i}/frr_conf", exist_ok=True)
        os.makedirs(f"conf/Sat{i}/frr_log", exist_ok=True)
    
        with open(f"conf/Sat{i}/frr_conf/ospf6d.conf", "w") as f:
            f.write(ospf6_conf)

#bgp配置
def write_bgp_conf(m,n):
    for i in range(m*n):
        area, orbit, number, k, location, border_router = divide_area(i,m,n)
        as_number=area+1
        if(border_router==0): #左边界
            bgp_conf = f"""!
hostname Sat{i}
!
router bgp {as_number}
  bgp router-id 192.{area}.{orbit}.{number}
  timers bgp 60 180
  no bgp ebgp-requires-policy
  no bgp network import-check
  neighbor eth2 interface remote-as external
  neighbor eth2 timers connect 5
  neighbor fd00::{area}:{orbit+2}:{number} remote-as {as_number}
  neighbor fd00::{area}:{orbit+2}:{number} update-source lo
  !
  address-family ipv6 unicast
    neighbor eth2 activate
    neighbor fd00::{area}:{orbit+2}:{number} activate
    network fd00::{area}:{orbit}:0/112
    network fd00::{area}:{orbit+1}:0/112
    network fd00::{area}:{orbit+2}:0/112
  exit-address-family
!
"""
            os.makedirs(f"conf/Sat{i}/frr_conf", exist_ok=True)
            with open(f"conf/Sat{i}/frr_conf/bgpd.conf", "w") as f:
                f.write(bgp_conf)
        
        elif(border_router==1):  #右边界
            bgp_conf = f"""!
hostname Sat{i}
!
router bgp {as_number}
  bgp router-id 192.{area}.{orbit}.{number}
  timers bgp 60 180
  no bgp ebgp-requires-policy
  no bgp network import-check
  neighbor eth3 interface remote-as external
  neighbor eth3 timers connect 5
  neighbor fd00::{area}:{orbit-2}:{number} remote-as {as_number}
  neighbor fd00::{area}:{orbit-2}:{number} update-source lo
  !
  address-family ipv6 unicast
    neighbor eth3 activate
    neighbor fd00::{area}:{orbit-2}:{number} activate
    network fd00::{area}:{orbit}:0/112
    network fd00::{area}:{orbit-1}:0/112
    network fd00::{area}:{orbit-2}:0/112
  exit-address-family
!
"""
            os.makedirs(f"conf/Sat{i}/frr_conf", exist_ok=True)
            with open(f"conf/Sat{i}/frr_conf/bgpd.conf", "w") as f:
                f.write(bgp_conf)

#daemons配置
def write_daemons_conf(m,n):
    for i in range(m*n):
        area, orbit, number, k, location, border_router = divide_area(i,m,n)
        if (border_router==0 or border_router==1):
            src = "daemons_bgp_ospf6"
        else: 
            src = "daemons_ospf6"
        dst = f"conf/Sat{i}/frr_conf/daemons"
        # 确保目标目录存在
        os.makedirs(os.path.dirname(dst), exist_ok=True)
    
        # 复制文件
        shutil.copy(src, dst)


def write_config_yaml(m, n):
    total = m * n
    yaml_path = Path("conf/config.yaml")
    if not yaml_path.exists():
        print(f"未找到文件: {yaml_path}")
        return
    content = yaml_path.read_text()
    lines = content.splitlines()

    try:
        start_idx = next(i for i, line in enumerate(lines) if line.strip() == "fixed_nodes:")
        end_idx = next(i for i, line in enumerate(lines[start_idx+1:], start=start_idx+1) if line.strip().startswith("links:"))
    except StopIteration:
        print("未找到 fixed_nodes: 或 links: 锚点，跳过 config.yaml 更新")
        return

    # 提取并保留非 Sat 节点的块
    preserved_blocks = []
    i = start_idx + 1
    while i < end_idx:
        line = lines[i]
        # 仅识别与 fixed_nodes 下同级键（两个空格缩进且以 ":" 结尾）
        if line.startswith("  ") and not line.startswith("    ") and line.rstrip().endswith(":"):
            key_name = line.strip().rstrip(":")
            # 找到此块的结束位置（下一个同级或到 end_idx）
            j = i + 1
            while j < end_idx and not (lines[j].startswith("  ") and not lines[j].startswith("    ") and lines[j].rstrip().endswith(":")):
                j += 1
            block_lines = lines[i:j]
            if not key_name.startswith("Sat"):
                preserved_blocks.extend(block_lines)
            # 移动到下一个块
            i = j
        else:
            # 不是块起始，直接保留（防御性处理）
            preserved_blocks.append(line)
            i += 1

    # 生成新的 Sat 节点块
    generated = []
    for idx in range(total):
        generated.append(f"  Sat{idx}:")
        generated.append("    template: sat_tmpl")
        generated.append(f"    sat_id: {idx}")

    # 拼装：fixed_nodes: + 新的 Sat + 原有非 Sat 保留 + 其余文件
    new_lines = []
    new_lines.extend(lines[:start_idx+1])
    new_lines.extend(generated)
    new_lines.extend(preserved_blocks)
    new_lines.extend(lines[end_idx:])

    yaml_path.write_text("\n".join(new_lines) + "\n")


def zip_conf_folder(source_folder, output_zip):
    with zipfile.ZipFile(output_zip, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for root, dirs, files in os.walk(source_folder, topdown=False):
            # 先处理子目录和文件，再处理父目录
            for name in files + dirs:
                path = os.path.join(root, name)
                arcname = os.path.relpath(path, source_folder)
                if os.path.isdir(path):
                    arcname += '/'  # 标记为目录
                zipf.write(path, arcname)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="生成卫星网络 FRR 配置")
    parser.add_argument("m", type=int, help="轨道数 m")
    parser.add_argument("n", type=int, help="每条轨道的卫星数 n")
    args = parser.parse_args()

    m = args.m
    n = args.n

    del_dir()
    write_zebra_conf(m, n)
    write_ospf6_conf(m, n)
    write_bgp_conf(m, n)
    write_daemons_conf(m, n)
    write_config_yaml(m, n)
    zip_conf_folder("conf", "3_prefix_conf.zip")