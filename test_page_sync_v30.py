"""RollingPlan v0.30 页面间数据同步回归测试

防的坑（健壮性审计 P1-3 / P1-4）：
- P1-3：执行页切换分类后，制定页 date_edit 还显示旧分类的日期；
  回制定页一保存，新分类的 start_date 被旧日期静默覆写
- P1-4：在制定页改了计划清单后直点执行页 tab，界面还是旧行，
  点「完成并滚动」归档的不是用户看到的那条
"""

import os
import sys
import tempfile

os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import QSettings, QDate

_tmp_dir = tempfile.mkdtemp(prefix="rollingplan_qsettings_")
os.environ["XDG_CONFIG_HOME"] = _tmp_dir

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from rollingplan import MainWindow

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
    d = win.data
    p1 = d.current_parent
    p1.name = "工作"
    p1.plans = ["任务1", "任务2"]
    p1.time_slots = [{"name": "早", "count": 1}]
    p1.start_date = QDate(2026, 1, 1)
    d.add_parent("学习")
    p2 = d.parents[1]
    p2.plans = ["英语"]
    p2.time_slots = [{"name": "晚", "count": 1}]
    p2.start_date = QDate(2027, 6, 15)   # 与分类1截然不同的日期
    return win


def test_switch_parent_no_date_overwrite():
    print("\n=== test_switch_parent_no_date_overwrite ===")
    win = make_window()
    win.editor.refresh_all()
    win.show_executor()                       # 进执行页（executor 绑分类1）
    win.executor.on_switch_parent_ui = True   # 占位，实际用 QInputDialog 桩模拟切换
    # 直接模拟切换结果：改 current_parent_idx 后重建 executor scheduler（与 on_switch_parent 一致）
    win.data.current_parent_idx = 1
    win.executor.scheduler = __import__("rollingplan").PlanScheduler(win.data.current_parent)
    # 走修复后的 show_editor：先 refresh_all 同步控件
    win.show_editor()
    ok(win.editor.date_edit.date() == win.data.current_parent.start_date,
       "进制定页：date_edit 已同步到当前分类的 start_date")
    win.editor.save_current_to_parent()
    ok(win.data.current_parent.start_date == QDate(2027, 6, 15),
       "保存编辑：新分类的 start_date 不被旧日期覆写")


def test_executor_refreshes_on_tab_show():
    print("\n=== test_executor_refreshes_on_tab_show ===")
    win = make_window()
    win.show_executor()
    win.tabs.setCurrentIndex(0)               # 回制定页
    # 删掉第一条计划（executor 的界面此时还是旧行）
    win.data.current_parent_idx = 0
    win.data.current_parent.plans.pop(0)
    # 直点执行页 tab（触发 _on_tab_changed）
    win._on_tab_changed(win.tabs.indexOf(win.executor))
    rows = win.executor.scheduler.today_state()["rows"]
    shown = [plan for _, plan in rows]
    ok(shown[0] == "任务2", "直点执行页：首格显示的是刷新后的计划（任务2）")
    # 完成第一格，归档的应该就是界面上的「任务2」
    win.executor.on_complete_slot(0)
    ok(win.data.current_parent.archived[0] == "任务2",
       "完成并滚动：归档的是用户看到的那条")


def main():
    test_switch_parent_no_date_overwrite()
    test_executor_refreshes_on_tab_show()

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
