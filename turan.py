import os
import json
import logging
import requests
from bs4 import BeautifulSoup
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
    ConversationHandler,
    CallbackQueryHandler,
)

# --- Ayarlar ve Sabitler ---
TELEGRAM_TOKEN = "7790558183:AAFNcKnGcI_Lb3bwU1gVvZt4-2w0TA9mxo0" # Token'ı buraya girin
BASE_URL = "https://alaznet.com.tr/service/altyapi/"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36 Edg/136.0.0.0",
    "Accept": "*/*",
    "Accept-Language": "tr,en;q=0.9,en-GB;q=0.8,en-US;q=0.7",
    "Referer": "https://alaznet.com.tr/service/altyapi/sayfa.php"
}

# ConversationHandler için durumlar (state'ler)
PLAKA, ILCE, MAHALLE, SOKAK, BINA, DAIRE = range(6)
SELECT_RESULT_ACTION = range(6, 7) # Sonuç sonrası eylem seçimi için

# --- Yardımcı Fonksiyonlar (CLI Kodundan Uyarlanmış) ---
def get_options_from_api(endpoint, params):
    try:
        resp = requests.get(BASE_URL + endpoint, params=params, headers=HEADERS, timeout=10)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        options = []
        for opt in soup.find_all("option"):
            value = opt.get("value")
            text = opt.text.strip()
            if value and value != "":
                options.append({"id": value, "text": text}) # Telegram butonları için dict
        return options
    except requests.exceptions.RequestException as e:
        logging.error(f"Seçenekler alınırken hata ({endpoint}): {e}")
        return []

def get_value_from_veriler_list(veriler_list, target_name):
    if not veriler_list: return None
    for item in veriler_list:
        if isinstance(item, dict) and item.get("name") == target_name:
            return item.get("value")
    return None

def kbps_to_mbps_str_detailed(kbps_val, default_val="N/A"):
    if kbps_val and kbps_val != "N/A":
        try:
            float_val = float(kbps_val)
            return f"{float_val / 1000:.0f} Mbps ({kbps_val} Kbps)"
        except ValueError: return default_val
    return default_val

def do_final_query(daire_id: str):
    try:
        resp = requests.get(BASE_URL + "sorgu.php", params={"daire_id": daire_id}, headers=HEADERS, timeout=20)
        resp.raise_for_status()
        return resp.json()
    except requests.exceptions.RequestException as e:
        logging.error(f"Son sorgu hatası (daire_id: {daire_id}): {e}")
        return {"hata_mesaji": f"API bağlantı hatası: {e}"}
    except json.JSONDecodeError as e:
        logging.error(f"JSON decode hatası (daire_id: {daire_id}): {e}")
        return {"hata_mesaji": "API'den gelen yanıt JSON formatında değil."}

# --- Sonuç Formatlama Fonksiyonları (Telegram için Düzenlendi) ---
def format_display_results_for_telegram(data, queried_bbk=None):
    if not data or data.get("hata_mesaji"):
        return f"Sorgu sırasında bir hata oluştu: {data.get('hata_mesaji', 'Bilinmeyen hata')}"

    output = ["--- Türk Telekom Altyapı Sorgu Özeti ---"]
    detay = data.get("detay", {})
    api_main_tip = data.get("tip", "Bilinmiyor")
    bbk_to_display = queried_bbk or data.get("aciklama", {}).get("AdresKodu", {}).get("Kod")

    if bbk_to_display: output.append(f"\n*Sorgulanan BBK Kodu (Daire ID):* {bbk_to_display}")
    full_adres = data.get("full_adres") or detay.get("AcikAdres", "Adres bilgisi bulunamadı.")
    output.append(f"*Adres:* {full_adres}")

    altyapi_tipi_ana = data.get("tip", "N/A")
    altyapi_hizi_ana = data.get("hiz", "N/A")
    altyapi_port_ana = str(data.get("port", "N/A"))

    fttb_eth_active_for_warning = False
    speed_asterisk_summary = ""
    altyapi_hizi_display = f"{altyapi_hizi_ana} Mbps" if str(altyapi_hizi_ana).isdigit() else "N/A"
    fttx_turu_ozet = "N/A (Fiber Değil)"

    if api_main_tip == "FIBER" and str(detay.get("FiberDurum")) == "1":
        fiber_veriler_listesi = detay.get("FiberVeriler")
        fttx1gb_fiber_val = get_value_from_veriler_list(fiber_veriler_listesi, "FTTX1GB")
        if fttx1gb_fiber_val == "1": fttx_turu_ozet = "FTTH (Gigabit)"
        elif fttx1gb_fiber_val == "-2":
            fttx_turu_ozet = "FTTB-ETH*"
            altyapi_hizi_display = "100 Mbps*"
            fttb_eth_active_for_warning = True
            speed_asterisk_summary = "*"
        else: fttx_turu_ozet = "Fiber (Detay Belirsiz)"

    output.append("\n*Genel Altyapı Bilgisi (Birincil Servis):*")
    output.append(f"  Aktif Altyapı Türü: {altyapi_tipi_ana}{speed_asterisk_summary}")
    output.append(f"  Tahmini Alınabilir Hız: {altyapi_hizi_display}")
    output.append(f"  Genel Boş Port Durumu (Birincil): {'Var' if altyapi_port_ana == '1' else ('Yok' if altyapi_port_ana == '0' else 'Bilinmiyor')}")

    if api_main_tip == "FIBER": output.append(f"  Detaylı Fiber Türü (Tahmini): {fttx_turu_ozet}")
    elif api_main_tip in ["VDSL", "ADSL"]:
        santral_mesafe_display = detay.get("SantralMesafe", "N/A")
        if santral_mesafe_display != "N/A" and str(santral_mesafe_display) != "0":
            output.append(f"  Santral Mesafesi (Tahmini): {santral_mesafe_display} metre")
        is_fttc_val = get_value_from_veriler_list(detay.get("VdslVeriler"), "ISFTTC") or \
                      get_value_from_veriler_list(detay.get("Veriler"), "ISFTTC") or "N/A"
        if is_fttc_val != "N/A" and is_fttc_val.strip() and is_fttc_val.lower() != "yok":
            output.append(f"  Saha Dolabı (FTTC/B) Bilgisi: {is_fttc_val}")

    output.append("\n--------------------------------------------------")
    output.append("UYARI: Bu sorgulama Türk Telekom yerleşik altyapı verilerini kullanır.")
    output.append("Burada gösterilen altyapı bilgileri ve hızlar tahminidir.")
    if fttb_eth_active_for_warning:
        output.append("* FTTB-ETH altyapılarında, daireye ulaşan hızın İSS veya bina içi tesisat kaynaklı olarak 100 Mbps ile sınırlı olabileceği gözlemlenmiştir.")
        output.append(f"  API'nin gösterdiği daha yüksek altyapı kapasitesi (örn: {altyapi_hizi_ana} Mbps) genellikle binaya kadar olan fiberin teorik potansiyelidir.")
    # Diğer uyarılar eklenebilir...
    output.append("En doğru ve güncel bilgi için lütfen doğrudan internet servis sağlayıcınızla iletişime geçiniz.")
    output.append("--------------------------------------------------")
    return "\n".join(output)

def format_display_structured_details_for_telegram(data, queried_bbk=None):
    if not data or data.get("hata_mesaji"):
        return f"Detaylar alınırken bir hata oluştu: {data.get('hata_mesaji', 'Bilinmeyen hata')}"

    output = ["\n--- Formatlı Teknik Detaylar ---"]
    api_main_tip = data.get("tip", "Bilinmiyor")
    detay = data.get("detay", {})
    api_main_hiz = data.get("hiz", "N/A")
    bbk_kodu_display = queried_bbk or data.get("aciklama", {}).get("AdresKodu", {}).get("Kod", "N/A")
    veriler_ana_liste = detay.get("Veriler")
    fiber_veriler_listesi = detay.get("FiberVeriler")
    vdsl_veriler_listesi = detay.get("VdslVeriler")

    mudurluk_adi = get_value_from_veriler_list(fiber_veriler_listesi, "SNTRLMDA") or \
                   get_value_from_veriler_list(vdsl_veriler_listesi, "SNTRLMDA") or \
                   get_value_from_veriler_list(veriler_ana_liste, "SNTRLMDA") or "N/A"
    santral_adi_display = detay.get("SantralAdi", "N/A")
    santral_mesafe_display = detay.get("SantralMesafe", "N/A")
    effective_fttx_type = "Yok / Uygulanamaz"
    port_max_hizi_label = "Port Max Hızı (Altyapı Kapasitesi)"
    port_max_hizi_display = f"{api_main_hiz} Mbps" if str(api_main_hiz).isdigit() else "N/A"
    service_speed_note = ""
    speed_asterisk = ""

    if api_main_tip == "FIBER" and str(detay.get("FiberDurum")) == "1":
        fttx1gb_fiber_val = get_value_from_veriler_list(fiber_veriler_listesi, "FTTX1GB")
        if fttx1gb_fiber_val == "1":
            effective_fttx_type = "FTTH (Gigabit)"
            service_speed_note = "Bu altyapı genellikle 1000 Mbps (Gigabit) hızı destekler."
        elif fttx1gb_fiber_val == "-2":
            effective_fttx_type = "FTTB-ETH*"
            port_max_hizi_label = "Daireye Tahmini Hız (İSS Paketi)"
            port_max_hizi_display = "100 Mbps*"
            speed_asterisk = "*"
            service_speed_note = f"*FTTB-ETH altyapılarında daireye ulaşan hızın 100 Mbps ile sınırlı olabileceği gözlemlenmiştir.\n  (Binaya kadar fiber kapasitesi: {api_main_hiz} Mbps). Lütfen İSS'niz ile güncel sunulan hızı teyit edin."
        else:
            effective_fttx_type = "Fiber (Detay Belirsiz)"
            service_speed_note = "Altyapı hız potansiyeli için İSS ile görüşün."

    is_emri_value = get_value_from_veriler_list(fiber_veriler_listesi, "ACKISEMRI") or \
                    get_value_from_veriler_list(vdsl_veriler_listesi, "ACKISEMRI") or \
                    get_value_from_veriler_list(veriler_ana_liste, "ACKISEMRI")
    is_emri_display = "YOK"
    if is_emri_value and is_emri_value.strip() and is_emri_value.strip() != "|" and is_emri_value.strip() != "| |":
        is_emri_display = f"VAR ({is_emri_value.strip()})"
    
    # Kısaltılmış versiyon, diğer kısımlar benzer şekilde eklenebilir.
    # Önemli olan print yerine string biriktirmek.
    output.append("\n*İnternet Bağlantı Bilgileri*")
    if api_main_tip == "FIBER" and str(detay.get("FiberDurum")) == "1":
        output.append(f"  Altyapı: FIBER {speed_asterisk}")
        fiber_bos_port_val = str(detay.get("FiberBosPort", "N/A"))
        fiber_bos_port_display = "VAR" if fiber_bos_port_val == "1" else ("YOK" if fiber_bos_port_val == "0" else "Bilinmiyor")
        output.append(f"  | Boş Port: {fiber_bos_port_display}")
        output.append(f"  | {port_max_hizi_label}: {port_max_hizi_display}")
        if service_speed_note: output.append(f"  Not: {service_speed_note}")
    elif api_main_tip == "VDSL" and str(detay.get("VdslDurum")) == "1":
         output.append(f"  Altyapı: VDSL")
         # ... VDSL detayları ...
    elif api_main_tip == "ADSL" and str(detay.get("AdslDurum")) == "1":
         output.append(f"  Altyapı: ADSL")
         # ... ADSL detayları ...

    output.append("\n*Genel Bilgiler*")
    output.append(f"  | BBK Kodu: {str(bbk_kodu_display)}")
    output.append(f"  | Müdürlük Adı: {mudurluk_adi}")
    output.append(f"  | Santral Adı: {santral_adi_display}")
    if api_main_tip == "FIBER":
        output.append(f"  | FTTX Altyapı Türü: {effective_fttx_type}")
    output.append(f"  | İş Emri: {is_emri_display}")
    return "\n".join(output)


# --- Telegram Bot Komutları ve Handler'ları ---
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Merhaba! Türk Telekom Altyapı Sorgulama Botu'na hoş geldiniz.\n"
        "Doğrudan BBK ile sorgulamak için: /sorgula_bbk <BBK_NUMARASI>\n"
        "Adres seçerek sorgulamak için: /sorgula_adres"
    )

async def sorgula_bbk_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args or not context.args[0].isdigit():
        await update.message.reply_text("Lütfen geçerli bir BBK numarası girin. Örnek: /sorgula_bbk 12345678")
        return

    bbk = context.args[0]
    await update.message.reply_text(f"{bbk} BBK için sorgulama yapılıyor, lütfen bekleyiniz...")
    
    api_data = do_final_query(bbk)
    context.user_data['api_data'] = api_data # Sonraki eylemler için sakla
    context.user_data['queried_bbk'] = bbk

    formatted_results = format_display_results_for_telegram(api_data, bbk)
    
    keyboard = [
        [InlineKeyboardButton("Teknik Detayları Gör", callback_data=f"details_{bbk}")],
        [InlineKeyboardButton("Ham JSON Verisini Gör", callback_data=f"json_{bbk}")],
        [InlineKeyboardButton("Yeni Sorgu", callback_data="new_query_start")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(formatted_results, reply_markup=reply_markup, parse_mode='Markdown')
    return SELECT_RESULT_ACTION


# --- Adresle Sorgulama (ConversationHandler) ---
async def sorgula_adres_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear() # Önceki sorgu verilerini temizle
    await update.message.reply_text("Adresle sorgulamaya hoş geldiniz.\nLütfen Plaka (il kodu) girin (örn: 06, 34):")
    return PLAKA

async def plaka_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    plaka = update.message.text.strip()
    if not plaka.isdigit() or not (1 <= len(plaka) <= 2):
        await update.message.reply_text("Geçersiz plaka formatı. Lütfen 1 veya 2 haneli bir sayı girin (örn: 6, 34). Tekrar /sorgula_adres yazın.")
        return ConversationHandler.END
    
    context.user_data['plaka'] = plaka.zfill(2)
    await update.message.reply_text(f"Plaka: {context.user_data['plaka']}. İlçeler getiriliyor...")
    
    options = get_options_from_api("district.php", {"city": context.user_data['plaka']})
    if not options:
        await update.message.reply_text("Bu plaka için ilçe bulunamadı. Lütfen /sorgula_adres ile tekrar deneyin.")
        return ConversationHandler.END

    keyboard = [[InlineKeyboardButton(opt['text'], callback_data=f"ilce_{opt['id']}")] for opt in options]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Lütfen bir ilçe seçin:", reply_markup=reply_markup)
    return ILCE

async def ilce_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    ilce_id = query.data.split('_')[1]
    context.user_data['ilce_id'] = ilce_id
    
    # Seçilen ilçe adını bulmak için (opsiyonel, sadece loglama/gösterme için)
    # previous_options = query.message.reply_markup.inline_keyboard 
    # for row in previous_options:
    #     if row[0].callback_data == query.data:
    #         context.user_data['ilce_ad'] = row[0].text
    #         break
    
    await query.edit_message_text(text=f"İlçe seçildi. Mahalleler getiriliyor...")
    options = get_options_from_api("neighborhoods.php", {"district": ilce_id})
    if not options:
        await query.edit_message_text("Bu ilçe için mahalle bulunamadı. Lütfen /sorgula_adres ile tekrar deneyin.")
        return ConversationHandler.END

    keyboard = [[InlineKeyboardButton(opt['text'], callback_data=f"mah_{opt['id']}")] for opt in options]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text("Lütfen bir mahalle seçin:", reply_markup=reply_markup)
    return MAHALLE

async def mahalle_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    mahalle_id = query.data.split('_')[1]
    context.user_data['mahalle_id'] = mahalle_id
    await query.edit_message_text(text=f"Mahalle seçildi. Sokak/Caddeler getiriliyor...")

    options = get_options_from_api("street.php", {"neighborhoods": mahalle_id})
    if not options:
        await query.edit_message_text("Bu mahalle için sokak/cadde bulunamadı. Lütfen /sorgula_adres ile tekrar deneyin.")
        return ConversationHandler.END
    keyboard = [[InlineKeyboardButton(opt['text'], callback_data=f"sok_{opt['id']}")] for opt in options]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text("Lütfen bir sokak/cadde seçin:", reply_markup=reply_markup)
    return SOKAK

async def sokak_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    sokak_id = query.data.split('_')[1]
    context.user_data['sokak_id'] = sokak_id
    await query.edit_message_text(text=f"Sokak/Cadde seçildi. Binalar getiriliyor...")

    options = get_options_from_api("building.php", {"street": sokak_id})
    if not options:
        await query.edit_message_text("Bu sokak/cadde için bina bulunamadı. Lütfen /sorgula_adres ile tekrar deneyin.")
        return ConversationHandler.END
    keyboard = [[InlineKeyboardButton(opt['text'], callback_data=f"bina_{opt['id']}")] for opt in options]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text("Lütfen bir bina seçin:", reply_markup=reply_markup)
    return BINA

async def bina_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    bina_id = query.data.split('_')[1]
    context.user_data['bina_id'] = bina_id
    await query.edit_message_text(text=f"Bina seçildi. Daireler getiriliyor...")

    options = get_options_from_api("home.php", {"building": bina_id})
    if not options:
        await query.edit_message_text("Bu bina için daire bulunamadı. Lütfen /sorgula_adres ile tekrar deneyin.")
        return ConversationHandler.END
    keyboard = [[InlineKeyboardButton(opt['text'], callback_data=f"daire_{opt['id']}")] for opt in options] # Daire ID'si BBK'dır
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text("Lütfen bir daire seçin:", reply_markup=reply_markup)
    return DAIRE

async def daire_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    daire_id = query.data.split('_')[1] # Bu BBK oluyor
    context.user_data['daire_id'] = daire_id
    
    await query.edit_message_text(text=f"Daire (BBK: {daire_id}) seçildi. Altyapı sorgulanıyor...")
    
    api_data = do_final_query(daire_id)
    context.user_data['api_data'] = api_data # Sonraki eylemler için sakla
    context.user_data['queried_bbk'] = daire_id

    formatted_results = format_display_results_for_telegram(api_data, daire_id)
    
    keyboard = [
        [InlineKeyboardButton("Teknik Detayları Gör", callback_data=f"details_{daire_id}")],
        [InlineKeyboardButton("Ham JSON Verisini Gör", callback_data=f"json_{daire_id}")],
        [InlineKeyboardButton("Yeni Sorgu", callback_data="new_query_start")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    # query.message üzerinden değil, yeni mesaj olarak göndermek daha temiz olabilir.
    # await query.edit_message_text(formatted_results, reply_markup=reply_markup, parse_mode='Markdown')
    await context.bot.send_message(chat_id=query.message.chat_id, text=formatted_results, reply_markup=reply_markup, parse_mode='Markdown')
    return SELECT_RESULT_ACTION


async def handle_result_action(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    action_data = query.data

    api_data = context.user_data.get('api_data')
    queried_bbk = context.user_data.get('queried_bbk')

    if not api_data or not queried_bbk:
        await query.edit_message_text("Önceki sorgu verileri bulunamadı. Lütfen yeni bir sorgu başlatın.")
        return ConversationHandler.END

    if action_data.startswith("details_"):
        details_text = format_display_structured_details_for_telegram(api_data, queried_bbk)
        # Önceki mesajı editlemek yerine yeni mesaj olarak gönderelim, çünkü çok uzun olabilir.
        await context.bot.send_message(chat_id=query.message.chat_id, text=details_text, parse_mode='Markdown')
        # Kullanıcıya tekrar seçenek sunmak için ana sonuç mesajını butonlarıyla tekrar gönderebiliriz veya yeni bir mesajda seçenek sunabiliriz.
        # Şimdilik sadece detayı gösterip bırakıyoruz. İstenirse burası geliştirilebilir.
        await query.message.reply_text("Teknik detaylar yukarıda gösterildi. Yeni bir sorgu için /start.")

    elif action_data.startswith("json_"):
        json_text = json.dumps(api_data, indent=2, ensure_ascii=False)
        # JSON çok uzun olabileceğinden, dosya olarak göndermek daha iyi olabilir veya parçalara bölmek.
        # Şimdilik kısa mesaj olarak deniyoruz.
        if len(json_text) > 4000: # Telegram mesaj limiti yaklaşık 4096
            json_text = json_text[:4000] + "\n...(veri kesildi)..."
        await context.bot.send_message(chat_id=query.message.chat_id, text=f"```json\n{json_text}\n```", parse_mode='MarkdownV2')
        await query.message.reply_text("Ham JSON yukarıda gösterildi. Yeni bir sorgu için /start.")

    elif action_data == "new_query_start":
        await query.edit_message_text("Yeni sorgu başlatılıyor...")
        # await start_command(update, context) # Bu direkt çalışmaz, query update'i farklı.
        await context.bot.send_message(chat_id=query.message.chat_id, text="Yeni sorgu için /start, /sorgula_bbk veya /sorgula_adres kullanabilirsiniz.")

    return ConversationHandler.END # Her eylemden sonra conversation'ı bitiriyoruz.


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("İşlem iptal edildi.")
    context.user_data.clear()
    return ConversationHandler.END

def main():
    logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    # Adresle sorgulama için ConversationHandler
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('sorgula_adres', sorgula_adres_start)],
        states={
            PLAKA: [MessageHandler(filters.TEXT & ~filters.COMMAND, plaka_received)],
            ILCE: [CallbackQueryHandler(ilce_selected, pattern='^ilce_')],
            MAHALLE: [CallbackQueryHandler(mahalle_selected, pattern='^mah_')],
            SOKAK: [CallbackQueryHandler(sokak_selected, pattern='^sok_')],
            BINA: [CallbackQueryHandler(bina_selected, pattern='^bina_')],
            DAIRE: [CallbackQueryHandler(daire_selected, pattern='^daire_')],
            SELECT_RESULT_ACTION: [CallbackQueryHandler(handle_result_action, pattern='^(details_|json_|new_query_start)')]
        },
        fallbacks=[CommandHandler('cancel', cancel)],
        per_message=False # Önemli: Butonlara basıldığında aynı mesajın handler'ı tetiklemesi için
    )
    
    # BBK ile sorgulama için de ConversationHandler (sadece sonuç eylemi için)
    # Veya CommandHandler ile başlayıp, sonuç sonrası butonlar için ayrı bir CallbackQueryHandler eklenebilir.
    # Şimdilik basit CommandHandler + CallbackQueryHandler kullanalım.
    sorgula_bbk_conv_handler = ConversationHandler(
        entry_points=[CommandHandler('sorgula_bbk', sorgula_bbk_command)],
        states={
            SELECT_RESULT_ACTION: [CallbackQueryHandler(handle_result_action, pattern='^(details_|json_|new_query_start)')]
        },
        fallbacks=[CommandHandler('cancel', cancel)],
         per_message=False
    )


    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(conv_handler) # Adresle sorgulama
    app.add_handler(sorgula_bbk_conv_handler) # BBK ile sorgulama ve sonuç eylemleri

    app.run_polling()

if __name__ == "__main__":
    main()
