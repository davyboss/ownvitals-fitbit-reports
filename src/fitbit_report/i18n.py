from __future__ import annotations

from typing import Any, Literal


Locale = Literal["en", "ru"]
SUPPORTED_LOCALES: tuple[Locale, ...] = ("en", "ru")


_MESSAGES: dict[str, dict[Locale, Any]] = {
    "main_menu.labels": {
        "en": (
            "Journal",
            "Check-in",
            "Ask",
            "Reports",
            "More",
        ),
        "ru": (
            "Дневник",
            "Чек-ин",
            "Спросить",
            "Отчёты",
            "Ещё",
        ),
    },
    "start": {
        "en": (
            "Hi! This is your personal health and productivity assistant.\n\n"
            "I combine Google Health data, journal entries, and productivity "
            "check-ins. Reports are saved to Obsidian and delivered here.\n\n"
            "Choose a section below to get started."
        ),
        "ru": (
            "Привет! Это твой личный health и productivity-ассистент.\n\n"
            "Я объединяю Google Health, дневник и оценки продуктивности, "
            "а отчёты сохраняю в Obsidian и присылаю сюда.\n\n"
            "Выбирай нужный раздел кнопками ниже."
        ),
    },
    "help": {
        "en": (
            "How to use the bot:\n\n"
            "Journal — meals, caffeine, nicotine, workouts, mood, and notes.\n"
            "Check-in — a short morning baseline and an evening workday review.\n"
            "Reports — read existing reports without generating a new one.\n"
            "More — entries, sync, Claude usage, status, and help.\n\n"
            "Commands are also available:\n"
            "/log caffeine 150mg at 10:30\n"
            "/log nicotine snus 12mg\n"
            "/log masturbation\n"
            "/mealtime breakfast 08:30 — save a meal time\n"
            "/fatsecret — connect FatSecret and enable nutrition imports\n"
            "/training — describe a workout or attach a photo\n"
            "/checkin evening energy=7 quality=8 focus=6\n"
            "/ask should I train today?\n"
            "/entries — show recent entries\n"
            "/edit 12 note=corrected text at=18:30\n"
            "/delete 12\n"
            "/editcheckin ID energy=7 focus=8\n"
            "/deletecheckin ID\n"
            "/usage — show this month's Claude usage\n"
            "/sync"
        ),
        "ru": (
            "Как пользоваться ботом:\n\n"
            "Дневник — питание, кофеин, никотин, тренировки, настроение и заметки.\n"
            "Чек-ин — утром базовые показатели, вечером результаты рабочего дня.\n"
            "Отчёты — просмотр уже созданных отчётов без новой генерации.\n"
            "Ещё — записи, синхронизация, расход Claude, статус и помощь.\n\n"
            "Команды тоже работают:\n"
            "/log caffeine 150mg at 10:30\n"
            "/log nicotine snus 12mg\n"
            "/log masturbation\n"
            "/mealtime breakfast 08:30 — сохранить время приёма пищи\n"
            "/fatsecret — подключить FatSecret и включить автоимпорт питания\n"
            "/training — прислать тренировку в свободном формате или фото\n"
            "/checkin evening energy=7 quality=8 focus=6\n"
            "/ask стоит ли сегодня тренироваться?\n"
            "/entries — последние записи\n"
            "/edit 12 note=исправленный текст at=18:30\n"
            "/delete 12\n"
            "/editcheckin ID energy=7 focus=8\n"
            "/deletecheckin ID\n"
            "/usage — расход токенов Claude за текущий месяц\n"
            "/sync"
        ),
    },
    "status": {
        "en": (
            "Application status:\n\n"
            "✅ Telegram bot is running\n"
            "🗄️ Database: {database_url}\n"
            "📁 Obsidian: {obsidian_vault}\n"
            "🌍 Time zone: {timezone}"
        ),
        "ru": (
            "Статус приложения:\n\n"
            "✅ Telegram-бот запущен\n"
            "🗄️ База данных: {database_url}\n"
            "📁 Obsidian: {obsidian_vault}\n"
            "🌍 Часовой пояс: {timezone}"
        ),
    },
    "usage": {
        "en": (
            "📈 Claude usage\n\n"
            "Period: {start} — {end}\n"
            "Calls: {calls}\n"
            "Input tokens: {input_tokens:,}\n"
            "Output tokens: {output_tokens:,}\n"
            "Cache-read tokens: {cache_read_tokens:,}\n"
            "Estimated API cost: ${estimated_cost:.6f}\n\n"
            "Estimated calls: {estimated_calls}\n\n"
            "This is an API-equivalent estimate based on the configured model rates. "
            "A Claude Pro subscription is billed separately and does not charge per token."
        ),
        "ru": (
            "📈 Расход Claude\n\n"
            "Период: {start} — {end}\n"
            "Вызовов: {calls}\n"
            "Входные токены: {input_tokens:,}\n"
            "Выходные токены: {output_tokens:,}\n"
            "Кэш прочитан: {cache_read_tokens:,}\n"
            "Оценка API-стоимости: ${estimated_cost:.6f}\n\n"
            "Приблизительных вызовов: {estimated_calls}\n\n"
            "Это расчёт эквивалентной стоимости API по тарифу модели. "
            "Подписка Claude Pro отдельно по токенам не списывается."
        ),
    },
    "menu.journal_prompt": {"en": "What would you like to log?", "ru": "Что хочешь записать?"},
    "menu.productivity_prompt": {"en": "Choose a check-in type:", "ru": "Выбери тип check-in:"},
    "menu.archive_prompt": {"en": "Which archive would you like to open?", "ru": "Какой архив открыть?"},
    "menu.more_prompt": {"en": "More options:", "ru": "Другие разделы:"},
    "menu.sync_prompt": {
        "en": "Sync will fetch fresh Google Health data. Start now?",
        "ru": "Синхронизация загрузит свежие данные Google Health. Запустить?",
    },
    "menu.ask_hint": {
        "en": "Send a question with /ask, for example: should I train today?",
        "ru": "Напиши вопрос командой /ask, например: стоит ли сегодня тренироваться?",
    },
    "menu.entries_hint": {
        "en": "Use /entries to see recent entries, /edit ID ... to change one, or /delete ID to remove one.",
        "ru": "Последние записи доступны командой /entries. Для изменения: /edit ID ..., для удаления: /delete ID.",
    },
    "menu.edit_entries_loading": {"en": "Opening your entries…", "ru": "Открываю список записей..."},
    "menu.usage_loading": {
        "en": "Showing Claude usage for the current month…",
        "ru": "Показываю расход Claude за текущий месяц...",
    },
    "menu.ask_next": {
        "en": (
            "Send your question in the next message or attach a photo with a caption.\n"
            "For example: should I train today?"
        ),
        "ru": (
            "Напиши вопрос следующим сообщением или прикрепи фотографию с подписью.\n"
            "Например: стоит ли мне сегодня тренироваться?"
        ),
    },
    "usage.unavailable": {
        "en": "Claude usage will be available after the application is updated.",
        "ru": "Учёт расхода Claude будет доступен после обновления приложения.",
    },
    "button.meal_time": {"en": "Meal time", "ru": "Время приёма пищи"},
    "button.add_food": {"en": "Add food", "ru": "Добавить еду"},
    "button.caffeine": {"en": "Caffeine", "ru": "Кофеин"},
    "button.fatsecret": {"en": "FatSecret import", "ru": "FatSecret автоимпорт"},
    "button.nicotine": {"en": "Nicotine", "ru": "Никотин"},
    "button.workout": {"en": "Workout", "ru": "Тренировка"},
    "button.alcohol": {"en": "Alcohol", "ru": "Алкоголь"},
    "button.mood": {"en": "Mood", "ru": "Настроение"},
    "button.stress": {"en": "Stress", "ru": "Стресс"},
    "button.note": {"en": "Note", "ru": "Заметка"},
    "button.illness": {"en": "Symptoms", "ru": "Самочувствие"},
    "button.private_event": {"en": "Private event", "ru": "Личное событие"},
    "button.main_menu": {"en": "Main menu", "ru": "Главное меню"},
    "button.daily_reports": {"en": "Daily reports", "ru": "Дневные отчёты"},
    "button.weekly_reports": {"en": "Weekly reports", "ru": "Недельные отчёты"},
    "button.monthly_reports": {"en": "Monthly reports", "ru": "Месячные отчёты"},
    "button.morning": {"en": "Morning", "ru": "Утренний"},
    "button.evening": {"en": "Evening", "ru": "Вечерний"},
    "button.sync_start": {"en": "Start", "ru": "Запустить"},
    "button.cancel": {"en": "Cancel", "ru": "Отмена"},
    "button.breakfast": {"en": "Breakfast", "ru": "Завтрак"},
    "button.lunch": {"en": "Lunch", "ru": "Обед"},
    "button.dinner": {"en": "Dinner", "ru": "Ужин"},
    "button.snack": {"en": "Snack", "ru": "Перекус"},
    "button.other": {"en": "Other", "ru": "Другое"},
    "button.now": {"en": "Now", "ru": "Сейчас"},
    "button.custom_time": {"en": "Choose a time", "ru": "Указать время"},
    "button.correct": {"en": "Looks right", "ru": "Всё верно"},
    "button.edit": {"en": "Edit", "ru": "Исправить"},
    "button.snus": {"en": "Snus", "ru": "Снюс"},
    "button.cigarettes": {"en": "Cigarettes", "ru": "Сигареты"},
    "button.vape": {"en": "Vape", "ru": "Вейп"},
    "button.import_today": {"en": "Import today", "ru": "Импортировать сегодня"},
    "button.connect_account": {"en": "Connect account", "ru": "Подключить аккаунт"},
    "button.reconnect": {"en": "Reconnect", "ru": "Переподключить"},
    "button.journal": {"en": "Journal", "ru": "Дневник"},
    "button.sonnet": {"en": "Sonnet — everyday question", "ru": "Sonnet — обычный вопрос"},
    "button.opus": {"en": "Opus — deeper analysis", "ru": "Opus — сложный анализ"},
    "button.archive": {"en": "Archive", "ru": "Архив"},
    "button.skip": {"en": "Skip", "ru": "Пропустить"},
    "button.delete": {"en": "Delete", "ru": "Удалить"},
    "button.my_entries": {"en": "My entries", "ru": "Мои записи"},
    "button.edit_entries": {"en": "Edit entries", "ru": "Редактировать записи"},
    "button.sync": {"en": "Sync", "ru": "Синхронизация"},
    "button.usage": {"en": "Claude usage", "ru": "Расход Claude"},
    "button.status": {"en": "Status", "ru": "Статус"},
    "button.help": {"en": "Help", "ru": "Помощь"},
    "button.more": {"en": "More", "ru": "Ещё"},
    "checkin.energy": {"en": "Energy", "ru": "Энергия"},
    "checkin.sleep_quality": {"en": "Sleep quality", "ru": "Качество сна"},
    "checkin.mood": {"en": "Mood", "ru": "Настроение"},
    "checkin.stress": {"en": "Stress", "ru": "Стресс"},
    "checkin.persistence": {"en": "Persistence", "ru": "Упорство"},
    "checkin.quality": {"en": "Work quality", "ru": "Качество работы"},
    "checkin.focus": {"en": "Focus", "ru": "Фокус"},
    "common.time_prompt": {"en": "When was this?", "ru": "Когда это было?"},
    "common.time_format": {
        "en": "Enter a time as HH:MM, for example 13:30.",
        "ru": "Напиши время в формате HH:MM, например 13:30.",
    },
    "common.saved": {"en": "Saved to your journal.", "ru": "Записал в дневник."},
    "common.save_failed": {
        "en": "❌ I couldn't save this entry. Please try again.",
        "ru": "❌ Не получилось сохранить запись. Попробуй ещё раз.",
    },
    "common.cancelled": {"en": "Entry cancelled.", "ru": "Запись отменена."},
    "common.photo_save_failed": {
        "en": "❌ I couldn't save the photo.",
        "ru": "❌ Не получилось сохранить фотографию.",
    },
    "journal.nicotine_prompt": {"en": "What did you use?", "ru": "Что именно употреблял?"},
    "journal.meal_type_prompt": {"en": "Which meal was this?", "ru": "Какой это приём пищи?"},
    "journal.amount_prompt": {
        "en": "Enter an amount, such as 1pc or 1pc 50mg.",
        "ru": "Введи количество. Можно написать 1шт или сразу 1шт 50мг.",
    },
    "journal.caffeine_prompt": {
        "en": "Enter the caffeine dose, for example 150mg.",
        "ru": "Введи дозу кофеина, например: 150mg.",
    },
    "journal.training_prompt": {
        "en": "Enter duration and intensity: duration=45 intensity=7",
        "ru": "Напиши длительность и интенсивность: duration=45 intensity=7",
    },
    "journal.note_prompt": {
        "en": "Send a short note in one message.",
        "ru": "Напиши короткую заметку одним сообщением.",
    },
    "journal.amount_format": {
        "en": "Use an amount such as 150mg, 12mg, or 1pc 50mg for nicotine.",
        "ru": "Формат количества: 150mg, 12mg или для никотина 1шт 50мг.",
    },
    "journal.empty_meal": {
        "en": "The meal description cannot be empty.",
        "ru": "Описание еды не должно быть пустым.",
    },
    "meal_time.command_format": {
        "en": "Format: /mealtime breakfast 08:30. Types: breakfast, lunch, dinner, snack, other.",
        "ru": "Формат: /mealtime breakfast 08:30. Типы: breakfast, lunch, dinner, snack, other.",
    },
    "meal_time.input_prompt": {
        "en": "Send the meal type and time, for example: breakfast 08:30.",
        "ru": "Напиши тип и время через пробел, например: breakfast 08:30.",
    },
    "meal_time.saved": {
        "en": (
            "✅ Saved {meal_type} at {time}.\n"
            "At the end of the day, send a FatSecret PDF link or attach the PDF itself."
        ),
        "ru": (
            "✅ Сохранил время: {meal_type} в {time}.\n"
            "В конце дня пришли ссылку на PDF из FatSecret или прикрепи сам PDF-файл."
        ),
    },
    "meal_time.db_busy": {
        "en": "❌ The database is busy with a background update. Try again in a minute.",
        "ru": "❌ База была занята фоновым обновлением. Нажми «Сейчас» ещё раз через минуту.",
    },
    "meal_time.save_failed": {
        "en": "❌ I couldn't save the meal time. Details were written to the log.",
        "ru": "❌ Не получилось сохранить время приёма пищи. Подробности записаны в лог.",
    },
    "fatsecret.loading_pdf": {
        "en": "⏳ Downloading and parsing the FatSecret PDF…",
        "ru": "⏳ Загружаю и разбираю PDF FatSecret...",
    },
    "fatsecret.pdf_too_large": {
        "en": "❌ The PDF is too large. Maximum size: 10 MB.",
        "ru": "❌ PDF слишком большой. Максимальный размер — 10 МБ.",
    },
    "fatsecret.parse_failed": {
        "en": "❌ I couldn't parse the FatSecret PDF. Check the file and try again.",
        "ru": "❌ Не удалось разобрать PDF FatSecret. {error}",
    },
    "fatsecret.url_failed": {
        "en": "❌ Import failed. Make sure this is a direct FatSecret daily-report PDF link.",
        "ru": "❌ Не удалось импортировать PDF. Проверь, что это прямая ссылка FatSecret на дневной PDF-отчёт.",
    },
    "fatsecret.document_failed": {
        "en": "❌ I couldn't parse this PDF. Make sure it is a FatSecret daily report.",
        "ru": "❌ Не удалось разобрать PDF FatSecret. Проверь, что это дневной PDF-отчёт из FatSecret.",
    },
    "fatsecret.imported": {
        "en": (
            "✅ FatSecret imported for {date}.\n"
            "Foods: {food_count} · meals: {meal_count}\n"
            "Exact calories and nutrients will be included in your next personal report."
        ),
        "ru": (
            "✅ FatSecret импортирован за {date}.\n"
            "Продуктов: {food_count} · приёмов пищи: {meal_count}\n"
            "Точные калории и нутриенты попадут в ближайший персональный отчёт."
        ),
    },
    "checkin.rate": {
        "en": "Rate: {label}\nChoose a number from 1 to 10.",
        "ru": "Оцени: {label}\nВыбери число от 1 до 10.",
    },
    "checkin.deep_work": {
        "en": "How many minutes of deep work did you get today? Send a number or choose Skip.",
        "ru": "Сколько минут глубокой работы было сегодня? Напиши число или нажми «Пропустить».",
    },
    "checkin.priority": {
        "en": "What was today's main priority? Send it or choose Skip.",
        "ru": "Какая главная задача была сегодня? Напиши её или нажми «Пропустить».",
    },
    "checkin.note": {
        "en": "Add a note about your day, or choose Skip.",
        "ru": "Добавить комментарий о дне? Напиши его или нажми «Пропустить».",
    },
    "checkin.invalid_minutes": {
        "en": "Send a whole number of minutes or choose Skip.",
        "ru": "Напиши целое число минут или нажми «Пропустить».",
    },
    "checkin.saved": {
        "en": "✅ Check-in saved. It will be included in your next report.",
        "ru": "✅ Check-in сохранён. Эти данные попадут в ближайший отчёт.",
    },
    "checkin.save_failed": {
        "en": "❌ I couldn't save the check-in. Start again from Check-in.",
        "ru": "❌ Не получилось сохранить check-in. Начни ещё раз с кнопки «Чек-ин».",
    },
    "checkin.started": {"en": "Starting your check-in.", "ru": "Начинаем check-in."},
    "navigation.main_open": {"en": "Main menu opened.", "ru": "Главное меню открыто."},
    "navigation.choose_section": {"en": "Choose a section:", "ru": "Выбери нужный раздел:"},
    "navigation.journal_open": {"en": "Journal opened.", "ru": "Дневник открыт."},
    "fatsecret.not_configured": {
        "en": (
            "🍽 FatSecret import\n\n"
            "Add FATSECRET_CONSUMER_KEY and FATSECRET_CONSUMER_SECRET to the server's .env, "
            "then restart the bot."
        ),
        "ru": (
            "🍽 FatSecret автоимпорт\n\n"
            "Сначала добавь FATSECRET_CONSUMER_KEY и FATSECRET_CONSUMER_SECRET "
            "в .env на сервере и перезапусти бота."
        ),
    },
    "fatsecret.connected": {
        "en": (
            "🍽 FatSecret connected\n\n"
            "Your diary is imported automatically every day at {time}. "
            "You can also start today's import manually."
        ),
        "ru": (
            "🍽 FatSecret подключён\n\n"
            "Я автоматически забираю дневник каждый день в {time}. "
            "Можно также запустить импорт за сегодня вручную."
        ),
    },
    "fatsecret.disconnected": {
        "en": (
            "🍽 FatSecret import\n\n"
            "Connect your account once. I will send you a FatSecret link; after approval, "
            "send the verifier code back here."
        ),
        "ru": (
            "🍽 FatSecret автоимпорт\n\n"
            "Подключи свой аккаунт один раз. Я пришлю ссылку FatSecret, "
            "а после подтверждения ты отправишь мне показанный verifier-код."
        ),
    },
    "fatsecret.settings_failed": {
        "en": "❌ I couldn't open the FatSecret settings.",
        "ru": "❌ Не удалось открыть настройки FatSecret.",
    },
    "fatsecret.connect_failed": {
        "en": "❌ I couldn't start FatSecret authorization. Check the server settings and try again.",
        "ru": "❌ Не удалось начать привязку. {error}",
    },
    "fatsecret.connect_failed_generic": {
        "en": "❌ I couldn't start FatSecret authorization.",
        "ru": "❌ Не удалось начать привязку FatSecret.",
    },
    "fatsecret.connect_steps": {
        "en": (
            "1. Open the link and sign in to FatSecret:\n{url}\n\n"
            "2. Approve access. FatSecret will show a verifier code.\n"
            "3. Send that code here in your next message."
        ),
        "ru": (
            "1. Открой ссылку и войди в свой аккаунт FatSecret:\n{url}\n\n"
            "2. Разреши доступ приложению. FatSecret покажет verifier-код.\n"
            "3. Пришли этот код следующим сообщением сюда."
        ),
    },
    "fatsecret.importing_today": {
        "en": "⏳ Importing today's nutrition data from FatSecret…",
        "ru": "⏳ Импортирую питание из FatSecret за сегодня...",
    },
    "fatsecret.api_import_failed": {
        "en": "❌ FatSecret import failed. Check the connection and try again later.",
        "ru": "❌ Импорт FatSecret не выполнен. {error}",
    },
    "fatsecret.api_import_failed_generic": {
        "en": "❌ I couldn't import nutrition data from FatSecret.",
        "ru": "❌ Не удалось импортировать питание из FatSecret.",
    },
    "fatsecret.connect_first": {
        "en": "Connect your FatSecret account first.",
        "ru": "Сначала подключи аккаунт FatSecret.",
    },
    "fatsecret.api_imported": {
        "en": "✅ FatSecret imported for {date}.\nFoods: {food_count} · meals: {meal_count}",
        "ru": "✅ FatSecret импортирован за {date}.\nПродуктов: {food_count} · приёмов пищи: {meal_count}",
    },
    "fatsecret.verify_failed": {
        "en": (
            "❌ I couldn't confirm the FatSecret connection. "
            "Send the verifier code again or restart the connection flow."
        ),
        "ru": (
            "❌ Не удалось подтвердить FatSecret. {error}\n"
            "Попробуй отправить verifier-код ещё раз или запусти привязку заново."
        ),
    },
    "fatsecret.verify_failed_generic": {
        "en": "❌ I couldn't confirm FatSecret. Restart the connection flow.",
        "ru": "❌ Не удалось подтвердить FatSecret. Запусти привязку заново.",
    },
    "fatsecret.connected_importing": {
        "en": "✅ FatSecret connected. Importing today's nutrition data now…",
        "ru": "✅ FatSecret подключён. Сейчас загружаю питание за сегодня...",
    },
    "fatsecret.first_import_failed": {
        "en": (
            "⚠️ The account is connected, but the first import failed. "
            "Try the FatSecret import button again later."
        ),
        "ru": (
            "⚠️ Аккаунт подключён, но первый импорт не прошёл. "
            "Попробуй кнопку «🍽 FatSecret автоимпорт» позже."
        ),
    },
    "fatsecret.auto_import_enabled": {
        "en": (
            "✅ Automatic import is enabled every day at {time}.\n"
            "Today: {food_count} foods · {meal_count} meals."
        ),
        "ru": (
            "✅ Автоимпорт включён: ежедневно в {time}.\n"
            "Сегодня: {food_count} продуктов · {meal_count} приёмов пищи."
        ),
    },
    "journal.command_failed": {
        "en": "I couldn't save that entry. Check the command format or use the Journal button.",
        "ru": "Не получилось записать. Проверь формат команды или воспользуйся кнопкой «Дневник».",
    },
    "journal.entries_header": {"en": "Recent entries:\n{entries}", "ru": "Последние записи:\n{entries}"},
    "journal.entries_empty": {"en": "No entries yet.", "ru": "Записей пока нет."},
    "journal.entries_help": {
        "en": "Edit: /edit ID note=text at=HH:MM\nDelete: /delete ID",
        "ru": "Изменить: /edit ID note=текст at=HH:MM\nУдалить: /delete ID",
    },
    "journal.photo_estimate": {"en": "meal estimate", "ru": "оценка состава блюда"},
    "journal.pending": {"en": "awaiting confirmation", "ru": "ожидает подтверждения"},
    "journal.edit_format": {
        "en": "Format: /edit ID note=text at=18:30",
        "ru": "Формат: /edit ID note=текст at=18:30",
    },
    "journal.edited": {"en": "✅ Entry updated:\n{entry}", "ru": "✅ Запись изменена:\n{entry}"},
    "journal.edited_short": {"en": "✅ Entry updated.", "ru": "✅ Запись изменена."},
    "journal.edit_failed": {
        "en": "❌ I couldn't update the entry. Check its ID and the command format.",
        "ru": "❌ Не удалось изменить запись. Проверь ID и формат.",
    },
    "journal.edit_failed_example": {
        "en": "I couldn't update the entry. Example: note=correction at=18:30",
        "ru": "Не удалось изменить запись. Пример: note=исправление at=18:30",
    },
    "journal.deleted": {"en": "✅ Entry #{entry_id} deleted.", "ru": "✅ Запись #{entry_id} удалена."},
    "journal.deleted_short": {"en": "✅ Entry deleted.", "ru": "✅ Запись удалена."},
    "journal.delete_failed": {
        "en": "❌ I couldn't delete the entry. Check its ID.",
        "ru": "❌ Не удалось удалить запись. Проверь ID.",
    },
    "journal.choose_entry": {
        "en": "Choose an entry to edit or delete:",
        "ru": "Выбери запись для изменения или удаления:",
    },
    "journal.delete_confirm": {
        "en": "Delete entry #{entry_id}?",
        "ru": "Удалить запись #{entry_id}?",
    },
    "journal.edit_instructions": {
        "en": (
            "Send changes as key=value, for example:\n"
            "note=corrected text at=18:30\n\n"
            "You can change note, at, quantity, dose, duration_min, intensity, and subtype."
        ),
        "ru": (
            "Напиши изменения в формате key=value, например:\n"
            "note=исправленный текст at=18:30\n\n"
            "Можно менять note, at, quantity, dose, duration_min, intensity, subtype."
        ),
    },
    "checkin.edited": {"en": "✅ Check-in updated.", "ru": "✅ Check-in изменён."},
    "checkin.edit_format": {
        "en": "❌ Format: /editcheckin ID energy=7 focus=8",
        "ru": "❌ Формат: /editcheckin ID energy=7 focus=8",
    },
    "checkin.deleted": {
        "en": "✅ Check-in #{checkin_id} deleted.",
        "ru": "✅ Check-in #{checkin_id} удалён.",
    },
    "checkin.delete_format": {
        "en": "❌ Format: /deletecheckin ID",
        "ru": "❌ Формат: /deletecheckin ID",
    },
    "checkin.command_failed": {
        "en": "I couldn't save the check-in. Use values from 1 to 10 or open Check-in.",
        "ru": "Не получилось сохранить check-in. Проверь значения от 1 до 10 или воспользуйся кнопкой «Чек-ин».",
    },
    "sync.loading": {"en": "⏳ Syncing Google Health data…", "ru": "⏳ Запускаю синхронизацию..."},
    "sync.cancelled": {"en": "Sync cancelled.", "ru": "Синхронизация отменена."},
    "sync.failed": {
        "en": "❌ Sync failed. Details were written to the log.",
        "ru": "❌ Синхронизация завершилась с ошибкой. Подробности записаны в лог.",
    },
    "sync.complete": {"en": "✅ Sync complete.", "ru": "✅ Синхронизация завершена."},
    "food.photo_missing": {
        "en": "Add a photo, a description, or exact details first.",
        "ru": "Сначала добавь фото, описание или точные данные.",
    },
    "food.analyzing": {
        "en": "Analyzing the meal…",
        "ru": "Анализирую приём пищи...",
    },
    "food.analysis_failed": {
        "en": "I couldn't analyze the meal. Check the details and try again.",
        "ru": "Не получилось проанализировать еду. Проверь данные и попробуй ещё раз.",
    },
    "food.confirmed": {
        "en": "Meal saved. It will be included in your next report.",
        "ru": "Приём пищи сохранён и попадёт в ближайший отчёт.",
    },
    "food.cancelled": {"en": "Meal entry cancelled.", "ru": "Запись еды отменена."},
    "food.confirm_missing": {
        "en": "I couldn't find a meal waiting for confirmation.",
        "ru": "Не нашёл ожидающую подтверждения запись еды.",
    },
    "food.confirm_failed": {
        "en": "I couldn't save the meal entry.",
        "ru": "Не получилось сохранить запись еды.",
    },
    "food.correction_prompt": {
        "en": "Tell me what to correct. For example: “the chicken was about 200 g, not 100 g”.",
        "ru": "Напиши, что исправить. Например: «курицы было около 200 г, а не 100 г».",
    },
    "food.correction_required": {
        "en": "Tell me what needs to be corrected.",
        "ru": "Напиши, что нужно исправить.",
    },
    "food.review": {
        "en": "Meal: {meal_type}\nTime: {time}\n\n{analysis}\n\nIs everything correct?",
        "ru": "Приём пищи: {meal_type}\nВремя: {time}\n\n{analysis}\n\nВсё верно?",
    },
    "food.meal_type_prompt": {
        "en": "Which meal was this?",
        "ru": "Какой это приём пищи?",
    },
    "food.photo_prompt": {
        "en": "Send a meal photo. You can add a caption or skip this step.",
        "ru": "Отправь фото еды. Можно добавить подпись или пропустить этот шаг.",
    },
    "food.description_prompt": {
        "en": "Describe the meal approximately: what it was and roughly how much. You can also send a photo here or skip this step.",
        "ru": "Примерно опиши еду: что это было и сколько примерно. Здесь также можно отправить фото или пропустить шаг.",
    },
    "food.exact_prompt": {
        "en": "Add any exact details you know: weight, calories, protein, fat, or carbohydrates. Example: 350 g; 620 kcal; P 35; F 20; C 70. You can also attach a photo or skip this step.",
        "ru": "Добавь известные точные данные: вес, калории, белки, жиры или углеводы. Например: 350 г; 620 ккал; Б 35; Ж 20; У 70. Можно также приложить фото или пропустить шаг.",
    },
    "food.need_details": {
        "en": "I need at least a photo, a description, or exact details to save a meal.",
        "ru": "Чтобы сохранить еду, нужно хотя бы фото, описание или точные данные.",
    },
    "food.time_prompt": {"en": "When did you eat this?", "ru": "Когда ты это съел?"},
    "food.approximate_composition": {
        "en": "Estimated composition:",
        "ru": "Примерный состав:",
    },
    "food.total": {"en": "Total: {value} kcal", "ru": "Итого: {value} ккал"},
    "food.item_calories": {"en": "{value} kcal", "ru": "{value} ккал"},
    "food.macros": {"en": "Estimated macros:", "ru": "БЖУ примерно:"},
    "food.protein": {"en": "Protein", "ru": "Белки"},
    "food.carbohydrates": {"en": "Carbohydrates", "ru": "Углеводы"},
    "food.fat": {"en": "Fat", "ru": "Жиры"},
    "food.grams": {"en": "{value} g", "ru": "{value} г"},
    "food.confidence": {"en": "Confidence: {value}", "ru": "Уверенность: {value}"},
    "food.confidence.insufficient": {"en": "insufficient", "ru": "недостаточная"},
    "food.confidence.low": {"en": "low", "ru": "низкая"},
    "food.confidence.medium": {"en": "medium", "ru": "средняя"},
    "food.confidence.high": {"en": "high", "ru": "высокая"},
    "question.analyzing_photos": {
        "en": "⏳ Analyzing your question and attached photos…",
        "ru": "⏳ Анализирую вопрос и прикреплённые фотографии...",
    },
    "question.empty_response": {
        "en": "❌ Claude returned an empty answer. This may be a temporary CLI or usage-limit issue; try again or choose Sonnet.",
        "ru": "❌ Claude не вернул текст ответа. Это временный сбой CLI или лимита; попробуй ещё раз либо выбери Sonnet.",
    },
    "question.failed": {
        "en": "❌ I couldn't answer. Details were written to the log.",
        "ru": "❌ Не удалось ответить. Подробности записаны в лог.",
    },
    "question.model_prompt": {
        "en": (
            "Which model should answer this question?\n"
            "Sonnet is faster and works well for everyday questions.\n"
            "Opus is better for deeper personal analysis."
        ),
        "ru": (
            "Какую модель использовать для этого вопроса?\n"
            "Sonnet быстрее и подходит для обычных вопросов.\n"
            "Opus лучше выбрать для сложного персонального анализа."
        ),
    },
    "question.input_prompt": {
        "en": "Send your question in the next message or attach a photo with a caption.\nFor example: should I train today?",
        "ru": "Напиши вопрос следующим сообщением или прикрепи фотографию с подписью.\nНапример: стоит ли мне сегодня тренироваться?",
    },
    "question.photo_added_choose": {
        "en": "Photo added to the question ({count}). Now choose a model above.",
        "ru": "Фото добавлено к вопросу ({count}). Теперь выбери модель выше.",
    },
    "question.photo_added_more": {
        "en": "Photo added ({count}). Send another photo or write your question.",
        "ru": "Фото добавлено ({count}). Пришли ещё фото или напиши вопрос к ним.",
    },
    "question.feedback_failed": {
        "en": "I couldn't save that feedback.",
        "ru": "Не удалось сохранить обратную связь.",
    },
    "question.expired": {
        "en": "This question has expired. Send it again with /ask.",
        "ru": "Вопрос устарел. Отправь его ещё раз через /ask.",
    },
    "question.model_selected": {
        "en": "Selected model: {model}",
        "ru": "Выбрана модель: {model}",
    },
    "training.input_prompt": {
        "en": "Send the workout as text or attach a photo/screenshot. Any format is fine: exercises, weights, repetitions, or sets.",
        "ru": "Пришли текст тренировки или фотографию/скриншот записи. Можно в любом формате: упражнения, веса, повторы, подходы.",
    },
    "training.analyzing": {
        "en": "⏳ Analyzing the workout with AI…",
        "ru": "⏳ Разбираю тренировку с помощью ИИ...",
    },
    "training.failed": {
        "en": "❌ I couldn't analyze the workout.",
        "ru": "❌ Не удалось разобрать тренировку.",
    },
    "training.saved": {
        "en": "✅ Workout saved and analyzed.",
        "ru": "✅ Тренировка сохранена и разобрана.",
    },
    "archive.empty": {
        "en": "There are no reports of this type in the archive yet.",
        "ru": "В архиве пока нет этих отчётов.",
    },
    "archive.choose": {
        "en": "Choose a saved report:",
        "ru": "Выбери сохранённый отчёт:",
    },
    "archive.missing": {
        "en": "That report is no longer available.",
        "ru": "Этот отчёт больше не найден.",
    },
    "archive.read_failed": {
        "en": "❌ I couldn't read that report.",
        "ru": "❌ Не удалось прочитать этот отчёт.",
    },
    "archive.report_header": {
        "en": "📄 Report {name}:",
        "ru": "📄 Отчёт {name}:",
    },
    "archive.menu": {"en": "Report archive:", "ru": "Архив отчётов:"},
    "report.type.daily": {"en": "daily", "ru": "дневной"},
    "report.type.weekly": {"en": "weekly", "ru": "недельный"},
    "report.type.monthly": {"en": "monthly", "ru": "месячный"},
    "report.automatic_header": {
        "en": "Automatic {report_type} report for {start} – {end}",
        "ru": "Автоматический {report_type} отчёт за {start} — {end}",
    },
    "report.chart_caption.daily": {
        "en": "How each factor contributed to today's readiness",
        "ru": "Вклад факторов в сегодняшнюю оценку состояния",
    },
    "report.chart_caption.period": {
        "en": "Personal trends over the report period",
        "ru": "Персональная динамика за период отчёта",
    },
    "report.feedback_prompt": {
        "en": "Your answer will be saved and used to make future reports more accurate.",
        "ru": "Ответ сохранится и поможет сделать следующие отчёты точнее.",
    },
    "report.feedback_title": {
        "en": "Review these assumptions",
        "ru": "Проверь предположения",
    },
    "report.feedback.yes": {"en": "Confirm", "ru": "Подтверждаю"},
    "report.feedback.no": {"en": "Reject", "ru": "Не подтверждаю"},
    "report.feedback.confirmed": {
        "en": "{index} · Confirmed",
        "ru": "{index} · Подтверждено",
    },
    "report.feedback.rejected": {
        "en": "{index} · Rejected",
        "ru": "{index} · Не подтверждено",
    },
}


def translate(key: str, locale: Locale = "ru", **values: object) -> Any:
    try:
        message = _MESSAGES[key][locale]
    except KeyError as exc:
        raise KeyError(f"missing translation: {key!r} for locale {locale!r}") from exc
    if isinstance(message, str):
        return message.format(**values)
    if values:
        raise TypeError(f"translation {key!r} does not accept interpolation values")
    return message


def validate_catalogs() -> None:
    expected = set(SUPPORTED_LOCALES)
    for key, translations in _MESSAGES.items():
        locales = set(translations)
        if locales != expected:
            missing = sorted(expected - locales)
            extra = sorted(locales - expected)
            raise ValueError(
                f"translation catalog mismatch for {key!r}: "
                f"missing={missing}, extra={extra}"
            )


def catalog_texts(locale: Locale) -> tuple[str, ...]:
    texts: list[str] = []
    for translations in _MESSAGES.values():
        value = translations[locale]
        if isinstance(value, str):
            texts.append(value)
        else:
            texts.extend(value)
    return tuple(texts)


validate_catalogs()
