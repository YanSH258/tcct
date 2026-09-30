# Changelog

## 0.4.1 — 2026-09-30

### 新增

- 收集菜单参数时支持 Tab 补全文件和目录名（目录自动补 `/`）。
- 主菜单支持两位数直达码（组号+命令号，如 `63` = DeepMD 菜单第 3 条
  `merge`）和 `r` 重跑上一条命令。
- 菜单不再询问默认为当前目录 `.` 的参数：在哪个目录启动就在哪个目录
  计算（GPUMDkit 式约定）；需要指定其他目录时使用命令行。
- 主菜单按 `h` 查看编号与脚本对照页：每个编号（含两位直达码）对应的
  命令、说明和源码文件路径。

### 调整

- 主菜单与子菜单改为 GPUMDkit/VASPKIT 式的横线框式版式：主菜单双列
  编号、居中版本页眉和快捷键页脚，中文按全角字符宽度对齐。

### 修复

- 菜单执行带 `--` 前缀声明的 y/n 开关（如 `abacus to-deepmd` 的
  `--strict`）时会拼出 `----strict` 导致命令失败。

### 验证

- 快速测试：109 项通过，5 项真实样例集成测试按约定跳过。

## 0.4.0 — 2026-08-01

### 新增

- `tcct abacus prepare-from-xyz`：将多帧 Extended XYZ 或目录中的多个 XYZ 文件
  按帧生成独立的 ABACUS `INPUT/KPT/STRU` 任务，并输出 manifest 和校验值。
- `tcct gpumd plot-nep-evaluation`：分别统计和绘制 NEP 训练集、独立测试集的
  energy/force/stress 或 virial 预测误差，并对大数据自动使用密度图。
- `tcct deepmd split`：使用固定 seed 的 random 或 uniform 方法划分 DeepMD NPY，
  输出逐帧 manifest、校验值并进行 NPY 回读验证。
- DeepMD 数据集报告可选全帧 PBC 最小原子距离、逐元素对最小距离和阈值计数；
  大型数据集默认不运行该耗时检查。
- `tcct cp2k aimd-to-deepmd`：使用 dpdata + CP2KData 将原生 CP2K AIMD
  位置、力、能量、晶胞和可用位力转换为经过回读验证的 DeepMD NPY。
- `tcct doctor`：检查 TCCT 版本、可选依赖和 ABACUS 赝势/轨道目录。
- `tcct abacus report`：输出 ABACUS 批量任务的 HTML、JSON、CSV 和 PNG 报告。
- Structure 转换支持 CIF、POSCAR、Extended XYZ 输入，并可输出 CIF、POSCAR、
  Extended XYZ 或带资源绝对路径的 ABACUS STRU。
- GitHub Actions 自动测试 Python 3.9/3.12、CLI 入口、源码包和 wheel。
- ABACUS、CP2K、VASP、DeepMD 的仓库外真实样例回归测试入口。

### 调整

- `tcct abacus check-relax --plot` 合并结构优化检查和收敛作图，移除重复的
  `plot-convergence` 菜单项。
- 交互菜单按“准备输入 → 检查/报告 → 提取数据 → 数据审计”的常用流程重排
  ABACUS、DeepMD 和 GPUMD 子命令编号。
- `tcct gpumd plot-nep-evaluation` 改为自动扫描 `loss.out` 及已有的 train/test
  energy、force、stress 和 virial 文件，替代重复的 `plot-nep-training` 命令。
- CLI 与交互菜单改为共用一个命令注册表。
- ABACUS 审计会列出缺少的完成证据，不再只写笼统的“完成证据不完整”。
- 主菜单按 Structure、ABACUS、CP2K、VASP、dpdata、DeepMD、GPUMD、DPA4、System
  排列，并直接显示每个模块的用途。
- `tcct cp2k collect` 改为 `tcct cp2k singlepoint-to-deepmd`，只输出 DeepMD NPY。
- `tcct vasp to-deepmd` 改为 `tcct vasp outcar-to-deepmd`。
- `tcct gpumd from-deepmd` 改为 `tcct gpumd npy-to-xyz`。
- 交互式 `dpdata convert` 可通过编号选择常用格式。
- CP2KData 改为默认依赖，普通 `uv sync` 即可使用 CP2K AIMD 转换。

### 验证

- 快速测试：74 项通过。
- 真实样例：ABACUS 报告、4 个 CP2K 单点审计、CP2K AIMD 转 DeepMD、VASP OUTCAR
  转 DeepMD、DeepMD 数据集报告全部通过。
