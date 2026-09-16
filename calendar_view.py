"""
RollingPlan 归档总览（v0.18 新增,v0.22 加按天分组）

第三页「📊 归档总览」：看每个分类的进度 + 归档历史 + 今天完成的列表。

v0.22 新增按天分组：archived 是按完成顺序的 list,daily_boundaries 是每个分界点
「之前的所有 archived 属于第 N 天」。calendar_view 用这个把 archive_list 切成
「📅 第 1 天（3 条） / 📅 第 2 天（5 条） / 📅 第 3 天（进行中，2 条）」三段。

依赖(rollingplan.py 里):
- PlanData, ParentPlan(用 daily_boundaries 字段)
- PlanScheduler
"""
from PyQt5.QtCore import Qt, QDateTime
from PyQt5.QtGui import QFont, QBrush, QPalette
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QListWidget, QListWidgetItem,
    QComboBox, QGroupBox, QPushButton, QFileDialog, QMessageBox,
)

from scheduler import PlanScheduler


def build_archive_text(p, scheduler, now_str=None):
    """v0.22b：把当前分类的归档历史写成 UTF-8 文本（纯函数，方便测）。

    结构：
        标题 / 分类 / 导出时间 / 进度
        📅 第 1 天（3 条）  ← 时间顺序（最近的一天在最后）
        ...
        ✅ 今天完成：…
        📋 各时段归档备注：…
    """
    now_str = now_str or QDateTime.currentDateTime().toString("yyyy-MM-dd HH:mm")
    done, total = scheduler.get_progress() if scheduler is not None else (0, 0)
    lines = [
        "RollingPlan 归档导出",
        f"分类：{p.name}",
        f"导出时间：{now_str}",
        f"进度：已推进 {done} / 共 {total} 条（{pct(done, total)}）",
        "",
    ]

    archived = list(p.archived)
    if not archived:
        lines.append("（暂无归档）")
    else:
        bounds = list(getattr(p, "daily_boundaries", []) or [])
        current_day = p.current_day if isinstance(p.current_day, int) else 0
        start = 0
        for day_i, b in enumerate(bounds, 1):
            plans = archived[start:b]
            lines.append(f"📅 第 {day_i} 天（{len(plans)} 条）")
            lines.extend(f"  {i}. {plan}" for i, plan in enumerate(plans, 1))
            start = b
        rest = archived[start:]
        if len(bounds) < current_day:
            head = f"📅 第 {len(bounds) + 1}–{current_day + 1} 天"
        else:
            head = f"📅 第 {current_day + 1} 天"
        head += f"（进行中，{len(rest)} 条）" if rest else "（无归档）"
        lines.append(head)
        lines.extend(f"  {i}. {plan}" for i, plan in enumerate(rest, 1))

    lines.append("")
    lines.append(f"估算：{estimate_text(p)}")
    done_today = scheduler.done_today() if scheduler is not None else []
    lines.append("✅ 今天完成：" + ("、".join(done_today) if done_today else "（无）"))

    notes = getattr(p, "slot_notes", None) or []
    if any(notes):
        lines.append("📋 各时段归档备注：")
        for i, n in enumerate(notes):
            if n:
                lines.append(f"  时段 {i + 1}: " + "、".join(n))
    return "\n".join(lines) + "\n"


def export_archive_text(path, p, scheduler, now_str=None):
    """写成文件（UTF-8，带 BOM 让 Windows 记事本也认）。返回传进来的 path。"""
    text = build_archive_text(p, scheduler, now_str=now_str)
    with open(path, "w", encoding="utf-8-sig", newline="\n") as f:
        f.write(text)
    return path


def estimate_days_left(p):
    """v0.23：按「每天 N 格」估算还要几天（纯函数，方便测）。

    返回 (remaining, slots_per_day, days_left)：
    - remaining = 还没完成的计划条数（总条数 - 已归档条数，负数收敛成 0）
    - slots_per_day = 每天的格子数（早/中/晚各 1 就是 3）；0 表示没配时段
    - days_left = 剩余条数 ÷ 每天格数 向上取整；条数为 0 → 0；没有格 → None（算不出来）
    """
    total = len(getattr(p, "plans", []) or [])
    done = len(getattr(p, "archived", []) or [])
    remaining = max(0, total - done)
    spd = sum(s.get("count", 1) for s in (getattr(p, "time_slots", []) or []))
    if remaining == 0:
        return remaining, spd, 0
    if spd <= 0:
        return remaining, spd, None
    return remaining, spd, (remaining + spd - 1) // spd


def estimate_text(p):
    """把 estimate_days_left 的结果说成人话（给第三页进度区用）。"""
    remaining, spd, days_left = estimate_days_left(p)
    if remaining == 0:
        return "计划已全部完成 ✓"
    if days_left is None:
        return f"还剩 {remaining} 条（还没设时段，算不出天数）"
    return f"还剩 {remaining} 条 ≈ 还要 {days_left} 天（每天 {spd} 格）"


class PlanCalendarView(QWidget):
    """归档总览页：每个分类的进度 + 归档历史(按天分组) + 今天完成的。

    数据通过 scheduler 的已有 API 拿：
    - get_progress() → (已推进, 总)
    - total_done() → 累计完成条数
    - done_today() → 今天完成的
    - archived (按完成顺序的 list)
    - daily_boundaries (ParentPlan 字段,v0.22 新增)
    - slot_notes (每格的归档备注)
    """

    def __init__(self, data, on_data_reloaded=None):
        super().__init__()
        self.data = data
        self.on_data_reloaded = on_data_reloaded
        self.scheduler = None        # 跟当前选中的分类绑定
        # v0.23：归档历史按天折叠的状态（只活在本次会话里，不写盘）
        self._day_open = {}          # 用户单独点开/收起的那些天：day_key -> bool
        self._expand_all = None      # 「全部展开/收起」按钮：True/False/None(没按过)
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

        # v0.22b：把当前分类的归档历史导出成文本文件（留档 / 回顾用）
        self.export_btn = QPushButton("⬇ 导出归档")
        self.export_btn.setToolTip("把当前分类的归档历史写成 .txt（按天分组 + 今天完成 + 各时段备注）")
        self.export_btn.clicked.connect(self._on_export)
        top_row.addWidget(self.export_btn)

        # v0.23：归档历史整体展开 / 收起（默认只展开最近一天）
        self.expand_all_btn = QPushButton("▾ 全部展开")
        self.expand_all_btn.setToolTip("展开或收起所有天的归档条目")
        self.expand_all_btn.clicked.connect(self._on_toggle_all)
        top_row.addWidget(self.expand_all_btn)
        layout.addLayout(top_row)

        # ============ 主区：进度 + 归档历史 + 今天完成 ============
        # 进度
        progress_group = QGroupBox("📈 进度")
        progress_inner = QVBoxLayout()
        self.progress_label = QLabel()
        self.progress_label.setFont(QFont("Microsoft YaHei", 14, QFont.Bold))
        self.progress_label.setAlignment(Qt.AlignCenter)
        progress_inner.addWidget(self.progress_label)
        # v0.23：按「每天 N 格」估算还要几天
        self.estimate_label = QLabel()
        self.estimate_label.setFont(QFont("Microsoft YaHei", 11))
        self.estimate_label.setAlignment(Qt.AlignCenter)
        self.estimate_label.setWordWrap(True)
        progress_inner.addWidget(self.estimate_label)
        progress_group.setLayout(progress_inner)
        layout.addWidget(progress_group)

        # 归档历史（按天分组）
        archive_group = QGroupBox("🗂 归档历史（按天分组，最近完成的在上）")
        archive_inner = QVBoxLayout()
        self.archive_list = QListWidget()
        self.archive_list.setFont(QFont("Microsoft YaHei", 12))
        self.archive_list.itemClicked.connect(self._on_archive_clicked)
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

    def _on_export(self):
        """v0.22b：导出当前分类的归档历史为文本文件。"""
        if self.scheduler is None:
            QMessageBox.information(self, "导出归档", "还没有可导出的分类。")
            return
        p = self.scheduler.p
        default_name = "{} 归档-{}.txt".format(
            p.name, QDateTime.currentDateTime().toString("yyyy-MM-dd")
        )
        path, _ = QFileDialog.getSaveFileName(
            self, "导出归档", default_name, "文本文件 (*.txt)"
        )
        if not path:
            return
        try:
            export_archive_text(path, p, self.scheduler)
        except OSError as exc:
            QMessageBox.warning(self, "导出失败", f"写文件失败：\n{exc}")
            return
        QMessageBox.information(self, "导出归档", f"已导出到：\n{path}")

    def _day_sections(self, p):
        """v0.22：把 archived 按天切成多段（时间顺序：第 1 天 → 当前天）。

        返回 [{"label": str, "start": int, "plans": [plan, ...], "current": bool}, ...]
        - 前 N 段 = 已经切过去的天（daily_boundaries 决定每段有多长）
        - 最后一段 = 当前天（rest = 最后一次切天之后归档的）
        "start" 是该段第一条在 p.archived 里的下标（用来判断「是不是今天完成的」）。
        """
        archived = list(p.archived)
        bounds = list(getattr(p, "daily_boundaries", []) or [])
        current_day = p.current_day if isinstance(p.current_day, int) else 0

        sections = []
        start = 0
        for day_i, b in enumerate(bounds, 1):
            plans = archived[start:b]
            sections.append({
                "label": f"📅 第 {day_i} 天（{len(plans)} 条）",
                "start": start,
                "plans": plans,
                "current": False,
            })
            start = b

        # 剩下的属于当前天。老存档（v0.21 之前没有 daily_boundaries）里这段可能横跨好几天 → 标成区间
        rest = archived[start:]
        if len(bounds) < current_day:
            label = f"📅 第 {len(bounds) + 1}–{current_day + 1} 天"
        else:
            label = f"📅 第 {current_day + 1} 天"
        label += f"（进行中，{len(rest)} 条）" if rest else "（无归档）"
        sections.append({
            "label": label,
            "start": start,
            "plans": rest,
            "current": True,
        })
        return sections

    def _archive_rows(self, p):
        """归档历史列表的行（显示顺序：最近的天在上、每天内部最近完成的在上）。

        返回 [{"kind","text","idx","day_key","open"}, ...]：
        - kind = "header"（每天一行分隔标题，可点开/收起）或 "plan"
        - idx = 该条目在 p.archived 里的下标（header 是 None）
        - day_key = 这一天的标识（收起状态按它记）
        - open = 这一天当前展开与否；收起时该天的条目行**不产出**（列表直接变短）
        """
        rows = []
        first_shown = True
        for sec in reversed(self._day_sections(p)):
            plans = sec["plans"]
            if not plans:
                continue
            key = sec["label"]
            is_open = self._section_open(key, first_shown)
            first_shown = False          # 默认只展开最上面（最近）那一天
            rows.append({
                "kind": "header",
                "text": ("▾ " if is_open else "▸ ") + key,
                "idx": None,
                "day_key": key,
                "open": is_open,
            })
            if not is_open:
                continue
            for off in range(len(plans) - 1, -1, -1):
                rows.append({
                    "kind": "plan",
                    "text": plans[off],
                    "idx": sec["start"] + off,
                    "day_key": key,
                    "open": True,
                })
        return rows

    def _section_open(self, key, first_shown=False):
        """v0.23：这一天展开还是收起。

        优先级：用户单独点过的 > 「全部展开/收起」按钮 > 默认（只展开最上面一天）。
        """
        if key in self._day_open:
            return self._day_open[key]
        if self._expand_all is not None:
            return self._expand_all
        return bool(first_shown)

    def _on_archive_clicked(self, item):
        """点「📅 第 N 天」那行 → 收起 / 展开那一天。"""
        if item.data(Qt.UserRole) != "day_header":
            return
        key = item.data(Qt.UserRole + 2)
        was_open = bool(item.data(Qt.UserRole + 3))
        self._day_open[key] = not was_open
        self._refresh_view()

    def _on_toggle_all(self):
        """「全部展开」↔「全部收起」（清掉单独点过的状态）。"""
        want_open = not (self._expand_all is True)
        self._expand_all = want_open
        self._day_open = {}
        self.expand_all_btn.setText("▸ 全部收起" if want_open else "▾ 全部展开")
        self._refresh_view()

    def _refresh_view(self):
        """拉一遍 scheduler 数据填进控件。"""
        if self.scheduler is None:
            self.progress_label.setText("（无分类）")
            self.estimate_label.setText("")
            self.archive_list.clear()
            self.today_label.setText("（无分类）")
            return
        p = self.scheduler.p
        done, total = self.scheduler.get_progress()
        self.progress_label.setText(f"已推进 {done} / 共 {total} 条（{pct(done, total)}）")
        self.estimate_label.setText(estimate_text(p))

        # 归档历史：按天分组 + 倒序（最近的天在最上面）
        self.archive_list.clear()
        if not p.archived:
            placeholder = QListWidgetItem("（暂无归档）")
            placeholder.setData(Qt.UserRole, "placeholder")
            placeholder.setFlags(Qt.NoItemFlags)
            self.archive_list.addItem(placeholder)
        else:
            base = getattr(p, "archived_base", 0) or 0
            header_color = self.palette().color(QPalette.WindowText)
            header_color.setAlpha(150)          # 跟着浅色 / 深色主题走，不用写死的灰
            for row in self._archive_rows(p):
                if row["kind"] == "header":
                    item = QListWidgetItem(row["text"])
                    item.setFont(QFont("Microsoft YaHei", 12, QFont.Bold))
                    item.setForeground(QBrush(header_color))
                    item.setFlags(Qt.ItemIsEnabled)      # v0.23：可点（收起/展开），但不可选
                    item.setData(Qt.UserRole, "day_header")
                    item.setData(Qt.UserRole + 2, row["day_key"])
                    item.setData(Qt.UserRole + 3, row["open"])
                else:
                    item = QListWidgetItem(f"      {row['text']}")
                    item.setData(Qt.UserRole, "plan")
                    item.setData(Qt.UserRole + 1, row["idx"])
                    if row["idx"] is not None and row["idx"] >= base:
                        # 今天完成的（archived[base:]）用深绿标
                        item.setForeground(Qt.darkGreen)
                self.archive_list.addItem(item)

        # 今天完成
        done_today = self.scheduler.done_today()
        if done_today:
            self.today_label.setText("、".join(done_today))
        else:
            self.today_label.setText("（今天还没完成任何计划）")

        # 每格的归档备注汇总
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
