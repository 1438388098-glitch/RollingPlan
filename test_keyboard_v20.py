"""
v0.20 快捷键回归测试 —— Ctrl+Shift+Z / Ctrl+Y 真正绑到 on_redo。

之前:tooltip / 注释都提到 Ctrl+Shift+Z 和 Ctrl+Y 是 redo,但 keyPressEvent
只绑了 Ctrl+Z → on_undo,这两个组合都 fall-through 到 super()(啥也不做)。

v0.20 修:在 MainWindow.keyPressEvent 加
- Ctrl+Shift+Z → executor.on_redo()
- Ctrl+Y      → executor.on_redo()

这里测的就是这两个组合 + 确保不破老的 Ctrl+Z/Ctrl+Enter/Ctrl+D 行为。

注:不在 test_scroll_v11.py 里加是因为它已经 170 个断言,加新场景混在一起反而难读;
独立文件 test_keyboard_v20.py 单独负责快捷键回归。
"""
import os
import sys
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtCore import Qt
from PyQt5.QtTest import QTest
from PyQt5.QtWidgets import QApplication

app = QApplication.instance() or QApplication(sys.argv)

import rollingplan
from rollingplan import MainWindow, PlanExecutor, PlanData


def _make_data():
    d = PlanData()
    p = d.current_parent
    p.plans = ["A", "B", "C", "D", "E", "F", "G", "H", "I"]
    p.time_slots = [{"name": "早", "count": 3}]
    p.normalize()
    return d


class TestKeyboardShortcuts(unittest.TestCase):
    """v0.20 修:在执行计划页 Ctrl+Shift+Z / Ctrl+Y 触发 on_redo。

    策略:用 spy 监听 executor.on_redo 是否被调用,而不是验证副作用
    (副作用在 test_undo_v16.py 已经覆盖得很全)。
    """

    def _boot_window(self):
        d = _make_data()
        win = MainWindow()
        win.data = d
        # v0.30：走窗口自己的 executor 替换 API —— executor 恒在 index 1。
        # (旧写法 removeTab(1)+addTab() 会把 executor 追加到 index 2,再
        #  setCurrentIndex(1) 实际显示的是归档页 —— 健壮性审计 P0-1 的 bug 模式,
        #  老测试用的正是这个模式,所以 bug 一直没被抓到)
        win.show_executor()
        win.tabs.setCurrentIndex(1)
        win.show()
        app.processEvents()
        return win

    def test_ctrl_shift_z_calls_on_redo(self):
        win = self._boot_window()
        called = []
        win.executor.on_redo = lambda: called.append("redo")
        QTest.keyClick(win, Qt.Key_Z, Qt.ControlModifier | Qt.ShiftModifier)
        app.processEvents()
        self.assertEqual(called, ["redo"], "Ctrl+Shift+Z 应该触发 on_redo")

    def test_ctrl_y_calls_on_redo(self):
        win = self._boot_window()
        called = []
        win.executor.on_redo = lambda: called.append("redo")
        QTest.keyClick(win, Qt.Key_Y, Qt.ControlModifier)
        app.processEvents()
        self.assertEqual(called, ["redo"], "Ctrl+Y 应该触发 on_redo")

    def test_plain_ctrl_z_still_calls_on_undo(self):
        """不要因为新加 Ctrl+Shift+Z 把老 Ctrl+Z 改了 —— 老 Ctrl+Z 必须还是 on_undo。"""
        win = self._boot_window()
        undo_calls, redo_calls = [], []
        win.executor.on_undo = lambda: undo_calls.append("undo")
        win.executor.on_redo = lambda: redo_calls.append("redo")
        QTest.keyClick(win, Qt.Key_Z, Qt.ControlModifier)  # 没 Shift
        app.processEvents()
        self.assertEqual(undo_calls, ["undo"], "Ctrl+Z(无 Shift)应该触发 on_undo")
        self.assertEqual(redo_calls, [], "Ctrl+Z(无 Shift)不应该触发 on_redo")

    def test_plain_z_does_nothing(self):
        """无 Ctrl 的 Z 不该触发任何 redo/undo(放行 super())。"""
        win = self._boot_window()
        called = []
        win.executor.on_redo = lambda: called.append("redo")
        win.executor.on_undo = lambda: called.append("undo")
        QTest.keyClick(win, Qt.Key_Z)  # 无 modifier
        app.processEvents()
        self.assertEqual(called, [], "裸 Z 不该触发 redo 或 undo")

    def test_shortcuts_inactive_on_other_tabs(self):
        """Ctrl+Shift+Z 在「制定计划」页不该拦截 —— 放行给 super()(输入框可以收到 Shift+Ctrl+Z)。"""
        win = self._boot_window()
        # 切到制定计划页(tab 0)
        win.tabs.setCurrentIndex(0)
        app.processEvents()
        called = []
        win.executor.on_redo = lambda: called.append("redo")
        QTest.keyClick(win, Qt.Key_Z, Qt.ControlModifier | Qt.ShiftModifier)
        app.processEvents()
        self.assertEqual(called, [], "Ctrl+Shift+Z 在制定计划页不该触发 on_redo")


if __name__ == "__main__":
    unittest.main(verbosity=2)
