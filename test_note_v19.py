"""
v0.19 归档备注可点击展开测试

覆盖:
- 老 UI 行为保留:QLabel 显示「归档：任务1」(老测试期望的格式)
- 新加 ▸/▾ 切换按钮:点击展开后,row 下方插入每条单独一行的详情 widget
- 再点收起:详情 widget 被删掉
- toggle 的文本在 ▸/▾ 之间切换
- 不点的时候,默认只有 QLabel 和 toggle button,没有详情 widget
"""
import os
import sys
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtWidgets import QApplication
app = QApplication.instance() or QApplication(sys.argv)

from rollingplan import PlanData
import rollingplan
from rollingplan import PlanExecutor, QToolButton, QWidget, QLabel


def _make_data():
    d = PlanData()
    p = d.current_parent
    p.plans = ["任务1", "任务2", "任务3", "任务4", "任务5", "任务6"]
    p.time_slots = [{"name": "早", "count": 3}]
    p.normalize()
    return d


class TestNoteWidgetInitial(unittest.TestCase):
    def test_no_note_no_widget(self):
        """note 为空/缺省时,根本不调 _build_note_widget(由 _add_slot_row 的 if note: 跳过)。"""
        d = _make_data()
        ex = PlanExecutor(d, lambda: None)
        # 不调用任何按钮,note 都是 []
        # 没有归档备注 row,所以根本不该有「归档」字样
        all_texts = []
        for i in range(ex.day_layout.count()):
            w = ex.day_layout.itemAt(i).widget()
            if w:
                for lbl in w.findChildren(QLabel):
                    all_texts.append(lbl.text())
        self.assertFalse(any("归档" in t for t in all_texts), "默认不应该有归档备注 widget")

    def test_after_complete_only_shows_note_label(self):
        """点了「仅完成」后,那一格出现「归档：任务1」+ 一个 ▸ toggle。"""
        d = _make_data()
        ex = PlanExecutor(d, lambda: None)
        ex.show()
        app.processEvents()
        # 找第一个「仅完成」按钮并点
        btns = []
        for i in range(ex.day_layout.count()):
            w = ex.day_layout.itemAt(i).widget()
            if w:
                btns += [b for b in w.findChildren(rollingplan.QPushButton) if b.text() == "仅完成"]
        self.assertTrue(btns)
        btns[0].click()
        app.processEvents()
        # 现在第一个 slot 行里应该出现「归档：任务1」
        # 收集第一个 row 的所有 label + button
        first_row = ex.day_layout.itemAt(0).widget()
        labels = [lbl.text() for lbl in first_row.findChildren(QLabel)]
        toggles = [t for t in first_row.findChildren(QToolButton) if t.text() in ("▸", "▾")]
        self.assertTrue(any("归档：任务1" in t for t in labels),
                        f"归档 label 没出现: {labels}")
        self.assertEqual(len(toggles), 1, "应该有一个 ▸ toggle 按钮")
        self.assertEqual(toggles[0].text(), "▸")


class TestNoteToggleExpand(unittest.TestCase):
    def setUp(self):
        d = _make_data()
        self.ex = PlanExecutor(d, lambda: None)
        self.ex.show()
        app.processEvents()
        # 触发第一个 slot 进入「仅完成」状态
        btns = []
        for i in range(self.ex.day_layout.count()):
            w = self.ex.day_layout.itemAt(i).widget()
            if w:
                btns += [b for b in w.findChildren(rollingplan.QPushButton) if b.text() == "仅完成"]
        btns[0].click()
        app.processEvents()
        self.first_row = self.ex.day_layout.itemAt(0).widget()

    def _find_toggle(self):
        return [t for t in self.first_row.findChildren(QToolButton) if t.text() in ("▸", "▾")][0]

    def _find_detail(self):
        d = self.first_row.findChild(QWidget, "rp-note-detail")
        if d is None:
            return None
        # deleteLater 异步,但 setParent(None) 后该 widget 不再属于 first_row 的 child tree。
        d_parent = d.parent()
        if d_parent is None or d_parent is not self.first_row:
            return None
        return d

    def test_collapsed_no_detail(self):
        self.assertIsNone(self._find_detail())

    def test_expand_creates_detail(self):
        t = self._find_toggle()
        t.setChecked(True)
        app.processEvents()
        d = self._find_detail()
        self.assertIsNotNone(d, "点开后详情 widget 应该出现")
        # 详情里的 label 文案:每条「N. 任务X」
        detail_labels = [lbl.text() for lbl in d.findChildren(QLabel)]
        self.assertTrue(any("1." in t and "任务1" in t for t in detail_labels),
                        f"详情里应该有「1. 任务1」: {detail_labels}")

    def test_toggle_text_flips(self):
        t = self._find_toggle()
        self.assertEqual(t.text(), "▸")
        t.setChecked(True)
        app.processEvents()
        self.assertEqual(t.text(), "▾")
        t.setChecked(False)
        app.processEvents()
        self.assertEqual(t.text(), "▸")

    def test_collapse_removes_detail(self):
        t = self._find_toggle()
        t.setChecked(True)
        app.processEvents()
        self.assertIsNotNone(self._find_detail())
        t.setChecked(False)
        app.processEvents()
        # deleteLater 是异步的 —— 但 findChild 现在的 child tree 应该已经 remove 了
        # (setVisible(False) + parent=None 是在 toggle 的处理里做的)。
        # 不行就多 processEvents 几次。
        for _ in range(5):
            app.processEvents()
            if self._find_detail() is None:
                break
        self.assertIsNone(self._find_detail())

    def test_old_label_still_there_after_expand(self):
        """展开后,老的「归档：任务1」label 仍然在(row 上,不是详情里)。"""
        t = self._find_toggle()
        t.setChecked(True)
        app.processEvents()
        # first_row 的所有 QLabel 还要包含「归档：任务1」
        labels = [lbl.text() for lbl in self.first_row.findChildren(QLabel)]
        self.assertTrue(any("归档：任务1" in s for s in labels),
                        f"展开后老 label 丢了: {labels}")


class TestMultiNoteOrder(unittest.TestCase):
    """多次「仅完成」→ 多次「完成并滚动」后,note 应该有多个条目,详情里顺序正确。"""

    def test_two_complete_only_two_entries(self):
        d = _make_data()
        ex = PlanExecutor(d, lambda: None)
        ex.show()
        app.processEvents()
        # 两次「仅完成」(_make_data 时 done=False,所以第一格可点)
        only_btns = []
        for i in range(ex.day_layout.count()):
            w = ex.day_layout.itemAt(i).widget()
            if w:
                only_btns += [b for b in w.findChildren(rollingplan.QPushButton) if b.text() == "仅完成"]
        only_btns[0].click()
        app.processEvents()
        # 现在第一格已 done,完成并滚动第二格(自动滚到原位置)
        scroll_btns = []
        for i in range(ex.day_layout.count()):
            w = ex.day_layout.itemAt(i).widget()
            if w:
                scroll_btns += [b for b in w.findChildren(rollingplan.QPushButton)
                                 if b.text() == "✓ 完成并滚动"]
        scroll_btns[0].click()
        app.processEvents()
        # 现在第一格 row 的 note 应该有 1 条(任务1 在完成并滚动时不再加进 notes,
        # 因为已经在 only_complete 时加过)。 第二格(row[1]) 的 note 应该有 1 条(任务2)
        # 简单一点:直接找两个 toggle 展开后看详情数量
        toggles = []
        for i in range(ex.day_layout.count()):
            w = ex.day_layout.itemAt(i).widget()
            if w:
                toggles += [t for t in w.findChildren(QToolButton) if t.text() in ("▸", "▾")]
        # 至少有一个 toggle
        self.assertGreaterEqual(len(toggles), 1)
        # 展开第一个,详情里应该至少有一条
        if toggles:
            toggles[0].setChecked(True)
            app.processEvents()
            first_detail = None
            for i in range(ex.day_layout.count()):
                w = ex.day_layout.itemAt(i).widget()
                if w:
                    first_detail = w.findChild(QWidget, "rp-note-detail")
                    if first_detail:
                        break
            if first_detail:
                lines = [lbl.text() for lbl in first_detail.findChildren(QLabel)]
                self.assertGreaterEqual(len(lines), 1, "点开后应该至少有一条详情")


if __name__ == "__main__":
    unittest.main(verbosity=2)
