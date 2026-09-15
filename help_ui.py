import os
import sys
import json
import webbrowser
from PyQt6.QtCore import Qt, QUrl, pyqtSignal, QTimer
from PyQt6.QtGui import (
    QColor,
    QDesktopServices,
    QFont,
    QIcon,
    QPainter,
    QLinearGradient,
    QPainterPath,
    QPen,
    QBrush,
)
from PyQt6.QtWidgets import (
    QApplication,
    QDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
    QGraphicsDropShadowEffect,
)

try:
    from qfluentwidgets import FluentIcon as FIF, SmoothScrollArea
except ImportError:
    FIF = None


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
APPDATA_PATH = os.path.join(BASE_DIR, "appdata.json")
DEFAULT_GROQ_URL = "https://console.groq.com/keys"


def _load_appdata():
    try:
        with open(APPDATA_PATH, "r", encoding="utf-8") as handle:
            data = json.load(handle)
            return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def get_groq_keys_url():
    data = _load_appdata()
    app_state = data.get("APP_STATE", {}) if isinstance(data, dict) else {}
    return (
        app_state.get("groq_api_keys_url")
        or data.get("groq_api_keys_url")
        or DEFAULT_GROQ_URL
    )


class GradientTitleLabel(QLabel):
    """Large Impact title with a soft light-grey -> white -> light-grey shade (No Glow)."""

    def __init__(self, text="", parent=None):
        super().__init__(text, parent)
        self.setObjectName("appTitle")
        self.setFont(QFont("Impact", 38))
        self.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self.setMinimumHeight(50)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)

        fm = self.fontMetrics()
        text_width = fm.horizontalAdvance(self.text())
        rect = self.rect()

        # 3 color shade gradient matching about_ui.py
        gradient = QLinearGradient(0, 0, text_width, 0)
        gradient.setColorAt(0.00, QColor("#A0A0B0"))  # Grey
        gradient.setColorAt(0.50, QColor("#FFFFFF"))  # White
        gradient.setColorAt(1.00, QColor("#A0A0B0"))  # Grey

        path = QPainterPath()
        y = rect.center().y() + fm.ascent() / 2.0 - fm.descent() / 2.0
        path.addText(0.0, float(y), self.font(), self.text())

        painter.fillPath(path, gradient)


class TimelineGraphic(QWidget):
    """Compact vertical timeline track that stays connected between every step."""

    def __init__(self, step_num, is_last, parent=None):
        super().__init__(parent)
        self.step_num = int(step_num)
        self.is_last = bool(is_last)
        self.setFixedWidth(42)
        self.setSizePolicy(
            QSizePolicy.Policy.Fixed,
            QSizePolicy.Policy.Expanding,
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        cx = self.width() // 2
        radius = 13
        cy = 22

        painter.setPen(QPen(QColor("#5A3774"), 2.0))
        if cy - radius > 0:
            painter.drawLine(cx, 0, cx, cy - radius)
        if not self.is_last:
            painter.drawLine(cx, cy + radius, cx, self.height())

        painter.setBrush(QBrush(QColor("#7B2CBF")))
        painter.setPen(QPen(QColor("#B77BDE"), 1.0))
        painter.drawEllipse(
            cx - radius,
            cy - radius,
            radius * 2,
            radius * 2,
        )

        painter.setPen(QPen(QColor("#FFFFFF")))
        painter.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        painter.drawText(
            cx - radius,
            cy - radius,
            radius * 2,
            radius * 2,
            Qt.AlignmentFlag.AlignCenter,
            str(self.step_num),
        )


class StepWidget(QWidget):
    """A clean timeline step with optional action button."""

    def __init__(
        self,
        step_num,
        is_last,
        title,
        desc,
        button_data=None,
        parent=None,
    ):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, False)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(14)

        self.timeline_graphic = TimelineGraphic(step_num, is_last, self)
        right_layout = QVBoxLayout()
        right_layout.setContentsMargins(0, 3, 4, 22)
        right_layout.setSpacing(7)

        title_lbl = QLabel(title, self)
        title_lbl.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        title_lbl.setFont(QFont("Segoe UI", 12, QFont.Weight.DemiBold))
        title_lbl.setStyleSheet(
            "color: #F5F2FA; background: transparent;"
        )

        desc_lbl = QLabel(desc, self)
        desc_lbl.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        desc_lbl.setWordWrap(True)
        desc_lbl.setFont(QFont("Segoe UI", 10))
        desc_lbl.setStyleSheet(
            "color: #AAA4B4; background: transparent; line-height: 1.2;"
        )

        right_layout.addWidget(title_lbl)
        right_layout.addWidget(desc_lbl)

        if button_data:
            button_row = QHBoxLayout()
            button_row.setContentsMargins(0, 5, 0, 0)
            button_row.setSpacing(8)

            button_items = button_data if isinstance(button_data, (list, tuple)) else [button_data]
            for item in button_items:
                btn = QPushButton(item["text"], self)
                btn.setCursor(Qt.CursorShape.PointingHandCursor)
                btn.setMinimumHeight(34)
                btn.setMinimumWidth(150)
                btn.setStyleSheet(
                    """
                    QPushButton {
                        background: #7B2CBF;
                        color: #FFFFFF;
                        border: 1px solid #9252C8;
                        border-radius: 8px;
                        padding: 6px 14px;
                        font-family: "Segoe UI";
                        font-size: 12px;
                        font-weight: 600;
                    }
                    QPushButton:hover {
                        background: #8D3ED0;
                        border-color: #B06BE8;
                    }
                    QPushButton:pressed {
                        background: #67239F;
                    }
                    """
                )
                btn.clicked.connect(item["callback"])
                button_row.addWidget(btn, 0, Qt.AlignmentFlag.AlignLeft)
            button_row.addStretch(1)
            right_layout.addLayout(button_row)

        layout.addWidget(self.timeline_graphic, 0)
        layout.addLayout(right_layout, 1)


class CardIcon(QWidget):
    """Render a FluentIcon (FIF) without borders, responsive to resize."""

    def __init__(self, kind, parent=None):
        super().__init__(parent)
        self.kind = kind
        self.icon_size = 28
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)

        self._label = QLabel(self)
        self._label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)

        icon_aliases = {
            "key": ("KEY", "VPN", "PASSWORD"),
            "settings": ("SETTING", "SETTING_NORMAL", "SETTINGS"),
            "info": ("INFO", "INFO_FILL", "HELP"),
            "chat": ("CHAT", "CHAT_SOLID", "COMMENTS"),
            "developer": ("CODE", "DEVELOPER_TOOLS", "COMMAND_PROMPT"),
            "about": ("INFO", "INFO_FILL", "HELP"),
        }
        self._fif_name = next(
            (name for name in icon_aliases.get(kind, ()) if FIF is not None and hasattr(FIF, name)),
            None,
        )
        self._apply_icon()

    def set_icon_size(self, size):
        if self.icon_size != size:
            self.icon_size = size
            self.setFixedSize(size + 16, size + 16)
            self._label.setFixedSize(size + 16, size + 16)
            self._apply_icon()

    def _apply_icon(self):
        self._label.clear()
        if FIF is None or self._fif_name is None:
            self._label.setText("•")
            self._label.setFont(QFont("Segoe UI", int(self.icon_size * 0.8), QFont.Weight.Bold))
            self._label.setStyleSheet("color: #FFFFFF; background: transparent;")
            return

        try:
            fluent_icon = getattr(FIF, self._fif_name)
            try:
                icon = fluent_icon.icon(color="#FFFFFF")
            except TypeError:
                icon = fluent_icon.icon()

            if isinstance(icon, QIcon):
                pixmap = icon.pixmap(self.icon_size, self.icon_size)
                self._label.setPixmap(pixmap)
                self._label.setStyleSheet("background: transparent;")
                return
        except Exception:
            pass

        self._label.setText("•")
        self._label.setFont(QFont("Segoe UI", int(self.icon_size * 0.8), QFont.Weight.Bold))
        self._label.setStyleSheet("color: #FFFFFF; background: transparent;")


class ModernCard(QFrame):
    """Dark Glass Card with shaded purple border and responsive icons."""

    clicked = pyqtSignal()

    def __init__(self, icon_kind, title, description, clickable=True, parent=None):
        super().__init__(parent)
        self.setObjectName("ModernCard")
        
        # Limit expansion strictly to keep the UI clean
        self.setMinimumHeight(155)
        self.setMaximumHeight(155)
        self.setMaximumWidth(750)
        
        self.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Preferred,
        )
        self.setCursor(
            Qt.CursorShape.PointingHandCursor
            if clickable
            else Qt.CursorShape.ArrowCursor
        )
        self._hovered = False

        layout = QHBoxLayout(self)
        layout.setContentsMargins(18, 14, 18, 14)
        layout.setSpacing(14)

        # Border-less Icon Widget
        self.icon = CardIcon(icon_kind, self)
        layout.addWidget(self.icon, 0, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)

        # Centered Text Area
        text_col = QVBoxLayout()
        text_col.setContentsMargins(0, 0, 0, 0)
        text_col.setSpacing(4)
        text_col.setAlignment(Qt.AlignmentFlag.AlignVCenter)

        self.title_label = QLabel(title, self)
        self.title_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.title_label.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
        self.title_label.setStyleSheet("color: #FFFFFF; background: transparent;")

        self.description_label = QLabel(description, self)
        self.description_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.description_label.setWordWrap(True)
        self.description_label.setFont(QFont("Segoe UI", 9))
        self.description_label.setStyleSheet("color: #A99EBA; background: transparent;")

        text_col.addWidget(self.title_label)
        text_col.addWidget(self.description_label)
        layout.addLayout(text_col, 1)

        self.chevron = QLabel("›", self)
        self.chevron.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.chevron.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.chevron.setFont(QFont("Segoe UI", 22, QFont.Weight.Normal))
        self.chevron.setFixedWidth(18)
        self.chevron.setStyleSheet("color: #8E7DA3; background: transparent;")
        layout.addWidget(self.chevron, 0, Qt.AlignmentFlag.AlignVCenter)

        self._glow = QGraphicsDropShadowEffect(self)
        self._glow.setOffset(0, 4)
        self._glow.setBlurRadius(16)
        self._glow.setColor(QColor(0, 0, 0, 80))
        self.setGraphicsEffect(self._glow)

    def update_responsive_icon(self, width):
        if width > 1400:
            self.icon.set_icon_size(34)
        elif width > 1100:
            self.icon.set_icon_size(30)
        else:
            self.icon.set_icon_size(26)

    def enterEvent(self, event):
        self._hovered = True
        self._glow.setBlurRadius(22)
        self._glow.setColor(QColor(138, 75, 205, 70))
        self.chevron.setStyleSheet("color: #FFFFFF; background: transparent;")
        self.description_label.setStyleSheet("color: #D3C9E3; background: transparent;")
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._hovered = False
        self._glow.setBlurRadius(16)
        self._glow.setColor(QColor(0, 0, 0, 80))
        self.chevron.setStyleSheet("color: #8E7DA3; background: transparent;")
        self.description_label.setStyleSheet("color: #A99EBA; background: transparent;")
        self.update()
        super().leaveEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        rect = self.rect().adjusted(1, 1, -1, -1)
        radius = 14.0

        # Light glass dark purple background
        bg_gradient = QLinearGradient(0, 0, self.width(), self.height())
        if self._hovered:
            bg_gradient.setColorAt(0.0, QColor(32, 24, 46, 220))
            bg_gradient.setColorAt(0.5, QColor(24, 18, 36, 230))
            bg_gradient.setColorAt(1.0, QColor(16, 12, 24, 240))
        else:
            bg_gradient.setColorAt(0.0, QColor(22, 17, 32, 180))
            bg_gradient.setColorAt(0.5, QColor(17, 13, 25, 190))
            bg_gradient.setColorAt(1.0, QColor(12, 9, 18, 200))

        # Shaded Purple Border Gradient
        border_gradient = QLinearGradient(0, 0, self.width(), self.height())
        if self._hovered:
            border_gradient.setColorAt(0.0, QColor("#C084FC"))  # Bright purple
            border_gradient.setColorAt(0.5, QColor("#9333EA"))  # Vibrant purple
            border_gradient.setColorAt(1.0, QColor("#581C87"))  # Deep purple
            pen_width = 1.5
        else:
            border_gradient.setColorAt(0.0, QColor("#7E22CE"))  # Purple
            border_gradient.setColorAt(0.5, QColor("#5B21B6"))  # Shaded purple
            border_gradient.setColorAt(1.0, QColor("#3B0764"))  # Dark purple
            pen_width = 1.2

        painter.setBrush(QBrush(bg_gradient))
        painter.setPen(QPen(QBrush(border_gradient), pen_width))
        painter.drawRoundedRect(rect, radius, radius)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
            event.accept()
            return
        super().mousePressEvent(event)


class HelpDialog(QDialog):
    """Premium dark help popup with a connected step-by-step timeline."""

    def __init__(self, title, subtitle, steps, parent=None):
        super().__init__(parent)
        self.setModal(True)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        screen = QApplication.primaryScreen()
        target_w, target_h = 820, 680
        if screen:
            area = screen.availableGeometry()
            target_w = min(target_w, max(720, area.width() - 70))
            target_h = min(target_h, max(590, area.height() - 70))
        self.resize(target_w, target_h)
        self.setMinimumSize(720, 590)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(14, 14, 14, 14)

        self.container = QFrame(self)
        self.container.setObjectName("HelpDialogContainer")
        outer.addWidget(self.container)

        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(46)
        shadow.setOffset(0, 12)
        shadow.setColor(QColor(0, 0, 0, 180))
        self.container.setGraphicsEffect(shadow)

        layout = QVBoxLayout(self.container)
        layout.setContentsMargins(30, 26, 30, 22)
        layout.setSpacing(14)

        header = QHBoxLayout()
        title_col = QVBoxLayout()
        title_col.setSpacing(5)

        self.title_label = QLabel(title, self.container)
        self.title_label.setFont(QFont("Segoe UI", 18, QFont.Weight.Bold))

        self.subtitle_label = QLabel(subtitle, self.container)
        self.subtitle_label.setWordWrap(True)
        self.subtitle_label.setFont(QFont("Segoe UI", 9))

        title_col.addWidget(self.title_label)
        title_col.addWidget(self.subtitle_label)
        header.addLayout(title_col, 1)

        close_btn = QPushButton("×", self.container)
        close_btn.setFixedSize(34, 34)
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.clicked.connect(self.reject)
        close_btn.setStyleSheet(
            """
            QPushButton {
                border: none;
                background: transparent;
                color: #8F8999;
                font-size: 26px;
                font-weight: 600;
                border-radius: 8px;
            }
            QPushButton:hover {
                background: #302B37;
                color: #FFFFFF;
            }
            """
        )
        header.addWidget(close_btn, 0, Qt.AlignmentFlag.AlignTop)
        layout.addLayout(header)

        separator = QFrame(self.container)
        separator.setFixedHeight(1)
        separator.setStyleSheet("background: #332E3A;")
        layout.addWidget(separator)

        scroll = QScrollArea(self.container)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        scroll.setStyleSheet(
            """
            QScrollArea {
                background: transparent;
                border: none;
            }
            QScrollBar:vertical {
                background: transparent;
                width: 7px;
                margin: 2px 0 2px 2px;
            }
            QScrollBar::handle:vertical {
                background: #5D3A70;
                border-radius: 3px;
                min-height: 34px;
            }
            QScrollBar::handle:vertical:hover {
                background: #7B2CBF;
            }
            QScrollBar::add-line:vertical,
            QScrollBar::sub-line:vertical {
                height: 0px;
            }
            """
        )

        body_widget = QWidget()
        body_widget.setObjectName("HelpBodyWidget")
        body_layout = QVBoxLayout(body_widget)
        body_layout.setContentsMargins(2, 10, 8, 6)
        body_layout.setSpacing(0)

        for i, step in enumerate(steps):
            widget = StepWidget(
                i + 1,
                i == len(steps) - 1,
                step["title"],
                step["desc"],
                step.get("button"),
                body_widget,
            )
            body_layout.addWidget(widget)

        scroll.setWidget(body_widget)
        layout.addWidget(scroll, 1)

        footer = QHBoxLayout()
        footer.setContentsMargins(0, 6, 0, 0)
        footer.addStretch(1)

        self.done_btn = QPushButton("Done", self.container)
        self.done_btn.setFixedSize(110, 38)
        self.done_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.done_btn.setStyleSheet(
            """
            QPushButton {
                background: #34313A;
                color: #D6D1DB;
                border: 1px solid #47424E;
                border-radius: 9px;
                font-family: "Segoe UI";
                font-size: 13px;
                font-weight: 600;
            }
            QPushButton:hover {
                background: #3B3742;
                color: #F0EDF3;
                border-color: #57505F;
            }
            QPushButton:pressed {
                background: #2D2A32;
            }
            """
        )
        self.done_btn.clicked.connect(self.accept)
        footer.addWidget(self.done_btn)

        layout.addLayout(footer)

        self.container.setStyleSheet(
            """
            QFrame#HelpDialogContainer {
                background: #1C1920;
                border: 1px solid #3A3140;
                border-radius: 18px;
            }
            """
        )
        body_widget.setStyleSheet(
            "QWidget#HelpBodyWidget { background: transparent; }"
        )
        self.title_label.setStyleSheet(
            "color: #F7F3FA; background: transparent;"
        )
        self.subtitle_label.setStyleSheet(
            "color: #97909F; background: transparent;"
        )
        self._center_on_parent()

    def _center_on_parent(self):
        parent = self.parentWidget()
        if parent and parent.isVisible():
            center = parent.mapToGlobal(parent.rect().center())
        else:
            screen = QApplication.primaryScreen()
            center = (
                screen.availableGeometry().center()
                if screen
                else None
            )
        if center is None:
            return

        geo = self.frameGeometry()
        geo.moveCenter(center)
        self.move(geo.topLeft())


def _open_url(url):
    try:
        print(url)
        QDesktopServices.openUrl(QUrl(url))
    except Exception:
        print('ex', url)
        try:
            webbrowser.open(url)
        except Exception:
            pass


def _provider_help_steps(provider):
    provider_data = {
        "Groq AI": {
            "url": "https://console.groq.com/keys",
            "button": "Groq AI",
            "steps": [
                {
                    "title": "Open the Groq API Console",
                    "desc": "Open the official Groq API key page. Sign in to your Groq account if needed, then open the API Keys area."
                },
                {
                    "title": "Create an API key",
                    "desc": "Use Create API Key, give the key a name, complete any requested verification, and create the key."
                },
                {
                    "title": "Copy the key",
                    "desc": "Copy the generated key immediately and keep it private. Do not post it in screenshots, chats, GitHub, or public files."
                },
            ],
        },
        "OpenRouter AI": {
            "url": "https://openrouter.ai/",
            "button": "OpenRouter AI",
            "steps": [
                {
                    "title": "Open OpenRouter",
                    "desc": "Open the official OpenRouter website and create an account or sign in to your existing account."
                },
                {
                    "title": "Open your profile and API Keys",
                    "desc": "After signing in, open your profile/account area, go to API Keys, choose New Key, and create a new key."
                },
                {
                    "title": "Copy the key",
                    "desc": "Copy the generated OpenRouter key immediately and keep it private."
                },
            ],
        },
        "Ollama Cloud": {
            "url": "https://ollama.com/",
            "button": "Ollama Cloud",
            "steps": [
                {
                    "title": "Open Ollama",
                    "desc": "Open the official Ollama website and sign up or sign in to your account."
                },
                {
                    "title": "Open Settings → Keys",
                    "desc": "From your account settings, open the Keys section and create a new API key."
                },
                {
                    "title": "Copy the key",
                    "desc": "Copy the generated Ollama Cloud key immediately and keep it private."
                },
            ],
        },
    }
    data = provider_data.get(provider)
    steps = []
    for item in data["steps"]:
        steps.append(dict(item))
    steps[0]["button"] = {"text": "Open site", "callback": lambda: _open_url(data["url"])}
    return steps


def _show_provider_api_help(provider, parent=None, return_to_main=True):
    provider_title = provider
    steps = _provider_help_steps(provider)
    dialog = HelpDialog(
        f"How to get an API key -> {provider_title}",
        "Follow these steps, copy the key, then paste it into the matching provider in Settings → API Configurations.",
        steps,
        parent=parent,
    )

    if return_to_main:
        dialog.done_btn.clicked.disconnect()
        dialog.done_btn.clicked.connect(lambda: _return_to_api_key_main(dialog, parent))
    return dialog.exec()


def _return_to_api_key_main(dialog, parent):
    try:
        dialog.accept()
    except Exception:
        pass
    QTimer.singleShot(0, lambda: show_api_key_help(parent))


def show_api_key_help(parent=None):
    def open_provider(provider):
        modal = QApplication.activeModalWidget()
        if modal is not None:
            try:
                modal.accept()
            except Exception:
                pass
        _show_provider_api_help(provider, parent)

    steps = [
        {
            "title": "Choose a provider",
            "desc": "Go to any provider below and create an API key. Void-Ai supports Groq AI, OpenRouter AI, and Ollama Cloud.",
            "button": [
                {"text": "Groq AI", "callback": lambda: open_provider("Groq AI")},
                {"text": "OpenRouter AI", "callback": lambda: open_provider("OpenRouter AI")},
                {"text": "Ollama Cloud", "callback": lambda: open_provider("Ollama Cloud")},
            ],
        },
        {
            "title": "Paste the key into Settings",
            "desc": "Copy the provider key you created, then open Settings → API Configurations and paste it into the matching provider's API key field. Save the field after pasting.",
        },
        {
            "title": "Choose your model",
            "desc": "In API Configurations, choose the provider and model for Fast, Flash, and Complex. You can change these later without editing source code.",
        },
    ]
    dialog = HelpDialog(
        "How to get an API key",
        "Void-Ai supports Groq AI, OpenRouter AI, and Ollama Cloud. Choose one provider below to see its exact setup steps.",
        steps,
        parent=parent,
    )
    return dialog.exec()


def show_chat_help(parent=None):
    steps = [
        {"title": "Start a chat", "desc": "Type your message into the chat box and press Enter. Use Shift+Enter when you want a new line without sending."},
        {"title": "Choose how Void-Ai should think", "desc": "Fast, Flash, and Complex use the model/provider configuration from Settings → API Configurations. You can choose different supported models for each role."},
        {"title": "Mode switching & Specialized chats", "desc": "You can select custom preset cards such as 'A Friend', 'Dev helper', or 'Learn Zone' to create specialized chats with custom system prompts. Alternatively, you can start a chat without selecting any mode. Note: Once a chat is started with a message, its mode is locked and cannot be changed later."},
        {"title": "Your chats are saved", "desc": "Void-Ai keeps conversations in its local multi-chat store, so you can switch between chats and return to older conversations."},
        {"title": "Work with code", "desc": "Ask Void-Ai to write, explain, debug, refactor, or improve code. Code responses are formatted into readable code blocks so copying is easier."},
        {"title": "Manage individual chats", "desc": "Use the chat sidebar to switch chats, rename or pin conversations, and delete an individual chat when you no longer need it."},
        {"title": "Clear everything when needed", "desc": "Settings → Data Management → Clear all data removes chats, messages, memories, and database data while leaving your saved settings and API configuration intact."},
    ]
    dialog = HelpDialog(
        "How to chat in Void-Ai",
        "Use multi-chat, model roles, memory, and code-focused conversations without changing the existing interface.",
        steps,
        parent=parent
    )
    return dialog.exec()


def show_customization_help(parent=None, open_settings=None):
    def _settings():
        modal = QApplication.activeModalWidget()
        if modal is not None and modal is not parent:
            try:
                modal.accept()
            except Exception:
                pass
        if callable(open_settings):
            open_settings()
        else:
            QMessageBox.information(
                parent,
                "Settings",
                "Launch Void-Ai normally to open System Settings.",
            )

    steps = [
        {
            "title": "Appearance & Themes",
            "desc": "Adjust chat text size and manage the accent themes assigned to Fast, Flash, and Complex."
        },
        {
            "title": "System Behavior",
            "desc": "Control the background aura animation, automatic loading of the recent chat, and real-time response streaming."
        },
        {
            "title": "API Configurations",
            "desc": "Manage Groq AI, OpenRouter AI, and Ollama Cloud API keys, then choose the provider and model used by Fast, Flash, and Complex."
        },
        {
            "title": "API Model Catalog",
            "desc": "Manage the model catalog used by the provider/model selectors. You can edit model IDs, delete entries, and add new catalog models from Settings."
        },
        {
            "title": "Data Management",
            "desc": "Clear all stored conversation data when you need a clean start, or restore the default application settings and API catalog from the built-in defaults backup."
        },
        {
            "title": "Built-in defaults",
            "desc": "Void-Ai includes default settings and API catalog data so Restore all settings can bring the configuration back to its original built-in state."
        },
        {
            "title": "Customize your model roles",
            "desc": "Fast, Flash, and Complex each have a selectable provider/model setup. Choose the model you prefer for each role and save it from API Configurations."
        },
        {
            "title": "Open Settings",
            "desc": "Use the button below to open the real System Settings page and change these options directly.",
            "button": {"text": "Open Settings", "callback": _settings}
        },
    ]
    dialog = HelpDialog(
        "Customize Void-Ai",
        "The Settings page controls appearance, behavior, API providers, model catalog entries, defaults, and data management.",
        steps,
        parent=parent
    )
    return dialog.exec()


def show_developer_help(parent=None):
    steps = [
        {"title": "Enable Developer Options", "desc": "Go to Settings → About → Developer Options and turn the switch on."},
        {"title": "What it unlocks", "desc": "Developer Options reveals the System Logs tab in the navigation panel."},
        {"title": "Check API errors", "desc": "When a Groq AI, OpenRouter AI, Ollama Cloud, model-selection, or other runtime operation fails, use System Logs to inspect the recorded error details."},
        {"title": "Check chat and system problems", "desc": "System Logs can also help you inspect problems with chat operations, navigation, loading, data management, configuration updates, and other application behavior."},
        {"title": "When to use it", "desc": "Turn Developer Options on when something does not behave as expected and you need more information before troubleshooting or reporting the issue."},
        {"title": "Turn it off when finished", "desc": "Disable Developer Options again to hide System Logs from the navigation bar."}
    ]
    dialog = HelpDialog(
        "Developer Options",
        "An optional diagnostic mode for troubleshooting API errors, system errors, and logs, and troubleshooting diagnostics.",
        steps,
        parent=parent
    )
    return dialog.exec()


class HelpPage(SmoothScrollArea):
    """Full Help tab; dark glass, compact and visually consistent with Void-Ai."""

    def __init__(self, main_window=None, parent=None):
        super().__init__(parent)
        self.main_window = main_window

        self.setObjectName("helpPage")
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded
        )
        self.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)

        self.container = QWidget()
        self.container.setObjectName("helpContainer")
        self.setWidget(self.container)

        self.layout = QVBoxLayout(self.container)
        self.layout.setContentsMargins(42, 22, 42, 30)
        self.layout.setSpacing(14)

        header = QHBoxLayout()
        header.setSpacing(14)

        title_col = QVBoxLayout()
        title_col.setSpacing(4)

        # 3 color shade title label from about_ui.py (without glow)
        self.title_lbl = GradientTitleLabel("Help", self.container)

        self.subtitle_lbl = QLabel(
            "Everything you need to get Void-Ai running, customize it, chat with it, and troubleshoot it.",
            self.container,
        )
        self.subtitle_lbl.setWordWrap(True)
        self.subtitle_lbl.setFont(QFont("Segoe UI", 10))

        title_col.addWidget(self.title_lbl)
        title_col.addWidget(self.subtitle_lbl)
        header.addLayout(title_col, 1)

        self.badge = QLabel("VOID-AI • HELP", self.container)
        self.badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.badge.setFixedSize(132, 34)
        header.addWidget(
            self.badge,
            0,
            Qt.AlignmentFlag.AlignTop,
        )
        self.layout.addLayout(header)

        self.hero = QFrame(self.container)
        self.hero.setObjectName("helpHero")
        hero_layout = QVBoxLayout(self.hero)
        hero_layout.setContentsMargins(0, 4, 0, 8)
        hero_layout.setSpacing(2)

        self.hero_title = QLabel("New to Void-AI? Start here.", self.hero)
        self.hero_title.setFont(
            QFont("Segoe UI", 13, QFont.Weight.DemiBold)
        )
        self.hero_body = QLabel(
            "The quickest setup is: get a Groq AI, OpenRouter AI, or Ollama Cloud API key, add it in Settings → API Configurations, then click New Chat and send your first message.",
            self.hero,
        )
        self.hero_body.setWordWrap(True)
        self.hero_body.setFont(QFont("Segoe UI", 10))

        hero_layout.addWidget(self.hero_title)
        hero_layout.addWidget(self.hero_body)
        self.layout.addWidget(self.hero)

        # Setup Grid and Wrapper to stop columns drifting apart
        self.grid_host = QWidget(self.container)
        self.grid = QGridLayout(self.grid_host)
        self.grid.setContentsMargins(0, 0, 0, 0)
        self.grid.setHorizontalSpacing(16)
        self.grid.setVerticalSpacing(16)

        self.grid_wrapper = QHBoxLayout()
        self.grid_wrapper.addWidget(self.grid_host, 1)
        self.grid_wrapper.addStretch(0)

        self.layout.addLayout(self.grid_wrapper)
        self.layout.addStretch(1)

        self.cards = []
        self._build_cards()
        self._apply_theme()

    def showEvent(self, event):
        super().showEvent(event)
        QTimer.singleShot(0, self._repair_page_layout)
        QTimer.singleShot(100, self._repair_page_layout)

    def _repair_page_layout(self):
        try:
            layout = self.container.layout()
            if layout is not None:
                layout.invalidate()
                layout.activate()
            self.container.updateGeometry()
            self.grid_host.updateGeometry()
            self.grid_host.adjustSize()
            self.updateGeometry()
            self.update()
        except Exception:
            pass

    def _build_cards(self):
        definitions = [
            (
                "key",
                "How to get API key?",
                "Create a Groq AI, OpenRouter AI, or Ollama Cloud key and connect it to the matching provider in API Configurations.",
                lambda: show_api_key_help(self),
            ),
            (
                "settings",
                "Customize Void-Ai",
                "Learn what the Settings page can change and when each option is useful.",
                lambda: show_customization_help(
                    self,
                    self._open_settings,
                ),
            ),
            (
                "info",
                "How does this app work?",
                "A quick guide to Void Core, multiple API providers, model routing, chat memory, and local storage.",
                lambda: self._show_about_how(),
            ),
            (
                "chat",
                "How to chat?",
                "Send messages, save conversations, work with code blocks, and manage chats.",
                lambda: show_chat_help(self),
            ),
            (
                "developer",
                "Developer Options",
                "Inspect API errors, system errors, logs, and troubleshooting diagnostics.",
                lambda: show_developer_help(self),
            ),
            (
                "about",
                "About",
                "Open the real About tab from inside the app.",
                self._open_about,
            ),
        ]

        for icon_kind, title, desc, callback in definitions:
            card = ModernCard(
                icon_kind,
                title,
                desc,
                clickable=True,
                parent=self.grid_host,
            )
            card.clicked.connect(callback)
            self.cards.append(card)

        self._relayout_cards()

    def _relayout_cards(self):
        while self.grid.count():
            item = self.grid.takeAt(0)
            widget = item.widget()
            if widget:
                widget.setParent(self.grid_host)

        available_width = max(0, self.viewport().width() - 84)
        columns = 2 if available_width >= 720 else 1

        for card in self.cards:
            card.update_responsive_icon(available_width)

        self.grid.setColumnStretch(0, 1)
        if columns == 2:
            self.grid.setColumnStretch(1, 1)
            self.grid_host.setMaximumWidth(750 * 2 + 16)
        else:
            self.grid.setColumnStretch(1, 0)
            self.grid_host.setMaximumWidth(750)

        for index, card in enumerate(self.cards):
            if columns == 1:
                self.grid.addWidget(card, index, 0)
            else:
                row, col = divmod(index, 2)
                self.grid.addWidget(card, row, col)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        QTimer.singleShot(0, self._relayout_cards)

    def _show_about_how(self):
        steps = [
            {
                "title": "Void Core",
                "desc": "The main chat surface where you talk to the AI, switch chats, and work with the current conversation."
            },
            {
                "title": "Multiple API providers",
                "desc": "Void-Ai can use Groq AI, OpenRouter AI, and Ollama Cloud. The active provider and model for Fast, Flash, and Complex are selected from Settings → API Configurations."
            },
            {
                "title": "Model routing",
                "desc": "Fast, Flash, and Complex are separate model roles. You can customize each role with a provider and model from the available API Model Catalog."
            },
            {
                "title": "Chat storage",
                "desc": "The existing multi-chat store keeps individual conversation data available when you switch between chats, while the settings configuration remains separate."
            },
            {
                "title": "Memory",
                "desc": "The AI engine can use the existing memory system to preserve relevant context for the chat experience."
            },
            {
                "title": "Settings & defaults",
                "desc": "Settings control appearance, behavior, API configurations, catalog entries, and data management. Built-in defaults allow the settings and API catalog to be restored when needed."
            },
            {
                "title": "System Logs",
                "desc": "Available as a developer-only navigation tab when Developer Options are enabled, including API and system error details useful for troubleshooting."
            },
        ]
        dialog = HelpDialog(
            "How Void-Ai works",
            "Quick overview of the core app flow, supported providers, model roles, memory, storage, and troubleshooting tools.",
            steps,
            parent=self,
        )
        dialog.exec()

    def _open_settings(self):
        if self.main_window and hasattr(self.main_window, "open_settings"):
            self.main_window.open_settings()
            return
        QMessageBox.information(
            self,
            "Settings",
            "Launch Void-Ai normally to open System Settings.",
        )

    def _open_about(self):
        if self.main_window and hasattr(self.main_window, "open_about"):
            self.main_window.open_about()
            return
        QMessageBox.information(
            self,
            "About",
            "Launch Void-Ai normally to open the About tab.",
        )

    def _apply_theme(self):
        self.setStyleSheet(
            """
            QScrollArea#helpPage {
                border: none;
                background: #111111;
            }
            QScrollBar:vertical,
            QScrollBar:horizontal {
                background: #181818;
                border: none;
            }
            QScrollBar:vertical {
                width: 9px;
                margin: 0;
            }
            QScrollBar:horizontal {
                height: 9px;
                margin: 0;
            }
            QScrollBar::handle:vertical,
            QScrollBar::handle:horizontal {
                background: #3A3A3A;
                border-radius: 4px;
                min-width: 28px;
                min-height: 28px;
            }
            QScrollBar::handle:vertical:hover,
            QScrollBar::handle:horizontal:hover {
                background: #4A4A4A;
            }
            QScrollBar::add-line:vertical,
            QScrollBar::sub-line:vertical,
            QScrollBar::add-line:horizontal,
            QScrollBar::sub-line:horizontal {
                width: 0px;
                height: 0px;
                border: none;
                background: none;
            }
            QScrollBar::add-page:vertical,
            QScrollBar::sub-page:vertical,
            QScrollBar::add-page:horizontal,
            QScrollBar::sub-page:horizontal {
                background: #181818;
            }
            """
        )
        self.container.setStyleSheet(
            "QWidget#helpContainer { background: #111111; }"
        )
        self.subtitle_lbl.setStyleSheet(
            "color: #8F8997; background: transparent;"
        )
        self.badge.setStyleSheet(
            """
            QLabel {
                background: #1B1220;
                color: #C98CF5;
                border: 1px solid #4A2B5A;
                border-radius: 11px;
                padding: 5px 10px;
                font-size: 10px;
                font-weight: 700;
                letter-spacing: 1px;
            }
            """
        )
        self.hero.setStyleSheet(
            "QFrame#helpHero { background: transparent; border: none; }"
        )
        self.hero_title.setStyleSheet(
            "color: #D69AF8; background: transparent;"
        )
        self.hero_body.setStyleSheet(
            "color: #9A949F; background: transparent;"
        )

    def open_help_card(self, title):
        for card in self.cards:
            if card.title_label.text() == title:
                card.clicked.emit()
                return True
        return False


if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setApplicationName("Void-Ai Help")
    window = HelpPage()
    window.setWindowTitle("Void-Ai — Help")
    window.resize(1080, 760)
    window.show()
    sys.exit(app.exec())