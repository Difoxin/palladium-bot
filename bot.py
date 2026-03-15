#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Palladium Bot - ТЕРАБАЙТНАЯ ВЕРСИЯ (ПОЛНЫЙ ФУНКЦИОНАЛ)
Данные в Telegram, на Render только метаданные
"""

import telebot
import json
import os
import re
import time
import random
import string
import hashlib
from datetime import datetime
from flask import Flask
import threading

# ===== НАСТРОЙКИ =====
TOKEN = "8621913179:AAHoiUHkluY_9PHlA3GI8VTeI0zrKAEeXmU"
ADMIN_ID = 7656295632

bot = telebot.TeleBot(TOKEN)
app = Flask(__name__)

# === ХРАНИЛИЩЕ МЕТАДАННЫХ (1 МБ НА ВСЮ ЖИЗНЬ) ===
METADATA_FILE = "metadata.json"

def load_metadata():
    """Загружает метаданные файлов"""
    if os.path.exists(METADATA_FILE):
        with open(METADATA_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {
        "files": [],           # все файлы
        "next_id": 1,          # следующий ID
        "users": {},           # пользователи
        "public_files": [],    # общие файлы (ID)
        "search_count": 0      # счетчик поисков
    }

def save_metadata():
    """Сохраняет метаданные"""
    with open(METADATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(metadata, f, ensure_ascii=False, indent=2)

# Загружаем метаданные
metadata = load_metadata()

# === СОСТОЯНИЯ ПОЛЬЗОВАТЕЛЕЙ ===
user_states = {}

# === ФУНКЦИИ ===

def is_admin(user_id):
    return user_id == ADMIN_ID

def register_user(message):
    user_id = str(message.from_user.id)
    if user_id not in metadata['users']:
        metadata['users'][user_id] = {
            'name': message.from_user.first_name,
            'username': message.from_user.username,
            'joined': datetime.now().isoformat(),
            'files': [],           # ID личных файлов
            'search_count': 0,
            'report_count': 0
        }
        save_metadata()

def get_user_files(user_id):
    """Возвращает список файлов пользователя"""
    user_id = str(user_id)
    if user_id not in metadata['users']:
        return []
    
    user_files = []
    for file_id in metadata['users'][user_id].get('files', []):
        for f in metadata['files']:
            if f['id'] == file_id:
                user_files.append(f)
                break
    return user_files

def get_public_files():
    """Возвращает список общих файлов"""
    public_files = []
    for file_id in metadata.get('public_files', []):
        for f in metadata['files']:
            if f['id'] == file_id:
                public_files.append(f)
                break
    return public_files

# === ВЕБ-СЕРВЕР ДЛЯ RENDER ===
@app.route('/')
def home():
    total_size = sum(f['size_gb'] for f in metadata['files'])
    return f"""
    <html>
    <head><title>Palladium Bot</title></head>
    <body>
        <h1>🚀 Palladium Bot работает 24/7</h1>
        <p>📁 Файлов: {len(metadata['files'])}</p>
        <p>💾 Общий объем: {total_size:.2f} ГБ</p>
        <p>👥 Пользователей: {len(metadata['users'])}</p>
        <p>📋 Метаданные: {os.path.getsize(METADATA_FILE)/1024:.1f} КБ</p>
        <p>🔍 Поисков: {metadata.get('search_count', 0)}</p>
        <hr>
        <p>Telegram: @PalladiumDataBot</p>
    </body>
    </html>
    """

# === КОМАНДЫ ===

@bot.message_handler(commands=['start'])
def start_command(message):
    register_user(message)
    user_id = message.from_user.id
    
    welcome = f"""
🔍 **PALLADIUM BOT - ТЕРАБАЙТНАЯ ВЕРСИЯ**
{'👑 АДМИНИСТРАТОР' if is_admin(user_id) else '👤 ПОЛЬЗОВАТЕЛЬ'}

📌 **КАК ЭТО РАБОТАЕТ:**
• Файлы хранятся в Telegram (хоть 100 ТБ)
• На сервере только метаданные (1 МБ)
• Поиск по тегам и названиям

📌 **ОСНОВНЫЕ КОМАНДЫ:**
/upload - загрузить файл в Telegram
/files - список всех файлов
/search [тег] - поиск по тегам
/tag [id] [теги] - добавить теги
/view [id] - посмотреть первые строки
/stats - статистика

📌 **ЛИЧНЫЕ ФАЙЛЫ:**
/myfiles - мои файлы
/addfile - добавить в личные
/deletefile [id] - удалить личный файл

📌 **ГЕНЕРАТОРЫ:**
/gen_password [длина] - пароль
/gen_identity - личность
/gen_card - карта

📌 **СИСТЕМА:**
/ping - проверка
/id - ваш ID

📌 **АДМИНИСТРАТОРУ:**
/admin_list - все файлы
/admin_add [id] - сделать общим
/admin_remove [id] - убрать из общих
/admin_delete [id] - удалить файл
/admin_stats - статистика админа
"""
    bot.reply_to(message, welcome, parse_mode='Markdown')

# === УПРАВЛЕНИЕ ФАЙЛАМИ ===

@bot.message_handler(commands=['upload'])
def upload_command(message):
    """Загрузить файл в Telegram"""
    bot.reply_to(message, 
        "📤 Отправьте файл (можно до 2 ГБ).\n"
        "Он сохранится в Telegram навсегда!\n\n"
        "После загрузки не забудьте добавить теги:\n"
        "/tag [id] [тег1] [тег2] ..."
    )

@bot.message_handler(content_types=['document'])
def handle_file(message):
    """Обработка загруженного файла"""
    user_id = message.from_user.id
    file_id = message.document.file_id
    file_name = message.document.file_name
    file_size = message.document.file_size
    
    # Проверяем размер
    size_gb = file_size / (1024**3)
    
    status_msg = bot.reply_to(message, f"📥 Получен файл: {file_name}\n⚙️ Сохраняю в Telegram...")
    
    try:
        # Сохраняем метаданные
        file_info = {
            'id': metadata['next_id'],
            'name': file_name,
            'telegram_file_id': file_id,
            'telegram_message_id': message.message_id,
            'size_gb': round(size_gb, 2),
            'size_bytes': file_size,
            'uploaded_by': user_id,
            'upload_date': datetime.now().isoformat(),
            'tags': [],
            'description': '',
            'is_public': False  # по умолчанию личный
        }
        
        metadata['files'].append(file_info)
        file_id_num = metadata['next_id']
        metadata['next_id'] += 1
        
        # Добавляем в личные файлы пользователя
        user_id_str = str(user_id)
        if user_id_str in metadata['users']:
            metadata['users'][user_id_str]['files'].append(file_id_num)
        
        save_metadata()
        
        bot.edit_message_text(
            f"✅ Файл сохранён в Telegram!\n"
            f"📁 {file_name}\n"
            f"📊 Размер: {size_gb:.2f} ГБ\n"
            f"🆔 ID файла: {file_id_num}\n\n"
            f"Теперь добавьте теги:\n"
            f"/tag {file_id_num} тег1 тег2 тег3",
            message.chat.id,
            status_msg.message_id
        )
        
    except Exception as e:
        bot.edit_message_text(f"❌ Ошибка: {e}", message.chat.id, status_msg.message_id)

@bot.message_handler(commands=['files'])
def files_command(message):
    """Показать все файлы"""
    all_files = metadata['files']
    
    if not all_files:
        bot.reply_to(message, "📁 Пока нет загруженных файлов")
        return
    
    # Считаем статистику
    total_size = sum(f['size_gb'] for f in all_files)
    public_count = len([f for f in all_files if f.get('is_public', False)])
    private_count = len(all_files) - public_count
    
    response = f"📁 **ВСЕГО ФАЙЛОВ:** {len(all_files)}\n"
    response += f"📊 **Общий объем:** {total_size:.2f} ГБ\n"
    response += f"🌐 **Общих:** {public_count} | 🔒 **Личных:** {private_count}\n"
    response += f"📋 **Метаданные:** {os.path.getsize(METADATA_FILE)/1024:.1f} КБ\n"
    response += "─" * 30 + "\n\n"
    
    # Показываем последние 10
    for f in all_files[-10:]:
        file_type = "🌐" if f.get('is_public', False) else "🔒"
        response += f"{file_type} **ID {f['id']}:** {f['name']}\n"
        response += f"   📊 {f['size_gb']} ГБ, теги: {', '.join(f['tags']) if f['tags'] else 'нет'}\n"
        response += f"   📅 {f['upload_date'][:10]}\n\n"
    
    bot.reply_to(message, response, parse_mode='Markdown')

@bot.message_handler(commands=['myfiles'])
def myfiles_command(message):
    """Список личных файлов пользователя"""
    user_id = str(message.from_user.id)
    user_files = get_user_files(user_id)
    
    if not user_files:
        bot.reply_to(message, "📁 У вас нет личных файлов")
        return
    
    total_size = sum(f['size_gb'] for f in user_files)
    
    response = f"📁 **ВАШИ ФАЙЛЫ ({len(user_files)}):**\n"
    response += f"💾 **Объем:** {total_size:.2f} ГБ\n"
    response += "─" * 30 + "\n\n"
    
    for f in user_files:
        public = "🌐" if f.get('is_public', False) else "🔒"
        response += f"{public} **ID {f['id']}:** {f['name']}\n"
        response += f"   📊 {f['size_gb']} ГБ, теги: {', '.join(f['tags'])}\n"
        response += f"   📅 {f['upload_date'][:10]}\n\n"
    
    bot.reply_to(message, response, parse_mode='Markdown')

@bot.message_handler(commands=['addfile'])
def addfile_command(message):
    """Добавить файл в личные (уже было при загрузке)"""
    bot.reply_to(message, 
        "📤 Для добавления файла используйте /upload\n"
        "После загрузки файл автоматически становится личным."
    )

@bot.message_handler(commands=['deletefile'])
def deletefile_command(message):
    """Удалить личный файл"""
    parts = message.text.split()
    if len(parts) != 2:
        bot.reply_to(message, "❌ Использование: /deletefile [id]")
        return
    
    try:
        file_id = int(parts[1])
    except:
        bot.reply_to(message, "❌ ID должен быть числом")
        return
    
    user_id = str(message.from_user.id)
    user_files = metadata['users'][user_id].get('files', [])
    
    if file_id not in user_files:
        bot.reply_to(message, "❌ Этот файл не принадлежит вам")
        return
    
    # Удаляем из списка пользователя
    metadata['users'][user_id]['files'].remove(file_id)
    
    # Если файл не общий и больше никому не принадлежит
    file_owners = 0
    for u in metadata['users'].values():
        if file_id in u.get('files', []):
            file_owners += 1
    
    if file_owners == 0 and not any(f['id'] == file_id and f.get('is_public', False) for f in metadata['files']):
        # Удаляем файл полностью
        metadata['files'] = [f for f in metadata['files'] if f['id'] != file_id]
    
    save_metadata()
    bot.reply_to(message, f"✅ Файл ID {file_id} удален из ваших личных")

# === ПОИСК И ТЕГИ ===

@bot.message_handler(commands=['search'])
def search_command(message):
    """Поиск по тегам"""
    query = message.text.replace('/search', '').strip().lower()
    
    if not query:
        bot.reply_to(message, "❌ Введите тег для поиска. Пример: /search телефон")
        return
    
    metadata['search_count'] = metadata.get('search_count', 0) + 1
    save_metadata()
    
    # Ищем по публичным файлам
    public_files = get_public_files()
    words = query.split()
    
    results = []
    for f in public_files:
        tags_text = ' '.join(f['tags']).lower()
        name_text = f['name'].lower()
        
        if all(word in tags_text or word in name_text for word in words):
            results.append(f)
    
    if not results:
        bot.reply_to(message, f"❌ Ничего не найдено по запросу: {query}")
        return
    
    response = f"🔍 **НАЙДЕНО:** {len(results)} файлов\n\n"
    
    for r in results[:10]:
        response += f"📁 **ID {r['id']}:** {r['name']}\n"
        response += f"   📊 {r['size_gb']} ГБ, теги: {', '.join(r['tags'])}\n"
        response += f"   👁️ /view {r['id']}\n\n"
    
    if len(results) > 10:
        response += f"... и еще {len(results) - 10} файлов"
    
    bot.reply_to(message, response, parse_mode='Markdown')

@bot.message_handler(commands=['tag'])
def tag_command(message):
    """Добавить теги к файлу"""
    parts = message.text.split()
    if len(parts) < 3:
        bot.reply_to(message, "❌ Использование: /tag [id] [тег1] [тег2] ...")
        return
    
    try:
        file_id = int(parts[1])
        new_tags = parts[2:]
    except:
        bot.reply_to(message, "❌ ID должен быть числом")
        return
    
    # Ищем файл
    file_found = None
    for f in metadata['files']:
        if f['id'] == file_id:
            file_found = f
            break
    
    if not file_found:
        bot.reply_to(message, f"❌ Файл с ID {file_id} не найден")
        return
    
    # Проверяем права (владелец или админ)
    user_id = str(message.from_user.id)
    is_owner = file_id in metadata['users'].get(user_id, {}).get('files', [])
    
    if not (is_owner or is_admin(message.from_user.id)):
        bot.reply_to(message, "❌ Вы можете редактировать только свои файлы")
        return
    
    # Добавляем теги
    for tag in new_tags:
        tag_clean = tag.lower().strip('#')
        if tag_clean and tag_clean not in file_found['tags']:
            file_found['tags'].append(tag_clean)
    
    save_metadata()
    
    bot.reply_to(message, 
        f"✅ Теги добавлены к файлу **{file_found['name']}**\n"
        f"📌 Текущие теги: {', '.join(file_found['tags'])}",
        parse_mode='Markdown'
    )

@bot.message_handler(commands=['view'])
def view_command(message):
    """Посмотреть первые строки файла"""
    parts = message.text.split()
    if len(parts) != 2:
        bot.reply_to(message, "❌ Использование: /view [id]")
        return
    
    try:
        file_id = int(parts[1])
    except:
        bot.reply_to(message, "❌ ID должен быть числом")
        return
    
    # Ищем файл
    file_found = None
    for f in metadata['files']:
        if f['id'] == file_id:
            file_found = f
            break
    
    if not file_found:
        bot.reply_to(message, f"❌ Файл с ID {file_id} не найден")
        return
    
    msg = bot.reply_to(message, f"📥 Скачиваю первые строки из Telegram...")
    
    try:
        # Скачиваем файл из Telegram
        file_info = bot.get_file(file_found['telegram_file_id'])
        downloaded = bot.download_file(file_info.file_path)
        
        # Берем только первые 100 КБ
        preview = downloaded[:100000].decode('utf-8', errors='ignore')
        lines = preview.split('\n')[:15]  # Первые 15 строк
        
        preview_text = "\n".join(lines)
        
        response = (
            f"📁 **{file_found['name']}**\n"
            f"📊 Размер: {file_found['size_gb']} ГБ\n"
            f"📌 Теги: {', '.join(file_found['tags'])}\n"
            f"🔗 ID: {file_id}\n\n"
            f"📋 **ПЕРВЫЕ 15 СТРОК:**\n"
            f"```\n{preview_text}\n```"
        )
        
        bot.edit_message_text(
            response,
            message.chat.id,
            msg.message_id,
            parse_mode='Markdown'
        )
    except Exception as e:
        bot.edit_message_text(f"❌ Ошибка: {e}", message.chat.id, msg.message_id)

# === ГЕНЕРАТОРЫ ===

@bot.message_handler(commands=['gen_password', 'gp'])
def gen_password_command(message):
    """Генератор паролей"""
    parts = message.text.split()
    length = 12
    
    if len(parts) > 1:
        try:
            length = int(parts[1])
            if length < 4:
                length = 4
            if length > 32:
                length = 32
        except:
            pass
    
    chars = string.ascii_letters + string.digits + "!@#$%^&*"
    password = ''.join(random.choice(chars) for _ in range(length))
    
    # Оценка сложности
    strength = 0
    if any(c.islower() for c in password): strength += 1
    if any(c.isupper() for c in password): strength += 1
    if any(c.isdigit() for c in password): strength += 1
    if any(c in "!@#$%^&*" for c in password): strength += 1
    if length >= 12: strength += 1
    
    strength_text = ['Очень слабый', 'Слабый', 'Средний', 'Хороший', 'Сильный', 'Очень сильный'][strength]
    
    response = f"""
🔐 **СГЕНЕРИРОВАННЫЙ ПАРОЛЬ**

**Пароль:** `{password}`
**Длина:** {length}
**Сложность:** {strength_text}

💡 Советы:
• Используйте менеджер паролей
• Не используйте один пароль везде
• Регулярно меняйте пароли
    """
    
    bot.reply_to(message, response, parse_mode='Markdown')

@bot.message_handler(commands=['gen_identity', 'gi'])
def gen_identity_command(message):
    """Генератор личности"""
    first_names_m = ['Александр', 'Дмитрий', 'Максим', 'Сергей', 'Андрей', 'Алексей', 'Артём', 'Илья']
    first_names_f = ['Анна', 'Мария', 'Елена', 'Дарья', 'Анастасия', 'Ольга', 'Татьяна', 'Екатерина']
    last_names_m = ['Иванов', 'Петров', 'Сидоров', 'Кузнецов', 'Смирнов', 'Попов', 'Васильев', 'Соколов']
    last_names_f = ['Иванова', 'Петрова', 'Сидорова', 'Кузнецова', 'Смирнова', 'Попова', 'Васильева', 'Соколова']
    cities = ['Москва', 'Санкт-Петербург', 'Казань', 'Новосибирск', 'Екатеринбург', 'Нижний Новгород', 'Самара']
    streets = ['Ленина', 'Пушкина', 'Гагарина', 'Советская', 'Мира', 'Садовая', 'Молодежная']
    
    gender = random.choice(['M', 'F'])
    
    if gender == 'M':
        first = random.choice(first_names_m)
        last = random.choice(last_names_m)
        patronymic = random.choice(['Александрович', 'Дмитриевич', 'Сергеевич', 'Андреевич', 'Петрович'])
    else:
        first = random.choice(first_names_f)
        last = random.choice(last_names_f)
        patronymic = random.choice(['Александровна', 'Дмитриевна', 'Сергеевна', 'Андреевна', 'Петровна'])
    
    year = random.randint(1970, 2005)
    month = random.randint(1, 12)
    day = random.randint(1, 28)
    
    phone = f"+7{random.randint(900, 999)}{random.randint(1000000, 9999999)}"
    email = f"{first.lower()}.{last.lower()}{random.randint(1, 99)}@{random.choice(['gmail.com', 'mail.ru', 'yandex.ru'])}"
    
    response = f"""
👤 **СГЕНЕРИРОВАННАЯ ЛИЧНОСТЬ**

📋 **ФИО:** {last} {first} {patronymic}
⚥ **Пол:** {'Мужской' if gender == 'M' else 'Женский'}
🎂 **Дата рождения:** {day:02d}.{month:02d}.{year}
📱 **Телефон:** `{phone}`
📧 **Email:** `{email}`
🏠 **Адрес:** г. {random.choice(cities)}, ул. {random.choice(streets)}, д. {random.randint(1,100)}

⚠️ **ВСЕ ДАННЫЕ ВЫМЫШЛЕНЫ**
    """
    
    bot.reply_to(message, response, parse_mode='Markdown')

@bot.message_handler(commands=['gen_card', 'gc'])
def gen_card_command(message):
    """Генератор банковских карт"""
    bins = ['4276', '4279', '5211', '5489', '2200', '2202', '4377', '4622']
    
    card_number = f"{random.choice(bins)} {random.randint(1000,9999)} {random.randint(1000,9999)} {random.randint(1000,9999)}"
    expiry = f"{random.randint(1,12):02d}/{random.randint(25,30)}"
    cvv = f"{random.randint(100,999)}"
    
    response = f"""
💳 **ТЕСТОВАЯ БАНКОВСКАЯ КАРТА**

**Номер:** `{card_number}`
**Срок:** {expiry}
**CVV:** {cvv}
**Владелец:** {random.choice(['IVANOV', 'PETROV', 'SIDOROV'])} {random.choice(['IVAN', 'PETR', 'MAXIM'])}

⚠️ **ТОЛЬКО ДЛЯ ТЕСТОВ!**
❌ Не пытайтесь использовать для реальных платежей
    """
    
    bot.reply_to(message, response, parse_mode='Markdown')

# === АДМИНИСТРАТОРСКИЕ КОМАНДЫ ===

@bot.message_handler(commands=['admin_list'])
def admin_list_command(message):
    """Список всех файлов для админа"""
    if not is_admin(message.from_user.id):
        bot.reply_to(message, "❌ Только для администратора")
        return
    
    all_files = metadata['files']
    if not all_files:
        bot.reply_to(message, "📁 Файлов нет")
        return
    
    total_size = sum(f['size_gb'] for f in all_files)
    
    response = f"📁 **ВСЕ ФАЙЛЫ ({len(all_files)}):**\n"
    response += f"💾 **Общий объем:** {total_size:.2f} ГБ\n"
    response += "─" * 30 + "\n\n"
    
    for f in all_files[-20:]:  # последние 20
        public = "🌐" if f.get('is_public', False) else "🔒"
        response += f"{public} **ID {f['id']}:** {f['name']}\n"
        response += f"   👤 Владелец: {f['uploaded_by']}\n"
        response += f"   📊 {f['size_gb']} ГБ, теги: {', '.join(f['tags'])}\n"
        response += f"   📅 {f['upload_date'][:10]}\n\n"
    
    # Разбиваем на части если длинное сообщение
    if len(response) > 4000:
        for i in range(0, len(response), 4000):
            bot.reply_to(message, response[i:i+4000], parse_mode='Markdown')
    else:
        bot.reply_to(message, response, parse_mode='Markdown')

@bot.message_handler(commands=['admin_add'])
def admin_add_command(message):
    """Сделать файл общим"""
    if not is_admin(message.from_user.id):
        bot.reply_to(message, "❌ Только для администрато