# RollingPlan

一个 PyQt5 桌面应用，实现「计划自动滚动分配」功能。

## 版本

### v0.11（当前）
- **每个时段栏加两个小按钮**：
  - **固定计划**：按下后这一格的原定计划**不参与前面时间栏触发的上滚**（它后面的照常参与）
    - 例：早1 中2 晚3，固定「中」，点「早 → 完成并滚动」→ 早3 **📌中2** 晚空（中的 2 没动，晚的 3 挤到早）
  - **拦截滚动**：按下后这一格**及往后**都不参与上滚
    - 例：同上但拦截「中」→ 早空 📌中2 📌晚3（中晚都锁住，早空出来的位置没人补）
    - 拦截「晚」→ 早2 中空 ⛔晚3（晚不动，中的 2 挤到早）
  - 两个都是可切换的小按钮，按下时行首显示 📌 / ⛔ 标记；再按一次取消
  - 腾出来的位置仍然**只由额外轮补**（不会从第二天拉计划）
- 完成的格子会顺手解开它的固定/拦截（不然它一直占着不动）
- 固定 / 拦截随天切换归零（它们是「今天」的设置）
- 新增 `test_scroll_v11.py`：132 断言（取代 v0.10 的 93 断言版本）

### v0.10
- **「完成」拆成两个动作**（v0.9 只有一种，且会从第二天拉计划）：
  - **仅完成**：这一格标记完成 —— 计划留在格里（灰字 + 删除线 + ✓），记进该时段的归档备注，按钮变灰，**后面的计划不滚动**
  - **✓ 完成并滚动**：归档这一格，后面的整体上滚一格
  - 按过「仅完成」的格子，之后还能按「完成并滚动」（= 解开这一格让它滚；归档和备注不会重复记）
- **腾出来的最后一格只由额外轮补**：额外轮为空就空着，**绝不把第二天的计划滚上来**
  - 例：早1 中2 晚3，点「早 → 完成并滚动」→ 早2 中3 **晚空**（不是晚4）；有额外轮 [4] 时 → 早2 中3 晚4
- **每格各自的归档备注**：行尾显示该时段栏已完成过的内容（小灰字「归档：1、4」）
- 修一个 UI 细节：刷新时旧控件原先只 `deleteLater()`，要等事件循环才真正脱离控件树（测试会抓到旧的按钮）；改成 `setParent(None)` + `deleteLater()`
- 新增 `test_scroll_v10.py`：93 断言（取代 v0.9 的 99 断言版本）

### v0.9
- **重写「完成并滚动」的语义**（v0.8 的实现是错的）：
  - v0.8 的行为：点「早1 完成」→ 它去**借第二天同名的早4** 顶上。结果 早 变成 4，任务4 同时出现在第 1 天和第 2 天，再点一次几乎没反应但背地里又借一条。
  - v0.9 的行为：计划是一列**待办队列**，时段只是「当天承装队列的栏位」。完成 = 把这条从队列里拿走（归档），后面的整体上滚一格 → 早2 中3 晚4，第 2 天跟着变成 5/6/7（不重复、不丢）。
  - 新增 `today_state()`：一次算清今天的行 / 额外轮 / 队列走到哪
  - 新增 `undo_complete()` / `can_undo_complete()`：**「退回」变成一键撤销今天最近一次完成**；今天没完成可撤时，才退额外轮最后一个（按钮文案会跟着变：`↶ 撤销完成` / `⤴ 退回`）
  - 进度跟着走：完成一条，`进度` +1
  - 顶部加一行「🗂 今天已完成：…」，归档了什么看得见
- **额外轮不再带时段名**：时段只是当天的栏位，不是计划本身的属性。点「加一个」就是把队列里下一个拉进额外轮（只显示计划内容）；当天有空行时它会滚上来，不在额外轮区重复显示
- **「添加指定」改成按计划挑**：从后面还没安排的计划清单里选一条提前安排（以前是按「时段名」挑，时段只剩栏位意思之后那样很别扭）
- **状态字段变了**（`archived` / `archived_base` / `consumed` 取代 v0.8 的 `completed_today`）；`from_dict` 会把 v0.8 的旧存档自动迁移过来
- 制定页的「计划预览」改用 `raw_calendar()`（铺开看计划怎么分，不受进度影响）；执行页的「计划日历」从今天起往后看
- 新增 `test_scroll_v09.py`：85 断言

### v0.8
- **暗色主题文字对比度修复**：
  - 问题：暗色下槽位的计划名渲染成黑字（非额外安排槽位被硬写 `color: black`），进度标签的 `gray`（`#808080`）在黑底上不可见，toolbutton / label 上一堆 inline `color: #888` 也和 QSS 打架
  - 修法：删掉**所有** widget 级硬编码文字色 —— 文字色统一交给 QSS（DARK_QSS `#cccccc` / LIGHT_QSS `#222222`），widget 级只保留背景色和边框色
  - `(无)` 占位文字改用 italic，不再用灰色
- **字号整体加大**：默认 11pt → 13pt，日期 14pt → 18pt，时段 / 计划名 14pt → 16pt
- **完成并滚动（complete-and-scroll）**：今天某个时段右侧出现「✓ 完成」按钮 —— 点一下把该槽位的当前计划归档，未来同名时段的下一条计划立刻滚上来（这就是「滚动计划」的手感）；没得借则显示空
  - 新增 `ParentPlan.completed_today`、`PlanScheduler.complete_today_slot()` / `can_complete_today_slot()`
  - `completed_today` 随 `to_dict` / `from_dict` 持久化；`on_next_day` 和 `reset_progress` 都会清空它
- 新增 `test_complete_v08.py`：29 断言

### v0.7
- **自写 QSS 主题（弃用 pyqtdarktheme）**：
  - 弃用原因：pyqtdarktheme 在 PyInstaller --onefile --windowed 打包后主题切换无效果（无异常无日志，setup_theme() 静默 no-op）
  - 改为 ~30 行自写 QSS（DARK_QSS / LIGHT_QSS），覆盖 QWidget / QMainWindow / QLabel / QLineEdit / QListWidget / QComboBox / QPushButton / QToolButton / QTabWidget / QTabBar（带选中对比度修复） / QGroupBox / QScrollBar / QMenu / QMessageBox / QProgressBar / QCheckBox / QRadioButton / QStatusBar
  - 仍保留 widget 级 inline stylesheet（主操作蓝底 #2196F3 / 完成绿底 #4CAF50 / 额外安排浅绿 #E8F5E9）
  - auto 主题：Windows 走注册表 `AppsUseLightTheme`，macOS 走 defaults
  - 打包小 ~5MB，无外部依赖
- **v0.6 冷调极简 UI**（保留）：
  - 制定计划页：分类列表 / 计划清单 / 时段 三个 GroupBox 默认收起，点击标题展开（QToolButton 手动控制 visibility）
  - 执行计划页：底部「更多 ▾」折叠区收纳次要操作（退回 / 添加指定 / 额外安排 / 计划日历）
  - 执行页主区「今天」居中 + 两个大按钮（蓝底+加一个 / 绿底今天完成）
  - 主题下拉框在制定页 + 执行页都可见
- **v0.5/v0.6.1/v0.6.2 调试日志**：
  - `~/.hermes_cache/rollingplan_debug.log`（滚动 512KB×2）
  - 解决 `--windowed` 下 sys.stderr=None 抛 AttributeError（_log 全 try/except）

### v0.6
- **冷调极简 UI**：
  - 制定计划页：分类列表 / 计划清单 / 时段 三个 GroupBox 默认收起，点击标题展开（QToolButton 手动控制 visibility，绕开 pyqtdarktheme 下 QGroupBox checkable 不生效的问题）
  - 执行计划页：底部「更多 ▾」折叠区收纳次要操作（退回 / 添加指定 / 额外安排 / 计划日历）
  - 执行计划页：「今天」时段垂直居中显示（`Qt.AlignCenter`），主操作按钮紧贴底部
  - 执行计划页：主操作按钮加大（`minHeight=50` + 圆角 6px + 内边距 14px）
  - 执行计划页：时段字号加大到 14pt
- **执行页主题切换**：从制定页下沉到执行页（两页都能切），QSettings 共享

### v0.5
- **三主题切换**：DarkFlat / LightClean / System(跟随系统),通过 `pyqtdarktheme` 实现
- 主题切换入口：制定计划页左上角下拉框，实时生效
- 选择跨会话持久化（QSettings `RollingPlan/theme`）
- Tab 文字对比度修复（pyqtdarktheme dark 主题默认未激活 Tab 文字过暗）
- 缺 `pyqtdarktheme` 时静默回退到默认 Fusion 样式

### v0.4
- **导入 JSON**：📥 按钮 — 从 JSON 文件加载并覆盖当前数据。先校验结构（parents / plans / time_slots 等基础字段），失败给出具体原因；版本号不匹配拒收。
- **导出 JSON**：📤 按钮 — 导出当前所有分类为 JSON（含 `version` + `exported_at` 时间戳 + `data` 段）。默认文件名 `RollingPlan_backup_YYYY-MM-DD.json`。
- **重置当前分类进度**：🔄 按钮 — 把当前分类的 `current_day` 归 0 + `borrowed_slots` 清空。plans / time_slots / start_date 不变。
- 数据格式向后兼容无 wrapper 的旧版 `to_dict()` 输出。

### v0.3
- **面向普通用户**：所有界面文案改为日常语言（"加一个"替代"借指定时间段"，"分类"替代"母计划"，"时段"替代"时间段"等）
- **加一个**（默认主按钮，蓝底）：自动顺延下一个未完成的计划，不问时段名
- **添加指定**（次要按钮，灰字）：弹对话框选时段名（旧的"借指定"功能保留）
- **退回**（次要按钮）：退掉最后一个额外安排
- **今天完成**（绿底）：进入下一天
- **窗口标题**：「日常计划管理」

### v0.2.1
- **健壮性修复**：
  - 借用判定去重 + 借过再退后能再借
  - 「下一天」按钮增加未完成确认弹窗
  - 借用期间禁止改时间段（避免索引错位）
  - 额外安排视觉强化（背景色 + 左边框 + 颜色加深）
  - 加载失败改为日志输出而非静默

### v0.2
- **多母计划**：每个母计划独立，可并行多个，列表切换
- **借指定时间段**：弹对话框选时间段名（上午/下午/晚上/自定义）
- **链式借**：借完明天的同名时间段，自动从后天借
- 退回 = 把额外轮最后 1 个推回去
- 母计划进度各自独立

### v0.1
- 计划写入 + 自定义时间段 + 自动分配
- 向前/向后滚动 + 额外轮
- QSettings 嵌入式保存

## 功能

- **母计划**：可多个并行（"工作"、"学习"、"健身"...）
- **子计划**：每个母计划下有自己的子计划列表
- **时间段**：可自定义数量和名称（如"早/中/晚"或"上午/下午/晚上"或"白天/晚上"）
- **执行**：当天时间段展示 + 额外轮（借来的，按借的顺序显示）
- **借指定时间段**：弹对话框选择"今天借哪个时间段"，会从最靠前的未借走的同名槽位借
- **链式借**：明天借空了就从后天借
- **退回**：把额外轮最后 1 个推回去（今天有完成过时，「退回」先用来撤销完成）
- **仅完成**：今天某一格点「仅完成」→ 标记完成、记进该时段备注，后面的计划不滚动
- **完成并滚动**：点「✓ 完成并滚动」→ 归档这一格、后面的整体上滚一格；腾出来的最后一格只由额外轮补
- **固定计划 / 拦截滚动**：每一格两个小按钮 —— 固定住这一格（它不上滚，后面的照常）、
  或从这一格起拦截滚动（这一格及往后都不上滚）
- **时段只是栏位**：时段名只表示「当天第几格」，不代表计划本身；额外轮里的计划不带时段名
- **主题**：暗色 / 亮色 / 跟随系统，自写 QSS，实时切换并跨会话记住
- **数据存储**：使用 QSettings 嵌入式保存

## 使用

```bash
pip install PyQt5
python rollingplan.py
```

## 打包成 Windows exe

**前提**：Windows 上装了 Python 3.10+，且 "Add Python to PATH" 已勾选。

**方法 1（推荐）**：双击 `build_windows.bat`，自动装依赖 + 打包
**方法 2**：手动执行
```cmd
pip install PyQt5 pyinstaller
pyinstaller --onefile --windowed --name RollingPlan rollingplan.py
```

生成的 exe 在 `dist\RollingPlan.exe`。

## 核心逻辑

见 `PlanScheduler` 类（`rollingplan.py`）：
- `pending()`：待办队列（`plans` 去掉已完成的）
- `today_state()`：今天的行 / 每格是否已完成 / 归档备注 / 额外轮 / 队列走到哪，一次算清
- `get_day_plans(day_index)`：取第 N 天的显示切片
- `get_calendar()` / `raw_calendar()`：执行页日历（从今天往后） / 制定页预览（整段铺开）
- `complete_only_slot(slot_idx)`：仅完成（不滚动）
- `complete_today_slot(slot_idx)`：完成并滚动（归档 + 上滚）
- `can_complete_only()` / `can_complete_today_slot()`：上面两个能不能点
- `undo_complete()` / `can_undo_complete()`：撤销今天最近一次完成（两种都算）
- `toggle_fixed(slot_idx)` / `toggle_blocked(slot_idx)`：固定计划 / 拦截滚动（可切）
- `borrow_next()` / `borrow_plan(计划)`：加一个 / 添加指定（进额外轮）
- `available_pick_plans()`：添加指定的候选（后面还没安排的计划，去重）
- `borrow_slot(name)` / `available_borrow_names()`：v0.3~v0.8 的按时段名入口，UI 已不用（保留给旧调用和回归测试）
- `return_last_borrowed()`：退回额外轮最后一个
- `get_progress()`：进度（已推进 / 总数，完成的也算）
- `all_consumed()`：判断全部完成

## 测试

```bash
python test_v2_2.py                 # v0.3 核心逻辑（33 断言）
python test_import_export_v04.py    # v0.4 导入/导出（49 断言）
python test_reset_v04.py            # v0.4 重置进度（24 断言）
python test_theme_v05.py            # v0.7 QSS 主题（38 断言）
python test_minimal_v06.py          # v0.6 极简 UI 折叠（32 断言）
python test_scroll_v11.py           # v0.11 仅完成/完成并滚动/固定/拦截（132 断言）
```

共 6 个文件 / 308 断言，全过。

覆盖：
- 单母计划 + 借指定时间段
- 链式借（借完明天同名，自动借后天）
- 同时间段 count>1 时借的边界
- 多母计划独立
- 导入/导出 round-trip
- JSON 结构校验失败处理（语法错/缺字段/类型错/版本不匹配）
- 旧格式向后兼容
- 重置进度保留 plans/time_slots/start_date
- 多分类隔离（只重置当前分类）
- 三主题切换 + QSettings 持久化
- 冷调极简 UI：折叠分组 + 时段居中 + 大按钮
