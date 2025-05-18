import os
import requests
from telegram import Update
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters
)

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

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Merhaba! Türk Telekom altyapı botuna hoşgeldin.\n"
        "/sorgu <BBK> yazarak sorgulama yapabilirsin.\nÖrn: /sorgu 12345678"
    )

async def sorgu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) != 1 or not context.args[0].isdigit():
        await update.message.reply_text("Kullanım: /sorgu <BBK (sadece rakam)>")
        return
    daire_id = context.args[0]
    await update.message.reply_text("Sorgulanıyor, lütfen bekleyin…")
    sonuc = altyapi_sorgula(daire_id)
    await update.message.reply_text(sonuc)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Komutlar:\n/sorgu <BBK>\n/start")

async def unknown(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Bilinmeyen komut. Yardım için /start yazabilirsin.")

def main():
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("sorgu", sorgu))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(MessageHandler(filters.COMMAND, unknown))
    app.run_polling()

if __name__ == "__main__":
    main()
