import logging

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QFrame, QMessageBox, QInputDialog

from PyQt6.QtWidgets import (QApplication, QMainWindow, QDialog, QVBoxLayout, 
                             QHBoxLayout, QLabel, QPushButton, QGraphicsDropShadowEffect, QWidget)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QFont

from qfluentwidgets import (
    FluentIcon as FIF, TransparentToolButton, LineEdit, ComboBox,
    TitleLabel, BodyLabel, CaptionLabel, SmoothScrollArea, Slider,
    SwitchButton, PushButton, isDarkTheme
)

import ui1 as ui
from ui1 import APP_STATE, THEMES, MODEL_CONFIGS, API_DATA, API_KEYS, save_appdata, global_signals


class SettingsGroupCard(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(8)
        self.wrappers = []
        self.setStyleSheet("SettingsGroupCard { background: transparent; border: none; }")
        global_signals.dark_mode_toggled.connect(self.update_style)

    def update_style(self):
        for wrapper in self.wrappers:
            if isDarkTheme():
                wrapper.setStyleSheet("QFrame#settingCardWrapper { background-color: rgba(255, 255, 255, 0.05); border: 1px solid rgba(255, 255, 255, 0.08); border-radius: 8px; }")
            else:
                wrapper.setStyleSheet("QFrame#settingCardWrapper { background-color: rgba(0, 0, 0, 0.04); border: 1px solid rgba(0, 0, 0, 0.08); border-radius: 8px; }")

    def add_row(self, widget, add_separator=True):
        wrapper = QFrame(self)
        wrapper.setObjectName("settingCardWrapper")
        wrapper_layout = QVBoxLayout(wrapper)
        wrapper_layout.setContentsMargins(0, 0, 0, 0)
        wrapper_layout.addWidget(widget)
        self.wrappers.append(wrapper)
        self.layout.addWidget(wrapper)
        self.update_style()


class SettingRowWidget(QWidget):
    def __init__(self, icon, title, desc, control_widget, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(12)
        
        icon_btn = TransparentToolButton(icon, self)
        icon_btn.setEnabled(False)
        
        text_layout = QVBoxLayout()
        text_layout.setSpacing(2)
        self.title_lbl = BodyLabel(title, self)
        self.desc_lbl = CaptionLabel(desc, self)
        
        text_layout.addWidget(self.title_lbl)
        text_layout.addWidget(self.desc_lbl)

        layout.addWidget(icon_btn)
        layout.addLayout(text_layout, stretch=1)
        layout.addWidget(control_widget)

        global_signals.dark_mode_toggled.connect(self.update_text_color)
        self.update_text_color()

    def update_text_color(self):
        if isDarkTheme():
            self.title_lbl.setStyleSheet("font-weight: bold; color: white;")
            self.desc_lbl.setStyleSheet("color: #d0d0d0;")
        else:
            self.title_lbl.setStyleSheet("font-weight: normal; color: black;")
            self.desc_lbl.setStyleSheet("color: #555555;")


class ModelThemeExpandRow(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.is_expanded = False
        self.content_labels = []
        self.init_ui()
        global_signals.theme_updated.connect(self.refresh_themes)
        global_signals.dark_mode_toggled.connect(self.update_text_color)
        self.update_text_color()

    def init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(16, 14, 16, 14)
        main_layout.setSpacing(12)

        header_layout = QHBoxLayout()
        header_layout.setContentsMargins(0, 0, 0, 0)
        
        icon_btn = TransparentToolButton(FIF.PALETTE, self)
        icon_btn.setEnabled(False)
        
        text_layout = QVBoxLayout()
        text_layout.setSpacing(2)
        self.title_lbl = BodyLabel("Model Accent Colors", self)
        self.desc_lbl = CaptionLabel("Manage color highlights for individual AI model buttons", self)
        text_layout.addWidget(self.title_lbl)
        text_layout.addWidget(self.desc_lbl)

        header_layout.addWidget(icon_btn)
        header_layout.addSpacing(10)
        header_layout.addLayout(text_layout, stretch=1)

        main_layout.addLayout(header_layout)

        self.content_widget = QWidget(self)
        self.content_widget.setStyleSheet("background: transparent;")
        self.content_layout = QVBoxLayout(self.content_widget)
        self.content_layout.setContentsMargins(0, 8, 0, 0)
        self.content_layout.setSpacing(10)

        self.model_combos = {}
        for model in ("Fast", "Flash", "Complex"):
            row_item = QWidget(self.content_widget)
            row_layout = QHBoxLayout(row_item)
            row_layout.setContentsMargins(0, 0, 0, 0)

            lbl = BodyLabel(model, row_item)
            self.content_labels.append(lbl)
            
            combo = ComboBox(row_item)
            for theme in THEMES.keys():
                combo.addItem(theme)
            combo.setCurrentText(APP_STATE.get("model_themes", {}).get(model, ""))
            combo.setFixedWidth(160)
            combo.currentTextChanged.connect(lambda text, m=model: self.on_theme_changed(m, text))
            
            row_layout.addWidget(lbl)
            row_layout.addStretch(1)
            row_layout.addWidget(combo)

            self.content_layout.addWidget(row_item)
            self.model_combos[model] = combo

        self.content_widget.hide()
        main_layout.addWidget(self.content_widget)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.mousePressEvent = lambda e: self.toggle_expansion()

    def update_text_color(self):
        if isDarkTheme():
            self.title_lbl.setStyleSheet("font-weight: bold; color: white;")
            self.desc_lbl.setStyleSheet("color: #d0d0d0;")
            for lbl in self.content_labels: lbl.setStyleSheet("color: white;")
        else:
            self.title_lbl.setStyleSheet("font-weight: normal; color: black;")
            self.desc_lbl.setStyleSheet("color: #555555;")
            for lbl in self.content_labels: lbl.setStyleSheet("color: black;")

    def toggle_expansion(self):
        self.is_expanded = not self.is_expanded
        if self.is_expanded:
            self.content_widget.show()
        else:
            self.content_widget.hide()

    def on_theme_changed(self, model, theme_name):
        if "model_themes" not in APP_STATE:
            APP_STATE["model_themes"] = {}
        APP_STATE["model_themes"][model] = theme_name
        save_appdata()
        logging.info(f"Model theme updated: {model} -> {theme_name}")
        global_signals.theme_updated.emit()

    def refresh_themes(self):
        for model, combo in self.model_combos.items():
            combo.blockSignals(True)
            combo.setCurrentText(APP_STATE.get("model_themes", {}).get(model, ""))
            combo.blockSignals(False)


class EditableApiKeyWidget(QWidget):
    def __init__(self, key_text="", on_save_callback=None, parent=None):
        super().__init__(parent)
        self.on_save_callback = on_save_callback

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        self.line_edit = LineEdit(self)
        self.line_edit.setText(key_text or "")
        self.line_edit.setEchoMode(LineEdit.EchoMode.Password)
        self.line_edit.setEnabled(False)
        self.line_edit.setFixedWidth(240)
        self.line_edit.returnPressed.connect(self.lock_and_save)

        self.edit_btn = TransparentToolButton(FIF.EDIT, self)
        self.edit_btn.setFixedSize(32, 32)
        self.edit_btn.setToolTip("Edit API key")
        self.edit_btn.clicked.connect(self.toggle_edit)

        layout.addWidget(self.line_edit)
        layout.addWidget(self.edit_btn)

    def toggle_edit(self):
        if not self.line_edit.isEnabled():
            self.line_edit.setEnabled(True)
            self.line_edit.setEchoMode(LineEdit.EchoMode.Normal)
            self.line_edit.setFocus()
        else:
            self.lock_and_save()

    def lock_and_save(self):
        self.line_edit.setEchoMode(LineEdit.EchoMode.Password)
        self.line_edit.setEnabled(False)
        if self.on_save_callback:
            self.on_save_callback()

    def text(self):
        return self.line_edit.text().strip()

    def setText(self, text):
        self.line_edit.setText(text or "")


class ApiRoleConfigRow(QWidget):
    """Fast/Flash/Complex row: provider + provider-filtered model only."""

    def __init__(self, role_name, settings_page, parent=None):
        super().__init__(parent)
        self.role_name = role_name
        self.settings_page = settings_page
        self._model_items = []

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        self.role_label = BodyLabel(role_name, self)
        self.role_label.setFixedWidth(70)

        self.provider_combo = ComboBox(self)
        self.provider_combo.setFixedWidth(150)
        self.model_combo = ComboBox(self)
        self.model_combo.setFixedWidth(300)

        profile = MODEL_CONFIGS.get(role_name, {}) if isinstance(MODEL_CONFIGS.get(role_name, {}), dict) else {}
        self.provider_combo.addItems(self.settings_page.provider_names())
        current_provider = profile.get("provider", "")
        if current_provider:
            self.provider_combo.setCurrentText(current_provider)

        self._reload_models(profile.get("model", ""))
        self.provider_combo.currentTextChanged.connect(self._provider_changed)
        self.model_combo.currentTextChanged.connect(self._model_changed)

        layout.addWidget(self.role_label)
        layout.addWidget(self.provider_combo)
        layout.addWidget(self.model_combo)
        layout.addStretch(1)

    def _provider_changed(self, provider):
        self._reload_models("")
        self._save()

    def _reload_models(self, preferred=""):
        provider = self.provider_combo.currentText().strip()
        self._model_items = []
        self.model_combo.blockSignals(True)
        self.model_combo.clear()
        for item in self.settings_page.models_for_provider(provider):
            item = dict(item)
            model_id = str(item.get("model_id", item.get("model_name", ""))).strip()
            if not model_id:
                continue
            self._model_items.append(item)
            display = f"* {model_id}" if item.get("default") else model_id
            # QFluentWidgets ComboBox expects plain text here; don't pass dict userData.
            self.model_combo.addItem(display)
        self.model_combo.blockSignals(False)

        wanted = str(preferred or "").strip()
        selected_index = -1
        for i, item in enumerate(self._model_items):
            model_id = str(item.get("model_id", item.get("model_name", ""))).strip()
            if model_id == wanted:
                selected_index = i
                break
        if selected_index < 0 and self._model_items:
            default_index = next((i for i, x in enumerate(self._model_items) if x.get("default")), 0)
            selected_index = default_index
        if selected_index >= 0:
            self.model_combo.setCurrentIndex(selected_index)

    def _selected_model_id(self):
        idx = self.model_combo.currentIndex()
        if 0 <= idx < len(self._model_items):
            return str(self._model_items[idx].get("model_id", self._model_items[idx].get("model_name", ""))).strip()
        return ""

    def _model_changed(self, _):
        self._save()

    def _save(self):
        MODEL_CONFIGS[self.role_name] = {
            "provider": self.provider_combo.currentText().strip(),
            "model": self._selected_model_id(),
        }
        self.settings_page.persist_model_configs(reason=f"{self.role_name} model configuration updated")

    def refresh(self):
        profile = MODEL_CONFIGS.get(self.role_name, {})
        self.provider_combo.blockSignals(True)
        self.provider_combo.setCurrentText(profile.get("provider", ""))
        self.provider_combo.blockSignals(False)
        self._reload_models(profile.get("model", ""))


class CatalogModelRow(QWidget):
    """Single editable model catalog row with provider + model ID + edit/delete."""

    def __init__(self, settings_page, provider, model_id, default=False, parent=None, is_new=False):
        super().__init__(parent)
        self.settings_page = settings_page
        self.original_provider = str(provider or "Groq AI")
        self.original_model_id = str(model_id or "")
        self.default_entry = bool(default)
        self.is_new = bool(is_new)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        self.default_lbl = BodyLabel("*" if self.default_entry else "", self)
        self.default_lbl.setFixedWidth(18)

        self.provider_combo = ComboBox(self)
        self.provider_combo.setFixedWidth(145)
        self.provider_combo.addItems(self.settings_page.catalog_provider_names())
        self.provider_combo.setCurrentText(self.original_provider)
        self.provider_combo.setEnabled(self.is_new)

        self.id_edit = LineEdit(self)
        self.id_edit.setText(self.original_model_id)
        self.id_edit.setPlaceholderText("Model ID")
        self.id_edit.setEnabled(self.is_new)

        self.action_btn = TransparentToolButton(
            FIF.EDIT if not self.is_new else FIF.SAVE, self
        )
        self.action_btn.setFixedSize(32, 32)
        self.action_btn.setToolTip("Save model" if self.is_new else "Edit model")
        self.action_btn.clicked.connect(self._toggle_or_save)

        self.delete_btn = TransparentToolButton(FIF.DELETE, self)
        self.delete_btn.setFixedSize(32, 32)
        self.delete_btn.setToolTip("Delete model")
        self.delete_btn.clicked.connect(self._delete)

        layout.addWidget(self.default_lbl)
        layout.addWidget(self.provider_combo)
        layout.addWidget(self.id_edit, 1)
        layout.addWidget(self.action_btn)
        layout.addWidget(self.delete_btn)

        if self.is_new:
            self.id_edit.setFocus()

    def _toggle_or_save(self):
        if not self.id_edit.isEnabled():
            self.id_edit.setEnabled(True)
            self.provider_combo.setEnabled(True)
            self.action_btn.setIcon(getattr(FIF, "SAVE", FIF.EDIT))
            self.action_btn.setToolTip("Save model")
            self.id_edit.setFocus()
            return

        provider = self.provider_combo.currentText().strip() or "Groq AI"
        model_id = self.id_edit.text().strip()
        if not model_id:
            global_signals.show_toast.emit("Model ID cannot be empty.", "error")
            self.id_edit.setFocus()
            return

        if self.is_new:
            saved = self.settings_page.add_catalog_model(provider, model_id)
        else:
            saved = self.settings_page.update_catalog_model(
                self.original_provider,
                self.original_model_id,
                provider,
                model_id,
            )

        if saved:
            self.settings_page.api_catalog_widget.refresh()

    def _delete(self):
        if self.is_new:
            self.deleteLater()
            return

        if self.settings_page.delete_catalog_model(
            self.original_provider,
            self.original_model_id,
        ):
            self.settings_page.api_catalog_widget.refresh()


class ApiCatalogEditor(QWidget):
    """Model catalog editor rendered inside the separate API Model Catalog row."""

    def __init__(self, settings_page, parent=None):
        super().__init__(parent)
        self.settings_page = settings_page

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 4, 0, 0)
        root.setSpacing(8)

        title = BodyLabel("API Model Catalog", self)
        desc = CaptionLabel(
            "Manage model IDs and providers used by Fast, Flash, and Complex.",
            self,
        )
        root.addWidget(title)
        root.addWidget(desc)

        self.list_layout = QVBoxLayout()
        self.list_layout.setSpacing(5)
        root.addLayout(self.list_layout)

        self.add_btn = PushButton("Add new model catalog", self)
        self.add_btn.setIcon(getattr(FIF, "ADD", FIF.EDIT))
        self.add_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.add_btn.clicked.connect(self.add_model)
        root.addWidget(self.add_btn)

        self.refresh()

    def refresh(self):
        while self.list_layout.count():
            item = self.list_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

        entries = []
        seen = set()

        # Role entries are displayed once, regardless of which role contains them.
        for role in ("Fast", "Flash", "Complex"):
            for item in self.settings_page.models_for_role(role):
                provider = str(item.get("provider", "")).strip()
                model_id = str(
                    item.get("model_id", item.get("model_name", ""))
                ).strip()
                if not provider or not model_id:
                    continue
                key = (provider, model_id)
                if key not in seen:
                    seen.add(key)
                    entries.append(
                        (provider, model_id, bool(item.get("default", False)))
                    )

        # Provider-wide custom entries are also catalog rows.
        for provider, items in (API_DATA.get("models") or {}).items():
            for item in items or []:
                model_id = str(
                    item.get("model_id", item.get("model_name", ""))
                ).strip()
                if not model_id:
                    continue
                key = (provider, model_id)
                if key not in seen:
                    seen.add(key)
                    entries.append(
                        (provider, model_id, bool(item.get("default", False)))
                    )

        for provider, model_id, default in entries:
            self.list_layout.addWidget(
                CatalogModelRow(
                    self.settings_page,
                    provider,
                    model_id,
                    default=default,
                    parent=self,
                )
            )

    def add_model(self):
        # New rows start with Groq AI. Provider remains editable only until Save.
        self.list_layout.addWidget(
            CatalogModelRow(
                self.settings_page,
                "Groq AI",
                "",
                default=False,
                parent=self,
                is_new=True,
            )
        )

class ApiProviderKeysRow(QWidget):
    """Provider credentials editor backed by the OS keyring, never appdata.json."""

    def __init__(self, settings_page, parent=None):
        super().__init__(parent)
        self.settings_page = settings_page
        self.widgets = {}
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        for provider in ("Groq AI", "OpenRouter", "Ollama Cloud"):
            box = QVBoxLayout()
            box.setSpacing(3)
            label = CaptionLabel(provider, self)
            editor = EditableApiKeyWidget(
                ui.API_KEYS.get(provider, ""),
                on_save_callback=lambda p=provider: self._save_provider_key(p),
                parent=self,
            )
            editor.line_edit.setFixedWidth(190)
            box.addWidget(label)
            box.addWidget(editor)
            holder = QWidget(self)
            holder.setLayout(box)
            layout.addWidget(holder, 1)
            self.widgets[provider] = editor

    def _save_provider_key(self, provider):
        value = self.widgets[provider].text()
        self.settings_page.persist_provider_key(provider, value)

    def refresh(self):
        for provider, widget in self.widgets.items():
            widget.setText(ui.API_KEYS.get(provider, ""))


class ApiConfigExpandRow(QWidget):
    """Expandable API credentials + model-role configuration row."""

    def __init__(self, settings_page=None, parent=None):
        super().__init__(parent)
        self.settings_page = settings_page
        self.is_expanded = False
        self.content_labels = []
        self.role_rows = {}
        self.init_ui()
        global_signals.dark_mode_toggled.connect(self.update_text_color)
        self.update_text_color()

    def init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(16, 14, 16, 14)
        main_layout.setSpacing(12)

        header_layout = QHBoxLayout()
        icon_btn = TransparentToolButton(FIF.IOT, self)
        icon_btn.setEnabled(False)

        text_layout = QVBoxLayout()
        self.title_lbl = BodyLabel("API Configurations", self)
        self.desc_lbl = CaptionLabel(
            "Set provider API keys and choose the active model for Fast, Flash, and Complex.",
            self,
        )
        text_layout.addWidget(self.title_lbl)
        text_layout.addWidget(self.desc_lbl)

        header_layout.addWidget(icon_btn)
        header_layout.addSpacing(10)
        header_layout.addLayout(text_layout, stretch=1)
        main_layout.addLayout(header_layout)

        self.content_widget = QWidget(self)
        self.content_widget.setStyleSheet("background: transparent;")
        self.content_layout = QVBoxLayout(self.content_widget)
        self.content_layout.setContentsMargins(0, 8, 0, 0)
        self.content_layout.setSpacing(10)

        keys_title = BodyLabel("Provider API Keys", self.content_widget)
        self.content_layout.addWidget(keys_title)

        self.provider_keys_row = ApiProviderKeysRow(
            self.settings_page,
            self.content_widget,
        )
        self.content_layout.addWidget(self.provider_keys_row)

        sep = QFrame(self.content_widget)
        sep.setFrameShape(QFrame.Shape.HLine)
        self.content_layout.addWidget(sep)

        for role in ("Fast", "Flash", "Complex"):
            row = ApiRoleConfigRow(
                role,
                self.settings_page,
                self.content_widget,
            )
            self.role_rows[role] = row
            self.content_labels.append(row.role_label)
            self.content_layout.addWidget(row)

        self.content_widget.hide()
        main_layout.addWidget(self.content_widget)

        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.mousePressEvent = lambda e: self.toggle_expansion()

    def update_text_color(self):
        if isDarkTheme():
            self.title_lbl.setStyleSheet("font-weight: bold; color: white;")
            self.desc_lbl.setStyleSheet("color: #d0d0d0;")
            for label in self.content_labels:
                label.setStyleSheet("color: white;")
        else:
            self.title_lbl.setStyleSheet("font-weight: normal; color: black;")
            self.desc_lbl.setStyleSheet("color: #555555;")
            for label in self.content_labels:
                label.setStyleSheet("color: black;")

    def toggle_expansion(self):
        self.is_expanded = not self.is_expanded
        self.content_widget.setVisible(self.is_expanded)

    def refresh(self):
        self.provider_keys_row.refresh()
        for row in self.role_rows.values():
            row.refresh()


class ApiCatalogExpandRow(QWidget):
    """Separate expandable API Model Catalog settings row."""

    def __init__(self, settings_page=None, parent=None):
        super().__init__(parent)
        self.settings_page = settings_page
        self.is_expanded = False
        self.init_ui()
        global_signals.dark_mode_toggled.connect(self.update_text_color)
        self.update_text_color()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(10)

        header = QHBoxLayout()
        icon_btn = TransparentToolButton(FIF.DOCUMENT, self)
        icon_btn.setEnabled(False)

        text = QVBoxLayout()
        self.title_lbl = BodyLabel("API Model Catalog", self)
        self.desc_lbl = CaptionLabel(
            "View and manage the complete provider/model catalog.",
            self,
        )
        text.addWidget(self.title_lbl)
        text.addWidget(self.desc_lbl)

        header.addWidget(icon_btn)
        header.addSpacing(10)
        header.addLayout(text, stretch=1)
        layout.addLayout(header)

        self.content_widget = QWidget(self)
        self.content_widget.setStyleSheet("background: transparent;")
        content_layout = QVBoxLayout(self.content_widget)
        content_layout.setContentsMargins(0, 8, 0, 0)
        content_layout.setSpacing(8)

        self.catalog = ApiCatalogEditor(
            self.settings_page,
            self.content_widget,
        )
        content_layout.addWidget(self.catalog)

        self.content_widget.hide()
        layout.addWidget(self.content_widget)

        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.mousePressEvent = lambda e: self.toggle_expansion()

    def update_text_color(self):
        if isDarkTheme():
            self.title_lbl.setStyleSheet("font-weight: bold; color: white;")
            self.desc_lbl.setStyleSheet("color: #d0d0d0;")
        else:
            self.title_lbl.setStyleSheet("font-weight: normal; color: black;")
            self.desc_lbl.setStyleSheet("color: #555555;")

    def toggle_expansion(self):
        self.is_expanded = not self.is_expanded
        self.content_widget.setVisible(self.is_expanded)

    def refresh(self):
        self.catalog.refresh()


class ConfirmationDialog(QDialog):
    def __init__(self, parent=None, title="Confirmation", message="", confirm_text="Clear all data"):
        super().__init__(parent)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setModal(True)
        self.result_value = False

        # Outer Card Container (Void-Ai Card styling)
        self.container = QWidget(self)
        self.container.setObjectName("CardContainer")

        # Subtle Drop Shadow Effect
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(25)
        shadow.setColor(QColor(0, 0, 0, 160))
        shadow.setOffset(0, 8)
        self.container.setGraphicsEffect(shadow)

        # Outer Layout
        dialog_layout = QVBoxLayout(self)
        dialog_layout.setContentsMargins(10, 10, 10, 10)
        dialog_layout.addWidget(self.container)

        # Inner Content Layout
        layout = QVBoxLayout(self.container)
        layout.setContentsMargins(22, 20, 22, 22)
        layout.setSpacing(12)

        # Title Label
        title_label = QLabel(title)
        title_label.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
        title_label.setObjectName("TitleLabel")

        # Message Body
        msg_label = QLabel(message)
        msg_label.setFont(QFont("Segoe UI", 9))
        msg_label.setWordWrap(True)
        msg_label.setObjectName("MsgLabel")

        # Action Buttons Layout
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(10)

        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.cancel_btn.setObjectName("CancelBtn")
        self.cancel_btn.clicked.connect(self.reject)

        self.confirm_btn = QPushButton(confirm_text)
        self.confirm_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.confirm_btn.setObjectName("ConfirmBtn")
        self.confirm_btn.clicked.connect(self.accept_action)

        btn_layout.addStretch()
        btn_layout.addWidget(self.cancel_btn)
        btn_layout.addWidget(self.confirm_btn)

        layout.addWidget(title_label)
        layout.addWidget(msg_label)
        layout.addSpacing(8)
        layout.addLayout(btn_layout)

        # Void-Ai Specific Color Palette
        self.setStyleSheet("""
            QWidget#CardContainer {
                background-color: #202020;
                border: 1px solid #383346;
                border-radius: 12px;
            }
            QLabel#TitleLabel {
                color: #FFFFFF;
            }
            QLabel#MsgLabel {
                color: #A39EB2;
                line-height: 1.4;
            }
            QPushButton#CancelBtn {
                background-color: #2F2A3A;
                color: #D6D1E3;
                border: 1px solid #433D52;
                border-radius: 8px;
                padding: 7px 16px;
                font-size: 13px;
                font-weight: 500;
            }
            QPushButton#CancelBtn:hover {
                background-color: #3B3449;
                color: #FFFFFF;
            }
            QPushButton#ConfirmBtn {
                background-color: #A855F7;
                color: #FFFFFF;
                border: none;
                border-radius: 8px;
                padding: 7px 18px;
                font-size: 13px;
                font-weight: 600;
            }
            QPushButton#ConfirmBtn:hover {
                background-color: #9333EA;
            }
            QPushButton#ConfirmBtn:pressed {
                background-color: #7E22CE;
            }
        """)

        self.setFixedWidth(420)

    def accept_action(self):
        self.result_value = True
        self.accept()

    @staticmethod
    def show_dialog(
        parent=None,
        title="Void-Ai: Confirmation",
        message="Are you sure you want to proceed?",
        confirm_text="Clear all data",
    ) -> bool:
        dialog = ConfirmationDialog(
            parent=parent,
            title=title,
            message=message,
            confirm_text=confirm_text,
        )
        
        dialog.adjustSize()
        if parent:
            parent_center = parent.rect().center()
            global_center = parent.mapToGlobal(parent_center)
            
            dialog_geo = dialog.frameGeometry()
            dialog_geo.moveCenter(global_center)
            dialog.move(dialog_geo.topLeft())

        return bool(dialog.exec() and dialog.result_value)


class SettingsPage(SmoothScrollArea):
    def __init__(self, main_window=None, parent=None):
        super().__init__(parent)
        self.main_window = main_window
        self.setObjectName("settingsPage")
        self.setWidgetResizable(True)
        self.setStyleSheet("QScrollArea { border: none; background: transparent; }")

        self.container = QWidget()
        self.container.setStyleSheet("background: transparent;")
        self.layout = QVBoxLayout(self.container)
        self.layout.setContentsMargins(40, 40, 40, 40)
        self.layout.setSpacing(16)

        header_layout = QHBoxLayout()
        self.title_lbl = TitleLabel("Settings", self)
        header_layout.addWidget(self.title_lbl)
        header_layout.addStretch(1)
        self.layout.addLayout(header_layout)

        app_section_lbl = BodyLabel("Appearance & Themes", self)
        app_section_lbl.setStyleSheet(
            "font-weight: bold; font-size: 15px; color: #888888; margin-top: 10px;"
        )
        self.layout.addWidget(app_section_lbl)

        self.appearance_card = SettingsGroupCard(self.container)

        self.slider = Slider(Qt.Orientation.Horizontal, self)
        self.slider.setRange(10, 28)
        self.slider.setValue(APP_STATE.get("font_size", 14))
        self.slider.setFixedWidth(128)
        self.slider.sliderReleased.connect(self.on_font_slider_released)

        font_row = SettingRowWidget(
            FIF.FONT_SIZE,
            "Chat Text Size",
            "Adjust the size of the messages in the chat.",
            self.slider,
            self.container,
        )
        self.appearance_card.add_row(font_row, add_separator=False)

        self.model_theme_widget = ModelThemeExpandRow(self.container)
        self.appearance_card.add_row(self.model_theme_widget, add_separator=True)
        self.layout.addWidget(self.appearance_card)

        behav_section_lbl = BodyLabel("System Behavior", self)
        behav_section_lbl.setStyleSheet(
            "font-weight: bold; font-size: 15px; color: #888888; margin-top: 15px;"
        )
        self.layout.addWidget(behav_section_lbl)

        self.behavior_card = SettingsGroupCard(self.container)

        self.bg_switch = SwitchButton(self)
        self.bg_switch.setChecked(APP_STATE.get("bg_animation", True))
        self.bg_switch.checkedChanged.connect(self.on_bg_anim_changed)

        bg_row = SettingRowWidget(
            FIF.BRUSH,
            "Background Aura Animation",
            "Enable or disable the ambient background pulse.",
            self.bg_switch,
            self.container,
        )
        self.behavior_card.add_row(bg_row, add_separator=False)

        self.auto_recent_switch = SwitchButton(self)
        self.auto_recent_switch.setChecked(
            APP_STATE.get("auto_load_recent_chat", True)
        )
        self.auto_recent_switch.checkedChanged.connect(
            self.on_auto_recent_changed
        )

        auto_recent_row = SettingRowWidget(
            FIF.VIEW,
            "Auto load recently used chat",
            "Open the most recently used chat automatically when Void-Ai starts.",
            self.auto_recent_switch,
            self.container,
        )
        self.behavior_card.add_row(auto_recent_row, add_separator=True)

        self.stream_switch = SwitchButton(self)
        self.stream_switch.setChecked(APP_STATE.get("stream_text", True))
        self.stream_switch.checkedChanged.connect(self.on_stream_changed)

        stream_row = SettingRowWidget(
            FIF.SPEED_HIGH,
            "Real-time Text Streaming",
            "Show AI responses character-by-character.",
            self.stream_switch,
            self.container,
        )
        self.behavior_card.add_row(stream_row, add_separator=True)
        self.layout.addWidget(self.behavior_card)

        api_section_lbl = BodyLabel("API Configuration", self)
        api_section_lbl.setStyleSheet(
            "font-weight: bold; font-size: 15px; color: #888888; margin-top: 15px;"
        )
        self.layout.addWidget(api_section_lbl)

        self.api_card = SettingsGroupCard(self.container)
        self.api_config_widget = ApiConfigExpandRow(
            settings_page=self,
            parent=self.container
        )
        self.api_card.add_row(self.api_config_widget, add_separator=False)

        self.api_catalog_card = SettingsGroupCard(self.container)
        self.api_catalog_widget = ApiCatalogExpandRow(
            settings_page=self,
            parent=self.container
        )
        self.api_catalog_card.add_row(self.api_catalog_widget, add_separator=False)

        self.layout.addWidget(self.api_card)
        self.layout.addWidget(self.api_catalog_card)

        data_section_lbl = BodyLabel("Data Management", self)
        data_section_lbl.setStyleSheet(
            "font-weight: bold; font-size: 15px; color: #888888; margin-top: 15px;"
        )
        self.layout.addWidget(data_section_lbl)

        self.data_card = SettingsGroupCard(self.container)

        self.restore_settings_btn = PushButton(
            "Restore",
            self,
            getattr(FIF, "SYNC", FIF.EDIT),
        )
        self.restore_settings_btn.setFixedWidth(170)
        self.restore_settings_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.restore_settings_btn.clicked.connect(self.confirm_restore_all_settings)
        if self.main_window and hasattr(self.main_window, "data_restore_state_changed"):
            self.main_window.data_restore_state_changed.connect(
                self._set_restore_button_busy
            )

        restore_settings_row = SettingRowWidget(
            getattr(FIF, "SYNC", FIF.EDIT),
            "Restore all settings",
            "Restore app settings and the API model catalog to defaults. Saved API keys remain in the secure keyring.",
            self.restore_settings_btn,
            self.container,
        )
        self.data_card.add_row(restore_settings_row, add_separator=True)

        self.clear_data_btn = PushButton("Reset", self, FIF.DELETE)
        self.clear_data_btn.setFixedWidth(170)
        self.clear_data_btn.clicked.connect(self.confirm_clear_all_data)
        if self.main_window and hasattr(self.main_window, "data_clear_state_changed"):
            self.main_window.data_clear_state_changed.connect(self._set_clear_button_busy)

        clear_data_row = SettingRowWidget(
            FIF.DELETE,
            "Reset",
            "Delete chats, messages, memories and database files. Settings stay untouched.",
            self.clear_data_btn,
            self.container,
        )
        self.data_card.add_row(clear_data_row, add_separator=False)
        self.layout.addWidget(self.data_card)

        # About
        # Kept at the bottom so Settings remains structurally unchanged.
        about_section_lbl = BodyLabel("About", self)
        about_section_lbl.setStyleSheet(
            "font-weight: bold; font-size: 15px; color: #888888; margin-top: 15px;"
        )
        self.layout.addWidget(about_section_lbl)

        self.about_card = SettingsGroupCard(self.container)
        self.about_btn = PushButton("About", self, FIF.INFO)
        self.about_btn.setFixedWidth(140)
        self.about_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.about_btn.clicked.connect(self._open_about)

        about_row = SettingRowWidget(
            FIF.INFO,
            "About Void-Ai",
            "View application information, features, and author details.",
            self.about_btn,
            self.container,
        )
        self.about_card.add_row(about_row, add_separator=True)

        self.help_btn = PushButton("Help", self, FIF.INFO)
        self.help_btn.setFixedWidth(140)
        self.help_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.help_btn.clicked.connect(self._open_help)

        help_row = SettingRowWidget(
            FIF.HELP,
            "Help",
            "Open the Void-Ai setup, chat, customization, and troubleshooting guide.",
            self.help_btn,
            self.container,
        )
        self.about_card.add_row(help_row, add_separator=True)

        self.dev_switch = SwitchButton(self)
        self.dev_switch.setChecked(
            APP_STATE.get("developer_options", False)
        )
        self.dev_switch.checkedChanged.connect(
            self.on_developer_options_changed
        )

        developer_row = SettingRowWidget(
            FIF.CODE,
            "Developer Options",
            "Show developer tools such as System Logs in the navigation panel.",
            self.dev_switch,
            self.container,
        )
        self.about_card.add_row(developer_row, add_separator=False)
        self.layout.addWidget(self.about_card)

        self.layout.addStretch(1)
        self.setWidget(self.container)

        global_signals.dark_mode_toggled.connect(self.update_theme_text)
        global_signals.settings_restored.connect(
            lambda _ok: self.refresh_after_restore()
        )
        self.update_theme_text()

    def _open_about(self):
        if self.main_window and hasattr(self.main_window, "open_about"):
            self.main_window.open_about()

    def _open_help(self):
        if self.main_window and hasattr(self.main_window, "open_help"):
            self.main_window.open_help()

    def confirm_restore_all_settings(self):
        if not self.main_window:
            return

        is_confirmed = ConfirmationDialog.show_dialog(
            parent=self,
            title="Void-Ai: Restore all settings?",
            message=(
                "Are you sure you want to restore all settings?\n\n"
                "This restores appdata.json and apidata.json from defaults_data.py. "
                "Your saved API keys in the secure keyring will stay unchanged.")
            ,
            confirm_text="Restore defaults",
        )
        if not is_confirmed:
            return

        self.restore_settings_btn.setEnabled(False)
        self.main_window.restore_all_settings()

    def _set_restore_button_busy(self, busy):
        if hasattr(self, "restore_settings_btn"):
            self.restore_settings_btn.setEnabled(not busy)

    def refresh_after_restore(self):
        self.slider.blockSignals(True)
        self.slider.setValue(int(APP_STATE.get("font_size", 13)))
        self.slider.blockSignals(False)

        self.bg_switch.blockSignals(True)
        self.bg_switch.setChecked(bool(APP_STATE.get("bg_animation", True)))
        self.bg_switch.blockSignals(False)

        self.stream_switch.blockSignals(True)
        self.stream_switch.setChecked(bool(APP_STATE.get("stream_text", True)))
        self.stream_switch.blockSignals(False)

        self.auto_recent_switch.blockSignals(True)
        self.auto_recent_switch.setChecked(bool(APP_STATE.get("auto_load_recent_chat", True)))
        self.auto_recent_switch.blockSignals(False)

        self.dev_switch.blockSignals(True)
        self.dev_switch.setChecked(bool(APP_STATE.get("developer_options", False)))
        self.dev_switch.blockSignals(False)

        self.api_config_widget.refresh()
        self.api_catalog_widget.refresh()

    def confirm_clear_all_data(self):
        if not self.main_window:
            return

        is_confirmed = ConfirmationDialog.show_dialog(
            parent=self,
            title="Void-AI: Warning!",
            message="Are you sure you want to clear all data?\n\nChats, messages, memories, and database files will be deleted."
        )


        if not is_confirmed:
            return

        self.clear_data_btn.setEnabled(False)
        self.main_window.clear_all_data()

    def _set_clear_button_busy(self, busy):
        if hasattr(self, "clear_data_btn"):
            self.clear_data_btn.setEnabled(not busy)

    def update_theme_text(self):
        self.title_lbl.setStyleSheet("font-size: 28px; color: white;")

    def on_font_slider_released(self):
        val = self.slider.value()
        APP_STATE["font_size"] = val
        save_appdata()
        logging.info(f"Font size updated to: {val}")
        global_signals.font_size_updated.emit(val)

    def on_bg_anim_changed(self, is_checked):
        APP_STATE["bg_animation"] = is_checked
        save_appdata()
        logging.info(f"Background aura animation toggled: {is_checked}")
        global_signals.bg_animation_toggled.emit(is_checked)

    def on_stream_changed(self, is_checked):
        APP_STATE["stream_text"] = is_checked
        save_appdata()
        logging.info(f"Real-time text streaming toggled: {is_checked}")

    def on_auto_recent_changed(self, is_checked):
        APP_STATE["auto_load_recent_chat"] = bool(is_checked)
        save_appdata()
        logging.info(
            "Auto load recently used chat toggled: %s",
            bool(is_checked),
        )

    def on_developer_options_changed(self, is_checked):
        enabled = bool(is_checked)
        APP_STATE["developer_options"] = enabled
        save_appdata()
        logging.info("Developer Options toggled: %s", enabled)

        if self.main_window and hasattr(
            self.main_window, "set_developer_options_enabled"
        ):
            self.main_window.set_developer_options_enabled(enabled)

    def provider_names(self):
        return list((API_DATA.get("providers") or {}).keys())

    def models_for_provider(self, provider):
        result = []
        for role in ("Fast", "Flash", "Complex"):
            for item in (API_DATA.get("roles", {}).get(role, []) or []):
                item = dict(item)
                if item.get("provider") == provider:
                    result.append(item)
        # Provider-wide custom entries may be stored here too.
        for item in (API_DATA.get("models", {}).get(provider, []) or []):
            item = dict(item)
            item["provider"] = provider
            result.append(item)

        dedupe = []
        seen = set()
        for item in result:
            model_id = item.get("model_id", item.get("model_name", ""))
            key = (provider, model_id)
            if model_id and key not in seen:
                seen.add(key)
                dedupe.append(item)
        return dedupe

    def models_for_role(self, role):
        return list(API_DATA.get("roles", {}).get(role, []) or [])

    def persist_model_configs(self, reason="Model configuration updated"):
        ui.MODEL_CONFIGS = MODEL_CONFIGS
        ui.API_KEYS = API_KEYS
        save_appdata()
        logging.info(reason)
        global_signals.show_toast.emit("Model configuration saved.", "success")
        try:
            if getattr(ui, "void_engine", None) is not None:
                ui.void_engine.update_configuration(MODEL_CONFIGS, API_DATA, API_KEYS)
        except Exception as exc:
            logging.error("Live AI configuration update failed: %s", exc)
        global_signals.theme_updated.emit()

    def persist_provider_key(self, provider, value):
        provider = str(provider or "").strip()
        value = str(value or "").strip()
        if not provider:
            return False

        try:
            ok = ui.set_api_key(provider, value)
        except Exception as exc:
            logging.exception("Secure API key update failed for %s", provider)
            ok = False

        if not ok:
            global_signals.show_toast.emit(
                "Could not save the API key securely. Make sure the 'keyring' package is installed.",
                "error",
            )
            return False

        # No API-key fields are written to appdata.json.
        logging.info("Provider API key updated securely: %s", provider)
        global_signals.show_toast.emit("Provider API key saved securely.", "success")
        return True

    def persist_provider_keys(self, reason="Provider API keys updated"):
        # Backward-compatible bulk refresh hook; credentials are already in keyring.
        for provider, widget in self.widgets.items():
            self.persist_provider_key(provider, widget.text())
        logging.info(reason)

    def catalog_provider_names(self):
        return ["Groq AI", "OpenRouter", "Ollama Cloud"]

    def update_catalog_model(self, old_provider, old_id, new_provider, new_id):
        old_provider = str(old_provider or "").strip()
        old_id = str(old_id or "").strip()
        new_provider = str(new_provider or "").strip()
        new_id = str(new_id or "").strip()

        if not old_provider or not old_id or not new_provider or not new_id:
            return False

        # Prevent duplicates in the destination provider.
        if (old_provider, old_id) != (new_provider, new_id):
            for role in ("Fast", "Flash", "Complex"):
                for item in API_DATA.setdefault("roles", {}).setdefault(role, []):
                    iid = str(item.get("model_id", item.get("model_name", ""))).strip()
                    if item.get("provider") == new_provider and iid == new_id:
                        global_signals.show_toast.emit("That model already exists.", "error")
                        return False

        changed = False

        # Update role catalog entries.
        for role in ("Fast", "Flash", "Complex"):
            for item in API_DATA.setdefault("roles", {}).setdefault(role, []):
                iid = str(item.get("model_id", item.get("model_name", ""))).strip()
                if item.get("provider") == old_provider and iid == old_id:
                    item["provider"] = new_provider
                    item["model_id"] = new_id
                    item["model_name"] = new_id
                    changed = True

        # Update provider-wide custom entries.
        old_items = API_DATA.setdefault("models", {}).setdefault(old_provider, [])
        moved = []
        kept = []
        for item in old_items:
            iid = str(item.get("model_id", item.get("model_name", ""))).strip()
            if iid == old_id:
                item["provider"] = new_provider
                item["model_id"] = new_id
                item["model_name"] = new_id
                moved.append(item)
                changed = True
            else:
                kept.append(item)
        API_DATA["models"][old_provider] = kept
        if moved:
            API_DATA.setdefault("models", {}).setdefault(new_provider, []).extend(moved)

        # Keep active role selections pointing at the edited catalog entry.
        for profile in MODEL_CONFIGS.values():
            if isinstance(profile, dict):
                if profile.get("provider") == old_provider and profile.get("model") == old_id:
                    profile["provider"] = new_provider
                    profile["model"] = new_id
                    changed = True

        return self.save_api_catalog() if changed else False

    def delete_catalog_model(self, provider, model_id):
        provider = str(provider or "").strip()
        model_id = str(model_id or "").strip()

        if not provider or not model_id:
            return False

        removed = False

        # Delete from role catalog.
        for role in ("Fast", "Flash", "Complex"):
            items = API_DATA.setdefault("roles", {}).setdefault(role, [])
            kept = []
            for item in items:
                iid = str(item.get("model_id", item.get("model_name", ""))).strip()
                if item.get("provider") == provider and iid == model_id:
                    removed = True
                else:
                    kept.append(item)
            API_DATA["roles"][role] = kept

        # Delete provider-wide catalog rows.
        items = API_DATA.setdefault("models", {}).setdefault(provider, [])
        kept = []
        for item in items:
            iid = str(item.get("model_id", item.get("model_name", ""))).strip()
            if iid == model_id:
                removed = True
            else:
                kept.append(item)
        API_DATA["models"][provider] = kept

        # Delete matching active model configuration from appdata.json.
        for role in ("Fast", "Flash", "Complex"):
            profile = MODEL_CONFIGS.get(role)
            if isinstance(profile, dict):
                if profile.get("provider") == provider and profile.get("model") == model_id:
                    MODEL_CONFIGS.pop(role, None)
                    removed = True

        if not removed:
            return False

        save_appdata()
        try:
            if getattr(ui, "void_engine", None) is not None:
                ui.void_engine.update_configuration(MODEL_CONFIGS, API_DATA, API_KEYS)
        except Exception as exc:
            logging.error("Live config refresh after catalog delete failed: %s", exc)

        return self.save_api_catalog()

    def add_catalog_model(self, provider, model_id):
        provider = str(provider or "Groq AI").strip() or "Groq AI"
        model_id = str(model_id or "").strip()
        if not model_id:
            return False

        API_DATA.setdefault("models", {}).setdefault(provider, [])

        for role in ("Fast", "Flash", "Complex"):
            for item in API_DATA.setdefault("roles", {}).setdefault(role, []):
                iid = str(item.get("model_id", item.get("model_name", ""))).strip()
                if item.get("provider") == provider and iid == model_id:
                    global_signals.show_toast.emit("That model already exists.", "error")
                    return False

        for item in API_DATA["models"][provider]:
            iid = str(item.get("model_id", item.get("model_name", ""))).strip()
            if iid == model_id:
                global_signals.show_toast.emit("That model already exists.", "error")
                return False

        API_DATA["models"][provider].append({
            "model_id": model_id,
            "model_name": model_id,
            "provider": provider,
            "default": False,
        })
        return self.save_api_catalog()

    def save_api_catalog(self):
        try:
            with open(ui.APIDATA_PATH, "w", encoding="utf-8") as f:
                import json
                json.dump(API_DATA, f, indent=2, ensure_ascii=False)
            logging.info("apidata.json updated.")
            global_signals.show_toast.emit("API model catalog saved.", "success")
            try:
                if getattr(ui, "void_engine", None) is not None:
                    ui.void_engine.update_configuration(
                        MODEL_CONFIGS,
                        API_DATA,
                    )
            except Exception as exc:
                logging.error("Live provider catalog update failed: %s", exc)
            if hasattr(self, "api_config_widget"):
                self.api_config_widget.refresh()
            if hasattr(self, "api_catalog_widget"):
                self.api_catalog_widget.refresh()
            return True
        except Exception as exc:
            logging.error("Failed to save apidata.json: %s", exc)
            global_signals.show_toast.emit("Could not save API catalog.", "error")
