#!/usr/bin/env python3
"""
简化版收敛日志转CSV工具（仅标准库）

用法:
  python3 log2csv_functional.py <输入目录或JSON文件> <输出CSV文件>

输出列（满足绘图脚本 experiment_utils/draw/converge_draw_{N}x{N}.py 的要求）:
  - router_name
  - log_file_path
  - total_trigger_events
  - convergence_p50_ms
  - convergence_p75_ms
  - convergence_p95_ms
"""

import csv
import json
import os
import sys
from pathlib import Path
from typing import Dict, List, Tuple

# 确保可以作为脚本运行时也能导入 experiment_utils（需在导入前注入）
THIS_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(THIS_DIR, os.pardir))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from experiment_utils.utils import log_info, log_error, log_success, log_warning, ProgressReporter


def percentiles(values: List[float]) -> Tuple[float, float, float]:
    """返回 P50, P75, P95（基于排序后按索引取值，避免第三方依赖）。"""
    if not values:
        return -1.0, -1.0, -1.0
    data = sorted(values)
    n = len(data)

    def pick(pct: float) -> float:
        if n == 1:
            return float(data[0])
        idx_float = (n - 1) * pct
        idx = int(idx_float) if idx_float.is_integer() else int(idx_float) + 1
        if idx >= n:
            idx = n - 1
        return float(data[idx])

    return pick(0.5), pick(0.75), pick(0.95)


def infer_router_name_from_path(file_path: str) -> str:
    for part in Path(file_path).parts:
        if part.startswith("router_"):
            return part
    return Path(file_path).stem


def parse_json_lines(file_path: str) -> List[Dict]:
    events: List[Dict] = []
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    events.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    except OSError:
        pass
    return events


def gather_router_stats_from_events(events: List[Dict], file_path: str) -> Dict[str, Dict]:
    """将事件按 router_name 聚合，统计分位点和触发事件数量。"""
    by_router: Dict[str, Dict] = {}
    for ev in events:
        router_name = ev.get("router_name") or infer_router_name_from_path(file_path)
        s = by_router.setdefault(router_name, {
            "file_path": file_path,
            "convergence_times": [],
            "trigger_events": 0,
        })
        # 收集会话完成的收敛时间
        if ev.get("event_type") == "session_completed":
            ct = ev.get("convergence_time_ms")
            if isinstance(ct, (int, float)):
                s["convergence_times"].append(float(ct))
        # 统计触发事件: 使用 route/netem 作为近似
        if ev.get("event_type") == "netem_detected":
            s["trigger_events"] += 1
        if ev.get("event_type") == "session_started" and ev.get("trigger_source") == "route":
            s["trigger_events"] += 1
    return by_router


def find_json_files(input_path: str) -> List[str]:
    p = Path(input_path)
    if p.is_file():
        return [str(p)]
    if not p.exists():
        return []
    return [str(fp) for fp in p.rglob("*.json")]


def build_rows(input_path: str) -> List[Dict]:
    rows: List[Dict] = []
    json_files = find_json_files(input_path)
    if not json_files:
        log_warning(f"未在 {input_path} 下找到任何 JSON 文件")
        return rows

    with ProgressReporter() as pr:
        task = pr.create_task(f"处理JSON: {len(json_files)} 个文件", total=len(json_files))
        for json_file in json_files:
            events = parse_json_lines(json_file)
            if not events:
                pr.update_task(task, 1)
                continue
            by_router = gather_router_stats_from_events(events, json_file)
            for router_name, s in by_router.items():
                p50, p75, p95 = percentiles(s["convergence_times"]) if s["convergence_times"] else (-1.0, -1.0, -1.0)
                rows.append({
                    "router_name": router_name,
                    "log_file_path": s["file_path"],
                    "total_trigger_events": s["trigger_events"],
                    "convergence_p50_ms": p50,
                    "convergence_p75_ms": p75,
                    "convergence_p95_ms": p95,
                })
            pr.update_task(task, 1)
    return rows


def write_csv(rows: List[Dict], output_csv: str) -> None:
    output_path = Path(output_csv)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if not rows:
        # 仍写出表头，避免后续绘图脚本报缺列错误
        fieldnames = [
            "router_name", "log_file_path", "total_trigger_events",
            "convergence_p50_ms", "convergence_p75_ms", "convergence_p95_ms",
        ]
        with open(output_path, "w", newline="", encoding="utf-8") as f:
            csv.DictWriter(f, fieldnames=fieldnames).writeheader()
        log_info(f"写出空表头到 {output_csv}")
        return

    fieldnames = list(rows[0].keys())
    with open(output_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for r in rows:
            w.writerow(r)
    log_success(f"写入 {len(rows)} 行到 {output_csv}")


def main() -> None:
    if len(sys.argv) != 3:
        print("使用方法: python log2csv_functional.py <输入目录或JSON文件> <输出CSV文件>")
        sys.exit(1)
    input_path, output_csv = sys.argv[1], sys.argv[2]
    log_info(f"开始处理: {input_path}")
    rows = build_rows(input_path)
    write_csv(rows, output_csv)
    log_success("完成")


if __name__ == "__main__":
    main()
