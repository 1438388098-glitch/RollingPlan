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
import tempfile
from logging.handlers import RotatingFileHandler
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QListWidget,
    QSpinBox, QDateEdit, QTextEdit, QMessageBox, QTabWidget,
    QGroupBox, QInputDialog, QFileDialog, QComboBox, QToolButton,
    QSizePolicy, QDialog, QScrollArea,
)
from PyQt5.QtCore import Qt, QDate, QSettings
from PyQt5.QtGui import QFont, QKeySequence
from PyQt5.QtWidgets import QShortcut

# 主题:QSS 字符串 + apply_theme 抽到独立模块(v0.14 重构,行为完全等价)
from theme import THEME_KEY, THEME_OPTIONS, apply_theme
from theme import DARK_QSS, LIGHT_QSS  # 向后兼容:test_theme_v05.py 直接 import 这两个常量
import animations
import theme


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
        # ---- v0.22 归档按天分组 ----
        # daily_boundaries[i] = 第 i+1 天结束时 archived 的长度
        # (切天时 push len(archived) 即 archived_base; 第 1 天不 push, 第 2 天 push 表示「第 1 天 N 条后切到第 2 天」)
        # calendar_view 用它做「📅 第 1 天 / 第 2 天」分组
        self.daily_boundaries = []
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
            # v0.22：归档按天分组边界(切天时 push len(archived))
            "daily_boundaries": self.daily_boundaries,
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
        # v0.30 类型防线（审计 P1-5）：脏 JSON 里的 "3"/2.7/-1 原样进来
        # 会让 addDays 抛 TypeError / 天数出现负值 —— 统一 int 化 + 夹非负
        try:
            self.current_day = max(0, int(d.get("current_day", 0)))
        except (TypeError, ValueError):
            self.current_day = 0
        self.borrowed_slots = d.get("borrowed_slots", [])
        self.archived = [a for a in (d.get("archived") or []) if isinstance(a, str)]
        self.archived_base = d.get("archived_base", 0) or 0
        self.consumed = d.get("consumed", 0) or 0
        # v0.22：归档按天分组边界(旧存档没有 → 空)
        self.daily_boundaries = [int(b) for b in (d.get("daily_boundaries") or []) if isinstance(b, (int, float))]
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
        # v0.22：daily_boundaries 收敛
        #   - 每个值在 [0, len(archived)] 内
        #   - 单调递增 + 去重（同一个边界只留一个）
        #   - 条数不超过已过去的天数（每切一天 push 一条 → len(daily_boundaries) ≤ current_day）
        if not isinstance(self.daily_boundaries, list):
            self.daily_boundaries = []
        bs = sorted(max(0, min(int(b), len(self.archived)))
                    for b in self.daily_boundaries if isinstance(b, (int, float)))
        deduped = [b for i, b in enumerate(bs) if i == 0 or b > bs[i - 1]]
        day_n = self.current_day if isinstance(self.current_day, int) else 0
        self.daily_boundaries = deduped[:max(0, day_n)]
        # v0.30：current_day 本身也收敛（审计 P1-5：normalize 之前唯独漏了它）
        if not isinstance(self.current_day, int) or self.current_day < 0:
            try:
                self.current_day = max(0, int(self.current_day))
            except (TypeError, ValueError):
                self.current_day = 0

    def reset_progress(self):
        """v0.4：重置进度。plans/time_slots/start_date 不变。"""
        self.current_day = 0
        self.borrowed_slots = []
        self.archived = []
        self.archived_base = 0
        self.consumed = 0
        # v0.22：归档按天分组边界也清空
        self.daily_boundaries = []
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
        "consumed", "daily_boundaries",
        "inplace_done", "slot_notes", "slot_fixed", "slot_blocked",
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
        # 切天（v0.22b）：天数变了优先报这个 —— 切天还会清额外轮 / 每格状态,
        # 不先判的话会被后面的「退回额外轮」抢走(额外轮少了几条)。
        day_now = cur["current_day"] if isinstance(cur["current_day"], int) else 0
        day_then = snap["current_day"] if isinstance(snap["current_day"], int) else 0
        if day_now != day_then:
            return "进入下一天" if day_now > day_then else "退回前一天"
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
            return "添加额外安排"
        if n_extra_now < n_extra_then:
            return "退回额外安排"
        return "修改"


class PlanData:
    """全局数据"""

    def __init__(self):
        self.parents = [ParentPlan("分类1")]
        self.current_parent_idx = 0
        self.last_load_error = None   # v0.30：读档失败的原因（无错为 None）

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
        # v0.30 类型防线（审计 P1-5）：负数/浮点/字符串 idx 原样进来会在
        # current_parent 处 IndexError 崩进程 —— int 化 + 夹进 [0, len-1]
        try:
            idx = int(d.get("current_parent_idx", 0))
        except (TypeError, ValueError):
            idx = 0
        if not 0 <= idx < len(self.parents):
            idx = 0
        self.current_parent_idx = idx

    def has_borrowed(self):
        """任一母计划是否正在借用额外轮（会因编辑而索引错位）"""
        return any(bool(p.borrowed_slots) for p in self.parents)

    def save(self):
        from theme import app_settings
        s = app_settings()
        # v0.30 R29（审计 P0-1 的保险丝）：3 代备份环。
        # 每次写入前把上一代数据轮转进 backup 链（backup ← 上一代，_2 ← 上上代…），
        # 「改错→保存→又改错→保存」也能救回最早一代。
        prev = s.value("plan_data")
        if prev:
            s.setValue("plan_data_backup_3", s.value("plan_data_backup_2"))
            s.setValue("plan_data_backup_2", s.value("plan_data_backup"))
            s.setValue("plan_data_backup", prev)
        s.setValue("plan_data", json.dumps(self.to_dict(), ensure_ascii=False))

    def load(self):
        """读档。失败时不再静默（审计 P0-1）：损坏的原始数据转存成备份文件，
        错误信息记到 last_load_error，由 MainWindow 弹窗告知用户。"""
        self.last_load_error = None
        from theme import app_settings
        s = app_settings()
        data = s.value("plan_data")
        if data is None:
            # v0.30 R10 一次性迁移：老版本在 Windows 把数据写进了注册表
            # （QSettings 两参构造 = NativeFormat），搬进 INI 后统一走文件存储
            legacy_s = QSettings(QSettings.NativeFormat, QSettings.UserScope,
                                 "RollingPlan", "Data")
            legacy = legacy_s.value("plan_data")
            if legacy:
                data = legacy
                s.setValue("plan_data", legacy)
                legacy_s.remove("plan_data")   # 迁移完成，注册表只清这一项
        if data:
            try:
                loaded = json.loads(data)
                if not isinstance(loaded, dict):
                    raise ValueError("plan_data 不是 JSON 对象")
                self.from_dict(loaded)
                return True
            except Exception as e:
                self.last_load_error = str(e)
                self._backup_corrupt_data(data)
        return False

    def _backup_corrupt_data(self, raw):
        """把读不出来/解析不了的原始数据转存到用户目录，永远可手工找回。"""
        try:
            from datetime import datetime
            log_dir = os.path.expanduser("~/.hermes_cache")
            try:
                os.makedirs(log_dir, exist_ok=True)
            except Exception:
                log_dir = tempfile.gettempdir()
            path = os.path.join(
                log_dir,
                "rollingplan_corrupt_backup_{}.json".format(
                    datetime.now().strftime("%Y%m%d_%H%M%S")),
            )
            with open(path, "w", encoding="utf-8") as f:
                f.write(raw)
            self.last_load_error += "\n损坏数据已备份到：" + path
        except Exception:
            pass

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
# v0.21: PlanExecutor + ExtraArrangementsDialog 抽到 executor.py
# (re-export 保持老测试/test_scroll_v11/test_minimal_v06 等 from rollingplan import PlanExecutor 工作)
from executor import PlanExecutor, ExtraArrangementsDialog  # noqa: F401


# ============== 主窗口 ==============

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.data = PlanData()
        if not self.data.load() and self.data.last_load_error:
            # v0.30（审计 P0-1）：读档失败必须让用户知道，而不是「数据凭空消失」
            QMessageBox.warning(
                self, "数据加载失败",
                "上次保存的数据读不出来，已用空数据启动。\n\n" + self.data.last_load_error,
            )
        self._start_backup_if_needed()
        self.setWindowTitle("日常计划管理")
        # v0.30 R12（审计 P2-9）：初始尺寸适配屏幕（1366x768 笔记本上 850 高会超屏）
        _screen = QApplication.primaryScreen()
        if _screen is not None:
            _avail = _screen.availableGeometry()
            self.resize(min(950, _avail.width() - 40), min(850, _avail.height() - 40))
            self.move(_avail.center() - self.rect().center())   # v0.30 R28：启动居中
        else:
            self.resize(950, 850)
        self.setMinimumSize(720, 520)

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
        # v0.30（审计 P2-4）：两个主题下拉互相同步（都在构造时读 QSettings，
        # 之后一边切换另一边不知道）——信号互连 + blockSignals 防递归
        self.executor.theme_combo.currentIndexChanged.connect(
            self._sync_theme_combos)
        self.editor.theme_combo.currentIndexChanged.connect(
            self._sync_theme_combos)
        # 第三页激活时也要能刷新（用户在第三页时执行页可能完成了一条）
        self.tabs.currentChanged.connect(self._on_tab_changed)
        self._refresh_window_title()

        # v0.30 R12（审计 P1-11）：Ctrl+1/2/3 直接切页 —— QShortcut 挂在窗口上，
        # 不依赖焦点链，任何控件拿到焦点都好使
        for _i in range(3):
            QShortcut(QKeySequence("Ctrl+{}".format(_i + 1)), self,
                      lambda idx=_i: self.tabs.setCurrentIndex(idx))

    def _sync_theme_combos(self, idx):
        """v0.30：把主题下拉的选择同步到另一页的下拉（不触发重复应用）。"""
        source = self.sender()
        target = self.editor.theme_combo if source is self.executor.theme_combo \
            else self.executor.theme_combo
        target.blockSignals(True)
        target.setCurrentIndex(idx)
        target.blockSignals(False)

    def _refresh_window_title(self):
        """v0.30 R28：标题带当前分类名，多分类时任务栏可分辨。"""
        try:
            self.setWindowTitle("日常计划管理 — 【{}】".format(self.data.current_parent.name))
        except (IndexError, AttributeError):
            self.setWindowTitle("日常计划管理")

    def _on_tab_changed(self, idx):
        """切页时刷新目标页 —— 用户可能在前一页改了数据。

        v0.30（审计 P1-4）：直点执行页 tab 也要刷 —— 否则界面显示的还是旧
        scheduler 的行，点「完成并滚动」归档的可能不是用户看到的那条。
        """
        w = self.tabs.widget(idx)
        if w is self.calendar_view:
            self.calendar_view.refresh()
        elif w is self.executor:
            self.executor.refresh()
        self._refresh_window_title()
        # v0.30 R16：切页不再挂整页透明度特效 —— 每帧全页重绘是切页卡顿感来源
        # （视觉复查 Top#2）；干脆的瞬时切换比半吊子淡入更「流畅」

    def _replace_executor(self):
        """换一个新 executor 并保证它始终占据 index 1（v0.30 修 P0）。

        旧实现 removeTab(1) + addTab() —— addTab 是**追加到末尾**，第三页（v0.18）
        出现后每点一次「开始执行」页签就变成 [制定, 归档, 执行]：
        setCurrentIndex(1) 显示的是归档页、快捷键门槛 currentIndex()!=1 全部失准、
        旧 executor 只是脱离页签树并不销毁（内存泄漏）。改成 insertTab(1) 兜底 +
        deleteLater 旧页。
        """
        old = getattr(self, "executor", None)
        self.executor = PlanExecutor(self.data, self.show_editor)
        if old is not None:
            old_idx = self.tabs.indexOf(old)
            if old_idx >= 0:
                self.tabs.removeTab(old_idx)
            old.deleteLater()
        self.tabs.insertTab(1, self.executor, "▶ 执行计划")

    def reload_executor(self):
        """v0.4：导入数据后重建 executor 引用新的 PlanData"""
        self._replace_executor()
        # v0.18：导入数据后归档总览页也要刷一遍(分类列表可能变了)
        if hasattr(self, "calendar_view"):
            self.calendar_view.refresh()

    def show_executor(self):
        self._replace_executor()
        self.tabs.setCurrentIndex(1)

    def show_editor(self):
        # v0.30（审计 P1-3）：进制定页前先把控件同步到当前分类 ——
        # 执行页切换分类后，editor 的 date_edit 还显示旧分类日期，
        # save_current_to_parent 会把旧日期覆写进新分类的 start_date
        self.editor.refresh_all()
        self.tabs.setCurrentIndex(0)

    def showEvent(self, event):
        """v0.30 R7：主窗口启动出场淡入（只做一次；offscreen 自动禁用）。"""
        super().showEvent(event)
        animations.launch_fade(self)

    def _start_backup_if_needed(self):
        """v0.30：读档失败启动后，把坏掉的 plan_data 挪进 backup 位。
        这样用户本次会话 save 出的新数据不会覆盖仅有的损坏原件（它已在 backup，
        原件内容也已转存为时间戳备份文件）。"""
        if self.data.last_load_error:
            from theme import app_settings
            s = app_settings()
            corrupt = s.value("plan_data")
            if corrupt:
                s.setValue("plan_data_backup", corrupt)
            s.remove("plan_data")

    def keyPressEvent(self, event):
        """只在「执行计划」页激活时，把快捷键转给 executor。

        v0.30：门槛从「currentIndex() != 1」改成「currentWidget() is not executor」
        —— 页签重建后顺序永远正确（_replace_executor 用 insertTab(1)），但按
        widget 身份判断对任何未来页签重排都免疫。

        映射:
        - Ctrl+Enter / Ctrl+Return  → 加一个
        - Ctrl+D                     → 今天完成 / 进入下一天
        - Ctrl+Z                     → 撤销（history 栈;on_undo）
        - Ctrl+Shift+Z / Ctrl+Y      → 重做（history 栈;on_redo）
        - Esc / Tab 等其他键放行给 super(),制定页的输入框、Tab 切换、对话框关闭都正常。
        """
        if self.tabs.currentWidget() is not self.executor:
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
                if mods & Qt.ShiftModifier:
                    # v0.20：Ctrl+Shift+Z = redo(老 tooltip / 注释里就提到,代码一直没绑)
                    self.executor.on_redo()
                else:
                    # v0.16：Ctrl+Z = 通用撤销(history 栈,覆盖所有修改类动作)。
                    # 老「退回」按钮(return_btn)走 on_return,行为不变（仅撤完成）。
                    self.executor.on_undo()
                return
            if key == Qt.Key_Y:
                # v0.20：Ctrl+Y = redo(标准编辑器绑定;redo_btn tooltip 提到了)
                self.executor.on_redo()
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
    from theme import app_settings
    s = app_settings()
    saved_theme = s.value(THEME_KEY, "dark")
    if saved_theme not in ("dark", "light", "auto"):
        saved_theme = "dark"
    _log(f"saved theme from QSettings: {saved_theme}")
    apply_theme(app, saved_theme)

    win = MainWindow()
    win.show()
    sys.exit(app.exec_())
