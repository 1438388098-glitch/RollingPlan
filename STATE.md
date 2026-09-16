# RollingPlan — 当前工作状态

> **最后更新**：2026-09-16 19:35
> **相关目录**：`D:\0-task\rollingplan`（验收副本） / `D:\0_git\RollingPlan`（git 仓库）
> **代码最新在**：分支 `autopilot/348240aadc58`（HEAD = `aa2267a`）—— `main` 还停在 v0.12，别对着 main 找新代码
> **接手先读本文件**：项目状态都记在这儿（版本 / 分支 / 改动 / 测试 / 路径 / 待办 / 坑）

## 项目一句话

PyQt5 桌面应用。**v0.22**：「日常计划管理」——计划是一列**待办队列**，时段是「当天承装队列的栏位」，
额外轮 = 「当天额外的时间栏」。每一格四个动作：仅完成 / 完成并滚动 / 固定计划 / 拦截滚动（拦截连带额外轮）；
上方「📋 额外安排（N）」细长条打开当天额外安排列表。多分类 + 添加指定 + 退回（可撤销）+ 导入导出 JSON +
重置进度 + 三主题 + 快捷键（Ctrl+Enter 加一个 / Ctrl+D 今天完成 / Ctrl+Z 撤销 / Ctrl+Shift+Z·Ctrl+Y 重做）+
撤销栈 + 第三页「📊 归档总览」（进度 + 「还剩 N 条 ≈ 还要 N 天」估算 / 归档历史**按天分组、可折叠** /
今天完成 + 各时段归档备注 / **⬇ 导出归档**成 .txt / 下拉还能选「（全部分类）」看全局；切天也能 Ctrl+Z 退回）。

## 分支与提交（重要）

`main` = `a4581a8`（v0.12 + 台账文档，与 origin/main 同步）。**v0.13 → v0.22 全部在 autopilot 分支链上，没有合并回 main，也没有 push**：

| 分支 | 覆盖版本 | tip |
|------|----------|-----|
| `autopilot/283447bffad0` | v0.13 快捷键 / v0.13 回归测试 / v0.14 抽 theme.py | `6374c90` |
| `autopilot/2c7bffb2db41` | v0.15 抽 scheduler.py / v0.16 撤销栈 / v0.17 抽 editor.py / v0.18 归档总览页 / v0.19 归档备注可展开 | `a63e433` |
| `autopilot/65dba054e425` | v0.20 修 Ctrl+Shift+Z·Ctrl+Y 未绑 / v0.21 抽 executor.py / v0.22 归档按天分组 | `7321579` |
| `autopilot/a1f32a7e7932` | v0.22b 切天可撤销 / 归档导出文本 / 测试脚本进仓库 | `e7b4a00` |
| `autopilot/348240aadc58` | **v0.23~v0.25** 剩余天数估算 / 按天折叠 / 全部分类汇总 / 文件名清洗 / README 更新 | `aa2267a` |

链是线性的（后一个 run 从上一个分支 tip 起）。要合进 main：

```bash
cd /mnt/d/0_git/RollingPlan
git checkout main && git merge --ff-only autopilot/348240aadc58
# 想推就再 git push origin main（配置里 push:false，我没推过）
```

## 版本改动一览

| 版本 | 内容 |
|------|------|
| v0.13 | Ctrl+Enter / Ctrl+D / Ctrl+Z 接管执行页三大主操作；补 v0.9 队列模型边界回归测试（41 断言） |
| v0.14 | 抽出 `theme.py`（QSS + apply_theme），零行为变化 |
| v0.15 | 抽出 `scheduler.py`（`PlanScheduler` + `_pending_of`） |
| v0.16 | **撤销栈**：`push_history()` / `undo()` / `redo()`，可撤任意最近动作（加 / 退 / 完成 / 固定 / 拦截），上限 50 |
| v0.17 | 抽出 `editor.py`（`PlanEditor` 单文件 UI） |
| v0.18 | 第三页「📊 归档总览」（`calendar_view.py`：进度 / 归档历史 / 今天完成 + `slot_notes` 汇总） |
| v0.19 | 归档备注可点击展开（`▸ / ▾`，展开后每条单独一行，老格式保留） |
| v0.20 | 修 bug：`MainWindow.keyPressEvent` 里 Ctrl+Shift+Z / Ctrl+Y **以前根本没绑** `on_redo`（只有注释和 tooltip 写着） |
| v0.21 | 抽出 `executor.py`（`PlanExecutor` + `ExtraArrangementsDialog`），`rollingplan.py` 1332 → 585 行 |
| v0.22 | **归档总览按天分组**：`ParentPlan.daily_boundaries`（切天时 push 当天 `len(archived)`），`calendar_view` 折成「📅 第 N 天（X 条）」分隔标题 + 该天条目 |
| v0.22b | **切天（今天完成）可撤销**：`on_next_day` 先 `push_history()`，Ctrl+Z 整块退回前一天 |
| v0.22b | **归档导出**：第三页右上「⬇ 导出归档」→ `build_archive_text()` / `export_archive_text()` 写 UTF-8 文本 |
| v0.22b | **测试基建**：`run_all_tests.sh` 进仓库（自动挑解释器、退出码 0/1/2）+ `sync_to_task.sh`（哈希核对同步） |
| v0.23 | **剩余天数估算**：第三页「还剩 N 条 ≈ 还要 N 天（每天 N 格）」；**归档历史按天折叠**（▾/▸ + 全部展开/收起，默认只展开最近一天） |
| v0.24 | **「（全部分类）」汇总视图**：下拉第 0 项，合计进度 + 估算 + 每个分类一块（进度 / 最近 3 条归档 / 今天完成）；导出支持一次写出全部分类 |
| v0.25 | **导出文件名清洗** `safe_filename()`（Windows 非法字符 / 首尾空格点 / 空名 / CON·NUL.txt 保留名）；**README 更新到 v0.25** |

v0.12 及以前（额外轮纳入拦截 / 固定 / 拦截 / 仅完成 / 完成并滚动 / 队列模型）见 git 历史里 `main` 的提交。

## 文件与行数（v0.22）

| 文件 | 行数 | 职责 |
|------|------|------|
| `rollingplan.py` | 614 | `ParentPlan` / `PlanData` / `MainWindow`（数据模型 + 主窗口，编辑器 / 执行器 / 归档页都从这里 re-export） |
| `executor.py` | 787 | `PlanExecutor`（执行页）+ `ExtraArrangementsDialog` |
| `editor.py` | 621 | `PlanEditor`（制定计划页） |
| `scheduler.py` | 565 | `PlanScheduler`（队列 / 当天行 / 完成 / 滚动 / 额外轮的算法都在这儿） |
| `calendar_view.py` | 619 | `PlanCalendarView`（归档总览：按天分组 + 折叠 + 全部分类 + 导出）+ 纯函数 `build_archive_text` / `build_all_archive_text` / `estimate_days_left` / `summarize_all` / `safe_filename` |
| `theme.py` | 388 | 三套 QSS + `apply_theme` |

## 测试状态

**11 个测试文件 / 0 失败**（2026-09-16 于验收副本 `.venv` 全量实测）。

跑法（**用这个脚本，别单个跑**）：

```bash
cd /mnt/d/0_git/RollingPlan
bash run_all_tests.sh        # 退出码 0 = 全过 / 1 = 有失败 / 2 = 环境不对（找不到带 PyQt5 的 python）
```

脚本会自己挑解释器（`ROLLINGPLAN_PYTHON` > 本目录 `.venv` > 验收副本 `.venv` > 系统 python），
每个测试文件的完整输出在 `/tmp/rollingplan-test-<文件名>.log`。**仓库和验收副本里是同一份**（`sync_to_task.sh` 会一起同步）。

改完代码同步到验收副本、顺手核对哈希：

```bash
bash sync_to_task.sh         # 只覆盖 *.py / STATE.md / README.md / run_all_tests.sh,不动 .venv / build / dist
```

| 测试文件 | 规模 | 覆盖 |
|----------|------|------|
| `test_v2_2.py` | 33 断言 | v0.3 核心逻辑（借指定 / 链式借 / 退回 / 多分类独立） |
| `test_import_export_v04.py` | 49 断言 | v0.4 导入导出 + 结构校验 + 旧格式兼容 |
| `test_reset_v04.py` | 24 断言 | v0.4 重置进度 |
| `test_theme_v05.py` | 38 断言 | v0.7 QSS 主题 + QSettings 持久化 |
| `test_minimal_v06.py` | 32 断言 | v0.6 极简 UI 折叠 |
| `test_scroll_v11.py` | 170 断言 | v0.9~v0.12 滚动语义全量 |
| `test_regression_v13.py` | 41 断言 | v0.9 队列模型回归 |
| `test_undo_v16.py` | 30 用例 | v0.16 撤销栈 + **v0.22b 切天可撤销** |
| `test_calendar_v18.py` | 73 用例 | v0.18 归档总览 + v0.22 按天分组 + v0.22b 导出 + v0.23 估算 / 折叠 + v0.24 全部分类 + v0.25 文件名清洗 |
| `test_note_v19.py` | 8 用例 | v0.19 归档备注展开 |
| `test_keyboard_v20.py` | 5 用例 | v0.13 + v0.20 快捷键（含修好的 redo） |

> `run_all_tests.sh` **2026-09-16 修过**：老版把每个测试的输出 pipe 给 `tail -5`，管道退出码恒为 0 →
> **测试全挂也报「全过」**。现在改成写日志 + 用 python 自己的退出码判断，脚本自己 exit 1。
> 已经自测过这条路径：把一个断言故意写错 → 脚本 exit 1 并打印 FAIL（别再退回管道写法）。
> 脚本 2026-09-16 起进 git 仓库了（以前只在验收副本，新克隆没法自测）。

## 构建（exe）

WSL 侧直接调 Windows 的 Python 打包（已验证可用：Windows Python 3.13 + PyInstaller 6.22.3）：

```bash
cd /mnt/c && cmd.exe /c "cd /d D:\0-task\rollingplan && python -m PyInstaller --onefile --windowed --name RollingPlan --distpath dist --workpath build --specpath . rollingplan.py"
```

或 Windows 上双击 `build_windows.bat`。
**`dist/RollingPlan.exe` 还是 v0.12 的**（2026-09-15 23:24，37,868,119 字节）—— v0.13~v0.22 的东西都没进 exe。

## 文件关键路径（WSL 视角）

| 用途 | 路径 |
|------|------|
| Git 仓库 | `/mnt/d/0_git/RollingPlan/` |
| 验收副本 | `/mnt/d/0-task/rollingplan/` |
| Python venv | `/mnt/d/0-task/rollingplan/.venv/`（PyQt5 5.15.11） |
| 测试脚本 | `/mnt/d/0-task/rollingplan/run_all_tests.sh` |

源码 / 测试每次改完都 `cp -f` 到验收副本（两边应当逐字节一致，可用 `git hash-object` 比对）。

## 接下来该做什么

1. **第一优先：真机验收 + 重新打包。** v0.13~v0.22b（七页 UI 改动里第三页是全新的、还有快捷键和撤销栈）
   **一次都没在真机跑过**，这轮迭代全是 headless 验证。要看的点：
   - 第三页「归档总览」的排版（进度 / 按天分组的归档历史 / 今天完成 + 时段备注）宽窄合不合适；
     **深色主题下分隔标题的对比度**（v0.22 起标题色取自调色板半透明，不再写死灰 `#555`）；
   - 「⬇ 导出归档」按钮的位置 + 导出的 .txt 用 Windows 记事本打开有没有乱码（写的是 UTF-8 带 BOM）；
     分类名里带 `/ : * ?` 之类的默认文件名会不会还是非法（v0.25 起会换成 `_`）；
   - 「今天完成」误点之后 **Ctrl+Z 能不能退回前一天**（v0.22b），撤销按钮文案会不会显示成「↶ 撤销「进入下一天」」；
   - 「📅 第 N 天」分组**点标题能不能收起/展开**（v0.23）、「全部展开 / 收起」按钮顺不顺手；
   - 下拉切到「（全部分类）」时的排版（每个分类一块 + 最近 3 条归档）够不够看（v0.24）；
   - 进度区那行「还剩 N 条 ≈ 还要 N 天」的措辞 / 字号（v0.23）；
   - Ctrl+Enter / Ctrl+D / Ctrl+Z / Ctrl+Shift+Z 在真机输入法下会不会被吃掉；
   - 每格 4 个按钮挤不挤（v0.12 就留着没确认）。
   验完把结论写回本文件的验收行，再重新打包 exe。
2. ~~把 `run_all_tests.sh` 收进 git 仓库~~ ✅ 已做（v0.22b：仓库根 `run_all_tests.sh` + `sync_to_task.sh`，
   两个脚本都自测过失败路径）。
3. **`main` 合并**：见上面「分支与提交」。合并前建议先真机验收一次。
4. 还没做的方向（按价值排）：
   - **布局重设计**（执行页只显示「今天 + 加一个 / 今天完成」）
   - **今日模式**（把「今天」单独做一页）
   - 清理 `borrow_slot()` / `available_borrow_names()`（v0.3~v0.8 的按时段名旧入口，UI 已不用，
     留着只为旧调用和 `test_v2_2` 回归）
   - ~~README 版本表~~ ✅ v0.25 已更新
5. **待用户确认的语义**（提过没定的）：
   - 「固定计划」是否允许后面的计划**越过**它去填前面的空位（现语义：允许 → 早1中2晚3 固定中、滚早 → 早3 中2 晚空）
   - 「直接拉取」是否要指定拉进今天某个具体时间栏（现语义：列表里一个按钮，按顺序拉下一条）

## 备忘（改代码前先看）

- WSL 没 Qt 显示，验证 GUI 只能 `QT_QPA_PLATFORM=offscreen` 跑 headless。
- **headless 测过 ≠ 验收过**：颜色 / 字号 / 布局 / 手感只能证明「不崩、属性对不对」，必须真机看一眼。
- **QSS 与 widget 级 inline stylesheet**：widget 级优先。**文字色绝对不要写在 widget 级 stylesheet 里**
  （v0.8 暗色黑字事故）。要跟主题走的颜色用 `self.palette().color(...)`（v0.22 的分组标题就是这么做的）。
- **v0.9 数据模型**：计划是队列，时段只是当天的栏位。别再把「时段名」当计划的属性。
- **v0.10 quota**：今天这一格最多从队列取 (格数 - 今天已归档条数) 条 —— 这是「腾出来的最后一格不从第二天补」
  的实现（`today_state()`），别去掉，否则第二天的计划又滚进今天。
- **「仅完成」= 钉住（pin）**：`inplace_done[i]` 记着那一格的计划内容；滚动 = 按 quota 重新从队列取。
- **v0.11 钉住机制**：`held[i] = inplace_done[i] or slot_fixed[i] or slot_blocked[i]`。
  加新玩法优先往这里挂，别另起一套（v0.9 就是各写各的才出的错）。池子要按**内容**扣掉钉住的计划。
- **额外轮是「当天的时间栏」**：`extras_frozen = any(blocked)`（有格子拦截时额外轮不候补）。
- **v0.22 `daily_boundaries` 的不变量**（改这块一定先读）：
  - 语义：`daily_boundaries[i]` = **第 i+1 天结束时** `len(archived)`；`current_day` 每 +1 就 push 一条。
  - 因此 `len(daily_boundaries) ≤ current_day`；`normalize()` 会把值夹进 `[0, len(archived)]`、排序去重、
    并按 `current_day` 截断（撤回到「还没切天」的状态时，多出来的边界要跟着消失）。
  - 刚切天时 `archived_base == daily_boundaries[-1]`（同一个数），**两边都要写**（`executor.on_next_day`）。
  - `daily_boundaries` 在 `_SNAPSHOT_KEYS` 里 → 撤销栈会一起恢复；不在 `to_dict` 之外的任何派生字段里。
  - **切天也会 push_history**（v0.22b）：`on_next_day` 在确认之后、改状态之前入栈，
    所以 Ctrl+Z 能整块退回前一天（弹窗点取消时**不入栈**）。`history_top_label()` 里
    「天数变了」的判断要放在归档/额外轮判断**之前**，否则会被「退回额外轮」抢走（切天会清额外轮）。
  - 老存档（v0.21 及以前）没有这个键 → 空列表，归档会标成「第 1–N 天」，不崩。
- **JSON 键名不能改**：`borrowed_slots`、`archived` / `archived_base` / `consumed`（v0.9）、
  `inplace_done` / `slot_notes`（v0.10）、`slot_fixed` / `slot_blocked`（v0.11）、`daily_boundaries`（v0.22）。
- **刷新 UI 时旧控件要 `setParent(None)`**：只 `deleteLater()` 会让旧按钮滞留在控件树里（v0.10 被抓到过）。
- **归档页列表行的标记**：`QListWidgetItem.setData(Qt.UserRole, "day_header"|"plan"|"placeholder")`
  （条目行还有 `UserRole+1` = 在 `archived` 里的下标）。测试按标记筛行，**别硬编码下标**——
  v0.22 加分隔标题时，老测试就是靠 `item(1)` 定位而集体错位的。
- **v0.23 折叠只是显示状态**：`_day_open` / `_expand_all` 只在会话里（不写盘、不动数据）；
  `_archive_rows()` 对收起的那一天**不产出行** → 测试里想断言全部条目要先 `cv._on_toggle_all()`。
  分隔标题从 v0.23 起是 `Qt.ItemIsEnabled`（可点、不可选），不再是 `NoItemFlags`。
- **v0.24 下拉第 0 项是「（全部分类）」**：分类的下标 = 下拉下标 **- 1**（`setCurrentIndex(1)` 是第一个分类）；
  `self._all_mode` 为真时 `self.scheduler is None`（别直接 `.p`，走 `_refresh_all_view()`）。
- **导出的默认文件名必须过 `safe_filename()`**：新加导出入口时别忘了（Windows 非法字符 / 保留名）。
- **估算口径**：`estimate_days_left` = (总条数 - 归档数) ÷ 每天格数，向上取整；「全部分类」的
  每天格数是**各分类格数之和**（不是取最大），所以合计天数可能比单个分类少。
- `from_dict` 会迁移 v0.8 的 `completed_today`（slot 序号 → 计划内容）。
- 内部 docstring / 变量名还留着「母计划 / 子计划 / 借」等旧术语（只在代码里，UI 文案已经改过）。
- 测试文件名 `test_v2_2.py` 是历史遗留（README 里写的），保留不动。
- v0.4 导入是**覆盖语义**（不是合并），额外轮 / 归档状态一并带过来。
- **WSL/DrvFS I/O 坑**：`dist/*.exe`（30+MB）在 WSL 里 `rm` 偶尔报 Input/output error，
  Windows 端 `del` 也可能拒绝访问 → 用资源管理器手动删。
- **auto 主题在 WSL offscreen 下 darkdetect 会卡** → 测试只测 dark / light。
- **QGroupBox checkable 不可靠** → v0.6 起用 QToolButton 手动控制 visibility。
- **`isVisible()` 检查要求父链可见**：构造 widget 不 `show()`，子 widget 都是 False → 测试要
  `widget.show()` + `processEvents()`。
