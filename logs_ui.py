from PyQt6.QtWidgets import QTextBrowser, QWidget, QVBoxLayout, QHBoxLayout
from qfluentwidgets import SmoothScrollArea, TitleLabel, PrimaryPushButton, FluentIcon as FIF, isDarkTheme
from ui1 import log_data_path, global_signals


class LogsPage(SmoothScrollArea):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("logsPage")
        self.setWidgetResizable(True)
        self.setStyleSheet("QScrollArea { border: none; background: transparent; }")
        
        self.container = QWidget()
        self.container.setStyleSheet("background: transparent;")
        self.layout = QVBoxLayout(self.container)
        self.layout.setContentsMargins(40, 40, 40, 40)
        self.layout.setSpacing(16)
        
        header_layout = QHBoxLayout()
        self.title_lbl = TitleLabel("System Logs", self)
        
        self.refresh_btn = PrimaryPushButton("Refresh Logs", self, FIF.SYNC)
        self.refresh_btn.setFixedWidth(150)
        self.refresh_btn.clicked.connect(self.load_logs)
        
        header_layout.addWidget(self.title_lbl)
        header_layout.addStretch(1)
        header_layout.addWidget(self.refresh_btn)
        self.layout.addLayout(header_layout)

        self.log_viewer = QTextBrowser(self.container)
        self.log_viewer.setReadOnly(True)
        self.layout.addWidget(self.log_viewer)

        self.setWidget(self.container)
        
        global_signals.dark_mode_toggled.connect(self.update_theme)
        self.update_theme()
        self.load_logs()

    def load_logs(self):
        try:
            with open(log_data_path, 'r', encoding='utf-8') as f:
                self.log_viewer.setPlainText(f.read())
            vbar = self.log_viewer.verticalScrollBar()
            vbar.setValue(vbar.maximum())
        except FileNotFoundError:
            self.log_viewer.setPlainText("No logs have been recorded yet.")
        except Exception as e:
            self.log_viewer.setPlainText(f"Failed to load logs: {e}")

    def update_theme(self):
        if isDarkTheme():
            self.log_viewer.setStyleSheet("background-color: #121218; color: #00FF7F; font-family: 'Consolas', monospace; font-size: 14px; border: 1px solid #333333; border-radius: 8px; padding: 10px;")
            self.title_lbl.setStyleSheet("font-size: 28px; color: white;")
        else:
            self.log_viewer.setStyleSheet("background-color: #f0f0f5; color: #006400; font-family: 'Consolas', monospace; font-size: 14px; border: 1px solid #cccccc; border-radius: 8px; padding: 10px;")
            self.title_lbl.setStyleSheet("font-size: 28px; color: black;")
