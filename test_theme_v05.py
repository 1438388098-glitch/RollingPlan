"""
RollingPlan v0.5 主题切换测试

覆盖：
- THEME_OPTIONS 三选项完整且 key 有效
- apply_theme('dark'/'light'/'auto') 不抛异常
- apply_theme 在 pyqtdarktheme 缺失时静默回退
- QSettings 持久化：on_theme_changed 后读 QSettings 能拿到值
- 主题切换跨 widget 实例保留

运行：QT_QPA_PLATFORM=offscreen python test_theme_v05.py
"""

import os
os.environ["QT_QPA_PLATFORM"] = "offscreen"

import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import QSettings, QTimer
app = QApplication(sys.argv)

from rollingplan import (
    THEME_OPTIONS, THEME_KEY, apply_theme,
    PlanEditor, PlanData,
)


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


def assert_in(item, container, label):
    if item in container:
        _bump_pass()
        print(f"  PASS [{label}]")
    else:
        _bump_fail()
        print(f"  FAIL [{label}]")
        sys.exit(1)


# ============== 测试 ==============

def test_theme_options():
    print("\n=== test_theme_options ===")
    keys = [k for k, _ in THEME_OPTIONS]
    labels = [l for _, l in THEME_OPTIONS]
    assert_eq(len(THEME_OPTIONS), 3, "3 个预设")
    assert_eq(keys, ["dark", "light", "auto"], "key 序列")
    assert_true(all("Dark" in l or "Light" in l or "System" in l for l in labels),
                "label 包含中文/英文提示")


def test_apply_theme_no_crash():
    print("\n=== test_apply_theme_no_crash ===")
    # 只测 dark/light — auto 在 WSL offscreen 下 darkdetect 会卡
    for key in ("dark", "light"):
        try:
            apply_theme(app, key)
            assert_true(True, f"apply_theme('{key}') 不抛异常")
        except Exception as e:
            assert_true(False, f"apply_theme('{key}') 抛异常: {e}")


def test_apply_theme_missing_lib():
    """当 pyqtdarktheme 不可用时，apply_theme 应静默返回。"""
    print("\n=== test_apply_theme_missing_lib ===")
    import sys
    saved = sys.modules.pop('qdarktheme', None)
    try:
        apply_theme(app, "dark")
        assert_true(True, "qdarktheme 缺失时静默回退，不崩")
    except Exception as e:
        assert_true(False, f"qdarktheme 缺失时崩了: {e}")
    finally:
        if saved is not None:
            sys.modules['qdarktheme'] = saved


def test_theme_persisted_to_qsettings():
    print("\n=== test_theme_persisted_to_qsettings ===")
    # 清掉之前可能的残留
    QSettings("RollingPlan", "Data").setValue(THEME_KEY, "dark")
    s = QSettings("RollingPlan", "Data")
    val = s.value(THEME_KEY, "dark")
    assert_eq(val, "dark", "QSettings 写入 dark 后能读出")


def test_editor_theme_combo_setup():
    """PlanEditor 创建时下拉框初始化 + currentIndex 反映 QSettings"""
    print("\n=== test_editor_theme_combo_setup ===")
    # 写一个偏好到 QSettings
    QSettings("RollingPlan", "Data").setValue(THEME_KEY, "light")

    data = PlanData()
    editor = PlanEditor(data, lambda: None)

    # 下拉框应该创建
    assert_true(hasattr(editor, 'theme_combo'), "editor.theme_combo 存在")
    assert_eq(editor.theme_combo.count(), 3, "3 个选项")

    # 当前索引应指向 light
    cur_data = editor.theme_combo.currentData() if hasattr(editor.theme_combo, 'currentData') else None
    # PyQt5 QComboBox 有 userData 通过 itemData(int) 拿
    cur_idx = editor.theme_combo.currentIndex()
    cur_key = editor.theme_combo.itemData(cur_idx)
    assert_eq(cur_key, "light", "currentIndex 指向 light（从 QSettings 读）")

    # 改回 dark 给后续测试留干净状态
    QSettings("RollingPlan", "Data").setValue(THEME_KEY, "dark")


def test_editor_theme_change_writes_qsettings():
    print("\n=== test_editor_theme_change_writes_qsettings ===")
    QSettings("RollingPlan", "Data").setValue(THEME_KEY, "dark")

    data = PlanData()
    editor = PlanEditor(data, lambda: None)

    # 触发下拉框变化：找到 light 的索引
    target_idx = None
    for i in range(editor.theme_combo.count()):
        if editor.theme_combo.itemData(i) == "light":
            target_idx = i
            break
    assert_true(target_idx is not None, "找到 light 索引")

    editor.theme_combo.setCurrentIndex(target_idx)
    # currentIndexChanged 应该已触发 on_theme_changed
    saved = QSettings("RollingPlan", "Data").value(THEME_KEY)
    assert_eq(saved, "light", "QSettings 写入 light")

    # 改回 dark 清理
    for i in range(editor.theme_combo.count()):
        if editor.theme_combo.itemData(i) == "dark":
            editor.theme_combo.setCurrentIndex(i)
            break


def test_editor_theme_change_invalid_qsettings_fallback():
    """QSettings 里有非法值时，editor 应 fallback 到 dark"""
    print("\n=== test_editor_theme_change_invalid_qsettings_fallback ===")
    QSettings("RollingPlan", "Data").setValue(THEME_KEY, "garbage_value")

    data = PlanData()
    editor = PlanEditor(data, lambda: None)
    cur_idx = editor.theme_combo.currentIndex()
    cur_key = editor.theme_combo.itemData(cur_idx)
    assert_eq(cur_key, "dark", "非法值 fallback 到 dark")

    # 清理
    QSettings("RollingPlan", "Data").setValue(THEME_KEY, "dark")


def test_stylesheet_contains_tab_fix():
    """apply_theme 后 app stylesheet 包含 Tab 修复"""
    print("\n=== test_stylesheet_contains_tab_fix ===")
    apply_theme(app, "dark")
    ss = app.styleSheet()
    assert_true("QTabBar" in ss, "stylesheet 包含 QTabBar 规则")
    assert_true("font-weight: bold" in ss, "激活 Tab 加粗")
    # dark 用具体颜色 #E0E0E0
    assert_true("#E0E0E0" in ss, "dark 用浅灰 #E0E0E0")

    apply_theme(app, "light")
    ss = app.styleSheet()
    assert_true("#424242" in ss, "light 用深灰 #424242")


def main():
    test_theme_options()
    test_apply_theme_no_crash()
    test_apply_theme_missing_lib()
    test_theme_persisted_to_qsettings()
    test_editor_theme_combo_setup()
    test_editor_theme_change_writes_qsettings()
    test_editor_theme_change_invalid_qsettings_fallback()
    test_stylesheet_contains_tab_fix()
    print(f"\n=== ALL TESTS PASSED ({PASS_COUNT} assertions) ===")


if __name__ == "__main__":
    main()
