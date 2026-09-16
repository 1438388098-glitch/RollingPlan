"""
v0.16 撤销栈测试

覆盖：
- ParentPlan.push_history / can_undo / can_redo / undo / redo 基本操作
- 每次 push 清空 _redo
- 栈上限 50,超出会丢最老的
- PlanScheduler 所有修改类方法都 push 了 history(完成/退回/添加/添加指定/删除安排/固定/拦截)
- undo() 能完整撤销 borrow_next 之后的状态(归档为空、额外轮为空)
- undo() 能完整撤销 complete_today_slot 之后的状态(归档不变、inplace_done/slot_fixed 解开、滚动回到原位)
- undo() 能完整撤销 toggle_fixed 之后的状态
- redo() 恢复被 undo 的状态
- history 栈不会污染其他分类(state 是绑在 ParentPlan 对象上)
- 重置进度 = 清空 history
- 老 API (can_undo_complete / undo_complete) 的精确语义保持 v0.15 不变
"""
import os
import sys
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtWidgets import QApplication
app = QApplication.instance() or QApplication(sys.argv)

from rollingplan import ParentPlan, PlanScheduler


def _make_parent(plans=None, slots=None):
    p = ParentPlan("测试分类")
    p.plans = list(plans or ["A", "B", "C", "D", "E", "F"])
    p.time_slots = list(slots or [{"name": "早", "count": 3}])
    p.start_date = p.start_date  # 默认 today
    p.current_day = 0
    p.normalize()
    return p


class TestParentPlanUndoStack(unittest.TestCase):
    """ParentPlan 直接的 history / undo / redo 行为。"""

    def test_empty_initially(self):
        p = _make_parent()
        self.assertFalse(p.can_undo())
        self.assertFalse(p.can_redo())
        self.assertEqual(p.undo(), False)
        self.assertEqual(p.redo(), False)

    def test_push_then_undo_restores(self):
        p = _make_parent()
        p.push_history()                # 快照空状态
        p.archived.append("X")          # 改一点
        self.assertTrue(p.can_undo())
        self.assertEqual(p.archived, ["X"])
        ok = p.undo()
        self.assertTrue(ok)
        self.assertEqual(p.archived, []) # archived 回到 []
        self.assertTrue(p.can_redo())

    def test_redo_restores_change(self):
        p = _make_parent()
        p.push_history()
        p.archived.append("X")
        p.undo()
        self.assertEqual(p.archived, [])
        ok = p.redo()
        self.assertTrue(ok)
        self.assertEqual(p.archived, ["X"])

    def test_new_push_clears_redo(self):
        p = _make_parent()
        p.push_history()
        p.archived.append("A")
        p.undo()                         # _redo = [snapshot-with-A]
        self.assertTrue(p.can_redo())
        p.archived.append("B")           # 这是一个未 push 的新操作
        p.push_history()                 # 新 push 会清掉 redo
        self.assertFalse(p.can_redo())

    def test_history_limit_caps_at_50(self):
        p = _make_parent()
        for i in range(60):
            p.archived.append(f"X{i}")
            p.push_history()
        # _history 应该 ≤ 50
        self.assertLessEqual(len(p._history), 50)

    def test_reset_progress_clears_history(self):
        p = _make_parent(plans=["A","B","C"])
        s = PlanScheduler(p)
        s.borrow_next()
        s.complete_today_slot(0)
        self.assertTrue(p.can_undo())
        p.reset_progress()
        self.assertFalse(p.can_undo())
        self.assertFalse(p.can_redo())


class TestSchedulerPushesHistory(unittest.TestCase):
    """所有修改类方法都 push history,这样 on_undo 能撤任意动作。"""

    def test_borrow_next_pushes(self):
        p = _make_parent()
        s = PlanScheduler(p)
        self.assertFalse(p.can_undo())
        s.borrow_next()
        self.assertTrue(p.can_undo())
        # undo 把额外轮退掉
        s.undo()
        self.assertEqual(p.borrowed_slots, [])

    def test_borrow_plan_pushes(self):
        p = _make_parent()
        s = PlanScheduler(p)
        ok = s.borrow_plan("D")            # 「添加指定」
        self.assertTrue(ok)
        self.assertEqual(len(p.borrowed_slots), 1)
        s.undo()
        self.assertEqual(p.borrowed_slots, [])

    def test_complete_today_pushes(self):
        p = _make_parent()
        s = PlanScheduler(p)
        before = list(p.archived)
        s.complete_today_slot(0)           # 早A 完成并滚动
        self.assertNotEqual(p.archived, before)
        s.undo()
        self.assertEqual(p.archived, before)
        self.assertEqual(p.inplace_done[0], None)

    def test_complete_only_pushes(self):
        p = _make_parent()
        s = PlanScheduler(p)
        before_arc = list(p.archived)
        before_inplace = list(p.inplace_done)
        s.complete_only_slot(0)            # 早A 仅完成
        self.assertNotEqual(p.archived, before_arc)
        s.undo()
        self.assertEqual(p.archived, before_arc)
        self.assertEqual(p.inplace_done, before_inplace)

    def test_toggle_fixed_pushes(self):
        p = _make_parent()
        s = PlanScheduler(p)
        self.assertFalse(s.today_state()["row_fixed"][0])
        s.toggle_fixed(0)
        self.assertTrue(s.today_state()["row_fixed"][0])
        s.undo()
        self.assertFalse(s.today_state()["row_fixed"][0])

    def test_toggle_blocked_pushes(self):
        p = _make_parent()
        s = PlanScheduler(p)
        s.toggle_blocked(0)                # 拦截「早」
        self.assertTrue(s.today_state()["row_blocked"][0])
        s.undo()
        self.assertFalse(s.today_state()["row_blocked"][0])

    def test_return_last_borrowed_pushes(self):
        p = _make_parent()
        s = PlanScheduler(p)
        s.borrow_next()                    # push 1: borrow
        s.borrow_next()                    # push 2: borrow
        self.assertEqual(len(p.borrowed_slots), 2)
        s.return_last_borrowed()           # push 3: return
        self.assertEqual(len(p.borrowed_slots), 1)
        s.undo()                           # 撤 return
        self.assertEqual(len(p.borrowed_slots), 2)

    def test_unborrow_plan_pushes(self):
        p = _make_parent()
        s = PlanScheduler(p)
        s.borrow_next()
        # 拿一条还没滚进今天行上的 —— 它在额外轮里
        # pending 队列 [A,B,C,D,E,F] -> consumed=0 -> today=[A,B,C];extras=[D]
        target = p.borrowed_slots[0][1]
        ok = s.unborrow_plan(target)
        self.assertTrue(ok)
        self.assertEqual(p.borrowed_slots, [])
        s.undo()
        self.assertEqual(len(p.borrowed_slots), 1)


class TestUndoRestoresScrolledState(unittest.TestCase):
    """撤销完成 / 撤销退回时,UI 显示应该完全回到改之前的样子。"""

    def test_undo_complete_restores_today_layout(self):
        p = _make_parent(plans=["1","2","3","4","5","6"], slots=[{"name":"早","count":3}])
        s = PlanScheduler(p)
        before = [row for row in s.today_state()["rows"]]
        s.complete_today_slot(0)           # 早1 完成并滚动 → 早2 中3 晚4
        self.assertNotEqual(before, s.today_state()["rows"])
        s.undo()
        self.assertEqual(before, s.today_state()["rows"])

    def test_undo_complete_chain_of_two(self):
        """连续完成两次,undo 两次都回到原状。"""
        p = _make_parent(plans=["1","2","3","4","5","6"], slots=[{"name":"早","count":3}])
        s = PlanScheduler(p)
        before = [row for row in s.today_state()["rows"]]
        s.complete_today_slot(0)
        s.complete_today_slot(0)           # 早2 完成并滚动（因已完成 1 格,quota=2）
        self.assertNotEqual(before, s.today_state()["rows"])
        s.undo()                           # 撤第二次
        # 还原回「早2 中3 晚4」
        self.assertEqual(s.today_state()["rows"][0], ("早", "2"))
        s.undo()                           # 撤第一次
        self.assertEqual(before, s.today_state()["rows"])

    def test_undo_borrow_chain(self):
        """加一个 → 加一个 → 退一个 → 撤退一个 → 撤加一个 → 撤加一个 = 回原状。"""
        p = _make_parent()
        s = PlanScheduler(p)
        before_extras = list(p.borrowed_slots)
        s.borrow_next()
        s.borrow_next()
        s.return_last_borrowed()
        self.assertEqual(len(p.borrowed_slots), 1)
        s.undo()                           # 撤 return
        self.assertEqual(len(p.borrowed_slots), 2)
        s.undo()                           # 撤 borrow
        self.assertEqual(len(p.borrowed_slots), 1)
        s.undo()                           # 撤 borrow
        self.assertEqual(p.borrowed_slots, before_extras)


class TestHistoryLabel(unittest.TestCase):
    """history_top_label 给 UI 用的提示。"""

    def test_no_history_empty_label(self):
        p = _make_parent()
        self.assertEqual(p.history_top_label(), "")

    def test_label_complete(self):
        p = _make_parent()
        s = PlanScheduler(p)
        s.complete_today_slot(0)           # 归档 +1
        self.assertIn("完成", p.history_top_label())

    def test_label_borrow(self):
        p = _make_parent()
        s = PlanScheduler(p)
        s.borrow_next()
        self.assertIn("额外轮", p.history_top_label())

    def test_label_return(self):
        p = _make_parent()
        s = PlanScheduler(p)
        s.borrow_next()
        s.return_last_borrowed()
        self.assertIn("退回", p.history_top_label())


class TestOldApiPreserved(unittest.TestCase):
    """老 API 的语义保持 v0.15 不变(给老测试/旧代码用)。"""

    def test_can_undo_complete_only_when_archived_today(self):
        p = _make_parent()
        s = PlanScheduler(p)
        self.assertFalse(s.can_undo_complete())
        # 手动改 archived 但 archived_base 跟着 consumed 后移 → done_today 仍为空
        # 模拟「今天完成了 1 条」
        p.archived_base = 0
        p.archived.append("A")
        self.assertTrue(s.can_undo_complete())
        # 但 archived_base 推到末尾(模拟切天) → done_today 空 → 不能 undo
        p.archived_base = len(p.archived)
        self.assertFalse(s.can_undo_complete())

    def test_undo_complete_does_not_touch_history_stack(self):
        """老 undo_complete 直接改归档/inplace_done/notes,不动 _history/_redo。"""
        p = _make_parent()
        s = PlanScheduler(p)
        p.archived_base = 0
        p.archived.append("A")
        self.assertFalse(p.can_undo())    # 老 API 不污染 history
        s.undo_complete()
        self.assertFalse(p.can_undo())
        self.assertFalse(p.can_redo())


class TestIsolatedPerParent(unittest.TestCase):
    """history 是绑在 ParentPlan 对象上的,不同分类之间不互相污染。"""

    def test_two_parents_have_independent_history(self):
        pa = _make_parent(plans=["1","2","3","4","5","6"])
        pb = _make_parent(plans=["X","Y","Z","W","V","U"])
        sa = PlanScheduler(pa)
        sb = PlanScheduler(pb)
        sa.borrow_next()
        sb.complete_today_slot(0)
        # pa 只能 undo borrow,pb 只能 undo complete
        sa.undo()
        self.assertEqual(pa.borrowed_slots, [])
        self.assertFalse(pa.can_undo())
        self.assertTrue(pa.can_redo())     # pa 的 redo 是 sa 撤掉的 borrow 操作
        sb.undo()
        self.assertEqual(pb.archived, [])
        self.assertFalse(pb.can_undo())
        # 两个 parent 的 history/redo 互不污染 —— 撤 pa 不影响 pb 的 stack
        self.assertEqual(pb.can_redo(), True)
        self.assertEqual(pa.can_redo(), True)


if __name__ == "__main__":
    unittest.main(verbosity=2)
