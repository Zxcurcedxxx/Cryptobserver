import telebot
import os
import requests
import json
import sqlite3
import matplotlib.pyplot as plt
from datetime import datetime
from telebot import types
from io import BytesIO
import time
import threading

BOT_TOKEN = "7910876699:AAF7CB7l2oPG6TAHYub9QYeRF5EVmw4IDMo"  
COINAPI_KEY = "be4f912e-3174-4a2e-ba64-d840b34bd66f"  

DATABASE_NAME = "crypto_bot.db"

bot = telebot.TeleBot(BOT_TOKEN)

def get_crypto_price(coin_id, currency="usd"):
    """Получает текущую цену криптовалюты с CoinGecko."""
    url = f"https://api.coingecko.com/api/v3/simple/price?ids={coin_id}&vs_currencies={currency.lower()}"
    try:
        response = requests.get(url)
        response.raise_for_status()
        data = response.json()
        return data[coin_id][currency.lower()]
    except requests.exceptions.RequestException as e:
        print(f"API Error: {e}")
        return None
    except (KeyError, ValueError) as e:
        print(f"Error parsing price data: {e}")
        return None
    except (KeyError, ValueError):
        print("Error parsing API response.")
        return None

#Тут запросы к api 
def get_historical_data(symbol, currency="USD", days="30"):
   
    url = f"https://api.coingecko.com/api/v3/coins/{symbol.lower()}/market_chart?vs_currency={currency.lower()}&days={days}"
    try:
        response = requests.get(url)
        response.raise_for_status()
        data = response.json()
        # CoinGecko возвращает список списков: [[timestamp, price], [timestamp, price], ...]
        historical_prices = [item[1] for item in data['prices']]
        return historical_prices
    except requests.exceptions.HTTPError as e:
        print(f"API Error: HTTP Error {e.response.status_code}: {e}")
        return None
    except requests.exceptions.RequestException as e:
        print(f"API Error: {e}")
        return None
    except (KeyError, ValueError):
        print("Error parsing API response.")
        return None

# БД
def create_database():
    """Создает базу данных и таблицы."""
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            preferred_currency TEXT DEFAULT 'USD',
            language TEXT DEFAULT 'ru'
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS alerts (
            alert_id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            symbol TEXT,
            target_price REAL,
            above_or_below TEXT,  -- 'above' or 'below'
            FOREIGN KEY (user_id) REFERENCES users (user_id)
        )
    """)

    conn.commit()
    conn.close()

def get_user_preferred_currency(user_id):
    
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT preferred_currency FROM users WHERE user_id = ?", (user_id,))
    result = cursor.fetchone()
    conn.close()
    if result:
        return result[0]
    else:
        return "USD" 

def set_user_preferred_currency(user_id, currency):
    
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET preferred_currency = ? WHERE user_id = ?", (currency, user_id))
    conn.commit()
    conn.close()

def add_user(user_id, username):
    
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()
    try:
        cursor.execute("INSERT INTO users (user_id, username) VALUES (?, ?)", (user_id, username))
        conn.commit()
    except sqlite3.IntegrityError:
        
        pass
    finally:
        conn.close()

def add_alert(user_id, symbol, target_price, above_or_below):
   
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()
    cursor.execute("INSERT INTO alerts (user_id, symbol, target_price, above_or_below) VALUES (?, ?, ?, ?)", (user_id, symbol, target_price, above_or_below))
    conn.commit()
    conn.close()

def get_user_alerts(user_id):
    
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT alert_id, symbol, target_price, above_or_below FROM alerts WHERE user_id = ?", (user_id,))
    alerts = cursor.fetchall()
    conn.close()
    return alerts

def remove_alert(alert_id):
    
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM alerts WHERE alert_id = ?", (alert_id,))
    conn.commit()
    conn.close()


#Тут было сложно
def generate_graph(data, symbol):
    """Генерирует график изменения цены."""
    plt.figure(figsize=(10, 5))
    plt.plot(data, color='green') 
    plt.title(f"Цена {symbol} 📈", fontsize=16) 
    plt.xlabel("Время", fontsize=12)
    plt.ylabel("Цена", fontsize=12)
    plt.grid(True, linestyle='--')  
    plt.xticks(rotation=45)  

    img = BytesIO()
    plt.savefig(img, format='png')
    img.seek(0)  

    plt.close()  
    return img

@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    user_id = message.from_user.id
    add_user(user_id, message.from_user.username)
    
    # Проверяем, есть ли у пользователя установленный язык
    if not get_user_language(user_id):
        markup = types.InlineKeyboardMarkup()
        btn_ru = types.InlineKeyboardButton("Русский 🇷🇺", callback_data='initial_lang_ru')
        btn_en = types.InlineKeyboardButton("English 🇬🇧", callback_data='initial_lang_en')
        markup.add(btn_ru, btn_en)
        bot.send_message(message.chat.id, "Выберите язык / Choose language:", reply_markup=markup)
        return
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    item1 = types.KeyboardButton("Курс 💰")  # Добавление эмоджи
    item2 = types.KeyboardButton("График 📈")  # Добавление эмоджи
    item3 = types.KeyboardButton("Профиль 👤")  # Добавление эмоджи
    item4 = types.KeyboardButton("Оповещения 🔔")  # Добавление эмоджи
    markup.add(item1, item2, item3, item4)
    bot.send_message(message.chat.id, "<b>Добро пожаловать! 👋</b> Используйте меню:", reply_markup=markup, parse_mode="HTML")  # HTML-разметка

@bot.message_handler(func=lambda message: message.text in ["Курс 💰", "Price 💰"])
def get_price_handler(message):
    markup = types.InlineKeyboardMarkup(row_width=2)
    crypto_buttons = [
        ("Bitcoin 🪙", "bitcoin"),
        ("Ethereum 💎", "ethereum"),
        ("TON 💠", "the-open-network"),
        ("USDT 💵", "tether"),
        ("BNB 🌟", "binancecoin"),
        ("Другая криптовалюта ➕", "other")
    ]
    
    for label, coin_id in crypto_buttons:
        markup.add(types.InlineKeyboardButton(label, callback_data=f'price_{coin_id}'))
    
    bot.send_message(message.chat.id, "<b>💰 Выберите криптовалюту:</b>", 
                     reply_markup=markup, parse_mode="HTML")

@bot.callback_query_handler(func=lambda call: call.data.startswith('price_'))
def handle_crypto_price_callback(call):
    crypto_labels = {
        "bitcoin": "Bitcoin",
        "ethereum": "Ethereum",
        "the-open-network": "TON",
        "tether": "USDT",
        "binancecoin": "BNB"
    }
    
    coin_id = call.data.split('_')[1]
    
    if coin_id == "other":
        bot.answer_callback_query(call.id)
        msg = bot.send_message(call.message.chat.id, "Введите ID криптовалюты (например, bitcoin):")
        bot.register_next_step_handler(msg, process_price_step)
        return
        
    currency = get_user_preferred_currency(call.from_user.id).lower()
    price = get_crypto_price(coin_id, currency)
    
    if price:
        markup = types.InlineKeyboardMarkup()
        back_button = types.InlineKeyboardButton("⬅️ Назад", callback_data="back_to_crypto_menu")
        markup.add(back_button)
        
        bot.answer_callback_query(call.id)
        bot.edit_message_text(
            f"Текущая цена <b>{crypto_labels[coin_id]}</b> в <b>{currency.upper()}</b>: <code>{price:.2f}</code>",
            call.message.chat.id,
            call.message.message_id,
            parse_mode="HTML",
            reply_markup=markup
        )
    else:
        bot.answer_callback_query(call.id, "Не удалось получить цену. Попробуйте позже.")

@bot.callback_query_handler(func=lambda call: call.data == "back_to_crypto_menu")
def back_to_crypto_menu(call):
    markup = types.InlineKeyboardMarkup(row_width=2)
    crypto_buttons = [
        ("Bitcoin 🪙", "bitcoin"),
        ("Ethereum 💎", "ethereum"),
        ("TON 💠", "the-open-network"),
        ("USDT 💵", "tether"),
        ("BNB 🌟", "binancecoin"),
        ("Другая криптовалюта ➕", "other")
    ]
    
    for label, coin_id in crypto_buttons:
        markup.add(types.InlineKeyboardButton(label, callback_data=f'price_{coin_id}'))
    
    bot.edit_message_text(
        "<b>💰 Выберите криптовалюту:</b>",
        call.message.chat.id,
        call.message.message_id,
        reply_markup=markup,
        parse_mode="HTML"
    )
    
    if price:
        bot.answer_callback_query(call.id)
        bot.edit_message_text(
            f"Текущая цена <b>{crypto_map[symbol]}</b> в <b>{currency}</b>: <code>{price:.2f}</code>",
            call.message.chat.id,
            call.message.message_id,
            parse_mode="HTML"
        )
    else:
        bot.answer_callback_query(call.id, "Не удалось получить цену. Попробуйте позже.")

@bot.message_handler(func=lambda message: message.text == "Другая криптовалюта ➕")
def other_crypto_handler(message):
    bot.send_message(message.chat.id, "Введите символ криптовалюты (например, BTC):")
    bot.register_next_step_handler(message, process_price_step)

def process_price_step(message):
    try:
        symbol = message.text.lower() #Изменено
        currency = get_user_preferred_currency(message.from_user.id)
        price = get_crypto_price(symbol, currency)
        if price:
            bot.send_message(message.chat.id, f"Текущая цена <b>{symbol}</b> в <b>{currency}</b>: <code>{price:.2f}</code>", parse_mode="HTML")
        else:
            bot.send_message(message.chat.id, "Не удалось получить цену. Проверьте символ и API.")
    except Exception as e:
        print(f"Error in process_price_step: {e}")
        bot.send_message(message.chat.id, "Произошла ошибка при получении цены.")

@bot.message_handler(func=lambda message: message.text == "График 📈")
def get_graph_handler(message):
    markup = types.InlineKeyboardMarkup(row_width=2)
    crypto_buttons = [
        ("Bitcoin 🪙", "bitcoin"),
        ("Ethereum 💎", "ethereum"),
        ("TON 💠", "the-open-network"),
        ("USDT 💵", "tether"),
        ("BNB 🌟", "binancecoin"),
        ("Другая криптовалюта ➕", "custom")
    ]
    
    for label, coin_id in crypto_buttons:
        markup.add(types.InlineKeyboardButton(label, callback_data=f'graph_{coin_id}'))
    
    bot.send_message(message.chat.id, "<b>📊 Выберите криптовалюту для графика:</b>", 
                     reply_markup=markup, parse_mode="HTML")

@bot.callback_query_handler(func=lambda call: call.data == 'graph_custom')
def handle_custom_graph_input(call):
    msg = bot.send_message(call.message.chat.id, 
                          "<b>📝 Введите ID криптовалюты с CoinGecko</b>\n"
                          "Например: <code>bitcoin</code>, <code>ethereum</code>, <code>the-open-network</code>",
                          parse_mode="HTML")
    bot.register_next_step_handler(msg, process_custom_graph_input)

def process_custom_graph_input(message):   
    coin_id = message.text.lower().strip()
    currency = get_user_preferred_currency(message.from_user.id).lower()
    try:
        historical_data = get_historical_data(coin_id, currency=currency)
        if historical_data:
            img = generate_graph(historical_data, coin_id.upper())
            bot.send_photo(message.chat.id, img, 
                         caption=f"<b>📈 График {coin_id.upper()}</b> в <b>{currency.upper()}</b>", 
                         parse_mode="HTML")
        else:
            bot.send_message(message.chat.id, "❌ Не удалось найти данные для указанной криптовалюты")
    except Exception as e:
        print(f"Error in process_custom_graph_input: {e}")
        bot.send_message(message.chat.id, "❌ Произошла ошибка при создании графика")

def process_graph_step(message):
    
    try:
        markup = types.InlineKeyboardMarkup(row_width=2)
        crypto_buttons = [
            ("Bitcoin 🪙", "bitcoin"),
            ("Ethereum 💎", "ethereum"),
            ("TON 💠", "the-open-network"),
            ("BNB 🌟", "binancecoin"),
            ("USDT 💵", "tether")
        ]
        
        buttons = []
        for label, symbol in crypto_buttons:
            buttons.append(types.InlineKeyboardButton(label, callback_data=f'graph_{symbol}'))
        markup.add(*buttons)
        
        bot.reply_to(message, "<b>📊 Выберите криптовалюту для графика:</b>", 
                    reply_markup=markup, parse_mode="HTML")
        return
        
    except Exception as e:
        print(f"Error in process_graph_step: {e}")
        bot.reply_to(message, "<b>❌ Произошла ошибка при создании графика.</b>", parse_mode="HTML")

@bot.callback_query_handler(func=lambda call: call.data.startswith('graph_'))
def handle_graph_callback(call):
   
    try:
        symbol = call.data.split('_')[1]
        currency = get_user_preferred_currency(call.from_user.id)
        historical_data = get_historical_data(symbol, currency=currency)
        
        if historical_data:
            img = generate_graph(historical_data, symbol.upper())
            bot.send_photo(call.message.chat.id, img, 
                         caption=f"<b>📈 График {symbol.upper()}</b> в <b>{currency}</b>", 
                         parse_mode="HTML")
        else:
            bot.answer_callback_query(call.id, "❌ Не удалось получить данные")
    except Exception as e:
        print(f"Error in handle_graph_callback: {e}")
        bot.answer_callback_query(call.id, "❌ Произошла ошибка")
        
        currency = get_user_preferred_currency(message.from_user.id)
        historical_data = get_historical_data(symbol, currency=currency)
        if historical_data:
            img = generate_graph(historical_data, symbol)
            bot.send_photo(message.chat.id, img, caption=f"График цены <b>{symbol}</b> в <b>{currency}</b>", parse_mode="HTML")
        else:
            bot.send_message(message.chat.id, "Не данные о валюте. Проверьте правильность ввода.")
    except Exception as e:
        print(f"Error in process_graph_step: {e}")
        bot.send_message(message.chat.id, "Произошла ошибка при создании графика.")

def get_user_language(user_id):
    
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT language FROM users WHERE user_id = ?", (user_id,))
    result = cursor.fetchone()
    conn.close()
    return result[0] if result else "ru"

def set_user_language(user_id, language):
    
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET language = ? WHERE user_id = ?", (language, user_id))
    conn.commit()
    conn.close()

@bot.message_handler(func=lambda message: message.text == "Профиль 👤")
def show_profile_handler(message):
    
    user_id = message.from_user.id
    username = message.from_user.username or "Не указано"
    preferred_currency = get_user_preferred_currency(user_id)
    language = get_user_language(user_id)
    
    
    profile_text = (
        "❯ <b>📱 Ваш Профиль</b> ❮\n\n"
        f"❯ <b>🆔 ID:</b>\n<blockquote>{user_id}</blockquote>\n"
        f"❯ <b>👤 Имя:</b>\n<blockquote>{username}</blockquote>\n"
        f"❯ <b>💰 Валюта:</b>\n<blockquote>{preferred_currency}</blockquote>\n"
        f"❯ <b>🌐 Язык:</b>\n<blockquote>{'Русский' if language == 'ru' else 'English'}</blockquote>"
    )

    
    markup = types.InlineKeyboardMarkup(row_width=2)
    btn_currency = types.InlineKeyboardButton("💰 Валюта", callback_data='show_currency')
    btn_language = types.InlineKeyboardButton("🌐 Язык", callback_data='show_language')
    markup.add(btn_currency, btn_language)

    bot.send_message(message.chat.id, profile_text, parse_mode="HTML", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data == 'show_currency')
def show_currency_options(call):
    
    current_currency = get_user_preferred_currency(call.from_user.id)
    markup = types.InlineKeyboardMarkup(row_width=2)
    
    currencies = [
        ("USD 🇺🇸", "USD"),
        ("EUR 🇪🇺", "EUR"),
        ("RUB 🇷🇺", "RUB"),
        ("USDT 💵", "USDT")
    ]
    
    buttons = []
    for label, currency in currencies:
        check_mark = "✅ " if currency == current_currency else ""
        buttons.append(types.InlineKeyboardButton(f"{check_mark}{label}", callback_data=f'currency_{currency}'))
    
    markup.add(*buttons)
    btn_back = types.InlineKeyboardButton("Назад 🔙", callback_data='back_to_profile')
    markup.add(btn_back)
    
    bot.edit_message_text("<b>💰 Выберите валюту:</b>", call.message.chat.id, call.message.message_id, 
                         reply_markup=markup, parse_mode="HTML")

@bot.callback_query_handler(func=lambda call: call.data == 'show_language')
def show_language_options(call):
    
    current_language = get_user_language(call.from_user.id)
    markup = types.InlineKeyboardMarkup()
    
    languages = [
        ("Русский 🇷🇺", "ru"),
        ("English 🇬🇧", "en")
    ]
    
    for label, lang in languages:
        check_mark = "✅ " if lang == current_language else ""
        btn = types.InlineKeyboardButton(f"{check_mark}{label}", callback_data=f'lang_{lang}')
        markup.add(btn)
    
    btn_back = types.InlineKeyboardButton("Назад 🔙", callback_data='back_to_profile')
    markup.add(btn_back)
    
    bot.edit_message_text("Choose language / Выберите язык:", call.message.chat.id, call.message.message_id, reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith('lang_') or call.data.startswith('initial_lang_'))
def change_language_callback(call):
   
    language = call.data.split('_')[1]
    user_id = call.from_user.id
    
    set_user_language(user_id, language)
    
    if language == 'ru':
        success_msg = "✅ Язык изменен на русский"
        welcome_msg = "<b>👋 Добро пожаловать!</b>"
        buttons = ["Курс 💰", "График 📈", "Профиль 👤", "Оповещения 🔔"]
    else:
        success_msg = "✅ Language changed to English"
        welcome_msg = "<b>👋 Welcome!</b>"
        buttons = ["Price 💰", "Chart 📈", "Profile 👤", "Alerts 🔔"]
    
    bot.answer_callback_query(call.id, success_msg)
    
    
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    for btn in buttons:
        markup.add(types.KeyboardButton(btn))
    
    if call.data.startswith('initial_lang_'):
        bot.send_message(call.message.chat.id, welcome_msg, reply_markup=markup, parse_mode="HTML")
    else:
        bot.delete_message(call.message.chat.id, call.message.message_id)
        bot.send_message(call.message.chat.id, welcome_msg, reply_markup=markup, parse_mode="HTML")
    
    if call.data.startswith('initial_lang_'):
        bot.send_message(call.message.chat.id, welcome_msg, reply_markup=markup, parse_mode="HTML")
    else:
        
        bot.edit_message_text(success_msg, call.message.chat.id, call.message.message_id)
        bot.send_message(call.message.chat.id, welcome_msg, reply_markup=markup, parse_mode="HTML")
        show_profile_handler(call.message)

@bot.callback_query_handler(func=lambda call: call.data == 'back_to_profile')
def back_to_profile_callback(call):
    
    show_profile_handler(call.message)

@bot.callback_query_handler(func=lambda call: call.data.startswith('currency_'))
def change_currency_callback(call):
    
    currency = call.data.split('_')[1]
    set_user_preferred_currency(call.from_user.id, currency)
    bot.answer_callback_query(call.id, f"Валюта изменена на {currency}")
    show_currency_options(call)  # Обновляем меню выбора валюты

@bot.message_handler(func=lambda message: message.text == "Оповещения 🔔")
def alerts_handler(message):
    
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    item1 = types.KeyboardButton("Создать оповещение ➕")  
    item2 = types.KeyboardButton("Список оповещений 📜") 
    item3 = types.KeyboardButton("Назад 🔙") 
    markup.add(item1, item2, item3)
    bot.send_message(message.chat.id, "Оповещения:", reply_markup=markup)

@bot.message_handler(func=lambda message: message.text == "Создать оповещение ➕")
def create_alert_handler(message):
   
    bot.send_message(message.chat.id, "Введите символ криптовалюты (например, bitcoin):") #Изменено
    bot.register_next_step_handler(message, process_alert_symbol_step)

def process_alert_symbol_step(message):
    
    try:
        symbol = message.text.lower() #Изменено
        bot.send_message(message.chat.id, "Введите целевую цену:")
        bot.register_next_step_handler(message, process_alert_price_step, symbol)
    except Exception as e:
        print(f"Error in process_alert_symbol_step: {e}")
        bot.send_message(message.chat.id, "Произошла ошибка.")

def process_alert_price_step(message, symbol):
    
    try:
        target_price = float(message.text)
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
        item1 = types.KeyboardButton("Выше ⬆️")
        item2 = types.KeyboardButton("Ниже ⬇️")
        markup.add(item1, item2)
        bot.send_message(message.chat.id, "При достижении какого уровня цены оповестить?", reply_markup=markup)
        bot.register_next_step_handler(message, process_alert_above_below_step, symbol, target_price)
    except ValueError:
        bot.send_message(message.chat.id, "Некорректный формат цены. Введите число.")
    except Exception as e:
        print(f"Error in process_alert_price_step: {e}")
        bot.send_message(message.chat.id, "Произошла ошибка.")

def process_alert_above_below_step(message, symbol, target_price):
    
    try:
        above_or_below = message.text.split()[0].lower()
        if above_or_below in ("выше", "ниже"):
            add_alert(message.from_user.id, symbol, target_price, above_or_below)
            bot.send_message(message.chat.id, f"Оповещение создано: <b>{symbol}</b> при <b>{above_or_below}</b> <code>{target_price}</code>", reply_markup=types.ReplyKeyboardRemove(), parse_mode="HTML")
        else:
            bot.send_message(message.chat.id, "Некорректный ввод. Выберите 'Выше' или 'Ниже'.", reply_markup=types.ReplyKeyboardRemove())
    except Exception as e:
        print(f"Error in process_alert_above_below_step: {e}")
        bot.send_message(message.chat.id, "Произошла ошибка.", reply_markup=types.ReplyKeyboardRemove())

@bot.message_handler(func=lambda message: message.text == "Список оповещений 📜")
def list_alerts_handler(message):
    
    alerts = get_user_alerts(message.from_user.id)
    if alerts:
        message_text = "<b>🔔 Ваши оповещения:</b>\n\n"
        for alert_id, symbol, target_price, above_or_below in alerts:
            message_text += f"<b>💎 {symbol}</b>\n" \
                          f"<b>📊 Условие:</b> <code>{above_or_below}</code>\n" \
                          f"<b>💵 Цена:</b> <code>{target_price}</code>\n" \
                          f"<b>🔑 ID:</b> <code>{alert_id}</code>\n\n"

        # Добавляем кнопки для удаления оповещений
        markup = types.InlineKeyboardMarkup()
        for alert_id, _, _, _ in alerts:
            btn = types.InlineKeyboardButton(f"Удалить {alert_id} 🗑️", callback_data=f"delete_alert_{alert_id}")
            markup.add(btn)

        bot.send_message(message.chat.id, message_text, reply_markup=markup, parse_mode="HTML")
    else:
        bot.send_message(message.chat.id, "У вас нет активных оповещений.")

@bot.callback_query_handler(func=lambda call: call.data.startswith('delete_alert_'))
def delete_alert_callback(call):
    
    alert_id = int(call.data.split('_')[2])
    remove_alert(alert_id)
    bot.answer_callback_query(call.id, f"Оповещение {alert_id} удалено")
    bot.send_message(call.message.chat.id, f"Оповещение <code>{alert_id}</code> удалено", parse_mode="HTML")
    # Обновляем список оповещений
    list_alerts_handler(call.message)

@bot.message_handler(func=lambda message: message.text == "Назад 🔙")
def back_to_menu(message):
    """Возвращает в главное меню."""
    send_welcome(message)

def check_alerts():
    
    while True:
        conn = sqlite3.connect(DATABASE_NAME)
        cursor = conn.cursor()
        cursor.execute("SELECT alert_id, user_id, symbol, target_price, above_or_below FROM alerts")
        alerts = cursor.fetchall()
        conn.close()

        for alert_id, user_id, symbol, target_price, above_or_below in alerts:
            try:
                current_price = get_crypto_price(symbol)
                if current_price:
                    if above_or_below == "выше" and current_price >= target_price:
                        bot.send_message(user_id, f"🔔 Внимание! Цена <b>{symbol}</b> достигла <code>{current_price:.2f}</code>, выше <code>{target_price}</code>! 🚀", parse_mode="HTML")
                        remove_alert(alert_id)  
                    elif above_or_below == "ниже" and current_price <= target_price:
                        bot.send_message(user_id, f"🔔 Внимание! Цена <b>{symbol}</b> достигла <code>{current_price:.2f}</code>, ниже <code>{target_price}</code>! 📉", parse_mode="HTML")
                        remove_alert(alert_id)  
                else:
                    print(f"Не удалось получить цену для {symbol} при проверке оповещений.")
            except Exception as e:
                print(f"Ошибка при проверке оповещения: {e}")
        time.sleep(60) 


# --- Запуск ---
if __name__ == '__main__':
    create_database()

    import threading
    alert_thread = threading.Thread(target=check_alerts)
    alert_thread.daemon = True 
    alert_thread.start()

    bot.infinity_polling()

