"""RollingPlan 主题模块（v0.30 设计系统重做）。

v0.7 起弃用 pyqtdarktheme 改自写 QSS；v0.14 抽出本模块；
v0.30 把「两份各自漂移的 QSS 大字符串」重写成「**一套 token 表 + 一份 QSS 模板**」：

- ``DARK_TOKENS`` / ``LIGHT_TOKENS``：全部颜色只在这两处定义（测试锚点色
  #1e1e1e / #f5f5f5 / #cccccc 保持不变，test_theme_v05 直接断言它们）
- ``QSS_TEMPLATE``：一份模板，``$name`` 占位（用 string.Template，避开 QSS 花括号），
  DARK_QSS / LIGHT_QSS 由它生成 —— 两套主题再也不可能漂移
- 语义角色选择器（``#rpPrimary`` / ``#rpSuccessSm`` / ``#rpCard`` / ``#rpDim`` …）：
  页面只 setObjectName，颜色全走全局 QSS —— 修掉 v0.29 前页面里几十处
  「widget 级硬编码色不跟主题走」的对比度 bug（深色下浅底浅字、#666 灰字看不见）
- 动效时长/缓动表（``MOTION``）也归口在这里，animations.py 与页面都从这取值

对外 API 不变：THEME_KEY / THEME_OPTIONS / DARK_QSS / LIGHT_QSS / apply_theme()。
"""

import string
import sys

# logging / RotatingFileHandler 复用主程序的 handler 名 "rollingplan"
import logging
from logging.handlers import RotatingFileHandler


THEME_KEY = "RollingPlan/theme"  # QSettings key


def app_settings():
    """全局唯一的 QSettings 入口（v0.30 R10）。

    用显式 IniFormat 四参构造 —— 旧的两参构造在 Windows 上走注册表
    （HKCU\Software\RollingPlan\Data）：数据不可备份、不可迁移、测试也无法隔离
    （setPath 只对 IniFormat 生效）。INI 文件与上游 Linux 布局一致，可备份可带走。
    """
    from PyQt5.QtCore import QSettings as _QS
    return _QS(_QS.IniFormat, _QS.UserScope, "RollingPlan", "Data")

THEME_OPTIONS = [
    ("dark", "深色"),
    ("light", "亮色"),
    ("auto", "跟随系统"),
]


# ============== 设计 token 表 ==============
# 规则：全仓库颜色只允许出现在这两张表里（页面用语义对象名走 QSS；
# 确实需要在代码里取色的场合用 current_tokens()）。
# ⚠️ 测试锚点：DARK 必须含 #1e1e1e（窗口底）与 #cccccc（基准文字），
#            LIGHT 必须含 #f5f5f5 与 #222222 —— test_theme_v05 直接断言。

DARK_TOKENS = dict(
    # 背景：窗口 < 卡片 < 输入面，三级层次
    bg="#1e1e1e",
    card="#232329",
    surface="#2a2a31",
    surface_hover="#33343d",
    divider="#33343c",
    border="#3c3d46",
    # 文字：strong > 基准 > dim（次要）> faint（弱化/已完成）
    text="#cccccc",
    text_strong="#e8e8e8",
    text_dim="#9a9da8",
    text_faint="#71747f",
    # 品牌蓝（选中 / 主操作 / 焦点）
    accent="#4f8cff",
    accent_hover="#6a9eff",
    accent_pressed="#3f74e0",
    on_accent="#ffffff",
    accent_soft="rgba(79,140,255,0.16)",
    # 语义色
    success="#4caf7d",
    success_hover="#5fc08e",
    success_pressed="#3d9a6a",
    success_soft="rgba(76,175,125,0.13)",
    danger="#e06666",
    danger_soft="rgba(224,102,102,0.14)",
    # 控件
    btn="#33343c",
    btn_hover="#3f404a",
    btn_pressed="#2a2b32",
    btn_disabled_bg="#26262c",
    btn_disabled_text="#66686f",
    btn_disabled_border="#33343c",
    input_bg="#2a2a31",
    input_text="#e8e8e8",
    input_border="#3c3d46",
    scroll="#5a5b64",
    scroll_hover="#787a84",
    shadow="rgba(0,0,0,0.45)",
)

LIGHT_TOKENS = dict(
    bg="#f5f5f5",
    card="#ffffff",
    surface="#ffffff",
    surface_hover="#eef0f4",
    divider="#e4e6eb",
    border="#d8dae0",
    text="#222222",
    text_strong="#111111",
    text_dim="#5d6270",
    text_faint="#9aa0ab",
    accent="#2e6fd8",
    accent_hover="#4380e8",
    accent_pressed="#2359b8",
    on_accent="#ffffff",
    accent_soft="rgba(46,111,216,0.10)",
    success="#2e9e63",
    success_hover="#38b273",
    success_pressed="#278a54",
    success_soft="rgba(46,158,99,0.10)",
    danger="#d64545",
    danger_soft="rgba(214,69,69,0.10)",
    btn="#e9eaee",
    btn_hover="#dde0e6",
    btn_pressed="#d0d3da",
    btn_disabled_bg="#f0f1f4",
    btn_disabled_text="#a4a9b4",
    btn_disabled_border="#e0e2e8",
    input_bg="#ffffff",
    input_text="#111111",
    input_border="#d8dae0",
    scroll="#c3c6cd",
    scroll_hover="#9da1ab",
    shadow="rgba(0,0,0,0.18)",
)

# 动效 token：全仓库时长/缓动只从这里取（animations.py / 页面统一口径）
MOTION = dict(
    fast=140,        # 微反馈：按压、hover 补偿、轻淡入
    base=200,        # 常规：淡入、浮现
    slow=280,        # 结构：折叠展开
    collapse=240,    # 结构：折叠收起（略快于展开，收比开利落）
    ease="OutCubic", # QEasingCurve.Type 名字（animations 负责映射）
)


def current_tokens(theme_name=None):
    """返回指定主题的 token 表；theme_name=None 时返回「当前已应用」的那套。
    apply_theme 之前调用返回 DARK_TOKENS（默认主题）。"""
    name = theme_name or _CURRENT_NAME
    return DARK_TOKENS if name != "light" else LIGHT_TOKENS


_CURRENT_NAME = "dark"


# ============== QSS 模板（$name 占位） ==============

QSS_TEMPLATE = """
QWidget {
    background-color: $bg;
    color: $text;
    font-family: "Microsoft YaHei", "Segoe UI", "Helvetica Neue", sans-serif;
    font-size: 13pt;
}
QMainWindow, QDialog {
    background-color: $bg;
}
QLabel {
    background: transparent;
    color: $text;
}

/* ---- 语义文字角色（页面 setObjectName，不再写 widget 级颜色）---- */
QLabel#rpTitle { font-size: 17pt; font-weight: bold; color: $text_strong; }
QLabel#rpH2 { font-size: 14pt; font-weight: bold; color: $text_strong; }
QLabel#rpDim { color: $text_dim; }
QLabel#rpFaint { color: $text_faint; }
QLabel#rpDone { color: $text_faint; text-decoration: line-through; }
QLabel#rpEmpty { color: $text_faint; font-style: italic; }
QLabel#rpOnAccent { color: $on_accent; }

/* ---- 输入类 ---- */
QLineEdit, QListWidget, QComboBox, QSpinBox, QDateEdit, QTextEdit, QPlainTextEdit {
    background-color: $input_bg;
    color: $input_text;
    border: 1px solid $input_border;
    border-radius: 6px;
    padding: 5px 8px;
    selection-background-color: $accent;
    selection-color: $on_accent;
}
QLineEdit:focus, QListWidget:focus, QComboBox:focus, QSpinBox:focus,
QDateEdit:focus, QTextEdit:focus, QPlainTextEdit:focus {
    border: 1px solid $accent;
}
QListWidget::item { padding: 5px 8px; color: $text; background: transparent; }
QListWidget::item:selected { background-color: $accent; color: $on_accent; }
QListWidget::item:hover:!selected { background-color: $surface_hover; }
QComboBox::drop-down { border: none; width: 22px; }
QComboBox QAbstractItemView {
    background-color: $surface;
    color: $text;
    border: 1px solid $border;
    selection-background-color: $accent;
    selection-color: $on_accent;
}

/* ---- 按钮 ---- */
QPushButton {
    background-color: $btn;
    color: $text_strong;
    border: 1px solid $border;
    border-radius: 6px;
    padding: 7px 16px;
}
QPushButton:hover { background-color: $btn_hover; }
QPushButton:pressed { background-color: $btn_pressed; }
QPushButton:focus { border: 1px solid $accent; }
QPushButton:disabled {
    color: $btn_disabled_text;
    background-color: $btn_disabled_bg;
    border-color: $btn_disabled_border;
}
QPushButton#rpPrimary {
    background-color: $accent;
    color: $on_accent;
    border: 1px solid $accent;
    font-weight: bold;
}
QPushButton#rpPrimary:hover { background-color: $accent_hover; border-color: $accent_hover; }
QPushButton#rpPrimary:pressed { background-color: $accent_pressed; }
QPushButton#rpSuccess {
    background-color: $success;
    color: $on_accent;
    border: 1px solid $success;
    font-weight: bold;
}
QPushButton#rpSuccess:hover { background-color: $success_hover; border-color: $success_hover; }
QPushButton#rpSuccess:pressed { background-color: $success_pressed; }
QPushButton#rpSuccessSm {
    background-color: $success;
    color: $on_accent;
    border: none;
    border-radius: 5px;
    padding: 5px 12px;
    font-weight: bold;
}
QPushButton#rpSuccessSm:hover { background-color: $success_hover; }
QPushButton#rpSuccessSm:pressed { background-color: $success_pressed; }
QPushButton#rpGhost, QToolButton#rpGhost {
    background: transparent;
    color: $text_dim;
    border: none;
}
QPushButton#rpGhost:hover, QToolButton#rpGhost:hover {
    background-color: $surface_hover;
    color: $text_strong;
}
QPushButton#rpGhost:pressed, QToolButton#rpGhost:pressed {
    background-color: $btn_pressed;
}
QPushButton#rpGhostOutline {
    background: transparent;
    color: $text_dim;
    border: 1px solid $border;
    border-radius: 6px;
    padding: 4px;
}
QPushButton#rpGhostOutline:hover { background-color: $accent_soft; color: $text_strong; border-color: $accent; }
QPushButton#rpGhostOutline:pressed { background-color: $btn_pressed; }
QPushButton#rpDangerGhost {
    background: transparent;
    color: $danger;
    border: 1px solid $border;
}
QPushButton#rpDangerGhost:hover { background-color: $danger_soft; border-color: $danger; }

/* ---- 工具按钮（折叠开关 / 更多 / ⋯）---- */
QToolButton {
    background: transparent;
    color: $text;
    border: none;
    padding: 6px 10px;
    text-align: left;
}
QToolButton:hover { color: $text_strong; }
QToolButton:checked { color: $accent; font-weight: bold; }
QToolButton#rpFold {
    color: $text_dim;
    padding: 5px 8px;
    border-radius: 6px;
}
QToolButton#rpFold:hover { background-color: $surface_hover; color: $text_strong; }
QToolButton#rpFold:checked { background-color: $accent_soft; color: $accent; }

/* ---- 页签 ---- */
QTabWidget::pane {
    border: 1px solid $border;
    background-color: $bg;
    top: -1px;
}
QTabBar::tab {
    background-color: $card;
    color: $text_dim;
    border: 1px solid $border;
    border-bottom: none;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
    padding: 7px 18px;
    margin-right: 2px;
}
QTabBar::tab:selected {
    color: $on_accent;
    background-color: $accent;
    font-weight: bold;
    border-color: $accent;
}
QTabBar::tab:hover:!selected { background-color: $surface_hover; color: $text_strong; }

/* ---- 卡片 / 分组 ---- */
QGroupBox {
    background-color: $card;
    border: 1px solid $border;
    border-radius: 8px;
    margin-top: 14px;
    padding: 10px;
    font-weight: bold;
}
QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    padding: 0 6px;
    color: $text_dim;
}
QWidget#rpCard {
    background-color: $card;
    border: 1px solid $border;
    border-radius: 8px;
}
QWidget#rpSlotCard {
    background-color: $card;
    border: 1px solid $border;
    border-left: 3px solid $accent;
    border-radius: 8px;
}
QWidget#rpSlotCard:hover {
    background-color: $surface_hover;
    border-color: $accent;
}
QWidget#rpExtraCard:hover {
    background-color: $surface_hover;
}
QWidget#rp-note-detail { background: transparent; }
QWidget#rpExtraCard {
    background-color: $success_soft;
    border: 1px solid $border;
    border-left: 3px solid $success;
    border-radius: 4px;
}
QFrame#rpDivider { background-color: $divider; max-height: 1px; border: none; }

/* ---- 滚动条（细、圆、悬停加深）---- */
QScrollBar:vertical { background: $bg; width: 10px; border: none; }
QScrollBar::handle:vertical { background: $scroll; border-radius: 4px; min-height: 24px; }
QScrollBar::handle:vertical:hover { background: $scroll_hover; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar:horizontal { background: $bg; height: 10px; border: none; }
QScrollBar::handle:horizontal { background: $scroll; border-radius: 4px; min-width: 24px; }
QScrollBar::handle:horizontal:hover { background: $scroll_hover; }
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0; }

/* ---- 菜单 / 弹窗 ---- */
QMenu {
    background-color: $surface;
    color: $text;
    border: 1px solid $border;
    border-radius: 6px;
    padding: 4px;
}
QMenu::item { padding: 5px 24px 5px 12px; border-radius: 4px; }
QMenu::item:selected { background-color: $accent; color: $on_accent; }
QMenu::separator { height: 1px; background: $divider; margin: 4px 8px; }
QMenuBar { background-color: $bg; color: $text; }
QMenuBar::item:selected { background-color: $surface_hover; }
QMessageBox, QInputDialog { background-color: $bg; }
QMessageBox QLabel { color: $text; }

/* ---- 其它 ---- */
QProgressBar {
    background-color: $surface;
    border: 1px solid $border;
    border-radius: 5px;
    text-align: center;
    color: $text;
}
QProgressBar::chunk { background-color: $accent; border-radius: 5px; }
QCheckBox { color: $text; background: transparent; }
QRadioButton { color: $text; background: transparent; }
QStatusBar { background-color: $bg; color: $text_dim; }
QToolTip {
    background-color: $surface;
    color: $text_strong;
    border: 1px solid $border;
    padding: 4px 8px;
}
"""

DARK_QSS = string.Template(QSS_TEMPLATE).substitute(**DARK_TOKENS)
LIGHT_QSS = string.Template(QSS_TEMPLATE).substitute(**LIGHT_TOKENS)


def _theme_log(msg):
    """写日志(复用主程序 logger 名 + stderr),与 rollingplan._log 行为等价。
    文件 log 走 logging.getLogger("rollingplan"),由主程序 _setup_logger() 注册;
    stderr 部分用 try/except 包住,避免 --windowed 下 stderr=None 崩溃。"""
    try:
        logging.getLogger("rollingplan").debug(msg)
    except Exception:
        pass
    try:
        sys.stderr.write("[RollingPlan] {}\n".format(msg))
    except Exception:
        pass


def _detect_system_theme():
    """检测系统是否是深色模式。Windows 走注册表,macOS 走 defaults,其他返回 False。"""
    try:
        if sys.platform == "win32":
            import winreg
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                                  r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize")
            value, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
            return value == 0
        elif sys.platform == "darwin":
            import subprocess
            result = subprocess.run(
                ["defaults", "read", "-g", "AppleInterfaceStyle"],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                universal_newlines=True, timeout=2,
            )
            return result.stdout.strip().lower() == "dark"
    except Exception as e:
        _theme_log("detect system theme failed: {}".format(e))
    return False


def apply_theme(app, theme_name):
    """应用主题(自写 QSS,无外部依赖)。
    theme_name: "dark" / "light" / "auto"
    """
    global _CURRENT_NAME
    _theme_log("apply_theme({}) called".format(theme_name))

    if theme_name == "auto":
        is_dark = _detect_system_theme()
        actual = "dark" if is_dark else "light"
        _theme_log("auto -> {} (system dark={})".format(actual, is_dark))
    else:
        actual = theme_name

    qss = DARK_QSS if actual == "dark" else LIGHT_QSS
    app.setStyleSheet(qss)
    _CURRENT_NAME = "dark" if actual == "dark" else "light"
    _theme_log("theme applied: {}, qss len={}".format(_CURRENT_NAME, len(qss)))
