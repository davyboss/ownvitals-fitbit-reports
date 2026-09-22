from fitbit_report.integrations.telegram import (
    MAIN_MENU_LABELS,
    _checkin_command,
    _set_checkin_flow,
    checkin_rating_fields,
    _journal_command_from_amount,
    help_text,
    journal_menu_markup,
    meal_type_markup,
    meal_time_markup,
    archive_menu_markup,
    archive_period_markup,
    food_confirmation_markup,
    food_meal_type_markup,
    food_step_markup,
    food_time_markup,
    fatsecret_markup,
    _clear_flow,
    _extract_fatsecret_url,
    _feedback_markup,
    feedback_claim_summaries,
    feedback_claim_indices,
    main_menu_markup,
    main_menu_labels,
    more_menu_markup,
    rating_markup,
    report_feedback_text,
    save_question_answer,
    split_report_text,
    send_report,
    sync_confirm_markup,
    start_text,
    status_text,
    usage_text,
)


def test_main_menu_contains_guided_sections():
    assert MAIN_MENU_LABELS == (
        "Дневник",
        "Чек-ин",
        "Спросить",
        "Отчёты",
        "Ещё",
    )
    keyboard = main_menu_markup().keyboard
    assert [button.text for row in keyboard for button in row] == list(MAIN_MENU_LABELS)
    assert [len(row) for row in keyboard] == [2, 2, 1]


def test_more_menu_contains_secondary_actions():
    buttons = [
        button
        for row in more_menu_markup().inline_keyboard
        for button in row
    ]

    assert [(button.text, button.callback_data) for button in buttons] == [
        ("Мои записи", "more:entries"),
        ("Синхронизация", "more:sync"),
        ("Расход Claude", "more:usage"),
        ("Статус", "more:status"),
        ("Помощь", "more:help"),
    ]


def test_english_main_menu_and_shell_copy_are_localized():
    from datetime import datetime, timezone

    labels = main_menu_labels("en")
    keyboard = main_menu_markup("en").keyboard

    assert labels[0] == "Journal"
    assert labels[-1] == "More"
    assert [button.text for row in keyboard for button in row] == list(labels)
    assert "personal health and productivity assistant" in start_text("en")
    assert "How to use the bot" in help_text("en")
    assert "Расход" not in usage_text(
        {},
        datetime(2026, 9, 1, tzinfo=timezone.utc),
        datetime(2026, 10, 1, tzinfo=timezone.utc),
        "en",
    )


def test_english_top_level_submenus_keep_stable_callback_data():
    journal_buttons = [
        button
        for row in journal_menu_markup("en").inline_keyboard
        for button in row
    ]
    archive_buttons = [
        button
        for row in archive_menu_markup("en").inline_keyboard
        for button in row
    ]

    assert journal_buttons[0].text == "Add food"
    assert journal_buttons[0].callback_data == "journal:add_food"
    assert archive_buttons[0].text == "Daily reports"
    assert archive_buttons[0].callback_data == "archive:list:daily"


def test_english_journal_controls_preserve_callback_contracts():
    from fitbit_report.integrations.telegram import (
        food_confirmation_markup,
        food_meal_type_markup,
        food_time_markup,
        meal_type_markup,
        nicotine_menu_markup,
        question_model_markup,
    )

    cases = (
        (meal_type_markup("en"), "Breakfast", "journal:meal:breakfast"),
        (food_meal_type_markup("en"), "Breakfast", "food:meal:breakfast"),
        (food_time_markup("en"), "Now", "food-time:now"),
        (food_confirmation_markup("en"), "Looks right", "food:confirm"),
        (nicotine_menu_markup("en"), "Snus", "journal:nicotine:snus"),
        (question_model_markup("en"), "Sonnet — everyday question", "question:model:sonnet"),
    )

    for markup, label, callback in cases:
        first = markup.inline_keyboard[0][0]
        assert first.text == label
        assert first.callback_data == callback


def test_english_main_menu_routes_to_english_journal_prompt():
    import asyncio
    from types import SimpleNamespace

    from fitbit_report.integrations.telegram import build_application

    replies = []

    class Message:
        text = "Journal"

        async def reply_text(self, text, **kwargs):
            replies.append((text, kwargs.get("reply_markup")))

    settings = SimpleNamespace(
        app_locale="en",
        telegram_bot_token="test-token",
        telegram_allowed_chat_id=42,
        obsidian_vault="obsidian-vault",
        database_url="sqlite:///data/app.db",
        timezone="Europe/Kiev",
    )
    application = build_application(settings, SimpleNamespace())
    handler = next(
        candidate
        for group in application.handlers.values()
        for candidate in group
        if getattr(candidate.callback, "__name__", "") == "handle_text"
    )
    update = SimpleNamespace(
        effective_chat=SimpleNamespace(id=42),
        effective_message=Message(),
    )
    context = SimpleNamespace(user_data={})

    asyncio.run(handler.callback(update, context))

    assert replies[0][0] == "What would you like to log?"
    first_button = replies[0][1].inline_keyboard[0][0]
    assert first_button.text == "Add food"
    assert first_button.callback_data == "journal:add_food"


def test_telegram_detects_fatsecret_pdf_link_with_query_parameters():
    url = "https://foods.fatsecret.com/export/1/ABC/2/day/food/FoodDiary_260820_foods.pdf?lang=ru&mkt=RU"

    assert _extract_fatsecret_url(f"Вот мой отчёт: {url}") == url


def test_feedback_markup_keeps_all_rows_after_one_item_is_rated():
    markup = _feedback_markup(
        report_id=42,
        claim_indices=(1, 3),
        selected={("claim", 1): "confirmed"},
    )

    assert markup is not None
    assert len(markup.inline_keyboard) == 2
    assert markup.inline_keyboard[0][0].text == "2 · Подтверждено"
    assert markup.inline_keyboard[0][1].text == "2 · Не подтверждаю"
    assert markup.inline_keyboard[1][0].text == "4 · Подтверждаю"
    assert markup.inline_keyboard[1][0].callback_data == "feedback:claim:42:3:confirmed"


def test_feedback_only_requests_uncertain_interpretations():
    claims = [
        {"kind": "fact", "confidence": "high"},
        {"kind": "association", "confidence": "low"},
        {"kind": "hypothesis", "confidence": "medium"},
        {"kind": "hypothesis", "confidence": "insufficient"},
        {"kind": "association", "confidence": "high"},
    ]

    assert feedback_claim_indices(claims) == (1, 2)


def test_feedback_prompt_links_each_button_number_to_a_short_assumption():
    from types import SimpleNamespace

    claims = [
        {"kind": "fact", "confidence": "high", "statement": "Измеренный факт."},
        {
            "kind": "association",
            "confidence": "low",
            "statement": (
                "После позднего отбоя и короткой ночи вы обычно отсыпаетесь "
                "следующей ночью. Дополнительные детали не нужны в подсказке."
            ),
        },
        {"kind": "fact", "confidence": "high", "statement": "Ещё один факт."},
        {
            "kind": "hypothesis",
            "confidence": "low",
            "statement": (
                "Пульс покоя и ВСР улучшились. Нагрузка снизилась. "
                "Гипотеза: меньшая нагрузка помогла восстановиться. "
                "Но данных пока мало."
            ),
        },
    ]
    summaries = feedback_claim_summaries(claims, "ru")
    result = SimpleNamespace(feedback_claim_summaries=summaries)

    text = report_feedback_text(result, "ru")

    assert summaries == (
        (1, "После позднего отбоя и короткой ночи вы обычно отсыпаетесь следующей ночью."),
        (3, "меньшая нагрузка помогла восстановиться."),
    )
    assert "<b>2.</b> После позднего отбоя" in text
    assert "<b>4.</b> меньшая нагрузка помогла восстановиться." in text
    assert "Измеренный факт" not in text


def test_feedback_prompt_escapes_model_text():
    from types import SimpleNamespace

    result = SimpleNamespace(
        feedback_claim_summaries=((1, "Сон < нормального & требует проверки."),)
    )

    text = report_feedback_text(result, "ru")

    assert "Сон &lt; нормального &amp; требует проверки." in text


def test_submenus_expose_stable_callback_data():
    journal_callbacks = [
        button.callback_data
        for row in journal_menu_markup().inline_keyboard
        for button in row
    ]
    assert "journal:caffeine" in journal_callbacks
    assert "journal:nicotine" in journal_callbacks
    assert "journal:meal_time" in journal_callbacks
    assert "journal:add_food" in journal_callbacks
    assert "journal:fatsecret" not in journal_callbacks


def test_fatsecret_menu_switches_from_connect_to_manual_import():
    disconnected = [
        button.callback_data
        for row in fatsecret_markup(False).inline_keyboard
        for button in row
    ]
    connected = [
        button.callback_data
        for row in fatsecret_markup(True).inline_keyboard
        for button in row
    ]

    assert "fatsecret:connect" in disconnected
    assert "fatsecret:sync" in connected


def test_meal_menu_exposes_common_meal_types():
    callbacks = [
        button.callback_data
        for row in meal_type_markup().inline_keyboard
        for button in row
    ]

    assert callbacks[:4] == [
        "journal:meal:breakfast",
        "journal:meal:lunch",
        "journal:meal:dinner",
        "journal:meal:snack",
    ]


def test_food_photo_flow_exposes_meal_types_and_confirmation_actions():
    draft_callbacks = [
        button.callback_data
        for row in food_step_markup("photo").inline_keyboard
        for button in row
    ]
    meal_callbacks = [
        button.callback_data
        for row in food_meal_type_markup().inline_keyboard
        for button in row
    ]
    time_callbacks = [
        button.callback_data
        for row in food_time_markup().inline_keyboard
        for button in row
    ]
    confirmation_callbacks = [
        button.callback_data
        for row in food_confirmation_markup().inline_keyboard
        for button in row
    ]

    assert draft_callbacks == ["food-draft:skip:photo", "food-draft:cancel"]
    assert meal_callbacks[:5] == [
        "food:meal:breakfast",
        "food:meal:lunch",
        "food:meal:dinner",
        "food:meal:snack",
        "food:meal:other",
    ]
    assert time_callbacks == ["food-time:now", "food-time:custom", "food-time:cancel"]
    assert confirmation_callbacks == ["food:confirm", "food:edit", "food:cancel"]


def test_add_food_flow_is_one_skippable_sequence():
    import asyncio
    from types import SimpleNamespace

    from fitbit_report.integrations.telegram import build_application

    edits = []

    class Query:
        data = "journal:add_food"

        async def answer(self, *args, **kwargs):
            return None

        async def edit_message_text(self, text, **kwargs):
            edits.append((text, kwargs.get("reply_markup")))

    settings = SimpleNamespace(
        app_locale="en",
        telegram_bot_token="test-token",
        telegram_allowed_chat_id=42,
        obsidian_vault="obsidian-vault",
        database_url="sqlite:///data/app.db",
        timezone="Europe/Kiev",
    )
    application = build_application(settings, SimpleNamespace())
    handler = next(
        candidate
        for group in application.handlers.values()
        for candidate in group
        if getattr(candidate.callback, "__name__", "") == "handle_callback"
    )
    query = Query()
    update = SimpleNamespace(
        effective_chat=SimpleNamespace(id=42),
        effective_message=SimpleNamespace(),
        callback_query=query,
    )
    context = SimpleNamespace(user_data={})

    asyncio.run(handler.callback(update, context))
    assert context.user_data["flow"] == "food_photo_input"
    assert edits[-1][1].inline_keyboard[0][0].callback_data == "food-draft:skip:photo"

    query.data = "food-draft:skip:photo"
    asyncio.run(handler.callback(update, context))
    assert context.user_data["flow"] == "food_description_input"

    query.data = "food-draft:skip:description"
    asyncio.run(handler.callback(update, context))
    assert context.user_data["flow"] == "food_exact_input"


def test_meal_time_flow_exposes_now_and_custom_time_buttons():
    callbacks = [
        button.callback_data
        for row in meal_time_markup().inline_keyboard
        for button in row
    ]

    assert callbacks == ["meal-time:now", "meal-time:custom", "meal-time:cancel"]


def test_clear_flow_removes_pending_food_photo_state():
    from types import SimpleNamespace

    context = SimpleNamespace(user_data={
        "flow": "food_confirmation",
        "food": {"photo_path": "meal.jpg"},
        "journal": {"category": "meal"},
        "checkin": {"period": "morning"},
    })

    _clear_flow(context)

    assert context.user_data == {}


def test_archive_menu_has_read_only_period_actions():
    callbacks = [
        button.callback_data
        for row in archive_menu_markup().inline_keyboard
        for button in row
    ]

    assert "archive:list:daily" in callbacks
    assert "archive:list:weekly" in callbacks
    assert "archive:list:monthly" in callbacks
    assert not any(callback.startswith("report:") for callback in callbacks)


def test_archive_period_markup_only_lists_existing_report_actions():
    callbacks = [
        button.callback_data
        for row in archive_period_markup("daily", ["2026-08-12.md", "2026-08-11.md"]).inline_keyboard
        for button in row
    ]

    assert callbacks == ["archive:view:daily:0", "archive:view:daily:1", "nav:archive"]


def test_application_does_not_register_manual_report_command():
    from types import SimpleNamespace

    from fitbit_report.integrations.telegram import build_application

    settings = SimpleNamespace(
        telegram_bot_token="test-token",
        telegram_allowed_chat_id=42,
        obsidian_vault="obsidian-vault",
        database_url="sqlite:///data/app.db",
        timezone="Europe/Kiev",
    )
    application = build_application(settings, SimpleNamespace())
    commands = [command for handler in application.handlers[0] for command in getattr(handler, "commands", ())]

    assert "report" not in commands


def test_fatsecret_document_from_unallowed_chat_is_ignored():
    import asyncio
    from types import SimpleNamespace

    from fitbit_report.integrations.telegram import build_application

    settings = SimpleNamespace(
        telegram_bot_token="test-token",
        telegram_allowed_chat_id=42,
        obsidian_vault="obsidian-vault",
        database_url="sqlite:///data/app.db",
        timezone="Europe/Kiev",
    )
    application = build_application(settings, SimpleNamespace())
    handler = next(
        candidate
        for group in application.handlers.values()
        for candidate in group
        if getattr(candidate.callback, "__name__", "")
        == "import_fatsecret_document_message"
    )

    class UnexpectedCall:
        def __getattr__(self, name):
            raise AssertionError(f"unauthorized document accessed {name}")

    update = SimpleNamespace(
        effective_chat=SimpleNamespace(id=7),
        effective_message=UnexpectedCall(),
    )
    context = UnexpectedCall()

    asyncio.run(handler.callback(update, context))


def test_fatsecret_document_from_allowed_chat_is_imported():
    import asyncio
    from types import SimpleNamespace

    from fitbit_report.integrations.telegram import build_application

    imported = []
    replies = []

    class Services:
        async def import_fatsecret_pdf_bytes(self, pdf_bytes, source_url):
            imported.append((pdf_bytes, source_url))
            return {"report_date": "2026-08-20", "food_count": 2, "meal_count": 1}

    class Message:
        document = SimpleNamespace(
            file_name="diary.pdf",
            mime_type="application/pdf",
            file_size=8,
            file_id="file-id",
            file_unique_id="unique-id",
        )
        caption = ""

        async def reply_text(self, text, **kwargs):
            replies.append(text)

    class TelegramFile:
        async def download_to_memory(self, out):
            out.write(b"%PDF-ok")

    class Bot:
        async def get_file(self, file_id):
            assert file_id == "file-id"
            return TelegramFile()

    settings = SimpleNamespace(
        telegram_bot_token="test-token",
        telegram_allowed_chat_id=42,
        obsidian_vault="obsidian-vault",
        database_url="sqlite:///data/app.db",
        timezone="Europe/Kiev",
    )
    application = build_application(settings, Services())
    handler = next(
        candidate
        for group in application.handlers.values()
        for candidate in group
        if getattr(candidate.callback, "__name__", "")
        == "import_fatsecret_document_message"
    )
    update = SimpleNamespace(
        effective_chat=SimpleNamespace(id=42),
        effective_message=Message(),
    )

    asyncio.run(handler.callback(update, SimpleNamespace(bot=Bot())))

    assert imported == [(b"%PDF-ok", "telegram://fatsecret/unique-id")]
    assert replies[0].startswith("⏳")
    assert replies[-1].startswith("✅")


def test_fatsecret_document_without_size_metadata_is_bounded():
    import asyncio
    from types import SimpleNamespace

    from fitbit_report.integrations.telegram import build_application
    from fitbit_report.journal.fatsecret import MAX_FATSECRET_PDF_BYTES

    replies = []

    class Services:
        async def import_fatsecret_pdf_bytes(self, pdf_bytes, source_url):
            raise AssertionError("oversized PDF reached the importer")

    class Message:
        document = SimpleNamespace(
            file_name="diary.pdf",
            mime_type="application/pdf",
            file_size=None,
            file_id="file-id",
            file_unique_id="unique-id",
        )
        caption = ""

        async def reply_text(self, text, **kwargs):
            replies.append(text)

    class TelegramFile:
        async def download_to_memory(self, out):
            out.write(b"x" * (MAX_FATSECRET_PDF_BYTES + 1))

    class Bot:
        async def get_file(self, file_id):
            return TelegramFile()

    settings = SimpleNamespace(
        telegram_bot_token="test-token",
        telegram_allowed_chat_id=42,
        obsidian_vault="obsidian-vault",
        database_url="sqlite:///data/app.db",
        timezone="Europe/Kiev",
    )
    application = build_application(settings, Services())
    handler = next(
        candidate
        for group in application.handlers.values()
        for candidate in group
        if getattr(candidate.callback, "__name__", "")
        == "import_fatsecret_document_message"
    )
    update = SimpleNamespace(
        effective_chat=SimpleNamespace(id=42),
        effective_message=Message(),
    )

    asyncio.run(handler.callback(update, SimpleNamespace(bot=Bot())))

    assert replies[-1].startswith("❌")
    assert "слишком большой" in replies[-1]


def test_help_text_explains_the_workflow():
    text = help_text()
    assert "Дневник" in text
    assert "Чек-ин" in text
    assert "/log" in text
    assert "/checkin" in text


def test_start_text_explains_personal_agent():
    text = start_text()
    assert "Google Health" in text
    assert "Obsidian" in text
    assert "кнопк" in text


def test_status_text_contains_safe_runtime_details_without_secrets():
    class Settings:
        database_url = "sqlite:///data/app.db"
        obsidian_vault = "D:/Obsidian/Health"
        timezone = "Europe/Kiev"

    text = status_text(Settings())
    assert "sqlite:///data/app.db" in text
    assert "D:/Obsidian/Health" in text
    assert "Europe/Kiev" in text
    assert "TELEGRAM_BOT_TOKEN" not in text


def test_guided_journal_builds_existing_parser_commands():
    assert _journal_command_from_amount({"category": "caffeine"}, "150mg") == "/log caffeine 150mg"
    assert _journal_command_from_amount(
        {"category": "nicotine", "subtype": "snus"}, "12mg"
    ) == "/log nicotine snus 12mg"
    assert _journal_command_from_amount(
        {"category": "nicotine", "subtype": "snus"}, "1шт 50мг"
    ) == "/log nicotine snus 1шт 50мг"


def test_guided_meal_builds_parser_command():
    from fitbit_report.integrations.telegram import _meal_command

    assert _meal_command("breakfast", "овсянка с бананом") == "/log meal breakfast овсянка с бананом"


def test_record_journal_returns_saved_meal_event(monkeypatch):
    from contextlib import contextmanager
    from types import SimpleNamespace

    import fitbit_report.integrations.telegram as telegram

    class FakeJournalService:
        def record(self, event, session):
            return SimpleNamespace(id=42, category=event.category)

    class FakeSession:
        def flush(self):
            pass

        def expunge(self, event):
            pass

    @contextmanager
    def fake_session_scope(engine):
        yield FakeSession()

    monkeypatch.setattr("fitbit_report.db.session.session_scope", fake_session_scope)
    monkeypatch.setattr("fitbit_report.journal.service.JournalService", FakeJournalService)

    event = telegram._record_journal(
        "/log meal snack Баунти 55 г",
        SimpleNamespace(timezone="Europe/Kiev"),
        SimpleNamespace(engine=object()),
    )

    assert event.id == 42
    assert event.category == "meal"


def test_record_journal_returns_usable_event_after_database_commit(tmp_path):
    from types import SimpleNamespace

    from sqlalchemy import create_engine

    import fitbit_report.integrations.telegram as telegram
    from fitbit_report.db.models import Base

    engine = create_engine(f"sqlite:///{tmp_path / 'app.db'}", future=True)
    Base.metadata.create_all(engine)

    event = telegram._record_journal(
        "/log meal snack Баунти 55 г",
        SimpleNamespace(timezone="Europe/Kiev"),
        SimpleNamespace(engine=engine),
    )

    assert event.id is not None
    assert event.category == "meal"


def test_guided_checkin_builds_existing_parser_command():
    command = _checkin_command(
        {
            "period": "evening",
            "values": {"energy": 7, "quality": 8, "deep_work_min": 120},
        }
    )
    assert command == "/checkin evening energy=7 quality=8 deep_work_min=120"


def test_checkin_text_flow_is_stored_where_text_handler_reads_it():
    from types import SimpleNamespace

    context = SimpleNamespace(user_data={"checkin": {}})

    _set_checkin_flow(context, "checkin_priority")

    assert context.user_data["flow"] == "checkin_priority"


def test_morning_checkin_asks_only_for_start_of_day_indicators():
    assert [key for key, _ in checkin_rating_fields("morning")] == [
        "energy",
        "sleep_quality",
        "mood",
        "stress",
    ]


def test_evening_checkin_asks_for_workday_results():
    assert [key for key, _ in checkin_rating_fields("evening")] == [
        "energy",
        "persistence",
        "quality",
        "focus",
        "mood",
        "stress",
    ]


def test_checkin_rating_markup_contains_scale_and_skip():
    callbacks = [
        button.callback_data
        for row in rating_markup("energy").inline_keyboard
        for button in row
    ]
    assert "checkin:set:energy:1" in callbacks
    assert "checkin:set:energy:10" in callbacks
    assert "checkin:skip:energy" in callbacks


def test_sync_confirmation_has_explicit_confirm_and_cancel():
    callbacks = [
        button.callback_data
        for row in sync_confirm_markup().inline_keyboard
        for button in row
    ]
    assert callbacks == ["sync:confirm", "sync:cancel"]


def test_split_report_text_keeps_each_chunk_under_limit():
    chunks = split_report_text("a" * 7100)

    assert [len(chunk) for chunk in chunks] == [3500, 3500, 100]


def test_save_question_answer_keeps_latest_full_answer(tmp_path):
    path = save_question_answer(tmp_path, "Что со сном?", "claude-opus-5", "Подробный ответ")

    assert path == tmp_path / "questions" / "last-answer.md"
    saved = path.read_text(encoding="utf-8")
    assert "Что со сном?" in saved
    assert "Подробный ответ" in saved


def test_send_report_sends_header_and_markdown_chunks():
    from datetime import date
    from pathlib import Path

    from fitbit_report.types import DateRange, ReportResult

    class Bot:
        def __init__(self):
            self.messages = []

        async def send_message(self, **kwargs):
            self.messages.append(kwargs)

    bot = Bot()
    result = ReportResult(
        "daily",
        DateRange(date(2026, 8, 12), date(2026, 8, 12)),
        Path("report.md"),
        "markdown",
    )

    import asyncio
    asyncio.run(send_report(bot, 42, result))

    assert [message["chat_id"] for message in bot.messages] == [42, 42]
    assert bot.messages[0]["text"]
    assert bot.messages[1]["text"] == "markdown"


def test_send_report_uses_english_delivery_copy_when_requested():
    from datetime import date
    from pathlib import Path

    from fitbit_report.types import DateRange, ReportResult

    class Bot:
        def __init__(self):
            self.messages = []

        async def send_message(self, **kwargs):
            self.messages.append(kwargs)

    bot = Bot()
    result = ReportResult(
        "daily",
        DateRange(date(2026, 8, 12), date(2026, 8, 12)),
        Path("report.md"),
        "English report",
    )

    import asyncio
    asyncio.run(send_report(bot, 42, result, "en"))

    assert bot.messages[0]["text"].startswith("Automatic daily report")
    assert "Автоматический" not in bot.messages[0]["text"]


def test_send_report_prefers_readable_telegram_text():
    from datetime import date
    from pathlib import Path

    from fitbit_report.types import DateRange, ReportResult

    class Bot:
        def __init__(self):
            self.messages = []

        async def send_message(self, **kwargs):
            self.messages.append(kwargs)

    bot = Bot()
    result = ReportResult(
        "daily",
        DateRange(date(2026, 8, 12), date(2026, 8, 12)),
        Path("report.md"),
        "frontmatter markdown",
        "📊 Дневной отчёт\n📝 Итог\nВсё хорошо",
    )

    import asyncio
    asyncio.run(send_report(bot, 42, result))

    assert bot.messages[1]["text"] == "📊 Дневной отчёт\n📝 Итог\nВсё хорошо"


def test_send_report_delivers_chart_before_long_text(tmp_path):
    from datetime import date
    from pathlib import Path

    from fitbit_report.types import DateRange, ReportResult

    class Bot:
        def __init__(self):
            self.actions = []

        async def send_message(self, **kwargs):
            self.actions.append(("message", kwargs["text"]))

        async def send_photo(self, **kwargs):
            self.actions.append(("photo", kwargs["caption"]))

    chart_path = tmp_path / "dashboard.png"
    chart_path.write_bytes(b"png")
    bot = Bot()
    result = ReportResult(
        "daily",
        DateRange(date(2026, 8, 12), date(2026, 8, 12)),
        Path("report.md"),
        "markdown",
        "readable report",
        chart_paths=(chart_path,),
    )

    import asyncio
    asyncio.run(send_report(bot, 42, result))

    assert [action[0] for action in bot.actions] == ["message", "photo", "message"]
    assert bot.actions[1][1] == "Вклад факторов в сегодняшнюю оценку состояния"


def test_send_report_prefers_single_rich_message(monkeypatch, tmp_path):
    import asyncio
    from datetime import date
    from pathlib import Path

    from fitbit_report.types import DateRange, ReportResult

    delivered = []

    async def fake_send_rich_report(**kwargs):
        delivered.append(kwargs)

    monkeypatch.setattr(
        "fitbit_report.integrations.telegram.send_rich_report",
        fake_send_rich_report,
    )

    class Bot:
        token = "test-token"

        async def send_message(self, **kwargs):
            raise AssertionError("fallback must not run after rich delivery")

        async def send_photo(self, **kwargs):
            raise AssertionError("fallback must not run after rich delivery")

    chart_path = tmp_path / "dashboard.png"
    chart_path.write_bytes(b"png")
    result = ReportResult(
        "daily",
        DateRange(date(2026, 8, 12), date(2026, 8, 12)),
        Path("report.md"),
        "markdown",
        telegram_rich_html="<h1>Daily report</h1>",
        telegram_before_chart="intro",
        telegram_after_chart="body",
        chart_paths=(chart_path,),
    )

    asyncio.run(send_report(Bot(), 42, result, "en"))

    assert delivered == [{
        "token": "test-token",
        "chat_id": 42,
        "rich_html": "<h1>Daily report</h1>",
        "chart_path": chart_path,
    }]


def test_send_report_falls_back_to_intro_chart_body(monkeypatch, tmp_path):
    import asyncio
    from datetime import date
    from pathlib import Path

    from fitbit_report.integrations.telegram_rich import RichMessageError
    from fitbit_report.types import DateRange, ReportResult

    async def reject_rich_report(**kwargs):
        raise RichMessageError("not supported")

    monkeypatch.setattr(
        "fitbit_report.integrations.telegram.send_rich_report",
        reject_rich_report,
    )

    class Bot:
        token = "test-token"

        def __init__(self):
            self.actions = []

        async def send_message(self, **kwargs):
            self.actions.append(("message", kwargs["text"], kwargs.get("parse_mode")))

        async def send_photo(self, **kwargs):
            self.actions.append(("photo", kwargs["caption"], None))

    chart_path = tmp_path / "dashboard.png"
    chart_path.write_bytes(b"png")
    result = ReportResult(
        "daily",
        DateRange(date(2026, 8, 12), date(2026, 8, 12)),
        Path("report.md"),
        "markdown",
        telegram_rich_html="<h1>Daily report</h1>",
        telegram_before_chart="intro",
        telegram_after_chart="body",
        chart_paths=(chart_path,),
    )
    bot = Bot()

    asyncio.run(send_report(bot, 42, result, "en"))

    assert [action[0] for action in bot.actions] == ["message", "photo", "message"]
    assert bot.actions[0] == ("message", "intro", "HTML")
    assert bot.actions[2] == ("message", "body", "HTML")
