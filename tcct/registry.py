"""Single command registry shared by the Typer CLI and interactive menu."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Optional, Tuple

from tcct.abacus.audit import audit
from tcct.abacus.check_relax import check_relax
from tcct.abacus.prepare_from_xyz import prepare_from_xyz
from tcct.abacus.report import report as abacus_report
from tcct.abacus.to_deepmd import to_deepmd
from tcct.cp2k.audit import audit as cp2k_audit
from tcct.cp2k.aimd_to_deepmd import aimd_to_deepmd
from tcct.cp2k.singlepoint_to_deepmd import singlepoint_to_deepmd
from tcct.deepmd.merge import merge
from tcct.deepmd.plot_parity import plot_parity as deepmd_plot_parity
from tcct.deepmd.report import report as deepmd_report
from tcct.deepmd.split import split as deepmd_split
from tcct.deepmd.stat import stat
from tcct.doctor import doctor
from tcct.dpdata.convert import convert
from tcct.dpdata.overlap import overlap
from tcct.dpdata.xyz_to_deepmd import xyz_to_deepmd
from tcct.dpa4.batch_relax import batch_relax
from tcct.dpa4.evaluate import evaluate as dpa4_evaluate
from tcct.dpa4.neb import neb as dpa4_neb
from tcct.dpa4.relax import relax as dpa4_relax
from tcct.gpumd.npy_to_xyz import npy_to_xyz
from tcct.gpumd.merge_loss import merge_loss
from tcct.gpumd.plot_nep_evaluation import plot_nep_evaluation
from tcct.gpumd.thermo import thermo
from tcct.structure.convert import convert as structure_convert
from tcct.vasp.outcar_to_deepmd import outcar_to_deepmd


MenuParameter = Tuple[str, str, str, bool]


@dataclass(frozen=True)
class CommandSpec:
    name: str
    callback: Callable[..., Any]
    menu_description: str
    menu_parameters: Tuple[MenuParameter, ...] = ()


@dataclass(frozen=True)
class GroupSpec:
    menu_key: str
    display_name: str
    cli_name: Optional[str]
    cli_help: str
    commands: Tuple[CommandSpec, ...]


GROUPS = (
    GroupSpec("1", "Structure", "structure", "单个结构文件转换", (
        CommandSpec("convert", structure_convert, "CIF/POSCAR/STRU/XYZ 相互转换", (
            ("input", "输入 CIF / POSCAR / Extended XYZ", "structure.cif", False),
            ("--to", "目标格式 (cif/xyz/poscar/stru)", "xyz", False),
            ("--basis", "STRU 基组 (pw/lcao)", "pw", False),
        )),
    )),
    GroupSpec("2", "ABACUS", "abacus", "输入准备、计算检查与数据提取", (
        CommandSpec("prepare-from-xyz", prepare_from_xyz, "将多个 XYZ 帧准备为 ABACUS 任务", (
            ("source", "多帧 Extended XYZ 或 XYZ 目录", "structures.xyz", False),
            ("template", "包含 INPUT 和 KPT 的模板目录", "template", False),
            ("output", "创建新的工作目录", "abacus_tasks", False),
        )),
        CommandSpec("audit", audit, "批量检查任务，输出 CSV/JSON", (("root", "任务根目录", ".", False),)),
        CommandSpec("report", abacus_report, "生成批量任务 HTML 报告", (
            ("root", "任务根目录", ".", False),
            ("--output", "报告目录", "abacus_report", False),
        )),
        CommandSpec("to-deepmd", to_deepmd, "从计算结果提取 DeepMD NPY", (
            ("root", "任务根目录", ".", False),
            ("output", "输出目录", "deepmd_from_abacus", False),
            ("--strict", "存在未完成任务时中止 (y/n)", "n", True),
        )),
        CommandSpec("check-relax", check_relax, "检查结构优化并可绘制收敛曲线", (
            ("dir", "计算目录", ".", False),
            ("plot", "是否生成收敛曲线 (y/n)", "n", True),
        )),
    )),
    GroupSpec("3", "CP2K", "cp2k", "计算检查与数据提取", (
        CommandSpec("audit", cp2k_audit, "批量检查输出，生成 CSV/JSON", (
            ("root", "任务根目录或 output.log", ".", False),
            ("--output", "审计 CSV", "cp2k_audit.csv", False),
        )),
        CommandSpec("singlepoint-to-deepmd", singlepoint_to_deepmd, "收集多个单点任务为 DeepMD NPY", (
            ("root", "CP2K 单点任务根目录", ".", False),
            ("output", "新的数据集目录", "cp2k_dataset", False),
        )),
        CommandSpec("aimd-to-deepmd", aimd_to_deepmd, "转换一个 AIMD 轨迹为 DeepMD NPY", (
            ("root", "CP2K AIMD 计算目录", ".", False),
            ("output", "新的数据集目录", "cp2k_aimd_dataset", False),
        )),
    )),
    GroupSpec("4", "VASP", "vasp", "OUTCAR 数据提取", (
        CommandSpec("outcar-to-deepmd", outcar_to_deepmd, "从 OUTCAR 提取 DeepMD NPY", (
            ("root", "任务根目录或 OUTCAR", ".", False),
            ("output", "输出目录", "vasp_dataset", False),
        )),
    )),
    GroupSpec("5", "dpdata", "dpdata", "带标签数据格式转换与重复检查", (
        CommandSpec("convert", convert, "高级格式转换（菜单可选常用格式）", (
            ("input", "输入文件或目录", ".", False),
            ("output", "输出文件或目录", "converted_data", False),
            ("--from", "输入格式", "deepmd/npy", False),
            ("--to", "输出格式", "extxyz", False),
        )),
        CommandSpec("xyz-to-deepmd", xyz_to_deepmd, "GPUMD/extxyz 转 DeepMD NPY", (
            ("input", "输入 GPUMD/extxyz 文件", "train.xyz", False),
            ("output", "输出目录", "deepmd", False),
        )),
        CommandSpec("overlap", overlap, "检查两个数据集中的重复帧", (
            ("reference", "参考结构数据集", "train.extxyz", False),
            ("candidate", "待检查结构数据集", "test.extxyz", False),
            ("--output", "JSON 汇总", "frame_overlap.json", False),
        )),
    )),
    GroupSpec("6", "DeepMD", "deepmd", "NPY 数据集统计、合并与报告", (
        CommandSpec("stat", stat, "统计 NPY 数据集", (("dir", "数据目录", ".", False),)),
        CommandSpec("report", deepmd_report, "生成 NPY 数据集审计报告", (
            ("dataset-path", "数据集目录", ".", False),
            ("--output", "报告目录", "deepmd_report", False),
            ("minimum-distance", "是否检查全部帧的 PBC 最小距离 (y/n)", "n", True),
        )),
        CommandSpec("merge", merge, "按组成合并 NPY 数据集", (
            ("@args", "输入目录（空格分隔）", "data_a data_b", False),
            ("--output", "输出目录", "deepmd_merged", False),
        )),
        CommandSpec("split", deepmd_split, "划分 NPY 训练集和测试集", (
            ("dataset", "DeepMD NPY 数据集", ".", False),
            ("--output", "新的划分目录", "deepmd_split", False),
            ("--test-size", "测试集比例或帧数", "0.1", False),
            ("--method", "选择方法 (random/uniform)", "random", False),
            ("--seed", "随机种子", "42", False),
        )),
        CommandSpec("plot-parity", deepmd_plot_parity, "绘制 dp test 对角线图 (E/F/V/S)", (
            ("directory", "dp test 输出目录", ".", False),
            ("--output", "输出图片", "deepmd_parity.png", False),
            ("--metrics", "误差指标 JSON", "deepmd_parity_metrics.json", False),
        )),
    )),
    GroupSpec("7", "GPUMD", "gpumd", "train.xyz 准备与 NEP 结果分析", (
        CommandSpec("npy-to-xyz", npy_to_xyz, "DeepMD NPY 转 GPUMD train.xyz", (
            ("dataset", "DeepMD NPY 数据集根目录", ".", False),
            ("output", "GPUMD Extended XYZ", "train.xyz", False),
        )),
        CommandSpec("plot-nep-evaluation", plot_nep_evaluation, "绘制 NEP loss 和已有预测结果", (
            ("directory", "NEP 输出目录", ".", False),
            ("--output", "输出图片", "nep_evaluation.png", False),
            ("--metrics", "误差指标 JSON", "nep_evaluation_metrics.json", False),
        )),
        CommandSpec("thermo", thermo, "统计或绘制 GPUMD thermo.out", (
            ("file", "thermo 文件", "thermo.out", False),
            ("plot", "是否生成热力学图 (y/n)", "n", True),
        )),
        CommandSpec("merge-loss", merge_loss, "合并首次训练与续训的 loss.out", (
            ("first", "首次训练 loss 文件", "loss.out", False),
            ("restart", "续训 loss 文件", "restart/loss.out", False),
            ("--output", "输出文件", "loss_merged.out", False),
        )),
    )),
    GroupSpec("8", "DPA4", "dpa4", "结构优化、单点计算和 NEB", (
        CommandSpec("relax", dpa4_relax, "使用 DPA4 优化结构", (
            ("input", "输入结构", "structure.xyz", False),
            ("--output", "输出结构", "structure_dpa4_relaxed.extxyz", False),
            ("--model", "DPA4 model.pt", "~/dpa4/Neo-MPtrj/model.pt", False),
        )),
        CommandSpec("batch-relax", batch_relax, "批量优化结构", (
            ("manifest", "任务 manifest", "structures.csv", False),
            ("--output-dir", "输出目录", "dpa4_batch_relax", False),
            ("--model", "DPA4 model.pt", "~/dpa4/Neo-MPtrj/model.pt", False),
        )),
        CommandSpec("evaluate", dpa4_evaluate, "计算能量和力", (
            ("input", "单帧或多帧结构", "structures.extxyz", False),
            ("--output", "带标注的 extxyz", "structures_dpa4_evaluated.extxyz", False),
            ("--model", "DPA4 model.pt", "~/dpa4/Neo-MPtrj/model.pt", False),
        )),
        CommandSpec("neb", dpa4_neb, "计算 NEB/CI-NEB", (
            ("initial", "已优化初态", "initial.extxyz", False),
            ("final", "已优化末态", "final.extxyz", False),
            ("--output-dir", "输出目录", "dpa4_neb", False),
            ("--model", "DPA4 model.pt", "~/dpa4/Neo-MPtrj/model.pt", False),
        )),
    )),
    GroupSpec("9", "System", None, "环境检查", (
        CommandSpec("doctor", doctor, "检查安装和计算资源"),
    )),
)
