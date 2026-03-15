#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Palladium Bot - ФИНАЛЬНАЯ ВЕРСИЯ 24/7
"""

import telebot
import sqlite3
import os
import re
import time
import random
import string
import hashlib
import json
from datetime import datetime
import threading
import requests
import base64

# ===== НАСТРОЙКИ =====
TOKEN = "8621913179:AAHoiUHkluY_9PHlA3GI8VTeI0zrKAEeXmU"
ADMIN_ID = 7656295632

# GitHub настройки (создайте токен!)
GITHUB_TOKEN = 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  # Замените на ваш токен!
GITHUB_REPO = "Difoxin/palladium-bot"
GITHUB_URL = f"https://api.github.com/repos/{GITHUB_REPO}/contents/palladium.db"

bot = telebot.TeleBot(TOKEN)

# === ФУНКЦИИ ДЛЯ РАБОТЫ С GITHUB ===

def download_db():
    """Скачивает базу данных с GitHub при запуске"""
    try:
        headers = {"Authorization": f"token {GITHUB_TOKEN}"}
        response = requests.get(GITHUB_URL, headers=headers)
        
        if response.status_code == 200:
            content = response.json()['content']
            db_data = base64.b64decode(content)
            
            with open('palladium.db', 'wb') as f:
                f.write(db_data)
            print("✅ База данных загружена с GitHub")
            return True
        else:
            print("❌ База не найдена, создаем новую")
            return False
    except Exception as e:
        print(f"❌ Ошибка загрузки: {e}")
        return False

def upload_db():
    """Загружает базу данных на GitHub"""
    try:
        with open('palladium.db', 'rb') as f:
            content = base64.b64encode(f.read()).decode('utf-8')
        
        # Сначала получаем текущий файл (чтобы узнать sha)
        headers = {"Authorization": f"token {GITHUB_TOKEN}"}
        response = requests.get(GITHUB_URL, headers=headers)
        
        data = {
            "message": f"Auto-update DB {datetime.now().isoformat()}",
            "content": content
        }
        
        if response.status_code == 200:
            data["sha"] = response.json()['sha']
        
        # Загружаем
        response = requests.put(GITHUB_URL, headers=headers, json=data)
        
        if response.status_code in [200, 201]:
            print("✅ База данных сохранена на GitHub")
        else:
            print(f"❌ Ошибка сохранения: {response.status_code}")
    except Exception as e:
        print(f"❌ Ошибка: {e}")

# Функция автосохранения каждые 5 минут
def auto_save():
    while True:
        time.sleep(300)  # 5 минут
        upload_db()
        print("💾 Автосохранение БД")

# Запускаем автосохранение в отдельном потоке
threading.Thread(target=auto_save, daemon=True).start()

# === БАЗА ДАННЫХ ===
# Загружаем последнюю версию
download_db()

conn = sqlite3.connect('palladium.db', check_same_thread=False)
cursor = conn.cursor()

# Создаем таблицы
cursor.execute('''
    CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        username TEXT,
        first_name TEXT,
        is_admin INTEGER DEFAULT 0,
        registered_date TEXT,
        search_count INTEGER DEFAULT 0,
        report_count INTEGER DEFAULT 0
    )
''')

cursor.execute('''
    CREATE TABLE IF NOT EXISTS public_files (
        file_id TEXT PRIMARY KEY,
        file_name TEXT,
        file_size INTEGER,
        message_id INTEGER,
        uploaded_by INTEGER,
        upload_date TEXT,
        record_count INTEGER DEFAULT 0
    )
''')

cursor.execute('''
    CREATE TABLE IF NOT EXISTS user_files (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        file_id TEXT,
        file_name TEXT,
        file_size INTEGER,
        message_id INTEGER,
        upload_date TEXT,
        record_count INTEGER DEFAULT 0
    )
''')

cursor.execute('''
    CREATE TABLE IF NOT EXISTS public_index (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        word TEXT,
        file_id TEXT,
        file_name TEXT,
        line_number INTEGER,
        full_line TEXT,
        preview TEXT,
        search_count INTEGER DEFAULT 0
    )
''')

cursor.execute('''
    CREATE TABLE IF NOT EXISTS user_index (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        word TEXT,
        file_id TEXT,
        file_name TEXT,
        line_number INTEGER,
        full_line TEXT,
        preview TEXT
    )
''')

conn.commit()

# === СОСТОЯНИЯ ПОЛЬЗОВАТЕЛЕЙ ===
user_states = {}

# === ФУНКЦИИ ===

def is_admin(user_id):
    return user_id == ADMIN_ID

def register_user(message):
    user_id = message.from_user.id
    username = message.from_user.username or ""
    first_name = message.from_user.first_name or ""
    
    cursor.execute('''
        INSERT OR IGNORE INTO users (user_id, username, first_name, registered_date)
        VALUES (?, ?, ?, ?)
    ''', (user_id, username, first_name, datetime.now().isoformat()))
    
    if user_id == ADMIN_ID:
        cursor.execute('UPDATE users SET is_admin = 1 WHERE user_id = ?', (user_id,))
    
    conn.commit()

def file_exists_public(file_name):
    cursor.execute('SELECT COUNT(*) FROM public_files WHERE file_name = ?', (file_name,))
    return cursor.fetchone()[0] > 0

def file_exists_user(user_id, file_name):
    cursor.execute('SELECT COUNT(*) FROM user_files WHERE user_id = ? AND file_name = ?', (user_id, file_name))
    return cursor.fetchone()[0] > 0

def index_file(file_id, file_name, content, is_public=True, user_id=None, progress_callback=None):
    """Индексация файла для поиска"""
    try:
        text = content.decode('utf-8', errors='ignore')
        lines = text.split('\n')
        total_lines = len(lines)
        indexed = 0
        record_count = 0
        
        if is_public:
            cursor.execute('DELETE FROM public_index WHERE file_id = ?', (file_id,))
        else:
            cursor.execute('DELETE FROM user_index WHERE file_id = ? AND user_id = ?', (file_id, user_id))
        
        for line_num, line in enumerate(lines, 1):
            if not line.strip():
                continue
            
            record_count += 1
            words = re.findall(r'[а-яёa-z0-9]+', line.lower())
            unique_words = set(words)
            
            for word in unique_words:
                if len(word) > 2:
                    preview = line[:100] + "..." if len(line) > 100 else line
                    
                    if is_public:
                        cursor.execute('''
                            INSERT INTO public_index (word, file_id, file_name, line_number, full_line, preview)
                            VALUES (?, ?, ?, ?, ?, ?)
                        ''', (word, file_id, file_name, line_num, line, preview))
                    else:
                        cursor.execute('''
                            INSERT INTO user_index (user_id, word, file_id, file_name, line_number, full_line, preview)
                            VALUES (?, ?, ?, ?, ?, ?, ?)
                        ''', (user_id, word, file_id, file_name, line_num, line, preview))
                    indexed += 1
            
            if line_num % 1000 == 0:
                conn.commit()
                if progress_callback:
                    progress_callback(line_num, total_lines)
        
        conn.commit()
        
        if is_public:
            cursor.execute('UPDATE public_files SET record_count = ? WHERE file_id = ?', (record_count, file_id))
        else:
            cursor.execute('UPDATE user_files SET record_count = ? WHERE file_id = ?', (record_count, file_id))
        
        conn.commit()
        
        if progress_callback:
            progress_callback(total_lines, total_lines)
        
        return indexed, record_count
    
    except Exception as e:
        print(f"Ошибка индексации: {e}")
        return 0, 0

def search_in_index(query, is_public=True, user_id=None):
    """Поиск в индексе"""
    words = re.findall(r'[а-яёa-z0-9]+', query.lower())
    results = []
    seen = set()
    
    for word in words:
        if len(word) < 3:
            continue
        
        if is_public:
            cursor.execute('''
                SELECT file_name, line_number, full_line, preview
                FROM public_index
                WHERE word LIKE ? OR word = ?
                ORDER BY file_name, line_number
            ''', (f'%{word}%', word))
        else:
            cursor.execute('''
                SELECT file_name, line_number, full_line, preview
                FROM user_index
                WHERE user_id = ? AND (word LIKE ? OR word = ?)
                ORDER BY file_name, line_number
            ''', (user_id, f'%{word}%', word))
        
        for row in cursor.fetchall():
            key = f"{row[0]}_{row[1]}"
            if key not in seen:
                seen.add(key)
                results.append({
                    'file': row[0],
                    'line': row[1],
                    'full_line': row[2],
                    'preview': row[3]
                })
    
    return results

def generate_report(query, results, user_info):
    """Генерация отчета"""
    now = datetime.now()
    date_str = now.strftime("%d.%m.%Y %H:%M")
    
    html = f"""<!DOCTYPE html>
<html>
<head><title>PALLADIUM REPORT</title></head>
<body>
<h1>PALLADIUM SEARCH REPORT</h1>
<p>Query: {query}</p>
<p>User: {user_info['name']} (ID: {user_info['id']})</p>
<p>Date: {date_str}</p>
<p>Results found: {len(results)}</p>
<hr>
"""
    for i, r in enumerate(results[:20], 1):
        html += f"<h3>{i}. {r['file']}:{r['line']}</h3>"
        html += f"<pre>{r['full_line']}</pre>"
    
    html += "</body></html>"
    return html

# === КОМАНДЫ БОТА ===

@bot.message_handler(commands=['start'])
def start_command(message):
    register_user(message)
    user_id = message.from_user.id
    
    welcome = f"""
🔍 PALLADIUM BOT 24/7
{'👑 АДМИН' if is_admin(user_id) else '👤 ПОЛЬЗОВАТЕЛЬ'}

✅ Бот работает круглосуточно
✅ Данные сохраняются на GitHub
✅ При перезапуске ничего не пропадает

📌 КОМАНДЫ:
/search [текст] - поиск
/mysearch [текст] - поиск по личным
/addfile - добавить файл
/myfiles - мои файлы
/admin_add - добавить общий (админ)
"""
    bot.reply_to(message, welcome)

@bot.message_handler(commands=['search', 's'])
def search_command(message):
    query = message.text.replace('/search', '').replace('/s', '').strip()
    
    if not query:
        bot.reply_to(message, "❌ Введите запрос. Пример: /search Иванов")
        return
    
    status_msg = bot.reply_to(message, f"🔍 Поиск: {query}...")
    
    try:
        results = search_in_index(query, is_public=True)
        
        if not results:
            bot.edit_message_text("❌ Ничего не найдено", message.chat.id, status_msg.message_id)
            return
        
        bot.edit_message_text(f"✅ Найдено {len(results)} совпадений", 
                            message.chat.id, status_msg.message_id)
        
        user_info = {
            'id': message.from_user.id,
            'name': message.from_user.first_name or "Пользователь",
            'username': message.from_user.username or "нет"
        }
        
        html_report = generate_report(query, results, user_info)
        
        report_filename = f"report_{message.from_user.id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
        
        with open(report_filename, 'w', encoding='utf-8') as f:
            f.write(html_report)
        
        with open(report_filename, 'rb') as f:
            bot.send_document(
                message.chat.id, 
                f,
                caption=f"📋 ОТЧЕТ\nЗапрос: {query}\nНайдено: {len(results)}"
            )
        
        os.remove(report_filename)
        bot.delete_message(message.chat.id, status_msg.message_id)
        
        cursor.execute('UPDATE users SET search_count = search_count + 1 WHERE user_id = ?', 
                      (message.from_user.id,))
        conn.commit()
        
    except Exception as e:
        bot.edit_message_text(f"❌ Ошибка: {e}", message.chat.id, status_msg.message_id)

@bot.message_handler(commands=['mysearch', 'ms'])
def mysearch_command(message):
    query = message.text.replace('/mysearch', '').replace('/ms', '').strip()
    user_id = message.from_user.id
    
    if not query:
        bot.reply_to(message, "❌ Введите запрос. Пример: /mysearch Иванов")
        return
    
    status_msg = bot.reply_to(message, f"🔍 Поиск в ваших файлах: {query}...")
    
    try:
        results = search_in_index(query, is_public=False, user_id=user_id)
        
        if not results:
            bot.edit_message_text("❌ В ваших файлах ничего нет", message.chat.id, status_msg.message_id)
            return
        
        bot.edit_message_text(f"✅ Найдено {len(results)} совпадений", 
                            message.chat.id, status_msg.message_id)
        
        user_info = {
            'id': user_id,
            'name': message.from_user.first_name or "Пользователь",
            'username': message.from_user.username or "нет"
        }
        
        html_report = generate_report(query, results, user_info)
        
        report_filename = f"report_{user_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
        
        with open(report_filename, 'w', encoding='utf-8') as f:
            f.write(html_report)
        
        with open(report_filename, 'rb') as f:
            bot.send_document(
                message.chat.id, 
                f,
                caption=f"📋 ОТЧЕТ (личные)\nЗапрос: {query}\nНайдено: {len(results)}"
            )
        
        os.remove(report_filename)
        bot.delete_message(message.chat.id, status_msg.message_id)
        
        cursor.execute('UPDATE users SET search_count = search_count + 1 WHERE user_id = ?', (user_id,))
        conn.commit()
        
    except Exception as e:
        bot.edit_message_text(f"❌ Ошибка: {e}", message.chat.id, status_msg.message_id)

@bot.message_handler(commands=['addfile'])
def addfile_command(message):
    user_states[message.from_user.id] = 'waiting_private_file'
    bot.reply_to(message, "📤 Отправьте файл для добавления в ЛИЧНЫЙ архив")

@bot.message_handler(commands=['myfiles'])
def myfiles_command(message):
    user_id = message.from_user.id
    
    cursor.execute('''
        SELECT file_name, file_size, record_count, upload_date 
        FROM user_files 
        WHERE user_id = ? 
        ORDER BY upload_date DESC
    ''', (user_id,))
    
    files = cursor.fetchall()
    
    if not files:
        bot.reply_to(message, "📁 У вас нет личных файлов")
        return
    
    response = "📁 ВАШИ ФАЙЛЫ:\n\n"
    
    for i, f in enumerate(files, 1):
        size_mb = f[1] / (1024*1024)
        response += f"{i}. {f[0]} ({size_mb:.1f} МБ, {f[2]} записей)\n"
    
    bot.reply_to(message, response)

@bot.message_handler(commands=['admin_add'])
def admin_add_command(message):
    if not is_admin(message.from_user.id):
        bot.reply_to(message, "❌ Только для администратора")
        return
    
    user_states[message.from_user.id] = 'waiting_public_file'
    bot.reply_to(message, "📤 Отправьте файл для добавления в ОБЩИЕ базы")

@bot.message_handler(commands=['admin_list'])
def admin_list_command(message):
    if not is_admin(message.from_user.id):
        bot.reply_to(message, "❌ Только для администратора")
        return
    
    cursor.execute('SELECT file_name, file_size, record_count, upload_date FROM public_files ORDER BY upload_date DESC')
    files = cursor.fetchall()
    
    if not files:
        bot.reply_to(message, "📁 Общих файлов пока нет")
        return
    
    response = "📁 ОБЩИЕ ФАЙЛЫ:\n\n"
    
    for i, f in enumerate(files, 1):
        size_mb = f[1] / (1024*1024)
        response += f"{i}. {f[0]} ({size_mb:.1f} МБ, {f[2]} записей)\n"
    
    bot.reply_to(message, response)

@bot.message_handler(commands=['stats'])
def stats_command(message):
    cursor.execute('SELECT COUNT(*) FROM users')
    total_users = cursor.fetchone()[0]
    
    cursor.execute('SELECT COUNT(*) FROM public_files')
    public_files = cursor.fetchone()[0]
    
    cursor.execute('SELECT COUNT(*) FROM user_files')
    user_files = cursor.fetchone()[0]
    
    stats = f"""
📊 СТАТИСТИКА

👥 Пользователей: {total_users}
📁 Общих файлов: {public_files}
📂 Личных файлов: {user_files}

💾 База данных сохраняется на GitHub
🔄 Автосохранение каждые 5 минут
"""
    
    bot.reply_to(message, stats)

@bot.message_handler(commands=['ping'])
def ping_command(message):
    bot.reply_to(message, "🏓 Pong! Бот работает 24/7")

@bot.message_handler(content_types=['document'])
def handle_file(message):
    user_id = message.from_user.id
    file_id = message.document.file_id
    file_name = message.document.file_name
    file_size = message.document.file_size
    
    if not (file_name.endswith('.csv') or file_name.endswith('.txt')):
        bot.reply_to(message, "❌ Поддерживаются только .csv и .txt")
        return
    
    status_msg = bot.reply_to(message, f"📥 Получен файл: {file_name}\n⚙️ Индексация...")
    
    try:
        file_info = bot.get_file(file_id)
        downloaded = bot.download_file(file_info.file_path)
        
        current_state = user_states.get(user_id)
        
        def update_progress(current, total):
            percent = int(current / total * 100)
            bot.edit_message_text(
                f"📥 Файл: {file_name}\n⚙️ Индексация: {percent}% ({current}/{total} строк)",
                message.chat.id,
                status_msg.message_id
            )
        
        if current_state == 'waiting_public_file' and is_admin(user_id):
            if file_exists_public(file_name):
                bot.edit_message_text(f"❌ Файл {file_name} уже есть", message.chat.id, status_msg.message_id)
            else:
                cursor.execute('''
                    INSERT INTO public_files (file_id, file_name, file_size, message_id, uploaded_by, upload_date)
                    VALUES (?, ?, ?, ?, ?, ?)
                ''', (file_id, file_name, file_size, message.message_id, user_id, datetime.now().isoformat()))
                conn.commit()
                
                indexed, records = index_file(file_id, file_name, downloaded, is_public=True, progress_callback=update_progress)
                
                bot.edit_message_text(f"✅ Файл {file_name} добавлен в ОБЩИЕ\n📊 Записей: {records}", 
                                    message.chat.id, status_msg.message_id)
                
                # Сохраняем БД после добавления
                upload_db()
        
        elif current_state == 'waiting_private_file':
            if file_exists_user(user_id, file_name):
                bot.edit_message_text(f"❌ Файл {file_name} уже есть", message.chat.id, status_msg.message_id)
            else:
                cursor.execute('''
                    INSERT INTO user_files (user_id, file_id, file_name, file_size, message_id, upload_date)
                    VALUES (?, ?, ?, ?, ?, ?)
                ''', (user_id, file_id, file_name, file_size, message.message_id, datetime.now().isoformat()))
                conn.commit()
                
                indexed, records = index_file(file_id, file_name, downloaded, is_public=False, user_id=user_id, progress_callback=update_progress)
                
                bot.edit_message_text(f"✅ Файл {file_name} добавлен в ЛИЧНЫЕ\n📊 Записей: {records}", 
                                    message.chat.id, status_msg.message_id)
                
                # Сохраняем БД после добавления
                upload_db()
        
        else:
            bot.edit_message_text("❌ Сначала выберите команду:\n/admin_add - для общих\n/addfile - для личных", 
                                message.chat.id, status_msg.message_id)
        
        user_states.pop(user_id, None)
        
    except Exception as e:
        bot.edit_message_text(f"❌ Ошибка: {e}", message.chat.id, status_msg.message_id)

# === ЗАПУСК ===
if __name__ == '__main__':
    print("=" * 50)
    print("🚀 ЗАПУСК БОТА PALLADIUM 24/7")
    print("=" * 50)
    print("✅ База данных загружена с GitHub")
    print("✅ Автосохранение каждые 5 минут")
    print("=" * 50)
    
    while True:
        try:
            bot.infinity_polling(timeout=60)
        except Exception as e:
            print(f"❌ Ошибка: {e}")
            time.sleep(5)
