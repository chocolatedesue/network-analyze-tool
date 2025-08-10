#!/usr/bin/env python3
"""
简化版 Torus 延迟配置脚本
为Torus拓扑设置网卡延迟以实现期望的链路延迟：
- 竖直环: 10ms网卡延迟 -> 20ms链路延迟
- 水平环: 20ms网卡延迟 -> 40ms链路延迟

说明: 链路延迟 = 两端网卡延迟之和
"""

import argparse
import subprocess
import sys
from typing import List, Optional, Tuple

import anyio

try:
    from rich.progress import Progress, BarColumn, TextColumn, TimeElapsedColumn
    HAS_RICH = True
except ImportError:  # pragma: no cover - 可选依赖
    HAS_RICH = False

def execute_command(cmd: str) -> Tuple[bool, Optional[str]]:
    """同步执行单个命令（保留给直接调用的场景）。"""
    try:
        subprocess.run(cmd, shell=True, check=True, capture_output=True)
        return True, None
    except subprocess.CalledProcessError:
        return False, f"命令失败: {cmd}"
    except Exception as e:  # noqa: BLE001 - 向上返回字符串即可
        return False, f"未知错误: {str(e)}"


async def execute_command_async(cmd: str) -> Tuple[bool, Optional[str]]:
    """异步执行单个 shell 命令，返回 (成功与否, 错误信息)。"""
    try:
        # 使用 /bin/sh 保持与 subprocess.run(shell=True) 一致的语义
        completed = await anyio.run_process(
            ["/bin/sh", "-lc", cmd],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        if completed.returncode == 0:
            return True, None
        return False, f"命令失败: {cmd}"
    except Exception as e:  # noqa: BLE001
        return False, f"未知错误: {str(e)}"


async def run_commands_anyio(commands: List[str], max_concurrency: int, verbose: bool) -> List[Tuple[bool, Optional[str]]]:
    """使用 anyio 并发执行命令，限制最大并发度。"""
    semaphore = anyio.Semaphore(max_concurrency)
    results: List[Tuple[bool, Optional[str]]] = [(False, None)] * len(commands)

    progress: Optional[Progress] = None
    task_id: Optional[int] = None

    async def worker(idx: int, cmd: str) -> None:
        async with semaphore:
            success, err = await execute_command_async(cmd)
            results[idx] = (success, err)
            if progress is not None and task_id is not None:
                progress.advance(task_id, 1)

    if HAS_RICH and not verbose:
        with Progress(
            TextColumn("[bold blue]执行进度"),
            BarColumn(),
            TextColumn("{task.completed}/{task.total}"),
            TimeElapsedColumn(),
        ) as progress_ctx:
            progress = progress_ctx
            task_id = progress.add_task("exec", total=len(commands))
            async with anyio.create_task_group() as tg:
                for i, cmd in enumerate(commands):
                    tg.start_soon(worker, i, cmd)
    else:
        async with anyio.create_task_group() as tg:
            for i, cmd in enumerate(commands):
                tg.start_soon(worker, i, cmd)

    return results

def build_containerlab_command(base_cmd: str, runtime: Optional[str] = None) -> str:
    """构建 containerlab 命令，按需注入 --runtime 以兼容 podman/docker。

    规则: 当 runtime 提供时，将其紧随 `containerlab` 之后插入。
    """
    if not runtime:
        return base_cmd
    parts = base_cmd.split(' ', 1)
    if len(parts) == 2 and parts[0] == 'containerlab':
        return f"containerlab --runtime {runtime} {parts[1]}"
    return f"{base_cmd} --runtime {runtime}"


def set_torus_delays(prefix: str, size: int, vertical_delay: int = 10, horizontal_delay: int = 20, execute: bool = False, max_workers: int = 4, verbose: bool = False, runtime: Optional[str] = None) -> list:
    """
    为Torus拓扑设置延迟
    
    Args:
        prefix: 节点前缀 (如: clab-ospfv3-torus9x9)
        size: 网格大小
        vertical_delay: 竖直环网卡延迟 (ms)
        horizontal_delay: 水平环网卡延迟 (ms)
        execute: 是否执行命令
        max_workers: 并发工作线程数
        verbose: 是否显示详细的并行处理信息
        runtime: 容器运行时 (docker/podman)
    """
    
    commands: List[str] = []
    
    print(f"=== 生成 {size}x{size} 延迟配置 ===")
    print(f"竖直环: {vertical_delay}ms网卡延迟 -> {vertical_delay*2}ms链路延迟 (eth1/eth2)")
    print(f"水平环: {horizontal_delay}ms网卡延迟 -> {horizontal_delay*2}ms链路延迟 (eth3/eth4)")
    if runtime:
        print(f"容器运行时: {runtime}")
    print()
    
    # 遍历所有节点
    for row in range(size):
        for col in range(size):
            node_name = f"{prefix}-router_{row:02d}_{col:02d}"
            
            # 竖直接口 - eth1 (north), eth2 (south)
            for eth in ['eth1', 'eth2']:
                base_cmd = f"containerlab tools netem set -n {node_name} -i {eth} --delay {vertical_delay}ms"
                cmd = build_containerlab_command(base_cmd, runtime)
                commands.append(cmd)
                if not execute:
                    print(f"{cmd}  # 竖直环网卡延迟")
            
            # 水平接口 - eth3 (west), eth4 (east)  
            for eth in ['eth3', 'eth4']:
                base_cmd = f"containerlab tools netem set -n {node_name} -i {eth} --delay {horizontal_delay}ms"
                cmd = build_containerlab_command(base_cmd, runtime)
                commands.append(cmd)
                if not execute:
                    print(f"{cmd}  # 水平环网卡延迟")
    
    print(f"\n总计 {len(commands)} 条命令")
    print(f"实现链路延迟: 竖直环{vertical_delay*2}ms, 水平环{horizontal_delay*2}ms")
    
    if execute:
        print(f"使用 {max_workers} 个并发任务执行命令...")

        try:
            results = anyio.run(run_commands_anyio, commands, max_workers, verbose)
        except Exception as e:  # noqa: BLE001
            print(f"并行处理出错: {e}")
            return commands

        # 统计结果
        success_count = sum(1 for success, _ in results if success)
        failed_commands = [cmd for (success, _), cmd in zip(results, commands) if not success]

        print(f"完成: {success_count}/{len(commands)} 成功")
        if failed_commands:
            print("失败的命令:")
            for cmd in failed_commands[:5]:  # 只显示前5个
                print(f"  - {cmd}")
            if len(failed_commands) > 5:
                print(f"  ... 还有 {len(failed_commands) - 5} 个失败")
    
    return commands

def main():
    parser = argparse.ArgumentParser(
        description="Torus拓扑延迟配置 (网卡延迟 -> 链路延迟)",
        epilog="""
注意: 链路延迟 = 两端网卡延迟之和
例如: 20ms网卡延迟 -> 40ms链路延迟
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
    parser.add_argument("--verbose", action="store_true",
                       help="显示详细的并行处理信息")
    
    args = parser.parse_args()
    
    if args.size <= 0:
        print("错误: 网格大小必须 > 0")
        sys.exit(1)
    
    if args.workers <= 0:
        print("错误: 工作线程数必须 > 0")
        sys.exit(1)
    
    commands = set_torus_delays(
        args.prefix, 
        args.size, 
        args.vertical, 
        args.horizontal, 
        args.execute,
        args.workers,
        args.verbose,
        args.runtime
    )
    
    if not args.execute:
        print("\n使用 --execute 参数来实际执行命令")

if __name__ == "__main__":
    main()
