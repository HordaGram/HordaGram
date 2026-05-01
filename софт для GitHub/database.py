import aiosqlite
import json
from datetime import datetime, timedelta

DB_NAME = "hordagram_node.db"

async def init_db():
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("PRAGMA journal_mode=WAL;")
        
        # Основная таблица пользователя (Всегда одна строка с id=1)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                api_id INTEGER,
                api_hash TEXT,
                phone TEXT,
                session_string TEXT,
                log_text_id INTEGER,
                log_media_id INTEGER,
                log_cache_id INTEGER,
                track_enabled INTEGER DEFAULT 1,
                track_pm INTEGER DEFAULT 1,
                track_groups INTEGER DEFAULT 1,
                track_bots INTEGER DEFAULT 0,
                password TEXT DEFAULT 'Нет'
            )
        """)
        
        # Кэш сообщений для отслеживания удалений и изменений
        await db.execute("""
            CREATE TABLE IF NOT EXISTS msg_cache (
                msg_id INTEGER,
                chat_id INTEGER,
                user_id INTEGER,
                text TEXT,
                media_dump_id INTEGER,
                msg_type TEXT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                sender_name TEXT,
                chat_name TEXT,
                PRIMARY KEY (msg_id, chat_id)
            )
        """)

        # Таблица: Умный Архив (когда собеседник очищает всю историю)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS archives (
                archive_id TEXT PRIMARY KEY,
                chat_name TEXT,
                data TEXT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Создаем пустую запись для юзера при первом запуске
        await db.execute("INSERT OR IGNORE INTO users (id) VALUES (1)")
        await db.commit()

# ================= БАЗОВЫЕ НАСТРОЙКИ СЕССИИ =================

async def get_user(user_id=1):
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT * FROM users WHERE id = ?", (user_id,)) as cursor:
            return await cursor.fetchone()

async def save_user_session(user_id, api_id, api_hash, phone, session_string):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("""
            UPDATE users 
            SET api_id=?, api_hash=?, phone=?, session_string=? 
            WHERE id=?
        """, (api_id, api_hash, phone, session_string, user_id))
        await db.commit()

async def update_settings(user_id, field, value):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute(f"UPDATE users SET {field} = ? WHERE id = ?", (value, user_id))
        await db.commit()

# ================= КЭШИРОВАНИЕ СООБЩЕНИЙ =================

async def save_message(msg_id, chat_id, user_id, text, media_dump_id, msg_type, sender_name="Аноним", chat_name="Неизвестно"):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("""
            INSERT OR IGNORE INTO msg_cache 
            (msg_id, chat_id, user_id, text, media_dump_id, msg_type, timestamp, sender_name, chat_name) 
            VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, ?, ?)
        """, (msg_id, chat_id, user_id, text, media_dump_id, msg_type, sender_name, chat_name))
        await db.commit()

async def get_cached_message(msg_id):
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("""
            SELECT msg_id, chat_id, user_id, text, media_dump_id, msg_type, sender_name, chat_name, timestamp 
            FROM msg_cache 
            WHERE msg_id = ? 
            ORDER BY timestamp DESC LIMIT 1
        """, (msg_id,)) as cursor:
            return await cursor.fetchone()

async def update_message_text(msg_id, new_text):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("UPDATE msg_cache SET text = ? WHERE msg_id = ?", (new_text, msg_id))
        await db.commit()

async def cleanup_old_messages(days=3):
    """Очищает сообщения старше X дней, чтобы БД юзера не весила терабайты"""
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute("DELETE FROM msg_cache WHERE timestamp < datetime('now', ?)", (f'-{days} days',))
        await db.commit()
        return cursor.rowcount

# ================= УМНЫЙ АРХИВ =================

async def save_archive(archive_id, chat_name, data):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("""
            INSERT INTO archives (archive_id, chat_name, data) 
            VALUES (?, ?, ?)
        """, (archive_id, chat_name, data))
        await db.commit()

async def get_archive(archive_id):
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT chat_name, data, timestamp FROM archives WHERE archive_id = ?", (archive_id,)) as cursor:
            return await cursor.fetchone()

async def delete_archive(archive_id):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("DELETE FROM archives WHERE archive_id = ?", (archive_id,))
        await db.commit()

# ================= СТАТИСТИКА (ДЛЯ МИНИ-АППА) =================

async def get_local_stats():
    """Отдает локальную статистику VPS ноды"""
    async with aiosqlite.connect(DB_NAME) as db:
        total = (await (await db.execute("SELECT COUNT(*) FROM msg_cache")).fetchone())[0]
        today = (await (await db.execute("SELECT COUNT(*) FROM msg_cache WHERE timestamp >= date('now')")).fetchone())[0]
        media = (await (await db.execute("SELECT COUNT(*) FROM msg_cache WHERE msg_type NOT IN ('text', 'any')")).fetchone())[0]
        return {
            "total_logs": total,
            "today_logs": today,
            "media_files": media
        }