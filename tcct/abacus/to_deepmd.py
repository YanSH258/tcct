"""Collect completed ABACUS tasks into composition-resolved DeepMD NPY."""

from __future__ import annotations

import json
import platform
from collections import Counter, defaultdict
from pathlib import Path
from typing import Optional

import numpy as np
import typer

from tcct.abacus.audit import (
    discover_tasks,
    inspect_task,
    parse_basis_type,
    parse_calculation,
)
from tcct.common.dpdata_utils import (
    append_system,
    exact_formula,
    finite_labeled,
    normalize,
    parse_type_map,
    require_dpdata,
)
from tcct.common.io import (
    ensure_empty_output,
    write_csv,
    write_json,
    write_sha256_manifest,
)


def _format(task: Path, requested: str) -> str:
    if requested != "auto":
        return requested
    basis_type = parse_basis_type(task)
    calculation = parse_calculation(task)
    if calculation == "scf":
        return f"abacus/{basis_type}/scf"
    if calculation in {"relax", "cell-relax"}:
        return f"abacus/{basis_type}/relax"
    if calculation == "md":
        return f"abacus/{basis_type}/md"
    raise ValueError(f"无法由 INPUT 判断 dpdata 格式: {task}")


def to_deepmd(
    root: Path = typer.Argument(Path("."), help="ABACUS 任务根目录"),
    output: Path = typer.Argument(..., help="输出目录"),
    pattern: str = typer.Option("**/INPUT", help="INPUT 搜索模式"),
    fmt: str = typer.Option(
        "auto",
        "--format",
        help="auto、abacus/{pw,lcao}/{scf,relax,md} 或 abacus/{scf,relax,md}",
    ),
    frames: str = typer.Option("all", help="all 或 final"),
    type_map: Optional[str] = typer.Option(
        None, help="元素顺序，逗号或空格分隔"
    ),
    set_size: int = typer.Option(2000, min=1),
    expected: Optional[int] = typer.Option(None, help="预期任务数"),
    skip_incomplete: bool = typer.Option(
        True,
        "--skip-incomplete/--strict",
        help="默认跳过未完成或解析失败的任务并提取其余；--strict 时任一任务"
        "未完成或解析失败即终止且不创建输出",
    ),
    require_virial: bool = typer.Option(True, "--virial/--no-virial"),
):
    """ABACUS 结果转 DeepMD NPY（默认提取已完成任务，跳过的记入审计 CSV）。"""
    if frames not in {"all", "final"}:
        typer.secho("错误: --frames 必须是 all 或 final", err=True, fg=typer.colors.RED)
        raise typer.Exit(1)
    dpdata = require_dpdata()
    tasks = discover_tasks(root.resolve(), pattern)
    if not tasks:
        typer.secho("错误: 未发现 ABACUS 任务", err=True, fg=typer.colors.RED)
        raise typer.Exit(1)
    if expected is not None and len(tasks) != expected:
        typer.secho(
            f"错误: 发现 {len(tasks)} 个任务，预期 {expected}",
            err=True,
            fg=typer.colors.RED,
        )
        raise typer.Exit(2)

    task_states = [(task, inspect_task(task)) for task in tasks]
    incomplete = [state for _, state in task_states if state["status"] != "PASS"]
    if incomplete and not skip_incomplete:
        typer.secho(
            f"错误: {len(incomplete)}/{len(tasks)} 个任务未完成；未创建输出",
            err=True,
            fg=typer.colors.RED,
        )
        raise typer.Exit(2)

    parsed = []
    audit_rows: list[dict] = []
    discovered_elements: set[str] = set()
    for task, state in task_states:
        if state["status"] != "PASS":
            detail = state.get("detail") or state["status"]
            audit_rows.append(
                {
                    "task": str(task),
                    "format": "",
                    "status": "SKIP",
                    "error": f"{state['status']}: {detail}",
                }
            )
            continue
        row = {"task": str(task), "format": "", "status": "PENDING", "error": ""}
        try:
            task_fmt = _format(task, fmt)
            data = dpdata.LabeledSystem(str(task), fmt=task_fmt)
            if len(data) < 1:
                raise ValueError("dpdata 返回零帧")
            mask = finite_labeled(data, require_virial=require_virial)
            valid = np.flatnonzero(mask)
            if valid.size < 1:
                raise ValueError("没有标注完整的有限值帧")
            if frames == "final":
                if valid[-1] != len(data) - 1:
                    raise ValueError("最后一帧标注不完整")
                valid = valid[-1:]
            selected = data.sub_system(valid)
            discovered_elements.update(selected.data["atom_names"])
            parsed.append((task, task_fmt, selected, valid))
            row.update(
                {
                    "format": task_fmt,
                    "status": "PASS",
                    "raw_frames": len(data),
                    "written_frames": len(selected),
                }
            )
        except Exception as exc:
            row.update(
                {
                    "status": "SKIP" if skip_incomplete else "FAIL",
                    "error": f"{type(exc).__name__}: {exc}",
                }
            )
        audit_rows.append(row)
    failed = [row for row in audit_rows if row["status"] == "FAIL"]
    if failed:
        typer.secho(
            f"错误: {len(failed)} 个已完成任务无法解析；未创建输出",
            err=True,
            fg=typer.colors.RED,
        )
        raise typer.Exit(2)
    skipped = [row for row in audit_rows if row["status"] == "SKIP"]
    if not parsed:
        typer.secho(
            f"错误: {len(skipped)}/{len(tasks)} 个任务未完成或无法解析，"
            "没有可提取的任务；未创建输出",
            err=True,
            fg=typer.colors.RED,
        )
        raise typer.Exit(2)
    if skipped:
        typer.secho(
            f"警告: 跳过 {len(skipped)}/{len(tasks)} 个任务"
            "（未完成或解析失败），明细见 task_parse_audit.csv",
            err=True,
            fg=typer.colors.YELLOW,
        )

    try:
        global_map = parse_type_map(type_map, discovered_elements)
        ensure_empty_output(output)
    except (ValueError, FileExistsError) as exc:
        typer.secho(f"错误: {exc}", err=True, fg=typer.colors.RED)
        raise typer.Exit(1) from exc

    systems = defaultdict(lambda: None)
    offsets: Counter[str] = Counter()
    frame_rows: list[dict] = []
    for task, task_fmt, data, raw_indices in parsed:
        system_id = exact_formula(data, global_map)
        normalized = normalize(data, global_map)
        systems[system_id] = append_system(systems[system_id], normalized)
        for local_index, raw_index in enumerate(raw_indices):
            frame_rows.append(
                {
                    "system_id": system_id,
                    "output_frame_index": offsets[system_id] + local_index,
                    "task": str(task),
                    "format": task_fmt,
                    "raw_frame_index": int(raw_index),
                    "energy_eV": float(data.data["energies"][local_index]),
                }
            )
        offsets[system_id] += len(data)

    system_rows = []
    for system_id, data in sorted(systems.items()):
        path = output / "deepmd_npy" / system_id
        data.to("deepmd/npy", str(path), set_size=set_size, prec=np.float64)
        loaded = dpdata.LabeledSystem(str(path), fmt="deepmd/npy")
        valid = finite_labeled(loaded, require_virial=require_virial)
        passed = (
            len(loaded) == len(data)
            and int(valid.sum()) == len(data)
            and list(loaded.data["atom_names"]) == global_map
        )
        system_rows.append(
            {
                "system_id": system_id,
                "frames": len(data),
                "natoms": data.get_natoms(),
                "type_map": " ".join(global_map),
                "validation": "PASS" if passed else "FAIL",
            }
        )

    write_csv(output / "task_parse_audit.csv", audit_rows)
    write_csv(output / "frame_manifest.csv", frame_rows)
    write_csv(output / "system_summary.csv", system_rows)
    summary = {
        "root": str(root.resolve()),
        "output": str(output.resolve()),
        "parser": "dpdata.LabeledSystem",
        "dpdata_version": getattr(dpdata, "__version__", "unknown"),
        "python_version": platform.python_version(),
        "numpy_version": np.__version__,
        "frame_mode": frames,
        "require_virial": require_virial,
        "type_map": global_map,
        "tasks_discovered": len(tasks),
        "tasks_parsed": len(parsed),
        "tasks_incomplete_skipped": len(incomplete),
        "tasks_parse_failed_skipped": max(len(skipped) - len(incomplete), 0),
        "systems": len(system_rows),
        "frames": len(frame_rows),
        "all_systems_validated": all(
            row["validation"] == "PASS" for row in system_rows
        ),
    }
    write_json(output / "reports" / "summary.json", summary)
    write_sha256_manifest(output)
    typer.echo(json.dumps(summary, ensure_ascii=False, indent=2))
    if not summary["all_systems_validated"]:
        raise typer.Exit(2)
