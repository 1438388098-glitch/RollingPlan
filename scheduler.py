"""
RollingPlan 调度器（v0.15 抽出）

把 PlanScheduler 与它依赖的 _pending_of helper 从 rollingplan.py 抽出到独立模块。
行为完全等价：所有现有测试继续通过；rollingplan.py 通过 re-export 保留
PlanScheduler / _pending_of 的导入路径。

依赖：
- ParentPlan 数据类（在 rollingplan.py 里）；这里只用属性，不重新定义
- PyQt5.QtCore.QDate —— 用于日历预览（raw_calendar / get_calendar 用 start_date.addDays）
"""
from PyQt5.QtCore import QDate  # noqa: F401  —— raw_calendar / get_calendar 用


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

    def __init__(self, parent: "ParentPlan"):
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
        """加一个：把队列里下一个还没安排的拉进额外轮

        v0.16：先 push 历史。
        """
        positions = self._future_slot_positions()
        if not positions:
            return False
        day, sname, sidx, plan = positions[0]
        self._push()
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
        """添加指定：把后面某一条还没安排的拉进额外轮

        v0.16：先 push 历史。
        """
        for day, sname, sidx, plan in self._future_slot_positions():
            if plan == plan_text:
                self._push()
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
        """添加指定（旧入口）：把后面坐在这个位置上的最近一条拉进额外轮

        v0.16：先 push 历史。
        """
        for day, sname, sidx, plan in self._future_slot_positions():
            if sname == slot_name:
                self._push()
                self.p.borrowed_slots.append([sname, plan, day, sidx])
                return True
        return False

    def unborrow_plan(self, plan_text):
        """删除该安排：把某一条额外安排撤掉（v0.12，UI 列表里逐条删）

        - 还在候补的：直接从额外轮拿走
        - 已经滚进今天某一格的：拿走之后那一格会重新按顺序补（补不到就空着）
        - 被拿走的那条回到「还没安排」的队里，以后还能再拉

        v0.16：先 push 历史。
        """
        self.p.normalize()
        for i, item in enumerate(self.p.borrowed_slots):
            if item[1] == plan_text:
                self._push()
                self.p.borrowed_slots.pop(i)
                self.p.normalize()
                return True
        return False

    def can_unborrow(self):
        return len(self.p.borrowed_slots) > 0

    def return_last_borrowed(self):
        """退回：把额外轮最后 1 个推回去

        v0.16：先 push 历史。
        """
        if not self.p.borrowed_slots:
            return False
        self._push()
        self.p.borrowed_slots.pop()
        return True

    def can_return(self):
        return len(self.p.borrowed_slots) > 0

    # ---------------- 完成 / 撤销 ----------------

    def _push(self):
        """v0.16：执行页修改前 push 一次状态快照（用于撤销栈）"""
        self.p.push_history()

    def complete_only_slot(self, slot_idx):
        """仅完成：这一格标记完成（记进该时段的归档备注），计划留在格里，不滚动

        用途：事情做完了，但不想让后面的计划往上滚（比如还想按原时段做）。
        按过之后这一格的「仅完成」就灰掉;想滚的时候还可以按「完成并滚动」。

        v0.16：先 push 历史,这样可以被 undo() 撤回。
        """
        st = self.today_state()
        rows = st["rows"]
        if slot_idx < 0 or slot_idx >= len(rows):
            return False
        plan = rows[slot_idx][1]
        if not plan or st["row_done"][slot_idx]:
            return False
        self._push()
        self.p.archived.append(plan)
        self._drop_from_extras(plan)
        self.p.normalize()
        self.p.inplace_done[slot_idx] = plan
        self.p.slot_notes[slot_idx].append(plan)
        return True

    def complete_today_slot(self, slot_idx):
        """完成并滚动:归档这一格,后面的整体上滚一格

        v0.10:腾出来的最后一格只由额外轮补 —— 不会把第二天的计划滚上来。
        v0.16:先 push 历史。
        """
        st = self.today_state()
        rows = st["rows"]
        if slot_idx < 0 or slot_idx >= len(rows):
            return False
        plan = rows[slot_idx][1]
        if not plan:
            return False
        self._push()
        if not st["row_done"][slot_idx]:
            # 这一格还没「仅完成」过:先归档 + 记进备注
            self.p.archived.append(plan)
            self._drop_from_extras(plan)
            self.p.normalize()
            self.p.slot_notes[slot_idx].append(plan)
        # 已经「仅完成」过的:归档和备注都做过了,这里只把它解开,让它滚起来
        self.p.inplace_done[slot_idx] = None
        # 固定 / 拦截过的格子,完成后也解开（不然它一直占着不动）
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
        """固定计划:这一格的原定计划不参与上滚(它后面的照常参与)

        v0.16:先 push 历史(改的是钉住状态,而不是队列/归档)
        """
        st = self.today_state()
        rows = st["rows"]
        if slot_idx < 0 or slot_idx >= len(rows):
            return False
        self.p.normalize()
        if st["row_fixed"][slot_idx]:
            self._push()
            self.p.slot_fixed[slot_idx] = None
        else:
            plan = rows[slot_idx][1]
            if not plan:
                return False
            self._push()
            self.p.slot_fixed[slot_idx] = plan
        self.p.normalize()
        return True

    def toggle_blocked(self, slot_idx):
        """拦截滚动:这一格以及往后的所有格子都不参与上滚

        v0.16:先 push 历史。
        """
        st = self.today_state()
        rows = st["rows"]
        if slot_idx < 0 or slot_idx >= len(rows):
            return False
        self.p.normalize()
        if st["row_blocked"][slot_idx]:
            self._push()
            for j in range(slot_idx, len(rows)):
                self.p.slot_blocked[j] = None
        else:
            self._push()
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

    def undo(self):
        """v0.16:整页撤销 —— 把上一次操作的状态恢复。"""
        return self.p.undo()

    def redo(self):
        """v0.16:整页重做 —— 恢复一次被 undo 的操作。"""
        return self.p.redo()

    # 兼容旧 API:v0.9~v0.15 的「撤销今天最近一次完成」(只撤完成,不撤加/退/固定/拦截)
    # 新栈已经覆盖它,但保留旧入口,免得 test_scroll_v11.py 这种回归测试还得改。
    def can_undo_complete(self):
        """老 API:撤销条件 = 今天有完成过的（不管 history 栈里有什么）。

        新栈里能 undo 任何东西（不只是完成），但旧 API 这个布尔只关心「能不能撤今天最后一次完成」。
        """
        return len(self.done_today()) > 0

    def undo_complete(self):
        """老 API:只撤今天最近一次完成（保留 v0.9~v0.15 的精确语义）。

        新版 on_undo() 才是通用的 undo —— 它能撤任意动作（不仅是完成）。
        """
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
