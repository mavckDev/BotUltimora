import logging
import warnings
import json
import os
from datetime import datetime, timedelta
from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup
)
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, filters, ContextTypes, ConversationHandler
)

warnings.filterwarnings("ignore")
logging.basicConfig(level=logging.CRITICAL)
logger = logging.getLogger(__name__)
logger.setLevel(logging.CRITICAL)

_boot_logger = logging.getLogger("boot")
_boot_logger.setLevel(logging.INFO)
_boot_handler = logging.StreamHandler()
_boot_handler.setFormatter(logging.Formatter("%(message)s"))
_boot_logger.addHandler(_boot_handler)
_boot_logger.propagate = False

TOKEN            = "8016636055:AAGLoruLL0ifFI7rSK3LXMGzL-QQ26Fiicw"
GROUP_ID         = -5246911983
CHANNEL_ID       = -1003746940227
CHANNEL_USERNAME = "zeroultimora"

PHOTO_MENU_ID      = "AgACAgQAAxkBAAN1aaBHgi7DoL4n_4AJjKofqljnrwoAAr0Maxs8OAFRk8VLWVe2vdoBAAMCAAN4AAM6BA"
STICKER_SEPARATORE = "CAACAgQAAxkBAAEQoNdpoHTSsQABPmJ4sao1hr4siltYZO0AAngeAAI5YNBQPitw_QABIcn7OgQ"

SPONSOR_FILE     = "sponsor_attive.json"
CANDIDATURE_FILE = "candidature.json"

PREZZI = {
    "12h":     2500,
    "24h":     3500,
    "2d":      5500,
    "plus":    5500,
    "plus_g":   500,
    "fissato": 5000,
    "repost":  2000,
    "perma":  10000,
}

(MENU, SEGNALA, REDAZIONE,
 SP_LISTINO, SP_GIORNI, SP_PAGAMENTO, SP_CONTENUTO) = range(7)

# PERSISTENZA SPONSOR
def carica_sponsor() -> dict:
    if os.path.exists(SPONSOR_FILE):
        try:
            with open(SPONSOR_FILE, "r") as f:
                raw = json.load(f)
            result = {}
            for k, v in raw.items():
                v["scadenza"] = datetime.fromisoformat(v["scadenza"]) if v["scadenza"] else None
                result[int(k)] = v
            return result
        except Exception:
            pass
    return {}

def salva_sponsor(d: dict):
    try:
        serializable = {}
        for k, v in d.items():
            serializable[str(k)] = {
                **v,
                "scadenza": v["scadenza"].isoformat() if v["scadenza"] else None
            }
        with open(SPONSOR_FILE, "w") as f:
            json.dump(serializable, f, indent=2)
    except Exception:
        pass

SPONSOR_ATTIVE: dict  = carica_sponsor()
SPONSOR_PENDING: dict = {}

def carica_canale_stato() -> dict:
    if os.path.exists(CANDIDATURE_FILE):
        try:
            with open(CANDIDATURE_FILE, "r") as f:
                data = json.load(f)
                return {"ultimo_tipo": data.get("_canale_ultimo_tipo")}
        except Exception:
            pass
    return {"ultimo_tipo": None}

def salva_canale_stato(stato: dict):
    try:
        data = carica_candidature()
        data["_canale_ultimo_tipo"] = stato.get("ultimo_tipo")
        with open(CANDIDATURE_FILE, "w") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except Exception:
        pass

CANALE_STATO: dict = carica_canale_stato()

# PERSISTENZA CANDIDATURE
DEFAULT_MODULO = (
    "Nome e cognome:\n"
    "Età:\n"
    "Città:\n"
    "Ruolo desiderato (es. giornalista, grafico, social media):\n"
    "Esperienza precedente:\n"
    "Perché vuoi entrare in ZeroUltim'Ora:\n"
    "Contatto preferito (Telegram/email):"
)

def carica_candidature() -> dict:
    if os.path.exists(CANDIDATURE_FILE):
        try:
            with open(CANDIDATURE_FILE, "r") as f:
                return json.load(f)
        except Exception:
            pass
    return {"aperte": False, "modulo": DEFAULT_MODULO, "pannello_msg_id": None}

def salva_candidature():
    try:
        with open(CANDIDATURE_FILE, "w") as f:
            json.dump(CANDIDATURE_CFG, f, indent=2, ensure_ascii=False)
    except Exception:
        pass

CANDIDATURE_CFG: dict = carica_candidature()

# UTILS
async def delete_msg_id(context, chat_id, msg_id):
    try:
        await context.bot.delete_message(chat_id, msg_id)
    except Exception:
        pass

async def safe_delete(update: Update):
    try:
        if update.callback_query:
            await update.callback_query.message.delete()
        elif update.message:
            await update.message.delete()
    except Exception:
        pass

async def delete_last_bot_msg(context, chat_id):
    key = f"last_bot_msg_{chat_id}"
    old = context.bot_data.get(key)
    if old:
        await delete_msg_id(context, chat_id, old)
        context.bot_data.pop(key, None)

async def send(context, chat_id: int, text: str, kb=None) -> int:
    msg = await context.bot.send_message(
        chat_id, text,
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(kb) if kb else None
    )
    context.bot_data[f"last_bot_msg_{chat_id}"] = msg.message_id
    return msg.message_id

def fp(centesimi: int) -> str:
    return f"€{centesimi:,}".replace(",", ".")

def calcola_prezzo(durata: str, giorni: int, extras: list) -> int:
    if durata == "perma":
        base = PREZZI["perma"]
    elif durata == "plus":
        base = PREZZI["plus"] + max(0, giorni - 2) * PREZZI["plus_g"]
    else:
        base = PREZZI.get(durata, 0)
    for ext in extras:
        base += PREZZI.get(ext, 0)
    return base

def descrivi_durata(durata: str, giorni: int) -> str:
    m = {"12h": "12 ore", "24h": "24 ore", "2d": "2 giorni", "perma": "Permanente ♾️"}
    return f"{giorni} giorni" if durata == "plus" else m.get(durata, durata)

def calcola_scadenza(durata: str, giorni: int):
    now = datetime.now()
    if durata == "12h":  return now + timedelta(hours=12)
    if durata == "24h":  return now + timedelta(hours=24)
    if durata == "2d":   return now + timedelta(days=2)
    if durata == "plus": return now + timedelta(days=giorni)
    return None

# MENU PRINCIPALE
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id

    if update.callback_query:
        await update.callback_query.answer()
        await safe_delete(update)

    await delete_last_bot_msg(context, chat_id)

    kb = [
        [InlineKeyboardButton("📰 Segnala notizia",    callback_data="news")],
        [InlineKeyboardButton("💼 Richiedi sponsor",   callback_data="sponsor")],
        [InlineKeyboardButton("🤝 Entra in redazione", callback_data="redazione")],
    ]
    msg = await context.bot.send_photo(
        chat_id, PHOTO_MENU_ID,
        caption="<b>ꜱᴛᴜᴅɪᴏ ᴛᴇʟᴇᴠɪꜱɪᴠᴏ | ᴢᴇʀᴏᴜʟᴛɪᴍ'ᴏʀᴀ</b>\n\nBenvenuto sul bot ufficiale di @ZeroUltimora, seleziona un'opzione:",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(kb)
    )
    context.bot_data[f"last_bot_msg_{chat_id}"] = msg.message_id
    return MENU

# NEWS
async def news_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    await update.callback_query.answer()
    await safe_delete(update)
    kb = [[InlineKeyboardButton("🔙 Indietro", callback_data="cancel")]]
    await send(context, chat_id,
        "📰 <b>SEGNALAZIONE NOTIZIA</b>\n"
        "Invia una notizia qui per segnarla.\nInserisci tutte le prove e/o foto in possesso.", kb)
    return SEGNALA

async def process_news(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id     = update.effective_chat.id
    user        = update.effective_user
    mittente    = f"@{user.username}" if user.username else user.first_name
    header      = f"📰 <b>NUOVA NOTIZIA SEGNALATA</b>\nDa: {mittente}\n\n"
    user_msg_id = update.message.message_id

    try:
        if update.message.text:
            await context.bot.send_message(GROUP_ID, header + update.message.text, parse_mode="HTML")
        elif update.message.photo:
            cap = (update.message.caption or "") + f"\n\n{header}"
            await context.bot.send_photo(GROUP_ID, update.message.photo[-1].file_id, caption=cap, parse_mode="HTML")
        elif update.message.video:
            cap = (update.message.caption or "") + f"\n\n{header}"
            await context.bot.send_video(GROUP_ID, update.message.video.file_id, caption=cap, parse_mode="HTML")
        elif update.message.document:
            cap = (update.message.caption or "") + f"\n\n{header}"
            await context.bot.send_document(GROUP_ID, update.message.document.file_id, caption=cap, parse_mode="HTML")
        else:
            await delete_msg_id(context, chat_id, user_msg_id)
            await delete_last_bot_msg(context, chat_id)
            kb = [[InlineKeyboardButton("🔙 Indietro", callback_data="cancel")]]
            await send(context, chat_id, "⚠️ Invia testo, foto, video o documento.", kb)
            return SEGNALA
    except Exception:
        await delete_msg_id(context, chat_id, user_msg_id)
        await delete_last_bot_msg(context, chat_id)
        kb = [[InlineKeyboardButton("🔙 Indietro", callback_data="cancel")]]
        await send(context, chat_id, "❌ Errore durante l'invio. Riprova.", kb)
        return SEGNALA

    await delete_msg_id(context, chat_id, user_msg_id)
    await delete_last_bot_msg(context, chat_id)
    kb = [[InlineKeyboardButton("🔙 Torna al menu", callback_data="cancel")]]
    await send(context, chat_id,
        "✅ <b>Notizia segnalata con successo!</b>\nUn giornalista la esaminerà a breve.", kb)
    return MENU

# REDAZIONE
async def redazione_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    await update.callback_query.answer()
    await safe_delete(update)

    if not CANDIDATURE_CFG["aperte"]:
        kb = [[InlineKeyboardButton("🔙 Torna al menu", callback_data="cancel")]]
        await send(context, chat_id,
            "🔒 <b>Candidature chiuse</b>\n\n"
            "Al momento le candidature sono chiuse. Resta aggiornato sul canale @ZeroUltimora!", kb)
        return MENU

    modulo = CANDIDATURE_CFG["modulo"]
    kb = [[InlineKeyboardButton("🔙 Torna al menu", callback_data="cancel")]]
    await send(context, chat_id,
        "🤝 <b>CANDIDATURA REDAZIONE</b>\n"
        "Le candidature sono attualmente <b>aperte</b>!\n"
        "Copia il modulo qui sotto, compilalo e invialo in un unico messaggio:\n\n"
        f"<code>{modulo}</code>", kb)
    return REDAZIONE

async def process_redazione(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id     = update.effective_chat.id
    user_msg_id = update.message.message_id

    if not CANDIDATURE_CFG["aperte"]:
        await delete_msg_id(context, chat_id, user_msg_id)
        await delete_last_bot_msg(context, chat_id)
        kb = [[InlineKeyboardButton("🔙 Torna al menu", callback_data="cancel")]]
        await send(context, chat_id, "🔒 <b>Candidature chiuse</b>\n\nSono appena state chiuse.", kb)
        return MENU

    user     = update.effective_user
    mittente = f"@{user.username}" if user.username else user.first_name
    testo    = update.message.text or "(nessun testo)"

    try:
        await context.bot.send_message(
            GROUP_ID,
            f"🤝 <b>NUOVA CANDIDATURA CONDUTTORE</b>\n"
            f"Username: {mittente}  |  ID: <code>{user.id}</code>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n\n{testo}",
            parse_mode="HTML"
        )
    except Exception:
        await delete_msg_id(context, chat_id, user_msg_id)
        await delete_last_bot_msg(context, chat_id)
        kb = [[InlineKeyboardButton("🔙 Indietro", callback_data="cancel")]]
        await send(context, chat_id, "❌ Errore durante l'invio. Riprova.", kb)
        return REDAZIONE

    await delete_msg_id(context, chat_id, user_msg_id)
    await delete_last_bot_msg(context, chat_id)
    kb = [[InlineKeyboardButton("🔙 Torna al menu", callback_data="cancel")]]
    await send(context, chat_id,
        "✅ <b>Candidatura inviata!</b>\n\n"
        "La direzione di ZeroUltim'Ora la esaminerà e ti contatterà al più presto. 🎙", kb)
    return MENU

# SPONSOR — LISTINO UNICO (durata + extra)
async def sponsor_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    await safe_delete(update)
    context.user_data["durata"] = None
    context.user_data["extras"] = []
    context.user_data["giorni"] = 2
    return await mostra_listino(context, update.effective_chat.id)

async def mostra_listino(context, chat_id: int):
    durata = context.user_data.get("durata")
    extras = context.user_data.get("extras", [])
    giorni = context.user_data.get("giorni", 2)

    def dl(key, label):
        return f"✅ {label}" if durata == key else label

    def el(key, label):
        return f"✅ {label}" if key in extras else label

    prezzo_str = ""
    if durata:
        tot = calcola_prezzo(durata, giorni, extras)
        prezzo_str = f"\n\n💰 Totale: <b>{fp(tot)}</b>"

    testo = (
        "💼 <b>LISTINO SPONSOR</b>\n\n"
        f"⏱️ 12h  »  <i>{fp(PREZZI['12h'])}</i>\n"
        f"⏱️ 24h  »  <i>{fp(PREZZI['24h'])}</i>\n"
        f"⏱️ 2 giorni  »  <i>{fp(PREZZI['2d'])}</i>\n"
        f"⏱️ 2+ giorni  »  <i>{fp(PREZZI['plus'])} + {fp(PREZZI['plus_g'])}/giorno</i>\n"
        f"♾️ Per sempre  »  <i>{fp(PREZZI['perma'])}</i>\n\n"
        f"📌 Messaggio fissato per 7 giorni  »  <i>prezzo base + {fp(PREZZI['fissato'])}</i>\n"
        f"🔄 Repost del messaggio  »  <i>prezzo base + {fp(PREZZI['repost'])}</i>"
        f"{prezzo_str}"
    )

    kb = [
        [InlineKeyboardButton(dl("12h",   "⏱️ 12h"),       callback_data="dur_12h"),
         InlineKeyboardButton(dl("24h",   "⏱️ 24h"),       callback_data="dur_24h")],
        [InlineKeyboardButton(dl("2d",    "⏱️ 2 giorni"),   callback_data="dur_2d"),
         InlineKeyboardButton(dl("plus",  "⏱️ 2+ giorni"),  callback_data="dur_plus")],
        [InlineKeyboardButton(dl("perma", "♾️ Per sempre"),  callback_data="dur_perma")],
        [InlineKeyboardButton(el("fissato", "📌 Fissato 7gg"), callback_data="ext_fissato"),
         InlineKeyboardButton(el("repost",  "🔄 Repost"),       callback_data="ext_repost")],
    ]
    if durata:
        kb.append([InlineKeyboardButton("📩 Procedi", callback_data="sp_procedi")])
    kb.append([InlineKeyboardButton("🔙 Indietro", callback_data="cancel")])

    existing = context.bot_data.get(f"last_bot_msg_{chat_id}")
    if existing:
        try:
            await context.bot.edit_message_text(
                chat_id=chat_id, message_id=existing,
                text=testo, parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup(kb)
            )
            return SP_LISTINO
        except Exception:
            pass
    await send(context, chat_id, testo, kb)
    return SP_LISTINO

async def sp_sel_durata(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    scelta  = update.callback_query.data.replace("dur_", "")
    chat_id = update.effective_chat.id

    if context.user_data.get("durata") == scelta:
        context.user_data["durata"] = None
    else:
        context.user_data["durata"] = scelta

    if context.user_data.get("durata") == "plus":
        await safe_delete(update)
        kb = [[InlineKeyboardButton("🔙 Annulla", callback_data="cancel")]]
        await send(context, chat_id, "📅 <b>Quanti giorni in totale?</b> (minimo 3):", kb)
        return SP_GIORNI

    return await mostra_listino(context, chat_id)

async def sp_sel_extra(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    ext    = update.callback_query.data.replace("ext_", "")
    extras = context.user_data.setdefault("extras", [])
    if ext in extras:
        extras.remove(ext)
    else:
        extras.append(ext)
    return await mostra_listino(context, update.effective_chat.id)

async def sp_giorni(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id     = update.effective_chat.id
    user_msg_id = update.message.message_id
    try:
        context.user_data["giorni"] = max(3, int(update.message.text.strip()))
    except ValueError:
        await delete_msg_id(context, chat_id, user_msg_id)
        await delete_last_bot_msg(context, chat_id)
        kb = [[InlineKeyboardButton("🔙 Annulla", callback_data="cancel")]]
        await send(context, chat_id, "⚠️ Inserisci un numero valido (es. 5):", kb)
        return SP_GIORNI

    await delete_msg_id(context, chat_id, user_msg_id)
    await delete_last_bot_msg(context, chat_id)
    return await mostra_listino(context, chat_id)

# SPONSOR — PROVA PAGAMENTO
async def sp_procedi(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    chat_id = update.effective_chat.id
    durata  = context.user_data.get("durata")
    giorni  = context.user_data.get("giorni", 2)
    extras  = context.user_data.get("extras", [])
    prezzo  = calcola_prezzo(durata, giorni, extras)
    await safe_delete(update)

    kb = [[InlineKeyboardButton("🔙 Annulla", callback_data="cancel")]]
    await send(context, chat_id,
        f"💳 <b>PROVA DI PAGAMENTO</b>\n\n"
        f"Invia il pagamento di <b>{fp(prezzo)}</b> tramite bonifico a:\n\n"
        f"👤 <b>ItzMavck</b> \n\n"
        "Poi invia qui lo <b>screenshot del bonifico </b>come conferma.", kb)
    return SP_PAGAMENTO

async def sp_ricevi_pagamento(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id     = update.effective_chat.id
    user_msg_id = update.message.message_id

    if not update.message.photo:
        await delete_msg_id(context, chat_id, user_msg_id)
        await delete_last_bot_msg(context, chat_id)
        kb = [[InlineKeyboardButton("🔙 Annulla", callback_data="cancel")]]
        await send(context, chat_id,
            "❌ <b>Formato non valido.</b>\n\n"
            "Devi inviare una <b>foto</b> del bonifico. Riprova:", kb)
        return SP_PAGAMENTO

    context.user_data["prova_pagamento"] = update.message.photo[-1].file_id
    await delete_msg_id(context, chat_id, user_msg_id)
    await delete_last_bot_msg(context, chat_id)

    kb = [[InlineKeyboardButton("🔙 Annulla", callback_data="cancel")]]
    await send(context, chat_id,
        "📩 <b>INVIA IL MESSAGGIO</b>\n\n"
        "Invia o inoltra il messaggio che vuoi pubblicare.\n", kb)
    return SP_CONTENUTO

# SPONSOR — CONTENUTO → al gruppo
async def sp_ricevi_contenuto(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id     = update.effective_chat.id
    user        = update.effective_user
    user_msg_id = update.message.message_id
    durata      = context.user_data.get("durata", "")
    giorni      = context.user_data.get("giorni", 2)
    extras      = context.user_data.get("extras", [])
    prova_pag   = context.user_data.get("prova_pagamento", "")
    mittente    = f"@{user.username}" if user.username else user.first_name
    prezzo      = calcola_prezzo(durata, giorni, extras)
    invio_at    = datetime.now()

    contenuto_tipo = None
    contenuto_id   = None
    contenuto_cap  = update.message.caption or ""

    if update.message.text:
        contenuto_tipo = "text"
        contenuto_id   = update.message.text
    elif update.message.photo:
        contenuto_tipo = "photo"
        contenuto_id   = update.message.photo[-1].file_id
    elif update.message.video:
        contenuto_tipo = "video"
        contenuto_id   = update.message.video.file_id
    elif update.message.document:
        contenuto_tipo = "document"
        contenuto_id   = update.message.document.file_id
    elif update.message.animation:
        contenuto_tipo = "animation"
        contenuto_id   = update.message.animation.file_id
    else:
        await delete_msg_id(context, chat_id, user_msg_id)
        await delete_last_bot_msg(context, chat_id)
        kb = [[InlineKeyboardButton("🔙 Annulla", callback_data="cancel")]]
        await send(context, chat_id, "⚠️ Tipo non supportato. Invia testo, foto, video o documento.", kb)
        return SP_CONTENUTO

    extra_str = ""
    if "fissato" in extras: extra_str += "\n📌 Messaggio fissato 7gg"
    if "repost"  in extras: extra_str += "\n🔄 1 Repost"

    try:
        anteprima = await context.bot.forward_message(
            chat_id=GROUP_ID,
            from_chat_id=chat_id,
            message_id=user_msg_id
        )

        kb_staff = build_kb_scheda(anteprima.message_id, "cpy")
        scheda = await context.bot.send_photo(
            GROUP_ID,
            photo=prova_pag,
            caption=(
                f"💼 <b>RICHIESTA SPONSOR</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"👤 <b> Cliente</b>: {mittente}\n"
                f"⏱️ <b>Durata</b>: {descrivi_durata(durata, giorni)}\n"
                f"💰 <b>Prezzo</b>: {fp(prezzo)}\n"
                f"📅  <b>Inviata</b>: {invio_at.strftime('%d/%m/%Y alle %H:%M')}"
                f"{extra_str}\n"
                f"━━━━━━━━━━━━━━━━━━━━"
            ),
            parse_mode="HTML",
            reply_markup=kb_staff
        )

        SPONSOR_PENDING[scheda.message_id] = {
            "user_id":        user.id,
            "user_chat_id":   chat_id,
            "mittente":       mittente,
            "durata":         durata,
            "giorni":         giorni,
            "extras":         extras,
            "prezzo":         prezzo,
            "contenuto_tipo": contenuto_tipo,
            "contenuto_id":   contenuto_id,
            "contenuto_cap":  contenuto_cap,
            "anteprima_id":   anteprima.message_id,
            "modalita":       "cpy",
            "invio_at":       invio_at.isoformat(),
            "from_chat_id":   chat_id,
            "from_msg_id":    user_msg_id,
        }

    except Exception:
        await delete_last_bot_msg(context, chat_id)
        kb = [[InlineKeyboardButton("🔙 Annulla", callback_data="cancel")]]
        await send(context, chat_id, f"❌ Errore durante l'invio. Contatta la redazione.", kb)
        return MENU

    await delete_last_bot_msg(context, chat_id)
    kb = [[InlineKeyboardButton("🔙 Menu", callback_data="cancel")]]
    await send(context, chat_id,
        "⏳ <b>Richiesta inviata allo staff!</b>\n\n"
        "La tua sponsor è in attesa di approvazione.\n"
        "Riceverai una notifica non appena verrà esaminata. 🔔", kb)
    return MENU

# SPONSOR — BOTTONI SCHEDA (gruppo)
def build_kb_scheda(anteprima_id: int, modalita: str) -> InlineKeyboardMarkup:
    fwd = "✅ Inoltra" if modalita == "fwd" else "📤 Inoltra"
    cpy = "✅ Copia"   if modalita == "cpy" else "📋 Copia"
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(fwd, callback_data=f"sp_modo_fwd_{anteprima_id}"),
         InlineKeyboardButton(cpy, callback_data=f"sp_modo_cpy_{anteprima_id}")],
        [InlineKeyboardButton("✅ Approva", callback_data=f"sp_approva_{anteprima_id}"),
         InlineKeyboardButton("❌ Rifiuta", callback_data=f"sp_rifiuta_{anteprima_id}")],
    ])

async def sp_modo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != GROUP_ID:
        await update.callback_query.answer("❌ Non autorizzato.", show_alert=True)
        return

    data      = update.callback_query.data
    nuova_mod = data.split("_")[2]
    scheda_id = update.callback_query.message.message_id

    pending = SPONSOR_PENDING.get(scheda_id)
    if not pending:
        await update.callback_query.answer("⚠️ Dati non trovati.", show_alert=True)
        return

    pending["modalita"] = nuova_mod
    await update.callback_query.answer(
        "Modalità: Inoltra ✅" if nuova_mod == "fwd" else "Modalità: Copia ✅"
    )
    try:
        await update.callback_query.message.edit_reply_markup(
            reply_markup=build_kb_scheda(pending["anteprima_id"], nuova_mod)
        )
    except Exception:
        pass

# SPONSOR — APPROVAZIONE (gruppo)
async def sp_approva(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != GROUP_ID:
        await update.callback_query.answer("❌ Non autorizzato.", show_alert=True)
        return

    await update.callback_query.answer()
    scheda_id = update.callback_query.message.message_id
    pending   = SPONSOR_PENDING.get(scheda_id)

    if not pending:
        await context.bot.send_message(GROUP_ID, "⚠️ Dati sponsor non trovati (già gestita?).")
        return

    modalita     = pending["modalita"]
    durata       = pending["durata"]
    giorni       = pending["giorni"]
    extras       = pending["extras"]
    user_chat_id = pending["user_chat_id"]
    prezzo       = pending["prezzo"]
    mittente     = pending["mittente"]
    tipo         = pending["contenuto_tipo"]
    cid          = pending["contenuto_id"]
    cap          = pending["contenuto_cap"] or ""
    from_chat_id = pending["from_chat_id"]
    from_msg_id  = pending["from_msg_id"]

    scadenza = calcola_scadenza(durata, giorni)
    scad_str = scadenza.strftime("%d/%m/%Y alle %H:%M") if scadenza else "Permanente ♾️"

    repost_at = None
    if "repost" in extras and scadenza:
        delta = (scadenza - datetime.now()) / 2
        if delta < timedelta(hours=12):
            delta = timedelta(hours=12)
        repost_at = (datetime.now() + delta).isoformat()

    try:
        # Non invia sticker se l'ultimo messaggio era già uno sticker
        sticker_id = None
        if CANALE_STATO.get("ultimo_tipo") != "sticker":
            sticker = await context.bot.send_sticker(CHANNEL_ID, STICKER_SEPARATORE)
            sticker_id = sticker.message_id
            CANALE_STATO["ultimo_tipo"] = "sticker"
            salva_canale_stato(CANALE_STATO)
        
        # Invia il messaggio "SPONSOR ZEROULTIMORA" prima della sponsor
        msg_sponsor = await context.bot.send_message(
            CHANNEL_ID,
            "❕ <b>ZeroUltim'Ora Sponsor</b>\n\n<i>👇 Lo Studio Televisivo non si prende la responsabilità di eventuali truffe o disagi provocati dal canale sponsorizzato.</i>\n\nPer maggiori informazioni sulle sponsor <a href=\"https://t.me/tecnoultimora/12146\"><b>clicca qui</b></a>",
            parse_mode="HTML"
        )
        sponsor_msg_id = msg_sponsor.message_id
        CANALE_STATO["ultimo_tipo"] = "text"
        salva_canale_stato(CANALE_STATO)

        # ── Pubblica il contenuto sul canale ──
        if modalita == "fwd":
            pub = await context.bot.forward_message(
                chat_id=CHANNEL_ID,
                from_chat_id=from_chat_id,
                message_id=from_msg_id
            )
        else:
            if tipo == "text":
                pub = await context.bot.send_message(CHANNEL_ID, cid)
            elif tipo == "photo":
                pub = await context.bot.send_photo(CHANNEL_ID, cid, caption=cap or None)
            elif tipo == "video":
                pub = await context.bot.send_video(CHANNEL_ID, cid, caption=cap or None)
            elif tipo == "document":
                pub = await context.bot.send_document(CHANNEL_ID, cid, caption=cap or None)
            elif tipo == "animation":
                pub = await context.bot.send_animation(CHANNEL_ID, cid, caption=cap or None)
            else:
                pub = await context.bot.send_message(CHANNEL_ID, cid)

        CANALE_STATO["ultimo_tipo"] = "sponsor"
        salva_canale_stato(CANALE_STATO)

        if "fissato" in extras:
            try:
                await context.bot.pin_chat_message(
                    CHANNEL_ID, pub.message_id,
                    disable_notification=True
                )
                try:
                    await context.bot.delete_message(CHANNEL_ID, pub.message_id + 1)
                except Exception:
                    pass
            except Exception:
                pass

        SPONSOR_ATTIVE[pub.message_id] = {
            "scadenza":  scadenza,
            "pin":       "fissato" in extras,
            "repost_at": repost_at,
            "repostato": False,
            "chat_id":   user_chat_id,
            "mittente":  mittente,
            "sticker_id": sticker_id,
            "sponsor_msg_id": sponsor_msg_id,
        }
        salva_sponsor(SPONSOR_ATTIVE)

        link = f"https://t.me/{CHANNEL_USERNAME}/{pub.message_id}"

        extra_str_notifica = ""
        if "fissato" in extras: extra_str_notifica += "\n📌 Messaggio fissato per 7gg"
        if "repost"  in extras: extra_str_notifica += "\n🔄 Repost incluso"

        await context.bot.send_message(
            user_chat_id,
            f"✅ <b>Sponsor approvata!</b>\n\n"
            f"<b>Prezzo:</b> {fp(prezzo)}\n"
            f"<b>Scadenza:</b> {scad_str}"
            f"{extra_str_notifica}\n\n"
            f'<i><a href="{link}">Clicca qui per visualizzarla</a></i>',
            parse_mode="HTML",
            disable_web_page_preview=True
        )

        modo_label = "Inoltrata 📤" if modalita == "fwd" else "Copiata 📋"
        await context.bot.edit_message_caption(
            chat_id=GROUP_ID,
            message_id=scheda_id,
            caption=(
                f"✅ <b>SPONSOR APPROVATA</b>  —  {modo_label}\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"👤 {mittente}\n"
                f"💰 {fp(prezzo)}\n"
                f"📅 Scade: {scad_str}"
            ),
            parse_mode="HTML"
        )

    except Exception as e:
        await context.bot.send_message(
            GROUP_ID,
            f"❌ Errore durante la pubblicazione:\n<code>{e}</code>",
            parse_mode="HTML"
        )
        return

    SPONSOR_PENDING.pop(scheda_id, None)

# SPONSOR — RIFIUTO (gruppo)
async def sp_rifiuta(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != GROUP_ID:
        await update.callback_query.answer("❌ Non autorizzato.", show_alert=True)
        return

    await update.callback_query.answer()
    scheda_id = update.callback_query.message.message_id
    pending   = SPONSOR_PENDING.get(scheda_id)

    if not pending:
        await context.bot.send_message(GROUP_ID, "⚠️ Dati sponsor non trovati (già gestita?).")
        return

    try:
        await context.bot.send_message(
            pending["user_chat_id"],
            "❌ <b>Sponsor rifiutata</b>\n\n"
            "La tua richiesta è stata rifiutata.\n"
            "Per maggiori informazioni contatta la redazione di ZeroUltim'Ora.",
            parse_mode="HTML"
        )
    except Exception:
        pass

    try:
        await context.bot.edit_message_caption(
            chat_id=GROUP_ID,
            message_id=scheda_id,
            caption=(
                f"❌ <b>SPONSOR RIFIUTATA</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"👤 {pending['mittente']}\n"
                f"💰 {fp(pending['prezzo'])}"
            ),
            parse_mode="HTML"
        )
    except Exception:
        pass

    SPONSOR_PENDING.pop(scheda_id, None)

# JOB: SCADENZE SPONSOR
async def check_sponsor(context: ContextTypes.DEFAULT_TYPE):
    now     = datetime.now()
    changed = False

    for msg_id, data in list(SPONSOR_ATTIVE.items()):
        if (data.get("repost_at") and not data.get("repostato") and
                now >= datetime.fromisoformat(data["repost_at"])):
            try:
                await context.bot.forward_message(CHANNEL_ID, CHANNEL_ID, msg_id)
                SPONSOR_ATTIVE[msg_id]["repostato"] = True
                CANALE_STATO["ultimo_tipo"] = "sponsor"
                salva_canale_stato(CANALE_STATO)
                changed = True
            except Exception:
                pass

        if data["scadenza"] and now > data["scadenza"]:
            try:
                await context.bot.delete_message(CHANNEL_ID, msg_id)
                if data["pin"]:
                    try:
                        await context.bot.unpin_chat_message(CHANNEL_ID, msg_id)
                    except Exception:
                        pass
            except Exception:
                pass
            sticker_id = data.get("sticker_id")
            if sticker_id:
                try:
                    await context.bot.delete_message(CHANNEL_ID, sticker_id)
                except Exception:
                    pass
            sponsor_msg_id = data.get("sponsor_msg_id")
            if sponsor_msg_id:
                try:
                    await context.bot.delete_message(CHANNEL_ID, sponsor_msg_id)
                except Exception:
                    pass
            del SPONSOR_ATTIVE[msg_id]
            changed = True

    if changed:
        salva_sponsor(SPONSOR_ATTIVE)

# PANNELLO CANDIDATURE
def pannello_testo() -> str:
    stato  = "✅ <b>APERTE</b>" if CANDIDATURE_CFG["aperte"] else "❌ <b>CHIUSE</b>"
    antepr = CANDIDATURE_CFG["modulo"][:200] + ("..." if len(CANDIDATURE_CFG["modulo"]) > 200 else "")
    return (
        f"🗂 <b>GESTIONE CANDIDATURE REDAZIONE</b>\n\n"
        f"Stato: {stato}\n\n"
        f"📋 <b>Modulo attuale:</b>\n<pre>{antepr}</pre>"
    )

def pannello_kb() -> InlineKeyboardMarkup:
    aperte = CANDIDATURE_CFG["aperte"]
    btn = (InlineKeyboardButton("❌ Chiudi candidature", callback_data="cand_chiudi")
           if aperte else
           InlineKeyboardButton("✅ Apri candidature", callback_data="cand_apri"))
    return InlineKeyboardMarkup([
        [btn],
        [InlineKeyboardButton("✏️ Modifica modulo", callback_data="cand_modifica")],
    ])

async def invia_o_aggiorna_pannello(context: ContextTypes.DEFAULT_TYPE):
    msg_id = CANDIDATURE_CFG.get("pannello_msg_id")
    testo  = pannello_testo()
    kb     = pannello_kb()
    if msg_id:
        try:
            await context.bot.edit_message_text(
                chat_id=GROUP_ID, message_id=msg_id,
                text=testo, parse_mode="HTML", reply_markup=kb)
            return
        except Exception:
            pass
    msg = await context.bot.send_message(GROUP_ID, testo, parse_mode="HTML", reply_markup=kb)
    CANDIDATURE_CFG["pannello_msg_id"] = msg.message_id
    salva_candidature()

async def cmd_candidature(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != GROUP_ID:
        return
    await invia_o_aggiorna_pannello(context)
    try:
        await update.message.delete()
    except Exception:
        pass

async def cand_apri(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != GROUP_ID:
        await update.callback_query.answer("❌ Non autorizzato.", show_alert=True)
        return
    await update.callback_query.answer("✅ Candidature aperte!")
    CANDIDATURE_CFG["aperte"] = True
    salva_candidature()
    await invia_o_aggiorna_pannello(context)

async def cand_chiudi(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != GROUP_ID:
        await update.callback_query.answer("❌ Non autorizzato.", show_alert=True)
        return
    await update.callback_query.answer("❌ Candidature chiuse.")
    CANDIDATURE_CFG["aperte"] = False
    salva_candidature()
    await invia_o_aggiorna_pannello(context)

async def cand_modifica(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != GROUP_ID:
        await update.callback_query.answer("❌ Non autorizzato.", show_alert=True)
        return
    await update.callback_query.answer()
    context.bot_data["attesa_modulo_da"] = update.callback_query.from_user.id
    await context.bot.send_message(
        GROUP_ID,
        "✏️ <b>MODIFICA MODULO</b>\n\nInvia il nuovo testo del modulo.",
        parse_mode="HTML"
    )

async def ricevi_nuovo_modulo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    attesa_da = context.bot_data.get("attesa_modulo_da")
    if not attesa_da or update.effective_user.id != attesa_da:
        return
    if update.effective_chat.id != GROUP_ID:
        return
    nuovo = update.message.text.strip()
    if not nuovo:
        return
    CANDIDATURE_CFG["modulo"] = nuovo
    salva_candidature()
    context.bot_data.pop("attesa_modulo_da", None)
    try:
        await update.message.delete()
    except Exception:
        pass
    await context.bot.send_message(
        GROUP_ID,
        f"✅ <b>Modulo aggiornato!</b>\n\n<pre>{nuovo}</pre>",
        parse_mode="HTML"
    )
    await invia_o_aggiorna_pannello(context)

# COMANDI STAFF
async def lista_sponsor_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != GROUP_ID:
        return
    if not SPONSOR_ATTIVE:
        await update.message.reply_text("Nessuna sponsor attiva al momento.")
        return

    testo = "📋 <b>SPONSOR ATTIVE</b>\n\n"
    for msg_id, info in SPONSOR_ATTIVE.items():
        sc   = info["scadenza"].strftime("%d/%m %H:%M") if info["scadenza"] else "Permanente"
        pin  = " 📌" if info["pin"] else ""
        nome = info.get("mittente", "Sconosciuto")
        link = f"https://t.me/{CHANNEL_USERNAME}/{msg_id}"
        testo += f'• <a href="{link}">Sponsor di {nome}</a> — {sc}{pin}\n'

    await update.message.reply_text(testo, parse_mode="HTML", disable_web_page_preview=True)

async def rimuovi_sponsor_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != GROUP_ID:
        return
    if not context.args:
        await update.message.reply_text("Uso: /rimuovi <msg_id>")
        return
    try:
        msg_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("⚠️ ID non valido.")
        return
    if msg_id not in SPONSOR_ATTIVE:
        await update.message.reply_text("⚠️ Sponsor non trovata.")
        return
    try:
        await context.bot.delete_message(CHANNEL_ID, msg_id)
        if SPONSOR_ATTIVE[msg_id].get("pin"):
            await context.bot.unpin_chat_message(CHANNEL_ID, msg_id)
    except Exception:
        pass
    sticker_id = SPONSOR_ATTIVE[msg_id].get("sticker_id")
    if sticker_id:
        try:
            await context.bot.delete_message(CHANNEL_ID, sticker_id)
        except Exception:
            pass
    nome = SPONSOR_ATTIVE[msg_id].get("mittente", str(msg_id))
    del SPONSOR_ATTIVE[msg_id]
    salva_sponsor(SPONSOR_ATTIVE)
    await update.message.reply_text(f"✅ Sponsor di <b>{nome}</b> rimossa.", parse_mode="HTML")

# HANDLER: messaggi di servizio nel canale
async def cancella_service_msg(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancella i messaggi di servizio 'Pinned a message' nel canale."""
    msg = update.channel_post or update.message
    if not msg:
        return
    if msg.chat.id != CHANNEL_ID:
        return
    if msg.pinned_message:
        try:
            await context.bot.delete_message(CHANNEL_ID, msg.message_id)
        except Exception:
            pass

async def monitora_canale(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Monitora TUTTI i messaggi nel canale e aggiorna lo stato dell'ultimo tipo"""
    msg = update.channel_post
    if not msg or msg.chat.id != CHANNEL_ID:
        return
    
    # Determina il tipo di messaggio
    if msg.sticker:
        CANALE_STATO["ultimo_tipo"] = "sticker"
    elif msg.text or msg.caption:
        CANALE_STATO["ultimo_tipo"] = "text"
    elif msg.photo or msg.video or msg.document or msg.animation:
        CANALE_STATO["ultimo_tipo"] = "media"
    else:
        CANALE_STATO["ultimo_tipo"] = "other"
    
    salva_canale_stato(CANALE_STATO)

# MAIN
def main():
    app = Application.builder().token(TOKEN).build()

    conv = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            MENU: [
                CallbackQueryHandler(news_start,      "^news$"),
                CallbackQueryHandler(sponsor_start,   "^sponsor$"),
                CallbackQueryHandler(redazione_start, "^redazione$"),
                CallbackQueryHandler(start,           "^cancel$"),
            ],
            SEGNALA: [
                MessageHandler(filters.ALL & ~filters.COMMAND, process_news),
                CallbackQueryHandler(start, "^cancel$"),
            ],
            REDAZIONE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, process_redazione),
                CallbackQueryHandler(start, "^cancel$"),
            ],
            SP_LISTINO: [
                CallbackQueryHandler(sp_sel_durata, "^dur_"),
                CallbackQueryHandler(sp_sel_extra,  "^ext_"),
                CallbackQueryHandler(sp_procedi,    "^sp_procedi$"),
                CallbackQueryHandler(start,         "^cancel$"),
            ],
            SP_GIORNI: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, sp_giorni),
                CallbackQueryHandler(start, "^cancel$"),
            ],
            SP_PAGAMENTO: [
                MessageHandler(filters.ALL & ~filters.COMMAND, sp_ricevi_pagamento),
                CallbackQueryHandler(start, "^cancel$"),
            ],
            SP_CONTENUTO: [
                MessageHandler(filters.ALL & ~filters.COMMAND, sp_ricevi_contenuto),
                CallbackQueryHandler(start, "^cancel$"),
            ],
        },
        fallbacks=[
            CommandHandler("start", start),
            CallbackQueryHandler(start, "^cancel$"),
        ],
        per_chat=True,
        per_message=False,
        allow_reentry=True,
    )

    app.add_handler(conv)

    app.add_handler(CommandHandler("candidature", cmd_candidature))
    app.add_handler(CommandHandler("sponsor",     lista_sponsor_cmd))
    app.add_handler(CommandHandler("rimuovi",     rimuovi_sponsor_cmd))

    app.add_handler(CallbackQueryHandler(cand_apri,     "^cand_apri$"))
    app.add_handler(CallbackQueryHandler(cand_chiudi,   "^cand_chiudi$"))
    app.add_handler(CallbackQueryHandler(cand_modifica, "^cand_modifica$"))

    app.add_handler(CallbackQueryHandler(sp_modo,    r"^sp_modo_(fwd|cpy)_\d+$"))
    app.add_handler(CallbackQueryHandler(sp_approva, r"^sp_approva_\d+$"))
    app.add_handler(CallbackQueryHandler(sp_rifiuta, r"^sp_rifiuta_\d+$"))

    app.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND & filters.Chat(GROUP_ID),
        ricevi_nuovo_modulo
    ))

    app.add_handler(MessageHandler(
        filters.Chat(CHANNEL_ID) & filters.StatusUpdate.PINNED_MESSAGE,
        cancella_service_msg
    ))

    app.add_handler(MessageHandler(
        filters.Chat(CHANNEL_ID),
        monitora_canale
    ))

    app.job_queue.run_repeating(check_sponsor, interval=60)

    _boot_logger.info("✅ Bot ZeroUltim'Ora avviato")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
