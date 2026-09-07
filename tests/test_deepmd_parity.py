"""deepmd plot-parity 的行为测试：合成 dp test detail 文件验证绘图与指标。"""

import json
from pathlib import Path

import numpy as np
import pytest
from typer.testing import CliRunner

from tcct.cli import app

runner = CliRunner()


def command_stderr(result) -> str:
    try:
        return result.stderr
    except ValueError:
        return result.output

E_PERATOM = np.array(
    [
        [-1.00, -1.01],
        [-0.80, -0.79],
    ]
)
FORCE = np.array(
    [
        [0.1, 0.2, 0.3, 0.11, 0.19, 0.31],
        [-0.1, -0.2, -0.3, -0.09, -0.21, -0.29],
    ]
)


def _tensor_rows(offset: float) -> np.ndarray:
    data = np.arange(1.0, 10.0)
    pred = data + offset
    return np.vstack([np.concatenate([data, pred]) for _ in range(2)])


@pytest.fixture
def detail_dir(tmp_path: Path) -> Path:
    np.savetxt(tmp_path / "detail.e_peratom.out", E_PERATOM)
    np.savetxt(tmp_path / "detail.f.out", FORCE)
    np.savetxt(tmp_path / "detail.v_peratom.out", _tensor_rows(0.1))
    np.savetxt(tmp_path / "detail.s.out", _tensor_rows(1.0e-4))
    return tmp_path


def test_plot_parity_draws_all_properties(detail_dir: Path, tmp_path: Path):
    plot = tmp_path / "parity.png"
    metrics = tmp_path / "parity.json"
    result = runner.invoke(
        app,
        ["deepmd", "plot-parity", str(detail_dir), "--output", str(plot), "--metrics", str(metrics)],
    )
    assert result.exit_code == 0, result.output
    assert plot.is_file()
    values = json.loads(metrics.read_text())
    assert set(values["properties"]) == {
        "energy per atom",
        "force",
        "virial per atom",
        "stress",
    }
    energy = values["properties"]["energy per atom"]
    assert energy["file"] == "detail.e_peratom.out"
    assert energy["plot_mode"] == "scatter"
    assert np.isclose(energy["rmse"], 10.0)  # 0.01 eV/atom -> 10 meV/atom
    assert np.isclose(values["properties"]["force"]["rmse"], 10.0)
    assert np.isclose(values["properties"]["virial per atom"]["rmse"], 100.0)
    stress = values["properties"]["stress"]
    assert np.isclose(stress["rmse"], 1.0e-4 * 160.2176634)
    assert "energy per atom RMSE: 10" in result.output


def test_plot_parity_skips_multi_system_headers(detail_dir: Path, tmp_path: Path):
    rows = np.vstack([E_PERATOM, E_PERATOM])
    lines = ["# deepmd_npy/sys_a: data_e pred_e"]
    for index, row in enumerate(rows):
        lines.append("  ".join(f"{value:.16e}" for value in row))
        if index == 1:
            lines.append("# deepmd_npy/sys_b: data_e pred_e")
    (detail_dir / "detail.e_peratom.out").write_text("\n".join(lines) + "\n")
    metrics = tmp_path / "parity.json"
    result = runner.invoke(
        app,
        [
            "deepmd",
            "plot-parity",
            str(detail_dir),
            "--output",
            str(tmp_path / "parity.png"),
            "--metrics",
            str(metrics),
        ],
    )
    assert result.exit_code == 0, result.output
    energy = json.loads(metrics.read_text())["properties"]["energy per atom"]
    assert energy["values"] == 4
    assert np.isclose(energy["rmse"], 10.0)


def test_plot_parity_missing_directory(tmp_path: Path):
    result = runner.invoke(
        app, ["deepmd", "plot-parity", str(tmp_path / "missing")]
    )
    assert result.exit_code == 1


def test_plot_parity_without_detail_files(tmp_path: Path):
    result = runner.invoke(
        app, ["deepmd", "plot-parity", str(tmp_path)]
    )
    stderr = command_stderr(result)
    assert result.exit_code == 2, stderr or result.output
    assert "未找到 dp test detail 文件" in stderr


def test_plot_parity_rejects_existing_output(detail_dir: Path, tmp_path: Path):
    existing = tmp_path / "parity.png"
    existing.write_bytes(b"png")
    result = runner.invoke(
        app,
        ["deepmd", "plot-parity", str(detail_dir), "--output", str(existing)],
    )
    assert result.exit_code == 1
