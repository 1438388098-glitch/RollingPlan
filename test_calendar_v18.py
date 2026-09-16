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

v0.22 追加（归档按天分组）：
- 归档历史按天分组:每天一条「📅 第 N 天（X 条）」分隔标题 + 该天的条目（天与天之间倒序）
- 老存档没有 daily_boundaries 时不崩,标成「第 1–N 天」
- daily_boundaries 的模型层收敛（to_dict / from_dict / normalize / reset_progress / 撤销栈）
- 切天（executor.on_next_day）把当天归档条数 push 进 daily_boundaries

列表结构的判定方式：QListWidgetItem.setData(Qt.UserRole) 标了
"day_header" / "plan" / "placeholder",测试按它筛行,不要硬编码下标
（否则加一行分隔标题就全错位 —— v0.22 就是这么发现的）。
"""
import os
import sys
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QApplication, QMessageBox
app = QApplication.instance() or QApplication(sys.argv)

from rollingplan import ParentPlan, PlanData
from calendar_view import (
    PlanCalendarView, build_archive_text, export_archive_text,
    estimate_days_left, estimate_text,
)
from scheduler import PlanScheduler


def _make_parent(name="测试", plans=None, slots=None):
    p = ParentPlan(name)
    p.plans = list(plans or ["1","2","3","4","5","6","7","8","9"])
    p.time_slots = list(slots or [{"name":"早","count":3}])
    p.normalize()
    return p


def _items_by_role(cv, role_name):
    """按 UserRole 里的标记筛列表行（不依赖下标）。"""
    out = []
    for i in range(cv.archive_list.count()):
        it = cv.archive_list.item(i)
        if it.data(Qt.UserRole) == role_name:
            out.append(it)
    return out


def _plan_rows(cv):
    return _items_by_role(cv, "plan")


def _header_rows(cv):
    return _items_by_role(cv, "day_header")


def _headers_text(cv):
    return [it.text() for it in _header_rows(cv)]


def _plans_text(cv):
    """条目文本（去掉前面的缩进空格）"""
    return [it.text().strip() for it in _plan_rows(cv)]


def _is_green(item):
    return item.foreground().color().green() > 50


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
        # 占位符有自己的标记（v0.22：测试用它区分「没归档」和「有归档但没分到天」）
        self.assertEqual(cv.archive_list.item(0).data(Qt.UserRole), "placeholder")


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
        # 3 条归档 → 3 个条目行（加上 1 行分隔标题）
        self.assertEqual(len(_plan_rows(cv)), 3)
        self.assertEqual(len(_header_rows(cv)), 1)

    def test_archive_list_recent_first(self):
        p, data = self._setup()
        cv = PlanCalendarView(data)
        # 倒序：第一个条目行 = 最新 = "3"
        texts = _plans_text(cv)
        self.assertEqual(texts, ["3", "2", "1"])

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
        rows = _plan_rows(cv)
        self.assertEqual(len(rows), 3)
        for i, item in enumerate(rows):
            self.assertTrue(_is_green(item), f"条目 {i} 没设成深绿: {item.text()}")

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
        rows = _plan_rows(cv)
        self.assertEqual(len(rows), 3)
        self.assertEqual(rows[0].text().strip(), "c")   # 最近的在最上
        self.assertEqual(rows[1].text().strip(), "b")
        t_color = rows[0].foreground().color()
        p_color = rows[1].foreground().color()
        self.assertNotEqual((t_color.red(), t_color.green(), t_color.blue()),
                            (p_color.red(), p_color.green(), p_color.blue()))

    def test_slot_notes_in_today_label(self):
        p, data = self._setup()
        cv = PlanCalendarView(data)
        # 各时段的归档备注也要在 today_label 里看到
        self.assertIn("时段 1", cv.today_label.text())
        self.assertIn("时段 2", cv.today_label.text())


class TestDayGrouping(unittest.TestCase):
    """v0.22：归档历史按天分组（daily_boundaries）。"""

    def _grouped(self):
        """第 1 天完成 3 条、切天、第 2 天又完成 2 条（current_day=1）。"""
        p = _make_parent(plans=["1","2","3","4","5","6","7","8","9"])
        p.archived.extend(["1","2","3","4","5"])
        p.current_day = 1
        p.daily_boundaries = [3]        # 第 1 天结束时 archived 长度 = 3
        p.archived_base = 3             # 第 2 天（今天）从 3 开始
        p.normalize()
        data = PlanData()
        data.parents = [p]
        data.current_parent_idx = 0
        return p, data

    def test_sections_split_by_boundary(self):
        p, data = self._grouped()
        cv = PlanCalendarView(data)
        secs = cv._day_sections(p)
        self.assertEqual(len(secs), 2)
        # 第 1 天 = archived[0:3]
        self.assertEqual(secs[0]["plans"], ["1","2","3"])
        self.assertEqual(secs[0]["start"], 0)
        self.assertFalse(secs[0]["current"])
        # 第 2 天 = archived[3:]（进行中）
        self.assertEqual(secs[1]["plans"], ["4","5"])
        self.assertEqual(secs[1]["start"], 3)
        self.assertTrue(secs[1]["current"])

    def test_headers_recent_day_first(self):
        p, data = self._grouped()
        cv = PlanCalendarView(data)
        headers = _headers_text(cv)
        self.assertEqual(len(headers), 2)
        self.assertIn("第 2 天", headers[0])      # 最近的天在最上
        self.assertIn("进行中", headers[0])
        self.assertIn("2 条", headers[0])
        self.assertIn("第 1 天", headers[1])
        self.assertIn("3 条", headers[1])

    def test_plan_rows_grouped_and_recent_first(self):
        p, data = self._grouped()
        cv = PlanCalendarView(data)
        # v0.23：默认只展开最近一天（第 2 天）→ 只有它的两条可见
        self.assertEqual(_plans_text(cv), ["5", "4"])
        kinds = [cv.archive_list.item(i).data(Qt.UserRole)
                 for i in range(cv.archive_list.count())]
        self.assertEqual(kinds, ["day_header", "plan", "plan", "day_header"])
        # 全部展开 → 五条都在，顺序仍是最近的在上
        cv._on_toggle_all()
        self.assertEqual(_plans_text(cv), ["5", "4", "3", "2", "1"])
        kinds = [cv.archive_list.item(i).data(Qt.UserRole)
                 for i in range(cv.archive_list.count())]
        self.assertEqual(kinds,
                         ["day_header", "plan", "plan",
                          "day_header", "plan", "plan", "plan"])

    def test_green_only_marks_today(self):
        p, data = self._grouped()
        cv = PlanCalendarView(data)
        cv._on_toggle_all()                     # 展开所有天才能看到过去的条目
        rows = _plan_rows(cv)
        # 前两行（第 2 天 = 今天）深绿
        self.assertTrue(_is_green(rows[0]))
        self.assertTrue(_is_green(rows[1]))
        # 后三行（第 1 天 = 过去）不是
        for it in rows[2:]:
            self.assertFalse(_is_green(it), f"过去的归档不该是深绿: {it.text().strip()}")

    def test_archived_idx_per_row(self):
        p, data = self._grouped()
        cv = PlanCalendarView(data)
        cv._on_toggle_all()
        idxs = [it.data(Qt.UserRole + 1) for it in _plan_rows(cv)]
        self.assertEqual(idxs, [4, 3, 2, 1, 0])   # 对应 archived 里的下标

    def test_header_rows_clickable_but_not_selectable(self):
        """v0.23：分隔标题可点（收起/展开）—— 有 Enabled 但没有 Selectable。"""
        p, data = self._grouped()
        cv = PlanCalendarView(data)
        for it in _header_rows(cv):
            self.assertEqual(it.flags(), Qt.ItemIsEnabled)

    def test_legacy_save_without_boundaries(self):
        """v0.21 之前的老存档没有 daily_boundaries → 一天都不切,标成区间。"""
        p = _make_parent(plans=["1","2","3","4","5","6"])
        p.archived.extend(["a","b","c"])
        p.current_day = 2            # 已经切过两次天,但边界信息缺失
        p.archived_base = 2
        p.daily_boundaries = []      # 老存档
        p.normalize()
        data = PlanData()
        data.parents = [p]
        cv = PlanCalendarView(data)
        headers = _headers_text(cv)
        self.assertEqual(len(headers), 1)
        self.assertIn("第 1–3 天", headers[0])
        self.assertEqual(_plans_text(cv), ["c", "b", "a"])

    def test_no_archive_current_day_only(self):
        """一条都没归档、但人已经在第 2 天 → 占位符照旧。"""
        p = _make_parent(plans=["1","2","3","4","5","6"])
        p.current_day = 1
        p.normalize()
        data = PlanData()
        data.parents = [p]
        cv = PlanCalendarView(data)
        self.assertEqual(cv.archive_list.count(), 1)
        self.assertEqual(cv.archive_list.item(0).data(Qt.UserRole), "placeholder")


class TestDailyBoundariesModel(unittest.TestCase):
    """v0.22：ParentPlan.daily_boundaries 的存取与收敛。"""

    def test_to_dict_from_dict_roundtrip(self):
        p = _make_parent(plans=["1","2","3","4","5","6"])
        p.archived.extend(["1","2","3","4"])
        p.current_day = 2
        p.daily_boundaries = [2, 4]
        d = p.to_dict()
        self.assertEqual(d["daily_boundaries"], [2, 4])
        q = ParentPlan()
        q.from_dict(d)
        self.assertEqual(q.daily_boundaries, [2, 4])

    def test_from_dict_old_save_defaults_empty(self):
        p = _make_parent(plans=["1","2","3"])
        d = p.to_dict()
        del d["daily_boundaries"]
        q = ParentPlan()
        q.from_dict(d)
        self.assertEqual(q.daily_boundaries, [])

    def test_from_dict_ignores_junk(self):
        p = _make_parent(plans=["1","2","3"])
        p.archived.extend(["1","2"])
        p.current_day = 2
        d = p.to_dict()
        d["daily_boundaries"] = ["x", None, 2]      # 混进非数字 → 只留 2
        q = ParentPlan()
        q.from_dict(d)
        self.assertEqual(q.daily_boundaries, [2])

    def test_normalize_clamps_to_archived_length(self):
        p = _make_parent(plans=["1","2","3","4","5","6"])
        p.archived.extend(["1","2"])
        p.current_day = 5
        p.daily_boundaries = [1, 999, -3]
        p.normalize()
        # 999 → 2（= len(archived)）,-3 → 0；排序去重后仍是 [0, 1, 2]
        self.assertEqual(p.daily_boundaries, [0, 1, 2])

    def test_normalize_dedupes_and_sorts(self):
        p = _make_parent(plans=["1","2","3","4","5","6"])
        p.archived.extend(["1","2","3"])
        p.current_day = 4
        p.daily_boundaries = [3, 1, 3, 1]
        p.normalize()
        self.assertEqual(p.daily_boundaries, [1, 3])

    def test_normalize_truncates_to_current_day(self):
        """每天切一次天才 push 一条 → 边界条数不可能超过 current_day。"""
        p = _make_parent(plans=["1","2","3","4","5","6"])
        p.archived.extend(["1","2","3"])
        p.current_day = 0                       # 还没切过天
        p.daily_boundaries = [1, 2, 3]          # 脏数据：多了
        p.normalize()
        self.assertEqual(p.daily_boundaries, [])

    def test_reset_progress_clears_boundaries(self):
        p = _make_parent(plans=["1","2","3","4","5","6"])
        p.archived.extend(["1","2","3"])
        p.current_day = 1
        p.daily_boundaries = [3]
        p.reset_progress()
        self.assertEqual(p.daily_boundaries, [])
        self.assertEqual(p.current_day, 0)
        self.assertEqual(p.archived_base, 0)
        self.assertEqual(p.archived, [])

    def test_undo_restores_boundaries(self):
        """撤销栈带上了 daily_boundaries（否则撤回去天分组会跟 current_day 不一致）。"""
        p = _make_parent(plans=["1","2","3","4","5","6"])
        p.archived.extend(["1","2","3"])
        p.current_day = 1
        p.daily_boundaries = [3]
        p.archived_base = 3
        p.push_history()
        p.archived.append("4")          # 完成一条
        p.archived_base = 3
        p.current_day = 2               # 又切了一天（不进栈,模拟直接改状态）
        p.daily_boundaries = [3, 4]
        p.normalize()
        self.assertTrue(p.undo())       # 回到 push_history 那一刻
        self.assertEqual(p.current_day, 1)
        self.assertEqual(p.daily_boundaries, [3])

    def test_snapshot_keys_include_boundaries(self):
        self.assertIn("daily_boundaries", ParentPlan._SNAPSHOT_KEYS)


class TestNextDayPushesBoundary(unittest.TestCase):
    """v0.22：executor.on_next_day 真的会把当天归档条数写进 daily_boundaries。"""

    def _win(self):
        from rollingplan import MainWindow
        win = MainWindow()
        p = ParentPlan("测试")
        p.plans = ["1","2","3","4","5","6","7","8","9"]
        p.time_slots = [{"name":"早","count":3}]
        p.normalize()
        win.data.parents = [p]
        win.data.current_parent_idx = 0
        win.executor.refresh()
        return win, p

    def test_on_next_day_appends_boundary(self):
        win, p = self._win()
        # 今天完成 1 条
        win.executor.on_complete_slot(0)
        self.assertEqual(len(p.archived), 1)

        orig = QMessageBox.question
        QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.Yes)
        try:
            win.executor.on_next_day()
        finally:
            QMessageBox.question = orig

        self.assertEqual(p.current_day, 1)
        self.assertEqual(p.daily_boundaries, [1])
        self.assertEqual(p.archived_base, 1)
        # 第 2 天再完成 1 条后,分组应该是「第 1 天 1 条 / 第 2 天进行中 1 条」
        win.executor.on_complete_slot(0)
        cv = win.calendar_view
        cv.refresh()
        # v0.23 起默认只展开最近一天 → 先看到今天那条
        self.assertEqual(_plans_text(cv), [p.archived[-1]])
        headers = _headers_text(cv)
        self.assertEqual(len(headers), 2)
        self.assertIn("第 2 天", headers[0])
        self.assertIn("第 1 天", headers[1])
        cv._on_toggle_all()
        self.assertEqual(_plans_text(cv), [p.archived[-1], p.archived[0]])


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
        self.assertEqual(len(_plan_rows(cv)), 2)
        # 倒序：最新在最上 = "2"，下面 "1"
        self.assertEqual(_plans_text(cv), ["2", "1"])

        # 切到学习
        cv.parent_combo.setCurrentIndex(1)
        self.assertEqual(len(_plan_rows(cv)), 1)
        self.assertEqual(_plans_text(cv), ["A"])

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


class TestArchiveExport(unittest.TestCase):
    """v0.22b：把归档历史导出成文本（「⬇ 导出归档」按钮背后那套）。"""

    def _sched(self, plans, archived, current_day=0, boundaries=None,
               archived_base=None, notes=None):
        p = _make_parent(plans=plans)
        p.archived.extend(archived)
        p.current_day = current_day
        p.daily_boundaries = list(boundaries or [])
        p.archived_base = len(archived) if archived_base is None else archived_base
        p.slot_notes = list(notes or [])
        p.normalize()
        return p, PlanScheduler(p)

    def test_text_has_day_groups_and_today(self):
        p, s = self._sched(["1", "2", "3", "4", "5", "6"],
                           ["1", "2", "3", "4", "5"], current_day=1, boundaries=[3],
                           archived_base=3)     # 第 2 天（今天）= archived[3:] = 4、5
        txt = build_archive_text(p, s, now_str="2026-09-16 18:20")
        self.assertIn("RollingPlan 归档导出", txt)
        self.assertIn("分类：测试", txt)
        self.assertIn("导出时间：2026-09-16 18:20", txt)
        self.assertIn("已推进", txt)
        self.assertIn("共 6 条", txt)
        self.assertIn("📅 第 1 天（3 条）", txt)
        self.assertIn("  1. 1", txt)
        self.assertIn("📅 第 2 天（进行中，2 条）", txt)
        self.assertIn("✅ 今天完成：4、5", txt)
        # 时间顺序：第 1 天在前
        self.assertLess(txt.index("第 1 天（3 条）"), txt.index("第 2 天（进行中"))
        # 第 1 天的三条都列出来了
        for n in ("1", "2", "3"):
            self.assertIn(f"  {n}. {n}", txt)

    def test_text_includes_slot_notes(self):
        p, s = self._sched(["1", "2", "3", "4", "5", "6"], ["1", "2", "3"],
                           current_day=1, boundaries=[3], archived_base=0,
                           notes=[["1"], ["2", "3"], []])
        txt = build_archive_text(p, s, now_str="X")
        self.assertIn("📋 各时段归档备注：", txt)
        self.assertIn("时段 1: 1", txt)
        self.assertIn("时段 2: 2、3", txt)
        self.assertNotIn("时段 3", txt)

    def test_text_empty_archive(self):
        p, s = self._sched(["1", "2", "3"], [])
        txt = build_archive_text(p, s, now_str="X")
        self.assertIn("（暂无归档）", txt)
        self.assertIn("✅ 今天完成：（无）", txt)

    def test_text_legacy_without_boundaries(self):
        p, s = self._sched(["1", "2", "3"], ["a", "b"], current_day=2)
        txt = build_archive_text(p, s, now_str="X")
        self.assertIn("第 1–3 天", txt)

    def test_export_writes_utf8_file(self):
        import tempfile
        p, s = self._sched(["1", "2", "3", "4", "5", "6"],
                           ["1", "2", "3", "4", "5"], current_day=1, boundaries=[3])
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "gt.txt")
            ret = export_archive_text(path, p, s, now_str="2026-09-16 18:20")
            self.assertEqual(ret, path)
            self.assertTrue(os.path.exists(path))
            with open(path, encoding="utf-8-sig") as f:
                got = f.read()
        self.assertEqual(got, build_archive_text(p, s, now_str="2026-09-16 18:20"))
        self.assertIn("📅 第 2 天（进行中，2 条）", got)

    def test_export_button_present(self):
        p, s = self._sched(["1", "2", "3"], ["1"])
        data = PlanData()
        data.parents = [p]
        cv = PlanCalendarView(data)
        self.assertTrue(hasattr(cv, "export_btn"))
        self.assertIn("导出", cv.export_btn.text())

    def test_export_handler_without_scheduler_safe(self):
        """没有分类时点导出不能崩（scheduler=None 分支）。"""
        cv = PlanCalendarView(PlanData())
        cv.scheduler = None
        orig = QMessageBox.information
        calls = []
        QMessageBox.information = staticmethod(lambda *a, **k: calls.append(a))
        try:
            cv._on_export()
        finally:
            QMessageBox.information = orig
        self.assertEqual(len(calls), 1)


class TestDayCollapse(unittest.TestCase):
    """v0.23：归档历史按天折叠（点「📅 第 N 天」收起/展开 + 全部展开按钮）。"""

    def _three_days(self):
        """第 1 天 2 条 / 第 2 天 2 条 / 第 3 天（今天）1 条。"""
        p = _make_parent(plans=["1", "2", "3", "4", "5", "6", "7", "8", "9"])
        p.archived.extend(["1", "2", "3", "4", "5"])
        p.current_day = 2
        p.daily_boundaries = [2, 4]
        p.archived_base = 4
        p.normalize()
        data = PlanData()
        data.parents = [p]
        data.current_parent_idx = 0
        return p, data

    def test_default_only_newest_open(self):
        p, data = self._three_days()
        cv = PlanCalendarView(data)
        self.assertEqual(_plans_text(cv), ["5"])            # 只看到今天那条
        heads = _header_rows(cv)
        self.assertEqual(len(heads), 3)
        self.assertTrue(heads[0].text().startswith("▾ "))    # 最近的一天展开
        self.assertTrue(heads[1].text().startswith("▸ "))
        self.assertTrue(heads[2].text().startswith("▸ "))

    def test_click_header_expands_then_collapses(self):
        p, data = self._three_days()
        cv = PlanCalendarView(data)
        cv._on_archive_clicked(_header_rows(cv)[2])          # 点「第 1 天」
        self.assertEqual(_plans_text(cv), ["5", "2", "1"])
        self.assertTrue(_header_rows(cv)[2].text().startswith("▾ "))
        cv._on_archive_clicked(_header_rows(cv)[2])          # 再点一次 → 收起
        self.assertEqual(_plans_text(cv), ["5"])

    def test_click_today_header_collapses_it(self):
        p, data = self._three_days()
        cv = PlanCalendarView(data)
        cv._on_archive_clicked(_header_rows(cv)[0])          # 收起今天
        self.assertEqual(_plans_text(cv), [])

    def test_click_plan_row_does_nothing(self):
        p, data = self._three_days()
        cv = PlanCalendarView(data)
        cv._on_archive_clicked(_plan_rows(cv)[0])
        self.assertEqual(_plans_text(cv), ["5"])

    def test_toggle_all_button_cycle(self):
        p, data = self._three_days()
        cv = PlanCalendarView(data)
        cv._on_toggle_all()                                  # 全部展开
        self.assertEqual(_plans_text(cv), ["5", "4", "3", "2", "1"])
        self.assertIn("全部收起", cv.expand_all_btn.text())
        cv._on_toggle_all()                                  # 全部收起
        self.assertEqual(_plans_text(cv), [])
        self.assertIn("全部展开", cv.expand_all_btn.text())
        cv._on_toggle_all()                                  # 再全部展开
        self.assertEqual(_plans_text(cv), ["5", "4", "3", "2", "1"])

    def test_toggle_all_clears_single_choices(self):
        p, data = self._three_days()
        cv = PlanCalendarView(data)
        cv._on_archive_clicked(_header_rows(cv)[2])          # 单独展开第 1 天
        cv._on_toggle_all()                                  # 全展开 → 清掉单独状态
        cv._on_toggle_all()                                  # 全收起
        cv._on_toggle_all()                                  # 全展开
        self.assertEqual(cv._day_open, {})

    def test_state_survives_refresh(self):
        p, data = self._three_days()
        cv = PlanCalendarView(data)
        cv._on_archive_clicked(_header_rows(cv)[2])
        cv.refresh()                                         # 页面重刷（比如从执行页切回来）
        self.assertEqual(_plans_text(cv), ["5", "2", "1"])

    def test_header_click_does_not_touch_data(self):
        """折叠纯粹是显示状态，不能改数据。"""
        p, data = self._three_days()
        before = list(p.archived)
        cv = PlanCalendarView(data)
        cv._on_archive_clicked(_header_rows(cv)[2])
        cv._on_toggle_all()
        self.assertEqual(p.archived, before)
        self.assertEqual(p.daily_boundaries, [2, 4])


class TestEstimateDaysLeft(unittest.TestCase):
    """v0.23：第三页的「还剩 N 条 ≈ 还要 N 天」（剩余条数 ÷ 每天格数）。"""

    def test_nine_plans_three_slots(self):
        p = _make_parent(plans=["1"] * 9)          # 9 条 · 每天 3 格
        self.assertEqual(estimate_days_left(p), (9, 3, 3))
        self.assertIn("还要 3 天", estimate_text(p))

    def test_rounds_up_partial_day(self):
        p = _make_parent(plans=["1"] * 9)
        p.archived.extend(["1"] * 7)               # 剩 2 条 → 1 天（不满也占一天）
        self.assertEqual(estimate_days_left(p), (2, 3, 1))

    def test_all_done(self):
        p = _make_parent(plans=["1"] * 4)
        p.archived.extend(["1"] * 4)
        self.assertEqual(estimate_days_left(p)[2], 0)
        self.assertIn("全部完成", estimate_text(p))

    def test_no_plans(self):
        p = _make_parent(plans=["x"])
        p.plans = []                # _make_parent 的空列表会被当默认值,所以后置清空
        p.normalize()
        self.assertEqual(estimate_days_left(p), (0, 3, 0))

    def test_no_slots_cannot_estimate(self):
        p = ParentPlan("空时段")
        p.plans = ["1", "2", "3"]
        p.time_slots = []
        p.normalize()
        remaining, spd, days = estimate_days_left(p)
        self.assertEqual((remaining, spd), (3, 0))
        self.assertIsNone(days)
        self.assertIn("算不出天数", estimate_text(p))

    def test_more_done_than_plans_never_negative(self):
        p = _make_parent(plans=["1", "2"])
        p.archived.extend(["1", "2", "3"])          # 脏数据：归档比计划多
        self.assertEqual(estimate_days_left(p)[0], 0)

    def test_label_and_export_show_estimate(self):
        p = _make_parent(plans=["1"] * 6)
        p.archived.extend(["1", "1"])               # 剩 4 条 → 还要 2 天
        data = PlanData()
        data.parents = [p]
        cv = PlanCalendarView(data)
        self.assertIn("还要 2 天", cv.estimate_label.text())
        txt = build_archive_text(p, PlanScheduler(p), now_str="X")
        self.assertIn("估算：还剩 4 条 ≈ 还要 2 天", txt)

    def test_label_empty_without_scheduler(self):
        cv = PlanCalendarView(PlanData())
        cv.scheduler = None
        cv._refresh_view()
        self.assertEqual(cv.estimate_label.text(), "")


if __name__ == "__main__":
    unittest.main(verbosity=2)
