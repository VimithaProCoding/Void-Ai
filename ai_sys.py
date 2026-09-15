import os
import json
import uuid
import secrets
import string
import sqlite3
import threading
import logging
import time
import shutil
import copy
from contextlib import contextmanager
from datetime import datetime, timezone
import re
import urllib.error
import urllib.request
from urllib.parse import urljoin

try:
    from openai import OpenAI
except Exception:
    OpenAI = None

try:
    from groq import Groq as GroqClient
except Exception:
    GroqClient = None

import chromadb
from chromadb.utils import embedding_functions
from PyQt6.QtCore import QThread, pyqtSignal


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MEMORY_ROOT = os.path.join(BASE_DIR, "memory_db")
CHAT_INDEX_DB = os.path.join(MEMORY_ROOT, "chats.sqlite3")
LEGACY_STATE_PATH = os.path.join(BASE_DIR, "memory_state.json")

logging.basicConfig(
    filename=os.path.join(BASE_DIR, "logdata.log"),
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)


class AIEngineThread(QThread):
    """Qt worker that keeps Groq streaming off the GUI thread."""

    chunk_received = pyqtSignal(str)
    finished_signal = pyqtSignal()
    error_signal = pyqtSignal(str)

    def __init__(self, engine, prompt, model_id, chat_id, stream=True, turn_id=None, system_prompt=None, parent=None):
        super().__init__(parent)
        self.engine = engine
        self.prompt = prompt
        self.model_id = model_id
        self.chat_id = chat_id
        self.stream = stream
        self.system_prompt = system_prompt
        self.turn_id = turn_id or uuid.uuid4().hex
        self.cancel_event = threading.Event()
        self.was_cancelled = False
        self._generation = 0

    def request_cancel(self):
        self.was_cancelled = True
        self.cancel_event.set()

    def run(self):
        try:
            generator = self.engine.chat_stream(
                self.prompt,
                self.model_id,
                self.chat_id,
                stream=self.stream,
                cancel_event=self.cancel_event,
                turn_id=self.turn_id,
                system_prompt=self.system_prompt,
            )
            for chunk in generator:
                if self.cancel_event.is_set():
                    self.was_cancelled = True
                    break
                if chunk:
                    self.chunk_received.emit(chunk)
        except Exception as exc:
            if self.cancel_event.is_set():
                self.was_cancelled = True
            else:
                self.error_signal.emit(str(exc))
        finally:
            if self.cancel_event.is_set():
                self.was_cancelled = True
            self.finished_signal.emit()


class ChatStore:
    """Persistent multi-chat store.

    Root index:
        memory_db/chats.sqlite3

    Per-chat data:
        memory_db/<chat_id>/messages.sqlite3
        memory_db/<chat_id>/chroma/
    """

    def __init__(self):
        self.base_dir = BASE_DIR
        self.root_dir = MEMORY_ROOT
        self.index_db = CHAT_INDEX_DB
        self._lock = threading.RLock()
        self._chroma_clients = {}
        self._collections = {}

    def initialize(self):
        os.makedirs(self.root_dir, exist_ok=True)
        with self._connect_index() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS chats (
                    chat_id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    pinned INTEGER NOT NULL DEFAULT 0
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_chats_updated ON chats(updated_at DESC)"
            )
            conn.commit()
        self._migrate_legacy_state()
        logging.info("Chat store initialized.")

    @contextmanager
    def _connect_index(self):
        conn = sqlite3.connect(self.index_db, timeout=30, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        try:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            yield conn
        finally:
            conn.close()

    @contextmanager
    def _connect_messages(self, chat_id):
        chat_dir = self.chat_dir(chat_id)
        os.makedirs(chat_dir, exist_ok=True)
        db_path = os.path.join(chat_dir, "messages.sqlite3")
        conn = sqlite3.connect(db_path, timeout=30, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        try:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    turn_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_messages_created ON messages(id)"
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS chat_state (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                )
                """
            )
            conn.commit()
            yield conn
        finally:
            conn.close()

    def chat_dir(self, chat_id):
        return os.path.join(self.root_dir, chat_id)

    def _new_chat_id(self):
        alphabet = string.ascii_letters + string.digits
        while True:
            chat_id = ''.join(secrets.choice(alphabet) for _ in range(20))
            with self._connect_index() as conn:
                exists = conn.execute(
                    "SELECT 1 FROM chats WHERE chat_id = ?", (chat_id,)
                ).fetchone()
            if not exists:
                return chat_id

    @staticmethod
    def _now():
        return datetime.now(timezone.utc).isoformat()

    def create_chat(self, initial_title="New Chat", chat_id=None):
        with self._lock:
            chat_id = chat_id or self._new_chat_id()
            chat_dir = self.chat_dir(chat_id)
            os.makedirs(os.path.join(chat_dir, "chroma"), exist_ok=True)
            created = self._now()
            safe_title = (initial_title or "New Chat").strip()[:120] or "New Chat"
            with self._connect_index() as conn:
                conn.execute(
                    """
                    INSERT INTO chats(chat_id, title, created_at, updated_at, pinned)
                    VALUES(?,?,?,?,0)
                    """,
                    (chat_id, safe_title, created, created),
                )
                conn.commit()
            with self._connect_messages(chat_id):
                pass
            logging.info("Created chat %s", chat_id)
            return self.get_chat(chat_id)

    def ensure_chat(self, chat_id, fallback_title="New Chat"):
        chat = self.get_chat(chat_id)
        if chat is not None:
            return chat
        return self.create_chat(fallback_title, chat_id=chat_id)

    def get_chat(self, chat_id):
        if not chat_id:
            return None
        with self._connect_index() as conn:
            row = conn.execute(
                "SELECT chat_id, title, created_at, updated_at, pinned FROM chats WHERE chat_id=?",
                (chat_id,),
            ).fetchone()
        if not row:
            return None
        data = dict(row)
        data["mode"] = self.get_chat_mode(chat_id)
        return data

    def list_chats(self):
        with self._connect_index() as conn:
            rows = conn.execute(
                """
                SELECT chat_id, title, created_at, updated_at, pinned
                FROM chats
                ORDER BY pinned DESC, updated_at DESC
                """
            ).fetchall()
        result = []
        for row in rows:
            item = dict(row)
            try:
                item["mode"] = self.get_chat_mode(item["chat_id"]) or "None"
                item["mode_source"] = self.get_chat_mode_source(item["chat_id"]) or "auto"
            except Exception:
                logging.exception("Failed to load chat mode for sidebar row.")
                item["mode"] = "None"
                item["mode_source"] = "auto"
            result.append(item)
        return result

    def rename_chat(self, chat_id, title):
        title = (title or "").strip()[:120] or "Untitled Chat"
        with self._connect_index() as conn:
            conn.execute(
                "UPDATE chats SET title=?, updated_at=? WHERE chat_id=?",
                (title, self._now(), chat_id),
            )
            conn.commit()
        logging.info("Renamed chat %s -> %s", chat_id, title)

    def pin_chat(self, chat_id, pinned=True):
        with self._connect_index() as conn:
            conn.execute(
                "UPDATE chats SET pinned=?, updated_at=? WHERE chat_id=?",
                (1 if pinned else 0, self._now(), chat_id),
            )
            conn.commit()
        logging.info("%s chat %s", "Pinned" if pinned else "Unpinned", chat_id)

    def touch_chat(self, chat_id):
        with self._connect_index() as conn:
            conn.execute(
                "UPDATE chats SET updated_at=? WHERE chat_id=?",
                (self._now(), chat_id),
            )
            conn.commit()

    def save_message(self, chat_id, turn_id, role, content):
        if not chat_id or not content:
            return
        with self._lock:
            self.ensure_chat(chat_id)
            with self._connect_messages(chat_id) as conn:
                conn.execute(
                    """
                    INSERT INTO messages(turn_id, role, content, created_at)
                    VALUES(?,?,?,?)
                    """,
                    (turn_id or uuid.uuid4().hex, role, content, self._now()),
                )
                conn.commit()
            self.touch_chat(chat_id)

    def delete_turn(self, chat_id, turn_id):
        if not chat_id or not turn_id:
            return
        with self._connect_messages(chat_id) as conn:
            conn.execute("DELETE FROM messages WHERE turn_id=?", (turn_id,))
            conn.commit()
        self.touch_chat(chat_id)

    def get_messages(self, chat_id):
        if not chat_id:
            return []
        if not os.path.isdir(self.chat_dir(chat_id)):
            return []
        with self._connect_messages(chat_id) as conn:
            rows = conn.execute(
                "SELECT turn_id, role, content, created_at FROM messages ORDER BY id ASC"
            ).fetchall()
        return [dict(row) for row in rows]

    def get_recent_messages(self, chat_id, limit=32):
        messages = self.get_messages(chat_id)
        return messages[-limit:]

    def message_count(self, chat_id):
        if not chat_id:
            return 0
        with self._connect_messages(chat_id) as conn:
            row = conn.execute("SELECT COUNT(*) AS c FROM messages").fetchone()
        return int(row["c"]) if row else 0

    def get_summary(self, chat_id):
        if not chat_id:
            return "No previous context recorded yet."
        with self._connect_messages(chat_id) as conn:
            row = conn.execute(
                "SELECT value FROM chat_state WHERE key='long_term_summary'"
            ).fetchone()
        return row["value"] if row else "No previous context recorded yet."

    def save_summary(self, chat_id, summary):
        if not chat_id:
            return
        with self._connect_messages(chat_id) as conn:
            conn.execute(
                """
                INSERT INTO chat_state(key,value) VALUES('long_term_summary',?)
                ON CONFLICT(key) DO UPDATE SET value=excluded.value
                """,
                (summary or "No previous context recorded yet.",),
            )
            conn.commit()
        self.touch_chat(chat_id)

    def get_chat_state(self, chat_id, key, default=None):
        if not chat_id or not key:
            return default
        try:
            with self._connect_messages(chat_id) as conn:
                row = conn.execute(
                    "SELECT value FROM chat_state WHERE key=?",
                    (str(key),),
                ).fetchone()
            return row["value"] if row else default
        except Exception:
            logging.exception("Failed to read chat state.")
            return default

    def set_chat_state(self, chat_id, key, value):
        if not chat_id or not key:
            return False
        with self._connect_messages(chat_id) as conn:
            conn.execute(
                """
                INSERT INTO chat_state(key,value) VALUES(?,?)
                ON CONFLICT(key) DO UPDATE SET value=excluded.value
                """,
                (str(key), str(value)),
            )
            conn.commit()
        self.touch_chat(chat_id)
        return True

    def get_chat_mode(self, chat_id):
        value = str(self.get_chat_state(chat_id, "prompt_mode", "") or "").strip()
        return value if value in {"A Friend", "Dev Helper", "Learn Zone", "None"} else None

    def get_chat_mode_source(self, chat_id):
        """Return whether the chat mode was explicitly chosen by the user or auto-detected."""
        source = str(self.get_chat_state(chat_id, "prompt_mode_source", "") or "").strip().lower()
        if source in {"user", "auto"}:
            return source
        # Chats created by older releases stored only prompt_mode. Treat those as
        # auto-detected so the new UI does not incorrectly show a manual-mode badge.
        return "auto" if self.get_chat_mode(chat_id) else None

    def set_chat_mode(self, chat_id, mode, source="user", force=False):
        mode = str(mode or "None").strip()
        if mode not in {"A Friend", "Dev Helper", "Learn Zone", "None"}:
            mode = "None"
        source = str(source or "user").strip().lower()
        if source not in {"user", "auto"}:
            source = "user"

        existing = self.get_chat_mode(chat_id)
        if existing is not None and not force:
            existing_source = self.get_chat_mode_source(chat_id) or source
            return existing == mode and existing_source == source

        self.set_chat_state(chat_id, "prompt_mode", mode)
        self.set_chat_state(chat_id, "prompt_mode_source", source)
        return True

    def _get_collection(self, chat_id):
        with self._lock:
            if chat_id in self._collections:
                return self._collections[chat_id]
            chroma_dir = os.path.join(self.chat_dir(chat_id), "chroma")
            os.makedirs(chroma_dir, exist_ok=True)
            client = chromadb.PersistentClient(path=chroma_dir)
            embed_fn = embedding_functions.DefaultEmbeddingFunction()
            collection = client.get_or_create_collection(
                name="user_memory",
                embedding_function=embed_fn,
            )
            self._chroma_clients[chat_id] = client
            self._collections[chat_id] = collection
            return collection

    def search_memory(self, chat_id, query, n_results=3):
        if not chat_id or not query:
            return ""
        try:
            collection = self._get_collection(chat_id)
            results = collection.query(query_texts=[query], n_results=n_results)
            docs = results.get("documents") or []
            if docs and docs[0]:
                return "\n".join(docs[0])
        except Exception as exc:
            logging.warning("Memory search skipped for %s: %s", chat_id, exc)
        return ""

    def add_memory(self, chat_id, turn_id, user_input, assistant_reply):
        if not chat_id or not assistant_reply:
            return
        try:
            collection = self._get_collection(chat_id)
            collection.add(
                documents=[f"User: {user_input} | AI: {assistant_reply}"],
                ids=[uuid.uuid4().hex],
                metadatas=[{"turn_id": turn_id, "type": "chat_turn"}],
            )
        except Exception as exc:
            logging.error("Failed to add Chroma memory for %s: %s", chat_id, exc)

    def delete_memory_turn(self, chat_id, turn_id):
        if not chat_id or not turn_id:
            return
        try:
            collection = self._get_collection(chat_id)
            collection.delete(where={"turn_id": turn_id})
        except Exception as exc:
            logging.error("Failed to remove Chroma memory %s/%s: %s", chat_id, turn_id, exc)

    def delete_chat(self, chat_id):
        """Delete one chat and every piece of data owned by that chat.

        The root chat index row, per-chat messages SQLite DB, chat_state, and
        the chat's Chroma memory folder are all removed together. Chroma
        client/collection references are released before the filesystem delete
        so Windows has the best chance of unlocking the files immediately.
        """
        if not chat_id:
            return
        with self._lock:
            collection = self._collections.pop(chat_id, None)
            client = self._chroma_clients.pop(chat_id, None)
            # Explicitly drop local references before deleting the directory.
            del collection
            del client

            with self._connect_index() as conn:
                conn.execute("DELETE FROM chats WHERE chat_id=?", (chat_id,))
                conn.commit()

            shutil.rmtree(self.chat_dir(chat_id), ignore_errors=True)
        logging.info("Deleted chat %s and all per-chat data", chat_id)

    def _migrate_legacy_state(self):
        """One-time migration from the old memory_state.json layout.

        The old JSON is not used after import. It is renamed to a .legacy file
        so existing data is not silently destroyed.
        """
        if not os.path.exists(LEGACY_STATE_PATH):
            return
        try:
            with self._connect_index() as conn:
                count = conn.execute("SELECT COUNT(*) AS c FROM chats").fetchone()["c"]
            if count != 0:
                return

            with open(LEGACY_STATE_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
            legacy_messages = data.get("short_term_memory", [])
            summary = data.get("long_term_summary", "")

            if not legacy_messages and not summary:
                return

            chat = self.create_chat("Recovered Chat")
            chat_id = chat["chat_id"]
            for msg in legacy_messages:
                if msg.get("role") in ("user", "assistant") and msg.get("content"):
                    self.save_message(
                        chat_id,
                        msg.get("turn_id") or uuid.uuid4().hex,
                        msg["role"],
                        msg["content"],
                    )
            if summary:
                self.save_summary(chat_id, summary)

            legacy_backup = LEGACY_STATE_PATH.replace(".json", ".legacy.json")
            if os.path.exists(legacy_backup):
                legacy_backup = LEGACY_STATE_PATH.replace(".json", f".{uuid.uuid4().hex[:6]}.legacy.json")
            os.replace(LEGACY_STATE_PATH, legacy_backup)
            logging.info("Migrated legacy memory_state.json to chat %s", chat_id)
        except Exception as exc:
            logging.error("Legacy memory migration failed: %s", exc)


class VoidMemoryEngine:
    """Provider-routed AI + persistent multi-chat memory engine.

    Fast/Flash/Complex model profiles live in appdata.json while provider/model
    catalog data lives in apidata.json. Background jobs always use Fast.
    """

    def __init__(self, model_profiles=None, api_catalog=None, api_keys=None):
        self.model_profiles = copy.deepcopy(model_profiles or {})
        self.api_catalog = copy.deepcopy(api_catalog or {})
        self.api_keys = copy.deepcopy(api_keys or {})
        self.chat_store = ChatStore()
        self.MAX_SHORT_TERM = 8
        self._summary_jobs = set()
        self._summary_lock = threading.RLock()
        self._summary_condition = threading.Condition(self._summary_lock)
        self._purge_generation = 0
        self._purging = False
        self._openai_clients = {}
        self._groq_clients = {}

    def update_configuration(self, model_profiles=None, api_catalog=None, api_keys=None):
        if model_profiles is not None:
            self.model_profiles = copy.deepcopy(model_profiles)
        if api_catalog is not None:
            self.api_catalog = copy.deepcopy(api_catalog)
        if api_keys is not None:
            self.api_keys = copy.deepcopy(api_keys)
        logging.info("AI provider configuration updated.")

    @staticmethod
    def _normalize_profile(profile):
        if not isinstance(profile, dict):
            return {}
        return {
            "provider": str(profile.get("provider", "")).strip(),
            "model": str(profile.get("model", profile.get("model_id", ""))).strip(),
        }

    def _default_profile_for_role(self, role):
        aliases = {
            "Fast Core": "Fast",
            "Smart Logic": "Flash",
            "Turbo Mini": "Complex",
        }
        role = aliases.get(str(role or ""), str(role or ""))
        configured = self._normalize_profile(self.model_profiles.get(role, {}))
        if configured.get("provider") and configured.get("model"):
            return configured

        for item in self.api_catalog.get("roles", {}).get(role, []) or []:
            if item.get("default"):
                return self._normalize_profile({
                    "provider": item.get("provider", ""),
                    "model": item.get("model_id", item.get("model_name", "")),
                })
        items = self.api_catalog.get("roles", {}).get(role, []) or []
        if items:
            item = items[0]
            return self._normalize_profile({
                "provider": item.get("provider", ""),
                "model": item.get("model_id", item.get("model_name", "")),
            })
        return configured

    def resolve_profile(self, role_or_profile):
        requested_role = role_or_profile if isinstance(role_or_profile, str) else ""
        profile = self._normalize_profile(role_or_profile) if isinstance(role_or_profile, dict) else self._default_profile_for_role(role_or_profile)

        provider = profile.get("provider", "")
        model = profile.get("model", "")
        if not provider or not model:
            raise ValueError(
                f"{requested_role or 'Model'} is not configured. Choose a provider and model in Settings."
            )

        provider_cfg = self.api_catalog.get("providers", {}).get(provider, {})
        if not provider_cfg:
            aliases = {"Groq": "Groq AI"}
            provider_name = aliases.get(provider, provider)
            provider_cfg = self.api_catalog.get("providers", {}).get(provider_name, {})
            provider = provider_name

        if not provider_cfg:
            raise ValueError(f"Provider '{provider}' is not configured in apidata.json.")

        # Provider credentials are runtime-only and come from the OS keyring via ui.py.
        api_key = str(self.api_keys.get(provider, "") or "").strip()
        return {
            **profile,
            "provider": provider,
            "api_key": api_key,
            "base_url": provider_cfg.get("base_url", ""),
            "protocol": provider_cfg.get("protocol", "openai_compatible"),
            "chat_path": provider_cfg.get("chat_path", "/chat/completions"),
            "headers": provider_cfg.get("headers", {}) or {},
        }

    def _fast_profile(self):
        return self.resolve_profile(self.model_profiles.get("Fast", {}))

    @staticmethod
    def _read_http_error(exc):
        try:
            raw = exc.read().decode("utf-8", errors="replace")
            try:
                payload = json.loads(raw)
                error = payload.get("error", payload)
                return error if isinstance(error, str) else json.dumps(error)
            except json.JSONDecodeError:
                return raw
        except Exception:
            return str(exc)

    def _get_provider_client(self, profile):
        provider = profile.get("provider", "")
        api_key = profile.get("api_key", "")

        if provider == "Groq AI" and GroqClient is not None:
            cache_key = (provider, api_key)
            client = self._groq_clients.get(cache_key)
            if client is None:
                client = GroqClient(
                    api_key=api_key,
                    timeout=90.0,
                    max_retries=0,
                )
                self._groq_clients[cache_key] = client
            return client

        if OpenAI is None:
            raise RuntimeError(
                "The openai package is required for OpenAI-compatible providers. "
                "Install it with: pip install -U openai"
            )

        cache_key = (
            provider,
            profile.get("base_url", ""),
            api_key,
        )
        client = self._openai_clients.get(cache_key)
        if client is not None:
            return client

        headers = {"User-Agent": "Void-Ai/1.3"}
        headers.update(profile.get("headers", {}) or {})

        client = OpenAI(
            api_key=api_key,
            base_url=profile.get("base_url", ""),
            timeout=90.0,
            max_retries=0,
            default_headers=headers,
        )
        self._openai_clients[cache_key] = client
        return client

    @staticmethod
    def _openai_stream_text(stream_response, cancel_event=None):
        try:
            for chunk in stream_response:
                if cancel_event is not None and cancel_event.is_set():
                    break
                try:
                    choices = getattr(chunk, "choices", None) or []
                    if not choices:
                        continue
                    delta = getattr(choices[0], "delta", None)
                    text = getattr(delta, "content", None) if delta is not None else None
                    if text:
                        yield text
                except Exception:
                    continue
        finally:
            close = getattr(stream_response, "close", None)
            if callable(close):
                try:
                    close()
                except Exception:
                    pass

    @staticmethod
    def _openai_response_to_dict(response):
        if isinstance(response, dict):
            return response
        try:
            return response.model_dump()
        except Exception:
            pass
        try:
            return dict(response)
        except Exception:
            return {}

    def _request_stream(self, profile, messages, stream=True, cancel_event=None):
        profile = self.resolve_profile(profile)
        base_url = profile["base_url"].rstrip("/")
        endpoint = f"{base_url}/{profile['chat_path'].lstrip('/')}"

        logging.info(
            "AI request: provider=%s model=%s endpoint=%s",
            profile["provider"], profile["model"], endpoint
        )

        if profile.get("protocol") == "openai_compatible":
            client = self._get_provider_client(profile)
            try:
                response = client.chat.completions.create(
                    model=profile["model"],
                    messages=messages,
                    stream=bool(stream),
                )
            except Exception as exc:
                status = getattr(exc, "status_code", None)
                body = getattr(exc, "body", None)
                detail = body if body is not None else str(exc)
                prefix = f"{profile['provider']} API error"
                if status is not None:
                    prefix += f" ({status})"
                raise RuntimeError(f"{prefix}: {detail}") from exc

            if stream:
                return self._openai_stream_text(response, cancel_event)
            return self._openai_response_to_dict(response)

        payload = {
            "model": profile["model"],
            "messages": messages,
            "stream": bool(stream),
        }
        req_headers = {
            "Content-Type": "application/json",
            "Accept": "application/x-ndjson" if stream else "application/json",
            "User-Agent": "Void-Ai/1.0",
        }
        api_key = profile.get("api_key", "")
        if api_key:
            req_headers["Authorization"] = f"Bearer {api_key}"
        req_headers.update(profile.get("headers", {}) or {})

        request = urllib.request.Request(
            endpoint,
            data=json.dumps(payload).encode("utf-8"),
            headers=req_headers,
            method="POST",
        )

        try:
            response = urllib.request.urlopen(request, timeout=90)
        except urllib.error.HTTPError as exc:
            detail = self._read_http_error(exc)
            raise RuntimeError(
                f"{profile['provider']} API error ({exc.code}): {detail}"
            ) from exc
        except urllib.error.URLError as exc:
            reason = getattr(exc, "reason", exc)
            raise RuntimeError(
                f"{profile['provider']} connection failed: {reason}"
            ) from exc

        if not stream:
            try:
                return json.loads(response.read().decode("utf-8", errors="replace"))
            finally:
                response.close()

        if profile.get("protocol") == "ollama":
            return self._iter_ollama_stream(response, cancel_event)
        return self._iter_openai_sse(response, cancel_event)

    @staticmethod
    def _iter_openai_sse(response, cancel_event=None):
        try:
            for raw_line in response:
                if cancel_event is not None and cancel_event.is_set():
                    break
                line = raw_line.decode("utf-8", errors="replace").strip()
                if not line or not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if data == "[DONE]":
                    break
                try:
                    payload = json.loads(data)
                except json.JSONDecodeError:
                    continue
                choices = payload.get("choices") or []
                if choices:
                    delta = choices[0].get("delta") or {}
                    text = delta.get("content")
                    if text:
                        yield text
        finally:
            response.close()

    @staticmethod
    def _iter_ollama_stream(response, cancel_event=None):
        try:
            for raw_line in response:
                if cancel_event is not None and cancel_event.is_set():
                    break
                line = raw_line.decode("utf-8", errors="replace").strip()
                if not line:
                    continue
                try:
                    payload = json.loads(line)
                except json.JSONDecodeError:
                    continue
                message = payload.get("message") or {}
                text = message.get("content")
                if text:
                    yield text
                if payload.get("done"):
                    break
        finally:
            response.close()

    def _complete(self, profile, messages):
        data = self._request_stream(profile, messages, stream=False)
        choices = data.get("choices") or []
        if choices:
            return ((choices[0].get("message") or {}).get("content") or "").strip()
        return ((data.get("message") or {}).get("content") or "").strip()

    def initialize_system(self):
        self.chat_store.initialize()
        logging.info("VoidMemoryEngine initialization complete.")

    def generate_startup_prompts(self):
        prompt = (
            "Generate a creative, very short greeting question (max 5 words) "
            "for an AI assistant welcome screen and a very short input placeholder "
            "prompt (max 6 words). Return ONLY a valid JSON object: "
            "{\"greeting\": \"...\", \"placeholder\": \"...\"}. "
            "No markdown or explanation."
        )
        try:
            raw = self._complete(
                self._fast_profile(),
                [{"role": "user", "content": prompt}],
            )
            if raw.startswith("```"):
                raw = re.sub(r"^```[a-zA-Z]*\n?", "", raw)
                raw = re.sub(r"\n?```$", "", raw)
            data = json.loads(raw.strip())
            greeting = str(data.get("greeting", "How can I help?")).strip()
            placeholder = str(
                data.get("placeholder", "What's on your mind today?")
            ).strip()
            return (
                greeting or "How can I help?",
                placeholder or "What's on your mind today?",
            )
        except Exception as exc:
            logging.error("Startup prompt generation failed: %s", exc)
            return "How can I help?", "What's on your mind today?"

    def close(self):
        # Chroma is lazily opened per chat. Releasing references lets Windows
        # unlock the local files when the app is closing/reinitializing.
        self.chat_store._collections.clear()
        self.chat_store._chroma_clients.clear()
        self._openai_clients.clear()
        self._groq_clients.clear()

    # ----- Multi-chat API -----

    def delete_chat(self, chat_id):
        self.chat_store.delete_chat(chat_id)

    def create_chat(self, title="New Chat", chat_id=None):
        return self.chat_store.create_chat(title, chat_id)

    def get_chat_mode(self, chat_id):
        return self.chat_store.get_chat_mode(chat_id)

    def get_chat_mode_source(self, chat_id):
        return self.chat_store.get_chat_mode_source(chat_id)

    def set_chat_mode(self, chat_id, mode, source="user", force=False):
        return self.chat_store.set_chat_mode(chat_id, mode, source=source, force=force)

    def list_chats(self):
        return self.chat_store.list_chats()

    def get_chat(self, chat_id):
        return self.chat_store.get_chat(chat_id)

    def rename_chat(self, chat_id, title):
        self.chat_store.rename_chat(chat_id, title)

    def pin_chat(self, chat_id, pinned=True):
        self.chat_store.pin_chat(chat_id, pinned)

    def load_chat(self, chat_id):
        chat = self.chat_store.get_chat(chat_id)
        if not chat:
            raise ValueError("Chat no longer exists.")
        return chat, self.chat_store.get_messages(chat_id)

    def get_chat_history(self, chat_id):
        return self.chat_store.get_messages(chat_id)

    def rollback_turn(self, chat_id, turn_id):
        self.chat_store.delete_turn(chat_id, turn_id)
        self.chat_store.delete_memory_turn(chat_id, turn_id)

    def purge_all_data(self):
        """Remove all chat/database/memory data without touching appdata.json.

        The settings file is intentionally outside this purge boundary. Chat
        index data, every per-chat SQLite/Chroma folder, legacy memory-state
        files, and the application log are cleared, then a fresh chat index is
        recreated so the running app remains usable immediately.
        """
        try:
            logging.info("Initiating Full Core Purge...")
            self.close()

            # Invalidate any background summary work that may still be finishing
            # so a late result cannot recreate data after the purge.
            with self._summary_lock:
                self._purge_generation += 1
                self._purging = True
                while self._summary_jobs:
                    self._summary_condition.wait(timeout=0.25)

            if os.path.exists(self.chat_store.root_dir):
                shutil.rmtree(self.chat_store.root_dir, ignore_errors=True)

            # Remove legacy memory-state files too. appdata.json is deliberately
            # excluded and therefore retains settings/API configuration.
            for filename in os.listdir(BASE_DIR):
                if filename.startswith("memory_state") and filename.endswith((".json", ".legacy.json")):
                    try:
                        os.remove(os.path.join(BASE_DIR, filename))
                    except FileNotFoundError:
                        pass
                    except Exception as exc:
                        logging.warning("Could not remove legacy memory file %s: %s", filename, exc)

            log_path = os.path.join(BASE_DIR, "logdata.log")
            if os.path.exists(log_path):
                with open(log_path, "w", encoding="utf-8") as f:
                    f.write("")

            self.initialize_system()
            # Re-initialization itself writes a few startup log lines. Clear
            # them again so a successful "Clear all data" actually leaves the
            # log store empty; future activity will naturally create new logs.
            if os.path.exists(log_path):
                with open(log_path, "w", encoding="utf-8") as f:
                    f.write("")
            with self._summary_lock:
                self._purging = False
                self._summary_condition.notify_all()
            return True
        except Exception as exc:
            with self._summary_lock:
                self._purging = False
                self._summary_condition.notify_all()
            logging.error("Error purging core data: %s", exc)
            return False

    # ----- AI / title generation -----

    def _small_task_profile(self):
        """Prefer a lightweight configured model for one-shot first-message classification."""
        candidates = []
        for item in self.api_catalog.get("roles", {}).get("Fast", []) or []:
            candidates.append(item)
        for item in self.api_catalog.get("models", {}).get("Groq AI", []) or []:
            candidates.append(item)
        for item in self.api_catalog.get("models", {}).get("OpenRouter", []) or []:
            candidates.append(item)

        for preferred in ("groq/compound-mini", "liquid/lfm-2.5-2.6b:free"):
            for item in candidates:
                if str(item.get("model_id", "")).strip() == preferred:
                    return self.resolve_profile({
                        "provider": str(item.get("provider", "")).strip(),
                        "model": preferred,
                    })
        return self._fast_profile()

    def generate_chat_title_and_mode(self, user_message, forced_mode=None):
        allowed = {"A Friend", "Dev Helper", "Learn Zone"}
        forced = forced_mode if forced_mode in allowed else None
        forced_instruction = (
            f"The user explicitly selected '{forced}' in the UI. The mode MUST be '{forced}'."
            if forced else
            "Choose exactly one mode: A Friend, Dev Helper, Learn Zone, or Other."
        )
        prompt = (
            "You are Void-AI's lightweight first-message classifier. Analyze the user's first message and return "
            "ONLY one valid JSON object with exactly two fields: title and mode. "
            "title must be a short natural title of at most 6 words. "
            "mode must be exactly A Friend, Dev Helper, Learn Zone, or Other. "
            "A Friend is casual conversation, feelings, support, personal chat, or wanting someone to talk with. "
            "Dev Helper is coding, debugging, software, APIs, databases, PyQt, ChromaDB, or implementation work. "
            "Learn Zone is learning, studying, explanation, concepts, tutorials, or step-by-step teaching. "
            "Other is anything that does not clearly fit those three. "
            "Understand English, Sinhala, and Romanized Sinhala/Singlish, including informal text like 'bn', 'machan', "
            "'meka', 'meka kohomada hadanne', 'therum karala denna', and 'katha karamu'. "
            + forced_instruction + "\n\n"
            + f"User first message:\n{user_message}"
        )
        try:
            raw = self._complete(
                self._small_task_profile(),
                [{"role": "user", "content": prompt}],
            )
            text = str(raw or "").strip()
            text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.I | re.S).strip()
            match = re.search(r"\{.*\}", text, flags=re.S)
            payload = json.loads(match.group(0) if match else text)
            title = " ".join(str(payload.get("title", "")).split()).strip("\"'")[:120]
            mode = str(payload.get("mode", "Other")).strip()
            if mode not in {"A Friend", "Dev Helper", "Learn Zone", "Other"}:
                mode = forced or "Other"
            if forced:
                mode = forced
            return {"title": title or self.fallback_title(user_message), "mode": mode}
        except Exception as exc:
            logging.warning("AI first-message title/mode generation failed: %s", exc)
            return {"title": self.fallback_title(user_message), "mode": forced or "Other"}

    def generate_chat_title(self, user_message):
        return str(self.generate_chat_title_and_mode(user_message).get("title") or self.fallback_title(user_message))

    @staticmethod
    def fallback_title(user_message):
        clean = " ".join((user_message or "").split())
        if not clean:
            return "New Chat"
        if len(clean) <= 48:
            return clean
        return clean[:45].rsplit(" ", 1)[0] + "…"

    # ----- Streaming + per-chat memory -----

    def chat_stream(
        self,
        user_input,
        model_config,
        chat_id,
        stream=True,
        cancel_event=None,
        turn_id=None,
        system_prompt=None,
    ):
        turn_id = turn_id or uuid.uuid4().hex
        if not chat_id:
            raise ValueError("A chat_id is required before sending a message.")
        self.chat_store.ensure_chat(chat_id)

        if cancel_event is not None and cancel_event.is_set():
            return

        self.chat_store.save_message(chat_id, turn_id, "user", user_input)

        try:
            past_context = self.chat_store.search_memory(
                chat_id, user_input, n_results=3
            )
            summary_snapshot = self.chat_store.get_summary(chat_id)
            history_snapshot = self.chat_store.get_recent_messages(
                chat_id, limit=32
            )
            api_history = [
                {"role": m.get("role"), "content": m.get("content")}
                for m in history_snapshot
                if m.get("role") in ("user", "assistant", "system", "tool")
                and m.get("content")
            ]

            base_system_prompt = str(system_prompt or "").strip() or "You are a helpful AI assistant."
            system_prompt = (
                f"{base_system_prompt}\n\n"
                f"Long-Term Memory: {summary_snapshot}\n"
                f"Relevant Past Data: {past_context}\n"
            )
            messages = [{"role": "system", "content": system_prompt}] + api_history

            profile = self.resolve_profile(model_config)
            response_data = self._request_stream(
                profile,
                messages,
                stream=stream,
                cancel_event=cancel_event,
            )

            reply_parts = []
            cancelled = False

            if stream:
                # API providers can deliver tiny chunks much faster than Qt can
                # repaint. Batch them in the worker thread so the GUI receives a
                # steady stream of updates instead of thousands of queued signals.
                emit_buffer = []
                buffered_chars = 0
                last_emit = time.monotonic()
                for text in response_data:
                    if cancel_event is not None and cancel_event.is_set():
                        cancelled = True
                        break
                    if not text:
                        continue

                    reply_parts.append(text)
                    emit_buffer.append(text)
                    buffered_chars += len(text)
                    now = time.monotonic()
                    if buffered_chars >= 96 or (now - last_emit) >= 0.025:
                        yield "".join(emit_buffer)
                        emit_buffer.clear()
                        buffered_chars = 0
                        last_emit = now

                if emit_buffer and not cancelled:
                    yield "".join(emit_buffer)
            else:
                if isinstance(response_data, dict):
                    choices = response_data.get("choices") or []
                    if choices:
                        full_reply = (
                            (choices[0].get("message") or {}).get("content") or ""
                        )
                    else:
                        full_reply = (
                            (response_data.get("message") or {}).get("content") or ""
                        )
                    if full_reply:
                        yield full_reply

            full_reply = "".join(reply_parts) if stream else full_reply

            if cancel_event is not None and cancel_event.is_set():
                cancelled = True

            if cancelled:
                logging.info(
                    "Cancelled turn=%s chat=%s provider=%s model=%s",
                    turn_id,
                    chat_id,
                    profile["provider"],
                    profile["model"],
                )
                self.rollback_turn(chat_id, turn_id)
                return

            self.chat_store.save_message(
                chat_id, turn_id, "assistant", full_reply
            )
            self.chat_store.add_memory(
                chat_id, turn_id, user_input, full_reply
            )
            if self.chat_store.message_count(chat_id) > self.MAX_SHORT_TERM:
                self._start_summary_job(chat_id)

        except Exception:
            self.rollback_turn(chat_id, turn_id)
            raise

    def _start_summary_job(self, chat_id):
        with self._summary_lock:
            if self._purging:
                return
            if chat_id in self._summary_jobs:
                return
            self._summary_jobs.add(chat_id)
            generation = self._purge_generation

        def job():
            try:
                self._summarize_chat(chat_id, generation)
            finally:
                with self._summary_lock:
                    self._summary_jobs.discard(chat_id)
                    self._summary_condition.notify_all()

        threading.Thread(target=job, name=f"VoidSummary-{chat_id}", daemon=True).start()

    def _summarize_chat(self, chat_id, generation=None):
        with self._summary_lock:
            active_generation = self._purge_generation
        if generation is not None and generation != active_generation:
            return

        messages = self.chat_store.get_messages(chat_id)
        if len(messages) <= self.MAX_SHORT_TERM:
            return

        older = messages[:-self.MAX_SHORT_TERM]
        older_text = "\n".join(
            f"{m['role'].upper()}: {m['content']}" for m in older
        )
        previous = self.chat_store.get_summary(chat_id)
        prompt = (
            "Maintain a concise long-term summary for a chat.\n"
            f"Previous summary: {previous}\n"
            f"Older conversation:\n{older_text}\n\n"
            "Return only the updated summary."
        )

        try:
            summary = self._complete(
                self._fast_profile(),
                [{"role": "user", "content": prompt}],
            )
            if summary:
                with self._summary_lock:
                    still_current = generation is None or generation == self._purge_generation
                if not still_current:
                    return
                if self.chat_store.get_chat(chat_id) is None:
                    return
                self.chat_store.save_summary(chat_id, summary)
                logging.info("Background summary updated for %s", chat_id)
        except Exception as exc:
            logging.error("Background summary error for %s: %s", chat_id, exc)