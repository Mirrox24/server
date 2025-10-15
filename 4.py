# Telegram Бот "Сберёнок" (aiogram v3+)
# Логика: При первом открытии чата показывается большая кнопка "Начать".

import asyncio
from aiogram import Bot, Dispatcher, types, F
from aiogram.types import WebAppInfo, InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton, \
    MenuButtonDefault, MenuButtonWebApp

# --- НАСТРОЙКА ---
# 1. ЗАМЕНИТЕ ЭТУ ССЫЛКУ на вашу РЕАЛЬНУЮ HTTPS-ссылку с GitHub Pages!
YOUR_PWA_URL = "https://mirrox24.github.io/-/"
# 2. Ваш токен от BotFather
BOT_TOKEN = "8412698561:AAHqZJSRMjDv8QEx6_GNEgxW4bspOtniiIg"
# -----------------

# Инициализация
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()


def get_main_menu_keyboard(url: str) -> ReplyKeyboardMarkup:
    """Создает постоянную кнопку 'Открыть Сберёнок PWA'."""
    web_app_info = WebAppInfo(url=url)

    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🚀 Открыть Сберёнок PWA", web_app=web_app_info)]
        ],
        resize_keyboard=True,
        one_time_keyboard=False
    )
    return keyboard


def get_start_button_keyboard() -> ReplyKeyboardMarkup:
    """Создает большую кнопку 'Начать работу' для первого взаимодействия."""
    # При нажатии на эту кнопку, она отправляет команду '/start'
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="✨ Начать работу со Сберёнком")]
        ],
        resize_keyboard=True,
        one_time_keyboard=True  # Исчезает после первого нажатия
    )
    return keyboard


@dp.message(F.text == "✨ Начать работу со Сберёнком")
@dp.message(F.text.startswith('/start') | F.text.startswith('/help'))
async def send_welcome(message: types.Message):
    """
    Обработка команды /start и нажатия кнопки "Начать работу".
    Устанавливает постоянную кнопку Web App.
    """

    # 1. Получаем клавиатуру с кнопкой Web App
    web_app_keyboard = get_main_menu_keyboard(YOUR_PWA_URL)

    welcome_text = (
        f"👋 Привет, {message.from_user.first_name}! Я Сберёнок, твой личный финансовый помощник. "
        "Нажми на кнопку 'Открыть Сберёнок PWA' ниже, чтобы запустить приложение!"
    )

    # 2. Отправляем приветствие и устанавливаем постоянную клавиатуру с Web App
    await message.answer(
        welcome_text,
        reply_markup=web_app_keyboard
    )


@dp.message(F.content_type.in_({'new_chat_members'}))
async def handle_new_member(message: types.Message):
    """
    Обрабатывает, когда пользователь впервые открывает чат.
    Сразу показывает большую кнопку "Начать работу".
    """
    if message.new_chat_members and message.new_chat_members[0].id == bot.id:
        return  # Если бота добавили в группу, игнорируем

    start_keyboard = get_start_button_keyboard()
    await message.answer(
        "Добро пожаловать! Я Сберёнок. Нажмите кнопку, чтобы начать:",
        reply_markup=start_keyboard
    )


async def main():
    print("Бот Сберёнок запущен и готов к работе!")
    await bot.delete_webhook(drop_pending_updates=True)

    # 1. УБИРАЕМ КНОПКУ МЕНЮ СЛЕВА!
    # Устанавливаем стандартное меню (без Web App)
    await bot.set_chat_menu_button(menu_button=MenuButtonDefault())

    # 2. Отправляем приветственное сообщение (для новых пользователей, если бот не отвечает сам)
    # При первом обращении пользователя, Telegram часто автоматически отправляет сообщение,
    # чтобы триггернуть 'handle_new_member' или просто пользователь нажмет /start.

    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())