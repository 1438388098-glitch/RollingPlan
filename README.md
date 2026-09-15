# RollingPlan

一个 PyQt5 桌面应用，实现「计划自动滚动分配」功能。

## 版本

### v0.7（当前）
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
- **退回**：把额外轮最后 1 个推回去
- **数据存储**：使用 QSettings 嵌入式保存

## 使用

```bash
pip install PyQt5 pyqtdarktheme
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
- `get_day_plans(day_index)`：取第 N 天计划切片
- `get_extra_plans()`：取额外轮（按借的顺序）
- `_future_slot_positions()`：未来可借的位置（day > current_day）
- `can_borrow_slot(slot_name)` / `borrow_slot(slot_name)`：借指定时间段
- `return_last_borrowed()`：退回最后借的
- `all_consumed()`：判断全部完成

## 测试

```bash
python test_v2_2.py                 # v0.3 核心逻辑（30 断言）
python test_import_export_v04.py    # v0.4 导入/导出（49 断言）
python test_reset_v04.py            # v0.4 重置进度（24 断言）
python test_theme_v05.py            # v0.5 主题切换（17 断言）
python test_minimal_v06.py          # v0.6 极简 UI 折叠（32 断言）
```

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
