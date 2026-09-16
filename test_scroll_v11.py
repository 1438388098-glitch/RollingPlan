"""
RollingPlan v0.10 「仅完成 / 完成并滚动」测试

布局前提：早/中/晚 三格，子计划 1..9。时段只是「当天承装计划的栏位」。

v0.9 的两个问题（user 反馈后修正）：
  1. 「完成」只有一种行为：归档 + 上滚，而且腾出来的最后一格会把**第二天的计划**
     滚上来（早=2 中=3 晚=4）
  2. 没有办法「只标记完成、先不动列表」

v0.10 规则：
  - 每格两个按钮：「仅完成」= 标记完成（记进该时段的归档备注）、计划留在格里、不滚动
    「✓ 完成并滚动」= 归档 + 后面的整体上滚一格
  - 腾出来的最后一格**只由额外轮补**；额外轮为空就空着，绝不把第二天的计划滚上来
  - 「仅完成」过的格子之后再按「完成并滚动」= 解开这一格让它滚（归档与备注早已记过，不重复）
  - 撤销（退回按钮）对两种完成都有效

覆盖：
- 仅完成：不滚动、计划留在格里、备注记上、按钮该灰
- 完成并滚动：归档 + 上滚；最后一格不从第二天补；有额外轮时由额外轮补
- 「仅完成」→「完成并滚动」的接力
- 归档备注（每格各自记）
- 进度两条都 +1
- 撤销两种完成
- 切天：consumed / archived_base / 每格状态归零；不重复不丢
- 队列/额外轮/添加指定的既有行为不回归
- UI：两个按钮、灰掉、删除线、备注文字
"""

import os
import sys
import tempfile

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import QDate, QSettings, Qt
from PyQt5.QtTest import QTest

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
    return s.get_day_plans(day)


def plans_of(s, day):
    return [p for _, p in s.get_day_plans(day)]


# ============== 仅完成 ==============

def test_complete_only_does_not_scroll():
    """仅完成：计划留在格里、不滚动、备注记上"""
    print("\n=== test_complete_only_does_not_scroll ===")
    d = make_data()
    p = d.parents[0]
    s = PlanScheduler(p)
    assert_true(s.complete_only_slot(0), "仅完成成功")
    st = s.today_state()
    assert_eq(st["rows"], [("早", "任务1"), ("中", "任务2"), ("晚", "任务3")],
              "三格都没动（不滚动）")
    assert_eq(st["row_done"], [True, False, False], "只有「早」标记为已完成")
    assert_eq(st["notes"], [["任务1"], [], []], "「早」的归档备注里有任务1")
    assert_eq(p.archived, ["任务1"], "任务1 已归档")


def test_complete_only_twice_is_rejected():
    print("\n=== test_complete_only_twice_is_rejected ===")
    d = make_data()
    s = PlanScheduler(d.parents[0])
    s.complete_only_slot(0)
    assert_eq(s.complete_only_slot(0), False, "同一格不能重复仅完成")
    assert_eq(s.can_complete_only(0), False, "can_complete_only → False")
    assert_eq(s.can_complete_only(1), True, "别的格子还能仅完成")


def test_complete_only_then_scroll():
    """仅完成 → 完成并滚动：解开那一格让它滚（不重复归档、不重复写备注）"""
    print("\n=== test_complete_only_then_scroll ===")
    d = make_data()
    p = d.parents[0]
    s = PlanScheduler(p)
    s.complete_only_slot(0)
    assert_eq(plans_of(s, 0), ["任务1", "任务2", "任务3"], "仅完成后没滚动")
    s.complete_today_slot(0)
    assert_eq(plans_of(s, 0), ["任务2", "任务3", None], "再按完成并滚动 → 上滚，最后一格空")
    assert_eq(p.archived, ["任务1"], "只归档一次（不重复）")
    assert_eq(s.today_state()["notes"][0], ["任务1"], "备注也只有一条")
    assert_eq(s.today_state()["row_done"][0], False, "钉子解开了")


# ============== 完成并滚动 ==============

def test_scroll_does_not_pull_tomorrow():
    """关键：腾出来的最后一格不从第二天补"""
    print("\n=== test_scroll_does_not_pull_tomorrow ===")
    d = make_data()
    s = PlanScheduler(d.parents[0])
    assert_eq(plans_of(s, 0), ["任务1", "任务2", "任务3"], "初始 早1 中2 晚3")
    s.complete_today_slot(0)
    assert_eq(plans_of(s, 0), ["任务2", "任务3", None],
              "完成并滚动早1 → 早2 中3 晚空（不是把任务4滚上来）")
    assert_eq(plans_of(s, 1), ["任务4", "任务5", "任务6"], "第2天不受影响")
    assert_true("任务4" not in plans_of(s, 0), "任务4 没有跑到今天")


def test_scroll_fills_last_row_from_extra():
    """有额外轮时，最后一格由额外轮补上"""
    print("\n=== test_scroll_fills_last_row_from_extra ===")
    d = make_data()
    p = d.parents[0]
    s = PlanScheduler(p)
    s.borrow_next()                       # 额外轮 = 任务4
    assert_eq(s.extra_plans(), ["任务4"], "额外轮里有任务4")
    s.complete_today_slot(0)
    st = s.today_state()
    assert_eq(plans_of(s, 0), ["任务2", "任务3", "任务4"], "任务4 从额外轮顶上来")
    assert_eq(st["promoted"], ["任务4"], "任务4 已滚上来")
    assert_eq(st["extra_left"], [], "不在额外轮区重复显示")
    assert_eq(plans_of(s, 1), ["任务4", "任务5", "任务6"], "第2天照旧（借出去的是副本）")


def test_scroll_twice_keeps_compacting():
    print("\n=== test_scroll_twice_keeps_compacting ===")
    d = make_data()
    s = PlanScheduler(d.parents[0])
    s.complete_today_slot(0)
    s.complete_today_slot(0)
    assert_eq(plans_of(s, 0), ["任务3", None, None],
              "完成两条 → 只剩任务3 在最上面（不从第二天补）")
    assert_eq(s.done_today(), ["任务1", "任务2"], "今天完成 2 条")


def test_scroll_keeps_done_rows_in_place():
    """仅完成钉住的格子不会被后面的滚动挤走"""
    print("\n=== test_scroll_keeps_done_rows_in_place ===")
    d = make_data()
    s = PlanScheduler(d.parents[0])
    s.complete_only_slot(0)     # 早 = 任务1（钉住）
    s.complete_today_slot(1)    # 中 = 任务2 归档并滚动
    st = s.today_state()
    assert_eq(st["rows"], [("早", "任务1"), ("中", "任务3"), ("晚", None)],
              "早还是任务1（钉住），任务3 顶到中，晚空")
    assert_eq(st["row_done"], [True, False, False], "只有早是钉住的")


def test_exhausted_shows_empty():
    print("\n=== test_exhausted_shows_empty ===")
    d = make_data(plan_count=3)
    s = PlanScheduler(d.parents[0])
    s.complete_today_slot(0)
    assert_eq(plans_of(s, 0), ["任务2", "任务3", None], "用完一格")
    s.complete_today_slot(0)
    assert_eq(plans_of(s, 0), ["任务3", None, None], "再滚一格")
    s.complete_today_slot(0)
    assert_eq(plans_of(s, 0), [None, None, None], "全空")
    assert_eq(s.can_complete_today_slot(0), False, "空了就不能完成")
    assert_true(s.all_consumed(), "all_consumed() = True")


# ============== 备注 / 进度 / 撤销 ==============

def test_notes_are_per_slot():
    print("\n=== test_notes_are_per_slot ===")
    d = make_data()
    s = PlanScheduler(d.parents[0])
    s.complete_today_slot(2)   # 晚 = 任务3
    s.complete_only_slot(0)    # 早 = 任务1
    assert_eq(s.today_state()["notes"], [["任务1"], [], ["任务3"]],
              "每格各自记自己的归档备注")


def test_progress_counts_both_kinds():
    print("\n=== test_progress_counts_both_kinds ===")
    d = make_data()
    s = PlanScheduler(d.parents[0])
    assert_eq(s.get_progress(), (3, 9), "初始 3 / 9")
    s.complete_only_slot(0)
    assert_eq(s.get_progress(), (4, 9), "仅完成 → 4 / 9")
    s.complete_today_slot(0)
    assert_eq(s.get_progress(), (4, 9), "同一格再滚动不重复计数")
    s.complete_today_slot(1)
    assert_eq(s.get_progress(), (5, 9), "另一格完成 → 5 / 9")


def test_undo_complete_only():
    print("\n=== test_undo_complete_only ===")
    d = make_data()
    p = d.parents[0]
    s = PlanScheduler(p)
    s.complete_only_slot(0)
    assert_true(s.undo_complete(), "撤销成功")
    assert_eq(p.archived, [], "归档清空")
    st = s.today_state()
    assert_eq(st["row_done"], [False, False, False], "钉子解开")
    assert_eq(st["notes"], [[], [], []], "备注清空")
    assert_eq(plans_of(s, 0), ["任务1", "任务2", "任务3"], "回到原样")


def test_undo_scroll():
    print("\n=== test_undo_scroll ===")
    d = make_data()
    p = d.parents[0]
    s = PlanScheduler(p)
    s.complete_today_slot(0)
    s.undo_complete()
    assert_eq(plans_of(s, 0), ["任务1", "任务2", "任务3"], "滚回去")
    assert_eq(p.archived, [], "归档清空")
    assert_eq(s.today_state()["notes"], [[], [], []], "备注清空")


def test_undo_only_today():
    print("\n=== test_undo_only_today ===")
    d = make_data()
    p = d.parents[0]
    s = PlanScheduler(p)
    s.complete_today_slot(0)
    p.consumed += s.today_state()["queue_used"]
    p.archived_base = len(p.archived)
    p.borrowed_slots = []
    p.inplace_done = []
    p.slot_notes = []
    p.current_day = 1
    p.normalize()
    assert_eq(s.can_undo_complete(), False, "昨天的完成不能撤")
    assert_eq(plans_of(s, 1), ["任务4", "任务5", "任务6"], "第2天从任务4 开始")


def test_next_day_resets_row_state():
    print("\n=== test_next_day_resets_row_state ===")
    d = make_data()
    p = d.parents[0]
    s = PlanScheduler(p)
    s.complete_only_slot(0)
    p.consumed += s.today_state()["queue_used"]
    p.archived_base = len(p.archived)
    p.borrowed_slots = []
    p.inplace_done = []
    p.slot_notes = []
    p.current_day = 1
    p.normalize()
    st = s.today_state()
    assert_eq(st["row_done"], [False, False, False], "新的一天没有钉住的格子")
    assert_eq(st["notes"], [[], [], []], "新的一天备注从空开始")
    assert_eq(s.done_today(), [], "「今天完成的」从空开始")


# ============== 持久化 ==============

def test_to_from_dict_roundtrip():
    print("\n=== test_to_from_dict_roundtrip ===")
    d = make_data()
    p = d.parents[0]
    s = PlanScheduler(p)
    s.complete_only_slot(0)
    s.complete_today_slot(1)
    data = p.to_dict()
    for key in ("archived", "archived_base", "consumed", "inplace_done", "slot_notes"):
        assert_true(key in data, f"to_dict 含 {key}")
    p2 = ParentPlan()
    p2.from_dict(data)
    assert_eq(p2.archived, ["任务1", "任务2"], "archived round-trip")
    assert_eq(p2.inplace_done, ["任务1", None, None], "inplace_done round-trip")
    assert_eq(p2.slot_notes, [["任务1"], ["任务2"], []], "slot_notes round-trip")
    s2 = PlanScheduler(p2)
    assert_eq(plans_of(s2, 0), ["任务1", "任务3", None], "恢复后显示一致")


def test_from_dict_pads_row_state():
    """旧存档没有 inplace_done / slot_notes → 自动补齐到当前格数"""
    print("\n=== test_from_dict_pads_row_state ===")
    legacy = {
        "name": "旧档",
        "plans": ["A", "B", "C", "D"],
        "time_slots": [{"name": "早", "count": 1}, {"name": "中", "count": 1}],
        "start_date": "2026-09-15",
        "current_day": 0,
        "borrowed_slots": [],
    }
    p = ParentPlan()
    p.from_dict(legacy)
    assert_eq(p.inplace_done, [None, None], "inplace_done 补齐 2 格")
    assert_eq(p.slot_notes, [[], []], "slot_notes 补齐 2 格")
    assert_eq(PlanScheduler(p).get_day_plans(0), [("早", "A"), ("中", "B")], "显示正常")


def test_reset_progress_clears_row_state():
    print("\n=== test_reset_progress_clears_row_state ===")
    d = make_data()
    p = d.parents[0]
    s = PlanScheduler(p)
    s.borrow_next()
    s.complete_only_slot(0)
    s.complete_today_slot(1)
    p.reset_progress()
    assert_eq(p.archived, [], "archived 清空")
    assert_eq(p.inplace_done, [], "inplace_done 清空")
    assert_eq(p.slot_notes, [], "slot_notes 清空")
    assert_eq(p.borrowed_slots, [], "额外轮清空")
    assert_eq(plans_of(PlanScheduler(p), 0), ["任务1", "任务2", "任务3"], "回到第一天原样")


# ============== 额外轮 / 添加指定（v0.9 行为不回归） ==============

def test_extra_stays_when_rows_full():
    print("\n=== test_extra_stays_when_rows_full ===")
    d = make_data()
    s = PlanScheduler(d.parents[0])
    s.borrow_next()
    st = s.today_state()
    assert_eq(st["promoted"], [], "行是满的 → 没有滚上来的")
    assert_eq(st["extra_left"], ["任务4"], "任务4 留在额外轮区")
    assert_eq(plans_of(s, 0), ["任务1", "任务2", "任务3"], "日内行不受影响")


def test_available_pick_plans():
    print("\n=== test_available_pick_plans ===")
    d = make_data()
    s = PlanScheduler(d.parents[0])
    assert_eq(s.available_pick_plans(),
              ["任务4", "任务5", "任务6", "任务7", "任务8", "任务9"],
              "候选 = 第2天起的计划")
    s.borrow_plan("任务5")
    assert_eq(s.available_pick_plans(),
              ["任务4", "任务6", "任务7", "任务8", "任务9"],
              "挑走任务5 → 候选里不再有它")


def test_borrow_plan_rejects_unknown_or_today():
    print("\n=== test_borrow_plan_rejects_unknown_or_today ===")
    d = make_data()
    s = PlanScheduler(d.parents[0])
    assert_eq(s.borrow_plan("任务1"), False, "今天的任务1 不能提前安排")
    assert_eq(s.borrow_plan("不存在"), False, "不存在的计划 → False")
    assert_eq(s.borrow_plan("任务4"), True, "后面的任务4 可以")


# ============== UI ==============

def find_buttons(ex, text):
    """只找当前显示的行里的按钮（刷新时旧控件是 deleteLater，别抓到旧的）"""
    out = []
    for layout in (ex.day_layout,):
        for i in range(layout.count()):
            item = layout.itemAt(i)
            if item and item.widget():
                out += [b for b in item.widget().findChildren(rollingplan.QPushButton)
                        if b.text() == text]
    return out


def day_labels(ex):
    out = []
    for i in range(ex.day_layout.count()):
        item = ex.day_layout.itemAt(i)
        if item and item.widget():
            out += [c.text() for c in item.widget().findChildren(rollingplan.QLabel)]
    return out


def dialog_labels(dlg):
    """额外安排列表对话框里的所有文字"""
    out = [dlg.hint.text()]
    for i in range(dlg.list_layout.count()):
        item = dlg.list_layout.itemAt(i)
        if item and item.widget():
            w = item.widget()
            if isinstance(w, rollingplan.QLabel):
                out.append(w.text())          # 占位提示牌本身就是 QLabel
            out += [c.text() for c in w.findChildren(rollingplan.QLabel)]
    return out


def dialog_delete_buttons(dlg):
    """列表里所有的「🗑 删除该安排」按钮"""
    out = []
    for i in range(dlg.list_layout.count()):
        item = dlg.list_layout.itemAt(i)
        if item and item.widget():
            out += [b for b in item.widget().findChildren(rollingplan.QPushButton)
                    if b.text() == "🗑 删除该安排"]
    return out


def test_executor_renders_two_buttons_per_row():
    print("\n=== test_executor_renders_two_buttons_per_row ===")
    d = make_data()
    ex = PlanExecutor(d, lambda: None)
    ex.show()
    app.processEvents()
    assert_eq(len(find_buttons(ex, "仅完成")), 3, "3 格各有一个「仅完成」")
    assert_eq(len(find_buttons(ex, "✓ 完成并滚动")), 3, "3 格各有一个「完成并滚动」")
    assert_eq(ex.return_btn.text(), "⤴ 退回", "还没完成过 → 退回按钮是「退回」")
    for b in find_buttons(ex, "仅完成"):
        assert_true(b.isEnabled(), "初始「仅完成」都可点")


def test_executor_complete_only_greys_button():
    print("\n=== test_executor_complete_only_greys_button ===")
    d = make_data()
    ex = PlanExecutor(d, lambda: None)
    ex.show()
    app.processEvents()
    find_buttons(ex, "仅完成")[0].click()
    app.processEvents()
    texts = day_labels(ex)
    assert_true(any("任务1" in t for t in texts), "任务1 还留在格里（不滚动）")
    assert_true(any(t.startswith("✓ 任务1") for t in texts), "显示成 ✓ 任务1（完成标记）")
    assert_true(any("归档：任务1" in t for t in texts), "归档备注显示出来了")
    btn = find_buttons(ex, "仅完成")[0]
    assert_eq(btn.isEnabled(), False, "「仅完成」灰掉")
    assert_true(find_buttons(ex, "✓ 完成并滚动")[0].isEnabled(), "「完成并滚动」还能按")


def test_executor_scroll_rolls_rows():
    print("\n=== test_executor_scroll_rolls_rows ===")
    d = make_data()
    ex = PlanExecutor(d, lambda: None)
    ex.show()
    app.processEvents()
    find_buttons(ex, "✓ 完成并滚动")[0].click()
    app.processEvents()
    texts = day_labels(ex)
    assert_true(any("任务2" in t for t in texts), "任务2 滚到第一格")
    assert_true(any("任务3" in t for t in texts), "任务3 滚到第二格")
    assert_true(not any("任务4" in t for t in texts), "任务4（第二天）没有滚上来")
    assert_eq(ex.return_btn.text(), "↶ 撤销完成", "退回按钮变成 ↶ 撤销完成")


def test_executor_return_undoes():
    print("\n=== test_executor_return_undoes ===")
    d = make_data()
    p = d.parents[0]
    ex = PlanExecutor(d, lambda: None)
    ex.show()
    app.processEvents()
    find_buttons(ex, "仅完成")[0].click()
    app.processEvents()
    ex.return_btn.click()
    app.processEvents()
    assert_eq(p.archived, [], "撤销后归档清空")
    assert_eq(p.inplace_done[0] if p.inplace_done else None, None, "钉子也解开")


def test_executor_extra_row_has_no_slot_name():
    """额外安排列表里只有计划内容，不带时段名（v0.12：列表在对话框里）"""
    print("\n=== test_executor_extra_row_has_no_slot_name ===")
    d = make_data()
    ex = PlanExecutor(d, lambda: None)
    ex.show()
    app.processEvents()
    ex.scheduler.borrow_next()
    ex.refresh()
    app.processEvents()
    dlg = rollingplan.ExtraArrangementsDialog(ex)
    texts = dialog_labels(dlg)
    assert_true(any("任务4" in t for t in texts), "列表里显示 任务4")
    assert_true(not any(t.strip().startswith("早") for t in texts), "额外安排不带时段名")
    assert_true(any("候补中" in t for t in texts), "标着「候补中」")
    assert_eq(ex.extra_btn.text(), "📋 额外安排（1）", "细长条按钮显示条数")


def test_fixed_slot_does_not_move():
    """固定计划：这一格的原定计划不参与上滚，后面的照常"""
    print("\n=== test_fixed_slot_does_not_move ===")
    d = make_data()
    s = PlanScheduler(d.parents[0])
    assert_true(s.toggle_fixed(1), "「中」固定成功")
    assert_eq(s.today_state()["row_fixed"], [False, True, False], "只有中标记为固定")
    assert_eq(plans_of(s, 0), ["任务1", "任务2", "任务3"], "标记时显示不变")
    s.complete_today_slot(0)
    st = s.today_state()
    assert_eq(st["rows"], [("早", "任务3"), ("中", "任务2"), ("晚", None)],
              "中的任务2 没动；晚的任务3 往前挤进了早")
    assert_eq(plans_of(s, 0).count("任务2"), 1, "任务2 只出现一次（不重复）")


def test_fixed_toggle_off():
    print("\n=== test_fixed_toggle_off ===")
    d = make_data()
    s = PlanScheduler(d.parents[0])
    s.toggle_fixed(1)
    s.toggle_fixed(1)
    assert_eq(s.today_state()["row_fixed"], [False, False, False], "再按一次取消")
    s.complete_today_slot(0)
    assert_eq(plans_of(s, 0), ["任务2", "任务3", None], "取消后恢复正常滚动")


def test_blocked_slot_and_after_do_not_move():
    """拦截滚动：这一格及往后的都不参与上滚"""
    print("\n=== test_blocked_slot_and_after_do_not_move ===")
    d = make_data()
    s = PlanScheduler(d.parents[0])
    assert_true(s.toggle_blocked(1), "从「中」开始拦截")
    assert_eq(s.today_state()["row_blocked"], [False, True, True], "中、晚都被拦截")
    s.complete_today_slot(0)
    st = s.today_state()
    assert_eq(st["rows"], [("早", None), ("中", "任务2"), ("晚", "任务3")],
              "中和晚都锁住；早腾出来的位置没人补（额外轮为空）")


def test_blocked_last_slot_only():
    print("\n=== test_blocked_last_slot_only ===")
    d = make_data()
    s = PlanScheduler(d.parents[0])
    s.toggle_blocked(2)          # 只拦最后一格
    s.complete_today_slot(0)
    st = s.today_state()
    assert_eq(st["rows"], [("早", "任务2"), ("中", None), ("晚", "任务3")],
              "晚的任务3 不动；中的任务2 挤到早（中空出来）")


def test_blocked_freed_slot_from_extra():
    """拦截时：额外轮是当天最后的时间栏，也在拦截范围里 —— 腾出来的位置没人补（v0.12）"""
    print("\n=== test_blocked_freed_slot_from_extra ===")
    d = make_data()
    s = PlanScheduler(d.parents[0])
    s.borrow_next()              # 额外轮 = 任务4
    s.toggle_blocked(1)
    s.complete_today_slot(0)
    st = s.today_state()
    assert_eq(st["extras_frozen"], True, "有格子拦截 → 额外轮也被拦")
    assert_eq(st["rows"], [("早", None), ("中", "任务2"), ("晚", "任务3")],
              "腾出来的位置是空的（额外轮不候补上来）")
    assert_eq(st["extra_left"], ["任务4"], "任务4 还留在额外轮里")
    assert_eq(st["promoted"], [], "没有任何额外安排滚进今天")


def test_blocked_allows_extra_when_no_block():
    """没拦截时，额外轮照旧候补（对照）"""
    print("\n=== test_blocked_allows_extra_when_no_block ===")
    d = make_data()
    s = PlanScheduler(d.parents[0])
    s.borrow_next()              # 额外轮 = 任务4
    s.complete_today_slot(0)     # 没有拦截
    st = s.today_state()
    assert_eq(st["extras_frozen"], False, "没拦截 → 额外轮不冻结")
    assert_eq(st["rows"], [("早", "任务2"), ("中", "任务3"), ("晚", "任务4")],
              "正常上滚，任务4 顶进最后一格")
    assert_eq(st["promoted"], ["任务4"], "任务4 已滚入今天")


def test_fixed_allows_extra():
    """固定（不是拦截）：额外轮不受影响，照旧候补"""
    print("\n=== test_fixed_allows_extra ===")
    d = make_data()
    s = PlanScheduler(d.parents[0])
    s.borrow_next()
    s.toggle_fixed(1)
    s.complete_today_slot(0)
    st = s.today_state()
    assert_eq(st["extras_frozen"], False, "固定不冻结额外轮")
    assert_eq(st["rows"], [("早", "任务3"), ("中", "任务2"), ("晚", "任务4")],
              "中的2 固定住；任务4 补进晚")


def test_unborrow_waiting_plan():
    """删除该安排：还没滚进来的，直接拿走"""
    print("\n=== test_unborrow_waiting_plan ===")
    d = make_data()
    s = PlanScheduler(d.parents[0])
    s.borrow_next()                       # 任务4 进额外轮（今天没空格，候补中）
    assert_eq(s.today_state()["extra_left"], ["任务4"], "任务4 在候补")
    assert_true(s.unborrow_plan("任务4"), "删除成功")
    assert_eq(s.today_state()["extras"], [], "额外轮空了")
    assert_true("任务4" in s.available_pick_plans(), "任务4 回到「还没安排」的队里")
    assert_eq(s.unborrow_plan("任务4"), False, "再删删不到")


def test_unborrow_promoted_plan():
    """删除已经滚进今天的安排：那一格由后面的候补顶上"""
    print("\n=== test_unborrow_promoted_plan ===")
    d = make_data()
    s = PlanScheduler(d.parents[0])
    s.borrow_next()                       # 任务4
    s.borrow_plan("任务7")                # 任务7
    s.complete_today_slot(0)              # 早1 归档 → 早=任务2 中=任务3 晚=任务4
    st = s.today_state()
    assert_eq(st["rows"], [("早", "任务2"), ("中", "任务3"), ("晚", "任务4")], "任务4 滚进晚")
    assert_eq(st["promoted"], ["任务4"], "任务4 已滚入")
    assert_true(s.unborrow_plan("任务4"), "把滚进来的任务4 删掉")
    st = s.today_state()
    assert_eq(st["rows"], [("早", "任务2"), ("中", "任务3"), ("晚", "任务7")],
              "晚那一格改成候补里的任务7")
    assert_eq(st["extras"], ["任务7"], "额外轮只剩任务7")


def test_executor_extra_button_and_dialog():
    print("\n=== test_executor_extra_button_and_dialog ===")
    d = make_data()
    ex = PlanExecutor(d, lambda: None)
    ex.show()
    app.processEvents()
    assert_eq(ex.extra_btn.text(), "📋 额外安排（0）", "初始 0 条")
    ex.scheduler.borrow_next()
    ex.refresh()
    app.processEvents()
    assert_eq(ex.extra_btn.text(), "📋 额外安排（1）", "加一个后显示 1 条")
    # 版式：长度 = 两个大按钮合起来的跨度，但更矮
    span = (ex.done_btn.x() + ex.done_btn.width()) - ex.add_next_btn.x()
    assert_eq(ex.extra_btn.width(), span, "细长条的长度 = 加一个+今天完成的跨度")
    assert_true(ex.extra_btn.height() < ex.add_next_btn.height(), "细长条更矮")

    dlg = rollingplan.ExtraArrangementsDialog(ex)
    assert_eq(len(dialog_delete_buttons(dlg)), 1, "列表里 1 个「删除该安排」")
    assert_eq(dlg.add_specific_btn.text(), "➕ 添加指定计划", "有「添加指定计划」")
    assert_eq(dlg.pull_next_btn.text(), "⤵ 直接拉取下一个", "有「直接拉取下一个」")

    dlg.pull_next_btn.click()
    app.processEvents()
    assert_eq(ex.extra_btn.text(), "📋 额外安排（2）", "直接拉取后 2 条")
    dialog_delete_buttons(dlg)[0].click()
    app.processEvents()
    assert_eq(ex.extra_btn.text(), "📋 额外安排（1）", "删掉一条后剩 1 条")


def test_dialog_marks_promoted_and_frozen():
    print("\n=== test_dialog_marks_promoted_and_frozen ===")
    d = make_data()
    ex = PlanExecutor(d, lambda: None)
    ex.show()
    app.processEvents()
    ex.scheduler.borrow_next()            # 任务4
    ex.scheduler.complete_today_slot(0)   # 早1 → 任务4 滚进晚
    ex.refresh()
    app.processEvents()
    dlg = rollingplan.ExtraArrangementsDialog(ex)
    texts = dialog_labels(dlg)
    assert_true(any("已滚入今天的第 3 格" in t for t in texts), "标出滚进了第 3 格")

    ex.scheduler.toggle_blocked(1)        # 拦截 → 额外轮冻结
    ex.refresh()
    app.processEvents()
    assert_true("已拦截" in ex.extra_btn.text(), "细长条按钮上标出「已拦截」")
    dlg2 = rollingplan.ExtraArrangementsDialog(ex)
    assert_true("拦截" in dlg2.hint.text(), "列表里提示被拦截")


def test_dialog_no_extra_placeholder():
    print("\n=== test_dialog_no_extra_placeholder ===")
    d = make_data()
    ex = PlanExecutor(d, lambda: None)
    ex.show()
    app.processEvents()
    dlg = rollingplan.ExtraArrangementsDialog(ex)
    assert_true(any("还没有额外安排" in t for t in dialog_labels(dlg)), "空列表有提示")
    assert_eq(len(dialog_delete_buttons(dlg)), 0, "空列表没有删除按钮")


def test_blocked_toggle_off():
    print("\n=== test_blocked_toggle_off ===")
    d = make_data()
    s = PlanScheduler(d.parents[0])
    s.toggle_blocked(1)
    s.toggle_blocked(1)
    assert_eq(s.today_state()["row_blocked"], [False, False, False], "再按一次全部取消")
    s.complete_today_slot(0)
    assert_eq(plans_of(s, 0), ["任务2", "任务3", None], "恢复正常滚动")


def test_complete_clears_fixed_and_blocked_on_that_row():
    print("\n=== test_complete_clears_fixed_and_blocked_on_that_row ===")
    d = make_data()
    s = PlanScheduler(d.parents[0])
    s.toggle_fixed(0)
    s.complete_today_slot(0)     # 完成这一格（它本来固定着）
    st = s.today_state()
    assert_eq(st["row_fixed"], [False, False, False], "完成后这一格的固定解开了")
    assert_eq(plans_of(s, 0), ["任务2", "任务3", None], "正常上滚")


def test_fixed_blocked_persist_and_reset():
    print("\n=== test_fixed_blocked_persist_and_reset ===")
    d = make_data()
    p = d.parents[0]
    s = PlanScheduler(p)
    s.toggle_fixed(1)
    s.toggle_blocked(2)
    data = p.to_dict()
    for key in ("slot_fixed", "slot_blocked"):
        assert_true(key in data, f"to_dict 含 {key}")
    p2 = ParentPlan()
    p2.from_dict(data)
    assert_eq(p2.slot_fixed, [None, "任务2", None], "slot_fixed round-trip")
    assert_eq(p2.slot_blocked, [None, None, "任务3"], "slot_blocked round-trip")
    p.reset_progress()
    assert_eq(p.slot_fixed, [], "重置清空 slot_fixed")
    assert_eq(p.slot_blocked, [], "重置清空 slot_blocked")


def test_next_day_clears_fixed_blocked():
    print("\n=== test_next_day_clears_fixed_blocked ===")
    d = make_data()
    p = d.parents[0]
    s = PlanScheduler(p)
    s.toggle_fixed(1)
    p.consumed += s.today_state()["queue_used"]
    p.archived_base = len(p.archived)
    p.borrowed_slots = []
    p.inplace_done = []
    p.slot_notes = []
    p.slot_fixed = []
    p.slot_blocked = []
    p.current_day = 1
    p.normalize()
    st = s.today_state()
    assert_eq(st["row_fixed"], [False, False, False], "新的一天固定归零")
    assert_eq(st["row_blocked"], [False, False, False], "新的一天拦截归零")
    assert_eq(plans_of(s, 1), ["任务4", "任务5", "任务6"], "第2天正常显示")


def test_executor_renders_toggle_buttons():
    print("\n=== test_executor_renders_toggle_buttons ===")
    d = make_data()
    ex = PlanExecutor(d, lambda: None)
    ex.show()
    app.processEvents()
    assert_eq(len(find_buttons(ex, "固定计划")), 3, "3 格各有「固定计划」")
    assert_eq(len(find_buttons(ex, "拦截滚动")), 3, "3 格各有「拦截滚动」")
    for b in find_buttons(ex, "固定计划") + find_buttons(ex, "拦截滚动"):
        assert_eq(b.isChecked(), False, "初始都未按下")


def test_executor_toggle_fixed_and_blocked():
    print("\n=== test_executor_toggle_fixed_and_blocked ===")
    d = make_data()
    ex = PlanExecutor(d, lambda: None)
    ex.show()
    app.processEvents()
    find_buttons(ex, "固定计划")[1].click()      # 中 → 固定
    app.processEvents()
    assert_true(find_buttons(ex, "固定计划")[1].isChecked(), "第二格「固定计划」按下去了")
    assert_true(any("📌" in t for t in day_labels(ex)), "行首出现 📌 标记")
    find_buttons(ex, "拦截滚动")[1].click()      # 中 → 拦截
    app.processEvents()
    assert_true(find_buttons(ex, "拦截滚动")[1].isChecked(), "「拦截滚动」按下去了")
    assert_true(any("⛔" in t for t in day_labels(ex)), "行首出现 ⛔ 标记")
    ex.scheduler.complete_today_slot(0)
    ex.refresh()
    app.processEvents()
    assert_eq(ex.scheduler.today_state()["rows"][1], ("中", "任务2"), "中被拦截，没动")


# ============== 快捷键(v0.13+) ==============

def test_keyboard_shortcuts_in_executor_tab():
    """Ctrl+Enter / Ctrl+Z 在执行计划页生效;Ctrl+D 触发 on_next_day(带二次确认);
    制定计划页 Ctrl+Enter / Ctrl+Z 不拦截。"""
    print("\n=== test_keyboard_shortcuts_in_executor_tab ===")
    from rollingplan import MainWindow

    d = make_data(plan_count=9)
    win = MainWindow()
    # 注入我们的数据(覆盖默认的空 data)
    win.data = d
    win.executor = PlanExecutor(d, lambda: None)
    win.tabs.removeTab(1)
    win.tabs.addTab(win.executor, "▶ 执行计划")
    win.tabs.setCurrentIndex(1)
    win.show()
    app.processEvents()

    sched = win.executor.scheduler

    # 1) Ctrl+Enter → on_add_next(多一条进额外轮)
    extra_before = len(sched.today_state().get("extras", []))
    QTest.keyClick(win, Qt.Key_Return, Qt.ControlModifier)
    app.processEvents()
    extra_after = len(sched.today_state().get("extras", []))
    assert_eq(extra_after, extra_before + 1, "Ctrl+Enter 把队列下一条拉进额外轮")

    # 2) Ctrl+Z → on_return(退掉刚才加的那条)
    QTest.keyClick(win, Qt.Key_Z, Qt.ControlModifier)
    app.processEvents()
    assert_eq(len(sched.today_state().get("extras", [])), extra_before, "Ctrl+Z 退掉额外轮最后一条")

    # 3) Ctrl+D → on_next_day(spy 验证被调用,不真正触发模态 QMessageBox.question,
    #     避免 headless offscreen 下阻塞。生产环境下弹窗由用户点确认/取消)
    next_day_calls = [0]
    def spy_next_day():
        next_day_calls[0] += 1
    original_next_day = win.executor.on_next_day
    win.executor.on_next_day = spy_next_day
    QTest.keyClick(win, Qt.Key_D, Qt.ControlModifier)
    app.processEvents()
    win.executor.on_next_day = original_next_day
    assert_eq(next_day_calls[0], 1, "Ctrl+D 触发 executor.on_next_day(由弹窗确认是否切天)")

    # 4) 无 Ctrl 的 Z/D/Enter 必须不触发快捷键(避免吞掉文本框常用键)
    leaked = {"hit": False}
    def fake_return():
        leaked["hit"] = True
    def fake_add_next():
        leaked["hit"] = True
    original_return = win.executor.on_return
    original_add = win.executor.on_add_next
    win.executor.on_return = fake_return
    win.executor.on_add_next = fake_add_next
    QTest.keyClick(win, Qt.Key_Z)
    QTest.keyClick(win, Qt.Key_Return)
    app.processEvents()
    win.executor.on_return = original_return
    win.executor.on_add_next = original_add
    assert_true(not leaked["hit"], "无 Ctrl 时 Z / Enter 不触发快捷键")

    # 5) 制定计划页 Ctrl+Enter / Ctrl+Z 必须不拦截(避免吞掉输入框常用组合)
    win.tabs.setCurrentIndex(0)
    app.processEvents()
    extras_pre_editor = len(sched.today_state().get("extras", []))
    QTest.keyClick(win, Qt.Key_Return, Qt.ControlModifier)
    QTest.keyClick(win, Qt.Key_Z, Qt.ControlModifier)
    app.processEvents()
    assert_eq(len(sched.today_state().get("extras", [])), extras_pre_editor,
              "制定计划页按 Ctrl+Enter / Ctrl+Z 不生效")


def main():
    test_complete_only_does_not_scroll()
    test_complete_only_twice_is_rejected()
    test_complete_only_then_scroll()
    test_scroll_does_not_pull_tomorrow()
    test_scroll_fills_last_row_from_extra()
    test_scroll_twice_keeps_compacting()
    test_scroll_keeps_done_rows_in_place()
    test_exhausted_shows_empty()
    test_notes_are_per_slot()
    test_progress_counts_both_kinds()
    test_undo_complete_only()
    test_undo_scroll()
    test_undo_only_today()
    test_next_day_resets_row_state()
    test_to_from_dict_roundtrip()
    test_from_dict_pads_row_state()
    test_reset_progress_clears_row_state()
    test_extra_stays_when_rows_full()
    test_available_pick_plans()
    test_borrow_plan_rejects_unknown_or_today()
    test_executor_renders_two_buttons_per_row()
    test_executor_complete_only_greys_button()
    test_executor_scroll_rolls_rows()
    test_executor_return_undoes()
    test_executor_extra_row_has_no_slot_name()
    test_fixed_slot_does_not_move()
    test_fixed_toggle_off()
    test_blocked_slot_and_after_do_not_move()
    test_blocked_last_slot_only()
    test_blocked_freed_slot_from_extra()
    test_blocked_allows_extra_when_no_block()
    test_fixed_allows_extra()
    test_unborrow_waiting_plan()
    test_unborrow_promoted_plan()
    test_executor_extra_button_and_dialog()
    test_dialog_marks_promoted_and_frozen()
    test_dialog_no_extra_placeholder()
    test_blocked_toggle_off()
    test_complete_clears_fixed_and_blocked_on_that_row()
    test_fixed_blocked_persist_and_reset()
    test_next_day_clears_fixed_blocked()
    test_executor_renders_toggle_buttons()
    test_executor_toggle_fixed_and_blocked()
    test_keyboard_shortcuts_in_executor_tab()

    print()
    print(f"PASS={PASS_COUNT}  FAIL={FAIL_COUNT}")
    if FAIL_COUNT == 0:
        print("=== ALL TESTS PASSED ===")
        sys.exit(0)
    print("=== TESTS FAILED ===")
    sys.exit(1)


if __name__ == "__main__":
    main()
