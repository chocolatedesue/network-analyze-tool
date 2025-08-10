#!/usr/bin/env python3
"""
优化版 Torus 延迟配置脚本
为Torus拓扑设置网卡延迟以实现期望的链路延迟：
- 竖直环: 10ms网卡延迟 -> 20ms链路延迟
- 水平环: 20ms网卡延迟 -> 40ms链路延迟

说明: 链路延迟 = 两端网卡延迟之和

优化特性:
- 使用 utils.py 的可复用工具
- 改进的错误处理和重试机制
- 更好的类型安全
- 优化的并发处理
"""

import argparse
import sys
from typing import Optional

import anyio

from utils import (
    DelayConfig,
    ExecutionConfig, 
    log_info, 
    log_success, 
    log_error,
    set_torus_delays_async
)


async def main_async(
    prefix: str,
    size: int,
    vertical_delay: int,
    horizontal_delay: int,
    runtime: Optional[str],
    execute: bool,
    max_workers: int,
    timeout: int,
    verbose: bool
) -> None:
    """异步主函数"""
    try:
        # 创建配置
        delay_config = DelayConfig(
            prefix=prefix,
            size=size,
            vertical_delay=vertical_delay,
            horizontal_delay=horizontal_delay,
            runtime=runtime
        )
        
        exec_config = ExecutionConfig(
            max_workers=max_workers,
            timeout=timeout,
            verbose=verbose,
            runtime=runtime or "docker"
        )
        
        # 执行延迟配置
        result = await set_torus_delays_async(delay_config, exec_config, execute)
        
        if result.is_error():
            log_error(f"配置失败: {result.unwrap_error()}")
            sys.exit(1)
        else:
            log_success("配置完成!")
            
    except ValueError as e:
        log_error(f"参数错误: {str(e)}")
        sys.exit(1)
    except Exception as e:
        log_error(f"未预期的错误: {str(e)}")
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(
        description="优化版 Torus拓扑延迟配置 (网卡延迟 -> 链路延迟)",
        epilog="""
注意: 链路延迟 = 两端网卡延迟之和
例如: 20ms网卡延迟 -> 40ms链路延迟

优化特性:
- 带重试的可靠命令执行
- 改进的错误处理和日志
- 优化的并发性能
- 类型安全的配置管理
        """
    )
    parser.add_argument("prefix", help="节点前缀 (如: clab-ospfv3-torus9x9)")
    parser.add_argument("size", type=int, help="网格大小")
    parser.add_argument("--vertical", type=int, default=10, 
                       help="竖直环网卡延迟(ms，默认10ms->20ms链路)")
    parser.add_argument("--horizontal", type=int, default=20, 
                       help="水平环网卡延迟(ms，默认20ms->40ms链路)")
    parser.add_argument("--runtime", choices=["docker", "podman"], default=None,
                       help="容器运行时 (docker/podman)")
    parser.add_argument("--execute", action="store_true", help="执行命令")
    parser.add_argument("--workers", type=int, default=4, 
                       help="并发工作线程数 (默认: 4)")
    parser.add_argument("--timeout", type=int, default=30,
                       help="命令超时时间(秒，默认: 30)")
    parser.add_argument("--verbose", action="store_true",
                       help="显示详细的执行信息")
    
    args = parser.parse_args()
    
    if args.workers <= 0:
        log_error("工作线程数必须 > 0")
        sys.exit(1)
    
    if args.timeout <= 0:
        log_error("超时时间必须 > 0")
        sys.exit(1)
    
    # 运行异步主函数
    anyio.run(
        main_async,
        args.prefix,
        args.size,
        args.vertical,
        args.horizontal,
        args.runtime,
        args.execute,
        args.workers,
        args.timeout,
        args.verbose
    )


if __name__ == "__main__":
    main()
