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
            inbound_name TEXT NOT NULL,
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

    # Статус нод для uptime/downtime отслеживания
    c.execute('''
        CREATE TABLE IF NOT EXISTS node_status (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            node_name TEXT NOT NULL,
            status TEXT NOT NULL,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            response_time_ms REAL
        )
    ''')

    # История инцидентов для статистики
    c.execute('''
        CREATE TABLE IF NOT EXISTS incident_stats (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            incident_id TEXT NOT NULL,
            event_type TEXT NOT NULL,
            old_status TEXT,
            new_status TEXT,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
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
        "SELECT telegram_id, inbound_name, client_email, subscription_path, created_at FROM users WHERE telegram_id = ?",
        (telegram_id,)
    )
    row = c.fetchone()
    conn.close()
    if row:
        return {
            "telegram_id": row[0],
            "inbound_name": row[1],
            "client_email": row[2],
            "subscription_path": row[3],
            "created_at": row[4]
        }
    return None


def add_user(telegram_id: int, inbound_name: str, client_email: str, subscription_path: str) -> None:
    """Добавляет или обновляет пользователя."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        "INSERT OR REPLACE INTO users (telegram_id, inbound_name, client_email, subscription_path) VALUES (?, ?, ?, ?)",
        (telegram_id, inbound_name, client_email, subscription_path)
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
    c.execute("SELECT telegram_id, inbound_name, client_email, subscription_path, created_at FROM users ORDER BY created_at")
    rows = c.fetchall()
    conn.close()
    return [
        {
            "telegram_id": row[0],
            "inbound_name": row[1],
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


def get_inbound_by_name(name: str) -> Optional[Dict[str, Any]]:
    """Возвращает данные inbound по имени."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT name, protocol, settings FROM xray_inbounds WHERE name = ?", (name,))
    row = c.fetchone()
    conn.close()
    if row:
        try:
            settings = json.loads(row[2])
        except:
            settings = {}
        return {
            "name": row[0],
            "protocol": row[1],
            "settings": settings
        }
    return None


# ---------------------------- Node Status & Uptime ----------------------------
def log_node_status(node_name: str, status: str, response_time_ms: float = None) -> None:
    """Логирует статус ноды для расчёта uptime."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        "INSERT INTO node_status (node_name, status, response_time_ms) VALUES (?, ?, ?)",
        (node_name, status, response_time_ms)
    )
    conn.commit()
    conn.close()

def get_node_uptime(node_name: str, hours: int = 24) -> Dict[str, Any]:
    """
    Рассчитывает uptime ноды за последние N часов.
    Возвращает: {'uptime_percent': float, 'total_checks': int, 'up_checks': int, 'downtime_events': list}
    """
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    # Получаем все проверки за последние N часов
    c.execute("""
        SELECT status, timestamp, response_time_ms 
        FROM node_status 
        WHERE node_name = ? 
        AND timestamp >= datetime('now', '-' || ? || ' hours')
        ORDER BY timestamp DESC
    """, (node_name, hours))
    rows = c.fetchall()
    conn.close()
    
    if not rows:
        return {'uptime_percent': 100.0, 'total_checks': 0, 'up_checks': 0, 'downtime_events': []}
    
    total_checks = len(rows)
    up_checks = sum(1 for r in rows if r[0] == 'up')
    uptime_percent = (up_checks / total_checks * 100) if total_checks > 0 else 100.0
    
    # Находим события downtime
    downtime_events = []
    prev_status = None
    for row in reversed(rows):  # chronological order
        status, ts, rtt = row
        if prev_status == 'up' and status == 'down':
            downtime_events.append({'start': ts, 'end': None})
        elif prev_status == 'down' and status == 'up' and downtime_events:
            downtime_events[-1]['end'] = ts
        prev_status = status
    
    return {
        'uptime_percent': round(uptime_percent, 2),
        'total_checks': total_checks,
        'up_checks': up_checks,
        'downtime_events': downtime_events
    }

def get_all_nodes_uptime(hours: int = 24) -> Dict[str, Dict[str, Any]]:
    """Возвращает uptime всех нод за последние N часов."""
    nodes = get_all_nodes()
    result = {}
    for node in nodes:
        result[node['name']] = get_node_uptime(node['name'], hours)
    return result


# ---------------------------- Incident Stats ----------------------------
def log_incident_event(incident_id: str, event_type: str, old_status: str = None, new_status: str = None) -> None:
    """Логирует событие инцидента для статистики."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        "INSERT INTO incident_stats (incident_id, event_type, old_status, new_status) VALUES (?, ?, ?, ?)",
        (incident_id, event_type, old_status, new_status)
    )
    conn.commit()
    conn.close()

def get_incident_stats(period_days: int = 7) -> Dict[str, Any]:
    """
    Возвращает статистику инцидентов за последние N дней.
    """
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    # Общее количество инцидентов
    c.execute("""
        SELECT COUNT(DISTINCT id) FROM incidents 
        WHERE created_at >= datetime('now', '-' || ? || ' days')
    """, (period_days,))
    total_incidents = c.fetchone()[0]
    
    # По статусам
    c.execute("""
        SELECT status, COUNT(*) FROM incidents 
        WHERE created_at >= datetime('now', '-' || ? || ' days')
        GROUP BY status
    """, (period_days,))
    by_status = dict(c.fetchall())
    
    # По важности
    c.execute("""
        SELECT importance, COUNT(*) FROM incidents 
        WHERE created_at >= datetime('now', '-' || ? || ' days')
        GROUP BY importance
    """, (period_days,))
    by_importance = dict(c.fetchall())
    
    # Среднее время решения (для resolved инцидентов)
    c.execute("""
        SELECT AVG(julianday(updated_at) - julianday(created_at)) * 24 * 60
        FROM incidents 
        WHERE status = 'resolved' 
        AND updated_at >= datetime('now', '-' || ? || ' days')
    """, (period_days,))
    avg_resolution_minutes = c.fetchone()[0]
    
    conn.close()
    
    return {
        'total_incidents': total_incidents,
        'by_status': by_status,
        'by_importance': by_importance,
        'avg_resolution_minutes': round(avg_resolution_minutes, 1) if avg_resolution_minutes else 0
    }

def get_daily_incident_count(days: int = 7) -> List[Dict[str, Any]]:
    """Возвращает количество инцидентов по дням."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        SELECT DATE(created_at), COUNT(*) 
        FROM incidents 
        WHERE created_at >= datetime('now', '-' || ? || ' days')
        GROUP BY DATE(created_at)
        ORDER BY DATE(created_at) DESC
    """, (days,))
    rows = c.fetchall()
    conn.close()
    return [{'date': row[0], 'count': row[1]} for row in rows]
