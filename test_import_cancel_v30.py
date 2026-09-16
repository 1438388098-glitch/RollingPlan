"""RollingPlan v0.30 导入取消链路回归测试

防的坑（健壮性审计 P0-2 / P2-6）：
- 旧版取消导入靠 data.load() 从磁盘回滚：
  1) 全新安装磁盘上还没有 plan_data → load() 返回 False，内存里仍是**已导入的数据**，
     下一次任意动作 save 就把它持久化（「取消」根本没取消）；
  2) 就算 load 成功，from_dict 也会把 parents 换成新对象，executor 的 scheduler
     仍指向孤立的旧 ParentPlan → 之后完成的动作写进孤立对象被 save 静默丢弃。
- v0.30 修：导入前 to_dict 快照；取消 → from_dict(快照) + on_data_reloaded()
  重建 executor，三个页面重新绑到同一批对象上。
"""

import os
import sys
import json
import tempfile

os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PyQt5.QtWidgets import QApplication, QMessageBox, QFileDialog
from PyQt5.QtCore import QSettings, QDate

_tmp_dir = tempfile.mkdtemp(prefix="rollingplan_qsettings_")
os.environ["XDG_CONFIG_HOME"] = _tmp_dir

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from rollingplan import MainWindow, PlanData

QSettings.setDefaultFormat(QSettings.IniFormat)
QSettings.setPath(QSettings.IniFormat, QSettings.UserScope, _tmp_dir)

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


def make_window_with_data():
    win = MainWindow()
    p = win.data.current_parent
    p.name = "原始分类"
    p.plans = ["原始任务1", "原始任务2"]
    p.time_slots = [{"name": "早", "count": 1}]
    p.start_date = QDate(2026, 1, 1)
    win.data.save()
    return win


def write_foreign_json(path):
    """一份内容完全不同的合法导出文件。"""
    other = PlanData()
    p = other.current_parent
    p.name = "外来分类"
    p.plans = ["外来任务A", "外来任务B", "外来任务C"]
    other.current_parent_idx = 0
    with open(path, "w", encoding="utf-8") as f:
        json.dump(other.export_to_dict(), f, ensure_ascii=False)


def test_import_cancel_restores_snapshot():
    print("\n=== test_import_cancel_restores_snapshot ===")
    win = make_window_with_data()
    fd, path = tempfile.mkstemp(suffix=".json")
    os.close(fd)
    write_foreign_json(path)

    orig_q = QMessageBox.question
    orig_fd = QFileDialog.getOpenFileName
    QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.No)
    QFileDialog.getOpenFileName = staticmethod(lambda *a, **k: (path, ""))
    try:
        win.editor.on_import()
        app.processEvents()
    finally:
        QMessageBox.question = orig_q
        QFileDialog.getOpenFileName = orig_fd

    ok(win.data.current_parent.name == "原始分类", "取消导入：分类名未被覆盖")
    ok(win.data.current_parent.plans == ["原始任务1", "原始任务2"], "取消导入：计划清单未变")
    ok(win.executor.scheduler.p is win.data.current_parent,
       "取消导入：executor 绑定的是当前 ParentPlan（不是孤立旧对象）")
    # 磁盘未被写入（仍是取消前 save 的原始数据）
    fresh = PlanData()
    ok(fresh.load() and fresh.current_parent.plans == ["原始任务1", "原始任务2"],
       "取消导入：磁盘数据保持原样")
    os.remove(path)


def test_import_cancel_works_on_fresh_install():
    print("\n=== test_import_cancel_works_on_fresh_install ===")
    # 全新安装：盘上还没有 plan_data，旧版 load() 回滚在这里失效。
    # （清掉本文件前序测试留下的隔离 QSettings，还原「空盘」前提）
    s = QSettings("RollingPlan", "Data")
    s.clear()
    s.sync()
    win = MainWindow()          # 不 save → 磁盘无数据
    ok(not win.data.load(), "前置：磁盘上没有已保存数据（全新安装）")
    fd, path = tempfile.mkstemp(suffix=".json")
    os.close(fd)
    write_foreign_json(path)

    orig_q = QMessageBox.question
    orig_fd = QFileDialog.getOpenFileName
    QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.No)
    QFileDialog.getOpenFileName = staticmethod(lambda *a, **k: (path, ""))
    try:
        win.editor.on_import()
        app.processEvents()
    finally:
        QMessageBox.question = orig_q
        QFileDialog.getOpenFileName = orig_fd

    ok(win.data.current_parent.name != "外来分类",
       "全新安装取消导入：内存不是导入数据（旧版在这里沦陷）")
    # 而且此刻 save 出去的不该是外来数据
    win.data.save()
    fresh = PlanData()
    fresh.load()
    ok(fresh.current_parent.name != "外来分类", "全新安装取消后 save 不持久化外来数据")
    os.remove(path)


def test_import_confirm_still_applies():
    print("\n=== test_import_confirm_still_applies ===")
    win = make_window_with_data()
    fd, path = tempfile.mkstemp(suffix=".json")
    os.close(fd)
    write_foreign_json(path)

    orig_q = QMessageBox.question
    orig_info = QMessageBox.information
    orig_fd = QFileDialog.getOpenFileName
    QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.Yes)
    # offscreen 下模态 information 会和旧 executor 的延迟删除打架（access violation），
    # 打桩掉 —— 它不是本测试的关注点
    QMessageBox.information = staticmethod(lambda *a, **k: None)
    QFileDialog.getOpenFileName = staticmethod(lambda *a, **k: (path, ""))
    try:
        win.editor.on_import()
        app.processEvents()
    finally:
        QMessageBox.question = orig_q
        QMessageBox.information = orig_info
        QFileDialog.getOpenFileName = orig_fd

    ok(win.data.current_parent.name == "外来分类", "确认导入：数据被替换")
    ok(win.executor.scheduler.p is win.data.current_parent, "确认导入：executor 绑到新数据")
    fresh = PlanData()
    ok(fresh.load() and fresh.current_parent.name == "外来分类", "确认导入：磁盘已更新")
    os.remove(path)


def main():
    test_import_cancel_restores_snapshot()
    test_import_cancel_works_on_fresh_install()
    test_import_confirm_still_applies()

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
