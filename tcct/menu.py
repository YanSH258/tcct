"""交互式菜单（GPUMDkit 风格）。

菜单本身不实现任何命令逻辑：收集参数后，通过 typer.testing.CliRunner
调用同一个 typer app 执行，保证与命令行模式行为完全一致。

交互体验：
- 收集参数时可用 Tab 补全文件/目录名；
- 主菜单支持两位数直达码（组号+命令号，如 63）和 r 重跑上一条命令。
"""

import glob
import os
import shlex
import sys
import unicodedata
from pathlib import Path

import typer
from typer.testing import CliRunner

from tcct import __version__
from tcct.registry import GROUPS

try:
    import readline  # noqa: F401  # Enable editing/history for input().
except ImportError:  # pragma: no cover - Windows may not provide readline.
    readline = None

BANNER = r"""
  _____   ____   ____  _____
 |_   _| / ___| / ___||_   _|
   | |  | |    | |      | |
   | |  | |___ | |___   | |
   |_|   \____| \____|  |_|
"""

_MENU_WIDTH = 62
_RULE = "-" * _MENU_WIDTH


def _width(text: str) -> int:
    """显示宽度：CJK 全角字符按 2 列计。"""
    return sum(2 if unicodedata.east_asian_width(ch) in "WF" else 1 for ch in text)


def _pad(text: str, width: int) -> str:
    return text + " " * max(0, width - _width(text))


def _center(text: str, width: int) -> str:
    gap = max(0, width - _width(text))
    return " " * (gap // 2) + text


def _print_main_menu() -> None:
    print(_RULE)
    print(_center(f"TCCT v{__version__}  理论与计算化学工具箱", _MENU_WIDTH))
    print(_RULE)
    entries = [(key, MENU[key][0]) for key in MENU] + [("0", "Exit")]
    for i in range(0, len(entries), 2):
        line = _pad(f" {entries[i][0]}) {entries[i][1]}", 32)
        if i + 1 < len(entries):
            line += f"{entries[i + 1][0]}) {entries[i + 1][1]}"
        print(line)
    print(_RULE)
    print(" h) 编号与脚本对照    两位数直达    r) 重跑    q/0) 退出")
    print(_RULE)


def _print_submenu(choice: str) -> None:
    name, commands = MENU[choice]
    print(_RULE)
    print(f" [{choice}] {name}  {_GROUP_HELP[choice]}")
    print(_RULE)
    name_width = max((_width(cmd) for cmd, _, _ in commands), default=0)
    for i, (cmd, desc, _) in enumerate(commands, 1):
        print(f" {_pad(f'{i}) {cmd}', name_width + 5)} {desc}")
    print(" 0) 返回")
    print(_RULE)

# 菜单与 CLI 使用同一份注册表，避免新增命令时只更新其中一处。
MENU = {
    group.menu_key: (
        group.display_name,
        [
            (
                command.name,
                command.menu_description,
                list(command.menu_parameters),
            )
            for command in group.commands
        ],
    )
    for group in GROUPS
}
_GROUP_NAME = {group.menu_key: group.cli_name or "" for group in GROUPS}
_GROUP_HELP = {group.menu_key: group.cli_help for group in GROUPS}

DPDATA_INPUT_FORMATS = (
    "deepmd/npy",
    "deepmd/raw",
    "extxyz",
    "gpumd/xyz",
    "vasp/outcar",
    "abacus/lcao/scf",
    "abacus/pw/scf",
    "cp2kdata/md",
)
DPDATA_OUTPUT_FORMATS = (
    "deepmd/npy",
    "deepmd/raw",
    "extxyz",
    "gpumd/xyz",
)


def _path_completer(text: str, state: int):
    """readline 补全回调：补全当前输入的文件/目录名，目录补 "/"。"""
    expanded = os.path.expanduser(text)
    base = os.path.dirname(expanded)
    prefix = os.path.basename(expanded)
    pattern = os.path.join(base, prefix + "*") if base else prefix + "*"
    matches = []
    for match in sorted(glob.glob(pattern)):
        if os.path.isdir(match) and not match.endswith(os.sep):
            match += os.sep
        matches.append(match)
    return matches[state] if state < len(matches) else None


def _set_path_completion(enabled: bool) -> None:
    """只在收集命令参数时开启 Tab 路径补全，菜单选择时不干扰。"""
    if readline is None:  # pragma: no cover - 无 readline 时静默降级
        return
    if enabled:
        readline.set_completer(_path_completer)
        readline.set_completer_delims(" \t\n")
        readline.parse_and_bind("tab: complete")
    else:
        readline.set_completer(None)


def _prompt(text: str, default: str) -> str:
    """提示输入，回车取默认值；输入 q/0 返回 None 表示取消。"""
    try:
        value = input(f"  {text} [{default}]: ").strip()
    except EOFError:
        return None
    if value.lower() in ("q", "0"):
        return None
    return value if value else default


def _prompt_dpdata_format(text: str, default: str, formats: tuple[str, ...]):
    """Select a common dpdata format by number, or accept an exact format name."""
    print(f"  {text}（输入编号或 dpdata 格式名）:")
    for index, name in enumerate(formats, 1):
        print(f"    {index}) {name}")
    try:
        value = input(f"  选择 [{default}]: ").strip()
    except EOFError:
        return None
    if value.lower() in ("q", "0"):
        return None
    if not value:
        return default
    if value.isdigit():
        index = int(value)
        if 1 <= index <= len(formats):
            return formats[index - 1]
        print("  无效编号，请重新输入。")
        return _prompt_dpdata_format(text, default, formats)
    return value


def _execute(app, args: list, display: list) -> None:
    """通过 CliRunner 复用 typer app 执行命令并回显输出。"""
    print(f"\n等价命令: {' '.join(display)}\n{'-' * 50}")
    try:
        runner = CliRunner(mix_stderr=False)  # click < 8.2
    except TypeError:
        runner = CliRunner()  # click >= 8.2 默认分离 stderr
    result = runner.invoke(app, args)
    if result.output:
        print(result.output, end="")
    if result.stderr and result.stderr not in result.output:
        print(result.stderr, end="")
    print(f"{'-' * 50}\n(退出码: {result.exit_code})")


def _run_command(app, group: str, cmd: str, params: list):
    """逐个收集参数，打印等价命令行，再复用 typer app 执行。

    返回 (args, display) 供重跑，取消时返回 None。
    """
    args = [group, cmd] if group else [cmd]
    display = ["tcct", group, cmd] if group else ["tcct", cmd]
    _set_path_completion(True)
    try:
        for name, text, default, is_flag in params:
            if not is_flag and default == ".":
                # 约定大于配置：启动目录即计算目录，不再询问（GPUMDkit 式约定）
                value = default
            elif group == "dpdata" and cmd == "convert" and name in {"--from", "--to"}:
                formats = DPDATA_INPUT_FORMATS if name == "--from" else DPDATA_OUTPUT_FORMATS
                value = _prompt_dpdata_format(text, default, formats)
            else:
                value = _prompt(text, default)
            if is_flag:
                # y/n 类开关：输入 q/0 视为 "否" 并继续执行，而非取消命令
                if value is not None and value.lower() in ("y", "yes"):
                    # registry 里的开关名有些自带 "--" 前缀，有些没有
                    flag = name if name.startswith("--") else f"--{name}"
                    args.append(flag)
                    display.append(flag)
            else:
                if value is None:
                    print("  已取消，返回上级菜单。")
                    return None
                if name == "@args":
                    values = shlex.split(value)
                    args.extend(values)
                    display.extend(values)
                elif name.startswith("--"):
                    args.extend([name, value])
                    display.extend([name, value])
                else:
                    args.append(value)
                    display.append(value)
    finally:
        _set_path_completion(False)

    _execute(app, args, display)
    return args, display


def _script_path(callback) -> str:
    """命令回调所在的源码文件，相对仓库根目录（如 tcct/abacus/check_relax.py）。"""
    module = sys.modules.get(callback.__module__)
    file = getattr(module, "__file__", None)
    if file is None:
        return callback.__module__
    try:
        package_dir = Path(__file__).resolve().parent
        return f"tcct/{Path(file).resolve().relative_to(package_dir)}"
    except ValueError:
        return file


def _print_code_map() -> None:
    """编号与脚本对照页：每个编号对应的命令、说明和源码文件。"""
    print(_RULE)
    print(" 编号与脚本对照（直达码 = 组号+命令号）")
    print(_RULE)
    for group in GROUPS:
        print(f"  [{group.menu_key}] {group.display_name}")
        for i, command in enumerate(group.commands, 1):
            print(f"    {group.menu_key}{i}) {command.name:24s} {command.menu_description}")
            print(f"        {_script_path(command.callback)}")
    print(_RULE)


def _match_direct_code(choice: str):
    """两位数直达码：组号+命令号（如 63 = 第 6 组的第 3 条命令）。"""
    if len(choice) != 2 or choice[0] not in MENU or not choice[1].isdigit():
        return None
    index = int(choice[1])
    commands = MENU[choice[0]][1]
    if 1 <= index <= len(commands):
        return choice[0], index
    return None


def _collect_and_run(app, choice: str, cmd: str, params: list):
    name = MENU[choice][0]
    # 默认为 "." 的参数不询问；全部参数都可跳过时不再打印参数收集头
    if any(is_flag or default != "." for _, _, default, is_flag in params):
        print(f"\n[{name} -> {cmd}] 请依次输入参数（回车使用默认值，q 取消）:")
    return _run_command(app, _GROUP_NAME[choice], cmd, params)


def run_menu(app) -> None:
    """主循环：选软件 -> 选命令 -> 输入参数 -> 执行。"""
    print(BANNER)

    last_invocation = None

    while True:
        _print_main_menu()
        try:
            choice = input("> ").strip().lower()
        except EOFError:
            print("\n再见！")
            return
        if choice in ("0", "q", ""):
            print("再见！")
            return
        if choice in ("h", "?"):
            _print_code_map()
            continue
        if choice == "r":
            if last_invocation is None:
                print("还没有可重跑的命令。\n")
            else:
                _execute(app, *last_invocation)
            continue

        direct = _match_direct_code(choice)
        if direct is None and choice not in MENU:
            print("无效选择，请重新输入。\n")
            continue

        if direct is not None:
            key, index = direct
            cmd, _, params = MENU[key][1][index - 1]
            result = _collect_and_run(app, key, cmd, params)
            if result is not None:
                last_invocation = result
            print()
            continue

        name, commands = MENU[choice]
        _print_submenu(choice)
        try:
            cidx = input("> ").strip().lower()
        except EOFError:
            print("\n再见！")
            return
        if cidx in ("0", "q", ""):
            print()
            continue
        if not cidx.isdigit() or not (1 <= int(cidx) <= len(commands)):
            print("无效选择。\n")
            continue

        cmd, _, params = commands[int(cidx) - 1]
        result = _collect_and_run(app, choice, cmd, params)
        if result is not None:
            last_invocation = result
        print()
