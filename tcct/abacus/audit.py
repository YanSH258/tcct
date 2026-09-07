"""Batch audit ABACUS SCF, relax, and cell-relax task directories."""

from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path
from typing import Optional

import typer

from tcct.common.io import write_csv, write_json

_CALC_RE = re.compile(r"^\s*calculation\s+(\S+)", re.I | re.M)
_BASIS_RE = re.compile(r"^\s*basis_type\s+(\S+)", re.I | re.M)
# SCF 收敛标记：CPU 构建打印 "charge density convergence is achieved"，
# GPU 构建打印 "#SCF IS CONVERGED#"。不做更宽的匹配（例如裸词 converged），
# 以免被 "Relaxation is not converged yet!" 之类的行误触发。
_SCF_CONV_RE = re.compile(
    r"charge\s+density\s+convergence\s+is\s+achieved|#\s*SCF\s+IS\s+CONVERGED\s*#",
    re.IGNORECASE,
)


def parse_calculation(task: Path) -> str:
    input_file = task / "INPUT"
    if not input_file.is_file():
        return "unknown"
    match = _CALC_RE.search(input_file.read_text(errors="replace"))
    return match.group(1).lower() if match else "unknown"


def parse_basis_type(task: Path, default: str = "lcao") -> str:
    """从 INPUT 读取 basis_type；缺失时默认 lcao（与 dpdata 常用格式一致）。"""
    input_file = task / "INPUT"
    if not input_file.is_file():
        return default
    match = _BASIS_RE.search(input_file.read_text(errors="replace"))
    return match.group(1).lower() if match else default


def find_log(task: Path, calculation: str) -> Optional[Path]:
    preferred = {
        "scf": "running_scf.log",
        "relax": "running_relax.log",
        "cell-relax": "running_cell-relax.log",
        "md": "running_md.log",
    }.get(calculation)
    logs = sorted(task.glob(f"OUT.*/{preferred}")) if preferred else []
    if preferred and (task / preferred).is_file():
        logs.append(task / preferred)
    if not logs:
        logs = sorted(task.glob("OUT.*/running_*.log"))
    if not logs:
        logs = sorted(task.glob("running_*.log"))
    return logs[-1] if logs else None


def inspect_task(task: Path) -> dict:
    calculation = parse_calculation(task)
    log = find_log(task, calculation)
    row = {
        "task": str(task),
        "calculation": calculation,
        "log": str(log) if log else "",
        "exit_0": (task / "ABACUS_EXIT_0").is_file(),
        "exit_nonzero": (task / "ABACUS_EXIT_NONZERO").is_file(),
        "scf_converged": False,
        "relax_converged": False,
        "final_energy": False,
        "finish_time": False,
        "has_force": False,
        "has_stress": False,
        "status": "INCOMPLETE",
    }
    if log is None:
        row["detail"] = "未找到 running_*.log"
        return row
    text = log.read_text(errors="replace")
    row.update(
        {
            "scf_converged": bool(_SCF_CONV_RE.search(text)),
            "relax_converged": "Relaxation is converged" in text,
            "final_energy": "!FINAL_ETOT_IS" in text,
            "finish_time": "Finish Time" in text,
            "has_force": "TOTAL-FORCE" in text,
            "has_stress": "TOTAL-STRESS" in text,
        }
    )
    calc_ok = row["scf_converged"]
    if calculation in {"relax", "cell-relax"}:
        calc_ok = calc_ok and row["relax_converged"]
    if calculation == "md":
        # MD 无 SCF/结构收敛概念，以正常结束为准
        calc_ok = row["finish_time"]
    if calculation == "md":
        passed = calc_ok and not row["exit_nonzero"]
    else:
        passed = (
            calc_ok
            and row["final_energy"]
            and row["finish_time"]
            and not row["exit_nonzero"]
        )
    row["status"] = "PASS" if passed else "INCOMPLETE"
    missing = []
    if not passed:
        if row["exit_nonzero"]:
            missing.append("存在 ABACUS_EXIT_NONZERO")
        if calculation not in {"md"} and not row["scf_converged"]:
            missing.append("未发现 SCF 收敛标记")
        if calculation in {"relax", "cell-relax"} and not row["relax_converged"]:
            missing.append("未发现结构优化收敛标记")
        if calculation != "md" and not row["final_energy"]:
            missing.append("未发现最终能量")
        if not row["finish_time"]:
            missing.append("未发现 Finish Time")
    row["detail"] = "；".join(missing)
    return row


def _inside_out_dir(path: Path) -> bool:
    """排除位于 ABACUS OUT.*/ 目录下的 INPUT（避免与任务目录重复）。"""
    return any(part.startswith("OUT.") for part in path.parent.parts)


def discover_tasks(root: Path, pattern: str) -> list[Path]:
    if (root / "INPUT").is_file():
        return [root]
    if pattern == "**/INPUT":
        paths = root.rglob("INPUT")
    else:
        paths = (path for path in root.glob(pattern) if path.name == "INPUT")
    return sorted({path.parent for path in paths if not _inside_out_dir(path)})


def audit(
    root: Path = typer.Argument(Path("."), help="任务目录"),
    pattern: str = typer.Option("**/INPUT", help="相对 root 的 INPUT 搜索模式"),
    output: Path = typer.Option(Path("abacus_audit.csv"), "-o", "--output"),
    expected: Optional[int] = typer.Option(None, help="预期任务数"),
    strict: bool = typer.Option(False, help="存在未完成任务时返回非零退出码"),
    json_out: bool = typer.Option(False, "--json", help="同时在 stdout 输出 JSON"),
):
    """批量检查 ABACUS 完成与收敛状态，生成 CSV/JSON 审计结果。"""
    if not root.is_dir():
        typer.secho(f"错误: 目录不存在: {root}", fg=typer.colors.RED, err=True)
        raise typer.Exit(1)
    tasks = discover_tasks(root.resolve(), pattern)
    if not tasks:
        typer.secho("错误: 未发现 INPUT 文件", fg=typer.colors.RED, err=True)
        raise typer.Exit(1)
    rows = [inspect_task(task) for task in tasks]
    write_csv(output, rows)
    counts = Counter(row["status"] for row in rows)
    summary = {
        "root": str(root.resolve()),
        "tasks": len(rows),
        "pass": counts["PASS"],
        "incomplete": counts["INCOMPLETE"],
        "expected": expected,
        "expected_match": expected is None or expected == len(rows),
        "output": str(output.resolve()),
    }
    write_json(output.with_suffix(".json"), summary)
    if json_out:
        typer.echo(json.dumps(summary, ensure_ascii=False, indent=2))
    else:
        typer.echo(
            f"任务 {len(rows)}，PASS {counts['PASS']}，"
            f"未完成 {counts['INCOMPLETE']}；报告: {output}"
        )
    failed = counts["INCOMPLETE"] > 0 or (expected is not None and expected != len(rows))
    if strict and failed:
        raise typer.Exit(2)
