from __future__ import annotations

from pathlib import Path
from typing import Optional, Set

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from ..core.types import TopologyType


class AppSettings(BaseSettings):
    """全局应用设置（可由环境变量/配置文件覆盖）"""

    model_config = SettingsConfigDict(
        env_prefix="TOPO_",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # 全局
    verbose: bool = Field(default=False, description="详细日志输出")
    dry_run: bool = Field(default=False, description="仅验证不生成")
    output_dir: Optional[Path] = Field(default=None, description="输出目录")

    # 通用拓扑参数
    size: int = Field(default=6, ge=2, le=100, description="网格大小")
    topology: TopologyType = Field(default=TopologyType.TORUS, description="拓扑类型")
    multi_area: bool = Field(default=False)
    area_size: Optional[int] = Field(default=None, ge=2)

    # 协议启用
    enable_bgp: bool = Field(default=False)
    enable_bfd: bool = Field(default=False)
    enable_ospf6: bool = Field(default=True)

    # OSPF 参数
    hello_interval: int = Field(default=2)
    dead_interval: int = Field(default=10)
    spf_delay: int = Field(default=50)
    lsa_min_arrival: int = Field(default=1000)
    maximum_paths: int = Field(default=64)

    # BGP 参数
    bgp_as: int = Field(default=65000)

    # 守护进程控制
    daemons_off: bool = Field(default=False)
    bgpd_off: bool = Field(default=False)
    ospf6d_off: bool = Field(default=False)
    bfdd_off: bool = Field(default=False)
    dummy_gen_protocols: Set[str] = Field(default_factory=set)
    disable_logging: bool = Field(default=False)

    # 配置文件（若 CLI 未提供，可通过环境变量或 .env 中指向）
    config_file: Optional[Path] = Field(default=None, description="配置文件路径，可选")


__all__ = ["AppSettings"]


