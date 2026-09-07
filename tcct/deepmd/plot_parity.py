"""将 DeePMD `dp test` 的 detail 文件绘制成预测-标注对角线图。

`dp test` 产生的 `detail.*.out` 是纯数值表，`#` 开头的行为注释；对多个 system
测试时每个 system 的块前各有一行注释头（如
`# deepmd_npy/H16O208Mg2P48Ca76Sr2: data_e pred_e`），随数据一同拼接。

支持的面板（只画存在的文件，互不依赖）：
- detail.e_peratom.out  2 列  data_e      pred_e      eV/atom
- detail.f.out          6 列  data_fx/fy/fz  pred_fx/fy/fz  eV/Å（逐原子行）
- detail.v_peratom.out  18 列 data_v**    pred_v**    eV/atom（9 分量合并统计）
- detail.s.out          18 列 data_s**    pred_s**    eV/Å³，绘制时换算为 GPa

总能量 detail.e.out 与总 virial detail.v.out 不参与绘图：绝对量被体系
本身的能量基准（电子数与组成决定的常数项）主导，逐原子量才跨体系可比。
绘图样式复用 `tcct.common.plot_style`（Times/Okabe–Ito/300 dpi PNG）。
"""

from __future__ import annotations

import json
from math import ceil
from pathlib import Path

import numpy as np
import typer

from tcct.common.plot_style import (
    COLORS,
    add_panel_labels,
    apply_plot_style,
    figure_size,
    save_figure,
)

# 1 eV/Å³ = 1.602176634e11 Pa = 160.2176634 GPa（eV 为 CODATA 精确值）。
_GPA_PER_EV_A3 = 160.2176634

# (面板名, 文件名, 最少列数, 标注列切片, 预测列切片,
#  坐标轴单位, 坐标轴换算因子, 指标显示单位, 指标换算因子)
# 张量面板的 9 个分量在统计与绘图前合并展平。
DETAIL_SPECS = (
    (
        "energy per atom", "detail.e_peratom.out", 2,
        slice(0, 1), slice(1, 2),
        "eV/atom", 1.0, "meV/atom", 1000.0,
    ),
    (
        "force", "detail.f.out", 6,
        slice(0, 3), slice(3, 6),
        "eV/Å", 1.0, "meV/Å", 1000.0,
    ),
    (
        "virial per atom", "detail.v_peratom.out", 18,
        slice(0, 9), slice(9, 18),
        "eV/atom", 1.0, "meV/atom", 1000.0,
    ),
    (
        "stress", "detail.s.out", 18,
        slice(0, 9), slice(9, 18),
        "GPa", _GPA_PER_EV_A3, "GPa", 1.0,
    ),
)


def _load_detail(path: Path, minimum_columns: int) -> np.ndarray:
    """加载 detail 数值表；`#` 注释头（含多 system 拼接头）自动跳过。"""
    try:
        data = np.loadtxt(path, comments="#")
    except ValueError as exc:
        raise ValueError(f"无法解析数值文件 {path}: {exc}") from exc
    data = np.atleast_2d(data)
    if data.shape[1] < minimum_columns:
        raise ValueError(
            f"{path} 至少需要 {minimum_columns} 列，实际为 {data.shape[1]} 列"
        )
    if not np.all(np.isfinite(data)):
        raise ValueError(f"{path} 包含 NaN 或无穷值")
    if len(data) < 1:
        raise ValueError(f"{path} 没有数据行")
    return data


def _errors(predicted: np.ndarray, reference: np.ndarray) -> dict[str, float]:
    """逐点 RMSE、MAE 与 R²（预测 - 标注）。"""
    residual = predicted - reference
    ss_res = float(np.sum(residual**2))
    ss_tot = float(np.sum((reference - np.mean(reference)) ** 2))
    return {
        "rmse": float(np.sqrt(np.mean(residual**2))),
        "mae": float(np.mean(np.abs(residual))),
        "r2": float(1.0 - ss_res / ss_tot) if ss_tot > 0.0 else 1.0,
    }


def _sample(
    reference: np.ndarray, predicted: np.ndarray, max_points: int
) -> tuple[np.ndarray, np.ndarray]:
    """超过 max_points 时等距下采样，保持对整个数值范围的覆盖。"""
    if len(reference) <= max_points:
        return reference, predicted
    indices = np.linspace(0, len(reference) - 1, max_points, dtype=int)
    return reference[indices], predicted[indices]


def _limits(values: np.ndarray, padding: float = 0.06) -> tuple[float, float]:
    """数据范围加 6% 边距；单一值时给出非零跨度。"""
    low = float(np.min(values))
    high = float(np.max(values))
    span = high - low
    if span == 0.0:
        span = max(abs(low), 1.0)
    return low - padding * span, high + padding * span


def _draw_panel(
    ax,
    reference: np.ndarray,
    predicted: np.ndarray,
    label: str,
    axis_unit: str,
    metric: dict,
    metric_unit: str,
    max_points: int,
    density_threshold: int,
) -> str:
    """画一个对角线面板：密集数据用二维密度图，稀疏数据用散点。

    返回实际绘制模式（"density" 或 "scatter"）。
    """
    lower, upper = _limits(np.concatenate((reference, predicted)))
    if reference.size >= density_threshold:
        from matplotlib.colors import LogNorm

        ax.hist2d(
            reference,
            predicted,
            bins=120,
            range=((lower, upper), (lower, upper)),
            cmin=1,
            cmap="Blues",
            norm=LogNorm(),
        )
        mode = "density"
    else:
        ref_plot, pred_plot = _sample(reference, predicted, max_points)
        ax.scatter(
            ref_plot,
            pred_plot,
            s=5,
            alpha=0.35,
            linewidths=0,
            rasterized=True,
            color=COLORS["blue"],
        )
        mode = "scatter"
    ax.plot([lower, upper], [lower, upper], color=COLORS["gray"], ls="--", lw=0.9)
    ax.set_xlim(lower, upper)
    ax.set_ylim(lower, upper)
    ax.set_aspect("equal", adjustable="box")
    ax.set_xlabel(f"DFT {label} ({axis_unit})")
    ax.set_ylabel(f"Predicted {label} ({axis_unit})")
    ax.text(
        0.04,
        0.96,
        f"RMSE = {metric['rmse']:.3g} {metric_unit}\n"
        f"MAE = {metric['mae']:.3g} {metric_unit}\n"
        f"$R^2$ = {metric['r2']:.4f}",
        transform=ax.transAxes,
        ha="left",
        va="top",
    )
    return mode


def plot_parity(
    directory: Path = typer.Argument(Path("."), help="dp test 输出目录"),
    output: Path = typer.Option(
        Path("deepmd_parity.png"), "--output", "-o", help="输出图片"
    ),
    metrics_output: Path = typer.Option(
        Path("deepmd_parity_metrics.json"), "--metrics", help="误差指标 JSON"
    ),
    max_points: int = typer.Option(
        200_000, min=1000, help="散点模式每个面板最多绘制的点数"
    ),
    density_threshold: int = typer.Option(
        100_000, min=1000, help="达到该数据量时改用二维密度图"
    ),
) -> None:
    """绘制 dp test detail 文件的能量/力/virial/应力对角线图。"""
    directory = directory.expanduser().resolve()
    output = output.expanduser().resolve()
    metrics_output = metrics_output.expanduser().resolve()
    if not directory.is_dir():
        typer.secho(f"错误: 目录不存在: {directory}", err=True, fg=typer.colors.RED)
        raise typer.Exit(1)
    for path in (output, metrics_output):
        if path.exists():
            typer.secho(f"错误: 输出文件已存在: {path}", err=True, fg=typer.colors.RED)
            raise typer.Exit(1)

    panels = []
    for name, filename, columns, ref_slice, pred_slice, axis_unit, axis_scale, metric_unit, metric_scale in DETAIL_SPECS:
        path = directory / filename
        if not path.is_file():
            continue
        data = _load_detail(path, columns)
        panels.append(
            {
                "name": name,
                "file": filename,
                "reference": data[:, ref_slice].reshape(-1) * axis_scale,
                "predicted": data[:, pred_slice].reshape(-1) * axis_scale,
                "axis_unit": axis_unit,
                "metric_unit": metric_unit,
                "metric_scale": metric_scale,
            }
        )
    if not panels:
        supported = ", ".join(filename for _, filename, *_ in DETAIL_SPECS)
        typer.secho(
            f"错误: 未找到 dp test detail 文件；支持: {supported}",
            err=True,
            fg=typer.colors.RED,
        )
        raise typer.Exit(2)

    for panel in panels:
        metric = _errors(panel["predicted"], panel["reference"])
        # 指标换算为显示单位（如 eV/atom -> meV/atom）。
        metric["rmse"] *= panel["metric_scale"]
        metric["mae"] *= panel["metric_scale"]
        metric["values"] = int(panel["reference"].size)
        metric["unit"] = panel["metric_unit"]
        metric["plot_mode"] = "pending"
        panel["metric"] = metric

    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError as exc:
        typer.secho(
            "错误: 该命令需要 matplotlib，请运行 pip install -e '.[plot]'",
            err=True,
            fg=typer.colors.RED,
        )
        raise typer.Exit(3) from exc

    apply_plot_style()
    columns = 2 if len(panels) == 4 else min(3, len(panels))
    rows = ceil(len(panels) / columns)
    size_kind = "single" if columns == 1 else "double"
    height_ratio = 0.9 if columns == 1 else 0.40 * rows
    fig, axes = plt.subplots(
        rows,
        columns,
        squeeze=False,
        figsize=figure_size(size_kind, height_ratio),
    )
    flat_axes = list(axes.flat)
    for ax, panel in zip(flat_axes, panels):
        panel["metric"]["plot_mode"] = _draw_panel(
            ax,
            panel["reference"],
            panel["predicted"],
            panel["name"],
            panel["axis_unit"],
            panel["metric"],
            panel["metric_unit"],
            max_points,
            density_threshold,
        )
    for ax in flat_axes[len(panels):]:
        ax.axis("off")
    add_panel_labels(flat_axes[: len(panels)])
    fig.tight_layout()

    report = {
        "directory": str(directory),
        "files_used": [str(panel["file"]) for panel in panels],
        "properties": {
            panel["name"]: {
                "file": panel["file"],
                "unit": panel["metric_unit"],
                **panel["metric"],
            }
            for panel in panels
        },
    }
    save_figure(fig, output)
    metrics_output.parent.mkdir(parents=True, exist_ok=True)
    metrics_output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")

    typer.echo(f"已保存图片: {output}")
    typer.echo(f"已保存误差指标: {metrics_output}")
    for panel in panels:
        metric = panel["metric"]
        typer.echo(
            f"{panel['name']} RMSE: {metric['rmse']:.3g} {panel['metric_unit']}"
            f"（{metric['values']} 点，{metric['plot_mode']} 模式）"
        )
