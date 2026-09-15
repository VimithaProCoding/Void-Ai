import os
import sys
import logging

from PyQt6.QtCore import QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QIcon, QGuiApplication
from PyQt6.QtWidgets import QApplication

from qfluentwidgets import (
    FluentWindow, NavigationItemPosition, FluentIcon as FIF,
    setTheme, Theme, setThemeColor
)

import ui1 as ui
from ui1 import (
    BASE_DIR, APP_STATE, save_appdata, global_signals,
    LoadingOverlay, NewChatNavigationWidget, RestoreSettingsThread, apply_restored_settings_to_runtime,
    InitEngineThread, AppToast
)
from ui2 import(
    ChatSidebarWidget, 
    VoidPage,
    ChatLoadThread,
    ChatDeleteThread,
    DataPurgeThread,
    StartupPromptsThread
    )

from settings_ui import SettingsPage
from logs_ui import LogsPage
from about_ui import AboutPage
from help_ui import HelpPage


class MainWindow(FluentWindow):
    data_clear_state_changed = pyqtSignal(bool)
    data_restore_state_changed = pyqtSignal(bool)

    def __init__(self):
        super().__init__()

        setTheme(Theme.DARK)
        setThemeColor(QColor("#9D4EDD"))

        self.setWindowTitle("Void-Ai")
        self.resize(1250, 850)
        self.center_window()

        icon_path = os.path.join(BASE_DIR, "icon.ico")
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))

        # + New Chat directly below the Fluent menu button.
        self.new_chat_nav = NewChatNavigationWidget(self)
        self.navigationInterface.addWidget(
            "newChatAction",
            self.new_chat_nav,
            onClick=self.start_new_chat,
            position=NavigationItemPosition.TOP,
            tooltip="New Chat",
        )
        #navigaer panel size
        self.navigationInterface.setExpandWidth(270)
        # Chat mode indicators distinguish manual selections from system auto-detection.

        self.void_page = VoidPage(self)
        self.addSubInterface(self.void_page, FIF.ROBOT, "Void Core")

        # Expanded-only multi-chat section.
        self.chat_sidebar = ChatSidebarWidget(self, self)
        self.navigationInterface.addWidget(
            "multiChatList",
            self.chat_sidebar,
            position=NavigationItemPosition.SCROLL,
        )

        self.logs_page = LogsPage(self)
        self.logs_nav_item = self.addSubInterface(
            self.logs_page,
            FIF.DOCUMENT,
            "System Logs",
            position=NavigationItemPosition.BOTTOM,
        )
        self.logs_nav_item.setVisible(
            bool(APP_STATE.get("developer_options", False))
        )

        # Keep Help directly above Settings, with Settings as the bottom-most
        # permanent navigation item. About remains a real registered interface,
        # but its navigation button is shown only while the About page is active.
        self.help_page = HelpPage(main_window=self, parent=self)
        self.help_nav_item = self.addSubInterface(
            self.help_page,
            FIF.HELP,
            "Help",
            position=NavigationItemPosition.BOTTOM,
        )

        self.settings_page = SettingsPage(main_window=self, parent=self)
        self.settings_nav_item = self.addSubInterface(
            self.settings_page,
            FIF.SETTING,
            "System Settings",
            position=NavigationItemPosition.BOTTOM,
        )

        # About stays registered in the stacked widget for reliable page routing,
        # but its navigation item is hidden until About is actually selected.
        self.about_page = AboutPage(self)
        self.about_nav_item = self.addSubInterface(
            self.about_page,
            FIF.INFO,
            "About",
            position=NavigationItemPosition.BOTTOM,
        )
        self.about_nav_item.setVisible(False)

        if hasattr(self.navigationInterface, "displayModeChanged"):
            self.navigationInterface.displayModeChanged.connect(
                self.on_navigation_mode_changed
            )
        self.stackedWidget.currentChanged.connect(self.on_tab_changed)

        self.app_toast = AppToast(self)
        global_signals.show_toast.connect(self.app_toast.show_message)

        self.loading_overlay = LoadingOverlay(self, void_page=self.void_page)
        self.loading_overlay.resize(self.size())
        self.chat_delete_threads = set()
        self.data_purge_thread = None
        self.restore_settings_thread = None
        self._clear_poll_timer = None
        self._restore_poll_timer = None

        logging.info("Starting Void-Ai Application...")

        self.init_thread = InitEngineThread()
        self.init_thread.finished_signal.connect(self.on_engine_ready)
        self.init_thread.start()

    def on_engine_ready(self):
        if self.loading_overlay:
            self.loading_overlay.fade_out_and_close()

        # Startup always opens on a blank/new chat.
        self.void_page.new_chat()
        self.refresh_chat_navigation()
        self.navigationInterface.setCurrentItem(
            self.void_page.objectName()
        )
        if hasattr(self, "about_nav_item"):
            self.about_nav_item.setVisible(False)

        # Background Thread එක හරහා API call එක ගෙන Dynamic Prompts update කරයි
        self.startup_thread = StartupPromptsThread(self)
        self.startup_thread.prompts_ready.connect(
            self.void_page.update_startup_prompts
        )
        self.startup_thread.start()

    def center_window(self):
        screen = QGuiApplication.primaryScreen()
        if screen:
            geometry = screen.availableGeometry()
            self.move(
                (geometry.width() - self.width()) // 2,
                (geometry.height() - self.height()) // 2
            )

    def set_chat_title(self, title):
        clean = (title or "").strip()
        self.setWindowTitle(
            "Void-Ai"
            if not clean or clean == "Void-Ai"
            else f"Void-Ai — {clean}"
        )

    def refresh_chat_navigation(self):
        try:
            # list_chats() now carries both the resolved prompt mode and its
            # source (user/auto). The sidebar uses that source so only manual
            # selections receive the colored mode dot.
            chats = ui.void_engine.list_chats()
            # list_chats() includes mode_source; the sidebar renders the dot
            # only when that source is explicitly "user".
            self.chat_sidebar.refresh(
                chats,
                self.void_page.current_chat_id
            )
            self.chat_sidebar.select_chat(
                self.void_page.current_chat_id
            )
        except Exception as exc:
            logging.warning(
                "Could not refresh multi-chat navigation: %s",
                exc
            )

    def start_new_chat(self):
        if self.void_page.worker is not None and self.void_page.worker.isRunning():
            global_signals.show_toast.emit(
                "Stop the current response before starting a new chat.",
                "error"
            )
            return

        self.stackedWidget.setCurrentWidget(self.void_page)

        self.navigationInterface.setCurrentItem(
            self.void_page.objectName()
        )
        self.void_page.new_chat()

    def open_chat(self, chat_id):
        if not chat_id:
            return
        
        self.stackedWidget.setCurrentWidget(self.void_page)
        self.navigationInterface.setCurrentItem(self.void_page.objectName())

        if chat_id == self.void_page.current_chat_id:
            # The same chat may be active while the user is viewing Settings
            # or Logs. Clicking that chat must still return to the chat UI.
            self.navigationInterface.setCurrentItem(self.void_page.objectName())
            return

        if self.void_page.worker is not None and self.void_page.worker.isRunning():
            global_signals.show_toast.emit(
                "Stop the current response before switching chats.",
                "error"
            )
            return

        self.navigationInterface.setCurrentItem(
            self.void_page.objectName()
        )
        self.show_loading_overlay()

        self.chat_load_thread = ChatLoadThread(chat_id, self)
        self.chat_load_thread.loaded.connect(self._finish_chat_load)
        self.chat_load_thread.error.connect(self._chat_load_error)
        self.chat_load_thread.finished.connect(
            self.chat_load_thread.deleteLater
        )
        self.chat_load_thread.start()

    def _finish_chat_load(self, chat_id, title, messages):
        self.void_page.populate_loaded_chat(
            chat_id,
            title,
            messages
        )
        self.refresh_chat_navigation()
        if self.loading_overlay:
            self.loading_overlay.fade_out_and_close()

    def _chat_load_error(self, message):
        logging.error("Chat loading failed: %s", message)
        global_signals.show_toast.emit(
            "Chat could not be loaded. Check Logs.",
            "error"
        )
        if self.loading_overlay:
            self.loading_overlay.fade_out_and_close()

    def rename_chat(self, chat_id, title):
        try:
            ui.void_engine.rename_chat(chat_id, title)
            if chat_id == self.void_page.current_chat_id:
                self.void_page.current_chat_title = title
                self.set_chat_title(title)
            self.refresh_chat_navigation()
        except Exception as exc:
            logging.error("Rename failed: %s", exc)
            global_signals.show_toast.emit(
                "Rename failed. Check Logs.",
                "error"
            )

    def pin_chat(self, chat_id, pinned):
        try:
            ui.void_engine.pin_chat(chat_id, pinned)
            self.refresh_chat_navigation()
        except Exception as exc:
            logging.error("Pin toggle failed: %s", exc)
            global_signals.show_toast.emit(
                "Pin update failed. Check Logs.",
                "error"
            )

    def delete_chat(self, chat_id, row=None):
        if not chat_id:
            return
        if self.data_purge_thread is not None and self.data_purge_thread.isRunning():
            return
        if self.void_page.worker is not None and self.void_page.worker.isRunning():
            global_signals.show_toast.emit(
                "Stop the current response before deleting this chat.",
                "error"
            )
            return

        is_current = chat_id == self.void_page.current_chat_id

        if row is not None and hasattr(row, "animate_delete"):
            row.animate_delete()

        # A deleted active chat immediately becomes a blank/new chat UI.
        # Navigation is refreshed only after the background filesystem delete.
        if is_current:
            self.void_page.new_chat(refresh_navigation=False, wait_for_title_worker=False)
            self.navigationInterface.setCurrentItem(self.void_page.objectName())

        thread = ChatDeleteThread(chat_id, self)
        self.chat_delete_threads.add(thread)
        thread.deleted.connect(
            lambda deleted_id, t=thread, active=is_current: self._chat_deleted(
                deleted_id, t, active
            )
        )
        thread.error.connect(
            lambda failed_id, message, t=thread: self._chat_delete_failed(
                failed_id, message, t, row
            )
        )
        thread.finished.connect(lambda t=thread: self._cleanup_chat_delete_thread(t))
        thread.start()

    def _chat_deleted(self, chat_id, thread, was_current):
        logging.info("Chat deleted from UI: %s", chat_id)

        if APP_STATE.get("last_chat_id") == chat_id:
            APP_STATE["last_chat_id"] = None
            save_appdata()

        self.refresh_chat_navigation()
        if was_current:
            self.set_chat_title("Void-Ai")
        global_signals.show_toast.emit("Chat deleted.", "success")

    def _chat_delete_failed(self, chat_id, message, thread, row=None):
        logging.error("Could not delete chat %s: %s", chat_id, message)
        if row is not None and hasattr(row, "restore_after_delete_failure"):
            row.restore_after_delete_failure()
        self.refresh_chat_navigation()
        global_signals.show_toast.emit("Chat delete failed. Check Logs.", "error")

    def _cleanup_chat_delete_thread(self, thread):
        self.chat_delete_threads.discard(thread)
        thread.deleteLater()

    def restore_all_settings(self):
        """Restore appdata.json + apidata.json using defaults_data.py without blocking the UI."""
        if self.restore_settings_thread is not None and self.restore_settings_thread.isRunning():
            return

        if self.data_purge_thread is not None and self.data_purge_thread.isRunning():
            global_signals.show_toast.emit(
                "Please wait for the current data operation to finish.",
                "error",
            )
            return

        if self.void_page.worker is not None and self.void_page.worker.isRunning():
            self.void_page._request_cancel()
            global_signals.show_toast.emit(
                "Stopping the active response before restoring settings...",
                "success",
            )
            self._wait_for_worker_before_restore()
            return

        self._begin_settings_restore()

    def _wait_for_worker_before_restore(self):
        if self.void_page.worker is not None and self.void_page.worker.isRunning():
            if self._restore_poll_timer is None:
                self._restore_poll_timer = QTimer(self)
                self._restore_poll_timer.setInterval(60)
                self._restore_poll_timer.timeout.connect(self._wait_for_worker_before_restore)
            self._restore_poll_timer.start()
            return

        if self._restore_poll_timer is not None:
            self._restore_poll_timer.stop()
        QTimer.singleShot(0, self._begin_settings_restore)

    def _begin_settings_restore(self):
        if self.restore_settings_thread is not None and self.restore_settings_thread.isRunning():
            return

        if self._restore_poll_timer is not None:
            self._restore_poll_timer.stop()

        self.data_restore_state_changed.emit(True)
        self.show_loading_overlay(
            "Restoring Void-Ai settings...",
            "Loading factory defaults and rebuilding the API configuration.",
        )

        self.restore_settings_thread = RestoreSettingsThread(self)
        self.restore_settings_thread.finished_signal.connect(
            self._finish_settings_restore
        )
        self.restore_settings_thread.finished.connect(
            self.restore_settings_thread.deleteLater
        )
        self.restore_settings_thread.start()

    def _finish_settings_restore(self, ok, message):
        self.restore_settings_thread = None
        self.data_restore_state_changed.emit(False)

        if not ok:
            logging.error("Settings restore failed: %s", message)
            if self.loading_overlay:
                self.loading_overlay.set_message(
                    "Settings restore failed.",
                    "No runtime settings were changed. Check Logs for details.",
                )
                QTimer.singleShot(1000, self.loading_overlay.fade_out_and_close)
            global_signals.show_toast.emit(
                "Settings restore failed. Check Logs.",
                "error",
            )
            return

        try:
            apply_restored_settings_to_runtime()

            if hasattr(self, "settings_page") and hasattr(
                self.settings_page, "refresh_after_restore"
            ):
                self.settings_page.refresh_after_restore()

            # Factory settings should also restore the navigation/developer state.
            self.set_chat_title("Void-Ai")
            self.set_developer_options_enabled(
                bool(APP_STATE.get("developer_options", False))
            )

            if self.loading_overlay:
                self.loading_overlay.set_message(
                    "Void-Ai is ready again.",
                    "All settings were restored from defaults_data.py.",
                )
                QTimer.singleShot(500, self.loading_overlay.fade_out_and_close)

            global_signals.show_toast.emit(
                "All settings restored successfully.",
                "success",
            )
        except Exception as exc:
            logging.exception("Runtime settings restore failed.")
            if self.loading_overlay:
                self.loading_overlay.set_message(
                    "Settings restore failed.",
                    "The files were restored, but the running app could not reload them. Check Logs.",
                )
                QTimer.singleShot(1000, self.loading_overlay.fade_out_and_close)
            global_signals.show_toast.emit(
                "Settings restore failed. Check Logs.",
                "error",
            )

    def clear_all_data(self):
        if self.data_purge_thread is not None and self.data_purge_thread.isRunning():
            return
        if self.void_page.worker is not None and self.void_page.worker.isRunning():
            self.void_page._request_cancel()
            global_signals.show_toast.emit(
                "Stopping the active response before clearing data...",
                "success"
            )
            self._wait_for_worker_before_purge()
            return

        self._begin_data_purge()

    def _wait_for_worker_before_purge(self):
        if self.void_page.worker is not None and self.void_page.worker.isRunning():
            if self._clear_poll_timer is None:
                self._clear_poll_timer = QTimer(self)
                self._clear_poll_timer.setInterval(60)
                self._clear_poll_timer.timeout.connect(self._wait_for_worker_before_purge)
            self._clear_poll_timer.start()
            return
        if self._clear_poll_timer is not None:
            self._clear_poll_timer.stop()
        QTimer.singleShot(0, self._begin_data_purge)

    def _begin_data_purge(self):
        if self.data_purge_thread is not None and self.data_purge_thread.isRunning():
            return

        if self._clear_poll_timer is not None:
            self._clear_poll_timer.stop()

        self.void_page.new_chat(refresh_navigation=False, wait_for_title_worker=False)

        # Purging all chat data invalidates any remembered startup chat.
        APP_STATE["last_chat_id"] = None
        save_appdata()

        self.navigationInterface.setCurrentItem(self.void_page.objectName())
        self.data_clear_state_changed.emit(True)
        self.show_loading_overlay(
            "Clearing Void-Ai data...",
            "Removing chats, messages, memories and database files. Settings will be preserved."
        )

        self.data_purge_thread = DataPurgeThread(self)
        self.data_purge_thread.finished_signal.connect(self._finish_data_purge)
        self.data_purge_thread.finished.connect(self.data_purge_thread.deleteLater)
        self.data_purge_thread.start()

    def _finish_data_purge(self, ok, message):
        thread = self.data_purge_thread
        self.data_clear_state_changed.emit(False)
        self.data_purge_thread = None
        self.void_page.new_chat(refresh_navigation=False)
        self.refresh_chat_navigation()
        self.navigationInterface.setCurrentItem(self.void_page.objectName())
        self.set_chat_title("Void-Ai")

        if self.loading_overlay:
            if ok:
                self.loading_overlay.set_message(
                    "Void-Ai is ready again.",
                    "All chats, messages and memories were cleared. appdata.json was preserved."
                )
            else:
                self.loading_overlay.set_message(
                    "Data clear failed.",
                    "Nothing was changed in appdata.json. Check Logs for the error."
                )
            QTimer.singleShot(450 if ok else 900, self.loading_overlay.fade_out_and_close)

        if ok:
            global_signals.show_toast.emit("All chat data cleared. Settings preserved.", "success")
        else:
            logging.error("Full data purge failed: %s", message)
            global_signals.show_toast.emit("Clear all data failed. Check Logs.", "error")

    def on_navigation_mode_changed(self, is_expanded=None):
        # Navigation panel එක Open (Expanded) ද Close (Compacted) ද යන්න අනුව Sidebar state එක update කරයි
        if hasattr(self.navigationInterface, "isExpanded"):
            expanded = self.navigationInterface.isExpanded()
            self.chat_sidebar.setCompacted(not expanded)
        self.chat_sidebar.updateGeometry()

    def _open_interface(self, page, nav_item=None, label="page"):
        """Select a FluentWindow interface through one safe navigation path."""
        if page is None:
            logging.error("%s is not initialized.", label)
            return False

        try:
            if nav_item is not None:
                nav_item.show()
                nav_item.setVisible(True)

            object_name = page.objectName()
            self.navigationInterface.setCurrentItem(object_name)
            self.stackedWidget.setCurrentWidget(page)
            return True
        except Exception as exc:
            logging.exception("Could not open %s: %s", label, exc)
            return False

    def open_settings(self):
        """Open System Settings immediately from Help or other surfaces."""
        self._open_interface(
            getattr(self, "settings_page", None),
            getattr(self, "settings_nav_item", None),
            "Settings",
        )

    def open_help(self):
        """Open Help from the home '?' button, Settings, or Help/About surfaces."""
        self._open_interface(
            getattr(self, "help_page", None),
            getattr(self, "help_nav_item", None),
            "Help",
        )

    def open_about(self):
        """Open About from Settings or the Help About card."""
        self._open_interface(
            getattr(self, "about_page", None),
            getattr(self, "about_nav_item", None),
            "About",
        )

    def on_tab_changed(self, index):
        current_widget = self.stackedWidget.widget(index)

        # About stays hidden from the sidebar except while its page is active.
        if hasattr(self, "about_nav_item"):
            self.about_nav_item.setVisible(current_widget is self.about_page)

        if current_widget == self.logs_page:
            if not APP_STATE.get("developer_options", False):
                self.navigationInterface.setCurrentItem(self.void_page.objectName())
                return
            self.logs_page.load_logs()

    def set_developer_options_enabled(self, enabled):
        """Show or hide developer-only navigation items immediately."""
        enabled = bool(enabled)

        if not hasattr(self, "logs_nav_item"):
            return

        try:
            if (
                not enabled
                and hasattr(self, "logs_page")
                and self.stackedWidget.currentWidget() == self.logs_page
            ):
                self.navigationInterface.setCurrentItem(
                    self.void_page.objectName()
                )
        except Exception:
            pass

        try:
            self.logs_nav_item.setVisible(enabled)
        except Exception:
            try:
                self.logs_nav_item.setHidden(not enabled)
            except Exception:
                pass

        logging.info(
            "Developer navigation %s.",
            "enabled" if enabled else "disabled",
        )

    def show_loading_overlay(self, title=None, subtitle=None):
        if self.loading_overlay:
            try:
                self.loading_overlay.anim_timer.stop()
                self.loading_overlay.deleteLater()
            except RuntimeError:
                pass

        self.loading_overlay = LoadingOverlay(
            self,
            void_page=self.void_page
        )
        self.loading_overlay.resize(self.size())
        if title is not None or subtitle is not None:
            self.loading_overlay.set_message(title, subtitle)
        self.loading_overlay.show()
        self.loading_overlay.raise_()
        QApplication.processEvents()

    def trigger_reinitialization(
        self,
        reinit_engine=False,
        chat_key=None,
        bg_key=None,
        model_profiles=None,
        api_catalog=None,
    ):
        self.show_loading_overlay()

        if reinit_engine:
            def start_init_thread():
                profiles = model_profiles
                catalog = api_catalog
                if profiles is None:
                    profiles = getattr(ui, "MODEL_CONFIGS", {})
                if catalog is None:
                    catalog = getattr(ui, "API_DATA", {})

                self.init_thread = InitEngineThread(
                    profiles,
                    catalog,
                )
                self.init_thread.finished_signal.connect(
                    self.on_engine_ready
                )
                self.init_thread.start()

            QTimer.singleShot(50, start_init_thread)
        else:
            QTimer.singleShot(
                700,
                self.loading_overlay.fade_out_and_close
            )

    def resizeEvent(self, event):
        super().resizeEvent(event)

        if hasattr(self, "loading_overlay") and self.loading_overlay:
            try:
                if self.loading_overlay.isVisible():
                    self.loading_overlay.resize(self.size())
            except RuntimeError:
                self.loading_overlay = None

        if hasattr(self, "app_toast") and self.app_toast:
            try:
                if self.app_toast.isVisible():
                    self.app_toast.move(
                        (self.width() - self.app_toast.width()) // 2,
                        30
                    )
            except RuntimeError:
                self.app_toast = None

    def on_engine_ready(self):
        if self.loading_overlay:
            self.loading_overlay.fade_out_and_close()

        self.set_developer_options_enabled(
            APP_STATE.get("developer_options", False)
        )

        # Restore the most recently used chat only when enabled.
        # Otherwise Void-Ai starts with a fresh chat.
        if APP_STATE.get("auto_load_recent_chat", True):
            recent_chat_id = APP_STATE.get("last_chat_id")

            if recent_chat_id:
                try:
                    available_chat_ids = {
                        chat.get("chat_id")
                        for chat in ui.void_engine.list_chats()
                        if chat.get("chat_id")
                    }
                except Exception as exc:
                    logging.warning(
                        "Could not inspect recent chats at startup: %s",
                        exc,
                    )
                    available_chat_ids = set()

                if recent_chat_id in available_chat_ids:
                    self.open_chat(recent_chat_id)
                    self.refresh_chat_navigation()
                    return

                # The remembered chat was deleted or is no longer available.
                APP_STATE["last_chat_id"] = None
                save_appdata()

        self.void_page.new_chat()
        self.refresh_chat_navigation()
        self.navigationInterface.setCurrentItem(
            self.void_page.objectName()
        )
#ara settings eka hadana, defults data eka hadanna, json wenuwata db ekak use karanna

if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
