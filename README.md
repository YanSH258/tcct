# TCCT

**TCCT（Theoretical & Computational Chemistry Tools）：面向理论与计算化学研究的轻量级 workflow + analysis toolkit，用统一 CLI 管理常见科研计算流程。**

TCCT 把平时散落在不同目录里的检查、转换、统计和画图脚本收进一个命令行入口
`tcct`。它不负责安装或替代 ABACUS、CP2K、VASP、DeepMD-kit、GPUMD、DPA4，而是处理这些
软件前后的重复工作。

## 为什么做这个工具

一次完整的计算材料工作通常会经过多个程序：

```text
DFT 计算（ABACUS / CP2K / VASP）
        ↓ 检查与数据提取
训练数据（DeepMD / NEP）
        ↓ 统计、合并与查重
模型训练与验证
        ↓
MD 模拟（GPUMD）
        ↓
结果分析与画图
```

这些步骤本身不复杂，但很容易反复写临时脚本，也容易出现输入约定不同、输出文件名混乱、
漏查未收敛任务等问题。TCCT 只收录实际会重复使用的操作，并为它们提供固定命令、
输入约定和输出格式。

## 主要功能

- 检查 ABACUS 和 CP2K 任务是否结束、是否收敛、标签是否完整；
- 从 ABACUS、CP2K 或 VASP 输出中收集标注，生成 DeepMD NPY；
- 转换 extxyz、DeepMD、CP2K、ABACUS、VASP 等常用格式；
- 在 CIF、Extended XYZ、POSCAR 之间转换，并生成 ABACUS STRU；
- 统计、合并和检查训练数据中的重复结构；
- 整理 GPUMD/NEP 训练数据并分析 NEP 训练结果；
- 使用 DPA4 做结构优化、单点计算和 NEB；
- 用同一套字体、配色和版式生成 PNG 科研图。

## 安装

推荐使用 [uv](https://docs.astral.sh/uv/)：

```bash
git clone git@github.com:YanSH258/tcct.git
cd tcct
uv sync --extra plot --extra dpdata --extra cp2k --extra structure
uv run tcct --help
```

需要在任意目录直接运行 `tcct` 时：

```bash
uv tool install --editable '.[plot,dpdata,cp2k,structure]'
```

也可以安装到现有 Python 3.9+ 环境：

```bash
python -m pip install -e '.[plot,dpdata,cp2k,structure]'
tcct --help
```

TCCT 只安装 Python 依赖。ABACUS、CP2K、DeepMD-kit 和 GPUMD 需要另外安装。
DPA4 需要单独的 deepmd-kit + dftd3 环境，见
[DPA4 说明](tcct/dpa4/README.md)。

## 使用

### 命令行

```bash
tcct --help
tcct doctor
tcct abacus audit ./tasks --strict
tcct abacus report ./tasks
tcct abacus prepare-from-xyz structures.xyz ./abacus_template ./abacus_tasks
tcct abacus to-deepmd ./tasks ./deepmd_data
tcct vasp outcar-to-deepmd ./vasp_tasks ./vasp_data
tcct cp2k singlepoint-to-deepmd ./cp2k_tasks ./cp2k_data
tcct cp2k aimd-to-deepmd ./cp2k_aimd ./cp2k_aimd_data
tcct deepmd split ./deepmd_data/deepmd_npy --test-size 0.1 --seed 42
tcct gpumd npy-to-xyz ./deepmd_data/deepmd_npy train.xyz
tcct deepmd stat ./deepmd_data/deepmd_npy
tcct dpdata overlap train.extxyz test.extxyz
tcct structure convert structure.cif --to stru
tcct gpumd plot-nep-evaluation ./train
```

所有命令都支持 `-h`：

```bash
tcct abacus audit -h
```

安装后可运行 `tcct doctor`，检查可选依赖以及 `ABACUS_PP_PATH`、
`ABACUS_ORB_PATH` 的配置状态；使用 `tcct doctor --json` 可获得机器可读结果。

### 交互菜单

不带参数运行即可进入菜单。菜单最终调用的仍是同一条 CLI 命令。

```bash
tcct
```

收集参数时可用 Tab 补全文件和目录名；默认为当前目录 `.` 的参数不再
询问（在哪个目录启动就在哪个目录计算）；主菜单按 `h` 查看编号与脚本
对照页，支持两位数直达码（组号+命令号，如 `63`）和 `r` 重跑上一条命令。
需要指定其他目录时使用命令行。

### 一个常用流程

```bash
# 1. 大模型 MD 产生带晶胞和 PBC 的 Extended XYZ 后，准备 ABACUS 任务
tcct abacus prepare-from-xyz trajectory.xyz ./abacus_template ./tasks

# 2. ABACUS 计算结束后检查任务
tcct abacus audit ./tasks --strict
tcct abacus report ./tasks

# 3. 提取带能量、力和 virial 的 DeepMD NPY
tcct abacus to-deepmd ./tasks ./deepmd_data

# 4. 审计数据并划分训练集/测试集
tcct deepmd report ./deepmd_data/deepmd_npy
tcct deepmd split ./deepmd_data/deepmd_npy --test-size 0.1 --seed 42

# 5. 检查训练集与测试集是否重复
tcct dpdata overlap train.extxyz test.extxyz

# 6. 训练结束后画 loss 和已有预测结果；独立测试集误差是主要验证证据
tcct gpumd plot-nep-evaluation ./train
```

更多例子见 [常用数据流程](examples/common_data_workflows.md)。

## 支持的模块


| 模块      | 用途                                   |
| ----------- | ---------------------------------------- |
| Structure | 单个结构文件转换                       |
| ABACUS    | XYZ 任务准备、计算检查、报告与数据提取 |
| CP2K      | 计算检查与数据提取                     |
| VASP      | OUTCAR 数据提取                        |
| dpdata    | 带标签数据格式转换与重复检查           |
| DeepMD    | NPY 数据集统计、合并与报告             |
| GPUMD     | train.xyz 准备与 NEP 结果分析          |
| DPA4      | 结构优化、单点计算和 NEB               |
| System    | 环境检查                               |

分类按输入对象确定：Structure 处理不含能量和力的单个周期结构；dpdata 处理带能量、
力或位力的标注数据。ABACUS、CP2K 和 VASP 的原生计算结果需要检查日志、收敛和文件
完整性，因此数据提取命令保留在对应软件模块中；dpdata `convert` 只负责直接格式转换。

## 项目目录

```text
tcct/
├── tcct/        # Python 包
│   ├── cli.py         # CLI 入口
│   ├── menu.py        # 交互菜单
│   ├── registry.py    # CLI 与菜单共用的命令注册表
│   ├── abacus/ cp2k/ vasp/ deepmd/ dpdata/ dpa4/ gpumd/ structure/
│   └── common/        # 共用代码和画图样式
├── tests/             # 测试
├── examples/          # 使用例子
├── workflow/          # 多命令流程脚本
├── knowledge/         # 使用记录和约定
├── AGENTS.md          # 命令路由和开发约定
└── CONTRIBUTING.md    # 添加命令的方法
```

## 文档

- 各模块的输入和输出：`tcct/<module>/README.md`
- 绘图规范：[knowledge/plotting_standard.md](knowledge/plotting_standard.md)
- 添加命令：[CONTRIBUTING.md](CONTRIBUTING.md)
- 版本变化：[CHANGELOG.md](CHANGELOG.md)
- 命令路由：[AGENTS.md](AGENTS.md)

## 参考文档

- [GPUMD documentation](https://gpumd.org/)
- [GPUMDkit](https://github.com/zhyan0603/GPUMDkit)
- [DeePMD-kit documentation](https://docs.deepmodeling.com/projects/deepmd/en/latest/)
- [dpdata documentation](https://docs.deepmodeling.com/projects/dpdata/en/master/)
- [CP2KData dpdata plugin](https://robinzyb.github.io/cp2kdata/docs/dpdata_plugin.html)
- [ABACUS documentation](https://abacus.deepmodeling.com/en/latest/)
- [CP2K manual](https://manual.cp2k.org/)
- [VASP documentation](https://www.vasp.at/wiki/)

## 贡献

添加高频重复使用的命令。具体要求见 [CONTRIBUTING.md](CONTRIBUTING.md)。
