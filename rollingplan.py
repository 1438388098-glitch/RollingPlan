"""
RollingPlan v0.3 — 日常计划管理（面向普通用户）

数据结构：
- 多个分类（工作/学习/健身...），每个分类独立：计划清单 / 时段 / 起始日期 / 当前天数 / 额外安排
- 切换分类：写入界面 + 执行界面都切换
- 「加一个」：自动顺延下一个未完成的计划
- 「添加指定」：弹对话框选时段名
- 额外安排按加入顺序显示
"""

import sys
import os
import json
import logging
from logging.handlers import RotatingFileHandler
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QListWidget,
    QSpinBox, QDateEdit, QTextEdit, QMessageBox, QTabWidget,
    QGroupBox, QInputDialog, QFileDialog, QComboBox, QToolButton,
    QSizePolicy, QDialog, QScrollArea,
)
from PyQt5.QtCore import Qt, QDate, QSettings
from PyQt5.QtGui import QFont

# 主题:QSS 字符串 + apply_theme 抽到独立模块(v0.14 重构,行为完全等价)
from theme import THEME_KEY, THEME_OPTIONS, apply_theme
from theme import DARK_QSS, LIGHT_QSS  # 向后兼容:test_theme_v05.py 直接 import 这两个常量


# ============== 数据模型 ==============

# v0.15：PlanScheduler 与 _pending_of helper 抽到 scheduler.py；
# 这里 re-export 一份以保持旧测试（test_v2_2 / test_scroll_v11 / test_reset_v04
# / test_import_export_v04 / test_regression_v13）从 rollingplan 直接 import 的写法继续工作
from scheduler import PlanScheduler, _pending_of  # noqa: F401


class ParentPlan:
    """单个母计划"""

    def __init__(self, name="新分类"):
        self.name = name
        self.plans = []
        self.time_slots = []
        self.start_date = QDate.currentDate()
        self.current_day = 0
        self.borrowed_slots = []   # 额外轮：[[slot_name, plan, day, slot_idx], ...] 按加进来的顺序
        # ---- v0.9 滚动状态 ----
        self.archived = []         # 已完成（归档）的计划内容（累计；从队列里移除）
        self.archived_base = 0     # 进入当前天时 len(archived) 的快照 →「今天完成的」= archived[base:]
        self.consumed = 0          # 当前天在队列（plans - archived）里的起点下标
        # ---- v0.10 每格各自的完成状态 ----
        self.inplace_done = []     # 「仅完成」钉住的格：长度 = 当天格数，每项是计划内容或 None
        self.slot_notes = []       # 每个时段栏的归档备注：[[内容, ...], ...] 长度 = 当天格数
        # ---- v0.11 「固定计划」/「拦截滚动」 ----
        self.slot_fixed = []       # 固定住的格：这一格的原定计划不参与上滚
        self.slot_blocked = []     # 拦截滚动的格：这一格及往后都不参与上滚
        # ---- v0.16 撤销栈（运行时不写盘：to_dict 不包含；切天/重启自动清空） ----
        # 快照 = _snapshot_dict() 返回的 dict;只覆盖可变的状态字段,plans/time_slots/name 不在栈里
        # (改计划/换名/换时段属于编辑器的活,不在执行页撤销栈范围)
        self._history = []         # 栈顶 = 最近一次;栈上限 50,新的操作清空 _redo
        self._redo = []

    def _slots_per_day(self):
        return sum(s.get("count", 1) for s in self.time_slots)

    def to_dict(self):
        return {
            "name": self.name,
            "plans": self.plans,
            "time_slots": self.time_slots,
            "start_date": self.start_date.toString("yyyy-MM-dd"),
            "current_day": self.current_day,
            "borrowed_slots": self.borrowed_slots,
            "archived": self.archived,
            "archived_base": self.archived_base,
            "consumed": self.consumed,
            "inplace_done": self.inplace_done,
            "slot_notes": self.slot_notes,
            "slot_fixed": self.slot_fixed,
            "slot_blocked": self.slot_blocked,
        }

    def from_dict(self, d):
        self.name = d.get("name", "新分类")
        self.plans = d.get("plans", [])
        self.time_slots = d.get("time_slots", [])
        sd = d.get("start_date")
        if sd:
            self.start_date = QDate.fromString(sd, "yyyy-MM-dd")
        self.current_day = d.get("current_day", 0)
        self.borrowed_slots = d.get("borrowed_slots", [])
        self.archived = [a for a in (d.get("archived") or []) if isinstance(a, str)]
        self.archived_base = d.get("archived_base", 0) or 0
        self.consumed = d.get("consumed", 0) or 0
        # v0.10：每格各自的完成状态（旧存档没有 → 空）
        self.inplace_done = list(d.get("inplace_done") or [])
        self.slot_notes = [list(n) for n in (d.get("slot_notes") or [])]
        # v0.11：固定计划 / 拦截滚动（旧存档没有 → 空）
        self.slot_fixed = list(d.get("slot_fixed") or [])
        self.slot_blocked = list(d.get("slot_blocked") or [])
        # v0.8 旧存档迁移：completed_today 里存的是「当前天的 slot 序号」，转成计划内容
        legacy = d.get("completed_today")
        if isinstance(legacy, list) and legacy and all(isinstance(x, int) for x in legacy):
            spd = sum(s.get("count", 1) for s in self.time_slots) or 1
            for slot_idx in sorted(set(legacy)):
                idx = self.current_day * spd + slot_idx
                if 0 <= idx < len(self.plans):
                    self.archived.append(self.plans[idx])
        self.normalize()

    def normalize(self):
        """把状态收敛到合法范围（幂等）。读档 / 改计划之后都调一次。"""
        if not isinstance(self.archived, list):
            self.archived = []
        self.archived = [a for a in self.archived if isinstance(a, str)]
        if not isinstance(self.borrowed_slots, list):
            self.borrowed_slots = []
        try:
            self.archived_base = int(self.archived_base or 0)
        except (TypeError, ValueError):
            self.archived_base = 0
        self.archived_base = min(max(self.archived_base, 0), len(self.archived))
        try:
            self.consumed = int(self.consumed or 0)
        except (TypeError, ValueError):
            self.consumed = 0
        self.consumed = min(max(self.consumed, 0), len(_pending_of(self)))
        # v0.10：每格状态对齐到当天的格数（改过时段数量也能收敛）
        spd = max(0, self._slots_per_day())

        def _pad_str_list(vals):
            vals = list(vals) if isinstance(vals, list) else []
            vals = [x if isinstance(x, str) else None for x in vals]
            return (vals + [None] * spd)[:spd]

        self.inplace_done = _pad_str_list(self.inplace_done)
        self.slot_fixed = _pad_str_list(self.slot_fixed)          # v0.11
        self.slot_blocked = _pad_str_list(self.slot_blocked)      # v0.11
        notes = self.slot_notes if isinstance(self.slot_notes, list) else []
        notes = [[x for x in (n or []) if isinstance(x, str)] if isinstance(n, list) else [] for n in notes]
        notes = (notes + [[] for _ in range(spd)])[:spd]
        self.slot_notes = notes

    def reset_progress(self):
        """v0.4：重置进度。plans/time_slots/start_date 不变。"""
        self.current_day = 0
        self.borrowed_slots = []
        self.archived = []
        self.archived_base = 0
        self.consumed = 0
        self.inplace_done = []
        self.slot_notes = []
        self.slot_fixed = []
        self.slot_blocked = []
        # 重置 = 一次大动作，把栈也清掉（不让用户「撤销整个重置」）
        self._history = []
        self._redo = []

    # ---------------- v0.16 撤销栈 ----------------

    _SNAPSHOT_KEYS = (
        "current_day", "borrowed_slots", "archived", "archived_base",
        "consumed", "inplace_done", "slot_notes", "slot_fixed", "slot_blocked",
    )
    _SNAPSHOT_INT_KEYS = ("current_day", "archived_base", "consumed")
    _HISTORY_LIMIT = 50

    def _snapshot_dict(self):
        """抓一份当前所有可逆状态的浅拷贝快照。

        列表里的内容是 list/str/None 不可变或拷贝;整数字段直接存。
        返回的 dict 可以被 pickle 也可以 json。
        """
        snap = {}
        for k in self._SNAPSHOT_KEYS:
            v = getattr(self, k, [] if k not in self._SNAPSHOT_INT_KEYS else 0)
            if isinstance(v, list):
                if k == "slot_notes":
                    snap[k] = [list(n) for n in v]
                else:
                    snap[k] = list(v)
            else:
                snap[k] = v
        return snap

    def _restore_snapshot(self, snap):
        """把 _snapshot_dict() 返回的 dict 套回去。"""
        for k in self._SNAPSHOT_KEYS:
            v = snap.get(k)
            if k == "slot_notes" and isinstance(v, list):
                setattr(self, k, [list(n) for n in v])
            elif isinstance(v, list):
                setattr(self, k, list(v))
            else:
                setattr(self, k, v)
        self.normalize()

    def push_history(self):
        """执行页修改状态前调一次：把当前状态入 _history,并清空 _redo。

        上限 50 —— 更老的扔掉（UI 上不可能一次滚那么远）。
        """
        self._history.append(self._snapshot_dict())
        if len(self._history) > self._HISTORY_LIMIT:
            self._history = self._history[-self._HISTORY_LIMIT:]
        self._redo = []

    def can_undo(self):
        return bool(self._history)

    def can_redo(self):
        return bool(self._redo)

    def undo(self):
        """弹一次 _history 顶,套回去;把当前快照推到 _redo。"""
        if not self._history:
            return False
        cur = self._snapshot_dict()
        snap = self._history.pop()
        self._redo.append(cur)
        if len(self._redo) > self._HISTORY_LIMIT:
            self._redo = self._redo[-self._HISTORY_LIMIT:]
        self._restore_snapshot(snap)
        return True

    def redo(self):
        """弹一次 _redo 顶,套回去;把当前快照推到 _history。"""
        if not self._redo:
            return False
        cur = self._snapshot_dict()
        snap = self._redo.pop()
        self._history.append(cur)
        if len(self._history) > self._HISTORY_LIMIT:
            self._history = self._history[-self._HISTORY_LIMIT:]
        self._restore_snapshot(snap)
        return True

    def history_top_label(self):
        """给 UI 用的：栈顶是哪个动作的简短说明。

        简化版：对比当前快照与栈顶快照的差异，给一句人能看懂的提示。
        旧版 undo_complete() 现在已变成 history 的一部分,所以可以放心删。
        """
        if not self._history:
            return ""
        snap = self._history[-1]
        cur = self._snapshot_dict()
        # 简单判断：归档条数变了 = 完成;额外轮条数变了 = 加/退
        n_arc_now = len(cur["archived"])
        n_arc_then = len(snap["archived"])
        n_extra_now = len(cur["borrowed_slots"])
        n_extra_then = len(snap["borrowed_slots"])
        if n_arc_now > n_arc_then:
            # 当前归档比栈顶多 = 栈顶是「撤销完成」的逆 → 提示「完成」相关
            diff = n_arc_now - n_arc_then
            return f"完成 {diff} 条" if diff > 1 else "完成"
        if n_arc_now < n_arc_then:
            return "撤销完成"
        if n_extra_now > n_extra_then:
            return "添加额外轮"
        if n_extra_now < n_extra_then:
            return "退回额外轮"
        return "修改"


class PlanData:
    """全局数据"""

    def __init__(self):
        self.parents = [ParentPlan("分类1")]
        self.current_parent_idx = 0

    @property
    def current_parent(self):
        return self.parents[self.current_parent_idx]

    def add_parent(self, name=None):
        if name is None:
            name = f"分类{len(self.parents)+1}"
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
            self.parents = [ParentPlan("分类1")]
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

    # ====== v0.4 导入/导出 ======

    EXPORT_VERSION = "0.4"

    def export_to_dict(self):
        """导出格式：纯 to_dict() + 版本/时间戳"""
        from datetime import datetime
        return {
            "version": self.EXPORT_VERSION,
            "exported_at": datetime.now().isoformat(timespec="seconds"),
            "data": self.to_dict(),
        }

    def export_to_file(self, path):
        """写入 JSON 文件。返回 (success, message)"""
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(self.export_to_dict(), f, ensure_ascii=False, indent=2)
            return True, f"已导出到 {path}"
        except Exception as e:
            return False, f"导出失败: {e}"

    def import_from_file(self, path):
        """从 JSON 文件加载。先校验再覆盖。
        返回 (success, message, stats)：
          - success=True: message=成功说明, stats={"parents": N, "plans_total": M, "borrowed_total": K}
          - success=False: message=具体失败原因, stats=None
        """
        try:
            with open(path, "r", encoding="utf-8") as f:
                raw = json.load(f)
        except FileNotFoundError:
            return False, f"文件不存在: {path}", None
        except json.JSONDecodeError as e:
            return False, f"JSON 解析失败: {e}", None
        except Exception as e:
            return False, f"读取失败: {e}", None

        # 校验
        ok, err = self._validate_import_payload(raw)
        if not ok:
            return False, err, None

        # 取出 data 段；向后兼容无 wrapper 的旧格式
        data = raw.get("data", raw)

        try:
            self.from_dict(data)
        except Exception as e:
            return False, f"数据结构异常: {e}", None

        # 统计
        parents = len(self.parents)
        plans_total = sum(len(p.plans) for p in self.parents)
        borrowed_total = sum(len(p.borrowed_slots) for p in self.parents)
        stats = {
            "parents": parents,
            "plans_total": plans_total,
            "borrowed_total": borrowed_total,
        }
        return True, "导入成功", stats

    @staticmethod
    def _validate_import_payload(raw):
        """校验导入文件结构。返回 (ok, error_msg)"""
        if not isinstance(raw, dict):
            return False, "文件根必须是 JSON 对象"
        # version 字段（可选但若存在则校验）
        ver = raw.get("version")
        if ver is not None and ver != PlanData.EXPORT_VERSION:
            return False, f"版本不兼容: 文件={ver}, 当前={PlanData.EXPORT_VERSION}"
        data = raw.get("data", raw)
        if not isinstance(data, dict):
            return False, "data 段必须是 JSON 对象"
        parents = data.get("parents")
        if not isinstance(parents, list):
            return False, "parents 必须是数组"
        if len(parents) == 0:
            return False, "parents 不能为空（至少 1 个分类）"
        # 每个 parent 基础字段
        for i, p in enumerate(parents):
            if not isinstance(p, dict):
                return False, f"第 {i+1} 个分类不是对象"
            for field in ("name", "plans", "time_slots"):
                if field not in p:
                    return False, f"第 {i+1} 个分类缺字段 '{field}'"
            if not isinstance(p["name"], str):
                return False, f"第 {i+1} 个分类的 name 不是字符串"
            if not isinstance(p["plans"], list):
                return False, f"第 {i+1} 个分类的 plans 不是数组"
            if not isinstance(p["time_slots"], list):
                return False, f"第 {i+1} 个分类的 time_slots 不是数组"
            # plans 内每项必须是字符串
            for j, plan in enumerate(p["plans"]):
                if not isinstance(plan, str):
                    return False, f"第 {i+1} 个分类的第 {j+1} 条计划不是字符串"
            # time_slots 内每项必须是 {name, count} 对象
            for j, slot in enumerate(p["time_slots"]):
                if not isinstance(slot, dict) or "name" not in slot:
                    return False, f"第 {i+1} 个分类的第 {j+1} 个时段格式错误"
        return True, ""


# v0.17：PlanEditor 抽到 editor.py；这里 re-export 保持旧的导入路径继续工作
from editor import PlanEditor  # noqa: F401
from calendar_view import PlanCalendarView  # noqa: F401

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
        layout.setSpacing(12)
        layout.setContentsMargins(20, 16, 20, 16)

        # ============ 顶部：分类 + 主题 + 返回（次要行）============
        top_row = QHBoxLayout()
        self.parent_combo_label = QLabel()
        self.parent_combo_label.setFont(QFont("Microsoft YaHei", 11))
        top_row.addWidget(self.parent_combo_label)
        self.parent_switch_btn = QPushButton("切换")
        self.parent_switch_btn.clicked.connect(self.on_switch_parent)
        top_row.addWidget(self.parent_switch_btn)
        top_row.addStretch()

        # 主题下拉（执行页也方便切）
        from rollingplan import THEME_OPTIONS
        self.theme_combo = QComboBox()
        for key, label in THEME_OPTIONS:
            self.theme_combo.addItem(label, userData=key)
        _saved = QSettings("RollingPlan", "Data").value(THEME_KEY, "dark")
        if _saved not in ("dark", "light", "auto"):
            _saved = "dark"
        for i, (k, _) in enumerate(THEME_OPTIONS):
            if k == _saved:
                self.theme_combo.setCurrentIndex(i)
                break
        self.theme_combo.currentIndexChanged.connect(self.on_theme_changed)
        top_row.addWidget(QLabel("主题:"))
        top_row.addWidget(self.theme_combo)

        edit_btn = QPushButton("← 返回制定")
        edit_btn.clicked.connect(self.on_switch_to_edit)
        top_row.addWidget(edit_btn)
        layout.addLayout(top_row)

        # ============ 日期 + 进度（中等字号）============
        self.date_label = QLabel()
        self.date_label.setFont(QFont("Microsoft YaHei", 18, QFont.Bold))
        self.date_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.date_label)

        self.progress_label = QLabel()
        self.progress_label.setAlignment(Qt.AlignCenter)
        self.progress_label.setFont(QFont("Microsoft YaHei", 13))
        # 不设 inline color — QSS 接管（dark 下浅灰、light 下深色都能看见）
        layout.addWidget(self.progress_label)

        # v0.9: 今天已完成（归档）了的计划
        self.done_label = QLabel()
        self.done_label.setAlignment(Qt.AlignCenter)
        self.done_label.setFont(QFont("Microsoft YaHei", 11))
        layout.addWidget(self.done_label)

        # ============ 今天：冷调主区 ============
        # 时段少时居中显示，时段多时自然撑开
        self.day_layout = QVBoxLayout()
        self.day_layout.setSpacing(8)
        self.day_layout.setAlignment(Qt.AlignCenter)  # 内容垂直居中
        day_container = QWidget()
        day_container.setLayout(self.day_layout)
        layout.addWidget(day_container, stretch=1)

        # ============ 额外安排：细长条按钮（在两大按钮上方）============
        # 长度与「加一个 + 今天完成」的总长相当，但矮一些 —— 点开是当天额外安排列表
        self.extra_btn = QPushButton("📋 额外安排（0）")
        self.extra_btn.setFont(QFont("Microsoft YaHei", 11))
        self.extra_btn.setMinimumHeight(30)
        self.extra_btn.setMaximumHeight(34)
        self.extra_btn.setStyleSheet(
            "QPushButton { border: 1px solid #999; border-radius: 5px; padding: 4px; }"
            "QPushButton:hover { background-color: rgba(33,150,243,0.15); }"
        )
        self.extra_btn.setCursor(Qt.PointingHandCursor)
        self.extra_btn.clicked.connect(self.on_show_extras)
        layout.addWidget(self.extra_btn)

        # ============ 主操作大按钮（两个并列、加大高度）============
        action_row = QHBoxLayout()
        action_row.setSpacing(10)

        self.add_next_btn = QPushButton("➕ 加一个")
        self.add_next_btn.setFont(QFont("Microsoft YaHei", 14, QFont.Bold))
        self.add_next_btn.setStyleSheet("background-color: #2196F3; color: white; padding: 14px; border-radius: 6px;")
        self.add_next_btn.setMinimumHeight(50)
        self.add_next_btn.setToolTip("从还没安排的队列里顺延一条  (Ctrl+Enter)")
        self.add_next_btn.clicked.connect(self.on_add_next)
        action_row.addWidget(self.add_next_btn)

        self.done_btn = QPushButton("✓ 今天完成")
        self.done_btn.setFont(QFont("Microsoft YaHei", 14, QFont.Bold))
        self.done_btn.setStyleSheet("background-color: #4CAF50; color: white; padding: 14px; border-radius: 6px;")
        self.done_btn.setMinimumHeight(50)
        self.done_btn.setToolTip("确认今天的安排全部结束,进入下一天  (Ctrl+D)")
        self.done_btn.clicked.connect(self.on_next_day)
        action_row.addWidget(self.done_btn)

        layout.addLayout(action_row)

        # ============ 次要操作：折叠区（默认收起）============
        self.advanced_toggle = QToolButton()
        self.advanced_toggle.setText("更多")
        self.advanced_toggle.setCheckable(True)
        self.advanced_toggle.setChecked(False)
        self.advanced_toggle.setStyleSheet("QToolButton { border: none; }")
        self.advanced_toggle.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.advanced_toggle.setArrowType(Qt.DownArrow)
        self.advanced_toggle.clicked.connect(self._toggle_advanced)
        layout.addWidget(self.advanced_toggle)

        self.advanced_container = QWidget()
        adv_layout = QVBoxLayout(self.advanced_container)
        adv_layout.setContentsMargins(0, 4, 0, 0)
        adv_layout.setSpacing(8)

        # 次要按钮行（v0.16）：
        # - return_btn = 老「退回」按钮（仅撤今天完成 / 退额外轮最后一条；旧行为不变）
        # - undo_btn   = 新「撤销」按钮（撤任意最近动作，含加/退/固定/拦截；通用 history 栈）
        # - redo_btn   = 新「重做」按钮（can_redo 时才显示）
        # 老按钮仍在第一位,因为它是历史最久的入口 + 旧测试直接读 return_btn 文案。
        # 新按钮给它腾两个位（撤销 + 重做），都在「添加指定」之前。
        sub_row = QHBoxLayout()
        self.return_btn = QPushButton("⤴ 退回")
        self.return_btn.setToolTip("优先撤销今天最近一次「完成」,否则退额外轮最后一条")
        self.return_btn.clicked.connect(self.on_return)
        sub_row.addWidget(self.return_btn)
        # 新版 history 栈的撤销入口
        self.undo_btn = QPushButton("↶ 撤销")
        self.undo_btn.setToolTip("撤销任意最近动作（完成/退回/添加/固定/拦截）(Ctrl+Shift+Z)")
        self.undo_btn.clicked.connect(self.on_undo)
        self.undo_btn.setVisible(False)   # 默认收起 —— 只在真的有 history 时显示
        sub_row.addWidget(self.undo_btn)
        self.redo_btn = QPushButton("↷ 重做")
        self.redo_btn.setToolTip("重做刚被撤销的动作 (Ctrl+Shift+Z)")
        self.redo_btn.clicked.connect(self.on_redo)
        self.redo_btn.setVisible(False)
        sub_row.addWidget(self.redo_btn)
        self.add_specific_btn = QPushButton("⋯ 添加指定")
        self.add_specific_btn.setStyleSheet("color: #666;")
        self.add_specific_btn.clicked.connect(self.on_add_specific)
        sub_row.addWidget(self.add_specific_btn)
        sub_row.addStretch()
        adv_layout.addLayout(sub_row)

        # 额外安排：v0.12 起列表移到「额外安排」按钮打开的对话框里
        # （按钮在主操作大按钮上方，见 __init__）

        # 计划日历（折叠在 advanced 里）
        cal_group = QGroupBox("计划日历")
        cal_inner = QVBoxLayout()
        self.calendar_area = QTextEdit()
        self.calendar_area.setReadOnly(True)
        self.calendar_area.setMaximumHeight(140)
        cal_inner.addWidget(self.calendar_area)
        cal_group.setLayout(cal_inner)
        adv_layout.addWidget(cal_group)

        self.advanced_container.setVisible(False)
        layout.addWidget(self.advanced_container)

        self.setLayout(layout)

    def _toggle_advanced(self):
        """切换「更多」折叠区显示"""
        checked = self.advanced_toggle.isChecked()
        self.advanced_container.setVisible(checked)
        self.advanced_toggle.setArrowType(Qt.DownArrow if checked else Qt.RightArrow)

    def on_theme_changed(self, idx):
        """执行页主题切换（与制定页同步）"""
        key = self.theme_combo.itemData(idx)
        if not key:
            return
        apply_theme(QApplication.instance(), key)
        s = QSettings("RollingPlan", "Data")
        s.setValue(THEME_KEY, key)

    def _clear_layout(self, layout):
        while layout.count():
            item = layout.takeAt(0)
            w = item.widget()
            if w:
                w.setParent(None)      # 立刻从控件树上摘掉（deleteLater 要等事件循环）
                w.deleteLater()

    def _add_slot_row(self, parent_layout, slot_name, plan, is_extra=False,
                       slot_idx=None, show_complete=False, done=False, note=None,
                       fixed=False, blocked=False):
        """添加一行。is_extra=True 时是「额外安排」，左边框绿色 + 浅绿背景。

        v0.11：
        - 今天的每一格四个按钮：「固定计划」「拦截滚动」（小按钮，可切）
          + 「仅完成」（标记完成、不滚动）+「✓ 完成并滚动」（归档并上滚）
        - done=True 的格子（按过「仅完成」）：计划加删除线 + ✓，按钮灰掉
        - fixed / blocked：格子左上角加 📌 / ⛔ 标记
        - note：这一格的归档备注（已完成过的内容），显示成行尾小灰字
        - 额外轮的行不带时段名 —— 时段只是当天承装计划的栏位
        """
        row = QHBoxLayout()
        bg = "#E8F5E9" if is_extra else None
        border_color = "#2E7D32" if is_extra else "#1E88E5"

        if is_extra:
            slot_label = QLabel("⤴")
            slot_label.setMinimumWidth(30)
        else:
            mark = "⛔" if blocked else ("📌" if fixed else "")
            slot_label = QLabel(f"  {mark}{slot_name}:")
            slot_label.setMinimumWidth(80)
        slot_label.setFont(QFont("Microsoft YaHei", 16, QFont.Bold))
        row.addWidget(slot_label)

        if plan:
            plan_label = QLabel(f"✓ {plan}" if done else plan)
            plan_label.setFont(QFont("Microsoft YaHei", 16))
            if done:
                # 灰 + 删除线。用中性灰（#888）而不是主题色 —— 深浅主题下都看得见
                plan_label.setStyleSheet("color: #888; text-decoration: line-through;")
        else:
            plan_label = QLabel("(无)")
            plan_label.setFont(QFont("Microsoft YaHei", 14))
            plan_label.setStyleSheet("font-style: italic;")
        row.addWidget(plan_label)

        # 这一格的归档备注
        if note:
            note_label = QLabel("  归档：" + "、".join(note))
            note_label.setFont(QFont("Microsoft YaHei", 10))
            note_label.setStyleSheet("color: #888;")
            row.addWidget(note_label)

        row.addStretch(1)

        if show_complete and slot_idx is not None:
            # 固定计划 / 拦截滚动（小按钮，可切换）
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

        if show_complete and plan and slot_idx is not None:
            # 仅完成：标记完成，不滚动
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

            # 完成并滚动：归档 + 后面的上滚一格
            scroll_btn = QPushButton("✓ 完成并滚动")
            scroll_btn.setFont(QFont("Microsoft YaHei", 10, QFont.Bold))
            scroll_btn.setStyleSheet(
                "QPushButton { background-color: #4CAF50; color: white; "
                "padding: 6px 12px; border-radius: 4px; }"
                "QPushButton:hover { background-color: #43A047; }"
                "QPushButton:pressed { background-color: #388E3C; }"
            )
            scroll_btn.setCursor(Qt.PointingHandCursor)
            scroll_btn.clicked.connect(
                lambda checked=False, idx=slot_idx: self.on_complete_slot(idx))
            row.addWidget(scroll_btn)

        container = QWidget()
        if bg:
            container.setStyleSheet(f"background-color: {bg}; border-left: 3px solid {border_color}; padding-left: 4px;")
        cl = QHBoxLayout(container)
        cl.setContentsMargins(6, 2, 6, 2)
        cl.addLayout(row)
        parent_layout.addWidget(container)

    def refresh(self):
        self._clear_layout(self.day_layout)

        p = self.data.current_parent
        self.scheduler = PlanScheduler(p)

        self.parent_combo_label.setText(f"【{p.name}】")

        if p.start_date:
            cd = p.start_date.addDays(p.current_day)
            self.date_label.setText(f"📅 第 {p.current_day+1} 天 ({cd.toString('yyyy-MM-dd ddd')})")

        consumed, total = self.scheduler.get_progress()
        self.progress_label.setText(f"进度：{consumed} / {total}")

        # 今天已完成（归档）
        done_today = self.scheduler.done_today()
        if done_today:
            self.done_label.setText("🗂 今天已完成：" + "、".join(done_today))
        else:
            self.done_label.setText("")

        # 今天
        st = self.scheduler.today_state()
        day_plans = st["rows"]
        if not day_plans:
            lbl = QLabel("今天没有安排")
            lbl.setAlignment(Qt.AlignCenter)
            self.day_layout.addWidget(lbl)
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

        # 按钮启用状态 + 文案
        # v0.16：return_btn = 老「退回」按钮（仅撤今天完成 / 退额外轮最后一条）,逻辑保持 v0.15 不变。
        # undo_btn = 新 history 栈的撤销入口,只在 history 不空时显示。
        # redo_btn = 新 history 栈的重做入口,只在 _redo 不空时显示。
        can_undo = self.scheduler.can_undo_complete()
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
            reply = QMessageBox.question(self, "进入明天", msg)
            if reply != QMessageBox.Yes:
                return

        p.current_day += 1
        p.consumed += scheduler.today_state()["queue_used"]  # 今天的队列走到哪了
        p.archived_base = len(p.archived)                    # 「今天完成的」重新从 0 算
        p.borrowed_slots = []                                # 切天时清空额外安排
        p.inplace_done = []                                  # 新的一天：每格状态归零
        p.slot_notes = []                                    # 新的一天：归档备注重新开始记
        p.slot_fixed = []                                    # 新的一天：固定 / 拦截也归零
        p.slot_blocked = []
        p.normalize()
        self.data.save()
        self.refresh()

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
        self.hint.setStyleSheet("color: #666;")
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
            self.hint.setText("今天有格子按了「拦截滚动」—— 额外轮是当天最后的时间栏，"
                              "也在拦截范围里，腾出来的位置不由它候补。")
        else:
            self.hint.setText("额外轮 = 当天额外的时间栏。额外加进来的计划在这里按顺序候补，"
                              "前面格子完成并滚动时才会顶上来。")

        if not borrowed:
            lbl = QLabel("还没有额外安排")
            lbl.setAlignment(Qt.AlignCenter)
            lbl.setStyleSheet("font-style: italic;")
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
                tag.setStyleSheet("color: #888;")
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


# ============== 主窗口 ==============

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.data = PlanData()
        self.data.load()
        self.setWindowTitle("日常计划管理")
        self.setGeometry(100, 100, 950, 850)

        self.tabs = QTabWidget()
        self.setCentralWidget(self.tabs)

        self.editor = PlanEditor(
            self.data, self.show_executor, on_data_reloaded=self.reload_executor,
        )
        self.executor = PlanExecutor(self.data, self.show_editor)
        # v0.18：第三页「📊 归档总览」—— 看历史归档、进度、今天完成的列表
        self.calendar_view = PlanCalendarView(self.data)

        self.tabs.addTab(self.editor, "✏️ 制定计划")
        self.tabs.addTab(self.executor, "▶ 执行计划")
        self.tabs.addTab(self.calendar_view, "📊 归档总览")
        # 第三页激活时也要能刷新（用户在第三页时执行页可能完成了一条）
        self.tabs.currentChanged.connect(self._on_tab_changed)

    def _on_tab_changed(self, idx):
        """切到归档总览页时刷一次 —— 用户可能在前两页完成了计划。"""
        if idx == 2:
            self.calendar_view.refresh()

    def reload_executor(self):
        """v0.4：导入数据后重建 executor 引用新的 PlanData"""
        self.executor = PlanExecutor(self.data, self.show_editor)
        self.tabs.removeTab(1)
        self.tabs.addTab(self.executor, "▶ 执行计划")
        # v0.18：导入数据后归档总览页也要刷一遍(分类列表可能变了)
        if hasattr(self, "calendar_view"):
            self.calendar_view.refresh()

    def show_executor(self):
        self.executor = PlanExecutor(self.data, self.show_editor)
        self.tabs.removeTab(1)
        self.tabs.addTab(self.executor, "▶ 执行计划")
        self.tabs.setCurrentIndex(1)

    def show_editor(self):
        self.tabs.setCurrentIndex(0)

    def keyPressEvent(self, event):
        """只在「执行计划」页激活时，把 Ctrl+Enter / Ctrl+D / Ctrl+Z / Ctrl+Shift+Z / Ctrl+Y 转给 executor。
        其他页面 / 其他组合一律放行给 super()(制定页的输入框、Tab 切换、Esc 关对话框等都正常)。"""
        if self.tabs.currentIndex() != 1:
            super().keyPressEvent(event)
            return
        key = event.key()
        mods = event.modifiers()
        if mods & Qt.ControlModifier:
            if key in (Qt.Key_Return, Qt.Key_Enter):
                self.executor.on_add_next()
                return
            if key == Qt.Key_D:
                self.executor.on_next_day()
                return
            if key == Qt.Key_Z:
                # v0.16：Ctrl+Z = 通用撤销（history 栈，覆盖所有修改类动作）。
                # 老「退回」按钮（return_btn）走 on_return,行为不变（仅撤完成）。
                self.executor.on_undo()
                return
        super().keyPressEvent(event)


# 主题(QSS + apply_theme)已抽出到 theme.py 模块(v0.14 重构,行为完全等价)



def _setup_logger():
    """建一个滚动日志文件 (~/.hermes_cache/rollingplan_debug.log)。"""
    log_dir = os.path.expanduser("~/.hermes_cache")
    try:
        os.makedirs(log_dir, exist_ok=True)
    except Exception:
        return None
    log_path = os.path.join(log_dir, "rollingplan_debug.log")
    try:
        h = RotatingFileHandler(log_path, maxBytes=512000, backupCount=2, encoding="utf-8")
        h.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
        log = logging.getLogger("rollingplan")
        log.setLevel(logging.DEBUG)
        log.addHandler(h)
        return log
    except Exception:
        return None


_LOG = _setup_logger()


def _log(msg):
    """写日志（如果有 logger），同时 stderr（但 --windowed 下 stderr 可能为 None）"""
    if _LOG:
        try:
            _LOG.debug(msg)
        except Exception:
            pass
    try:
        sys.stderr.write(f"[RollingPlan] {msg}\n")
    except Exception:
        pass


# ============== 入口 ==============

if __name__ == "__main__":
    _log(f"启动 cwd={os.getcwd()}")
    app = QApplication(sys.argv)
    app.setStyle("Fusion")

    # 从 QSettings 读取上次主题，默认 dark
    s = QSettings("RollingPlan", "Data")
    saved_theme = s.value(THEME_KEY, "dark")
    if saved_theme not in ("dark", "light", "auto"):
        saved_theme = "dark"
    _log(f"saved theme from QSettings: {saved_theme}")
    apply_theme(app, saved_theme)

    win = MainWindow()
    win.show()
    sys.exit(app.exec_())
