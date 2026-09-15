"""
RollingPlan v0.2.1 健壮性测试
覆盖：
- 单母计划 + 借指定时间段
- 链式借（借完明天同名，自动借后天）
- 同时间段 count>1 时借的边界
- 多母计划独立
- 借过再退后能再借（v0.2.1 修复）
- available_borrow_names 去重（v0.2.1 修复）
- 借用期间改时间段被拒绝（v0.2.1 修复）
- 借出内容快照独立（v0.2.1 修复）

运行：python test_v2_2.py
"""

import os
os.environ["QT_QPA_PLATFORM"] = "offscreen"

import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PyQt5.QtWidgets import QApplication
app = QApplication(sys.argv)

from rollingplan import PlanData, PlanScheduler, ParentPlan
from PyQt5.QtCore import QDate


def assert_eq(actual, expected, label):
    if actual != expected:
        print(f"  FAIL [{label}]")
        print(f"    expected: {expected}")
        print(f"    actual:   {actual}")
        sys.exit(1)
    print(f"  PASS [{label}]")


def test_basic_borrow():
    print("\n=== test_basic_borrow: 单母计划 + 借指定时间段 ===")
    p = ParentPlan("test")
    p.time_slots = [{"name":"早","count":1}, {"name":"晚","count":1}]
    p.plans = [f"任务{i+1}" for i in range(6)]
    p.start_date = QDate.currentDate()
    p.current_day = 0
    s = PlanScheduler(p)

    assert_eq(s.borrow_slot("早"), True, "借早成功")
    assert_eq(p.borrowed_slots, [["早", "任务3", 1, 0]], "借到 day1 早")
    assert_eq(s.borrow_slot("晚"), True, "借晚成功")
    assert_eq(s.borrow_slot("早"), True, "借早成功(day2 早)")
    assert_eq(len(p.borrowed_slots), 3, "借出 3 条")


def test_chain_borrow():
    print("\n=== test_chain_borrow: 链式借 ===")
    p = ParentPlan("chain")
    p.time_slots = [{"name":"晚","count":1}]
    p.plans = [f"X{i+1}" for i in range(4)]
    p.current_day = 0
    s = PlanScheduler(p)

    s.borrow_slot("晚")  # day1 晚
    s.borrow_slot("晚")  # day2 晚
    s.borrow_slot("晚")  # day3 晚
    s.borrow_slot("晚")  # 应失败
    assert_eq(len(p.borrowed_slots), 3, "链式借到第三天截止")
    assert_eq(s.can_borrow_slot("晚"), False, "无法再借")


def test_borrow_return_reborrow():
    print("\n=== test_borrow_return_reborrow: 借过再退后能再借（v0.2.1 修复）===")
    p = ParentPlan("rerow")
    p.time_slots = [{"name":"早","count":1}]
    p.plans = ["A", "B", "C", "D"]
    p.current_day = 0
    s = PlanScheduler(p)

    s.borrow_slot("早")
    s.return_last_borrowed()
    assert_eq(s.can_borrow_slot("早"), True, "退回后仍可借")
    s.borrow_slot("早")
    assert_eq(len(p.borrowed_slots), 1, "再借成功")


def test_count_gt1():
    print("\\n=== test_count_gt1: 同时间段 count>1 借的边界 ===")
    # 场景 A: 6 plans, 早×2 + 晚×1 = 3 slots/day, 2 days
    # future = day1 only (day0 = current), day1 槽位: 早-0/早-1/晚
    p = ParentPlan("cnt2")
    p.time_slots = [{"name":"早","count":2}, {"name":"晚","count":1}]
    p.plans = [f"Y{i+1}" for i in range(6)]
    p.current_day = 0
    s = PlanScheduler(p)

    s.borrow_slot("早")  # day1 早-0 = Y4
    s.borrow_slot("早")  # day1 早-1 = Y5
    ok3 = s.borrow_slot("早")  # 没第 3 个早可借了（day1 只有 2 个早，day2 不存在）
    assert_eq(ok3, False, "6 plans：借第 3 次早失败（无 day2）")

    # 场景 B: 9 plans, 早×2 + 晚×1 = 3 slots/day, 3 days
    # future = day1 + day2，可借 4 个早
    p2 = ParentPlan("cnt2b")
    p2.time_slots = [{"name":"早","count":2}, {"name":"晚","count":1}]
    p2.plans = [f"Y{i+1}" for i in range(9)]
    p2.current_day = 0
    s2 = PlanScheduler(p2)

    s2.borrow_slot("早")  # day1 早-0
    s2.borrow_slot("早")  # day1 早-1
    ok3 = s2.borrow_slot("早")  # day2 早-0
    assert_eq(ok3, True, "9 plans：借第 3 次早借到 day2")
    assert_eq(len(p2.borrowed_slots), 3, "借出 3 条")


def test_multi_parent():
    print("\n=== test_multi_parent: 多母计划独立 ===")
    pd = PlanData()
    pd.add_parent("A")
    pd.add_parent("B")

    pa = ParentPlan("A")
    pa.time_slots = [{"name":"早","count":1}]
    pa.plans = ["A1", "A2", "A3", "A4"]
    pd.parents[0] = pa

    pb = ParentPlan("B")
    pb.time_slots = [{"name":"早","count":1}]
    pb.plans = ["B1", "B2", "B3", "B4"]
    pd.parents[1] = pb

    sa = PlanScheduler(pd.parents[0])
    sb = PlanScheduler(pd.parents[1])

    sa.borrow_slot("早")
    sa.borrow_slot("早")
    assert_eq(len(pd.parents[0].borrowed_slots), 2, "A 借了 2 个")
    assert_eq(len(pd.parents[1].borrowed_slots), 0, "B 没借")
    assert_eq(sb.can_borrow_slot("早"), True, "B 还能借")


def test_available_names_dedup():
    print("\n=== test_available_names_dedup: available_borrow_names 去重（v0.2.1 修复）===")
    p = ParentPlan("dedup")
    p.time_slots = [{"name":"早","count":3}]
    p.plans = [f"Z{i+1}" for i in range(6)]
    p.current_day = 0
    s = PlanScheduler(p)

    names = s.available_borrow_names()
    assert_eq(names, ["早"], "去重后只有 1 个 '早'")

    s.borrow_slot("早")
    s.borrow_slot("早")
    names2 = s.available_borrow_names()
    assert_eq(names2, ["早"], "借出后仍只 1 个 '早'")


def test_has_borrowed_blocks_slot_edit():
    print("\n=== test_has_borrowed_blocks_slot_edit: 借用期间改时间段被拒绝（v0.2.1 修复）===")
    pd = PlanData()
    pd.parents[0].time_slots = [{"name":"早","count":1}]
    pd.parents[0].plans = ["P1", "P2"]
    pd.parents[0].current_day = 0
    s = PlanScheduler(pd.parents[0])
    s.borrow_slot("早")

    assert_eq(pd.has_borrowed(), True, "has_borrowed=True")
    # 真实 UI 层会调 has_borrowed() 阻止 add_slot/edit_slot/del_slot
    # 这里只验证 has_borrowed 函数正确


def test_borrow_snapshot_independence():
    print("\\n=== test_borrow_snapshot_independence: 借出内容快照独立 ===")
    # 3 plans, 1 slot/day (早×1) = 3 days
    # current=day0=任务1, future=day1=任务2, day2=任务3
    # 借"早" → day1 早 = 任务2
    p = ParentPlan("snap")
    p.time_slots = [{"name":"早","count":1}]
    plans = ["原始任务1", "原始任务2", "原始任务3"]
    p.plans = plans
    p.current_day = 0
    s = PlanScheduler(p)

    s.borrow_slot("早")  # 借 day1 早 = "原始任务2"
    assert_eq(p.borrowed_slots[0][1], "原始任务2", "借出原始内容")

    # 修改原 plans（模拟用户编辑 day0 那个"原始任务1"）
    p.plans[0] = "改过的任务1"
    # 借出的快照应保持原值（指向 day1 的"原始任务2"，与 day0 无关）
    assert_eq(p.borrowed_slots[0][1], "原始任务2", "编辑原 plans 不影响借出快照")

    # 修改原 plans 的 day1 那个（索引 1）
    p.plans[1] = "改过的任务2"
    # 借出快照（Python str 不可变）应仍为 "原始任务2"
    assert_eq(p.borrowed_slots[0][1], "原始任务2", "编辑借出位置原 plans 也不影响快照")


def test_borrow_next_v03():
    """v0.3 新增：borrow_next 加一个（不分时段名）"""
    print("\\n=== test_borrow_next_v03: 加一个（v0.3 新增）===")
    # 9 plans, 早/中/晚 ×1 = 3 slots/day, 3 days
    # day0 (current): 早=任务1, 中=任务2, 晚=任务3
    # day1 (future): 早=任务4, 中=任务5, 晚=任务6
    # day2 (future): 早=任务7, 中=任务8, 晚=任务9
    p = ParentPlan("next")
    p.time_slots = [{"name":"早","count":1}, {"name":"中","count":1}, {"name":"晚","count":1}]
    p.plans = [f"任务{i+1}" for i in range(9)]
    p.current_day = 0
    s = PlanScheduler(p)

    # 加 1 个：future 最早位置 = day1 早 = 任务4
    assert_eq(s.borrow_next(), True, "加 1 成功")
    assert_eq(p.borrowed_slots[0], ["早", "任务4", 1, 0], "借到 day1 早-0 = 任务4")

    # 加 2 个：下一个未借 = day1 中 = 任务5
    assert_eq(s.borrow_next(), True, "加 2 成功")
    assert_eq(p.borrowed_slots[1], ["中", "任务5", 1, 1], "借到 day1 中 = 任务5")

    # 加 3 个：下一个未借 = day1 晚 = 任务6
    assert_eq(s.borrow_next(), True, "加 3 成功")
    assert_eq(p.borrowed_slots[2], ["晚", "任务6", 1, 2], "借到 day1 晚 = 任务6")

    # 加 4 个：下一个未借 = day2 早 = 任务7（不卡在 day1 的"晚"上）
    assert_eq(s.borrow_next(), True, "加 4 成功（跨天）")
    assert_eq(p.borrowed_slots[3], ["早", "任务7", 2, 0], "借到 day2 早-0 = 任务7")

    # can_borrow_next 应仍然 True（还剩 8/9 = 2 个）
    assert_eq(s.can_borrow_next(), True, "还能继续加")

    # 借光
    while s.borrow_next():
        pass
    assert_eq(s.can_borrow_next(), False, "借光后不能再加")
    assert_eq(len(p.borrowed_slots), 6, "总共借出 6 条（2 天 × 3 槽）")

    # 退回后能再借
    s.return_last_borrowed()
    assert_eq(s.can_borrow_next(), True, "退回后又能加")


def main():
    test_basic_borrow()
    test_chain_borrow()
    test_borrow_return_reborrow()
    test_count_gt1()
    test_multi_parent()
    test_available_names_dedup()
    test_has_borrowed_blocks_slot_edit()
    test_borrow_snapshot_independence()
    test_borrow_next_v03()
    print("\\n=== ALL TESTS PASSED ===")


if __name__ == "__main__":
    main()
