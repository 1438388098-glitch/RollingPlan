"""
RollingPlan 编辑器（v0.17 抽出）

把 PlanEditor 从 rollingplan.py 抽到独立模块。PlanEditor 是「制定计划」页：
分类管理 / 计划清单 / 时段编辑 / 起始日期 / 计划预览。

依赖（在 rollingplan.py 里定义）:
- PlanData, ParentPlan, PlanScheduler
- apply_theme, THEME_KEY, THEME_OPTIONS（在 theme.py）

行为完全等价：所有现有测试继续通过；rollingplan.py 通过 re-export PlanEditor 保持旧导入路径。
"""

from PyQt5.QtCore import Qt, QDate, QSettings
from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QListWidget,
    QSpinBox, QDateEdit, QTextEdit, QMessageBox,
    QComboBox, QToolButton, QGroupBox, QApplication,
    QInputDialog, QFileDialog, QDialog, QFormLayout,
)

from scheduler import PlanScheduler
from theme import THEME_KEY, THEME_OPTIONS, apply_theme
import animations
import theme

# PlanData 类型提示用（避免循环 import：rollingplan.py 会 import editor）
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from rollingplan import PlanData  # noqa: F401


class PlanEditor(QWidget):
    def __init__(self, data, on_switch_to_exec, on_data_reloaded=None):
        super().__init__()
        self.data = data
        self.on_switch_to_exec = on_switch_to_exec
        self.on_data_reloaded = on_data_reloaded  # v0.4：导入后通知主窗口刷新 executor
        self.scheduler = PlanScheduler(data.current_parent)
        self.init_ui()
        self.refresh_all()

    def init_ui(self):
        layout = QVBoxLayout()
        layout.setContentsMargins(24, 20, 24, 20)

        title = QLabel("日常计划管理 — 制定计划")
        title.setObjectName("rpTitle")
        layout.addWidget(title)

        # v0.30：新手引导条（审计 P1-1/P2-1）—— 没计划或没时段时可见，
        # 配齐后自动消失；不改变任何折叠组的默认收起行为（极简口径不动）
        self.guide_label = QLabel(
            "三步开始：① 点开「▸ 计划清单」添加要做的事 → ② 点开「▸ 时段」划分一天 → ③ 点「开始执行」"
        )
        self.guide_label.setObjectName("rpDim")
        self.guide_label.setWordWrap(True)
        layout.addWidget(self.guide_label)

        # ============ 主题（常驻）+ 其余收进「⋯」（v0.27b 瘦身）============
        io_row = QHBoxLayout()
        # 主题切换（全局设置，最左）
        theme_label = QLabel("主题:")
        io_row.addWidget(theme_label)
        self.theme_combo = QComboBox()   # THEME_OPTIONS 已在模块顶部 from theme import
        for key, label in THEME_OPTIONS:
            self.theme_combo.addItem(label, userData=key)
        # 初始值从 QSettings 读
        from theme import app_settings
        _saved = app_settings().value(THEME_KEY, "dark")
        if _saved not in ("dark", "light", "auto"):
            _saved = "dark"
        for i, (k, _) in enumerate(THEME_OPTIONS):
            if k == _saved:
                self.theme_combo.setCurrentIndex(i)
                break
        self.theme_combo.currentIndexChanged.connect(self.on_theme_changed)
        io_row.addWidget(self.theme_combo)
        io_row.addStretch()

        # 「⋯」：重置进度 / 导入 / 导出 / 预览 都收在这里（默认收起）
        self._more_toggle = QToolButton()
        self._more_toggle.setText("⋯")
        self._more_toggle.setCheckable(True)
        self._more_toggle.setChecked(False)
        self._more_toggle.setObjectName("rpFold")
        self._more_toggle.setToolButtonStyle(Qt.ToolButtonTextOnly)
        self._more_toggle.setToolTip("重置进度 / 导入 / 导出 / 预览")
        self._more_toggle.clicked.connect(self._toggle_more)
        io_row.addWidget(self._more_toggle)
        layout.addLayout(io_row)

        self._more_container = QWidget()
        more_row = QHBoxLayout(self._more_container)
        more_row.setContentsMargins(0, 0, 0, 0)

        self.restore_backup_btn = QPushButton("♻️ 恢复上次备份")
        self.restore_backup_btn.setObjectName("rpGhost")
        self.restore_backup_btn.setToolTip(
            "把数据回滚到上一次保存前的状态（每次保存都会自动留一份上一代备份）")
        self.restore_backup_btn.clicked.connect(self.on_restore_backup)
        more_row.addWidget(self.restore_backup_btn)

        self.reset_btn = QPushButton("🔄 重置当前分类进度")
        self.reset_btn.setObjectName("rpGhost")
        self.reset_btn.clicked.connect(self.on_reset_progress)
        more_row.addWidget(self.reset_btn)

        self.import_btn = QPushButton("📥 导入 JSON")
        self.import_btn.setObjectName("rpGhost")
        self.import_btn.clicked.connect(self.on_import)
        more_row.addWidget(self.import_btn)

        self.export_btn = QPushButton("📤 导出 JSON")
        self.export_btn.setObjectName("rpGhost")
        self.export_btn.clicked.connect(self.on_export)
        more_row.addWidget(self.export_btn)

        self.preview_btn = QPushButton("预览")
        self.preview_btn.clicked.connect(self.preview_calendar)
        more_row.addWidget(self.preview_btn)

        more_row.addStretch()
        self._more_container.setVisible(False)
        layout.addWidget(self._more_container)

        # ============ 分类列表（默认收起）============
        # QGroupBox 的 checkable + checked=False 在 pyqtdarktheme 下不自动隐藏子 widget，
        # 改用 QToolButton 手动控制 visibility
        parent_group = QGroupBox()
        self._parent_toggle = QToolButton()
        self._parent_toggle.setText("▸ 计划分类")
        self._parent_toggle.setCheckable(True)
        self._parent_toggle.setChecked(False)
        self._parent_toggle.setObjectName("rpFold")
        self._parent_toggle.setToolButtonStyle(Qt.ToolButtonTextOnly)
        self._parent_toggle.clicked.connect(self._toggle_parent_group)
        self._parent_body = QWidget()
        pg_outer = QVBoxLayout(self._parent_body)
        self.parent_name_label = QLabel()
        self.parent_name_label.setObjectName("rpSlotName")
        pg_outer.addWidget(self.parent_name_label)
        pg_layout = QHBoxLayout()

        self.parent_list = QListWidget()
        self.parent_list.setMaximumWidth(180)
        self.parent_list.currentRowChanged.connect(self.on_parent_select)
        self.parent_list.itemDoubleClicked.connect(
            lambda item: self.on_rename_parent())   # v0.30 R27：双击重命名分类
        pg_layout.addWidget(self.parent_list)

        pg_btn_col = QVBoxLayout()
        for text, cb in [
            ("+ 新建分类", self.on_add_parent),
            ("重命名", self.on_rename_parent),
            ("删除选中", self.on_del_parent),
            ("↑ 上移", self.on_parent_up),
            ("↓ 下移", self.on_parent_down),
        ]:
            btn = QPushButton(text)
            if text.startswith("删除"):
                btn.setObjectName("rpDangerGhost")   # v0.30 R32：危险操作视觉区分
            btn.clicked.connect(cb)
            pg_btn_col.addWidget(btn)
        pg_btn_col.addStretch()
        pg_layout.addLayout(pg_btn_col)

        pg_outer.addLayout(pg_layout)
        self._parent_body.setVisible(False)  # 默认收起
        # 装进 GroupBox：标题用 QToolButton 替代，内容是 body
        group_layout = QVBoxLayout(parent_group)
        group_layout.addWidget(self._parent_toggle)
        group_layout.addWidget(self._parent_body)
        layout.addWidget(parent_group)

        # ============ 计划清单（默认收起）============
        plan_group = QGroupBox()
        self._plan_toggle = QToolButton()
        self._plan_toggle.setText("▸ 计划清单")
        self._plan_toggle.setCheckable(True)
        self._plan_toggle.setChecked(False)
        self._plan_toggle.setObjectName("rpFold")
        self._plan_toggle.setToolButtonStyle(Qt.ToolButtonTextOnly)
        self._plan_toggle.clicked.connect(self._toggle_plan_group)
        self._plan_body = QWidget()
        plan_outer = QVBoxLayout(self._plan_body)
        plan_layout = QVBoxLayout()

        self.plan_list = QListWidget()
        self.plan_list.setMinimumHeight(160)
        self.plan_list.setMaximumHeight(240)
        self.plan_list.itemDoubleClicked.connect(
            lambda item: self.edit_plan())   # v0.30 R27：双击编辑计划
        plan_layout.addWidget(self.plan_list)

        edit_row = QHBoxLayout()
        self.plan_input = QLineEdit()
        self.plan_input.setPlaceholderText("输入计划内容，回车添加")
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
            if text == "删除":
                btn.setObjectName("rpDangerGhost")
            btn.clicked.connect(cb)
            edit_row.addWidget(btn)

        plan_layout.addLayout(edit_row)
        plan_outer.addLayout(plan_layout)
        self._plan_body.setVisible(False)
        plan_group_layout = QVBoxLayout(plan_group)
        plan_group_layout.addWidget(self._plan_toggle)
        plan_group_layout.addWidget(self._plan_body)
        layout.addWidget(plan_group)

        # ============ 时段（默认收起）============
        slot_group = QGroupBox()
        self._slot_toggle = QToolButton()
        self._slot_toggle.setText("▸ 时段")
        self._slot_toggle.setCheckable(True)
        self._slot_toggle.setChecked(False)
        self._slot_toggle.setObjectName("rpFold")
        self._slot_toggle.setToolButtonStyle(Qt.ToolButtonTextOnly)
        self._slot_toggle.clicked.connect(self._toggle_slot_group)
        self._slot_body = QWidget()
        slot_outer = QVBoxLayout(self._slot_body)
        slot_layout = QVBoxLayout()

        self.slot_list = QListWidget()
        self.slot_list.setMinimumHeight(120)
        self.slot_list.setMaximumHeight(180)
        self.slot_list.itemDoubleClicked.connect(
            lambda item: self.edit_slot())   # v0.30 R27：双击编辑时段
        slot_layout.addWidget(self.slot_list)

        slot_row = QHBoxLayout()
        self.slot_name_input = QLineEdit()
        self.slot_name_input.setPlaceholderText("时段名（早 / 中 / 晚……）")
        self.slot_name_input.returnPressed.connect(self.add_slot)   # v0.30：回车即添加
        slot_row.addWidget(self.slot_name_input)

        self.slot_count_input = QSpinBox()
        self.slot_count_input.setMinimum(1)
        self.slot_count_input.setMaximum(10)
        self.slot_count_input.setValue(1)
        self.slot_count_input.setPrefix("每天 ")
        self.slot_count_input.setSuffix(" 次")
        slot_row.addWidget(self.slot_count_input)

        for text, cb in [
            ("添加", self.add_slot),
            ("编辑", self.edit_slot),
            ("删除", self.del_slot),
            ("↑", self.slot_up),
            ("↓", self.slot_down),
        ]:
            btn = QPushButton(text)
            if text == "删除":
                btn.setObjectName("rpDangerGhost")
            btn.clicked.connect(cb)
            slot_row.addWidget(btn)

        slot_layout.addLayout(slot_row)
        slot_outer.addLayout(slot_layout)
        self._slot_body.setVisible(False)
        slot_group_layout = QVBoxLayout(slot_group)
        slot_group_layout.addWidget(self._slot_toggle)
        slot_group_layout.addWidget(self._slot_body)
        layout.addWidget(slot_group)

        # ============ 起始日期（v0.27b：默认收起，跟其它三组一致）============
        self._date_toggle = QToolButton()
        self._date_toggle.setText("▸ 起始日期")
        self._date_toggle.setCheckable(True)
        self._date_toggle.setChecked(False)
        self._date_toggle.setObjectName("rpFold")
        self._date_toggle.setToolButtonStyle(Qt.ToolButtonTextOnly)
        self._date_toggle.clicked.connect(self._toggle_date_group)
        layout.addWidget(self._date_toggle)

        self._date_body = QWidget()
        date_layout = QHBoxLayout(self._date_body)
        date_layout.setContentsMargins(0, 0, 0, 0)
        self.date_edit = QDateEdit()
        self.date_edit.setCalendarPopup(True)
        self.date_edit.setDate(QDate.currentDate())
        date_layout.addWidget(self.date_edit)
        date_layout.addStretch()
        self._date_body.setVisible(False)
        layout.addWidget(self._date_body)

        # ============ 操作 ============
        btn_row = QHBoxLayout()
        save_btn = QPushButton("保存并预览")
        save_btn.clicked.connect(self.save_and_preview)
        btn_row.addWidget(save_btn)

        go_exec = QPushButton("开始执行 →")
        go_exec.setObjectName("rpPrimary")
        go_exec.clicked.connect(self.go_exec)
        btn_row.addWidget(go_exec)

        layout.addLayout(btn_row)

        self.preview_area = QTextEdit()
        self.preview_area.setReadOnly(True)
        self.preview_area.setMaximumHeight(180)
        # v0.28：预览区默认不占版面 —— 点了「预览」/「生成计划」才出现
        self.preview_area.setVisible(False)
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
        """v0.30（审计 P0-5）：取消=取消。旧版把「取消」和「名字为空」都
        当成「建一个默认分类」，用户按个 Esc 就多出一个分类还被切过去。"""
        self.save_current_to_parent()
        name, ok = QInputDialog.getText(self, "新建分类", "分类名:")
        if not ok:
            return
        name = name.strip()
        if not name:
            QMessageBox.warning(self, "提示", "分类名不能为空")
            return
        # v0.30 R24（审计 P2-11）：重名会让「切换分类」永远命中第一个
        if name in [p.name for p in self.data.parents]:
            QMessageBox.warning(self, "提示", "已有叫「{}」的分类，换一个名字吧".format(name))
            return
        self.data.add_parent(name)
        self.data.current_parent_idx = len(self.data.parents) - 1
        self.scheduler = PlanScheduler(self.data.current_parent)
        self.refresh_all()
        self.data.save()

    def on_rename_parent(self):
        idx = self.parent_list.currentRow()
        if idx < 0:
            QMessageBox.information(self, "提示", "请先在列表里选中一个分类")
            return
        new_name, ok = QInputDialog.getText(self, "重命名", "新名称:", text=self.data.parents[idx].name)
        if ok and new_name.strip():
            new_name = new_name.strip()
            if new_name != self.data.parents[idx].name and \
                    new_name in [p.name for p in self.data.parents]:
                QMessageBox.warning(self, "提示", "已有叫「{}」的分类，换一个名字吧".format(new_name))
                return
            self.data.parents[idx].name = new_name
            self.refresh_all()
            self.data.save()

    def on_del_parent(self):
        idx = self.parent_list.currentRow()
        if idx < 0:
            QMessageBox.information(self, "提示", "请先在列表里选中一个分类")
            return
        if len(self.data.parents) <= 1:
            QMessageBox.warning(self, "提示", "至少保留一个分类")
            return
        reply = QMessageBox.question(
            self, "确认删除",
            "删除分类「{}」？\n\n该分类的计划、进度、归档将一并删除，且无法撤销。".format(
                self.data.parents[idx].name),
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
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

    def _toggle_more(self):
        """v0.27b：重置进度 / 导入 / 导出 / 预览 的折叠开关（v0.29：带高度动画）"""
        animations.toggle_section(self._more_container, self._more_toggle.isChecked())

    def _toggle_date_group(self):
        """v0.27b：起始日期折叠（v0.29：带高度动画）"""
        checked = self._date_toggle.isChecked()
        animations.toggle_section(self._date_body, checked)
        self._date_toggle.setText("▾ 起始日期" if checked else "▸ 起始日期")

    def _toggle_parent_group(self):
        checked = self._parent_toggle.isChecked()
        animations.toggle_section(self._parent_body, checked)
        self._parent_toggle.setText("▾ 计划分类" if checked else "▸ 计划分类")

    def _toggle_plan_group(self):
        checked = self._plan_toggle.isChecked()
        animations.toggle_section(self._plan_body, checked)
        self._plan_toggle.setText("▾ 计划清单" if checked else "▸ 计划清单")

    def _toggle_slot_group(self):
        checked = self._slot_toggle.isChecked()
        animations.toggle_section(self._slot_body, checked)
        self._slot_toggle.setText("▾ 时段" if checked else "▸ 时段")

    def refresh_all(self):
        # 分类列表
        self.parent_list.blockSignals(True)
        self.parent_list.clear()
        for i, p in enumerate(self.data.parents):
            self.parent_list.addItem(f"{i+1}. {p.name}")
        if self.data.current_parent_idx < self.parent_list.count():
            self.parent_list.setCurrentRow(self.data.current_parent_idx)
        self.parent_list.blockSignals(False)

        cp = self.data.current_parent
        self.parent_name_label.setText(f"正在编辑：{cp.name}")

        # v0.30 R26（审计 P2-14）：重建列表前记住选中行和滚动位置，重建后还原，
        # 连续编辑（添加/上移/下移）时界面不再跳回顶部
        plan_cur = self.plan_list.currentRow()
        plan_scroll = self.plan_list.verticalScrollBar().value()
        slot_cur = self.slot_list.currentRow()
        slot_scroll = self.slot_list.verticalScrollBar().value()

        # 计划
        self.plan_list.clear()
        for i, plan in enumerate(cp.plans):
            self.plan_list.addItem(f"{i+1}. {plan}")

        # 时段
        self.slot_list.clear()
        for i, slot in enumerate(cp.time_slots):
            disp = slot["name"]
            if slot.get("count", 1) > 1:
                disp += f" ×{slot['count']}"
            self.slot_list.addItem(f"{i+1}. {disp}")

        # 还原选中与滚动位置
        if 0 <= plan_cur < self.plan_list.count():
            self.plan_list.setCurrentRow(plan_cur)
            self.plan_list.verticalScrollBar().setValue(plan_scroll)
        if 0 <= slot_cur < self.slot_list.count():
            self.slot_list.setCurrentRow(slot_cur)
            self.slot_list.verticalScrollBar().setValue(slot_scroll)

        if cp.start_date:
            self.date_edit.setDate(cp.start_date)

        self.scheduler = PlanScheduler(cp)

        # v0.30：配齐计划+时段后引导条淡出退场（不瞬移）
        should_show = not (cp.plans and cp.time_slots)
        if not should_show and self.guide_label.isVisible():
            animations.fade_out(self.guide_label, theme.MOTION["fast"])
        else:
            self.guide_label.setVisible(should_show)

    def _reveal(self, toggle, body, input_widget=None):
        """v0.30：校验失败时展开对应折叠组并聚焦输入框（审计 P1-8）。"""
        if not toggle.isChecked():
            toggle.setChecked(True)
            toggle.setText(toggle.text().replace("▸", "▾", 1))
        animations.toggle_section(body, True)
        if input_widget is not None:
            input_widget.setFocus()

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
            QMessageBox.information(self, "提示", "请先在列表里选中一项")
            return
        new_text, ok = QInputDialog.getText(self, "编辑计划", "新内容:", text=self.data.current_parent.plans[cur])
        if ok and new_text.strip():
            self.data.current_parent.plans[cur] = new_text.strip()
            self.refresh_all()
            self.data.save()

    def del_plan(self):
        cur = self.plan_list.currentRow()
        if cur < 0:
            QMessageBox.information(self, "提示", "请先在列表里选中一项")
            return
        # v0.30（审计 P0-2）：删除不可撤销（撤销栈不覆盖编辑器），必须确认
        name = self.data.current_parent.plans[cur]
        ans = QMessageBox.question(
            self, "确认删除",
            "删除计划「{}」？\n\n删除后无法撤销（执行页的进度不受影响）。".format(name),
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if ans != QMessageBox.Yes:
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
        if self.data.current_parent.borrowed_slots:
            QMessageBox.warning(
                self, "提示",
                "分类「{}」今天有额外安排正在进行，暂时无法修改时段。\n完成今天后再来调整吧。".format(
                    self.data.current_parent.name))
            return
        self.data.current_parent.time_slots.append({"name": name, "count": count})
        self.slot_name_input.clear()
        self.slot_count_input.setValue(1)
        self.refresh_all()
        self.data.save()

    def edit_slot(self):
        cur = self.slot_list.currentRow()
        if cur < 0:
            QMessageBox.information(self, "提示", "请先在列表里选中一项")
            return
        if self.data.current_parent.borrowed_slots:
            QMessageBox.warning(
                self, "提示",
                "分类「{}」今天有额外安排正在进行，暂时无法修改时段。\n完成今天后再来调整吧。".format(
                    self.data.current_parent.name))
            return
        slot = self.data.current_parent.time_slots[cur]
        # v0.30：一个表单搞定名字+数量（审计 P1-4：不再连弹两个框）
        dlg = _SlotEditDialog(self, slot["name"], slot.get("count", 1))
        if dlg.exec_() == QDialog.Accepted:
            name = dlg.name_edit.text().strip()
            if name:
                self.data.current_parent.time_slots[cur] = {
                    "name": name, "count": dlg.count_spin.value(),
                }
                self.refresh_all()
                self.data.save()

    def del_slot(self):
        cur = self.slot_list.currentRow()
        if cur < 0:
            QMessageBox.information(self, "提示", "请先在列表里选中一项")
            return
        if self.data.current_parent.borrowed_slots:
            QMessageBox.warning(
                self, "提示",
                "分类「{}」今天有额外安排正在进行，暂时无法修改时段。\n完成今天后再来调整吧。".format(
                    self.data.current_parent.name))
            return
        # v0.30（审计 P0-3）：删时段会改变每天的分格结构，今天的格子状态会重排
        name = self.data.current_parent.time_slots[cur]["name"]
        ans = QMessageBox.question(
            self, "确认删除",
            "删除时段「{}」？\n\n每天的分格会变化，今天的格子状态会重排；删除后无法撤销。".format(name),
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if ans != QMessageBox.Yes:
            return
        self.data.current_parent.time_slots.pop(cur)
        self.refresh_all()
        self.data.save()

    def slot_up(self):
        if self.data.current_parent.borrowed_slots:
            QMessageBox.warning(
                self, "提示",
                "分类「{}」今天有额外安排正在进行，暂时无法修改时段。".format(
                    self.data.current_parent.name))
            return
        cur = self.slot_list.currentRow()
        if cur > 0:
            s = self.data.current_parent.time_slots
            s[cur-1], s[cur] = s[cur], s[cur-1]
            self.refresh_all()
            self.slot_list.setCurrentRow(cur - 1)
            self.data.save()

    def slot_down(self):
        if self.data.current_parent.borrowed_slots:
            QMessageBox.warning(
                self, "提示",
                "分类「{}」今天有额外安排正在进行，暂时无法修改时段。".format(
                    self.data.current_parent.name))
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

    # ====== v0.4 主题切换 ======

    def on_theme_changed(self, idx):
        """主题下拉框变化：应用 + 持久化。"""
        key = self.theme_combo.itemData(idx)
        if not key:
            return
        apply_theme(QApplication.instance(), key)
        animations.fade_in(self, theme.MOTION["fast"])   # R16：换肤后轻淡入缓冲硬切
        from theme import app_settings
        s = app_settings()
        s.setValue(THEME_KEY, key)

    # ====== v0.4 导入/导出 ======

    def on_restore_backup(self):
        """v0.30 R23：一键恢复上一次保存前的数据（plan_data_backup）。

        save() 每次写入前都会把上一代数据自动挪进 plan_data_backup，
        所以这个入口能撤销「最近一次保存」造成的变化（误删分类/误导入等）。
        恢复本身也会 save —— 被恢复掉的当前数据同样进 backup，可再次恢复（来回切）。
        """
        import json as _json
        from theme import app_settings
        s = app_settings()
        # v0.30 R31：与 3 代备份环配套 —— 让用户选恢复哪一代
        gens = [
            ("上一次保存前（最近备份）", "plan_data_backup"),
            ("上上次保存前", "plan_data_backup_2"),
            ("第三次保存前", "plan_data_backup_3"),
        ]
        available = [(label, key) for label, key in gens if s.value(key)]
        if not available:
            QMessageBox.information(
                self, "恢复备份", "还没有可用的备份（备份在第一次保存之后才会生成）。")
            return
        backup = None
        if len(available) == 1:
            backup = s.value(available[0][1])
        else:
            sel, ok = QInputDialog.getItem(
                self, "恢复备份", "恢复到哪一步？", [label for label, _ in available], 0, False)
            if not ok:
                return
            backup = s.value(dict(available)[sel])
        if not backup:
            QMessageBox.information(
                self, "恢复备份", "还没有可用的备份（备份在第一次保存之后才会生成）。")
            return
        try:
            data = _json.loads(backup)
            if not isinstance(data, dict):
                raise ValueError("备份不是 JSON 对象")
        except Exception as e:
            QMessageBox.warning(self, "恢复备份", "备份读不出来：{}".format(e))
            return

        try:
            n_parents = len(data.get("parents", []))
        except Exception:
            n_parents = 0
        reply = QMessageBox.question(
            self, "确认恢复备份",
            "把所有数据回滚到上一次保存前的状态（共 {} 个分类）？\n\n"
            "当前数据也会被自动备份，可以再次「恢复」切回来。".format(n_parents),
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if reply != QMessageBox.Yes:
            return

        self.data.from_dict(data)
        self.data.save()
        if self.on_data_reloaded:
            self.on_data_reloaded()
        self.refresh_all()
        QMessageBox.information(self, "恢复备份", "已恢复到上一次保存前的数据。")

    def on_reset_progress(self):
        """重置当前分类进度：current_day=0, borrowed_slots=[]。
        plans/time_slots/start_date 不变。
        """
        cp = self.data.current_parent
        if cp.current_day == 0 and not cp.borrowed_slots:
            QMessageBox.information(
                self, "提示",
                f"分类「{cp.name}」进度已是初始状态（第 1 天），无需重置。",
            )
            return

        borrowed_n = len(cp.borrowed_slots)
        confirm = QMessageBox.question(
            self, "确认重置进度",
            f"将重置分类「{cp.name}」的进度：\n"
            f"  • 当前天：第 {cp.current_day + 1} 天 → 第 1 天\n"
            f"  • 额外安排：{borrowed_n} 条 → 清空\n\n"
            f"计划内容、时段、起始日期不变。\n"
            f"确认重置？",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if confirm != QMessageBox.Yes:
            return

        cp.reset_progress()
        self.data.save()
        if self.on_data_reloaded:
            self.on_data_reloaded()  # executor 也要刷
        self.refresh_all()
        QMessageBox.information(
            self, "重置完成",
            f"分类「{cp.name}」进度已重置为第 1 天。",
        )

    def on_export(self):
        """导出当前所有分类为 JSON"""
        self.save_current_to_parent()
        self.data.save()  # 确保磁盘最新
        from datetime import date
        default_name = f"RollingPlan_backup_{date.today().isoformat()}.json"
        path, _ = QFileDialog.getSaveFileName(
            self, "导出计划数据", default_name,
            "JSON 文件 (*.json);;所有文件 (*)",
        )
        if not path:
            return
        ok, msg = self.data.export_to_file(path)
        if ok:
            QMessageBox.information(self, "导出成功", msg)
        else:
            QMessageBox.warning(self, "导出失败", msg)

    def on_import(self):
        """从 JSON 导入。会覆盖当前所有数据。

        v0.30 修数据丢失链（健壮性审计 P0-2/P2-6）：
        - import_from_file 内部就会 from_dict 覆盖内存，旧版「确认框点否」时靠
          data.load() 从磁盘回滚 —— 但 load 可能失败（全新安装盘上还没有 plan_data），
          而且就算 load 成功，from_dict 也会把 parents 换成一批**新对象**，
          executor / 归档页的 scheduler 仍指向孤立的旧 ParentPlan，
          之后任何完成动作都写进孤立对象然后被 save 静默丢弃。
        - 现在导入前抓 to_dict 快照；点「否」直接 from_dict(快照) 恢复内存，
          并像导入成功一样通知 on_data_reloaded() 重建 executor / 刷归档页，
          保证三个页面重新绑到同一批对象上。
        """
        path, _ = QFileDialog.getOpenFileName(
            self, "导入计划数据", "",
            "JSON 文件 (*.json);;所有文件 (*)",
        )
        if not path:
            return

        snapshot = self.data.to_dict()   # 覆盖前的内存快照（取消时就恢复它）

        ok, msg, stats = self.data.import_from_file(path)
        if not ok:
            QMessageBox.warning(
                self, "导入失败",
                "这个文件可能不是 RollingPlan 导出的备份文件。\n\n技术细节：" + msg)
            return

        # 校验失败分支已返回；此处 stats 必非 None
        assert stats is not None
        s_parents = stats["parents"]
        s_plans = stats["plans_total"]
        s_borrowed = stats["borrowed_total"]

        # 确认覆盖
        confirm = QMessageBox.question(
            self, "确认导入",
            f"将覆盖当前所有数据：\n"
            f"  • 分类数：{s_parents}\n"
            f"  • 计划总数：{s_plans}\n"
            f"  • 当前未完成的额外安排：{s_borrowed}\n\n"
            f"确认导入？此操作会覆盖现有数据。",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if confirm != QMessageBox.Yes:
            # 取消：恢复导入前的内存状态（不碰磁盘），并同步三个页面的对象绑定
            self.data.from_dict(snapshot)
            if self.on_data_reloaded:
                self.on_data_reloaded()
            self.refresh_all()
            return

        # 写入磁盘 + 通知主窗口刷 executor + 刷自己
        self.data.save()
        if self.on_data_reloaded:
            self.on_data_reloaded()
        self.refresh_all()
        QMessageBox.information(
            self, "导入成功",
            f"已导入：分类 {s_parents} 个，"
            f"计划 {s_plans} 条，"
            f"额外安排 {s_borrowed} 条。",
        )

    def preview_calendar(self):
        self.save_current_to_parent()
        self.scheduler = PlanScheduler(self.data.current_parent)
        p = self.data.current_parent
        if not p.plans:
            QMessageBox.warning(self, "提示", "请先在「计划清单」添加要做的事")
            self._reveal(self._plan_toggle, self._plan_body, self.plan_input)
            return
        if not p.time_slots:
            QMessageBox.warning(self, "提示", "请先在「时段」划分一天")
            self._reveal(self._slot_toggle, self._slot_body, self.slot_name_input)
            return
        self._reveal(self._plan_toggle, self._plan_body)      # 保险：都齐了才走到这
        self._reveal(self._slot_toggle, self._slot_body)
        cal = self.scheduler.raw_calendar()
        lines = [f"📅 【{p.name}】计划预览（共 {len(cal)} 天）", "=" * 40]
        for i, (d, plans) in enumerate(cal):
            lines.append(f"\n第{i+1}天 ({d.toString('MM-dd ddd')}):")
            for sname, plan in plans:
                m = "✓" if plan else "·"
                lines.append(f"  {m} {sname}: {plan if plan else '(空)'}")
        self.preview_area.setText("\n".join(lines))
        self.preview_area.setVisible(True)   # v0.28：有内容才占版面
        animations.fade_in(self.preview_area, theme.MOTION["base"])   # 预览区浮现

    def go_exec(self):
        cp = self.data.current_parent
        if not cp.plans or not cp.time_slots or not cp.start_date:
            missing = []
            if not cp.plans:
                missing.append("计划清单（添加要做的事）")
            if not cp.time_slots:
                missing.append("时段（一天分几段）")
            if not cp.start_date:
                missing.append("起始日期（哪天开始）")
            QMessageBox.warning(self, "提示", "还差这些就能开始：\n  • " + "\n  • ".join(missing))
            if not cp.plans:
                self._reveal(self._plan_toggle, self._plan_body, self.plan_input)
            elif not cp.time_slots:
                self._reveal(self._slot_toggle, self._slot_body, self.slot_name_input)
            return
        self.save_current_to_parent()
        self.data.save()
        self.on_switch_to_exec()




class _SlotEditDialog(QDialog):
    """v0.30：时段编辑单表单（名字 + 数量一个框搞定，替代两个 QInputDialog 串联）。"""

    def __init__(self, parent, name="", count=1):
        super().__init__(parent)
        self.setWindowTitle("编辑时段")
        self.setMinimumWidth(280)
        form = QFormLayout(self)
        form.setSpacing(12)
        form.setContentsMargins(20, 16, 20, 16)

        self.name_edit = QLineEdit(name)
        self.name_edit.setPlaceholderText("早 / 中 / 晚……")
        form.addRow("时段名", self.name_edit)

        self.count_spin = QSpinBox()
        self.count_spin.setRange(1, 10)
        self.count_spin.setValue(count)
        self.count_spin.setPrefix("每天 ")
        self.count_spin.setSuffix(" 次")
        form.addRow("数量", self.count_spin)

        btns = QHBoxLayout()
        cancel_btn = QPushButton("取消")
        cancel_btn.clicked.connect(self.reject)
        ok_btn = QPushButton("确定")
        ok_btn.setObjectName("rpPrimary")
        ok_btn.clicked.connect(self.accept)
        btns.addStretch(1)
        btns.addWidget(cancel_btn)
        btns.addWidget(ok_btn)
        form.addRow(btns)

        self.name_edit.setFocus()
        self.name_edit.selectAll()
        self.name_edit.returnPressed.connect(self.accept)
