import logging
import asyncio
import json
import os
from aiogram import Bot, Dispatcher, types
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.utils import executor
from datetime import datetime
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO)

BOT_TOKEN = os.getenv("BOT_TOKEN")
SPREADSHEET_ID = os.getenv("SPREADSHEET_ID")
SHEET_NAME = os.getenv("SHEET_NAME", "Лист1")
GOOGLE_CREDS = os.getenv("GOOGLE_CREDS")

bot = Bot(token=BOT_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(bot, storage=storage)


def get_sheet():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    if GOOGLE_CREDS:
        creds_dict = json.loads(GOOGLE_CREDS)
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    else:
        creds = ServiceAccountCredentials.from_json_keyfile_name("credentials.json", scope)
    client = gspread.authorize(creds)
    return client.open_by_key(SPREADSHEET_ID).worksheet(SHEET_NAME)


def append_report(data: dict):
    sheet = get_sheet()
    row = [data["date"], data["event"], data["name_role"], data["start_time"], data["end_time"], ""]
    sheet.append_row(row, value_input_option="USER_ENTERED")


class ReportForm(StatesGroup):
    date = State()
    event = State()
    name_role = State()
    start_time = State()
    end_time = State()
    confirm = State()


@dp.message_handler(commands=["start"])
async def cmd_start(message: types.Message):
    await message.answer("👋 Привет! Я бот для отчётов о работе.\n\nКоманды:\n/report — отправить отчёт о смене\n/help — помощь")


@dp.message_handler(commands=["help"])
async def cmd_help(message: types.Message):
    await message.answer("📋 Как заполнить отчёт:\n\n1. Напиши /report\n2. Отвечай на вопросы бота\n3. Подтверди отчёт — данные уйдут в таблицу\n\nФормат времени: ЧЧ:ММ (например 09:00)\nФормат даты: ДД.ММ.ГГГГ (например 04.05.2026)")


@dp.message_handler(commands=["report"])
async def cmd_report(message: types.Message):
    await ReportForm.date.set()
    today = datetime.now().strftime("%d.%m.%Y")
    await message.answer(f"📅 Введи дату мероприятия:\n(сегодня: {today})\n\nПример: 04.05.2026")


@dp.message_handler(state=ReportForm.date)
async def process_date(message: types.Message, state: FSMContext):
    text = message.text.strip()
    try:
        datetime.strptime(text, "%d.%m.%Y")
    except ValueError:
        await message.answer("❌ Неверный формат. Введи дату так: 04.05.2026")
        return
    await state.update_data(date=text)
    await ReportForm.event.set()
    await message.answer("🎭 Название мероприятия:")


@dp.message_handler(state=ReportForm.event)
async def process_event(message: types.Message, state: FSMContext):
    await state.update_data(event=message.text.strip())
    await ReportForm.name_role.set()
    await message.answer("👤 Твоё имя и должность:\n\nПример: Андрей — постановщик")


@dp.message_handler(state=ReportForm.name_role)
async def process_name_role(message: types.Message, state: FSMContext):
    await state.update_data(name_role=message.text.strip())
    await ReportForm.start_time.set()
    await message.answer("🕐 Время начала работы:\n\nПример: 09:00")


@dp.message_handler(state=ReportForm.start_time)
async def process_start(message: types.Message, state: FSMContext):
    text = message.text.strip()
    try:
        datetime.strptime(text, "%H:%M")
    except ValueError:
        await message.answer("❌ Неверный формат. Введи время так: 09:00")
        return
    await state.update_data(start_time=text)
    await ReportForm.end_time.set()
    await message.answer("🕕 Время окончания работы:\n\nПример: 18:00")


@dp.message_handler(state=ReportForm.end_time)
async def process_end(message: types.Message, state: FSMContext):
    text = message.text.strip()
    try:
        datetime.strptime(text, "%H:%M")
    except ValueError:
        await message.answer("❌ Неверный формат. Введи время так: 18:00")
        return
    await state.update_data(end_time=text)
    data = await state.get_data()
    await ReportForm.confirm.set()
    summary = (f"📋 Проверь отчёт:\n\n📅 Дата: {data['date']}\n🎭 Мероприятие: {data['event']}\n"
               f"👤 Имя / должность: {data['name_role']}\n🕐 Начало: {data['start_time']}\n"
               f"🕕 Конец: {text}\n\nОтправить? Напиши да или нет")
    await message.answer(summary)


@dp.message_handler(state=ReportForm.confirm)
async def process_confirm(message: types.Message, state: FSMContext):
    answer = message.text.strip().lower()
    if answer in ("да", "yes", "d", "y", "+"):
        data = await state.get_data()
        try:
            append_report(data)
            await message.answer("✅ Отчёт записан в таблицу!\n\nСпасибо, данные уже в Google Sheets 📊")
        except Exception as e:
            logging.error(f"Sheets error: {e}")
            await message.answer("⚠️ Ошибка при записи в таблицу. Сообщи руководителю — данные не сохранились.")
        await state.finish()
    elif answer in ("нет", "no", "n", "-"):
        await state.finish()
        await message.answer("❌ Отчёт отменён. Чтобы начать заново — напиши /report")
    else:
        await message.answer("Напиши да или нет")


if __name__ == "__main__":
    executor.start_polling(dp, skip_updates=True)
