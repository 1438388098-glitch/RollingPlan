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

def _pending_of(p):
    """待办队列：plans 去掉已完成的（按内容移除，保持原顺序）

    v0.9：完成用「计划内容」记账，不用下标 —— 这样编辑计划列表、
    跨天、上滚之后都不会指错行。
    """
    rem = list(p.plans)
    for a in getattr(p, "archived", []) or []:
        if a in rem:
            rem.remove(a)
    return rem


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


# ============== 核心调度 ==============

class PlanScheduler:
    """母计划调度器

    v0.9 模型：计划是一列待办队列，时段是「当天承装队列的栏位」。

    - 队列 = plans 去掉已完成（archived）的部分
    - 当天显示 = 队列里属于今天的 + 额外轮滚进来的 + 后面顺位补上的，
      一共 slots_per_day() 行；时段名只是行号，不代表计划本身
    - 完成一条 = 从队列里拿走（归档），后面的整体上滚一格
    - 额外轮 = 点「加一个」从未来拉进来的计划，排在当天的行后面；
      当天有空行时先由它们顶上
    """

    def __init__(self, parent: ParentPlan):
        self.p = parent

    # ---------------- 基础 ----------------

    def slots_per_day(self):
        return sum(s.get("count", 1) for s in self.p.time_slots)

    def _expand_slots(self):
        """把时间段展开成 [(slot_name, idx), ...] 的列表"""
        result = []
        idx = 0
        for slot in self.p.time_slots:
            for _ in range(slot.get("count", 1)):
                result.append((slot["name"], idx))
                idx += 1
        return result

    def pending(self):
        """待办队列（已完成的不在里面）"""
        return _pending_of(self.p)

    def done_today(self):
        """今天已完成的计划内容（按完成顺序）"""
        base = getattr(self.p, "archived_base", 0) or 0
        return list(getattr(self.p, "archived", [])[base:])

    def total_done(self):
        return len(getattr(self.p, "archived", []) or [])

    def extra_plans(self):
        """额外轮的计划内容（按加进来的顺序）"""
        out = []
        for entry in self.p.borrowed_slots:
            if isinstance(entry, (list, tuple)) and len(entry) >= 2:
                out.append(entry[1])
        return out

    # ---------------- 当天显示 ----------------

    def _pad_str(self, vals, spd):
        vals = list(vals) if isinstance(vals, list) else []
        vals = [x if isinstance(x, str) else None for x in vals]
        return (vals + [None] * spd)[:spd]

    def _pad_notes(self, notes, spd):
        notes = notes if isinstance(notes, list) else []
        out = [[x for x in (n or []) if isinstance(x, str)] if isinstance(n, list) else []
               for n in notes]
        return (out + [[] for _ in range(spd)])[:spd]

    def today_state(self):
        """把今天的显示一次算清（UI 和后续逻辑共用）

        v0.11：每格可以「固定计划」（这一格的原定计划不上移）或
        「拦截滚动」（这一格及往后的都不上移）。被钉住的格都显示自己的计划、不参与滚动；
        其余格子按队列顺序取计划。取到的条数上限 = 格数 - 今天已归档条数（quota）——
        所以腾出来的最后一格只由额外轮补，不会把第二天的计划滚上来。

        rows          [(slot_name, plan|None), ...]  今天的行
        row_done      [bool, ...]                    「仅完成」的格
        row_fixed     [bool, ...]                    「固定计划」的格
        row_blocked   [bool, ...]                    「拦截滚动」的格
        notes         [[内容, ...], ...]              每格的归档备注
        promoted      额外轮里已经滚到今天的行上的那几条（不在额外轮区重复显示）
        extra_left    额外轮里还没滚上来的（UI「额外安排」区显示这些）
        queue_used    今天从队列里取走了几条（进下一天时 consumed 就步进这么多）
        extras        额外轮全部内容
        """
        spd = self.slots_per_day()
        if spd == 0:
            return {"rows": [], "row_done": [], "row_fixed": [], "row_blocked": [],
                    "notes": [], "promoted": [], "extra_left": [],
                    "extras_frozen": False, "queue_used": 0,
                    "extras": []}

        slots = self._expand_slots()
        q = self.pending()
        start = min(max(self.p.consumed, 0), len(q))

        pinned = self._pad_str(getattr(self.p, "inplace_done", None), spd)   # 仅完成
        fixed = self._pad_str(getattr(self.p, "slot_fixed", None), spd)      # 固定计划
        blocked = self._pad_str(getattr(self.p, "slot_blocked", None), spd)  # 拦截滚动
        notes = self._pad_notes(getattr(self.p, "slot_notes", None), spd)

        # 被钉住的格：显示自己的计划、不参与滚动
        held = [pinned[i] or fixed[i] or blocked[i] for i in range(spd)]
        held_count = sum(1 for x in held if x)

        quota = max(0, spd - len(self.done_today()))
        head = q[start:start + max(0, min(quota, len(q) - start))]

        # 被钉住的计划不放进池子（否则会重复显示）
        skip = [x for x in held if x]
        pool = []
        for plan in head:
            if plan in skip:
                skip.remove(plan)
                continue
            pool.append(plan)

        movable = spd - held_count
        own = pool[:movable]
        extras = self.extra_plans()
        # v0.12：「额外轮」是当天最后的时间栏 —— 只要有格子按了「拦截滚动」，
        # 额外轮也在拦截范围里，腾出来的位置不再由它候补上来
        extras_frozen = any(blocked)
        used_extras = [] if extras_frozen else extras[:max(0, movable - len(own))]

        rows, row_done, row_fixed, row_blocked = [], [], [], []
        queue_iter = iter(own)
        extra_iter = iter(used_extras)
        for i in range(spd):
            row_fixed.append(bool(fixed[i]))
            row_blocked.append(bool(blocked[i]))
            if held[i]:
                rows.append((slots[i][0], held[i]))
                row_done.append(bool(pinned[i]))
                continue
            item = next(queue_iter, None)
            if item is None:
                item = next(extra_iter, None)
            rows.append((slots[i][0], item))
            row_done.append(False)

        return {
            "rows": rows,
            "row_done": row_done,
            "row_fixed": row_fixed,
            "row_blocked": row_blocked,
            "notes": notes,
            "promoted": list(used_extras),
            "extra_left": extras[len(used_extras):],
            "extras_frozen": extras_frozen,
            "queue_used": min(quota, max(0, len(q) - start)),
            "extras": extras,
        }

    def get_day_plans(self, day_index):
        """第 day_index 天的显示切片 [(slot_name, plan|None), ...]

        - day_index == current_day：今天（含上滚 / 额外轮顶进来的）
        - day_index >  current_day：按现在的状态往后推（计划日历预览用）
        - day_index <  current_day：已经过去的天，回不去了 → 空
        """
        spd = self.slots_per_day()
        if spd == 0:
            return []
        if day_index < self.p.current_day:
            return []
        if day_index == self.p.current_day:
            return self.today_state()["rows"]

        slots = self._expand_slots()
        q = self.pending()
        st = self.today_state()
        start = min(max(self.p.consumed, 0), len(q)) + st["queue_used"]
        start += (day_index - self.p.current_day - 1) * spd
        rows = []
        for i in range(spd):
            k = start + i
            rows.append((slots[i][0], q[k] if 0 <= k < len(q) else None))
        return rows

    def get_calendar(self):
        """计划日历：从今天开始往后（过去的天不再回溯）"""
        if not self.p.start_date:
            return []
        spd = self.slots_per_day()
        if spd == 0:
            return []
        q = self.pending()
        st = self.today_state()
        rest = max(0, len(q) - (min(max(self.p.consumed, 0), len(q)) + st["queue_used"]))
        n_days = 1 + (rest + spd - 1) // spd
        cal = []
        for k in range(n_days):
            d = self.p.start_date.addDays(self.p.current_day + k)
            cal.append((d, self.get_day_plans(self.p.current_day + k)))
        return cal

    def raw_calendar(self):
        """制定页预览用：按原始计划表整段铺开（不看进度，只看计划怎么分）"""
        spd = self.slots_per_day()
        if not self.p.start_date or spd == 0 or not self.p.plans:
            return []
        slots = self._expand_slots()
        total_days = (len(self.p.plans) + spd - 1) // spd
        cal = []
        for i in range(total_days):
            d = self.p.start_date.addDays(i)
            slice_ = self.p.plans[i * spd:(i + 1) * spd]
            rows = [(slots[j][0], slice_[j] if j < len(slice_) else None) for j in range(spd)]
            cal.append((d, rows))
        return cal

    # ---------------- 额外轮（加一个 / 添加指定 / 退回） ----------------

    def _future_slot_positions(self):
        """还没进今天、也没进额外轮的位置：
        [(day, slot_name, slot_idx, plan), ...]，按队列顺序

        v0.9：已经在额外轮里的那几条要跳过。按「内容」扣减而不是按下标 ——
        因为「添加指定」可以挑一条不在队首的，按下标数量跳会跳错
        （同一个内容出现多次时，各算一次，所以重名的计划也能分别安排）
        """
        spd = self.slots_per_day()
        if spd == 0:
            return []
        q = self.pending()
        st = self.today_state()
        start = min(max(self.p.consumed, 0), len(q)) + st["queue_used"]
        skip = list(st["extras"])
        slots = self._expand_slots()
        result = []
        for k in range(start, len(q)):
            plan = q[k]
            if plan in skip:
                skip.remove(plan)   # 这一条已经在额外轮里了
                continue
            off = k - self.p.consumed
            day = self.p.current_day + (off // spd if off >= 0 else 0)
            slot_idx = off % spd
            result.append((day, slots[slot_idx][0], slot_idx, plan))
        return result

    def can_borrow_slot(self, slot_name):
        """能否加指定时段：后面还有坐在这个位置上的计划"""
        for _, sname, _, _ in self._future_slot_positions():
            if sname == slot_name:
                return True
        return False

    def can_borrow_next(self):
        """能否加一个：后面还有没安排的计划"""
        return len(self._future_slot_positions()) > 0

    def borrow_next(self):
        """加一个：把队列里下一个还没安排的拉进额外轮"""
        positions = self._future_slot_positions()
        if not positions:
            return False
        day, sname, sidx, plan = positions[0]
        self.p.borrowed_slots.append([sname, plan, day, sidx])
        return True

    def available_pick_plans(self):
        """还能提前安排的计划内容（去重，按队列顺序）

        v0.9：用户按「计划」挑，不再按时段名挑 —— 时段只是当天的栏位。
        """
        out = []
        for _, _, _, plan in self._future_slot_positions():
            if plan not in out:
                out.append(plan)
        return out

    def borrow_plan(self, plan_text):
        """添加指定：把后面某一条还没安排的拉进额外轮"""
        for day, sname, sidx, plan in self._future_slot_positions():
            if plan == plan_text:
                self.p.borrowed_slots.append([sname, plan, day, sidx])
                return True
        return False

    # ---- 下面两个是 v0.3~v0.8 的「按时段名借」入口，UI 已经不用了 ----
    # （保留是为了兼容旧调用和 test_v2_2 的回归测试；两者的候选位置都来自
    #  _future_slot_positions()，逻辑是同一套）

    def available_borrow_names(self):
        """去重后所有还能加的位置名"""
        names = []
        for _, sname, _, _ in self._future_slot_positions():
            if sname not in names:
                names.append(sname)
        return names

    def borrow_slot(self, slot_name):
        """添加指定（旧入口）：把后面坐在这个位置上的最近一条拉进额外轮"""
        for day, sname, sidx, plan in self._future_slot_positions():
            if sname == slot_name:
                self.p.borrowed_slots.append([sname, plan, day, sidx])
                return True
        return False

    def unborrow_plan(self, plan_text):
        """删除该安排：把某一条额外安排撤掉（v0.12，UI 列表里逐条删）

        - 还在候补的：直接从额外轮拿走
        - 已经滚进今天某一格的：拿走之后那一格会重新按顺序补（补不到就空着）
        - 被拿走的那条回到「还没安排」的队里，以后还能再拉
        """
        self.p.normalize()
        for i, item in enumerate(self.p.borrowed_slots):
            if item[1] == plan_text:
                self.p.borrowed_slots.pop(i)
                self.p.normalize()
                return True
        return False

    def can_unborrow(self):
        return len(self.p.borrowed_slots) > 0

    def return_last_borrowed(self):
        """退回：把额外轮最后 1 个推回去"""
        if not self.p.borrowed_slots:
            return False
        self.p.borrowed_slots.pop()
        return True

    def can_return(self):
        return len(self.p.borrowed_slots) > 0

    # ---------------- 完成 / 撤销 ----------------

    def complete_only_slot(self, slot_idx):
        """仅完成：这一格标记完成（记进该时段的归档备注），计划留在格里，不滚动

        用途：事情做完了，但不想让后面的计划往上滚（比如还想按原时段做）。
        按过之后这一格的「仅完成」就灰掉；想滚的时候还可以按「完成并滚动」。
        """
        st = self.today_state()
        rows = st["rows"]
        if slot_idx < 0 or slot_idx >= len(rows):
            return False
        plan = rows[slot_idx][1]
        if not plan or st["row_done"][slot_idx]:
            return False
        self.p.archived.append(plan)
        self._drop_from_extras(plan)
        self.p.normalize()
        self.p.inplace_done[slot_idx] = plan
        self.p.slot_notes[slot_idx].append(plan)
        return True

    def complete_today_slot(self, slot_idx):
        """完成并滚动：归档这一格，后面的整体上滚一格

        v0.10：腾出来的最后一格只由额外轮补 —— 不会把第二天的计划滚上来。
        """
        st = self.today_state()
        rows = st["rows"]
        if slot_idx < 0 or slot_idx >= len(rows):
            return False
        plan = rows[slot_idx][1]
        if not plan:
            return False
        if not st["row_done"][slot_idx]:
            # 这一格还没「仅完成」过：先归档 + 记进备注
            self.p.archived.append(plan)
            self._drop_from_extras(plan)
            self.p.normalize()
            self.p.slot_notes[slot_idx].append(plan)
        # 已经「仅完成」过的：归档和备注都做过了，这里只把它解开，让它滚起来
        self.p.inplace_done[slot_idx] = None
        # 固定 / 拦截过的格子，完成后也解开（不然它一直占着不动）
        self.p.slot_fixed[slot_idx] = None
        self.p.slot_blocked[slot_idx] = None
        self.p.normalize()
        return True

    def can_complete_only(self, slot_idx):
        st = self.today_state()
        rows = st["rows"]
        if slot_idx < 0 or slot_idx >= len(rows):
            return False
        return bool(rows[slot_idx][1]) and not st["row_done"][slot_idx]

    def can_complete_today_slot(self, slot_idx):
        rows = self.today_state()["rows"]
        if slot_idx < 0 or slot_idx >= len(rows):
            return False
        return rows[slot_idx][1] is not None

    def toggle_fixed(self, slot_idx):
        """固定计划：这一格的原定计划不参与上滚（它后面的照常参与）"""
        st = self.today_state()
        rows = st["rows"]
        if slot_idx < 0 or slot_idx >= len(rows):
            return False
        self.p.normalize()
        if st["row_fixed"][slot_idx]:
            self.p.slot_fixed[slot_idx] = None
        else:
            plan = rows[slot_idx][1]
            if not plan:
                return False
            self.p.slot_fixed[slot_idx] = plan
        self.p.normalize()
        return True

    def toggle_blocked(self, slot_idx):
        """拦截滚动：这一格以及往后的所有格子都不参与上滚"""
        st = self.today_state()
        rows = st["rows"]
        if slot_idx < 0 or slot_idx >= len(rows):
            return False
        self.p.normalize()
        if st["row_blocked"][slot_idx]:
            for j in range(slot_idx, len(rows)):
                self.p.slot_blocked[j] = None
        else:
            for j in range(slot_idx, len(rows)):
                self.p.slot_blocked[j] = rows[j][1] or None
        self.p.normalize()
        return True

    def can_fix_slot(self, slot_idx):
        st = self.today_state()
        rows = st["rows"]
        if slot_idx < 0 or slot_idx >= len(rows):
            return False
        return bool(rows[slot_idx][1])

    def _drop_from_extras(self, plan):
        """完成的这条本来就在额外轮里的话，额外轮里那条也算做完了"""
        self.p.borrowed_slots = [
            e for e in self.p.borrowed_slots
            if not (isinstance(e, (list, tuple)) and len(e) >= 2 and e[1] == plan)
        ]

    def can_undo_complete(self):
        """今天有完成过的就能撤销（过去几天的不能撤）"""
        return len(self.done_today()) > 0

    def undo_complete(self):
        """撤销今天最后一次完成（「仅完成」和「完成并滚动」都算）"""
        if not self.can_undo_complete():
            return False
        plan = self.p.archived.pop()
        self.p.normalize()
        # 「仅完成」钉住的那一格解开
        for i, item in enumerate(self.p.inplace_done):
            if item == plan:
                self.p.inplace_done[i] = None
                break
        # 归档备注里也拿掉（最后一条匹配的）
        for i in range(len(self.p.slot_notes) - 1, -1, -1):
            note = self.p.slot_notes[i]
            if plan in note:
                note.pop(len(note) - 1 - note[::-1].index(plan))
                break
        self.p.normalize()
        return True

    # ---------------- 其他 ----------------

    def save_parent(self):
        pass  # 占位，实际由外部 PlanData.save() 触发

    def all_consumed(self):
        """全部结束：今天没有能显示的行 + 没有额外轮 + 后面也没有了"""
        if any(p is not None for _, p in self.today_state()["rows"]):
            return False
        if self.extra_plans():
            return False
        return not self.can_borrow_next()

    def get_progress(self):
        """进度：已推进到 / 总条数

        已推进 = 当前天窗口在原始计划表里的结束位置 + 今天完成的条数
        （所以点一次「完成」，数字就往前走一格）
        """
        spd = self.slots_per_day()
        if spd == 0:
            return 0, 0
        total = len(self.p.plans)
        qlen = max(0, total - self.total_done())
        advance = min(max(self.p.consumed, 0), qlen) + spd
        return min(advance + self.total_done(), total), total


# ============== 写入界面 ==============

class PlanEditor(QWidget):
    def __init__(self, data: PlanData, on_switch_to_exec, on_data_reloaded=None):
        super().__init__()
        self.data = data
        self.on_switch_to_exec = on_switch_to_exec
        self.on_data_reloaded = on_data_reloaded  # v0.4：导入后通知主窗口刷新 executor
        self.scheduler = PlanScheduler(data.current_parent)
        self.init_ui()
        self.refresh_all()

    def init_ui(self):
        layout = QVBoxLayout()

        title = QLabel("日常计划管理 — 制定计划")
        title.setFont(QFont("Microsoft YaHei", 16, QFont.Bold))
        layout.addWidget(title)

        # ============ 主题 + 导入/导出/重置 ============
        io_row = QHBoxLayout()
        # 主题切换（最左，全局设置）
        theme_label = QLabel("主题:")
        io_row.addWidget(theme_label)
        from rollingplan import THEME_OPTIONS  # 避免循环引用
        self.theme_combo = QComboBox()
        for key, label in THEME_OPTIONS:
            self.theme_combo.addItem(label, userData=key)
        # 初始值从 QSettings 读
        _saved = QSettings("RollingPlan", "Data").value(THEME_KEY, "dark")
        if _saved not in ("dark", "light", "auto"):
            _saved = "dark"
        for i, (k, _) in enumerate(THEME_OPTIONS):
            if k == _saved:
                self.theme_combo.setCurrentIndex(i)
                break
        self.theme_combo.currentIndexChanged.connect(self.on_theme_changed)
        io_row.addWidget(self.theme_combo)
        io_row.addStretch()
        reset_btn = QPushButton("🔄 重置当前分类进度")
        reset_btn.setStyleSheet("color: #666;")
        reset_btn.clicked.connect(self.on_reset_progress)
        io_row.addWidget(reset_btn)
        import_btn = QPushButton("📥 导入 JSON")
        import_btn.setStyleSheet("color: #666;")
        import_btn.clicked.connect(self.on_import)
        io_row.addWidget(import_btn)
        export_btn = QPushButton("📤 导出 JSON")
        export_btn.setStyleSheet("color: #666;")
        export_btn.clicked.connect(self.on_export)
        io_row.addWidget(export_btn)
        layout.addLayout(io_row)

        # ============ 分类列表（默认收起）============
        # QGroupBox 的 checkable + checked=False 在 pyqtdarktheme 下不自动隐藏子 widget，
        # 改用 QToolButton 手动控制 visibility
        parent_group = QGroupBox()
        self._parent_toggle = QToolButton()
        self._parent_toggle.setText("▸ 计划分类")
        self._parent_toggle.setCheckable(True)
        self._parent_toggle.setChecked(False)
        self._parent_toggle.setStyleSheet("QToolButton { border: none; padding: 4px; }")
        self._parent_toggle.setToolButtonStyle(Qt.ToolButtonTextOnly)
        self._parent_toggle.clicked.connect(self._toggle_parent_group)
        self._parent_body = QWidget()
        pg_outer = QVBoxLayout(self._parent_body)
        self.parent_name_label = QLabel()
        self.parent_name_label.setFont(QFont("Microsoft YaHei", 12, QFont.Bold))
        pg_outer.addWidget(self.parent_name_label)
        pg_layout = QHBoxLayout()

        self.parent_list = QListWidget()
        self.parent_list.setMaximumWidth(180)
        self.parent_list.currentRowChanged.connect(self.on_parent_select)
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
        self._plan_toggle.setStyleSheet("QToolButton { border: none; padding: 4px; }")
        self._plan_toggle.setToolButtonStyle(Qt.ToolButtonTextOnly)
        self._plan_toggle.clicked.connect(self._toggle_plan_group)
        self._plan_body = QWidget()
        plan_outer = QVBoxLayout(self._plan_body)
        plan_layout = QVBoxLayout()

        self.plan_list = QListWidget()
        self.plan_list.setMaximumHeight(160)
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
        self._slot_toggle.setStyleSheet("QToolButton { border: none; padding: 4px; }")
        self._slot_toggle.setToolButtonStyle(Qt.ToolButtonTextOnly)
        self._slot_toggle.clicked.connect(self._toggle_slot_group)
        self._slot_body = QWidget()
        slot_outer = QVBoxLayout(self._slot_body)
        slot_layout = QVBoxLayout()

        self.slot_list = QListWidget()
        self.slot_list.setMaximumHeight(120)
        slot_layout.addWidget(self.slot_list)

        slot_row = QHBoxLayout()
        self.slot_name_input = QLineEdit()
        self.slot_name_input.setPlaceholderText("时段名（早 / 中 / 晚……）")
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
            btn.clicked.connect(cb)
            slot_row.addWidget(btn)

        slot_layout.addLayout(slot_row)
        slot_outer.addLayout(slot_layout)
        self._slot_body.setVisible(False)
        slot_group_layout = QVBoxLayout(slot_group)
        slot_group_layout.addWidget(self._slot_toggle)
        slot_group_layout.addWidget(self._slot_body)
        layout.addWidget(slot_group)

        # ============ 起始日期 ============
        date_group = QGroupBox("起始日期")
        date_layout = QHBoxLayout()
        self.date_edit = QDateEdit()
        self.date_edit.setCalendarPopup(True)
        self.date_edit.setDate(QDate.currentDate())
        date_layout.addWidget(self.date_edit)
        date_group.setLayout(date_layout)
        layout.addWidget(date_group)

        # ============ 操作 ============
        btn_row = QHBoxLayout()
        save_btn = QPushButton("生成计划")
        save_btn.setFont(QFont("Microsoft YaHei", 11, QFont.Bold))
        save_btn.clicked.connect(self.save_and_preview)
        btn_row.addWidget(save_btn)

        preview_btn = QPushButton("预览")
        preview_btn.clicked.connect(self.preview_calendar)
        btn_row.addWidget(preview_btn)

        go_exec = QPushButton("开始执行 →")
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
        name, ok = QInputDialog.getText(self, "新建分类", "分类名:")
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
            QMessageBox.warning(self, "提示", "至少保留一个分类")
            return
        reply = QMessageBox.question(self, "确认", f"删除分类「{self.data.parents[idx].name}」？")
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

    def _toggle_parent_group(self):
        checked = self._parent_toggle.isChecked()
        self._parent_body.setVisible(checked)
        self._parent_toggle.setText("▾ 计划分类" if checked else "▸ 计划分类")

    def _toggle_plan_group(self):
        checked = self._plan_toggle.isChecked()
        self._plan_body.setVisible(checked)
        self._plan_toggle.setText("▾ 计划清单" if checked else "▸ 计划清单")

    def _toggle_slot_group(self):
        checked = self._slot_toggle.isChecked()
        self._slot_body.setVisible(checked)
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
        new_text, ok = QInputDialog.getText(self, "编辑计划", "新内容:", text=self.data.current_parent.plans[cur])
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
            QMessageBox.warning(self, "提示", "当前有额外安排正在进行，无法修改时段。\n完成今天后再来调整吧。")
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
            QMessageBox.warning(self, "提示", "当前有额外安排正在进行，无法修改时段。\n完成今天后再来调整吧。")
            return
        slot = self.data.current_parent.time_slots[cur]
        new_name, ok = QInputDialog.getText(self, "编辑时段", "新名称:", text=slot["name"])
        if ok and new_name.strip():
            new_count, ok2 = QInputDialog.getInt(self, "编辑时段", "新数量:", value=slot.get("count", 1), min=1, max=10)
            if ok2:
                self.data.current_parent.time_slots[cur] = {"name": new_name, "count": new_count}
                self.refresh_all()
                self.data.save()

    def del_slot(self):
        cur = self.slot_list.currentRow()
        if cur < 0:
            return
        if self.data.has_borrowed():
            QMessageBox.warning(self, "提示", "当前有额外安排正在进行，无法修改时段。\n完成今天后再来调整吧。")
            return
        self.data.current_parent.time_slots.pop(cur)
        self.refresh_all()
        self.data.save()

    def slot_up(self):
        if self.data.has_borrowed():
            QMessageBox.warning(self, "提示", "当前有额外安排正在进行，无法修改时段。")
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
            QMessageBox.warning(self, "提示", "当前有额外安排正在进行，无法修改时段。")
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
        s = QSettings("RollingPlan", "Data")
        s.setValue(THEME_KEY, key)

    # ====== v0.4 导入/导出 ======

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
        )
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
        """从 JSON 导入。会覆盖当前所有数据。"""
        path, _ = QFileDialog.getOpenFileName(
            self, "导入计划数据", "",
            "JSON 文件 (*.json);;所有文件 (*)",
        )
        if not path:
            return

        ok, msg, stats = self.data.import_from_file(path)
        if not ok:
            QMessageBox.warning(self, "导入失败", msg)
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
        )
        if confirm != QMessageBox.Yes:
            # 回滚——重新加载磁盘上的旧数据
            self.data.load()
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
            QMessageBox.warning(self, "提示", "请先添加计划内容")
            return
        if not p.time_slots:
            QMessageBox.warning(self, "提示", "请先添加时段")
            return
        cal = self.scheduler.raw_calendar()
        lines = [f"📅 【{p.name}】计划预览（共 {len(cal)} 天）", "=" * 40]
        for i, (d, plans) in enumerate(cal):
            lines.append(f"\n第{i+1}天 ({d.toString('MM-dd ddd')}):")
            for sname, plan in plans:
                m = "✓" if plan else "·"
                lines.append(f"  {m} {sname}: {plan if plan else '(空)'}")
        self.preview_area.setText("\n".join(lines))

    def go_exec(self):
        cp = self.data.current_parent
        if not cp.plans or not cp.time_slots or not cp.start_date:
            QMessageBox.warning(self, "提示", "请先完成：\n  • 计划清单（添加要做的事）\n  • 时段（一天分几段）\n  • 起始日期（哪天开始）")
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

        # 次要按钮行：退回 + 添加指定
        sub_row = QHBoxLayout()
        self.return_btn = QPushButton("⤴ 退回")
        self.return_btn.setToolTip("优先撤销今天最近一次「完成」,否则退额外轮最后一条  (Ctrl+Z)")
        self.return_btn.clicked.connect(self.on_return)
        sub_row.addWidget(self.return_btn)
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
        can_undo = self.scheduler.can_undo_complete()
        self.return_btn.setEnabled(can_undo or self.scheduler.can_return())
        self.return_btn.setText("↶ 撤销完成" if can_undo else "⤴ 退回")
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
        """退回：优先撤销今天最近一次「完成」，没有了再退额外轮最后一个"""
        if self.scheduler.can_undo_complete():
            ok = self.scheduler.undo_complete()
        else:
            ok = self.scheduler.return_last_borrowed()
        if ok:
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

        self.tabs.addTab(self.editor, "✏️ 制定计划")
        self.tabs.addTab(self.executor, "▶ 执行计划")

    def reload_executor(self):
        """v0.4：导入数据后重建 executor 引用新的 PlanData"""
        self.executor = PlanExecutor(self.data, self.show_editor)
        self.tabs.removeTab(1)
        self.tabs.addTab(self.executor, "▶ 执行计划")

    def show_executor(self):
        self.executor = PlanExecutor(self.data, self.show_editor)
        self.tabs.removeTab(1)
        self.tabs.addTab(self.executor, "▶ 执行计划")
        self.tabs.setCurrentIndex(1)

    def show_editor(self):
        self.tabs.setCurrentIndex(0)

    def keyPressEvent(self, event):
        """只在「执行计划」页激活时,把 Ctrl+Enter / Ctrl+D / Ctrl+Z 转给 executor。
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
                self.executor.on_return()
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
