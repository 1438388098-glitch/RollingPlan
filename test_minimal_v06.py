"""
RollingPlan v0.6 极简界面（折叠分组）测试

覆盖：
- PlanEditor 三个折叠按钮（_parent_toggle/_plan_toggle/_slot_toggle）
  初始为收起状态（checked=False, body 不可见）
- 点击后切换 visible + 切换箭头 ▸ / ▾
- PlanExecutor 「更多」按钮初始收起
  - 点击后 advanced_container 可见 + 箭头切换
- 执行页主题下拉框存在并能切换

运行：QT_QPA_PLATFORM=offscreen python test_minimal_v06.py
"""

import os
os.environ["QT_QPA_PLATFORM"] = "offscreen"

import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PyQt5.QtWidgets import QApplication, QPushButton, QToolButton, QWidget
app = QApplication(sys.argv)

from theme import app_settings
from rollingplan import (
    PlanEditor, PlanExecutor, PlanData, PlanScheduler,
    THEME_OPTIONS, THEME_KEY,
)
from PyQt5.QtCore import QDate, Qt


PASS_COUNT = 0
FAIL_COUNT = 0


def _bump_pass():
    global PASS_COUNT
    PASS_COUNT += 1


def _bump_fail():
    global FAIL_COUNT
    FAIL_COUNT += 1


def assert_eq(actual, expected, label):
    if actual == expected:
        _bump_pass()
        print(f"  PASS [{label}]")
    else:
        _bump_fail()
        print(f"  FAIL [{label}]")
        print(f"    expected: {expected!r}")
        print(f"    actual:   {actual!r}")
        sys.exit(1)


def assert_true(cond, label):
    if cond:
        _bump_pass()
        print(f"  PASS [{label}]")
    else:
        _bump_fail()
        print(f"  FAIL [{label}]")
        sys.exit(1)


def assert_visible(w, label):
    """检查 widget 可见（自身 + parent chain）"""
    if not w.isVisible():
        _bump_fail()
        print(f"  FAIL [{label}] widget 不可见")
        sys.exit(1)
    p = w.parent()
    while p is not None:
        if not p.isVisible():
            _bump_fail()
            print(f"  FAIL [{label}] parent chain 不可见")
            sys.exit(1)
        p = p.parent()
    _bump_pass()
    print(f"  PASS [{label}]")


def assert_not_visible(w, label):
    """检查 widget 不可见（自身或 parent chain 任一层）"""
    if not w.isVisible():
        _bump_pass()
        print(f"  PASS [{label}]")
        return
    p = w.parent()
    while p is not None:
        if not p.isVisible():
            _bump_pass()
            print(f"  PASS [{label}] (parent invisible)")
            return
        p = p.parent()
    _bump_fail()
    print(f"  FAIL [{label}] widget 实际可见")
    sys.exit(1)


def make_data():
    data = PlanData()
    data.parents[0].name = "工作"
    data.parents[0].time_slots = [{"name": "早", "count": 1}, {"name": "晚", "count": 1}]
    data.parents[0].plans = ["A", "B", "C"]
    data.parents[0].start_date = QDate.currentDate()
    return data


def _show(widget):
    """显示 widget 并处理事件（让 isVisible 真正生效）"""
    widget.show()
    app.processEvents()


# ============== PlanEditor 折叠测试 ==============

def test_editor_three_toggles_exist():
    print("\n=== test_editor_three_toggles_exist ===")
    ed = PlanEditor(make_data(), lambda: None)
    _show(ed)
    assert_true(hasattr(ed, '_parent_toggle'), "_parent_toggle 存在")
    assert_true(hasattr(ed, '_plan_toggle'), "_plan_toggle 存在")
    assert_true(hasattr(ed, '_slot_toggle'), "_slot_toggle 存在")


def test_editor_toggles_initially_collapsed():
    print("\n=== test_editor_toggles_initially_collapsed ===")
    ed = PlanEditor(make_data(), lambda: None)
    _show(ed)
    assert_eq(ed._parent_toggle.isChecked(), False, "分类 toggle 初始收起")
    assert_eq(ed._plan_toggle.isChecked(), False, "计划 toggle 初始收起")
    assert_eq(ed._slot_toggle.isChecked(), False, "时段 toggle 初始收起")
    assert_not_visible(ed._parent_body, "分类 body 初始不可见")
    assert_not_visible(ed._plan_body, "计划 body 初始不可见")
    assert_not_visible(ed._slot_body, "时段 body 初始不可见")
    assert_true("▸" in ed._parent_toggle.text(), "分类 toggle 显示 ▸")
    assert_true("▸" in ed._plan_toggle.text(), "计划 toggle 显示 ▸")
    assert_true("▸" in ed._slot_toggle.text(), "时段 toggle 显示 ▸")


def test_editor_toggle_expands_collapse():
    print("\n=== test_editor_toggle_expands_collapse ===")
    ed = PlanEditor(make_data(), lambda: None)
    _show(ed)

    ed._parent_toggle.click()
    app.processEvents()
    assert_eq(ed._parent_toggle.isChecked(), True, "分类 toggle 展开后 checked=True")
    assert_visible(ed._parent_body, "分类 body 展开后可见")
    assert_true("▾" in ed._parent_toggle.text(), "分类 toggle 展开后显示 ▾")

    ed._parent_toggle.click()
    app.processEvents()
    assert_eq(ed._parent_toggle.isChecked(), False, "分类 toggle 再点收起")
    assert_not_visible(ed._parent_body, "分类 body 收起后不可见")
    assert_true("▸" in ed._parent_toggle.text(), "分类 toggle 收起后显示 ▸")


def test_editor_toggles_independent():
    print("\n=== test_editor_toggles_independent ===")
    ed = PlanEditor(make_data(), lambda: None)
    _show(ed)
    ed._parent_toggle.click()
    ed._slot_toggle.click()
    app.processEvents()
    assert_visible(ed._parent_body, "分类 body 可见")
    assert_visible(ed._slot_body, "时段 body 可见")
    assert_not_visible(ed._plan_body, "计划 body 仍不可见")


# ============== PlanExecutor 折叠测试 ==============

def test_executor_advanced_toggle_exists():
    print("\n=== test_executor_advanced_toggle_exists ===")
    ex = PlanExecutor(make_data(), lambda: None)
    _show(ex)
    assert_true(hasattr(ex, 'advanced_toggle'), "advanced_toggle 存在")
    assert_true(hasattr(ex, 'advanced_container'), "advanced_container 存在")


def test_executor_advanced_initially_collapsed():
    print("\n=== test_executor_advanced_initially_collapsed ===")
    ex = PlanExecutor(make_data(), lambda: None)
    _show(ex)
    assert_eq(ex.advanced_toggle.isChecked(), False, "advanced_toggle 初始收起")
    assert_not_visible(ex.advanced_container, "advanced_container 初始不可见")


def test_executor_advanced_toggle_expands():
    print("\n=== test_executor_advanced_toggle_expands ===")
    ex = PlanExecutor(make_data(), lambda: None)
    _show(ex)
    ex.advanced_toggle.click()
    app.processEvents()
    assert_eq(ex.advanced_toggle.isChecked(), True, "advanced_toggle 展开")
    assert_visible(ex.advanced_container, "advanced_container 展开")
    from PyQt5.QtCore import Qt
    assert_eq(ex.advanced_toggle.arrowType(), Qt.DownArrow, "箭头变 DownArrow")


def test_executor_theme_combo_exists():
    print("\n=== test_executor_theme_combo_exists ===")
    ex = PlanExecutor(make_data(), lambda: None)
    _show(ex)
    assert_true(hasattr(ex, 'theme_combo'), "执行页 theme_combo 存在")
    assert_eq(ex.theme_combo.count(), 3, "3 个主题选项")


def test_executor_theme_combo_change_writes_qsettings():
    print("\n=== test_executor_theme_combo_change_writes_qsettings ===")
    from PyQt5.QtCore import QSettings
    app_settings().setValue(THEME_KEY, "dark")

    ex = PlanExecutor(make_data(), lambda: None)
    _show(ex)
    target = None
    for i in range(ex.theme_combo.count()):
        if ex.theme_combo.itemData(i) == "light":
            target = i
            break
    assert_true(target is not None, "找到 light 索引")

    ex.theme_combo.setCurrentIndex(target)
    saved = app_settings().value(THEME_KEY)
    assert_eq(saved, "light", "QSettings 写入 light")

    # 还原 dark
    for i in range(ex.theme_combo.count()):
        if ex.theme_combo.itemData(i) == "dark":
            ex.theme_combo.setCurrentIndex(i)
            break


def _find_btn(w, text):
    """按文字找按钮（v0.26 用：次要入口没有属性名了）"""
    from PyQt5.QtWidgets import QPushButton
    for b in w.findChildren(QPushButton):
        if b.text() == text:
            return b
    return None


# ============== v0.26 执行页顶端极简 ==============


def test_executor_top_bar_minimal_v026():
    print("\n=== test_executor_top_bar_minimal_v026 ===")
    ex = PlanExecutor(make_data(), lambda: None)
    _show(ex)
    # 顶栏默认只剩两个东西：「更多」+ 分类名
    assert_true(ex.advanced_toggle.isVisible(), "「更多」常驻可见")
    assert_true(ex.parent_combo_label.isVisible(), "分类名常驻可见")
    # 原来的次要入口全部收起
    assert_not_visible(ex.parent_switch_btn, "「切换分类」默认收起")
    assert_not_visible(ex.theme_combo, "主题下拉默认收起")
    assert_not_visible(_find_btn(ex, "← 返回制定"), "「返回制定」默认收起")


def test_executor_status_line_merged_v026():
    print("\n=== test_executor_status_line_merged_v026 ===")
    ex = PlanExecutor(make_data(), lambda: None)
    _show(ex)
    # 三行（日期/进度/今天完成）→ 两行（日期 + 一行状态）
    assert_true(hasattr(ex, "status_label"), "status_label 存在")
    assert_true(not hasattr(ex, "progress_label"), "旧 progress_label 已删掉")
    assert_true(not hasattr(ex, "done_label"), "旧 done_label 已删掉")
    text = ex.status_label.text()
    assert_true("进度" in text and "/" in text, f"状态行含进度：{text!r}")
    assert_true("今天完成" in text, f"状态行含今天完成：{text!r}")


def test_executor_more_reveals_minor_entries_v026():
    print("\n=== test_executor_more_reveals_minor_entries_v026 ===")
    ex = PlanExecutor(make_data(), lambda: None)
    _show(ex)
    ex.advanced_toggle.click()
    app.processEvents()
    assert_visible(ex.parent_switch_btn, "展开后「切换分类」可见")
    assert_visible(ex.theme_combo, "展开后主题下拉可见")
    assert_visible(_find_btn(ex, "← 返回制定"), "展开后「返回制定」可见")


def test_executor_today_done_goes_to_tooltip_v026():
    print("\n=== test_executor_today_done_goes_to_tooltip_v026 ===")
    ex = PlanExecutor(make_data(), lambda: None)
    _show(ex)
    # 什么都没完成时：0 条、tooltip 为空
    assert_true("今天完成 0 条" in ex.status_label.text(),
                f"空态：{ex.status_label.text()!r}")
    assert_eq(ex.status_label.toolTip(), "", "空态 tooltip 为空")
    # 完成一格（早1：A）→ 状态行计数 +1，内容进 tooltip 而不占版面
    ex.scheduler.complete_today_slot(0)
    ex.refresh()
    app.processEvents()
    assert_true("今天完成 1 条" in ex.status_label.text(),
                f"完成后：{ex.status_label.text()!r}")
    assert_true("A" in ex.status_label.toolTip(), f"tooltip 含已完成内容：{ex.status_label.toolTip()!r}")


# ============== v0.26b 每格只留一个按钮 ==============


def _visible_buttons(w):
    from PyQt5.QtWidgets import QPushButton
    return [b for b in w.findChildren(QPushButton) if b.isVisible()]


def test_slot_row_single_button_v026b():
    print("\n=== test_slot_row_single_button_v026b ===")
    ex = PlanExecutor(make_data(), lambda: None)
    _show(ex)
    ex.refresh()
    app.processEvents()
    trays = ex.findChildren(QWidget)
    rows = [t for t in trays
            if t.contextMenuPolicy() == Qt.CustomContextMenu and t.findChildren(QPushButton)]
    assert_true(len(rows) >= 1, f"找到格子行容器（{len(rows)} 个）")
    for i, row in enumerate(rows):
        vis = _visible_buttons(row)
        assert_eq(len(vis), 1, f"第 {i+1} 行常驻按钮只有 1 个")
        assert_eq(vis[0].text(), "✓ 完成并滚动", f"第 {i+1} 行留的是「✓ 完成并滚动」")


def test_slot_hidden_buttons_still_exist_v026b():
    print("\n=== test_slot_hidden_buttons_still_exist_v026b ===")
    ex = PlanExecutor(make_data(), lambda: None)
    _show(ex)
    ex.refresh()
    app.processEvents()
    # 次要按钮只是藏起来，不是删掉：还能点、还能生效（旧测试也靠这个）
    only = _find_btn(ex, "仅完成")
    assert_true(only is not None, "「仅完成」按钮还在（隐藏）")
    assert_true(not only.isVisible(), "「仅完成」默认不显示")
    assert_true(_find_btn(ex, "固定计划") is not None, "「固定计划」按钮还在")
    assert_true(_find_btn(ex, "拦截滚动") is not None, "「拦截滚动」按钮还在")
    # 点了照样生效：早1 的 A 变成「已完成（不滚动）」
    only.click()
    app.processEvents()
    assert_true(PlanScheduler(ex.data.current_parent).today_state()["row_done"][0],
                "点隐藏的「仅完成」→ 该格标记完成")


def test_slot_context_menu_actions_v026b():
    print("\n=== test_slot_context_menu_actions_v026b ===")
    ex = PlanExecutor(make_data(), lambda: None)
    _show(ex)
    ex.refresh()
    app.processEvents()
    menu = ex._build_slot_menu(ex, 0, False, False, False)
    texts = [a.text() for a in menu.actions() if not a.isSeparator()]
    assert_eq(texts, ["仅完成（不滚动）", "固定计划", "拦截滚动", "✓ 完成并滚动"],
              "右键菜单里能找回全部次要操作")
    # 已标记完成的那一格：仅完成 置灰，固定/拦截 文案变「取消…」
    menu2 = ex._build_slot_menu(ex, 0, True, True, True)
    texts2 = [a.text() for a in menu2.actions() if not a.isSeparator()]
    assert_eq(texts2, ["仅完成（不滚动）", "取消固定", "取消拦截", "✓ 完成并滚动"],
              "已固定/拦截时菜单文案改成「取消…」")
    assert_eq(menu2.actions()[0].isEnabled(), False, "已完成的格子「仅完成」置灰")


# ============== v0.27 额外安排按钮 0 条隐藏 + 队列一行化 ==============


def test_extra_button_hidden_at_zero_v027():
    print("\n=== test_extra_button_hidden_at_zero_v027 ===")
    ex = PlanExecutor(make_data(), lambda: None)
    _show(ex)
    assert_eq(ex.extra_btn.text(), "📋 额外安排（0）", "0 条：文案仍在（老测试照旧）")
    assert_true(not ex.extra_btn.isVisible(), "0 条：按钮不出现")
    ex.scheduler.borrow_next()
    ex.refresh()
    app.processEvents()
    assert_true(ex.extra_btn.isVisible(), "有 1 条：按钮冒出来")
    assert_true("额外安排（1）" in ex.extra_btn.text(), "有 1 条：文案带条数")


def test_queue_line_collapsed_v027():
    print("\n=== test_queue_line_collapsed_v027 ===")
    ex = PlanExecutor(make_data(), lambda: None)
    _show(ex)
    assert_true(ex.queue_toggle.isVisible(), "队列标题行常驻可见")
    assert_true("计划队列" in ex.queue_toggle.text(), f"标题文案：{ex.queue_toggle.text()!r}")
    assert_true("条" in ex.queue_toggle.text(), "标题带剩余条数")
    assert_not_visible(ex.queue_container, "队列默认收起")
    assert_not_visible(ex.calendar_area, "队列内容默认看不见")
    ex.queue_toggle.click()
    app.processEvents()
    assert_visible(ex.calendar_area, "点开后队列可见")
    assert_eq(ex.queue_toggle.arrowType(), Qt.DownArrow, "点开后箭头朝下")
    ex.queue_toggle.click()
    app.processEvents()
    assert_not_visible(ex.queue_container, "再点一次收起")


def test_queue_not_in_advanced_v027():
    print("\n=== test_queue_not_in_advanced_v027 ===")
    ex = PlanExecutor(make_data(), lambda: None)
    _show(ex)
    ex.advanced_toggle.click()
    app.processEvents()
    # 队列已经搬出「更多」了：展开「更多」也不该顺带把队列带出来
    assert_not_visible(ex.queue_container, "「更多」展开 ≠ 队列展开")
    names = [w.text() for w in ex.advanced_container.findChildren(QToolButton)]
    assert_true("计划队列 · 还有 5 条" not in names, "队列标题不在「更多」容器里")


# ============== v0.27b 制定页瘦身 ==============


def test_editor_more_collapsed_v027b():
    print("\n=== test_editor_more_collapsed_v027b ===")
    ed = PlanEditor(make_data(), lambda: None)
    _show(ed)
    assert_true(ed._more_toggle.isVisible(), "「⋯」常驻可见")
    assert_not_visible(ed._more_container, "重置/导入/导出/预览 默认收起")
    for name in ("reset_btn", "import_btn", "export_btn", "preview_btn"):
        assert_true(hasattr(ed, name), f"{name} 还在（只是藏起来）")
    ed._more_toggle.click()
    app.processEvents()
    assert_visible(ed.reset_btn, "展开后「重置」可见")
    assert_visible(ed.import_btn, "展开后「导入」可见")
    assert_visible(ed.export_btn, "展开后「导出」可见")
    assert_visible(ed.preview_btn, "展开后「预览」可见")


def test_editor_date_group_collapsed_v027b():
    print("\n=== test_editor_date_group_collapsed_v027b ===")
    ed = PlanEditor(make_data(), lambda: None)
    _show(ed)
    assert_eq(ed._date_toggle.isChecked(), False, "起始日期初始收起")
    assert_not_visible(ed._date_body, "日期选择器默认不可见")
    assert_true("▸" in ed._date_toggle.text(), "收起时显示 ▸")
    ed._date_toggle.click()
    app.processEvents()
    assert_visible(ed.date_edit, "展开后日期选择器可见")
    assert_true("▾" in ed._date_toggle.text(), "展开后显示 ▾")


def test_editor_main_actions_still_visible_v027b():
    print("\n=== test_editor_main_actions_still_visible_v027b ===")
    ed = PlanEditor(make_data(), lambda: None)
    _show(ed)
    # 主操作（保存并预览 / 开始执行）留在外面，不被折叠
    # （v0.30 R32：「生成计划」更名「保存并预览」，主样式让给「开始执行 →」）
    assert_visible(_find_btn(ed, "保存并预览"), "「保存并预览」常驻")
    assert_visible(_find_btn(ed, "开始执行 →"), "「开始执行 →」常驻")
    assert_not_visible(_find_btn(ed, "预览"), "「预览」已收进「⋯」")
    # 四个组（分类/计划/时段/日期）默认都是收起的
    for attr in ("_parent_toggle", "_plan_toggle", "_slot_toggle", "_date_toggle"):
        assert_eq(getattr(ed, attr).isChecked(), False, f"{attr} 默认收起")


# ============== v0.28 归档总览页瘦身 + 预览区按需出现 ==============


def _cal_data(archived=None):
    data = PlanData()
    p = data.parents[0]
    p.name = "备考"
    p.time_slots = [{"name": "早", "count": 1}, {"name": "中", "count": 1}]
    p.plans = ["电机学", "电力电子", "高电压"]
    p.start_date = QDate.currentDate()
    if archived:
        p.archived = list(archived)
        p.archived_base = 0
    data.current_parent_idx = 0
    return data


def test_calendar_more_collapsed_v028():
    print("\n=== test_calendar_more_collapsed_v028 ===")
    from calendar_view import PlanCalendarView
    cv = PlanCalendarView(_cal_data(archived=["电机学"]))
    cv.resize(520, 700)
    cv.show()
    app.processEvents()
    assert_true(cv.more_toggle.isVisible(), "「⋯」常驻可见")
    assert_not_visible(cv.more_container, "导出/全部展开 默认收起")
    assert_true(hasattr(cv, "export_btn"), "export_btn 还在（藏起来）")
    assert_true(hasattr(cv, "expand_all_btn"), "expand_all_btn 还在（藏起来）")
    cv.more_toggle.click()
    app.processEvents()
    assert_visible(cv.export_btn, "展开后「导出归档」可见")
    assert_visible(cv.expand_all_btn, "展开后「全部展开」可见")


def test_calendar_today_group_hidden_when_empty_v028():
    print("\n=== test_calendar_today_group_hidden_when_empty_v028 ===")
    from calendar_view import PlanCalendarView
    # 今天什么都没完成 → 这一块不出现
    cv = PlanCalendarView(_cal_data())
    cv.resize(520, 700)
    cv.show()
    app.processEvents()
    assert_true(not cv.today_group.isVisible(), "没完成时「今天完成」整组收起")
    # 有完成 → 冒出来
    cv2 = PlanCalendarView(_cal_data(archived=["电机学"]))
    cv2.resize(520, 700)
    cv2.show()
    app.processEvents()
    assert_true(cv2.today_group.isVisible(), "有完成时「今天完成」出现")


def test_editor_preview_hidden_until_used_v028():
    print("\n=== test_editor_preview_hidden_until_used_v028 ===")
    ed = PlanEditor(make_data(), lambda: None)
    _show(ed)
    assert_true(not ed.preview_area.isVisible(), "预览区默认不占版面")
    ed.preview_calendar()
    app.processEvents()
    assert_true(ed.preview_area.isVisible(), "点「预览」后预览区出现")
    assert_true(len(ed.preview_area.toPlainText()) > 0, "预览区有内容")


def main():
    test_editor_three_toggles_exist()
    test_editor_toggles_initially_collapsed()
    test_editor_toggle_expands_collapse()
    test_editor_toggles_independent()
    test_executor_advanced_toggle_exists()
    test_executor_advanced_initially_collapsed()
    test_executor_advanced_toggle_expands()
    test_executor_theme_combo_exists()
    test_executor_theme_combo_change_writes_qsettings()
    test_executor_top_bar_minimal_v026()
    test_executor_status_line_merged_v026()
    test_executor_more_reveals_minor_entries_v026()
    test_executor_today_done_goes_to_tooltip_v026()
    test_slot_row_single_button_v026b()
    test_slot_hidden_buttons_still_exist_v026b()
    test_slot_context_menu_actions_v026b()
    test_extra_button_hidden_at_zero_v027()
    test_queue_line_collapsed_v027()
    test_queue_not_in_advanced_v027()
    test_editor_more_collapsed_v027b()
    test_editor_date_group_collapsed_v027b()
    test_editor_main_actions_still_visible_v027b()
    test_calendar_more_collapsed_v028()
    test_calendar_today_group_hidden_when_empty_v028()
    test_editor_preview_hidden_until_used_v028()
    print(f"\n=== ALL TESTS PASSED ({PASS_COUNT} assertions) ===")


if __name__ == "__main__":
    main()
