#!/usr/bin/env python3
"""
网络故障注入工具 - 使用 anyio 优化版本
模拟网络故障，通过操作容器网络接口或使用netem

特性:
- 使用 anyio 统一异步处理
- 简化的函数式编程风格
- 类型安全的拓扑处理
- 改进的错误处理和结果报告
- 去除复杂状态管理
- 可组合的故障注入策略

使用方法:
    uv run experiment_utils/inject.py clab-ospfv3-torus5x5 --max-executions 3 -t netem
    uv run experiment_utils/inject.py clab-ospfv3-grid5x5 --failure-ratio 0.2 -t link
    uv run experiment_utils/inject.py clab-ospfv3-torus5x5 --specific-link 0,0-0,1 --execute
"""

from __future__ import annotations

import random
import re
import subprocess
import time
from dataclasses import dataclass
from enum import Enum
from typing import List, Tuple, Optional, Set, Iterator

# 核心依赖
import anyio
import typer
from rich.table import Table
from rich.console import Console

# 复用公共工具（支持脚本直接运行与包运行）
try:
    from experiment_utils.utils import (
        Result,
        ExecutionConfig,
        log_info,
        log_error,
        log_success,
        log_warning,
        run_shell_with_retry,
        ProgressReporter,
        create_container_name,
    )
except ModuleNotFoundError:
    import sys as _sys
    from pathlib import Path as _Path
    _sys.path.insert(0, str(_Path(__file__).resolve().parent.parent))
    from experiment_utils.utils import (
        Result,
        ExecutionConfig,
        log_info,
        log_error,
        log_success,
        log_warning,
        run_shell_with_retry,
        ProgressReporter,
        create_container_name,
    )

console = Console()

# ============================================================================
# 工具类型和函数
# ============================================================================

# ============================================================================
# 核心数据类型
# ============================================================================

class InjectionType(Enum):
    """故障注入类型"""
    LINK = "link"
    NETEM = "netem"

class LinkAction(Enum):
    """链路操作类型"""
    UP = "up"
    DOWN = "down"

class Direction(Enum):
    """方向枚举"""
    NORTH = (-1, 0)
    SOUTH = (1, 0)
    WEST = (0, -1)
    EAST = (0, 1)

@dataclass(frozen=True)
class Coordinate:
    """坐标点"""
    x: int
    y: int
    
    def __iter__(self):
        return iter((self.x, self.y))

@dataclass(frozen=True)
class Link:
    """网络链路"""
    node1: Coordinate
    node2: Coordinate
    
    def __post_init__(self):
        # 确保链路的节点顺序一致（用于去重）
        if (self.node1.x, self.node1.y) > (self.node2.x, self.node2.y):
            object.__setattr__(self, 'node1', self.node2)
            object.__setattr__(self, 'node2', self.node1)

@dataclass(frozen=True)
class TopologyConfig:
    """拓扑配置"""
    width: int
    height: int
    topology_type: str  # "grid" or "torus"
    
    def __post_init__(self):
        if self.width <= 0 or self.height <= 0:
            raise ValueError("拓扑尺寸必须大于0")
        if self.topology_type not in ["grid", "torus"]:
            raise ValueError("拓扑类型必须是'grid'或'torus'")
    
    @property
    def size(self) -> int:
        return self.width * self.height

@dataclass(frozen=True)
class InjectionConfig:
    """故障注入配置"""
    injection_type: InjectionType
    min_interval: float = 13.0
    max_interval: float = 20.0
    max_executions: int = 6
    warmup_delay: float = 10.0
    cooldown_delay: float = 20.0
    failure_ratio: float = 0.1
    consistent_cycles: bool = False
    vertical_delay: int = 10  # 竖直方向网卡延迟(ms)
    horizontal_delay: int = 20  # 水平方向网卡延迟(ms)
    specific_link: Optional[Tuple[Tuple[int, int], Tuple[int, int]]] = None  # 指定单链路故障

    def __post_init__(self):
        if self.min_interval <= 0 or self.max_interval <= 0:
            raise ValueError("时间间隔必须大于0")
        if self.min_interval > self.max_interval:
            raise ValueError("最小间隔不能大于最大间隔")
        if not 0 < self.failure_ratio <= 1:
            raise ValueError("故障比例必须在(0, 1]范围内")
        if self.max_executions <= 0:
            raise ValueError("最大执行次数必须大于0")
        if self.vertical_delay < 0 or self.horizontal_delay < 0:
            raise ValueError("延迟值不能为负数")

@dataclass(frozen=True)
class InjectionCommand:
    """故障注入命令"""
    container_name: str
    interface: str
    command: str
    link: Link
    action: LinkAction

@dataclass(frozen=True)
class InjectionResult:
    """故障注入结果"""
    command: InjectionCommand
    success: bool
    output: str = ""
    error: Optional[str] = None
    duration: float = 0.0

@dataclass(frozen=True)
class CycleResult:
    """注入周期结果"""
    cycle_number: int
    failed_links: Set[Link]
    injection_results: List[InjectionResult]
    recovery_results: List[InjectionResult]
    total_duration: float

# ============================================================================
# 纯函数 - 拓扑处理逻辑
# ============================================================================

def parse_topology_from_prefix(prefix: str) -> Result[TopologyConfig, str]:
    """从容器前缀解析拓扑信息"""
    pattern = r'.*-(grid|torus)(\d+)x(\d+)$'
    match = re.search(pattern, prefix, re.IGNORECASE)
    
    if not match:
        return Result.error(f"无法从前缀 '{prefix}' 解析拓扑信息。期望格式: *-grid5x5 或 *-torus5x5")
    
    topology_type_str, width_str, height_str = match.groups()
    
    try:
        width = int(width_str)
        height = int(height_str)
        topology_type = topology_type_str.lower()
        
        return Result.ok(TopologyConfig(width, height, topology_type))
    except ValueError as e:
        return Result.error(f"解析拓扑参数失败: {str(e)}")

def get_neighbors(coord: Coordinate, topology: TopologyConfig) -> List[Coordinate]:
    """获取节点的邻居节点"""
    neighbors = []
    
    if topology.topology_type == "grid":
        # Grid拓扑 - 只有边界内的相邻节点
        directions = [Direction.NORTH, Direction.SOUTH, Direction.WEST, Direction.EAST]
        for direction in directions:
            dx, dy = direction.value
            nx, ny = coord.x + dx, coord.y + dy
            if 0 <= nx < topology.width and 0 <= ny < topology.height:
                neighbors.append(Coordinate(nx, ny))
    
    elif topology.topology_type == "torus":
        # Torus拓扑 - 边缘环绕
        directions = [Direction.NORTH, Direction.SOUTH, Direction.WEST, Direction.EAST]
        for direction in directions:
            dx, dy = direction.value
            nx = (coord.x + dx) % topology.width
            ny = (coord.y + dy) % topology.height
            neighbors.append(Coordinate(nx, ny))
    
    return neighbors

def generate_all_coordinates(topology: TopologyConfig) -> Iterator[Coordinate]:
    """生成拓扑中的所有坐标"""
    for x in range(topology.width):
        for y in range(topology.height):
            yield Coordinate(x, y)

def generate_all_links(topology: TopologyConfig) -> Set[Link]:
    """生成拓扑中的所有链路"""
    links = set()
    
    for coord in generate_all_coordinates(topology):
        neighbors = get_neighbors(coord, topology)
        for neighbor in neighbors:
            link = Link(coord, neighbor)
            links.add(link)
    
    return links

def select_failed_links(all_links: Set[Link], failure_ratio: float, seed: Optional[int] = None) -> Set[Link]:
    """选择要故障的链路"""
    if seed is not None:
        random.seed(seed)

    num_failed = max(1, int(len(all_links) * failure_ratio))
    return set(random.sample(list(all_links), num_failed))

def parse_specific_link(link_str: str) -> Result[Tuple[Tuple[int, int], Tuple[int, int]], str]:
    """解析指定链路字符串

    格式: "x1,y1-x2,y2" 例如: "0,0-0,1"
    """
    try:
        parts = link_str.split('-')
        if len(parts) != 2:
            return Result.error("链路格式错误，应为 'x1,y1-x2,y2'")

        coord1_parts = parts[0].split(',')
        coord2_parts = parts[1].split(',')

        if len(coord1_parts) != 2 or len(coord2_parts) != 2:
            return Result.error("坐标格式错误，应为 'x,y'")

        x1, y1 = int(coord1_parts[0]), int(coord1_parts[1])
        x2, y2 = int(coord2_parts[0]), int(coord2_parts[1])

        return Result.ok(((x1, y1), (x2, y2)))
    except ValueError:
        return Result.error("坐标必须为整数")

def create_specific_link(coord1: Tuple[int, int], coord2: Tuple[int, int]) -> Link:
    """根据坐标创建链路"""
    return Link(Coordinate(coord1[0], coord1[1]), Coordinate(coord2[0], coord2[1]))

def select_specific_link(all_links: Set[Link], specific_link: Tuple[Tuple[int, int], Tuple[int, int]]) -> Result[Set[Link], str]:
    """选择指定的链路"""
    target_link = create_specific_link(specific_link[0], specific_link[1])

    if target_link in all_links:
        return Result.ok({target_link})
    else:
        return Result.error(f"指定的链路 {specific_link[0]} <-> {specific_link[1]} 在拓扑中不存在")

def calculate_direction(coord1: Coordinate, coord2: Coordinate, topology: TopologyConfig) -> Tuple[int, int]:
    """计算两个坐标之间的方向（考虑torus环绕）"""
    dx = coord2.x - coord1.x
    dy = coord2.y - coord1.y
    
    # 处理torus环绕 - 选择最短路径
    if topology.topology_type == "torus":
        if abs(dx) > topology.width // 2:
            dx = -1 if dx > 0 else 1
        if abs(dy) > topology.height // 2:
            dy = -1 if dy > 0 else 1
    
    return (dx, dy)

def get_interface_and_delay(direction: Tuple[int, int], injection_config: InjectionConfig) -> Tuple[str, str]:
    """根据方向获取接口名称和延迟"""
    # 接口映射: eth1=north, eth2=south, eth3=west, eth4=east
    # 使用配置中的自定义延迟值
    interface_map = {
        (-1, 0): ("eth1", f"{injection_config.vertical_delay * 2}ms"),  # north (链路延迟 = 2 * 网卡延迟)
        (1, 0): ("eth2", f"{injection_config.vertical_delay * 2}ms"),   # south
        (0, -1): ("eth3", f"{injection_config.horizontal_delay * 2}ms"),  # west
        (0, 1): ("eth4", f"{injection_config.horizontal_delay * 2}ms")    # east
    }

    return interface_map.get(direction, ("eth1", f"{injection_config.vertical_delay * 2}ms"))

def create_container_name(prefix: str, coord: Coordinate) -> str:
    """创建容器名称"""
    return f"{prefix}-router_{coord.x:02d}_{coord.y:02d}"

def generate_injection_commands(
    link: Link,
    action: LinkAction,
    injection_type: InjectionType,
    topology: TopologyConfig,
    prefix: str,
    injection_config: InjectionConfig
) -> List[InjectionCommand]:
    """生成故障注入命令"""
    commands = []
    
    # 计算方向
    direction = calculate_direction(link.node1, link.node2, topology)
    reverse_direction = (-direction[0], -direction[1])
    
    # 获取接口和延迟
    interface1, delay1 = get_interface_and_delay(direction, injection_config)
    interface2, delay2 = get_interface_and_delay(reverse_direction, injection_config)
    
    # 创建容器名称
    container1 = create_container_name(prefix, link.node1)
    container2 = create_container_name(prefix, link.node2)
    
    if injection_type == InjectionType.NETEM:
        if action == LinkAction.DOWN:
            # 设置100%丢包模拟链路故障
            cmd1 = f"containerlab tools netem set -n {container1} -i {interface1} --loss 100 --delay {delay1}"
            cmd2 = f"containerlab tools netem set -n {container2} -i {interface2} --loss 100 --delay {delay2}"
        else:  # LinkAction.UP
            # 设置0%丢包恢复链路
            cmd1 = f"containerlab tools netem set -n {container1} -i {interface1} --loss 0 --delay {delay1}"
            cmd2 = f"containerlab tools netem set -n {container2} -i {interface2} --loss 0 --delay {delay2}"
    else:  # InjectionType.LINK
        if action == LinkAction.DOWN:
            cmd1 = f"docker exec {container1} ifconfig {interface1} down"
            cmd2 = f"docker exec {container2} ifconfig {interface2} down"
        else:  # LinkAction.UP
            cmd1 = f"docker exec {container1} ifconfig {interface1} up"
            cmd2 = f"docker exec {container2} ifconfig {interface2} up"
    
    commands.extend([
        InjectionCommand(container1, interface1, cmd1, link, action),
        InjectionCommand(container2, interface2, cmd2, link, action)
    ])
    
    return commands

# ============================================================================
# 命令执行函数 - 使用 anyio 异步处理
# ============================================================================

@dataclass(frozen=True)
class ExecutionConfig:
    """执行配置"""
    max_workers: int = 4
    timeout: int = 30
    verbose: bool = False

async def execute_injection_command(command: InjectionCommand, timeout: int = 30) -> InjectionResult:
    """异步执行故障注入命令"""
    start_time = time.time()
    try:
        rc, out, err = await run_shell_with_retry(command.command, timeout)
        duration = time.time() - start_time
        return InjectionResult(
            command=command,
            success=(rc == 0),
            output=out,
            error=(err if err and rc != 0 else None),
            duration=duration,
        )
    except TimeoutError:
        duration = time.time() - start_time
        return InjectionResult(command=command, success=False, error="命令超时", duration=duration)
    except Exception as e:
        duration = time.time() - start_time
        return InjectionResult(command=command, success=False, error=f"执行错误: {str(e)}", duration=duration)

async def execute_commands_batch(
    commands: List[InjectionCommand],
    exec_config: ExecutionConfig
) -> List[InjectionResult]:
    """异步批量执行故障注入命令"""

    async def execute_with_semaphore(semaphore: anyio.Semaphore, command: InjectionCommand) -> InjectionResult:
        async with semaphore:
            return await execute_injection_command(command, exec_config.timeout)

    # 使用信号量限制并发数
    semaphore = anyio.Semaphore(exec_config.max_workers)

    # 显示进度
    with ProgressReporter() as progress:
        if progress.use_rich:
            task_id = progress.create_task("执行故障注入", len(commands))
        results = []
        async with anyio.create_task_group() as tg:
            async def run_command(cmd):
                result = await execute_with_semaphore(semaphore, cmd)
                results.append(result)
                if progress.use_rich:
                    progress.update_task(task_id, 1)
            for command in commands:
                tg.start_soon(run_command, command)
    return results

# ============================================================================
# 显示和报告函数
# ============================================================================

def print_topology_summary(topology: TopologyConfig, prefix: str):
    """打印拓扑摘要"""
    table = Table(title=f"{topology.topology_type.upper()} 拓扑故障注入配置")
    table.add_column("配置项", style="cyan")
    table.add_column("值", style="green")

    table.add_row("容器前缀", prefix)
    table.add_row("拓扑类型", topology.topology_type.upper())
    table.add_row("拓扑尺寸", f"{topology.width}x{topology.height}")
    table.add_row("节点总数", str(topology.size))

    console.print(table)

def print_injection_summary(
    injection_config: InjectionConfig,
    total_links: int,
    failed_links: Set[Link],
    topology: TopologyConfig,
    prefix: str
):
    """打印注入配置摘要"""
    log_info(f"故障注入类型: {injection_config.injection_type.value}")
    log_info(f"总链路数: {total_links}")
    log_info(f"故障链路数: {len(failed_links)} ({len(failed_links)/total_links*100:.1f}%)")

    if injection_config.specific_link:
        link = list(failed_links)[0]
        log_info(f"指定故障链路: ({link.node1.x},{link.node1.y}) <-> ({link.node2.x},{link.node2.y})")

    log_info(f"执行周期: {injection_config.max_executions}")
    log_info(f"间隔时间: {injection_config.min_interval}-{injection_config.max_interval}秒")
    log_info(f"延迟配置: 竖直方向{injection_config.vertical_delay * 2}ms, 水平方向{injection_config.horizontal_delay * 2}ms (链路延迟)")

    # 显示示例命令
    if failed_links:
        show_example_command(failed_links, injection_config, topology, prefix)

def show_example_command(
    failed_links: Set[Link],
    injection_config: InjectionConfig,
    topology: TopologyConfig,
    prefix: str
):
    """显示将要执行的示例命令"""
    # 取第一个链路作为示例
    example_link = next(iter(failed_links))

    # 生成示例命令
    example_commands = generate_injection_commands(
        example_link, LinkAction.DOWN, injection_config.injection_type,
        topology, prefix, injection_config
    )

    if example_commands:
        log_info("示例命令 (将要执行的命令类型):")
        # 显示第一个命令作为示例
        example_cmd = example_commands[0]
        console.print(f"  [yellow]容器:[/yellow] {example_cmd.container_name}")
        console.print(f"  [yellow]接口:[/yellow] {example_cmd.interface}")
        console.print(f"  [yellow]命令:[/yellow] [cyan]{example_cmd.command}[/cyan]")

        if len(example_commands) > 1:
            log_info(f"  (每个链路将在两个方向执行类似命令)")

def show_cycle_example_command(command: InjectionCommand, cycle_number: int):
    """显示当前周期的示例命令"""
    console.print(f"\n[bold blue]📋 第 {cycle_number} 周期示例命令:[/bold blue]")
    console.print(f"  [yellow]容器:[/yellow] {command.container_name}")
    console.print(f"  [yellow]接口:[/yellow] {command.interface}")
    console.print(f"  [yellow]操作:[/yellow] {'故障注入' if command.action == LinkAction.DOWN else '故障恢复'}")
    console.print(f"  [yellow]命令:[/yellow] [cyan]{command.command}[/cyan]")

def print_cycle_results(results: List[CycleResult]):
    """打印周期执行结果"""
    total_injections = sum(len(r.injection_results) for r in results)
    total_recoveries = sum(len(r.recovery_results) for r in results)
    successful_injections = sum(
        len([ir for ir in r.injection_results if ir.success]) for r in results
    )
    successful_recoveries = sum(
        len([rr for rr in r.recovery_results if rr.success]) for r in results
    )
    
    log_success(f"完成 {len(results)} 个注入周期")
    log_info(f"故障注入: {successful_injections}/{total_injections} 成功")
    log_info(f"故障恢复: {successful_recoveries}/{total_recoveries} 成功")
    
    if results:
        avg_duration = sum(r.total_duration for r in results) / len(results)
        log_info(f"平均周期时间: {avg_duration:.2f}秒")

# ============================================================================
# 主要业务逻辑
# ============================================================================

async def execute_injection_cycle(
    failed_links: Set[Link],
    injection_config: InjectionConfig,
    topology: TopologyConfig,
    prefix: str,
    exec_config: ExecutionConfig,
    cycle_number: int
) -> Result[CycleResult, str]:
    """异步执行单个故障注入周期"""

    cycle_start_time = time.time()

    log_info(f"开始第 {cycle_number} 个注入周期，故障链路: {len(failed_links)} 个")

    # 生成故障注入命令
    injection_commands = []
    for link in failed_links:
        commands = generate_injection_commands(
            link, LinkAction.DOWN, injection_config.injection_type, topology, prefix, injection_config
        )
        injection_commands.extend(commands)

    # 显示本周期的示例命令
    if injection_commands:
        show_cycle_example_command(injection_commands[0], cycle_number)

    # 执行故障注入
    log_info("执行故障注入...")
    injection_results = await execute_commands_batch(injection_commands, exec_config)

    # 检查故障注入是否有失败
    failed_injections = [r for r in injection_results if not r.success]
    if failed_injections:
        error_msg = f"故障注入失败 ({len(failed_injections)}/{len(injection_results)} 个命令失败)"
        log_error(error_msg)
        for result in failed_injections[:3]:  # 只显示前3个错误
            console.print(f"  [red]✗[/red] {result.command.container_name}:{result.command.interface} - {result.error}")
        if len(failed_injections) > 3:
            console.print(f"  [red]... 还有 {len(failed_injections) - 3} 个失败[/red]")
        return Result.error(error_msg)

    # 等待随机时间
    wait_time = random.uniform(injection_config.min_interval, injection_config.max_interval)
    log_info(f"等待 {wait_time:.1f} 秒...")
    await anyio.sleep(wait_time)

    # 生成恢复命令
    recovery_commands = []
    for link in failed_links:
        commands = generate_injection_commands(
            link, LinkAction.UP, injection_config.injection_type, topology, prefix, injection_config
        )
        recovery_commands.extend(commands)

    # 显示恢复阶段的示例命令
    if recovery_commands:
        show_cycle_example_command(recovery_commands[0], cycle_number)

    # 执行故障恢复
    log_info("执行故障恢复...")
    recovery_results = await execute_commands_batch(recovery_commands, exec_config)

    # 检查故障恢复是否有失败
    failed_recoveries = [r for r in recovery_results if not r.success]
    if failed_recoveries:
        error_msg = f"故障恢复失败 ({len(failed_recoveries)}/{len(recovery_results)} 个命令失败)"
        log_error(error_msg)
        for result in failed_recoveries[:3]:  # 只显示前3个错误
            console.print(f"  [red]✗[/red] {result.command.container_name}:{result.command.interface} - {result.error}")
        if len(failed_recoveries) > 3:
            console.print(f"  [red]... 还有 {len(failed_recoveries) - 3} 个失败[/red]")
        return Result.error(error_msg)

    # 冷却时间
    log_info(f"冷却 {injection_config.cooldown_delay} 秒...")
    await anyio.sleep(injection_config.cooldown_delay)

    cycle_duration = time.time() - cycle_start_time

    return Result.ok(CycleResult(
        cycle_number=cycle_number,
        failed_links=failed_links,
        injection_results=injection_results,
        recovery_results=recovery_results,
        total_duration=cycle_duration
    ))

# ============================================================================
# 辅助函数 - 函数式编程风格
# ============================================================================

def setup_topology_and_links(prefix: str, injection_config: InjectionConfig) -> Result[Tuple[TopologyConfig, Set[Link], Set[Link]], str]:
    """设置拓扑和链路选择 - 纯函数式处理"""
    return (parse_topology_from_prefix(prefix)
            .and_then(lambda topology: Result.ok((topology, generate_all_links(topology))))
            .and_then(lambda data: select_failed_links_functional(data[0], data[1], injection_config)
                     .map(lambda failed_links: (data[0], data[1], failed_links))))

def select_failed_links_functional(_topology: TopologyConfig, all_links: Set[Link], injection_config: InjectionConfig) -> Result[Set[Link], str]:
    """函数式链路选择"""
    if injection_config.specific_link:
        return select_specific_link(all_links, injection_config.specific_link)
    else:
        return Result.ok(select_failed_links(all_links, injection_config.failure_ratio))

def show_preview_info(failed_links: Set[Link]) -> None:
    """显示预览信息 - 副作用隔离"""
    log_info("预览模式 - 将要执行的操作:")
    log_info(f"将在 {len(failed_links)} 个链路上执行故障注入")

    preview_links = list(failed_links)[:3]
    for i, link in enumerate(preview_links):
        log_info(f"  链路 {i+1}: ({link.node1.x},{link.node1.y}) <-> ({link.node2.x},{link.node2.y})")

    if len(failed_links) > 3:
        log_info(f"  ... 还有 {len(failed_links) - 3} 个链路")
    log_info("使用 --execute 参数来实际执行故障注入")

async def execute_cycles_functional(
    all_links: Set[Link],
    initial_failed_links: Set[Link],
    injection_config: InjectionConfig,
    topology: TopologyConfig,
    prefix: str,
    exec_config: ExecutionConfig
) -> Result[List[CycleResult], str]:
    """异步函数式执行周期"""

    def generate_cycle_links():
        """生成每个周期的故障链路"""
        yield initial_failed_links
        for _ in range(1, injection_config.max_executions):
            # 如果指定了单点故障或者设置了一致性周期，则使用相同的链路
            if injection_config.specific_link or injection_config.consistent_cycles:
                yield initial_failed_links
            else:
                yield select_failed_links(all_links, injection_config.failure_ratio)

    try:
        # 预热
        log_info(f"开始执行故障注入，预热 {injection_config.warmup_delay} 秒...")
        await anyio.sleep(injection_config.warmup_delay)

        # 执行所有周期并收集结果
        cycle_results = []
        for cycle_num, failed_links in enumerate(generate_cycle_links(), 1):
            result = await execute_injection_cycle(
                failed_links, injection_config, topology, prefix, exec_config, cycle_num
            )
            if result.is_ok():
                cycle_results.append(result.unwrap())
            else:
                # 出现错误时立即退出
                console.print(f"\n[red]💥 第 {cycle_num} 个周期执行失败，停止执行[/red]")
                console.print(f"[red]错误详情: {result._error}[/red]")
                return result  # 直接返回错误结果

        print_cycle_results(cycle_results)
        return Result.ok(cycle_results)

    except KeyboardInterrupt:
        log_warning("用户中断故障注入")
        return Result.ok(cycle_results)
    except Exception as e:
        return Result.error(f"故障注入执行失败: {str(e)}")

async def run_fault_injection_functional(
    prefix: str,
    injection_config: InjectionConfig,
    exec_config: ExecutionConfig,
    execute: bool = False,
    show_preview: bool = True
) -> Result[List[CycleResult], str]:
    """异步简化的函数式故障注入主函数

    使用函数式编程原则：
    - 纯函数组合
    - 不可变数据
    - 副作用隔离
    - 管道式处理
    """

    # 函数式管道：设置 -> 预览/执行 -> 结果
    setup_result = setup_topology_and_links(prefix, injection_config)
    if setup_result.is_error():
        return setup_result

    context = handle_topology_setup(*setup_result.unwrap(), prefix, injection_config)
    return await handle_execution_mode(context, execute, show_preview, exec_config)

def handle_topology_setup(topology: TopologyConfig, all_links: Set[Link], failed_links: Set[Link], prefix: str, injection_config: InjectionConfig) -> dict:
    """处理拓扑设置 - 副作用隔离"""
    print_topology_summary(topology, prefix)
    print_injection_summary(injection_config, len(all_links), failed_links, topology, prefix)

    return {
        'topology': topology,
        'all_links': all_links,
        'failed_links': failed_links,
        'prefix': prefix,
        'injection_config': injection_config
    }

async def handle_execution_mode(context: dict, execute: bool, show_preview: bool, exec_config: ExecutionConfig) -> Result[List[CycleResult], str]:
    """异步处理执行模式 - 条件分支简化"""
    if show_preview and not execute:
        show_preview_info(context['failed_links'])
        return Result.ok([])

    if execute:
        return await execute_cycles_functional(
            context['all_links'],
            context['failed_links'],
            context['injection_config'],
            context['topology'],
            context['prefix'],
            exec_config
        )

    return Result.ok([])

# ============================================================================
# CLI接口
# ============================================================================

def create_typer_app():
    """创建Typer应用"""
    app = typer.Typer(
        name="inject_functional",
        help="函数式版本的网络故障注入工具",
        epilog="模拟网络故障，支持链路故障和netem延迟/丢包"
    )

    @app.command()
    def main(
        prefix: str = typer.Argument(..., help="容器前缀 (如: clab-ospfv3-torus5x5)"),
        injection_type: str = typer.Option("netem", "-t", "--type", help="注入类型 (link/netem)"),
        max_executions: int = typer.Option(6, "--max-executions", help="最大执行周期数"),
        min_interval: float = typer.Option(13.0, "--min-interval", help="最小间隔时间(秒)"),
        max_interval: float = typer.Option(20.0, "--max-interval", help="最大间隔时间(秒)"),
        failure_ratio: float = typer.Option(0.1, "--failure-ratio", help="故障链路比例 (0-1)"),
        warmup_delay: float = typer.Option(10.0, "--warmup-delay", help="预热延迟(秒)"),
        cooldown_delay: float = typer.Option(20.0, "--cooldown-delay", help="冷却延迟(秒)"),
        consistent_cycles: bool = typer.Option(False, "--consistent-cycles", help="保持相同的故障链路"),
        vertical_delay: int = typer.Option(10, "--vertical-delay", help="竖直方向网卡延迟(ms，默认10ms->20ms链路)"),
        horizontal_delay: int = typer.Option(20, "--horizontal-delay", help="水平方向网卡延迟(ms，默认20ms->40ms链路)"),
        specific_link: Optional[str] = typer.Option(None, "--specific-link", help="指定单链路故障 (格式: x1,y1-x2,y2，如: 0,0-0,1)"),
        execute: bool = typer.Option(False, "--execute", help="执行故障注入"),
        workers: int = typer.Option(4, "--workers", help="并发工作线程数"),
        timeout: int = typer.Option(30, "--timeout", help="命令超时时间(秒)"),
        verbose: bool = typer.Option(False, "--verbose", help="显示详细信息")
    ):
        """执行网络故障注入"""
        async def async_main():
            try:
                # 验证注入类型
                try:
                    injection_type_enum = InjectionType(injection_type.lower())
                except ValueError:
                    log_error(f"无效的注入类型: {injection_type}. 可用类型: {', '.join([t.value for t in InjectionType])}")
                    raise typer.Exit(1)

                # 解析指定链路（如果提供）
                parsed_specific_link = None
                if specific_link:
                    link_result = parse_specific_link(specific_link)
                    if link_result.is_error():
                        log_error(f"链路格式错误: {link_result._error}")
                        raise typer.Exit(1)
                    parsed_specific_link = link_result.unwrap()

                # 创建配置对象
                injection_config = InjectionConfig(
                    injection_type=injection_type_enum,
                    min_interval=min_interval,
                    max_interval=max_interval,
                    max_executions=max_executions,
                    warmup_delay=warmup_delay,
                    cooldown_delay=cooldown_delay,
                    failure_ratio=failure_ratio,
                    consistent_cycles=consistent_cycles,
                    vertical_delay=vertical_delay,
                    horizontal_delay=horizontal_delay,
                    specific_link=parsed_specific_link
                )
                exec_config = ExecutionConfig(max_workers=workers, timeout=timeout, verbose=verbose)

                # 执行主要逻辑
                result = await run_fault_injection_functional(
                    prefix, injection_config, exec_config, execute, show_preview=not execute
                )

                if result.is_error():
                    log_error(result._error)
                    raise typer.Exit(1)

                log_success("故障注入完成")

            except Exception as e:
                log_error(f"未知错误: {str(e)}")
                raise typer.Exit(1)

        # 运行异步主函数
        anyio.run(async_main)

    return app

def main():
    """主入口函数"""
    app = create_typer_app()
    app()


if __name__ == "__main__":
    main()
