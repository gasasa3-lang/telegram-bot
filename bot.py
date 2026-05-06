import json
import logging
import asyncio
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from datetime import datetime
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import os
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO)

BOT_TOKEN = os.getenv("BOT_TOKEN")
SPREADSHEET_ID = os.getenv("SPREADSHEET_ID")
SHEET_NAME = os.getenv("SHEET_NAME", "Лист1")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())


# ─── Google Sheets ───────────────────────────────────────────────────────────

def get_sheet():
    scope = [
        "https://spreadsheets.google.com/feeds",
        "https://www.googleapis.com/auth/drive",
    ]
    GOOGLE_CREDS = os.getenv("GOOGLE_CREDS")
    if GOOGLE_CREDS:
        creds = ServiceAccountCredentials.from_json_keyfile_dict(json.loads(GOOGLE_CREDS), scope)
    else:
        creds = ServiceAccountCredentials.from_json_keyfile_name("credentials.json", scope)
    client = gspread.authorize(creds)
    return client.open_by_key(SPREADSHEET_ID).worksheet(SHEET_NAME)


def append_report(data: dict):
    """Добавляет строку отчёта в Google Sheets."""
    sheet = get_sheet()
    row = [
        data["date"],           # A — дата
        data["event"],          # B — мероприятие
        data["name_role"],      # C — имя + должность
        data["start_time"],     # D — начало
        data["end_time"],       # E — конец
        "",                     # F — формула считает сама
    ]
    sheet.append_row(row, value_input_option="USER_ENTERED")


# ─── FSM состояния ────────────────────────────────────────────────────────────

class ReportForm(StatesGroup):
    date = State()
    event = State()
    name_role = State()
    start_time = State()
    end_time = State()
    confirm = State()


# ─── Хэндлеры ────────────────────────────────────────────────────────────────

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer(
        "👋 Привет! Я бот для отчётов о работе.\n\n"
        "Команды:\n"
        "/report — отправить отчёт о смене\n"
        "/help — помощь"
    )


@dp.message(Command("help"))
async def cmd_help(message: types.Message):
    await message.answer(
        "📋 Как заполнить отчёт:\n\n"
        "1. Напиши /report\n"
        "2. Отвечай на вопросы бота\n"
        "3. Подтверди отчёт — данные уйдут в таблицу\n\n"
        "Формат времени: ЧЧ:ММ (например 09:00)\n"
        "Формат даты: ДД.ММ.ГГГГ (например 04.05.2026)"
    )


@dp.message(Command("report"))
async def cmd_report(message: types.Message, state: FSMContext):
    today = datetime.now().strftime("%d.%m.%Y")
    await state.set_state(ReportForm.date)
    await message.answer(
        f"📅 Введи дату мероприятия:\n(сегодня: {today})\n\nПример: 04.05.2026"
    )


@dp.message(ReportForm.date)
async def process_date(message: types.Message, state: FSMContext):
    text = message.text.strip()
    # Валидация формата даты
    try:
        datetime.strptime(text, "%d.%m.%Y")
    except ValueError:
        await message.answer("❌ Неверный формат. Введи дату так: 04.05.2026")
        return
    await state.update_data(date=text)
    await state.set_state(ReportForm.event)
    await message.answer("🎭 Название мероприятия:")


@dp.message(ReportForm.event)
async def process_event(message: types.Message, state: FSMContext):
    await state.update_data(event=message.text.strip())
    await state.set_state(ReportForm.name_role)
    await message.answer(
        "👤 Твоё имя и должность:\n\nПример: Андрей — постановщик"
    )


@dp.message(ReportForm.name_role)
async def process_name_role(message: types.Message, state: FSMContext):
    await state.update_data(name_role=message.text.strip())
    await state.set_state(ReportForm.start_time)
    await message.answer("🕐 Время начала работы:\n\nПример: 09:00")


@dp.message(ReportForm.start_time)
async def process_start(message: types.Message, state: FSMContext):
    text = message.text.strip()
    try:
        datetime.strptime(text, "%H:%M")
    except ValueError:
        await message.answer("❌ Неверный формат. Введи время так: 09:00")
        return
    await state.update_data(start_time=text)
    await state.set_state(ReportForm.end_time)
    await message.answer("🕕 Время окончания работы:\n\nПример: 18:00")


@dp.message(ReportForm.end_time)
async def process_end(message: types.Message, state: FSMContext):
    text = message.text.strip()
    try:
        datetime.strptime(text, "%H:%M")
    except ValueError:
        await message.answer("❌ Неверный формат. Введи время так: 18:00")
        return
    await state.update_data(end_time=text)

    data = await state.get_data()
    await state.set_state(ReportForm.confirm)

    summary = (
        f"📋 Проверь отчёт:\n\n"
        f"📅 Дата: {data['date']}\n"
        f"🎭 Мероприятие: {data['event']}\n"
        f"👤 Имя / должность: {data['name_role']}\n"
        f"🕐 Начало: {data['start_time']}\n"
        f"🕕 Конец: {text}\n\n"
        f"Отправить? Напиши да или нет"
    )
    await message.answer(summary)


@dp.message(ReportForm.confirm)
async def process_confirm(message: types.Message, state: FSMContext):
    answer = message.text.strip().lower()

    if answer in ("да", "yes", "d", "y", "+"):
        data = await state.get_data()
        try:
            append_report(data)
            await message.answer(
                "✅ Отчёт записан в таблицу!\n\n"
                "Спасибо, данные уже в Google Sheets 📊"
            )
        except Exception as e:
            logging.error(f"Sheets error: {e}")
            await message.answer(
                "⚠️ Ошибка при записи в таблицу. "
                "Сообщи руководителю — данные не сохранились."
            )
        await state.clear()

    elif answer in ("нет", "no", "n", "-"):
        await state.clear()
        await message.answer(
            "❌ Отчёт отменён. Чтобы начать заново — напиши /report"
        )
    else:
        await message.answer("Напиши да или нет")


# ─── Запуск ───────────────────────────────────────────────────────────────────

async def main():
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
