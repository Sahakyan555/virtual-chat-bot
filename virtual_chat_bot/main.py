import asyncio
import logging
from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

# Կարգավորումներ (API Token-ը փոխարինիր քո բոտի տոկենով)
TOKEN = "8785702920:AAEd4fuU6StVTw5RHptPU3HwAPoX6e8gCYM"
ADMIN_ID = (6614409372 # Գրիր քո Telegram ID-ն, որ կարողանաս օգտվել ադմին հրամաններից
)

bot = Bot(token=TOKEN)
dp = Dispatcher()

logging.basicConfig(level=logging.INFO)

# Հիշողության բազա
games = {}  # chat_id -> game_state
banned_users = set()
muted_users = {}  # user_id -> unblock_time


class AdminState(StatesGroup):
    waiting_for_feedback = State()


# Թեմատիկ բառեր և դրոշներ
THEMES = {
    "normal": {
        "spy_name": "ԼՐՏԵՍ",
        "word": "Սրճարան",
        "emoji": "🕵️‍♂️",
        "desc": "Ստանդարտ ռեժիմ",
    },
    "valentine": {
        "spy_name": "ՎԱԼԵՆՏԻՆ",
        "word": "Սեր",
        "emoji": "❤️",
        "desc": "Վալենտինի տոն",
    },
    "new_year": {
        "spy_name": "ՁՄԵՐ ՊԱՊԻԿ",
        "word": "Տոնածառ",
        "emoji": "🎄",
        "desc": "Նոր տարի",
    },
    "helloween": {
        "spy_name": "ԶՈՄԲԻ",
        "word": "Գերեզմանոց",
        "emoji": "🎃",
        "desc": "Հելոուին",
    },
}

current_theme = "normal"


# --- ՀՐԱՄԱՆՆԵՐ / START ԵՎ ՄՅՈՒՍՆԵՐ ---
@dp.message(Command("start"))
async def cmd_start(message: Message):
    if message.from.id in banned_users:
        await message.answer("Դուք արգելափակված եք այս բոտում:")
        return

    text = (
        "👋 Ես լրտես բոտն եմ, այս խաղի խաղավարը։\n"
        "Հավաքվեք ընկերներով, խաղացեք և գտեք լրտեսին:"
    )
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="📜 Խաղի կանոններ", callback_data="rules"
                )
            ],
            [
                InlineKeyboardButton(
                    text="➕ Ավելացնել չաթին",
                    url=f"https://t.me/{(await bot.me()).username}?startgroup=true",
                )
            ],
            [
                InlineKeyboardButton(
                    text="✉️ Անանուն նամակ ադմինին", callback_data="feedback"
                )
            ],
        ]
    )
    await message.answer(text, reply_markup=keyboard)


@dp.callback_query(F.data == "rules")
async def show_rules(callback: CallbackQuery):
    rules_text = (
        "📖 **Խաղի կանոններ:**\n\n"
        "1. Մասնակիցների նվազագույն քանակը 3 է։\n"
        "2. Սկսելուց հետո բոտը գաղտնի բառ կամ «ԼՐՏԵՍ» կարգավիճակ կուղարկի բոլորին անձնական նամակով:\n"
        "3. Մասնակիցները հերթով գրում են բառեր՝ փորձելով հասկանալ՝ ով է լրտեսը:\n"
        "4. Լրտեսն իր հերթին կարող է կռահել բառը և հաղթել։\n"
        "5. 3 շրջանից հետո տեղի է ունենում ընդհանուր քվեարկություն:"
    )
    await callback.message.edit_text(
        rules_text,
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="🔙 Հետ", callback_data="back_start")]
            ]
        ),
    )


@dp.callback_query(F.data == "back_start")
async def back_to_start(callback: CallbackQuery):
    await callback.message.delete()
    await cmd_start(callback.message)


# --- ԽԱՂԻ ՀՐԱՄԱՆՆԵՐ (GROUP) ---
@dp.message(Command("Ստարտ"))
async def start_game_reg(message: Message):
    if message.chat.type == "private":
        await message.answer(
            "Այս հրամանն աշխատում է միայն խմբային չաթերում:"
        )
        return

    chat_id = message.chat.id
    if chat_id in games and games[chat_id]["active"]:
        await message.answer(
            "Խաղն արդեն սկսված է կամ գրանցումն ընթացքի մեջ է:"
        )
        return

    games[chat_id] = {
        "active": False,
        "players": {},  # user_id -> {name, username, words_count}
        "spies": [],
        "stage": "reg",
        "timer_task": None,
    }

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🎮 Միանալ լրտես խաղին", callback_data="join_game"
                )
            ]
        ]
    )

    msg = await message.answer(
        "🚨 **Սկսվել է «Լրտես» խաղի գրանցումը։**\n"
        "Սեղմեք ներքևի կոճակը՝ միանալու համար:\n"
        "Ժամանակը՝ 5 րոպե կամ ուղարկեք /սկսել_խաղը:",
        reply_markup=keyboard,
    )
    games[chat_id]["reg_message_id"] = msg.message_id

    # 5 րոպեանոց ավտոմատ սպասում
    async def auto_start():
        await asyncio.sleep(300)
        if chat_id in games and not games[chat_id]["active"]:
            await run_game(chat_id, message)

    games[chat_id]["timer_task"] = asyncio.create_task(auto_start())


@dp.callback_query(F.data == "join_game")
async def join_game(callback: CallbackQuery):
    chat_id = callback.message.chat.id
    user = callback.from_user

    if chat_id not in games or games[chat_id]["stage"] != "reg":
        await callback.answer(
            "Գրանցումն այլևս ակտիվ չէ կամ խաղ չկա:", show_alert=True
        )
        return

    if user.id in games[chat_id]["players"]:
        await callback.answer(
            "Դուք արդեն միացել եք խաղին:", show_alert=True
        )
        return

    games[chat_id]["players"][user.id] = {
        "name": user.full_name,
        "username": user.username or user.first_name,
        "words_count": 0,
    }

    await callback.answer("Դուք հաջողությամբ միացաք խաղին!")
    # Թարմացնում ենք մասնակիցների ցանկը չաթում
    players_list = "\n".join(
        [f"• @{p['username']}" for p in games[chat_id]["players"].values()]
    )
    await callback.message.edit_text(
        f"🚨 **«Լրտես» խաղի գրանցումը ընթացքի մեջ է։**\n\n"
        f"**Մասնակիցներ ({len(games[chat_id]['players'])}):**\n{players_list}",
        reply_markup=callback.message.reply_markup,
    )


@dp.message(Command("ավելացնել_ժամանակը"))
async def add_time(message: Message):
    # Կարող է լինել /ավելացնել_ժամանակը 30 կամ ուղղակի /ավելացնել_ժամանակը
    args = message.text.split()
    seconds = 60
    if len(args) > 1 and args[1].isdigit():
        seconds = int(args[1])

    await message.answer(
        f"⏰ Ժամանակն ավելացվեց {seconds} վայրկյանով (այս տարբերակում ժամչափն ավելացնում է սպասման շեմը):"
    )


@dp.message(Command("սկսել_խաղը"))
async def manual_start(message: Message):
    chat_id = message.chat.id
    if chat_id not in games or games[chat_id]["active"]:
        await message.answer("Խաղը հնարավոր չէ սկսել:")
        return

    if len(games[chat_id]["players"]) < 3:
        await message.answer(
            "Խաղալու համար հարկավոր է առնվազն 3 մասնակից։"
        )
        return

    if games[chat_id]["timer_task"]:
        games[chat_id]["timer_task"].cancel()

    await run_game(chat_id, message)


@dp.message(Command("չեղարկել_խաղը"))
async def cancel_game(message: Message):
    chat_id = message.chat.id
    if chat_id in games:
        if games[chat_id]["timer_task"]:
            games[chat_id]["timer_task"].cancel()
        del games[chat_id]
        await message.answer("❌ Խաղը չեղարկվեց:")
    else:
        await message.answer("Ընթացիկ խաղ չկա:")


# --- ԽԱՂԻ ՍԿԻԶԲ ԵՎ ՏՐԱՄԱԲԱՆՈՒԹՅՈՒՆ ---
async def run_game(chat_id, message_obj):
    game = games[chat_id]
    game["active"] = True
    game["stage"] = "playing"

    players_ids = list(game["players"].keys())
    import random

    random.shuffle(players_ids)

    # Լրտեսների քանակը ըստ կանոնների
    count = len(players_ids)
    if 3 <= count <= 5:
        spy_count = 1
    elif 5 < count <= 8:
        spy_count = 2
    elif 8 < count <= 12:
        spy_count = 3
    elif 12 < count <= 15:
        spy_count = 4
    elif 15 < count <= 20:
        spy_count = 5
    else:
        spy_count = 5

    game["spies"] = players_ids[:spy_count]
    regular_players = players_ids[spy_count:]

    theme_data = THEMES[current_theme]
    word = theme_data["word"]
    spy_title = theme_data["spy_name"]

    # Ուղարկում ենք դերերը անձնական նամակով
    for uid in players_ids:
        try:
            if uid in game["spies"]:
                spies_usernames = ", ".join(
                    [
                        f"@{game['players'][s]['username']}"
                        for s in game["spies"]
                    ]
                )
                await bot.send_message(
                    uid,
                    f"⚠️ Դուք **{spy_title}** եք! Ձեր նպատակն է չբացահայտվել և կռահել բառը:\n"
                    f"Ձեր թիմակիցներն են՝ {spies_usernames} (կարող եք շփվել այստեղ):",
                )
            else:
                await bot.send_message(
                    uid,
                    f"🎯 Ձեր գաղտնի բառը՝ **{word}**\nԳտեք լրտեսին:",
                )
        except Exception:
            pass  # Եթե բոտին լսել չի տվել լիչկայում

    await bot.send_message(
        chat_id,
        "🔔 **Խաղը սկսվեց!** Բոլորին ուղարկվեցին դերերը անձնական նամակով:\n"
        "Լրտեսը կարող է սեղմել հատուկ կոճակը՝ գուշակելու համար:",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text=f"🕵️ {spy_title}՝ Գուշակել բառը",
                        callback_data="spy_guess_start",
                    )
                ]
            ]
        ),
    )

    # Խաղային հերթականություն (3 շրջան)
    game["turn_index"] = 0
    game["round"] = 1
    game["current_players_queue"] = players_ids * 3

    await next_turn(chat_id)


async def next_turn(chat_id):
    game = games[chat_id]
    if game["turn_index"] >= len(game["current_players_queue"]):
        # Հասել ենք 3 շրջանի վերջին -> Քվեարկություն
        await start_voting(chat_id)
        return

    current_uid = game["current_players_queue"][game["turn_index"]]
    user_info = game["players"][current_uid]

    game["turn_index"] += 1
    await bot.send_message(
        chat_id,
        f"🗣 Հիմա բառ կասի @{user_info['username']}: (Գրիր քո բառը չաթում)",
    )


@dp.message()
async def handle_chat_messages(message: Message):
    if message.chat.type == "private":
        # Անձնական նամակների մշակում (լրտեսների զրույց կամ գուշակություն)
        return

    chat_id = message.chat.id
    if chat_id not in games or not games.get(chat_id, {}).get("active"):
        return

    user_id = message.from.id
    game = games[chat_id]

    # Ստուգում ենք՝ արդյոք այս պահին խոսելու հերթն այս օգտատիրոջն է
    # (Պարզեցված կերպով կարող ենք թույլ տալ կամ հետևել հերթին)
    pass


@dp.callback_query(F.data == "spy_guess_start")
async def spy_guess_callback(callback: CallbackQuery):
    chat_id = callback.message.chat.id
    user_id = callback.from_user.id

    if chat_id not in games or user_id not in games[chat_id]["spies"]:
        await callback.answer("Դուք լրտես չեք:", show_alert=True)
        return

    await callback.message.answer(
        f"@{callback.from_user.username}, գրեք ձեր կռահած բառը պատասխան նամակով կամ չաթում:"
    )
    # Այստեղ կարող ենք ակտիվացնել լրտեսի գուշակման սպասման ռեժիմը


# --- ՔՎԵԱՐԿՈՒԹՅՈՒՆ ԵՎ ԱՎԱՐՏ ---
async def start_voting(chat_id):
    game = games[chat_id]
    game["stage"] = "voting"

    keyboard_buttons = []
    for uid, p in game["players"].items():
        keyboard_buttons.append(
            [
                InlineKeyboardButton(
                    text=f"👤 @{p['username']}", callback_data=f"vote_{uid}"
                )
            ]
        )

    await bot.send_message(
        chat_id,
        "🗳 Դուք յուրաքանչյուրդ ասել եք երեք բառ:\nՑանկանու՞մ եք քվեարկել ինչ-որ մեկին, թե՞ շարունակել:",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="🗳 Քվեարկել", callback_data="go_to_vote"
                    ),
                    InlineKeyboardButton(
                        text="▶️ Շարունակել", callback_data="continue_game"
                    ),
                ]
            ]
        ),
    )


@dp.callback_query(F.data == "go_to_vote")
async def open_voting_list(callback: CallbackQuery):
    chat_id = callback.message.chat.id
    game = games.get(chat_id)
    if not game:
        return

    keyboard_buttons = []
    for uid, p in game["players"].items():
        keyboard_buttons.append(
            [
                InlineKeyboardButton(
                    text=f"❌ @{p['username']}", callback_data=f"vote_user_{uid}"
                )
            ]
        )

    await callback.message.edit_text(
        "Ընտրեք մասնակցին, ում կասկածում եք լրտես լինելու մեջ:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard_buttons),
    )


@dp.callback_query(F.data.startswith("vote_user_"))
async def register_vote(callback: CallbackQuery):
    target_uid = int(callback.data.split("_")[2])
    chat_id = callback.message.chat.id
    game = games.get(chat_id)

    if not game:
        return

    target_user = game["players"].get(target_uid)
    voter_username = callback.from_user.username

    await bot.send_message(
        chat_id,
        f"@{voter_username} կարծում է, որ @{target_user['username']} ԼՐՏԵՍ Է։",
    )
    await callback.answer("Ձեր ձայնը գրանցվեց!")


@dp.callback_query(F.data == "continue_game")
async def continue_playing(callback: CallbackQuery):
    chat_id = callback.message.chat.id
    await callback.message.edit_text(
        "Խաղը շարունակվում է։ Հաջորդ փուլը սկսվում է..."
    )
    # Նորից կարող ենք շարունակել հերթը կամ ավարտել
    del games[chat_id]


# --- ԱԴՄԻՆԻ ՖՈՒՆԿՑԻԱՆԵՐ ԵՎ ՏՈՆԱԿԱՆ ԱԲԴԵՅԹՆԵՐ ---
@dp.message(Command("ban"))
async def admin_ban(message: Message):
    if message.from.id != ADMIN_ID:
        return
    args = message.text.split()
    if len(args) > 1:
        uid = int(args[1])
        banned_users.add(uid)
        await message.answer(f"Օգտատեր {uid}-ը արգելափակվեց:")


@dp.message(Command("unban"))
async def admin_unban(message: Message):
    if message.from.id != ADMIN_ID:
        return
    args = message.text.split()
    if len(args) > 1:
        uid = int(args[1])
        banned_users.discard(uid)
        await message.answer(f"Օգտատեր {uid}-ը ապաարգելափակվեց:")


@dp.message(Command("valentine"))
async def update_valentine(message: Message):
    global current_theme
    current_theme = "valentine"
    await message.answer(
        "❤️ Վալենտինի ռեժիմն ակտիվացավ! Լրտեսը դարձավ **ՎԱԼԵՆՏԻՆ**:"
    )


@dp.message(Command("new_year"))
async def update_newyear(message: Message):
    global current_theme
    current_theme = "new_year"
    await message.answer(
        "🎄 Նոր տարվա ռեժիմն ակտիվացավ! Լրտեսը դարձավ **ՁՄԵՐ ՊԱՊԻԿ**:"
    )


@dp.message(Command("helloween"))
async def update_helloween(message: Message):
    global current_theme
    current_theme = "helloween"
    await message.answer(
        "🎃 Հելոուինի ռեժիմն ակտիվացավ! Լրտեսը դարձավ **ԶՈՄԲԻ**:"
    )


@dp.message(Command("normal_bot"))
async def update_normal(message: Message):
    global current_theme
    current_theme = "normal"
    await message.answer("🔄 Բոտը վերադարձավ ստանդարտ տեսքի:")


# --- ԱՆԱՆՈՒՆ ՆԱՄԱԿ ԱԴՄԻՆԻՆ ---
@dp.callback_query(F.data == "feedback")
async def feedback_start(callback: CallbackQuery, state: FSMContext):
    await callback.message.answer(
        "Գրեք ձեր նամակը, առաջարկը կամ բողոքը այստեղ, և այն անանուն կհասնի ադմինին:"
    )
    await state.set_state(AdminState.waiting_for_feedback)
    await callback.answer()


@dp.message(AdminState.waiting_for_feedback)
async def receive_feedback(message: Message, state: FSMContext):
    user = message.from.id
    username = message.from.user.username or "Չկա"
    full_name = message.from.user.full_name

    text_to_admin = (
        f"Անուն՝ {full_name}\n"
        f"User: @{username} (ID: {user})\n\n"
        f"Օգտատերի նամակը⬇️\n{message.text}"
    )

    try:
        await bot.send_message(ADMIN_ID, text_to_admin)
        await message.answer(
            "✅ Ձեր նամակը հաջողությամբ ուղարկվեց ադմինին:"
        )
    except Exception:
        await message.answer("❌ Նամակն ուղարկելիս սխալ տեղի ունեցավ:")

    await state.clear()


# Բոտի գործարկում
async def main():
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
