"""
v0.18 归档总览（PlanCalendarView）测试

覆盖：
- 构造后默认显示「无归档」占位符
- 选了带归档历史的分类后,archive_list 显示归档条目(最近在上)
- 进度标签显示「已推进 X / 共 Y 条」格式
- 今天完成的列表单独高亮（绿色字 + 出现在 today_label）
- 每格的 slot_notes 也显示出来
- 分类切换：换到另一个分类时刷新整页
- 空进度 (0/0) 不崩
"""
import os
import sys
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtWidgets import QApplication
app = QApplication.instance() or QApplication(sys.argv)

from rollingplan import ParentPlan, PlanData
from calendar_view import PlanCalendarView


def _make_parent(name="测试", plans=None, slots=None):
    p = ParentPlan(name)
    p.plans = list(plans or ["1","2","3","4","5","6","7","8","9"])
    p.time_slots = list(slots or [{"name":"早","count":3}])
    p.normalize()
    return p


class TestCalendarViewInitial(unittest.TestCase):
    def test_default_first_parent(self):
        data = PlanData()
        # 默认有一个分类
        cv = PlanCalendarView(data)
        # progress_label 应有非空内容
        self.assertNotEqual(cv.progress_label.text(), "")
        # 列表至少有一行（占位符或归档条目）
        self.assertGreaterEqual(cv.archive_list.count(), 1)

    def test_empty_archived_shows_placeholder(self):
        data = PlanData()
        cv = PlanCalendarView(data)
        # 默认 archived 空 → 占位符
        self.assertEqual(cv.archive_list.count(), 1)
        first = cv.archive_list.item(0).text()
        self.assertIn("暂无归档", first)


class TestCalendarViewWithArchive(unittest.TestCase):
    def _setup(self):
        p = _make_parent(plans=["1","2","3","4","5","6"])
        p.archived_base = 0
        p.archived.extend(["1", "2", "3"])     # 累计完成 3 条
        p.inplace_done = ["1", None, None]
        p.slot_notes = [["1"], ["2"], ["3"]]
        data = PlanData()
        data.parents = [p]
        data.current_parent_idx = 0
        return p, data

    def test_archive_list_count(self):
        p, data = self._setup()
        cv = PlanCalendarView(data)
        # 3 条归档 → 列表 3 行（没占位符）
        self.assertEqual(cv.archive_list.count(), 3)

    def test_archive_list_recent_first(self):
        p, data = self._setup()
        cv = PlanCalendarView(data)
        # 倒序：列表 index 0 = 最新 = "3"
        self.assertIn("3", cv.archive_list.item(0).text())
        self.assertIn("2", cv.archive_list.item(1).text())
        self.assertIn("1", cv.archive_list.item(2).text())

    def test_progress_label_format(self):
        p, data = self._setup()
        cv = PlanCalendarView(data)
        # plans=6, archived=3 → get_progress 算的是「已推进」包含归档
        text = cv.progress_label.text()
        self.assertIn("已推进", text)
        self.assertIn("共 6 条", text)

    def test_today_label_shows_done_today(self):
        p, data = self._setup()
        cv = PlanCalendarView(data)
        # archived_base=0 → done_today = archived 全部 = ["1","2","3"]
        self.assertIn("1", cv.today_label.text())
        self.assertIn("2", cv.today_label.text())
        self.assertIn("3", cv.today_label.text())

    def test_today_highlight_color(self):
        """今天完成的几条在 archive_list 里前景色应该是 darkGreen。"""
        p, data = self._setup()
        cv = PlanCalendarView(data)
        # 3 条都今天完成 → 全都应该是深绿。
        # QBrush 默认前景色是黑色(Qt.GlobalColor.black);darkGreen 的 green 分量 > 50。
        for i in range(cv.archive_list.count()):
            item = cv.archive_list.item(i)
            color = item.foreground().color()
            self.assertGreater(color.green(), 50, f"item {i} 没设成深绿: {color.name()}")

    def test_non_today_not_green(self):
        """今天之前完成的（在 done_today 之外的）不是深绿。

        实现说明:这里对比「今天」和「非今天」两条 item 的前景色,要求它们不同就行 —
        不要硬编码 RGB,否则 dark/light 主题切换时这个断言会变成 flaky。
        """
        # 不用 _setup —— 那个已经 archived.extend 过了,我们这里要严格控制 archived 的内容
        p = _make_parent(plans=["1","2","3","4","5","6"])
        p.archived.extend(["a","b","c"])     # 归档历史
        p.archived_base = 2                   # 只有 "c" 是今天完成的
        p.slot_notes = [["c"], [], []]
        data = PlanData()
        data.parents = [p]
        cv = PlanCalendarView(data)
        self.assertEqual(cv.archive_list.count(), 3)
        item_today = cv.archive_list.item(0)   # "c" 今天 → 深绿
        item_past = cv.archive_list.item(1)    # "b" 不是今天 → 默认色
        t_color = item_today.foreground().color()
        p_color = item_past.foreground().color()
        self.assertNotEqual((t_color.red(), t_color.green(), t_color.blue()),
                            (p_color.red(), p_color.green(), p_color.blue()))

    def test_slot_notes_in_today_label(self):
        p, data = self._setup()
        cv = PlanCalendarView(data)
        # 各时段的归档备注也要在 today_label 里看到
        self.assertIn("时段 1", cv.today_label.text())
        self.assertIn("时段 2", cv.today_label.text())


class TestMultiParentSwitch(unittest.TestCase):
    def test_switch_parent_refreshes(self):
        pa = _make_parent(name="工作", plans=["1","2","3"])
        pa.archived_base = 0
        pa.archived.extend(["1","2"])
        pb = _make_parent(name="学习", plans=["A","B","C","D"])
        pb.archived_base = 0
        pb.archived.extend(["A"])
        data = PlanData()
        data.parents = [pa, pb]
        data.current_parent_idx = 0

        cv = PlanCalendarView(data)
        self.assertEqual(cv.archive_list.count(), 2)
        # 倒序：item(0) = 最新 = "2"，item(1) = "1"
        self.assertIn("2", cv.archive_list.item(0).text())
        self.assertIn("1", cv.archive_list.item(1).text())

        # 切到学习
        cv.parent_combo.setCurrentIndex(1)
        self.assertEqual(cv.archive_list.count(), 1)
        self.assertIn("A", cv.archive_list.item(0).text())

    def test_empty_progress_no_crash(self):
        p = _make_parent(name="空")
        p.plans = []                  # 没计划
        p.time_slots = [{"name":"早","count":3}]
        p.normalize()
        data = PlanData()
        data.parents = [p]
        cv = PlanCalendarView(data)
        # 不崩就行
        self.assertNotEqual(cv.progress_label.text(), "")


class TestMainWindowHasThirdTab(unittest.TestCase):
    def test_three_tabs_present(self):
        from rollingplan import MainWindow
        mw = MainWindow()
        self.assertEqual(mw.tabs.count(), 3)
        labels = [mw.tabs.tabText(i) for i in range(3)]
        self.assertIn("归档总览", labels[2])

    def test_calendar_view_attached(self):
        from rollingplan import MainWindow
        mw = MainWindow()
        self.assertTrue(hasattr(mw, "calendar_view"))
        # 是 PlanCalendarView 实例
        from calendar_view import PlanCalendarView
        self.assertIsInstance(mw.calendar_view, PlanCalendarView)


if __name__ == "__main__":
    unittest.main(verbosity=2)
