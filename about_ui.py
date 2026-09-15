import sys

from PyQt6.QtCore import Qt, QUrl, QTimer
from PyQt6.QtGui import (
    QDesktopServices, 
    QCursor, 
    QFont, 
    QColor, 
    QPainter, 
    QLinearGradient, 
    QPainterPath
)
from PyQt6.QtWidgets import (
    QApplication,
    QDialog,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QFrame,
    QGraphicsDropShadowEffect,
    QSizePolicy,
)

# qfluentwidgets මගින් icons ලබාගැනීම
from qfluentwidgets import FluentIcon as FIF, SmoothScrollArea


class GradientTitleLabel(QLabel):
    """Large Impact title with a soft light-grey -> white -> light-grey shade."""

    def __init__(self, text="", parent=None):
        super().__init__(text, parent)
        self.setObjectName("appTitle")
        self.setFont(QFont("Impact", 46))
        self.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self.setMinimumHeight(58)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)

        fm = self.fontMetrics()
        text_width = fm.horizontalAdvance(self.text())
        rect = self.rect()

        # අකුරු වල පළලට පමණක් ගැලපෙන ලෙස Gradient එක සැකසීම (3 color shade)
        gradient = QLinearGradient(0, 0, text_width, 0)
        gradient.setColorAt(0.00, QColor("#A0A0B0"))  # Grey
        gradient.setColorAt(0.50, QColor("#FFFFFF"))  # White
        gradient.setColorAt(1.00, QColor("#A0A0B0"))  # Grey

        # Text එක හිස්ව පෙනෙන Bug එක පාලනය කිරීමට QPainterPath භාවිතයෙන් අකුරු හැඩතල ඇඳීම 
        path = QPainterPath()
        y = rect.center().y() + fm.ascent() / 2.0 - fm.descent() / 2.0
        path.addText(0.0, float(y), self.font(), self.text())

        painter.fillPath(path, gradient)


class FeatureItem(QFrame):
    """Minimal feature row: no card border/background, only an accent line + hover."""

    def __init__(self, title, description, parent=None):
        super().__init__(parent)
        self.setObjectName("featureItem")
        self.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Minimum,
        )
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 11, 10, 12)
        layout.setSpacing(4)

        title_label = QLabel(title, self)
        title_label.setObjectName("featureTitle")
        title_label.setWordWrap(True)
        title_label.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Minimum,
        )
        title_label.setAttribute(
            Qt.WidgetAttribute.WA_TransparentForMouseEvents,
            True,
        )

        desc_label = QLabel(description, self)
        desc_label.setObjectName("featureDesc")
        desc_label.setWordWrap(True)
        desc_label.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Minimum,
        )
        desc_label.setAlignment(
            Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft
        )
        desc_label.setAttribute(
            Qt.WidgetAttribute.WA_TransparentForMouseEvents,
            True,
        )

        layout.addWidget(title_label)
        layout.addWidget(desc_label)


class ContactDialog(QDialog):
    """Compact contact dialog styled to match the existing About/Settings modal language."""

    EMAIL = "hmvimithavimitha@gmail.com"

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setModal(True)

        self.container = QFrame(self)
        self.container.setObjectName("ContactCardContainer")

        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(25)
        shadow.setColor(QColor(0, 0, 0, 170))
        shadow.setOffset(0, 8)
        self.container.setGraphicsEffect(shadow)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(10, 10, 10, 10)
        outer.addWidget(self.container)

        layout = QVBoxLayout(self.container)
        layout.setContentsMargins(22, 20, 22, 22)
        layout.setSpacing(12)

        title = QLabel("Contact Me", self.container)
        title.setObjectName("ContactTitle")
        title.setFont(QFont("Impact", 12, QFont.Weight.Bold))

        body = QLabel(
            "Get in touch through GitHub, WhatsApp, or email. Your client and browser will open only after you choose an action.",
            self.container,
        )
        body.setObjectName("ContactBody")
        body.setWordWrap(True)
        body.setFont(QFont("Segoe UI", 9))

        layout.addWidget(title)
        layout.addWidget(body)

        github_btn = QPushButton("View on GitHub", self.container)
        github_btn.setObjectName("ContactActionBtn")
        github_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        github_btn.clicked.connect(lambda: QDesktopServices.openUrl(QUrl("https://github.com/VimithaProCoding")))
        layout.addWidget(github_btn)

        # අලුත් WhatsApp Button එක
        whatsapp_btn = QPushButton("View on WhatsApp", self.container)
        whatsapp_btn.setObjectName("ContactWhatsappBtn")
        whatsapp_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        whatsapp_btn.clicked.connect(self.open_whatsapp)
        layout.addWidget(whatsapp_btn)

        email_row = QHBoxLayout()
        email_row.setSpacing(8)

        email_label = QLabel(self.EMAIL, self.container)
        email_label.setObjectName("ContactEmail")
        email_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)

        # FIF භාවිතා කල අලුත් Copy Icon Button එක
        self.copy_btn = QPushButton(self.container)
        self.copy_btn.setObjectName("CopyEmailBtn")
        self.copy_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.copy_btn.setFixedSize(34, 34)
        self.copy_btn.setToolTip("Copy email")
        self.copy_btn.setIcon(FIF.COPY.icon(color=QColor("white")))
        self.copy_btn.clicked.connect(self.copy_email)

        email_row.addWidget(email_label, 1)
        email_row.addWidget(self.copy_btn)
        layout.addLayout(email_row)

        footer = QHBoxLayout()
        footer.addStretch(1)
        done_btn = QPushButton("Done", self.container)
        done_btn.setObjectName("ContactDoneBtn")
        done_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        done_btn.setFixedSize(92, 36)
        done_btn.clicked.connect(self.accept)
        footer.addWidget(done_btn)
        layout.addSpacing(4)
        layout.addLayout(footer)

        self.setFixedWidth(420)
        self.setStyleSheet("""
            QFrame#ContactCardContainer {
                background-color: #202020;
                border: 1px solid #383346;
                border-radius: 12px;
            }
            QLabel#ContactTitle { color: #FFFFFF; }
            QLabel#ContactBody { color: #A39EB2; line-height: 1.4; }
            QLabel#ContactEmail {
                color: #F0DDF9;
                background-color: #2F2A3A;
                border: 1px solid #433D52;
                border-radius: 8px;
                padding: 8px 10px;
            }
            QPushButton#ContactActionBtn {
                background-color: #A855F7;
                color: #FFFFFF;
                border: none;
                border-radius: 8px;
                padding: 7px 16px;
                font-size: 13px;
                font-weight: 600;
            }
            QPushButton#ContactActionBtn:hover { background-color: #9333EA; }
            
            QPushButton#ContactWhatsappBtn {
                background-color: #25D366;
                color: #FFFFFF;
                border: none;
                border-radius: 8px;
                padding: 7px 16px;
                font-size: 13px;
                font-weight: 600;
            }
            QPushButton#ContactWhatsappBtn:hover { background-color: #20BD5A; }

            QPushButton#CopyEmailBtn {
                background-color: #2F2A3A;
                border: 1px solid #433D52;
                border-radius: 8px;
            }
            QPushButton#CopyEmailBtn:hover {
                background-color: #3B3449;
            }
            QPushButton#ContactDoneBtn {
                background-color: #2F2A3A;
                color: #D6D1E3;
                border: 1px solid #433D52;
                border-radius: 8px;
                font-size: 13px;
                font-weight: 600;
            }
            QPushButton#ContactDoneBtn:hover {
                background-color: #3B3449;
                color: #FFFFFF;
            }
        """)

    def showEvent(self, event):
        # Popup එක UI එකේ මැදින්ම විවෘත වීම තහවුරු කිරීමට showEvent භාවිතා කිරීම
        super().showEvent(event)
        self._center_on_parent()

    def open_whatsapp(self):
        # Auto message එක සමග web.whatsapp හරහා විවෘත වීම
        url = "https://web.whatsapp.com/send?phone=9472229307"
        QDesktopServices.openUrl(QUrl(url))

    def copy_email(self):
        QApplication.clipboard().setText(self.EMAIL)
        
        # Click කළ විට එන Animation / Hover Effect සහ Icon එක (right/accept) මාරු වීම
        self.copy_btn.setIcon(FIF.ACCEPT.icon(color=QColor("white")))
        self.copy_btn.setStyleSheet("""
            QPushButton#CopyEmailBtn {
                background-color: #3B3449; 
                border: 1px solid #9D4EDD;
            }
        """)
        
        # තත්පර 2කට පසු නැවතත් පැරණි icon එකටම මාරු වීම
        QTimer.singleShot(2000, self.reset_copy_btn)

    def reset_copy_btn(self):
        self.copy_btn.setIcon(FIF.COPY.icon(color=QColor("white")))
        self.copy_btn.setStyleSheet("")

    def _center_on_parent(self):
        parent = self.parentWidget()
        if parent and parent.isVisible():
            center = parent.mapToGlobal(parent.rect().center())
        else:
            screen = QApplication.primaryScreen()
            center = screen.availableGeometry().center() if screen else None
        
        if center is not None:
            geo = self.frameGeometry()
            geo.moveCenter(center)
            self.move(geo.topLeft())


class AboutPage(SmoothScrollArea):
    """Void-Ai About page integrated to match the application's main UI layout."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("aboutPage")
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)

        self._build_ui()
        self._setup_animations()
        self._apply_styles()

    def _build_ui(self):
        content_widget = QWidget()
        content_widget.setObjectName("scrollContent")
        content_widget.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Minimum,
        )

        content_layout = QVBoxLayout(content_widget)
        content_layout.setContentsMargins(40, 40, 40, 40)
        content_layout.setSpacing(16)
        content_layout.setSizeConstraint(QVBoxLayout.SizeConstraint.SetMinAndMaxSize)

        header_layout = QVBoxLayout()
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(7)

        self.app_title = GradientTitleLabel("About", content_widget)
        
        # Void-Ai Label එකට යටින් Version එක එක් කිරීම
        #self.version_footer = QLabel("\nvoid-ai 1.1.1", content_widget)
        #self.version_footer.setObjectName("versionFooter")

        app_subtitle = QLabel(
            "\nMid-Level AI Desktop Interface — Powered by Python",
            content_widget,
        )
        app_subtitle.setObjectName("appSubtitle")
        app_subtitle.setWordWrap(True)

        app_desc = QLabel(
            "<span style='color: #C77DFF; font-weight: 600;'>"
            "Void-Ai is a desktop artificial intelligence interface"
            "</span> engineered with Python, PyQt6, and QFluentWidgets for "
            "responsive AI workflows, modular provider support, memory, and local chat management.",
            content_widget,
        )
        app_desc.setObjectName("mainDesc")
        app_desc.setWordWrap(True)
        app_desc.setTextFormat(Qt.TextFormat.RichText)

        header_layout.addWidget(self.app_title)
        #header_layout.addWidget(self.version_footer)
        header_layout.addWidget(app_subtitle)
        header_layout.addWidget(app_desc)
        content_layout.addLayout(header_layout)

        content_layout.addWidget(self._separator())

        features_header = QLabel("New Looks", content_widget)
        features_header.setObjectName("sectionHeader")
        content_layout.addWidget(features_header)

        features_widget = QWidget(content_widget)
        features_widget.setObjectName("featuresWidget")
        features_widget.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Minimum,
        )
        features_layout = QVBoxLayout(features_widget)
        features_layout.setContentsMargins(0, 0, 0, 0)
        features_layout.setSpacing(2)

        features_list = [
            (
                "Fluent UI Experience",
                "Designed with smooth animations, fluid transitions, and responsive layout panels.",
            ),
            (
                "Multi-Provider AI Support",
                "Connect Groq AI, OpenRouter AI, or Ollama Cloud and choose the provider/model that fits each AI role.",
            ),
            (
                "Custom Code Block Rendering",
                "Features syntax-highlighted code blocks with one-click copy utilities.",
            ),
            (
                "Persistent Memory Save",
                "Intelligently saves and restores session context across chats seamlessly.",
            ),
            (
                "Multi-Chat Management",
                "Effortlessly handle multiple concurrent chat threads and topics.",
            ),
            (
                "Interactive Navigation Bar",
                "A clean sidebar layout for instant switching between streams and settings.",
            ),
        ]

        for title, description in features_list:
            features_layout.addWidget(
                FeatureItem(title, description, features_widget)
            )

        content_layout.addWidget(features_widget)
        content_layout.addWidget(self._separator())

        dev_header = QLabel("Development & Author", content_widget)
        dev_header.setObjectName("sectionHeader")
        content_layout.addWidget(dev_header)

        dev_desc = QLabel(
            "Architected and refined by VimithaBro as a modular Python desktop AI application "
            "with multi-provider support, persistent chat handling, configurable models, and a developer-focused settings system.",
            content_widget,
        )
        dev_desc.setObjectName("devDesc")
        dev_desc.setWordWrap(True)
        content_layout.addWidget(dev_desc)

        btn_layout = QHBoxLayout()
        btn_layout.setContentsMargins(0, 1, 0, 0)
        btn_layout.setAlignment(Qt.AlignmentFlag.AlignLeft)

        self.contact_btn = QPushButton("Contact Me", content_widget)
        self.contact_btn.setObjectName("githubBtn")
        self.contact_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.contact_btn.setFixedSize(160, 40)
        self.contact_btn.clicked.connect(self.show_contact_dialog)
        btn_layout.addWidget(self.contact_btn)
        btn_layout.addStretch(1)
        content_layout.addLayout(btn_layout)

        content_layout.addStretch(1)

        self.setWidget(content_widget)

    @staticmethod
    def _separator():
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setObjectName("separator")
        line.setFixedHeight(1)
        return line

    def showEvent(self, event):
        super().showEvent(event)
        # Keep the existing glow animation, but repair the scroll/layout geometry
        # after FluentWindow switches to this page.
        QTimer.singleShot(0, self._repair_page_layout)
        QTimer.singleShot(100, self._repair_page_layout)

    def _repair_page_layout(self):
        try:
            layout = self.layout()
            if layout is not None:
                layout.invalidate()
                layout.activate()
            scroll_area = self.findChild(QScrollArea, "mainScrollArea")
            if scroll_area is not None:
                scroll_area.updateGeometry()
                scroll_area.viewport().update()
                content = scroll_area.widget()
                if content is not None:
                    content.updateGeometry()
                    content.adjustSize()
            self.updateGeometry()
            self.update()
        except Exception:
            pass

    def showEvent(self, event):
        super().showEvent(event)
        QTimer.singleShot(0, self._repair_page_layout)
        QTimer.singleShot(100, self._repair_page_layout)

    def _repair_page_layout(self):
        try:
            widget = self.widget()
            if widget is not None:
                layout = widget.layout()
                if layout is not None:
                    layout.invalidate()
                    layout.activate()
                widget.updateGeometry()
                widget.adjustSize()
            self.updateGeometry()
            self.update()
        except Exception:
            pass

    def _setup_animations(self):
        self.glow_effect = QGraphicsDropShadowEffect(self)
        self.glow_effect.setBlurRadius(18)
        self.glow_effect.setColor(QColor(157, 78, 221, 165))
        self.glow_effect.setOffset(0, 0)
        self.app_title.setGraphicsEffect(self.glow_effect)

        self.glow_timer = QTimer(self)
        self.glow_timer.timeout.connect(self._update_glow)
        self.glow_timer.start(70)

        self.glow_radius = 13.0
        self.glow_direction = 1

    def _update_glow(self):
        self.glow_radius += self.glow_direction * 0.12
        if self.glow_radius >= 24.0:
            self.glow_direction = -1
        elif self.glow_radius <= 10.0:
            self.glow_direction = 1
        self.glow_effect.setBlurRadius(self.glow_radius)

    def show_contact_dialog(self):
        dialog = ContactDialog(parent=self)
        dialog.exec()

    def _apply_styles(self):
        self.setStyleSheet(
            """
            #aboutPage,
            #scrollContent,
            #mainScrollArea {
                background-color: #111111;
                color: #ECECEC;
                font-family: 'Segoe UI', 'Inter', 'Helvetica Neue', sans-serif;
            }

            #mainScrollArea {
                border: none;
            }

            #featuresWidget {
                background: transparent;
            }

            QScrollBar:vertical {
                border: none;
                background: transparent;
                width: 8px;
                margin: 4px 2px 4px 0;
            }

            QScrollBar::handle:vertical {
                border: none;
                background: #404040;
                min-height: 54px;
                border-radius: 4px;
            }

            QScrollBar::handle:vertical:hover {
                background: #9D4EDD;
            }

            QScrollBar::handle:vertical:pressed {
                background: #C77DFF;
            }

            QScrollBar::add-line:vertical,
            QScrollBar::sub-line:vertical,
            QScrollBar::add-page:vertical,
            QScrollBar::sub-page:vertical {
                border: none;
                background: transparent;
                height: 0px;
            }

            #appTitle {
                background: transparent;
                color: #FFFFFF;
                font-family: "Impact";
                font-size: 46px;
                font-weight: 400;
            }

            #appSubtitle {
                font-size: 15px;
                font-weight: 600;
                color: #A3A3A3;
            }


            #versionFooter {
                font-size: 11px;
                font-weight: 500;
                color: #77727E;
                margin-top: -6px;
            }

            #mainDesc {
                font-size: 14px;
                color: #C5C5D2;
                line-height: 1.5;
                margin-top: 3px;
            }

            #sectionHeader {
                font-size: 19px;
                font-weight: 700;
                color: #FFFFFF;
                margin-top: 2px;
                margin-bottom: 3px;
            }

            #separator {
                background-color: #252525;
                border: none;
                margin-top: 4px;
                margin-bottom: 4px;
            }

            #featureItem {
                border: none;
                border-left: 2px solid #29242F;
                border-radius: 0px;
                background: transparent;
            }

            #featureItem:hover {
                border: none;
                border-left: 2px solid #9D4EDD;
                border-radius: 0px;
                background-color: rgba(157, 78, 221, 0.055);
            }

            #featureTitle {
                font-size: 14px;
                font-weight: 700;
                color: #FFFFFF;
            }

            #featureDesc {
                font-size: 13px;
                color: #9F9FA8;
            }

            #devDesc {
                font-size: 14px;
                color: #C5C5D2;
                line-height: 1.5;
            }

            #githubBtn {
                background-color: #7B2CBF;
                color: #FFFFFF;
                border: none;
                border-radius: 8px;
                font-size: 13px;
                font-weight: 600;
            }

            #githubBtn:hover {
                background-color: #8B3DD1;
            }

            #githubBtn:pressed {
                background-color: #6A1FA8;
            }
            """
        )


AboutTab = AboutPage


if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setFont(QFont("Segoe UI", 10))

    window = QWidget()
    window.setWindowTitle("Void-Ai - About")
    window.resize(1000, 750)

    layout = QVBoxLayout(window)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.addWidget(AboutPage())

    window.show()
    sys.exit(app.exec())