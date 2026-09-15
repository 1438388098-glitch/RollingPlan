# RollingPlan

一个 PyQt5 桌面应用，实现「计划自动滚动分配」功能。

## 版本

### v0.4（当前）
- **导入 JSON**：📥 按钮 — 从 JSON 文件加载并覆盖当前数据。先校验结构（parents / plans / time_slots 等基础字段），失败给出具体原因；版本号不匹配拒收。
- **导出 JSON**：📤 按钮 — 导出当前所有分类为 JSON（含 `version` + `exported_at` 时间戳 + `data` 段）。默认文件名 `RollingPlan_backup_YYYY-MM-DD.json`。
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
- `get_day_plans(day_index)`：取第 N 天计划切片
- `get_extra_plans()`：取额外轮（按借的顺序）
- `_future_slot_positions()`：未来可借的位置（day > current_day）
- `can_borrow_slot(slot_name)` / `borrow_slot(slot_name)`：借指定时间段
- `return_last_borrowed()`：退回最后借的
- `all_consumed()`：判断全部完成

## 测试

```bash
python test_v2_2.py          # v0.3 核心逻辑（30 断言）
python test_import_export_v04.py   # v0.4 导入/导出（49 断言）
```

覆盖：
- 单母计划 + 借指定时间段
- 链式借（借完明天同名，自动借后天）
- 同时间段 count>1 时借的边界
- 多母计划独立
- 导入/导出 round-trip
- JSON 结构校验失败处理（语法错/缺字段/类型错/版本不匹配）
- 旧格式向后兼容
