"""
RollingPlan v0.9 「完成并滚动」测试（重写 v0.8 的语义）

v0.8 的错误行为：点 早1 的「完成」→ 去借第二天同名的早4，导致
  - 早 = 4（第二天的计划滚进了今天）
  - 4 同时出现在第1天和第2天
  - 再点一次几乎没反应，但背地里又借了一条

v0.9 的正确行为：点 早1 的「完成」→ 1 归档（从队列里拿走），
  后面的整体上滚一格 → 早2 中3 晚4；第2天跟着变成 5/6/7（不重复、不丢）

覆盖：
- 完成后队列上滚（早/中/晚 全部上移；从后面顺位补一格）
- 第2天跟着上移，不出现重复项
- 完成中间那一格
- 额外轮：行满时留在额外轮，有空行时先顶上来
- 额外轮不带时段名（时段只是当天承装的栏位）
- 撤销完成 / 切天后不能再撤 → 退回降级为退额外轮
- 进度随完成 +1
- 归档不影响 plans 原文；to_dict/from_dict round-trip
- v0.8 旧存档迁移（completed_today 的 slot 序号 → 计划内容）
- reset_progress 清零
- 切天：consumed / archived_base 正确步进
- UI：✓ 完成按钮、点完 row 内容上滚、↶ 撤销完成 文案
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
from rollingplan import PlanData, PlanExecutor, ParentPlan, PlanScheduler

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


def make_data(plan_count=9, day_slots=("早", "中", "晚")):
    """默认：早/中/晚 ×1 = 3 格/天，任务1..9 = 3 天"""
    d = PlanData()
    p = ParentPlan(name="学习")
    p.plans = [f"任务{i+1}" for i in range(plan_count)]
    p.time_slots = [{"name": n, "count": 1} for n in day_slots]
    p.start_date = QDate(2026, 9, 15)
    p.current_day = 0
    p.borrowed_slots = []
    d.parents = [p]
    return d


def rows_of(s, day):
    return [(n, p) for n, p in s.get_day_plans(day)]


# ============== 核心：队列上滚 ==============

def test_complete_rolls_next_plan_up():
    """点 早1 完成 → 早2 中3 晚4（整条队列上移一格）"""
    print("\n=== test_complete_rolls_next_plan_up ===")
    d = make_data()
    s = PlanScheduler(d.parents[0])
    assert_eq(rows_of(s, 0), [("早", "任务1"), ("中", "任务2"), ("晚", "任务3")], "初始 早1 中2 晚3")

    s.complete_today_slot(0)
    assert_eq(rows_of(s, 0),
              [("早", "任务2"), ("中", "任务3"), ("晚", "任务4")],
              "完成后 早2 中3 晚4（从后面顺位补上，不是借第二天的早）")
    assert_true(s.get_day_plans(0)[0][1] != "任务4" or s.get_day_plans(0)[2][1] == "任务4",
                "任务4 出现在「晚」，不是出现在「早」")


def test_next_day_shifts_too_no_duplicate():
    """第2天跟着上移：不重复出现任务4"""
    print("\n=== test_next_day_shifts_too_no_duplicate ===")
    d = make_data()
    s = PlanScheduler(d.parents[0])
    s.complete_today_slot(0)
    assert_eq(rows_of(s, 1),
              [("早", "任务5"), ("中", "任务6"), ("晚", "任务7")],
              "第2天 = 5/6/7（任务4 已经在第1天用掉了）")
    # 全表检查：任务4 只出现一次
    all_plans = []
    for day in range(3):
        all_plans += [p for _, p in s.get_day_plans(day) if p]
    assert_eq(all_plans.count("任务4"), 1, "任务4 全表只出现 1 次")
    assert_true("任务1" not in all_plans, "任务1 已归档，不再出现")


def test_complete_middle_slot():
    """完成中间那一格：早1 中3 晚4"""
    print("\n=== test_complete_middle_slot ===")
    d = make_data()
    s = PlanScheduler(d.parents[0])
    s.complete_today_slot(1)  # 中=任务2
    assert_eq(rows_of(s, 0),
              [("早", "任务1"), ("中", "任务3"), ("晚", "任务4")],
              "完成中2 → 早1 中3 晚4")


def test_complete_all_rows_keeps_rolling():
    """连续完成：一格一格往下滚"""
    print("\n=== test_complete_all_rows_keeps_rolling ===")
    d = make_data()
    s = PlanScheduler(d.parents[0])
    s.complete_today_slot(0)   # 任务1 归档
    assert_eq(rows_of(s, 0)[0][1], "任务2", "第 1 次完成后 早=任务2")
    s.complete_today_slot(0)   # 任务2 归档
    assert_eq(rows_of(s, 0), [("早", "任务3"), ("中", "任务4"), ("晚", "任务5")],
              "第 2 次完成后 早3 中4 晚5")
    s.complete_today_slot(0)
    assert_eq(rows_of(s, 0), [("早", "任务4"), ("中", "任务5"), ("晚", "任务6")],
              "第 3 次完成后 早4 中5 晚6")
    assert_eq(s.done_today(), ["任务1", "任务2", "任务3"], "今天完成 3 条")
    assert_eq(s.total_done(), 3, "累计归档 3 条")


def test_plan_count_exhausted_shows_empty():
    """计划用完 → 行显示 None"""
    print("\n=== test_plan_count_exhausted_shows_empty ===")
    d = make_data(plan_count=3)  # 只有 1 天
    s = PlanScheduler(d.parents[0])
    assert_eq(s.can_complete_today_slot(0), True, "有计划 → 能完成")
    s.complete_today_slot(0)
    assert_eq(rows_of(s, 0), [("早", "任务2"), ("中", "任务3"), ("晚", None)],
              "用完最后一格 → 晚 = None")
    s.complete_today_slot(0)
    s.complete_today_slot(0)
    assert_eq(rows_of(s, 0), [("早", None), ("中", None), ("晚", None)], "全空")
    assert_eq(s.can_complete_today_slot(0), False, "全空 → 不能完成")
    assert_true(s.all_consumed(), "all_consumed() = True")


def test_archive_keeps_master_plans():
    """归档只影响队列，不动 plans 原文"""
    print("\n=== test_archive_keeps_master_plans ===")
    d = make_data()
    p = d.parents[0]
    s = PlanScheduler(p)
    s.complete_today_slot(0)
    assert_eq(p.plans[0], "任务1", "plans[0] 原文保留")
    assert_eq(p.archived, ["任务1"], "archived = [任务1]")
    assert_true("任务1" not in s.pending(), "归档的不在队列里")


# ============== 额外轮 ==============

def test_extra_stays_when_rows_full():
    """行是满的 → 额外轮留在额外轮区"""
    print("\n=== test_extra_stays_when_rows_full ===")
    d = make_data()
    s = PlanScheduler(d.parents[0])
    assert_true(s.borrow_next(), "加一个成功")
    assert_eq(s.extra_plans(), ["任务4"], "额外轮 = [任务4]（下一个未安排的）")
    st = s.today_state()
    assert_eq(st["promoted"], [], "行是满的 → 没有顶进日内的")
    assert_eq(st["extra_left"], ["任务4"], "留在额外轮区")
    assert_eq([p for _, p in st["rows"]], ["任务1", "任务2", "任务3"], "日内行不受影响")


def test_extra_rolls_into_freed_row():
    """完成一格后，额外轮那条先顶上（排在后面的顺位之前）"""
    print("\n=== test_extra_rolls_into_freed_row ===")
    d = make_data()
    s = PlanScheduler(d.parents[0])
    s.borrow_next()            # 额外轮 = [任务4]
    s.complete_today_slot(0)   # 任务1 归档 → 空出一格
    st = s.today_state()
    assert_eq([p for _, p in st["rows"]], ["任务2", "任务3", "任务4"],
              "额外轮的任务4 顶进「晚」")
    assert_eq(st["promoted"], ["任务4"], "promoted = [任务4]")
    assert_eq(st["extra_left"], [], "额外轮区空了")


def test_extra_rolls_into_rows_in_order():
    """额外轮有多条时，随着前面的完成一条条滚上今天的行"""
    print("\n=== test_extra_rolls_into_rows_in_order ===")
    d = make_data()
    s = PlanScheduler(d.parents[0])
    s.borrow_next()  # 任务4
    s.borrow_next()  # 任务5
    s.complete_today_slot(0)  # 任务1 归档 → 空 1 格
    st = s.today_state()
    assert_eq([p for _, p in st["rows"]], ["任务2", "任务3", "任务4"], "任务4 先滚上来")
    assert_eq(st["promoted"], ["任务4"], "任务4 已进今天的行")
    assert_eq(st["extra_left"], ["任务5"], "任务5 还在额外轮")
    s.complete_today_slot(0)  # 任务2 归档 → 再空 1 格
    st = s.today_state()
    assert_eq([p for _, p in st["rows"]], ["任务3", "任务4", "任务5"], "任务5 接着滚上来")
    assert_eq(st["extra_left"], [], "额外轮区空了")
    assert_eq(rows_of(s, 1), [("早", "任务6"), ("中", "任务7"), ("晚", "任务8")],
              "第2天从任务6 开始（没丢任务，也没重复）")


def test_complete_promoted_extra_removes_it():
    """完成的正是额外轮顶上来的那条 → 它从额外轮里消失"""
    print("\n=== test_complete_promoted_extra_removes_it ===")
    d = make_data()
    p = d.parents[0]
    s = PlanScheduler(p)
    s.borrow_next()           # 任务4
    s.complete_today_slot(0)  # 任务1 归档 → 任务4 顶到「晚」
    s.complete_today_slot(2)  # 完成「晚」= 任务4
    assert_eq(p.archived, ["任务1", "任务4"], "任务4 也归档了")
    assert_eq(p.borrowed_slots, [], "额外轮里那条已移除")
    assert_eq(s.pending().count("任务4"), 0, "队列里不再有任务4")


# ============== 撤销 / 进度 / 切天 ==============

def test_undo_complete():
    """撤销完成：放回队列原位"""
    print("\n=== test_undo_complete ===")
    d = make_data()
    p = d.parents[0]
    s = PlanScheduler(p)
    assert_eq(s.can_undo_complete(), False, "还没完成 → 不能撤")
    s.complete_today_slot(0)
    assert_eq(s.can_undo_complete(), True, "完成过 → 能撤")
    assert_true(s.undo_complete(), "撤销成功")
    assert_eq(p.archived, [], "archived 清空")
    assert_eq(rows_of(s, 0), [("早", "任务1"), ("中", "任务2"), ("晚", "任务3")], "回到原样")


def test_undo_only_today():
    """切天后不能再撤销昨天的完成 → 退回降级为退额外轮"""
    print("\n=== test_undo_only_today ===")
    d = make_data()
    p = d.parents[0]
    s = PlanScheduler(p)
    s.complete_today_slot(0)
    # 模拟 on_next_day
    p.consumed += s.today_state()["queue_used"]
    p.archived_base = len(p.archived)
    p.current_day = 1
    assert_eq(s.can_undo_complete(), False, "昨天的完成不能撤")
    assert_true(s.total_done() == 1, "累计归档仍然记着 1 条")
    assert_eq(rows_of(s, 1), [("早", "任务5"), ("中", "任务6"), ("晚", "任务7")],
              "切天不重复、不丢（任务4 在第1天用过了）")


def test_progress_grows_on_complete():
    """进度随完成 +1"""
    print("\n=== test_progress_grows_on_complete ===")
    d = make_data()
    s = PlanScheduler(d.parents[0])
    assert_eq(s.get_progress(), (3, 9), "初始 3 / 9")
    s.complete_today_slot(0)
    assert_eq(s.get_progress(), (4, 9), "完成 1 条 → 4 / 9")
    s.complete_today_slot(0)
    assert_eq(s.get_progress(), (5, 9), "完成 2 条 → 5 / 9")


def test_next_day_advances_queue():
    """切天：consumed / archived_base 正确步进"""
    print("\n=== test_next_day_advances_queue ===")
    d = make_data()
    p = d.parents[0]
    s = PlanScheduler(p)
    s.complete_today_slot(0)                 # 任务1 归档 → 今天显示 2,3,4
    assert_eq(s.today_state()["queue_used"], 3, "今天从队列取走 3 条")
    p.consumed += s.today_state()["queue_used"]
    p.archived_base = len(p.archived)
    p.borrowed_slots = []
    p.current_day = 1
    p.normalize()
    assert_eq(p.consumed, 3, "consumed = 3")
    assert_eq(p.archived_base, 1, "archived_base = 1")
    assert_eq(s.done_today(), [], "新的一天：今天已完成 = 空")
    assert_eq(rows_of(s, 1), [("早", "任务5"), ("中", "任务6"), ("晚", "任务7")],
              "第2天 = 5/6/7")


def test_extra_rolls_up_not_lost_or_duplicated():
    """额外轮滚上来之后，切天不丢也不重复"""
    print("\n=== test_extra_rolls_up_not_lost_or_duplicated ===")
    d = make_data()
    p = d.parents[0]
    s = PlanScheduler(p)
    s.borrow_next()            # 任务4 进额外轮
    s.complete_today_slot(0)   # 任务1 归档 → 任务4 滚上今天的行
    st = s.today_state()
    assert_eq([x for _, x in st["rows"]], ["任务2", "任务3", "任务4"], "任务4 滚上来了")
    assert_eq(st["extra_left"], [], "额外轮区不再重复显示 任务4")
    assert_eq(st["queue_used"], 3, "今天从队列取走 3 条（2、3、4）")

    p.consumed += st["queue_used"]
    p.archived_base = len(p.archived)
    p.borrowed_slots = []
    p.current_day = 1
    p.normalize()
    assert_eq(rows_of(s, 1), [("早", "任务5"), ("中", "任务6"), ("晚", "任务7")],
              "第2天 = 5/6/7（任务4 今天已经用掉了）")
    seen = []
    for day in range(1, 3):
        seen += [x for _, x in s.get_day_plans(day) if x]
    assert_eq(sorted(seen), ["任务5", "任务6", "任务7", "任务8", "任务9"],
              "剩下的计划一条不少")


# ============== 持久化 ==============

def test_to_from_dict_roundtrip():
    print("\n=== test_to_from_dict_roundtrip ===")
    d = make_data()
    p = d.parents[0]
    s = PlanScheduler(p)
    s.complete_today_slot(0)
    data = p.to_dict()
    for key in ("archived", "archived_base", "consumed"):
        assert_true(key in data, f"to_dict 含 {key}")
    p2 = ParentPlan()
    p2.from_dict(data)
    assert_eq(p2.archived, ["任务1"], "archived round-trip")
    assert_eq(p2.consumed, 0, "consumed round-trip")
    assert_eq(PlanScheduler(p2).get_day_plans(0)[0], ("早", "任务2"), "恢复后显示 任务2")


def test_legacy_completed_today_migration():
    """v0.8 旧存档：completed_today 是 slot 序号 → 迁成计划内容"""
    print("\n=== test_legacy_completed_today_migration ===")
    legacy = {
        "name": "旧档",
        "plans": [f"任务{i+1}" for i in range(9)],
        "time_slots": [{"name": "早", "count": 1}, {"name": "中", "count": 1}, {"name": "晚", "count": 1}],
        "start_date": "2026-09-15",
        "current_day": 0,
        "borrowed_slots": [],
        "completed_today": [0],
    }
    p = ParentPlan()
    p.from_dict(legacy)
    assert_eq(p.archived, ["任务1"], "completed_today=[0] → archived=[任务1]")
    assert_eq(PlanScheduler(p).get_day_plans(0)[0], ("早", "任务2"), "旧档显示任务2（已上滚）")


def test_reset_progress_clears_scroll_state():
    print("\n=== test_reset_progress_clears_scroll_state ===")
    d = make_data()
    p = d.parents[0]
    s = PlanScheduler(p)
    s.borrow_next()
    s.complete_today_slot(0)
    p.reset_progress()
    assert_eq(p.archived, [], "archived 清空")
    assert_eq(p.archived_base, 0, "archived_base 归零")
    assert_eq(p.consumed, 0, "consumed 归零")
    assert_eq(p.borrowed_slots, [], "额外轮清空")
    assert_eq(rows_of(PlanScheduler(p), 0)[0], ("早", "任务1"), "回到第一天原样")


# ============== UI ==============

def find_buttons(ex, text):
    return [b for b in ex.findChildren(rollingplan.QPushButton) if b.text() == text]


def test_executor_renders_complete_buttons():
    print("\n=== test_executor_renders_complete_buttons ===")
    d = make_data()
    ex = PlanExecutor(d, lambda: None)
    ex.show()
    app.processEvents()
    assert_eq(len(find_buttons(ex, "✓ 完成")), 3, "3 格各有 1 个 ✓ 完成")
    assert_eq(len(find_buttons(ex, "⤴ 退回")), 1, "退回按钮在（今天还没完成过）")
    assert_eq(len(find_buttons(ex, "↶ 撤销完成")), 0, "还没完成 → 没有撤销文案")


def test_executor_complete_rolls_row_and_shows_undo():
    print("\n=== test_executor_complete_rolls_row_and_shows_undo ===")
    d = make_data()
    ex = PlanExecutor(d, lambda: None)
    ex.show()
    app.processEvents()

    def day_texts():
        out = []
        for i in range(ex.day_layout.count()):
            item = ex.day_layout.itemAt(i)
            if item and item.widget():
                out += [c.text() for c in item.widget().findChildren(rollingplan.QLabel)]
        return out

    before = day_texts()
    assert_true(any("任务3" in t for t in before), "初始日内含 任务3")
    find_buttons(ex, "✓ 完成")[0].click()
    app.processEvents()

    after = day_texts()
    assert_true(any("任务4" in t for t in after), "完成早1 后 任务4 滚进日内")
    assert_true(not any(t.strip().endswith("任务1") for t in after), "任务1 不再显示")
    assert_true(any("早" == t.strip("  :") for t in after), "时段名还在（栏位不变）")
    assert_eq(len(find_buttons(ex, "↶ 撤销完成")), 1, "完成后退回按钮变成 ↶ 撤销完成")
    assert_true(any("任务1" in t for t in [ex.done_label.text()]), "已完成区显示 任务1")


def test_executor_extra_row_has_no_slot_name():
    """额外轮的行不带第二天的时段名"""
    print("\n=== test_executor_extra_row_has_no_slot_name ===")
    d = make_data()
    ex = PlanExecutor(d, lambda: None)
    ex.show()
    app.processEvents()
    ex.scheduler.borrow_next()   # 任务4 进额外轮
    ex.refresh()
    app.processEvents()
    extra_texts = []
    for i in range(ex.extra_layout.count()):
        item = ex.extra_layout.itemAt(i)
        if item and item.widget():
            extra_texts += [c.text() for c in item.widget().findChildren(rollingplan.QLabel)]
    assert_true(any("任务4" in t for t in extra_texts), "额外轮显示 任务4")
    assert_true(not any("早" in t for t in extra_texts), "额外轮不带时段名（没有 早/中/晚）")


def test_executor_return_undoes_complete():
    """退回按钮优先撤销完成"""
    print("\n=== test_executor_return_undoes_complete ===")
    d = make_data()
    p = d.parents[0]
    ex = PlanExecutor(d, lambda: None)
    ex.show()
    app.processEvents()
    find_buttons(ex, "✓ 完成")[0].click()
    app.processEvents()
    assert_eq(p.archived, ["任务1"], "先完成 任务1")
    find_buttons(ex, "↶ 撤销完成")[0].click()
    app.processEvents()
    assert_eq(p.archived, [], "撤销后归档清空")
    assert_eq(ex.scheduler.get_day_plans(0)[0], ("早", "任务1"), "任务1 回到「早」")


def test_available_pick_plans():
    """添加指定：候选是「后面还没安排的计划」，按队列顺序，去重"""
    print("\n=== test_available_pick_plans ===")
    d = make_data()
    s = PlanScheduler(d.parents[0])
    assert_eq(s.available_pick_plans(),
              ["任务4", "任务5", "任务6", "任务7", "任务8", "任务9"],
              "候选 = 第2天起的计划（今天的三条不算）")
    s.borrow_plan("任务5")
    assert_eq(s.available_pick_plans(),
              ["任务4", "任务6", "任务7", "任务8", "任务9"],
              "挑走一条 → 候选里不再有它（任务5）")


def test_borrow_plan_not_head():
    """可以挑后面的一条（不是队首）：它进额外轮，且不乱序、不丢"""
    print("\n=== test_borrow_plan_not_head ===")
    d = make_data()
    p = d.parents[0]
    s = PlanScheduler(p)
    assert_true(s.borrow_plan("任务7"), "挑中第3天的任务7")
    assert_eq(p.borrowed_slots[0][1], "任务7", "额外轮里是任务7")
    st = s.today_state()
    assert_eq([x for _, x in st["rows"]], ["任务1", "任务2", "任务3"], "今天的行不受影响")
    assert_eq(st["extra_left"], ["任务7"], "任务7 先在额外轮待着")
    # 把它前面的都完成掉，它会自然滚上来
    for _ in range(6):
        s.complete_today_slot(0)
    st = s.today_state()
    assert_eq([x for _, x in st["rows"]], ["任务7", "任务8", "任务9"], "任务7 滚到今天第一格")
    assert_eq(st["extra_left"], [], "滚上来后不再重复显示在额外轮")


def test_borrow_plan_rejects_unknown_or_today():
    print("\n=== test_borrow_plan_rejects_unknown_or_today ===")
    d = make_data()
    s = PlanScheduler(d.parents[0])
    assert_eq(s.borrow_plan("任务1"), False, "今天的任务1 不能「提前安排」")
    assert_eq(s.borrow_plan("不存在"), False, "不存在的计划 → False")
    assert_eq(s.borrow_plan("任务4"), True, "后面的任务4 可以")


def test_executor_add_specific_picks_plan():
    """UI：添加指定 → 选一条计划 → 进额外轮（不带时段名）"""
    print("\n=== test_executor_add_specific_picks_plan ===")
    d = make_data()
    ex = PlanExecutor(d, lambda: None)
    ex.show()
    app.processEvents()
    original = rollingplan.QInputDialog.getItem
    try:
        rollingplan.QInputDialog.getItem = staticmethod(lambda *a, **k: ("任务6", True))
        ex.on_add_specific()
        app.processEvents()
    finally:
        rollingplan.QInputDialog.getItem = original
    assert_eq(d.parents[0].borrowed_slots[0][1], "任务6", "挑中的任务6 进了额外轮")
    extra_texts = []
    for i in range(ex.extra_layout.count()):
        item = ex.extra_layout.itemAt(i)
        if item and item.widget():
            extra_texts += [c.text() for c in item.widget().findChildren(rollingplan.QLabel)]
    assert_true(any("任务6" in t for t in extra_texts), "额外轮显示 任务6")
    assert_true(not any("早" in t or "中" in t or "晚" in t for t in extra_texts),
                "额外轮不带时段名")


def main():
    test_complete_rolls_next_plan_up()
    test_next_day_shifts_too_no_duplicate()
    test_complete_middle_slot()
    test_complete_all_rows_keeps_rolling()
    test_plan_count_exhausted_shows_empty()
    test_archive_keeps_master_plans()
    test_extra_stays_when_rows_full()
    test_extra_rolls_into_freed_row()
    test_extra_rolls_into_rows_in_order()
    test_complete_promoted_extra_removes_it()
    test_undo_complete()
    test_undo_only_today()
    test_progress_grows_on_complete()
    test_next_day_advances_queue()
    test_extra_rolls_up_not_lost_or_duplicated()
    test_to_from_dict_roundtrip()
    test_legacy_completed_today_migration()
    test_reset_progress_clears_scroll_state()
    test_executor_renders_complete_buttons()
    test_executor_complete_rolls_row_and_shows_undo()
    test_executor_extra_row_has_no_slot_name()
    test_executor_return_undoes_complete()
    test_available_pick_plans()
    test_borrow_plan_not_head()
    test_borrow_plan_rejects_unknown_or_today()
    test_executor_add_specific_picks_plan()

    print()
    print(f"PASS={PASS_COUNT}  FAIL={FAIL_COUNT}")
    if FAIL_COUNT == 0:
        print("=== ALL TESTS PASSED ===")
        sys.exit(0)
    print("=== TESTS FAILED ===")
    sys.exit(1)


if __name__ == "__main__":
    main()
