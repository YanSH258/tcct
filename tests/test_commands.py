import json
import tempfile
import unittest
from pathlib import Path

import numpy as np
from typer.testing import CliRunner

from tcct.abacus.audit import discover_tasks, inspect_task, parse_basis_type
from tcct.abacus.check_relax import parse_series
from tcct.cli import app
from tcct.dpa4.common import read_fixed_indices
from tcct.dpa4.batch_relax import read_manifest, safe_case_id
from tcct.dpa4.evaluate import frame_metrics
from tcct.dpdata.overlap import frame_hash
from tcct.cp2k.parser import parse_cp2k_output
from tcct.common.plot_style import (
    COLOR_CYCLE,
    SINGLE_COLUMN_MM,
    apply_plot_style,
    figure_size,
)
from tcct.gpumd.thermo import cell_series, read_time_interval


def write_deepmd(path: Path, x: float, energy: float) -> None:
    import dpdata

    data = {
        "atom_names": ["H"],
        "atom_numbs": [2],
        "atom_types": np.array([0, 0]),
        "cells": np.array([np.eye(3) * 10.0]),
        "coords": np.array([[[0.0, 0.0, 0.0], [x, 0.0, 0.0]]]),
        "energies": np.array([energy]),
        "forces": np.zeros((1, 2, 3)),
        "virials": np.zeros((1, 3, 3)),
        "orig": np.zeros(3),
    }
    dpdata.LabeledSystem(data=data).to("deepmd/npy", str(path))


def command_stderr(result) -> str:
    """Support Click versions that merge stderr into the captured output."""
    try:
        return result.stderr
    except ValueError:
        return result.output


class CommandTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.runner = CliRunner()

    def tearDown(self):
        self.temp.cleanup()

    def test_shared_plot_style(self):
        import matplotlib as mpl

        apply_plot_style()
        width, height = figure_size("single", 0.5)
        self.assertAlmostEqual(width, SINGLE_COLUMN_MM / 25.4)
        self.assertAlmostEqual(height, width * 0.5)
        self.assertEqual(mpl.rcParams["font.family"], ["serif"])
        self.assertEqual(mpl.rcParams["font.serif"][0], "Times New Roman")
        self.assertEqual(
            mpl.rcParams["axes.prop_cycle"].by_key()["color"], COLOR_CYCLE
        )

    def test_abacus_audit_passes_complete_scf(self):
        task = self.root / "task"
        out = task / "OUT.test"
        out.mkdir(parents=True)
        (task / "INPUT").write_text("INPUT_PARAMETERS\ncalculation scf\n")
        (out / "running_scf.log").write_text(
            "charge density convergence is achieved\n"
            "!FINAL_ETOT_IS -1.0 eV\n"
            "TOTAL-FORCE (eV/Angstrom)\n"
            "TOTAL-STRESS (KBAR)\n"
            "Finish Time : now\n"
        )
        result = inspect_task(task)
        self.assertEqual(result["status"], "PASS")
        report = self.root / "audit.csv"
        cli = self.runner.invoke(
            app, ["abacus", "audit", str(task), "-o", str(report), "--strict"]
        )
        self.assertEqual(cli.exit_code, 0, cli.output)
        self.assertTrue(report.is_file())

    def test_abacus_audit_accepts_gpu_scf_marker(self):
        task = self.root / "gpu_task"
        out = task / "OUT.test"
        out.mkdir(parents=True)
        (task / "INPUT").write_text("INPUT_PARAMETERS\ncalculation scf\n")
        (out / "running_scf.log").write_text(
            "#SCF IS CONVERGED#\n"
            "!FINAL_ETOT_IS -1.0 eV\n"
            "TOTAL-FORCE (eV/Angstrom)\n"
            "TOTAL-STRESS (KBAR)\n"
            "Finish Time : now\n"
        )
        result = inspect_task(task)
        self.assertTrue(result["scf_converged"])
        self.assertEqual(result["status"], "PASS")
        cli = self.runner.invoke(
            app,
            ["abacus", "audit", str(task), "-o", str(self.root / "gpu_audit.csv")],
        )
        self.assertEqual(cli.exit_code, 0, cli.output)
        self.assertTrue((self.root / "gpu_audit.csv").is_file())

    def test_abacus_audit_ignores_ionic_not_converged_wording(self):
        task = self.root / "wording_task"
        out = task / "OUT.test"
        out.mkdir(parents=True)
        (task / "INPUT").write_text("INPUT_PARAMETERS\ncalculation scf\n")
        (out / "running_scf.log").write_text(
            "Relaxation is not converged yet!\n"
            "Finish Time : now\n"
        )
        result = inspect_task(task)
        self.assertFalse(result["scf_converged"])
        self.assertEqual(result["status"], "INCOMPLETE")

    def test_abacus_audit_passes_complete_md(self):
        task = self.root / "mdtask"
        out = task / "OUT.test"
        out.mkdir(parents=True)
        (task / "INPUT").write_text("INPUT_PARAMETERS\ncalculation md\nbasis_type pw\n")
        (out / "running_md.log").write_text("Finish Time : now\n")
        result = inspect_task(task)
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(result["calculation"], "md")

    def test_parse_basis_type(self):
        task = self.root / "task"
        task.mkdir()
        (task / "INPUT").write_text("INPUT_PARAMETERS\nbasis_type pw\n")
        self.assertEqual(parse_basis_type(task), "pw")
        self.assertEqual(parse_basis_type(self.root / "missing"), "lcao")

    def test_dpa4_batch_manifest_and_case_id(self):
        manifest = self.root / "structures.csv"
        manifest.write_text("id,input\ncase one,a.xyz\n")
        rows = read_manifest(manifest)
        self.assertEqual(rows[0]["input"], "a.xyz")
        self.assertEqual(safe_case_id(rows[0]["id"]), "case_one")

    def test_dpa4_batch_manifest_requires_input(self):
        manifest = self.root / "bad.csv"
        manifest.write_text("id,path\none,a.xyz\n")
        with self.assertRaises(ValueError):
            read_manifest(manifest)

    def test_dpa4_evaluate_frame_metrics(self):
        result = frame_metrics(
            energy=-4.0,
            forces=np.array([[3.0, 0.0, 0.0], [0.0, 4.0, 0.0]]),
            atom_count=2,
        )
        self.assertAlmostEqual(result["energy_per_atom_eV"], -2.0)
        self.assertAlmostEqual(result["maximum_atomic_force_eV_A"], 4.0)
        self.assertAlmostEqual(
            result["force_component_rms_eV_A"],
            np.sqrt(25.0 / 6.0),
        )

    def test_dpdata_overlap_detects_shared_frame(self):
        from ase import Atoms
        from ase.io import write

        reference = self.root / "reference.extxyz"
        candidate = self.root / "candidate.extxyz"
        shared = Atoms("H2", positions=[[0, 0, 0], [0.7, 0, 0]])
        other = Atoms("H2", positions=[[0, 0, 0], [0.8, 0, 0]])
        write(reference, [shared, other])
        write(candidate, [shared])
        output = self.root / "overlap.json"
        result = self.runner.invoke(
            app,
            [
                "dpdata",
                "overlap",
                str(reference),
                str(candidate),
                "-o",
                str(output),
            ],
        )
        self.assertEqual(result.exit_code, 0, result.output)
        report = json.loads(output.read_text())
        self.assertEqual(report["overlapping_unique_frames"], 1)
        self.assertEqual(report["overlapping_frame_pairs"], 1)

    def test_frame_hash_can_ignore_atom_order(self):
        from ase import Atoms

        first = Atoms("HO", positions=[[0, 0, 0], [1, 0, 0]])
        second = Atoms("OH", positions=[[1, 0, 0], [0, 0, 0]])
        self.assertNotEqual(frame_hash(first), frame_hash(second))
        self.assertEqual(
            frame_hash(first, order_independent=True),
            frame_hash(second, order_independent=True),
        )

    def test_cp2k_audit_parses_complete_single_point(self):
        task = self.root / "task"
        task.mkdir()
        log = task / "output.log"
        log.write_text(
            " CELL| Vector a [angstrom]: 10.0 0.0 0.0\n"
            " CELL| Vector b [angstrom]: 0.0 10.0 0.0\n"
            " CELL| Vector c [angstrom]: 0.0 0.0 10.0\n"
            " *** SCF run converged in 10 steps ***\n"
            " ENERGY| Total FORCE_EVAL ( QS ) energy [hartree] -1.000000\n"
            " FORCES| Atomic forces [hartree/bohr]\n"
            " FORCES| 1 1.0E-3 0.0 0.0 1.0E-3\n"
            " FORCES| 2 -1.0E-3 0.0 0.0 1.0E-3\n"
            " PROGRAM ENDED AT\n"
        )
        parsed = parse_cp2k_output(log)
        self.assertEqual(parsed["status"], "PASS")
        self.assertEqual(parsed["final_force_atoms"], 2)
        output = self.root / "audit.csv"
        result = self.runner.invoke(
            app,
            ["cp2k", "audit", str(task), "-o", str(output), "--strict"],
        )
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertTrue(output.is_file())

    def test_cp2k_parser_accepts_current_energy_and_force_table(self):
        log = self.root / "current_cp2k.log"
        log.write_text(
            " CELL| Vector a [angstrom]: 10.0 0.0 0.0\n"
            " CELL| Vector b [angstrom]: 0.0 10.0 0.0\n"
            " CELL| Vector c [angstrom]: 0.0 0.0 10.0\n"
            " *** SCF run converged in 10 steps ***\n"
            " ENERGY| Total FORCE_EVAL ( QS ) energy [a.u.]: -1.000000\n"
            " ATOMIC FORCES in [a.u.]\n"
            " # Atom Kind Element X Y Z\n"
            " 1 1 H 1.0E-3 0.0 0.0\n"
            " 2 1 H -1.0E-3 0.0 0.0\n"
            " SUM OF ATOMIC FORCES 0.0 0.0 0.0 0.0\n"
            " PROGRAM ENDED AT\n"
        )

        parsed = parse_cp2k_output(log)

        self.assertEqual(parsed["status"], "PASS")
        self.assertEqual(parsed["energy_records"], 1)
        self.assertEqual(parsed["force_blocks"], 1)
        self.assertEqual(parsed["final_force_atoms"], 2)

    def test_cp2k_singlepoint_to_deepmd_exports_npy_only(self):
        task = self.root / "task"
        task.mkdir()
        (task / "structure.xyz").write_text(
            "2\n\nH 0.0 0.0 0.0\nH 0.7 0.0 0.0\n"
        )
        (task / "output.log").write_text(
            " CELL| Vector a [angstrom]: 10.0 0.0 0.0\n"
            " CELL| Vector b [angstrom]: 0.0 10.0 0.0\n"
            " CELL| Vector c [angstrom]: 0.0 0.0 10.0\n"
            " *** SCF run converged in 10 steps ***\n"
            " ENERGY| Total FORCE_EVAL ( QS ) energy [hartree] -1.000000\n"
            " FORCES| Atomic forces [hartree/bohr]\n"
            " FORCES| 1 1.0E-3 0.0 0.0 1.0E-3\n"
            " FORCES| 2 -1.0E-3 0.0 0.0 1.0E-3\n"
            " PROGRAM ENDED AT\n"
        )
        output = self.root / "dataset"
        result = self.runner.invoke(
            app,
            ["cp2k", "singlepoint-to-deepmd", str(task), str(output), "--expected", "1"],
        )
        self.assertEqual(result.exit_code, 0, result.output)
        summary = json.loads((output / "reports" / "summary.json").read_text())
        self.assertEqual(summary["frames"], 1)
        self.assertTrue(summary["all_systems_validated"])
        self.assertTrue((output / "deepmd_npy" / "H2" / "type.raw").is_file())
        self.assertFalse((output / "extxyz").exists())

    def test_cp2k_singlepoint_to_deepmd_preserves_existing_output(self):
        output = self.root / "existing"
        output.mkdir()
        marker = output / "keep.txt"
        marker.write_text("keep")
        result = self.runner.invoke(
            app,
            ["cp2k", "singlepoint-to-deepmd", str(self.root), str(output)],
        )
        self.assertEqual(result.exit_code, 1, result.output)
        self.assertEqual(marker.read_text(), "keep")

    def test_discover_tasks_skips_out_hap_input(self):
        task = self.root / "task"
        out = task / "OUT.test"
        out.mkdir(parents=True)
        (task / "INPUT").write_text("INPUT_PARAMETERS\ncalculation scf\n")
        (out / "INPUT").write_text("INPUT_PARAMETERS\ncalculation scf\n")
        tasks = discover_tasks(self.root, "**/INPUT")
        self.assertEqual(tasks, [task])

    def test_check_relax_reports_concise_convergence(self):
        task = self.root / "relax_task"
        task.mkdir()
        log = task / "running_relax.log"
        log.write_text(
            "STEP OF RELAXATION : 1\n"
            "final etot is -2.0 eV\n"
            "Largest gradient in force is 0.2 eV/A.\n"
            "Relaxation is not converged yet!\n"
            "STEP OF RELAXATION : 2\n"
            "final etot is -2.1 eV\n"
            "Largest gradient in force is 0.02 eV/A.\n"
            "Relaxation is converged!\n"
        )
        result = self.runner.invoke(
            app, ["abacus", "check-relax", str(task)]
        )
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn("Relaxation is converged!", result.output)
        self.assertNotIn("Relaxation is not converged yet!", result.output)
        self.assertIn("离子步数: 最后一步为第 2 步", result.output)
        self.assertIn("提取数值: 0.02", result.output)

    def test_check_relax_can_plot_convergence(self):
        task = self.root / "relax_plot"
        task.mkdir()
        (task / "running_cell-relax.log").write_text(
            "STEP OF RELAXATION : 1\n"
            "final etot is -2.0 eV\n"
            "Largest gradient in force is 0.2\n"
            "Largest gradient in stress is 1.2\n"
            "STEP OF RELAXATION : 2\n"
            "final etot is -2.1 eV\n"
            "Largest gradient in force is 0.02\n"
            "Largest gradient in stress is 0.3\n"
            "Relaxation is converged\n"
        )
        result = self.runner.invoke(
            app, ["abacus", "check-relax", str(task), "--plot"]
        )
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertTrue((task / "abacus_relax_convergence.png").is_file())
        self.assertIn("收敛曲线:", result.output)

    def test_parse_convergence_series(self):
        log = self.root / "running_relax.log"
        log.write_text(
            "final etot is -2.0 eV\n"
            "Largest gradient in force is 0.2\n"
            "Largest gradient in stress is 1.2\n"
            "final etot is -2.1 eV\n"
            "Largest gradient in force is 0.02\n"
            "Relaxation is converged\n"
        )
        result = parse_series(log)
        self.assertEqual(result["energy"], [-2.0, -2.1])
        self.assertEqual(result["force"], [0.2, 0.02])
        self.assertTrue(result["converged"])

    def test_merge_and_convert(self):
        first = self.root / "first" / "H2"
        second = self.root / "second" / "H2"
        write_deepmd(first, 0.7, -1.0)
        write_deepmd(second, 0.8, -0.9)
        merged = self.root / "merged"
        result = self.runner.invoke(
            app,
            [
                "deepmd",
                "merge",
                str(first.parent),
                str(second.parent),
                "--output",
                str(merged),
            ],
        )
        self.assertEqual(result.exit_code, 0, result.output)
        summary = json.loads((merged / "reports" / "summary.json").read_text())
        self.assertEqual(summary["frames"], 2)
        self.assertEqual(summary["duplicate_frames"], 0)
        xyz = self.root / "merged.xyz"
        result = self.runner.invoke(
            app,
            [
                "dpdata",
                "convert",
                str(merged / "deepmd_npy" / "H2"),
                str(xyz),
                "--from",
                "deepmd/npy",
                "--to",
                "extxyz",
                "--virial",
            ],
        )
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertTrue(xyz.is_file())

    def test_merge_rejects_duplicate_frame(self):
        first = self.root / "first" / "H2"
        second = self.root / "second" / "H2"
        write_deepmd(first, 0.7, -1.0)
        write_deepmd(second, 0.7, -1.0)
        output = self.root / "merged"
        result = self.runner.invoke(
            app,
            [
                "deepmd",
                "merge",
                str(first.parent),
                str(second.parent),
                "--output",
                str(output),
            ],
        )
        self.assertEqual(result.exit_code, 2, result.output)
        self.assertTrue((output / "duplicate_frames.csv").is_file())

    def test_xyz_to_deepmd_writes_raw_and_npy_when_requested(self):
        xyz = self.root / "train.xyz"
        xyz.write_text(
            "2\n"
            'Lattice="10 0 0 0 10 0 0 0 10" '
            "Properties=species:S:1:pos:R:3:force:R:3 "
            'energy=-1.0 virial="0 0 0 0 0 0 0 0 0" pbc="T T T"\n'
            "H 0 0 0 0 0 0\n"
            "H 0.7 0 0 0 0 0\n"
        )
        output = self.root / "deepmd"
        result = self.runner.invoke(
            app,
            ["dpdata", "xyz-to-deepmd", str(xyz), str(output), "--set-size", "1", "--raw"],
        )
        self.assertEqual(result.exit_code, 0, result.output)
        summary = json.loads(result.output)
        self.assertEqual(summary["systems"], 1)
        self.assertEqual(summary["frames"], 1)
        self.assertEqual(summary["formats"], ["deepmd/npy", "deepmd/raw"])
        systems = [path for path in output.iterdir() if path.is_dir()]
        self.assertEqual(len(systems), 1)
        self.assertTrue((systems[0] / "coord.raw").is_file())
        self.assertTrue((systems[0] / "set.000" / "coord.npy").is_file())

    def test_xyz_to_deepmd_rejects_nonempty_output(self):
        xyz = self.root / "train.xyz"
        xyz.write_text("not parsed")
        output = self.root / "deepmd"
        output.mkdir()
        (output / "keep").write_text("do not overwrite")
        result = self.runner.invoke(
            app, ["dpdata", "xyz-to-deepmd", str(xyz), str(output)]
        )
        self.assertEqual(result.exit_code, 1, result.output)
        self.assertIn("输出路径已存在且非空", command_stderr(result))

    def test_gpumd_merge_loss_offsets_restart_steps(self):
        first = self.root / "loss.out"
        restart = self.root / "restart_loss.out"
        output = self.root / "loss_merged.out"
        first.write_text("100 1.0 0.5\n200 0.8 0.4\n")
        restart.write_text("100 0.7 0.3\n200 0.6 0.2\n")
        result = self.runner.invoke(
            app,
            [
                "gpumd",
                "merge-loss",
                str(first),
                str(restart),
                "--output",
                str(output),
            ],
        )
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertEqual(
            output.read_text().splitlines(),
            [
                "100 1.0 0.5",
                "200 0.8 0.4",
                "300 0.7 0.3",
                "400 0.6 0.2",
            ],
        )

    def test_gpumd_merge_loss_rejects_existing_output(self):
        first = self.root / "loss.out"
        restart = self.root / "restart_loss.out"
        output = self.root / "loss_merged.out"
        first.write_text("100 1.0\n")
        restart.write_text("100 0.8\n")
        output.write_text("keep\n")
        result = self.runner.invoke(
            app,
            [
                "gpumd",
                "merge-loss",
                str(first),
                str(restart),
                "--output",
                str(output),
            ],
        )
        self.assertEqual(result.exit_code, 1, result.output)
        self.assertEqual(output.read_text(), "keep\n")

    def test_gpumd_thermo_plot_matches_gpumd_layout(self):
        run_in = self.root / "run.in"
        run_in.write_text("time_step 2\ndump_thermo 50\n")
        self.assertAlmostEqual(read_time_interval(run_in), 0.1)

        data = np.array(
            [
                [300, 1, -5, 0.1, 0.2, 0.3, 0, 0, 0, 10, 11, 12],
                [310, 2, -6, 0.2, 0.3, 0.4, 0, 0, 0, 10.1, 11.1, 12.1],
            ],
            dtype=float,
        )
        thermo_file = self.root / "thermo.out"
        np.savetxt(thermo_file, data)
        cell = cell_series(data)
        self.assertAlmostEqual(cell["volume"][0], 1320.0)

        plot = self.root / "thermo.png"
        averages = self.root / "thermo_averages.txt"
        result = self.runner.invoke(
            app,
            [
                "gpumd",
                "thermo",
                str(thermo_file),
                "--plot",
                "--run-in",
                str(run_in),
                "--output",
                str(plot),
                "--averages",
                str(averages),
            ],
        )
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertTrue(plot.is_file())
        self.assertIn("Temperature: 310", averages.read_text())

    def test_gpumd_thermo_default_outputs_follow_input_directory(self):
        data_dir = self.root / "gpumd_run"
        data_dir.mkdir()
        thermo_file = data_dir / "thermo.out"
        np.savetxt(
            thermo_file,
            np.array(
                (
                    [300, 1, -5, 0.1, 0.2, 0.3, 0, 0, 0, 10, 11, 12],
                    [310, 2, -6, 0.2, 0.3, 0.4, 0, 0, 0, 10.1, 11.1, 12.1],
                ),
                dtype=float,
            ),
        )

        result = self.runner.invoke(
            app,
            ["gpumd", "thermo", str(thermo_file), "--plot"],
        )

        self.assertEqual(result.exit_code, 0, result.output)
        self.assertTrue((data_dir / "thermo.png").is_file())
        self.assertTrue((data_dir / "thermo_averages.txt").is_file())
        self.assertFalse((self.root / "thermo.png").exists())
        self.assertIn(str(data_dir / "thermo.png"), result.output)

    def test_dpa4_fixed_indices_are_one_based(self):
        indices = self.root / "fixed.txt"
        indices.write_text("1 3 5\n")
        self.assertEqual(read_fixed_indices(indices, 5), [0, 2, 4])

    def test_dpa4_relax_rejects_missing_input(self):
        result = self.runner.invoke(
            app,
            ["dpa4", "relax", str(self.root / "missing.xyz")],
        )
        self.assertEqual(result.exit_code, 1, result.output)
        self.assertIn("输入结构不存在", command_stderr(result))

    def test_dpa4_neb_rejects_missing_endpoint(self):
        result = self.runner.invoke(
            app,
            [
                "dpa4",
                "neb",
                str(self.root / "missing_initial.xyz"),
                str(self.root / "missing_final.xyz"),
            ],
        )
        self.assertEqual(result.exit_code, 1, result.output)
        self.assertIn("初态结构不存在", command_stderr(result))


if __name__ == "__main__":
    unittest.main()
