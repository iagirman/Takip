import telebot
import os
import random
from datetime import datetime, time, timedelta
import time as systime
import threading
import json
from flask import Flask
from threading import Thread

import gspread
from oauth2client.service_account import ServiceAccountCredentials

MOTIVATION = [
    "Sıcak hava seni Kur’an okumaktan tembelleştirmesin", 
    "Kur’an okumamanın zararını başka bir şeyle kapatamazsın!",
    "Bu kadar dinlenmek yeter! Hadi Kur’an dersini oku!",
    "Bari sen Kur’an okumayı terkedenlerden olma!",
    "Seni boş gündemlerine çekmeye çalışanları sen Kur’an okumaya davet et!",
    "Elindeki hazinenin farkında mısın?",
    "Kur’an’a bakmayıp gününü zararla kapatma!",
    "Bugün Rabbin sana ne dedi?",
    "Hayat kitabına bakmayı unutma!",
    "Tembellik etme, Kur’an dersine çalış!",
    "Kur’an’dan gıdanı ihmal etme!"
    "Haydi Ey Mücahidim"
]

TOKEN = os.environ['TOKEN']
CHAT_ID = os.environ['CHAT_ID']  # Grup için
SHEET_ID = os.environ['SHEET_ID']
bot = telebot.TeleBot(TOKEN)
PAGES_FILE = "pages.json"

scope = [
    'https://spreadsheets.google.com/feeds',
    'https://www.googleapis.com/auth/drive'
]
creds = ServiceAccountCredentials.from_json_keyfile_name('service_account.json', scope)
gsheet = gspread.authorize(creds)
sheet_okuma = gsheet.open_by_key(SHEET_ID).worksheet("Okuma Takip")
sheet_ceza = gsheet.open_by_key(SHEET_ID).worksheet("Cezalar")
sheet_ayar = gsheet.open_by_key(SHEET_ID).worksheet("BotAyar")

with open(PAGES_FILE) as f:
    pages = json.load(f)

def get_kuran_gunu(now=None):
    now = now or datetime.utcnow() + timedelta(hours=3)  # Türkiye saati!
    if now.time() < time(11, 30):
        return (now - timedelta(days=1)).strftime("%Y-%m-%d")
    else:
        return now.strftime("%Y-%m-%d")

def get_current_page():
    try:
        val = sheet_ayar.acell('A2').value
        return int(val) if val else 0
    except Exception:
        return 0

def set_current_page(val):
    sheet_ayar.update_acell('A2', str(val))

def add_or_update_user(first_name, user_id, username):
    names = sheet_okuma.col_values(1)
    user_ids = sheet_okuma.col_values(2)
    found = False
    for idx, uid in enumerate(user_ids[1:], start=2):
        if str(uid) == str(user_id):
            sheet_okuma.update_cell(idx, 1, first_name)
            sheet_okuma.update_cell(idx, 3, username if username else "")
            found = True
            break
    if not found:
        sheet_okuma.append_row([first_name, user_id, username if username else ""])
        print(f"Kullanıcı eklendi: {first_name} (id:{user_id})")

def get_user_row(username_or_id):
    # id ya da @kullaniciadi ile satır bulucu
    user_ids = sheet_okuma.col_values(2)
    usernames = sheet_okuma.col_values(3)
    username_or_id = str(username_or_id).lower().replace("@", "")
    for idx in range(1, len(user_ids)):
        if user_ids[idx] == username_or_id or usernames[idx].lower().replace("@", "") == username_or_id:
            return idx+1
    return None

def get_today_colnum():
    today = get_kuran_gunu()
    cols = sheet_okuma.row_values(1)
    try:
        return cols.index(today) + 1
    except ValueError:
        sheet_okuma.update_cell(1, len(cols) + 1, today)
        return len(cols) + 1

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
        mention = f'<a href="tg://user?id={uid}">{name}</a>'
        if cell == "✅":
            okuyanlar.append(mention)
        else:
            okumayanlar.append(mention)
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

def mark_read(first_name, user_id, username, date=None):
    if date is None:
        date = get_kuran_gunu()
    add_or_update_user(first_name, user_id, username)
    names = sheet_okuma.col_values(1)
    user_ids = sheet_okuma.col_values(2)
    row_num = None
    for idx, uid in enumerate(user_ids):
        if idx == 0:
            continue
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

def send_page(page_num, chat_id, pin=False):
    try:
        image_id = pages[page_num]
        image_url = f"https://drive.google.com/uc?export=view&id={image_id}"
        msg = bot.send_photo(chat_id=chat_id, photo=image_url, caption=f"📖 Kur’an Sayfa {page_num + 1}")
        if pin:
            try:
                bot.unpin_chat_message(chat_id)
            except Exception:
                pass
            try:
                bot.pin_chat_message(chat_id, msg.message_id)
            except Exception:
                pass
        print(f"Sayfa {page_num + 1} gönderildi ({chat_id})")
        return True
    except Exception as e:
        print(f"Hata: {e}")
        bot.send_message(chat_id=chat_id, text="Sayfa gönderilemedi veya bulunamadı!")
        return False

def send_daily_pages(advance_page=False):
    current_page = get_current_page()
    send_page(current_page, CHAT_ID, pin=True)
    send_page(current_page + 1, CHAT_ID)
    if advance_page:
        set_current_page(current_page + 2)

def add_penalty(user, amount):
    sheet_ceza.append_row([user, amount, get_kuran_gunu()])

def get_penalties():
    all_rows = sheet_ceza.get_all_records()
    summary = {}
    for row in all_rows:
        user = row.get('İsim') or row.get('isim') or row.get('Name') or row.get('name')
        amount = int(row.get('Ceza') or row.get('ceza') or row.get('Penalty') or 0)
        summary[user] = summary.get(user, 0) + amount
    return summary

def daily_check_and_penalty():
    gun_basi = get_kuran_gunu()
    yesterday = (datetime.strptime(gun_basi, "%Y-%m-%d") - timedelta(days=1)).strftime("%Y-%m-%d")
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

def send_motivation(chat_id):
    msg = random.choice(MOTIVATION)
    unread = get_unread_mentions()
    if unread:
        msg += f"\n\nHenüz okumayanlar: {unread}"
    bot.send_message(chat_id=chat_id, text=msg, parse_mode="HTML")

# === KOMUTLAR ===
@bot.message_handler(commands=['gonder'])
def manual_send(message):
    current_page = get_current_page()
    send_page(current_page, message.chat.id, pin=True)
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
    args = message.text.split()
    # Tek kişilik detaylı rapor
    if len(args) > 1:
        username = args[1].replace("@", "")
        row = get_user_row(username)
        if not row:
            bot.send_message(chat_id=message.chat.id, text="Kullanıcı bulunamadı.")
            return
        name = sheet_okuma.cell(row, 1).value
        user_id = sheet_okuma.cell(row, 2).value
        # Ceza
        penalties = get_penalties()
        ceza = penalties.get(name, 0)
        # Okuma istatistiği
        col_values = sheet_okuma.row_values(1)
        okuma_vals = sheet_okuma.row_values(row)[1:]
        okudu = sum([1 for x in okuma_vals if x == "✅"])
        eksik = sum([1 for x in okuma_vals if x != "✅" and x.strip()])
        msg = f"📋 <b>{name}</b> raporu:\n\n"
        msg += f"Toplam ceza: {ceza} TL\n"
        msg += f"Toplam okuduğu gün: {okudu}\n"
        msg += f"Kaçırdığı gün: {eksik}\n"
        if ceza >= 100:
            msg += f"⚠️ Çok yüksek ceza! Lütfen okuma alışkanlığını düzelt!\n"
        bot.send_message(chat_id=message.chat.id, text=msg, parse_mode="HTML")
        return
    # Toplu rapor
    penalties = get_penalties()
    if not penalties:
        bot.send_message(chat_id=message.chat.id, text="📊 Hiç ceza yok.")
        return
    report = "📊 Ceza Raporu:\n"
    for user, amount in penalties.items():
        report += f"• {user}: {amount} TL"
        if amount >= 100:
            report += " ⚠️ Cezanı öde güzel kardeşim canımızı sıkmaa!\n"
        else:
            report += "\n"
    bot.send_message(chat_id=message.chat.id, text=report)

@bot.message_handler(commands=['eksik'])
def eksik_komutu(message):
    args = message.text.split()
    if len(args) > 1:
        username = args[1].replace("@", "")
        row = get_user_row(username)
        if not row:
            bot.send_message(chat_id=message.chat.id, text="Kullanıcı bulunamadı.")
            return
    else:
        # Kendi özel mesajı
        if message.chat.type == 'private':
            user_id = str(message.from_user.id)
            row = get_user_row(user_id)
        else:
            bot.send_message(chat_id=message.chat.id, text="Kimin eksik günleri? /eksik [kullanıcıadı]")
            return
        if not row:
            bot.send_message(chat_id=message.chat.id, text="Kullanıcı bulunamadı.")
            return
    name = sheet_okuma.cell(row, 1).value
    col_values = sheet_okuma.row_values(1)[1:]
    okuma_vals = sheet_okuma.row_values(row)[1:]
    eksikler = []
    for i, v in enumerate(okuma_vals):
        if v != "✅" and col_values[i].strip():
            page_start = get_current_page() - (len(col_values) - i)
            page_str = f"({page_start+1}-{page_start+2})"
            eksikler.append(f"{col_values[i]} {page_str}")
    if not eksikler:
        bot.send_message(chat_id=message.chat.id, text=f"{name} için hiç eksik gün yok!")
        return
    msg = f"{name} eksik günler ve sayfa aralıkları:\n" + "\n".join(eksikler)
    bot.send_message(chat_id=message.chat.id, text=msg)

@bot.message_handler(commands=['kimlerokudu', 'kimokudu'])
def kimler_okudu(message):
    show_who_read(message.chat.id)

@bot.message_handler(commands=['yardim', 'komutlar', 'help'])
def komutlar_listesi(message):
    help_text = (
        "📋 <b>Kullanılabilir Komutlar:</b>\n\n"
        "<b>/gonder</b> — Bugünkü 2 Kur’an sayfasını tekrar gönderir (grup/özel).\n"
        "<b>/sayfa [n]</b> — Belirli bir Kur’an sayfasını gönderir (grup/özel).\n"
        "<b>/okudum</b> — (Grup) O gün okuduğunuzu işaretler, ardından okuyanlar tablosu gelir.\n"
        "<b>/kimlerokudu</b> — (Grup) Bugün okuyan/okumayan raporu.\n"
        "<b>/rapor</b> — Ceza raporunu gönderir veya /rapor [kullanıcı] ile detaylı bilgi.\n"
        "<b>/eksik</b> — (Özel) Eksik günlerinizi veya /eksik [kullanıcı] ile eksikleri görürsünüz.\n"
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

def scheduler():
    while True:
        now = datetime.utcnow() + timedelta(hours=3)  # Türkiye saati!
        hhmm = now.strftime("%H:%M")
        if hhmm == "11:30":
            daily_check_and_penalty()
            send_daily_pages(advance_page=True)
            systime.sleep(90)
        elif now.hour >= 6 and now.hour < 24 and now.minute == 0 and now.hour % 2 == 0:
            send_motivation(CHAT_ID)
            systime.sleep(60)
        systime.sleep(20)

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
