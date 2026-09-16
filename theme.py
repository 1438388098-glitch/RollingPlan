"""RollingPlan 主题模块(v0.14 重构抽出)。

v0.7 起弃用 pyqtdarktheme,自写 QSS。本模块把所有主题相关的东西集中到一处:
- QSS 字符串常量(DARK_QSS / LIGHT_QSS)
- 主题元数据(THEME_KEY / THEME_OPTIONS)
- 应用主题入口:apply_theme(app, theme_name)
- 系统主题探测:_detect_system_theme()

行为完全等价于 v0.7~v0.13 内联在 rollingplan.py 时的版本。
日志复用 logger 名 "rollingplan",与主程序文件 log handler 共享,所以
apply_theme 的文件 log 行为不变。
"""

import os
import sys

# logging / RotatingFileHandler 复用主程序的 handler 名 "rollingplan"
# ——和 v0.13 行为等价(主程序已 _setup_logger() 注册过同名 logger)
import logging
from logging.handlers import RotatingFileHandler


THEME_KEY = "RollingPlan/theme"  # QSettings key

THEME_OPTIONS = [
    ("dark", "Dark · 深色扁平"),
    ("light", "Light · 清爽亮色"),
    ("auto", "System · 跟随系统"),
]


# ============== QSS 主题表 ==============
# 冷调极简:深色用 #1e1e1e 主背景 + #2d2d30 控件背景 + #cccccc 文字
#          浅色用 #f5f5f5 主背景 + #ffffff 控件背景 + #222222 文字
# 高亮色统一:主操作 #2196F3 (蓝) + 完成 #4CAF50 (绿) + 警告 #f44336 (红)

DARK_QSS = """
QWidget {
    background-color: #1e1e1e;
    color: #cccccc;
    font-family: "Microsoft YaHei", "Segoe UI", "Helvetica Neue", sans-serif;
    font-size: 13pt;
}
QMainWindow, QDialog {
    background-color: #1e1e1e;
}
QLabel {
    background: transparent;
    color: #cccccc;
}
QLineEdit, QListWidget, QComboBox, QSpinBox, QDateEdit, QTextEdit, QPlainTextEdit {
    background-color: #2d2d30;
    color: #e8e8e8;
    border: 1px solid #3f3f46;
    border-radius: 3px;
    padding: 4px 6px;
    selection-background-color: #1E88E5;
    selection-color: white;
}
QLineEdit:focus, QListWidget:focus, QComboBox:focus, QSpinBox:focus, QDateEdit:focus, QTextEdit:focus, QPlainTextEdit:focus {
    border: 1px solid #1E88E5;
}
QListWidget::item {
    padding: 4px 6px;
}
QListWidget::item:selected {
    background-color: #1E88E5;
    color: white;
}
QPushButton {
    background-color: #3f3f46;
    color: #e8e8e8;
    border: 1px solid #555;
    border-radius: 4px;
    padding: 6px 14px;
}
QPushButton:hover { background-color: #505057; }
QPushButton:pressed { background-color: #2d2d30; }
QPushButton:disabled { color: #6a6a6a; background-color: #2a2a2a; border-color: #3a3a3a; }
QToolButton {
    background: transparent;
    color: #cccccc;
    border: none;
    padding: 6px 10px;
    text-align: left;
}
QToolButton:hover { color: white; }
QToolButton:checked { color: #1E88E5; font-weight: bold; }
QTabWidget::pane {
    border: 1px solid #3f3f46;
    background-color: #1e1e1e;
    top: -1px;
}
QTabBar::tab {
    background-color: #2d2d30;
    color: #cccccc;
    border: 1px solid #3f3f46;
    border-bottom: none;
    border-top-left-radius: 3px;
    border-top-right-radius: 3px;
    padding: 6px 14px;
    margin-right: 1px;
}
QTabBar::tab:selected {
    color: white;
    background-color: #1E88E5;
    font-weight: bold;
    border-color: #1E88E5;
}
QTabBar::tab:hover:!selected {
    background-color: #3a3a3a;
    color: white;
}
QGroupBox {
    background-color: #252526;
    border: 1px solid #3f3f46;
    border-radius: 4px;
    margin-top: 14px;
    padding: 8px;
    font-weight: bold;
}
QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    padding: 0 6px;
    color: #1E88E5;
}
QScrollBar:vertical {
    background: #1e1e1e;
    width: 12px;
    border: none;
}
QScrollBar::handle:vertical {
    background: #555;
    border-radius: 4px;
    min-height: 20px;
}
QScrollBar::handle:vertical:hover { background: #777; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar:horizontal {
    background: #1e1e1e;
    height: 12px;
    border: none;
}
QScrollBar::handle:horizontal {
    background: #555;
    border-radius: 4px;
    min-width: 20px;
}
QScrollBar::handle:horizontal:hover { background: #777; }
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0; }
QMenu {
    background-color: #2d2d30;
    color: #cccccc;
    border: 1px solid #3f3f46;
}
QMenu::item:selected {
    background-color: #1E88E5;
    color: white;
}
QMenuBar {
    background-color: #1e1e1e;
    color: #cccccc;
}
QMenuBar::item:selected {
    background-color: #3f3f46;
}
QMessageBox, QInputDialog {
    background-color: #2d2d30;
    color: #cccccc;
}
QProgressBar {
    background-color: #2d2d30;
    border: 1px solid #3f3f46;
    border-radius: 3px;
    text-align: center;
    color: white;
}
QProgressBar::chunk {
    background-color: #1E88E5;
    border-radius: 3px;
}
QCheckBox { color: #cccccc; background: transparent; }
QRadioButton { color: #cccccc; background: transparent; }
QStatusBar { background-color: #1e1e1e; color: #888; }
"""

LIGHT_QSS = """
QWidget {
    background-color: #f5f5f5;
    color: #222222;
    font-family: "Microsoft YaHei", "Segoe UI", "Helvetica Neue", sans-serif;
    font-size: 13pt;
}
QMainWindow, QDialog {
    background-color: #f5f5f5;
}
QLabel {
    background: transparent;
    color: #222222;
}
QLineEdit, QListWidget, QComboBox, QSpinBox, QDateEdit, QTextEdit, QPlainTextEdit {
    background-color: #ffffff;
    color: #222222;
    border: 1px solid #c0c0c0;
    border-radius: 3px;
    padding: 4px 6px;
    selection-background-color: #1976D2;
    selection-color: white;
}
QLineEdit:focus, QListWidget:focus, QComboBox:focus, QSpinBox:focus, QDateEdit:focus, QTextEdit:focus, QPlainTextEdit:focus {
    border: 1px solid #1976D2;
}
QListWidget::item {
    padding: 4px 6px;
}
QListWidget::item:selected {
    background-color: #1976D2;
    color: white;
}
QPushButton {
    background-color: #e8e8e8;
    color: #222222;
    border: 1px solid #c0c0c0;
    border-radius: 4px;
    padding: 6px 14px;
}
QPushButton:hover { background-color: #d8d8d8; }
QPushButton:pressed { background-color: #c8c8c8; }
QPushButton:disabled { color: #999; background-color: #f0f0f0; border-color: #d0d0d0; }
QToolButton {
    background: transparent;
    color: #222222;
    border: none;
    padding: 6px 10px;
    text-align: left;
}
QToolButton:hover { color: #1976D2; }
QToolButton:checked { color: #1976D2; font-weight: bold; }
QTabWidget::pane {
    border: 1px solid #c0c0c0;
    background-color: #ffffff;
    top: -1px;
}
QTabBar::tab {
    background-color: #e8e8e8;
    color: #222222;
    border: 1px solid #c0c0c0;
    border-bottom: none;
    border-top-left-radius: 3px;
    border-top-right-radius: 3px;
    padding: 6px 14px;
    margin-right: 1px;
}
QTabBar::tab:selected {
    color: white;
    background-color: #1976D2;
    font-weight: bold;
    border-color: #1976D2;
}
QTabBar::tab:hover:!selected {
    background-color: #f0f0f0;
}
QGroupBox {
    background-color: #ffffff;
    border: 1px solid #c0c0c0;
    border-radius: 4px;
    margin-top: 14px;
    padding: 8px;
    font-weight: bold;
}
QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    padding: 0 6px;
    color: #1976D2;
}
QScrollBar:vertical {
    background: #f5f5f5;
    width: 12px;
    border: none;
}
QScrollBar::handle:vertical {
    background: #c0c0c0;
    border-radius: 4px;
    min-height: 20px;
}
QScrollBar::handle:vertical:hover { background: #999; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar:horizontal {
    background: #f5f5f5;
    height: 12px;
    border: none;
}
QScrollBar::handle:horizontal {
    background: #c0c0c0;
    border-radius: 4px;
    min-width: 20px;
}
QScrollBar::handle:horizontal:hover { background: #999; }
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0; }
QMenu {
    background-color: #ffffff;
    color: #222222;
    border: 1px solid #c0c0c0;
}
QMenu::item:selected {
    background-color: #1976D2;
    color: white;
}
QMenuBar {
    background-color: #f5f5f5;
    color: #222222;
}
QMenuBar::item:selected {
    background-color: #e0e0e0;
}
QMessageBox, QInputDialog {
    background-color: #ffffff;
    color: #222222;
}
QProgressBar {
    background-color: #e8e8e8;
    border: 1px solid #c0c0c0;
    border-radius: 3px;
    text-align: center;
    color: #222222;
}
QProgressBar::chunk {
    background-color: #1976D2;
    border-radius: 3px;
}
QCheckBox { color: #222222; background: transparent; }
QRadioButton { color: #222222; background: transparent; }
QStatusBar { background-color: #f5f5f5; color: #666; }
"""


def _theme_log(msg):
    """写日志(复用主程序 logger 名 + stderr),与 rollingplan._log 行为等价。
    文件 log 走 logging.getLogger("rollingplan"),由主程序 _setup_logger() 注册;
    stderr 部分用 try/except 包住,避免 --windowed 下 stderr=None 崩溃。"""
    try:
        logging.getLogger("rollingplan").debug(msg)
    except Exception:
        pass
    try:
        sys.stderr.write(f"[RollingPlan] {msg}\n")
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
                capture_output=True, text=True, timeout=2
            )
            return result.stdout.strip().lower() == "dark"
    except Exception as e:
        _theme_log(f"detect system theme failed: {e}")
    return False


def apply_theme(app, theme_name: str):
    """应用主题(自写 QSS,无外部依赖)。
    theme_name: "dark" / "light" / "auto"
    """
    _theme_log(f"apply_theme({theme_name}) called")

    if theme_name == "auto":
        is_dark = _detect_system_theme()
        actual = "dark" if is_dark else "light"
        _theme_log(f"auto -> {actual} (system dark={is_dark})")
    else:
        actual = theme_name

    qss = DARK_QSS if actual == "dark" else LIGHT_QSS
    app.setStyleSheet(qss)
    _theme_log(f"theme applied: {actual}, qss len={len(qss)}")