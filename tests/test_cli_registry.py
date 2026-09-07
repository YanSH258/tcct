from typer.main import get_command
from typer.testing import CliRunner

from tcct.cli import app
from tcct.menu import MENU, _prompt_dpdata_format
from tcct.registry import GROUPS


runner = CliRunner()


def test_main_menu_order_and_descriptions():
    assert [(group.menu_key, group.display_name, group.cli_help) for group in GROUPS] == [
        ("1", "Structure", "单个结构文件转换"),
        ("2", "ABACUS", "输入准备、计算检查与数据提取"),
        ("3", "CP2K", "计算检查与数据提取"),
        ("4", "VASP", "OUTCAR 数据提取"),
        ("5", "dpdata", "带标签数据格式转换与重复检查"),
        ("6", "DeepMD", "NPY 数据集统计、合并与报告"),
        ("7", "GPUMD", "train.xyz 准备与 NEP 结果分析"),
        ("8", "DPA4", "结构优化、单点计算和 NEB"),
        ("9", "System", "环境检查"),
    ]


def test_dpdata_format_menu_accepts_number_and_exact_name(monkeypatch):
    answers = iter(["3", "deepmd/npy/mixed"])
    monkeypatch.setattr("builtins.input", lambda _: next(answers))
    formats = ("deepmd/npy", "deepmd/raw", "extxyz")
    assert _prompt_dpdata_format("输入格式", "deepmd/npy", formats) == "extxyz"
    assert (
        _prompt_dpdata_format("输入格式", "deepmd/npy", formats)
        == "deepmd/npy/mixed"
    )


def test_registry_matches_cli_and_menu():
    root = get_command(app)
    expected_root = {group.cli_name for group in GROUPS if group.cli_name}
    expected_root.update(
        command.name
        for group in GROUPS
        if group.cli_name is None
        for command in group.commands
    )
    assert set(root.commands) == expected_root

    for group in GROUPS:
        menu_commands = {entry[0] for entry in MENU[group.menu_key][1]}
        expected_commands = {command.name for command in group.commands}
        assert menu_commands == expected_commands
        if group.cli_name is not None:
            assert set(root.commands[group.cli_name].commands) == expected_commands


def test_workflow_command_order():
    commands = {
        group.cli_name: [command.name for command in group.commands]
        for group in GROUPS
        if group.cli_name is not None
    }
    assert commands["abacus"] == [
        "prepare-from-xyz",
        "audit",
        "report",
        "to-deepmd",
        "check-relax",
    ]
    assert commands["deepmd"] == ["stat", "report", "merge", "split", "plot-parity"]
    assert commands["gpumd"] == [
        "npy-to-xyz",
        "plot-nep-evaluation",
        "thermo",
        "merge-loss",
    ]


def test_every_registered_command_has_working_help():
    for group in GROUPS:
        for command in group.commands:
            arguments = (
                [group.cli_name, command.name, "--help"]
                if group.cli_name
                else [command.name, "--help"]
            )
            result = runner.invoke(app, arguments)
            assert result.exit_code == 0, f"{' '.join(arguments)}\n{result.output}"


def test_removed_command_names_are_not_registered():
    root = get_command(app)
    assert "from-deepmd" not in root.commands["gpumd"].commands
    assert "collect" not in root.commands["cp2k"].commands
    assert "to-deepmd" not in root.commands["vasp"].commands
    assert "npy-to-xyz" in root.commands["gpumd"].commands
    assert "singlepoint-to-deepmd" in root.commands["cp2k"].commands
    assert "outcar-to-deepmd" in root.commands["vasp"].commands
    assert "plot-convergence" not in root.commands["abacus"].commands
