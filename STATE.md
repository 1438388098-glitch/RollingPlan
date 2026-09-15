# RollingPlan — 当前工作状态

> **最后更新**：2026-09-15 22:45
> **会话位置**：`D:\0-task\rollingplan`（验收副本） / `D:\0_git\RollingPlan`（git 仓库）
> **远程**：v0.10 提交后与 `origin/main` 同步（无未推提交）

## 项目一句话

PyQt5 桌面应用。**v0.10 已完成**：「日常计划管理」——计划是一列**待办队列**，时段是「当天承装队列的栏位」；每格有两个动作：「仅完成」（标记完成、列表不动）和「完成并滚动」（归档 + 后面整体上滚一格，腾出来的最后一格只由额外轮补）。多分类 + 加一个 / 添加指定 / 退回（可撤销完成）+ 导入导出 JSON + 重置进度 + 三主题（自写 QSS）+ 冷调极简 UI。

## 当前版本

**v0.10** — 18 commits on `main`，已全部 push

## v0.10 核心改动（已落地）—— 仅完成 / 完成并滚动

用户反馈（v0.9 之后）：「完成」要有两种 —— 一种只标记、不动列表；一种才滚动。
而且滚动的最后一格**不许从第二天拉计划**。

**规则**：
- **仅完成**：这一格标记完成 —— 计划留在格里（灰字 + 删除线 + ✓），记进该时段的**归档备注**，
  按钮变灰，**后面的计划不滚动**
- **完成并滚动**：归档这一格，后面的整体上滚一格
- 按过「仅完成」的格子，之后还能按「完成并滚动」= 解开这一格让它滚（归档与备注不重复记）
- **腾出来的最后一格只由额外轮补**：额外轮为空就空着，绝不把第二天的计划滚上来
  - 早1 中2 晚3，点「早 → 完成并滚动」→ 早2 中3 **晚空**（v0.9 会变成晚4 —— 那是这次要修的）
  - 额外轮 [4] 时 → 早2 中3 晚4
- **每格各自的归档备注**：行尾小灰字「归档：1、4」
- 进度：两种完成都 +1（同一格先「仅完成」再「完成并滚动」不重复计数）

**代码**：
- `ParentPlan` 新增 `inplace_done`（「仅完成」钉住的格）/ `slot_notes`（每格归档备注），
  两者都按当天的格数在 `normalize()` 里对齐（改过时段数量也能收敛）
- `PlanScheduler` 新增 `complete_only_slot()` / `can_complete_only()` / `_drop_from_extras()`；
  `complete_today_slot()` 改为「完成并滚动」；`today_state()` 增加 `row_done` / `notes`，
  并用 quota（= 格数 - 今天已归档条数）实现「不从第二天补」
- `undo_complete()` 现在也会解开钉子 + 撤回备注
- `PlanExecutor`：每格两个按钮、完成态灰字删除线、行尾备注、「今天已完成」标签；
  `_clear_layout()` 改成 `setParent(None)` + `deleteLater()`（旧控件不再滞留在控件树里）
- 切天时清空 `inplace_done` / `slot_notes` / 额外轮，`consumed` 按今天真正从队列取走的条数步进

### v0.9 核心改动（已落地）—— 重写「完成并滚动」的语义

**用户报的 bug（v0.8 的错）**：早/中/晚三格、子计划 1..9。点「早1 的完成」，
它去**借第二天同名的早4** 顶上 → 早 变成 4；任务4 同时出现在第 1 天和第 2 天；
再点一次基本没反应（那一格还是 4），但背地里又借了一条（4 和 7 一起挂在额外轮）。

**根因**：`complete_today_slot()` 走的是 `borrow_slot(时段名)` —— 语义是「从未来借一条同名时段」，
而用户要的是「当天这列整体上移一格」。所以这不是补几行能修好的，是数据模型的事。

**v0.9 的模型**：
- **队列** = `plans` 去掉已完成（`archived`）的部分，保持原顺序
- **今天的行** = 队列里从 `consumed` 开始的 `slots_per_day()` 条；时段名只是行号
- **完成** = 把这条从队列拿走（归档）→ 队列一变，今天和后面几天的显示自然整体上移
  - 点早1 完成 → 早2 中3 晚4；第 2 天 → 5/6/7（不重复、不丢）
- **额外轮** = 用户点「加一个」从队列后段拉进来的计划，**不带时段名**（时段只是当天的栏位）；
  当它出现在今天的行上时算「滚上来了」，不在额外轮区重复显示
- **退回** = 优先**撤销今天最近一次完成**（按钮文案变 `↶ 撤销完成`）；今天没完成可撤时
  才退额外轮最后一个（文案 `⤴ 退回`）
- **添加指定**（v0.9 起）= 从**后面还没安排的计划清单**里挑一条提前安排
  （以前是按「时段名」挑；时段只剩栏位意思之后那样很别扭）。新增
  `available_pick_plans()` / `borrow_plan(计划)`
- **进度** = 完成一条 +1
- 顶部多一行「🗂 今天已完成：…」，归档了什么看得见

**代码**：
- `ParentPlan` 新增 `archived` / `archived_base` / `consumed`（取代 v0.8 的 `completed_today`）
- `PlanScheduler` 新增 `pending()` / `today_state()` / `done_today()` / `total_done()` /
  `undo_complete()` / `can_undo_complete()` / `raw_calendar()` / `available_pick_plans()` /
  `borrow_plan()`；重写 `get_day_plans` / `get_calendar` / `complete_today_slot` /
  `_future_slot_positions` / `get_progress` / `all_consumed`
- `_future_slot_positions()` 里「已在额外轮里的要跳过」是**按内容扣减**的，不是按下标数量 ——
  「添加指定」可以挑一条不在队首的，按下标跳会跳错（重名计划各算一次）
- `PlanExecutor`：日内行 / 额外轮 / 日历预览 / 退回按钮改造；新增「今天已完成」标签
- 制定页「计划预览」改用 `raw_calendar()`（铺开看计划怎么分，不受进度影响）
- **旧存档自动迁移**：`from_dict` 见到 v0.8 的 `completed_today`（slot 序号）→ 转成计划内容

### v0.8 核心改动（已落地）
- 暗色主题文字对比度修复（widget 级 inline 颜色会盖过 QSS —— 全删，文字色统一交给 QSS）
- 字号整体加大（默认 11→13pt，日期 18pt，时段/计划名 16pt）
- 完成并滚动**首版**（语义错的，v0.9 重写）

### v0.7 核心改动（已落地）
- 自写 QSS 主题（弃用 pyqtdarktheme —— onefile 打包后 `setup_theme()` 静默 no-op）
- `_detect_system_theme()` 处理 auto（Windows 注册表 / macOS defaults）
- 打包小 ~5MB，运行时无外部依赖

### v0.6 核心改动（已落地）
- 冷调极简 UI：三个 GroupBox 默认收起（QToolButton 手动控制 visibility）
- 执行页底部「更多 ▾」收纳次要操作；「今天」主区垂直居中；主操作按钮加大（minHeight=50）

### v0.5 核心改动（已落地）
- 三主题切换（DarkFlat / LightClean / System）+ QSettings 持久化 + Tab 对比度修复

### v0.4 核心改动（已落地）
- 导出 JSON（含 version/exported_at/data）+ 导入 JSON（**覆盖语义**，先校验后弹窗确认，取消回滚）
- 重置当前分类进度（🔄）：`current_day=0` + 额外轮清空 + 归档清空
- 新增 `reload_executor()`（导入/重置后重建 executor）

### v0.3 核心改动（已落地）
- UI 文案口语化：母计划→分类、子计划→计划、时间段→时段、额外轮→额外安排
- 按钮布局重构：`➕ 加一个`（主） / `⤴ 退回` / `✓ 今天完成`（主） / `⋯ 添加指定`

### v0.2.1 / v0.2 基础（已落地）
- 借指定时段 / 链式借 / 退回 / 多分类独立 / QSettings 持久化
- 借用判定去重、下一天确认弹窗、借用期间禁改时段、额外安排视觉强化、加载失败改日志

## 仓库状态

- **`main`**：v0.9，17 个 commit，**已 push，与 origin/main 一致**
- **远程**：https://github.com/704315792-crypto/RollingPlan.git
- **验收副本**：`D:\0-task\rollingplan\`
  - 与 git 仓库的源码/测试/文档逐一对齐（md5 校验过）
  - `.venv`：PyQt5 5.15.11（v0.7 起不再需要 pyqtdarktheme）
  - `dist/RollingPlan.exe`：v0.9 重建（见下方「构建」）
  - `build/` `dist/` `RollingPlan.spec` 是构建产物，`.gitignore` 已忽略，只存在于验收副本

## 测试状态

**6 个测试文件 / 总计 269 个断言全过，0 失败**（2026-09-15 22:40 于验收副本 .venv 实测）

| 测试文件 | 断言 | 覆盖 |
|----------|------|------|
| `test_v2_2.py` | **33** | v0.3 核心逻辑（借指定 / 链式借 / 退回 / 多分类独立） |
| `test_import_export_v04.py` | **49** | v0.4 导入/导出 + 结构校验 + 旧格式兼容 |
| `test_reset_v04.py` | **24** | v0.4 重置进度（保留 plans/time_slots/start_date，多分类隔离） |
| `test_theme_v05.py` | **38** | v0.7 QSS 主题 + QSettings 持久化 + stderr=None 不崩 |
| `test_minimal_v06.py` | **32** | v0.6 极简 UI 折叠 + 主区居中 + 大按钮 |
| `test_scroll_v10.py` | **93** | v0.10 仅完成 / 完成并滚动 / 不从第二天补 / 归档备注 / 撤销 / 额外轮 / UI |

`test_complete_v08.py`（v0.8 的错行为）和 `test_scroll_v09.py`（v0.9 语义）都已删，
现由 `test_scroll_v10.py` 覆盖。

跑法：
```bash
cd /mnt/d/0-task/rollingplan
QT_QPA_PLATFORM=offscreen .venv/bin/python test_scroll_v10.py
```

## 构建（exe）

WSL 侧可以直接调 Windows 的 Python 打包（已验证可用：Windows Python 3.13 + PyInstaller 6.22.3）：

```bash
cd /mnt/c && cmd.exe /c "cd /d D:\0-task\rollingplan && python -m PyInstaller --onefile --windowed --name RollingPlan --distpath dist --workpath build --specpath . rollingplan.py"
```

或者 Windows 上双击 `build_windows.bat`（它会先装依赖再打包）。

## 文件关键路径（WSL 视角）

| 用途 | 路径 |
|------|------|
| Git 仓库 | `/mnt/d/0_git/RollingPlan/` |
| 验收副本 | `/mnt/d/0-task/rollingplan/` |
| Python venv | `/mnt/d/0-task/rollingplan/.venv/` |
| 主程序 | `/mnt/d/0_git/RollingPlan/rollingplan.py`（2171 行 / 81706 字节） |
| 构建脚本 | `/mnt/d/0_git/RollingPlan/build_windows.bat` |

## 还没做的方向

1. ~~修 bug~~ / ~~UX 打磨~~ / ~~打包发布~~ ✅ 都已落地
2. **新功能**（未做）：
   - 快捷键（Ctrl+Enter 加一个 / Ctrl+D 今天完成 / Ctrl+Z 退回）
   - 撤销栈（现在只能撤「完成」，且只限今天）
   - **布局重设计**（执行页只显示「今天 + 加一个/今天完成」）
   - **今日模式**（独立第三页）
3. **代码重构**（未做）：单文件 2000+ 行可拆 `model.py` / `scheduler.py` / `editor.py` / `executor.py` / `theme.py`
   - 顺带可以清掉 `borrow_slot()` / `available_borrow_names()`（v0.3~v0.8 的按时段名入口，
     UI 已经不用了；留着只是为了旧调用和 test_v2_2 的回归测试）

## 下次新会话该做什么

**前置**：无需 push（已同步）。直接读本文件即可接着干。

**选项 A**：从「还没做的方向 2」里挑下一个新功能（快捷键改动最小、见效最快）
**选项 B**：重构分模块（按 5 个模块拆 model/scheduler/editor/executor/theme）
**选项 C**：先问用户 v0.10 在真机上用起来对不对（**headless 测试 = 269 断言全过，
但视觉/手感没有真机确认** —— 参见下方备忘）

## 备忘

- WSL 没 Qt 显示，要验证 GUI 只能用 `QT_QPA_PLATFORM=offscreen` 跑 headless
- **headless 测过 ≠ 验收过**：涉及视觉 / 手感（颜色、字号、布局、点起来顺不顺）的改动，
  headless 只能证明「不崩、属性对不对」。必须让用户真机跑一次，并把确认结果写回本文件的验收行
- **QSS 与 widget 级 inline stylesheet**：widget 级 inline 优先。**文字色绝对不要写在 widget 级
  stylesheet 里**（v0.8 的暗色黑字事故就是这个），widget 级只写背景色 / 边框色
- **v0.9 的数据模型**：计划是队列，时段只是当天的栏位。
  改 `PlanScheduler` 时别再把「时段名」当成计划的属性 —— 那是 v0.8 那套错误语义的残留
- **v0.10 的显示模型**：今天这一格最多从队列取 (格数 - 今天已归档条数) 条 —— 这就是
  「腾出来的最后一格不从第二天补」的实现（quota）。改 `today_state()` 时别把这个 quota 去掉，
  否则第二天的计划又会滚进今天
- **「仅完成」是钉住（pin）**：`inplace_done[i]` 记着那一格的计划内容，它在格里不走也不占队列配额；
  滚动的本质是「按 quota 重新从队列取」，所以解开钉子自然就滚了
- **JSON 字段名**：`borrowed_slots`（额外轮）、`archived` / `archived_base` / `consumed`（v0.9）、
  `inplace_done` / `slot_notes`（v0.10）。重构时不能改这些键名
- **刷新 UI 时旧控件要 `setParent(None)`**：只 `deleteLater()` 的话，旧按钮会滞留在控件树里
  直到事件循环处理删除 —— 测试会抓到旧的（v0.10 被抓到过），界面上也可能闪一下
- `from_dict` 会迁移 v0.8 的 `completed_today`（slot 序号 → 计划内容）；v0.8 时期自动借进来的
  额外轮条目仍留在 `borrowed_slots` 里，用户可以用「退回」清掉
- 内部 docstring 还保留「母计划 / 子计划 / 借」等术语（变量名 + 注释）—— 不影响 UI
- 测试文件名 `test_v2_2.py` 是历史遗留（README 里写的），保留不动
- v0.4 导入是**覆盖语义**（不是合并），额外轮 / 归档状态一并带过来
- **WSL/DrvFS I/O 坑**：`dist/*.exe`（30+MB）在 WSL 里 rm 偶尔报 Input/output error，
  Windows 端 `del` 也可能拒绝访问。绕过办法：Windows 资源管理器手动删
- **auto 主题在 WSL offscreen 下 darkdetect 会卡** —— 测试只测 dark/light，不测 auto
- **QGroupBox checkable 不可靠**（pyqtdarktheme 时代）—— v0.6 起改用 QToolButton 手动控制 visibility
- **isVisible() 检查时父链必须至少一层可见**：构造 widget 但不 show()，子 widget 的
  isVisible() 都是 False。测试必须 widget.show() + processEvents()
