"""
RollingPlan v0.9~v0.13 队列模型的边界回归测试

现状 test_scroll_v11.py 覆盖了主路径(完成/滚动/固定/拦截/额外轮),
但以下边界没有专门测试,任何对 today_state() / complete_today_slot() /
borrow_plan() / next_day() 的修改都应该让这些断言持续通过:

  - 切天后 borrowed_slots 是否真的清空、里面的 plan 是否回到候选队列
  - archived_base 在每次切天后是否被重置,不同日期的"今天已完成"互不污染
  - borrow_plan 提前拉一条跨天计划:它如何滚进新一天的行上
  - 多分类隔离:在 ParentPlan A 上完成/借走的操作不影响 ParentPlan B 的状态
    (STATE.md "v0.4 多分类独立"是写过的契约,但 scroll 套件没回归过)

运行:QT_QPA_PLATFORM=offscreen python test_regression_v13.py
"""

import os
import sys

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import QDate

app = QApplication.instance() or QApplication(sys.argv)

from rollingplan import PlanData, PlanScheduler, ParentPlan

PASS_COUNT = 0
FAIL_COUNT = 0


def assert_eq(a, b, label):
    global PASS_COUNT, FAIL_COUNT
    if a == b:
        PASS_COUNT += 1
        print(f"  PASS [{label}]")
    else:
        FAIL_COUNT += 1
        print(f"  FAIL [{label}]")
        print(f"    expected: {b!r}")
        print(f"    actual:   {a!r}")


def assert_true(cond, label):
    global PASS_COUNT, FAIL_COUNT
    if cond:
        PASS_COUNT += 1
        print(f"  PASS [{label}]")
    else:
        FAIL_COUNT += 1
        print(f"  FAIL [{label}]")


def make_parent(name="学习", plan_count=9, slots=("早", "中", "晚")):
    p = ParentPlan(name=name)
    p.plans = [f"{name}-任务{i+1}" for i in range(plan_count)]
    p.time_slots = [{"name": n, "count": 1} for n in slots]
    p.start_date = QDate(2026, 9, 15)
    p.current_day = 0
    p.borrowed_slots = []
    return p


# ============== 1. 切天清空额外轮 ==============3

def test_next_day_clears_borrowed_promotes_to_new_day():
    """加 2 条额外安排 → 直接切天(没完成 day0 任何格)→
    borrowed_slots 清空(切天不保留),那 2 条被 promo 进新一天的行首两格
    (v0.9 语义:额外轮里没滚上今天行的,切天时优先占用新一天的前几格)。"""
    print("\n=== test_next_day_clears_borrowed_promotes_to_new_day ===")
    p = make_parent(plan_count=9)
    s = PlanScheduler(p)

    # 加 2 条: borrow_plan 用「计划名」(v0.9 入口)
    assert_true(s.borrow_plan(f"{p.name}-任务4"), "添加指定:任务4")
    assert_true(s.borrow_plan(f"{p.name}-任务5"), "添加指定:任务5")
    assert_eq(len(p.borrowed_slots), 2, "切天前 borrowed_slots=2")

    # 切天(模拟 on_next_day 那几行)
    st = s.today_state()
    p.current_day += 1
    p.consumed += st["queue_used"]
    p.archived_base = len(p.archived)
    p.borrowed_slots = []          # on_next_day 内会清空
    p.inplace_done = []
    p.slot_notes = []
    p.slot_fixed = []
    p.slot_blocked = []
    p.normalize()

    assert_eq(p.borrowed_slots, [], "切天后 borrowed_slots=[]")
    assert_eq(s.extra_plans(), [], "切天后 extra_plans()=[]")

    # 那 2 条 promo 进 day1 行首
    day1_plans = [pl for _, pl in s.today_state()["rows"]]
    assert_eq(day1_plans[0], f"{p.name}-任务4", "任务4 占据 day1 第 1 格")
    assert_eq(day1_plans[1], f"{p.name}-任务5", "任务5 占据 day1 第 2 格")


# ============== 2. archived_base 每天重置 ==============4

def test_archived_base_resets_each_day():
    """day 0 完成 2 条 → day 1 完成 2 条 → done_today() 在 day 0 / day 1 各只看自己;
    total_done 累计所有天的完成。"""
    print("\n=== test_archived_base_resets_each_day ===")
    p = make_parent(plan_count=9)
    s = PlanScheduler(p)

    # day 0: 完成早 + 中
    s.complete_today_slot(0)
    s.complete_today_slot(1)
    assert_eq(len(s.done_today()), 2, "day0 done_today=2")
    assert_eq(s.total_done(), 2, "day0 total_done=2")

    # 切天
    st = s.today_state()
    p.current_day += 1
    p.consumed += st["queue_used"]
    p.archived_base = len(p.archived)
    p.borrowed_slots = []
    p.inplace_done = []
    p.slot_notes = []
    p.slot_fixed = []
    p.slot_blocked = []
    p.normalize()

    # day 1: 完成早 + 中
    s.complete_today_slot(0)
    s.complete_today_slot(1)
    assert_eq(len(s.done_today()), 2, "day1 done_today 仍是 2(只看今天的)")
    assert_eq(s.total_done(), 4, "total_done=4(累计)")

    # 再切回一遍确认 base 没被污染
    st = s.today_state()
    p.current_day += 1
    p.consumed += st["queue_used"]
    p.archived_base = len(p.archived)
    p.borrowed_slots = []
    p.inplace_done = []
    p.slot_notes = []
    p.slot_fixed = []
    p.slot_blocked = []
    p.normalize()
    assert_eq(len(s.done_today()), 0, "day2 done_today=0(全新一天)")
    assert_eq(s.total_done(), 4, "total_done 不变")


# ============== 3. 跨天 borrow_plan → 新一天的 promo ==============5

def test_borrow_specific_promotes_to_next_day_rows():
    """borrow_plan 在 day 0 提前拉一条跨天计划 → day 0 全部完成 → 切天 →
    那条额外安排应出现在 day 1 的行上(作为 row[i].plan),不重复出现在额外轮区。"""
    print("\n=== test_borrow_specific_promotes_to_next_day_rows ===")
    p = make_parent(plan_count=9)
    s = PlanScheduler(p)

    # day 0 借任务5(原本在 day 2)
    assert_true(s.borrow_plan(f"{p.name}-任务5"), "day0 添加指定:任务5")
    st = s.today_state()
    day0_plans = [pl for _, pl in st["rows"]]
    # day 0 三格已满(1/2/3),任务5 进额外轮区,不挤进行(rows 是排满的就停)
    assert_true(f"{p.name}-任务5" not in day0_plans, "day0 行上不重复显示任务5")
    assert_true(f"{p.name}-任务5" in st["extra_left"], "任务5 留在额外轮(待 roll up)")
    assert_eq(len(st["rows"]), 3, "day0 仍是 3 行")

    # 完成 day 0 全部3 格
    s.complete_today_slot(0)
    s.complete_today_slot(1)
    s.complete_today_slot(2)

    # 切天
    st = s.today_state()
    p.current_day += 1
    p.consumed += st["queue_used"]
    p.archived_base = len(p.archived)
    p.borrowed_slots = []
    p.inplace_done = []
    p.slot_notes = []
    p.slot_fixed = []
    p.slot_blocked = []
    p.normalize()

    day1 = s.today_state()
    day1_plans = [pl for _, pl in day1["rows"]]
    # 任务5 应该已经在 day 1 的行里(被 promo)
    assert_true(f"{p.name}-任务5" in day1_plans, "切天后任务5 出现在 day1 行上")
    # 队列推进正确:day0 queued 3 条(day 0 的 1/2/3),任务5 占用 day1 第 1 格 → day1 第 2/3 格是 4/6
    assert_eq(day1_plans.count(None), 0, "day1 三格都填满(无空)")


# ============== 4. 多分类隔离 ==============6

def test_parents_are_isolated_under_v9_model():
    """在 ParentPlan A 上完成/借走的操作,绝不能影响 ParentPlan B 的
    archived / consumed / borrowed_slots / current_day —— 即便两者都用
    同一个 PlanScheduler 类。"""
    print("\n=== test_parents_are_isolated_under_v9_model ===")
    pa = make_parent(name="学习", plan_count=9)
    pb = make_parent(name="健身", plan_count=9)
    d = PlanData()
    d.parents = [pa, pb]
    d.current_parent_idx = 0

    sa = PlanScheduler(pa)
    sb = PlanScheduler(pb)

    # 在 A 上操作:完成 1 条 + 借 1 条
    sa.complete_today_slot(0)
    sb_pa_before = (pb.current_day, len(pb.archived), len(pb.borrowed_slots), pb.consumed)
    sa.borrow_plan("学习-任务4")
    assert_eq((pb.current_day, len(pb.archived), len(pb.borrowed_slots), pb.consumed),
              sb_pa_before, "在 A 上操作不影响 B 的核心状态")

    # 反向:在 B 上完成,B 不应污染 A
    sb.complete_today_slot(0)
    sb.borrow_plan("健身-任务4")
    assert_eq(pa.current_day, 0, "B 操作不影响 A 的 current_day")
    assert_eq(len(pa.archived), 1, "B 操作不影响 A 的 archived(仍是 1)")
    assert_eq(len(pa.borrowed_slots), 1, "B 操作不影响 A 的 borrowed_slots(仍是 1)")
    assert_true("健身-任务4" not in [e[1] for e in pa.borrowed_slots],
                "B 借的任务不会跑到 A 的 borrowed_slots 里")


# ============== 5. reset_progress 不污染其他分类(v0.4 契约再回归) ==============7

def test_reset_progress_does_not_touch_other_parents_v9_fields():
    """reset_progress 只清自己的字段;其他 ParentPlan 的 v0.9+ 字段(inplace_done /
    slot_notes / slot_fixed / slot_blocked / archived_base)也都不能被动到。"""
    print("\n=== test_reset_progress_does_not_touch_other_parents_v9_fields ===")
    pa = make_parent(name="学习")
    pb = make_parent(name="健身")

    # A 全部 v0.9 字段都"脏"
    pa.current_day = 2
    pa.archived = ["x", "y", "z"]
    pa.archived_base = 1
    pa.consumed = 3
    pa.borrowed_slots = [["早", "X", 0, 0]]
    pa.inplace_done = ["x", None, None]
    pa.slot_notes = [["x"], [], []]
    pa.slot_fixed = ["y", None, None]
    pa.slot_blocked = [None, None, None]

    # B 也"脏"但保留作对照
    pb.current_day = 5
    pb.archived = ["p", "q"]
    pb.archived_base = 1
    pb.consumed = 2
    pb.borrowed_slots = [["早", "P", 0, 0]]
    pb.inplace_done = ["p", None, None]
    pb.slot_notes = [["p"], [], []]
    pb.slot_fixed = ["q", None, None]
    pb.slot_blocked = [None, None, None]

    pa.reset_progress()

    # A 全清零
    assert_eq(pa.current_day, 0, "A current_day=0")
    assert_eq(pa.archived, [], "A archived=[]")
    assert_eq(pa.consumed, 0, "A consumed=0")
    assert_eq(pa.borrowed_slots, [], "A borrowed_slots=[]")
    assert_eq(pa.inplace_done, [], "A inplace_done=[]")
    assert_eq(pa.slot_notes, [], "A slot_notes=[]")
    assert_eq(pa.slot_fixed, [], "A slot_fixed=[]")
    assert_eq(pa.slot_blocked, [], "A slot_blocked=[]")

    # B 一切如旧
    assert_eq(pb.current_day, 5, "B current_day 不变")
    assert_eq(pb.archived, ["p", "q"], "B archived 不变")
    assert_eq(pb.archived_base, 1, "B archived_base 不变")
    assert_eq(pb.consumed, 2, "B consumed 不变")
    assert_eq(pb.borrowed_slots, [["早", "P", 0, 0]], "B borrowed_slots 不变")
    assert_eq(pb.inplace_done, ["p", None, None], "B inplace_done 不变")
    assert_eq(pb.slot_notes, [["p"], [], []], "B slot_notes 不变")
    assert_eq(pb.slot_fixed, ["q", None, None], "B slot_fixed 不变")
    assert_eq(pb.slot_blocked, [None, None, None], "B slot_blocked 不变")


def main():
    test_next_day_clears_borrowed_promotes_to_new_day()
    test_archived_base_resets_each_day()
    test_borrow_specific_promotes_to_next_day_rows()
    test_parents_are_isolated_under_v9_model()
    test_reset_progress_does_not_touch_other_parents_v9_fields()

    print()
    print(f"PASS={PASS_COUNT}  FAIL={FAIL_COUNT}")
    if FAIL_COUNT == 0:
        print("=== ALL TESTS PASSED ===")
        sys.exit(0)
    print("=== TESTS FAILED ===")
    sys.exit(1)


if __name__ == "__main__":
    main()