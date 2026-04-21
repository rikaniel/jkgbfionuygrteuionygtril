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

# Импортируем наш кастомный API клиент вместо py3xui
from custom_xui_api import get_xui_api, XUIAPI

from db import (
    init_db, get_user, get_all_users,
    sync_nodes_from_config, sync_masking_sites_from_config, sync_inbounds_from_config,
    get_all_nodes, get_all_masking_sites, get_all_inbounds,
    add_incident, get_incident, set_incident_message_id,
    add_admin, is_admin, get_inbound_by_name
)
from checks import check_node, check_website, check_geo_resource

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
GEOIP_URL = GLOBAL.get("geoip_url")
GEOSITE_URL = GLOBAL.get("geosite_url")

PROXY = GLOBAL.get("telegram_proxy")
PANEL_PROXY = GLOBAL.get("panel_proxy")  # Отдельный прокси для панели (может быть null)

if PROXY:
    # Настройка прокси для всех запросов telebot
    apihelper.proxy = {'http': PROXY, 'https': PROXY}
    logger.info(f"Используется прокси для Telegram: {PROXY}")

# Настройка прокси для 3x-ui API (если указан panel_proxy, иначе используем telegram_proxy)
api_proxy = PANEL_PROXY if PANEL_PROXY else PROXY
if api_proxy:
    import os
    # Преобразуем socks5://127.0.0.1:10808 в формат для requests
    if api_proxy.startswith("socks5://"):
        proxy_for_requests = api_proxy.replace("socks5://", "socks5h://")
    else:
        proxy_for_requests = api_proxy
    os.environ["HTTP_PROXY"] = proxy_for_requests
    os.environ["HTTPS_PROXY"] = proxy_for_requests
    logger.info(f"Прокси для 3x-ui API: {proxy_for_requests}")
else:
    api_proxy = None
    logger.info("3x-ui API работает без прокси")

# Создаём бота
bot = telebot.TeleBot(TELEGRAM_TOKEN, parse_mode="Markdown")

# Инициализация БД
init_db()
sync_nodes_from_config(CONFIG.get("nodes", []))
sync_masking_sites_from_config(CONFIG.get("masking_sites", []))
sync_inbounds_from_config(CONFIG.get("xray_inbounds", []))

for admin_id in GLOBAL.get("admin_ids", []):
    add_admin(admin_id)
    logger.info(f"Добавлен администратор: {admin_id}")

# ------------------------------------------------------------------
# Вспомогательные функции 3x-ui
# ------------------------------------------------------------------
# Глобальный API клиент с автоматическим переподключением
_api_client: Optional[XUIAPI] = None
_api_last_login_time = 0
_API_SESSION_TTL = 300  # 5 минут

def get_api_client() -> XUIAPI:
    """Возвращает глобальный API клиент с кэшированием сессии."""
    global _api_client, _api_last_login_time
    
    current_time = time.time()
    
    # Если клиент существует и сессия ещё действительна - возвращаем его
    if _api_client is not None and (current_time - _api_last_login_time) < _API_SESSION_TTL:
        if _api_client.is_logged_in:
            logger.debug("Используется кэшированная сессия 3x-ui API")
            return _api_client
    
    # Создаём нового клиента через нашу функцию
    try:
        logger.info(f"Попытка входа в 3x-ui панель: {PANEL_HOST} (user: {PANEL_USER})")
        _api_client = get_xui_api(PANEL_HOST, PANEL_USER, PANEL_PASS, api_proxy)
        _api_last_login_time = current_time
        
        if _api_client.is_logged_in:
            logger.info("✅ Успешный вход в 3x-ui панель")
            return _api_client
        else:
            logger.error("❌ Не удалось войти в 3x-ui панель")
            raise Exception("Login failed")
            
    except Exception as e:
        logger.error(f"❌ Ошибка входа в 3x-ui панель: {e}", exc_info=True)
        raise

def get_client_by_email(inbound_name: str, email: str) -> Optional[Dict]:
    """Получает клиента по имени inbound и email через 3x-ui API."""
    try:
        api = get_api_client()
        
        # Наш кастомный API сам ищет клиента по email во всех inbound'ах
        client_data = api.get_client_by_email(email)
        
        if client_data:
            # Проверяем, что клиент из нужного inbound
            client_inbound_name = client_data.get('inbound_remark', '')
            if str(client_inbound_name) == str(inbound_name) or str(client_data.get('inbound_id')) == str(inbound_name):
                logger.info(f"✅ Клиент {email} найден в inbound '{inbound_name}'")
                return client_data
            else:
                logger.warning(f"Клиент {email} найден в другом inbound: '{client_inbound_name}' (ожидался '{inbound_name}')")
                return None
        
        logger.warning(f"❌ Клиент {email} не найден в панели")
        return None
        
    except Exception as e:
        logger.error(f"Ошибка получения клиента {email}: {e}", exc_info=True)
        # Пробуем пересоздать клиента при ошибке сессии
        try:
            global _api_client, _api_last_login_time
            _api_client = get_xui_api(PANEL_HOST, PANEL_USER, PANEL_PASS, api_proxy)
            _api_last_login_time = time.time()
            
            # Повторяем поиск
            client_data = _api_client.get_client_by_email(email)
            if client_data:
                return client_data
        except Exception as e2:
            logger.error(f"Повторная ошибка получения клиента {email}: {e2}", exc_info=True)
        return None

def get_client_traffic(client_data: Dict) -> Optional[Dict]:
    """Получает трафик клиента из API."""
    api = get_api_client()
    
    inbound_id = client_data.get('inbound_id')
    email = client_data.get('email')
    
    if not inbound_id or not email:
        logger.error("Нет inbound_id или email для получения трафика")
        return None
    
    # Получаем статистику через наш API
    stats = api.get_client_stats(inbound_id, email)
    
    if stats:
        return {
            'up': stats.get('up', 0),
            'down': stats.get('down', 0),
            'total': stats.get('total', 0)
        }
    
    # Если не получили статистику, возвращаем дефолтные значения
    logger.warning(f"Не удалось получить статистику для {email}, возвращаем нули")
    return {'up': 0, 'down': 0, 'total': 0}

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
    markup = types.ReplyKeyboardMarkup(row_width=2, resize_keyboard=True)
    markup.add("📊 Статистика", "🔗 Ссылка на подписку")
    markup.add("ℹ️ Помощь")
    return markup

def back_to_menu_keyboard():
    markup = types.ReplyKeyboardMarkup(row_width=1, resize_keyboard=True)
    markup.add("◀️ Назад в меню")
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
        markup.add("🔧 Админ-панель")

    bot.send_message(
        message.chat.id,
        "👋 **Добро пожаловать в панель мониторинга!**\nВыберите действие:",
        reply_markup=markup
    )

@bot.message_handler(func=lambda message: True)
def handle_message(message: types.Message):
    user_id = message.from_user.id
    text = message.text

    # Игнорируем команды (они обрабатываются отдельно)
    if text.startswith('/'):
        return

    user = get_user(user_id)
    if not user:
        bot.reply_to(message, "⛔ Доступ запрещён.")
        return

    if text == "◀️ Назад в меню":
        markup = main_menu_keyboard()
        if is_admin(user_id):
            markup.add("🔧 Админ-панель")
        bot.send_message(
            message.chat.id,
            "👋 **Главное меню**\nВыберите действие:",
            reply_markup=markup
        )
        return

    if text == "ℹ️ Помощь":
        help_text = (
            "📌 **Доступные возможности:**\n"
            "• *Статистика* — текущий расход трафика и срок действия подписки.\n"
            "• *Ссылка на подписку* — URL для импорта в клиент.\n\n"
        )
        bot.send_message(
            message.chat.id,
            help_text,
            reply_markup=back_to_menu_keyboard()
        )
        return

    inbound_name = user.get("inbound_name") or user.get("inbound_id")
    client_email = user["client_email"]

    if not inbound_name:
        bot.send_message(
            message.chat.id,
            f"❌ Ошибка конфигурации: не указан inbound для пользователя.",
            reply_markup=back_to_menu_keyboard()
        )
        logger.error(f"У пользователя {user_id} не указан inbound_name или inbound_id")
        return

    client = get_client_by_email(inbound_name, client_email)
    if not client:
        bot.send_message(
            message.chat.id,
            f"❌ Клиент `{client_email}` не найден в inbound '{inbound_name}'. Проверьте настройки.",
            reply_markup=back_to_menu_keyboard()
        )
        return

    if text == "📊 Статистика":
        bot.send_message(message.chat.id, "⏳ Запрос данных с сервера...")
        try:
            traffic = get_client_traffic(client)
            if traffic:
                up = format_bytes(traffic['up'])
                down = format_bytes(traffic['down'])
                total = format_bytes(traffic['total'])
            else:
                up = down = total = "0 Б"
            
            # Получаем данные о сроке действия и лимитах из client_data
            expiry_time = client.get('expiryTime', client.get('expiry_time', 0))
            total_gb = client.get('totalGB', client.get('total_gb', 0))
            
            expiry = format_expiry(expiry_time)
            total_quota = format_bytes(total_gb * 1024**3) if total_gb > 0 else "∞"

            status_text = (
                f"📊 **Статистика подписки** `{client_email}`\n"
                f"⬆️ Отправлено: {up}\n"
                f"⬇️ Получено: {down}\n"
                f"📦 Всего передано: {total}\n"
                f"📉 Лимит трафика: {total_quota}\n"
                f"⏳ Истекает: {expiry}\n"
                f"🕒 Обновлено: {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}"
            )
            bot.send_message(
                message.chat.id,
                status_text,
                reply_markup=back_to_menu_keyboard()
            )
        except Exception as e:
            logger.error(f"Ошибка получения статуса: {e}", exc_info=True)
            bot.send_message(
                message.chat.id,
                "❌ Не удалось получить статистику.",
                reply_markup=back_to_menu_keyboard()
            )

    elif text == "🔗 Ссылка на подписку":
        sub_url = f"{SUB_BASE}{user['subscription_path']}"
        bot.send_message(
            message.chat.id,
            f"🔗 **Ваша ссылка для подписки:**\n`{sub_url}`\n\n"
            "⚠️ Никому не передавайте эту ссылку!",
            reply_markup=back_to_menu_keyboard()
        )

    elif text == "🔧 Админ-панель":
        if is_admin(user_id):
            from admin import admin_menu_handler
            admin_menu_handler(message)
        else:
            bot.reply_to(message, "⛔ У вас нет доступа к админ-панели.")

# ------------------------------------------------------------------
# Фоновые задачи (запускаются в отдельном потоке)
# ------------------------------------------------------------------
def scheduled_full_check():
    """Полная проверка всех систем: ноды, сайты, geo-ресурсы."""
    logger.info("Запуск плановой проверки нод и сайтов...")
    
    # Получаем все inbound'ы для прокси-пинга
    inbounds = get_all_inbounds()
    
    # Проверка нод через proxy
    nodes = get_all_nodes()
    for node in nodes:
        target = f"node:{node['name']}"
        # Пинг через первый доступный inbound (proxy)
        alive = check_node(node['ip'], node['port'], timeout=PING_TIMEOUT, inbounds=inbounds)
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

    # Проверка сайтов маскировки
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
    
    # Проверка GeoIP и GeoSite ресурсов
    if GEOIP_URL:
        target = "geo:geoip"
        ok = check_geo_resource(GEOIP_URL)
        if not ok:
            incident_id = add_incident(
                importance="high",
                description=f"GeoIP ресурс **{GEOIP_URL}** недоступен.",
                target=target
            )
            if incident_id:
                incident = get_incident(incident_id)
                msg_id = post_incident_to_channel(incident)
                if msg_id:
                    set_incident_message_id(incident_id, msg_id)
                logger.warning(f"Создан инцидент {incident_id} для GeoIP")
    
    if GEOSITE_URL:
        target = "geo:geosite"
        ok = check_geo_resource(GEOSITE_URL)
        if not ok:
            incident_id = add_incident(
                importance="high",
                description=f"GeoSite ресурс **{GEOSITE_URL}** недоступен.",
                target=target
            )
            if incident_id:
                incident = get_incident(incident_id)
                msg_id = post_incident_to_channel(incident)
                if msg_id:
                    set_incident_message_id(incident_id, msg_id)
                logger.warning(f"Создан инцидент {incident_id} для GeoSite")
    
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
    
    # Регистрируем админские хендлеры
    from admin import register_handlers
    register_handlers(bot, INCIDENT_CHANNEL)
    
    # Запускаем планировщик в отдельном потоке
    threading.Thread(target=scheduler_thread, daemon=True).start()
    # Запускаем бота
    bot.infinity_polling()
