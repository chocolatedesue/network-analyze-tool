#!/usr/bin/env python3
"""
Entry point for running topo_gen as a module
This allows running: python -m topo_gen
"""

try:
    # 当以模块方式运行: python -m topo_gen
    from .cli import app
except ImportError:
    # 当被直接当作脚本执行时，回退到绝对导入
    from topo_gen.cli import app

if __name__ == "__main__":
    app()
