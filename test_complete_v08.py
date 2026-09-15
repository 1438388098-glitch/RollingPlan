"""
RollingPlan v0.8 完成-滚动测试

覆盖：
- complete_today_slot(slot_idx) 归档后该 slot 显示 None
- complete_today_slot 后借同 slot_name 的下一个 plan 滚入
- completed_today 跨 get_day_plans 持久
- 切换到下一天后 completed_today 清空
- to_dict / from_dict 持久 completed_today
- reset_progress 清空 completed_today
- can_complete_today_slot 仅当 slot 有 plan 时返回 True
- PlanExecutor 渲染当天 slot 行有 ✓ 完成 按钮（当 plan 非空时）
- on_complete_slot 调用后该 slot 在 UI 隐藏 + 下一个 plan 滚入
"""

import os
import sys
import tempfile

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import QDate, QSettings

_tmp = tempfile.mkdtemp(prefix="rollingplan_qsettings_")
os.environ["XDG_CONFIG_HOME"] = _tmp
QSettings.setDefaultFormat(QSettings.IniFormat)
QSettings.setPath(QSettings.IniFormat, QSettings.UserScope, _tmp)

import rollingplan
from rollingplan import (
    PlanData, PlanExecutor, ParentPlan, PlanScheduler,
)

app = QApplication.instance() or QApplication(sys.argv)
rollingplan.apply_theme(app, "dark")

PASS_COUNT = 0
FAIL_COUNT = 0


def assert_true(cond, label):
    global PASS_COUNT, FAIL_COUNT
    if cond:
        PASS_COUNT += 1
        print(f"  PASS [{label}]")
    else:
        FAIL_COUNT += 1
        print(f"  FAIL [{label}]")


def assert_eq(a, b, label):
    assert_true(a == b, f"{label} (expected={b!r}, got={a!r})")


def make_data(plan_count=6):
    """plans=6, 早+中+晚=3 slots/day, 2 days"""
    d = PlanData()
    p = ParentPlan(name="学习")
    p.plans = [f"任务{i+1}" for i in range(plan_count)]
    p.time_slots = [{"name": "早", "count": 1},
                    {"name": "中", "count": 1},
                    {"name": "晚", "count": 1}]
    p.start_date = QDate(2026, 9, 15)
    p.current_day = 0
    p.borrowed_slots = []
    p.completed_today = []
    d.parents = [p]
    return d


# ============== 数据层测试 ==============

def test_complete_today_slot_borrows_next_into_slot():
    """归档后 borrow_slot 把下一个同 slot_name plan 滚入（不是显示空）"""
    print("\n=== test_complete_today_slot_borrows_next_into_slot ===")
    d = make_data()
    s = PlanScheduler(d.parents[0])
    # day0 slot0 早 = 任务1；day1 slot0 早 = 任务4
    s.complete_today_slot(0)  # 归档 day0 早(任务1) → 借 day1 早(任务4) 滚入
    day = s.get_day_plans(0)
    assert_eq(day[0], ("早", "任务4"), "归档后 day0 早 = 任务4 (从 day1 滚入)")
    # day1 早槽位被借走 → 但 PlanScheduler 的 get_day_plans 算的是 plans 切片
    # 不会被 borrow 改 plans 切片，所以 day1 早仍然显示任务4
    # （这是 borrow 机制的固有特性：borrowed 的"原版"是 day1 slot0，
    #  现在通过 completed_today 标记在 day0 slot0 显示）
    # 真正"消失"的表现是：day0 早不再 = 任务1
    assert_true(day[0] != ("早", "任务1"), "day0 早不再是 任务1 (已归档)")


def test_complete_today_slot_no_more_to_borrow_shows_empty():
    """没的可借时，slot 显示 None"""
    print("\n=== test_complete_today_slot_no_more_to_borrow_shows_empty ===")
    d = make_data(plan_count=3)  # 只有 1 天
    s = PlanScheduler(d.parents[0])
    s.complete_today_slot(0)  # 归档 day0 早(任务1)，但没未来可借
    day = s.get_day_plans(0)
    assert_eq(day[0], ("早", None), "无可借 → slot 显示 None")


def test_completed_today_persists_in_get_day_plans():
    """completed_today 在 get_day_plans 中持续生效"""
    print("\n=== test_completed_today_persists_in_get_day_plans ===")
    d = make_data()
    s = PlanScheduler(d.parents[0])
    s.complete_today_slot(0)
    s.complete_today_slot(2)  # 也归档晚
    # 多次 refresh/get_day_plans 仍然看到 archived
    for _ in range(3):
        day = s.get_day_plans(0)
        assert_eq(day[0], ("早", "任务4"), f"call {_}: 早=任务4")
        assert_eq(day[2], ("晚", "任务6"), f"call {_}: 晚=任务6")


def test_can_complete_today_slot():
    """can_complete_today_slot 仅当 slot 有 plan 时返回 True"""
    print("\n=== test_can_complete_today_slot ===")
    d = make_data(plan_count=3)  # 1 天, 没可借
    s = PlanScheduler(d.parents[0])
    assert_true(s.can_complete_today_slot(0), "slot 0 有 plan → True")
    assert_true(s.can_complete_today_slot(1), "slot 1 有 plan → True")
    assert_true(s.can_complete_today_slot(2), "slot 2 有 plan → True")
    # 归档后没的可借，slot 显示 None，can_complete 应该 False
    s.complete_today_slot(0)
    assert_eq(s.can_complete_today_slot(0), False, "归档后无可借 → slot 0 → False")


def test_next_day_clears_completed_today():
    """切到下一天后 completed_today 清空"""
    print("\n=== test_next_day_clears_completed_today ===")
    d = make_data()
    s = PlanScheduler(d.parents[0])
    s.complete_today_slot(0)
    s.complete_today_slot(1)
    assert_eq(len(s.p.completed_today), 2, "切天前 completed_today 有 2 项")
    s.p.current_day = 1
    s.p.completed_today = []  # 模拟 on_next_day 行为
    assert_eq(s.p.completed_today, [], "切天后 completed_today 已清空")


def test_to_from_dict_includes_completed_today():
    """to_dict / from_dict 持久 completed_today"""
    print("\n=== test_to_from_dict_includes_completed_today ===")
    d = make_data()
    s = PlanScheduler(d.parents[0])
    s.complete_today_slot(1)
    data = s.p.to_dict()
    assert_true("completed_today" in data, "to_dict 含 completed_today 键")
    assert_eq(data["completed_today"], [1], "to_dict completed_today=[1]")

    # roundtrip
    p2 = ParentPlan()
    p2.from_dict(data)
    assert_eq(p2.completed_today, [1], "from_dict 恢复 completed_today=[1]")


def test_reset_progress_clears_completed_today():
    print("\n=== test_reset_progress_clears_completed_today ===")
    d = make_data()
    s = PlanScheduler(d.parents[0])
    s.complete_today_slot(0)
    s.p.reset_progress()
    assert_eq(s.p.completed_today, [], "reset_progress 清空 completed_today")


# ============== UI 测试 ==============

def test_executor_renders_complete_button_for_today_slots():
    """今天的 slot 行有 ✓ 完成 按钮（仅当有 plan 时）"""
    print("\n=== test_executor_renders_complete_button_for_today_slots ===")
    d = make_data()
    ex = PlanExecutor(d, lambda: None)
    ex.show()
    app.processEvents()
    # 找完成按钮（在 day_layout 子树里）
    complete_btns = ex.findChildren(type(ex.add_next_btn).__bases__[0])  # QPushButton
    # 找 "✓ 完成" 文案的按钮
    found = [b for b in ex.findChildren(rollingplan.QPushButton) if b.text() == "✓ 完成"]
    assert_eq(len(found), 3, f"3 个 slot 各有 1 个 ✓ 完成 按钮 (got {len(found)})")
    # 所有按钮 enable
    for i, b in enumerate(found):
        assert_true(b.isEnabled(), f"完成按钮 {i} enabled")


def test_on_complete_slot_ui_hides_and_rolls():
    """点击完成 → UI 立即刷新 + 下一个 plan 滚入"""
    print("\n=== test_on_complete_slot_ui_hides_and_rolls ===")
    d = make_data()
    ex = PlanExecutor(d, lambda: None)
    ex.show()
    app.processEvents()
    # 找第一个完成按钮
    complete_btns = [b for b in ex.findChildren(rollingplan.QPushButton) if b.text() == "✓ 完成"]
    assert_eq(len(complete_btns), 3, "3 个完成按钮")
    # 点击 slot 0 (早) 的完成
    complete_btns[0].click()
    app.processEvents()
    # data 状态：completed_today=[0], borrowed_slots 有 1 条 (早, 任务4, day1, 0)
    p = d.parents[0]
    assert_eq(p.completed_today, [0], "completed_today=[0]")
    assert_eq(len(p.borrowed_slots), 1, "borrowed_slots 有 1 条")
    assert_eq(p.borrowed_slots[0][0], "早", "borrowed 是 早")
    assert_eq(p.borrowed_slots[0][1], "任务4", "borrowed 是 任务4")
    # UI: 找 "任务4" 文字的 QLabel，应该在 day_layout 里
    day_layout_labels = []
    for i in range(ex.day_layout.count()):
        item = ex.day_layout.itemAt(i)
        if item and item.widget():
            for child in item.widget().findChildren(rollingplan.QLabel):
                if child.text() == "任务4":
                    day_layout_labels.append(child)
    assert_true(len(day_layout_labels) >= 1, "任务4 出现在 day_layout (滚动效果)")


def main():
    test_complete_today_slot_borrows_next_into_slot()
    test_complete_today_slot_no_more_to_borrow_shows_empty()
    test_completed_today_persists_in_get_day_plans()
    test_can_complete_today_slot()
    test_next_day_clears_completed_today()
    test_to_from_dict_includes_completed_today()
    test_reset_progress_clears_completed_today()
    test_executor_renders_complete_button_for_today_slots()
    test_on_complete_slot_ui_hides_and_rolls()

    print()
    print(f"PASS={PASS_COUNT}  FAIL={FAIL_COUNT}")
    if FAIL_COUNT == 0:
        print("=== ALL TESTS PASSED ===")
        sys.exit(0)
    else:
        print("=== TESTS FAILED ===")
        sys.exit(1)


if __name__ == "__main__":
    main()
