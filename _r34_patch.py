# -*- coding: utf-8 -*-
"""R34 补丁：完成反馈强调（跑完即删）"""
import io

# 1) theme.py：rpFlash 语义角色
with io.open("theme.py", "r", encoding="utf-8") as f:
    src = f.read()
old = u'''QLabel#rpSmall { font-size: 11pt; color: $text_dim; }'''
new = u'''QLabel#rpSmall { font-size: 11pt; color: $text_dim; }
QLabel#rpFlash { color: $success; font-weight: bold; }'''
assert src.count(old) == 1
src = src.replace(old, new)
with io.open("theme.py", "w", encoding="utf-8", newline="") as f:
    f.write(src)
print("theme.py ok")

# 2) executor.py：完成并滚动后状态行闪 success
with io.open("executor.py", "r", encoding="utf-8") as f:
    src = f.read()
old = u'''    def on_complete_slot(self, slot_idx):
        """完成并滚动：归档这一格，后面的整体上滚一格"""
        if self.scheduler.complete_today_slot(slot_idx):
            self.data.save()
            self.refresh()
            animations.fade_in(self.day_container, 150)   # 完成滚动后的轻反馈'''
new = u'''    def _flash_status(self):
        """v0.30 R34（走查 #8）：状态行闪 success 色，让「生效了」看得见。"""
        if not animations.enabled():
            return
        self.status_label.setObjectName("rpFlash")
        self.status_label.setStyleSheet("")   # 触发重排版（颜色走 QSS）
        self.status_label.style().unpolish(self.status_label)
        self.status_label.style().polish(self.status_label)
        from PyQt5.QtCore import QTimer
        QTimer.singleShot(900, self._unflash_status)

    def _unflash_status(self):
        self.status_label.setObjectName("rpDim")
        self.status_label.style().unpolish(self.status_label)
        self.status_label.style().polish(self.status_label)

    def on_complete_slot(self, slot_idx):
        """完成并滚动：归档这一格，后面的整体上滚一格"""
        if self.scheduler.complete_today_slot(slot_idx):
            self.data.save()
            self.refresh()
            animations.fade_in(self.day_container, 150)   # 完成滚动后的轻反馈
            self._flash_status()'''
assert src.count(old) == 1
src = src.replace(old, new)
# style() 需要 import
old = u'''from PyQt5.QtGui import QFont, QCursor'''
new = u'''from PyQt5.QtGui import QFont, QCursor
from PyQt5.QtGui import QPalette'''
if "QPalette" not in src:
    pass  # 不需要 QPalette，占位
with io.open("executor.py", "w", encoding="utf-8", newline="") as f:
    f.write(src)
print("executor.py ok")
