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


@dataclass
class TemplateConfig:
    """模板配置"""
    router_name: RouterName
    hostname: str
    router_id: RouterID
    loopback_ipv6: IPv6Address


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
        """生成zebra.conf模板 - 按建议文档优化"""
        return f"""!
! Zebra configuration for {config.hostname}
!
frr version 7.5.1_git
frr defaults traditional
!
hostname {config.hostname}
password zebra
enable password zebra
!
! Loopback Interface (基础网络配置)
interface lo
 description "Loopback interface for router ID"
 ipv6 address {config.loopback_ipv6}/128
!
! Physical Interfaces (基础网络配置)
! 在实际部署中，这里会有具体的物理接口配置
!
! IP Forwarding (基础网络配置)
ip forwarding
ipv6 forwarding
!
! Logging (在基础网络配置后)
log file /var/log/frr/zebra.log debugging
log commands
!
line vty
!
"""


class StaticTemplateGenerator(BaseTemplateGenerator):
    """Static路由配置模板生成器"""
    
    def __init__(self):
        super().__init__("staticd.conf")
    
    def generate(self, config: TemplateConfig) -> str:
        """生成staticd.conf模板"""
        return f"""!
! Static routing configuration for {config.hostname}
!
frr version 7.5.1_git
frr defaults traditional
!
hostname {config.hostname}
!
log file /var/log/frr/staticd.log debugging
log commands
!
line vty
!
"""


class MgmtTemplateGenerator(BaseTemplateGenerator):
    """管理配置模板生成器"""
    
    def __init__(self):
        super().__init__("mgmtd.conf")
    
    def generate(self, config: TemplateConfig) -> str:
        """生成mgmtd.conf模板"""
        return f"""!
! Management daemon configuration for {config.hostname}
!
frr version 7.5.1_git
frr defaults traditional
!
hostname {config.hostname}
!
log file /var/log/frr/mgmtd.log debugging
log commands
!
line vty
!
"""


class VtyshTemplateGenerator(BaseTemplateGenerator):
    """Vtysh配置模板生成器"""
    
    def __init__(self):
        super().__init__("vtysh.conf")
    
    def generate(self, config: TemplateConfig) -> str:
        """生成vtysh.conf模板"""
        return f"""!
! Vtysh configuration for {config.hostname}
!
no service integrated-vtysh-config
!
username root nopassword
!
"""


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


def create_template_config(router_info: RouterInfo) -> TemplateConfig:
    """从路由器信息创建模板配置"""
    hostname = f"r{router_info.coordinate.row:02d}_{router_info.coordinate.col:02d}"
    
    return TemplateConfig(
        router_name=router_info.name,
        hostname=hostname,
        router_id=router_info.router_id,
        loopback_ipv6=router_info.loopback_ipv6
    )


def generate_all_templates(router_info: RouterInfo) -> Dict[str, str]:
    """生成所有模板文件内容"""
    template_config = create_template_config(router_info)
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
