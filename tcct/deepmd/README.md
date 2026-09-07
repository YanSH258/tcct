# DeePMD

DeePMD raw/npy 数据集的统计与合并。每个命令的详细参数见 `tcct deepmd <命令> -h`。

## `tcct deepmd report DATASET_PATH`

- 输入：DeepMD NPY 数据集。每个 system 需要 `type.raw`、一个或多个 `set.*`，
  set 中需要 `coord.npy` 和 `box.npy`；`energy.npy`、`force.npy`、`virial.npy`
  可以缺失并会如实记录。`type_map.raw` 可选。
- 输出：默认写入新的 `deepmd_report/` 目录，包括 `report.html`、`report.json`、
  `systems.csv`、`duplicates.csv` 和三张 PNG 图。
- 统计：总能、每原子能量、同组成相对能量、力分量、原子力模长、逐帧最大原子力、
  组成分布和 exact normalized duplicate；使用 `--minimum-distance` 时增加 PBC 下的
  逐帧/逐元素对最小原子距离。
- `--force-threshold VALUE` 只统计超过阈值的原子数，不据此评价数据质量。
- `--minimum-distance` 对全部帧计算最小距离；默认关闭，避免大型数据集的报告明显变慢。
- `--minimum-distance-threshold VALUE` 会自动开启最小距离检查，只统计低于阈值的帧数，
  不自动删除结构，也不据此评价数据质量。
- 重复帧按元素、PBC、晶胞和坐标在 6 位小数归一化后判断；不做近似结构或 RMSD 聚类。
- 输出目录非空、必需结构数组缺失或数组形状不一致时退出码非零。

示例：

```bash
tcct deepmd report ./dataset
tcct deepmd report ./dataset --output audit_2026_07 \
  --force-threshold 10 --minimum-distance --minimum-distance-threshold 0.8
```

## `tcct deepmd split DATASET`

- 输入：一个 DeepMD NPY system，或递归包含多个 system 的数据集根目录；所有帧必须有
  有限的晶胞、坐标、energy 和 force。`--virial` 可强制要求 virial。
- 方法：`random`（默认，默认 seed 为 42）或 `uniform`。`--test-size 0.1` 表示比例，
  `--test-size 100` 表示准确帧数。选择发生在按路径和帧号排列的全数据集帧序列上。
- 输出：默认新建 `deepmd_split/`，其中 `train/` 和 `test/` 保留原 system 边界；
  `frame_manifest.csv` 记录每一帧的来源和去向，`systems.csv` 记录各输出 system，
  `summary.json` 保存方法、seed、帧数和依赖版本，`SHA256SUMS.csv` 保存文件校验值。
- 验证：所有输出 system 都以 `deepmd/npy` 重新读取，核对帧数、type map、晶胞、
  坐标、能量、力和已有 virial。输出目录非空时拒绝覆盖。

```bash
tcct deepmd split ./dataset --test-size 0.1 --method random --seed 42
tcct deepmd split ./dataset -o split_uniform --test-size 100 --method uniform
```

## `tcct deepmd stat [DIR]`（默认当前目录）
- 输入：DeePMD raw/npy 数据集。DIR 下每个子目录是一个 system（含 `type.raw` +
  `set.*/{coord,energy,force,box}.npy`，可选 `type_map.raw`）；DIR 本身是单个 system 也兼容。
- 输出（stdout）：system 数量、每个 system 的 frame 数与原子数、各元素原子计数
  （有 type_map.raw 时显示元素符号）、能量范围、力分量绝对值范围；`--json` 输出 JSON。
- 找不到数据：stderr 报错，退出码 1。仅依赖 numpy，不依赖 dpdata。

## `tcct deepmd merge INPUT... --output DIR`
- 输入：两个或多个 DeepMD NPY 数据集。
- 按精确化学组成合并，并统一 type map。
- 默认拒绝重复的 cell+coord+atom-type 帧。

## `tcct deepmd plot-parity [DIR]`（默认当前目录）
- 输入：`dp test` 生成的 `detail.*.out` 数值表。对多 system 测试时每个 system
  块前的 `#` 注释头（随数据拼接）会自动跳过。只画存在的文件，互不依赖：
  `detail.e_peratom.out`（2 列）、`detail.f.out`（6 列，逐原子力）、
  `detail.v_peratom.out`（18 列，9 分量合并）、`detail.s.out`（18 列，
  eV/Å³ 换算为 GPa）。
- 输出：默认在 DIR 写 `deepmd_parity.png`（每性质一个"预测 vs DFT"对角线
  面板，最多 2×2；点数 ≥100000 自动改用二维密度图）和
  `deepmd_parity_metrics.json`（逐性质 RMSE/MAE/R² 与点数）。stdout 汇报
  各性质 RMSE。能量/virial 指标以 meV/atom、力以 meV/Å、应力以 GPa 显示。
- 边界：总能量 `detail.e.out` 与总 virial `detail.v.out` 不参与绘图（绝对量
  受体系能量基准主导，逐原子量才跨体系可比）；不做按 system 拆分，多 system
  结果合并统计；输出文件已存在时拒绝覆盖（退出码 1），目录中没有任何
  detail 文件时退出码 2。

```bash
cd stage26 && tcct deepmd plot-parity
tcct deepmd plot-parity ./dp_test_out -o parity_v2.png
```

## 依赖

`stat` 仅依赖 numpy；`report` 需要 matplotlib 和 ASE（均延迟导入）；`merge` 和
`split` 需要 dpdata（延迟导入）；`plot-parity` 需要 matplotlib（延迟导入）。
