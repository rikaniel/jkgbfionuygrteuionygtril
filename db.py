"""
Модуль для работы с базой данных SQLite.
Содержит функции инициализации, CRUD-операции для пользователей, инцидентов,
администраторов, нод и сайтов маскировки.
"""

import sqlite3
import random
import string
import json
import logging
from datetime import datetime
from typing import List, Dict, Optional, Any

logger = logging.getLogger(__name__)

DB_PATH = "bot.db"

# ---------------------------- Инициализация БД ----------------------------
def init_db() -> None:
    """Создаёт все необходимые таблицы, если их нет."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    # Пользователи (подписки)
    c.execute('''
        CREATE TABLE IF NOT EXISTS users (
            telegram_id INTEGER PRIMARY KEY,
            inbound_id INTEGER NOT NULL,
            client_email TEXT NOT NULL,
            subscription_path TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Инциденты
    c.execute('''
        CREATE TABLE IF NOT EXISTS incidents (
            id TEXT PRIMARY KEY,
            importance TEXT NOT NULL,
            status TEXT NOT NULL,
            description TEXT NOT NULL,
            target TEXT NOT NULL,
            message_id INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Администраторы
    c.execute('''
        CREATE TABLE IF NOT EXISTS admins (
            telegram_id INTEGER PRIMARY KEY
        )
    ''')

    # Ноды (общие для всех пользователей)
    c.execute('''
        CREATE TABLE IF NOT EXISTS nodes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            ip TEXT NOT NULL,
            port INTEGER NOT NULL
        )
    ''')

    # Сайты маскировки
    c.execute('''
        CREATE TABLE IF NOT EXISTS masking_sites (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            url TEXT NOT NULL UNIQUE,
            expected_content TEXT
        )
    ''')

    # Xray Inbounds (прокси для пинга)
    c.execute('''
        CREATE TABLE IF NOT EXISTS xray_inbounds (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            protocol TEXT NOT NULL,
            settings TEXT NOT NULL
        )
    ''')

    conn.commit()
    conn.close()
    logger.info("База данных инициализирована")


# ---------------------------- Пользователи ----------------------------
def get_user(telegram_id: int) -> Optional[Dict[str, Any]]:
    """Возвращает данные пользователя по Telegram ID или None."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        "SELECT telegram_id, inbound_id, client_email, subscription_path, created_at FROM users WHERE telegram_id = ?",
        (telegram_id,)
    )
    row = c.fetchone()
    conn.close()
    if row:
        return {
            "telegram_id": row[0],
            "inbound_id": row[1],
            "client_email": row[2],
            "subscription_path": row[3],
            "created_at": row[4]
        }
    return None


def add_user(telegram_id: int, inbound_id: int, client_email: str, subscription_path: str) -> None:
    """Добавляет или обновляет пользователя."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        "INSERT OR REPLACE INTO users (telegram_id, inbound_id, client_email, subscription_path) VALUES (?, ?, ?, ?)",
        (telegram_id, inbound_id, client_email, subscription_path)
    )
    conn.commit()
    conn.close()
    logger.info(f"Пользователь {telegram_id} добавлен/обновлён")


def delete_user(telegram_id: int) -> bool:
    """Удаляет пользователя. Возвращает True, если запись существовала."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("DELETE FROM users WHERE telegram_id = ?", (telegram_id,))
    deleted = c.rowcount > 0
    conn.commit()
    conn.close()
    if deleted:
        logger.info(f"Пользователь {telegram_id} удалён")
    return deleted


def get_all_users() -> List[Dict[str, Any]]:
    """Возвращает список всех пользователей."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT telegram_id, inbound_id, client_email, subscription_path, created_at FROM users ORDER BY created_at")
    rows = c.fetchall()
    conn.close()
    return [
        {
            "telegram_id": row[0],
            "inbound_id": row[1],
            "client_email": row[2],
            "subscription_path": row[3],
            "created_at": row[4]
        }
        for row in rows
    ]


# ---------------------------- Инциденты ----------------------------
def generate_incident_id(length: int = 8) -> str:
    """Генерирует случайный ID из заглавных букв и цифр."""
    chars = string.ascii_uppercase + string.digits
    return ''.join(random.choices(chars, k=length))


def add_incident(importance: str, description: str, target: str) -> Optional[str]:
    """
    Добавляет новый инцидент, если нет активного с таким же target.
    Возвращает ID созданного инцидента или None, если дубликат.
    """
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    # Проверяем, нет ли уже открытого инцидента с таким target
    c.execute(
        "SELECT id FROM incidents WHERE target = ? AND status != 'resolved'",
        (target,)
    )
    if c.fetchone():
        conn.close()
        logger.debug(f"Инцидент для target '{target}' уже существует, пропускаем")
        return None

    incident_id = generate_incident_id()
    c.execute(
        "INSERT INTO incidents (id, importance, status, description, target) VALUES (?, ?, ?, ?, ?)",
        (incident_id, importance, "registered", description, target)
    )
    conn.commit()
    conn.close()
    logger.info(f"Создан инцидент {incident_id} (target: {target})")
    return incident_id


def update_incident_status(incident_id: str, new_status: str) -> bool:
    """Обновляет статус инцидента. Возвращает True, если запись обновлена."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        "UPDATE incidents SET status = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
        (new_status, incident_id)
    )
    updated = c.rowcount > 0
    conn.commit()
    conn.close()
    if updated:
        logger.info(f"Статус инцидента {incident_id} изменён на '{new_status}'")
    return updated


def update_incident_description(incident_id: str, new_description: str) -> bool:
    """Обновляет описание инцидента. Возвращает True, если запись обновлена."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        "UPDATE incidents SET description = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
        (new_description, incident_id)
    )
    updated = c.rowcount > 0
    conn.commit()
    conn.close()
    if updated:
        logger.info(f"Описание инцидента {incident_id} обновлено")
    return updated


def get_incident(incident_id: str) -> Optional[Dict[str, Any]]:
    """Возвращает данные инцидента по ID."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        "SELECT id, importance, status, description, target, message_id, created_at, updated_at FROM incidents WHERE id = ?",
        (incident_id,)
    )
    row = c.fetchone()
    conn.close()
    if row:
        return {
            "id": row[0],
            "importance": row[1],
            "status": row[2],
            "description": row[3],
            "target": row[4],
            "message_id": row[5],
            "created_at": row[6],
            "updated_at": row[7]
        }
    return None


def get_active_incidents() -> List[Dict[str, Any]]:
    """Возвращает список активных инцидентов (статусы: registered, in_progress)."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        "SELECT id, importance, status, description, target, message_id, created_at, updated_at "
        "FROM incidents WHERE status IN ('registered', 'in_progress') ORDER BY created_at DESC"
    )
    rows = c.fetchall()
    conn.close()
    return [
        {
            "id": row[0],
            "importance": row[1],
            "status": row[2],
            "description": row[3],
            "target": row[4],
            "message_id": row[5],
            "created_at": row[6],
            "updated_at": row[7]
        }
        for row in rows
    ]


def set_incident_message_id(incident_id: str, message_id: int) -> None:
    """Сохраняет ID сообщения в канале для инцидента."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        "UPDATE incidents SET message_id = ? WHERE id = ?",
        (message_id, incident_id)
    )
    conn.commit()
    conn.close()
    logger.debug(f"Для инцидента {incident_id} сохранён message_id={message_id}")


# ---------------------------- Администраторы ----------------------------
def is_admin(telegram_id: int) -> bool:
    """Проверяет, является ли пользователь администратором."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT 1 FROM admins WHERE telegram_id = ?", (telegram_id,))
    exists = c.fetchone() is not None
    conn.close()
    return exists


def add_admin(telegram_id: int) -> None:
    """Добавляет администратора (если ещё не существует)."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("INSERT OR IGNORE INTO admins (telegram_id) VALUES (?)", (telegram_id,))
    conn.commit()
    conn.close()
    logger.info(f"Администратор {telegram_id} добавлен")


def remove_admin(telegram_id: int) -> bool:
    """Удаляет администратора. Возвращает True, если запись существовала."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("DELETE FROM admins WHERE telegram_id = ?", (telegram_id,))
    deleted = c.rowcount > 0
    conn.commit()
    conn.close()
    if deleted:
        logger.info(f"Администратор {telegram_id} удалён")
    return deleted


def get_all_admins() -> List[int]:
    """Возвращает список Telegram ID всех администраторов."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT telegram_id FROM admins")
    rows = c.fetchall()
    conn.close()
    return [row[0] for row in rows]


# ---------------------------- Ноды ----------------------------
def sync_nodes_from_config(nodes_config: List[Dict[str, Any]]) -> None:
    """
    Синхронизирует таблицу nodes с конфигурацией.
    Добавляет новые ноды, обновляет существующие (по name).
    """
    if not nodes_config:
        return
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    for node in nodes_config:
        c.execute(
            "INSERT OR REPLACE INTO nodes (name, ip, port) VALUES (?, ?, ?)",
            (node['name'], node['ip'], node['port'])
        )
    conn.commit()
    conn.close()
    logger.info(f"Синхронизировано {len(nodes_config)} нод")


def get_all_nodes() -> List[Dict[str, Any]]:
    """Возвращает список всех нод."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT name, ip, port FROM nodes ORDER BY name")
    rows = c.fetchall()
    conn.close()
    return [{"name": row[0], "ip": row[1], "port": row[2]} for row in rows]


def add_node(name: str, ip: str, port: int) -> None:
    """Добавляет новую ноду (или обновляет существующую)."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        "INSERT OR REPLACE INTO nodes (name, ip, port) VALUES (?, ?, ?)",
        (name, ip, port)
    )
    conn.commit()
    conn.close()
    logger.info(f"Нода '{name}' добавлена/обновлена")


def delete_node(name: str) -> bool:
    """Удаляет ноду по имени."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("DELETE FROM nodes WHERE name = ?", (name,))
    deleted = c.rowcount > 0
    conn.commit()
    conn.close()
    if deleted:
        logger.info(f"Нода '{name}' удалена")
    return deleted


# ---------------------------- Сайты маскировки ----------------------------
def sync_masking_sites_from_config(sites_config: List[Dict[str, Any]]) -> None:
    """
    Синхронизирует таблицу masking_sites с конфигурацией.
    Добавляет новые сайты, обновляет существующие (по url).
    """
    if not sites_config:
        return
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    for site in sites_config:
        c.execute(
            "INSERT OR REPLACE INTO masking_sites (url, expected_content) VALUES (?, ?)",
            (site['url'], site.get('expected_content'))
        )
    conn.commit()
    conn.close()
    logger.info(f"Синхронизировано {len(sites_config)} сайтов маскировки")


def get_all_masking_sites() -> List[Dict[str, Any]]:
    """Возвращает список всех сайтов маскировки."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT url, expected_content FROM masking_sites ORDER BY url")
    rows = c.fetchall()
    conn.close()
    return [{"url": row[0], "expected_content": row[1]} for row in rows]


def add_masking_site(url: str, expected_content: Optional[str] = None) -> None:
    """Добавляет или обновляет сайт маскировки."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        "INSERT OR REPLACE INTO masking_sites (url, expected_content) VALUES (?, ?)",
        (url, expected_content)
    )
    conn.commit()
    conn.close()
    logger.info(f"Сайт маскировки '{url}' добавлен/обновлён")


def delete_masking_site(url: str) -> bool:
    """Удаляет сайт маскировки по URL."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("DELETE FROM masking_sites WHERE url = ?", (url,))
    deleted = c.rowcount > 0
    conn.commit()
    conn.close()
    if deleted:
        logger.info(f"Сайт маскировки '{url}' удалён")
    return deleted


# ---------------------------- Xray Inbounds ----------------------------
def sync_inbounds_from_config(inbounds_config: List[Dict[str, Any]]) -> None:
    """
    Синхронизирует таблицу xray_inbounds с конфигурацией.
    Добавляет новые inbound'ы, обновляет существующие (по name).
    """
    if not inbounds_config:
        return
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    for inbound in inbounds_config:
        settings_json = json.dumps(inbound.get('settings', {}))
        c.execute(
            "INSERT OR REPLACE INTO xray_inbounds (name, protocol, settings) VALUES (?, ?, ?)",
            (inbound['name'], inbound.get('protocol', 'vmess'), settings_json)
        )
    conn.commit()
    conn.close()
    logger.info(f"Синхронизировано {len(inbounds_config)} Xray inbound'ов")


def get_all_inbounds() -> List[Dict[str, Any]]:
    """Возвращает список всех Xray inbound'ов."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT name, protocol, settings FROM xray_inbounds ORDER BY name")
    rows = c.fetchall()
    conn.close()
    result = []
    for row in rows:
        try:
            settings = json.loads(row[2])
        except:
            settings = {}
        result.append({
            "name": row[0],
            "protocol": row[1],
            "settings": settings
        })
    return result


def add_inbound(name: str, protocol: str, settings: Dict[str, Any]) -> None:
    """Добавляет или обновляет Xray inbound."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    settings_json = json.dumps(settings)
    c.execute(
        "INSERT OR REPLACE INTO xray_inbounds (name, protocol, settings) VALUES (?, ?, ?)",
        (name, protocol, settings_json)
    )
    conn.commit()
    conn.close()
    logger.info(f"Xray inbound '{name}' добавлен/обновлён")


def delete_inbound(name: str) -> bool:
    """Удаляет Xray inbound по имени."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("DELETE FROM xray_inbounds WHERE name = ?", (name,))
    deleted = c.rowcount > 0
    conn.commit()
    conn.close()
    if deleted:
        logger.info(f"Xray inbound '{name}' удалён")
    return deleted
