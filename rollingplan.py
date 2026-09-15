"""
RollingPlan v0.2 — 母计划 + 借指定时间段 + 链式借

数据结构：
- 多个母计划，每个母计划独立：plans / time_slots / start_date / current_day / borrowed_slots
- 切换母计划：写入界面 + 执行界面都切换
- 借指定时间段：借的是"名为 X 的时间段位置"，从最靠前的未占用槽位借
- 链式借：明天借空了，从后天借
- 额外轮按借的顺序显示
"""

import sys
import json
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QListWidget,
    QSpinBox, QDateEdit, QTextEdit, QMessageBox, QTabWidget,
    QGroupBox, QInputDialog
)
from PyQt5.QtCore import Qt, QDate, QSettings
from PyQt5.QtGui import QFont


# ============== 数据模型 ==============

class ParentPlan:
    """单个母计划"""

    def __init__(self, name="新母计划"):
        self.name = name
        self.plans = []
        self.time_slots = []
        self.start_date = QDate.currentDate()
        self.current_day = 0
        self.borrowed_slots = []  # [[slot_name, plan, day, slot_idx], ...] 按借的顺序

    def to_dict(self):
        return {
            "name": self.name,
            "plans": self.plans,
            "time_slots": self.time_slots,
            "start_date": self.start_date.toString("yyyy-MM-dd"),
            "current_day": self.current_day,
            "borrowed_slots": self.borrowed_slots,
        }

    def from_dict(self, d):
        self.name = d.get("name", "新母计划")
        self.plans = d.get("plans", [])
        self.time_slots = d.get("time_slots", [])
        sd = d.get("start_date")
        if sd:
            self.start_date = QDate.fromString(sd, "yyyy-MM-dd")
        self.current_day = d.get("current_day", 0)
        self.borrowed_slots = d.get("borrowed_slots", [])


class PlanData:
    """全局数据"""

    def __init__(self):
        self.parents = [ParentPlan("母计划1")]
        self.current_parent_idx = 0

    @property
    def current_parent(self):
        return self.parents[self.current_parent_idx]

    def add_parent(self, name=None):
        if name is None:
            name = f"母计划{len(self.parents)+1}"
        self.parents.append(ParentPlan(name))

    def remove_parent(self, idx):
        if 0 <= idx < len(self.parents) and len(self.parents) > 1:
            self.parents.pop(idx)
            if self.current_parent_idx >= len(self.parents):
                self.current_parent_idx = len(self.parents) - 1

    def to_dict(self):
        return {
            "parents": [p.to_dict() for p in self.parents],
            "current_parent_idx": self.current_parent_idx,
        }

    def from_dict(self, d):
        self.parents = []
        for pd in d.get("parents", []):
            p = ParentPlan()
            p.from_dict(pd)
            self.parents.append(p)
        if not self.parents:
            self.parents = [ParentPlan("母计划1")]
        self.current_parent_idx = d.get("current_parent_idx", 0)
        if self.current_parent_idx >= len(self.parents):
            self.current_parent_idx = 0

    def has_borrowed(self):
        """任一母计划是否正在借用额外轮（会因编辑而索引错位）"""
        return any(bool(p.borrowed_slots) for p in self.parents)

    def save(self):
        s = QSettings("RollingPlan", "Data")
        s.setValue("plan_data", json.dumps(self.to_dict(), ensure_ascii=False))

    def load(self):
        s = QSettings("RollingPlan", "Data")
        data = s.value("plan_data")
        if data:
            try:
                loaded = json.loads(data)
                if not isinstance(loaded, dict):
                    raise ValueError("plan_data 不是 dict")
                self.from_dict(loaded)
                return True
            except Exception as e:
                print(f"[RollingPlan] 数据加载失败，使用默认数据: {e}")
        return False


# ============== 核心调度 ==============

class PlanScheduler:
    """母计划调度器"""

    def __init__(self, parent: ParentPlan):
        self.p = parent

    def slots_per_day(self):
        return sum(s.get("count", 1) for s in self.p.time_slots)

    def _expand_slots(self):
        """把时间段展开成 [(slot_name, plan_idx), ...] 的列表"""
        result = []
        idx = 0
        for slot in self.p.time_slots:
            for _ in range(slot.get("count", 1)):
                result.append((slot["name"], idx))
                idx += 1
        return result

    def get_day_plans(self, day_index):
        """第 day_index 天的计划切片 [(slot_name, plan), ...]"""
        spd = self.slots_per_day()
        if spd == 0:
            return []
        slots = self._expand_slots()
        start = day_index * spd
        plans_slice = self.p.plans[start:start + spd]

        result = []
        for i, (sname, sidx) in enumerate(slots):
            if i < len(plans_slice):
                result.append((sname, plans_slice[i]))
            else:
                result.append((sname, None))
        return result

    def get_calendar(self):
        if not self.p.start_date:
            return []
        spd = self.slots_per_day()
        if spd == 0 or not self.p.plans:
            return []
        total_days = (len(self.p.plans) + spd - 1) // spd
        cal = []
        for i in range(total_days):
            d = self.p.start_date.addDays(i)
            cal.append((d, self.get_day_plans(i)))
        return cal

    def _all_slot_positions(self):
        """所有时间段位置: [(day_index, slot_name, plan_idx), ...]"""
        spd = self.slots_per_day()
        if spd == 0 or not self.p.plans:
            return []
        result = []
        day_count = (len(self.p.plans) + spd - 1) // spd
        for day in range(day_count):
            day_plans = self.get_day_plans(day)
            for i, (sname, plan) in enumerate(day_plans):
                result.append((day, sname, i, plan))
        return result

    def _borrowed_set(self):
        """已被借出的 (day, slot_idx) 集合"""
        result = set()
        for entry in self.p.borrowed_slots:
            if len(entry) >= 4:
                _, _, day, slot_idx = entry
                result.add((day, slot_idx))
        return result

    def get_borrowed_slots_with_meta(self):
        """额外轮完整信息：[(slot_name, plan, day, slot_idx), ...]"""
        return [tuple(b) for b in self.p.borrowed_slots if len(b) >= 4]

    def get_extra_plans(self):
        """额外轮展示：[(slot_name, plan), ...]"""
        result = []
        for entry in self.get_borrowed_slots_with_meta():
            slot_name, plan, day, slot_idx = entry
            result.append((slot_name, plan))
        return result

    def _future_slot_positions(self):
        """未来可借的位置（day > current_day）:
        [(day, slot_name, slot_idx, plan), ...]
        按 (day, slot_idx) 顺序
        排除已被借出的位置"""
        spd = self.slots_per_day()
        if spd == 0 or not self.p.plans:
            return []
        borrowed = self._borrowed_set()
        result = []
        day_count = (len(self.p.plans) + spd - 1) // spd
        for day in range(self.p.current_day + 1, day_count):
            day_plans = self.get_day_plans(day)
            for i, (sname, plan) in enumerate(day_plans):
                if plan is not None and (day, i) not in borrowed:
                    result.append((day, sname, i, plan))
        return result

    def can_borrow_slot(self, slot_name):
        """能否借指定时间段：从未来位置里找同名未借的"""
        for day, sname, sidx, plan in self._future_slot_positions():
            if sname == slot_name:
                return True
        return False

    def available_borrow_names(self):
        """去重后所有当前可借的时间段名"""
        names = []
        for _, sname, _, _ in self._future_slot_positions():
            if sname not in names:
                names.append(sname)
        return names

    def borrow_slot(self, slot_name):
        """借指定时间段：从未来位置里找同名未借的最近一个
        借出时拷贝 plan 字符串，防止后续编辑子计划影响额外轮内容"""
        for day, sname, sidx, plan in self._future_slot_positions():
            if sname == slot_name:
                self.p.borrowed_slots.append([sname, plan, day, sidx])
                self.save_parent()
                return True
        return False

    def return_last_borrowed(self):
        """向后滚动：把额外轮最后 1 个推回去"""
        if not self.p.borrowed_slots:
            return False
        self.p.borrowed_slots.pop()
        self.save_parent()
        return True

    def can_return(self):
        return len(self.p.borrowed_slots) > 0

    def save_parent(self):
        pass  # 占位，实际由外部 PlanData.save() 触发

    def all_consumed(self):
        """所有计划是否都已用完：
        条件 = 当前天所有时间段都为空 + 没额外轮可借 + 当前天不能继续往后滚
        简化：当前天无内容 + 没额外轮 + 后面也没可借的"""
        day_plans = self.get_day_plans(self.p.current_day)
        day_has_content = any(p is not None for _, p in day_plans)

        # 检查还能不能借任何时间段
        any_can_borrow = False
        for slot in self.p.time_slots:
            if self.can_borrow_slot(slot["name"]):
                any_can_borrow = True
                break

        return not day_has_content and not any_can_borrow and not self.can_return()

    def get_progress(self):
        """进度：已分配的槽位数 / 总槽位数
        已分配 = (current_day + 1) * spd 但不超过总计划数"""
        spd = self.slots_per_day()
        if spd == 0:
            return 0, 0
        consumed = min((self.p.current_day + 1) * spd, len(self.p.plans))
        return consumed, len(self.p.plans)


# ============== 写入界面 ==============

class PlanEditor(QWidget):
    def __init__(self, data: PlanData, on_switch_to_exec):
        super().__init__()
        self.data = data
        self.on_switch_to_exec = on_switch_to_exec
        self.scheduler = PlanScheduler(data.current_parent)
        self.init_ui()
        self.refresh_all()

    def init_ui(self):
        layout = QVBoxLayout()

        title = QLabel("RollingPlan — 计划写入")
        title.setFont(QFont("Microsoft YaHei", 16, QFont.Bold))
        layout.addWidget(title)

        # ============ 母计划列表 ============
        parent_group = QGroupBox("母计划列表（可多个并行，切换编辑）")
        pg_layout = QHBoxLayout()

        self.parent_list = QListWidget()
        self.parent_list.setMaximumWidth(180)
        self.parent_list.currentRowChanged.connect(self.on_parent_select)
        pg_layout.addWidget(self.parent_list)

        pg_btn_col = QVBoxLayout()
        for text, cb in [
            ("+ 新建母计划", self.on_add_parent),
            ("重命名", self.on_rename_parent),
            ("删除选中", self.on_del_parent),
            ("↑ 上移", self.on_parent_up),
            ("↓ 下移", self.on_parent_down),
        ]:
            btn = QPushButton(text)
            btn.clicked.connect(cb)
            pg_btn_col.addWidget(btn)
        pg_btn_col.addStretch()
        pg_layout.addLayout(pg_btn_col)

        parent_group.setLayout(pg_layout)
        layout.addWidget(parent_group)

        # ============ 当前母计划名 ============
        self.parent_name_label = QLabel()
        self.parent_name_label.setFont(QFont("Microsoft YaHei", 12, QFont.Bold))
        layout.addWidget(self.parent_name_label)

        # ============ 子计划列表 ============
        plan_group = QGroupBox("子计划列表（按顺序）")
        plan_layout = QVBoxLayout()

        self.plan_list = QListWidget()
        self.plan_list.setMaximumHeight(160)
        plan_layout.addWidget(self.plan_list)

        edit_row = QHBoxLayout()
        self.plan_input = QLineEdit()
        self.plan_input.setPlaceholderText("输入子计划内容，回车添加")
        self.plan_input.returnPressed.connect(self.add_plan)
        edit_row.addWidget(self.plan_input)

        for text, cb in [
            ("添加", self.add_plan),
            ("编辑", self.edit_plan),
            ("删除", self.del_plan),
            ("↑", self.plan_up),
            ("↓", self.plan_down),
        ]:
            btn = QPushButton(text)
            btn.clicked.connect(cb)
            edit_row.addWidget(btn)

        plan_layout.addLayout(edit_row)
        plan_group.setLayout(plan_layout)
        layout.addWidget(plan_group)

        # ============ 时间段 ============
        slot_group = QGroupBox("时间段（可自定义）")
        slot_layout = QVBoxLayout()

        self.slot_list = QListWidget()
        self.slot_list.setMaximumHeight(120)
        slot_layout.addWidget(self.slot_list)

        slot_row = QHBoxLayout()
        self.slot_name_input = QLineEdit()
        self.slot_name_input.setPlaceholderText("时间段名")
        slot_row.addWidget(self.slot_name_input)

        self.slot_count_input = QSpinBox()
        self.slot_count_input.setMinimum(1)
        self.slot_count_input.setMaximum(10)
        self.slot_count_input.setValue(1)
        self.slot_count_input.setPrefix("数量:")
        slot_row.addWidget(self.slot_count_input)

        for text, cb in [
            ("添加", self.add_slot),
            ("编辑", self.edit_slot),
            ("删除", self.del_slot),
            ("↑", self.slot_up),
            ("↓", self.slot_down),
        ]:
            btn = QPushButton(text)
            btn.clicked.connect(cb)
            slot_row.addWidget(btn)

        slot_layout.addLayout(slot_row)
        slot_group.setLayout(slot_layout)
        layout.addWidget(slot_group)

        # ============ 开始日期 ============
        date_group = QGroupBox("开始日期")
        date_layout = QHBoxLayout()
        self.date_edit = QDateEdit()
        self.date_edit.setCalendarPopup(True)
        self.date_edit.setDate(QDate.currentDate())
        date_layout.addWidget(self.date_edit)
        date_group.setLayout(date_layout)
        layout.addWidget(date_group)

        # ============ 操作 ============
        btn_row = QHBoxLayout()
        save_btn = QPushButton("保存并生成计划表")
        save_btn.setFont(QFont("Microsoft YaHei", 11, QFont.Bold))
        save_btn.clicked.connect(self.save_and_preview)
        btn_row.addWidget(save_btn)

        preview_btn = QPushButton("预览")
        preview_btn.clicked.connect(self.preview_calendar)
        btn_row.addWidget(preview_btn)

        go_exec = QPushButton("进入执行界面 →")
        go_exec.clicked.connect(self.go_exec)
        btn_row.addWidget(go_exec)

        layout.addLayout(btn_row)

        self.preview_area = QTextEdit()
        self.preview_area.setReadOnly(True)
        self.preview_area.setMaximumHeight(180)
        layout.addWidget(self.preview_area)

        self.setLayout(layout)

    def on_parent_select(self, idx):
        if idx < 0 or idx >= len(self.data.parents):
            return
        # 切换前先保存当前编辑内容到当前母计划
        self.save_current_to_parent()
        self.data.current_parent_idx = idx
        self.scheduler = PlanScheduler(self.data.current_parent)
        self.refresh_all()

    def save_current_to_parent(self):
        """把当前界面控件值写回当前母计划"""
        cp = self.data.current_parent
        cp.start_date = self.date_edit.date()
        # plans / time_slots 已经直接绑定在 self.data.current_parent 上
        # 这里只额外保存日期

    def on_add_parent(self):
        self.save_current_to_parent()
        name, ok = QInputDialog.getText(self, "新建母计划", "母计划名:")
        if ok and name.strip():
            self.data.add_parent(name.strip())
        else:
            self.data.add_parent()
        self.data.current_parent_idx = len(self.data.parents) - 1
        self.scheduler = PlanScheduler(self.data.current_parent)
        self.refresh_all()
        self.data.save()

    def on_rename_parent(self):
        idx = self.parent_list.currentRow()
        if idx < 0:
            return
        new_name, ok = QInputDialog.getText(self, "重命名", "新名称:", text=self.data.parents[idx].name)
        if ok and new_name.strip():
            self.data.parents[idx].name = new_name.strip()
            self.refresh_all()
            self.data.save()

    def on_del_parent(self):
        idx = self.parent_list.currentRow()
        if idx < 0:
            return
        if len(self.data.parents) <= 1:
            QMessageBox.warning(self, "提示", "至少保留一个母计划")
            return
        reply = QMessageBox.question(self, "确认", f"删除母计划「{self.data.parents[idx].name}」？")
        if reply == QMessageBox.Yes:
            self.data.remove_parent(idx)
            self.scheduler = PlanScheduler(self.data.current_parent)
            self.refresh_all()
            self.data.save()

    def on_parent_up(self):
        idx = self.parent_list.currentRow()
        if idx > 0:
            self.data.parents[idx-1], self.data.parents[idx] = self.data.parents[idx], self.data.parents[idx-1]
            self.data.current_parent_idx = idx - 1
            self.refresh_all()
            self.data.save()

    def on_parent_down(self):
        idx = self.parent_list.currentRow()
        if 0 <= idx < len(self.data.parents) - 1:
            self.data.parents[idx+1], self.data.parents[idx] = self.data.parents[idx], self.data.parents[idx+1]
            self.data.current_parent_idx = idx + 1
            self.refresh_all()
            self.data.save()

    def refresh_all(self):
        # 母计划列表
        self.parent_list.blockSignals(True)
        self.parent_list.clear()
        for i, p in enumerate(self.data.parents):
            self.parent_list.addItem(f"{i+1}. {p.name}")
        if self.data.current_parent_idx < self.parent_list.count():
            self.parent_list.setCurrentRow(self.data.current_parent_idx)
        self.parent_list.blockSignals(False)

        cp = self.data.current_parent
        self.parent_name_label.setText(f"当前母计划：{cp.name}")

        # 子计划
        self.plan_list.clear()
        for i, plan in enumerate(cp.plans):
            self.plan_list.addItem(f"{i+1}. {plan}")

        # 时间段
        self.slot_list.clear()
        for i, slot in enumerate(cp.time_slots):
            disp = slot["name"]
            if slot.get("count", 1) > 1:
                disp += f" x{slot['count']}"
            self.slot_list.addItem(f"{i+1}. {disp}")

        if cp.start_date:
            self.date_edit.setDate(cp.start_date)

        self.scheduler = PlanScheduler(cp)

    def add_plan(self):
        text = self.plan_input.text().strip()
        if text:
            self.data.current_parent.plans.append(text)
            self.plan_input.clear()
            self.refresh_all()
            self.data.save()

    def edit_plan(self):
        cur = self.plan_list.currentRow()
        if cur < 0:
            return
        new_text, ok = QInputDialog.getText(self, "编辑", "新内容:", text=self.data.current_parent.plans[cur])
        if ok and new_text.strip():
            self.data.current_parent.plans[cur] = new_text.strip()
            self.refresh_all()
            self.data.save()

    def del_plan(self):
        cur = self.plan_list.currentRow()
        if cur < 0:
            return
        self.data.current_parent.plans.pop(cur)
        self.refresh_all()
        self.data.save()

    def plan_up(self):
        cur = self.plan_list.currentRow()
        if cur > 0:
            p = self.data.current_parent.plans
            p[cur-1], p[cur] = p[cur], p[cur-1]
            self.refresh_all()
            self.plan_list.setCurrentRow(cur - 1)
            self.data.save()

    def plan_down(self):
        cur = self.plan_list.currentRow()
        p = self.data.current_parent.plans
        if 0 <= cur < len(p) - 1:
            p[cur+1], p[cur] = p[cur], p[cur+1]
            self.refresh_all()
            self.plan_list.setCurrentRow(cur + 1)
            self.data.save()

    def add_slot(self):
        name = self.slot_name_input.text().strip()
        count = self.slot_count_input.value()
        if not name:
            return
        if self.data.has_borrowed():
            QMessageBox.warning(self, "提示", "当前有母计划正在借用额外轮，无法修改时间段。\n请先退回所有借出的时间段。")
            return
        self.data.current_parent.time_slots.append({"name": name, "count": count})
        self.slot_name_input.clear()
        self.slot_count_input.setValue(1)
        self.refresh_all()
        self.data.save()

    def edit_slot(self):
        cur = self.slot_list.currentRow()
        if cur < 0:
            return
        if self.data.has_borrowed():
            QMessageBox.warning(self, "提示", "当前有母计划正在借用额外轮，无法修改时间段。\n请先退回所有借出的时间段。")
            return
        slot = self.data.current_parent.time_slots[cur]
        new_name, ok = QInputDialog.getText(self, "编辑", "新名称:", text=slot["name"])
        if ok and new_name.strip():
            new_count, ok2 = QInputDialog.getInt(self, "编辑", "新数量:", value=slot.get("count", 1), min=1, max=10)
            if ok2:
                self.data.current_parent.time_slots[cur] = {"name": new_name, "count": new_count}
                self.refresh_all()
                self.data.save()

    def del_slot(self):
        cur = self.slot_list.currentRow()
        if cur < 0:
            return
        if self.data.has_borrowed():
            QMessageBox.warning(self, "提示", "当前有母计划正在借用额外轮，无法修改时间段。\n请先退回所有借出的时间段。")
            return
        self.data.current_parent.time_slots.pop(cur)
        self.refresh_all()
        self.data.save()

    def slot_up(self):
        if self.data.has_borrowed():
            QMessageBox.warning(self, "提示", "当前有母计划正在借用额外轮，无法修改时间段。")
            return
        cur = self.slot_list.currentRow()
        if cur > 0:
            s = self.data.current_parent.time_slots
            s[cur-1], s[cur] = s[cur], s[cur-1]
            self.refresh_all()
            self.slot_list.setCurrentRow(cur - 1)
            self.data.save()

    def slot_down(self):
        if self.data.has_borrowed():
            QMessageBox.warning(self, "提示", "当前有母计划正在借用额外轮，无法修改时间段。")
            return
        cur = self.slot_list.currentRow()
        s = self.data.current_parent.time_slots
        if 0 <= cur < len(s) - 1:
            s[cur+1], s[cur] = s[cur], s[cur+1]
            self.refresh_all()
            self.slot_list.setCurrentRow(cur + 1)
            self.data.save()

    def save_and_preview(self):
        self.save_current_to_parent()
        self.data.save()
        self.preview_calendar()

    def preview_calendar(self):
        self.save_current_to_parent()
        self.scheduler = PlanScheduler(self.data.current_parent)
        p = self.data.current_parent
        if not p.plans:
            QMessageBox.warning(self, "提示", "请先添加子计划")
            return
        if not p.time_slots:
            QMessageBox.warning(self, "提示", "请先添加时间段")
            return
        cal = self.scheduler.get_calendar()
        lines = [f"📅 【{p.name}】计划表（共 {len(cal)} 天）", "=" * 40]
        for i, (d, plans) in enumerate(cal):
            lines.append(f"\n第{i+1}天 ({d.toString('MM-dd ddd')}):")
            for sname, plan in plans:
                m = "✓" if plan else "·"
                lines.append(f"  {m} {sname}: {plan if plan else '(空)'}")
        self.preview_area.setText("\n".join(lines))

    def go_exec(self):
        cp = self.data.current_parent
        if not cp.plans or not cp.time_slots or not cp.start_date:
            QMessageBox.warning(self, "提示", "请先完成子计划/时间段/开始日期")
            return
        self.save_current_to_parent()
        self.data.save()
        self.on_switch_to_exec()


# ============== 执行界面 ==============

class PlanExecutor(QWidget):
    def __init__(self, data: PlanData, on_switch_to_edit):
        super().__init__()
        self.data = data
        self.on_switch_to_edit = on_switch_to_edit
        self.scheduler = PlanScheduler(data.current_parent)
        self.init_ui()
        self.refresh()

    def init_ui(self):
        layout = QVBoxLayout()

        title = QLabel("RollingPlan — 计划执行")
        title.setFont(QFont("Microsoft YaHei", 16, QFont.Bold))
        layout.addWidget(title)

        # 母计划切换
        parent_row = QHBoxLayout()
        parent_row.addWidget(QLabel("当前母计划:"))
        self.parent_combo_label = QLabel()
        self.parent_combo_label.setFont(QFont("Microsoft YaHei", 11, QFont.Bold))
        parent_row.addWidget(self.parent_combo_label)

        self.parent_switch_btn = QPushButton("切换母计划 →")
        self.parent_switch_btn.clicked.connect(self.on_switch_parent)
        parent_row.addWidget(self.parent_switch_btn)
        parent_row.addStretch()

        edit_btn = QPushButton("← 返回编辑")
        edit_btn.clicked.connect(self.on_switch_to_edit)
        parent_row.addWidget(edit_btn)
        layout.addLayout(parent_row)

        # 信息行
        info_row = QHBoxLayout()
        self.date_label = QLabel()
        self.date_label.setFont(QFont("Microsoft YaHei", 12, QFont.Bold))
        info_row.addWidget(self.date_label)

        self.progress_label = QLabel()
        info_row.addWidget(self.progress_label)
        info_row.addStretch()
        layout.addLayout(info_row)

        # 当天
        self.day_group = QGroupBox("当天时间段")
        self.day_layout = QVBoxLayout()
        self.day_group.setLayout(self.day_layout)
        layout.addWidget(self.day_group)

        # 额外轮
        self.extra_group = QGroupBox("额外轮（借指定时间段而来，按借的顺序）")
        self.extra_layout = QVBoxLayout()
        self.extra_group.setLayout(self.extra_layout)
        layout.addWidget(self.extra_group)

        # 滚动按钮
        roll_row = QHBoxLayout()

        self.borrow_btn = QPushButton("借指定时间段 →")
        self.borrow_btn.setFont(QFont("Microsoft YaHei", 11))
        self.borrow_btn.setStyleSheet("background-color: #FF9800; color: white;")
        self.borrow_btn.clicked.connect(self.on_borrow)
        roll_row.addWidget(self.borrow_btn)

        self.return_btn = QPushButton("← 退回最后借的")
        self.return_btn.setFont(QFont("Microsoft YaHei", 11))
        self.return_btn.clicked.connect(self.on_return)
        roll_row.addWidget(self.return_btn)

        next_btn = QPushButton("✓ 当天完成 → 下一天")
        next_btn.setFont(QFont("Microsoft YaHei", 11))
        next_btn.setStyleSheet("background-color: #4CAF50; color: white;")
        next_btn.clicked.connect(self.on_next_day)
        roll_row.addWidget(next_btn)

        layout.addLayout(roll_row)

        # 日历
        cal_group = QGroupBox("完整日历预览")
        cal_layout = QVBoxLayout()
        self.calendar_area = QTextEdit()
        self.calendar_area.setReadOnly(True)
        self.calendar_area.setMaximumHeight(160)
        cal_layout.addWidget(self.calendar_area)
        cal_group.setLayout(cal_layout)
        layout.addWidget(cal_group)

        self.setLayout(layout)

    def _clear_layout(self, layout):
        while layout.count():
            item = layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

    def _add_slot_row(self, parent_layout, slot_name, plan, is_extra=False):
        row = QHBoxLayout()
        prefix = "⤴ " if is_extra else "  "
        color = "#1B5E20" if is_extra else "black"
        bg = "#E8F5E9" if is_extra else None

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
        if bg:
            container.setStyleSheet(f"background-color: {bg}; border-left: 3px solid {color}; padding-left: 4px;")
        cl = QHBoxLayout(container)
        cl.setContentsMargins(6, 2, 6, 2)
        cl.addLayout(row)
        parent_layout.addWidget(container)

    def refresh(self):
        self._clear_layout(self.day_layout)
        self._clear_layout(self.extra_layout)

        p = self.data.current_parent
        self.scheduler = PlanScheduler(p)

        self.parent_combo_label.setText(f"【{p.name}】")

        if p.start_date:
            cd = p.start_date.addDays(p.current_day)
            self.date_label.setText(f"📅 第 {p.current_day+1} 天 ({cd.toString('yyyy-MM-dd ddd')})")

        consumed, total = self.scheduler.get_progress()
        self.progress_label.setText(f"进度：{consumed}/{total}")

        # 当天
        day_plans = self.scheduler.get_day_plans(p.current_day)
        if not day_plans:
            lbl = QLabel("(当天没有安排)")
            lbl.setAlignment(Qt.AlignCenter)
            self.day_layout.addWidget(lbl)
        else:
            for sname, plan in day_plans:
                self._add_slot_row(self.day_layout, sname, plan, is_extra=False)

        # 额外轮
        extra = self.scheduler.get_extra_plans()
        if not extra:
            lbl = QLabel("(尚未借，或已无更多可借)")
            lbl.setAlignment(Qt.AlignCenter)
            lbl.setStyleSheet("color: gray;")
            self.extra_layout.addWidget(lbl)
        else:
            for sname, plan in extra:
                self._add_slot_row(self.extra_layout, sname, plan, is_extra=True)

        self.return_btn.setEnabled(self.scheduler.can_return())

        # 借按钮：检查是否还有任何可借
        self.borrow_btn.setEnabled(bool(self.scheduler.available_borrow_names()))

        self.refresh_calendar_preview()

    def refresh_calendar_preview(self):
        p = self.data.current_parent
        cal = self.scheduler.get_calendar()
        spd = self.scheduler.slots_per_day()
        borrowed_set = set()
        for entry in self.scheduler.get_borrowed_slots_with_meta():
            _, _, day, slot_idx = entry
            borrowed_set.add((day, slot_idx))

        lines = []
        for i, (d, plans) in enumerate(cal):
            marker = "👉" if i == p.current_day else "  "
            extra_marker = f" [+{len(self.scheduler.get_extra_plans())}借]" if i == p.current_day and self.scheduler.get_extra_plans() else ""
            lines.append(f"{marker} 第{i+1}天 ({d.toString('MM-dd ddd')}){extra_marker}")
            for j, (sname, plan) in enumerate(plans):
                b_mark = "📤" if (i, j) in borrowed_set else "  "
                content = plan if plan else "·"
                lines.append(f"  {b_mark} {sname}: {content}")
            lines.append("")

        self.calendar_area.setText("\n".join(lines))

    def on_borrow(self):
        """弹对话框选时间段名"""
        if self.scheduler.all_consumed():
            QMessageBox.information(self, "提示", "🎉 所有计划/任务已完成！")
            return

        available = self.scheduler.available_borrow_names()
        if not available:
            QMessageBox.warning(self, "提示", "当前无可借的时间段")
            return

        name, ok = QInputDialog.getItem(self, "借指定时间段", "选择要借的时间段:", available, 0, False)
        if ok and name:
            if self.scheduler.borrow_slot(name):
                self.data.save()
                self.refresh()
            else:
                QMessageBox.warning(self, "提示", f"无法借「{name}」")

    def on_return(self):
        if self.scheduler.return_last_borrowed():
            self.data.save()
            self.refresh()

    def on_next_day(self):
        p = self.data.current_parent
        scheduler = self.scheduler
        day_plans = scheduler.get_day_plans(p.current_day)
        day_has_content = any(plan is not None for _, plan in day_plans)
        can_still_borrow = bool(scheduler.available_borrow_names())
        can_still_return = scheduler.can_return()

        unfinished = []
        if day_has_content:
            unfinished.append("当天还有时间段未完成")
        if can_still_borrow:
            unfinished.append("还有可借的时间段")
        if can_still_return:
            unfinished.append("已借的额外轮可退回")

        if unfinished:
            msg = "今天是第 {} 天，还有未完成项：\n  • {}\n\n确认进入下一天？".format(
                p.current_day + 1, "\n  • ".join(unfinished)
            )
            reply = QMessageBox.question(self, "确认下一天", msg)
            if reply != QMessageBox.Yes:
                return

        p.current_day += 1
        p.borrowed_slots = []  # 切天时清空额外轮
        self.data.save()
        self.refresh()

    def on_switch_parent(self):
        """切换母计划"""
        names = [p.name for p in self.data.parents]
        cur_name = self.data.current_parent.name
        try:
            cur_idx = names.index(cur_name)
        except ValueError:
            cur_idx = 0
        name, ok = QInputDialog.getItem(self, "切换母计划", "选择母计划:", names, cur_idx, False)
        if ok and name:
            self.data.current_parent_idx = names.index(name)
            self.data.save()
            self.scheduler = PlanScheduler(self.data.current_parent)
            self.refresh()


# ============== 主窗口 ==============

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.data = PlanData()
        self.data.load()
        self.setWindowTitle("RollingPlan v0.2")
        self.setGeometry(100, 100, 950, 850)

        self.tabs = QTabWidget()
        self.setCentralWidget(self.tabs)

        self.editor = PlanEditor(self.data, self.show_executor)
        self.executor = PlanExecutor(self.data, self.show_editor)

        self.tabs.addTab(self.editor, "📝 计划写入")
        self.tabs.addTab(self.executor, "▶ 计划执行")

    def show_executor(self):
        self.executor = PlanExecutor(self.data, self.show_editor)
        self.tabs.removeTab(1)
        self.tabs.addTab(self.executor, "▶ 计划执行")
        self.tabs.setCurrentIndex(1)

    def show_editor(self):
        self.tabs.setCurrentIndex(0)


# ============== 入口 ==============

if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    win = MainWindow()
    win.show()
    sys.exit(app.exec_())
