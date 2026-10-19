# structure

单个周期结构的轻量级格式转换。pymatgen 负责可靠展开 CIF 空间群，ASE/dpdata
负责读取和输出 CIF、Extended XYZ、VASP POSCAR 或 ABACUS STRU。

## `tcct structure convert INPUT --to FORMAT`

- 输入：单结构 CIF、POSCAR，或包含完整 `Lattice` 和 `pbc` 的 Extended XYZ。
  文件名无法识别时可用 `--from cif|poscar|extxyz` 明确指定。普通 XYZ 没有周期晶胞，
  不能用于这里的周期结构转换。
- `--to cif`：输出 `<文件名>.cif`。
- `--to xyz`：输出 `<文件名>.xyz`，实际内容为包含 `Lattice` 和 `pbc` 的
  Extended XYZ。
- `--to poscar`：输出 `<文件名>.vasp`，采用 VASP POSCAR 格式和分数坐标。
- `--to stru`：输出 `<文件名>.STRU`。默认从 `ABACUS_PP_PATH` 按
  `element.json` 查找赝势；没有映射文件时只接受每个元素唯一匹配的 `.upf`。
- `--basis lcao`：除赝势外，从 `ABACUS_ORB_PATH` 查找配套 `.orb`；默认 `pw`
  不写 `NUMERICAL_ORBITAL`。
- `--pp-dir` / `--orb-dir`：临时切换资源库，不修改全局配置。
- STRU 默认直接写入赝势和轨道的绝对路径，不创建软链接，也不生成 `INPUT`。
- `--output/-o`：覆盖默认输出文件名。已有文件不会覆盖。
- 默认只打印输出路径和校验摘要；`--json` 输出完整校验、赝势和轨道文件记录。

每次转换完成后都会重新读取输出，核对元素、原子数、PBC、晶格度量、体积和分数坐标。
多帧输入、部分占位 CIF、缺失/歧义赝势以及回读不一致都会以非零退出码停止。

```bash
tcct structure convert Al.cif --to xyz
tcct structure convert Al.cif --to poscar --output POSCAR
tcct structure convert Al.cif --to stru --output STRU
tcct structure convert Al.cif --to stru --basis lcao
tcct structure convert POSCAR --to xyz
tcct structure convert frame.extxyz --to stru
```

格式转换不会判断某套赝势是否适合具体研究。续接已有计算或机器学习数据时，应使用原项目
完全相同的赝势文件；使用 `--json` 可记录文件名和 SHA-256。

## `tcct structure check-geometry [INPUT]`

只读检查 `d < ratio × (r_cov_i + r_cov_j)`，默认 ratio=0.7。沿用表面催化项目
geometry_filter.py 的 ASE 邻居表判据，包括周期自身镜像，遵循输入 PBC。
普通 XYZ 按非周期结构检查；几何通过不代表能量稳定。

- 输入默认当前目录，支持 ASE 可读的单帧/多帧文件；目录递归发现
  `.xyz/.extxyz/.cif/.vasp`、`POSCAR/CONTCAR`。
- `--pattern` 指定目录 glob，`--format` 指定 ASE 格式；CIF 复用现有 pymatgen
  空间群展开读取器。依赖：`pip install 'tcct[structure]'`。
- `--ratio` 必须为有限正数。`--output/-o` 默认当前目录 `geometry_check.json`，拒绝覆盖。
- JSON 记录源文件、帧号、原子数、PBC、异常原子对、周期像偏移、距离和阈值（Å）。
  帧号和原子索引从 0 开始。不修改输入；读取失败不生成部分报告。
- 退出码：0 全部通过，1 参数/读写错误，2 发现过近原子。

```bash
tcct structure check-geometry trajectory.xyz
tcct structure check-geometry structures/ --ratio 0.7
tcct structure check-geometry structures/ --pattern '**/*.extxyz' -o audit.json
```
