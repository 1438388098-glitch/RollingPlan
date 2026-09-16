"""
RollingPlan 动效模块（v0.29 新增，v0.30 R7 动效 v2 重整）。

设计口径（动效是为了让「状态变了」被看见，不是装饰）：
- 只在状态切换的时刻动：页面切换 / 折叠区展开收起 / 完成并滚动刷新 /
  新内容浮现 / 对话框与主窗口出现
- 撤销、固定、拦截这类操作不加动 —— 用户知道发生了什么，别抢戏
- 时长/缓动统一从 theme.MOTION 取（fast=微反馈 / base=常规 / slow=结构），
  全仓库不再出现散落的 duration 魔数
- v2 变化：窗口级出场用 windowOpacity（合成器侧，便宜且顺滑），
  不再对整页挂 QGraphicsOpacityEffect（每帧全页重绘，观感也廉价）；
  页内淡入保留特效方案但只用于中小控件

流水线约定：
- **QT_QPA_PLATFORM=offscreen 时全部动效自动禁用**（run_all_tests.sh / dump_minimal_view.py
  都跑 offscreen）——禁用路径就是一句 setVisible，测试行为零变化
- QGraphicsOpacityEffect 动完立刻摘掉（setGraphicsEffect(None)），不留渲染开销
- 同一控件的同一动画再次触发时，旧动画先 disconnect+stop（反转折叠中途再点不会跳变）
- 控件中途被销毁（executor.refresh 会 deleteLater 旧行）是安全的：
  QPropertyAnimation 以控件为 parent，控件死动画跟着死；Python 回调全部 try/except RuntimeError
"""

import os

from PyQt5.QtCore import QPropertyAnimation, QEasingCurve
from PyQt5.QtWidgets import (
    QGraphicsOpacityEffect, QWIDGETSIZE_MAX,
)

from theme import MOTION

# 运行时开关（测试之外也可以手动关掉动效）
_ENABLED = True

# QEasingCurve.Type 的名字 → 枚举（延迟解析，避免 import 顺序问题）
_EASINGS = None


def _easing(name):
    global _EASINGS
    if _EASINGS is None:
        from PyQt5.QtCore import QEasingCurve as _EC
        _EASINGS = {
            "OutCubic": _EC.OutCubic,
            "OutQuint": _EC.OutQuint,
            "OutBack": _EC.OutBack,
        }
    if name not in _EASINGS:
        name = "OutCubic"
    return _EASINGS[name]


def enabled():
    """动效总开关。offscreen（headless 测试 / 文字 dump）下恒为 False。"""
    if os.environ.get("QT_QPA_PLATFORM") == "offscreen":
        return False
    return _ENABLED


def set_enabled(value):
    """手动开关动效（offscreen 优先级更高，关不掉它的禁用）。"""
    global _ENABLED
    _ENABLED = bool(value)


# ============== 内部工具 ==============

def _stop_old(widget, key):
    """停掉挂在 widget 身上的旧动画（key = 私有属性名），并断开它的 finished。

    不 disconnect 就 stop 的话，旧动画的 finished 回调会立刻执行
    （比如把刚要重新展开的区域又 setVisible(False)）—— 折叠/展开来回快点会跳变。
    """
    old = getattr(widget, key, None)
    if old is None:
        return
    try:
        old.finished.disconnect()
    except (TypeError, RuntimeError):
        pass
    try:
        old.stop()
    except RuntimeError:
        pass
    try:
        delattr(widget, key)
    except (AttributeError, RuntimeError):
        pass


def _make_anim(target, prop, duration):
    anim = QPropertyAnimation(target, prop.encode(), target)   # parent=target：控件亡则动画亡
    anim.setDuration(duration)
    anim.setEasingCurve(_easing(MOTION.get("ease", "OutCubic")))
    return anim


# ============== 对外动效 ==============

def fade_in(widget, duration=None):
    """淡入：0 → 1 透明度，动完摘掉特效。默认时长 MOTION['base']。

    只应该对「已经可见」的控件调用（调用方先 setVisible(True)）。
    isVisible 全程为 True，所以这个动效不影响任何基于可见性的测试断言。
    大面积整页不建议用（每帧全页重绘）——整页/窗口请用 pop_window / launch_fade。
    """
    if widget is None or not enabled() or not widget.isVisible():
        return
    key = "_rp_anim_fade"
    _stop_old(widget, key)
    effect = widget.graphicsEffect()
    if not isinstance(effect, QGraphicsOpacityEffect):
        effect = QGraphicsOpacityEffect(widget)
        widget.setGraphicsEffect(effect)
    effect.setOpacity(0.0)
    anim = _make_anim(effect, "opacity", duration or MOTION["base"])

    def _finished():
        try:
            widget.setGraphicsEffect(None)   # 摘特效（同时删除 effect）
            delattr(widget, key)
        except (AttributeError, RuntimeError):
            pass

    anim.finished.connect(_finished)
    setattr(widget, key, anim)
    anim.start(QPropertyAnimation.DeleteWhenStopped)


def pop_window(widget, duration=None):
    """窗口出场：windowOpacity 0 → 1（合成器侧动画，顺滑且零布局开销）。

    只对真窗口（isWindow()）生效；对话框弹出、主窗口启动共用这一套。
    """
    if widget is None or not enabled() or not widget.isWindow():
        return
    key = "_rp_anim_winpop"
    _stop_old(widget, key)
    widget.setWindowOpacity(0.0)
    anim = _make_anim(widget, "windowOpacity", duration or MOTION["fast"])
    anim.setStartValue(0.0)
    anim.setEndValue(1.0)

    def _finished():
        try:
            widget.setWindowOpacity(1.0)
            delattr(widget, key)
        except (AttributeError, RuntimeError):
            pass

    anim.finished.connect(_finished)
    setattr(widget, key, anim)
    anim.start(QPropertyAnimation.DeleteWhenStopped)


def launch_fade(window):
    """应用启动出场：主窗口 windowOpacity 0 → 1，只做一次。"""
    if getattr(window, "_rp_launched", False):
        return
    window._rp_launched = True
    pop_window(window, MOTION["base"])


def toggle_section(widget, visible, duration=None):
    """折叠区展开 / 收起（高度动画）。禁用路径 = 一句 setVisible，零行为变化。

    用 maximumHeight 而不是 geometry —— 让父布局自己重排，下面内容被平滑推上/推下。
    展开完成后把 maximumHeight 还原成无上限，窗口拉伸不受影响。
    """
    if widget is None:
        return
    if not enabled():
        widget.setVisible(visible)
        return
    if visible:
        was_hidden = not widget.isVisible()
        widget.setMaximumHeight(0)
        widget.setVisible(True)
        hint = widget.sizeHint()
        target = max(hint.height(), widget.minimumSizeHint().height(), 1)
        _animate_property(
            widget, "maximumHeight", 0, target, duration or MOTION["slow"],
            on_finished=lambda: widget.setMaximumHeight(QWIDGETSIZE_MAX),
        )
        if was_hidden:
            fade_in(widget, min(duration or MOTION["base"], MOTION["base"]))
    else:
        if not widget.isVisible():
            return
        _animate_property(
            widget, "maximumHeight", widget.height(), 0,
            max((duration or MOTION["slow"]) - 40, MOTION["fast"]),
            on_finished=lambda: (
                widget.setVisible(False),
                widget.setMaximumHeight(QWIDGETSIZE_MAX),
            ),
        )


def _animate_property(widget, prop, start, end, duration, on_finished=None):
    """对 widget 的 Qt 属性做一次 OutCubic 动画，动完自动清理。"""
    key = "_rp_anim_" + prop
    if not enabled():
        if on_finished is not None:
            on_finished()
        return
    _stop_old(widget, key)
    anim = _make_anim(widget, prop, duration)
    anim.setStartValue(start)
    anim.setEndValue(end)

    def _finished():
        try:
            delattr(widget, key)
        except (AttributeError, RuntimeError):
            pass
        if on_finished is not None:
            try:
                on_finished()
            except RuntimeError:
                pass

    anim.finished.connect(_finished)
    setattr(widget, key, anim)
    anim.start(QPropertyAnimation.DeleteWhenStopped)
