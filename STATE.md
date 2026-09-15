# RollingPlan — 当前工作状态

> **最后更新**：2026-09-15 21:45
> **会话位置**：`D:\0-task\rollingplan`（验收副本） / `D:\0_git\RollingPlan`（git 仓库）
> **远程**：`origin/main` == `main` == `04f6393`（13 commits 已于 2026-09-15 21:40 push，无未推提交）

## 项目一句话

PyQt5 桌面应用。**v0.8 已完成**：「日常计划管理」——多分类（工作/学习/健身...）的计划按天滚动分配，支持自动顺延加一个额外安排 + 指定时段添加 + 点一下完成让后续计划滚上来 + 导入/导出 JSON 备份 + 重置当前分类进度 + 三主题切换（自写 QSS）+ 冷调极简 UI（折叠分组 + 居中主区 + 大按钮）。

## 当前版本

**v0.8** — 16 commits on `main`，已全部 push

### v0.8 核心改动（已落地）

用户反馈（v0.7 之后）：
- 暗色主题下文字看不见（看书/刷题/复习 渲染成黑字压在黑底上）
- 全局字号偏小
- 缺「点一下完成 → 下一条滚上来」的滚动感

根因：`_add_slot_row()` 对非额外安排槽位硬写了 `plan_label.setStyleSheet('color: black')`，`progress_label` 硬写 `color: gray`（`#808080` 在暗底上不可见），加上 toolbutton / label 上一堆 inline `color: #888` / `gray` 全部和 QSS 的文字色打架。

修复：
- 删掉所有 widget 级硬编码文字色，只留背景色和边框色 —— 文字色统一交给 QSS（DARK_QSS `QLabel { color: #cccccc }` / LIGHT_QSS `color: #222222`）
- 默认字号 11pt → 13pt；`date_label` 14pt → 18pt；`slot_label` / `plan_label` 14pt → 16pt
- `(无)` 占位文字改用 italic，不再用灰色
- `progress_label` / 折叠按钮 / 「更多」按钮的文字色都改为主题托管

新功能 完成并滚动（complete-and-scroll）：
- 新增 `ParentPlan.completed_today: list[slot_idx]`
- 新增 `PlanScheduler.complete_today_slot(slot_idx)` / `can_complete_today_slot()` —— 把 `(current_day, slot_idx)` 标记为已归档，并立刻 `borrow_slot(sname)` 去未来取同名时段的下一条计划
- `get_day_plans()` 更新：若 `slot_idx in completed_today`，按顺序查 `borrowed_slots`，用同意时段名的下一条借来的计划顶替原计划（这就是「滚上来」的效果）；没得借就渲染空
- `on_next_day` 清空 `completed_today`；`to_dict` / `from_dict` 持久化 `completed_today`；`reset_progress` 也清空
- `_add_slot_row()` 在 `show_complete=True` 且 plan 非空时（只限今天的槽位）右侧加一个「✓ 完成」按钮；新增 `on_complete_slot(slot_idx)` 处理器

### v0.7 核心改动（已落地）

- **自写 QSS 主题（弃用 pyqtdarktheme）**：v0.5/v0.6 的 exe 里主题切换静默失效 —— `qdarktheme.setup_theme()` 在 PyInstaller `--onefile --windowed` 下 no-op（无异常、无日志、UI 不变，疑似 `_os_appearance` 模块访问方式和 onefile 解包布局不匹配）。改为自写 `DARK_QSS` / `LIGHT_QSS`（各 30+ 行），覆盖 QWidget / QMainWindow / QLabel / QLineEdit / QListWidget / QComboBox / QPushButton / QToolButton / QTabWidget / QTabBar（带选中态对比度修复） / QGroupBox / QScrollBar / QMenu / QMessageBox / QProgressBar / QCheckBox / QRadioButton / QStatusBar
- 新增 `_detect_system_theme()` 处理 auto（Windows 走注册表 `AppsUseLightTheme`，macOS 走 `defaults`）
- widget 级 inline stylesheet（主操作 `#2196F3` 蓝底 / 完成 `#4CAF50` 绿底 / 额外安排 `#E8F5E9` 浅绿）仍在、优先级高于 QSS —— QSS 只管通用 widget
- `build_windows.bat` 去掉 `pip install pyqtdarktheme` 和 `--collect-all qdarktheme`（包小 ~5MB，运行时无外部依赖）
- `test_theme_v05.py` 重写为 QSS 版本：38 断言（原 17）

### v0.6 核心改动（已落地）

- **冷调极简 UI**：制定计划页三个 GroupBox（分类列表/计划清单/时段）默认收起，用 QToolButton 手动控制 visibility（绕开 pyqtdarktheme 下 QGroupBox checkable 不生效的坑）
- **执行计划页底部「更多 ▾」**：收纳退回 / 添加指定 / 额外安排 / 计划日历等次要操作
- **「今天」主区垂直居中**：日期+进度靠上，时段居中显示，主操作按钮紧贴底部
- **主操作按钮加大**：minHeight=50 + 圆角 6px + 内边距 14px + 字号 14pt
- **时段字号加大到 14pt**
- **执行页主题切换**：从制定页下沉到执行页，两页都能切
- 新增 `test_minimal_v06.py`：32 个断言

### v0.5 核心改动（已落地）

- **三主题切换**：DarkFlat / LightClean / System（跟随系统）
- **主题切换入口**：制定计划页左上角下拉框，实时生效
- **跨会话持久化**：QSettings `RollingPlan/theme`
- **Tab 文字对比度修复**：dark 主题默认未激活 Tab 文字几乎不可见，改用具体颜色（dark: `#E0E0E0` / `#1E88E5`，light: `#424242` / `#1976D2`）
- **缺 pyqtdarktheme 静默回退**：try/except ImportError + 默认 Fusion 样式（**v0.7 起此依赖已移除，本节仅存历史**）

### v0.4 核心改动（已落地）

- **导出 JSON**（📤 按钮，制定计划页右上角）：含 `version="0.4"` + `exported_at` ISO 时间戳 + `data` 段。默认文件名 `RollingPlan_backup_YYYY-MM-DD.json`。
- **导入 JSON**（📥 按钮）：**覆盖语义**（不是合并）；先校验结构（parents/plans/time_slots/类型/版本号），失败给具体原因；**确认弹窗**显示分类数/计划总数/额外安排数；取消时 `data.load()` 回滚。
- **重置当前分类进度**（🔄 按钮）：`current_day=0` + `borrowed_slots=[]`，plans/time_slots/start_date 不变。已是初始状态时弹"无需重置"提示。
- 向后兼容无 wrapper 的旧版 `to_dict()` JSON。
- `MainWindow.reload_executor()`：导入/重置后重建 executor 引用新 PlanData。
- `ParentPlan.reset_progress()`：单分类进度归零的方法。
- 新增 2 个测试文件：`test_import_export_v04.py`（49 断言）+ `test_reset_v04.py`（24 断言）。

### v0.3 核心改动（已落地）

- UI 文案全面口语化：母计划→分类、子计划→计划、时间段→时段、额外轮→额外安排
- **按钮布局重构**：
  - `[➕ 加一个]`（蓝底主按钮，默认操作）— `borrow_next()`，自动顺延下一未完成
  - `[⤴ 退回]`（次要）— `return_last_borrowed()`
  - `[✓ 今天完成]`（绿底主按钮）— `on_next_day()`
  - `[⋯ 添加指定]`（灰字次要）— `borrow_slot(name)`，弹框选时段
- 新增 `scheduler.borrow_next() / can_borrow_next()`
- 窗口标题改为「日常计划管理」

### v0.2.1 健壮性修复（已落地）

- 借用判定去重（`_borrowed_set()` helper）+ 借过再退后能再借
- 「下一天」增加未完成确认弹窗（入口改名为「✓ 今天完成」→ 弹窗「进入明天」）
- 借用期间禁止改时段（`PlanData.has_borrowed()`）
- 额外安排视觉强化（背景色 `#E8F5E9` + 左边框 3px + 深绿文字 `#1B5E20`）
- `load()` 失败从静默改日志输出 + 类型校验
- `build_windows.bat` 全英文 + CRLF（修 GBK 编码乱码）

### v0.2 基础功能（已落地）

- 多分类 + 借指定时段 + 链式借 + 退回 + QSettings 持久化

## 仓库状态

- **`main`**：`04f6393`（v0.8），16 个 commit，**已 push，与 origin/main 一致**
- **远程**：https://github.com/704315792-crypto/RollingPlan.git
- **13 commits 于 2026-09-15 21:40 一次推完**（`9dc7387..04f6393`），覆盖 v0.2.2 起直到 v0.8 的全部工作

- **验收副本**：`D:\0-task\rollingplan\`（每次新会话开始时从此处运行 / 打包）
  - 与 git 仓库的文件已逐一对齐（rollingplan.py / README.md / STATE.md / build_windows.bat / 6 个测试文件）
  - `.venv`：PyQt5 5.15.11（**v0.7 起不再需要 pyqtdarktheme**）
  - `dist/RollingPlan.exe`：v0.8，37,841,798 字节，构建于 2026-09-15 21:20
  - `build/` `dist/` `RollingPlan.spec` 是构建产物，`.gitignore` 里已忽略，只存在于验收副本

## 测试状态

**6 个测试文件 / 总计 205 个断言全过，0 失败**（2026-09-15 21:44 于验收副本 .venv 实测）

| 测试文件 | 断言 | 覆盖 |
|----------|------|------|
| `test_v2_2.py` | **33** | v0.3 核心逻辑（借指定 / 链式借 / 退回 / 多分类独立） |
| `test_import_export_v04.py` | **49** | v0.4 导入/导出 + 结构校验 + 旧格式兼容 |
| `test_reset_v04.py` | **24** | v0.4 重置进度（保留 plans/time_slots/start_date，多分类隔离） |
| `test_theme_v05.py` | **38** | v0.7 QSS 主题（DARK_QSS / LIGHT_QSS 内容 + QSettings 持久化 + stderr=None 不崩） |
| `test_minimal_v06.py` | **32** | v0.6 极简 UI 折叠 + 主区居中 + 大按钮 |
| `test_complete_v08.py` | **29** | v0.8 完成并滚动（借来的滚上来 / 没得借显示空 / completed_today 持久化 / 重置清空 / UI 点 3 个 ✓ 完成 后滚上来） |

跑法：
```bash
cd /mnt/d/0-task/rollingplan
QT_QPA_PLATFORM=offscreen .venv/bin/python test_complete_v08.py
```

## 文件关键路径（WSL 视角）

| 用途 | 路径 |
|------|------|
| Git 仓库 | `/mnt/d/0_git/RollingPlan/` |
| 验收副本 | `/mnt/d/0-task/rollingplan/` |
| Python venv | `/mnt/d/0-task/rollingplan/.venv/` |
| 主程序 | `/mnt/d/0_git/RollingPlan/rollingplan.py`（1869 行 / 68445 字节） |
| 构建脚本 | `/mnt/d/0_git/RollingPlan/build_windows.bat` |

## 还没做的方向（按之前提的）

1. **修 bug 9 项** ✅ 已全部落地（v0.2.1）
2. **UX 打磨** ✅ v0.3 文案重写 + v0.5/v0.7 主题 + v0.6/v0.8 布局与对比度
3. **打包/发布** ✅ `build_windows.bat` 就绪（v0.7 起无 pyqtdarktheme 依赖）；exe 构建 + 启动均验证通过
4. **新功能**（v0.4 导入导出+重置、v0.5/v0.7 主题、v0.8 完成并滚动 已做；**未做**）：
   - 快捷键（Ctrl+Enter 加一个 / Ctrl+D 今天完成 / Ctrl+Z 退回）
   - 撤销栈
   - **布局重设计**（执行页只显示「今天 + 加一个/今天完成」）
   - **今日模式**（独立第三页）
5. **代码重构**（未做）：单文件 1869 行可拆 `model.py` / `scheduler.py` / `editor.py` / `executor.py` / `theme.py`

## 下次新会话该做什么

**前置**：无需 push（已同步）。直接读本文件即可接着干。

**选项 A**：从「还没做的方向 4」里挑下一个新功能
- 快捷键（中等，改动小、见效快）
- 布局重设计（中等）
- 今日模式（中等）

**选项 B**：重构分模块（读本文件即可，按 5 个模块拆 model/scheduler/editor/executor/theme）

**选项 C**：先找用户确认 v0.8 的暗色对比度修复在真机（Windows 上双击 exe）是否达到预期 —— v0.8 的改动只跑过 headless 测试，视觉部分没有真机确认

## 备忘

- WSL 没 Qt 显示，要验证 GUI 只能用 `QT_QPA_PLATFORM=offscreen` 跑 headless
- **QSS 与 widget 级 inline stylesheet 的关系**：widget 级 inline 优先于 QSS。所以**文字色绝对不要写在 widget 级 stylesheet 里**（v0.8 的暗色黑字事故就是这个），widget 级只写背景色 / 边框色
- `borrowed_slots` / `completed_today` 是 JSON 字段名，重构时**不能改**（会破坏已存数据）
- 内部 docstring 还保留"母计划/子计划/借"等术语（变量名 + 注释）— 这些不影响 UI
- 测试文件名 `test_v2_2.py` 是历史遗留（README 里写的），保留不动
- v0.4 导入是**覆盖语义**（不是合并），`borrowed_slots` / `completed_today` 一并带过来
- **WSL/DrvFS I/O 坑**：`dist/*.exe` 这类大文件在 WSL 里 rm 偶尔报 Input/output error，Windows 端 `del` 也可能拒绝访问。绕过办法：Windows 资源管理器手动删
- **pyqtdarktheme 的坑（历史）**：必须 `--collect-all qdarktheme`，且 onefile 下 setup_theme() 仍可能静默失效 —— v0.7 直接自写 QSS 绕开了整个依赖
- **auto 主题在 WSL offscreen 下 darkdetect 会卡**——测试只测 dark/light，不测 auto
- **QGroupBox checkable 不可靠**（pyqtdarktheme 时代）——v0.6 起改用 QToolButton 手动控制 body widget 的 visibility
- **isVisible() 检查时父链必须至少一层可见**：构造 widget 但不 show()，所有子 widget 的 isVisible() 都返回 False。测试时必须 widget.show() + processEvents()
