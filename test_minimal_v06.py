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

from PyQt5.QtWidgets import QApplication
app = QApplication(sys.argv)

from rollingplan import (
    PlanEditor, PlanExecutor, PlanData,
    THEME_OPTIONS, THEME_KEY,
)
from PyQt5.QtCore import QDate


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
    QSettings("RollingPlan", "Data").setValue(THEME_KEY, "dark")

    ex = PlanExecutor(make_data(), lambda: None)
    _show(ex)
    target = None
    for i in range(ex.theme_combo.count()):
        if ex.theme_combo.itemData(i) == "light":
            target = i
            break
    assert_true(target is not None, "找到 light 索引")

    ex.theme_combo.setCurrentIndex(target)
    saved = QSettings("RollingPlan", "Data").value(THEME_KEY)
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
    print(f"\n=== ALL TESTS PASSED ({PASS_COUNT} assertions) ===")


if __name__ == "__main__":
    main()
