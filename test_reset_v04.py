"""
RollingPlan v0.4 重置进度测试

覆盖：
- ParentPlan.reset_progress()：current_day=0, borrowed_slots=[]
- plans/time_slots/start_date 不变
- 多分类隔离：只重置当前分类，其他分类的进度不动
- 重置后 PlanScheduler 能正常工作（get_day_plans / borrow_next 都正常）

运行：QT_QPA_PLATFORM=offscreen python test_reset_v04.py
"""

import os
os.environ["QT_QPA_PLATFORM"] = "offscreen"

import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PyQt5.QtWidgets import QApplication
app = QApplication(sys.argv)

from PyQt5.QtCore import QDate
from rollingplan import PlanData, PlanScheduler, ParentPlan


PASS_COUNT = 0
FAIL_COUNT = 0


def assert_eq(actual, expected, label):
    global PASS_COUNT, FAIL_COUNT
    if actual == expected:
        PASS_COUNT += 1
        print(f"  PASS [{label}]")
    else:
        FAIL_COUNT += 1
        print(f"  FAIL [{label}]")
        print(f"    expected: {expected!r}")
        print(f"    actual:   {actual!r}")
        sys.exit(1)


def assert_true(cond, label):
    global PASS_COUNT, FAIL_COUNT
    if cond:
        PASS_COUNT += 1
        print(f"  PASS [{label}]")
    else:
        FAIL_COUNT += 1
        print(f"  FAIL [{label}]")
        sys.exit(1)


# ============== 测试 ==============

def make_progressed_parent():
    """构造一个已进度的 ParentPlan"""
    p = ParentPlan("已进度")
    p.time_slots = [{"name": "早", "count": 1}, {"name": "晚", "count": 1}]
    p.plans = ["A", "B", "C", "D", "E", "F"]
    p.start_date = QDate(2026, 9, 15)
    p.current_day = 1  # 已走到第 2 天，future = day2，可借 2 个
    s = PlanScheduler(p)
    s.borrow_slot("早")  # 借 day2 早
    s.borrow_slot("晚")  # 借 day2 晚
    return p


def test_reset_progress_basic():
    print("\n=== test_reset_progress_basic ===")
    p = make_progressed_parent()

    # 验证前置状态
    assert_eq(p.current_day, 1, "前置：current_day=1")
    assert_eq(len(p.borrowed_slots), 2, "前置：borrowed=2")

    p.reset_progress()

    assert_eq(p.current_day, 0, "重置后 current_day=0")
    assert_eq(p.borrowed_slots, [], "重置后 borrowed_slots=[]")


def test_reset_preserves_structure():
    print("\n=== test_reset_preserves_structure: plans/time_slots/start_date 不变 ===")
    p = make_progressed_parent()
    orig_plans = list(p.plans)
    orig_slots = list(p.time_slots)
    orig_date = QDate(p.start_date)  # QDate 是值类型，拷贝

    p.reset_progress()

    assert_eq(p.plans, orig_plans, "plans 不变")
    assert_eq(p.time_slots, orig_slots, "time_slots 不变")
    assert_eq(p.start_date, orig_date, "start_date 不变")


def test_reset_already_at_start():
    print("\n=== test_reset_already_at_start: 初始状态调 reset_progress 无副作用 ===")
    p = ParentPlan("初始")
    p.time_slots = [{"name": "早", "count": 1}]
    p.plans = ["X", "Y", "Z"]
    p.start_date = QDate(2026, 9, 15)
    p.current_day = 0
    # borrowed_slots 默认空

    p.reset_progress()
    assert_eq(p.current_day, 0, "保持 0")
    assert_eq(p.borrowed_slots, [], "保持空")


def test_reset_works_after_reset():
    print("\n=== test_reset_works_after_reset: 重置后能正常 borrow ===")
    p = make_progressed_parent()
    p.reset_progress()

    # 重置后应该能重新借
    s = PlanScheduler(p)
    assert_eq(s.borrow_slot("早"), True, "重置后能借早")
    assert_eq(s.borrow_slot("晚"), True, "重置后能借晚")
    assert_eq(len(p.borrowed_slots), 2, "borrowed 重新填充")
    assert_eq(s.can_borrow_next(), True, "还能继续借")


def test_reset_isolates_parents():
    print("\n=== test_reset_isolates_parents: 多分类只重置当前 ===")
    pd = PlanData()
    pd.add_parent("A")
    pd.add_parent("B")

    # 分类 A 已进度
    pa = pd.parents[0]
    pa.name = "A"
    pa.time_slots = [{"name": "早", "count": 1}]
    pa.plans = ["A1", "A2", "A3", "A4"]
    pa.start_date = QDate(2026, 9, 15)
    pa.current_day = 2
    PlanScheduler(pa).borrow_slot("早")

    # 分类 B 也已进度
    pb = pd.parents[1]
    pb.name = "B"
    pb.time_slots = [{"name": "早", "count": 1}]
    pb.plans = ["B1", "B2", "B3", "B4"]
    pb.start_date = QDate(2026, 9, 16)
    pb.current_day = 1
    PlanScheduler(pb).borrow_slot("早")

    # 前置
    assert_eq(pa.current_day, 2, "A 前置 day=2")
    assert_eq(pb.current_day, 1, "B 前置 day=1")
    assert_eq(len(pa.borrowed_slots), 1, "A 前置 borrowed=1")
    assert_eq(len(pb.borrowed_slots), 1, "B 前置 borrowed=1")

    # 重置 A
    pa.reset_progress()

    # A 重置，B 不动
    assert_eq(pa.current_day, 0, "A 重置后 day=0")
    assert_eq(pa.borrowed_slots, [], "A 重置后 borrowed=空")
    assert_eq(pb.current_day, 1, "B 不受影响 day=1")
    assert_eq(len(pb.borrowed_slots), 1, "B borrowed 不变")


def test_reset_then_to_dict_roundtrip():
    print("\n=== test_reset_then_to_dict_roundtrip: 重置后导出仍能 round-trip ===")
    p = make_progressed_parent()
    p.reset_progress()

    # to_dict / from_dict 应能正常处理重置后的状态
    pd = PlanData()
    pd.parents[0] = p
    raw = pd.to_dict()
    assert_eq(raw["parents"][0]["current_day"], 0, "导出 current_day=0")
    assert_eq(raw["parents"][0]["borrowed_slots"], [], "导出 borrowed=[]")
    assert_eq(raw["parents"][0]["plans"], ["A", "B", "C", "D", "E", "F"], "plans 保留")


def main():
    test_reset_progress_basic()
    test_reset_preserves_structure()
    test_reset_already_at_start()
    test_reset_works_after_reset()
    test_reset_isolates_parents()
    test_reset_then_to_dict_roundtrip()
    print(f"\n=== ALL TESTS PASSED ({PASS_COUNT} assertions) ===")


if __name__ == "__main__":
    main()
