import os
import asyncio
import logging
from aiohttp import web
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart, CommandObject
from aiogram.utils.deep_linking import create_start_link
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

# --------------------------------------------------------------------------
# НАСТРОЙКИ
# --------------------------------------------------------------------------
API_TOKEN = '8908828254:AAGKtq5RRkeiTsJbF8bfELld-Zgr5UW3lho'  # Вставьте токен от @BotFather
ADMIN_ID = 1464235091                  # Ваш личный Telegram ID (число)

GOOGLE_FORM_URL = "https://docs.google.com/forms/d/e/1FAIpQLSce-M6e9yasNlKK_riqGXvKdtYufsX0Po4kQCCuvknEqQlOvw/viewform?usp=header"

STARS_PER_REFERRAL = 5    # Награда за 1 друга (Звёзд)
MIN_WITHDRAW_STARS = 30  # Минимальный порог вывода
# --------------------------------------------------------------------------

bot = Bot(token=API_TOKEN)
dp = Dispatcher()

# Временная база данных пользователей
db = {}

def get_or_create_user(user: types.User):
    user_id = user.id
    if user_id not in db:
        db[user_id] = {
            "referrer": None,
            "referrals_count": 0,
            "stars_balance": 0,
            "username": user.username or user.first_name
        }
    else:
        db[user_id]["username"] = user.username or user.first_name
    return db[user_id]

# --------------------------------------------------------------------------
# ЛОГИКА БОТА
# --------------------------------------------------------------------------

@dp.message(CommandStart())
async def start_handler(message: types.Message, command: CommandObject):
    user = message.from_user
    user_data = get_or_create_user(user)
    
    args = command.args
    if args and args.isdigit():
        referrer_id = int(args)
        
        if referrer_id != user.id and user_data["referrer"] is None:
            user_data["referrer"] = referrer_id
            
            if referrer_id in db:
                db[referrer_id]["referrals_count"] += 1
                db[referrer_id]["stars_balance"] += STARS_PER_REFERRAL
                
                try:
                    await bot.send_message(
                        chat_id=referrer_id,
                        text=(
                            f"🎉 **새로운 추천 등록! (Новый реферал!)**\n\n"
                            f"누군가가 당신의 링크로 들어왔습니다!\n"
                            f"보상: **+{STARS_PER_REFERRAL} Stars** 🌟"
                        ),
                        parse_mode="Markdown"
                    )
                except Exception:
                    pass

    ref_link = await create_start_link(bot, str(user.id), encode=False)

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="📝 설문조사 참여하기 (Заполнить форму)", url=GOOGLE_FORM_URL)
            ],
            [
                InlineKeyboardButton(text="🎁 보상 신청하기 (Запросить вывод)", callback_data="request_withdraw")
            ],
            [
                InlineKeyboardButton(text="🔄 내 통계 새로고침 (Обновить)", callback_data="refresh_stats")
            ]
        ]
    )

    welcome_text = (
        f"안녕하세요, {user.first_name}님! 👋\n\n"
        f"📌 **설문조사에 참여하고 친구를 초대해보세요!**\n"
        f"아래 버튼을 눌러 설문조사를 작성하실 수 있습니다.\n\n"
        f"🔗 **당신의 전용 추천 링크 (Ваша реферальная ссылка):**\n"
        f"`{ref_link}`\n\n"
        f"이 링크를 카카오톡, 네이버 블로그, 텔레그램에 공유하세요!\n"
        f"친구 1명 초대당 **{STARS_PER_REFERRAL} Stars** 🌟를 드립니다.\n\n"
        f"📊 **내 통계 (Моя статистика):**\n"
        f"• 초대한 친구: {user_data['referrals_count']}명\n"
        f"• 적립된 스타: {user_data['stars_balance']} 🌟\n"
        f"• 최소 출금 조건: {MIN_WITHDRAW_STARS} Stars 이상"
    )

    await message.answer(welcome_text, parse_mode="Markdown", reply_markup=keyboard)

@dp.callback_query(F.data == "request_withdraw")
async def withdraw_handler(callback: types.CallbackQuery):
    user = callback.from_user
    user_data = get_or_create_user(user)

    if user_data["stars_balance"] < MIN_WITHDRAW_STARS:
        await callback.answer(
            f"❌ 출금 불가! 최소 {MIN_WITHDRAW_STARS} Stars가 필요합니다.",
            show_alert=True
        )
        return

    admin_msg = (
        f"🔔 **НОВАЯ ЗАЯВКА НА ВЫВОД ЗВЁЗД!**\n\n"
        f"👤 Пользователь: @{user_data['username']} (ID: `{user.id}`)\n"
        f"👥 Привёл друзей: {user_data['referrals_count']}\n"
        f"🌟 Запросил Звёзд: {user_data['stars_balance']}"
    )
    
    try:
        await bot.send_message(chat_id=ADMIN_ID, text=admin_msg, parse_mode="Markdown")
        await callback.answer(
            "✅ 신청이 완료되었습니다! 관리자가 확인 후 선물로 스타를 보내드립니다.",
            show_alert=True
        )
    except Exception:
        await callback.answer("Ошибка отправки заявки админу.", show_alert=True)

@dp.callback_query(F.data == "refresh_stats")
async def refresh_stats_handler(callback: types.CallbackQuery):
    user = callback.from_user
    user_data = get_or_create_user(user)
    ref_link = await create_start_link(bot, str(user.id), encode=False)

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="📝 설문조사 참여하기 (Заполнить форму)", url=GOOGLE_FORM_URL)
            ],
            [
                InlineKeyboardButton(text="🎁 보상 신청하기 (Запросить вывод)", callback_data="request_withdraw")
            ],
            [
                InlineKeyboardButton(text="🔄 내 통계 새로고침 (Обновить)", callback_data="refresh_stats")
            ]
        ]
    )

    updated_text = (
        f"안녕하세요, {user.first_name}님! 👋\n\n"
        f"📌 **설문조사에 참여하고 친구를 초대해보세요!**\n"
        f"아래 버튼을 눌러 설문조사를 작성하실 수 있습니다.\n\n"
        f"🔗 **당신의 전용 추천 링크 (Ваша реферальная ссылка):**\n"
        f"`{ref_link}`\n\n"
        f"이 링크를 카카오톡, 네이버 블로그, 텔레그램에 공유하세요!\n"
        f"친구 1명 초대당 **{STARS_PER_REFERRAL} Stars** 🌟를 드립니다.\n\n"
        f"📊 **내 통계 (Моя статистика):**\n"
        f"• 초대한 친구: {user_data['referrals_count']}명\n"
        f"• 적립된 스타: {user_data['stars_balance']} 🌟\n"
        f"• 최소 출금 조건: {MIN_WITHDRAW_STARS} Stars 이상"
    )

    try:
        await callback.message.edit_text(updated_text, parse_mode="Markdown", reply_markup=keyboard)
        await callback.answer("통계가 갱신되었습니다!")
    except Exception:
        await callback.answer()

# --------------------------------------------------------------------------
# ВЕБ-СЕРВЕР ДЛЯ RENDER И ЗАПУСК
# --------------------------------------------------------------------------

async def handle_ping(request):
    return web.Response(text="Bot is running!")

async def start_web_server():
    app = web.Application()
    app.router.add_get('/', handle_ping)
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.environ.get("PORT", 8080))
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()

async def main():
    logging.basicConfig(level=logging.INFO)
    await start_web_server()  # Запуск веб-сервера для Render
    print("Бот и веб-сервер успешно запущены!")
    await dp.start_polling(bot)

if __name__ == '__main__':
    asyncio.run(main())
