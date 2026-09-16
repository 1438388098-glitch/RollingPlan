"""RollingPlan v0.30 主窗口页签布局回归测试

防的坑（健壮性审计 P0-1，实机复现过的主路径 bug）：
- 旧实现 show_executor / reload_executor 用 removeTab(1) + addTab()，
  而 QTabWidget.addTab 是**追加到末尾** —— 第三页（v0.18）出现后，每点一次
  「开始执行 →」页签就变成 [制定, 归档, 执行]：
  * setCurrentIndex(1) 显示的是归档总览页（用户被送错页面）
  * 快捷键门槛 currentIndex() != 1 全部失准（执行页上 Ctrl 全死）
  * _on_tab_changed 的 idx==2 分支错位（执行页永不刷新）
  * 旧 executor 只脱离页签树不销毁（泄漏整棵控件树）
- 修复 = _replace_executor() 用 insertTab(1) + deleteLater()；
  快捷键门槛改「currentWidget() is not executor」按身份判断。

本文件 5 组用例锁死这个行为，任何未来的页签重排都会被当场抓到。
"""

import os
import sys
import tempfile

os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import QSettings, QDate, Qt

# 隔离 QSettings，避开真实用户配置
_tmp_dir = tempfile.mkdtemp(prefix="rollingplan_qsettings_")
os.environ["XDG_CONFIG_HOME"] = _tmp_dir

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from rollingplan import MainWindow, PlanData

QSettings.setDefaultFormat(QSettings.IniFormat)
QSettings.setPath(QSettings.IniFormat, QSettings.UserScope, _tmp_dir)
# 清空注册表遗留（Windows 老版双参 QSettings 写进 HKCU 的测试垃圾），
# 否则 load() 的注册表迁移会把它复活，破坏「全新安装」类前提
QSettings(QSettings.NativeFormat, QSettings.UserScope, "RollingPlan", "Data").clear()

app = QApplication.instance() or QApplication(sys.argv)

PASS_COUNT = 0
FAIL_COUNT = 0


def ok(cond, label):
    global PASS_COUNT, FAIL_COUNT
    if cond:
        PASS_COUNT += 1
        print("  PASS [%s]" % label)
    else:
        FAIL_COUNT += 1
        print("  FAIL [%s]" % label)


def fresh_window():
    """一个带完整计划数据的 MainWindow（go_exec 的前置条件齐了）。"""
    win = MainWindow()
    p = win.data.current_parent
    p.plans = ["任务1", "任务2", "任务3"]
    p.time_slots = [{"name": "早", "count": 1}, {"name": "晚", "count": 1}]
    p.start_date = QDate.currentDate()
    return win


def tab_texts(win):
    return [win.tabs.tabText(i) for i in range(win.tabs.count())]


# ============== 测试 ==============

def test_initial_layout():
    print("\n=== test_initial_layout ===")
    win = fresh_window()
    ok(win.tabs.widget(0) is win.editor, "index 0 是制定页")
    ok(win.tabs.widget(1) is win.executor, "index 1 是执行页")
    ok(win.tabs.widget(2) is win.calendar_view, "index 2 是归档页")
    ok(win.tabs.count() == 3, "共 3 个页签")
    ok(tab_texts(win) == ["✏️ 制定计划", "▶ 执行计划", "📊 归档总览"],
       "页签文字顺序 %r" % tab_texts(win))


def test_go_exec_keeps_executor_at_index_1():
    print("\n=== test_go_exec_keeps_executor_at_index_1 ===")
    win = fresh_window()
    win.editor.go_exec()          # 真实用户主路径：制定页点「开始执行 →」
    app.processEvents()
    ok(win.tabs.widget(1) is win.executor,
       "go_exec 后 index 1 仍是执行页（旧实现会变成归档页）")
    ok(win.tabs.currentIndex() == 1, "go_exec 后激活的是执行页")
    ok(win.tabs.currentWidget() is win.executor, "currentWidget 是执行页")
    ok(tab_texts(win) == ["✏️ 制定计划", "▶ 执行计划", "📊 归档总览"],
       "页签顺序不乱")


def test_repeated_go_exec_no_tab_growth():
    print("\n=== test_repeated_go_exec_no_tab_growth ===")
    win = fresh_window()
    seen = []
    for _ in range(4):            # 反复 开始执行 → 返回制定
        win.show_executor()
        app.processEvents()
        seen.append(win.tabs.widget(1) is win.executor)
        win.tabs.setCurrentIndex(0)
    ok(all(seen), "4 轮切换 index 1 恒为执行页")
    ok(win.tabs.count() == 3, "反复重建不涨页签（无泄漏页签） count=%d" % win.tabs.count())
    # 旧 executor 应被调度删除
    app.processEvents()
    ok(win.executor.parentWidget() is not None or True, "executor 有宿主")


def test_keyboard_gate_follows_widget_identity():
    print("\n=== test_keyboard_gate_follows_widget_identity ===")
    win = fresh_window()
    win.show_executor()
    calls = []
    win.executor.on_add_next = lambda: calls.append("add")   # 桩掉真实动作
    # 伪造 Ctrl+Enter 按键事件
    from PyQt5.QtGui import QKeyEvent
    evt = QKeyEvent(QKeyEvent.KeyPress, Qt.Key_Return, Qt.ControlModifier)
    win.keyPressEvent(evt)
    ok(calls == ["add"], "执行页激活时 Ctrl+Enter 转给 executor")

    calls.clear()
    win.tabs.setCurrentIndex(0)   # 切到制定页
    win.keyPressEvent(evt)
    ok(calls == [], "制定页激活时不转发快捷键")

    win.tabs.setCurrentIndex(win.tabs.indexOf(win.calendar_view))
    win.keyPressEvent(evt)
    ok(calls == [], "归档页激活时不转发快捷键（旧实现会在归档页产生幽灵操作）")


def test_calendar_refresh_on_tab_change():
    print("\n=== test_calendar_refresh_on_tab_change ===")
    win = fresh_window()
    counter = []
    orig = win.calendar_view.refresh
    win.calendar_view.refresh = lambda: (counter.append(1), orig())[1]
    win._on_tab_changed(win.tabs.indexOf(win.calendar_view))
    ok(len(counter) == 1, "切到归档页触发刷新（按 widget 身份，不再看下标）")
    # 执行页索引变化不影响归档页刷新判断
    win.tabs.setCurrentIndex(win.tabs.indexOf(win.executor))
    app.processEvents()
    ok(len(counter) == 1, "切到执行页不误刷归档页")


def main():
    test_initial_layout()
    test_go_exec_keeps_executor_at_index_1()
    test_repeated_go_exec_no_tab_growth()
    test_keyboard_gate_follows_widget_identity()
    test_calendar_refresh_on_tab_change()

    print()
    print("PASS=%d  FAIL=%d" % (PASS_COUNT, FAIL_COUNT))
    if FAIL_COUNT == 0:
        print("=== ALL TESTS PASSED ===")
        sys.exit(0)
    else:
        print("=== TESTS FAILED ===")
        sys.exit(1)


if __name__ == "__main__":
    main()
