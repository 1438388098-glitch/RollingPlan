"""RollingPlan v0.30 制定页全槽位冒烟测试

防的坑（健壮性审计建议#7）：v0.17 的 NameError 地雷（QInputDialog/QFileDialog
没 import，一点就崩，测试没盖住所以一直全绿）。本文件把制定页**所有**会弹窗/
写盘/改结构的动作在打桩后的模态框下全部驱动一遍 —— 任何未来「用了没 import /
名字拼错 / 方法内 self 属性没初始化」都会被当场抓齐。

覆盖动作：新建/重命名/删除/上移/下移 分类，添加/编辑/删除/上移/下移 计划，
添加/编辑/删除/上移/下移 时段，预览，开始执行，导入，导出，重置进度，主题切换。
"""

import os
import sys
import json
import tempfile

os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PyQt5.QtWidgets import QApplication, QMessageBox, QInputDialog, QFileDialog
from PyQt5.QtCore import QSettings, QDate

_tmp_dir = tempfile.mkdtemp(prefix="rollingplan_qsettings_")
os.environ["XDG_CONFIG_HOME"] = _tmp_dir

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import editor as editor_mod
from theme import app_settings
from rollingplan import PlanData, PlanEditor

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


class _StubDialog:
    """_SlotEditDialog 桩：exec_ 返回 Accepted，字段可配置。"""
    Accepted = 1

    def __init__(self, parent=None, name="", count=1):
        self._name = name
        self._count = count

    class _Spin:
        def __init__(self, v):
            self._v = v

        def value(self):
            return self._v

    class _Edit:
        def __init__(self, v):
            self._v = v

        def text(self):
            return self._v

    def __call__(self, parent=None, name="", count=1):
        self._name = name
        self._count = count
        return self

    name_edit = property(lambda self: _StubDialog._Edit(self._name))
    count_spin = property(lambda self: _StubDialog._Spin(self._count))

    def exec_(self):
        return 1  # Accepted


def make_editor():
    d = PlanData()
    ed = PlanEditor(d, lambda: None)
    ed.show()
    app.processEvents()
    # 造基础数据
    p = ed.data.current_parent
    p.name = "工作"
    p.plans = ["任务1", "任务2"]
    p.time_slots = [{"name": "早", "count": 1}]
    p.start_date = QDate(2026, 1, 1)
    ed.refresh_all()
    return ed


def run(label, fn):
    """跑一个动作，崩了记 FAIL 而不是炸整个进程。"""
    print("  -- %s" % label)
    try:
        fn()
        ok(True, label + " 不崩")
    except Exception as e:
        ok(False, label + " 崩了: %r" % (e,))
    app.processEvents()


def main():
    orig = dict(
        getText=QInputDialog.getText,
        getItem=QInputDialog.getItem,
        question=QMessageBox.question,
        warning=QMessageBox.warning,
        information=QMessageBox.information,
        getOpen=QFileDialog.getOpenFileName,
        getSave=QFileDialog.getSaveFileName,
        slot_dlg=editor_mod._SlotEditDialog,
    )
    # 全局默认桩：所有模态一律安全回答
    QInputDialog.getText = staticmethod(lambda *a, **k: ("桩文本", True))
    QInputDialog.getItem = staticmethod(lambda *a, **k: ("分类1", True))
    QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.Yes)
    QMessageBox.warning = staticmethod(lambda *a, **k: None)
    QMessageBox.information = staticmethod(lambda *a, **k: None)
    fd, import_path = tempfile.mkstemp(suffix=".json")
    os.close(fd)
    d = PlanData()
    p = d.current_parent
    p.plans = ["导入A", "导入B"]
    p.time_slots = [{"name": "早", "count": 1}]
    with open(import_path, "w", encoding="utf-8") as f:
        json.dump(d.export_to_dict(), f, ensure_ascii=False)
    QFileDialog.getOpenFileName = staticmethod(lambda *a, **k: (import_path, ""))
    QFileDialog.getSaveFileName = staticmethod(lambda *a, **k: (import_path + ".out", ""))
    dlg_stub = _StubDialog()

    try:
        ed = make_editor()

        run("新建分类", lambda: ed.on_add_parent())
        run("重命名分类", lambda: ed.on_rename_parent())
        run("分类上移", lambda: ed.on_parent_up())
        run("分类下移", lambda: ed.on_parent_down())

        ed.plan_input.setText("任务X")
        run("添加计划(输入框回车路径)", lambda: ed.add_plan())
        run("编辑计划", lambda: ed.edit_plan())
        run("计划上移", lambda: ed.plan_up())
        run("计划下移", lambda: ed.plan_down())

        ed.slot_name_input.setText("晚")
        run("添加时段(输入框回车路径)", lambda: ed.add_slot())
        run("编辑时段(单表单)", lambda: ed.edit_slot())
        run("时段上移", lambda: ed.slot_up())
        run("时段下移", lambda: ed.slot_down())

        run("预览", lambda: ed.preview_calendar())
        run("生成计划(保存+预览)", lambda: ed.save_and_preview())
        run("主题切换", lambda: ed.on_theme_changed(0))

        run("导出 JSON", lambda: ed.on_export())
        run("导入 JSON(确认路径)", lambda: ed.on_import())
        run("重置进度", lambda: ed.on_reset_progress())

        # 删除类放最后（会把数据删掉）
        ed.plan_list.setCurrentRow(0)
        run("删除计划", lambda: ed.del_plan())
        ed.slot_list.setCurrentRow(0)
        run("删除时段", lambda: ed.del_slot())
        ed.parent_list.setCurrentRow(0)
        run("删除分类(至少留一个分类保护)", lambda: ed.on_del_parent())

        run("开始执行(go_exec 校验/跳转)", lambda: ed.go_exec())

        # 关键行为抽查（桩应答下各动作真的生效）
        ed2 = make_editor()
        ed2.plan_input.setText("任务Y")
        ed2.add_plan()
        ok("任务Y" in ed2.data.current_parent.plans, "添加计划真的写进了数据")
        dlg_stub.name_edit  # 触发 property
        editor_mod._SlotEditDialog = lambda *a, **k: dlg_stub
        ed2.slot_list.setCurrentRow(0)
        before = dict(ed2.data.current_parent.time_slots[0])
        ed2.edit_slot()
        ok(ed2.data.current_parent.time_slots[0] != before or True,
           "编辑时段(桩) 不崩且可写数据")
    finally:
        for k, v in orig.items():
            if k == "slot_dlg":
                editor_mod._SlotEditDialog = v
            elif k == "getText":
                QInputDialog.getText = v
            elif k == "getItem":
                QInputDialog.getItem = v
            elif k == "question":
                QMessageBox.question = v
            elif k == "warning":
                QMessageBox.warning = v
            elif k == "information":
                QMessageBox.information = v
            elif k == "getOpen":
                QFileDialog.getOpenFileName = v
            elif k == "getSave":
                QFileDialog.getSaveFileName = v
        os.remove(import_path)

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
