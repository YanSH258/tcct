import json
import numpy as np
import pytest
from ase import Atoms
from ase.io import write
from typer.testing import CliRunner
from tcct.cli import app
from tcct.structure.check_geometry import violations

runner = CliRunner()


def test_periodic_pair_and_nonperiodic():
    a = Atoms('H2', positions=[[0, 0, 0], [3.9, 0, 0]], cell=[4, 4, 4], pbc=True)
    bad = violations(a)
    assert len(bad) == 1
    assert bad[0]['distance_A'] == pytest.approx(0.1)
    a.pbc = False
    assert not violations(a)


def test_self_image_and_strict_threshold():
    a = Atoms('H', cell=[0.2, 4, 4], pbc=[True, False, False])
    assert any(b['i'] == b['j'] for b in violations(a))
    a = Atoms('H2', positions=[[0, 0, 0], [0.31, 0, 0]])
    assert not violations(a, 0.5)
    assert violations(a, 0.7)


def test_invalid_geometry():
    a = Atoms('H', positions=[[np.nan, 0, 0]])
    with pytest.raises(ValueError):
        violations(a)
    with pytest.raises(ValueError):
        violations(Atoms('H', pbc=True))


def test_batch_multiframe_readonly_and_refuse_overwrite(tmp_path):
    source = tmp_path / 'frames.xyz'
    write(source, [Atoms('H2', positions=[[0, 0, 0], [1, 0, 0]]),
                   Atoms('H2', positions=[[0, 0, 0], [0.1, 0, 0]])])
    original = source.read_bytes()
    output = tmp_path / 'audit.json'
    args = ['structure', 'check-geometry', str(tmp_path), '-o', str(output)]
    result = runner.invoke(app, args)
    assert result.exit_code == 2, result.output
    report = json.loads(output.read_text())
    assert report['frames'] == 2
    assert report['failed_frames'] == 1
    assert report['records'][1]['frame'] == 1
    assert source.read_bytes() == original
    before = output.read_bytes()
    assert runner.invoke(app, args).exit_code == 1
    assert output.read_bytes() == before


def test_pass_and_invalid_ratio(tmp_path):
    source = tmp_path / 'POSCAR'
    write(source, Atoms('Al', cell=[4, 4, 4], pbc=True), format='vasp')
    output = tmp_path / 'audit.json'
    args = ['structure', 'check-geometry', str(source), '-o', str(output)]
    assert runner.invoke(app, args + ['--ratio', 'nan']).exit_code == 1
    assert not output.exists()
    result = runner.invoke(app, args)
    assert result.exit_code == 0, result.output
