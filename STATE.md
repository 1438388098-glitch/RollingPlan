# RollingPlan — 当前工作状态

> **最后更新**：2026-09-15 14:30
> **会话位置**：`D:\0-task\rollingplan`（验收副本） / `D:\0_git\RollingPlan`（git 仓库）
> **远程**：本地领先 origin/main 4 个 commit（未 push）

## 项目一句话

PyQt5 桌面应用。**v0.4 已完成**：「日常计划管理」——多分类（工作/学习/健身...）的计划按天滚动分配，支持自动顺延加一个额外安排 + 指定时段添加 + **导入/导出 JSON 备份**。

## 当前版本

**v0.4** — commit 待提交 on `main`

### v0.4 核心改动（已落地）
- **导出 JSON**（📤 按钮，制定计划页右上角）：含 `version="0.4"` + `exported_at` ISO 时间戳 + `data` 段。默认文件名 `RollingPlan_backup_YYYY-MM-DD.json`。
- **导入 JSON**（📥 按钮）：覆盖当前所有数据；先校验结构（parents/plans/time_slots/类型/版本号），失败给具体原因；**确认弹窗**显示分类数/计划总数/额外安排数；取消时 `data.load()` 回滚。
- 向后兼容无 wrapper 的旧版 `to_dict()` JSON。
- `MainWindow.reload_executor()`：导入成功后重建 executor 引用新 PlanData。
- 新增 `test_import_export_v04.py`：**49 个断言全过**（覆盖 round-trip / 校验失败 / 旧格式 / 回滚）。

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

- **本地**：`main` 分支领先 origin/main 4 个 commit（未 push）
  - `c4d8cc2` v0.3: UI for end users + add_next button as default
  - `13a029c` build_windows.bat: 全英文输出 + CRLF 行尾
  - `b2fe541` v0.2.1: 健壮性修复
  - `9dc7387` Add build_windows.bat
  - `3eac8e1` v0.2: 多母计划 + 借指定时间段 + 链式借
  - `254442a` Initial commit: RollingPlan v0.1
  - + `f44e944` STATE.md
  - + 待提交: v0.4 import/export

- **验收副本**：`D:\0-task\rollingplan\`（每次新会话开始时从此处复制运行）
  - `rollingplan.py` (44257 字节)
  - `test_v2_2.py` (9191 字节)
  - `test_import_export_v04.py` (11756 字节)
  - `README.md` (~3300 字节)
  - `build_windows.bat` (1415 字节)
  - `.gitignore` (138 字节)
  - **构建残留未清**：`build/` `dist/` `RollingPlan.spec`（下次构建前先删）

## 测试状态

**总计 79 个断言全过**：
- `test_v2_2.py`：**30 断言**（v0.3 核心）
- `test_import_export_v04.py`：**49 断言**（v0.4 导入/导出）

v0.4 测试覆盖：
- export_to_dict 结构（三层 wrapper）
- round-trip 字段一致（含 borrowed_slots + current_parent_idx）
- 空 PlanData 边界
- 校验失败：文件不存在 / JSON 语法错 / 根非 dict / 缺 parents / parents 空 / 单 parent 缺字段 / plans 内非字符串 / 版本不匹配
- 旧格式（无 wrapper）向后兼容
- 取消时回滚（data.load() 恢复）

## 文件关键路径（WSL 视角）

| 用途 | 路径 |
|------|------|
| Git 仓库 | `/mnt/d/0_git/RollingPlan/` |
| 验收副本 | `/mnt/d/0-task/rollingplan/` |
| Python venv | `/mnt/d/0-task/rollingplan/.venv/` |
| 启动测试 | `cd /mnt/d/0-task/rollingplan && QT_QPA_PLATFORM=offscreen .venv/bin/python test_import_export_v04.py` |

## 还没做的方向（按之前提的）

1. **修 bug 9 项** ✅ 已全部落地（v0.2.1）
2. **UX 打磨** — v0.3 完成大部分文案重写；额外轮视觉已强化
3. **打包/发布** — `build_windows.bat` 已就绪，**build + 启动运行均验证通过**（9/15 验收）
4. **新功能**（v0.4 已做导入导出；未做）：
   - 重置当前分类进度
   - 快捷键（Ctrl+Enter 加一个 / Ctrl+D 今天完成 / Ctrl+Z 退回）
   - 撤销栈
5. **代码重构**（未做）：单文件 1200+ 行可拆 `model.py` / `scheduler.py` / `editor.py` / `executor.py`

## 下次新会话该做什么

**选项 B 续**：从「还没做的方向 4」里选下一个新功能
- 重置进度（最简单，~30 行）
- 快捷键（中等，UI 复杂度高一点）

**选项 C**：重构分模块
- 读这个 STATE.md 就知道当前状态，按 5 个模块拆

## 备忘

- WSL 没 Qt 显示，要验证 GUI 只能用 `QT_QPA_PLATFORM=offscreen` 跑 headless
- `borrowed_slots` 是 JSON 字段名，重构时**不能改**（会破坏已存数据）
- 内部 docstring 还保留"母计划/子计划/借"等术语（变量名 + 注释）— 这些不影响 UI
- 测试文件名 `test_v2_2.py` 是历史遗留（README 里写的），保留不动
- v0.4 导入是**覆盖语义**（不是合并），`borrowed_slots` 一并带过来——切换设备/恢复备份场景更直觉
- v0.4 导入校验失败的错误信息是中文，对用户友好；开发者看也能定位问题
