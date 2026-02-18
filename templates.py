import os
from collections.abc import Sequence
from datetime import datetime
from html import escape

from models.enums import ReissueCategory
from models.reissue import ReissueGirl
from utils.time import TASHKENT_TZ

# ── Language: "uz" for production (girls), "ru" for testing ──────────────────

_lang = os.getenv("BOT_LANG", "uz")


def _t(ru: str, uz: str) -> str:
    """Return Russian or Uzbek text based on BOT_LANG env var."""
    return ru if _lang == "ru" else uz


def fallback_manager_name() -> str:
    """Fallback when manager is not found in DB."""
    return _t("менеджер", "menejer")


def format_remaining(hours: int, minutes: int) -> str:
    """Format remaining time: '2ч 30мин' or '2 soat 30 daq'."""
    if hours > 0:
        return _t(f"{hours}ч {minutes}мин", f"{hours} soat {minutes} daq")
    return _t(f"{minutes}мин", f"{minutes} daq")


def _topic_link(name: str, topic_id: int | None, group_id: int | None) -> str:
    """Format name as HTML link to forum topic, or plain text if no topic."""
    safe_name = escape(name)
    if topic_id and group_id:
        # t.me/c/ uses group_id without -100 prefix
        clean_id = str(group_id).replace("-100", "")
        return f'<a href="https://t.me/c/{clean_id}/{topic_id}">{safe_name}</a>'
    return safe_name


class BotDescriptionTemplates:
    @staticmethod
    def full_description() -> str:
        return _t(
            "Помощник по приёму таблетки.\n\n"
            "Бот каждый день будет напоминать "
            "о приёме таблетки и проверять видео-отчёт.\n\n"
            "Регистрация займёт пару минут.",

            "Dori qabul qilish yordamchisi.\n\n"
            "Bot har kuni tabletkani ichishni eslatadi "
            "va video-hisobotni tekshiradi.\n\n"
            "Ro'yxatdan o'tish bir necha daqiqa oladi.",
        )

    @staticmethod
    def short_description() -> str:
        return _t("Помощник по приёму таблетки", "Dori qabul qilish yordamchisi")


class MenuTemplates:
    @staticmethod
    def main_menu() -> str:
        return (
            "<b>KOK Bot — Панель управления</b>\n\n"
            "Выберите действие:"
        )

    @staticmethod
    def topic_cleared() -> str:
        return "Топик очищен"

    @staticmethod
    def feature_not_ready() -> str:
        return "В разработке"


class AddTemplates:
    @staticmethod
    def time_restricted() -> str:
        return "Ссылки можно создавать до 20:00. Попробуйте завтра"

    # --- Паспорт ---

    @staticmethod
    def ask_passport() -> str:
        return "Отправьте фото паспорта"

    @staticmethod
    def ask_passport_processing() -> str:
        return "Подождите, обрабатываю фото..."

    @staticmethod
    def ocr_passport_result(name: str) -> str:
        return (
            "Распознано из паспорта:\n"
            f"ФИО: <b>{escape(name)}</b>"
        )

    @staticmethod
    def not_a_passport() -> str:
        return "<i>Это не паспорт. Отправьте фото первой страницы паспорта</i>"

    @staticmethod
    def ocr_passport_bad_photo() -> str:
        return (
            "<i>Не удалось распознать паспорт. "
            "Сделайте фото более чётким и попробуйте ещё раз</i>"
        )

    # --- Чек ---

    @staticmethod
    def ask_receipt() -> str:
        return "Отправьте фото чека"

    @staticmethod
    def ask_receipt_processing() -> str:
        return "Подождите, обрабатываю фото..."

    @staticmethod
    def ocr_receipt_result(price: int) -> str:
        formatted = f"{price:,}".replace(",", " ")
        return (
            "Распознано из чека:\n"
            f"Препарат найден, цена: <b>{formatted} сум</b>"
        )

    @staticmethod
    def not_a_receipt() -> str:
        return "<i>Это не чек. Отправьте фото чека из аптеки</i>"

    @staticmethod
    def ocr_receipt_bad_photo() -> str:
        return (
            "<i>Не удалось распознать чек. "
            "Сделайте фото более чётким и попробуйте ещё раз</i>"
        )

    @staticmethod
    def ocr_receipt_no_kok() -> str:
        return (
            "<i>Препарат не найден в чеке. "
            "Отправьте фото другого чека</i>"
        )

    @staticmethod
    def ocr_receipt_no_price() -> str:
        return (
            "<i>Препарат найден, но цена не распознана. "
            "Сделайте фото более чётким и попробуйте ещё раз</i>"
        )

    # --- Карта ---

    @staticmethod
    def ask_card() -> str:
        return "Отправьте фото банковской карты"

    @staticmethod
    def ask_card_processing() -> str:
        return "Подождите, обрабатываю фото..."

    @staticmethod
    def ocr_card_result(card_number: str, card_holder: str) -> str:
        return (
            "Распознано с карты:\n"
            f"Номер: <b>{escape(card_number)}</b>\n"
            f"Владелец: <b>{escape(card_holder)}</b>"
        )

    @staticmethod
    def not_a_card() -> str:
        return "<i>Это не банковская карта. Отправьте фото карты</i>"

    @staticmethod
    def ocr_card_bad_photo() -> str:
        return (
            "<i>Не удалось распознать карту. "
            "Сделайте фото более чётким и попробуйте ещё раз</i>"
        )

    # --- Общее ---

    @staticmethod
    def photo_only() -> str:
        return "<i>Неподдерживаемый формат. Отправьте фото</i>"

    @staticmethod
    def ocr_server_error() -> str:
        return "<i>Ошибка сервера, попробуйте через минуту</i>"

    @staticmethod
    def link_created(name: str, bot_username: str, invite_code: str) -> str:
        link = f"https://t.me/{bot_username}?start={invite_code}"
        return (
            f"Ссылка создана для <b>{escape(name)}</b>\n\n"
            f"<code>{link}</code>"
        )

    @staticmethod
    def user_has_active_course() -> str:
        return "У этого человека уже есть активная программа"

    @staticmethod
    def error_try_later() -> str:
        return "Ошибка, попробуйте позже через 5 минут"

    # --- Уведомление бухгалтеру ---

    @staticmethod
    def accountant_caption(
        name: str, card_number: str, card_holder_name: str,
    ) -> str:
        return (
            f"\U0001f464 {escape(name)}\n"
            f"\U0001f4b3 <code>{escape(card_number)}</code>\n"
            f"\U0001f4dd <code>{escape(card_holder_name)}</code>"
        )

    @staticmethod
    def accountant_send_receipt() -> str:
        return "Загрузите чек об оплате"


class PaymentTemplates:
    @staticmethod
    def ask_receipt(girl_name: str) -> str:
        return f"Отправьте фото чека об оплате для <b>{escape(girl_name)}</b>"

    @staticmethod
    def processing() -> str:
        return "Подождите, обрабатываю фото..."

    @staticmethod
    def not_a_receipt() -> str:
        return "<i>Это не чек об оплате. Отправьте фото чека</i>"

    @staticmethod
    def no_amount() -> str:
        return "<i>Не удалось определить сумму. Попробуйте другое фото</i>"

    @staticmethod
    def already_uploaded() -> str:
        return "Чек уже загружен для этого курса"

    @staticmethod
    def course_not_payable() -> str:
        return "Курс завершён или отклонён"

    @staticmethod
    def server_error() -> str:
        return "<i>Ошибка сервера, попробуйте через минуту</i>"

    @staticmethod
    def photo_only() -> str:
        return "<i>Отправьте фото чека об оплате</i>"

    @staticmethod
    def receipt_accepted(amount: int) -> str:
        formatted = f"{amount:,}".replace(",", " ")
        return f"\u2705 Чек принят. Сумма: {formatted} сум"

    @staticmethod
    def receipt_uploaded() -> str:
        return "\u2705 Чек загружен"

    @staticmethod
    def manager_receipt(girl_name: str, amount: int) -> str:
        formatted = f"{amount:,}".replace(",", " ")
        return (
            f"\U0001f4b3 Чек оплаты для <b>{escape(girl_name)}</b>\n"
            f"Сумма: {formatted} сум"
        )


class ReissueTemplates:
    _CATEGORY_HEADERS: dict[ReissueCategory, str] = {
        ReissueCategory.NOT_STARTED: "⬜ Не начала:",
        ReissueCategory.IN_PROGRESS: "🟡 В процессе:",
        ReissueCategory.EXPIRED: "🔴 Просрочено:",
    }

    @staticmethod
    def manager_only() -> str:
        return "Функция доступна только менеджерам"

    @classmethod
    def select_girl(cls, girls: Sequence[ReissueGirl]) -> str:
        lines: list[str] = []
        current_category: ReissueCategory | None = None

        for number, girl in enumerate(girls, start=1):
            if girl.category != current_category:
                if current_category is not None:
                    lines.append("")
                lines.append(cls._CATEGORY_HEADERS[girl.category])
                current_category = girl.category

            lines.append(f"{number}. {girl.short_name} — {girl.date_str}")

        return "\n".join(lines)

    @staticmethod
    def no_girls() -> str:
        return "Нет девушек с незавершённой регистрацией"

    @staticmethod
    def link_reissued(name: str, bot_username: str, invite_code: str) -> str:
        link = f"https://t.me/{bot_username}?start={invite_code}"
        return (
            f"Ссылка для <b>{escape(name)}</b>\n\n"
            f"<code>{link}</code>"
        )

    @staticmethod
    def error_try_later() -> str:
        return "Ошибка, попробуйте позже через 5 минут"


class OnboardingTemplates:
    # --- /start по ролям ---

    @staticmethod
    def manager_greeting(name: str) -> str:
        return f"Привет, {escape(name)}! Используй меня в группе для добавления девушек."

    @staticmethod
    def accountant_greeting(name: str) -> str:
        return f"Привет, {escape(name)}! Я буду отправлять тебе данные для оплаты."

    # --- Невалидные сценарии ---

    @staticmethod
    def no_link() -> str:
        return _t(
            "Попроси ссылку у менеджера",
            "Menejerdan havola so'ra",
        )

    @staticmethod
    def invalid_link() -> str:
        return _t("Ссылка недействительна", "Havola yaroqsiz")

    @staticmethod
    def link_used() -> str:
        return _t("Ссылка уже использована", "Havola allaqachon ishlatilgan")

    @staticmethod
    def link_expired(date_str: str) -> str:
        return _t(
            f"Ты должна была зарегистрироваться {date_str} до 00:00. "
            f"Обратись за новой ссылкой к своему менеджеру",
            f"Sen {date_str} kuni soat 00:00 gacha ro'yxatdan o'tishing kerak edi. "
            f"Menejeringdan yangi havola so'ra",
        )

    @staticmethod
    def use_buttons() -> str:
        return _t("Выбери одну из кнопок\u2757", "Tugmalardan birini tanla\u2757")

    @staticmethod
    def no_slots_left() -> str:
        return _t(
            "Слишком поздно, нет доступных слотов. Попробуй завтра",
            "Juda kech, bo'sh vaqt yo'q. Ertaga urinib ko'r",
        )

    @staticmethod
    def error_try_again() -> str:
        return _t("Ошибка, попробуй ещё раз", "Xatolik, qaytadan urinib ko'r")

    @staticmethod
    def session_expired() -> str:
        return _t("Сессия истекла", "Sessiya tugagan")

    @staticmethod
    def link_expired_contact_manager() -> str:
        return _t(
            "Ссылка истекла. Обратись к менеджеру",
            "Havola muddati tugagan. Menejerga murojaat qil",
        )

    # --- Шаги онбординга ---

    @staticmethod
    def instructions() -> str:
        return _t(
            "<b>Что тебя ждёт:</b>\n\n"
            "1. Выбери день менструального цикла\n"
            "2. Выбери удобное время приёма\n"
            "3. Ознакомься с правилами программы\n\n"
            "Это займёт пару минут.",

            "<b>Seni nima kutmoqda:</b>\n\n"
            "1. Hayz siklining kunini tanla\n"
            "2. Qulay qabul vaqtini tanla\n"
            "3. Dastur qoidalari bilan tanish\n\n"
            "Bu bir necha daqiqa oladi.",
        )

    @staticmethod
    def cycle_day() -> str:
        return _t(
            "<b>Какой сейчас день менструального цикла?</b>\n\n"
            "Выбери один из вариантов:",

            "<b>Hozir hayz siklining nechanchi kuni?</b>\n\n"
            "Variantlardan birini tanla:",
        )

    @staticmethod
    def intake_time() -> str:
        return _t(
            "<b>Во сколько тебе удобно принимать таблетку?</b>\n\n"
            "Выбери время:",

            "<b>Senga dori ichish uchun qaysi vaqt qulay?</b>\n\n"
            "Vaqtni tanla:",
        )

    @staticmethod
    def rules(intake_time_str: str, start_date_str: str) -> str:
        if _lang == "ru":
            return (
                "<b>Правила программы</b>\n\n"
                f"<b>Ты начинаешь с {start_date_str} в {intake_time_str}</b>\n\n"
                "Каждый день в это время ты должна:\n"
                "1. Выпить таблетку\n"
                "2. Снять видео как ты это делаешь\n"
                "3. Отправить видео боту\n\n"
                "<b>Почему важно пить таблетку:</b>\n"
                "Таблетка регулирует гормональный фон. "
                "Пропуск или опоздание может вызвать кровотечение "
                "и вся проделанная работа будет напрасной.\n\n"
                "<b>Опоздания:</b>\n"
                "— Допускается опоздание до 30 минут\n"
                "— После 3-х опозданий — снятие с программы\n"
                "— Если не отправишь видео в течение 2 часов — снятие с программы"
            )
        return (
            "<b>Dastur qoidalari</b>\n\n"
            f"<b>Sen {start_date_str} kuni soat {intake_time_str} da boshlaysan</b>\n\n"
            "Har kuni shu vaqtda sen:\n"
            "1. Dori tabletkasini ichishing kerak\n"
            "2. Buni qanday qilayotganingni videoga olishing kerak\n"
            "3. Videoni botga yuborishing kerak\n\n"
            "<b>Dori ichish nima uchun muhim:</b>\n"
            "Dori gormon fonini tartibga soladi. "
            "Tashlab ketish yoki kechikish qon ketishiga olib kelishi mumkin "
            "va barcha qilingan ish befoyda bo'ladi.\n\n"
            "<b>Kechikishlar:</b>\n"
            "— 30 daqiqagacha kechikishga ruxsat beriladi\n"
            "— 3 ta kechikishdan keyin — dasturdan chiqarish\n"
            "— Agar 2 soat ichida video yubormasan — dasturdan chiqarish"
        )

    @staticmethod
    def tutorial_video_caption() -> str:
        if _lang == "ru":
            return (
                "📹 <b>Как снимать видео-кружок</b>\n\n"
                "1. Открой чат с ботом\n"
                "2. Справа внизу нажми на 🎤 чтобы переключить на 📷\n"
                "3. Зажми 📷 и подними палец вверх чтобы начать запись\n"
                "4. Покажи блистер и таблетку\n"
                "5. Покажи как глотаешь\n\n"
                'Подробнее смотри <a href="https://www.youtube.com/shorts/z7QUbsttDy0">видео-урок</a>\n\n'
                "Потренируйся перед отправкой, чтобы уверенно снимать! 💪"
            )
        return (
            "📹 <b>Video-doirani qanday suratga olish kerak</b>\n\n"
            "1. Bot bilan chatni och\n"
            "2. O'ng pastda 🎤 ni bosib 📷 ga o'tkaz\n"
            "3. 📷 ni bosib tur va yozishni boshlash uchun barmog'ingni yuqoriga ko'tar\n"
            "4. Blisterni va tabletkani ko'rsat\n"
            "5. Qanday yutayotganingni ko'rsat\n\n"
            'Batafsil <a href="https://www.youtube.com/shorts/z7QUbsttDy0">video-darsni</a> ko\'r\n\n'
            "Yuborishdan oldin mashq qil, ishonchli suratga olish uchun! 💪"
        )

    @staticmethod
    def bot_instructions() -> str:
        if _lang == "ru":
            return (
                "<b>Как работает бот</b>\n\n"
                "Каждый день:\n"
                "— За 1 час до приёма придёт напоминание\n"
                "— За 10 минут — ещё одно напоминание\n"
                "— Ты снимаешь видео и отправляешь его сюда\n"
                "— Бот проверит видео и засчитает день\n\n"
                "<b>Требования к видео:</b>\n"
                "— Ты должна быть в кадре\n"
                "— Покажи блистер упаковки\n"
                "— Таблетка должна быть видна\n"
                "— Покажи как глотаешь таблетку\n\n"
                "<b>Пересъёмка:</b>\n"
                "— Если видео не прошло проверку, менеджер может попросить переснять\n"
                "— Ты получишь сообщение с дедлайном для пересъёмки\n"
                "— Отправь новое видео до указанного времени\n\n"
                "<b>Апелляция:</b>\n"
                "— У тебя есть 2 апелляции на всю программу\n"
                "— Если не смогла отправить видео — сними обычное видео на телефон и сохрани его\n"
                "— При подаче апелляции отправь это видео с объяснением причины\n"
                "— Каждую апелляцию рассматривает менеджер\n\n"
                "Программа длится <b>21 день</b>. Удачи!"
            )
        return (
            "<b>Bot qanday ishlaydi</b>\n\n"
            "Har kuni:\n"
            "— Qabul qilishdan 1 soat oldin eslatma keladi\n"
            "— 10 daqiqa oldin — yana bir eslatma\n"
            "— Sen video olasan va uni shu yerga yuborasan\n"
            "— Bot videoni tekshiradi va kunni hisoblaydi\n\n"
            "<b>Videoga talablar:</b>\n"
            "— Sen kadrda bo'lishing kerak\n"
            "— Blisterni ko'rsat\n"
            "— Tabletka ko'rinishi kerak\n"
            "— Tabletkani qanday yutayotganingni ko'rsat\n\n"
            "<b>Qayta suratga olish:</b>\n"
            "— Agar video tekshiruvdan o'tmasa, menejer qayta suratga olishni so'rashi mumkin\n"
            "— Sen qayta suratga olish muddati bilan xabar olasan\n"
            "— Yangi videoni ko'rsatilgan vaqtgacha yubor\n\n"
            "<b>Apellyatsiya:</b>\n"
            "— Butun dastur davomida senga 2 ta apellyatsiya berilgan\n"
            "— Agar video yubora olmagan bo'lsang — telefonga oddiy video ol va saqlap qo'y\n"
            "— Apellyatsiya berishda bu videoni sababini tushuntirish bilan yubor\n"
            "— Har bir apellyatsiyani menejer ko'rib chiqadi\n\n"
            "Dastur <b>21 kun</b> davom etadi. Omad!"
        )

    # --- Топик (менеджер видит — всегда русский) ---

    @staticmethod
    def topic_name(
        last_name: str,
        first_name: str,
        patronymic: str | None,
        manager_name: str,
        current_day: int,
        total_days: int,
    ) -> str:
        first_initial = first_name[0] + "." if first_name else ""
        patron_initial = ""
        if patronymic:
            # Remove "kizi"/"qizi" suffix before taking initial
            parts = patronymic.split()
            clean = [p for p in parts if p.lower() not in ("kizi", "qizi")]
            if clean:
                patron_initial = clean[0][0] + "."
        initials = first_initial + patron_initial
        name_part = f"{last_name} {initials}" if initials else last_name
        return f"{name_part} ({manager_name}) {current_day}/{total_days}"

    @staticmethod
    def registration_card(
        full_name: str,
        cycle_day: int,
        intake_time_str: str,
        start_date_str: str,
        telegram_username: str | None,
        telegram_id: int,
    ) -> str:
        contact = f"@{telegram_username}" if telegram_username else f"tg://user?id={telegram_id}"
        return (
            "<b>📋 Регистрация</b>\n\n"
            f"👤 ФИО: {escape(full_name)}\n"
            f"📅 День цикла: {cycle_day}\n"
            f"⏰ Время приёма: {intake_time_str}\n"
            f"🗓 Дата начала: {start_date_str}\n"
            f"💬 Telegram: {escape(contact)}"
        )


class VideoTemplates:
    @staticmethod
    def processing() -> str:
        return _t(
            "Подожди, смотрю как ты пила...",
            "Kut, qanday ichganingni ko'ryapman...",
        )

    @staticmethod
    def approved(day: int, total_days: int) -> str:
        return _t(
            f"Молодец! День {day}/{total_days} засчитан \U0001f7e2",
            f"Barakalla! {day}/{total_days}-kun qabul qilindi \U0001f7e2",
        )

    @staticmethod
    def pending_review() -> str:
        return _t(
            "Я не уверен что на видео ты пьёшь таблетку. "
            "Отправил менеджеру на проверку, подожди",
            "Videoda tabletka ichayotganingga ishonchim komil emas. "
            "Menejerga tekshirishga yubordim, kut",
        )

    # ── Topic (менеджер — всегда русский) ──

    @staticmethod
    def topic_approved(day: int, total_days: int) -> str:
        return f"{day}/{total_days} выпила \U0001f7e2"

    @staticmethod
    def topic_pending_review(day: int, total_days: int, reason: str) -> str:
        return f"{day}/{total_days} — AI не уверен: {reason}"

    # ── Girl private chat ──

    @staticmethod
    def no_active_course() -> str:
        return _t("У тебя нет активной программы", "Senda faol dastur yo'q")

    @staticmethod
    def already_sent_today() -> str:
        return _t(
            "Ты уже отправила видео сегодня",
            "Sen bugun allaqachon video yuborgansan",
        )

    @staticmethod
    def window_early(open_time: str) -> str:
        return _t(
            f"Рано, окно приёма видео откроется в {open_time}",
            f"Erta, video qabul qilish oynasi soat {open_time} da ochiladi",
        )

    @staticmethod
    def window_closed() -> str:
        return _t("Окно приёма закрыто", "Qabul oynasi yopilgan")

    @staticmethod
    def send_video() -> str:
        return _t(
            "Отправь видео, сейчас время приёма",
            "Video yubor, hozir qabul vaqti",
        )

    @staticmethod
    def video_only() -> str:
        return _t(
            "Я принимаю только видео во время приёма таблетки",
            "Men faqat tabletka ichish vaqtida video qabul qilaman",
        )

    @staticmethod
    def course_completed(total_days: int) -> str:
        return _t(
            f"Поздравляю! Ты прошла программу {total_days} дней!",
            f"Tabriklayman! Sen {total_days} kunlik dasturni tugatding!",
        )

    @staticmethod
    def ai_error() -> str:
        return _t(
            "Ошибка проверки видео, попробуй через минуту",
            "Videoni tekshirishda xatolik, bir daqiqadan keyin urinib ko'r",
        )

    # ── Phase 2.2: Manager confirm / reject ──

    @staticmethod
    def topic_confirmed(day: int, total_days: int) -> str:
        return f"{day}/{total_days} выпила (подтверждено менеджером) \U0001f7e2"

    @staticmethod
    def private_confirmed(day: int, total_days: int) -> str:
        return _t(
            f"Молодец! Менеджер подтвердил, день {day}/{total_days} засчитан \U0001f7e2",
            f"Barakalla! Menejer tasdiqladi, {day}/{total_days}-kun qabul qilindi \U0001f7e2",
        )

    @staticmethod
    def topic_rejected() -> str:
        return "Программа завершена. Видео отклонено менеджером"

    @staticmethod
    def private_rejected(manager_name: str) -> str:
        safe = escape(manager_name)
        return _t(
            "Менеджер отклонил видео. На нём не видно что ты пьёшь таблетку. "
            f"Программа закончена. Обратись к менеджеру: {safe}",
            "Menejer videoni rad etdi. Unda tabletka ichayotganing ko'rinmaydi. "
            f"Dastur tugadi. Menejeringga murojaat qil: {safe}",
        )

    @staticmethod
    def review_already_handled() -> str:
        return "Это видео уже проверено"

    # ── Phase 2.3: Reshoot ──

    @staticmethod
    def topic_reshoot(day: int, deadline_str: str, remaining: str) -> str:
        return f"🔄 День {day} — переснять видео. Дедлайн: {deadline_str} (осталось {remaining})"

    @staticmethod
    def private_reshoot(deadline_str: str, remaining: str) -> str:
        return _t(
            "🔄 Менеджер просит переснять видео. "
            f"Сними новое видео и отправь сюда до {deadline_str} (осталось {remaining})",
            "🔄 Menejer videoni qayta olishni so'ramoqda. "
            f"Yangi video ol va shu yerga {deadline_str} gacha yubor (qoldi {remaining})",
        )

    @staticmethod
    def reshoot_expired() -> str:
        return _t(
            "Время на пересъёмку истекло",
            "Qayta suratga olish vaqti tugadi",
        )

    # ── Phase 2.4: Manager notifications (менеджер — всегда русский) ──

    @staticmethod
    def manager_review_dm(
        girl_name: str, deadline_str: str, remaining: str,
        topic_id: int | None, group_id: int | None,
    ) -> str:
        name_part = _topic_link(girl_name, topic_id, group_id)
        return f"📹 Проверь видео {name_part}\n⏰ Дедлайн: {deadline_str} (осталось {remaining})"

    @staticmethod
    def general_review_request(
        manager_name: str, girl_name: str, deadline_str: str, remaining: str,
        topic_id: int | None, group_id: int | None,
    ) -> str:
        name_part = _topic_link(girl_name, topic_id, group_id)
        return f"📹 {escape(manager_name)}, проверь видео {name_part}\n⏰ Дедлайн: {deadline_str} (осталось {remaining})"

    # ── Phase 3: Late strikes ──

    @staticmethod
    def approved_late(
        day: int, total_days: int, strike: int, max_strikes: int,
    ) -> str:
        remaining = max_strikes - strike
        return _t(
            f"День {day}/{total_days} засчитан \U0001f7e2\n\n"
            f"\u26a0\ufe0f Но ты опоздала! Опоздание {strike}/{max_strikes}. "
            f"Ещё {remaining} — сниму с программы. "
            "Пожалуйста не опаздывай — это важно для результата",

            f"{day}/{total_days}-kun qabul qilindi \U0001f7e2\n\n"
            f"\u26a0\ufe0f Lekin kechikding! Kechikish {strike}/{max_strikes}. "
            f"Yana {remaining} ta — dasturdan chiqaraman. "
            "Iltimos kechikma — bu natija uchun muhim",
        )

    @staticmethod
    def private_late_removed(late_dates_formatted: str, manager_name: str) -> str:
        safe = escape(manager_name)
        return _t(
            f"Ты опоздала слишком много раз:\n{late_dates_formatted}\n\n"
            f"Программа закончена. Обратись к менеджеру: {safe}",

            f"Sen juda ko'p marta kechikding:\n{late_dates_formatted}\n\n"
            f"Dastur tugadi. Menejeringga murojaat qil: {safe}",
        )

    # ── Topic/general (менеджер — всегда русский) ──

    @staticmethod
    def topic_late_warning(strike: int, max_strikes: int) -> str:
        remaining = max_strikes - strike
        return f"\u26a0\ufe0f Опоздание {strike}/{max_strikes}. Осталось {remaining} — сниму с программы"

    @staticmethod
    def topic_late_removed(late_dates_formatted: str) -> str:
        return f"Снята с программы. Опоздания:\n{late_dates_formatted}"

    @staticmethod
    def general_late_removed(
        girl_name: str, topic_id: int | None, group_id: int | None,
    ) -> str:
        name = _topic_link(girl_name, topic_id, group_id)
        return f"❌ {name} снята — опоздала слишком много раз"

    @staticmethod
    def general_manager_rejected(
        manager_name: str, girl_name: str,
        topic_id: int | None, group_id: int | None,
    ) -> str:
        name = _topic_link(girl_name, topic_id, group_id)
        return f"❌ {name} снята — {escape(manager_name)} отклонил видео"

    @staticmethod
    def format_late_dates(late_dates: list[str]) -> str:
        """Format ISO dates to human-readable list."""
        lines = []
        for i, iso_date in enumerate(late_dates, 1):
            try:
                dt = datetime.fromisoformat(iso_date).astimezone(TASHKENT_TZ)
                lines.append(f"{i}. {dt.strftime('%d.%m %H:%M')}")
            except (ValueError, TypeError):
                lines.append(f"{i}. {iso_date}")
        return "\n".join(lines)

    # ── Course completion ──

    @staticmethod
    def private_completed(total_days: int) -> str:
        return _t(
            f"\U0001f389 Поздравляю! Ты прошла программу {total_days} дней!\n\n"
            "Спасибо за дисциплину. Желаю здоровья!",

            f"\U0001f389 Tabriklayman! Sen {total_days} kunlik dasturni tugatding!\n\n"
            "Intizoming uchun rahmat. Sog'lik tilayman!",
        )

    @staticmethod
    def topic_completed(day: int, total_days: int) -> str:
        return f"{day}/{total_days} \u2014 Программа завершена! \u2705"


class AppealTemplates:
    """Templates for the appeal flow (Phase 5)."""

    MAX_APPEALS = 2

    # ── Girl's private chat ──

    @staticmethod
    def ask_video() -> str:
        return _t(
            "Отправь видео-доказательство того, что ты пила таблетку",
            "Tabletka ichganingni tasdiqlovchi video yubor",
        )

    @staticmethod
    def ask_text() -> str:
        return _t(
            "Теперь напиши текстом, почему считаешь решение несправедливым",
            "Endi matn bilan yoz, nima uchun qaror adolatsiz deb hisoblaysan",
        )

    @staticmethod
    def video_only() -> str:
        return _t("Отправь видео", "Video yubor")

    @staticmethod
    def text_only() -> str:
        return _t("Напиши текстом", "Matn bilan yoz")

    @staticmethod
    def appeal_submitted() -> str:
        return _t(
            "Апелляция отправлена менеджеру на рассмотрение. Жди ответа",
            "Apellyatsiya menejerga ko'rib chiqish uchun yuborildi. Javob kut",
        )

    @staticmethod
    def appeal_accepted(appeal_count: int) -> str:
        if appeal_count == 1:
            return _t(
                "Апелляция принята! Продолжай программу.\n\n"
                "Имей в виду — у тебя осталась ещё одна попытка апелляции",

                "Apellyatsiya qabul qilindi! Dasturni davom ettir.\n\n"
                "E'tiborga ol — senda yana bitta apellyatsiya imkoniyati qoldi",
            )
        return _t(
            "Апелляция принята! Продолжай программу.\n\n"
            "Но это была последняя возможность. "
            "Следующее нарушение — окончательное снятие",

            "Apellyatsiya qabul qilindi! Dasturni davom ettir.\n\n"
            "Lekin bu oxirgi imkoniyat edi. "
            "Keyingi qoidabuzarlik — yakuniy chiqarish",
        )

    @staticmethod
    def appeal_declined(manager_name: str) -> str:
        safe = escape(manager_name)
        return _t(
            "Менеджер отклонил апелляцию. Программа окончательно закончена. "
            f"Обратись к менеджеру: {safe}",
            "Menejer apellyatsiyani rad etdi. Dastur yakuniy tugadi. "
            f"Menejeringga murojaat qil: {safe}",
        )

    # ── Alerts (girl sees as popup) ──

    @staticmethod
    def appeal_already_handled() -> str:
        return "Эта апелляция уже рассмотрена"

    @staticmethod
    def no_active_appeal() -> str:
        return _t("Нет активной апелляции", "Faol apellyatsiya yo'q")

    @staticmethod
    def appeal_race_condition() -> str:
        return _t(
            "Ошибка: попробуй ещё раз",
            "Xatolik: qaytadan urinib ko'r",
        )

    # ── Topic messages (менеджер — всегда русский) ──

    @staticmethod
    def topic_appeal_submitted(appeal_text: str) -> str:
        return f"Апелляция:\n\n{escape(appeal_text)}"

    @staticmethod
    def topic_appeal_accepted(appeal_count: int, max_appeals: int) -> str:
        return (
            f"Апелляция принята ({appeal_count}/{max_appeals}). "
            "Продолжает программу"
        )

    @staticmethod
    def topic_appeal_declined(appeal_count: int, max_appeals: int) -> str:
        return (
            f"Апелляция отклонена ({appeal_count}/{max_appeals}). "
            "Программа окончательно закончена"
        )

    # ── General topic / manager notifications (менеджер — всегда русский) ──

    @staticmethod
    def manager_appeal_dm(
        girl_name: str, deadline_str: str, remaining: str,
        topic_id: int | None, group_id: int | None,
    ) -> str:
        name_part = _topic_link(girl_name, topic_id, group_id)
        return (
            f"⚖️ Проверь апелляцию {name_part}\n"
            f"⏰ Дедлайн: {deadline_str} (осталось {remaining}), иначе автоотказ"
        )

    @staticmethod
    def general_appeal_request(
        manager_name: str, girl_name: str, deadline_str: str, remaining: str,
        topic_id: int | None, group_id: int | None,
    ) -> str:
        name_part = _topic_link(girl_name, topic_id, group_id)
        return (
            f"⚖️ {escape(manager_name)}, проверь апелляцию {name_part}\n"
            f"⏰ Дедлайн: {deadline_str} (осталось {remaining}), иначе автоотказ"
        )


class WorkerTemplates:
    """Templates for worker notifications (Phase 4)."""

    # ── Reminders (girl's private chat) ──

    @staticmethod
    def reminder_1h(intake_time: str) -> str:
        return _t(
            f"Через час пора пить таблетку. Время приёма: {intake_time}",
            f"Bir soatdan keyin dori ichish vaqti. Qabul vaqti: {intake_time}",
        )

    @staticmethod
    def reminder_10min(intake_time: str) -> str:
        return _t(
            f"Через 10 минут пора пить таблетку! Время приёма: {intake_time}",
            f"10 daqiqadan keyin dori ichish vaqti! Qabul vaqti: {intake_time}",
        )

    # ── Strike +30 min ──

    @staticmethod
    def strike_warning(strike: int, max_strikes: int) -> str:
        remaining = max_strikes - strike
        return _t(
            f"Выпей скорей, у тебя уже опоздание!\n\n"
            f"Опоздание {strike}/{max_strikes}. "
            f"Ещё {remaining} — сниму с программы. "
            "Если не отправишь видео в течение 2 часов — снятие с программы",

            f"Tezroq ich, sen allaqachon kechikding!\n\n"
            f"Kechikish {strike}/{max_strikes}. "
            f"Yana {remaining} ta — dasturdan chiqaraman. "
            "Agar 2 soat ichida video yubormasan — dasturdan chiqarish",
        )

    # ── Auto-removal +2h (girl's private chat) ──

    @staticmethod
    def removal_no_video(manager_name: str) -> str:
        safe = escape(manager_name)
        return _t(
            "Ты не отправила видео в течение 2 часов. "
            f"Программа закончена. Обратись к менеджеру: {safe}",
            "Sen 2 soat ichida video yubormading. "
            f"Dastur tugadi. Menejeringga murojaat qil: {safe}",
        )

    # ── Topic/general (менеджер — всегда русский) ──

    @staticmethod
    def topic_removal_no_video() -> str:
        return "Снята с программы. Не отправила видео за 2 часа"

    @staticmethod
    def general_removal_no_video(
        girl_name: str, topic_id: int | None, group_id: int | None,
    ) -> str:
        name = _topic_link(girl_name, topic_id, group_id)
        return f"❌ {name} снята — не отправила видео за 2 часа"

    # ── Review deadline expired (girl's private chat) ──

    @staticmethod
    def removal_review_expired(manager_name: str) -> str:
        safe = escape(manager_name)
        return _t(
            "Менеджер не подтвердил видео в срок. "
            f"Программа закончена. Обратись к менеджеру: {safe}",
            "Menejer videoni o'z vaqtida tasdiqlamadi. "
            f"Dastur tugadi. Menejeringga murojaat qil: {safe}",
        )

    @staticmethod
    def topic_removal_review_expired() -> str:
        return "Снята с программы. Менеджер не проверил видео вовремя"

    @staticmethod
    def general_removal_review_expired(
        manager_name: str, girl_name: str,
        topic_id: int | None, group_id: int | None,
    ) -> str:
        name = _topic_link(girl_name, topic_id, group_id)
        return f"❌ {name} снята — {escape(manager_name)} не проверил видео вовремя"

    # ── Reshoot deadline expired (girl's private chat) ──

    @staticmethod
    def removal_reshoot_expired(manager_name: str) -> str:
        safe = escape(manager_name)
        return _t(
            "Ты не пересняла видео в срок. "
            f"Программа закончена. Обратись к менеджеру: {safe}",
            "Sen videoni o'z vaqtida qayta olmading. "
            f"Dastur tugadi. Menejeringga murojaat qil: {safe}",
        )

    @staticmethod
    def topic_removal_reshoot_expired() -> str:
        return "Снята с программы. Не пересняла видео вовремя"

    @staticmethod
    def general_removal_reshoot_expired(
        girl_name: str, topic_id: int | None, group_id: int | None,
    ) -> str:
        name = _topic_link(girl_name, topic_id, group_id)
        return f"❌ {name} снята — не пересняла видео вовремя"

    # ── Appeal deadline expired ──

    @staticmethod
    def removal_appeal_expired(manager_name: str) -> str:
        safe = escape(manager_name)
        return _t(
            "Время апелляции истекло. "
            f"Программа окончательно закончена. Обратись к менеджеру: {safe}",
            "Apellyatsiya muddati tugadi. "
            f"Dastur yakuniy tugadi. Menejeringga murojaat qil: {safe}",
        )

    @staticmethod
    def topic_appeal_expired() -> str:
        return "Апелляция автоматически отклонена (менеджер не ответил вовремя)"

    @staticmethod
    def general_appeal_expired(
        manager_name: str, girl_name: str,
        topic_id: int | None, group_id: int | None,
    ) -> str:
        name = _topic_link(girl_name, topic_id, group_id)
        return f"❌ Апелляция {name} отклонена — {escape(manager_name)} не ответил вовремя"


class CardTemplates:
    """Templates for registration card buttons (Extend / Complete)."""

    @staticmethod
    def already_handled() -> str:
        return "Действие уже выполнено"

    @staticmethod
    def course_not_active() -> str:
        return "Курс не активен"

    # ── Extend ──

    @staticmethod
    def already_extended() -> str:
        return "Курс уже продлён"

    @staticmethod
    def topic_extended(old_total: int, new_total: int) -> str:
        return f"Курс продлён: {old_total} → {new_total} дней"

    @staticmethod
    def private_extended() -> str:
        return _t(
            "Твой курс продлён ещё на 21 день",
            "Kursing yana 21 kunga uzaytirildi",
        )

    # ── Complete ──

    @staticmethod
    def topic_completed_early(current_day: int, total_days: int) -> str:
        return (
            f"Программа завершена досрочно "
            f"(день {current_day}/{total_days})"
        )

    @staticmethod
    def private_completed_early() -> str:
        return _t(
            "Твоя программа завершена. Спасибо за участие!",
            "Dasturing tugadi. Ishtirok etganing uchun rahmat!",
        )
