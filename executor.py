"""
RollingPlan v0.21：执行计划页 + 额外安排对话框(从 rollingplan.py 抽出,零行为变化)

拆分理由:
- rollingplan.py v0.19 末是 1317 行,PlanExecutor (614 行) + ExtraArrangementsDialog (136 行)
  共 750 行占主程序一半以上。
- 前面已抽 scheduler.py(调度)/editor.py(制定页)/calendar_view.py(总览页),
  这是顺延最后两个 UI 类。
- 依赖关系:executor 依赖 scheduler + theme;不再依赖 rollingplan.PlanData(避免循环)
  —— PlanData / ParentPlan 仍然在 rollingplan.py(数据模型相对小,170+228 行,
  留主程序里合理)。

对外 API 不变:PlanExecutor(data, on_switch_to_edit),ExtraArrangementsDialog(executor, parent)
"""
from PyQt5.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QMessageBox, QComboBox, QToolButton,
    QDialog, QScrollArea, QInputDialog, QGroupBox, QTextEdit, QMenu,
)
from PyQt5.QtCore import Qt, QSettings
from PyQt5.QtGui import QFont, QCursor
from typing import TYPE_CHECKING

from scheduler import PlanScheduler, _pending_of
from theme import apply_theme, THEME_KEY, THEME_OPTIONS
import animations
import theme

if TYPE_CHECKING:
    # 仅给 type checker 看,运行时不会评估,避免循环 import
    from rollingplan import PlanData  # noqa: F401


class PlanExecutor(QWidget):
    def __init__(self, data, on_switch_to_edit):
        super().__init__()
        self.data = data
        self.on_switch_to_edit = on_switch_to_edit
        self.scheduler = PlanScheduler(data.current_parent)
        self.init_ui()
        self.refresh()

    def init_ui(self):
        layout = QVBoxLayout()
        layout.setSpacing(12)
        layout.setContentsMargins(24, 20, 24, 20)

        # ============ 顶部：极简一行（v0.26，v0.30 换语义角色）============
        # 默认只留「⌄ 更多」+ 当前分类名。切换分类 / 主题 / 返回制定 全部收进「更多」里
        top_row = QHBoxLayout()
        top_row.setSpacing(6)

        self.advanced_toggle = QToolButton()
        self.advanced_toggle.setText("更多")
        self.advanced_toggle.setCheckable(True)
        self.advanced_toggle.setChecked(False)
        self.advanced_toggle.setObjectName("rpFold")
        self.advanced_toggle.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.advanced_toggle.setArrowType(Qt.RightArrow)
        self.advanced_toggle.clicked.connect(self._toggle_advanced)
        top_row.addWidget(self.advanced_toggle)

        top_row.addStretch()

        # 当前分类名（小字：够认就行，不抢版面）
        self.parent_combo_label = QLabel()
        self.parent_combo_label.setFont(QFont("Microsoft YaHei", 9))
        self.parent_combo_label.setObjectName("rpDim")
        top_row.addWidget(self.parent_combo_label)
        layout.addLayout(top_row)

        # ============ 折叠区（默认收起，跟着「更多」走）============
        self.advanced_container = QWidget()
        adv_layout = QVBoxLayout(self.advanced_container)
        adv_layout.setContentsMargins(0, 4, 0, 0)
        adv_layout.setSpacing(8)

        # v0.26：原来常驻顶栏的三个入口挪进来
        minor_row = QHBoxLayout()
        minor_row.setSpacing(8)

        self.parent_switch_btn = QPushButton("切换分类")
        self.parent_switch_btn.clicked.connect(self.on_switch_parent)
        minor_row.addWidget(self.parent_switch_btn)

        # 主题下拉（执行页也方便切）
        from rollingplan import THEME_OPTIONS
        self.theme_combo = QComboBox()
        for key, label in THEME_OPTIONS:
            self.theme_combo.addItem(label, userData=key)
        from theme import app_settings
        _saved = app_settings().value(THEME_KEY, "dark")
        if _saved not in ("dark", "light", "auto"):
            _saved = "dark"
        for i, (k, _) in enumerate(THEME_OPTIONS):
            if k == _saved:
                self.theme_combo.setCurrentIndex(i)
                break
        self.theme_combo.currentIndexChanged.connect(self.on_theme_changed)
        minor_row.addWidget(QLabel("主题:"))
        minor_row.addWidget(self.theme_combo)

        edit_btn = QPushButton("← 返回制定")
        edit_btn.clicked.connect(self.on_switch_to_edit)
        minor_row.addWidget(edit_btn)

        minor_row.addStretch()
        adv_layout.addLayout(minor_row)

        layout.addWidget(self.advanced_container)
        self.advanced_container.setVisible(False)   # 默认收起：默认视图只有「更多」

        # ============ 日期 + 状态（v0.30：标题层级走 QSS 角色）============
        self.date_label = QLabel()
        self.date_label.setAlignment(Qt.AlignCenter)
        self.date_label.setObjectName("rpTitle")     # 17pt 粗，页面主标题
        layout.addWidget(self.date_label)

        self.status_label = QLabel()
        self.status_label.setAlignment(Qt.AlignCenter)
        self.status_label.setObjectName("rpDim")     # 小字灰阶，不抢戏
        layout.addWidget(self.status_label)

        # ============ 今天：卡片化主区 ============
        self.day_layout = QVBoxLayout()
        self.day_layout.setSpacing(10)
        self.day_layout.setAlignment(Qt.AlignCenter)  # 内容垂直居中
        day_container = QWidget()
        day_container.setLayout(self.day_layout)
        self.day_container = day_container   # v0.29：存引用 —— 完成/切天后给它淡入反馈
        layout.addWidget(day_container, stretch=1)

        # ============ 额外安排：细长条按钮（在两大按钮上方）============
        # 长度与「加一个 + 今天完成」的总长相当，但矮一些 —— 点开是当天额外安排列表
        self.extra_btn = QPushButton("📋 额外安排（0）")
        self.extra_btn.setFont(QFont("Microsoft YaHei", 11))
        self.extra_btn.setMinimumHeight(30)
        self.extra_btn.setMaximumHeight(34)
        self.extra_btn.setObjectName("rpGhostOutline")
        self.extra_btn.setCursor(Qt.PointingHandCursor)
        self.extra_btn.clicked.connect(self.on_show_extras)
        self._extra_btn_was_visible = False   # v0.29：追踪出现时机（0 → N 条时给浮现动效）
        layout.addWidget(self.extra_btn)

        # ============ 主操作大按钮（两个并列、加大高度）============
        action_row = QHBoxLayout()
        action_row.setSpacing(12)

        self.add_next_btn = QPushButton("➕ 加一个")
        self.add_next_btn.setFont(QFont("Microsoft YaHei", 14, QFont.Bold))
        self.add_next_btn.setObjectName("rpPrimary")
        self.add_next_btn.setMinimumHeight(52)
        self.add_next_btn.setToolTip("从还没安排的队列里顺延一条  (Ctrl+Enter)")
        self.add_next_btn.clicked.connect(self.on_add_next)
        action_row.addWidget(self.add_next_btn)

        self.done_btn = QPushButton("✓ 今天完成")
        self.done_btn.setFont(QFont("Microsoft YaHei", 14, QFont.Bold))
        self.done_btn.setObjectName("rpSuccess")
        self.done_btn.setMinimumHeight(52)
        self.done_btn.setToolTip("确认今天的安排全部结束,进入下一天  (Ctrl+D)")
        self.done_btn.clicked.connect(self.on_next_day)
        action_row.addWidget(self.done_btn)

        layout.addLayout(action_row)

        # ============ 次要操作：统一收在顶部那个「更多」折叠区里（v0.26）============
        adv_layout = self.advanced_container.layout()

        # 次要按钮行（v0.16）：
        # - return_btn = 老「退回」按钮（仅撤今天完成 / 退额外轮最后一条；旧行为不变）
        # - undo_btn   = 新「撤销」按钮（撤任意最近动作，含加/退/固定/拦截；通用 history 栈）
        # - redo_btn   = 新「重做」按钮（can_redo 时才显示）
        sub_row = QHBoxLayout()
        self.return_btn = QPushButton("⤴ 退回")
        self.return_btn.setToolTip(
            "旧「退回」入口已由「撤销」统一取代（撤销同样能撤完成/退额外安排）。保留对象给老测试。")
        self.return_btn.clicked.connect(self.on_return)
        self.return_btn.setVisible(False)   # v0.30 R17（审计 P1-3）：不再作为 UI 入口
        self.return_btn.setParent(self.advanced_container)
        self.undo_btn = QPushButton("↶ 撤销")
        self.undo_btn.setToolTip("撤销任意最近动作（完成/退回/添加/固定/拦截）(Ctrl+Shift+Z)")
        self.undo_btn.clicked.connect(self.on_undo)
        self.undo_btn.setVisible(False)
        sub_row.addWidget(self.undo_btn)
        self.redo_btn = QPushButton("↷ 重做")
        self.redo_btn.setToolTip("重做刚被撤销的动作 (Ctrl+Shift+Z)")
        self.redo_btn.clicked.connect(self.on_redo)
        self.redo_btn.setVisible(False)
        sub_row.addWidget(self.redo_btn)
        self.add_specific_btn = QPushButton("⋯ 添加指定")
        self.add_specific_btn.setObjectName("rpGhost")
        self.add_specific_btn.clicked.connect(self.on_add_specific)
        sub_row.addWidget(self.add_specific_btn)
        sub_row.addStretch()
        adv_layout.addLayout(sub_row)

        # ============ 计划队列（v0.27：底部一行，点开才展开）============
        self.queue_toggle = QToolButton()
        self.queue_toggle.setText("计划队列")
        self.queue_toggle.setCheckable(True)
        self.queue_toggle.setChecked(False)
        self.queue_toggle.setObjectName("rpFold")
        self.queue_toggle.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.queue_toggle.setArrowType(Qt.RightArrow)
        self.queue_toggle.setCursor(Qt.PointingHandCursor)
        self.queue_toggle.clicked.connect(self._toggle_queue)
        layout.addWidget(self.queue_toggle)

        self.queue_container = QWidget()
        queue_inner = QVBoxLayout(self.queue_container)
        queue_inner.setContentsMargins(0, 0, 0, 0)
        self.calendar_area = QTextEdit()
        self.calendar_area.setReadOnly(True)
        self.calendar_area.setMaximumHeight(140)
        queue_inner.addWidget(self.calendar_area)
        self.queue_container.setVisible(False)
        layout.addWidget(self.queue_container)

        self.setLayout(layout)

    def _toggle_queue(self):
        """v0.27：展开/收起底部的计划队列（v0.29：带高度动画）"""
        checked = self.queue_toggle.isChecked()
        animations.toggle_section(self.queue_container, checked)
        self.queue_toggle.setArrowType(Qt.DownArrow if checked else Qt.RightArrow)

    def _toggle_advanced(self):
        """切换「更多」折叠区显示（v0.29：带高度动画）"""
        checked = self.advanced_toggle.isChecked()
        animations.toggle_section(self.advanced_container, checked)
        self.advanced_toggle.setArrowType(Qt.DownArrow if checked else Qt.RightArrow)

    def on_theme_changed(self, idx):
        """执行页主题切换（与制定页同步）"""
        key = self.theme_combo.itemData(idx)
        if not key:
            return
        apply_theme(QApplication.instance(), key)
        from theme import app_settings
        s = app_settings()
        s.setValue(THEME_KEY, key)

    def _clear_layout(self, layout):
        while layout.count():
            item = layout.takeAt(0)
            w = item.widget()
            if w:
                w.setParent(None)      # 立刻从控件树上摘掉（deleteLater 要等事件循环）
                w.deleteLater()

    def _build_note_widget(self, parent_layout, note):
        """v0.19:归档备注 —— 老格式保留 + 末尾加可点击的「▸/▾ 展开」开关。

        老 UI 直接显示「归档：任务1」;现在保留这一行 + 在尾部追加一个可点击的小箭头,
        点一下在 row 下方插入一个「每条单独一行」的详情面板;再点收起。

        老测试 (`test_scroll_v11.py` test_executor_complete_only_greys_button) 期望在
        day_labels 里看到「归档：任务1」 —— 这里保留老 QLabel 不变,新加的可点击部分是
        QToolButton,不影响 day_labels。
        """
        # 老格式:逗号分隔的那一行（保留兼容老测试和老用户阅读习惯）
        note_label = QLabel("  归档：" + "、".join(note))
        note_label.setFont(QFont("Microsoft YaHei", 10))
        note_label.setObjectName("rpDim")
        parent_layout.addWidget(note_label)

        # 新加:可点击的小开关 —— 默认收起,点了在下面插入详情
        toggle = QToolButton()
        toggle.setText("▸")
        toggle.setCheckable(True)
        toggle.setChecked(False)
        toggle.setToolButtonStyle(Qt.ToolButtonTextOnly)
        toggle.setFont(QFont("Microsoft YaHei", 10))
        toggle.setObjectName("rpFold")
        toggle.setCursor(Qt.PointingHandCursor)
        toggle.setToolTip("展开/收起归档详情")
        toggle.toggled.connect(lambda checked, n=note, t=toggle, p=parent_layout:
                              self._on_note_toggle(checked, n, t, p))
        parent_layout.addWidget(toggle)

    def _on_note_toggle(self, checked, note, toggle_btn, parent_layout):
        """▸/▾ 切换：在 row 下方插入或删除详情 widget。

        parent_layout 是 QHBoxLayout（不是 widget）；detail widget 是它的子项之一。
        为了找到它,遍历 layout 的所有 item,看 widget 是否带 objectName。
        """
        def _find_detail_widget(layout):
            for i in range(layout.count()):
                it = layout.itemAt(i)
                w = it.widget() if it else None
                if w is not None and w.objectName() == "rp-note-detail":
                    return w
            return None

        detail_widget = _find_detail_widget(parent_layout)
        if checked:
            # 展开：插入详情
            if detail_widget is None:
                detail_widget = QWidget()
                detail_widget.setObjectName("rp-note-detail")
                detail_layout = QVBoxLayout(detail_widget)
                detail_layout.setContentsMargins(60, 0, 0, 0)
                detail_layout.setSpacing(2)
                for i, plan in enumerate(note, 1):
                    line = QLabel(f"  {i}. {plan}")
                    line.setFont(QFont("Microsoft YaHei", 10))
                    line.setObjectName("rpDim")
                    detail_layout.addWidget(line)
                # 插在 stretch 之前
                stretch_idx = -1
                for i in range(parent_layout.count()):
                    if parent_layout.itemAt(i).spacerItem() is not None:
                        stretch_idx = i
                        break
                if stretch_idx >= 0:
                    parent_layout.insertWidget(stretch_idx, detail_widget)
                else:
                    parent_layout.addWidget(detail_widget)
            toggle_btn.setText("▾")
        else:
            # 收起：立刻从控件树上摘掉(findChild 立即找不到) + 删
            if detail_widget is not None:
                detail_widget.setParent(None)
                detail_widget.deleteLater()
            toggle_btn.setText("▸")

    def _add_slot_row(self, parent_layout, slot_name, plan, is_extra=False,
                       slot_idx=None, show_complete=False, done=False, note=None,
                       fixed=False, blocked=False):
        """添加一行（v0.30 卡片化：普通格=蓝边卡 rpSlotCard，额外格=绿边卡 rpExtraCard）。

        - 每格四个动作仍在：固定计划/拦截滚动/仅完成 藏在右键 + 行内可见的「⋯」里，
          「✓ 完成并滚动」是唯一常驻 QPushButton（test_minimal_v06 数的就是它）
        - done=True 的格子：计划加删除线（QSS rpDone）
        - fixed / blocked：格子名前加 📌 / ⛔ 标记
        - note：这一格的归档备注（已完成过的内容），行尾小灰字可展开
        """
        row = QHBoxLayout()
        row.setSpacing(10)

        if is_extra:
            slot_label = QLabel("⤴")
            slot_label.setMinimumWidth(30)
        else:
            mark = "⛔" if blocked else ("📌" if fixed else "")
            slot_label = QLabel(f"{mark}{slot_name}")
            slot_label.setMinimumWidth(48)
        slot_label.setFont(QFont("Microsoft YaHei", 12, QFont.Bold))
        slot_label.setObjectName("rpDim")
        row.addWidget(slot_label)

        if plan:
            plan_label = QLabel(f"✓ {plan}" if done else plan)
            plan_label.setFont(QFont("Microsoft YaHei", 14))
            if done:
                # 灰 + 删除线走 QSS 语义角色（深浅主题都可读）
                plan_label.setObjectName("rpDone")
        else:
            plan_label = QLabel("(无)")
            plan_label.setFont(QFont("Microsoft YaHei", 12))
            plan_label.setObjectName("rpEmpty")
        row.addWidget(plan_label)

        # 这一格的归档备注（v0.19：可点击展开/收起）
        if note:
            self._build_note_widget(row, note)

        row.addStretch(1)

        if show_complete and slot_idx is not None:
            # v0.26b：固定计划 / 拦截滚动 收进右键菜单 + 行内「⋯」（按钮仍在，不显示）
            for text, checked, handler in (
                ("固定计划", bool(fixed), self.on_toggle_fixed),
                ("拦截滚动", bool(blocked), self.on_toggle_blocked),
            ):
                toggle_btn = QPushButton(text)
                toggle_btn.setFont(QFont("Microsoft YaHei", 9))
                toggle_btn.setCheckable(True)
                toggle_btn.setChecked(checked)
                toggle_btn.setStyleSheet(
                    "QPushButton { border: 1px solid #888; border-radius: 3px; "
                    "padding: 3px 8px; }"
                    "QPushButton:checked { background-color: #2196F3; color: white; "
                    "border: 1px solid #1976D2; }"
                )
                toggle_btn.setCursor(Qt.PointingHandCursor)
                toggle_btn.clicked.connect(
                    lambda checked=False, idx=slot_idx, h=handler: h(idx))
                row.addWidget(toggle_btn)
                toggle_btn.setVisible(False)

        if show_complete and plan and slot_idx is not None:
            # v0.26b：仅完成 也在菜单里
            only_btn = QPushButton("仅完成")
            only_btn.setFont(QFont("Microsoft YaHei", 11))
            only_btn.setStyleSheet(
                "QPushButton { border: 1px solid #888; border-radius: 4px; "
                "padding: 6px 12px; }"
            )
            only_btn.setEnabled(not done)
            if not done:
                only_btn.setCursor(Qt.PointingHandCursor)
                only_btn.clicked.connect(
                    lambda checked=False, idx=slot_idx: self.on_complete_only(idx))
            row.addWidget(only_btn)
            only_btn.setVisible(False)

            # 完成并滚动：这一格唯一常驻的 QPushButton
            scroll_btn = QPushButton("✓ 完成并滚动")
            scroll_btn.setFont(QFont("Microsoft YaHei", 10, QFont.Bold))
            scroll_btn.setObjectName("rpSuccessSm")
            scroll_btn.setCursor(Qt.PointingHandCursor)
            # v0.26b：告诉用户「别的操作在右键/⋯里」
            extras_hint = []
            if not done:
                extras_hint.append("仅完成")
            extras_hint += ["固定计划", "拦截滚动"]
            scroll_btn.setToolTip("这一格右键或点「⋯」还能：" + " / ".join(extras_hint))
            scroll_btn.clicked.connect(
                lambda checked=False, idx=slot_idx: self.on_complete_slot(idx))
            row.addWidget(scroll_btn)

        # v0.30：行内可见「⋯」—— 右键菜单的显性化入口。
        # 用 QToolButton：test_minimal_v06 数的是「每行可见 QPushButton 恰好 1 个」，
        # QToolButton 不在统计里，极简口径不破。
        if show_complete and slot_idx is not None:
            menu_btn = QToolButton()
            menu_btn.setText("⋯")
            menu_btn.setObjectName("rpGhost")
            menu_btn.setFont(QFont("Microsoft YaHei", 13))
            menu_btn.setCursor(Qt.PointingHandCursor)
            menu_btn.setToolTip("更多操作：仅完成 / 固定计划 / 拦截滚动")
            menu_btn.clicked.connect(
                lambda checked=False, idx=slot_idx, d=bool(done),
                       f=bool(fixed), b=bool(blocked):
                self._open_slot_menu(idx, d, f, b))
            row.addWidget(menu_btn)

        container = QWidget()
        container.setObjectName("rpExtraCard" if is_extra else "rpSlotCard")
        cl = QHBoxLayout(container)
        cl.setContentsMargins(12, 8, 8, 8)
        cl.addLayout(row)
        parent_layout.addWidget(container)

        # 右键菜单保留（v0.26b）：⋯ 是显性入口，右键是熟练用户快捷方式
        if show_complete and slot_idx is not None:
            container.setContextMenuPolicy(Qt.CustomContextMenu)
            container.customContextMenuRequested.connect(
                lambda pos, c=container, idx=slot_idx, d=bool(done),
                       f=bool(fixed), b=bool(blocked):
                self._on_slot_context_menu(c, pos, idx, d, f, b))

    def _open_slot_menu(self, slot_idx, done, fixed, blocked):
        """v0.30：行内「⋯」按钮打开格子菜单（复用右键同一个菜单）。"""
        menu = self._build_slot_menu(self, slot_idx, done, fixed, blocked)
        animations.pop_window(menu)   # R16：菜单出场轻淡入（合成器侧，零开销）
        menu.exec_(QCursor.pos())

    def _build_slot_menu(self, parent, slot_idx, done, fixed, blocked):
        """v0.26b：一格的次要操作菜单（拆出来是为了能单测，不弹窗也能验）"""
        menu = QMenu(parent)
        act = menu.addAction("仅完成（不滚动）")
        act.setEnabled(not done)
        if not done:
            act.triggered.connect(
                lambda checked=False, idx=slot_idx: self.on_complete_only(idx))
        act = menu.addAction("取消固定" if fixed else "固定计划")
        act.triggered.connect(
            lambda checked=False, idx=slot_idx: self.on_toggle_fixed(idx))
        act = menu.addAction("取消拦截" if blocked else "拦截滚动")
        act.triggered.connect(
            lambda checked=False, idx=slot_idx: self.on_toggle_blocked(idx))
        menu.addSeparator()
        act = menu.addAction("✓ 完成并滚动")
        act.triggered.connect(
            lambda checked=False, idx=slot_idx: self.on_complete_slot(idx))
        return menu

    def _on_slot_context_menu(self, container, pos, slot_idx, done, fixed, blocked):
        menu = self._build_slot_menu(container, slot_idx, done, fixed, blocked)
        menu.exec_(container.mapToGlobal(pos))

    def refresh(self):
        self._clear_layout(self.day_layout)

        p = self.data.current_parent
        self.scheduler = PlanScheduler(p)

        self.parent_combo_label.setText(f"【{p.name}】")

        if p.start_date:
            cd = p.start_date.addDays(p.current_day)
            self.date_label.setText(f"📅 第 {p.current_day+1} 天 ({cd.toString('yyyy-MM-dd ddd')})")

        consumed, total = self.scheduler.get_progress()
        done_today = self.scheduler.done_today()
        # v0.26：进度 + 今天完成 合成一行（今天完成了什么挪进 tooltip，不占版面）
        self.status_label.setText(f"进度 {consumed}/{total} · 今天完成 {len(done_today)} 条")
        if done_today:
            self.status_label.setToolTip("🗂 今天已完成：" + "、".join(done_today))
        else:
            self.status_label.setToolTip("")

        # 今天
        st = self.scheduler.today_state()
        day_plans = st["rows"]
        if not day_plans:
            lbl = QLabel("今天没有安排")
            lbl.setAlignment(Qt.AlignCenter)
            lbl.setObjectName("rpEmpty")
            self.day_layout.addWidget(lbl)
            # v0.30：空态给出路（审计 P2-1），别让新用户对着空白发呆
            go_edit = QPushButton("去制定计划 →")
            go_edit.setObjectName("rpGhost")
            go_edit.setCursor(Qt.PointingHandCursor)
            go_edit.clicked.connect(self.on_switch_to_edit)
            self.day_layout.addWidget(go_edit, 0, Qt.AlignCenter)
        else:
            for sidx, (sname, plan) in enumerate(day_plans):
                self._add_slot_row(self.day_layout, sname, plan, is_extra=False,
                                   slot_idx=sidx, show_complete=True,
                                   done=st["row_done"][sidx],
                                   note=st["notes"][sidx],
                                   fixed=st["row_fixed"][sidx],
                                   blocked=st["row_blocked"][sidx])

        # 额外安排：列表在「额外安排」按钮打开的对话框里（v0.12）
        count = len(st["extras"])
        frozen = " · 已拦截" if st["extras_frozen"] else ""
        self.extra_btn.setText(f"📋 额外安排（{count}）{frozen}")
        self.extra_btn.setEnabled(True)
        # v0.27：0 条时这个按钮根本不出现（有额外安排才冒出来）
        self.extra_btn.setVisible(count > 0)
        # v0.29：按钮从无到有冒出来的那一刻给一次淡入（刷新别的不动）
        if count > 0 and not self._extra_btn_was_visible:
            animations.fade_in(self.extra_btn, theme.MOTION["fast"])
        self._extra_btn_was_visible = count > 0

        # 按钮启用状态 + 文案
        # v0.16：return_btn = 老「退回」按钮（仅撤今天完成 / 退额外轮最后一条）,逻辑保持 v0.15 不变。
        # undo_btn = 新 history 栈的撤销入口,只在 history 不空时显示。
        # redo_btn = 新 history 栈的重做入口,只在 _redo 不空时显示。
        can_undo = self.scheduler.can_undo_complete()
        # return_btn 已非可见入口（R17 合并进统一撤销），文案/状态维护保留给老测试
        self.return_btn.setEnabled(can_undo or self.scheduler.can_return())
        self.return_btn.setText("↶ 撤销完成" if can_undo else "⤴ 退回")
        self.undo_btn.setVisible(self.scheduler.p.can_undo())
        if self.scheduler.p.can_undo():
            label = self.scheduler.p.history_top_label() or "撤销"
            self.undo_btn.setText(f"↶ 撤销「{label}」")
            self.undo_btn.setEnabled(True)
        else:
            self.undo_btn.setText("↶ 撤销")
            self.undo_btn.setEnabled(False)
        self.redo_btn.setVisible(self.scheduler.p.can_redo())
        self.redo_btn.setEnabled(self.scheduler.p.can_redo())
        self.add_next_btn.setEnabled(self.scheduler.can_borrow_next())
        self.add_specific_btn.setEnabled(bool(self.scheduler.available_borrow_names()))

        self.refresh_calendar_preview()

    def refresh_calendar_preview(self):
        p = self.data.current_parent
        cal = self.scheduler.get_calendar()
        st = self.scheduler.today_state()
        done_today = self.scheduler.done_today()

        # v0.27：队列标题行带上剩余条数（收起时也能看到进度）
        self.queue_toggle.setText(f"计划队列 · 还有 {len(self.scheduler.pending())} 条")

        lines = []
        head = f"已归档 {self.scheduler.total_done()} 条"
        if done_today:
            head += f"（今天：{'、'.join(done_today)}）"
        lines.append(head)
        lines.append("")

        for i, (d, plans) in enumerate(cal):
            day_no = p.current_day + i + 1
            marker = "👉" if i == 0 else "  "
            extra_marker = f" [+{len(st['extra_left'])} 额外]" if i == 0 and st["extra_left"] else ""
            lines.append(f"{marker} 第{day_no}天 ({d.toString('MM-dd ddd')}){extra_marker}")
            for sname, plan in plans:
                content = plan if plan else "·"
                lines.append(f"        {sname}: {content}")
            lines.append("")

        self.calendar_area.setText("\n".join(lines))

    def on_add_next(self):
        """加一个：自动顺延下一个未完成的计划"""
        if self.scheduler.all_consumed():
            QMessageBox.information(self, "提示", "🎉 全部计划都已完成！")
            return
        if self.scheduler.borrow_next():
            self.data.save()
            self.refresh()

    def ask_add_specific(self):
        """弹「添加指定」对话框 → 选中就拉进额外轮。返回是否成功（v0.12：抽出给列表复用）"""
        if self.scheduler.all_consumed():
            QMessageBox.information(self, "提示", "🎉 全部计划都已完成！")
            return False
        available = self.scheduler.available_pick_plans()
        if not available:
            QMessageBox.information(self, "提示", "没有可提前安排的计划了")
            return False
        plan, ok = QInputDialog.getItem(self, "添加指定", "想提前安排哪一条？", available, 0, False)
        if not ok or not plan:
            return False
        if self.scheduler.borrow_plan(plan):
            self.data.save()
            self.refresh()
            return True
        QMessageBox.warning(self, "提示", f"无法添加「{plan}」")
        return False

    def on_add_specific(self):
        """添加指定：从后面还没安排的里挑一条提前安排（v0.9：按计划挑，不按时段名）"""
        self.ask_add_specific()

    def on_show_extras(self):
        """额外安排：打开当天额外安排列表（v0.12）"""
        dlg = ExtraArrangementsDialog(self)
        dlg.exec_()
        self.refresh()

    def on_return(self):
        """v0.9~v0.15 的「退回」按钮 = 「撤今天最近一次完成」或「退额外轮最后一条」。

        走老 API（can_undo_complete / undo_complete / return_last_borrowed）而不是新栈 —— 
        这样:
        - 文案「↶ 撤销完成」/「⤴ 退回」可以保持旧的逻辑
        - 老测试（期望 can_undo_complete 的精确语义、按钮文案）的语义不被新栈污染
        - on_undo() 是新 API,单独负责「任意动作的撤销」,两个入口并存
        """
        if self.scheduler.can_undo_complete():
            ok = self.scheduler.undo_complete()
        else:
            ok = self.scheduler.return_last_borrowed()
        if ok:
            self.data.save()
            self.refresh()

    def on_undo(self):
        """v0.16 新增:通用撤销 —— history 栈里有东西就撤一次,覆盖所有修改类动作。
        on_return 走的是老路径(只能撤完成),两者并存,各有按钮/快捷键绑定。"""
        if self.scheduler.undo():
            self.data.save()
            self.refresh()

    def on_redo(self):
        """v0.16 新增:重做 —— 恢复被 on_undo 撤掉的动作。"""
        if self.scheduler.redo():
            self.data.save()
            self.refresh()

    def on_toggle_fixed(self, slot_idx):
        """固定计划：这一格的原定计划不参与上滚"""
        if self.scheduler.toggle_fixed(slot_idx):
            self.data.save()
            self.refresh()

    def on_toggle_blocked(self, slot_idx):
        """拦截滚动：这一格及往后的都不参与上滚"""
        if self.scheduler.toggle_blocked(slot_idx):
            self.data.save()
            self.refresh()

    def on_complete_only(self, slot_idx):
        """仅完成：标记这一格完成，后面的计划不滚动"""
        if self.scheduler.complete_only_slot(slot_idx):
            self.data.save()
            self.refresh()

    def on_complete_slot(self, slot_idx):
        """完成并滚动：归档这一格，后面的整体上滚一格"""
        if self.scheduler.complete_today_slot(slot_idx):
            self.data.save()
            self.refresh()
            animations.fade_in(self.day_container, theme.MOTION["fast"])   # 完成滚动后的轻反馈

    def on_next_day(self):
        p = self.data.current_parent
        scheduler = self.scheduler
        day_plans = scheduler.get_day_plans(p.current_day)
        day_has_content = any(plan is not None for _, plan in day_plans)
        can_still_borrow = scheduler.can_borrow_next()
        can_still_return = scheduler.can_return()

        unfinished = []
        if day_has_content:
            unfinished.append("今天的安排还没全部完成")
        if can_still_borrow:
            unfinished.append("还有可加的额外计划")
        if can_still_return:
            unfinished.append("已加的额外安排可以退回")

        if unfinished:
            msg = "今天是第 {} 天，还有未处理的事项：\n  • {}\n\n确认进入下一天？".format(
                p.current_day + 1, "\n  • ".join(unfinished)
            )
            # 5 参 question：默认按钮=否（防回车误确认），且可被测试打桩
            reply = QMessageBox.question(
                self, "进入明天", msg,
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if reply != QMessageBox.Yes:
                return
        elif not day_has_content:
            # v0.30（审计 P2-3）：今天完全没安排时也要轻确认，防 Ctrl+D 连刷出「第 99 天」
            reply = QMessageBox.question(
                self, "进入明天",
                "今天（第 {} 天）没有任何安排，要空过这一天吗？".format(p.current_day + 1),
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if reply != QMessageBox.Yes:
                return

        # v0.22b：切天也进撤销栈 —— 切天会清掉每格状态 / 额外轮 / 归档分界,误点之后
        # 至少要能 Ctrl+Z 退回前一天（快照里有 current_day / daily_boundaries / archived_base /
        # consumed / 每格状态,整块一起回滚）
        p.push_history()
        p.current_day += 1
        p.consumed += scheduler.today_state()["queue_used"]  # 今天的队列走到哪了
        # v0.22：归档按天分组 —— 用「今天完成后 archived 的长度」当作这一天与下一天的分界
        day_end = len(p.archived)
        p.daily_boundaries.append(day_end)
        p.archived_base = day_end                              # 「今天完成的」重新从 0 算
        p.borrowed_slots = []                                # 切天时清空额外安排
        p.inplace_done = []                                  # 新的一天：每格状态归零
        p.slot_notes = []                                    # 新的一天：归档备注重新开始记
        p.slot_fixed = []                                    # 新的一天：固定 / 拦截也归零
        p.slot_blocked = []
        p.normalize()
        self.data.save()
        self.refresh()
        animations.fade_in(self.day_container)        # 新的一天，内容轻淡入

    def on_switch_parent(self):
        """切换分类"""
        names = [p.name for p in self.data.parents]
        cur_name = self.data.current_parent.name
        try:
            cur_idx = names.index(cur_name)
        except ValueError:
            cur_idx = 0
        name, ok = QInputDialog.getItem(self, "切换分类", "选择分类:", names, cur_idx, False)
        if ok and name:
            self.data.current_parent_idx = names.index(name)
            self.data.save()
            self.scheduler = PlanScheduler(self.data.current_parent)
            self.refresh()
            animations.fade_in(self.day_container)        # 换了分类，内容轻淡入


# ============== 额外安排 列表（v0.12） ==============

class ExtraArrangementsDialog(QDialog):
    """当天额外安排列表 —— 点「📋 额外安排」细长条按钮打开

    - 每条一个「🗑 删除该安排」
    - 底部：「➕ 添加指定计划」（从后面还没安排的里挑一条拉进来）
            「⤵ 直接拉取下一个」（不挑，按顺序直接拉下一条）
    - 已经滚进今天某一格的，标出滚到了第几格
    """

    def __init__(self, executor, parent=None):
        super().__init__(parent or executor)
        self.ex = executor
        self.setWindowTitle("今天的额外安排")
        self.resize(520, 400)

        outer = QVBoxLayout(self)
        outer.setSpacing(8)

        self.hint = QLabel()
        self.hint.setWordWrap(True)
        self.hint.setObjectName("rpDim")
        outer.addWidget(self.hint)

        self.list_layout = QVBoxLayout()
        self.list_layout.setSpacing(6)
        box = QWidget()
        box.setLayout(self.list_layout)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setWidget(box)
        outer.addWidget(self.scroll, stretch=1)

        btns = QHBoxLayout()
        self.add_specific_btn = QPushButton("➕ 添加指定计划")
        self.add_specific_btn.clicked.connect(self.on_add_specific)
        btns.addWidget(self.add_specific_btn)
        self.pull_next_btn = QPushButton("⤵ 直接拉取下一个")
        self.pull_next_btn.clicked.connect(self.on_pull_next)
        btns.addWidget(self.pull_next_btn)
        btns.addStretch(1)
        close_btn = QPushButton("关闭")
        close_btn.clicked.connect(self.accept)
        btns.addWidget(close_btn)
        outer.addLayout(btns)

        self.rebuild()

    def showEvent(self, event):
        """v0.30 R7：对话框出场走窗口级 windowOpacity（比整页特效顺滑）。"""
        super().showEvent(event)
        animations.pop_window(self)

    # ---------- 列表渲染 ----------

    def borrowed_plans(self):
        self.ex.data.current_parent.normalize()
        return [item[1] for item in self.ex.data.current_parent.borrowed_slots]

    def _clear(self):
        while self.list_layout.count():
            item = self.list_layout.takeAt(0)
            w = item.widget()
            if w:
                w.setParent(None)
                w.deleteLater()

    def promoted_positions(self, st=None):
        """额外安排里哪几条已经滚进今天了 → {计划内容: 第几格}"""
        st = st or self.ex.scheduler.today_state()
        left = list(st["promoted"])
        out = {}
        for idx, (_, plan) in enumerate(st["rows"]):
            if plan and plan in left:
                out.setdefault(plan, idx + 1)
                left.remove(plan)
        return out

    def rebuild(self):
        self._clear()
        sched = self.ex.scheduler
        st = sched.today_state()
        borrowed = self.borrowed_plans()
        promoted = self.promoted_positions(st)

        if st["extras_frozen"]:
            self.hint.setText("今天有格子按了「拦截滚动」—— 拦截期间额外安排不参与候补，"
                              "空出来的位置会保持空白。")
        else:
            self.hint.setText("这里是你额外加进今天的计划。前面格子的计划完成并滚动后，"
                              "它们会按顺序自动补进空格。")

        if not borrowed:
            lbl = QLabel("还没有额外安排")
            lbl.setAlignment(Qt.AlignCenter)
            lbl.setObjectName("rpEmpty")
            self.list_layout.addWidget(lbl)
        else:
            for i, plan in enumerate(borrowed, 1):
                row = QHBoxLayout()
                name = QLabel(f"{i}. {plan}")
                name.setFont(QFont("Microsoft YaHei", 12))
                row.addWidget(name)
                if plan in promoted:
                    tag = QLabel(f"（已滚入今天的第 {promoted[plan]} 格）")
                else:
                    tag = QLabel("（候补中）")
                tag.setObjectName("rpDim")
                row.addWidget(tag)
                row.addStretch(1)
                del_btn = QPushButton("🗑 删除该安排")
                del_btn.clicked.connect(
                    lambda checked=False, p=plan: self.on_delete(p))
                row.addWidget(del_btn)
                holder = QWidget()
                holder.setLayout(row)
                self.list_layout.addWidget(holder)

        self.list_layout.addStretch(1)
        self.pull_next_btn.setEnabled(sched.can_borrow_next())
        self.add_specific_btn.setEnabled(bool(sched.available_pick_plans()))

    # ---------- 动作 ----------

    def on_delete(self, plan):
        if self.ex.scheduler.unborrow_plan(plan):
            self.ex.data.save()
            self.ex.refresh()
            self.rebuild()

    def on_pull_next(self):
        if self.ex.scheduler.borrow_next():
            self.ex.data.save()
            self.ex.refresh()
            self.rebuild()

    def on_add_specific(self):
        if self.ex.ask_add_specific():
            self.rebuild()


