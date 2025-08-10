"""
简化的模板生成器
生成基础配置文件模板，不依赖复杂的第三方库
"""

from __future__ import annotations

from typing import Dict, List, Optional
from dataclasses import dataclass
from pathlib import Path

from ..core.types import RouterName, RouterID, IPv6Address
from ..core.models import RouterInfo, TopologyConfig
from .renderer import render_template


@dataclass
class TemplateConfig:
    """模板配置"""
    router_name: RouterName
    hostname: str
    router_id: RouterID
    loopback_ipv6: IPv6Address
    disable_logging: bool = False


class BaseTemplateGenerator:
    """基础模板生成器"""
    
    def __init__(self, template_name: str):
        self.template_name = template_name
    
    def generate(self, config: TemplateConfig) -> str:
        """生成模板内容"""
        raise NotImplementedError


class ZebraTemplateGenerator(BaseTemplateGenerator):
    """Zebra配置模板生成器"""
    
    def __init__(self):
        super().__init__("zebra.conf")
    
    def generate(self, config: TemplateConfig) -> str:
        """生成zebra.conf模板（通过Jinja2渲染）"""
        loopback = str(config.loopback_ipv6)
        if "/128" not in loopback:
            loopback = f"{loopback}/128"

        return render_template(
            "zebra.conf.j2",
            {
                # 这里沿用历史行为，使用 TemplateConfig.hostname 作为 FRR 的 hostname
                "router_name": config.hostname,
                "loopback_ipv6": loopback,
                # 模板阶段尚未分配物理接口地址，保持为空列表
                "interfaces": [],
                "disable_logging": config.disable_logging,
            },
        )


class StaticTemplateGenerator(BaseTemplateGenerator):
    """Static路由配置模板生成器"""
    
    def __init__(self):
        super().__init__("staticd.conf")
    
    def generate(self, config: TemplateConfig) -> str:
        """生成staticd.conf模板（通过Jinja2渲染）"""
        return render_template(
            "staticd.conf.j2",
            {
                "router_name": config.hostname,
                "disable_logging": config.disable_logging,
            },
        )


class MgmtTemplateGenerator(BaseTemplateGenerator):
    """管理配置模板生成器"""
    
    def __init__(self):
        super().__init__("mgmtd.conf")
    
    def generate(self, config: TemplateConfig) -> str:
        """生成mgmtd.conf模板（通过Jinja2渲染）"""
        return render_template(
            "mgmtd.conf.j2",
            {
                "router_name": config.hostname,
                "disable_logging": config.disable_logging,
            },
        )


class VtyshTemplateGenerator(BaseTemplateGenerator):
    """Vtysh配置模板生成器"""
    
    def __init__(self):
        super().__init__("vtysh.conf")
    
    def generate(self, config: TemplateConfig) -> str:
        """生成vtysh.conf模板（通过Jinja2渲染）"""
        return render_template(
            "vtysh.conf.j2",
            {
                "router_name": config.hostname,
            },
        )


class TemplateGeneratorFactory:
    """模板生成器工厂"""
    
    _generators: Dict[str, type] = {
        "zebra.conf": ZebraTemplateGenerator,
        "staticd.conf": StaticTemplateGenerator,
        "mgmtd.conf": MgmtTemplateGenerator,
        "vtysh.conf": VtyshTemplateGenerator,
    }
    
    @classmethod
    def register(cls, template_name: str, generator_class: type):
        """注册模板生成器"""
        cls._generators[template_name] = generator_class
    
    @classmethod
    def create(cls, template_name: str) -> BaseTemplateGenerator:
        """创建模板生成器"""
        if template_name not in cls._generators:
            raise ValueError(f"未知的模板类型: {template_name}")
        
        generator_class = cls._generators[template_name]
        return generator_class()
    
    @classmethod
    def get_all_templates(cls) -> List[str]:
        """获取所有支持的模板类型"""
        return list(cls._generators.keys())


def create_template_config(router_info: RouterInfo, topology_config: TopologyConfig = None) -> TemplateConfig:
    """从路由器信息创建模板配置"""
    hostname = f"r{router_info.coordinate.row:02d}_{router_info.coordinate.col:02d}"
    disable_logging = topology_config.disable_logging if topology_config else False

    return TemplateConfig(
        router_name=router_info.name,
        hostname=hostname,
        router_id=router_info.router_id,
        loopback_ipv6=router_info.loopback_ipv6,
        disable_logging=disable_logging
    )


def generate_all_templates(router_info: RouterInfo, topology_config: TopologyConfig = None) -> Dict[str, str]:
    """生成所有模板文件内容"""
    template_config = create_template_config(router_info, topology_config)
    results = {}

    for template_name in TemplateGeneratorFactory.get_all_templates():
        generator = TemplateGeneratorFactory.create(template_name)
        results[template_name] = generator.generate(template_config)

    return results


def generate_template_content(template_name: str, hostname: str) -> str:
    """生成指定模板的内容（兼容旧接口）"""
    # 创建简单的模板配置
    config = TemplateConfig(
        router_name=hostname,
        hostname=hostname,
        router_id=f"10.0.0.1",  # 默认路由器ID
        loopback_ipv6="2001:db8:1000::1"  # 默认loopback地址
    )
    
    generator = TemplateGeneratorFactory.create(template_name)
    return generator.generate(config)
