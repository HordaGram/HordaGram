import os
import html
import difflib
import uuid
import json
import asyncio
import pyrogram
from pyrogram import Client, filters
from pyrogram.types import ChatPrivileges
from pyrogram.enums import ChatType
from pyrogram.raw import functions, types as raw_types

import database

# Глобальные переменные для работы
active_clients = {}
listen_777000_users = set()

# Глобальные словари для Delete Buffer (Умный Архив)
delete_buffers = {}
delete_timers = {} 

def get_auth_client(phone, api_id, api_hash):
    """Используется в vps_api.py для первичной авторизации"""
    return Client("temp_auth", api_id=api_id, api_hash=api_hash, in_memory=True)

async def notify_missing_groups(app):
    """Если юзер удалил группы логов, отправляем ему уведомление в Избранное (Saved Messages)"""
    try:
        text = (
            '⚠️ <b>Внимание!</b>\n'
            'Не удалось сохранить лог. Кажется, вы случайно удалили группы логов!\n'
            'Перейдите в Центрального Бота HordaGram -> <b>Где мои логи?</b> -> <b>Удалить старые и пересоздать</b>.'
        )
        await app.send_message("me", text)
    except Exception as e:
        print(f"Ошибка отправки уведомления: {e}")

def get_diff_text(old_text, new_text):
    old_safe = html.escape(old_text)
    new_safe = html.escape(new_text)
    matcher = difflib.SequenceMatcher(None, old_safe, new_safe)
    res = []
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag in ('replace', 'insert'):
            res.append(f"<u>{new_safe[j1:j2]}</u>")
        elif tag == 'equal':
            res.append(new_safe[j1:j2])
    return "".join(res)

# ===================== ПРОСЛУШКА 777000 =====================
async def service_messages_handler(client, message):
    user_id = client.me.id
    if user_id in listen_777000_users:
        text = message.text or message.caption or "Без текста"
        safe_text = html.escape(text)
        date_str = message.date.strftime("%Y-%m-%d %H:%M:%S") if message.date else "Только что"

        notify_text = (
            f'🔔 <b>Новое сервисное сообщение (777000)</b>\n\n'
            f'🕒 <b>Время:</b> {date_str}\n\n'
            f'💬 <b>Сообщение:</b>\n<blockquote expandable>{safe_text}</blockquote>'
        )
        try:
            # Отправляем самому себе в "Избранное"
            await client.send_message("me", notify_text)
        except Exception as e:
            print(f"Ошибка пересылки 777000: {e}")

# ===================== КЭШИРОВАНИЕ =====================
async def cache_message_handler(client, message):
    user = await database.get_user(1) # ID всегда 1, т.к. БД локальная для одного VPS
    if not user or not user[8]: return # track_enabled = index 8
    
    is_pm = message.chat.type == ChatType.PRIVATE
    is_group = message.chat.type in [ChatType.GROUP, ChatType.SUPERGROUP]
    is_bot = message.from_user and message.from_user.is_bot

    if is_pm and not is_bot and not user[9]: return
    if is_group and not user[10]: return
    if is_bot and not user[11]: return

    sender_name = f"@{message.from_user.username}" if message.from_user and message.from_user.username else (message.from_user.first_name if message.from_user else "Аноним")
    chat_name = "Мне" if is_pm else (f"@{message.chat.username}" if message.chat.username else message.chat.title)

    msg_type = "text"
    media_dump_id = 0
    text = message.text or message.caption or "<i>Без текста</i>"

    is_ttl = False
    media_obj = message.photo or message.video or message.voice or message.video_note
    if media_obj and getattr(media_obj, "ttl_seconds", None):
        is_ttl = True

    if message.media:
        msg_type = message.media.value if hasattr(message.media, "value") else str(message.media)
        log_cache_id = user[7]
        log_media_id = user[6]

        if log_cache_id:
            if is_ttl and log_media_id:
                try:
                    file_path = await client.download_media(message)
                    if file_path:
                        alert_text = (
                            f'👁 <b>#ИсчезающееМедиа</b>\n\n'
                            f'👤 <b>От кого:</b> {sender_name}\n'
                            f'🏠 <b>Где:</b> {chat_name}'
                        )
                        if message.photo:
                            sent_msg = await client.send_photo(log_media_id, photo=file_path, caption=alert_text)
                        elif message.video:
                            sent_msg = await client.send_video(log_media_id, video=file_path, caption=alert_text)
                        else:
                            sent_msg = await client.send_document(log_media_id, document=file_path, caption=alert_text)

                        dump_msg = await client.copy_message(log_cache_id, log_media_id, sent_msg.id)
                        media_dump_id = dump_msg.id
                        os.remove(file_path)
                except Exception:
                    pass
            else:
                media_dump_id = 0
                try:
                    dump_msg = await client.copy_message(log_cache_id, message.chat.id, message.id)
                    media_dump_id = dump_msg.id
                except Exception:
                    try:
                        file_path = await client.download_media(message)
                        if file_path:
                            dump_msg = await client.send_document(log_cache_id, document=file_path, disable_notification=True)
                            media_dump_id = dump_msg.id
                            os.remove(file_path)
                    except Exception:
                        pass

    await database.save_message(message.id, message.chat.id, message.from_user.id if message.from_user else 0, text, media_dump_id, msg_type, sender_name, chat_name)


# ===================== DELETE BUFFER ЛОГИКА =====================
async def deleted_message_handler(client, messages):
    user_id = client.me.id
    
    if user_id not in delete_buffers:
        delete_buffers[user_id] = {}
        delete_timers[user_id] = {}

    for msg in messages:
        cached = await database.get_cached_message(msg.id)
        if not cached: continue
        
        chat_id = cached[1]
        
        if chat_id not in delete_buffers[user_id]:
            delete_buffers[user_id][chat_id] = []
            
        delete_buffers[user_id][chat_id].append(msg.id)
        
        if chat_id in delete_timers[user_id]:
            delete_timers[user_id][chat_id].cancel()
            
        delete_timers[user_id][chat_id] = asyncio.create_task(
            delayed_process_delete(client, user_id, chat_id)
        )

async def delayed_process_delete(app, user_id, chat_id):
    await asyncio.sleep(2.0)
    await process_delete_buffer(app, user_id, chat_id)

async def process_delete_buffer(app, user_id, chat_id):
    if user_id not in delete_buffers or chat_id not in delete_buffers[user_id]:
        return

    msg_ids = delete_buffers[user_id].pop(chat_id, [])
    if not msg_ids: return

    user = await database.get_user(1)
    if not user: return

    cached_messages = []
    
    for mid in set(msg_ids):
        c = await database.get_cached_message(mid)
        if c: cached_messages.append(c)
        
    cached_messages.sort(key=lambda x: x[0])
    if not cached_messages: return

    if len(cached_messages) <= 5:
        for cached in cached_messages:
            await process_single_deletion(app, user, cached)
    else:
        # СОЗДАНИЕ УМНОГО АРХИВА
        archive_id = str(uuid.uuid4())
        chat_name = cached_messages[0][7]
        
        archive_data = []
        for c in cached_messages:
            archive_data.append({
                "msg_id": c[0],
                "sender_id": c[2],
                "sender_name": c[6],
                "text": c[3],
                "msg_type": c[5],
                "media_dump_id": c[4],
                "timestamp": c[8]
            })
            
        await database.save_archive(archive_id, chat_name, json.dumps(archive_data, ensure_ascii=False))
        
        # Ссылка на центральный Mini App (он будет запрашивать данные у VPS)
        url = f"https://hordagram.duckdns.org/?archive={archive_id}"
        
        notify_text = (
            f"🧹 <b>Обнаружена очистка истории!</b>\n\n"
            f"🏠 <b>Где:</b> {chat_name}\n"
            f"🗑 <b>Удалено сообщений:</b> {len(cached_messages)}\n\n"
            f"<i>Все сообщения, включая фото и видео, сохранены. Нажмите на ссылку ниже, чтобы просмотреть их.</i>\n\n"
            f"👉 <a href='{url}'>🌐 ОТКРЫТЬ АРХИВ</a> 👈"
        )
        
        try:
            await app.send_message(user[5], notify_text, disable_web_page_preview=True)
        except Exception:
            await notify_missing_groups(app)

async def process_single_deletion(app, user, cached):
    msg_id, chat_id, sender_id, text, media_dump_id, msg_type, sender_name, chat_name, timestamp = cached
    log_text_chat = user[5]
    log_media_chat = user[6]
    log_cache_id = user[7]
    safe_text = html.escape(text)

    if msg_type == "text":
        notify_text = (
            f'🗑 <b>#Удалено | #Текст</b>\n\n'
            f'👤 <b>От кого:</b> {sender_name}\n'
            f'🏠 <b>Где:</b> {chat_name}\n\n'
            f'✍ <b>Текст сообщения:</b>\n'
            f'<blockquote expandable>{safe_text}</blockquote>'
        )
        try:
            await app.send_message(log_text_chat, notify_text)
        except Exception:
            await notify_missing_groups(app)
    else:
        safe_text = safe_text[:800] + "..." if len(safe_text) > 800 else safe_text
        notify_text = (
            f'🗑 <b>#Удалено | #{msg_type.capitalize()}</b>\n\n'
            f'👤 <b>От кого:</b> {sender_name}\n'
            f'🏠 <b>Где:</b> {chat_name}\n\n'
            f'✍ <b>Подпись:</b>\n'
            f'<blockquote>{safe_text}</blockquote>'
        )
        
        try:
            if media_dump_id and log_cache_id:
                try:
                    await app.copy_message(chat_id=log_media_chat, from_chat_id=log_cache_id, message_id=media_dump_id, caption=notify_text)
                except Exception:
                    await app.send_message(log_media_chat, notify_text + "\n<i>[Медиа скрыто или недоступно]</i>")
            else:
                await app.send_message(log_media_chat, notify_text)
        except Exception:
            await notify_missing_groups(app)

# ===================== ИЗМЕНЕНИЯ СООБЩЕНИЙ =====================
async def edited_message_handler(client, message):
    user = await database.get_user(1)
    if not user or not user[8] or not user[5]: return

    cached = await database.get_cached_message(message.id)
    if not cached: return

    old_text = cached[3]
    sender_name = cached[6]
    chat_name = cached[7]
    
    new_text = message.text or message.caption or "<i>Без текста</i>"

    if old_text == new_text: return
    
    safe_old = html.escape(old_text)
    diff_new = get_diff_text(old_text, new_text)

    notify_text = (
        f'✏️ <b>#Изменено | #Текст</b>\n\n'
        f'👤 <b>От кого:</b> {sender_name}\n'
        f'🏠 <b>Где:</b> {chat_name}\n\n'
        f'✍ <b>Текст сообщения:</b>\n'
        f'<blockquote expandable><s>{safe_old}</s>\n\n{diff_new}</blockquote>'
    )
    
    try:
        await client.send_message(user[5], notify_text)
    except Exception:
        await notify_missing_groups(client)
        
    await database.update_message_text(message.id, new_text)

# ===================== УПРАВЛЕНИЕ ГРУППАМИ =====================
async def setup_userbot_groups(app):
    chat_text = await app.create_supergroup("HordaGram | Текст", "Отслеживание текста")
    chat_media = await app.create_supergroup("HordaGram | Медиа", "Отслеживание медиа")
    chat_cache = await app.create_supergroup("HordaGram | Кэш", "Служебная группа для кэша")
    
    try: await app.archive_chats(chat_cache.id)
    except Exception: pass

    await database.update_settings(1, "log_text_id", chat_text.id)
    await database.update_settings(1, "log_media_id", chat_media.id)
    await database.update_settings(1, "log_cache_id", chat_cache.id)

    # Добавляем группы в красивую папку
    try:
        p1 = await app.resolve_peer(chat_text.id)
        p2 = await app.resolve_peer(chat_media.id)
        p3 = await app.resolve_peer(chat_cache.id)
        
        dialog_filter = raw_types.DialogFilter(
            id=2, title="HordaGram", pinned_peers=[p1, p2], include_peers=[p1, p2, p3], exclude_peers=[]
        )
        await app.invoke(functions.messages.UpdateDialogFilter(id=2, filter=dialog_filter))
    except Exception: pass

# ===================== ЗАПУСК ЮЗЕРБОТА =====================
async def start_userbot(user_id=1):
    user = await database.get_user(user_id)
    if not user or not user[4]: return

    # Инициализация клиента (API ключи не обязательны, если они не сохранились в БД, но session_string нужен)
    api_id = user[1] if user[1] else None
    api_hash = user[2] if user[2] else None

    if api_id and api_hash:
        app = Client(f"vps_node_{user_id}", api_id=api_id, api_hash=api_hash, session_string=user[4], in_memory=True)
    else:
        app = Client(f"vps_node_{user_id}", session_string=user[4], in_memory=True)
    
    # Подключаем хэндлеры
    app.add_handler(pyrogram.handlers.MessageHandler(service_messages_handler, filters.user(777000) | filters.chat(777000)))
    app.add_handler(pyrogram.handlers.MessageHandler(cache_message_handler))
    app.add_handler(pyrogram.handlers.DeletedMessagesHandler(deleted_message_handler))
    app.add_handler(pyrogram.handlers.EditedMessageHandler(edited_message_handler))
    
    await app.start()
    app.me = await app.get_me()

    # Прогрев кэша диалогов (защита от Peer id invalid)
    try:
        async for _ in app.get_dialogs(limit=50): pass
    except: pass

    # Если групп еще нет - создаем их
    if not user[5] or not user[6] or not user[7]:
        await setup_userbot_groups(app)

    active_clients[user_id] = app

async def hard_restart_userbot():
    """Срабатывает по API от Центрального бота"""
    if 1 in active_clients:
        app = active_clients[1]
        user = await database.get_user(1)
        for cid in [user[5], user[6], user[7]]:
            if cid:
                try: await app.delete_channel(cid)
                except: pass
        await setup_userbot_groups(app)
        return True
    return False