"""RollingPlan v0.30 跨天链路端到端回归测试（上游 STATE 挂账的 candidate-020）

链路：多天完成 → 切天 → 撤销 → 重做 → 归档导出 → JSON 导出/导入往返。
保护的是整个应用最复杂的数据流（archived / daily_boundaries / consumed /
slot_notes 在跨天 + 撤销重做下的不变量），以及导出内容与内存数据的一致性。
"""

import os
import sys
import json
import tempfile

os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PyQt5.QtWidgets import QApplication, QMessageBox
from PyQt5.QtCore import QSettings, QDate

_tmp_dir = tempfile.mkdtemp(prefix="rollingplan_qsettings_")
os.environ["XDG_CONFIG_HOME"] = _tmp_dir

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from theme import app_settings
from rollingplan import MainWindow, PlanData

QSettings.setDefaultFormat(QSettings.IniFormat)
QSettings.setPath(QSettings.IniFormat, QSettings.UserScope, _tmp_dir)
app_settings().clear()

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


def boot():
    win = MainWindow()
    p = win.data.current_parent
    p.name = "链路"
    p.plans = ["T1", "T2", "T3", "T4", "T5", "T6", "T7", "T8", "T9"]
    p.time_slots = [{"name": "早", "count": 3}]
    p.start_date = QDate(2026, 9, 1)
    win.editor.refresh_all()
    win.show_executor()
    app.processEvents()
    return win


def complete_n(win, n):
    for _ in range(n):
        win.executor.on_complete_slot(0)
        app.processEvents()


def test_crossday_chain():
    print("\n=== test_crossday_chain ===")
    win = boot()

    # 第 1 天：完成 2 条
    complete_n(win, 2)
    p = win.data.current_parent
    ok(p.archived == ["T1", "T2"], "第1天归档 T1/T2")

    # 切天（第1天还有 1 条 T3 未完成 → 会弹确认，桩成 Yes）
    orig_q = QMessageBox.question
    QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.Yes)
    try:
        win.executor.on_next_day()
        app.processEvents()
    finally:
        pass  # 桩保留到本测试结束（后面切天还要用）

    ok(p.current_day == 1, "进入第 2 天")
    ok(p.daily_boundaries == [2], "daily_boundaries 记录第 1 天边界=2")
    st = win.executor.scheduler.today_state()
    ok([plan for _, plan in st["rows"]] == ["T4", "T5", "T6"], "第 2 天行是 T4/T5/T6")

    # 第 2 天完成 1 条再切天
    complete_n(win, 1)
    ok(p.archived == ["T1", "T2", "T4"], "第2天归档 T4（T3 还在第1天队列位置）")
    win.executor.on_next_day()
    app.processEvents()
    ok(p.current_day == 2 and p.daily_boundaries == [2, 3], "第 2 天边界=3")

    # 撤销一次切天 → 回到第 2 天
    win.executor.on_undo()
    app.processEvents()
    ok(p.current_day == 1 and p.daily_boundaries == [2], "撤销切天：回到第 2 天，边界回落")

    # 重做 → 再回第 3 天
    win.executor.on_redo()
    app.processEvents()
    ok(p.current_day == 2 and p.daily_boundaries == [2, 3], "重做切天：边界恢复")

    # 导出归档：内容应与内存一致
    from calendar_view import build_archive_text
    txt = build_archive_text(p, win.executor.scheduler)
    ok("T1" in txt and "T4" in txt and "T5" not in txt, "归档导出含已完成、不含未完成")
    ok("第 1 天（2 条）" in txt, "导出按天分组：第 1 天 2 条")

    # JSON 往返：to_dict → 新 PlanData → 数据一致
    d2 = PlanData()
    ok(d2.from_dict(json.loads(json.dumps(win.data.to_dict()))) is None, "JSON 往返不抛异常")
    p2 = d2.current_parent
    ok(p2.archived == p.archived and p2.daily_boundaries == p.daily_boundaries,
       "往返后 archived/daily_boundaries 一致")
    ok(p2.current_day == p.current_day, "往返后 current_day 一致")

    QMessageBox.question = orig_q


def test_roundtrip_survives_normalize():
    print("\n=== test_roundtrip_survives_normalize ===")
    win = boot()
    complete_n(win, 4)
    p = win.data.current_parent
    QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.Yes)
    win.executor.on_next_day()
    complete_n(win, 2)
    win.executor.on_next_day()
    app.processEvents()

    snap = json.loads(json.dumps(win.data.to_dict()))
    d2 = PlanData()
    d2.from_dict(snap)
    p2 = d2.current_parent
    ok(p2.archived == p.archived, "往返：archived 一致")
    ok(p2.daily_boundaries == p.daily_boundaries, "往返：daily_boundaries 一致")
    ok(p2.slot_notes == p.slot_notes, "往返：slot_notes 一致")
    ok(p2.consumed == p.consumed, "往返：consumed 一致")
    # 再 normalize 一次幂等
    p2.normalize()
    ok(p2.daily_boundaries == p.daily_boundaries, "normalize 幂等")


def main():
    test_crossday_chain()
    test_roundtrip_survives_normalize()

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
