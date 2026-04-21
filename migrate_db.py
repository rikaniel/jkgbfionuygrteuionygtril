#!/usr/bin/env python3
"""
Скрипт миграции базы данных: преобразование inbound_id -> inbound_name
"""
import sqlite3
import json
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DB_PATH = "bot.db"
CONFIG_PATH = "config.json"

def migrate_db():
    """Мигрирует базу данных, заменяя inbound_id на inbound_name."""
    
    # Загружаем конфигурацию для получения маппинга inbound'ов
    try:
        with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
            config = json.load(f)
    except Exception as e:
        logger.error(f"Не удалось загрузить config.json: {e}")
        return
    
    # Создаём маппинг ID -> name из config
    id_to_name = {}
    inbounds_config = config.get('xray_inbounds', [])
    for idx, inbound in enumerate(inbounds_config):
        # Индексы начинаются с 1 (как в старом коде)
        id_to_name[idx + 1] = inbound['name']
        logger.info(f"Inbound ID {idx + 1} -> '{inbound['name']}'")
    
    # Подключаемся к БД
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    # Проверяем, существует ли таблица users
    c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='users'")
    if not c.fetchone():
        logger.info("Таблица users не существует, миграция не требуется")
        conn.close()
        return
    
    # Проверяем структуру таблицы
    c.execute("PRAGMA table_info(users)")
    columns = [col[1] for col in c.fetchall()]
    
    if 'inbound_name' in columns:
        logger.info("Колонка inbound_name уже существует, миграция не требуется")
        conn.close()
        return
    
    if 'inbound_id' not in columns:
        logger.info("Колонка inbound_id не найдена, миграция не требуется")
        conn.close()
        return
    
    # Создаём временную таблицу с новой структурой
    logger.info("Создание временной таблицы...")
    c.execute('''
        CREATE TABLE IF NOT EXISTS users_new (
            telegram_id INTEGER PRIMARY KEY,
            inbound_name TEXT NOT NULL,
            client_email TEXT NOT NULL,
            subscription_path TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Копируем данные с преобразованием
    c.execute("SELECT telegram_id, inbound_id, client_email, subscription_path, created_at FROM users")
    rows = c.fetchall()
    
    migrated_count = 0
    for row in rows:
        tg_id, inbound_id, email, path, created_at = row
        
        # Преобразуем ID в name
        inbound_name = id_to_name.get(inbound_id, f"inbound_{inbound_id}")
        
        c.execute(
            "INSERT INTO users_new (telegram_id, inbound_name, client_email, subscription_path, created_at) VALUES (?, ?, ?, ?, ?)",
            (tg_id, inbound_name, email, path, created_at)
        )
        migrated_count += 1
        logger.info(f"Мигрирован пользователь {tg_id}: inbound_id={inbound_id} -> inbound_name='{inbound_name}'")
    
    # Удаляем старую таблицу и переименовываем новую
    c.execute("DROP TABLE users")
    c.execute("ALTER TABLE users_new RENAME TO users")
    
    conn.commit()
    conn.close()
    
    logger.info(f"✅ Миграция завершена! Мигрировано {migrated_count} пользователей.")

if __name__ == "__main__":
    migrate_db()
