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
API_TOKEN = 'ВАШ_TELEGRAM_BOT_TOKEN'  # Вставьте токен от @BotFather
ADMIN_ID = 123456789                  # Ваш личный Telegram ID (число)

GOOGLE_FORM_URL = "https://docs.google.com/forms/d/e/1FAIpQLSce-M6e9yasNlKK_riqGXvKdtYufsX0Po4kQCCuvknEqQlOvw/viewform?usp=header"

STARS_PER_REFERRAL = 5    # Награда за 1 друга (Звёзд)
MIN_WITHDRAW_STARS = 30  # Минимальный порог вывода (Звёзд)
# --------------------------------------------------------------------------

bot = Bot(token=API_TOKEN)
dp = Dispatcher()

# Временная база данных пользователей
# user_id: {"referrer": int, "referrals_count": int, "stars_balance": int, "username": str, "lang": str}
db = {}

# --------------------------------------------------------------------------
# ТЕКСТЫ НА 3 ЯЗЫКАХ (KR, EN, RU)
# --------------------------------------------------------------------------
TEXTS = {
    "kr": {
        "welcome": (
            "안녕하세요, {name}님! 👋\n\n"
            "📌 **설문조사에 참여하고 친구를 초대해보세요!**\n"
            "아래 버튼을 눌러 설문조사를 작성하실 수 있습니다.\n\n"
            "🔗 **당신의 전용 추천 링크:**\n"
            "`{ref_link}`\n\n"
            "이 링크를 카카오톡, 네이버 블로그, 텔레그램에 공유하세요!\n"
            "친구 1명 초대당 **{stars} Stars** 🌟를 드립니다.\n\n"
            "📊 **내 통계:**\n"
            "• 초대한 친구: {count}명\n"
            "• 적립된 스타: {balance} 🌟\n"
            "• 최소 출금 조건: {min_stars} Stars 이상"
        ),
        "btn_form": "📝 설문조사 참여하기",
        "btn_withdraw": "🎁 보상 신청하기",
        "btn_refresh": "🔄 내 통계 새로고침",
        "btn_lang": "🌐 언어 변경 / Change Language",
        "notify_ref": "🎉 **새로운 추천 등록!**\n\n누군가가 당신의 링크로 들어왔습니다!\n보상: **+{stars} Stars** 🌟",
        "withdraw_low": "❌ 출금 불가! 최소 {min_stars} Stars가 필요합니다.",
        "withdraw_ok": "✅ 신청이 완료되었습니다! 관리자가 확인 후 선물로 스타를 보내드립니다.",
        "refreshed": "통계가 갱신되었습니다!",
        "select_lang": "🌐 **언어를 선택해주세요 / Please select your language:**"
    },
    "en": {
        "welcome": (
            "Hello, {name}! 👋\n\n"
            "📌 **Take the survey and invite your friends!**\n"
            "Click the button below to complete the survey.\n\n"
            "🔗 **Your Referral Link:**\n"
            "`{ref_link}`\n\n"
            "Share this link anywhere (Telegram, KakaoTalk, Socials)!\n"
            "Earn **{stars} Stars** 🌟 for each invited friend.\n\n"
            "📊 **My Statistics:**\n"
            "• Invited Friends: {count}\n"
            "• Accumulated Stars: {balance} 🌟\n"
            "• Minimum Payout: {min_stars} Stars"
        ),
        "btn_form": "📝 Take Survey",
        "btn_withdraw": "🎁 Claim Reward",
        "btn_refresh": "🔄 Refresh Stats",
        "btn_lang": "🌐 Change Language",
        "notify_ref": "🎉 **New Referral!**\n\nSomeone joined using your link!\nReward: **+{stars} Stars** 🌟",
        "withdraw_low": "❌ Cannot withdraw! You need at least {min_stars} Stars.",
        "withdraw_ok": "✅ Request submitted! The admin will review and send your gift.",
        "refreshed": "Statistics updated!",
        "select_lang": "🌐 **Please select your language:**"
    },
    "ru": {
        "welcome": (
            "Здравствуйте, {name}! 👋\n\n"
            "📌 **Пройдите опрос и приглашайте друзей!**\n"
            "Нажмите кнопку ниже, чтобы заполнить форму.\n\n"
            "🔗 **Ваша реферальная ссылка:**\n"
            "`{ref_link}`\n\n"
            "Делитесь этой ссылкой в соцсетях и мессенджерах!\n"
            "За каждого друга вы получаете **{stars} Stars** 🌟.\n\n"
            "📊 **Ваша статистика:**\n"
            "• Приглашено друзей: {count}\n"
            "• Накоплено Звёзд: {balance} 🌟\n"
            "• Минимум для вывода: {min_stars} Stars"
        ),
        "btn_form": "📝 Заполнить форму",
        "btn_withdraw": "🎁 Запросить вывод",
        "btn_refresh": "🔄 Обновить статистику",
        "btn_lang": "🌐 Сменить язык",
        "notify_ref": "🎉 **Новый реферал!**\n\nКто-то перешёл по вашей ссылке!\nНаграда: **+{stars} Stars** 🌟",
        "withdraw_low": "❌ Вывод недоступен! Нужно минимум {min_stars} Stars.",
        "withdraw_ok": "✅ Заявка отправлена! Администратор проверит и пришлёт подарок.",
        "refreshed": "Статистика обновлена!",
        "select_lang": "🌐 **Выберите язык / Please select language:**"
    }
}

def get_or_create_user(user: types.User):
    user_id = user.id
    if user_id not in db:
        db[user_id] = {
            "referrer": None,
            "referrals_count": 0,
            "stars_balance": 0,
            "username": user.username or user.first_name,
            "lang": None  # Язык пока не выбран
        }
    else:
        db[user_id]["username"] = user.username or user.first_name
    return db[user_id]

def get_main_keyboard(lang: str) -> InlineKeyboardMarkup:
    t = TEXTS[lang]
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=t["btn_form"], url=GOOGLE_FORM_URL)],
            [InlineKeyboardButton(text=t["btn_withdraw"], callback_data="request_withdraw")],
            [InlineKeyboardButton(text=t["btn_refresh"], callback_data="refresh_stats")],
            [InlineKeyboardButton(text=t["btn_lang"], callback_data="open_lang_menu")]
        ]
    )

def get_lang_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🇰🇷 한국어", callback_data="set_lang_kr")],
            [InlineKeyboardButton(text="🇺🇸 English", callback_data="set_lang_en")],
            [InlineKeyboardButton(text="🇷🇺 Русский", callback_data="set_lang_ru")]
        ]
    )

# --------------------------------------------------------------------------
# ЛОГИКА БОТА
# --------------------------------------------------------------------------

@dp.message(CommandStart())
async def start_handler(message: types.Message, command: CommandObject):
    user = message.from_user
    user_data = get_or_create_user(user)
    
    # Обработка реферального перехода
    args = command.args
    if args and args.isdigit():
        referrer_id = int(args)
        if referrer_id != user.id and user_data["referrer"] is None:
            user_data["referrer"] = referrer_id
            
            if referrer_id in db:
                db[referrer_id]["referrals_count"] += 1
                db[referrer_id]["stars_balance"] += STARS_PER_REFERRAL
                
                ref_lang = db[referrer_id]["lang"] or "kr"
                try:
                    await bot.send_message(
                        chat_id=referrer_id,
                        text=TEXTS[ref_lang]["notify_ref"].format(stars=STARS_PER_REFERRAL),
                        parse_mode="Markdown"
                    )
                except Exception:
                    pass

    # Если язык ещё не выбран — показываем меню выбора
    if user_data["lang"] is None:
        await message.answer(
            "🌐 **언어를 선택해주세요 / Choose your language:**",
            reply_markup=get_lang_keyboard(),
            parse_mode="Markdown"
        )
    else:
        await send_main_menu(message.chat.id, user, user_data)

async def send_main_menu(chat_id: int, user: types.User, user_data: dict):
    lang = user_data["lang"] or "kr"
    t = TEXTS[lang]
    ref_link = await create_start_link(bot, str(user.id), encode=False)

    text = t["welcome"].format(
        name=user.first_name,
        ref_link=ref_link,
        stars=STARS_PER_REFERRAL,
        count=user_data['referrals_count'],
        balance=user_data['stars_balance'],
        min_stars=MIN_WITHDRAW_STARS
    )

    await bot.send_message(chat_id=chat_id, text=text, parse_mode="Markdown", reply_markup=get_main_keyboard(lang))

# Обработка выбора языка
@dp.callback_query(F.data.startswith("set_lang_"))
async def set_language_handler(callback: types.CallbackQuery):
    user = callback.from_user
    user_data = get_or_create_user(user)
    
    selected_lang = callback.data.split("_")[-1]  # kr, en, ru
    user_data["lang"] = selected_lang
    
    await callback.answer()
    try:
        await callback.message.delete()
    except Exception:
        pass

    await send_main_menu(callback.message.chat.id, user, user_data)

# Кнопка смены языка из главного меню
@dp.callback_query(F.data == "open_lang_menu")
async def open_lang_menu_handler(callback: types.CallbackQuery):
    await callback.message.edit_text(
        "🌐 **언어를 선택해주세요 / Choose your language:**",
        reply_markup=get_lang_keyboard(),
        parse_mode="Markdown"
    )

# Запрос вывода средств
@dp.callback_query(F.data == "request_withdraw")
async def withdraw_handler(callback: types.CallbackQuery):
    user = callback.from_user
    user_data = get_or_create_user(user)
    lang = user_data["lang"] or "kr"
    t = TEXTS[lang]

    if user_data["stars_balance"] < MIN_WITHDRAW_STARS:
        await callback.answer(t["withdraw_low"].format(min_stars=MIN_WITHDRAW_STARS), show_alert=True)
        return

    admin_msg = (
        f"🔔 **НОВАЯ ЗАЯВКА НА ВЫВОД ЗВЁЗД!**\n\n"
        f"👤 Пользователь: @{user_data['username']} (ID: `{user.id}`)\n"
        f"🌐 Язык пользователя: {lang.upper()}\n"
        f"👥 Привёл друзей: {user_data['referrals_count']}\n"
        f"🌟 Запросил Звёзд: {user_data['stars_balance']}"
    )
    
    try:
        await bot.send_message(chat_id=ADMIN_ID, text=admin_msg, parse_mode="Markdown")
        await callback.answer(t["withdraw_ok"], show_alert=True)
    except Exception:
        await callback.answer("Error sending request to Admin.", show_alert=True)

# Обновление статистики
@dp.callback_query(F.data == "refresh_stats")
async def refresh_stats_handler(callback: types.CallbackQuery):
    user = callback.from_user
    user_data = get_or_create_user(user)
    lang = user_data["lang"] or "kr"
    t = TEXTS[lang]

    ref_link = await create_start_link(bot, str(user.id), encode=False)

    text = t["welcome"].format(
        name=user.first_name,
        ref_link=ref_link,
        stars=STARS_PER_REFERRAL,
        count=user_data['referrals_count'],
        balance=user_data['stars_balance'],
        min_stars=MIN_WITHDRAW_STARS
    )

    try:
        await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=get_main_keyboard(lang))
        await callback.answer(t["refreshed"])
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
    await start_web_server()
    print("Мультиязычный бот и веб-сервер успешно запущены!")
    await dp.start_polling(bot)

if __name__ == '__main__':
    asyncio.run(main())
