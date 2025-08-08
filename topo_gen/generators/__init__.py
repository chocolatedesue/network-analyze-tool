"""
生成器模块初始化
导出配置生成器和引擎
"""

from .config import (
    ConfigGenerator, ConfigBuilder, ConfigSection,
    DaemonsConfigGenerator, ZebraConfigGenerator, OSPF6ConfigGenerator,
    ConfigGeneratorFactory, create_config_pipeline
)

from .engine import (
    ModernTopologyGenerator, GenerationContext, generate_topology
)

from .templates import (
    TemplateGeneratorFactory, BaseTemplateGenerator,
    ZebraTemplateGenerator, StaticTemplateGenerator, MgmtTemplateGenerator,
    generate_all_templates, generate_template_content
)

__all__ = [
    # 配置生成器
    'ConfigGenerator', 'ConfigBuilder', 'ConfigSection',
    'DaemonsConfigGenerator', 'ZebraConfigGenerator', 'OSPF6ConfigGenerator',
    'ConfigGeneratorFactory', 'create_config_pipeline',

    # 生成引擎
    'ModernTopologyGenerator', 'GenerationContext', 'generate_topology',

    # 模板生成器
    'TemplateGeneratorFactory', 'BaseTemplateGenerator',
    'ZebraTemplateGenerator', 'StaticTemplateGenerator', 'MgmtTemplateGenerator',
    'generate_all_templates', 'generate_template_content'
]
