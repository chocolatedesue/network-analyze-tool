"""
Refactored satellite FRR config generator.

Design references topo_gen's modular, typed, and CLI-driven approach
while keeping the original write_conf.py behavior compatible:

- Generates per-node FRR configs under `conf/Sat{i}/frr_conf` and logs
- Updates `conf/config.yaml` fixed_nodes: Sat blocks
- Zips the `conf/` folder to `3_prefix_conf.zip` by default

Usage examples:

- uv run online-service/main.py gen-conf 10 10
- uv run online-service/confgen.py 10 10 --zip-name custom.zip
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Tuple
import argparse
import os
import shutil
import zipfile


@dataclass(frozen=True)
class GenParams:
    m: int  # number of orbits
    n: int  # satellites per orbit
    out_dir: Path = Path("conf")
    zip_name: str = "3_prefix_conf.zip"


def _safe_mkdir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def _del_old_sat_dirs(out_dir: Path) -> None:
    """Remove existing Sat* directories under out_dir.

    Keeps non-Sat directories/files untouched.
    """
    if not out_dir.exists():
        return
    for child in out_dir.iterdir():
        if child.is_dir() and child.name.startswith("Sat"):
            try:
                shutil.rmtree(child)
            except Exception as e:
                print(f"删除 {child} 时出错: {e}")


def divide_area(i: int, m: int, n: int) -> Tuple[int, int, int, int, int, int]:
    """Compute area/orbit numbering and border role for satellite index i.

    Returns (area, orbit, number, k, location, border_router)
    - k: number of orbits per area (fixed 3, matching original script)
    - location: orbit % k; 0..k-1 where 0 is left border, k-1 right border
    - border_router: -1 for non-border, 0 for left border, 1 for right border
    """
    k = 3
    area = i // (n * k)
    orbit = i // n
    number = i % n

    location = orbit % k
    border_router = -1
    if location == 0 and number == 5:
        border_router = 0
    elif location == k - 1 and number == 5:
        border_router = 1
    return area, orbit, number, k, location, border_router


def _write_text(file_path: Path, content: str) -> None:
    _safe_mkdir(file_path.parent)
    file_path.write_text(content)


def write_zebra_conf(params: GenParams) -> None:
    """Generate zebra.conf per Sat node under {out}/Sat{i}/frr_conf."""
    for i in range(params.m * params.n):
        area, orbit, number, *_ = divide_area(i, params.m, params.n)
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
        _write_text(params.out_dir / f"Sat{i}/frr_conf/zebra.conf", zebra_conf)


def write_ospf6_conf(params: GenParams) -> None:
    """Generate ospf6d.conf per Sat node with interface set based on border role."""
    for i in range(params.m * params.n):
        area, orbit, number, k, location, _ = divide_area(i, params.m, params.n)

        def base_header() -> str:
            return (
                f"!\n"
                f"frr version 8.4-my-manual-build\n"
                f"frr defaults traditional\n"
                f"hostname Sat{i}\n!\n"
            )

        # Determine active interfaces
        if location == 0:
            active_eths = ["eth0", "eth1", "eth3"]
        elif 1 <= location <= k - 2:
            active_eths = ["eth0", "eth1", "eth2", "eth3"]
        else:  # location == k-1
            active_eths = ["eth0", "eth1", "eth2"]

        intf_blocks = []
        for eth in active_eths:
            intf_blocks.append(
                f"interface {eth}\n"
                f"  ipv6 ospf6 area 0.0.0.0\n"
                f"  ipv6 ospf6 hello-interval 60\n"
                f"  ipv6 ospf6 dead-interval 180\n!\n"
            )

        router_block = (
            f"router ospf6\n"
            f"  ospf6 router-id 10.{area}.{orbit}.{number}\n"
            f"  redistribute connected\n"
            f"  redistribute bgp\n!\n"
        )

        ospf6_conf = base_header() + "".join(intf_blocks) + router_block

        dst_dir = params.out_dir / f"Sat{i}/frr_conf"
        log_dir = params.out_dir / f"Sat{i}/frr_log"
        _safe_mkdir(dst_dir)
        _safe_mkdir(log_dir)
        _write_text(dst_dir / "ospf6d.conf", ospf6_conf)


def _render_daemons_content(enable_bgp: bool) -> str:
    """Render FRR daemons config content (minimal set)."""
    return "\n".join(
        [
            "# This file tells the frr package which daemons to start.",
            "zebra=yes",
            f"bgpd={'yes' if enable_bgp else 'no'}",
            "ospf6d=yes",
            "staticd=no",
            "isisd=no",
            "bfdd=no",
            "mgmtd=no",
            "vtysh_enable=yes",
            ""
        ]
    )


def write_bgp_conf(params: GenParams) -> None:
    """Generate bgpd.conf only for border routers (left/right)."""
    for i in range(params.m * params.n):
        area, orbit, number, k, location, border_router = divide_area(i, params.m, params.n)
        as_number = area + 1
        if border_router == 0:  # left border
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
        elif border_router == 1:  # right border
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
    network fd00::{area}:{orbit}:0/112
    network fd00::{area}:{orbit-1}:0/112
    network fd00::{area}:{orbit-2}:0/112
  exit-address-family
!
"""
        else:
            bgp_conf = ""

        # Write bgpd.conf only when needed; daemons handled separately
        if bgp_conf:
            _write_text(params.out_dir / f"Sat{i}/frr_conf/bgpd.conf", bgp_conf)


def write_daemons_conf(params: GenParams) -> None:
    """Generate daemons file per node (no external template copy)."""
    for i in range(params.m * params.n):
        _, _, _, _, _, border_router = divide_area(i, params.m, params.n)
        enable_bgp = border_router in (0, 1)
        content = _render_daemons_content(enable_bgp)
        _write_text(params.out_dir / f"Sat{i}/frr_conf/daemons", content)


def write_config_yaml(params: GenParams) -> None:
    """Update conf/config.yaml (aligned with docs/config.yaml schema).

    Behavior:
    - If `{out}/config.yaml` does not exist, seed it from
      `online-service/docs/config.yaml` if available; otherwise, create a minimal
      skeleton with `templates` + empty `fixed_nodes` and `links`.
    - Then, regenerate `fixed_nodes` Sat blocks for total m*n while preserving
      any non-Sat entries already present in `fixed_nodes` (e.g., gs/alice).
    - Everything outside `fixed_nodes` remains unchanged.
    """
    yaml_path = params.out_dir / "config.yaml"
    if not yaml_path.exists():
        # Try to seed from docs/config.yaml
        docs_yaml = Path(__file__).parent / "docs" / "config.yaml"
        if docs_yaml.exists():
            _safe_mkdir(yaml_path.parent)
            shutil.copyfile(docs_yaml, yaml_path)
            print(f"已从模板复制: {docs_yaml} -> {yaml_path}")
        else:
            # Create a minimal skeleton
            skeleton = (
                "templates:\n"
                "  sat_tmpl:\n"
                "    node_type: sat\n"
                "    image: library/frrouting/frr:v8.4.0\n"
                "    volumes:\n"
                "    - frr_conf:/etc/frr\n"
                "    - frr_log:/var/log/frr\n"
                "    fixed_vNICs:\n"
                "      eth0: {}\n      eth1: {}\n      eth2: {}\n      eth3: {}\n"
                "fixed_nodes:\n"
                "links:\n  engines:\n  - walker_delta\n  veth_pairs: []\n"
            )
            _safe_mkdir(yaml_path.parent)
            yaml_path.write_text(skeleton)
            print(f"已创建最小模板: {yaml_path}")

    content = yaml_path.read_text()
    lines = content.splitlines()

    try:
        start_idx = next(i for i, line in enumerate(lines) if line.strip() == "fixed_nodes:")
        # Find the next top-level section header (no leading spaces and endswith ':')
        end_idx = None
        for j in range(start_idx + 1, len(lines)):
            lj = lines[j]
            if lj and not lj.startswith(" ") and lj.rstrip().endswith(":"):
                end_idx = j
                break
        if end_idx is None:
            end_idx = len(lines)
    except StopIteration:
        print("未找到 fixed_nodes:，跳过 config.yaml 更新")
        return

    # Preserve non-Sat blocks under fixed_nodes
    preserved_blocks: list[str] = []
    i = start_idx + 1
    while i < end_idx:
        line = lines[i]
        if line.startswith("  ") and not line.startswith("    ") and line.rstrip().endswith(":"):
            key_name = line.strip().rstrip(":")
            j = i + 1
            while (
                j < end_idx
                and not (
                    lines[j].startswith("  ")
                    and not lines[j].startswith("    ")
                    and lines[j].rstrip().endswith(":")
                )
            ):
                j += 1
            block_lines = lines[i:j]
            if not key_name.startswith("Sat"):
                preserved_blocks.extend(block_lines)
            i = j
        else:
            preserved_blocks.append(line)
            i += 1

    # Generate Sat blocks
    total = params.m * params.n
    generated: list[str] = []
    for idx in range(total):
        generated.append(f"  Sat{idx}:")
        generated.append("    template: sat_tmpl")
        generated.append(f"    sat_id: {idx}")

    new_lines: list[str] = []
    new_lines.extend(lines[: start_idx + 1])
    new_lines.extend(generated)
    new_lines.extend(preserved_blocks)
    new_lines.extend(lines[end_idx:])
    yaml_path.write_text("\n".join(new_lines) + "\n")


def zip_conf_folder(source_folder: Path, output_zip: Path) -> None:
    """Zip the entire conf folder, including empty dirs, with stable arcnames."""
    with zipfile.ZipFile(output_zip, "w", zipfile.ZIP_DEFLATED) as zipf:
        for root, dirs, files in os.walk(source_folder, topdown=False):
            for name in files + dirs:
                path = Path(root) / name
                arcname = os.path.relpath(path, source_folder)
                if path.is_dir():
                    arcname += "/"
                zipf.write(path, arcname)


def generate_all(params: GenParams) -> Path:
    """End-to-end generation and zipping; returns zip file path."""
    _safe_mkdir(params.out_dir)
    _del_old_sat_dirs(params.out_dir)
    write_zebra_conf(params)
    write_ospf6_conf(params)
    write_bgp_conf(params)
    write_daemons_conf(params)
    write_config_yaml(params)

    zip_path = Path(params.zip_name)
    zip_conf_folder(params.out_dir, zip_path)
    return zip_path


def _arg_main() -> None:
    parser = argparse.ArgumentParser(description="生成卫星网络 FRR 配置 (refactored)")
    parser.add_argument("m", type=int, help="轨道数 m")
    parser.add_argument("n", type=int, help="每条轨道的卫星数 n")
    parser.add_argument("--out-dir", type=Path, default=Path("conf"), help="输出目录 (默认: conf)")
    parser.add_argument("--zip-name", type=str, default="3_prefix_conf.zip", help="Zip 文件名")
    args = parser.parse_args()

    params = GenParams(m=args.m, n=args.n, out_dir=args.out_dir, zip_name=args.zip_name)
    zip_path = generate_all(params)
    print(f"已生成配置并打包: {zip_path}")


if __name__ == "__main__":
    _arg_main()
