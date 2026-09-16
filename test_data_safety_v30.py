"""RollingPlan v0.30 数据安全包回归测试

覆盖（UX 审计 P0-1/P0-2/P0-3/P0-5 的修复面）：
- save() 自动留一代备份（plan_data_backup）
- 坏数据 load()：返回 False、记 last_load_error、损坏原件转存时间戳备份文件
- MainWindow 读档失败会弹窗（启动后坏数据挪进 backup 位，plan_data 被清）
- 删除计划/时段有确认框（5 参 question 的默认按钮=否）；点否不删、点是才删
- 新建分类：取消（ok=False）不创建；空名提示且不创建
"""

import os
import sys
import glob
import tempfile

os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PyQt5.QtWidgets import QApplication, QMessageBox, QInputDialog
from PyQt5.QtCore import QSettings, QDate

_tmp_dir = tempfile.mkdtemp(prefix="rollingplan_qsettings_")
os.environ["XDG_CONFIG_HOME"] = _tmp_dir

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from theme import app_settings
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


def make_window():
    win = MainWindow()
    p = win.data.current_parent
    p.name = "工作"
    p.plans = ["任务1", "任务2"]
    p.time_slots = [{"name": "早", "count": 1}]
    p.start_date = QDate(2026, 1, 1)
    win.data.save()
    return win


def test_save_keeps_backup():
    print("\n=== test_save_keeps_backup ===")
    # 第一次 save：plan_data 落盘（此时无旧值，backup 位还不存在）
    make_window()
    s = app_settings()
    ok(s.value("plan_data") is not None, "plan_data 已写入")
    # 第二次 save：上一代数据应被自动挪进 backup 位
    make_window()
    s = app_settings()
    ok(s.value("plan_data_backup") is not None, "plan_data_backup 已自动留下")


def test_corrupt_load_backed_up_and_reported():
    print("\n=== test_corrupt_load_backed_up_and_reported ===")
    s = app_settings()
    corrupt = "{這不是JSON。。。"
    s.setValue("plan_data", corrupt)
    s.sync()

    before = set(glob.glob(os.path.expanduser("~/.hermes_cache/rollingplan_corrupt_backup_*.json")))
    d = PlanData()
    ok(d.load() is False, "坏数据 load 返回 False")
    ok(d.last_load_error is not None and len(d.last_load_error) > 0, "last_load_error 记录原因")
    after = set(glob.glob(os.path.expanduser("~/.hermes_cache/rollingplan_corrupt_backup_*.json")))
    ok(len(after - before) == 1, "损坏原件转存成时间戳备份文件")
    ok(d.current_parent.plans == [], "失败后回退到空数据（不崩）")


def test_mainwindow_warns_and_quarantines():
    print("\n=== test_mainwindow_warns_and_quarantines ===")
    s = app_settings()
    s.setValue("plan_data", "not-a-dict")
    s.sync()

    warns = []
    orig_warn = QMessageBox.warning
    QMessageBox.warning = staticmethod(lambda *a, **k: warns.append(k) or a[1])
    try:
        win = MainWindow()
        app.processEvents()
    finally:
        QMessageBox.warning = orig_warn

    ok(len(warns) == 1, "启动时读档失败弹窗告知用户")
    s2 = app_settings()
    ok(s2.value("plan_data_backup") == "not-a-dict", "损坏原件被隔离进 backup 位")
    ok(s2.value("plan_data") is None, "plan_data 已清空（本次会话可正常 save）")
    # 本次会话 save 后：新数据在 plan_data，坏原件仍在 backup
    win.data.save()
    s3 = app_settings()
    ok(s3.value("plan_data") is not None, "隔离后能正常 save 新数据")


def test_del_plan_and_slot_need_confirmation():
    print("\n=== test_del_plan_and_slot_need_confirmation ===")
    win = make_window()
    win.editor.refresh_all()
    win.editor.plan_list.setCurrentRow(0)

    orig_q = QMessageBox.question
    QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.No)
    try:
        win.editor.del_plan()
        win.editor.slot_list.setCurrentRow(0)
        win.editor.del_slot()
    finally:
        QMessageBox.question = orig_q
    ok(win.data.current_parent.plans == ["任务1", "任务2"], "点「否」：计划没删")
    ok(win.data.current_parent.time_slots == [{"name": "早", "count": 1}], "点「否」：时段没删")

    QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.Yes)
    try:
        win.editor.del_plan()
    finally:
        QMessageBox.question = orig_q
    ok(win.data.current_parent.plans == ["任务2"], "点「是」：计划删除")


def test_add_parent_cancel_creates_nothing():
    print("\n=== test_add_parent_cancel_creates_nothing ===")
    win = make_window()
    n = len(win.data.parents)
    orig_get = QInputDialog.getText
    orig_warn = QMessageBox.warning
    QInputDialog.getText = staticmethod(lambda *a, **k: ("", False))
    QMessageBox.warning = staticmethod(lambda *a, **k: None)   # 空名分支的真模态在 offscreen 会崩
    try:
        win.editor.on_add_parent()
        after_cancel = len(win.data.parents)
        QInputDialog.getText = staticmethod(lambda *a, **k: ("", True))
        win.editor.on_add_parent()
        after_empty = len(win.data.parents)
        QInputDialog.getText = staticmethod(lambda *a, **k: ("新分类X", True))
        win.editor.on_add_parent()
        after_ok = len(win.data.parents)
    finally:
        QInputDialog.getText = orig_get
        QMessageBox.warning = orig_warn
    ok(after_cancel == n, "取消（Esc）：不再偷偷创建默认分类")
    ok(after_empty == n, "空名：提示且不创建")
    ok(after_ok == n + 1 and win.data.parents[-1].name == "新分类X",
       "正常输入：创建成功")


def main():
    test_save_keeps_backup()
    test_corrupt_load_backed_up_and_reported()
    test_mainwindow_warns_and_quarantines()
    test_del_plan_and_slot_need_confirmation()
    test_add_parent_cancel_creates_nothing()

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
