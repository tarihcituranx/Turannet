import os
import logging
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters
import requests

# Telegram bot tokenın doğrudan burada
TELEGRAM_TOKEN = "7790558183:AAFNcKnGcI_Lb3bwU1gVvZt4-2w0TA9mxo0"

BASE_URL = "https://alaznet.com.tr/service/altyapi/"
HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Accept": "*/*",
    "Accept-Language": "tr,en;q=0.9",
    "Referer": "https://alaznet.com.tr/service/altyapi/sayfa.php"
}

def altyapi_sorgula(daire_id):
    try:
        resp = requests.get(BASE_URL + "sorgu.php", params={"daire_id": daire_id}, headers=HEADERS, timeout=20)
        resp.raise_for_status()
        data = resp.json()
        if str(data.get("hata", "true")).lower() != "false":
            return "❗️ Bilgi bulunamadı veya API hatası oluştu."
        tip = data.get("tip", "Bilinmiyor")
        hiz = data.get("hiz", "N/A")
        adres = data.get("full_adres", "Adres yok.")
        return f"🏷 BBK: {daire_id}\n📍 Adres: {adres}\n🔌 Tip: {tip}\n⚡️ Hız: {hiz} Mbps"
    except Exception as e:
        return f"❗️ Sorgu hatası: {e}"

def start(update, context):
    update.message.reply_text(
        "Merhaba! Türk Telekom altyapı botuna hoşgeldin.\n"
        "/sorgu <BBK> yazarak sorgulama yapabilirsin.\nÖrn: /sorgu 12345678"
    )

def sorgu(update, context):
    if len(context.args) != 1 or not context.args[0].isdigit():
        return update.message.reply_text("Kullanım: /sorgu <BBK (sadece rakam)>")
    daire_id = context.args[0]
    update.message.reply_text("Sorgulanıyor, lütfen bekleyin…")
    sonuc = altyapi_sorgula(daire_id)
    update.message.reply_text(sonuc)

def help_command(update, context):
    update.message.reply_text("Komutlar:\n/sorgu <BBK>\n/start")

def main():
    updater = Updater(TELEGRAM_TOKEN, use_context=True)
    dp = updater.dispatcher

    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(CommandHandler("sorgu", sorgu))
    dp.add_handler(CommandHandler("help", help_command))
    dp.add_handler(MessageHandler(Filters.text & ~Filters.command, help_command))

    updater.start_polling()
    updater.idle()

if __name__ == "__main__":
    main()