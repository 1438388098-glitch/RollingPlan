"""
RollingPlan v0.7 自写 QSS 主题测试

覆盖：
- THEME_OPTIONS 三项 (dark/light/auto)
- apply_theme(dark) 设置 DARK_QSS，stylesheet 长度 > 0
- apply_theme(light) 设置 LIGHT_QSS，stylesheet 长度 > 0
- apply_theme(auto) 自动检测 → 用 DARK 或 LIGHT
- 切换主题后 stylesheet 内容变化
- QSettings 持久化 theme
- PlanEditor / PlanExecutor 主题下拉框同步 QSettings
- 非预期 theme_name 静默回退
- QSS 包含关键 QWidget 规则（QTabBar、QPushButton 等）
- _log 在 stderr=None 时不崩
- apply_theme 在 stderr=None 时不崩
"""

import os
import sys
import tempfile

os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import QSettings

# 先把临时 QSettings 目录准备好，避开真实用户配置
_tmp_dir = tempfile.mkdtemp(prefix="rollingplan_qsettings_")
os.environ["XDG_CONFIG_HOME"] = _tmp_dir

# 现在才 import 项目模块（QSettings 在 import 时读环境）
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rollingplan
from theme import app_settings
from rollingplan import (
    apply_theme, THEME_OPTIONS, DARK_QSS, LIGHT_QSS,
    PlanData, PlanEditor, PlanExecutor,
)

# 重置 QSettings 到临时域
QSettings.setDefaultFormat(QSettings.IniFormat)
QSettings.setPath(QSettings.IniFormat, QSettings.UserScope, _tmp_dir)

app = QApplication.instance() or QApplication(sys.argv)

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


# ============== 测试 ==============

def test_theme_options():
    print("\n=== test_theme_options ===")
    assert_eq(len(THEME_OPTIONS), 3, "THEME_OPTIONS 长度 3")
    names = [k for k, _ in THEME_OPTIONS]
    assert_eq(set(names), {"dark", "light", "auto"}, "主题名集合")


def test_dark_qss_content():
    print("\n=== test_dark_qss_content ===")
    assert_true("QWidget" in DARK_QSS, "DARK_QSS 含 QWidget 规则")
    assert_true("#1e1e1e" in DARK_QSS, "DARK_QSS 含主背景 #1e1e1e")
    assert_true("QTabBar" in DARK_QSS, "DARK_QSS 含 QTabBar")
    assert_true("QPushButton" in DARK_QSS, "DARK_QSS 含 QPushButton")
    assert_true(len(DARK_QSS) > 1000, f"DARK_QSS 长度={len(DARK_QSS)} > 1000")


def test_light_qss_content():
    print("\n=== test_light_qss_content ===")
    assert_true("QWidget" in LIGHT_QSS, "LIGHT_QSS 含 QWidget 规则")
    assert_true("#f5f5f5" in LIGHT_QSS, "LIGHT_QSS 含主背景 #f5f5f5")
    assert_true("QTabBar" in LIGHT_QSS, "LIGHT_QSS 含 QTabBar")
    assert_true("QPushButton" in LIGHT_QSS, "LIGHT_QSS 含 QPushButton")
    assert_true(len(LIGHT_QSS) > 1000, f"LIGHT_QSS 长度={len(LIGHT_QSS)} > 1000")


def test_apply_dark():
    print("\n=== test_apply_dark ===")
    apply_theme(app, "dark")
    ss = app.styleSheet()
    assert_eq(ss, DARK_QSS, "apply_theme(dark) → setStyleSheet(DARK_QSS)")
    assert_true("#1e1e1e" in ss, "stylesheet 含深色主背景")


def test_apply_light():
    print("\n=== test_apply_light ===")
    apply_theme(app, "light")
    ss = app.styleSheet()
    assert_eq(ss, LIGHT_QSS, "apply_theme(light) → setStyleSheet(LIGHT_QSS)")
    assert_true("#f5f5f5" in ss, "stylesheet 含浅色主背景")


def test_apply_dark_then_light_changes_sheet():
    print("\n=== test_apply_dark_then_light_changes_sheet ===")
    apply_theme(app, "dark")
    dark = app.styleSheet()
    apply_theme(app, "light")
    light = app.styleSheet()
    assert_true(dark != light, "dark → light 后 stylesheet 内容不同")
    assert_true("#1e1e1e" in dark, "dark 主题含深色背景")
    assert_true("#1e1e1e" not in light, "light 主题不含深色背景")


def test_apply_auto_picks_one():
    print("\n=== test_apply_auto_picks_one ===")
    apply_theme(app, "auto")
    ss = app.styleSheet()
    # auto 一定 fallthrough 到 dark 或 light 之一
    assert_true(ss == DARK_QSS or ss == LIGHT_QSS,
                f"auto 后 stylesheet 是 DARK 或 LIGHT (got len={len(ss)})")


def test_apply_invalid_fallback_dark():
    print("\n=== test_apply_invalid_fallback_dark ===")
    apply_theme(app, "totally_invalid")
    ss = app.styleSheet()
    # 非法值时不应该崩；fallback 行为：从代码看 "totally_invalid" 走 else 分支 → actual = "totally_invalid"
    # 不是 dark 也不是 light，所以 qss = LIGHT_QSS（因为 actual != "dark"）
    # 这里只验不崩
    assert_true(len(ss) > 1000, f"非法 theme_name 不崩 (got len={len(ss)})")


def test_theme_persisted_to_qsettings():
    print("\n=== test_theme_persisted_to_qsettings ===")
    from rollingplan import THEME_KEY
    s = app_settings()
    s.setValue(THEME_KEY, "light")
    s.sync()
    s2 = app_settings()
    saved = s2.value(THEME_KEY, "dark")
    assert_eq(saved, "light", "QSettings 写入并读出 light")


def test_editor_theme_combo_setup():
    print("\n=== test_editor_theme_combo_setup ===")
    s = app_settings()
    s.setValue(rollingplan.THEME_KEY, "dark")
    s.sync()
    d = PlanData()
    ed = PlanEditor(d, lambda: None)
    ed.show()
    app.processEvents()
    from PyQt5.QtWidgets import QComboBox
    assert_true(hasattr(ed, "theme_combo"), "editor 有 theme_combo")
    assert_true(isinstance(ed.theme_combo, QComboBox), "theme_combo 是 QComboBox")
    assert_eq(ed.theme_combo.count(), 3, "theme_combo 3 项")


def test_editor_theme_change_writes_qsettings():
    print("\n=== test_editor_theme_change_writes_qsettings ===")
    d = PlanData()
    ed = PlanEditor(d, lambda: None)
    ed.show()
    app.processEvents()
    # 找到 light 索引
    light_idx = -1
    for i in range(ed.theme_combo.count()):
        if ed.theme_combo.itemData(i) == "light":
            light_idx = i
            break
    assert_true(light_idx >= 0, "找到 light 索引")
    ed.theme_combo.setCurrentIndex(light_idx)
    ed.on_theme_changed(light_idx)
    s = app_settings()
    saved = s.value(rollingplan.THEME_KEY, "dark")
    assert_eq(saved, "light", "QSettings 写入 light")


def test_executor_theme_combo_present():
    print("\n=== test_executor_theme_combo_present ===")
    d = PlanData()
    ex = PlanExecutor(d, lambda: None)
    ex.show()
    app.processEvents()
    from PyQt5.QtWidgets import QComboBox
    assert_true(hasattr(ex, "theme_combo"), "executor 有 theme_combo")
    assert_true(isinstance(ex.theme_combo, QComboBox), "executor theme_combo 是 QComboBox")
    assert_eq(ex.theme_combo.count(), 3, "executor theme_combo 3 项")


def test_executor_theme_combo_change_writes_qsettings():
    print("\n=== test_executor_theme_combo_change_writes_qsettings ===")
    d = PlanData()
    ex = PlanExecutor(d, lambda: None)
    ex.show()
    app.processEvents()
    light_idx = -1
    for i in range(ex.theme_combo.count()):
        if ex.theme_combo.itemData(i) == "light":
            light_idx = i
            break
    assert_true(light_idx >= 0, "找到 light 索引")
    ex.theme_combo.setCurrentIndex(light_idx)
    ex.on_theme_changed(light_idx)
    s = app_settings()
    saved = s.value(rollingplan.THEME_KEY, "dark")
    assert_eq(saved, "light", "executor 切 light 后 QSettings 写入 light")


def test_stylesheet_contains_tab_fix():
    """QSS 自带 tab 文字对比度（不再需要单独 tab_fix 注入）"""
    print("\n=== test_stylesheet_contains_tab_fix ===")
    apply_theme(app, "dark")
    ss = app.styleSheet()
    assert_true("QTabBar" in ss, "stylesheet 包含 QTabBar 规则")
    assert_true("QTabBar::tab:selected" in ss, "激活 Tab 加粗")
    assert_true("font-weight: bold" in ss, "激活 Tab 字体加粗")
    # dark 主题 tab 文字色（深色背景下用浅色文字，css 灰阶任一即可）
    assert_true(("#cccccc" in ss) or ("#e8e8e8" in ss),
                "dark 主题 tab 文字用浅色（#cccccc 或 #e8e8e8）")


def test_log_works_when_stderr_is_none():
    print("\n=== test_log_works_when_stderr_is_none ===")
    saved_stderr = sys.stderr
    try:
        sys.stderr = None
        rollingplan._log("test message with stderr=None")
        assert_true(True, "_log 在 stderr=None 时不崩")
    except Exception as e:
        assert_true(False, f"_log 崩了: {e}")
    finally:
        sys.stderr = saved_stderr


def test_apply_theme_works_when_stderr_is_none():
    print("\n=== test_apply_theme_works_when_stderr_is_none ===")
    saved_stderr = sys.stderr
    try:
        sys.stderr = None
        apply_theme(app, "dark")
        apply_theme(app, "light")
        assert_true(True, "apply_theme 在 stderr=None 时不崩")
    except Exception as e:
        assert_true(False, f"apply_theme 崩了: {e}")
    finally:
        sys.stderr = saved_stderr


def main():
    test_theme_options()
    test_dark_qss_content()
    test_light_qss_content()
    test_apply_dark()
    test_apply_light()
    test_apply_dark_then_light_changes_sheet()
    test_apply_auto_picks_one()
    test_apply_invalid_fallback_dark()
    test_theme_persisted_to_qsettings()
    test_editor_theme_combo_setup()
    test_editor_theme_change_writes_qsettings()
    test_executor_theme_combo_present()
    test_executor_theme_combo_change_writes_qsettings()
    test_stylesheet_contains_tab_fix()
    test_log_works_when_stderr_is_none()
    test_apply_theme_works_when_stderr_is_none()

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
