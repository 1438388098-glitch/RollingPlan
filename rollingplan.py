"""
RollingPlan — 计划自动滚动程序

功能：
1. 写入界面：输入计划列表 + 自定义时间段 + 开始日期，自动生成计划表
2. 执行界面：显示当天时间段，提供额外轮，支持向前/向后滚动
3. 滚动后：后续所有天按原始时间段自动重新填充

技术栈：PyQt5 + 内置数据存储（QSettings 嵌入式）
"""

import sys
import json
from datetime import datetime, timedelta
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QListWidget, QListWidgetItem,
    QSpinBox, QDateEdit, QTextEdit, QMessageBox, QTabWidget,
    QGroupBox, QInputDialog
)
from PyQt5.QtCore import Qt, QDate, QSettings
from PyQt5.QtGui import QFont, QColor


# ============== 数据模型 ==============

class PlanData:
    """计划数据模型 - 嵌入式存储"""

    def __init__(self):
        self.plans = []           # 计划列表 ["a", "b", "c", ...]
        self.time_slots = []      # 时间段列表 [{"name": "上午", "count": 1}, ...]
        self.start_date = None    # 开始日期 QDate
        self.current_day = 0      # 当前是第几天（0-indexed），由用户滚动控制
        self.extra_count = 0      # 额外轮数量（从明天借过来的时间段数）

    def add_plan(self, text):
        if text.strip():
            self.plans.append(text.strip())

    def remove_plan(self, index):
        if 0 <= index < len(self.plans):
            self.plans.pop(index)

    def update_plan(self, index, text):
        if 0 <= index < len(self.plans):
            self.plans[index] = text.strip()

    def to_dict(self):
        return {
            "plans": self.plans,
            "time_slots": self.time_slots,
            "start_date": self.start_date.toString("yyyy-MM-dd") if self.start_date else None,
            "current_day": self.current_day,
            "extra_count": self.extra_count,
        }

    def from_dict(self, data):
        self.plans = data.get("plans", [])
        self.time_slots = data.get("time_slots", [])
        sd = data.get("start_date")
        self.start_date = QDate.fromString(sd, "yyyy-MM-dd") if sd else None
        self.current_day = data.get("current_day", 0)
        self.extra_count = data.get("extra_count", 0)

    def save(self):
        settings = QSettings("RollingPlan", "Data")
        settings.setValue("plan_data", json.dumps(self.to_dict()))

    def load(self):
        settings = QSettings("RollingPlan", "Data")
        data = settings.value("plan_data")
        if data:
            try:
                self.from_dict(json.loads(data))
                return True
            except Exception:
                pass
        return False


# ============== 核心调度逻辑 ==============

class PlanScheduler:
    """计划调度器 - 把计划按时间段切片到日历，支持滚动"""

    def __init__(self, data: PlanData):
        self.data = data

    def slots_per_day(self):
        """每天时间段总数"""
        return sum(slot.get("count", 1) for slot in self.data.time_slots)

    def get_day_plans(self, day_index):
        """
        获取第 day_index 天的计划切片
        返回: [(时间段名, 计划内容或None), ...]
        """
        spd = self.slots_per_day()
        if spd == 0:
            return []

        start_idx = day_index * spd
        end_idx = start_idx + spd
        raw = self.data.plans[start_idx:end_idx]

        # 展开时间段
        result = []
        plan_idx = 0
        for slot in self.data.time_slots:
            for _ in range(slot.get("count", 1)):
                if plan_idx < len(raw):
                    result.append((slot["name"], raw[plan_idx]))
                    plan_idx += 1
                else:
                    result.append((slot["name"], None))
        return result

    def get_calendar(self):
        """生成完整日历"""
        if not self.data.start_date:
            return []
        spd = self.slots_per_day()
        if spd == 0:
            return []
        total_days = (len(self.data.plans) + spd - 1) // spd
        calendar = []
        for i in range(total_days):
            date = self.data.start_date.addDays(i)
            plans = self.get_day_plans(i)
            calendar.append((date, plans))
        return calendar

    def get_extra_plans(self):
        """
        获取额外轮计划列表
        逻辑：从明天 (current_day + 1) 的前 extra_count 个时间段取
        """
        if self.data.extra_count <= 0:
            return []

        next_day_idx = self.data.current_day + 1
        next_day_plans = self.get_day_plans(next_day_idx)

        # 取前 extra_count 个（按时间段顺序）
        return next_day_plans[:self.data.extra_count]

    def can_roll_forward(self):
        """能否向前滚动：明天还有至少 (extra_count + 1) 个时间段可借"""
        spd = self.slots_per_day()
        if spd == 0:
            return False
        # 明天的计划切片长度
        next_day_plans = self.get_day_plans(self.data.current_day + 1)
        # 借走前 extra_count 个后，还要至少剩 1 个
        return len(next_day_plans) > self.data.extra_count

    def can_roll_backward(self):
        """能否向后滚动：至少要有 1 个额外轮可以推回去"""
        return self.data.extra_count > 0

    def roll_forward(self):
        """向前滚动：从明天多借 1 个时间段到额外轮"""
        if not self.can_roll_forward():
            return False
        self.data.extra_count += 1
        self.data.save()
        return True

    def roll_backward(self):
        """向后滚动：把额外轮最后 1 个推回明天"""
        if not self.can_roll_backward():
            return False
        self.data.extra_count -= 1
        self.data.save()
        return True

    def all_plans_consumed(self):
        """所有计划是否都已用完：
        条件 = 当前天没计划 AND 额外轮也借无可借"""
        spd = self.slots_per_day()
        if spd == 0:
            return True
        day_plans = self.get_day_plans(self.data.current_day)
        day_has_content = any(plan is not None for _, plan in day_plans)
        return not day_has_content and not self.can_roll_forward()

    def is_day_complete(self):
        """当天是否所有时间段都有计划（不算额外轮）"""
        day_plans = self.get_day_plans(self.data.current_day)
        return all(plan is not None for _, plan in day_plans)


# ============== 写入界面 ==============

class PlanEditor(QWidget):
    def __init__(self, data: PlanData, scheduler: PlanScheduler, on_switch_to_exec):
        super().__init__()
        self.data = data
        self.scheduler = scheduler
        self.on_switch_to_exec = on_switch_to_exec
        self.init_ui()
        self.refresh_all()

    def init_ui(self):
        layout = QVBoxLayout()

        title = QLabel("RollingPlan — 计划写入")
        title.setFont(QFont("Microsoft YaHei", 16, QFont.Bold))
        layout.addWidget(title)

        # 计划列表
        plan_group = QGroupBox("计划列表（按顺序）")
        plan_layout = QVBoxLayout()

        self.plan_list = QListWidget()
        self.plan_list.setMaximumHeight(180)
        plan_layout.addWidget(self.plan_list)

        edit_row = QHBoxLayout()
        self.plan_input = QLineEdit()
        self.plan_input.setPlaceholderText("输入计划内容，回车添加")
        self.plan_input.returnPressed.connect(self.add_plan)
        edit_row.addWidget(self.plan_input)

        for text, callback in [
            ("添加", self.add_plan),
            ("编辑选中", self.edit_plan),
            ("删除选中", self.delete_plan),
            ("↑ 上移", self.move_plan_up),
            ("↓ 下移", self.move_plan_down),
        ]:
            btn = QPushButton(text)
            btn.clicked.connect(callback)
            edit_row.addWidget(btn)

        plan_layout.addLayout(edit_row)
        plan_group.setLayout(plan_layout)
        layout.addWidget(plan_group)

        # 时间段
        slot_group = QGroupBox("每天时间段（可自定义）")
        slot_layout = QVBoxLayout()

        self.slot_list = QListWidget()
        self.slot_list.setMaximumHeight(120)
        slot_layout.addWidget(self.slot_list)

        slot_edit_row = QHBoxLayout()
        self.slot_name_input = QLineEdit()
        self.slot_name_input.setPlaceholderText("时间段名（如：上午）")
        slot_edit_row.addWidget(self.slot_name_input)

        self.slot_count_input = QSpinBox()
        self.slot_count_input.setMinimum(1)
        self.slot_count_input.setMaximum(10)
        self.slot_count_input.setValue(1)
        self.slot_count_input.setPrefix("数量:")
        slot_edit_row.addWidget(self.slot_count_input)

        for text, callback in [
            ("添加时间段", self.add_slot),
            ("编辑选中", self.edit_slot),
            ("删除选中", self.delete_slot),
            ("↑ 上移", self.move_slot_up),
            ("↓ 下移", self.move_slot_down),
        ]:
            btn = QPushButton(text)
            btn.clicked.connect(callback)
            slot_edit_row.addWidget(btn)

        slot_layout.addLayout(slot_edit_row)
        slot_group.setLayout(slot_layout)
        layout.addWidget(slot_group)

        # 开始日期
        date_group = QGroupBox("开始日期")
        date_layout = QHBoxLayout()

        self.date_edit = QDateEdit()
        self.date_edit.setCalendarPopup(True)
        self.date_edit.setDate(QDate.currentDate())
        date_layout.addWidget(self.date_edit)
        date_group.setLayout(date_layout)
        layout.addWidget(date_group)

        # 操作按钮
        btn_row = QHBoxLayout()

        save_btn = QPushButton("保存并生成计划表")
        save_btn.setFont(QFont("Microsoft YaHei", 11, QFont.Bold))
        save_btn.clicked.connect(self.save_and_preview)
        btn_row.addWidget(save_btn)

        preview_btn = QPushButton("预览生成结果")
        preview_btn.clicked.connect(self.preview_calendar)
        btn_row.addWidget(preview_btn)

        go_exec_btn = QPushButton("进入执行界面 →")
        go_exec_btn.clicked.connect(self.go_to_exec)
        btn_row.addWidget(go_exec_btn)

        layout.addLayout(btn_row)

        # 预览区
        self.preview_area = QTextEdit()
        self.preview_area.setReadOnly(True)
        self.preview_area.setMaximumHeight(200)
        layout.addWidget(self.preview_area)

        self.setLayout(layout)

    def refresh_all(self):
        self.plan_list.clear()
        for i, plan in enumerate(self.data.plans):
            self.plan_list.addItem(f"{i+1}. {plan}")

        self.slot_list.clear()
        for i, slot in enumerate(self.data.time_slots):
            display = slot["name"]
            if slot.get("count", 1) > 1:
                display += f" x{slot['count']}"
            self.slot_list.addItem(f"{i+1}. {display}")

        if self.data.start_date:
            self.date_edit.setDate(self.data.start_date)

    def add_plan(self):
        text = self.plan_input.text().strip()
        if text:
            self.data.add_plan(text)
            self.plan_input.clear()
            self.refresh_all()

    def edit_plan(self):
        current = self.plan_list.currentRow()
        if current < 0:
            QMessageBox.warning(self, "提示", "请先选中要编辑的计划")
            return
        new_text, ok = QInputDialog.getText(self, "编辑计划", "新内容:", text=self.data.plans[current])
        if ok and new_text.strip():
            self.data.update_plan(current, new_text)
            self.refresh_all()

    def delete_plan(self):
        current = self.plan_list.currentRow()
        if current < 0:
            QMessageBox.warning(self, "提示", "请先选中要删除的计划")
            return
        self.data.remove_plan(current)
        self.refresh_all()

    def move_plan_up(self):
        current = self.plan_list.currentRow()
        if current > 0:
            self.data.plans[current-1], self.data.plans[current] = self.data.plans[current], self.data.plans[current-1]
            self.refresh_all()
            self.plan_list.setCurrentRow(current - 1)

    def move_plan_down(self):
        current = self.plan_list.currentRow()
        if 0 <= current < len(self.data.plans) - 1:
            self.data.plans[current+1], self.data.plans[current] = self.data.plans[current], self.data.plans[current+1]
            self.refresh_all()
            self.plan_list.setCurrentRow(current + 1)

    def add_slot(self):
        name = self.slot_name_input.text().strip()
        count = self.slot_count_input.value()
        if name:
            self.data.time_slots.append({"name": name, "count": count})
            self.slot_name_input.clear()
            self.slot_count_input.setValue(1)
            self.refresh_all()

    def edit_slot(self):
        current = self.slot_list.currentRow()
        if current < 0:
            QMessageBox.warning(self, "提示", "请先选中要编辑的时间段")
            return
        slot = self.data.time_slots[current]
        new_name, ok = QInputDialog.getText(self, "编辑时间段", "新名称:", text=slot["name"])
        if ok and new_name.strip():
            new_count, ok2 = QInputDialog.getInt(self, "编辑时间段", "新数量:", value=slot.get("count", 1), min=1, max=10)
            if ok2:
                self.data.time_slots[current] = {"name": new_name, "count": new_count}
                self.refresh_all()

    def delete_slot(self):
        current = self.slot_list.currentRow()
        if current < 0:
            QMessageBox.warning(self, "提示", "请先选中要删除的时间段")
            return
        self.data.time_slots.pop(current)
        self.refresh_all()

    def move_slot_up(self):
        current = self.slot_list.currentRow()
        if current > 0:
            self.data.time_slots[current-1], self.data.time_slots[current] = self.data.time_slots[current], self.data.time_slots[current-1]
            self.refresh_all()
            self.slot_list.setCurrentRow(current - 1)

    def move_slot_down(self):
        current = self.slot_list.currentRow()
        if 0 <= current < len(self.data.time_slots) - 1:
            self.data.time_slots[current+1], self.data.time_slots[current] = self.data.time_slots[current], self.data.time_slots[current+1]
            self.refresh_all()
            self.slot_list.setCurrentRow(current + 1)

    def save_and_preview(self):
        self.data.start_date = self.date_edit.date()
        self.data.save()
        self.preview_calendar()

    def preview_calendar(self):
        self.data.start_date = self.date_edit.date()
        self.scheduler = PlanScheduler(self.data)

        if not self.data.plans:
            QMessageBox.warning(self, "提示", "请先添加计划")
            return
        if not self.data.time_slots:
            QMessageBox.warning(self, "提示", "请先添加时间段")
            return

        calendar = self.scheduler.get_calendar()
        lines = [f"📅 计划表（共 {len(calendar)} 天）", "=" * 40]

        for i, (date, plans) in enumerate(calendar):
            lines.append(f"\n第 {i+1} 天 ({date.toString('yyyy-MM-dd ddd')}):")
            for slot_name, plan in plans:
                marker = "  ✓ " if plan else "  · "
                content = plan if plan else "(空)"
                lines.append(f"{marker}{slot_name}: {content}")

        self.preview_area.setText("\n".join(lines))

    def go_to_exec(self):
        if not self.data.plans or not self.data.time_slots or not self.data.start_date:
            QMessageBox.warning(self, "提示", "请先完成计划列表/时间段/开始日期的填写")
            return
        self.data.save()
        self.on_switch_to_exec()


# ============== 执行界面 ==============

class PlanExecutor(QWidget):
    def __init__(self, data: PlanData, scheduler: PlanScheduler, on_switch_to_edit):
        super().__init__()
        self.data = data
        self.scheduler = scheduler
        self.on_switch_to_edit = on_switch_to_edit
        self.init_ui()
        self.refresh()

    def init_ui(self):
        layout = QVBoxLayout()

        title = QLabel("RollingPlan — 计划执行")
        title.setFont(QFont("Microsoft YaHei", 16, QFont.Bold))
        layout.addWidget(title)

        info_row = QHBoxLayout()
        self.date_label = QLabel()
        self.date_label.setFont(QFont("Microsoft YaHei", 12, QFont.Bold))
        info_row.addWidget(self.date_label)

        self.progress_label = QLabel()
        info_row.addWidget(self.progress_label)

        info_row.addStretch()

        edit_btn = QPushButton("← 返回编辑")
        edit_btn.clicked.connect(self.on_switch_to_edit)
        info_row.addWidget(edit_btn)

        layout.addLayout(info_row)

        # 当天时间段
        self.day_group = QGroupBox("当天时间段")
        self.day_layout = QVBoxLayout()
        self.day_group.setLayout(self.day_layout)
        layout.addWidget(self.day_group)

        # 额外轮
        self.extra_group = QGroupBox("额外轮（向前滚动后填充）")
        self.extra_layout = QVBoxLayout()
        self.extra_group.setLayout(self.extra_layout)
        layout.addWidget(self.extra_group)

        # 滚动按钮
        roll_row = QHBoxLayout()

        self.roll_backward_btn = QPushButton("← 向后滚动（少做）")
        self.roll_backward_btn.setFont(QFont("Microsoft YaHei", 11))
        self.roll_backward_btn.clicked.connect(self.on_roll_backward)
        roll_row.addWidget(self.roll_backward_btn)

        self.roll_forward_btn = QPushButton("向前滚动（多做）→")
        self.roll_forward_btn.setFont(QFont("Microsoft YaHei", 11))
        self.roll_forward_btn.clicked.connect(self.on_roll_forward)
        roll_row.addWidget(self.roll_forward_btn)

        # 当天完成按钮（推进到下一天）
        next_btn = QPushButton("✓ 当天完成 → 下一天")
        next_btn.setFont(QFont("Microsoft YaHei", 11))
        next_btn.setStyleSheet("background-color: #4CAF50; color: white;")
        next_btn.clicked.connect(self.on_next_day)
        roll_row.addWidget(next_btn)

        layout.addLayout(roll_row)

        # 日历预览
        cal_group = QGroupBox("完整日历预览")
        cal_layout = QVBoxLayout()
        self.calendar_area = QTextEdit()
        self.calendar_area.setReadOnly(True)
        self.calendar_area.setMaximumHeight(180)
        cal_layout.addWidget(self.calendar_area)
        cal_group.setLayout(cal_layout)
        layout.addWidget(cal_group)

        self.setLayout(layout)

    def _add_slot_row(self, parent_layout, slot_name, plan, is_extra=False):
        row = QHBoxLayout()

        prefix = "⤴ " if is_extra else ""
        color = "#2E7D32" if is_extra else "black"

        slot_label = QLabel(f"{prefix}{slot_name}:")
        slot_label.setMinimumWidth(120 if is_extra else 80)
        slot_label.setFont(QFont("Microsoft YaHei", 10, QFont.Bold))
        slot_label.setStyleSheet(f"color: {color};")
        row.addWidget(slot_label)

        plan_label = QLabel(plan if plan else "(无)")
        if not plan:
            plan_label.setStyleSheet("color: gray;")
        else:
            plan_label.setStyleSheet(f"color: {color};")
        row.addWidget(plan_label)
        row.addStretch()

        container = QWidget()
        cl = QHBoxLayout(container)
        cl.setContentsMargins(0, 0, 0, 0)
        cl.addLayout(row)
        parent_layout.addWidget(container)

    def refresh(self):
        # 清空
        for layout in [self.day_layout, self.extra_layout]:
            while layout.count():
                item = layout.takeAt(0)
                w = item.widget()
                if w:
                    w.deleteLater()

        # 日期标签
        if self.data.start_date:
            current_date = self.data.start_date.addDays(self.data.current_day)
            self.date_label.setText(f"📅 第 {self.data.current_day+1} 天 ({current_date.toString('yyyy-MM-dd ddd')})")

        # 进度
        total = len(self.data.plans)
        spd = self.scheduler.slots_per_day()
        consumed = (self.data.current_day + 1) * spd
        consumed = min(consumed, total)
        self.progress_label.setText(f"进度: {consumed}/{total}")

        # 当天时间段
        day_plans = self.scheduler.get_day_plans(self.data.current_day)
        if not day_plans:
            lbl = QLabel("(当天没有安排)")
            lbl.setAlignment(Qt.AlignCenter)
            self.day_layout.addWidget(lbl)
        else:
            for slot_name, plan in day_plans:
                self._add_slot_row(self.day_layout, slot_name, plan, is_extra=False)

        # 额外轮
        extra_plans = self.scheduler.get_extra_plans()
        if not extra_plans:
            lbl = QLabel("(尚未向前滚动，或已无更多计划)")
            lbl.setAlignment(Qt.AlignCenter)
            lbl.setStyleSheet("color: gray;")
            self.extra_layout.addWidget(lbl)
        else:
            for slot_name, plan in extra_plans:
                self._add_slot_row(self.extra_layout, slot_name, plan, is_extra=True)

        # 按钮状态
        self.roll_forward_btn.setEnabled(self.scheduler.can_roll_forward())
        self.roll_backward_btn.setEnabled(self.scheduler.can_roll_backward())

        # 日历预览
        self.refresh_calendar_preview()

    def refresh_calendar_preview(self):
        calendar = self.scheduler.get_calendar()
        spd = self.scheduler.slots_per_day()

        lines = []
        for i, (date, plans) in enumerate(calendar):
            marker = "👉" if i == self.data.current_day else "  "
            extra_marker = f" [+{self.data.extra_count}额外]" if i == self.data.current_day and self.data.extra_count > 0 else ""
            lines.append(f"{marker} 第{i+1}天 ({date.toString('MM-dd ddd')}){extra_marker}")
            for slot_name, plan in plans:
                content = plan if plan else "·"
                lines.append(f"    {slot_name}: {content}")
            lines.append("")

        self.calendar_area.setText("\n".join(lines))

    def on_roll_forward(self):
        if self.scheduler.all_plans_consumed() and self.data.extra_count == 0:
            QMessageBox.information(self, "提示", "🎉 所有计划/任务已完成！")
            return
        if self.scheduler.roll_forward():
            self.refresh()

    def on_roll_backward(self):
        if self.scheduler.roll_backward():
            self.refresh()

    def on_next_day(self):
        """推进到下一天"""
        self.data.current_day += 1
        self.data.extra_count = 0  # 切天时重置额外轮
        self.data.save()
        self.refresh()


# ============== 主窗口 ==============

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.data = PlanData()
        self.data.load()
        self.scheduler = PlanScheduler(self.data)

        self.setWindowTitle("RollingPlan v0.1")
        self.setGeometry(100, 100, 900, 800)

        self.tabs = QTabWidget()
        self.setCentralWidget(self.tabs)

        self.editor = PlanEditor(self.data, self.scheduler, self.show_executor)
        self.executor = PlanExecutor(self.data, self.scheduler, self.show_editor)

        self.tabs.addTab(self.editor, "📝 计划写入")
        self.tabs.addTab(self.executor, "▶ 计划执行")

    def show_executor(self):
        self.executor = PlanExecutor(self.data, self.scheduler, self.show_editor)
        self.tabs.removeTab(1)
        self.tabs.addTab(self.executor, "▶ 计划执行")
        self.tabs.setCurrentIndex(1)

    def show_editor(self):
        self.tabs.setCurrentIndex(0)


# ============== 入口 ==============

if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyle("Fusion")

    window = MainWindow()
    window.show()

    sys.exit(app.exec_())
