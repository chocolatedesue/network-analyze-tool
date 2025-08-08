"""
简化的文件系统操作模块
使用anyio进行异步文件操作，不依赖复杂的第三方库
"""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple
from pathlib import Path
import anyio
from anyio import Path as AsyncPath
import stat

from .core.types import RouterName, Success, Failure, Result, TopologyType
from .core.models import TopologyConfig, RouterInfo, SystemRequirements
from .generators.config import ConfigGeneratorFactory
from .generators.templates import TemplateGeneratorFactory, generate_all_templates


def get_topology_type_str(topology_type) -> str:
    """获取拓扑类型字符串"""
    if hasattr(topology_type, 'value'):
        return topology_type.value
    return str(topology_type)


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
        log_files = ["zebra.log", "ospf6d.log", "bgpd.log", "bfdd.log", "staticd.log", "route.json"]
        for log_file in log_files:
            log_file_path = log_path / log_file
            await log_file_path.touch()
            # 设置权限为777
            import os
            await anyio.to_thread.run_sync(
                os.chmod, str(log_file_path), stat.S_IRWXU | stat.S_IRWXG | stat.S_IRWXO
            )
    
    async def write_template_files(self, routers: List[RouterInfo]) -> Result:
        """写入模板文件"""
        try:
            for router in routers:
                await self._write_router_templates(router)
            
            return Success(f"成功写入 {len(routers)} 个路由器的模板文件")
            
        except Exception as e:
            return Failure(f"模板文件写入失败: {str(e)}")
    
    async def _write_router_templates(self, router: RouterInfo):
        """为单个路由器写入模板文件"""
        templates = generate_all_templates(router)
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
            config_types = ["daemons", "zebra.conf", "ospf6d.conf"]
            
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
        
        for config_type in config_types:
            generator = ConfigGeneratorFactory.create(config_type)
            content = generator.generate(router, config)
            
            if content:  # 只写入非空内容
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
            yaml_filename = f"ospfv3_{topo_type}{config.size}x{config.size}.clab.yaml"
            
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
                "image": "docker.cnb.cool/jmncnic/frrbgpls/origin:latest",
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

        # 生成完整配置
        clab_config = {
            "name": f"ospfv3-{topo_suffix}{config.size}x{config.size}",
            "mgmt": {
                "network": f"ospfv3_{topo_suffix}_mgmt_{config.size}x{config.size}",
                **mgmt_config
            },
            "topology": {
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
    base_dir = Path(f"ospfv3_{get_topology_type_str(config.topology_type)}{config.size}x{config.size}")
    
    fs_manager = FileSystemManager(base_dir)
    return await fs_manager.create_directory_structure(routers)


async def create_all_template_files(
    routers: List[RouterInfo],
    requirements: SystemRequirements,
    base_dir: Path
) -> Result:
    """创建所有模板文件"""
    fs_manager = FileSystemManager(base_dir)
    return await fs_manager.write_template_files(routers)


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
