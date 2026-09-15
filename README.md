# RollingPlan

一个 PyQt5 桌面应用，实现「计划自动滚动分配」功能。

## 功能

- **计划写入**：输入计划列表（可自由编辑）+ 自定义每天时间段（数量+名称，可上下移）+ 开始日期
- **自动分配**：按时间段数切片到日历
- **执行界面**：显示当天时间段 + 额外轮（滚动产生）
- **滚动控制**：
  - 向前滚动 = 从明天借 1 个时间段到今天的额外轮（连点 N 次可借 N 个）
  - 向后滚动 = 把额外轮最后 1 个推回明天
  - 当天完成 → 推进到下一天
- **数据存储**：使用 QSettings 嵌入式保存

## 使用

```bash
pip install PyQt5
python rollingplan.py
```

## 打包成 exe

```bash
pip install pyinstaller
pyinstaller --onefile --windowed --name RollingPlan rollingplan.py
```

生成的 exe 在 `dist/RollingPlan.exe`。

## 核心逻辑

见 `PlanScheduler` 类（`rollingplan.py`）：
- `get_day_plans(day_index)`：取第 N 天计划切片
- `get_extra_plans()`：取额外轮（明天前 extra_count 个时间段）
- `roll_forward()` / `roll_backward()`：滚动控制
- `all_plans_consumed()`：判断全部完成

## 测试

```bash
python test_rolling.py
```

覆盖：
- 默认切片分配
- 单次/多次向前滚动
- 推到借完的边界
- 自定义时间段（4 段、count>1）
