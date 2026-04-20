#!/usr/bin/env python3
"""
Главный модуль Telegram-бота для мониторинга 3x-ui.
Использует pyTelegramBotAPI (telebot).
"""

import json
import logging
import threading
import time
import schedule
from datetime import datetime
from typing import Dict, Optional, List, Any

import telebot
from telebot import types, apihelper

from py3xui import Api, Client

from db import (
    init_db, get_user, get_all_users,
    sync_nodes_from_config, sync_masking_sites_from_config,
    get_all_nodes, get_all_masking_sites,
    add_incident, get_incident, set_incident_message_id,
    add_admin, is_admin
)
from checks import check_node, check_website

# ------------------------------------------------------------------
# Настройка логирования
# ------------------------------------------------------------------
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ------------------------------------------------------------------
# Загрузка конфигурации
# ------------------------------------------------------------------
def load_config() -> Dict[str, Any]:
    with open("config.json", "r", encoding="utf-8") as f:
        return json.load(f)

CONFIG = load_config()
GLOBAL = CONFIG["global_settings"]

TELEGRAM_TOKEN = GLOBAL["telegram_token"]
PANEL_HOST = GLOBAL["panel_host"]
PANEL_USER = GLOBAL["panel_username"]
PANEL_PASS = GLOBAL["panel_password"]
SUB_BASE = GLOBAL["subscription_base_url"]
INCIDENT_CHANNEL = GLOBAL["incident_channel"]
REPORT_INTERVAL_HOURS = GLOBAL.get("report_interval_hours", 1)
PING_TIMEOUT = GLOBAL.get("ping_timeout", 2)
PING_COUNT = GLOBAL.get("ping_count", 1)

PROXY = GLOBAL.get("telegram_proxy")
if PROXY:
    # Настройка прокси для всех запросов telebot
    apihelper.proxy = {'http': PROXY, 'https': PROXY}
    logger.info(f"Используется прокси: {PROXY}")

# Создаём бота
bot = telebot.TeleBot(TELEGRAM_TOKEN, parse_mode="Markdown")

# Инициализация БД
init_db()
sync_nodes_from_config(CONFIG.get("nodes", []))
sync_masking_sites_from_config(CONFIG.get("masking_sites", []))

for admin_id in GLOBAL.get("admin_ids", []):
    add_admin(admin_id)
    logger.info(f"Добавлен администратор: {admin_id}")

# Создаём бота
bot = telebot.TeleBot(TELEGRAM_TOKEN, parse_mode="Markdown")

# ------------------------------------------------------------------
# Вспомогательные функции 3x-ui
# ------------------------------------------------------------------
def get_api_client() -> Api:
    api = Api(PANEL_HOST, PANEL_USER, PANEL_PASS)
    api.login()
    return api

def get_client_by_email(inbound_id: int, email: str) -> Optional[Client]:
    api = get_api_client()
    try:
        inbound = api.inbound.get_by_id(inbound_id)
        for client in inbound.settings.clients:
            if client.email == email:
                return client
        return None
    except Exception as e:
        logger.error(f"Ошибка получения клиента {email}: {e}")
        return None

def get_client_traffic(client: Client):
    api = get_api_client()
    data = None
    if client.id:
        try:
            data = api.client.get_traffic_by_id(client.id)
        except:
            pass
    if data is None:
        try:
            data = api.client.get_traffic_by_email(client.email)
        except:
            pass

    up = down = total = 0
    if isinstance(data, list):
        data = data[0] if data else {}
    if isinstance(data, dict):
        up = data.get('up', 0)
        down = data.get('down', 0)
        total = data.get('total', 0)
    elif hasattr(data, 'up'):
        up = data.up
        down = data.down
        total = data.total

    class Traffic: pass
    t = Traffic()
    t.up = up
    t.down = down
    t.total = total
    return t

def format_bytes(num: int) -> str:
    for unit in ['Б', 'КБ', 'МБ', 'ГБ', 'ТБ']:
        if abs(num) < 1024.0:
            return f"{num:.2f} {unit}"
        num /= 1024.0
    return f"{num:.2f} ПБ"

def format_expiry(expiry_timestamp_ms: int) -> str:
    if expiry_timestamp_ms == 0:
        return "∞ (без ограничения)"
    dt = datetime.fromtimestamp(expiry_timestamp_ms / 1000.0)
    return dt.strftime("%d.%m.%Y %H:%M")

# ------------------------------------------------------------------
# Работа с каналом инцидентов
# ------------------------------------------------------------------
def post_incident_to_channel(incident: Dict[str, Any]) -> Optional[int]:
    if not INCIDENT_CHANNEL:
        return None
    text = (
        f"🚨 **Инцидент:** `{incident['id']}`\n"
        f"📌 Важность: {incident['importance']}\n"
        f"📊 Статус: {incident['status']}\n\n"
        f"📝 Описание:\n{incident['description']}"
    )
    try:
        msg = bot.send_message(INCIDENT_CHANNEL, text, parse_mode="Markdown")
        return msg.message_id
    except Exception as e:
        logger.error(f"Ошибка отправки в канал: {e}")
        return None

def update_incident_post(incident: Dict[str, Any]):
    if not INCIDENT_CHANNEL or not incident.get("message_id"):
        return
    text = (
        f"🚨 **Инцидент:** `{incident['id']}`\n"
        f"📌 Важность: {incident['importance']}\n"
        f"📊 Статус: {incident['status']}\n\n"
        f"📝 Описание:\n{incident['description']}"
    )
    try:
        bot.edit_message_text(
            chat_id=INCIDENT_CHANNEL,
            message_id=incident["message_id"],
            text=text,
            parse_mode="Markdown"
        )
    except Exception as e:
        logger.error(f"Ошибка редактирования поста: {e}")

# ------------------------------------------------------------------
# Клавиатуры
# ------------------------------------------------------------------
def main_menu_keyboard():
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("📊 Статистика", callback_data="status"))
    markup.add(types.InlineKeyboardButton("🔗 Ссылка на подписку", callback_data="link"))
    markup.add(types.InlineKeyboardButton("ℹ️ Помощь", callback_data="help"))
    return markup

def back_to_menu_keyboard():
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("◀️ Назад в меню", callback_data="menu"))
    return markup

# ------------------------------------------------------------------
# Обработчики команд
# ------------------------------------------------------------------
@bot.message_handler(commands=['start'])
def start(message: types.Message):
    user_id = message.from_user.id
    logger.info(f"Получена команда /start от {user_id}")

    user = get_user(user_id)
    if not user:
        bot.reply_to(message, "⛔ У вас нет доступа к этому боту.")
        return

    markup = main_menu_keyboard()
    if is_admin(user_id):
        markup.add(types.InlineKeyboardButton("🔧 Админ-панель", callback_data="admin_menu"))

    bot.send_message(
        message.chat.id,
        "👋 **Добро пожаловать в панель мониторинга!**\nВыберите действие:",
        reply_markup=markup
    )

@bot.callback_query_handler(func=lambda call: True)
def handle_callback(call: types.CallbackQuery):
    user_id = call.from_user.id
    data = call.data

    # Админские колбэки обрабатываются в отдельном модуле
    if data.startswith("admin_"):
        # Будет обработано в admin.py
        return

    user = get_user(user_id)
    if not user:
        bot.edit_message_text("⛔ Доступ запрещён.", call.message.chat.id, call.message.message_id)
        return

    if data == "menu":
        markup = main_menu_keyboard()
        if is_admin(user_id):
            markup.add(types.InlineKeyboardButton("🔧 Админ-панель", callback_data="admin_menu"))
        bot.edit_message_text(
            "👋 **Главное меню**\nВыберите действие:",
            call.message.chat.id,
            call.message.message_id,
            reply_markup=markup
        )
        return

    if data == "help":
        help_text = (
            "📌 **Доступные возможности:**\n"
            "• *Статистика* — текущий расход трафика и срок действия подписки.\n"
            "• *Ссылка на подписку* — URL для импорта в клиент.\n\n"
        )
        bot.edit_message_text(
            help_text,
            call.message.chat.id,
            call.message.message_id,
            reply_markup=back_to_menu_keyboard()
        )
        return

    inbound_id = user["inbound_id"]
    client_email = user["client_email"]

    client = get_client_by_email(inbound_id, client_email)
    if not client:
        bot.edit_message_text(
            f"❌ Клиент `{client_email}` не найден в inbound {inbound_id}.",
            call.message.chat.id,
            call.message.message_id,
            reply_markup=back_to_menu_keyboard()
        )
        return

    if data == "status":
        bot.edit_message_text("⏳ Запрос данных с сервера...", call.message.chat.id, call.message.message_id)
        try:
            traffic = get_client_traffic(client)
            up = format_bytes(traffic.up)
            down = format_bytes(traffic.down)
            total = format_bytes(traffic.total)
            expiry = format_expiry(client.expiry_time)
            total_quota = format_bytes(client.total_gb * 1024**3) if client.total_gb > 0 else "∞"

            status_text = (
                f"📊 **Статистика подписки** `{client_email}`\n"
                f"⬆️ Отправлено: {up}\n"
                f"⬇️ Получено: {down}\n"
                f"📦 Всего передано: {total}\n"
                f"📉 Лимит трафика: {total_quota}\n"
                f"⏳ Истекает: {expiry}\n"
                f"🕒 Обновлено: {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}"
            )
            bot.edit_message_text(
                status_text,
                call.message.chat.id,
                call.message.message_id,
                reply_markup=back_to_menu_keyboard()
            )
        except Exception as e:
            logger.error(f"Ошибка получения статуса: {e}")
            bot.edit_message_text(
                "❌ Не удалось получить статистику.",
                call.message.chat.id,
                call.message.message_id,
                reply_markup=back_to_menu_keyboard()
            )

    elif data == "link":
        sub_url = f"{SUB_BASE}{user['subscription_path']}"
        bot.edit_message_text(
            f"🔗 **Ваша ссылка для подписки:**\n`{sub_url}`\n\n"
            "⚠️ Никому не передавайте эту ссылку!",
            call.message.chat.id,
            call.message.message_id,
            reply_markup=back_to_menu_keyboard()
        )

    bot.answer_callback_query(call.id)

# ------------------------------------------------------------------
# Фоновые задачи (запускаются в отдельном потоке)
# ------------------------------------------------------------------
def scheduled_full_check():
    logger.info("Запуск плановой проверки нод и сайтов...")
    nodes = get_all_nodes()
    for node in nodes:
        target = f"node:{node['name']}"
        alive = check_node(node['ip'], node['port'], timeout=PING_TIMEOUT)
        if not alive:
            incident_id = add_incident(
                importance="high",
                description=f"Нода **{node['name']}** ({node['ip']}:{node['port']}) недоступна.",
                target=target
            )
            if incident_id:
                incident = get_incident(incident_id)
                msg_id = post_incident_to_channel(incident)
                if msg_id:
                    set_incident_message_id(incident_id, msg_id)
                logger.warning(f"Создан инцидент {incident_id} для ноды {node['name']}")

    sites = get_all_masking_sites()
    for site in sites:
        target = f"site:{site['url']}"
        ok = check_website(site['url'], site.get('expected_content'))
        if not ok:
            incident_id = add_incident(
                importance="medium",
                description=f"Сайт маскировки **{site['url']}** недоступен или контент не совпадает.",
                target=target
            )
            if incident_id:
                incident = get_incident(incident_id)
                msg_id = post_incident_to_channel(incident)
                if msg_id:
                    set_incident_message_id(incident_id, msg_id)
                logger.warning(f"Создан инцидент {incident_id} для сайта {site['url']}")
    logger.info("Плановая проверка завершена")

def scheduler_thread():
    """Поток для запуска периодических задач."""
    schedule.every(1).hours.do(scheduled_full_check)

    # Первый запуск через 10 секунд
    threading.Timer(10, scheduled_full_check).start()

    while True:
        schedule.run_pending()
        time.sleep(1)

# ------------------------------------------------------------------
# Запуск
# ------------------------------------------------------------------
if __name__ == "__main__":
    logger.info("🤖 Бот запущен...")
    # Запускаем планировщик в отдельном потоке
    threading.Thread(target=scheduler_thread, daemon=True).start()
    # Запускаем бота
    bot.infinity_polling()
