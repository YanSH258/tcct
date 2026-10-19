import os

from typer.main import get_command
from typer.testing import CliRunner

from tcct.cli import app
from tcct.menu import (
    MENU,
    _match_direct_code,
    _path_completer,
    _prompt_dpdata_format,
    _run_command,
    run_menu,
)
from tcct.registry import GROUPS


runner = CliRunner()


def _scripted_inputs(answers, prompts):
    answers = iter(answers)

    def fake_input(prompt=""):
        prompts.append(prompt)
        return next(answers)

    return fake_input


def _params(group_key, cmd_name):
    for cmd, _, params in MENU[group_key][1]:
        if cmd == cmd_name:
            return params
    raise AssertionError(f"menu command not found: {cmd_name}")


def _fake_execute(captured):
    return lambda app, args, display: captured.append((args, display))


def test_main_menu_order_and_descriptions():
    assert [(group.menu_key, group.display_name, group.cli_help) for group in GROUPS] == [
        ("1", "Structure", "结构转换与几何检查"),
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


def test_run_command_skips_prompt_for_cwd_default(monkeypatch):
    monkeypatch.setattr("tcct.menu._execute", _fake_execute([]))

    def no_input(prompt=""):
        raise AssertionError(f"unexpected prompt: {prompt}")

    monkeypatch.setattr("builtins.input", no_input)
    # audit 的 root 默认 "."，不询问，直接用启动目录
    result = _run_command(app, "abacus", "audit", _params("2", "audit"))
    assert result[0] == ["abacus", "audit", "."]


def test_run_command_applies_flag_choices(monkeypatch):
    monkeypatch.setattr("tcct.menu._execute", _fake_execute([]))
    # registry 里 --strict 自带 "--" 前缀，plot 没有；两种都要拼成合法开关
    monkeypatch.setattr("builtins.input", _scripted_inputs(["", "y"], []))
    result = _run_command(app, "abacus", "to-deepmd", _params("2", "to-deepmd"))
    assert result[0] == ["abacus", "to-deepmd", ".", "deepmd_from_abacus", "--strict"]

    monkeypatch.setattr("builtins.input", _scripted_inputs(["y"], []))
    result = _run_command(app, "abacus", "check-relax", _params("2", "check-relax"))
    assert result[0] == ["abacus", "check-relax", ".", "--plot"]


def test_run_command_cancel_returns_none(monkeypatch):
    monkeypatch.setattr("tcct.menu._execute", _fake_execute([]))
    # report 的 root 默认 "." 不询问，取消发生在 --output 提示上
    monkeypatch.setattr("builtins.input", _scripted_inputs(["q"], []))
    assert _run_command(app, "abacus", "report", _params("2", "report")) is None


def test_match_direct_code():
    assert _match_direct_code("63") == ("6", 3)
    assert _match_direct_code("11") == ("1", 1)
    assert _match_direct_code("91") == ("9", 1)
    assert _match_direct_code("66") is None  # DeepMD 只有 5 条命令
    assert _match_direct_code("6") is None
    assert _match_direct_code("ab") is None
    assert _match_direct_code("0") is None


def test_run_menu_direct_code_and_rerun(monkeypatch):
    captured = []
    monkeypatch.setattr("tcct.menu._execute", _fake_execute(captured))
    # audit 的 root 默认 "." 不询问；report 只问 --output
    answers = ["22", "23", "rep", "r", "0"]
    monkeypatch.setattr("builtins.input", _scripted_inputs(answers, []))
    run_menu(app)
    assert captured[0][0] == ["abacus", "audit", "."]
    assert captured[-1][0] == ["abacus", "report", ".", "--output", "rep"]


def test_run_menu_rerun_without_history(monkeypatch, capsys):
    monkeypatch.setattr("builtins.input", _scripted_inputs(["r", "0"], []))
    run_menu(app)
    assert "还没有可重跑的命令" in capsys.readouterr().out


def test_run_menu_code_map_lists_numbers_and_scripts(monkeypatch, capsys):
    monkeypatch.setattr("builtins.input", _scripted_inputs(["h", "0"], []))
    run_menu(app)
    out = capsys.readouterr().out
    assert "编号与脚本对照" in out
    assert "25" in out  # 直达码：ABACUS 第 5 条 check-relax
    assert "tcct/abacus/check_relax.py" in out
    assert "tcct/tcct/" not in out  # 防止包目录重复前缀
    assert "tcct/doctor.py" in out


def test_path_completer_completes_files_and_dirs(tmp_path, monkeypatch):
    (tmp_path / "a.xyz").write_text("", encoding="utf-8")
    (tmp_path / "b.xyz").write_text("", encoding="utf-8")
    (tmp_path / "sub").mkdir()
    monkeypatch.chdir(tmp_path)
    assert _path_completer("a", 0) == "a.xyz"
    assert _path_completer("a", 1) is None
    assert _path_completer("s", 0) == "sub" + os.sep
    assert _path_completer("", 0) == "a.xyz"
    assert _path_completer("nope", 0) is None
