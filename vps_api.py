import os
import asyncio
import uvicorn
from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.responses import JSONResponse
from dotenv import load_dotenv

import database
from userbot_app import (
    start_userbot, 
    get_auth_client, 
    active_clients, 
    hard_restart_userbot,
    listen_777000_users
)

# Загружаем логин и пароль, сгенерированные при установке (из файла .env)
load_dotenv()
VPS_LOGIN = os.getenv("VPS_LOGIN")
VPS_PASSWORD = os.getenv("VPS_PASSWORD")

app = FastAPI(title="HordaGram VPS Node API")
security = HTTPBasic()

# Временное хранилище сессии во время авторизации номера телефона
auth_sessions = {}

def verify_credentials(credentials: HTTPBasicCredentials = Depends(security)):
    """Проверка Логина и Пароля от Центрального Бота"""
    if credentials.username != VPS_LOGIN or credentials.password != VPS_PASSWORD:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect login or password",
            headers={"WWW-Authenticate": "Basic"},
        )
    return credentials.username

# ================= ФОНОВЫЕ ЗАДАЧИ =================

async def db_garbage_collector():
    """Автоматически очищает старые сообщения из БД, чтобы не забить диск VPS"""
    while True:
        try:
            await database.cleanup_old_messages(days=3)
        except Exception as e:
            print(f"Ошибка очистки БД: {e}")
        await asyncio.sleep(43200)  # Раз в 12 часов

@app.on_event("startup")
async def startup_event():
    """Срабатывает при запуске сервера"""
    await database.init_db()
    asyncio.create_task(db_garbage_collector())
    
    # Пытаемся запустить юзербота, если сессия уже сохранена в БД
    user = await database.get_user(1)
    if user and user[4]:  # index 4 is session_string
        print("Найдена сохраненная сессия. Запуск юзербота...")
        asyncio.create_task(start_userbot(1))

# ================= АПИ ДЛЯ АВТОРИЗАЦИИ В TELEGRAM =================

@app.post("/api/auth/send_code")
async def api_send_code(phone: str, api_id: int, api_hash: str, _: str = Depends(verify_credentials)):
    """Шаг 1: Запросить код у Telegram"""
    try:
        client = get_auth_client(phone, api_id, api_hash)
        await client.connect()
        sent_code = await client.send_code(phone)
        
        auth_sessions["temp"] = {
            "client": client, 
            "phone_code_hash": sent_code.phone_code_hash,
            "phone": phone,
            "api_id": api_id,
            "api_hash": api_hash
        }
        return JSONResponse({"status": "ok", "message": "Code sent successfully"})
    except Exception as e:
        return JSONResponse({"status": "error", "message": str(e)}, status_code=400)

@app.post("/api/auth/submit_code")
async def api_submit_code(code: str, _: str = Depends(verify_credentials)):
    """Шаг 2: Ввод кода подтверждения"""
    if "temp" not in auth_sessions:
        return JSONResponse({"status": "error", "message": "Session not found. Try sending code again."}, status_code=400)
    
    session = auth_sessions["temp"]
    client = session["client"]
    
    try:
        await client.sign_in(session["phone"], session["phone_code_hash"], code)
        session_string = await client.export_session_string()
        await client.disconnect()
        
        # Сохраняем сессию в локальную БД
        await database.save_user_session(1, session["api_id"], session["api_hash"], session["phone"], session_string)
        
        # Запускаем перехватчик
        asyncio.create_task(start_userbot(1))
        auth_sessions.clear()
        
        return JSONResponse({"status": "ok", "message": "Authenticated successfully"})
    except Exception as e:
        if "SESSION_PASSWORD_NEEDED" in str(e):
            return JSONResponse({"status": "2fa_required", "message": "2FA Password needed"})
        return JSONResponse({"status": "error", "message": str(e)}, status_code=400)

@app.post("/api/auth/submit_password")
async def api_submit_password(password: str, _: str = Depends(verify_credentials)):
    """Шаг 3: Ввод облачного пароля 2FA"""
    if "temp" not in auth_sessions:
        return JSONResponse({"status": "error", "message": "Session not found."}, status_code=400)

    session = auth_sessions["temp"]
    client = session["client"]
    
    try:
        await client.check_password(password)
        session_string = await client.export_session_string()
        await client.disconnect()
        
        await database.save_user_session(1, session["api_id"], session["api_hash"], session["phone"], session_string)
        await database.update_settings(1, "password", password)
        
        asyncio.create_task(start_userbot(1))
        auth_sessions.clear()
        
        return JSONResponse({"status": "ok", "message": "Authenticated successfully"})
    except Exception as e:
        return JSONResponse({"status": "error", "message": str(e)}, status_code=400)

# ================= АПИ УПРАВЛЕНИЯ ЮЗЕРБОТОМ =================

@app.get("/api/status")
async def api_get_status(_: str = Depends(verify_credentials)):
    """Возвращает статус юзербота (работает/слетел) и статистику для Дашборда"""
    user = await database.get_user(1)
    if not user:
        return {"status": "empty"}
        
    is_active = 1 in active_clients
    stats = await database.get_local_stats()
    
    return {
        "status": "running" if is_active else "stopped", 
        "has_session": bool(user[4]),
        "track_enabled": bool(user[8]),
        "stats": stats
    }

@app.post("/api/settings/toggle")
async def api_toggle_setting(field: str, _: str = Depends(verify_credentials)):
    """Включение/выключение настроек отслеживания (track_pm, track_groups и т.д.)"""
    user = await database.get_user(1)
    if not user:
        return JSONResponse({"status": "error", "message": "User not found"}, status_code=400)

    fields_map = {
        "track_enabled": 8,
        "track_pm": 9,
        "track_groups": 10,
        "track_bots": 11
    }
    
    if field not in fields_map:
        return JSONResponse({"status": "error", "message": "Invalid field"}, status_code=400)

    current_value = user[fields_map[field]]
    new_value = 0 if current_value else 1
    
    await database.update_settings(1, field, new_value)
    return {"status": "ok", "new_value": new_value}

@app.post("/api/action/recreate_groups")
async def api_recreate_groups(_: str = Depends(verify_credentials)):
    """Пересоздает группы логов и папку"""
    success = await hard_restart_userbot()
    if success:
        return {"status": "ok"}
    return JSONResponse({"status": "error", "message": "Userbot is not running"}, status_code=400)

@app.post("/api/action/logout")
async def api_logout(_: str = Depends(verify_credentials)):
    """Полный выход: удаление групп и сессии"""
    if 1 in active_clients:
        app_client = active_clients[1]
        user = await database.get_user(1)
        
        # Удаляем группы
        for cid in [user[5], user[6], user[7]]:
            if cid:
                try: await app_client.delete_channel(cid)
                except: pass
                
        await app_client.stop()
        del active_clients[1]

    # Стираем из БД
    await database.save_user_session(1, None, None, None, None)
    for field in ["log_text_id", "log_media_id", "log_cache_id", "password"]:
        await database.update_settings(1, field, None)
        
    return {"status": "ok"}

# ================= АПИ ДЛЯ WEB MINI-APP (ПОЛУЧЕНИЕ АРХИВОВ) =================
# Эти роуты открыты, так как они используются для выдачи данных в Дашборд
# (Дашборд знает уникальный UUID архива, поэтому перебор исключен)

@app.get("/api/archive/{archive_id}")
async def get_archive_data(archive_id: str):
    archive = await database.get_archive(archive_id)
    if not archive:
        raise HTTPException(status_code=404, detail="Archive not found")
    
    chat_name, data_json, timestamp = archive
    return {
        "archive_id": archive_id,
        "chat_name": chat_name,
        "timestamp": timestamp,
        "messages": json.loads(data_json)
    }

@app.delete("/api/archive/{archive_id}")
async def api_delete_archive(archive_id: str, _: str = Depends(verify_credentials)):
    await database.delete_archive(archive_id)
    return {"status": "ok"}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)