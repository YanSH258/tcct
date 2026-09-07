# ABACUS

ABACUS 任务的输入准备、批量审计、收敛分析与数据提取。每个命令的详细参数见
`tcct abacus <命令> -h`。

## `tcct abacus check-relax [DIR]`（默认当前目录）
- 输入：DIR 下的 `running_relax.log` 或 `running_cell-relax.log`，也支持位于 `OUT.*/`。
- 输出（stdout）：日志路径；是否发现收敛标记（列出匹配行）；最后一步离子步序号；
  总能（匹配 `final etot` / `!FINAL` 行，找不到会明说"未找到总能行"）；最大力。
- `--plot`：同时绘制能量、最大力和已有最大应力随离子步的收敛曲线，默认写到
  `DIR/abacus_relax_convergence.png`；`--output` 可指定其他图片路径。
- 日志不存在：stderr 报错，退出码 1。

## `tcct abacus audit [ROOT]`
- 输入：ROOT 下由 `INPUT` 标识的 ABACUS 任务目录。
- 判断：正常结束、SCF/结构收敛（SCF 收敛标记兼容 CPU 与 GPU 构建）、最终能量、力和应力证据。
- 输出：`abacus_audit.csv` 和 `abacus_audit.json`。
- `--strict`：存在未完成任务时返回退出码 2。

## `tcct abacus prepare-from-xyz SOURCE TEMPLATE [OUTPUT]`

- 输入：一个多帧 Extended XYZ，或包含多个 `.xyz`/`.extxyz` 文件的目录；每一帧
  必须包含有限坐标、有效晶胞和三维 PBC，普通 XYZ 会被拒绝。
- 模板：`TEMPLATE/INPUT` 和 `TEMPLATE/KPT`。计算参数不修改，只将每个任务的
  `suffix` 设为唯一值；INPUT 必须明确包含 `calculation` 和 `basis_type`。
- STRU：复用 `structure convert` 的写出与回读校验，赝势使用 `ABACUS_PP_PATH`；
  LCAO 轨道使用 `ABACUS_ORB_PATH`，并在 STRU 中写入绝对路径。
- 输出：默认 `abacus_tasks/`，包含 `tasks/task_000001/INPUT|KPT|STRU`、
  `task_manifest.csv`、`task_list.txt`、`summary.json` 和 `SHA256SUMS.csv`。
- 边界：不生成提交脚本、不提交任务、不覆盖已有输出目录；XYZ 中的能量、力和
  virial 标签不会写入 ABACUS 输入。

```bash
tcct abacus prepare-from-xyz structures.xyz template abacus_tasks
tcct abacus prepare-from-xyz xyz_files/ template abacus_tasks
```

## `tcct abacus report [ROOT]`
- 复用 `audit` 的任务发现、完成证据和状态判断，以及 `check-relax` 的能量、
  最大力和最大应力解析，不另写 ABACUS 日志解析器。
- 输出目录默认为 `abacus_report/`，包含 `report.html`、`report.json`、`jobs.csv`、
  `failed_jobs.csv` 和 `figures/` 下的任务状态与 relax 指标 PNG。
- `--expected`：记录并检查预期任务数；`--strict`：报告生成后，存在未完成任务或
  任务数不符时返回退出码 2。
- 提示只陈述缺少日志、完成证据不完整、任务数不符等事实，不判断计算质量。

## `tcct abacus to-deepmd ROOT OUTPUT`
- 输入：一批已完成的 ABACUS SCF、relax、cell-relax 或 MD 任务。
- 解析：自动读取 `INPUT` 中的 `calculation` 与 `basis_type`，选择 dpdata 官方的
  `abacus/{lcao,pw}/{scf,relax,md}` 格式，不使用模糊的通用解析模式。
- 输出：`deepmd_npy/<exact_formula>/`、逐任务审计、逐帧 manifest、汇总和 SHA256。
- 默认要求 virial；不接受缺失标签，不覆盖非空输出目录。

## 依赖

- 硬依赖：仅 typer + numpy。
- `check-relax --plot`：matplotlib（延迟导入）。
- `report`：matplotlib（延迟导入）。
- `to-deepmd`：dpdata（延迟导入）。
