#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Palladium Bot - РАБОЧАЯ ВЕРСИЯ С БЫСТРЫМ ПОИСКОМ
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
from flask import Flask
import threading

# ===== НАСТРОЙКИ =====
TOKEN = "8621913179:AAHoiUHkluY_9PHlA3GI8VTeI0zrKAEeXmU"
ADMIN_ID = 7656295632

bot = telebot.TeleBot(TOKEN)
app = Flask(__name__)

# === БАЗА ДАННЫХ ===
DB_FILE = "palladium.db"

def get_db():
    """Получить соединение с БД"""
    conn = sqlite3.connect(DB_FILE, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """Создание таблиц"""
    conn = get_db()
    cursor = conn.cursor()
    
    # Таблица пользователей
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
    
    # Таблица файлов
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS files (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            file_id TEXT,
            file_name TEXT,
            file_size INTEGER,
            message_id INTEGER,
            uploaded_by INTEGER,
            upload_date TEXT,
            is_public INTEGER DEFAULT 0,
            total_lines INTEGER DEFAULT 0
        )
    ''')
    
    # Индекс для поиска
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS index_words (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            word TEXT,
            file_id INTEGER,
            line_number INTEGER,
            full_line TEXT,
            preview TEXT,
            FOREIGN KEY(file_id) REFERENCES files(id)
        )
    ''')
    
    # Индекс для быстрого поиска
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_word ON index_words(word)')
    
    conn.commit()
    conn.close()

# Инициализируем БД
init_db()

# === СОСТОЯНИЯ ПОЛЬЗОВАТЕЛЕЙ ===
user_states = {}

# === ФУНКЦИИ ===

def is_admin(user_id):
    return user_id == ADMIN_ID

def register_user(message):
    user_id = message.from_user.id
    username = message.from_user.username or ""
    first_name = message.from_user.first_name or ""
    
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute('''
        INSERT OR IGNORE INTO users (user_id, username, first_name, registered_date)
        VALUES (?, ?, ?, ?)
    ''', (user_id, username, first_name, datetime.now().isoformat()))
    
    if user_id == ADMIN_ID:
        cursor.execute('UPDATE users SET is_admin = 1 WHERE user_id = ?', (user_id,))
    
    conn.commit()
    conn.close()

def index_file(file_id, file_name, content, uploaded_by, progress_callback=None):
    """Индексация файла для поиска"""
    try:
        text = content.decode('utf-8', errors='ignore')
        lines = text.split('\n')
        total_lines = len(lines)
        indexed = 0
        
        conn = get_db()
        cursor = conn.cursor()
        
        # Сохраняем информацию о файле
        cursor.execute('''
            INSERT INTO files (file_id, file_name, file_size, message_id, uploaded_by, upload_date, total_lines)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (file_id, file_name, len(content), 0, uploaded_by, datetime.now().isoformat(), total_lines))
        
        file_db_id = cursor.lastrowid
        
        # Индексируем строки
        batch = []
        for line_num, line in enumerate(lines, 1):
            if not line.strip():
                continue
            
            # Извлекаем слова
            words = re.findall(r'[а-яёa-z0-9]+', line.lower())
            unique_words = set(words)
            
            for word in unique_words:
                if len(word) > 2:
                    preview = line[:100] + "..." if len(line) > 100 else line
                    batch.append((word, file_db_id, line_num, line, preview))
            
            # Сохраняем пачками по 1000
            if len(batch) >= 1000:
                cursor.executemany('''
                    INSERT INTO index_words (word, file_id, line_number, full_line, preview)
                    VALUES (?, ?, ?, ?, ?)
                ''', batch)
                batch = []
                conn.commit()
                
                if progress_callback:
                    progress_callback(line_num, total_lines)
        
        # Сохраняем остаток
        if batch:
            cursor.executemany('''
                INSERT INTO index_words (word, file_id, line_number, full_line, preview)
                VALUES (?, ?, ?, ?, ?)
            ''', batch)
            conn.commit()
        
        conn.close()
        
        if progress_callback:
            progress_callback(total_lines, total_lines)
        
        return indexed
    
    except Exception as e:
        print(f"Ошибка индексации: {e}")
        return 0

# === ИСПРАВЛЕННАЯ ФУНКЦИЯ ПОИСКА ===
def search_in_index(query, limit=100):
    """Поиск в индексе - ИСПРАВЛЕННАЯ ВЕРСИЯ"""
    words = re.findall(r'[а-яёa-z0-9]+', query.lower())
    if not words:
        return []
    
    conn = get_db()
    cursor = conn.cursor()
    results = []
    seen = set()
    
    # Для одного слова - как было
    if len(words) == 1:
        cursor.execute('''
            SELECT DISTINCT i.line_number, i.full_line, i.preview, f.file_name, f.id
            FROM index_words i
            JOIN files f ON i.file_id = f.id
            WHERE i.word = ? OR i.word LIKE ?
            ORDER BY i.line_number
            LIMIT ?
        ''', (words[0], f'%{words[0]}%', limit))
        
        for row in cursor.fetchall():
            key = f"{row[4]}_{row[0]}"
            if key not in seen:
                seen.add(key)
                results.append({
                    'file': row[3],
                    'line': row[0],
                    'full_line': row[1],
                    'preview': row[2],
                    'file_id': row[4]
                })
    
    # Для нескольких слов - ищем ТОЛЬКО там, где есть ВСЕ слова!
    else:
        # Строим сложный запрос: ищем строки, где есть все слова
        placeholders = ','.join(['?'] * len(words))
        
        # Находим все строки, где встречаются наши слова
        cursor.execute(f'''
            SELECT line_number, file_id, COUNT(DISTINCT word) as word_count
            FROM index_words
            WHERE word IN ({placeholders})
            GROUP BY file_id, line_number
            HAVING word_count = ?
            ORDER BY file_id, line_number
            LIMIT ?
        ''', words + [len(words), limit])
        
        matching_lines = cursor.fetchall()
        
        # Для каждой найденной строки получаем полные данные
        for line_num, file_id, _ in matching_lines:
            cursor.execute('''
                SELECT i.full_line, i.preview, f.file_name
                FROM index_words i
                JOIN files f ON i.file_id = f.id
                WHERE i.file_id = ? AND i.line_number = ?
                LIMIT 1
            ''', (file_id, line_num))
            
            row = cursor.fetchone()
            if row:
                key = f"{file_id}_{line_num}"
                if key not in seen:
                    seen.add(key)
                    results.append({
                        'file': row[2],
                        'line': line_num,
                        'full_line': row[0],
                        'preview': row[1],
                        'file_id': file_id
                    })
    
    conn.close()
    return results

def get_public_files():
    """Получить список общих файлов"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM files WHERE is_public = 1 ORDER BY upload_date DESC')
    files = cursor.fetchall()
    conn.close()
    return [dict(f) for f in files]

def make_file_public(file_id):
    """Сделать файл общим"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('UPDATE files SET is_public = 1 WHERE id = ?', (file_id,))
    conn.commit()
    conn.close()

def get_user_files(user_id):
    """Получить файлы пользователя"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM files WHERE uploaded_by = ? ORDER BY upload_date DESC', (user_id,))
    files = cursor.fetchall()
    conn.close()
    return [dict(f) for f in files]

def generate_html_report(query, results, user_info):
    """Генерация HTML отчета"""
    now = datetime.now()
    
    html = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>Palladium Search Report</title>
    <style>
        body {{
            font-family: 'Courier New', monospace;
            background: #1a1a1a;
            color: #fff;
            padding: 20px;
        }}
        .container {{
            max-width: 1000px;
            margin: 0 auto;
            background: #2d2d2d;
            border: 1px solid #ff0000;
            padding: 20px;
        }}
        h1 {{
            color: #ff0000;
            border-bottom: 2px solid #ff0000;
            padding-bottom: 10px;
        }}
        .query {{
            background: #000;
            padding: 15px;
            margin: 20px 0;
            border-left: 5px solid #ff0000;
        }}
        .result {{
            background: #1f1f1f;
            border: 1px solid #333;
            padding: 15px;
            margin: 10px 0;
        }}
        .result:hover {{
            border-color: #ff0000;
        }}
        .file-name {{
            color: #ff0000;
            font-size: 14px;
        }}
        .line-number {{
            color: #888;
            font-size: 12px;
        }}
        .content {{
            color: #fff;
            font-size: 14px;
            margin-top: 10px;
            white-space: pre-wrap;
        }}
        .footer {{
            margin-top: 30px;
            color: #888;
            font-size: 12px;
            text-align: right;
        }}
    </style>
</head>
<body>
    <div class="container">
        <h1>🔍 PALLADIUM SEARCH REPORT</h1>
        
        <div class="query">
            <strong>Запрос:</strong> {query}<br>
            <strong>Пользователь:</strong> {user_info['name']} (ID: {user_info['id']})<br>
            <strong>Время:</strong> {now.strftime('%d.%m.%Y %H:%M:%S')}<br>
            <strong>Найдено:</strong> {len(results)} совпадений
        </div>
        
        <h2>Результаты:</h2>
"""
    
    for i, r in enumerate(results[:50], 1):
        html += f"""
        <div class="result">
            <div class="file-name">📁 {r['file']} <span class="line-number">(строка {r['line']})</span></div>
            <div class="content">{r['full_line']}</div>
        </div>
"""
    
    if len(results) > 50:
        html += f"<p>... и еще {len(results) - 50} результатов</p>"
    
    html += f"""
        <div class="footer">
            Отчет сформирован системой PALLADIUM<br>
            Хеш: {hashlib.md5(f"{query}{now}".encode()).hexdigest()[:16].upper()}
        </div>
    </div>
</body>
</html>"""
    
    return html

# === ВЕБ-СЕРВЕР ===
@app.route('/')
def home():
    return "Palladium Bot is running! Telegram: @PalladiumDataBot"

# === КОМАНДЫ ===

@bot.message_handler(commands=['start'])
def start_command(message):
    register_user(message)
    user_id = message.from_user.id
    
    welcome = f"""
🔍 **PALLADIUM BOT - ПОЛНАЯ ВЕРСИЯ**
{'👑 АДМИНИСТРАТОР' if is_admin(user_id) else '👤 ПОЛЬЗОВАТЕЛЬ'}

📌 **ПОИСК:**
/search [текст] - быстрый поиск по всем файлам
/s [текст] - сокращенно
/report [текст] - поиск с HTML отчетом

📌 **ФАЙЛЫ:**
/upload - загрузить файл (индексация)
/myfiles - мои файлы
/public - общие файлы

📌 **ГЕНЕРАТОРЫ:**
/password [длина] - пароль
/identity - личность
/card - карта

📌 **АДМИНИСТРАТОРУ:**
/admin_list - все файлы
/admin_add [id] - сделать общим
/admin_delete [id] - удалить файл

📌 **СИСТЕМА:**
/stats - статистика
/ping - проверка
/id - ваш ID
    """
    bot.reply_to(message, welcome, parse_mode='Markdown')

@bot.message_handler(commands=['search', 's'])
def search_command(message):
    """Быстрый поиск"""
    query = message.text.replace('/search', '').replace('/s', '').strip()
    
    if not query:
        bot.reply_to(message, "❌ Введите запрос. Пример: /search Иван")
        return
    
    status_msg = bot.reply_to(message, f"🔍 Ищу: {query}...")
    
    start_time = time.time()
    results = search_in_index(query, limit=50)
    search_time = time.time() - start_time
    
    if not results:
        bot.edit_message_text(f"❌ Ничего не найдено за {search_time:.2f} сек", 
                            message.chat.id, status_msg.message_id)
        return
    
    response = f"✅ Найдено {len(results)} совпадений за {search_time:.2f} сек:\n\n"
    
    # Группируем по файлам
    by_file = {}
    for r in results:
        if r['file'] not in by_file:
            by_file[r['file']] = []
        by_file[r['file']].append(r)
    
    for file_name, file_results in list(by_file.items())[:3]:
        response += f"📁 **{file_name}** ({len(file_results)})\n"
        for r in file_results[:3]:
            preview = r['full_line'][:100] + "..." if len(r['full_line']) > 100 else r['full_line']
            response += f"   • стр.{r['line']}: {preview}\n"
        if len(file_results) > 3:
            response += f"   ... и еще {len(file_results)-3}\n"
        response += "\n"
    
    if len(by_file) > 3:
        response += f"... и еще в {len(by_file)-3} файлах"
    
    bot.edit_message_text(response, message.chat.id, status_msg.message_id, parse_mode='Markdown')

@bot.message_handler(commands=['report'])
def report_command(message):
    """Поиск с HTML отчетом"""
    query = message.text.replace('/report', '').strip()
    
    if not query:
        bot.reply_to(message, "❌ Введите запрос. Пример: /report Иван")
        return
    
    status_msg = bot.reply_to(message, f"🔍 Поиск: {query}\n📄 Формирование отчета...")
    
    try:
        results = search_in_index(query, limit=200)
        
        if not results:
            bot.edit_message_text("❌ Ничего не найдено", message.chat.id, status_msg.message_id)
            return
        
        user_info = {
            'id': message.from_user.id,
            'name': message.from_user.first_name or "Пользователь",
            'username': message.from_user.username or "нет"
        }
        
        html = generate_html_report(query, results, user_info)
        
        filename = f"report_{message.from_user.id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
        with open(filename, 'w', encoding='utf-8') as f:
            f.write(html)
        
        with open(filename, 'rb') as f:
            bot.send_document(
                message.chat.id,
                f,
                caption=f"📋 Отчет по запросу '{query}'\nНайдено: {len(results)} совпадений"
            )
        
        os.remove(filename)
        bot.delete_message(message.chat.id, status_msg.message_id)
        
    except Exception as e:
        bot.edit_message_text(f"❌ Ошибка: {e}", message.chat.id, status_msg.message_id)

@bot.message_handler(commands=['upload'])
def upload_command(message):
    user_states[message.from_user.id] = 'waiting_file'
    bot.reply_to(message, "📤 Отправьте файл (.csv или .txt) для индексации")

@bot.message_handler(content_types=['document'])
def handle_file(message):
    user_id = message.from_user.id
    file_id = message.document.file_id
    file_name = message.document.file_name
    file_size = message.document.file_size
    
    if not (file_name.endswith('.csv') or file_name.endswith('.txt')):
        bot.reply_to(message, "❌ Поддерживаются только .csv и .txt")
        return
    
    if user_states.get(user_id) != 'waiting_file':
        bot.reply_to(message, "❌ Сначала введите /upload")
        return
    
    status_msg = bot.reply_to(message, f"📥 Получен файл: {file_name}\n⚙️ Индексация...")
    
    try:
        file_info = bot.get_file(file_id)
        downloaded = bot.download_file(file_info.file_path)
        
        def update_progress(current, total):
            percent = int(current / total * 100)
            bot.edit_message_text(
                f"📥 Файл: {file_name}\n⚙️ Индексация: {percent}% ({current}/{total} строк)",
                message.chat.id,
                status_msg.message_id
            )
        
        indexed = index_file(file_id, file_name, downloaded, user_id, update_progress)
        
        bot.edit_message_text(
            f"✅ Файл {file_name} проиндексирован\n📊 Проиндексировано строк: {indexed}",
            message.chat.id,
            status_msg.message_id
        )
        
        user_states.pop(user_id, None)
        
    except Exception as e:
        bot.edit_message_text(f"❌ Ошибка: {e}", message.chat.id, status_msg.message_id)

@bot.message_handler(commands=['myfiles'])
def myfiles_command(message):
    user_id = message.from_user.id
    files = get_user_files(user_id)
    
    if not files:
        bot.reply_to(message, "📁 У вас нет файлов")
        return
    
    response = "📁 **ВАШИ ФАЙЛЫ:**\n\n"
    for f in files:
        public = "🌐" if f['is_public'] else "🔒"
        size_mb = f['file_size'] / (1024*1024)
        response += f"{public} **ID {f['id']}:** {f['file_name']}\n"
        response += f"   📊 {size_mb:.1f} МБ, {f['total_lines']} строк\n"
        response += f"   📅 {f['upload_date'][:10]}\n\n"
    
    bot.reply_to(message, response, parse_mode='Markdown')

@bot.message_handler(commands=['public'])
def public_command(message):
    files = get_public_files()
    
    if not files:
        bot.reply_to(message, "📁 Общих файлов пока нет")
        return
    
    response = "🌐 **ОБЩИЕ ФАЙЛЫ:**\n\n"
    for f in files:
        size_mb = f['file_size'] / (1024*1024)
        response += f"📁 **ID {f['id']}:** {f['file_name']}\n"
        response += f"   📊 {size_mb:.1f} МБ, {f['total_lines']} строк\n"
        response += f"   📅 {f['upload_date'][:10]}\n\n"
    
    bot.reply_to(message, response, parse_mode='Markdown')

@bot.message_handler(commands=['admin_list'])
def admin_list_command(message):
    if not is_admin(message.from_user.id):
        bot.reply_to(message, "❌ Только для администратора")
        return
    
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM files ORDER BY upload_date DESC')
    files = cursor.fetchall()
    conn.close()
    
    if not files:
        bot.reply_to(message, "📁 Файлов нет")
        return
    
    response = "📁 **ВСЕ ФАЙЛЫ:**\n\n"
    for f in files:
        public = "🌐" if f['is_public'] else "🔒"
        size_mb = f['file_size'] / (1024*1024)
        response += f"{public} **ID {f['id']}:** {f['file_name']}\n"
        response += f"   👤 Загрузил: {f['uploaded_by']}\n"
        response += f"   📊 {size_mb:.1f} МБ, {f['total_lines']} строк\n"
        response += f"   📅 {f['upload_date'][:10]}\n\n"
    
    bot.reply_to(message, response, parse_mode='Markdown')

@bot.message_handler(commands=['admin_add'])
def admin_add_command(message):
    if not is_admin(message.from_user.id):
        bot.reply_to(message, "❌ Только для администратора")
        return
    
    parts = message.text.split()
    if len(parts) != 2:
        bot.reply_to(message, "❌ Использование: /admin_add [id]")
        return
    
    try:
        file_id = int(parts[1])
        make_file_public(file_id)
        bot.reply_to(message, f"✅ Файл ID {file_id} теперь общий")
    except:
        bot.reply_to(message, "❌ Неверный ID")

@bot.message_handler(commands=['password', 'gp'])
def password_command(message):
    parts = message.text.split()
    length = 12
    
    if len(parts) > 1:
        try:
            length = int(parts[1])
            if length < 4:
                length = 4
            if l