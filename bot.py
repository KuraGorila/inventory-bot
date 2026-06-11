import os
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    CallbackQueryHandler, ConversationHandler, filters, ContextTypes
)
from sheets import SheetsClient
from datetime import datetime

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Conversation states
(PILIH_AKSI, INPUT_NAMA_BARANG, INPUT_KUALITAS, INPUT_JUMLAH, INPUT_MODAL, KONFIRMASI) = range(6)

CABANG_MAP = {
    os.getenv("TELEGRAM_ID_CABANG1"): "Cabang 1",
    os.getenv("TELEGRAM_ID_CABANG2"): "Cabang 2",
}

sheets = SheetsClient()


def get_cabang(user_id: str) -> str | None:
    return CABANG_MAP.get(str(user_id))


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    cabang = get_cabang(user_id)
    if not cabang:
        await update.message.reply_text(
            "⛔ Akses ditolak. ID Telegram kamu tidak terdaftar.\n"
            f"ID kamu: `{user_id}`",
            parse_mode="Markdown"
        )
        return ConversationHandler.END

    keyboard = [
        [InlineKeyboardButton("📦 Input Barang Masuk", callback_data="barang_masuk")],
        [InlineKeyboardButton("📊 Lihat Stok Cabangku", callback_data="lihat_stok_sendiri")],
        [InlineKeyboardButton("🏪 Lihat Stok Semua Cabang", callback_data="lihat_stok_semua")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        f"👋 Halo! Kamu terdaftar sebagai *{cabang}*\n\nPilih aksi:",
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )
    return PILIH_AKSI


async def pilih_aksi(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = str(query.from_user.id)
    cabang = get_cabang(user_id)

    if query.data == "barang_masuk":
        context.user_data["cabang"] = cabang
        await query.edit_message_text("📦 *Input Barang Masuk*\n\nKetik nama barang:", parse_mode="Markdown")
        return INPUT_NAMA_BARANG

    elif query.data == "lihat_stok_sendiri":
        stok = sheets.get_stok(cabang=cabang)
        pesan = format_stok(stok, judul=f"📊 Stok {cabang}")
        await query.edit_message_text(pesan, parse_mode="Markdown")
        return ConversationHandler.END

    elif query.data == "lihat_stok_semua":
        stok = sheets.get_stok()
        pesan = format_stok(stok, judul="🏪 Stok Semua Cabang")
        await query.edit_message_text(pesan, parse_mode="Markdown")
        return ConversationHandler.END


def format_stok(stok: list, judul: str) -> str:
    if not stok:
        return f"{judul}\n\n_Belum ada data stok._"
    lines = [f"*{judul}*\n"]
    cabang_sebelumnya = ""
    for row in stok:
        if row.get("cabang") != cabang_sebelumnya:
            cabang_sebelumnya = row.get("cabang", "")
            lines.append(f"\n🏪 *{cabang_sebelumnya}*")
        lines.append(f"  • {row['nama_barang']} — *{row['stok']}* {row.get('satuan', 'pcs')}")
    return "\n".join(lines)


async def input_nama_barang(update: Update, context: ContextTypes.DEFAULT_TYPE):
    nama = update.message.text.strip()
    context.user_data["nama_barang"] = nama

    keyboard = [
        [InlineKeyboardButton("A", callback_data="kualitas_A"),
         InlineKeyboardButton("B", callback_data="kualitas_B"),
         InlineKeyboardButton("C", callback_data="kualitas_C")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        f"✅ Nama barang: *{nama}*\n\nPilih kualitas:",
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )
    return INPUT_KUALITAS


async def input_kualitas(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    kualitas = query.data.replace("kualitas_", "")
    context.user_data["kualitas"] = kualitas
    await query.edit_message_text(
        f"✅ Kualitas: *{kualitas}*\n\nMasukkan jumlah (angka saja):",
        parse_mode="Markdown"
    )
    return INPUT_JUMLAH


async def input_jumlah(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        jumlah = int(update.message.text.strip())
        if jumlah <= 0:
            raise ValueError
    except ValueError:
        await update.message.reply_text("⚠️ Masukkan angka yang valid (lebih dari 0):")
        return INPUT_JUMLAH

    context.user_data["jumlah"] = jumlah
    await update.message.reply_text(
        f"✅ Jumlah: *{jumlah}*\n\nMasukkan modal per satuan (Rp, angka saja):",
        parse_mode="Markdown"
    )
    return INPUT_MODAL


async def input_modal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        modal_text = update.message.text.strip().replace(".", "").replace(",", "")
        modal = int(modal_text)
        if modal < 0:
            raise ValueError
    except ValueError:
        await update.message.reply_text("⚠️ Masukkan nominal modal yang valid (contoh: 50000):")
        return INPUT_MODAL

    context.user_data["modal"] = modal
    data = context.user_data

    keyboard = [
        [InlineKeyboardButton("✅ Simpan", callback_data="simpan"),
         InlineKeyboardButton("❌ Batal", callback_data="batal")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        f"📋 *Konfirmasi Data Barang Masuk*\n\n"
        f"🏪 Cabang: *{data['cabang']}*\n"
        f"📦 Nama Barang: *{data['nama_barang']}*\n"
        f"⭐ Kualitas: *{data['kualitas']}*\n"
        f"🔢 Jumlah: *{data['jumlah']}*\n"
        f"💰 Modal/satuan: *Rp {data['modal']:,}*\n"
        f"💵 Total Modal: *Rp {data['jumlah'] * data['modal']:,}*",
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )
    return KONFIRMASI


async def konfirmasi(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "batal":
        await query.edit_message_text("❌ Input dibatalkan.")
        return ConversationHandler.END

    data = context.user_data
    tanggal = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    nama_user = query.from_user.full_name

    try:
        sheets.tambah_barang_masuk(
            tanggal=tanggal,
            cabang=data["cabang"],
            nama_barang=data["nama_barang"],
            kualitas=data["kualitas"],
            jumlah=data["jumlah"],
            modal=data["modal"],
            input_by=nama_user
        )
        await query.edit_message_text(
            f"✅ *Berhasil disimpan!*\n\n"
            f"📦 {data['nama_barang']} ({data['kualitas']}) — {data['jumlah']} unit\n"
            f"masuk ke *{data['cabang']}* pada {tanggal}",
            parse_mode="Markdown"
        )
    except Exception as e:
        logger.error(f"Error saving to sheet: {e}")
        await query.edit_message_text(
            "❌ Gagal menyimpan data. Coba lagi atau hubungi admin."
        )

    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Dibatalkan. Ketik /start untuk mulai lagi.")
    return ConversationHandler.END


def main():
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        raise ValueError("TELEGRAM_BOT_TOKEN tidak ditemukan di environment variables")

    app = Application.builder().token(token).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            PILIH_AKSI: [CallbackQueryHandler(pilih_aksi)],
            INPUT_NAMA_BARANG: [MessageHandler(filters.TEXT & ~filters.COMMAND, input_nama_barang)],
            INPUT_KUALITAS: [CallbackQueryHandler(input_kualitas, pattern="^kualitas_")],
            INPUT_JUMLAH: [MessageHandler(filters.TEXT & ~filters.COMMAND, input_jumlah)],
            INPUT_MODAL: [MessageHandler(filters.TEXT & ~filters.COMMAND, input_modal)],
            KONFIRMASI: [CallbackQueryHandler(konfirmasi, pattern="^(simpan|batal)$")],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    app.add_handler(conv_handler)

    logger.info("Bot berjalan...")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
