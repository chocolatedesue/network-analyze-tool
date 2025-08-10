"""
生成器模块初始化
导出配置生成器和引擎
"""

from .config import (
    ConfigGenerator,
    DaemonsConfigGenerator, ZebraConfigGenerator, OSPF6ConfigGenerator, BGPConfigGenerator, BFDConfigGenerator,
    ConfigGeneratorFactory, create_config_pipeline
)


from .templates import (
    TemplateGeneratorFactory, BaseTemplateGenerator,
    ZebraTemplateGenerator, StaticTemplateGenerator, MgmtTemplateGenerator,
    generate_all_templates, generate_template_content
)

__all__ = [
    # 配置生成器
    'ConfigGenerator',
    'DaemonsConfigGenerator', 'ZebraConfigGenerator', 'OSPF6ConfigGenerator', 'BGPConfigGenerator', 'BFDConfigGenerator',
    'ConfigGeneratorFactory', 'create_config_pipeline',

    # 模板生成器
    'TemplateGeneratorFactory', 'BaseTemplateGenerator',
    'ZebraTemplateGenerator', 'StaticTemplateGenerator', 'MgmtTemplateGenerator',
    'generate_all_templates', 'generate_template_content'
]
