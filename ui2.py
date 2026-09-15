from ui1 import *
from ui1 import _LegacyVoidPage, _system_prompt_for_mode

class ChatTitleButton(QPushButton):
    """Title button that paints the manual-mode dot inside itself."""

    def __init__(self, text="", parent=None):
        super().__init__(text, parent)
        self._mode_color = None
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.setMinimumWidth(0)

    def set_mode_indicator(self, color=None):
        self._mode_color = str(color).strip() if color else None
        self.update()

    def paintEvent(self, event):
        super().paintEvent(event)
        if not self._mode_color:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(QColor(self._mode_color)))
        painter.drawEllipse(7, max(0, (self.height() - 8) // 2), 8, 8)
        painter.end()


class ChatNavRow(QFrame):
    def __init__(self, chat, open_callback, menu_callback, parent=None):
        super().__init__(parent)
        self.chat = dict(chat)
        self.chat_id = self.chat["chat_id"]
        self.open_callback = open_callback
        self.menu_callback = menu_callback
        self.selected = False
        self._renaming = False
        self._deleting = False
        self._delete_anim = None
        self._delete_opacity_anim = None

        self.setFixedHeight(38)
        self.setObjectName("chatNavRow")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 2, 2, 2)
        layout.setSpacing(2)

        raw_title = self.chat.get("title") or "New Chat"
        display_title = self.format_title(raw_title)

        # IMPORTANT: the indicator is painted by the button itself. Do not add
        # a child QFrame/QLabel for the dot; that was the unreliable old logic.
        self.title_button = ChatTitleButton(display_title, self)
        self.title_button.setToolTip(raw_title)
        self.title_button.clicked.connect(lambda: self.open_callback(self.chat_id))

        self.menu_button = TransparentToolButton(FIF.MORE, self)
        self.menu_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.menu_button.setFixedWidth(30)
        self.menu_button.clicked.connect(lambda: self.menu_callback(self))

        self.rename_edit = QLineEdit(self)
        self.rename_edit.setText(raw_title)
        self.rename_edit.hide()
        self.rename_edit.returnPressed.connect(self._commit_rename)

        layout.addWidget(self.title_button, 1)
        layout.addWidget(self.rename_edit, 1)
        layout.addWidget(self.menu_button)
        self._update_mode_dot()
        self.update_style(False)


    @staticmethod
    def format_title(title, max_len=23):
        """අකුරු 23ට වැඩි Title අගට '...' එකතු කරන Helper Logic එක"""
        clean_title = (title or "New Chat").strip()
        if len(clean_title) > max_len:
            return clean_title[:max_len] + "..."
        return clean_title

    def _update_mode_dot(self):
        # Manual/user mode only. Auto-detected mode deliberately has no dot.
        mode = str(self.chat.get("mode") or "").strip()
        source = str(self.chat.get("mode_source") or "").strip().lower()
        color = PROMPT_MODE_COLORS.get(mode) if source == "user" else None
        self.title_button.set_mode_indicator(color)

    def update_chat(self, chat):
        self.chat = dict(chat)
        self.chat_id = self.chat["chat_id"]
        raw_title = self.chat.get("title") or "New Chat"
        display_title = self.format_title(raw_title)
        
        self.title_button.setText(display_title)
        self.title_button.setToolTip(raw_title)
        self.rename_edit.setText(raw_title)
        self._update_mode_dot()
        self.update_style(self.selected)

    def set_selected(self, selected):
        self.selected = bool(selected)
        self.update_style(self.selected)

    def start_rename(self):
        if self._renaming:
            return
        self._renaming = True
        self.title_button.hide()
        self.menu_button.hide()
        self.rename_edit.show()
        self.rename_edit.setFocus()
        self.rename_edit.selectAll()

    def _commit_rename(self):
        if not self._renaming:
            return
        self._renaming = False
        raw_title = self.rename_edit.text().strip() or self.chat.get("title") or "Untitled Chat"
        display_title = self.format_title(raw_title)
        
        self.title_button.setText(display_title)
        self.title_button.setToolTip(raw_title)
        self.title_button.show()
        self.menu_button.show()
        self.rename_edit.hide()
        self.menu_callback(self, action="rename", value=raw_title)

    def focusOutEvent(self, event):
        if self._renaming:
            self._commit_rename()
        super().focusOutEvent(event)




    def animate_delete(self):
        """Visually collapse this row while the filesystem delete runs."""
        if self._deleting:
            return
        self._deleting = True
        self.menu_button.setEnabled(False)
        self.title_button.setEnabled(False)
        self.rename_edit.setEnabled(False)

        effect = self.graphicsEffect()
        if not isinstance(effect, QGraphicsOpacityEffect):
            effect = QGraphicsOpacityEffect(self)
            self.setGraphicsEffect(effect)
        effect.setOpacity(1.0)

        self._delete_opacity_anim = QPropertyAnimation(effect, b"opacity", self)
        self._delete_opacity_anim.setDuration(220)
        self._delete_opacity_anim.setStartValue(1.0)
        self._delete_opacity_anim.setEndValue(0.0)
        self._delete_opacity_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._delete_opacity_anim.start()

        current_height = self.height() or 38
        self.setMinimumHeight(0)
        self.setMaximumHeight(current_height)
        self._delete_anim = QPropertyAnimation(self, b"maximumHeight", self)
        self._delete_anim.setDuration(240)
        self._delete_anim.setStartValue(current_height)
        self._delete_anim.setEndValue(0)
        self._delete_anim.setEasingCurve(QEasingCurve.Type.InCubic)
        self._delete_anim.finished.connect(self.hide)
        self._delete_anim.start()

    def restore_after_delete_failure(self):
        if not self._deleting:
            return
        self._deleting = False
        self.show()
        self.menu_button.setEnabled(True)
        self.title_button.setEnabled(True)
        self.rename_edit.setEnabled(True)
        self.setMinimumHeight(38)
        self.setMaximumHeight(38)
        effect = self.graphicsEffect()
        if isinstance(effect, QGraphicsOpacityEffect):
            effect.setOpacity(1.0)

    def update_style(self, selected):
        if selected:
            # Purple වෙනුවට Dark mode එකට ගැළපෙන අළු/සුදු hover effect එක
            bg = "rgba(255, 255, 255, 0.12)"
            border = "rgba(255, 255, 255, 0.2)"
        else:
            bg = "transparent"
            border = "transparent"

        self.setStyleSheet(f"""
            QFrame#chatNavRow {{
                background: {bg};
                border: 1px solid {border};
                border-radius: 7px;
            }}
            QFrame#chatNavRow:hover {{
                background: rgba(255, 255, 255, 0.08);
            }}
            QPushButton {{
                background: transparent;
                border: none;
                color: #FFFFFF; /* Pure White Titles */
                text-align: left;
                padding: 0 6px 0 22px;
                font-size: 14px; /* Title size එක ටිකක් ලොකු කළා */
            }}
            QLineEdit {{
                background: rgba(20, 20, 20, 0.95);
                color: white;
                border: 1px solid #555555;
                border-radius: 6px;
                padding: 4px 6px;
            }}
        """)

class ChatSidebarWidget(NavigationWidget):

    def __init__(self, main_window, parent=None):
        super().__init__(False, parent)
        self.main_window = main_window
        self.rows = {}
        self.compacted = True

        # Layout එක දිගටම යටටම Full Height එකෙන් Expand වෙන්න සකස් කිරීම
        self.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        self.setStyleSheet("background: transparent; border: none;")

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0) # margins 0 කළා
        outer.setSpacing(0)

        self.content = QWidget(self)
        self.content.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        self.content.setStyleSheet("background: transparent;")
        content_layout = QVBoxLayout(self.content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)

        # Smooth scrolling
        self.scroll = SmoothScrollArea(self.content)
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.scroll.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded
        )

        self.scroll.setStyleSheet("""
            QScrollArea {
                border: none;
                background: transparent;
            }
            QScrollBar:vertical {
                border: none;
                background: transparent;
                width: 5px;
                margin: 0px;
            }
            QScrollBar::handle:vertical {
                background: rgba(150, 150, 150, 0.35);
                min-height: 28px;
                border-radius: 2px;
            }
            QScrollBar::handle:vertical:hover {
                background: rgba(180, 180, 180, 0.6);
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0px;
                background: none;
            }
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
                background: none;
            }
        """)

        self.list_host = QWidget(self.scroll)
        self.list_host.setStyleSheet("background: transparent;")
        self.list_layout = QVBoxLayout(self.list_host)
        self.list_layout.setContentsMargins(0, 2, 4, 2)
        self.list_layout.setSpacing(2)
        self.scroll.setWidget(self.list_host)

        content_layout.addWidget(self.scroll)
        outer.addWidget(self.content)

        self._set_compacted_state(True)

    def setCompacted(self, isCompacted):
        try:
            super().setCompacted(isCompacted)
        except Exception:
            pass
        self._set_compacted_state(bool(isCompacted))
        if not isCompacted:
            try:
                self.refresh(
                    void_engine.list_chats(),
                    self.main_window.void_page.current_chat_id,
                )
            except Exception:
                pass

    def _set_compacted_state(self, compacted):
        self.compacted = compacted
        self.content.setVisible(not compacted)
        if compacted:
            self.setFixedHeight(0)
        else:
            self.setMinimumHeight(550)
            self.setMaximumHeight(16777215)
            # Parent එක ඇතුලේ Vertical Space එක සම්පූර්ණයෙන්ම ලබා ගැනීමට Expand Policy එක තහවුරු කිරීම
            self.setSizePolicy(
                QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
            )
            self.updateGeometry()

    def _clear_list(self):
        while self.list_layout.count():
            item = self.list_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self.rows.clear()

    def _add_section_label(self, text):
        label = QLabel(text, self.list_host)
        label.setStyleSheet(
            "color:#888888; font-size:10px; font-weight:700; "
            "letter-spacing:1.4px; padding:6px 5px 2px 5px;"
        )
        self.list_layout.addWidget(label)

    def refresh(self, chats, selected_chat_id=None):
        if self.compacted:
            return

        self._clear_list()
        pinned = [c for c in chats if c.get("pinned")]
        recent = [c for c in chats if not c.get("pinned")]

        if pinned:
            self._add_section_label("PINNED CHATS")
            for chat in pinned:
                self._add_row(chat, selected_chat_id)

        if recent:
            self._add_section_label("RECENT CHATS")
            for chat in recent:
                self._add_row(chat, selected_chat_id)

        if not pinned and not recent:
            empty = QLabel("No chats yet", self.list_host)
            empty.setStyleSheet(
                "color:#776A84; font-size:11px; padding:8px 5px;"
            )
            self.list_layout.addWidget(empty)

        self.list_layout.addStretch(1)

    def _add_row(self, chat, selected_chat_id):
        row = ChatNavRow(
            chat,
            open_callback=self.main_window.open_chat,
            menu_callback=self.show_row_menu,
            parent=self.list_host,
        )
        row.set_selected(chat.get("chat_id") == selected_chat_id)
        self.rows[chat.get("chat_id")] = row
        self.list_layout.addWidget(row)

    def show_row_menu(self, row, action=None, value=None):
        if action == "rename":
            self.main_window.rename_chat(row.chat_id, value)
            return

        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu {
                background: #1E1E1E;
                color: white;
                border: 1px solid #333333;
                padding: 4px;
            }
            QMenu::item {
                padding: 7px 24px 7px 10px;
                border-radius: 5px;
            }
            QMenu::item:selected {
                background: rgba(255, 255, 255, 0.1);
            }
        """)

        rename_action = menu.addAction("Rename")
        pin_action = menu.addAction(
            "Unpin" if row.chat.get("pinned") else "Pin"
        )
        rename_action.triggered.connect(row.start_rename)
        pin_action.triggered.connect(
            lambda: self.main_window.pin_chat(
                row.chat_id, not bool(row.chat.get("pinned"))
            )
        )

        menu.addSeparator()
        delete_action = menu.addAction("Delete")
        delete_action.triggered.connect(
            lambda: self.main_window.delete_chat(row.chat_id, row)
        )

        menu.exec(
            row.menu_button.mapToGlobal(row.menu_button.rect().bottomLeft())
        )

    def select_chat(self, chat_id):
        for cid, row in self.rows.items():
            row.set_selected(cid == chat_id)

class ChatLoadThread(QThread):
    loaded = pyqtSignal(str, str, object)
    error = pyqtSignal(str)

    def __init__(self, chat_id, parent=None):
        super().__init__(parent)
        self.chat_id = chat_id

    def run(self):
        try:
            chat, messages = void_engine.load_chat(self.chat_id)
            self.loaded.emit(
                self.chat_id,
                chat.get("title", "Chat"),
                messages,
            )
        except Exception as exc:
            self.error.emit(str(exc))


class ChatDeleteThread(QThread):
    """Delete one chat off the GUI thread so the sidebar never freezes."""
    deleted = pyqtSignal(str)
    error = pyqtSignal(str, str)

    def __init__(self, chat_id, parent=None):
        super().__init__(parent)
        self.chat_id = chat_id

    def run(self):
        try:
            void_engine.delete_chat(self.chat_id)
            self.deleted.emit(self.chat_id)
        except Exception as exc:
            logging.exception("Chat deletion failed for %s", self.chat_id)
            self.error.emit(self.chat_id, str(exc))


class DataPurgeThread(QThread):
    """Clear persistent chat/memory data without blocking the GUI."""
    finished_signal = pyqtSignal(bool, str)

    def run(self):
        try:
            ok = bool(void_engine.purge_all_data())
            self.finished_signal.emit(ok, "" if ok else "Core purge failed.")
        except Exception as exc:
            logging.exception("Full data purge thread failed")
            self.finished_signal.emit(False, str(exc))


class ChatTitleThread(QThread):
    title_ready = pyqtSignal(str, str, str)

    def __init__(self, chat_id, user_message, forced_mode=None, parent=None):
        super().__init__(parent)
        self.chat_id = chat_id
        self.user_message = user_message
        self.forced_mode = forced_mode if forced_mode in PROMPT_MODES else None

    def run(self):
        title = void_engine.fallback_title(self.user_message)
        mode = self.forced_mode or "None"
        try:
            result = void_engine.generate_chat_title_and_mode(self.user_message, forced_mode=self.forced_mode)
            if isinstance(result, dict):
                title = str(result.get("title") or title).strip()[:120] or title
                candidate = str(result.get("mode") or "Other").strip()
                mode = candidate if candidate in PROMPT_MODES else "None"
        except Exception:
            logging.exception("First-message title/mode generation failed.")
        if self.isInterruptionRequested():
            return
        self.title_ready.emit(self.chat_id, title, mode)


class StartupPromptsThread(QThread):
    prompts_ready = pyqtSignal(str, str)

    def __init__(self, parent=None):
        super().__init__(parent)

    def run(self):
        try:
            greeting, placeholder = void_engine.generate_startup_prompts()
            self.prompts_ready.emit(greeting, placeholder)
        except Exception as exc:
            logging.error("StartupPromptsThread execution error: %s", exc)
            self.prompts_ready.emit("How can I help?", "What's on your mind today?")

class VoidPage(_LegacyVoidPage):
    """Original Void-Ai page with persistent multi-chat behavior layered on top."""
    def __init__(self, parent=None):
        self.main_window = parent
        self.current_chat_id = None
        self.current_chat_title = "New Chat"
        self.title_worker = None
        self.intent_worker = None
        self._pending_model_config = None
        self._pending_turn_id = None
        self._pending_generation = 0
        self._pending_user_text = ""
        self.selected_prompt_mode = "None"
        self.locked_prompt_mode = False
        super().__init__(parent)

        # Dark-only: the existing brush/light-mode control is simply removed
        # from the visible UI without disturbing the original page geometry.
        if hasattr(self, "theme_btn"):
            self.theme_btn.hide()

        self.fetch_startup_prompts()

    def fetch_startup_prompts(self):
        self.startup_worker = StartupPromptsThread(self)
        self.startup_worker.prompts_ready.connect(self.update_startup_prompts)
        self.startup_worker.finished.connect(self.startup_worker.deleteLater)
        self.startup_worker.start()

    def new_chat(self, refresh_navigation=True, wait_for_title_worker=True):
        if self.worker is not None and self.worker.isRunning():
            return False

        self.is_first_interaction = True

        self.current_chat_id = None
        self.current_chat_title = "New Chat"
        self.last_user_text = ""
        self._cancel_requested = False
        self.selected_prompt_mode = "None"
        self.locked_prompt_mode = False
        if hasattr(self, "prompt_mode_badge"):
            self.prompt_mode_badge.hide()
            self.prompt_mode_badge.set_none(locked=False)

        # Starting a fresh chat intentionally clears the remembered startup chat.
        if APP_STATE.get("last_chat_id") is not None:
            APP_STATE["last_chat_id"] = None
            save_appdata()
        self._active_turn_id = None

        if self.intent_worker is not None:
            try:
                if self.intent_worker.isRunning():
                    self.intent_worker.requestInterruption()
                    if wait_for_title_worker:
                        self.intent_worker.wait(400)
            except RuntimeError:
                pass
            self.intent_worker = None
        self._pending_model_config = None
        self._pending_turn_id = None
        self._pending_generation = 0
        self._pending_user_text = ""

        if self.title_worker is not None:
            if isdeleted(self.title_worker):
                self.title_worker = None
            elif wait_for_title_worker:
                try:
                    if self.title_worker.isRunning():
                        self.title_worker.quit()
                        self.title_worker.wait()
                except RuntimeError:
                    pass
                finally:
                    self.title_worker = None
            else:
                # Do not block the GUI for an in-flight title request. Its
                # finished signal is guarded by _clear_title_worker(), and its
                # late result cannot update a different current chat.
                pass

        self._remove_dynamic_spacer()

        for bubble in list(self.chat_bubbles):
            self._remove_bubble(bubble)
        self.chat_bubbles.clear()

        self.current_ai_bubble = None
        self.current_user_bubble = None

        self.input_box.clear()
        self.input_box.setFixedHeight(self.input_box.min_height)

        self.void_core.set_mode("Idle")
        self.void_core.setFixedSize(272, 272)
        self.welcome_container.show()
        self.welcome_opacity.setOpacity(1.0)
        self.chat_scroll.hide()
        self.top_stretch.show()
        self.bottom_stretch.show()

        self.main_layout.setStretchFactor(self.top_stretch, 15)
        self.main_layout.setStretchFactor(self.bottom_stretch, 37)
        self.main_layout.setStretchFactor(self.chat_scroll, 0)

        if self.main_window and hasattr(self.main_window, "set_chat_title"):
            self.main_window.set_chat_title("Void-Ai")
        if refresh_navigation and self.main_window and hasattr(self.main_window, "refresh_chat_navigation"):
            self.main_window.refresh_chat_navigation()
        
        return True


    def _clear_title_worker(self):
        worker = self.sender()
        if worker is self.title_worker:
            self.title_worker = None

    def populate_loaded_chat(self, chat_id, title, messages):
        self.current_chat_id = chat_id
        self.current_chat_title = title or "Chat"
        try:
            saved_mode = void_engine.get_chat_mode(chat_id)
            mode_source = void_engine.get_chat_mode_source(chat_id)
        except Exception:
            logging.exception("Could not load saved chat mode.")
            saved_mode = None
            mode_source = "auto"
        # Auto-detected modes still lock the conversation's prompt behavior, but
        # intentionally leave the composer badge hidden. Only explicit user modes
        # get the visible/manual badge.
        self._lock_prompt_mode(
            saved_mode if saved_mode in PROMPT_MODES else "None",
            show_badge=(mode_source == "user"),
        )

        # Remember the most recently opened conversation for the next launch.
        APP_STATE["last_chat_id"] = chat_id
        save_appdata()

        self._remove_dynamic_spacer()

        for bubble in list(self.chat_bubbles):
            self._remove_bubble(bubble)
        self.chat_bubbles.clear()

        self.current_ai_bubble = None
        self.current_user_bubble = None
        self.last_user_text = ""

        self.trigger_awakening(animate=False)

        for message in messages:
            role = message.get("role")
            content = message.get("content", "")
            if role in ("user", "assistant"):
                self.add_chat_bubble(
                    content,
                    is_user=(role == "user"),
                    animate=False
                )

        QTimer.singleShot(80, self.scroll_to_bottom)
        QTimer.singleShot(250, self.scroll_to_bottom)
        QTimer.singleShot(500, self.scroll_to_bottom)

        if self.main_window and hasattr(self.main_window, "set_chat_title"):
            self.main_window.set_chat_title(self.current_chat_title)
        if self.main_window and hasattr(self.main_window, "refresh_chat_navigation"):
            self.main_window.refresh_chat_navigation()

    def load_chat_history(self):
        # Kept for compatibility with the previous entry point. Startup
        # intentionally begins on a fresh new chat.
        self.new_chat()

    def _rollback_current_message(self, restore_text=True, animate=True):
        turn_id = self._active_turn_id
        chat_id = self.current_chat_id

        if turn_id and chat_id:
            try:
                void_engine.rollback_turn(chat_id, turn_id)
            except Exception as exc:
                logging.error(
                    f"Failed to rollback cancelled turn {turn_id}: {exc}"
                )

        self._remove_dynamic_spacer()

        self._remove_bubble(self.current_ai_bubble)
        self._remove_bubble(self.current_user_bubble)

        self.current_ai_bubble = None
        self.current_user_bubble = None

        if restore_text and self.last_user_text:
            self.input_box.blockSignals(True)
            self.input_box.setPlainText(self.last_user_text)
            self.input_box.blockSignals(False)
            self.input_box.setFixedHeight(self.input_box.min_height)

        if not self.chat_bubbles:
            self._restore_initial_layout_if_empty()

    def process_message(self):
        if self.worker is not None and self.worker.isRunning():
            return
        if self.intent_worker is not None and self.intent_worker.isRunning():
            return

        text = self.input_box.toPlainText().strip()
        if not text:
            return

        self.last_user_text = text
        self._cancel_requested = False
        self._stream_generation += 1
        self._pending_generation = self._stream_generation
        self._pending_turn_id = uuid.uuid4().hex
        self._pending_user_text = text

        if self.current_chat_id is None:
            initial_title = void_engine.fallback_title(text)
            chat = void_engine.create_chat(initial_title)
            self.current_chat_id = chat["chat_id"]
            self.current_chat_title = chat.get("title", initial_title)

            # Persist an explicitly selected mode BEFORE the new chat is
            # refreshed into the navigator. This makes the first sidebar row
            # appear with its dot immediately, instead of adding the dot only
            # after the title/mode worker finishes. Auto mode is intentionally
            # left unset here; it must never create a manual-mode indicator.
            if self.selected_prompt_mode in PROMPT_MODES:
                try:
                    void_engine.set_chat_mode(
                        self.current_chat_id,
                        self.selected_prompt_mode,
                        source="user",
                    )
                except Exception:
                    logging.exception("Could not persist user-selected mode for new chat.")

            APP_STATE["last_chat_id"] = self.current_chat_id
            save_appdata()

        self.input_box.clear()
        self.input_box.setFixedHeight(self.input_box.min_height)
        if self.is_first_interaction:
            self.trigger_awakening(animate=True)

        self._set_streaming_ui(True)
        self.void_core.set_mode("Thinking")
        self._remove_dynamic_spacer()

        self.current_user_bubble = self.add_chat_bubble(text, is_user=True)
        self.current_ai_bubble = None
        viewport_height = self.chat_scroll.viewport().height()
        if not hasattr(self, "bottom_spacer") or self.bottom_spacer is None:
            self.bottom_spacer = QWidget()
        self.bottom_spacer.setFixedHeight(viewport_height + 72)
        self.chat_layout.addWidget(self.bottom_spacer)
        QTimer.singleShot(20, lambda b=self.current_user_bubble: self.scroll_to_user_message(b))

        selected_model = self.model_combo.currentText()
        self._pending_model_config = copy.deepcopy(MODEL_CONFIGS.get(selected_model, {}))
        forced_mode = self.selected_prompt_mode if self.selected_prompt_mode in PROMPT_MODES else None

        if self.locked_prompt_mode:
            self._start_pending_ai(self.selected_prompt_mode if self.selected_prompt_mode in PROMPT_MODES else "None")
            if self.main_window and hasattr(self.main_window, "refresh_chat_navigation"):
                self.main_window.refresh_chat_navigation()
            return

        # One lightweight API call determines the title and mode together for the first message.
        self.intent_worker = ChatTitleThread(
            self.current_chat_id,
            text,
            forced_mode=forced_mode,
            parent=self,
        )
        self.intent_worker.title_ready.connect(self.on_chat_title_ready)
        self.intent_worker.finished.connect(self._clear_intent_worker)
        self.intent_worker.finished.connect(self.intent_worker.deleteLater)
        self.intent_worker.start()

        if self.main_window and hasattr(self.main_window, "refresh_chat_navigation"):
            self.main_window.refresh_chat_navigation()
        if self.main_window and hasattr(self.main_window, "set_chat_title"):
            self.main_window.set_chat_title(self.current_chat_title)

    def _start_pending_ai(self, resolved_mode):
        if self._cancel_requested or not self._pending_user_text or not self._pending_turn_id:
            return
        worker = AIEngineThread(
            void_engine,
            self._pending_user_text,
            self._pending_model_config or {},
            self.current_chat_id,
            stream=APP_STATE.get("stream_text", True),
            turn_id=self._pending_turn_id,
            system_prompt=_system_prompt_for_mode(resolved_mode),
            parent=self,
        )
        worker._generation = self._pending_generation
        self.worker = worker
        self._active_turn_id = self._pending_turn_id
        worker.chunk_received.connect(self.on_chunk_received)
        worker.error_signal.connect(self.on_error)
        worker.finished_signal.connect(self.on_stream_finished)
        worker.start()

    def _clear_intent_worker(self):
        worker = self.sender()
        if worker is self.intent_worker:
            self.intent_worker = None

    def on_chat_title_ready(self, chat_id, title, mode):
        if chat_id != self.current_chat_id or self._cancel_requested:
            if chat_id == self.current_chat_id and self._cancel_requested:
                self._rollback_current_message(restore_text=True)
            return

        self.current_chat_title = title or void_engine.fallback_title(self._pending_user_text)
        resolved_mode = mode if mode in PROMPT_MODES else "None"
        # `selected_prompt_mode` is non-empty only when the user explicitly chose
        # a card/mode before sending the first message. Otherwise the classifier's
        # result is auto and must never render as a manual UI badge.
        mode_source = "user" if self.selected_prompt_mode in PROMPT_MODES else "auto"
        try:
            existing_mode = void_engine.get_chat_mode(chat_id)
            if existing_mode in PROMPT_MODES or existing_mode == "None":
                resolved_mode = existing_mode
                existing_source = void_engine.get_chat_mode_source(chat_id)
                mode_source = existing_source if existing_source in {"user", "auto"} else mode_source
            else:
                void_engine.set_chat_mode(chat_id, resolved_mode, source=mode_source)
        except Exception:
            logging.exception("Could not persist first-message chat mode.")

        self._lock_prompt_mode(resolved_mode, show_badge=(mode_source == "user"))
        try:
            void_engine.rename_chat(chat_id, self.current_chat_title)
        except Exception:
            logging.exception("Could not persist generated chat title.")

        if self.main_window and hasattr(self.main_window, "set_chat_title"):
            self.main_window.set_chat_title(self.current_chat_title)
        if self.main_window and hasattr(self.main_window, "refresh_chat_navigation"):
            self.main_window.refresh_chat_navigation()

        if not self._pending_user_text or not self._pending_turn_id:
            self._set_streaming_ui(False)
            return
        self._start_pending_ai(resolved_mode)

    def on_error(self, error_msg):
        logging.error(f"AI Streaming Failed: {error_msg}")
        global_signals.show_toast.emit(
            "AI Connection Failed: Check Logs!",
            "error"
        )
        self._rollback_current_message(restore_text=True)
        self._cancel_requested = False
        self.send_btn.set_cancelling(False)
        self._set_streaming_ui(False)
        self.input_box.setFocus()
        self.void_core.set_mode("Idle")
        self.worker = None
        self._active_turn_id = None

    def on_stream_finished(self):
        worker = self.sender()
        cancelled = self._cancel_requested or (
            worker is not None and getattr(worker, "was_cancelled", False)
        )

        if cancelled:
            self._rollback_current_message(restore_text=True)
        else:
            if self.current_ai_bubble:
                self.current_ai_bubble.finalize()
            self._remove_dynamic_spacer()

        self._cancel_requested = False
        self._set_streaming_ui(False)
        self.input_box.setFocus()
        self.void_core.set_mode("Idle")

        if worker is self.worker:
            self.worker = None
        self._active_turn_id = None

        if self.main_window and hasattr(self.main_window, "refresh_chat_navigation"):
            self.main_window.refresh_chat_navigation()

    def update_startup_prompts(self, greeting, placeholder):
        if hasattr(self, 'ask_label') and self.ask_label:
            self.ask_label.setText(greeting)
            self.ask_label.update()
        if hasattr(self, 'input_box') and self.input_box:
            self.input_box.setPlaceholderText(placeholder)