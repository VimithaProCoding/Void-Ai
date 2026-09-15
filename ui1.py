import sys
import math
import os
import logging
import threading
import re
import base64
import json
import html
import random
import copy
import uuid

os.environ["QT_LOGGING_RULES"] = "*.debug=false;qt.text.font.*=false;qt.qpa.fonts=false"

from PyQt6.sip import isdeleted
from PyQt6.QtCore import (
    Qt, QTimer, QPoint, QPointF, QRectF, QPropertyAnimation,
    QEasingCurve, QVariantAnimation, QThread, pyqtSignal, QObject, QSize, QRect
)
from PyQt6.QtGui import (
    QPainter, QColor, QRadialGradient, QLinearGradient, QPen, QBrush,
    QPainterPath, QFont, QIcon, QGuiApplication, QAction
)
from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QFrame, QScrollArea,
    QSizePolicy, QGraphicsOpacityEffect, QTextBrowser, QLabel,
    QGraphicsDropShadowEffect, QTextEdit, QPushButton, QMenu, QLineEdit, QMessageBox
)

from qfluentwidgets import (
    NavigationItemPosition, NavigationWidget, NavigationToolButton,
    NavigationPushButton, FluentIcon as FIF, LineEdit, ComboBox, TitleLabel, BodyLabel, CaptionLabel,
    setThemeColor, TransparentToolButton, isDarkTheme, SmoothScrollArea,
    Slider, SwitchButton
)
from qfluentwidgets import IndeterminateProgressRing, PushButton

import markdown
from pygments import highlight
from pygments.lexers import get_lexer_by_name, guess_lexer
from pygments.formatters import HtmlFormatter

from ai_sys import VoidMemoryEngine, AIEngineThread
from defaults_data import get_default_appdata, get_default_apidata
import keyring_store



def get_base_dir():
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


BASE_DIR = get_base_dir()
log_data_path = os.path.join(BASE_DIR, 'logdata.log')
APPDATA_PATH = os.path.join(BASE_DIR, 'appdata.json')
APIDATA_PATH = os.path.join(BASE_DIR, 'apidata.json')

logging.basicConfig(
    filename=log_data_path,
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)


class SaveAppDataThread(QThread):
    """Background configuration saver so settings never block the UI."""
    def __init__(self, data):
        super().__init__()
        self.data = data

    def run(self):
        try:
            with open(APPDATA_PATH, 'w', encoding='utf-8') as f:
                json.dump(self.data, f, indent=4)
        except Exception as e:
            logging.error(f"Failed to save appdata.json in thread: {e}")



class RestoreSettingsThread(QThread):
    """Restore factory settings in a worker thread so the GUI stays responsive."""

    finished_signal = pyqtSignal(bool, str)

    def run(self):
        tmp_app = APPDATA_PATH + ".restore.tmp"
        tmp_api = APIDATA_PATH + ".restore.tmp"
        try:
            default_app = get_default_appdata()
            default_api = get_default_apidata()

            # API credentials never belong in appdata.json; restore resets them in keyring.
            default_app = copy.deepcopy(default_app)
            default_app.pop("API_KEYS", None)
            default_app.pop("CHAT_API_KEY", None)
            default_app.pop("BG_API_KEY", None)
            for profile in (default_app.get("MODEL_CONFIGS", {}) or {}).values():
                if isinstance(profile, dict):
                    profile.pop("api_key", None)

            with open(tmp_app, "w", encoding="utf-8") as f:
                json.dump(default_app, f, indent=4, ensure_ascii=False)

            with open(tmp_api, "w", encoding="utf-8") as f:
                json.dump(default_api, f, indent=2, ensure_ascii=False)

            os.replace(tmp_app, APPDATA_PATH)
            os.replace(tmp_api, APIDATA_PATH)

            self.finished_signal.emit(True, "All settings restored from defaults_data.py.")
        except Exception as exc:
            for path in (tmp_app, tmp_api):
                try:
                    if os.path.exists(path):
                        os.remove(path)
                except Exception:
                    pass
            logging.exception("Failed to restore factory settings.")
            self.finished_signal.emit(False, str(exc))


def load_appdata():
    if os.path.exists(APPDATA_PATH):
        try:
            with open(APPDATA_PATH, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logging.error(f"Failed to read appdata.json: {e}")
    return {}


appdata = load_appdata()

# Migrate any plaintext credentials from older releases before the next appdata save.
_legacy_api_keys = dict(appdata.get("API_KEYS", {}) or {})
_legacy_chat_key = str(appdata.get("CHAT_API_KEY", "") or "").strip()
_legacy_bg_key = str(appdata.get("BG_API_KEY", "") or "").strip()
if _legacy_chat_key and "Groq AI" not in _legacy_api_keys:
    _legacy_api_keys["Groq AI"] = _legacy_chat_key
if _legacy_bg_key and "Groq AI" not in _legacy_api_keys:
    _legacy_api_keys["Groq AI"] = _legacy_bg_key
keyring_store.migrate_legacy_keys(_legacy_api_keys)
_legacy_keys_secured = all(
    not str(value or "").strip()
    or bool(keyring_store.get_api_key(provider))
    for provider, value in _legacy_api_keys.items()
)

THEMES = appdata.get("THEMES", {})
APP_STATE = appdata.get("APP_STATE", {})
MODEL_CONFIGS = appdata.get("MODEL_CONFIGS", {})
# Runtime-only provider credentials. Persistent storage is the OS keyring.
API_KEYS = keyring_store.load_provider_keys()

def load_apidata():
    if os.path.exists(APIDATA_PATH):
        try:
            with open(APIDATA_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as exc:
            logging.error("Failed to read apidata.json: %s", exc)
    return {"version": 1, "providers": {}, "roles": {}}

API_DATA = load_apidata()
# Backward-compatible in-process aliases. New code reads MODEL_CONFIGS instead.
CHAT_API_KEY = ""
BG_API_KEY = ""

default_legacy_model_ids = {
    "Fast Core": "openai/gpt-oss-20b",
    "Smart Logic": "qwen/qwen3.6-27b",
    "Turbo Mini": "groq/compound-mini",
}
for old_name, new_name in (
    ("Fast Core", "Fast"),
    ("Smart Logic", "Flash"),
    ("Turbo Mini", "Complex"),
):
    existing = MODEL_CONFIGS.get(new_name)
    if not isinstance(existing, dict):
        existing = {}
    if not existing.get("provider") and _legacy_chat_key:
        existing["provider"] = "Groq AI"
    if not existing.get("model"):
        existing["model"] = (
            APP_STATE.get("model_ids", {}).get(
                old_name, default_legacy_model_ids[old_name]
            )
        )
    existing.pop("api_key", None)
    MODEL_CONFIGS[new_name] = existing

# Persistent behavior flags.
APP_STATE.setdefault("auto_load_recent_chat", True)
APP_STATE.setdefault("developer_options", False)
APP_STATE.setdefault("last_chat_id", None)
APP_STATE.setdefault("font_size", 13)
APP_STATE.setdefault("bg_animation", True)
APP_STATE.setdefault("stream_text", True)

# Welcome-screen cards.  Kept inside APP_STATE so they survive the existing
# appdata save/restore flow without introducing another settings file.
DEFAULT_HOME_CARD_PROMPTS = {
    "A Friend": [
        "Talk about your day, share feelings, or just chat.",
        "Always here to listen when you feel lonely.",
        "Friendly conversations for any mood, anytime."
    ],
    "Dev Helper": [
        "Build websites, apps, and write code easily.",
        "Get clean and working code for your projects.",
        "Create software from scratch with step-by-step code."
    ],
    "Learn Zone": [
        "Learn coding, studies, and new skills easily.",
        "Simple explanations for hard topics and lessons.",
        "Ask questions and boost your knowledge every day."
    ],
}
APP_STATE.setdefault("home_card_prompts", copy.deepcopy(DEFAULT_HOME_CARD_PROMPTS))
APP_STATE.setdefault("prompt_mode_colors", {"A Friend": "#FF4D6D", "Dev Helper": "#00C853", "Learn Zone": "#9D4EDD"})

def _load_prompt_catalog():
    global _PROMPT_CATALOG
    if _PROMPT_CATALOG is not None:
        return _PROMPT_CATALOG
    try:
        with open(PROMPTS_PATH, "r", encoding="utf-8") as handle:
            data = json.load(handle)
        raw = data.get("prompts", {}) if isinstance(data, dict) else {}
        _PROMPT_CATALOG = {}
        for pid, item in raw.items():
            value = item.get("prompt", "") if isinstance(item, dict) else item
            value = str(value or "").strip()
            if value:
                _PROMPT_CATALOG[str(pid)] = value
    except Exception:
        logging.exception("Could not load prompts.json")
        _PROMPT_CATALOG = {}
    return _PROMPT_CATALOG

def _system_prompt_for_mode(mode):
    prompt_ids = {"A Friend": "a_friend", "Dev Helper": "dev_helper", "Learn Zone": "learn_zone", "None": "general"}
    prompt = _load_prompt_catalog().get(prompt_ids.get(mode, "general"), "")
    return prompt or "You are Void-AI, a helpful general assistant. Give accurate, useful, natural answers and match the user's language, including English, Sinhala, and Romanized Sinhala/Singlish."
# Prompt modes are separate from the existing model roles.
PROMPT_MODES = ("A Friend", "Dev Helper", "Learn Zone")
PROMPT_MODE_COLORS = {
    "A Friend": "#FF4D6D",
    "Dev Helper": "#00C853",
    "Learn Zone": "#9D4EDD",
}
try:
    _stored_mode_colors = APP_STATE.get("prompt_mode_colors", {})
    if isinstance(_stored_mode_colors, dict):
        PROMPT_MODE_COLORS.update({
            mode: str(color).strip()
            for mode, color in _stored_mode_colors.items()
            if mode in PROMPT_MODE_COLORS and str(color).strip()
        })
except Exception:
    logging.exception("Could not load prompt mode colors from appdata.")
PROMPT_FALLBACK_NAME = "None"
PROMPTS_PATH = os.path.join(BASE_DIR, "prompts.json")
_PROMPT_CATALOG = None


# New display names while retaining the user's existing theme assignments.
old_theme_names = APP_STATE.get("model_themes", {})
APP_STATE["model_themes"] = {
    "Fast": old_theme_names.get("Fast", old_theme_names.get("Fast Core", "Neon Purple")),
    "Flash": old_theme_names.get("Flash", old_theme_names.get("Smart Logic", "Emerald Green")),
    "Complex": old_theme_names.get("Complex", old_theme_names.get("Turbo Mini", "Velvet Rose")),
}


def save_appdata():
    # API credentials are deliberately excluded. They live only in the OS keyring.
    data = {
        "THEMES": THEMES,
        "APP_STATE": APP_STATE,
        "MODEL_CONFIGS": MODEL_CONFIGS,
    }
    save_thread = SaveAppDataThread(data)
    save_thread.finished.connect(save_thread.deleteLater)
    save_thread.start()
    if not hasattr(save_appdata, "_threads"):
        save_appdata._threads = []
    save_appdata._threads.append(save_thread)
    save_thread.finished.connect(
        lambda: save_appdata._threads.remove(save_thread)
        if save_thread in save_appdata._threads else None
    )


def get_api_key(provider):
    provider = str(provider or "").strip()
    value = keyring_store.get_api_key(provider)
    API_KEYS[provider] = value
    return value


def set_api_key(provider, value):
    provider = str(provider or "").strip()
    value = str(value or "").strip()
    ok = keyring_store.set_api_key(provider, value)
    if ok:
        if value:
            API_KEYS[provider] = value
        else:
            API_KEYS[provider] = ""
        if globals().get("void_engine") is not None:
            try:
                void_engine.update_configuration(MODEL_CONFIGS, API_DATA, API_KEYS)
            except Exception as exc:
                logging.error("Live API key update failed: %s", exc)
    return ok


def delete_api_key(provider):
    return set_api_key(provider, "")



if (("API_KEYS" in appdata) or ("CHAT_API_KEY" in appdata) or ("BG_API_KEY" in appdata)) and _legacy_keys_secured:
    save_appdata()
elif not os.path.exists(APPDATA_PATH):
    save_appdata()


void_engine = VoidMemoryEngine(MODEL_CONFIGS, API_DATA, API_KEYS)


class GlobalSignals(QObject):
    theme_updated = pyqtSignal()
    font_size_updated = pyqtSignal(int)
    bg_animation_toggled = pyqtSignal(bool)
    dark_mode_toggled = pyqtSignal(bool)
    show_toast = pyqtSignal(str, str)
    chats_updated = pyqtSignal()
    chat_title_updated = pyqtSignal(str, str)
    settings_restored = pyqtSignal(bool)


global_signals = GlobalSignals()


def apply_restored_settings_to_runtime():
    """Replace live configuration dictionaries with the factory defaults."""
    global THEMES, APP_STATE, MODEL_CONFIGS, API_KEYS, API_DATA
    default_app = get_default_appdata()
    default_api = get_default_apidata()

    THEMES.clear()
    THEMES.update(copy.deepcopy(default_app.get("THEMES", {})))

    APP_STATE.clear()
    APP_STATE.update(copy.deepcopy(default_app.get("APP_STATE", {})))
    APP_STATE.setdefault("home_card_prompts", copy.deepcopy(DEFAULT_HOME_CARD_PROMPTS))

    MODEL_CONFIGS.clear()
    MODEL_CONFIGS.update(copy.deepcopy(default_app.get("MODEL_CONFIGS", {})))

    # Restore only application/configuration data. Provider credentials stay in
    # the OS keyring and must never be deleted by Restore all settings.
    API_KEYS.clear()
    API_KEYS.update(keyring_store.load_provider_keys())

    API_DATA.clear()
    API_DATA.update(copy.deepcopy(default_api))

    if globals().get("void_engine") is not None:
        try:
            void_engine.update_configuration(MODEL_CONFIGS, API_DATA, API_KEYS)
        except Exception as exc:
            logging.error("Failed to apply restored configuration to AI engine: %s", exc)

    global_signals.settings_restored.emit(True)
    global_signals.theme_updated.emit()
    global_signals.font_size_updated.emit(int(APP_STATE.get("font_size", 13)))
    global_signals.bg_animation_toggled.emit(bool(APP_STATE.get("bg_animation", True)))



class SendGlowButton(QPushButton):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(36, 36)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.is_busy = False          # True => show stop icon
        self.is_cancelling = False   # True => dim theme only during cancellation hand-off

    def set_busy(self, busy: bool):
        # Streaming itself must keep the exact normal button styling. Only the
        # glyph changes from send-arrow to stop-square.
        self.is_busy = busy
        self.is_cancelling = False
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.update()

    def set_cancelling(self, cancelling: bool):
        # The button is dimmed ONLY after the stop button has actually been
        # pressed and while cancellation is being acknowledged.
        self.is_cancelling = cancelling
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        rect = QRectF(self.rect()).adjusted(1, 1, -1, -1)

        grad = QRadialGradient(rect.center().x(), rect.top() + rect.height() * 0.3, rect.width() * 0.75)
        
        if self.is_cancelling:
            grad.setColorAt(0.0, QColor(90, 40, 115))
            grad.setColorAt(0.55, QColor(55, 20, 75))
            grad.setColorAt(1.0, QColor(30, 8, 45))
            border_pen = QPen(QColor(130, 70, 170, 100), 1.2)
        elif self.underMouse():
            grad.setColorAt(0.0, QColor(225, 140, 255))
            grad.setColorAt(0.55, QColor(165, 75, 245))
            grad.setColorAt(1.0, QColor(105, 30, 175))
            border_pen = QPen(QColor(240, 200, 255, 220), 1.2)
        else:
            grad.setColorAt(0.0, QColor(205, 120, 255))
            grad.setColorAt(0.55, QColor(145, 55, 225))
            grad.setColorAt(1.0, QColor(85, 15, 145))
            border_pen = QPen(QColor(240, 200, 255, 160), 1.2)

        painter.setBrush(QBrush(grad))
        painter.setPen(border_pen)
        painter.drawEllipse(rect)

        cx, cy = rect.center().x(), rect.center().y()

        if self.is_busy:
            sq_size = 10.0
            painter.setBrush(QBrush(QColor(220, 180, 255, 230)))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRoundedRect(QRectF(cx - sq_size / 2.0, cy - sq_size / 2.0, sq_size, sq_size), 2.5, 2.5)
        else:
            painter.setPen(QPen(QColor(255, 255, 255), 2.2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.MiterJoin))
            arrow_path = QPainterPath()
            arrow_path.moveTo(cx - 5, cy + 1)
            arrow_path.lineTo(cx, cy - 4)
            arrow_path.lineTo(cx + 5, cy + 1)
            arrow_path.moveTo(cx, cy - 4)
            arrow_path.lineTo(cx, cy + 6)
            painter.drawPath(arrow_path)


class MicCircleButton(QPushButton):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(36, 36)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        rect = QRectF(self.rect()).adjusted(1, 1, -1, -1)

        if isDarkTheme():
            bg_color = QColor(65, 52, 82, 220) if self.underMouse() else QColor(42, 32, 55, 170)
            border_color = QColor(255, 255, 255, 60) if self.underMouse() else QColor(255, 255, 255, 30)
            icon_color = QColor(255, 255, 255) if self.underMouse() else QColor(190, 185, 205)
        else:
            bg_color = QColor(220, 208, 235, 220) if self.underMouse() else QColor(235, 225, 248, 180)
            border_color = QColor(150, 80, 220, 90)
            icon_color = QColor(60, 40, 80)

        painter.setBrush(QBrush(bg_color))
        painter.setPen(QPen(border_color, 1.0))
        painter.drawEllipse(rect)

        cx, cy = rect.center().x(), rect.center().y()
        painter.setPen(QPen(icon_color, 1.8, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        painter.setBrush(Qt.BrushStyle.NoBrush)

        painter.drawRoundedRect(QRectF(cx - 3.5, cy - 7, 7, 10), 3.5, 3.5)

        arc_path = QPainterPath()
        arc_path.arcMoveTo(QRectF(cx - 6, cy - 4, 12, 10), 0)
        arc_path.arcTo(QRectF(cx - 6, cy - 4, 12, 10), 0, -180)
        painter.drawPath(arc_path)

        painter.drawLine(QPointF(cx, cy + 6), QPointF(cx, cy + 9))


class InputContainerFrame(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("inputContainer")
        # Keep the composer lightweight: no graphics-effect stack, no animated
        # shadow, and no heavy outline. The glass look is painted directly.
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        global_signals.dark_mode_toggled.connect(lambda _: self.update())

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        radius = 18.0

        path = QPainterPath()
        path.addRoundedRect(rect, radius, radius)

        if isDarkTheme():
            # Deep-purple glass: darker body, translucent middle layer and a
            # very soft plum highlight. No visible border is drawn.
            glass_grad = QLinearGradient(rect.topLeft(), rect.bottomRight())
            glass_grad.setColorAt(0.0, QColor(42, 22, 58, 235))
            glass_grad.setColorAt(0.35, QColor(27, 14, 39, 222))
            glass_grad.setColorAt(0.72, QColor(20, 10, 30, 232))
            glass_grad.setColorAt(1.0, QColor(31, 14, 44, 238))
            painter.fillPath(path, QBrush(glass_grad))

            # Subtle glass reflection inside the top edge; intentionally not a
            # border, just a soft highlight that makes the surface feel premium.
            highlight = QPainterPath()
            inner = rect.adjusted(1.5, 1.5, -1.5, -1.5)
            highlight.addRoundedRect(inner, radius - 1.5, radius - 1.5)
            highlight_pen = QPen(QColor(224, 192, 245, 34), 1.0)
            painter.setPen(highlight_pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawPath(highlight)
        else:
            glass_grad = QLinearGradient(rect.topLeft(), rect.bottomRight())
            glass_grad.setColorAt(0.0, QColor(249, 243, 255, 235))
            glass_grad.setColorAt(0.55, QColor(242, 233, 250, 228))
            glass_grad.setColorAt(1.0, QColor(235, 224, 246, 235))
            painter.fillPath(path, QBrush(glass_grad))


class InputTextEdit(QTextEdit):
    return_pressed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptRichText(False)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setLineWrapMode(QTextEdit.LineWrapMode.WidgetWidth)
        self.setPlaceholderText("What's on your mind today?")
        
        # One-line composer by default; it expands upward as more text is typed.
        self.min_height = 48
        self.max_height = 150
        self.setFixedHeight(self.min_height)
        
        self.textChanged.connect(self.adjust_height)

    def adjust_height(self):
        doc_h = int(self.document().size().height())
        new_h = max(self.min_height, min(doc_h + 8, self.max_height))
        self.setFixedHeight(new_h)

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            if not (event.modifiers() & Qt.KeyboardModifier.ShiftModifier):
                self.return_pressed.emit()
                return
        super().keyPressEvent(event)


class GlowingImpactLabel(QLabel):
    """Static Void-Ai header label. No continuous animation to keep the UI light."""
    def __init__(self, text="Void-Ai", parent=None):
        super().__init__(text, parent)
        self.color_start = QColor("#C77DFF")
        self.color_end = QColor("#7B2CBF")
        self.setFont(QFont("Impact", 24))
        self.setStyleSheet("color: #FFFFFF; background: transparent;")


class HowCanIHelpLabel(QLabel):
    def __init__(self, text="How can I help?", parent=None):
        super().__init__(text, parent)
        self.setText(text)
        self.setFont(QFont("Impact", 33))
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setFixedHeight(56)
        self.setMinimumWidth(360)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        rect = self.rect()
        grad = QLinearGradient(rect.left(), 0, rect.right(), 0)
        
        if isDarkTheme():
            # Left: Light Grey, Center: Pure White, Right: Light Grey
            grad.setColorAt(0.0, QColor(140, 140, 155))
            grad.setColorAt(0.5, QColor(255, 255, 255))
            grad.setColorAt(1.0, QColor(140, 140, 155))
        else:
            grad.setColorAt(0.0, QColor(100, 100, 115))
            grad.setColorAt(0.5, QColor(20, 20, 30))
            grad.setColorAt(1.0, QColor(100, 100, 115))
            
        text_str = self.text()
        font_size = 30
        if len(text_str) > 28:
            font_size = 20
        elif len(text_str) > 18:
            font_size = 24

        font = QFont("Impact", font_size)
        font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 1)
        painter.setFont(font)
        painter.setPen(QPen(QBrush(grad), 0))
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, text_str)


class HomePromptCard(QFrame):
    clicked = pyqtSignal(str)
    """Lightweight display-only welcome card with safe smooth hover zoom.

    The card uses the supplied gradient themes and geometry animation, but does
    not use QGraphics effects. Keeping the animated surface inside a fixed
    parent prevents layout clipping and avoids the QPainter conflicts caused
    by stacked graphics effects.
    """

    def __init__(self, title, description, start_color, end_color, parent=None):
        super().__init__(parent)
        self.title = str(title)
        self.description = str(description)
        self.start_color = QColor(start_color)
        self.end_color = QColor(end_color)

        # Fixed outer area gives the animated card room to zoom without being
        # clipped by the parent layout. The extra vertical breathing room keeps
        # the bottom edge fully visible while the card is enlarged.
        self.setFixedSize(244, 138)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setStyleSheet("background: transparent;")
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        self.card = QFrame(self)
        self.normal_geom = QRect(6, 8, 232, 118)
        self.hover_geom = QRect(0, 4, 244, 130)
        self.card.setGeometry(self.normal_geom)
        self.card.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        # Mouse input belongs to the outer card widget so press/release
        # animation and the eventual mode-selection signal always fire even
        # when the pointer is directly over the colored card surface.
        self.card.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.card.setStyleSheet(
            f"""
            QFrame {{
                background: qlineargradient(
                    spread:pad,
                    x1:0, y1:0, x2:1, y2:1,
                    stop:0 {self.start_color.name()},
                    stop:1 {self.end_color.name()}
                );
                border: none;
                border-radius: 20px;
            }}
            """
        )

        layout = QVBoxLayout(self.card)
        layout.setContentsMargins(17, 15, 17, 14)
        layout.setSpacing(5)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)

        self.title_label = QLabel(self.title, self.card)
        self.title_label.setFont(QFont("Segoe UI Semibold", 14))
        self.title_label.setStyleSheet(
            "background: transparent; border: none; color: #FFFFFF; font-weight: 600;"
        )
        self.title_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)

        self.description_label = QLabel(self.description, self.card)
        self.description_label.setWordWrap(True)
        self.description_label.setAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop
        )
        self.description_label.setFont(QFont("Segoe UI", 9))
        self.description_label.setStyleSheet(
            "background: transparent; border: none; color: rgba(235,235,240,225);"
        )
        self.description_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)

        layout.addWidget(self.title_label)
        layout.addWidget(self.description_label, 1)

        # Smooth hover + press geometry animation. The pressed state is a very
        # small inward zoom so the card feels physically clickable without
        # changing the surrounding layout.
        self.anim = QPropertyAnimation(self.card, b"geometry", self)
        self.anim.setDuration(350)
        self.anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.pressed_geom = QRect(11, 13, 222, 112)

        # Hovering either the card surface or its child labels should count as
        # hovering the card. The labels are transparent to mouse events, so the
        # parent receives enter/leave consistently.

    def enterEvent(self, event):
        self.anim.stop()
        self.anim.setStartValue(self.card.geometry())
        self.anim.setEndValue(self.hover_geom)
        self.anim.start()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self.anim.stop()
        self.anim.setStartValue(self.card.geometry())
        self.anim.setEndValue(self.normal_geom)
        self.anim.start()
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.anim.stop()
            self.anim.setStartValue(self.card.geometry())
            self.anim.setEndValue(self.pressed_geom)
            self.anim.setDuration(85)
            self.anim.setEasingCurve(QEasingCurve.Type.OutQuad)
            self.anim.start()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.anim.stop()
            self.anim.setStartValue(self.card.geometry())
            self.anim.setEndValue(self.hover_geom if self.rect().contains(event.position().toPoint()) else self.normal_geom)
            self.anim.setDuration(130)
            self.anim.setEasingCurve(QEasingCurve.Type.OutCubic)
            self.anim.start()
            # Let the pressed state remain visible for a tiny moment before the
            # mode switch starts, so the click has a clear physical response.
            QTimer.singleShot(55, lambda: self.clicked.emit(self.title))
            event.accept()
            return
        super().mouseReleaseEvent(event)




class PromptModeBadge(QFrame):
    """Premium two-tone mode badge shown inside the composer.

    Manual modes are shown as a locked pill after the first message. Auto-detected
    modes can reuse the same runtime state without displaying this badge.
    """
    close_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.mode = "None"
        self.locked = False
        self.start_color = QColor("#9D4EDD")
        self.end_color = QColor("#C77DFF")
        self.setObjectName("promptModeBadge")
        self.setFixedHeight(30)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 2, 8, 2)
        layout.setSpacing(0)

        self.label = QLabel("None", self)
        self.label.setFont(QFont("Segoe UI Semibold", 10))
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        layout.addWidget(self.label, 1)

        self.close_btn = TransparentToolButton(FIF.CLOSE, self)
        self.close_btn.setFixedSize(22, 22)
        self.close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.close_btn.clicked.connect(self.close_requested.emit)
        self.close_btn.hide()
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        layout.addWidget(self.close_btn)
        self.setStyleSheet("QFrame#promptModeBadge { background: transparent; border: none; }")

    def _colors_for_mode(self, mode):
        card_pairs = {
            "A Friend": ("#ff007f", "#7a00ff"),
            "Dev Helper": ("#11998e", "#38ef7d"),
            "Learn Zone": ("#6728E7", "#8E2DE2"),
        }
        return tuple(QColor(c) for c in card_pairs.get(mode, ("#8B7A99", "#C9B8D6")))

    def set_mode(self, mode, locked=False):
        self.mode = mode if mode in PROMPT_MODES else "None"
        self.locked = bool(locked)
        self.start_color, self.end_color = self._colors_for_mode(self.mode)
        self.label.setText(self.mode if self.mode in PROMPT_MODES else "None")
        if self.mode in PROMPT_MODES:
            first, *rest = self.mode.split(" ", 1)
            second = rest[0] if rest else ""
            self.label.setText(
                f'<span style="color:{self.start_color.name()};">{first}</span>'
                + (f' <span style="color:{self.end_color.name()};">{second}</span>' if second else "")
            )
        else:
            self.label.setStyleSheet("color:rgba(255,255,255,0.65); font-weight:600; background:transparent;")
        self.close_btn.setVisible(False)
        self.update()

    def enterEvent(self, event):
        if self.mode in PROMPT_MODES and not self.locked:
            self.close_btn.show()
        super().enterEvent(event)

    def leaveEvent(self, event):
        if not self.locked:
            self.close_btn.hide()
        super().leaveEvent(event)

    def set_none(self, locked=False):
        self.set_mode("None", locked=locked)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(self.rect()).adjusted(0.7, 0.7, -0.7, -0.7)

        if self.mode in PROMPT_MODES:
            bg = QLinearGradient(rect.topLeft(), rect.topRight())
            bg.setColorAt(0.0, QColor(self.start_color.red(), self.start_color.green(), self.start_color.blue(), 35))
            bg.setColorAt(1.0, QColor(self.end_color.red(), self.end_color.green(), self.end_color.blue(), 20))
            painter.setBrush(QBrush(bg))

            border = QLinearGradient(rect.topLeft(), rect.topRight())
            border.setColorAt(0.0, self.start_color)
            border.setColorAt(1.0, self.end_color)
            painter.setPen(QPen(QBrush(border), 1.2))
        else:
            painter.setBrush(QBrush(QColor(255, 255, 255, 12)))
            painter.setPen(QPen(QColor(255, 255, 255, 28), 1.0))

        painter.drawRoundedRect(rect, 15, 15)
        super().paintEvent(event)

class SingularityHorizonWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        
        self.theme_color = QColor(157, 78, 221)
        self.scale_factor = 1.0
        self.target_scale = 1.0
        self.speed = 0.02
        self.target_speed = 0.02
        self.pulse_frequency = 1.2
        self.target_pulse_freq = 1.2
        self.pulse_amplitude = 0.04
        self.target_pulse_amp = 0.04
        self.glow_intensity = 140.0
        self.target_glow_intensity = 140.0
        self.ripple_intensity = 0.0
        self.target_ripple_intensity = 0.0

        self.pulse_phase = 0.0
        self.rotation_phase = 0.0
        self.ripple_phase = 0.0

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_anim)
        self.timer.start(16)
        self.setMinimumSize(60, 60)

    def set_mode(self, mode_name):
        if mode_name == "Idle":
            self.target_scale = 1.0
            self.target_speed = 0.02
            self.target_pulse_freq = 1.2
            self.target_pulse_amp = 0.04
            self.target_glow_intensity = 140.0
            self.target_ripple_intensity = 0.0

        elif mode_name == "Thinking":
            self.target_scale = 1.35
            self.target_speed = 0.05
            self.target_pulse_freq = 4.5
            self.target_pulse_amp = 0.20
            self.target_glow_intensity = 255.0
            self.target_ripple_intensity = 1.0

        elif mode_name == "Displaying Messages":
            self.target_scale = 1.15
            self.target_speed = 0.035
            self.target_pulse_freq = 2.8
            self.target_pulse_amp = 0.10
            self.target_glow_intensity = 190.0
            self.target_ripple_intensity = 0.5

    def update_anim(self):
        lerp_rate = 0.05
        self.scale_factor += (self.target_scale - self.scale_factor) * lerp_rate
        self.speed += (self.target_speed - self.speed) * lerp_rate
        self.pulse_frequency += (self.target_pulse_freq - self.pulse_frequency) * lerp_rate
        self.pulse_amplitude += (self.target_pulse_amp - self.pulse_amplitude) * lerp_rate
        self.glow_intensity += (self.target_glow_intensity - self.glow_intensity) * lerp_rate
        self.ripple_intensity += (self.target_ripple_intensity - self.ripple_intensity) * lerp_rate

        dt = 0.016
        self.pulse_phase = (self.pulse_phase + self.pulse_frequency * dt * 2.0) % (2.0 * math.pi)
        self.rotation_phase = (self.rotation_phase + self.speed) % (2.0 * math.pi)
        self.ripple_phase = (self.ripple_phase + 1.5 * dt) % 3.0

        self.update()

    def paintEvent(self, event):
        w, h = self.width(), self.height()
        if w <= 0 or h <= 0: return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        cx, cy = w / 2, h / 2
        pulse = math.sin(self.pulse_phase) * self.pulse_amplitude
        dynamic_scale = self.scale_factor + pulse
        
        base_r = max(1.0, min(w, h) * 0.22 * dynamic_scale)

        r_val = self.theme_color.red()
        g_val = self.theme_color.green()
        b_val = self.theme_color.blue()

        max_allowed_r = min(cx, cy) - 2.0

        if self.ripple_intensity > 0.001:
            ripple_count = 3
            for i in range(ripple_count):
                curr_phase = math.fmod(self.ripple_phase + i * 1.0, 3.0)
                ripple_r = base_r * (1.0 + curr_phase * 0.5)
                if ripple_r >= max_allowed_r: continue
                alpha = int(max(0, (150 - curr_phase * 50) * self.ripple_intensity))
                if alpha > 0:
                    ripple_color = QColor(r_val, g_val, b_val, alpha)
                    painter.setPen(QPen(ripple_color, 2, Qt.PenStyle.DotLine))
                    painter.setBrush(Qt.BrushStyle.NoBrush)
                    painter.drawEllipse(QPointF(cx, cy), ripple_r, ripple_r)

        num_rings = 5
        for i in range(num_rings):
            angle = self.rotation_phase * (1.0 + i * 0.2) + (i * math.pi / num_rings)
            rx = base_r * (1.30 + math.sin(angle * 0.5) * 0.12)
            ry = base_r * (0.35 + math.cos(angle * 0.5) * 0.08)
            
            painter.save()
            painter.translate(cx, cy)
            painter.rotate(35 * (i - 2) + math.sin(self.rotation_phase) * 10)
            
            ring_alpha = int(min(255, self.glow_intensity * (0.4 + i * 0.15)))
            ring_pen = QPen(QColor(r_val, g_val, b_val, ring_alpha), 2)
            painter.setPen(ring_pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawEllipse(QPointF(0, 0), rx, ry)
            
            px = math.cos(self.rotation_phase * 2 + i) * rx
            py = math.sin(self.rotation_phase * 2 + i) * ry
            painter.setBrush(QBrush(QColor(255, 255, 255, 220)))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawEllipse(QPointF(px, py), 3.0, 3.0)
            painter.restore()

        glow_r = min(max_allowed_r, base_r * 1.4)
        glow_grad = QRadialGradient(cx, cy, glow_r)
        glow_grad.setColorAt(0, QColor(r_val, g_val, b_val, int(self.glow_intensity * 0.6)))
        glow_grad.setColorAt(0.6, QColor(r_val, g_val, b_val, int(self.glow_intensity * 0.15)))
        glow_grad.setColorAt(1.0, QColor(0, 0, 0, 0))
        
        painter.setBrush(QBrush(glow_grad))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(QPointF(cx, cy), glow_r, glow_r)

        center_grad = QRadialGradient(cx - base_r * 0.1, cy - base_r * 0.1, base_r * 0.95)
        
        if isDarkTheme():
            center_grad.setColorAt(0, QColor(0, 0, 0))
            center_grad.setColorAt(0.82, QColor(5, 3, 10))
            center_grad.setColorAt(0.95, QColor(r_val, g_val, b_val, int(self.glow_intensity)))
            center_grad.setColorAt(1.0, QColor(255, 255, 255, 230))
            pen_color = QColor(255, 255, 255, 180)
        else:
            center_grad.setColorAt(0, QColor(255, 255, 255))
            center_grad.setColorAt(0.70, QColor(230, 232, 242))
            center_grad.setColorAt(0.88, QColor(190, 195, 215))
            center_grad.setColorAt(0.96, QColor(r_val, g_val, b_val, int(self.glow_intensity)))
            center_grad.setColorAt(1.0, QColor(r_val, g_val, b_val, 230))
            pen_color = QColor(r_val, g_val, b_val, 180)

        painter.setBrush(QBrush(center_grad))
        painter.setPen(QPen(pen_color, 1.8))
        painter.drawEllipse(QPointF(cx, cy), base_r * 0.85, base_r * 0.85)


class AppToast(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("appToast")
        self.setFixedHeight(60)
        self.setFixedWidth(400)
        
        layout = QHBoxLayout(self)
        layout.setContentsMargins(15, 10, 15, 10)
        layout.setSpacing(10)
        
        self.icon_lbl = QLabel("⚠️", self)
        self.icon_lbl.setStyleSheet("font-size: 20px; background: transparent;")
        
        self.msg_lbl = BodyLabel("", self)
        self.msg_lbl.setStyleSheet("color: white; font-weight: bold; background: transparent;")
        self.msg_lbl.setWordWrap(True)
        
        layout.addWidget(self.icon_lbl)
        layout.addWidget(self.msg_lbl, stretch=1)
        
        self.opacity_effect = QGraphicsOpacityEffect(self)
        self.opacity_effect.setOpacity(0.0)
        self.setGraphicsEffect(self.opacity_effect)
        self.hide()
        
        self.hide_timer = QTimer(self)
        self.hide_timer.setSingleShot(True)
        self.hide_timer.timeout.connect(self.hide_toast)

    def show_message(self, message, msg_type="error"):
        self.msg_lbl.setText(message)
        if msg_type == "success":
            self.icon_lbl.setText("")
            self.setStyleSheet("QFrame#appToast { background-color: rgba(30, 190, 100, 0.95); border: 1px solid #1EBE64; border-radius: 12px; }")
        else:
            self.icon_lbl.setText("")
            self.setStyleSheet("QFrame#appToast { background-color: rgba(220, 20, 60, 0.95); border: 1px solid #ff4d4d; border-radius: 12px; }")

        parent_rect = self.parentWidget().rect()
        x = (parent_rect.width() - self.width()) // 2
        y = 30
        self.move(x, y)
        self.show()
        self.raise_()
        
        self.anim = QPropertyAnimation(self.opacity_effect, b"opacity")
        self.anim.setDuration(300)
        self.anim.setStartValue(0.0)
        self.anim.setEndValue(1.0)
        self.anim.start()
        self.hide_timer.start(3000 if msg_type == "success" else 5000)

    def hide_toast(self):
        self.anim = QPropertyAnimation(self.opacity_effect, b"opacity")
        self.anim.setDuration(300)
        self.anim.setStartValue(1.0)
        self.anim.setEndValue(0.0)
        self.anim.finished.connect(self.hide)
        self.anim.start()


class LoadingOverlay(QFrame):
    def __init__(self, parent=None, void_page=None):
        super().__init__(parent)
        self.setObjectName("loadingOverlay")
        self.void_page = void_page
        self.time = 0.0
        
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMouseTracking(True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoMousePropagation, True)

        self.layout = QVBoxLayout(self)
        self.layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        self.void_core_mini = SingularityHorizonWidget(self)
        self.void_core_mini.setFixedSize(130, 130)
        self.void_core_mini.set_mode('Idle')
        
        self.loading_lbl = TitleLabel("Initializing VoidCore systems...", self)
        self.loading_lbl.setStyleSheet("color: white; font-size: 22px; font-weight: bold;")
        self.loading_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.sub_lbl = CaptionLabel("Loading databases & verifying models. Please wait.", self)
        self.sub_lbl.setStyleSheet("color: #aaaaaa; font-size: 14px;")
        self.sub_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        self.layout.addWidget(self.void_core_mini, alignment=Qt.AlignmentFlag.AlignCenter)
        self.layout.addSpacing(20)
        self.layout.addWidget(self.loading_lbl)
        self.layout.addWidget(self.sub_lbl)

        self.opacity_effect = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self.opacity_effect)
        self.opacity_effect.setOpacity(1.0)
        
        self.anim_timer = QTimer(self)
        self.anim_timer.timeout.connect(self.update_bg)
        self.anim_timer.start(50)

    def set_message(self, title=None, subtitle=None):
        """Update overlay copy for a long-running maintenance operation."""
        if title is not None:
            self.loading_lbl.setText(title)
        if subtitle is not None:
            self.sub_lbl.setText(subtitle)

    def showEvent(self, event):
        super().showEvent(event)
        if self.void_page and hasattr(self.void_page, 'void_core'):
            self.void_page.void_core.hide()

    def update_bg(self):
        self.time += 0.05
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = 15 + math.sin(self.time)*5
        painter.fillRect(self.rect(), QColor(10, 10, int(15+r), 230))

    def fade_out_and_close(self):
        if hasattr(self, 'anim_timer') and self.anim_timer.isActive():
            self.anim_timer.stop()
        if hasattr(self, 'void_core_mini') and hasattr(self.void_core_mini, 'timer'):
            self.void_core_mini.timer.stop()

        self.anim = QPropertyAnimation(self.opacity_effect, b"opacity")
        self.anim.setDuration(600)
        self.anim.setStartValue(1.0)
        self.anim.setEndValue(0.0)
        
        def _on_finish():
            if self.void_page and hasattr(self.void_page, 'void_core'):
                self.void_page.void_core.show()
            self.hide()
            self.deleteLater()

        self.anim.finished.connect(_on_finish)
        self.anim.start()

    def mousePressEvent(self, event):
        event.accept()


class InitEngineThread(QThread):
    finished_signal = pyqtSignal()

    def __init__(self, model_profiles=None, api_catalog=None):
        super().__init__()
        self.model_profiles = copy.deepcopy(model_profiles) if model_profiles is not None else None
        self.api_catalog = copy.deepcopy(api_catalog) if api_catalog is not None else None

    def run(self):
        global void_engine, MODEL_CONFIGS, API_DATA
        if self.model_profiles is not None:
            MODEL_CONFIGS = copy.deepcopy(self.model_profiles)
        if self.api_catalog is not None:
            API_DATA = copy.deepcopy(self.api_catalog)

        void_engine = VoidMemoryEngine(MODEL_CONFIGS, API_DATA, API_KEYS)
        void_engine.initialize_system()
        self.finished_signal.emit()


class MarkdownRenderThread(QThread):
    render_complete = pyqtSignal(str, bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.raw_text = ""
        self.current_size = 14
        self.is_dark = True
        self.pending_render = False
        self.streaming = True
        self._state_lock = threading.RLock()

    def request_render(self, text, size, is_dark, streaming=True):
        with self._state_lock:
            self.raw_text = text
            self.current_size = size
            self.is_dark = is_dark
            self.streaming = bool(streaming)
            self.pending_render = True
        
        # Thread එක දැනටමත් වැඩ නම්, අලුත් text එක ආවම ආයේ run වෙන්න signal එකක් දෙනවා
        if not self.isRunning():
            self.start()
        else:
            self.pending_render = True

    def run(self):
        while True:
            if self.isInterruptionRequested():
                return
            self.pending_render = False
            text = self.raw_text
            text = self.raw_text.replace("\r\n", "\n").replace("\r", "").replace("\t", "    ")
            streaming = self.streaming

            if streaming:
                # Lightweight streaming renderer: keep code-block layout and
                # colors, but defer expensive Pygments highlighting to final.
                bg_col = "#13131c" if self.is_dark else "#f8f9fa"
                head_bg = "#212130" if self.is_dark else "#e8e8f0"
                border_col = "#382952" if self.is_dark else "#d0c4e8"
                txt_col = "#e1e1e6" if self.is_dark else "#222222"
                lang_col = "#a090c0" if self.is_dark else "#665588"
                font_col = "#ffffff" if self.is_dark else "#111111"
                pattern = re.compile(r'```([a-zA-Z0-9+\-#]*)\n?(.*?)```', re.DOTALL)
                parts, last_end = [], 0
                for match in pattern.finditer(text):
                    normal = text[last_end:match.start()]
                    if normal:
                        parts.append(markdown.markdown(normal, extensions=['tables']))
                    lang = (match.group(1) or '').strip()
                    raw_code = match.group(2)
                    code = html.escape(raw_code)
                    b64_code = base64.b64encode(raw_code.encode('utf-8')).decode('utf-8')
                    parts.append(f'''<table width="100%" style="border:1px solid {border_col}; background-color:{bg_col}; margin:10px 0;" cellspacing="0" cellpadding="0">
<tr><td style="background-color:{head_bg}; padding:6px 12px; border-bottom:1px solid {border_col};"><span style="color:{lang_col}; font-size:11px; font-weight:bold; text-transform:uppercase;">{lang or 'CODE'}</span></td><td style="background-color:{head_bg}; padding:6px 12px; border-bottom:1px solid {border_col};" align="right"><a href="copy-code:{b64_code}">Copy</a></td></tr>
<tr><td colspan="2" style="padding:10px; color:{txt_col};"><pre>{code}</pre></td></tr></table>''')
                    last_end = match.end()
                remaining = text[last_end:]
                if remaining:
                    parts.append(markdown.markdown(remaining, extensions=['tables']))
                final_html = ''.join(parts)
                wrapped_html = f'''<style>pre {{ white-space:pre-wrap; word-wrap:break-word; margin:0; font-family:'Consolas','Courier New',monospace; }} table {{ table-layout:fixed; width:100%; }} td {{ word-wrap:break-word; overflow-wrap:break-word; }}</style><div style='font-family:"Segoe UI",sans-serif; font-size:{self.current_size}px; color:{font_col}; line-height:1.5;'>{final_html}</div>'''
                if self.isInterruptionRequested():
                    return
                self.render_complete.emit(wrapped_html, True)
                if not self.pending_render:
                    break
                continue

            if text.count("```") % 2 != 0: text += "\n```"

            pattern = re.compile(r'```([a-zA-Z0-9\+\-\#]*)\n(.*?)```', re.DOTALL)
            parts = []
            last_end = 0
            
            is_dark = self.is_dark
            bg_col = "#13131c" if is_dark else "#f8f9fa"
            head_bg = "#212130" if is_dark else "#e8e8f0"
            border_col = "#382952" if is_dark else "#d0c4e8"
            txt_col = "#e1e1e6" if is_dark else "#222222"
            lang_col = "#a090c0" if is_dark else "#665588"

            pygment_style = 'dracula' if is_dark else 'friendly'

            svg_raw = f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="{lang_col}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path></svg>'
            b64_svg = base64.b64encode(svg_raw.encode('utf-8')).decode('utf-8')

            for match in pattern.finditer(text):
                normal_text = text[last_end:match.start()]
                if normal_text:
                    parts.append(markdown.markdown(normal_text, extensions=['tables']))
                
                lang = match.group(1).strip()
                code = match.group(2)
                try:
                    lexer = get_lexer_by_name(lang) if lang else guess_lexer(code)
                except:
                    lexer = get_lexer_by_name("text")
                try:
                    formatter = HtmlFormatter(style=pygment_style, noclasses=True)
                except:
                    formatter = HtmlFormatter(style='monokai' if is_dark else 'default', noclasses=True)

                highlighted = highlight(code, lexer, formatter)
                b64_code = base64.b64encode(code.encode('utf-8')).decode('utf-8')
                
                wrapper = f'''
                <table width="100%" style="border: 1px solid {border_col}; background-color: {bg_col}; margin: 10px 0px;" cellspacing="0" cellpadding="0">
                    <tr>
                        <td style="background-color: {head_bg}; padding: 6px 12px; border-bottom: 1px solid {border_col};" align="left">
                            <span style="color: {lang_col}; font-family: 'Segoe UI', sans-serif; font-size: 11px; font-weight: bold; text-transform: uppercase;">{lang or 'CODE'}</span>
                        </td>
                        <td style="background-color: {head_bg}; padding: 6px 12px; border-bottom: 1px solid {border_col};" align="right">
                            <a href="copy-code:{b64_code}" style="text-decoration: none;" title="Copy Code">
                                <img src="data:image/svg+xml;base64,{b64_svg}" width="16" height="16">
                            </a>
                        </td>
                    </tr>
                    <tr>
                        <td colspan="2" style="padding: 10px; color: {txt_col};">
                            {highlighted}
                        </td>
                    </tr>
                </table>
                '''
                parts.append(wrapper)
                last_end = match.end()
            
            remaining = text[last_end:]
            if remaining:
                parts.append(markdown.markdown(remaining, extensions=['tables']))
                
            final_html = "".join(parts)
            font_col = "#ffffff" if is_dark else "#111111"
            wrapped_html = f"""
            <style>
                pre {{ white-space: pre-wrap; word-wrap: break-word; margin: 0; font-family: 'Consolas', 'Courier New', monospace; }}
                table {{ table-layout: fixed; width: 100%; }}
                td {{ word-wrap: break-word; overflow-wrap: break-word; }}
            </style>
            <div style='font-family: "Segoe UI", sans-serif; font-size: {self.current_size}px; color: {font_col}; line-height: 1.5;'>{final_html}</div>
            """
            
            # HTML එක හදල ඉවර උනාම Main Thread එකට යවනවා
            if self.isInterruptionRequested():
                return
            self.render_complete.emit(wrapped_html, False)
            
            # Render වෙන අතරතුරේ අලුත් chunk එකක් ආවේ නැත්තම් loop එකෙන් අයින් වෙනවා
            if not self.pending_render:
                break


class ChatTextBrowser(QTextBrowser):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.raw_text = ""
        self.current_size = APP_STATE.get('font_size', 14)
        self.max_allowed_width = 950 
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        
        self.setOpenLinks(False)
        self.setOpenExternalLinks(False)
        self.anchorClicked.connect(self.handle_link)
        
        self.setStyleSheet("background: transparent; border: none;")
        self._adjusting = False
        self.document().documentLayout().documentSizeChanged.connect(self.adjust_size)

        # Thread එක Initializing කිරීම
        self.render_thread = MarkdownRenderThread(self)
        self.render_thread.render_complete.connect(self.on_render_complete)

    def set_max_allowed_width(self, width):
        if self.max_allowed_width != width:
            self.max_allowed_width = max(160, width)
            self.adjust_size()

    def handle_link(self, url):
        url_str = url.toString()
        if "copy-code:" in url_str:
            b64_code = url_str.split("copy-code:")[-1]
            b64_code = b64_code.replace('%3D', '=')
            try:
                code = base64.b64decode(b64_code).decode('utf-8')
                QApplication.clipboard().setText(code)
                global_signals.show_toast.emit("Code Copied to Clipboard!", "success")
            except Exception as e:
                logging.error(f"Copy failed: {e}")
        else:
            import webbrowser
            webbrowser.open(url_str)

    def setMarkdownContent(self, raw_text, streaming=False):
        self.raw_text = raw_text
        self.render_html(streaming=streaming)

    def render_html(self, streaming=True):
        # Browser එක හෝ Render Thread එක Delete වී ඇත්නම් Call කිරීම නවත්වයි
        if isdeleted(self) or not hasattr(self, 'render_thread') or isdeleted(self.render_thread):
            return
        
        is_dark = isDarkTheme()
        try:
            self.render_thread.request_render(self.raw_text, self.current_size, is_dark, streaming=streaming)
        except RuntimeError:
            pass

    def get_parent_scroll_area(self):
        parent = self.parentWidget()
        while parent:
            if isinstance(parent, QScrollArea):
                return parent
            parent = parent.parentWidget()
        return None

    def on_render_complete(self, final_html, streaming=True):
        # Update කරන්න කලින් Scroll Position එක Save කරගන්නවා
        scroll_area = self.get_parent_scroll_area()
        saved_scroll = 0
        is_at_bottom = False
        
        if scroll_area:
            vbar = scroll_area.verticalScrollBar()
            saved_scroll = vbar.value()
            max_scroll = vbar.maximum()
            # User අන්තිමටම පල්ලෙහා ඉන්නවද කියලා බලනවා (Threshold ~15px)
            is_at_bottom = (max_scroll - saved_scroll <= 15)

        # Signals නවත්තලා HTML එක set කරනවා (layout එක ගැස්සෙන එක නවත්තන්න)
        self.document().blockSignals(True)
        self.setHtml(final_html)
        self.document().blockSignals(False)
        
        self.adjust_size(lightweight=streaming)

        # Update උනාට පස්සේ ආයෙත් පරණ Scroll Position එකටම හරවනවා
        if scroll_area:
            vbar = scroll_area.verticalScrollBar()
            if is_at_bottom:
                QTimer.singleShot(0, lambda bar=vbar: bar.setValue(bar.maximum()))
            elif not streaming:
                vbar.setValue(saved_scroll)

    def adjust_size(self, lightweight=False):
        if self._adjusting:
            return
        self._adjusting = True
        try:
            target_max = self.max_allowed_width
            if lightweight:
                self.document().setTextWidth(target_max)
                final_width = target_max
            else:
                self.document().setTextWidth(-1)
                doc_width = self.document().idealWidth()
                if doc_width > target_max:
                    self.document().setTextWidth(target_max)
                    final_width = target_max
                else:
                    self.document().setTextWidth(doc_width)
                    final_width = doc_width
            doc_height = self.document().size().height()
            self.setFixedSize(int(final_width) + 24, int(doc_height) + 14)
        finally:
            self._adjusting = False

    def update_style(self, size):
        if isdeleted(self) or not hasattr(self, 'render_thread') or isdeleted(self.render_thread):
            return
        self.current_size = size
        self.render_html()


class ChatBubble(QFrame):
    def __init__(self, text="", is_user=False, theme_data=None, parent=None, animate=True):
        super().__init__(parent)
        self.is_user = is_user
        self.buffer_text = ""
        self.theme_data = theme_data or THEMES.get("Neon Purple", {})
        
        self.init_ui()
        self.text_browser.setMarkdownContent(text)
        
        self.opacity_effect = QGraphicsOpacityEffect(self)
        self.opacity_effect.setOpacity(1.0 if not animate else 0.0)
        self.setGraphicsEffect(self.opacity_effect)

        self.render_timer = QTimer(self)
        # Batch streaming chunks before re-rendering markdown/HTML.
        # This reduces QTextDocument churn and keeps the UI responsive.
        self.render_timer.setInterval(120)
        self.render_timer.timeout.connect(self._flush_buffer)

        global_signals.font_size_updated.connect(lambda size: self.text_browser.update_style(size))
        global_signals.dark_mode_toggled.connect(self.update_theme_style)
        
        def on_font_size_updated(self, size):
            if not isdeleted(self) and hasattr(self, 'text_browser') and not isdeleted(self.text_browser):
                self.text_browser.update_style(size)

        if animate: self.animate_entry()

    def init_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 4, 0, 4)
        layout.setSpacing(0)
        
        self.bubble = QFrame(self)
        bubble_layout = QVBoxLayout(self.bubble)
        bubble_layout.setContentsMargins(14, 10, 14, 6)
        bubble_layout.setSpacing(4)
        
        self.text_browser = ChatTextBrowser(self.bubble)
        bubble_layout.addWidget(self.text_browser)

        bottom_layout = QHBoxLayout()
        bottom_layout.setContentsMargins(0, 0, 0, 0)
        bottom_layout.addStretch(1)
        
        self.copy_btn = TransparentToolButton(FIF.COPY, self.bubble)
        self.copy_btn.setFixedSize(26, 26)
        self.copy_btn.setToolTip("Copy Message")
        self.copy_btn.clicked.connect(self.copy_to_clipboard)
        bottom_layout.addWidget(self.copy_btn)
        bubble_layout.addLayout(bottom_layout)
        
        if self.is_user:
            self.apply_user_theme(THEMES.get("Neon Purple", {}))
            self.copy_btn.hide()
            layout.addStretch(1)
            layout.addWidget(self.bubble)
        else:
            self.update_theme_style(isDarkTheme())
            layout.addWidget(self.bubble)
            layout.addStretch(1)

    def update_available_width(self, container_width):
        max_bubble_w = min(880, max(200, int(container_width * 0.85) - 36))
        self.text_browser.set_max_allowed_width(max_bubble_w)

    def update_theme_style(self, is_dark=None):
        if is_dark is None: is_dark = isDarkTheme()
        if self.is_user:
            self.apply_user_theme(THEMES.get("Neon Purple", {}))
        else:
            if is_dark:
                self.bubble.setStyleSheet("QFrame { background-color: rgba(25, 25, 35, 230); border: none; border-radius: 16px; border-bottom-left-radius: 4px; }")
            else:
                self.bubble.setStyleSheet("QFrame { background-color: rgba(235, 235, 242, 230); border: none; border-radius: 16px; border-bottom-left-radius: 4px; }")
        self.text_browser.update_style(APP_STATE.get('font_size', 14))

    def apply_user_theme(self, theme_data=None):
        if not self.is_user: return
        start_c = "#C77DFF"
        end_c = "#7B2CBF"
        self.bubble.setStyleSheet(f"""
            QFrame {{ background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 {start_c}, stop:1 {end_c});
                     border-radius: 16px; border-bottom-right-radius: 4px; }}
        """)

    def append_text(self, new_text):
        self.buffer_text += new_text
        if not self.render_timer.isActive(): self.render_timer.start()

    def _flush_buffer(self):
        if self.buffer_text:
            self.text_browser.raw_text += self.buffer_text
            self.buffer_text = ""
            self.text_browser.render_html(streaming=True)

    def finalize(self):
        self.render_timer.stop()
        self._flush_buffer()
        self.text_browser.render_html(streaming=False)

    def copy_to_clipboard(self):
        QApplication.clipboard().setText(self.text_browser.raw_text)
        global_signals.show_toast.emit("Message Copied!", "success")

    def animate_entry(self):
        self.anim = QPropertyAnimation(self.opacity_effect, b"opacity")
        self.anim.setDuration(400)
        self.anim.setStartValue(0.0)
        self.anim.setEndValue(1.0)
        self.anim.setEasingCurve(QEasingCurve.Type.OutQuad)
        self.anim.start()

class _LegacyVoidPage(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName('voidPage')
        self.is_first_interaction = True
        self.current_ai_bubble = None
        self.current_user_bubble = None
        self.last_user_text = ""
        self.chat_bubbles = []
        self.worker = None
        self._cancel_requested = False
        self._stream_generation = 0
        self._active_turn_id = None

        self.bg_time = 0.0
        self.bg_timer = QTimer(self)
        self.bg_timer.timeout.connect(self.update_background)
        self.bg_timer.start(50)
        
        self.init_ui()
        global_signals.theme_updated.connect(self.refresh_current_theme)
        global_signals.bg_animation_toggled.connect(self.toggle_bg_animation)
        global_signals.dark_mode_toggled.connect(self.on_dark_mode_toggled)

    def toggle_bg_animation(self, state):
        if state: self.bg_timer.start(50)
        else: self.bg_timer.stop(); self.update()

    def update_background(self):
        self.bg_time += 0.05
        self.update()

    def init_ui(self):
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(20, 18, 20, 18)

        header_layout = QHBoxLayout()
        self.title_lbl = GlowingImpactLabel("Void-Ai", self)
        
        self.theme_btn = TransparentToolButton(FIF.BRUSH, self)
        #self.theme_btn.clicked.connect(self.toggle_dark_mode)

        self.help_btn = TransparentToolButton(FIF.QUESTION,self)
        self.help_btn.setToolTip("Help")
        self.help_btn.clicked.connect(self._open_help)
        
        header_layout.addWidget(self.title_lbl)
        header_layout.addStretch(1)
        header_layout.addWidget(self.help_btn)
        header_layout.addWidget(self.theme_btn)
        self.main_layout.addLayout(header_layout)

        self.top_stretch = QWidget(self)
        self.main_layout.addWidget(self.top_stretch)

        self.core_align_layout = QHBoxLayout()
        self.core_align_layout.addStretch(1)
        
        self.core_container = QWidget(self)
        self.core_container.setMinimumWidth(760)
        self.core_container.setMaximumWidth(900)
        core_layout = QVBoxLayout(self.core_container)
        core_layout.setContentsMargins(0, 0, 0, 0)
        core_layout.setSpacing(0)
        
        self.void_core = SingularityHorizonWidget(self.core_container)
        self.void_core.setFixedSize(272, 272)
        self.void_core.set_mode('Idle')
        
        # Welcome Sub Container ("Welcome to Void-Ai" & "How can I help?")
        self.welcome_container = QWidget(self.core_container)
        self.welcome_container.setMinimumWidth(760)
        welcome_layout = QVBoxLayout(self.welcome_container)
        # Keep the text block close to the core and reserve the lower space for cards.
        welcome_layout.setContentsMargins(0, 4, 0, 0)
        welcome_layout.setSpacing(8)

        self.welcome_sub_label = QLabel("Welcome to Void-Ai", self.welcome_container)
        self.welcome_sub_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.welcome_sub_label.setMinimumHeight(24)
        self.welcome_sub_label.setStyleSheet("color: rgba(205, 197, 220, 235); font-size: 15px; font-weight: 500;")

        self.ask_label = HowCanIHelpLabel("How can I help?", self.welcome_container)

        welcome_layout.addWidget(self.welcome_sub_label)
        welcome_layout.addWidget(self.ask_label)

        self.home_cards_row = QWidget(self.welcome_container)
        self.home_cards_row.setMinimumWidth(760)
        self.home_cards_row.setFixedHeight(140)
        cards_layout = QHBoxLayout(self.home_cards_row)
        cards_layout.setContentsMargins(0, 8, 0, 0)
        cards_layout.setSpacing(14)

        card_data = APP_STATE.get("home_card_prompts", DEFAULT_HOME_CARD_PROMPTS)
        # User-selected card themes: keep the exact colorful gradient pair
        # from the supplied card design.
        card_styles = {
            "A Friend": ("#ff007f", "#7a00ff"),
            "Dev Helper": ("#11998e", "#38ef7d"),
            "Learn Zone": ("#4A00E0", "#8E2DE2"),
        }

        def random_card_detail(name):
            options = card_data.get(name, DEFAULT_HOME_CARD_PROMPTS[name])
            if not isinstance(options, list) or not options:
                options = DEFAULT_HOME_CARD_PROMPTS[name]
            return random.choice([str(item) for item in options if str(item).strip()])                 if any(str(item).strip() for item in options) else DEFAULT_HOME_CARD_PROMPTS[name][0]

        self.friend_card = HomePromptCard(
            "A Friend",
            random_card_detail("A Friend"),
            *card_styles["A Friend"],
            self.home_cards_row,
        )
        self.developer_helper_card = HomePromptCard(
            "Dev Helper",
            random_card_detail("Dev Helper"),
            *card_styles["Dev Helper"],
            self.home_cards_row,
        )
        self.learn_zone_card = HomePromptCard(
            "Learn Zone",
            random_card_detail("Learn Zone"),
            *card_styles["Learn Zone"],
            self.home_cards_row,
        )

        cards_layout.addWidget(self.friend_card)
        cards_layout.addWidget(self.developer_helper_card)
        cards_layout.addWidget(self.learn_zone_card)

        self.friend_card.clicked.connect(self.select_prompt_mode)
        self.developer_helper_card.clicked.connect(self.select_prompt_mode)
        self.learn_zone_card.clicked.connect(self.select_prompt_mode)

        welcome_layout.addWidget(self.home_cards_row)

        self.welcome_opacity = QGraphicsOpacityEffect(self.welcome_container)
        self.welcome_container.setGraphicsEffect(self.welcome_opacity)
        
        core_layout.addWidget(self.void_core, alignment=Qt.AlignmentFlag.AlignCenter)
        core_layout.addWidget(self.welcome_container, alignment=Qt.AlignmentFlag.AlignCenter)
        
        self.core_align_layout.addWidget(self.core_container)
        self.core_align_layout.addStretch(1)
        self.main_layout.addLayout(self.core_align_layout)

        self.chat_scroll = QScrollArea(self)
        self.chat_scroll.setWidgetResizable(True)
        
        self.chat_container = QWidget()
        self.chat_container.setStyleSheet("background: transparent;")
        self.chat_container_layout = QHBoxLayout(self.chat_container)
        self.chat_container_layout.setContentsMargins(0, 0, 0, 0)
        
        self.chat_container_layout.addStretch(1)
        
        self.chat_vbox_widget = QWidget()
        self.chat_vbox_widget.setMaximumWidth(1050) 
        self.chat_layout = QVBoxLayout(self.chat_vbox_widget)
        self.chat_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.chat_layout.addStretch(1)
        
        self.chat_container_layout.addWidget(self.chat_vbox_widget, stretch=10)
        self.chat_container_layout.addStretch(1)
        
        self.chat_scroll.setWidget(self.chat_container)
        self.chat_scroll.hide()
        self.main_layout.addWidget(self.chat_scroll)

        self.bottom_stretch = QWidget(self)
        self.main_layout.addWidget(self.bottom_stretch)

        input_align_layout = QHBoxLayout()
        input_align_layout.addStretch(1)
        
        self.input_wrapper = QWidget(self)
        self.input_wrapper.setMaximumWidth(760)
        wrapper_layout = QHBoxLayout(self.input_wrapper)
        wrapper_layout.setContentsMargins(0, 0, 0, 0)
        
        self.input_container = InputContainerFrame(self.input_wrapper)
        container_vertical_layout = QVBoxLayout(self.input_container)
        container_vertical_layout.setContentsMargins(16, 12, 16, 10)
        container_vertical_layout.setSpacing(8)

        self.input_box = InputTextEdit(self.input_container)
        self.input_box.return_pressed.connect(self.process_message)

        bottom_action_bar = QHBoxLayout()
        bottom_action_bar.setContentsMargins(0, 0, 0, 0)
        bottom_action_bar.setSpacing(10)

        self.model_combo = ComboBox(self.input_container)
        for key in ("Fast", "Flash", "Complex"):
            self.model_combo.addItem(key)
        current_default = APP_STATE.get("selected_model_role", "Fast")
        self.model_combo.setCurrentText(
            current_default if current_default in ("Fast", "Flash", "Complex") else "Fast"
        )
        self.model_combo.setFixedWidth(135)
        self.model_combo.setFixedHeight(32)
        self.model_combo.currentTextChanged.connect(self.on_model_changed)

        self.prompt_mode_badge = PromptModeBadge(self.input_container)
        self.prompt_mode_badge.setFixedWidth(145)
        self.prompt_mode_badge.close_requested.connect(self.clear_prompt_mode)
        self.prompt_mode_badge.hide()

        self.mic_btn = MicCircleButton(self.input_container)
        self.send_btn = SendGlowButton(self.input_container)
        self.send_btn.clicked.connect(self._on_send_button_clicked)

        bottom_action_bar.addWidget(self.model_combo)
        bottom_action_bar.addWidget(self.prompt_mode_badge)
        bottom_action_bar.addStretch(1)
        bottom_action_bar.addWidget(self.mic_btn)
        bottom_action_bar.addWidget(self.send_btn)

        container_vertical_layout.addWidget(self.input_box)
        container_vertical_layout.addLayout(bottom_action_bar)
        wrapper_layout.addWidget(self.input_container)
        
        input_align_layout.addWidget(self.input_wrapper, stretch=10)
        input_align_layout.addStretch(1)
        
        self.main_layout.addLayout(input_align_layout)

        dev_layout = QHBoxLayout()
        dev_lbl = CaptionLabel("Developer VMA", self)
        dev_lbl.setStyleSheet("color: rgba(128, 128, 128, 120); font-size: 11px; font-weight: 500;")
        dev_layout.addStretch(1)
        dev_layout.addWidget(dev_lbl)
        dev_layout.addStretch(1)
        self.main_layout.addLayout(dev_layout)

        # Elevate void core slightly upwards by tweaking idle stretch ratios
        self.main_layout.setStretchFactor(self.top_stretch, 15)
        self.main_layout.setStretchFactor(self.bottom_stretch, 37)
        self.main_layout.setStretchFactor(self.chat_scroll, 0)
        
        self.apply_static_ui_styles()
        self.on_model_changed(self.model_combo.currentText())

    def _open_help(self):
        main_window = getattr(self, "main_window", None)
        if main_window is not None and hasattr(main_window, "open_help"):
            main_window.open_help()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.update_bubble_widths()

    def update_bubble_widths(self):
        container_w = self.chat_vbox_widget.width()
        if container_w <= 0:
            container_w = min(self.width(), 1050)
        for bubble in self.chat_bubbles:
            bubble.update_available_width(container_w)

    def smooth_scroll_to_target(self, target_val):
        vbar = self.chat_scroll.verticalScrollBar()
        self.scroll_anim = QPropertyAnimation(vbar, b"value")
        self.scroll_anim.setDuration(300)
        self.scroll_anim.setStartValue(vbar.value())
        self.scroll_anim.setEndValue(target_val)
        self.scroll_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.scroll_anim.start()

    def scroll_to_user_message(self, bubble):
        if not bubble: return
        QApplication.processEvents()
        
        # User message එකේ පිහිටීම අනුව Viewport එකේ උඩටම Scroll කිරීම
        pos_y = bubble.mapTo(self.chat_container, QPoint(0, 0)).y()
        self.smooth_scroll_to_target(max(0, pos_y - 10))

    def scroll_slightly_down(self):
        vbar = self.chat_scroll.verticalScrollBar()
        current = vbar.value()
        target = min(vbar.maximum(), current + 120)
        self.smooth_scroll_to_target(target)

    def scroll_to_bottom(self):
        QApplication.processEvents()
        vbar = self.chat_scroll.verticalScrollBar()
        vbar.setValue(vbar.maximum())

    def apply_static_ui_styles(self):
        r, g, b = 157, 78, 221
        
        global_scroll_css = """
            QScrollBar:vertical {
                border: none;
                background: transparent;
                width: 8px;
                margin: 0px;
            }
            QScrollBar::handle:vertical {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #C77DFF, stop:1 #7B2CBF);
                min-height: 35px;
                border-radius: 4px;
            }
            QScrollBar::handle:vertical:hover {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #E0A2FF, stop:1 #9D4EDD);
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0px; background: none; }
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: none; }

            QScrollBar:horizontal {
                border: none;
                background: transparent;
                height: 8px;
                margin: 0px;
            }
            QScrollBar::handle:horizontal {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #C77DFF, stop:1 #7B2CBF);
                min-width: 35px;
                border-radius: 4px;
            }
            QScrollBar::handle:horizontal:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #E0A2FF, stop:1 #9D4EDD);
            }
            QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0px; background: none; }
            QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal { background: none; }
        """
        
        self.setStyleSheet(global_scroll_css)
        self.chat_scroll.setStyleSheet(f"QScrollArea {{ border: none; background: transparent; }} {global_scroll_css}")

        if isDarkTheme():
            self.input_box.setStyleSheet(f"""
                QTextEdit {{
                    border: none;
                    background: transparent;
                    color: #FAFAFA;
                    font-size: 14px;
                    font-family: 'Segoe UI', sans-serif;
                    selection-background-color: rgba({r}, {g}, {b}, 0.55);
                    selection-color: #FFFFFF;
                }}
            """)
            self.welcome_sub_label.setStyleSheet("color: rgba(205, 197, 220, 235); font-size: 15px; font-weight: 500; font-family: 'Segoe UI', sans-serif;")
        else:
            self.input_box.setStyleSheet(f"""
                QTextEdit {{
                    border: none;
                    background: transparent;
                    color: #1A0926;
                    font-size: 14px;
                    font-family: 'Segoe UI', sans-serif;
                    selection-background-color: rgba({r}, {g}, {b}, 0.35);
                    selection-color: #000000;
                }}
            """)
            self.welcome_sub_label.setStyleSheet("color: rgba(205, 197, 220, 235); font-size: 15px; font-weight: 500; font-family: 'Segoe UI', sans-serif;")

        setThemeColor(QColor(157, 78, 221))

    def on_model_changed(self, selected_model_name):
        if selected_model_name not in ("Fast", "Flash", "Complex"):
            selected_model_name = "Fast"
        APP_STATE["selected_model_role"] = selected_model_name
        save_appdata()
        theme_name = APP_STATE.get("model_themes", {}).get(selected_model_name, "Neon Purple")
        theme_data = THEMES.get(theme_name, THEMES.get("Neon Purple", {}))
        
        col_start = theme_data.get("grad_start", "#C77DFF")
        col_main = theme_data.get("hex", "#9D4EDD")
        col_end = theme_data.get("grad_end", "#7B2CBF")

        is_dark = isDarkTheme()
        bg_glass = "rgba(35, 18, 50, 0.65)" if is_dark else "rgba(255, 255, 255, 0.80)"
        hover_glass = "rgba(50, 25, 75, 0.85)" if is_dark else "rgba(255, 255, 255, 0.95)"

        self.model_combo.setStyleSheet(f"""
            QComboBox, ComboBox {{
                border: none;
                border-radius: 13px;
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:1,
                    stop:0 {bg_glass},
                    stop:0.55 rgba(47, 24, 64, 0.58),
                    stop:1 {hover_glass}
                );
                color: {col_start};
                font-weight: 600;
                font-size: 12px;
                padding: 0px 10px;
                min-height: 30px;
            }}
            QComboBox:hover, ComboBox:hover {{
                border: none;
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:1,
                    stop:0 rgba(74, 38, 96, 0.72),
                    stop:1 rgba(37, 18, 52, 0.82)
                );
            }}
            QComboBox::drop-down, ComboBox::drop-down {{
                border: none;
                width: 1px;
                background: transparent;
            }}
            QComboBox::down-arrow, ComboBox::down-arrow {{
                image: none;
                width: 0px;
                height: 0px;
                margin: 0px;
            }}
            QComboBox QAbstractItemView {{
                border: 1px solid {col_main};
                border-radius: 6px;
                background-color: {'#181222' if is_dark else '#F5EEF8'};
                color: {'#FFFFFF' if is_dark else '#111111'};
                selection-background-color: {col_main};
                selection-color: white;
                padding: 4px;
            }}
        """)

    def on_dark_mode_toggled(self):
        self.apply_static_ui_styles()
        self.on_model_changed(self.model_combo.currentText())
        self.mic_btn.update()
        self.send_btn.update()
        self.ask_label.update()
        self.update()

    def revert_to_idle(self, animate=True):
        self.is_first_interaction = True
        
        if animate:
            self.layout_anim = QVariantAnimation(self)
            self.layout_anim.setDuration(750)
            self.layout_anim.setEasingCurve(QEasingCurve.Type.InOutCubic)
            self.layout_anim.setStartValue(1.0)
            self.layout_anim.setEndValue(0.0)
            self.layout_anim.valueChanged.connect(self.update_layout_shift)
            self.layout_anim.start()
        else:
            self.update_layout_shift(0.0)

    def trigger_awakening(self, animate=True):
        self.is_first_interaction = False
        setThemeColor(QColor(157, 78, 221))
        self.on_model_changed(self.model_combo.currentText())
        
        if animate:
            self.layout_anim = QVariantAnimation(self)
            self.layout_anim.setDuration(750)
            self.layout_anim.setEasingCurve(QEasingCurve.Type.InOutCubic)
            self.layout_anim.setStartValue(0.0)
            self.layout_anim.setEndValue(1.0)
            self.layout_anim.valueChanged.connect(self.update_layout_shift)
            self.layout_anim.start()
        else:
            self.update_layout_shift(1.0)

    def update_layout_shift(self, val):
        target_size = int(272 - (172 * val))
        self.void_core.setFixedSize(target_size, target_size)
        
        self.welcome_opacity.setOpacity(max(0.0, 1.0 - (val * 1.5)))
        
        if val < 0.99:
            self.welcome_container.show()
            self.top_stretch.show()
            self.bottom_stretch.show()

        if val > 0.02 and not self.chat_scroll.isVisible():
            self.chat_scroll.show()
        elif val <= 0.02 and self.chat_scroll.isVisible():
            self.chat_scroll.hide()

        top_s = int(50 * (1.0 - val))
        bot_s = int(88 * (1.0 - val))
        chat_s = int(200 * val)

        self.main_layout.setStretchFactor(self.top_stretch, top_s)
        self.main_layout.setStretchFactor(self.bottom_stretch, bot_s)
        self.main_layout.setStretchFactor(self.chat_scroll, chat_s)

        if val >= 0.99:
            self.welcome_container.hide()
            self.top_stretch.hide()
            self.bottom_stretch.hide()
            self.main_layout.setStretchFactor(self.chat_scroll, 1)

    def load_chat_history(self):
        history = void_engine.get_chat_history()
        if history:
            self.trigger_awakening(animate=False)
            for msg in history:
                is_u = (msg["role"] == "user")
                self.add_chat_bubble(msg["content"], is_user=is_u, animate=False)
            
            QTimer.singleShot(100, self.scroll_to_bottom)
            QTimer.singleShot(300, self.scroll_to_bottom)
            QTimer.singleShot(600, self.scroll_to_bottom)

    def refresh_current_theme(self):
        self.on_model_changed(self.model_combo.currentText())

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        outer_bg = QColor(32, 32, 32) if isDarkTheme() else QColor(243, 243, 243)
        painter.fillRect(self.rect(), outer_bg)

        # Outer Floating Rounded Frame Margin and Corner Radius
        margin = 8
        card_rect = QRectF(self.rect()).adjusted(margin, margin, -margin, -margin)
        corner_radius = 16.0
        
        path = QPainterPath()
        path.addRoundedRect(card_rect, corner_radius, corner_radius)

        grad = QRadialGradient(card_rect.center().x(), card_rect.center().y(), card_rect.width())
        
        pulse = math.sin(self.bg_time) * 12 if APP_STATE.get("bg_animation", True) else 0
        r, g, b = 157, 78, 221

        if isDarkTheme():
            grad.setColorAt(0, QColor(max(0, min(255, int(r * 0.22) + int(pulse))), max(0, min(255, int(g * 0.22))), max(0, min(255, int(b * 0.22) + int(pulse))), 255))
            grad.setColorAt(1, QColor(10, 8, 16, 255))
            border_pen = QPen(QColor(255, 255, 255, 25), 1.2)
        else:
            grad.setColorAt(0, QColor(max(195, min(235, 210 + int(r * 0.12) + int(pulse * 0.4))), max(195, min(235, 210 + int(g * 0.12))), max(200, min(240, 215 + int(b * 0.12))), 255))
            grad.setColorAt(1, QColor(215, 215, 222, 255))
            border_pen = QPen(QColor(0, 0, 0, 30), 1.2)
            
        painter.fillPath(path, QBrush(grad))
        painter.setPen(border_pen)
        painter.drawRoundedRect(card_rect, corner_radius, corner_radius)

    def _on_send_button_clicked(self):
        """Send a new prompt, or cancel the active stream."""
        if self.worker is not None and self.worker.isRunning():
            if not self._cancel_requested:
                self._request_cancel()
            return
        self.process_message()

    def _set_streaming_ui(self, streaming: bool):
        """Keep the input usable while streaming and swap send -> cancel."""
        self.input_box.setEnabled(not streaming)
        self.model_combo.setEnabled(not streaming)
        self.send_btn.set_busy(streaming)
        # The stop/cancel button must remain clickable while a reply is being
        # generated. It is only disabled after the user actually requests a
        # cancellation, until the worker confirms it is finished.
        self.send_btn.setEnabled(True)
        self.input_box.setPlaceholderText(
            "Void-Ai is thinking..." if streaming else "Type your message to Void-Ai..."
        )

    def _request_cancel(self):
        """Ask the backend stream to abort; UI cleanup happens on worker finish."""
        worker = self.worker
        if worker is None or not worker.isRunning():
            return

        self._cancel_requested = True
        self.send_btn.setEnabled(False)
        # Only the cancellation hand-off is visually dimmed.
        self.send_btn.set_cancelling(True)
        self.send_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.void_core.set_mode('Thinking')
        worker.request_cancel()

    def _remove_bubble(self, bubble):
        if bubble is None:
            return
        try:
            self.chat_layout.removeWidget(bubble)
        except RuntimeError:
            pass
        if bubble in self.chat_bubbles:
            self.chat_bubbles.remove(bubble)

        # Do not destroy a ChatBubble while its markdown worker thread is still
        # running; request interruption and give it a brief chance to exit.
        try:
            render_thread = bubble.text_browser.render_thread
            if render_thread.isRunning():
                render_thread.requestInterruption()
                render_thread.wait(120)
        except (AttributeError, RuntimeError):
            pass

        bubble.deleteLater()

    def _remove_dynamic_spacer(self):
        spacer = getattr(self, 'bottom_spacer', None)
        if spacer is not None:
            try:
                self.chat_layout.removeWidget(spacer)
            except RuntimeError:
                pass
            spacer.setFixedHeight(0)

    def _restore_initial_layout_if_empty(self):
        """Return to the original welcome screen only when no chat remains."""
        if self.chat_bubbles:
            return

        self.revert_to_idle(animate=True)
        self.chat_scroll.hide()
        self.top_stretch.show()
        self.bottom_stretch.show()
        self.main_layout.setStretchFactor(self.top_stretch, 15)
        self.main_layout.setStretchFactor(self.bottom_stretch, 37)
        self.main_layout.setStretchFactor(self.chat_scroll, 0)

    def _rollback_current_message(self, restore_text=True, animate=True):
        """Remove only the active user/reply pair and restore the prompt.

        The backend is also asked to delete any already-committed memory/Chroma
        record for this exact turn, so a late cancellation cannot leave the
        cancelled prompt behind in persistent state.
        """
        turn_id = self._active_turn_id
        if turn_id:
            try:
                void_engine.rollback_turn(turn_id)
            except Exception as e:
                logging.error(f"Failed to rollback cancelled turn {turn_id}: {e}")

        self._remove_dynamic_spacer()

        current_user = self.current_user_bubble
        current_ai = self.current_ai_bubble

        self._remove_bubble(current_ai)
        self._remove_bubble(current_user)

        self.current_ai_bubble = None
        self.current_user_bubble = None

        if restore_text and self.last_user_text:
            self.input_box.blockSignals(True)
            self.input_box.setPlainText(self.last_user_text)
            self.input_box.blockSignals(False)
            self.input_box.setFixedHeight(self.input_box.min_height)

        self._restore_initial_layout_if_empty()



    def select_prompt_mode(self, mode):
        if getattr(self, "locked_prompt_mode", False) or getattr(self, "current_chat_id", None) is not None:
            return
        mode = str(mode or "").strip()
        if mode not in PROMPT_MODES:
            return
        self.selected_prompt_mode = mode
        self.prompt_mode_badge.set_mode(mode, locked=False)
        self.prompt_mode_badge.show()
        self.input_box.setFocus()

    def clear_prompt_mode(self):
        if getattr(self, "locked_prompt_mode", False) or getattr(self, "current_chat_id", None) is not None:
            return
        self.selected_prompt_mode = "None"
        self.prompt_mode_badge.set_none(locked=False)
        self.prompt_mode_badge.hide()
        self.input_box.setFocus()

    def _lock_prompt_mode(self, mode, show_badge=True):
        self.selected_prompt_mode = mode if mode in PROMPT_MODES else "None"
        self.locked_prompt_mode = True
        self.prompt_mode_badge.set_mode(self.selected_prompt_mode, locked=True)
        self.prompt_mode_badge.setVisible(bool(show_badge and self.selected_prompt_mode in PROMPT_MODES))

    def process_message(self):
        # Never start a second request while one is active.
        if self.worker is not None and self.worker.isRunning():
            return

        text = self.input_box.toPlainText().strip()
        if not text:
            return

        self.last_user_text = text
        self._cancel_requested = False
        self._stream_generation += 1
        generation = self._stream_generation
        turn_id = uuid.uuid4().hex

        self.input_box.clear()
        self.input_box.setFixedHeight(self.input_box.min_height)

        first_interaction = self.is_first_interaction
        if first_interaction:
            self.trigger_awakening(animate=True)

        self._set_streaming_ui(True)
        self.void_core.set_mode('Thinking')

        # Keep the tail spacer beneath the active turn so the user bubble can
        # sit at the top of the viewport with comfortable visual breathing room.
        if not hasattr(self, 'bottom_spacer') or self.bottom_spacer is None:
            self.bottom_spacer = QWidget()
        self._remove_dynamic_spacer()

        self.current_user_bubble = self.add_chat_bubble(text, is_user=True)
        self.current_ai_bubble = None

        scroll_widget = getattr(self, 'chat_scroll', None)
        viewport_height = scroll_widget.viewport().height() if scroll_widget else 600
        self.bottom_spacer.setFixedHeight(viewport_height + 72)
        self.chat_layout.addWidget(self.bottom_spacer)

        QTimer.singleShot(20, lambda b=self.current_user_bubble: self.scroll_to_user_message(b))

        selected_model = self.model_combo.currentText()
        model_config = copy.deepcopy(MODEL_CONFIGS.get(selected_model, {}))

        self.worker = AIEngineThread(
            void_engine,
            text,
            model_config,
            self.current_chat_id,
            stream=APP_STATE.get("stream_text", True),
            turn_id=turn_id,
        )
        self.worker._generation = generation
        self.worker.turn_id = turn_id
        self._active_turn_id = turn_id
        self.worker.chunk_received.connect(self.on_chunk_received)
        self.worker.error_signal.connect(self.on_error)
        self.worker.finished_signal.connect(self.on_stream_finished)
        self.worker.start()

    def on_chunk_received(self, chunk_text):
        if self._cancel_requested or not chunk_text:
            return

        if self.current_ai_bubble is None:
            self._remove_dynamic_spacer()
            self.current_ai_bubble = self.add_chat_bubble("", is_user=False)

            if hasattr(self, 'bottom_spacer') and self.bottom_spacer:
                self.chat_layout.addWidget(self.bottom_spacer)

            self.void_core.set_mode('Displaying Messages')

        self.current_ai_bubble.append_text(chunk_text)

    def on_error(self, error_msg):
        logging.error(f"AI Streaming Failed: {error_msg}")
        global_signals.show_toast.emit("AI Connection Failed: Check Logs!", "error")

        # Errors behave like a safe rollback: discard only the active turn and
        # put the user's prompt back in the composer.
        self._rollback_current_message(restore_text=True)
        self._cancel_requested = False
        self.send_btn.set_cancelling(False)
        self._set_streaming_ui(False)
        self.input_box.setFocus()
        self.void_core.set_mode('Idle' if self.chat_bubbles else 'Idle')
        self.worker = None
        self._active_turn_id = None

    def on_stream_finished(self):
        worker = self.sender()
        cancelled = self._cancel_requested or (worker is not None and getattr(worker, 'was_cancelled', False))

        if cancelled:
            # A cancelled request must never be committed to memory. Remove the
            # partial UI turn and return the prompt to the textbox.
            self._rollback_current_message(restore_text=True)
        else:
            if self.current_ai_bubble:
                self.current_ai_bubble.finalize()
            self._remove_dynamic_spacer()

        # Normalise state after either success or cancellation.
        self._cancel_requested = False
        self._set_streaming_ui(False)
        self.input_box.setFocus()
        self.void_core.set_mode('Idle')

        if worker is self.worker:
            self.worker = None
        self._active_turn_id = None

    def add_chat_bubble(self, text, is_user, animate=True):
        bubble = ChatBubble(text, is_user, theme_data=THEMES.get("Neon Purple", {}), parent=self.chat_vbox_widget, animate=animate)
        container_w = self.chat_vbox_widget.width()
        if container_w <= 0: container_w = self.width()
        bubble.update_available_width(container_w)
        
        self.chat_bubbles.append(bubble)
        count = self.chat_layout.count()
        self.chat_layout.insertWidget(count - 1, bubble)
        return bubble


class NewChatNavigationWidget(NavigationPushButton):
    """The + button directly beneath Fluent's menu button."""
    def __init__(self, parent=None):
        super().__init__(FIF.LABEL, "New Chat", False, parent)
        self.setToolTip("New Chat")

