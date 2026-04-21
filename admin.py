"""
Административная панель для бота на telebot.
Содержит все функции управления: пользователи, инциденты, ноды, сайты, админы.
"""

import logging
from datetime import datetime
from typing import Dict, List, Any

import telebot
from telebot import types

from db import (
    get_user, add_user, delete_user, get_all_users,
    get_incident, get_active_incidents, update_incident_status,
    update_incident_description, add_incident, set_incident_message_id,
    is_admin, add_admin, remove_admin, get_all_admins,
    get_all_nodes, add_node, delete_node,
    get_all_masking_sites, add_masking_site, delete_masking_site,
    get_all_inbounds, add_inbound, delete_inbound
)
from checks import check_node, check_website, check_geo_resource
from main import main_menu_keyboard

logger = logging.getLogger(__name__)

# Глобальные переменные, которые будут установлены при регистрации
INCIDENT_CHANNEL: str = ""
bot: telebot.TeleBot = None

# Временное хранилище для пошаговых операций (в памяти)
user_states = {}

# ---------------------------- Вспомогательные функции ----------------------------
def require_admin(func):
    """Декоратор для проверки прав администратора."""
    def wrapper(message: types.Message):
        if not is_admin(message.from_user.id):
            bot.reply_to(message, "⛔ У вас нет прав администратора.")
            return
        return func(message)
    return wrapper

def safe_edit_or_send(text: str, chat_id: int, message_id: int = None, reply_markup=None, parse_mode="Markdown"):
    """
    Безопасная функция: пытается редактировать сообщение, 
    если не получается - отправляет новое.
    """
    try:
        if message_id:
            return bot.edit_message_text(
                text=text,
                chat_id=chat_id,
                message_id=message_id,
                reply_markup=reply_markup,
                parse_mode=parse_mode
            )
        else:
            return bot.send_message(
                chat_id=chat_id,
                text=text,
                reply_markup=reply_markup,
                parse_mode=parse_mode
            )
    except telebot.apihelper.ApiTelegramException as e:
        if "message can't be edited" in str(e) or "message to edit not found" in str(e):
            # Если нельзя редактировать - отправляем новое сообщение
            return bot.send_message(
                chat_id=chat_id,
                text=text,
                reply_markup=reply_markup,
                parse_mode=parse_mode
            )
        raise

def update_incident_channel_post(incident: Dict[str, Any]):
    """Обновляет или создаёт пост в канале."""
    if not INCIDENT_CHANNEL:
        return
    text = (
        f"🚨 **Инцидент:** `{incident['id']}`\n"
        f"📌 Важность: {incident['importance']}\n"
        f"📊 Статус: {incident['status']}\n\n"
        f"📝 Описание:\n{incident['description']}"
    )
    try:
        if incident.get("message_id"):
            safe_edit_or_send(
                chat_id=INCIDENT_CHANNEL,
                message_id=incident["message_id"],
                text=text,
                parse_mode="Markdown"
            )
        else:
            msg = bot.send_message(INCIDENT_CHANNEL, text, parse_mode="Markdown")
            set_incident_message_id(incident["id"], msg.message_id)
    except Exception as e:
        logger.error(f"Ошибка обновления поста в канале: {e}")

# ---------------------------- Главное меню админа ----------------------------
@require_admin
def admin_command(message: types.Message):
    """Обработчик команды /admin."""
    markup = types.ReplyKeyboardMarkup(row_width=2, resize_keyboard=True)
    markup.add(
        "📋 Активные инциденты",
        "➕ Создать инцидент",
        "👥 Управление пользователями",
        "🌐 Управление нодами",
        "🔗 Сайты маскировки",
        "👑 Администраторы",
        "❌ Закрыть"
    )
    bot.send_message(
        message.chat.id,
        "🔧 **Административная панель**\nВыберите раздел:",
        reply_markup=markup
    )

def admin_menu_handler(message: types.Message):
    """Обработчик кнопки 'Админ-панель' из главного меню."""
    admin_command(message)

# ---------------------------- Обработчик текстовых сообщений админки ----------------------------
@require_admin
def admin_text_handler(message: types.Message):
    """Обработчик текстовых кнопок ReplyKeyboard для админ-панели."""
    text = message.text
    
    if text == "📋 Активные инциденты":
        # Эмуляция колбэка admin_incidents
        class FakeCall:
            def __init__(self, msg):
                self.data = "admin_incidents"
                self.from_user = msg.from_user
                self.message = msg
        admin_callback_handler(FakeCall(message))
    
    elif text == "➕ Создать инцидент":
        class FakeCall:
            def __init__(self, msg):
                self.data = "admin_create_incident"
                self.from_user = msg.from_user
                self.message = msg
        admin_callback_handler(FakeCall(message))
    
    elif text == "👥 Управление пользователями":
        class FakeCall:
            def __init__(self, msg):
                self.data = "admin_users_menu"
                self.from_user = msg.from_user
                self.message = msg
        admin_callback_handler(FakeCall(message))
    
    elif text == "🌐 Управление нодами":
        class FakeCall:
            def __init__(self, msg):
                self.data = "admin_nodes_menu"
                self.from_user = msg.from_user
                self.message = msg
        admin_callback_handler(FakeCall(message))
    
    elif text == "🔗 Сайты маскировки":
        class FakeCall:
            def __init__(self, msg):
                self.data = "admin_sites_menu"
                self.from_user = msg.from_user
                self.message = msg
        admin_callback_handler(FakeCall(message))
    
    elif text == "👑 Администраторы":
        class FakeCall:
            def __init__(self, msg):
                self.data = "admin_admins_menu"
                self.from_user = msg.from_user
                self.message = msg
        admin_callback_handler(FakeCall(message))
    
    elif text == "❌ Закрыть":
        bot.send_message(
            message.chat.id,
            "👋 Главное меню",
            reply_markup=main_menu_keyboard()
        )

# Регистрируем обработчик текстовых сообщений в main.py через decorator

# ---------------------------- Главный обработчик колбэков ----------------------------
def admin_callback_handler(call: types.CallbackQuery):
    """Маршрутизация всех admin_* колбэков."""
    data = call.data
    user_id = call.from_user.id
    if not is_admin(user_id):
        bot.answer_callback_query(call.id, "⛔ Доступ запрещён", show_alert=True)
        return

    # Главное меню
    if data == "admin_menu":
        markup = types.InlineKeyboardMarkup(row_width=1)
        markup.add(
            types.InlineKeyboardButton("📋 Активные инциденты", callback_data="admin_incidents"),
            types.InlineKeyboardButton("➕ Создать инцидент", callback_data="admin_create_incident"),
            types.InlineKeyboardButton("👥 Управление пользователями", callback_data="admin_users_menu"),
            types.InlineKeyboardButton("🌐 Управление нодами", callback_data="admin_nodes_menu"),
            types.InlineKeyboardButton("🔗 Сайты маскировки", callback_data="admin_sites_menu"),
            types.InlineKeyboardButton("👑 Администраторы", callback_data="admin_admins_menu"),
            types.InlineKeyboardButton("❌ Закрыть", callback_data="admin_close")
        )
        safe_edit_or_send(
            "🔧 **Административная панель**\nВыберите раздел:",
            call.message.chat.id,
            call.message.message_id,
            reply_markup=markup
        )
    elif data == "admin_close":
        bot.delete_message(call.message.chat.id, call.message.message_id)

    # Инциденты
    elif data == "admin_create_incident":
        start_create_incident(call)
    elif data == "admin_incidents":
        show_active_incidents(call)
    elif data.startswith("admin_incident_"):
        inc_id = data.replace("admin_incident_", "")
        show_incident_detail(call, inc_id)
    elif data.startswith("admin_inc_status_"):
        inc_id = data.replace("admin_inc_status_", "")
        change_incident_status_menu(call, inc_id)
    elif data.startswith("admin_inc_setstatus_"):
        parts = data.split('_')
        inc_id = parts[3]
        new_status = parts[4]
        set_incident_status(call, inc_id, new_status)
    elif data.startswith("admin_inc_desc_"):
        inc_id = data.replace("admin_inc_desc_", "")
        start_change_description(call, inc_id)
    elif data.startswith("admin_inc_refresh_"):
        inc_id = data.replace("admin_inc_refresh_", "")
        incident = get_incident(inc_id)
        if incident:
            update_incident_channel_post(incident)
            bot.answer_callback_query(call.id, "Пост обновлён")
        show_incident_detail(call, inc_id)

    # Пользователи
    elif data == "admin_users_menu":
        users_menu(call)
    elif data == "admin_users_list":
        list_users(call)
    elif data == "admin_users_add":
        start_add_user(call)
    elif data == "admin_users_delete":
        start_delete_user(call)
    elif data.startswith("admin_user_del_"):
        tg_id = int(data.split('_')[-1])
        confirm_delete_user(call, tg_id)

    # Ноды
    elif data == "admin_nodes_menu":
        nodes_menu(call)
    elif data == "admin_nodes_list":
        list_nodes(call)
    elif data == "admin_nodes_add":
        start_add_node(call)
    elif data == "admin_nodes_delete":
        start_delete_node(call)
    elif data.startswith("admin_node_del_"):
        name = data.replace("admin_node_del_", "")
        confirm_delete_node(call, name)
    elif data == "admin_nodes_check":
        check_all_nodes_action(call)

    # Сайты
    elif data == "admin_sites_menu":
        sites_menu(call)
    elif data == "admin_sites_list":
        list_sites(call)
    elif data == "admin_sites_add":
        start_add_site(call)
    elif data == "admin_sites_delete":
        start_delete_site(call)
    elif data.startswith("admin_site_del_"):
        url = data.replace("admin_site_del_", "")
        confirm_delete_site(call, url)
    elif data == "admin_sites_check":
        check_all_sites_action(call)

    # Админы
    elif data == "admin_admins_menu":
        admins_menu(call)
    elif data == "admin_admins_list":
        list_admins(call)
    elif data == "admin_admins_add":
        start_add_admin(call)
    elif data == "admin_admins_remove":
        start_remove_admin(call)
    elif data.startswith("admin_admin_del_"):
        tg_id = int(data.replace("admin_admin_del_", ""))
        confirm_remove_admin(call, tg_id)

    # Xray Inbounds
    elif data == "admin_inbounds_menu":
        inbounds_menu(call)
    elif data == "admin_inbounds_list":
        list_inbounds(call)
    elif data == "admin_inbounds_add":
        start_add_inbound(call)
    elif data == "admin_inbounds_delete":
        start_delete_inbound(call)
    elif data.startswith("admin_inbound_del_"):
        name = data.replace("admin_inbound_del_", "")
        confirm_delete_inbound(call, name)

    bot.answer_callback_query(call.id)

# ---------------------------- Работа с инцидентами ----------------------------
def show_active_incidents(call: types.CallbackQuery):
    incidents = get_active_incidents()
    if not incidents:
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("◀️ Назад", callback_data="admin_menu"))
        safe_edit_or_send("✅ Нет активных инцидентов.", call.message.chat.id, call.message.message_id, reply_markup=markup)
        return

    markup = types.InlineKeyboardMarkup(row_width=1)
    for inc in incidents[:10]:
        short = (inc['description'][:30] + '...') if len(inc['description']) > 30 else inc['description']
        markup.add(types.InlineKeyboardButton(
            f"{inc['id']} [{inc['status']}] {short}",
            callback_data=f"admin_incident_{inc['id']}"
        ))
    markup.add(types.InlineKeyboardButton("◀️ Назад", callback_data="admin_menu"))
    safe_edit_or_send("📋 **Активные инциденты:**", call.message.chat.id, call.message.message_id, reply_markup=markup)

def show_incident_detail(call: types.CallbackQuery, inc_id: str):
    incident = get_incident(inc_id)
    if not incident:
        safe_edit_or_send("❌ Инцидент не найден.")
        return

    text = (
        f"🚨 **Инцидент:** `{incident['id']}`\n"
        f"📌 Важность: {incident['importance']}\n"
        f"📊 Статус: {incident['status']}\n"
        f"🎯 Цель: {incident['target']}\n"
        f"📅 Создан: {incident['created_at']}\n"
        f"🔄 Обновлён: {incident['updated_at']}\n\n"
        f"📝 Описание:\n{incident['description']}"
    )
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("✏️ Изменить статус", callback_data=f"admin_inc_status_{inc_id}"),
        types.InlineKeyboardButton("📝 Изменить описание", callback_data=f"admin_inc_desc_{inc_id}")
    )
    markup.add(types.InlineKeyboardButton("🔄 Обновить пост", callback_data=f"admin_inc_refresh_{inc_id}"))
    markup.add(types.InlineKeyboardButton("◀️ К списку", callback_data="admin_incidents"))
    safe_edit_or_send(text, call.message.chat.id, call.message.message_id, reply_markup=markup)

def change_incident_status_menu(call: types.CallbackQuery, inc_id: str):
    incident = get_incident(inc_id)
    if not incident:
        return
    statuses = ["registered", "in_progress", "resolved"]
    display = {"registered": "📌 Зарегистрирован", "in_progress": "🔧 В работе", "resolved": "✅ Решено"}
    markup = types.InlineKeyboardMarkup(row_width=1)
    for st in statuses:
        if st == incident['status']:
            continue
        markup.add(types.InlineKeyboardButton(display[st], callback_data=f"admin_inc_setstatus_{inc_id}_{st}"))
    markup.add(types.InlineKeyboardButton("◀️ Назад", callback_data=f"admin_incident_{inc_id}"))
    safe_edit_or_send(f"Выберите новый статус для инцидента {inc_id}:", call.message.chat.id, call.message.message_id, reply_markup=markup)

def set_incident_status(call: types.CallbackQuery, inc_id: str, new_status: str):
    if not update_incident_status(inc_id, new_status):
        bot.answer_callback_query(call.id, "Не удалось обновить статус", show_alert=True)
        return
    incident = get_incident(inc_id)
    update_incident_channel_post(incident)
    bot.answer_callback_query(call.id, f"Статус изменён на {new_status}")
    show_incident_detail(call, inc_id)

def start_change_description(call: types.CallbackQuery, inc_id: str):
    user_states[call.from_user.id] = {"action": "edit_incident_description", "incident_id": inc_id}
    msg = bot.send_message(
        call.message.chat.id,
        f"Введите новое описание для инцидента {inc_id}:"
    )
    bot.register_next_step_handler(msg, process_new_description)

def process_new_description(message: types.Message):
    user_id = message.from_user.id
    state = user_states.pop(user_id, {})
    if state.get("action") != "edit_incident_description":
        return
    inc_id = state["incident_id"]
    new_desc = message.text.strip()
    if not new_desc:
        bot.reply_to(message, "❌ Описание не может быть пустым.")
        return
    if update_incident_description(inc_id, new_desc):
        incident = get_incident(inc_id)
        update_incident_channel_post(incident)
        bot.send_message(message.chat.id, "✅ Описание обновлено.")
        # Показать детали инцидента заново (упрощённо)
        show_incident_detail_from_message(message, inc_id)
    else:
        bot.send_message(message.chat.id, "❌ Не удалось обновить описание.")

def show_incident_detail_from_message(message: types.Message, inc_id: str):
    incident = get_incident(inc_id)
    if not incident:
        return
    text = (
        f"🚨 **Инцидент:** `{incident['id']}`\n"
        f"📌 Важность: {incident['importance']}\n"
        f"📊 Статус: {incident['status']}\n"
        f"🎯 Цель: {incident['target']}\n"
        f"📅 Создан: {incident['created_at']}\n"
        f"🔄 Обновлён: {incident['updated_at']}\n\n"
        f"📝 Описание:\n{incident['description']}"
    )
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("✏️ Изменить статус", callback_data=f"admin_inc_status_{inc_id}"),
        types.InlineKeyboardButton("📝 Изменить описание", callback_data=f"admin_inc_desc_{inc_id}")
    )
    markup.add(types.InlineKeyboardButton("🔄 Обновить пост", callback_data=f"admin_inc_refresh_{inc_id}"))
    markup.add(types.InlineKeyboardButton("◀️ К списку", callback_data="admin_incidents"))
    bot.send_message(message.chat.id, text, reply_markup=markup)

# ---------------------------- Создание инцидента вручную ----------------------------
def start_create_incident(call: types.CallbackQuery):
    user_states[call.from_user.id] = {"action": "create_incident"}
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(
        types.InlineKeyboardButton("🔴 Высокая", callback_data="inc_imp_high"),
        types.InlineKeyboardButton("🟡 Средняя", callback_data="inc_imp_medium"),
        types.InlineKeyboardButton("🟢 Низкая", callback_data="inc_imp_low"),
        types.InlineKeyboardButton("Отмена", callback_data="admin_menu")
    )
    safe_edit_or_send(
        "Выберите важность инцидента:",
        call.message.chat.id,
        call.message.message_id,
        reply_markup=markup
    )

def create_incident_importance_callback(call: types.CallbackQuery):
    data = call.data
    if data == "admin_menu":
        return admin_callback_handler(call)
    importance = data.replace("inc_imp_", "")
    user_states[call.from_user.id] = {"action": "create_incident", "importance": importance}
    msg = bot.send_message(
        f"Важность: {importance}\nВведите описание инцидента:",
        call.message.chat.id,
        call.message.message_id
    )
    bot.register_next_step_handler(msg, create_incident_description_step)

def create_incident_description_step(message: types.Message):
    user_id = message.from_user.id
    state = user_states.get(user_id, {})
    if state.get("action") != "create_incident":
        return
    description = message.text.strip()
    if not description:
        bot.reply_to(message, "Описание не может быть пустым.")
        return
    state["description"] = description
    user_states[user_id] = state
    msg = bot.send_message(message.chat.id, "Введите target (например, node:имя или site:url) или '-' для пропуска:")
    bot.register_next_step_handler(msg, create_incident_target_step)

def create_incident_target_step(message: types.Message):
    user_id = message.from_user.id
    state = user_states.pop(user_id, {})
    target = message.text.strip()
    if target == '-':
        target = f"manual_{datetime.now().strftime('%Y%m%d%H%M%S')}"
    incident_id = add_incident(state["importance"], state["description"], target)
    if incident_id:
        incident = get_incident(incident_id)
        update_incident_channel_post(incident)
        bot.send_message(message.chat.id, f"✅ Инцидент {incident_id} создан.")
    else:
        bot.send_message(message.chat.id, "❌ Не удалось создать инцидент (возможно, дубликат target).")
    admin_command(message)

# ---------------------------- Управление пользователями ----------------------------
def users_menu(call: types.CallbackQuery):
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(
        types.InlineKeyboardButton("📋 Список пользователей", callback_data="admin_users_list"),
        types.InlineKeyboardButton("➕ Добавить пользователя", callback_data="admin_users_add"),
        types.InlineKeyboardButton("❌ Удалить пользователя", callback_data="admin_users_delete"),
        types.InlineKeyboardButton("◀️ Назад", callback_data="admin_menu")
    )
    safe_edit_or_send("👥 **Управление пользователями**", call.message.chat.id, call.message.message_id, reply_markup=markup)

def list_users(call: types.CallbackQuery):
    users = get_all_users()
    if not users:
        safe_edit_or_send("👥 Нет зарегистрированных пользователей.")
        return
    text = "**Список пользователей:**\n"
    for u in users:
        text += f"• `{u['telegram_id']}` — {u['client_email']} (inbound {u['inbound_id']})\n"
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("◀️ Назад", callback_data="admin_users_menu"))
    safe_edit_or_send(text, call.message.chat.id, call.message.message_id, reply_markup=markup)

def start_add_user(call: types.CallbackQuery):
    user_states[call.from_user.id] = {"action": "add_user"}
    msg = bot.send_message(call.message.chat.id, "Введите Telegram ID нового пользователя:")
    bot.register_next_step_handler(msg, add_user_tg_step)

def add_user_tg_step(message: types.Message):
    try:
        tg_id = int(message.text.strip())
    except ValueError:
        bot.reply_to(message, "❌ Введите число.")
        return
    user_states[message.from_user.id]["tg_id"] = tg_id
    msg = bot.send_message(message.chat.id, "Введите inbound_name (имя inbound из 3x-ui):")
    bot.register_next_step_handler(msg, add_user_inbound_step)

def add_user_inbound_step(message: types.Message):
    inbound_name = message.text.strip()
    if not inbound_name:
        bot.reply_to(message, "❌ Inbound name не может быть пустым.")
        return
    user_states[message.from_user.id]["inbound_name"] = inbound_name
    msg = bot.send_message(message.chat.id, "Введите client_email:")
    bot.register_next_step_handler(msg, add_user_email_step)

def add_user_email_step(message: types.Message):
    email = message.text.strip()
    if not email:
        bot.reply_to(message, "❌ Email не может быть пустым.")
        return
    user_states[message.from_user.id]["email"] = email
    msg = bot.send_message(message.chat.id, "Введите subscription_path (например, /sub/xxxx):")
    bot.register_next_step_handler(msg, add_user_path_step)

def add_user_path_step(message: types.Message):
    path = message.text.strip()
    if not path:
        bot.reply_to(message, "❌ Путь не может быть пустым.")
        return
    state = user_states.pop(message.from_user.id)
    add_user(state["tg_id"], state["inbound_name"], state["email"], path)
    bot.send_message(message.chat.id, f"✅ Пользователь {state['tg_id']} добавлен с inbound '{state['inbound_name']}'.")
    admin_command(message)

def start_delete_user(call: types.CallbackQuery):
    users = get_all_users()
    if not users:
        safe_edit_or_send("Нет пользователей для удаления.")
        return
    markup = types.InlineKeyboardMarkup(row_width=1)
    for u in users:
        markup.add(types.InlineKeyboardButton(
            f"❌ {u['telegram_id']} - {u['client_email']}",
            callback_data=f"admin_user_del_{u['telegram_id']}"
        ))
    markup.add(types.InlineKeyboardButton("◀️ Назад", callback_data="admin_users_menu"))
    safe_edit_or_send("Выберите пользователя для удаления:", call.message.chat.id, call.message.message_id, reply_markup=markup)

def confirm_delete_user(call: types.CallbackQuery, tg_id: int):
    if delete_user(tg_id):
        bot.answer_callback_query(call.id, "Пользователь удалён", show_alert=True)
        safe_edit_or_send(f"✅ Пользователь {tg_id} удалён.")
    else:
        bot.answer_callback_query(call.id, "Ошибка удаления", show_alert=True)
    users_menu(call)

# ---------------------------- Управление нодами ----------------------------
def nodes_menu(call: types.CallbackQuery):
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(
        types.InlineKeyboardButton("📋 Список нод", callback_data="admin_nodes_list"),
        types.InlineKeyboardButton("➕ Добавить ноду", callback_data="admin_nodes_add"),
        types.InlineKeyboardButton("❌ Удалить ноду", callback_data="admin_nodes_delete"),
        types.InlineKeyboardButton("🔄 Проверить все ноды", callback_data="admin_nodes_check"),
        types.InlineKeyboardButton("🔗 Xray Inbounds", callback_data="admin_inbounds_menu"),
        types.InlineKeyboardButton("◀️ Назад", callback_data="admin_menu")
    )
    safe_edit_or_send("🌐 **Управление нодами**", call.message.chat.id, call.message.message_id, reply_markup=markup)

def list_nodes(call: types.CallbackQuery):
    nodes = get_all_nodes()
    if not nodes:
        safe_edit_or_send("🌐 Нет добавленных нод.")
        return
    text = "**Список нод:**\n"
    for n in nodes:
        text += f"• **{n['name']}** — {n['ip']}:{n['port']}\n"
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("◀️ Назад", callback_data="admin_nodes_menu"))
    safe_edit_or_send(text, call.message.chat.id, call.message.message_id, reply_markup=markup)

def start_add_node(call: types.CallbackQuery):
    user_states[call.from_user.id] = {"action": "add_node"}
    msg = bot.send_message("Введите имя ноды (уникальное):")
    bot.register_next_step_handler(msg, add_node_name_step)

def add_node_name_step(message: types.Message):
    name = message.text.strip()
    if not name:
        bot.reply_to(message, "Имя не может быть пустым.")
        return
    user_states[message.from_user.id]["name"] = name
    msg = bot.send_message(message.chat.id, "Введите IP-адрес:")
    bot.register_next_step_handler(msg, add_node_ip_step)

def add_node_ip_step(message: types.Message):
    ip = message.text.strip()
    user_states[message.from_user.id]["ip"] = ip
    msg = bot.send_message(message.chat.id, "Введите порт:")
    bot.register_next_step_handler(msg, add_node_port_step)

def add_node_port_step(message: types.Message):
    try:
        port = int(message.text.strip())
    except ValueError:
        bot.reply_to(message, "Порт должен быть числом.")
        return
    state = user_states.pop(message.from_user.id)
    add_node(state["name"], state["ip"], port)
    bot.send_message(message.chat.id, f"✅ Нода {state['name']} добавлена.")
    admin_command(message)

def start_delete_node(call: types.CallbackQuery):
    nodes = get_all_nodes()
    if not nodes:
        safe_edit_or_send("Нет нод для удаления.")
        return
    markup = types.InlineKeyboardMarkup(row_width=1)
    for n in nodes:
        markup.add(types.InlineKeyboardButton(
            f"❌ {n['name']} ({n['ip']}:{n['port']})",
            callback_data=f"admin_node_del_{n['name']}"
        ))
    markup.add(types.InlineKeyboardButton("◀️ Назад", callback_data="admin_nodes_menu"))
    safe_edit_or_send("Выберите ноду для удаления:", call.message.chat.id, call.message.message_id, reply_markup=markup)

def confirm_delete_node(call: types.CallbackQuery, name: str):
    if delete_node(name):
        bot.answer_callback_query(call.id, "Нода удалена", show_alert=True)
        safe_edit_or_send(f"✅ Нода {name} удалена.")
    else:
        bot.answer_callback_query(call.id, "Ошибка удаления", show_alert=True)
    nodes_menu(call)

def check_all_nodes_action(call: types.CallbackQuery):
    nodes = get_all_nodes()
    if not nodes:
        safe_edit_or_send("Нет нод для проверки.")
        return
    safe_edit_or_send("⏳ Проверяю доступность нод через proxy...")
    
    # Получаем inbounds для прокси-проверки
    inbounds = get_all_inbounds()
    
    lines = ["**Результаты проверки нод:**"]
    for node in nodes:
        alive = check_node(node['ip'], node['port'], inbounds=inbounds)
        status = "✅ Доступна" if alive else "❌ Недоступна"
        lines.append(f"• **{node['name']}** ({node['ip']}:{node['port']}): {status}")
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("◀️ Назад", callback_data="admin_nodes_menu"))
    safe_edit_or_send("\n".join(lines), call.message.chat.id, call.message.message_id, reply_markup=markup)

# ---------------------------- Управление сайтами ----------------------------
def sites_menu(call: types.CallbackQuery):
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(
        types.InlineKeyboardButton("📋 Список сайтов", callback_data="admin_sites_list"),
        types.InlineKeyboardButton("➕ Добавить сайт", callback_data="admin_sites_add"),
        types.InlineKeyboardButton("❌ Удалить сайт", callback_data="admin_sites_delete"),
        types.InlineKeyboardButton("🔍 Проверить все сайты", callback_data="admin_sites_check"),
        types.InlineKeyboardButton("◀️ Назад", callback_data="admin_menu")
    )
    safe_edit_or_send("🔗 **Управление сайтами маскировки**", call.message.chat.id, call.message.message_id, reply_markup=markup)

def list_sites(call: types.CallbackQuery):
    sites = get_all_masking_sites()
    if not sites:
        safe_edit_or_send("Нет добавленных сайтов.")
        return
    text = "**Сайты маскировки:**\n"
    for s in sites:
        exp = s['expected_content'] or "нет"
        text += f"• {s['url']} (ожидаемый контент: {exp})\n"
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("◀️ Назад", callback_data="admin_sites_menu"))
    safe_edit_or_send(text, call.message.chat.id, call.message.message_id, reply_markup=markup)

def start_add_site(call: types.CallbackQuery):
    user_states[call.from_user.id] = {"action": "add_site"}
    msg = bot.send_message("Введите URL сайта (с http/https):")
    bot.register_next_step_handler(msg, add_site_url_step)

def add_site_url_step(message: types.Message):
    url = message.text.strip()
    if not url.startswith(('http://', 'https://')):
        bot.reply_to(message, "URL должен начинаться с http:// или https://")
        return
    user_states[message.from_user.id]["url"] = url
    msg = bot.send_message(message.chat.id, "Введите ожидаемый контент (или '-' если не требуется):")
    bot.register_next_step_handler(msg, add_site_content_step)

def add_site_content_step(message: types.Message):
    content = message.text.strip()
    if content == '-':
        content = None
    state = user_states.pop(message.from_user.id)
    add_masking_site(state["url"], content)
    bot.send_message(message.chat.id, f"✅ Сайт {state['url']} добавлен.")
    admin_command(message)

def start_delete_site(call: types.CallbackQuery):
    sites = get_all_masking_sites()
    if not sites:
        safe_edit_or_send("Нет сайтов для удаления.")
        return
    markup = types.InlineKeyboardMarkup(row_width=1)
    for s in sites:
        markup.add(types.InlineKeyboardButton(
            f"❌ {s['url']}",
            callback_data=f"admin_site_del_{s['url']}"
        ))
    markup.add(types.InlineKeyboardButton("◀️ Назад", callback_data="admin_sites_menu"))
    safe_edit_or_send("Выберите сайт для удаления:", call.message.chat.id, call.message.message_id, reply_markup=markup)

def confirm_delete_site(call: types.CallbackQuery, url: str):
    if delete_masking_site(url):
        bot.answer_callback_query(call.id, "Сайт удалён", show_alert=True)
        safe_edit_or_send(f"✅ Сайт {url} удалён.")
    else:
        bot.answer_callback_query(call.id, "Ошибка удаления", show_alert=True)
    sites_menu(call)

def check_all_sites_action(call: types.CallbackQuery):
    sites = get_all_masking_sites()
    if not sites:
        safe_edit_or_send("Нет сайтов для проверки.")
        return
    safe_edit_or_send("⏳ Проверяю сайты...")
    lines = ["**Результаты проверки сайтов:**"]
    for site in sites:
        ok = check_website(site['url'], site.get('expected_content'))
        status = "✅ Работает" if ok else "❌ Недоступен"
        lines.append(f"• {site['url']}: {status}")
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("◀️ Назад", callback_data="admin_sites_menu"))
    safe_edit_or_send("\n".join(lines), call.message.chat.id, call.message.message_id, reply_markup=markup)

# ---------------------------- Управление админами ----------------------------
def admins_menu(call: types.CallbackQuery):
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(
        types.InlineKeyboardButton("📋 Список админов", callback_data="admin_admins_list"),
        types.InlineKeyboardButton("➕ Добавить админа", callback_data="admin_admins_add"),
        types.InlineKeyboardButton("❌ Удалить админа", callback_data="admin_admins_remove"),
        types.InlineKeyboardButton("◀️ Назад", callback_data="admin_menu")
    )
    safe_edit_or_send("👑 **Управление администраторами**", call.message.chat.id, call.message.message_id, reply_markup=markup)

def list_admins(call: types.CallbackQuery):
    admins = get_all_admins()
    text = "**Администраторы:**\n" + "\n".join(f"• `{a}`" for a in admins)
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("◀️ Назад", callback_data="admin_admins_menu"))
    safe_edit_or_send(text, call.message.chat.id, call.message.message_id, reply_markup=markup)

def start_add_admin(call: types.CallbackQuery):
    user_states[call.from_user.id] = {"action": "add_admin"}
    msg = bot.send_message("Введите Telegram ID нового администратора:")
    bot.register_next_step_handler(msg, add_admin_step)

def add_admin_step(message: types.Message):
    try:
        tg_id = int(message.text.strip())
    except ValueError:
        bot.reply_to(message, "Введите число.")
        return
    add_admin(tg_id)
    user_states.pop(message.from_user.id, None)
    bot.send_message(message.chat.id, f"✅ Администратор {tg_id} добавлен.")
    admin_command(message)

def start_remove_admin(call: types.CallbackQuery):
    admins = get_all_admins()
    if len(admins) <= 1:
        safe_edit_or_send("Нельзя удалить последнего администратора.")
        return
    markup = types.InlineKeyboardMarkup(row_width=1)
    for a in admins:
        if a == call.from_user.id:
            continue
        markup.add(types.InlineKeyboardButton(f"❌ {a}", callback_data=f"admin_admin_del_{a}"))
    markup.add(types.InlineKeyboardButton("◀️ Назад", callback_data="admin_admins_menu"))
    safe_edit_or_send("Выберите администратора для удаления:", call.message.chat.id, call.message.message_id, reply_markup=markup)

def confirm_remove_admin(call: types.CallbackQuery, tg_id: int):
    if remove_admin(tg_id):
        bot.answer_callback_query(call.id, "Администратор удалён", show_alert=True)
        safe_edit_or_send(f"✅ Администратор {tg_id} удалён.")
    else:
        bot.answer_callback_query(call.id, "Ошибка", show_alert=True)
    admins_menu(call)

# ---------------------------- Управление Xray Inbounds ----------------------------
def inbounds_menu(call: types.CallbackQuery):
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(
        types.InlineKeyboardButton("📋 Список Inbounds", callback_data="admin_inbounds_list"),
        types.InlineKeyboardButton("➕ Добавить Inbound", callback_data="admin_inbounds_add"),
        types.InlineKeyboardButton("❌ Удалить Inbound", callback_data="admin_inbounds_delete"),
        types.InlineKeyboardButton("◀️ Назад", callback_data="admin_nodes_menu")
    )
    safe_edit_or_send("🔗 **Управление Xray Inbounds**\nЭти прокси используются для пинга нод.", call.message.chat.id, call.message.message_id, reply_markup=markup)

def list_inbounds(call: types.CallbackQuery):
    inbounds = get_all_inbounds()
    if not inbounds:
        safe_edit_or_send("🔗 Нет добавленных Xray Inbounds.")
        return
    text = "**Список Xray Inbounds:**\n"
    for ib in inbounds:
        text += f"• **{ib['name']}** — {ib['protocol']}\n"
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("◀️ Назад", callback_data="admin_inbounds_menu"))
    safe_edit_or_send(text, call.message.chat.id, call.message.message_id, reply_markup=markup)

def start_add_inbound(call: types.CallbackQuery):
    user_states[call.from_user.id] = {"action": "add_inbound"}
    msg = bot.send_message("Введите имя inbound (уникальное):")
    bot.register_next_step_handler(msg, add_inbound_name_step)

def add_inbound_name_step(message: types.Message):
    name = message.text.strip()
    if not name:
        bot.reply_to(message, "Имя не может быть пустым.")
        return
    user_states[message.from_user.id]["name"] = name
    msg = bot.send_message(message.chat.id, "Введите протокол (vmess, vless, trojan и т.д.):")
    bot.register_next_step_handler(msg, add_inbound_protocol_step)

def add_inbound_protocol_step(message: types.Message):
    protocol = message.text.strip().lower()
    user_states[message.from_user.id]["protocol"] = protocol
    msg = bot.send_message(message.chat.id, "Введите адрес proxy (например, proxy1.example.com):")
    bot.register_next_step_handler(msg, add_inbound_address_step)

def add_inbound_address_step(message: types.Message):
    address = message.text.strip()
    user_states[message.from_user.id]["address"] = address
    msg = bot.send_message(message.chat.id, "Введите порт:")
    bot.register_next_step_handler(msg, add_inbound_port_step)

def add_inbound_port_step(message: types.Message):
    try:
        port = int(message.text.strip())
    except ValueError:
        bot.reply_to(message, "Порт должен быть числом.")
        return
    state = user_states.pop(message.from_user.id)
    settings = {
        "address": state["address"],
        "port": port
    }
    add_inbound(state["name"], state["protocol"], settings)
    bot.send_message(message.chat.id, f"✅ Xray inbound {state['name']} добавлен.")
    admin_command(message)

def start_delete_inbound(call: types.CallbackQuery):
    inbounds = get_all_inbounds()
    if not inbounds:
        safe_edit_or_send("Нет Inbounds для удаления.")
        return
    markup = types.InlineKeyboardMarkup(row_width=1)
    for ib in inbounds:
        markup.add(types.InlineKeyboardButton(
            f"❌ {ib['name']} ({ib['protocol']})",
            callback_data=f"admin_inbound_del_{ib['name']}"
        ))
    markup.add(types.InlineKeyboardButton("◀️ Назад", callback_data="admin_inbounds_menu"))
    safe_edit_or_send("Выберите Inbound для удаления:", call.message.chat.id, call.message.message_id, reply_markup=markup)

def confirm_delete_inbound(call: types.CallbackQuery, name: str):
    if delete_inbound(name):
        bot.answer_callback_query(call.id, "Inbound удалён", show_alert=True)
        safe_edit_or_send(f"✅ Xray inbound {name} удалён.")
    else:
        bot.answer_callback_query(call.id, "Ошибка удаления", show_alert=True)
    inbounds_menu(call)

# ---------------------------- Регистрация хендлеров ----------------------------
def register_handlers(bot_instance: telebot.TeleBot, incident_channel: str):
    global bot, INCIDENT_CHANNEL
    bot = bot_instance
    INCIDENT_CHANNEL = incident_channel

    # Команда /admin
    bot.register_message_handler(admin_command, commands=['admin'])

    # Главный обработчик колбэков админки (паттерн 'admin_')
    bot.register_callback_query_handler(admin_callback_handler, func=lambda call: call.data.startswith('admin_'))

    # Дополнительные колбэки для создания инцидента (не admin_)
    bot.register_callback_query_handler(create_incident_importance_callback, func=lambda call: call.data.startswith('inc_imp_'))

    logger.info("Административные хендлеры зарегистрированы")