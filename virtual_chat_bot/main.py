import asyncio
import logging
import random
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    LabeledPrice,
    PreCheckoutQuery,
)

# 🔑 Կարգավորումներ
TOKEN = "8888526170:AAGnMdx_Tj7wcGCz7epRYBX1jz17maANNKU"  # Փոխարինիր քո բոտի թոքենով
ADMIN_ID = 6614409372  # Փոխարինիր քո Telegram ID-ով

bot = Bot(token=TOKEN)
dp = Dispatcher()

# --- ՀԻՇՈՂՈՒԹՅԱՆ ԲԱԶԱ (In-memory DB հիմք) ---
users_db = {}  # user_id: {lang, name, gender, age, flag, photo, coins, vip_days, vip_plus_days, ref_count}
banned_users = set()
global_chat_members = set()
likes_db = {}  # user_id: set(liked_user_ids)
active_matches = {}  # user_id: partner_id
theme_mode = "normal"  # normal, valentinday, halloween, newyear
shop_modifier = 0  # Տոկոսային փոփոխություն խանութի գների համար (+/- %)


# --- ՖԵՅՍԲՈՒՔՅԱՆ / ՏԵՔՍՏԱՅԻՆ ԹԵՄԱՆԵՐԻ ՈՒՂՂՈՐԴԻՉ ---
def get_theme_emoji():
  if theme_mode == "valentinday":
    return "💖"
  elif theme_mode == "halloween":
    return "🎃"
  elif theme_mode == "newyear":
    return "🎄"
  return "🔥"


# --- FSM (ՎԻՃԱԿՆԵՐ) ---
class RegState(StatesGroup):
  lang = State()
  name = State()
  gender = State()
  age = State()
  flag = State()
  photo = State()


class AdminState(StatesGroup):
  broadcast = State()


class ProfileEditState(StatesGroup):
  confirm = State()


class MiniGamePlayState(StatesGroup):
  bet = State()


class UserMessageToAdmin(StatesGroup):
  text = State()


# --- START ՀՐԱՄԱՆ ԵՎ ԳՐԱՆՑՈՒՄ ---
@dp.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):
  user_id = message.from_user.id
  if user_id in banned_users:
    await message.answer("❌ Դու արգելափակված ես այս համակարգից։")
    return

  # Եթե արդեն գրանցված է, բացում ենք անմիջապես պրոֆիլը
  if user_id in users_db:
    await show_profile(message, user_id)
    return

  # Եթե նոր է, առաջարկում ենք ընտրել լեզու
  keyboard = InlineKeyboardMarkup(
      inline_keyboard=[
          [
              InlineKeyboardButton(text="🇦🇲 Հայերեն", callback_data="lang_am"),
              InlineKeyboardButton(text="🇷🇺 Русский", callback_data="lang_ru"),
          ],
          [
              InlineKeyboardButton(text="🇬🇧 English", callback_data="lang_en"),
              InlineKeyboardButton(text="🇩🇪 Deutsch", callback_data="lang_de"),
          ],
          [InlineKeyboardButton(text="🇫🇷 Français", callback_data="lang_fr")],
      ]
  )
  await message.answer(
      f"{get_theme_emoji()} Ընտրեք ձեր նախընտրած լեզուն / Select your language:",
      reply_markup=keyboard,
  )
  await state.set_state(RegState.lang)


@dp.callback_query(F.data.startswith("lang_"), RegState.lang)
async def process_lang(callback: types.CallbackQuery, state: FSMContext):
  lang = callback.data.split("_")[1]
  await state.update_data(lang=lang)
  await callback.message.edit_text(
      "✍️ Հիանալի է։ Այժմ ընտրեք գործողությունը:",
      reply_markup=InlineKeyboardMarkup(
          inline_keyboard=[
              [
                  InlineKeyboardButton(
                      text="📝 Գրանցվել", callback_data="reg_start"
                  )
              ],
              [
                  InlineKeyboardButton(
                      text="💎 Donate Admin-ին (Stars)",
                      callback_data="reg_donate",
                  )
              ],
          ]
      ),
  )
  await callback.answer()


@dp.callback_query(F.data == "reg_donate")
async def reg_donate_prompt(callback: types.CallbackQuery):
  await callback.message.answer(
      "⭐ Խնդրում ենք մուտքագրել այն Telegram Stars-ի քանակը, որով ցանկանում եք"
      " աջակցել ադմինին (օրինակ՝ /donate 50):"
  )
  await callback.answer()


@dp.message(Command("donate"))
async def custom_donate_stars(message: types.Message):
  args = message.text.split()
  if len(args) < 2 or not args[1].isdigit():
    await message.answer(
        "⚠️ Օգտագործումը սխալ է։ Գրեք օրինակ՝ `/donate 50`",
        parse_mode="Markdown",
    )
    return
  amount = int(args[1])
  prices = [LabeledPrice(label="Տելեգրամ Դոնատ / Donate", amount=amount)]
  await message.bot.send_invoice(
      chat_id=message.chat.id,
      title="Աջակցություն Ադմինին",
      description=(
          "Շնորհակալություն Virtual Chat բոտին և ադմինիստրատորին աջակցելու համար:"
      ),
      payload=f"donate_{amount}",
      currency="XTR",  # Telegram Stars
      prices=prices,
  )


@dp.callback_query(F.data == "reg_start")
async def reg_name(callback: types.CallbackQuery, state: FSMContext):
  await callback.message.edit_text("Խնդրում ենք ուղարկել ձեր **անունը**:")
  await state.set_state(RegState.name)
  await callback.answer()


@dp.message(RegState.name)
async def reg_gender_step(message: types.Message, state: FSMContext):
  await state.update_data(name=message.text)
  keyboard = InlineKeyboardMarkup(
      inline_keyboard=[
          [
              InlineKeyboardButton(text="👦 Տղա", callback_data="gender_boy"),
              InlineKeyboardButton(
                  text="👧 Աղջիկ", callback_data="gender_girl"
              ),
          ],
          [InlineKeyboardButton(text="✨ Այլ", callback_data="gender_other")],
      ]
  )
  await message.answer("Ընտրեք ձեր սեռը:", reply_markup=keyboard)
  await state.set_state(RegState.gender)


@dp.callback_query(F.data.startswith("gender_"), RegState.gender)
async def reg_age_step(callback: types.CallbackQuery, state: FSMContext):
  gender = callback.data.split("_")[1]
  await state.update_data(gender=gender)
  await callback.message.edit_text("Խնդրում ենք գրել ձեր **տարիքը** (թվով):")
  await state.set_state(RegState.age)
  await callback.answer()


@dp.message(RegState.age)
async def reg_flag_step(message: types.Message, state: FSMContext):
  if not message.text.isdigit():
    await message.answer("Խնդրում ենք գրել ճիշտ տարիք (թիվ):")
    return
  await state.update_data(age=int(message.text))
  await message.answer(
      "Ուղարկեք ձեր պետության **դրոշը emoji-ով** (օրինակ՝ 🇦🇲):"
  )
  await state.set_state(RegState.flag)


@dp.message(RegState.flag)
async def reg_photo_step(message: types.Message, state: FSMContext):
  await state.update_data(flag=message.text)
  await message.answer(
      "Ուղարկեք ձեր պրոֆիլի **նկարը** (լուսանկար չատի համար):"
  )
  await state.set_state(RegState.photo)


@dp.message(RegState.photo, F.photo)
async def reg_finish(message: types.Message, state: FSMContext):
  photo_id = message.photo[-1].file_id
  data = await state.get_data()
  user_id = message.from_user.id

  users_db[user_id] = {
      "lang": data["lang"],
      "name": data["name"],
      "gender": data["gender"],
      "age": data["age"],
      "flag": data["flag"],
      "photo": photo_id,
      "coins": 10,  # Սկզբնական բոնուսային կոյններ
      "vip_days": 0,
      "vip_plus_days": 0,
      "ref_count": 0,
      "username": message.from_user.username or "No username",
  }
  global_chat_members.add(user_id)
  await state.clear()
  await message.answer("🎉 Գրանցումը հաջողությամբ ավարտվեց!")
  await show_profile(message, user_id)


# --- ՊՐՈՖԻԼԻՑ ՑՈՒՑԱԴՐՈՒՄ ---
async def show_profile(event, user_id):
  user = users_db[user_id]
  status_badge = "👑 VIP+" if user["vip_plus_days"] > 0 else ("💎 VIP" if user["vip_days"] > 0 else "👤 Սովորական")
  
  text = (
      f"{get_theme_emoji()} **Ձեր Պրոֆիլը** ({status_badge})\n\n"
      f"👤 Անուն: {user['name']}\n"
      f"⚧ Սեռ: {user['gender']}\n"
      f"🎂 Տարիք: {user['age']}\n"
      f"🌍 Դրոշ: {user['flag']}\n"
      f"🪙 Կոյններ: {user['coins']} coin\n"
      f"🔗 Ձեր հղումը: `https://t.me/{(await bot.me()).username}?start=ref_{user_id}`\n"
  )

  keyboard = InlineKeyboardMarkup(
      inline_keyboard=[
          [
              InlineKeyboardButton(text="🔍 Փնտրել ընկեր", callback_data="find_friend"),
              InlineKeyboardButton(text="🛒 Գնումներ", callback_data="shop_main"),
          ],
          [
              InlineKeyboardButton(text="🎮 Mini Game", callback_data="minigame_menu"),
              InlineKeyboardButton(text="💬 Մտնել Chat", callback_data="enter_global_chat"),
          ],
          [
              InlineKeyboardButton(text="⭐ Donate Admin-ին", callback_data="profile_donate"),
              InlineKeyboardButton(text="✉️ Նամակ Ադմինին", callback_data="msg_to_admin"),
          ],
          [
              InlineKeyboardButton(text="🔄 Փոխել պրոֆիլը (100 ⭐️)", callback_data="reset_profile"),
          ],
      ]
  )

  if isinstance(event, types.Message):
    await bot.send_photo(chat_id=event.chat.id, photo=user["photo"], caption=text, reply_markup=keyboard, parse_mode="Markdown")
  elif isinstance(event, types.CallbackQuery):
    await event.message.answer_photo(photo=user["photo"], caption=text, reply_markup=keyboard, parse_mode="Markdown")


@dp.callback_query(F.data == "profile_donate")
async def profile_donate_cb(callback: types.CallbackQuery):
  await callback.message.answer("⭐ Գրեք `/donate [թիվ]` հրամանը՝ ադմինին աստղեր նվիրաբերելու համար:")
  await callback.answer()


@dp.callback_query(F.data == "msg_to_admin")
async def msg_to_admin_start(callback: types.CallbackQuery, state: FSMContext):
  await callback.message.answer("✍️ Գրեք ձեր նամակը ադմինիստրատորին. այն կուղարկվի ձեր տվյալների հետ միասին:")
  await state.set_state(UserMessageToAdmin.text)
  await callback.answer()


@dp.message(UserMessageToAdmin.text)
async def send_msg_to_admin_finish(message: types.Message, state: FSMContext):
  user_id = message.from_user.id
  user = users_db.get(user_id, {})
  text = (
      f"📩 **ՆԱՄԱԿ ԱԴՄԻՆԻՆ**\n\n"
      f"👤 Օգտատեր: {user.get('name', 'N/A')}\n"
      f"🆔 User ID: `{user_id}`\n"
      f"🔗 Nickname: @{user.get('username', 'none')}\n\n"
      f"💬 Բովանդակություն:\n{message.text}"
  )
  try:
    await bot.send_message(chat_id=ADMIN_ID, text=text, parse_mode="Markdown")
    await message.answer("✅ Ձեր նամակը հաջողությամբ ուղարկվեց ադմինիստրատորին:")
  except Exception:
    await message.answer("❌ Չհաջողվեց ուղարկել նամակը:")
  await state.clear()


# --- ՓՆՏՐԵԼ ԸՆԿԵՐ ԵՎ ԶՐՈՒՑԱՐԱՆԻ ՄԵԽԱՆԻԿԱ ---
@dp.callback_query(F.data == "find_friend")
async def find_friend_menu(callback: types.CallbackQuery):
  keyboard = InlineKeyboardMarkup(
      inline_keyboard=[
          [
              InlineKeyboardButton(text="👦 Փնտրել տղա", callback_data="search_gender_boy"),
              InlineKeyboardButton(text="👧 Փնտրել աղջիկ", callback_data="search_gender_girl"),
          ],
          [InlineKeyboardButton(text="🔙 Հետ", callback_data="back_to_profile")],
      ]
  )
  await callback.message.edit_caption(caption="🔍 Ո՞ում եք ցանկանում փնտրել:", reply_markup=keyboard)
  await callback.answer()


@dp.callback_query(F.data.startswith("search_gender_"))
async def search_partner_by_gender(callback: types.CallbackQuery):
  target_gender = callback.data.split("_")[2]  # boy or girl
  user_id = callback.from_user.id
  
  # Գտնում ենք համապատասխան մարդկանց բազայից
  candidates = [uid for uid, u in users_db.items() if uid != user_id and u["gender"].lower() in target_gender]
  
  if not candidates:
    await callback.answer("😔 Այս պահին համապատասխան օգտատերեր չկան:", show_alert=True)
    return

  partner_id = random.choice(candidates)
  partner = users_db[partner_id]

  keyboard = InlineKeyboardMarkup(
      inline_keyboard=[
          [
              InlineKeyboardButton(text="❤️ Հավանել", callback_data=f"like_{partner_id}"),
              InlineKeyboardButton(text="👎 Մերժել", callback_data="dislike_partner"),
          ],
          [InlineKeyboardButton(text="🔙 Հետ", callback_data="find_friend")],
      ]
  )
  
  caption = (
      f"👤 **Անկետա**\n"
      f"Անուն: {partner['name']}\n"
      f"Տարիք: {partner['age']}\n"
      f"Դրոշ: {partner['flag']}"
  )
  await callback.message.answer_photo(photo=partner["photo"], caption=caption, reply_markup=keyboard)
  await callback.answer()


@dp.callback_query(F.data.startswith("like_"))
async def process_like(callback: types.CallbackQuery):
  user_id = callback.from_user.id
  partner_id = int(callback.data.split("_")[1])
  
  if partner_id not in likes_db:
    likes_db[partner_id] = set()
  likes_db[partner_id].add(user_id)

  # Ստուգում ենք՝ արդյոք փոխադարձ է
  if user_id in likes_db and partner_id in likes_db[user_id]:
    # Համընկնում կա! Գանձում ենք 1-ական կոյն
    if users_db.get(user_id, {}).get("coins", 0) >= 1 and users_db.get(partner_id, {}).get("coins", 0) >= 1:
      users_db[user_id]["coins"] -= 1
      users_db[partner_id]["coins"] -= 1
      active_matches[user_id] = partner_id
      active_matches[partner_id] = user_id
      
      await callback.message.answer("🎉 **Փոխադարձ համընկնում (Match)!** Ձեզանից և ձեր զրուցակցից գանձվեց 1 coin: Այժմ կարող եք շփվել:")
      try:
        await bot.send_message(chat_id=partner_id, text="🎉 **Փոխադարձ համընկնում (Match)!** Ձեզանից և ձեր զրուցակցից գանձվեց 1 coin:")
      except Exception:
        pass
    else:
      await callback.message.answer("⚠️ Զրույցը սկսելու համար երկու կողմն էլ պետք է ունենան առնվազն 1 coin կամ կատարեն դոնատ/գնում։")
  else:
      await callback.message.answer("❤️ Հավանումն ուղարկված է:")
  await callback.answer()


@dp.callback_query(F.data == "dislike_partner")
async def process_dislike(callback: types.CallbackQuery):
  await callback.message.answer("❌ Մերժվեց։ Փնտրեք հաջորդին:")
  await callback.answer()


# --- ԳՆՈՒՄՆԵՐ ԵՎ VIP ՀԱՄԱԿԱՐԳ ---
@dp.callback_query(F.data == "shop_main")
async def shop_main_menu(callback: types.CallbackQuery):
  keyboard = InlineKeyboardMarkup(
      inline_keyboard=[
          [
              InlineKeyboardButton(text="🛍 Գնել իմ համար", callback_data="buy_self"),
              InlineKeyboardButton(text="🎁 Գնել ընկերոջ համար", callback_data="buy_friend"),
          ],
          [InlineKeyboardButton(text="👑 VIP / VIP+ Առավելություններ", callback_data="vip_info")],
          [InlineKeyboardButton(text="🔙 Հետ", callback_data="back_to_profile")],
      ]
  )
  await callback.message.edit_caption(caption="🛒 **Խանութ և Դրամարկղ**\nԸնտրեք բաժինը.", reply_markup=keyboard)
  await callback.answer()


@dp.callback_query(F.data == "vip_info")
async def vip_info_menu(callback: types.CallbackQuery):
  text = (
      "👑 **VIP ԱՌԱՎԵԼՈՒԹՅՈՒՆՆԵՐ**\n"
      "• 15% զեղչ բոլոր գնումների վրա\n"
      "• Ավելի ճոխ պրոֆիլի ձևավորում\n"
      "• Մինի խաղերում շահումը կրկնապատկվում է (x2)\n\n"
      "👑 **VIP+ ԱՌԱՎԵԼՈՒԹՅՈՒՆՆԵՐ**\n"
      "• 25% զեղչ բոլոր գնումների վրա\n"
      "• Շատ ճոխ պրոֆիլ\n"
      "• Մինի խաղերում շահումը եռապատկվում է (x3)\n"
  )
  keyboard = InlineKeyboardMarkup(
      inline_keyboard=[
          [InlineKeyboardButton(text="💎 Գնել VIP", callback_data="buy_vip_list")],
          [InlineKeyboardButton(text="🌟 Գնել VIP+", callback_data="buy_vipplus_list")],
          [InlineKeyboardButton(text="🔙 Հետ", callback_data="shop_main")],
      ]
  )
  await callback.message.edit_caption(caption=text, reply_markup=keyboard)


@dp.callback_query(F.data == "buy_vip_list")
async def buy_vip_list(callback: types.CallbackQuery):
  keyboard = InlineKeyboardMarkup(
      inline_keyboard=[
          [InlineKeyboardButton(text="VIP 10 օր - 55 ⭐️", callback_data="pay_vip_10")],
          [InlineKeyboardButton(text="VIP 20 օր - 90 ⭐️", callback_data="pay_vip_20")],
          [InlineKeyboardButton(text="VIP 30 օր - 120 ⭐️", callback_data="pay_vip_30")],
          [InlineKeyboardButton(text="🔙 Հետ", callback_data="vip_info")],
      ]
  )
  await callback.message.edit_caption(caption="💎 **Ընտրեք VIP փաթեթը**", reply_markup=keyboard)


@dp.callback_query(F.data == "buy_vipplus_list")
async def buy_vipplus_list(callback: types.CallbackQuery):
  keyboard = InlineKeyboardMarkup(
      inline_keyboard=[
          [InlineKeyboardButton(text="VIP+ 10 օր - 90 ⭐️", callback_data="pay_vipplus_10")],
          [InlineKeyboardButton(text="VIP+ 20 օր - 195 ⭐️", callback_data="pay_vipplus_20")],
          [InlineKeyboardButton(text="VIP+ 30 օր - 230 ⭐️", callback_data="pay_vipplus_30")],
          [InlineKeyboardButton(text="🔙 Հետ", callback_data="vip_info")],
      ]
  )
  await callback.message.edit_caption(caption="🌟 **Ընտրեք VIP+ փաթեթը**", reply_markup=keyboard)


@dp.callback_query(F.data.startswith("pay_vip_"))
async def process_vip_invoice(callback: types.CallbackQuery):
  days = int(callback.data.split("_")[3])
  stars_map = {10: 55, 20: 90, 30: 120}
  cost = int(stars_map[days] * (1 + shop_modifier / 100.0))
  
  prices = [LabeledPrice(label=f"VIP {days} օր", amount=cost)]
  await callback.message.bot.send_invoice(
      chat_id=callback.message.chat.id,
      title=f"VIP կարգավիճակ ({days} օր)",
      description="Ձեռք բերեք VIP արտոնություններ",
      payload=f"vip_{days}",
      currency="XTR",
      prices=prices,
  )


@dp.callback_query(F.data.startswith("pay_vipplus_"))
async def process_vipplus_invoice(callback: types.CallbackQuery):
  days = int(callback.data.split("_")[2])
  stars_map = {10: 90, 20: 195, 30: 230}
  cost = int(stars_map[days] * (1 + shop_modifier / 100.0))

  prices = [LabeledPrice(label=f"VIP+ {days} օր", amount=cost)]
  await callback.message.bot.send_invoice(
      chat_id=callback.message.chat.id,
      title=f"VIP+ կարգավիճակ ({days} օր)",
      description="Ձեռք բերեք VIP+ առավելագույն արտոնություններ",
      payload=f"vipplus_{days}",
      currency="XTR",
      prices=prices,
  )


@dp.callback_query(F.data == "buy_self")
async def buy_coins_self(callback: types.CallbackQuery):
  keyboard = InlineKeyboardMarkup(
      inline_keyboard=[
          [InlineKeyboardButton(text="100 coin = 50 ⭐️", callback_data="coinpay_100_50")],
          [InlineKeyboardButton(text="150 coin = 85 ⭐️", callback_data="coinpay_150_85")],
          [InlineKeyboardButton(text="200 coin = 95 ⭐️", callback_data="coinpay_200_95")],
          [InlineKeyboardButton(text="250 coin = 111 ⭐️", callback_data="coinpay_250_111")],
          [InlineKeyboardButton(text="300 coin = 195 ⭐️", callback_data="coinpay_300_195")],
          [InlineKeyboardButton(text="350 coin = 225 ⭐️", callback_data="coinpay_350_225")],
          [InlineKeyboardButton(text="🔙 Հետ", callback_data="shop_main")],
      ]
  )
  await callback.message.edit_caption(caption="🪙 **Ընտրեք կոյնների փաթեթը**", reply_markup=keyboard)


@dp.callback_query(F.data.startswith("coinpay_"))
async def process_coin_purchase(callback: types.CallbackQuery):
  parts = callback.data.split("_")
  coins = int(parts[1])
  stars = int(parts[2])
  cost = int(stars * (1 + shop_modifier / 100.0))

  prices = [LabeledPrice(label=f"{coins} Coins", amount=cost)]
  await callback.message.bot.send_invoice(
      chat_id=callback.message.chat.id,
      title=f"Գնել {coins} Կոյն",
      description="Ավելացրեք ձեր հաշվեկշիռը",
      payload=f"coins_{coins}",
      currency="XTR",
      prices=prices,
  )


# --- TELEGRAM STARS ՎՃԱՐՄԱՆ ՀԱՍՏԱՏՈՒՄ ---
@dp.pre_checkout_query()
async def pre_checkout_handler(pre_checkout_query: PreCheckoutQuery):
  await pre_checkout_query.answer(ok=True)


@dp.message(F.successful_payment)
async def successful_payment_handler(message: types.Message):
  payload = message.successful_payment.invoice_payload
  user_id = message.from_user.id
  user = users_db.get(user_id)
  if not user:
    return

  if payload.startswith("coins_"):
    coins = int(payload.split("_")[1])
    user["coins"] += coins
    await message.answer(f"✅ Հաջողությամբ գնվեց և ավելացավ {coins} coin:")
  elif payload.startswith("vip_"):
    days = int(payload.split("_")[1])
    user["vip_days"] += days
    await message.answer(f"👑 Շնորհավորում ենք, ձեզ ավելացավ VIP {days} օրով:")
  elif payload.startswith("vipplus_"):
    days = int(payload.split("_")[1])
    user["vip_plus_days"] += days
    await message.answer(f"🌟 Շնորհավորում ենք, ձեզ ավելացավ VIP+ {days} օրով:")


# --- MINI GAME (5x5 ՌՈՒՄԲԵՐՈՎ ԽԱՂ) ---
@dp.callback_query(F.data == "minigame_menu")
async def minigame_menu(callback: types.CallbackQuery):
  keyboard = InlineKeyboardMarkup(
      inline_keyboard=[
          [InlineKeyboardButton(text="🎮 Վճարովի խաղ (5 ⭐️)", callback_data="mg_paid")],
          [InlineKeyboardButton(text="🕹 Դեմո խաղ (Անվճար)", callback_data="mg_demo")],
          [InlineKeyboardButton(text="🔙 Հետ", callback_data="back_to_profile")],
      ]
  )
  await callback.message.edit_caption(caption="🎮 **Mini Game: Ռումբեր և Կոյններ**\nԸնտրեք խաղի ռեժիմը.", reply_markup=keyboard)
  await callback.answer()


@dp.callback_query(F.data == "mg_demo")
async def minigame_demo_start(callback: types.CallbackQuery, state: FSMContext):
  await callback.message.answer("🕹 Դեմո խաղ։ Մուտքագրեք ձեր խաղադրույքը (կոյններով):")
  await state.set_state(MiniGamePlayState.bet)
  await state.update_data(is_paid=False)
  await callback.answer()


@dp.callback_query(F.data == "mg_paid")
async def minigame_paid_start(callback: types.CallbackQuery, state: FSMContext):
  # Վճարովի խաղի համար պահանջվում է 5 աստղ
  prices = [LabeledPrice(label="Մուտք խաղին", amount=5)]
  await callback.message.bot.send_invoice(
      chat_id=callback.message.chat.id,
      title="Mini Game Մուտքավճար",
      description="Վճարեք 5 ⭐️ վճարովի խաղ մտնելու համար",
      payload="minigame_fee",
      currency="XTR",
      prices=prices,
  )
  await callback.answer()


@dp.message(MiniGamePlayState.bet)
async def minigame_play_process(message: types.Message, state: FSMContext):
  if not message.text.isdigit():
    await message.answer("Խնդրում ենք մուտքագրել թիվ:")
    return
  bet = int(message.text)
  user_id = message.from_user.id
  user = users_db[user_id]

  if user["coins"] < bet:
    await message.answer("⚠️ Ձեր հաշվեկշռում բավարար կոյններ չկան այս խաղադրույքի համար:")
    return

  user["coins"] -= bet
  # Խաղի մեխանիկա՝ 5x5 վանդակներից մեկը ռումբ է
  has_bomb = random.choice([True, False, False, False, False])
  
  if has_bomb:
    await message.answer("💥 Ցավոք, դուք բացեցիք ռումբը և կորցրեցիք ներդրված կոյնները:")
    await state.clear()
  else:
    multiplier = 1.50
    if user["vip_plus_days"] > 0:
      multiplier = 3.0
    elif user["vip_days"] > 0:
      multiplier = 2.0

    won = int(bet * multiplier)
    user["coins"] += won
    await message.answer(f"🎉 Հաղթանակ! Ռումբ չկար։ Բազմապատկիչը՝ x{multiplier}, դուք շահեցիք {won} coin!")
    await state.clear()


# --- ՄՇՏԱԿԱՆ ՉԱՏ ԵՎ ՀԵՏ ԿՈՃԱԿՆԵՐ ---
@dp.callback_query(F.data == "enter_global_chat")
async def enter_global_chat(callback: types.CallbackQuery):
  await callback.message.answer("💬 Դուք հաջողությամբ միացաք ընդհանուր վիրտուալ չատին։ Գրեք ձեր հաղորդագրությունը:")
  await callback.answer()


@dp.callback_query(F.data == "back_to_profile")
async def back_to_profile_cb(callback: types.CallbackQuery):
  await callback.message.delete()
  await show_profile(callback.message, callback.from_user.id)


@dp.callback_query(F.data == "reset_profile")
async def reset_profile_cb(callback: types.CallbackQuery, state: FSMContext):
  user_id = callback.from_user.id
  user = users_db.get(user_id)
  if user and user["coins"] >= 100:  # Կամ 100 աստղ պահանջով
    del users_db[user_id]
    await callback.message.answer("🔄 Ձեր պրոֆիլը զրոյացվեց։ Սկսելու համար սեղմեք /start")
  else:
    await callback.message.answer("⚠️ Պրոֆիլը զրոյացնելու համար անհրաժեշտ է վճարել 100 ⭐️ կամ բավարար միջոցներ:")
  await callback.answer()


# --- ԱԴՄԻՆԻՍՏՐԱՏՈՐԻ ՀՐԱՄԱՆՆԵՐ ---
@dp.message(Command("vip"))
async def admin_set_vip(message: types.Message):
  if message.from_user.id != ADMIN_ID:
    return
  args = message.text.split()
  if len(args) < 3:
    await message.answer("Օգտագործումը՝ `/vip [ID] [օրեր]`", parse_mode="Markdown")
    return
  target_id = int(args[1])
  days = int(args[2])
  if target_id in users_db:
    users_db[target_id]["vip_days"] += days
    await message.answer(f"✅ Օգտատեր {target_id}-ին ավելացավ VIP {days} օրով:")


@dp.message(Command("vipplus"))
async def admin_set_vipplus(message: types.Message):
  if message.from_user.id != ADMIN_ID:
    return
  args = message.text.split()
  if len(args) < 3:
    await message.answer("Օգտագործումը՝ `/vipplus [ID] [օրեր]`", parse_mode="Markdown")
    return
  target_id = int(args[1])
  days = int(args[2])
  if target_id in users_db:
    users_db[target_id]["vip_plus_days"] += days
    await message.answer(f"✅ Օգտատեր {target_id}-ին ավելացավ VIP+ {days} օրով:")


@dp.message(Command("online"))
async def admin_online_stats(message: types.Message):
  if message.from_user.id != ADMIN_ID:
    return
  total_registered = len(users_db)
  active_online = len(global_chat_members)
  await message.answer(f"📊 **Վիճակագրություն**\n\n👥 Գրանցվածներ: {total_registered}\n🟢 Ակտիվ/Օնլայն: {active_online}", parse_mode="Markdown")


@dp.message(Command("coin"))
async def admin_give_coins(message: types.Message):
  if message.from_user.id != ADMIN_ID:
    return
  args = message.text.split()
  if len(args) < 3:
    await message.answer("Օգտագործումը՝ `/coin [ID] [քանակ]`", parse_mode="Markdown")
    return
  target_id = int(args[1])
  amount = int(args[2])
  if target_id in users_db:
    users_db[target_id]["coins"] += amount
    await message.answer(f"✅ Օգտատեր {target_id}-ին փոխանցվեց {amount} coin:")


@dp.message(Command("valentinday"))
async def admin_theme_valentinday(message: types.Message):
  global theme_mode
  if message.from_user.id != ADMIN_ID:
    return
  theme_mode = "valentinday"
  await message.answer("💖 Վալենտինի տոնական թեման ակտիվացված է!")


@dp.message(Command("halloween"))
async def admin_theme_halloween(message: types.Message):
  global theme_mode
  if message.from_user.id != ADMIN_ID:
    return
  theme_mode = "halloween"
  await message.answer("🎃 Հելոուինի թեման ակտիվացված է!")


@dp.message(Command("newyear"))
async def admin_theme_newyear(message: types.Message):
  global theme_mode
  if message.from_user.id != ADMIN_ID:
    return
  theme_mode = "newyear"
  await message.answer("🎄 Ամանորյա թեման ակտիվացված է!")


@dp.message(Command("normalbot"))
async def admin_theme_normal(message: types.Message):
  global theme_mode
  if message.from_user.id != ADMIN_ID:
    return
  theme_mode = "normal"
  await message.answer("🔄 Բոտը վերադարձավ սովորական ռեժիմին:")


@dp.message(Command("ban"))
async def admin_ban_user(message: types.Message):
  if message.from_user.id != ADMIN_ID:
    return
  args = message.text.split()
  if len(args) < 2:
    return
  target_id = int(args[1])
  banned_users.add(target_id)
  await message.answer(f"🚫 Օգտատեր {target_id}-ը արգելափակվեց:")


@dp.message(Command("unban"))
async def admin_unban_user(message: types.Message):
  if message.from_user.id != ADMIN_ID:
    return
  args = message.text.split()
  if len(args) < 2:
    return
  target_id = int(args[1])
  if target_id in banned_users:
    banned_users.remove(target_id)
  await message.answer(f"✅ Օգտատեր {target_id}-ը հանվեց արգելափակումից:")


@dp.message(Command("shop"))
async def admin_shop_modifier(message: types.Message):
  global shop_modifier
  if message.from_user.id != ADMIN_ID:
    return
  args = message.text.split()
  if len(args) < 2:
    return
  # Օրինակ՝ /shop 10- կամ /shop 10+
  val_str = args[1]
  num = int(val_str[:-1])
  sign = val_str[-1]
  shop_modifier = -num if sign == "-" else num
  await message.answer(f"⚙️ Խանութի գների փոփոխիչը սահմանվեց: {sign}{num}%")


# --- ԳՈՐԾԱՐԿՈՒՄ ---
async def main():
  logging.basicConfig(level=logging.INFO)
  print("🔥 Virtual Chat բոտը հաջողությամբ գործարկվեց!")
  await dp.start_polling(bot)


if __name__ == "__main__":
  asyncio.run(main())