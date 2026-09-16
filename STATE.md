# RollingPlan — 当前工作状态

> **最后更新**：2026-09-17 凌晨（autopilot iter-6 全夜跑：v0.30 推倒重设计 R1~R22）
> **相关目录**：`D:\0-task\rollingplan`（验收副本） / `D:\0_git\RollingPlan`（git 仓库）
> ⚠️ 上面两个是原作者机器的路径。**协作者克隆在 `D:\Claudeworkspace\RollingPlan`**
> （origin = 1438388098-glitch/RollingPlan 的 fork，upstream = yM7-1/RollingPlan，有 write 权限）。
> 本机跑测试：`ROLLINGPLAN_PYTHON="$(which python)" bash run_all_tests.sh`
> （`python` = Anaconda 3.6.5 + PyQt5，实测 11 个文件全过）。
> **代码最新在**：本地 `main`（v0.28b + v0.29 动效，**领先 origin/main 2 个提交，待 push**）
> **接手先读本文件**：项目状态都记在这儿（版本 / 分支 / 改动 / 测试 / 路径 / 待办 / 坑）
> **现在处在哪一步**：**v0.30 推倒重设计完成（R1~R22）**：设计系统 token 化、三个 P0
> （页签错位/导入取消丢数据/读档失败静默）、三页卡片化重设计、动效 v2、存储迁移 INI、
> 易用性批量修复；**17 个测试文件 530 断言 + 116 用例全绿**；
> 待办 = **真机验收 + push（本地 main 领先远端 30+ 提交）**

## 项目一句话

PyQt5 桌面应用。**v0.22**：「日常计划管理」——计划是一列**待办队列**，时段是「当天承装队列的栏位」，
额外轮 = 「当天额外的时间栏」。每一格四个动作：仅完成 / 完成并滚动 / 固定计划 / 拦截滚动（拦截连带额外轮）；
上方「📋 额外安排（N）」细长条打开当天额外安排列表。多分类 + 添加指定 + 退回（可撤销）+ 导入导出 JSON +
重置进度 + 三主题 + 快捷键（Ctrl+Enter 加一个 / Ctrl+D 今天完成 / Ctrl+Z 撤销 / Ctrl+Shift+Z·Ctrl+Y 重做）+
撤销栈 + 第三页「📊 归档总览」（进度 + 「还剩 N 条 ≈ 还要 N 天」估算 / 归档历史**按天分组、可折叠** /
今天完成 + 各时段归档备注 / **⬇ 导出归档**成 .txt / 下拉还能选「（全部分类）」看全局；切天也能 Ctrl+Z 退回）。

## 分支与提交

**`main` = `a698b64`（v0.25），已 push，与 `origin/main` 一致。** v0.13 → v0.25 全部在 main 上：
之前那些 autopilot 分支链已经**快进合并**进 main（`git merge --ff-only autopilot/348240aadc58`，
一个 merge commit 都没有，单纯往后挪），链是：

| 分支（历史，可删） | 覆盖版本 | tip |
|------|----------|-----|
| `autopilot/283447bffad0` | v0.13 快捷键 / v0.13 回归测试 / v0.14 抽 theme.py | `6374c90` |
| `autopilot/2c7bffb2db41` | v0.15 抽 scheduler.py / v0.16 撤销栈 / v0.17 抽 editor.py / v0.18 归档总览页 / v0.19 归档备注可展开 | `a63e433` |
| `autopilot/65dba054e425` | v0.20 修 Ctrl+Shift+Z·Ctrl+Y 未绑 / v0.21 抽 executor.py / v0.22 归档按天分组 | `7321579` |
| `autopilot/a1f32a7e7932` | v0.22b 切天可撤销 / 归档导出文本 / 测试脚本进仓库 | `e7b4a00` |
| `autopilot/348240aadc58` | v0.23~v0.25 剩余天数估算 / 按天折叠 / 全部分类汇总 / 文件名清洗 / README 更新 | `aa2267a` |
| `autopilot/e80c1c2c58a6` | **v0.26~v0.28 极简界面改造**（执行页顶栏 / 每格一个按钮 / 0 条不显示 / 队列一行化 / 制定页 / 归档页） | 已 ff 合并进 main |

这些分支的提交都在 main 里，本地留着只是当书签；要清理就 `git branch -d autopilot/*`（**别在
autopilot run 还开着的时候删**）。下一轮迭代直接 `cd` 进仓库、对着 main 开跑，不用再管这条链。

推代码（HTTPS + `~/.netrc` 里的 PAT，别用 SSH）：

```bash
cd /mnt/d/0_git/RollingPlan
export GIT_TERMINAL_PROMPT=0
git push origin main        # 没配 credential.helper，git 会自己读 ~/.netrc
```

## 版本改动一览

| 版本 | 内容 |
|------|------|
| v0.30 | **推倒重设计全夜跑（iter-6 R1~R22，subagent 三路审计驱动）**：
|  | R1 设计系统 token 化（theme.py 重写：DARK_TOKENS/LIGHT_TOKENS/QSS_TEMPLATE + string.Template，15 个语义角色选择器 rpPrimary/rpSuccess/rpGhost/rpFold/rpDone/rpDim/rpSlotCard/rpExtraCard…，页面内联硬编码色 27 处全迁移）|
|  | R2 修 P0 页签错位（removeTab+addTab 是追加→insertTab(1)+deleteLater；快捷键门槛按 currentWidget 身份；新增 test_tabs_v30）|
|  | R3 修导入取消数据丢失链（to_dict 快照回滚替代 load() 回滚；test_import_cancel_v30）|
|  | R4 from_dict 类型防线（idx/day sanitize+clamp；test_data_sanity_v30）|
|  | R5 执行页卡片化重设计（rpSlotCard/rpExtraCard + 行内可见 ⋯ QToolButton + 空态 CTA + rpTitle 层级）|
|  | R6 制定页重设计（新手引导条 + 时段单表单 _SlotEditDialog + 回车添加 + 校验自动展开聚焦）|
|  | R7 动效 v2（MOTION token 表 + 窗口级 windowOpacity 出场 + 卡片 hover）|
|  | R8 页面同步（切分类日期覆写 + 直点 tab 旧行；test_page_sync_v30）|
|  | R9 P0 数据安全包（读档失败弹窗+损坏转存 ~/.hermes_cache 时间戳备份+坏数据隔离；save 留一代 plan_data_backup；删除计划/时段确认；取消不偷建分类；test_data_safety_v30）|
|  | R10 存储迁移（QSettings 显式 IniFormat 四参构造，Windows 不再写注册表；load 一次性迁移注册表旧数据；测试隔离随之真正生效）|
|  | R11 归档页排版统一；R12 Ctrl+1/2/3 切页 + 窗口自适应小屏；R13 逻辑毛刺（额外安排锁改当前分类粒度/切天列具体条目+防连刷/重复时段编号）；R14 深色可读性（darkGreen→token、palette 假跟主题→token、rp-note-detail 透明）；R15 安全默认（三处确认默认否）；R16 动效收口（删整页切页特效/时长归 MOTION/fade_out/主题切换缓冲/菜单淡入）；R17 撤销入口统一（旧退回退隐）；R18 术语统一（额外轮→额外安排/报错人话/主题下拉同步）；R19 字号间距清账（23 处 QFont 清零/4px 网格/边距统一）；R20 工具链 Windows 兼容（venv Scripts 布局/PYTHONUTF8/循环导入清理）；R21 制定页 22 动作冒烟测试（test_editor_smoke_v30）；R22 本文档轮 |
|  | R23~R31（expansion）一键恢复上次备份（可来回切/选代数）、分类名唯一性、无选中提示、列表高度+保选保滚动、双击编辑、窗口标题带分类+启动居中、3 代备份环、禁用按钮原因提示 |
|  | R32~R34（走查审计 Top 修复）：「✓ 今天完成」→「⏭ 结束今天 →」、引导条指路折叠、「保存并预览」让主样式给「开始执行 →」、删除按钮 rpDangerGhost、撤销/重做移出折叠区常驻显现、完成后状态行闪 success 色 |
|  | R35 重新打包 exe（39,050,053 字节，Python 3.13 + PyInstaller，含 v0.30 全部改动；仍未真机启动验证）|
| v0.29 | **全局动效**：新模块 `animations.py`（165 行）统一收口 —— `fade_in()` / `toggle_section()`（maximumHeight 高度动画）。接入：切页淡入（MainWindow._on_tab_changed）/ 执行页「更多」+ 队列行、制定页五组、归档页「⋯」折叠区高度展开收起 / 完成并滚动·切天·切分类 后 day_container 轻淡入 / 额外安排按钮·归档「今天完成」·制定页预览区 从无到有时浮现 / ExtraArrangementsDialog 弹出淡入。OutCubic + 150~220ms；特效动完即摘；同控件同动画重触发先 disconnect+stop（中途反转不跳变）；**`QT_QPA_PLATFORM=offscreen` 下 enabled() 恒 False，禁用路径 = 一句 setVisible** → 测试行为与 v0.28 一致（11 文件全绿 + dump 逐字节相同已验证）。executor 新存 `self.day_container` 引用 + `_extra_btn_was_visible` 追踪；calendar_view 的 today_group 可见性统一走 `_set_today_group_visible()` |
| v0.28b | **修 bug**：`editor.py` 缺 `QInputDialog` / `QFileDialog` 的 import —— 新建分类 / 重命名 / 编辑计划 / 编辑时段 / 导入 / 导出 一点就 NameError（v0.17 抽分文件时丢的；测试没盖住这几条 UI 路径所以一直全绿没暴露） |
| v0.26 | **执行页顶栏极简**：默认只剩「更多」+ 分类名（切换分类/主题/返回制定 收进折叠区）；日期/进度/今天完成 三行并成两行 |
| v0.14 | 抽出 `theme.py`（QSS + apply_theme），零行为变化 |
| v0.13 | Ctrl+Enter / Ctrl+D / Ctrl+Z 接管执行页三大主操作；补 v0.9 队列模型边界回归测试（41 断言） |
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
| v0.26 | **执行页顶栏极简**：只剩「更多」+ 分类名（切换分类/主题/返回制定 收进折叠区）；日期/进度/今天完成 三行并两行（完成内容进 tooltip） |
| v0.26b | **每格只留一个「✓ 完成并滚动」**：仅完成/固定计划/拦截滚动 收进格子右键菜单（按钮对象都还在，只是不显示） |
| v0.27 | **0 条不显示**（额外安排按钮 0 条时彻底隐藏）+ **队列一行化**（底部「计划队列 · 还有 N 条」，点开才展开） |
| v0.27b | **制定页瘦身**：重置进度/导入/导出/预览 进右上「⋯」；起始日期跟其它三组一样默认收起；底部只留「生成计划 + 开始执行 →」 |
| v0.28 | **归档页瘦身**：导出/全部展开 进「⋯」；「✅ 今天完成」空白时整块不出现；制定页预览区按需出现；README 写「极简口径」 |

v0.12 及以前（额外轮纳入拦截 / 固定 / 拦截 / 仅完成 / 完成并滚动 / 队列模型）见 git 历史里 `main` 的提交。

## 文件与行数（v0.30）

| 文件 | 行数 | 职责 |
|------|------|------|
| `executor.py` | 878 | `PlanExecutor`（执行页）+ `ExtraArrangementsDialog`；v0.29 存 `day_container` 引用、额外安排按钮浮现追踪、对话框 showEvent 淡入 |
| `editor.py` | 813 | `PlanEditor`（制定计划页）；五组折叠走 `animations.toggle_section` |
| `calendar_view.py` | 665 | `PlanCalendarView`（归档总览）+ 纯函数；today_group 可见性统一走 `_set_today_group_visible()`（浮现动效） |
| `rollingplan.py` | 760 | `ParentPlan` / `PlanData` / `MainWindow`；v0.29 切页淡入 |
| `scheduler.py` | 565 | `PlanScheduler`（队列 / 当天行 / 完成 / 滚动 / 额外轮的算法都在这儿） |
| `animations.py` | 262 | **v0.29 全局动效**：`fade_in` / `toggle_section`（maximumHeight 高度动画）/ 动画重触发防跳变 / offscreen 自动禁用 |
| `theme.py` | 462 | 三套 QSS + `apply_theme` |

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

WSL 侧直接调 Windows 的 Python 打包（已验证可用：Windows Python 3.13.14 + PyQt5 5.15.2 + PyInstaller 6.22.3）：

```bash
cd /mnt/c && cmd.exe /c "cd /d D:\0-task\rollingplan && python -m PyInstaller --noconfirm --onefile \
  --windowed --name RollingPlan --distpath dist --workpath build --specpath . rollingplan.py"
```

或 Windows 上双击 `build_windows.bat`（会先装依赖）。
**`dist/RollingPlan.exe` 已经是 v0.28 的**（2026-09-16 20:11 重打，37,867,210 字节；旧 v0.12 / v0.25 的都已删）。
⚠️ 这个 exe **还没人启动验证过**（想验但被安全策略拦了），下次改完代码要重新打包。

## 文件关键路径（WSL 视角）

| 用途 | 路径 |
|------|------|
| Git 仓库 | `/mnt/d/0_git/RollingPlan/` |
| 验收副本 | `/mnt/d/0-task/rollingplan/` |
| Python venv（WSL 用） | `/mnt/d/0-task/rollingplan/.venv/`（PyQt5 5.15.11，Linux venv；Windows 上别用） |
| 测试脚本 | 仓库根 `run_all_tests.sh`（验收副本里是同一份） |
| 打包产物 | `/mnt/d/0-task/rollingplan/dist/RollingPlan.exe`（v0.28，2026-09-16 20:11，37,867,210 字节） |
| 界面自查工具 | 仓库根 `dump_minimal_view.py`（文字打印三页「默认视图」里真正可见的控件树） |

源码 / 测试每次改完都 `cp -f` 到验收副本（两边应当逐字节一致，可用 `git hash-object` 比对）。

## 迭代进度（autopilot 运行记录）

代码是分四轮「自我迭代」跑出来的（skill：`auto-iterate-project`，每轮 3~5 个候选、一次一个、
提交前跑全量测试）：

| 轮次 | 分支（已合进 main） | 产出 | 轮数 |
|------|--------------------|------|------|
| iter-1 | `autopilot/283447bffad0` | v0.13 快捷键 / v0.13 回归测试 / v0.14 抽 theme.py | 3 |
| iter-2 | `autopilot/2c7bffb2db41` | v0.15~v0.19（抽 scheduler / 撤销栈 / 抽 editor / 归档总览页 / 备注可展开） | 5 |
| iter-2b | `autopilot/65dba054e425` | v0.20~v0.22（修 redo 未绑 / 抽 executor / 归档按天分组） | 3 |
| iter-3 | `autopilot/a1f32a7e7932` | v0.22b（切天可撤销 / 归档导出 / 测试脚本进仓库） | 3 |
| iter-4 | `autopilot/348240aadc58` | v0.23~v0.25（剩余天数估算 / 按天折叠 / 全部分类汇总 / 文件名清洗 / README） | 5 |
| iter-5 | `autopilot/e80c1c2c58a6` | **v0.26~v0.28 极简界面改造**（用户验收反馈：「功能没问题，但界面太杂乱、分散注意力」） | 5 |

每个 run 的状态留在仓库的 `.autopilot/`（`state.json` / `backlog.json` / `retrospective.md` /
`last-summary.md`；未跟踪、不推远端）。**下一轮要开新 run**：

```bash
cd /mnt/d/0_git/RollingPlan        # 对着 main 开跑（分支已合并，不用再接力旧链）
python3 ~/.hermes/skills/auto-iterate-project/scripts/autopilot_state.py init --repo $PWD --force \
  --max-rounds 3 --max-minutes 150 --branch-mode feature \
  --check-commands "$PWD/run_all_tests.sh" --commit-message-prefix iter-5 \
  --candidates-per-round 1 --commit-every-rounds 1 --verify-every-rounds 1 --report-lang zh
# 然后 backlog-add 补候选（旧候选基本都用完了）→ backlog-rank → begin-round → 干活 → commit → complete-round
```

`backlog.json` 里还剩 1 个没做的候选：**candidate-020 归档 / 持久化的跨天链路回归测试**
（「多天完成 → 切天 → 撤销 → 重做 → 导出 → JSON 往返」的端到端链路）。

## 接下来该做什么

1. **只剩这一件：真机验收（v0.13~v0.28 都没在真机跑过，全是 headless 验证）**。
   代码已改到 v0.28，**exe 还是 v0.25 打的 → 验收前先重新打包**（命令见「构建（exe）」）。
   或者直接跑源码：`cd /d D:\0-task\rollingplan && python rollingplan.py`（Windows Python + PyQt5 已装好）。
   这轮是**极简改造**，重点看：
   - 执行页默认视图：顶栏只有「更多」+ 分类名，中间「📅 第 N 天 + 一行小字」，每格只有 1 个「✓ 完成并滚动」，
     底部「加一个 / 今天完成」+ 一行「计划队列 · 还有 N 条」—— **顺不顺眼、够不够用**；
   - **格子右键菜单**（仅完成 / 固定计划 / 拦截滚动 / 完成并滚动）：能不能发现、点了生不生效；
     `✓` 按钮 hover 的 tooltip 有没有说「这一格右键还能…」；
   - 「更多」里的 切换分类 / 主题 / 返回制定 / 退回 / 撤销 / 重做 / 添加指定 找不找得到；
   - 「📋 额外安排」按钮：0 条时应该**完全不出现**，有额外安排时才冒出来；
   - 队列一行点开 / 收起（箭头方向对不对）、制定页右上「⋯」（重置/导入/导出/预览）、
     四个组（计划分类/计划清单/时段/起始日期）的 ▸ 展开手感；
   - 归档页右上「⋯」（导出归档 / 全部展开·收起）；「✅ 今天完成」在没完成时应该整块消失；
     导出 .txt 用记事本打开乱码吗；「📅 第 N 天」点标题收起/展开；
   - 误点「今天完成」后 Ctrl+Z 能不能退回前一天（v0.22b）；
   - Ctrl+Enter / Ctrl+D / Ctrl+Z / Ctrl+Shift+Z 在真机输入法下会不会被吃掉；
   - **exe 能不能正常打开这一条还没人验过**（我试着启动 + 查进程被安全策略拦了，见「备忘」）。
   验完把结论写回本文件（改动只影响界面，数据格式没变，老存档照用）。
2. ✅ 已做：`run_all_tests.sh` / `sync_to_task.sh` 进仓库；`main` ff 合并 + push（tip `d3b156d`）；
   README 更新到 v0.25；仓库与验收副本逐文件哈希一致。
3. 还没做的方向（按价值排）：
   - **布局重设计**（执行页只显示「今天 + 加一个 / 今天完成」）
   - **今日模式**（把「今天」单独做一页）
   - 清理 `borrow_slot()` / `available_borrow_names()`（v0.3~v0.8 的按时段名旧入口，UI 已不用，
     留着只为旧调用和 `test_v2_2` 回归）
   - candidate-020 那条跨天链路回归测试
4. **待用户确认的语义**（提过没定的）：
   - 「固定计划」是否允许后面的计划**越过**它去填前面的空位（现语义：允许 → 早1中2晚3 固定中、滚早 → 早3 中2 晚空）
   - 「直接拉取」是否要指定拉进今天某个具体时间栏（现语义：列表里一个按钮，按顺序拉下一条）

## 备忘（改代码前先看）

- **iter-6 全夜跑的三条新教训**：
  1. **autopilot 每轮开工必须先单独跑 begin-round、确认树干净再动代码** ——
     R6/R10 两次把改动和 begin-round 混在同一条链里，commit 被拒/round 记错 SHA，
     只能 commit --round <N> 补孤儿提交。
  2. **QSettings 两参构造在 Windows = 注册表**：v30 之前的测试隔离
     （setDefaultFormat+setPath）对它完全不生效，测试互相污染还写穿真实数据。
     现已全仓库改 theme.app_settings()（显式 IniFormat 四参）。**别再直接 new QSettings("RollingPlan","Data")**。
  3. **测试里打桩模态框只许 patch 静态方法**（QMessageBox.question / QInputDialog.getText），
     patch 实例方法 exec_ 或让真模态在 offscreen 弹出来 = 挂死/段错误/退出崩溃。
- **v0.29 动效三条铁律**（改 UI 前先看）：
  1. **offscreen 恒禁用**：`animations.enabled()` 见 `QT_QPA_PLATFORM=offscreen` 就 False，
     禁用路径 = 一句 `setVisible`。**测试 / dump_minimal_view 必须永远走这条路** ——
     别在测试里开动效，别把折叠逻辑从 `toggle_section` 换回裸 `setVisible`（裸写反而不一致）。
  2. **特效用完即摘**：`fade_in` 结束回调里 `setGraphicsEffect(None)`；
     别对长期存在的控件挂透明度特效不管（渲染走光栅化路径，挂着有开销）。
  3. **同控件同动画重触发**：`_stop_old()` 先 `finished.disconnect()` 再 `stop()` ——
     不 disconnect 的话旧动画 stop 会触发它的 finished 回调（比如把刚要展开的区域又藏回去），
     折叠/展开来回快点会跳变。
  冒烟脚本（桌面模式验证动画真在动，临时可删）：`/tmp/rp_anim_smoke.py`，
  跑法 `PYTHONPATH=<仓库> python /tmp/rp_anim_smoke.py`。
- **跑 autopilot 的硬流程：`begin-round` → 干活 → `commit` → `complete-round`**。
  漏掉 `begin-round` 时 `commit` 会拒绝（`[ERROR] No round is open`），但改动会留在暂存区、
  `complete-round` 却可能已经把轮次记上 —— 就会出现「轮次 +1 但没有 commit」的不一致。
  补救：`commit --round <N>`（允许 orphan commit）再核对 `git log` / `git status`。
  **别把 autopilot 命令的输出用 `| tail -N` 截断**，报错行常在最前面，截没了就看不见。
- **headless 测过 ≠ 验收过**：颜色 / 字号 / 布局 / 手感只能证明「不崩、属性对不对」，必须真机看一眼。
- **副本里的 mtime 就是「编辑时间」**（`sync_to_task.sh` 用 `cp -pf` 保留源文件 mtime）。
  判断 exe 新不新，直接比 `dist/RollingPlan.exe` 和副本 `*.py` 的 mtime：exe 更新 = 产物不陈旧。
  （踩过：早先用 `cp -f`，同步会把源码 mtime 刷成「复制时刻」，看上去比 exe 还新，白白怀疑 exe 是旧的。
  真判断只看**内容哈希** —— `git hash-object` 两边一致才是硬证据。）
- **「启动 exe / 关掉进程」这类动作会被安全策略拦**：我试过用 PowerShell 启动 exe + 12 秒后查进程 +
  `Stop-Process`，被判定需要用户确认而拦下（`taskkill /F` 同理）。要么请用户放行，要么直接让用户
  双击 `D:\0-task\rollingplan\dist\RollingPlan.exe`。**别换着写法反复试**。
- **Windows 侧打包环境（2026-09-16 实测）**：`python` = 3.13.14 + PyQt5 5.15.2 + PyInstaller 6.22.3，
  打包命令（`--noconfirm` 别省，省了会卡在交互确认上）：
  ```bash
  cd /mnt/c && cmd.exe /c "cd /d D:\0-task\rollingplan && python -m PyInstaller --noconfirm --onefile \
    --windowed --name RollingPlan --distpath dist --workpath build --specpath . rollingplan.py"
  ```
  删旧 exe / build 缓存要用 **Windows 侧** `cmd.exe /c "del /f /q ... & rmdir /s /q ..."`（WSL 删 30MB+ 的
  DrvFS 文件会报 I/O error）。打包前先 `python C:\...\Temp\rp_check_modules.py` 那种小脚本验一下
  副本源码在 Windows 上能 import（我这次就是这么验的；临时脚本在 Windows Temp 里，可删）。
- **副本里的 `.venv` 是 WSL 的 Linux venv**（python 3.11.16 clang），**Windows 上跑源码别用它**，
  用系统 `python`（PyQt5 已装）。
- **工具输出会把 `PASS=<数字>` 掩码成 `PASS=***`**（像是被当成密码赋值了）→ 统计断言数时从落盘的
  `/tmp/rollingplan-test-*.log` 里解析，别读工具栏里的字面值。
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
