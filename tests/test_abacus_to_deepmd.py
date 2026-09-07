"""abacus to-deepmd 的跳过/严格模式行为测试。

用内存构造的 dpdata 体系 + 桩替换 require_dpdata，避免真实 ABACUS 输出；
NPY 写出与回读校验走真实 dpdata 逻辑。
"""

import json
from pathlib import Path

import numpy as np
import pytest
from typer.testing import CliRunner

from tcct.cli import app

GOOD_LOG = (
    "charge density convergence is achieved\n"
    "!FINAL_ETOT_IS -1.0 eV\n"
    "TOTAL-FORCE (eV/Angstrom)\n"
    "TOTAL-STRESS (KBAR)\n"
    "Finish Time : now\n"
)
INPUT_TEXT = "INPUT_PARAMETERS\ncalculation scf\nbasis_type pw\n"


def write_task(root: Path, name: str, log_text: str) -> Path:
    task = root / name
    out = task / "OUT.test"
    out.mkdir(parents=True)
    (task / "INPUT").write_text(INPUT_TEXT)
    (out / "running_scf.log").write_text(log_text)
    return task


def system_data() -> dict:
    return {
        "atom_names": ["H"],
        "atom_numbs": [2],
        "atom_types": np.array([0, 0]),
        "cells": np.array([np.eye(3) * 10.0]),
        "coords": np.array([[[0.0, 0.0, 0.0], [0.8, 0.0, 0.0]]]),
        "energies": np.array([-1.0]),
        "forces": np.zeros((1, 2, 3)),
        "virials": np.zeros((1, 3, 3)),
        "orig": np.zeros(3),
    }


class _StubDpdata:
    """dpdata 桩模块：LabeledSystem 真子类，路径含 broken 抛错，
    deepmd/npy 走真实文件读取，其余返回内存构造的体系。"""

    __version__ = "stub"

    def __init__(self):
        import dpdata

        class LabeledSystem(dpdata.LabeledSystem):
            def __init__(self, path=None, fmt=None, **kwargs):
                if fmt == "deepmd/npy":
                    super().__init__(path, fmt=fmt, **kwargs)
                elif "broken" in str(path):
                    raise ValueError("boom")
                else:
                    super().__init__(data=system_data())

        self.LabeledSystem = LabeledSystem


@pytest.fixture
def stub_dpdata(monkeypatch):
    monkeypatch.setattr(
        "tcct.abacus.to_deepmd.require_dpdata", lambda: _StubDpdata()
    )


def command_stderr(result) -> str:
    try:
        return result.stderr
    except ValueError:
        return result.output


def audit_rows(output: Path) -> list[dict]:
    import csv

    with open(output / "task_parse_audit.csv") as handle:
        return list(csv.DictReader(handle))


def test_default_skips_incomplete_and_extracts_done(
    tmp_path: Path, stub_dpdata
):
    root = tmp_path / "tasks"
    write_task(root, "good_task", GOOD_LOG)
    write_task(root, "pending_task", "Finish Time : now\n")
    output = tmp_path / "dataset"

    result = CliRunner().invoke(
        app, ["abacus", "to-deepmd", str(root), str(output)]
    )

    assert result.exit_code == 0, command_stderr(result) or result.output
    assert (output / "deepmd_npy" / "H2" / "type.raw").is_file()
    rows = audit_rows(output)
    skip = [row for row in rows if row["status"] == "SKIP"]
    assert len(skip) == 1
    assert skip[0]["task"].endswith("pending_task")
    assert "INCOMPLETE" in skip[0]["error"]
    summary = json.loads((output / "reports" / "summary.json").read_text())
    assert summary["tasks_parsed"] == 1
    assert summary["tasks_incomplete_skipped"] == 1
    assert summary["tasks_parse_failed_skipped"] == 0
    assert "跳过 1/2" in command_stderr(result)


def test_strict_aborts_on_incomplete(tmp_path: Path, stub_dpdata):
    root = tmp_path / "tasks"
    write_task(root, "good_task", GOOD_LOG)
    write_task(root, "pending_task", "Finish Time : now\n")
    output = tmp_path / "dataset"

    result = CliRunner().invoke(
        app, ["abacus", "to-deepmd", str(root), str(output), "--strict"]
    )

    stderr = command_stderr(result)
    assert result.exit_code == 2, stderr or result.output
    assert "1/2 个任务未完成" in stderr
    assert not output.exists()


def test_default_skips_unparseable_task(tmp_path: Path, stub_dpdata):
    root = tmp_path / "tasks"
    write_task(root, "good_task", GOOD_LOG)
    write_task(root, "broken_task", GOOD_LOG)
    output = tmp_path / "dataset"

    result = CliRunner().invoke(
        app, ["abacus", "to-deepmd", str(root), str(output)]
    )

    assert result.exit_code == 0, command_stderr(result) or result.output
    assert (output / "deepmd_npy" / "H2" / "type.raw").is_file()
    rows = audit_rows(output)
    skip = [row for row in rows if row["status"] == "SKIP"]
    assert len(skip) == 1
    assert skip[0]["task"].endswith("broken_task")
    assert "boom" in skip[0]["error"]
    summary = json.loads((output / "reports" / "summary.json").read_text())
    assert summary["tasks_parse_failed_skipped"] == 1


def test_no_extractable_tasks_fails_without_output(tmp_path: Path, stub_dpdata):
    root = tmp_path / "tasks"
    write_task(root, "pending_task", "Finish Time : now\n")
    output = tmp_path / "dataset"

    result = CliRunner().invoke(
        app, ["abacus", "to-deepmd", str(root), str(output)]
    )

    stderr = command_stderr(result)
    assert result.exit_code == 2, stderr or result.output
    assert "没有可提取的任务" in stderr
    assert not output.exists()
