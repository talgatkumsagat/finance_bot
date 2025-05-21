import matplotlib.pyplot as plt
import csv
from io import BytesIO
from datetime import datetime, timedelta
from db import add_transaction, get_summary_by_category, export_all_transactions
from config import BOT_TOKEN

from telegram import (
    Update, ReplyKeyboardMarkup, InlineKeyboardButton,
    InlineKeyboardMarkup, InputFile
)
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    CallbackQueryHandler, ContextTypes, filters
)
import sqlite3

# Главное меню
MAIN_MENU = [["💰 Доход", "💸 Расход"], ["📊 Статистика", "🗑 Сброс"]]

income_categories = ["Работа", "Фриланс", "Премия", "Другое"]
expense_categories = ["Магазин", "Метро", "Кафе", "Кредит", "Другое"]

user_state = {}

period_options = {
    "📅 Сегодня": 1,
    "🗓 Неделя": 7,
    "📆 Месяц": 30,
    "📈 3 месяца": 90,
    "🪙 6 месяцев": 180,
    "📅 Год": 365
}

# Подключение к базе
conn = sqlite3.connect("finance.db", check_same_thread=False)
cursor = conn.cursor()

# /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Привет! Выбери действие:",
        reply_markup=ReplyKeyboardMarkup(MAIN_MENU, resize_keyboard=True)
    )

# Обработка всех текстов
async def handle_all_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    user_id = update.effective_user.id

    if user_id in user_state and "category" in user_state[user_id]:
        try:
            amount = float(text)
            t = user_state[user_id]
            add_transaction(user_id, t["type"], t["category"], amount)
            type_label = "Доход" if t["type"] == "income" else "Расход"
            now = datetime.now().strftime("%d.%m.%Y %H:%M")

            await update.message.reply_text(
                f"✅ Запись добавлена!\n"
                f"{type_label}: {amount}₸\n"
                f"Категория: {t['category']}\n"
                f"🕒 {now}",
                reply_markup=ReplyKeyboardMarkup(MAIN_MENU, resize_keyboard=True)
            )
        except ValueError:
            await update.message.reply_text("❗ Введите сумму числом.")
        user_state.pop(user_id, None)
        return

    if text == "💰 Доход":
        user_state[user_id] = {"type": "income"}
        await update.message.reply_text(
            "Выберите категорию дохода:",
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton(cat, callback_data=cat)] for cat in income_categories]
            )
        )
    elif text == "💸 Расход":
        user_state[user_id] = {"type": "expense"}
        await update.message.reply_text(
            "Выберите категорию расхода:",
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton(cat, callback_data=cat)] for cat in expense_categories]
            )
        )
    elif text == "📊 Статистика":
        keyboard = [[InlineKeyboardButton(label, callback_data=f"period:{days}")]
                    for label, days in period_options.items()]
        await update.message.reply_text("Выберите период:", reply_markup=InlineKeyboardMarkup(keyboard))

    elif text == "🗑 Сброс":
        await update.message.reply_text(
            "⚠️ Вы уверены, что хотите удалить все свои данные?",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("✅ Подтвердить сброс", callback_data="confirm_reset")],
                [InlineKeyboardButton("❌ Отмена", callback_data="cancel_reset")]
            ])
        )

# Подтверждение сброса
async def handle_reset_confirmation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    if query.data == "confirm_reset":
        cursor.execute("DELETE FROM transactions WHERE user_id = ?", (user_id,))
        conn.commit()
        await query.message.reply_text("✅ Все ваши данные были удалены.", reply_markup=ReplyKeyboardMarkup(MAIN_MENU, resize_keyboard=True))
    else:
        await query.message.reply_text("❌ Сброс отменён.", reply_markup=ReplyKeyboardMarkup(MAIN_MENU, resize_keyboard=True))

# Выбор категории
async def handle_category_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    category = query.data
    user_id = query.from_user.id
    user_state[user_id]["category"] = category
    await query.message.reply_text("Введите сумму:")

# Обработка периода статистики
async def handle_period_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    _, days = query.data.split(":")
    days = int(days)

    msg = await context.bot.send_message(chat_id=user_id, text="⏳ Построение диаграммы…")

    income_data = get_summary_by_category(user_id, days, "income")
    expense_data = get_summary_by_category(user_id, days, "expense")

    total_income = sum(income_data.values())
    total_expense = sum(expense_data.values())
    balance = total_income - total_expense

    await query.message.reply_text(
        f"📊 Период: {days} дней\n"
        f"Доход: {total_income}₸\n"
        f"Расход: {total_expense}₸\n"
        f"Баланс: {balance}₸"
    )

    if expense_data:
        img = generate_pie_chart(expense_data, "Расходы по категориям")
        await context.bot.send_photo(chat_id=user_id, photo=img)

    if income_data:
        img = generate_pie_chart(income_data, "Доходы по категориям")
        await context.bot.send_photo(chat_id=user_id, photo=img)

    await msg.delete()

# Экспорт CSV
async def export_csv(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    data = export_all_transactions(user_id)

    if not data:
        await update.message.reply_text("Нет данных для экспорта.")
        return

    buf = BytesIO()
    writer = csv.writer(buf)
    writer.writerow(["Дата", "Тип", "Категория", "Сумма"])
    writer.writerows(data)
    buf.seek(0)

    await update.message.reply_document(
        document=InputFile(buf, filename="finance_export.csv"),
        caption="📄 Все транзакции"
    )

# Построение круговой диаграммы
def generate_pie_chart(data: dict, title: str) -> InputFile:
    fig, ax = plt.subplots()
    total = sum(data.values())

    labels = [f"{cat}\n{amt:.0f}₸ ({amt / total:.1%})" for cat, amt in data.items()]
    ax.pie(data.values(), labels=labels, startangle=90)
    ax.axis("equal")
    plt.title(title)

    buf = BytesIO()
    plt.savefig(buf, format="png", bbox_inches="tight")
    buf.seek(0)
    plt.close()
    return InputFile(buf, filename="chart.png")

# Регистрация хендлеров
app = ApplicationBuilder().token(BOT_TOKEN).build()
app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("export", export_csv))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_all_text))
app.add_handler(CallbackQueryHandler(handle_category_selection, pattern="^(?!period:|confirm_reset|cancel_reset).*"))
app.add_handler(CallbackQueryHandler(handle_period_selection, pattern="^period:"))
app.add_handler(CallbackQueryHandler(handle_reset_confirmation, pattern="^(confirm_reset|cancel_reset)$"))

if __name__ == "__main__":
    app.run_polling()
