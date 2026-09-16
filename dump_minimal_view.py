"""把执行页「默认视图」里可见的控件按树打出来 —— 用文字代替截图，验证极简效果。

用法：QT_QPA_PLATFORM=offscreen <venv python> dump_minimal_view.py
"""
import os
import sys

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PyQt5.QtCore import QDate  # noqa: E402
from PyQt5.QtWidgets import (  # noqa: E402
    QApplication,
    QAbstractButton,
    QComboBox,
    QGroupBox,
    QLabel,
)

app = QApplication(sys.argv)

from rollingplan import PlanData, PlanExecutor  # noqa: E402


def make_data():
    data = PlanData()
    p = data.parents[0]
    p.name = "备考"
    p.time_slots = [{"name": "早", "count": 1}, {"name": "中", "count": 1}, {"name": "晚", "count": 1}]
    p.plans = ["电机学 第一轮", "电力电子 强化", "高电压 错题", "行测 判断推理", "电分 计算"]
    p.start_date = QDate.currentDate()
    p.archived = ["电分 第一章"]
    p.archived_base = 0
    return data


def walk(w, depth=0, out=None):
    out = out if out is not None else []
    if not w.isVisible():
        return out
    klass = type(w).__name__
    text = ""
    if isinstance(w, QAbstractButton):
        text = w.text()
    elif isinstance(w, QLabel):
        text = w.text()
    elif isinstance(w, QGroupBox):
        text = w.title()
    elif isinstance(w, QComboBox):
        text = "下拉[{}]".format(w.currentText())
    if text or klass in ("QLineEdit", "QTextEdit"):
        out.append("{}{} {} {}x{} @{},{}".format(
            "  " * depth, klass, text[:24], w.width(), w.height(), w.x(), w.y()))
    for child in w.children():
        if hasattr(child, "isVisible"):
            walk(child, depth + 1, out)
    return out


ex = PlanExecutor(make_data(), lambda: None)
ex.resize(560, 780)
ex.show()
app.processEvents()

print("=== 执行页「默认视图」（未点「更多」）可见控件 ===")
for line in walk(ex):
    print(line)

ex.advanced_toggle.click()
app.processEvents()
print()
print("=== 点开「更多」之后 ===")
for line in walk(ex):
    print(line)

from rollingplan import PlanEditor  # noqa: E402

ed = PlanEditor(make_data(), lambda: None)
ed.resize(560, 780)
ed.show()
app.processEvents()
print()
print("=== 制定页「默认视图」可见控件 ===")
for line in walk(ed):
    print(line)

from calendar_view import PlanCalendarView  # noqa: E402

cv = PlanCalendarView(make_data())
cv.resize(560, 780)
cv.show()
app.processEvents()
print()
print("=== 归档总览页「默认视图」可见控件 ===")
for line in walk(cv):
    print(line)
