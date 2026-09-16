"""
RollingPlan 归档总览（v0.18 新增）

第三页「📊 归档总览」：看每个分类的进度 + 归档历史 + 今天完成的列表。

依赖（rollingplan.py 里）:
- PlanData, PlanScheduler
"""
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QListWidget, QListWidgetItem,
    QComboBox, QGroupBox,
)

from scheduler import PlanScheduler


class PlanCalendarView(QWidget):
    """归档总览页：每个分类的进度 + 归档历史 + 今天完成的。

    数据通过 scheduler 的已有 API 拿：
    - get_progress() → (已推进, 总)
    - total_done() → 累计完成条数
    - done_today() → 今天完成的
    - archived (按完成顺序的 list)
    - slot_notes (每格的归档备注)
    """

    def __init__(self, data, on_data_reloaded=None):
        super().__init__()
        self.data = data
        self.on_data_reloaded = on_data_reloaded
        self.scheduler = None        # 跟当前选中的分类绑定
        self._init_ui()
        self.refresh()

    def _init_ui(self):
        layout = QVBoxLayout()
        layout.setSpacing(12)
        layout.setContentsMargins(20, 16, 20, 16)

        # ============ 顶部：分类切换 + 标题 ============
        top_row = QHBoxLayout()
        title = QLabel("📊 归档总览")
        title.setFont(QFont("Microsoft YaHei", 16, QFont.Bold))
        top_row.addWidget(title)

        top_row.addStretch()

        top_row.addWidget(QLabel("分类:"))
        self.parent_combo = QComboBox()
        self.parent_combo.setMinimumWidth(140)
        self.parent_combo.currentIndexChanged.connect(self._on_parent_changed)
        top_row.addWidget(self.parent_combo)
        layout.addLayout(top_row)

        # ============ 主区：进度 + 归档历史 + 今天完成 ============
        # 进度
        progress_group = QGroupBox("📈 进度")
        progress_inner = QVBoxLayout()
        self.progress_label = QLabel()
        self.progress_label.setFont(QFont("Microsoft YaHei", 14, QFont.Bold))
        self.progress_label.setAlignment(Qt.AlignCenter)
        progress_inner.addWidget(self.progress_label)
        progress_group.setLayout(progress_inner)
        layout.addWidget(progress_group)

        # 归档历史（所有已完成归档，按完成顺序；最近的在最上面）
        archive_group = QGroupBox("🗂 归档历史（按完成顺序，最近在上）")
        archive_inner = QVBoxLayout()
        self.archive_list = QListWidget()
        self.archive_list.setFont(QFont("Microsoft YaHei", 12))
        archive_inner.addWidget(self.archive_list)
        archive_group.setLayout(archive_inner)
        layout.addWidget(archive_group, stretch=1)

        # 今天完成（在归档历史里也能看到，但单独高亮一份更直观）
        today_group = QGroupBox("✅ 今天完成")
        today_inner = QVBoxLayout()
        self.today_label = QLabel()
        self.today_label.setFont(QFont("Microsoft YaHei", 13))
        self.today_label.setWordWrap(True)
        today_inner.addWidget(self.today_label)
        today_group.setLayout(today_inner)
        layout.addWidget(today_group)

        self.setLayout(layout)

    def _on_parent_changed(self, idx):
        """分类切换:重新拿 scheduler,刷新一遍"""
        if idx < 0 or idx >= len(self.data.parents):
            return
        self.scheduler = PlanScheduler(self.data.parents[idx])
        self._refresh_view()

    def refresh(self):
        """外部调用（导入数据后、分类切换后）刷新整页。"""
        # 先按当前 data.parents 重建下拉
        cur_idx = self.parent_combo.currentIndex()
        self.parent_combo.blockSignals(True)
        self.parent_combo.clear()
        for p in self.data.parents:
            self.parent_combo.addItem(p.name)
        # 尽量保持原选项
        if 0 <= cur_idx < self.parent_combo.count():
            self.parent_combo.setCurrentIndex(cur_idx)
        elif self.parent_combo.count() > 0:
            self.parent_combo.setCurrentIndex(self.data.current_parent_idx)
        self.parent_combo.blockSignals(False)

        idx = self.parent_combo.currentIndex()
        if 0 <= idx < len(self.data.parents):
            self.scheduler = PlanScheduler(self.data.parents[idx])
        else:
            self.scheduler = None
        self._refresh_view()

    def _refresh_view(self):
        """拉一遍 scheduler 数据填进控件。"""
        if self.scheduler is None:
            self.progress_label.setText("(无分类)")
            self.archive_list.clear()
            self.today_label.setText("(无分类)")
            return
        p = self.scheduler.p
        done, total = self.scheduler.get_progress()
        self.progress_label.setText(f"已推进 {done} / 共 {total} 条（{pct(done, total)}）")

        # 归档历史：archived 是按完成顺序的 list，最近 push 的在末尾
        # 列表显示时倒过来 —— 最近的在最上面
        self.archive_list.clear()
        archived = list(p.archived)
        if not archived:
            placeholder = QListWidgetItem("（暂无归档）")
            placeholder.setFlags(Qt.NoItemFlags)   # 不可选
            self.archive_list.addItem(placeholder)
        else:
            n = len(archived)
            for i, plan in enumerate(reversed(archived)):
                order = n - i   # 序号
                item = QListWidgetItem(f"{order:>3}.  {plan}")
                # 标出"今天完成"的那几条
                if i < len(self.scheduler.done_today()):
                    item.setForeground(Qt.darkGreen)
                self.archive_list.addItem(item)

        # 今天完成
        done_today = self.scheduler.done_today()
        if done_today:
            self.today_label.setText("、".join(done_today))
        else:
            self.today_label.setText("（今天还没完成任何计划）")

        # 每格的归档备注汇总（额外信息：哪一格 / 哪个时段完成了什么）
        notes = getattr(p, "slot_notes", None) or []
        if any(n for n in notes):
            self.today_label.setText(
                self.today_label.text() + "\n\n📋 当天各时段归档备注：" +
                "\n".join(
                    f"  时段 {i+1}: " + "、".join(n) if n else ""
                    for i, n in enumerate(notes)
                )
            )


def pct(done, total):
    if total <= 0:
        return "0%"
    return f"{int(done * 100 / total)}%"
