"""Read-only covalent-radius geometry screening, including periodic self images."""
from pathlib import Path
from typing import Optional
import json

import numpy as np
import typer


def violations(atoms, ratio=0.7):
    """Return close pairs (zero-based indices and lattice image offsets)."""
    from ase.data import covalent_radii
    from ase.neighborlist import neighbor_list

    if not np.isfinite(ratio) or ratio <= 0:
        raise ValueError("ratio 必须为有限正数")
    if not len(atoms):
        raise ValueError("结构没有原子")
    if not np.isfinite(atoms.positions).all() or not np.isfinite(atoms.cell.array).all():
        raise ValueError("坐标或晶胞包含非有限数值")
    if atoms.pbc.any() and np.linalg.matrix_rank(atoms.cell.array[atoms.pbc]) < int(atoms.pbc.sum()):
        raise ValueError("周期方向晶胞向量退化或缺失")
    if np.any(atoms.numbers == 0):
        raise ValueError("未知元素没有可用共价半径")
    radii = covalent_radii[atoms.numbers]
    i, j, distances, shifts = neighbor_list(
        'ijdS', atoms, float(2 * ratio * radii.max() + 1e-6), self_interaction=False
    )
    result = []
    for a, b, distance, shift in zip(i, j, distances, shifts):
        # Keep one orientation of each pair, including self-image pairs.
        if a > b or (a == b and tuple(shift) <= (0, 0, 0)):
            continue
        threshold = ratio * (radii[a] + radii[b])
        if distance < threshold:
            result.append(dict(i=int(a), j=int(b), elements=[atoms[a].symbol, atoms[b].symbol],
                               image=shift.tolist(), distance_A=float(distance), threshold_A=float(threshold)))
    return result


def check_geometry(
    input: Path = typer.Argument(Path('.'), help="结构文件或目录；目录默认递归检查常见结构文件"),
    ratio: float = typer.Option(0.7, '--ratio', help="拒绝 d < ratio × 共价半径和"),
    pattern: Optional[str] = typer.Option(None, '--pattern', help="目录 glob，例如 '**/*.xyz'"),
    format: Optional[str] = typer.Option(None, '--format', help="ASE 输入格式，例如 extxyz 或 vasp"),
    output: Path = typer.Option(Path('geometry_check.json'), '--output', '-o', help="JSON 报告，拒绝覆盖"),
):
    """检查单帧、多帧或目录中的过近原子，写入 geometry_check.json。

    示例：tcct structure check-geometry trajectory.xyz --ratio 0.7
    输入通过 ASE 读取；CIF 使用已有空间群展开读取器。报告逐文件、逐帧记录
    异常原子对、周期像、距离与阈值；原子和帧均从 0 编号，不修改输入。
    退出码：0 全部通过，1 输入/输出错误，2 检测到过近原子。
    """
    try:
        from tcct.structure.convert import _require_ase, read_single_cif
        _require_ase()
        from ase.io import iread
        if not np.isfinite(ratio) or ratio <= 0:
            raise ValueError('ratio 必须为有限正数')
        if output.exists():
            raise ValueError(f'拒绝覆盖已有报告：{output}')
        if input.is_file():
            paths = [input]
        elif input.is_dir():
            paths = sorted(p for p in input.glob(pattern or '**/*') if p.is_file() and
                           (pattern is not None or p.suffix.lower() in {'.xyz', '.extxyz', '.cif', '.vasp'}
                            or p.name in {'POSCAR', 'CONTCAR'}))
        else:
            raise ValueError(f'输入不存在：{input}')
        if not paths:
            raise ValueError('没有找到结构文件')
        records = []
        for path in paths:
            fmt = format or ('vasp' if path.name in {'POSCAR', 'CONTCAR'} else None)
            frames = [read_single_cif(path)] if (fmt == 'cif' or (fmt is None and path.suffix.lower() == '.cif')) else iread(path, index=':', format=fmt)
            count = 0
            for frame, atoms in enumerate(frames):
                count += 1
                bad = violations(atoms, ratio)
                records.append(dict(path=str(path.resolve()), frame=frame, natoms=len(atoms),
                                    pbc=atoms.pbc.tolist(), valid=not bad, violations=bad))
            if not count:
                raise ValueError(f'文件没有结构帧：{path}')
        failed = sum(not r['valid'] for r in records)
        report = dict(ratio=ratio, index_base=0, frames=len(records), failed_frames=failed, records=records)
        with output.open('x', encoding='utf-8') as stream:
            json.dump(report, stream, ensure_ascii=False, indent=2)
            stream.write('\n')
    except Exception as exc:
        typer.echo(f'几何检查失败：{exc}', err=True)
        raise typer.Exit(1)
    typer.echo(f"检查 {len(records)} 帧，异常 {failed} 帧；报告：{output}")
    if failed:
        raise typer.Exit(2)
