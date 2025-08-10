"""
简化的文件系统操作模块
使用anyio进行异步文件操作，不依赖复杂的第三方库
"""

from __future__ import annotations

from typing import Dict, List, Tuple
from pathlib import Path
import anyio
from anyio import Path as AsyncPath
import stat
import os

from .core.types import RouterName, Success, Failure, Result
from .core.models import TopologyConfig, RouterInfo, SystemRequirements
from .generators.config import ConfigGeneratorFactory
from .generators.templates import generate_all_templates
from .utils.topo import get_topology_type_str

def get_protocol_suffix(config: TopologyConfig) -> str:
    """获取协议后缀标识"""
    protocols = []
    
    # 检查启用的路由协议
    if config.ospf_config is not None:
        protocols.append("ospf6")
    if config.enable_isis:
        protocols.append("isis")
    
    # 如果没有启用任何路由协议，默认返回ospf6（向后兼容）
    if not protocols:
        protocols.append("ospf6")
    
    return "_".join(protocols)


class FileSystemManager:
    """文件系统管理器"""
    
    def __init__(self, base_dir: Path):
        self.base_dir = Path(base_dir)
    
    async def create_directory_structure(self, routers: List[RouterInfo]) -> Result:
        """创建目录结构"""
        try:
            # 创建基础目录
            await self._create_base_directories()
            
            # 为每个路由器创建目录
            for router in routers:
                await self._create_router_directories(router)
            
            return Success(f"成功创建 {len(routers)} 个路由器目录")
            
        except Exception as e:
            return Failure(f"目录创建失败: {str(e)}")
    
    async def _create_base_directories(self):
        """创建基础目录"""
        base_path = AsyncPath(self.base_dir)
        await base_path.mkdir(parents=True, exist_ok=True)
        
        etc_path = base_path / "etc"
        await etc_path.mkdir(exist_ok=True)
        
        configs_path = base_path / "configs"
        await configs_path.mkdir(exist_ok=True)
    
    async def _create_router_directories(self, router: RouterInfo):
        """为单个路由器创建目录"""
        router_path = AsyncPath(self.base_dir) / "etc" / router.name
        await router_path.mkdir(parents=True, exist_ok=True)
        
        # 创建配置目录
        conf_path = router_path / "conf"
        await conf_path.mkdir(exist_ok=True)
        
        # 创建日志目录
        log_path = router_path / "log"
        await log_path.mkdir(exist_ok=True)
        
        # 创建日志文件
        log_files = ["zebra.log", "ospf6d.log", "bgpd.log", "bfdd.log", "staticd.log", "route.json", "isisd.log"]
        for log_file in log_files:
            log_file_path = log_path / log_file
            await log_file_path.touch()
            # 设置权限为777
            import os
            await anyio.to_thread.run_sync(
                os.chmod, str(log_file_path), stat.S_IRWXU | stat.S_IRWXG | stat.S_IRWXO
            )
    
    async def write_template_files(self, routers: List[RouterInfo], config: TopologyConfig = None) -> Result:
        """写入模板文件"""
        try:
            for router in routers:
                await self._write_router_templates(router, config)

            return Success(f"成功写入 {len(routers)} 个路由器的模板文件")

        except Exception as e:
            return Failure(f"模板文件写入失败: {str(e)}")

    async def _write_router_templates(self, router: RouterInfo, config: TopologyConfig = None):
        """为单个路由器写入模板文件"""
        templates = generate_all_templates(router, config)
        conf_path = AsyncPath(self.base_dir) / "etc" / router.name / "conf"

        for template_name, content in templates.items():
            file_path = conf_path / template_name
            async with await file_path.open('w') as f:
                await f.write(content)
    
    async def write_config_files(
        self, 
        routers: List[RouterInfo], 
        config: TopologyConfig,
        interface_mappings: Dict[RouterName, Dict[str, str]]
    ) -> Result:
        """写入配置文件"""
        try:
            config_types = ["daemons", "zebra.conf"]

            if config.ospf_config is not None:
                config_types.append("ospf6d.conf")

            if config.enable_isis:
                config_types.append("isisd.conf")

            if config.enable_bgp:
                config_types.append("bgpd.conf")

            if config.enable_bfd:
                config_types.append("bfdd.conf")
            
            for router in routers:
                await self._write_router_configs(router, config, config_types, interface_mappings)
            
            return Success(f"成功写入 {len(routers)} 个路由器的配置文件")
            
        except Exception as e:
            return Failure(f"配置文件写入失败: {str(e)}")
    
    async def _write_router_configs(
        self, 
        router: RouterInfo, 
        config: TopologyConfig,
        config_types: List[str],
        interface_mappings: Dict[RouterName, Dict[str, str]]
    ):
        """为单个路由器写入配置文件"""
        conf_path = AsyncPath(self.base_dir) / "etc" / router.name / "conf"
        
        # 更新路由器接口信息
        if router.name in interface_mappings:
            router.interfaces.update(interface_mappings[router.name])
        
        # 在写入前，清理与当前启用协议不一致的旧配置文件
        # 仅处理我们生成的协议配置文件，避免误删其他文件
        stale_candidates = {"ospf6d.conf", "isisd.conf", "bgpd.conf", "bfdd.conf"}
        allowed_now = set(config_types)
        for fname in stale_candidates:
            if fname not in allowed_now:
                file_path = conf_path / fname
                try:
                    if await file_path.exists():
                        await file_path.unlink()
                except Exception:
                    # 清理失败不影响后续写入
                    pass

        for config_type in config_types:
            generator = ConfigGeneratorFactory.create(config_type)
            content = generator.generate(router, config)

            # 处理 dummy 生成：如果配置的协议在 dummy 集合中，则将真实内容写到 -bak.conf，并生成空主配置
            protocol_name = config_type  # e.g., "ospf6d.conf"
            is_dummy = False
            if hasattr(config, 'dummy_gen_protocols') and isinstance(config.dummy_gen_protocols, set):
                # 支持传入如 'ospf6d', 'bgpd', 'bfdd'
                base = protocol_name.split('.')[0]
                if base in config.dummy_gen_protocols:
                    is_dummy = True

            if content:
                if is_dummy:
                    # 写入备份配置
                    bak_path = conf_path / f"{protocol_name.replace('.conf', '')}-bak.conf"
                    async with await bak_path.open('w') as f:
                        await f.write(content)
                    # 写入空主配置
                    file_path = conf_path / protocol_name
                    async with await file_path.open('w') as f:
                        await f.write("")
                else:
                    file_path = conf_path / config_type
                    async with await file_path.open('w') as f:
                        await f.write(content)
    
    async def write_containerlab_yaml(
        self, 
        config: TopologyConfig,
        routers: List[RouterInfo],
        links: List[Tuple[str, str, str, str]]  # (router1, intf1, router2, intf2)
    ) -> Result:
        """写入ContainerLab YAML配置"""
        try:
            yaml_content = self._generate_containerlab_yaml(config, routers, links)
            
            # 确定文件名
            topo_type = get_topology_type_str(config.topology_type)
            protocol_suffix = get_protocol_suffix(config)
            yaml_filename = f"{protocol_suffix}_{topo_type}{config.size}x{config.size}.clab.yaml"
            
            yaml_path = AsyncPath(self.base_dir) / yaml_filename
            async with await yaml_path.open('w') as f:
                await f.write(yaml_content)
            
            return Success(f"成功生成ContainerLab配置: {yaml_filename}")
            
        except Exception as e:
            return Failure(f"ContainerLab YAML生成失败: {str(e)}")
    
    def _generate_containerlab_yaml(
        self,
        config: TopologyConfig,
        routers: List[RouterInfo],
        links: List[Tuple[str, str, str, str]]
    ) -> str:
        """生成ContainerLab YAML内容"""
        import yaml

        # 确定拓扑类型名称
        topo_type_str = get_topology_type_str(config.topology_type)
        if topo_type_str == "special" and config.special_config:
            base_name = get_topology_type_str(config.special_config.base_topology)
            if config.special_config.include_base_connections:
                topo_suffix = f"{base_name}_special"
            else:
                topo_suffix = "pure_special"
        else:
            topo_suffix = topo_type_str

        # 生成节点配置
        nodes = {}
        for router in routers:
            nodes[router.name] = {
                "kind": "linux",
                # "image": "docker.cnb.cool/jmncnic/frrbgpls/origin:latest",
                # "image": "quay.io/frrouting/frr:10.3.1",
                "image" : "registry.cn-hangzhou.aliyuncs.com/ccdswork/frr-mod:latest-linux-amd64",
                "binds": [
                    f"etc/{router.name}/conf:/etc/frr",
                    f"etc/{router.name}/log:/var/log/frr",
                ]
            }

        # 生成链路配置
        clab_links = []
        for router1, intf1, router2, intf2 in links:
            clab_links.append({
                "endpoints": [f"{router1}:{intf1}", f"{router2}:{intf2}"]
            })

        # 生成管理网络配置
        mgmt_config = self._generate_mgmt_network(config.total_routers)

        # 计算 CPU 亲和性范围：0 ~ (cpus - 2)
        try:
            total_cpus = os.cpu_count() or 1
        except Exception:
            total_cpus = 1      
        cpu_set_range = f"0-{max(0, total_cpus - 2)}"

        # 生成完整配置
        protocol_suffix = get_protocol_suffix(config)
        clab_config = {
            "name": f"{protocol_suffix.replace('_', '-')}-{topo_suffix}{config.size}x{config.size}",
            "mgmt": {
                "network": f"{protocol_suffix}_{topo_suffix}_mgmt_{config.size}x{config.size}",
                **mgmt_config
            },
            "topology": {
                "defaults": {
                    # 限制所有容器 CPU 亲和性到 0~cpus-1，单容器上限 1.0 vCPU，内存上限 512MB
                    "cpu-set": cpu_set_range,
                    # "cpu": 1.0,
                    "memory": "512MB",
                },
                "nodes": nodes,
                "links": clab_links
            }
        }

        return yaml.dump(clab_config, default_flow_style=False, indent=2)

    def _generate_mgmt_network(self, total_routers: int) -> Dict[str, str]:
        """生成管理网络配置"""
        if total_routers <= 254:
            return {
                "ipv4-subnet": "192.168.200.0/24",
                "ipv6-subnet": "2001:db8:3000:0::/64"
            }
        elif total_routers <= 65534:
            return {
                "ipv4-subnet": "10.100.0.0/16",
                "ipv6-subnet": "2001:db8:3000::/56"
            }
        else:
            return {
                "ipv4-subnet": "10.100.0.0/12",
                "ipv6-subnet": "2001:db8:3000::/48"
            }


# 便利函数
async def create_all_directories(
    config: TopologyConfig,
    routers: List[RouterInfo],
    requirements: SystemRequirements
) -> Result:
    """创建所有目录"""
    if getattr(config, "output_dir", None):
        base_dir = Path(str(config.output_dir))
    else:
        protocol_suffix = get_protocol_suffix(config)
        base_dir = Path(f"{protocol_suffix}_{get_topology_type_str(config.topology_type)}{config.size}x{config.size}")

    fs_manager = FileSystemManager(base_dir)
    return await fs_manager.create_directory_structure(routers)


async def create_all_template_files(
    routers: List[RouterInfo],
    requirements: SystemRequirements,
    base_dir: Path,
    config: TopologyConfig = None
) -> Result:
    """创建所有模板文件"""
    fs_manager = FileSystemManager(base_dir)
    return await fs_manager.write_template_files(routers, config)


async def generate_all_config_files(
    config: TopologyConfig,
    routers: List[RouterInfo],
    interface_mappings: Dict[RouterName, Dict[str, str]],
    requirements: SystemRequirements,
    base_dir: Path
) -> Result:
    """生成所有配置文件"""
    fs_manager = FileSystemManager(base_dir)
    return await fs_manager.write_config_files(routers, config, interface_mappings)


async def generate_clab_yaml(
    config: TopologyConfig,
    routers: List[RouterInfo],
    links: List[Tuple[str, str, str, str]],
    base_dir: Path
) -> Result:
    """生成ContainerLab YAML"""
    fs_manager = FileSystemManager(base_dir)
    return await fs_manager.write_containerlab_yaml(config, routers, links)
