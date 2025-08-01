import telebot
import os
import datetime
import time
import threading
import json
import random
from flask import Flask
from threading import Thread
from datetime import datetime, time, timedelta
import gspread
from oauth2client.service_account import ServiceAccountCredentials

# Motive sözler listesi
MOTIVATION = [
    "Sıcak hava seni Kur’an okumaktan tembelleştirmesin, Kur’an okumamanın zararını başka bir şeyle kapatamazsın!",
    "Bu kadar dinlenmek yeter! Hadi Kur’an dersini oku!",
    "Bari sen Kur’an okumayı terkedenlerden olma!",
    "Seni boş gündemelerine çekmeye çalışanları sen Kur’an okumaya davet et!",
    "Elindeki hazinenin farkında mısın?",
    "Kur’ana bakmayıp gününü zararla kapatma!",
    "Bugün Rabbin sana ne dedi?",
    "Hayat kitabına bakmayı unutma!",
    "Tembellik etme, Kur’an dersine çalış!",
    "Kur’andan gıdanı ihmal etme!"
]

with open("pages.json") as f:
    pages = json.load(f)

TOKEN = os.environ['TOKEN']
CHAT_ID = os.environ['CHAT_ID']  # Grup için
SHEET_ID = os.environ['SHEET_ID']
bot = telebot.TeleBot(TOKEN)
PAGE_FILE = "current_page.json"

scope = [
    'https://spreadsheets.google.com/feeds',
    'https://www.googleapis.com/auth/drive'
]
creds = ServiceAccountCredentials.from_json_keyfile_name('service_account.json', scope)
gsheet = gspread.authorize(creds)
sheet_okuma = gsheet.open_by_key(SHEET_ID).worksheet("Okuma Takip")
sheet_ceza = gsheet.open_by_key(SHEET_ID).worksheet("Cezalar")

def get_kuran_gunu(now=None):
    now = now or datetime.now()
    if now.time() < time(11, 30):
        return (now - timedelta(days=1)).strftime("%Y-%m-%d")
    else:
        return now.strftime("%Y-%m-%d")
    
# Kullanıcı Sheets'te yoksa otomatik ekle veya varsa güncelle (ad, user_id, username)
def add_or_update_user(first_name, user_id, username):
    names = sheet_okuma.col_values(1)
    user_ids = sheet_okuma.col_values(2)
    usernames = sheet_okuma.col_values(3)
    # Eğer user_id zaten varsa, adını ve username'i güncelle
    found = False
    for idx, uid in enumerate(user_ids[1:], start=2):  # başlık var
        if str(uid) == str(user_id):
            sheet_okuma.update_cell(idx, 1, first_name)
            sheet_okuma.update_cell(idx, 3, username if username else "")
            found = True
            break
    if not found:
        sheet_okuma.append_row([first_name, user_id, username if username else ""])
        print(f"Kullanıcı eklendi: {first_name} (id:{user_id})")

# Okumayanları tıklanabilir HTML mention ile listele (user_id ile)
def get_unread_mentions():
    today = get_kuran_gunu()
    names = sheet_okuma.col_values(1)[1:]
    user_ids = sheet_okuma.col_values(2)[1:]
    date_cols = sheet_okuma.row_values(1)
    try:
        col_num = date_cols.index(today) + 1
    except ValueError:
        return ""
    unread_mentions = []
    for i, (name, uid) in enumerate(zip(names, user_ids)):
        cell = sheet_okuma.cell(i + 2, col_num).value
        if cell != "✅" and uid:
            mention = f'<a href="tg://user?id={uid}">{name}</a>'
            unread_mentions.append(mention)
    return " ".join(unread_mentions)

# Hatırlatma mesajı (otomatik/manüel) - HTML parse_mode ile!
def send_motivation(chat_id):
    msg = random.choice(MOTIVATION)
    unread = get_unread_mentions()
    if unread:
        msg += f"\n\nHenüz okumayanlar: {unread}"
    bot.send_message(chat_id=chat_id, text=msg, parse_mode="HTML")

# Ceza Fonksiyonları
def add_penalty(user, amount):
    sheet_ceza.append_row([user, amount, datetime.datetime.now().strftime("%Y-%m-%d")])

def get_penalties():
    all_rows = sheet_ceza.get_all_records()
    summary = {}
    for row in all_rows:
        user = row.get('İsim') or row.get('isim') or row.get('Name') or row.get('name')
        amount = int(row.get('Ceza') or row.get('ceza') or row.get('Penalty') or 0)
        summary[user] = summary.get(user, 0) + amount
    return summary

# Günlük Okuma Tablosu Takibi
def mark_read(first_name, user_id, username, date=None):
    if date is None:
        date = get_kuran_gunu()
    # Güncel user_id ile ekle/güncelle
    add_or_update_user(first_name, user_id, username)
    names = sheet_okuma.col_values(1)
    user_ids = sheet_okuma.col_values(2)
    row_num = None
    for idx, uid in enumerate(user_ids):
        if idx == 0:
            continue  # başlık satırı
        if str(uid) == str(user_id):
            row_num = idx + 1
            break
    if row_num is None:
        return False, "Kullanıcı bulunamadı"
    try:
        date_cols = sheet_okuma.row_values(1)
        col_num = date_cols.index(date) + 1
    except ValueError:
        col_num = len(sheet_okuma.row_values(1)) + 1
        sheet_okuma.update_cell(1, col_num, date)
    sheet_okuma.update_cell(row_num, col_num, "✅")
    return True, f"{first_name} için {date} günü ✅ olarak işaretlendi."

def load_current_page():
    try:
        with open(PAGE_FILE, "r") as f:
            return json.load(f)["page"]
    except:
        return 0

def save_current_page(page_num):
    with open(PAGE_FILE, "w") as f:
        json.dump({"page": page_num}, f)

def send_page(page_num, chat_id):
    try:
        image_id = pages[page_num]
        image_url = f"https://drive.google.com/uc?export=view&id={image_id}"
        bot.send_photo(chat_id=chat_id, photo=image_url, caption=f"📖 Kur’an Sayfa {page_num + 1}")
        print(f"Sayfa {page_num + 1} gönderildi ({chat_id})")
        return True
    except Exception as e:
        print(f"Hata: {e}")
        bot.send_message(chat_id=chat_id, text="Sayfa gönderilemedi veya bulunamadı!")
        return False

def send_daily_pages(advance_page=False):
    current_page = load_current_page()
    for i in range(2):
        send_page(current_page + i, CHAT_ID)
    if advance_page:
        save_current_page(current_page + 2)

def show_who_read(chat_id):
    today = get_kuran_gunu()
    names = sheet_okuma.col_values(1)[1:]
    user_ids = sheet_okuma.col_values(2)[1:]
    date_cols = sheet_okuma.row_values(1)
    try:
        col_num = date_cols.index(today) + 1
    except ValueError:
        bot.send_message(chat_id=chat_id, text="Bugün için henüz kayıt yok.")
        return
    okuyanlar = []
    okumayanlar = []
    for i, (name, uid) in enumerate(zip(names, user_ids)):
        cell = sheet_okuma.cell(i + 2, col_num).value
        if cell == "✅":
            okuyanlar.append(f'<a href="tg://user?id={uid}">{name}</a>')
        else:
            okumayanlar.append(f'<a href="tg://user?id={uid}">{name}</a>')
    msg = "📖 <b>Bugün Okuyanlar:</b>\n"
    if okuyanlar:
        msg += "✅ " + ", ".join(okuyanlar) + "\n"
    else:
        msg += "_Henüz kimse okumadı._\n"
    msg += "\n⏳ <b>Henüz Okumayanlar:</b>\n"
    if okumayanlar:
        msg += "❌ " + ", ".join(okumayanlar)
    else:
        msg += "_Herkes okudu!_"
    bot.send_message(chat_id=chat_id, text=msg, parse_mode="HTML")

# KOMUTLAR
@bot.message_handler(commands=['gonder'])
def manual_send(message):
    current_page = load_current_page()
    send_page(current_page, message.chat.id)
    send_page(current_page + 1, message.chat.id)
    bot.send_message(chat_id=message.chat.id, text="✅ Bugünkü 2 sayfa gönderildi!")

@bot.message_handler(commands=['sayfa'])
def send_specific_page(message):
    try:
        page_num = int(message.text.split()[1]) - 1
        if 0 <= page_num < len(pages):
            send_page(page_num, message.chat.id)
            bot.send_message(chat_id=message.chat.id, text=f"✅ Sayfa {page_num+1} gönderildi!")
        else:
            bot.send_message(chat_id=message.chat.id, text=f"❌ Geçersiz sayfa (1-{len(pages)}) arası")
    except:
        bot.send_message(chat_id=message.chat.id, text="❌ Kullanım: /sayfa [sayı]")

@bot.message_handler(commands=['okudum'])
def handle_okudum(message):
    if message.chat.type == 'private':
        bot.send_message(chat_id=message.chat.id, text="Bu komut sadece grup sohbetinde kullanılabilir.")
        return
    user = message.from_user
    first_name = user.first_name
    user_id = user.id
    username = "@" + user.username if user.username else ""
    args = message.text.split()
    date = None
    if len(args) > 1:
        date = args[1]
    success, msg = mark_read(first_name, user_id, username, date)
    if success:
        bot.send_message(chat_id=message.chat.id, text=msg)
        show_who_read(message.chat.id)
    else:
        bot.send_message(chat_id=message.chat.id, text=f"Hata: {msg}")

@bot.message_handler(commands=['rapor'])
def ceza_rapor(message):
    if message.chat.type == 'private':
        bot.send_message(chat_id=message.chat.id, text="Bu komut sadece grup sohbetinde kullanılabilir.")
        return
    penalties = get_penalties()
    if not penalties:
        bot.send_message(chat_id=message.chat.id, text="📊 Hiç ceza yok.")
    else:
        report = "📊 Ceza Raporu:\n"
        for user, amount in penalties.items():
            report += f"• {user}: {amount} TL\n"
        bot.send_message(chat_id=message.chat.id, text=report)

@bot.message_handler(commands=['kimlerokudu', 'kimokudu'])
def kimler_okudu(message):
    if message.chat.type == 'private':
        bot.send_message(chat_id=message.chat.id, text="Bu komut sadece grup sohbetinde kullanılabilir.")
        return
    show_who_read(message.chat.id)

@bot.message_handler(commands=['yardim', 'komutlar', 'help'])
def komutlar_listesi(message):
    help_text = (
        "📋 <b>Kullanılabilir Komutlar:</b>\n\n"
        "<b>/gonder</b> — Bugünkü 2 Kur’an sayfasını tekrar gönderir (grup/özel).\n"
        "<b>/sayfa [n]</b> — Belirli bir Kur’an sayfasını gönderir (grup/özel).\n"
        "<b>/okudum</b> — (Grup) O gün okuduğunuzu işaretler, ardından okuyanlar tablosu gelir.\n"
        "<b>/kimlerokudu</b> — (Grup) Bugün okuyan/okumayan raporu.\n"
        "<b>/rapor</b> — (Grup) Ceza raporunu gönderir.\n"
        "<b>/hatirlat</b> — (Grup) Motive sözlerle hatırlatma.\n"
        "<b>/yardim</b> veya <b>/komutlar</b> — Bu rehberi gösterir."
    )
    bot.send_message(chat_id=message.chat.id, text=help_text, parse_mode="HTML")

@bot.message_handler(commands=['hatirlat'])
def manuel_hatirlat(message):
    if message.chat.type != 'private':
        send_motivation(message.chat.id)
    else:
        bot.send_message(chat_id=message.chat.id, text=random.choice(MOTIVATION))

@bot.message_handler(content_types=['new_chat_members'])
def welcome_new_member(message):
    for new_member in message.new_chat_members:
        username = "@" + new_member.username if new_member.username else ""
        first_name = new_member.first_name
        user_id = new_member.id
        bot.send_message(
            chat_id=message.chat.id,
            text=f"👋 Hoşgeldin {first_name} kardeşim!\nRabbim seni Kur’an ehli kılsın ve okuyanlardan eylesin. 🤲"
        )
        add_or_update_user(first_name, user_id, username)

def daily_check_and_penalty():
    gun_basi = get_kuran_gunu()
    yesterday = (datetime.datetime.strptime(gun_basi, "%Y-%m-%d") - timedelta(days=1)).strftime("%Y-%m-%d")
    names = sheet_okuma.col_values(1)[1:]
    user_ids = sheet_okuma.col_values(2)[1:]
    date_cols = sheet_okuma.row_values(1)
    try:
        col_num = date_cols.index(yesterday) + 1
    except ValueError:
        return
    penalties = []
    for i, (name, uid) in enumerate(zip(names, user_ids)):
        cell = sheet_okuma.cell(i + 2, col_num).value
        if cell != "✅":
            penalties.append(f'<a href="tg://user?id={uid}">{name}</a>')
            add_penalty(name, 10)
    if penalties:
        bot.send_message(
            chat_id=CHAT_ID,
            text=f"❗️ {yesterday} günü okuma yapmadığı için ceza alanlar:\n" + "\n".join(penalties),
            parse_mode="HTML"
        )

def scheduler():
    while True:
        now = datetime.datetime.now()
        hhmm = now.strftime("%H:%M")
        if hhmm == "11:30":
            daily_check_and_penalty()
            send_daily_pages(advance_page=True)
            time.sleep(90)
        elif now.hour >= 6 and now.hour < 24 and now.minute == 0 and now.hour % 2 == 0:
            send_motivation(CHAT_ID)
            time.sleep(60)
        time.sleep(20)

app = Flask('')

@app.route('/')
def home():
    print("Bot çalışıyor - keep alive ping alındı!")
    return "Bot çalışıyor."

def run():
    app.run(host='0.0.0.0', port=8080)

Thread(target=scheduler, daemon=True).start()
Thread(target=run).start()

print("🤖 Bot aktif...")
bot.polling()

