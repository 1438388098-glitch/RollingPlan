# -*- coding: utf-8 -*-
"""R35 文档补丁（跑完即删）"""
import io

with io.open("STATE.md", "r", encoding="utf-8") as f:
    src = f.read()

old = u'''|  | R22 本文档轮 |'''
new = u'''|  | R22 本文档轮 |
|  | R23~R31（expansion）一键恢复上次备份（可来回切/选代数）、分类名唯一性、无选中提示、列表高度+保选保滚动、双击编辑、窗口标题带分类+启动居中、3 代备份环、禁用按钮原因提示、主题切换轻淡入 |
|  | R32~R34（走查审计 Top 修复）：「✓ 今天完成」→「⏭ 结束今天 →」、引导条指路折叠、「保存并预览」让主样式给「开始执行 →」、删除按钮 rpDangerGhost、撤销/重做移出折叠区常驻显现、完成后状态行闪 success 色 |
|  | R35 重新打包 exe（39,050,053 字节，PyInstaller 6.x + Python 3.13 + PyQt5，v0.30 全部改动；仍未真机启动验证）|'''
assert src.count(old) == 1
src = src.replace(old, new)

old = u'''> 待办 = **真机验收 + push（本地 main 领先远端 20+ 提交）**'''
new = u'''> 待办 = **真机验收 + push（本地 main 领先远端 30+ 提交）**；dist/RollingPlan.exe 已重打为 v0.30'''
assert src.count(old) == 1
src = src.replace(old, new)

with io.open("STATE.md", "w", encoding="utf-8", newline="") as f:
    f.write(src)
print("STATE.md ok")

# .gitignore：构建产物不进库
gi = u"""__pycache__/
build/
dist/
*.spec
.autopilot/
"""
with io.open(".gitignore", "w", encoding="utf-8", newline="") as f:
    f.write(gi)
print(".gitignore ok")
