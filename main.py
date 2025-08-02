import telebot
import os
import random
from datetime import datetime, time, timedelta, timezone
import time as systime
import threading
import json
from flask import Flask
from threading import Thread

import gspread
from oauth2client.service_account import ServiceAccountCredentials

# MOTİVASYON SÖZLERİ
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

# ORTAM DEĞİŞKENLERİ
TOKEN = os.environ['TOKEN']
CHAT_ID = os.environ['CHAT_ID']  # Grup için
SHEET_ID = os.environ['SHEET_ID']
bot = telebot.TeleBot(TOKEN)

# GOOGLE SHEETS BAĞLANTISI
scope = [
    'https://spreadsheets.google.com/feeds',
    'https://www.googleapis.com/auth/drive'
]
creds = ServiceAccountCredentials.from_json_keyfile_name('service_account.json', scope)
gsheet = gspread.authorize(creds)
sheet_okuma = gsheet.open_by_key(SHEET_ID).worksheet("Okuma Takip")
sheet_ceza = gsheet.open_by_key(SHEET_ID).worksheet("Cezalar")
sheet_ayar = gsheet.open_by_key(SHEET_ID).worksheet("BotAyar")  # current_page burada tutulacak

# TÜRKİYE SAATİYLE GÜN HESABI (11:30)
def get_kuran_gunu(now=None):
    tz_tr = timezone(timedelta(hours=3))
    now = now or datetime.now(tz_tr)
    if now.time() < time(11, 30):
        return (now - timedelta(days=1)).strftime("%Y-%m-%d")
    else:
        return now.strftime("%Y-%m-%d")

# SAYFA TAKİBİ - current_page artık Sheets'te tutuluyor
def load_current_page():
    val = sheet_ayar.acell('A2').value
    return int(val) if val and val.isdigit() else 0

def save_current_page(page_num):
    sheet_ayar.update_acell('A2', str(page_num))

# KULLANICI KAYDI VE GÜNCELLEME
def add_or_update_user(first_name, user_id, username):
    names = sheet_okuma.col_values(1)
    user_ids = sheet_okuma.col_values(2)
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

# KURAN SAYFALARI (pages.json)
with open("pages.json") as f:
    pages = json.load(f)

def send_page(page_num, chat_id, pin_message=False):
    try:
        image_id = pages[page_num]
        image_url = f"https://drive.google.com/uc?export=view&id={image_id}"
        msg = bot.send_photo(chat_id=chat_id, photo=image_url, caption=f"📖 Kur’an Sayfa {page_num + 1}")
        print(f"Sayfa {page_num + 1} gönderildi ({chat_id})")
        if pin_message:
            try:
                bot.pin_chat_message(chat_id=chat_id, message_id=msg.message_id, disable_notification=True)
            except Exception as e:
                print("Pin hatası:", e)
        return True
    except Exception as e:
        print(f"Hata: {e}")
        bot.send_message(chat_id=chat_id, text="Sayfa gönderilemedi veya bulunamadı!")
        return False

def send_daily_pages(advance_page=False):
    current_page = load_current_page()

    if advance_page:
        current_page += 2
        save_current_page(current_page)

    for i in range(2):
        send_page(current_page + i, CHAT_ID, pin_message=(i == 0))

# OKUMA KAYIT & RAPOR FONKSİYONLARI
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

def mark_read(first_name, user_id, username, date=None):
    if date is None:
        date = get_kuran_gunu()
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

# CEZA SİSTEMİ
def add_penalty(user, amount):
    sheet_ceza.append_row([user, amount, datetime.now(timezone(timedelta(hours=3))).strftime("%Y-%m-%d")])

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
    # Ceza kınama
    summary = get_penalties()
    sertler = [k for k, v in summary.items() if v >= 100]
    if sertler:
        bot.send_message(
            chat_id=CHAT_ID,
            text="⚠️ " + ", ".join(sertler) + " toplam cezan 100 TL'yi geçti! Kur'an'a karşı bu kadar lakayt olmak yakışmıyor! Lütfen toparlan!",
            parse_mode="HTML"
        )

# MOTİVASYONLU HATIRLATMA
def send_motivation(chat_id):
    msg = random.choice(MOTIVATION)
    unread = get_unread_mentions()
    if unread:
        msg += f"\n\nHenüz okumayanlar: {unread}"
    bot.send_message(chat_id=chat_id, text=msg, parse_mode="HTML")



# KOMUTLAR
@bot.message_handler(commands=['hatirlat'])
def manuel_hatirlat(message):
    send_motivation(message.chat.id)

@bot.message_handler(commands=['saat'])
def saat_kontrol(message):
    tz_tr = timezone(timedelta(hours=3))
    now = datetime.now(tz_tr)
    bot.send_message(chat_id=message.chat.id, text=f"Türkiye saatiyle şu an: {now.strftime('%Y-%m-%d %H:%M:%S')}")

@bot.message_handler(commands=['gonder'])
def manual_send(message):
    current_page = load_current_page()
    send_page(current_page, message.chat.id, pin_message=True)
    send_page(current_page + 1, message.chat.id)
    bot.send_message(chat_id=message.chat.id, text="✅ Bugünkü 2 sayfa gönderildi!")
@bot.message_handler(commands=['saat'])
def saat_kontrol(message):
    tz_tr = timezone(timedelta(hours=3))
    now = datetime.now(tz_tr)
    bot.send_message(chat_id=message.chat.id, text=f"Türkiye saatiyle şu an: {now.strftime('%Y-%m-%d %H:%M:%S')}")

@bot.message_handler(commands=['gonder'])
def manual_send(message):
    current_page = load_current_page()
    send_page(current_page, message.chat.id, pin_message=True)
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
        date = args[1]  # YYYY-MM-DD formatı beklenir
    success, msg = mark_read(first_name, user_id, username, date)
    if success:
        bot.send_message(chat_id=message.chat.id, text=msg)
        show_who_read(message.chat.id)
    else:
        bot.send_message(chat_id=message.chat.id, text=f"Hata: {msg}")

@bot.message_handler(commands=['rapor'])
def rapor_komutu(message):
    user = message.from_user
    args = message.text.split()
    arg = None
    try:
        arg = args[1]
    except IndexError:
        pass

    # Kişiyi bul
    names = sheet_okuma.col_values(1)[1:]
    user_ids = sheet_okuma.col_values(2)[1:]
    usernames = sheet_okuma.col_values(3)[1:]
    date_cols = sheet_okuma.row_values(1)[3:]

    idx = None
    for i, (name, uid, uname) in enumerate(zip(names, user_ids, usernames)):
        if arg:
            if (
                str(arg).lower() in (str(uid).lower(), str(uname).lower(), str(name).lower())
                or (arg.startswith('@') and arg.lower() == str(uname).lower())
            ):
                idx = i
                break
        else:
            # Boşsa kendi id ya da username
            if str(user.id) == str(uid) or (user.username and ("@" + user.username) == uname):
                idx = i
                break
    if idx is None:
        bot.send_message(message.chat.id, "Kullanıcı bulunamadı.")
        return

    # Verileri çek
    okuma_row = sheet_okuma.row_values(idx + 2)[3:]
    try:
        first_read_idx = okuma_row.index("✅")
    except ValueError:
        bot.send_message(message.chat.id, "Henüz hiç okuma kaydı yok.")
        return

    total_days = len(okuma_row[first_read_idx:])
    read_days = sum(1 for v in okuma_row[first_read_idx:] if v == "✅")
    unread_days = total_days - read_days
    success_rate = (read_days / total_days * 100) if total_days else 0

    # Ceza hesapla
    penalties = get_penalties()
    total_penalty = penalties.get(names[idx], 0)

    # Son gün okudu mu?
    last_date = date_cols[-1] if date_cols else "?"
    last_read = okuma_row[-1] if okuma_row else ""
    last_status = "✅" if last_read == "✅" else "❌"

    rapor = (
        f"📊 <b>{names[idx]} Kullanıcı Raporu</b>\n\n"
        f"• Toplam takip edilen gün: <b>{total_days}</b>\n"
        f"• Okuduğu gün: <b>{read_days}</b>\n"
        f"• Okumadığı gün: <b>{unread_days}</b>\n"
        f"• Başarı oranı: <b>{success_rate:.1f}%</b>\n"
        f"• Ceza toplamı: <b>{total_penalty} TL</b>\n"
        f"• Son gün ({last_date}) durumu: {last_status}\n"
    )
    bot.send_message(message.chat.id, rapor, parse_mode="HTML")

@bot.message_handler(commands=['cezalar'])
def ceza_rapor(message):
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
    show_who_read(message.chat.id)

@bot.message_handler(commands=['eksik'])
def eksik_komutu(message):
    user = message.from_user
    arg = None
    try:
        arg = message.text.split()[1]
    except IndexError:
        pass

    # Google Sheets verilerini al
    names = sheet_okuma.col_values(1)[1:]
    user_ids = sheet_okuma.col_values(2)[1:]
    usernames = sheet_okuma.col_values(3)[1:]
    date_cols = sheet_okuma.row_values(1)[3:]  # ilk 3 sütun kullanıcı bilgisi

    # Kullanıcıyı bul
    idx = None
    for i, (name, uid, uname) in enumerate(zip(names, user_ids, usernames)):
        if arg:
            if str(arg).lower() in (str(uid).lower(), str(uname).lower(), str(name).lower()) \
                    or (arg.startswith('@') and arg.lower() == str(uname).lower()):
                idx = i
                break
        else:
            if str(user.id) == str(uid) or (user.username and ("@" + user.username) == uname):
                idx = i
                break

    if idx is None:
        bot.send_message(message.chat.id, "Kullanıcı bulunamadı.")
        return

    # Okuma satırı
    okuma_row = sheet_okuma.row_values(idx + 2)[3:]  # 2: başlık, 1-index offset
    try:
        first_read_idx = okuma_row.index("✅")
    except ValueError:
        first_read_idx = len(okuma_row)

    current_page = load_current_page()
    toplam_gun = len(okuma_row)

    eksikler = []
    for col_idx, cell in enumerate(okuma_row[first_read_idx:], start=first_read_idx):
        if cell != "✅":
            tarih = date_cols[col_idx]
            gecikme = toplam_gun - col_idx - 1
            sayfa1 = current_page - 2 * gecikme
            sayfa2 = sayfa1 + 1

            eksikler.append(f"{tarih}: {sayfa1 + 1}–{sayfa2 + 1}")

    if eksikler:
        msg = f"<b>{names[idx]} için eksik okuma günleri:</b>\n\n" + "\n".join(f"❌ {e}" for e in eksikler)
    else:
        msg = f"✅ {names[idx]} için eksik gün yok."

    bot.send_message(chat_id=message.chat.id, text=msg, parse_mode="HTML")



@bot.message_handler(commands=['yardim', 'komutlar', 'help'])
def komutlar_listesi(message):
    help_text = (
        "📋 <b>Kullanılabilir Komutlar:</b>\n\n"
        "<b>/gonder</b> — Bugünkü 2 Kur’an sayfasını tekrar gönderir (grup/özel).\n"
        "<b>/sayfa [n]</b> — Belirli bir Kur’an sayfasını gönderir (grup/özel).\n"
        "<b>/okudum</b> — (Grup) O gün okuduğunuzu işaretler, ardından okuyanlar tablosu gelir.\n"
        "<b>/kimlerokudu</b> — (Grup) Bugün okuyan/okumayan raporu.\n"
        "<b>/cezalar</b> — (Grup) Ceza raporunu gönderir.\n"
        "<b>/rapor</b> kişiye ait rapor gösterir.\n"
        "<b>/hatirlat</b> — (Grup) Motive sözlerle hatırlatma.\n"
        "<b>/eksik</b> — (Grup) Okumadığınız sayfaları gösterir\n"
        "<b>/yardim</b> veya <b>/komutlar</b> — Bu rehberi gösterir."
    )
    bot.send_message(chat_id=message.chat.id, text=help_text, parse_mode="HTML")

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

# SCHEDULER (Her gün 11:30'da yeni sayfa ve ceza, 2 saatte bir hatırlatma)
def scheduler():
    while True:
        tz_tr = timezone(timedelta(hours=3))
        now = datetime.now(tz_tr)
        print(f"[Scheduler] Şu an TR saatiyle: {now.strftime('%Y-%m-%d %H:%M:%S')}")
        hhmm = now.strftime("%H:%M")
        if hhmm == "11:30":
            daily_check_and_penalty()
            send_daily_pages(advance_page=True)
            systime.sleep(90)
        elif now.hour >= 6 and now.hour < 24 and now.minute == 0 and now.hour % 2 == 0:
            send_motivation(CHAT_ID)
            print("Hatırlatma gönderildi!")
            systime.sleep(60)
        systime.sleep(20)

# FLASK APP (Render / UptimeRobot için)
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
