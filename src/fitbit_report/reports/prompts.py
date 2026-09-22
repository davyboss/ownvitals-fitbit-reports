import json

from fitbit_report.i18n import Locale
from fitbit_report.reports.context import ReportContext


PROMPT_VERSION = "18"


def _build_english_prompt(context: ReportContext) -> str:
    budgets = {
        "daily": "Return 4–6 claims, no more than 7; 3–4 recommendations and 1–2 experiments. ",
        "weekly": "Return 5–8 claims, no more than 8; 4–5 recommendations and 2–3 experiments. ",
        "monthly": "Return 6–10 claims, no more than 10; 4–6 recommendations and 2–4 experiments. ",
    }
    return (
        "Analyze only the supplied user data. Act as an autonomous personal analyst, not a "
        "questionnaire. Extract sleep, resting heart rate, HRV, activity, workouts, nutrition, "
        "check-ins, and personal baselines from the context yourself. Never ask the user to repeat "
        "or confirm a metric already present. If a metric is absent, say that the record is missing; "
        "do not replace that with a question. The report must be self-contained and must not contain "
        "follow-up questions. Hide technical field names and internal objects such as personal_state, "
        "baseline_28d, health_before_day, source_ids, and data_completeness; describe them as the "
        "user's readiness, personal baseline, state before the day, sources, and data completeness. "
        "Do not invent values. Write every textual field—summary, statement, recommendations, and "
        "experiments—in English. Separate facts, associations, and hypotheses. Consider sleep, daily "
        "activity, exercise sessions and their metrics, gym_training, nutrition, confirmed meal "
        "estimates, journal events, wellbeing, and productivity. Treat calories and nutrients inferred "
        "from photos as approximate ranges and respect their stated confidence. "
        + budgets[context.report_type]
        + "Claims must contain only decision-relevant findings: personal patterns, material deviations, "
        "conflicting data, or concrete next steps. Combine related metrics into synthetic findings. Do "
        "not turn every normal value or missing record into a separate claim, repeat the same conclusion, "
        "or add low-value items to fill the budget. Tie every recommendation to a strong finding and "
        "every experiment to a specific personal hypothesis. Use 7d, 14d, and 28d baselines as the "
        "user's personal norms and always account for sample counts. Do not make confident claims from "
        "insufficient or limited baselines, and do not use population norms. Missing logging does not "
        "prove that an event did not occur. Use exercise details for pace, splits, elevation, pauses, and "
        "GPS metadata. Use productivity_context as a timeline, distinguishing morning and evening "
        "check-ins, health_before_day, timeline, and baseline_28d. Compare sleep and wake times from "
        "health.sleep_timing_history rather than asking the user. Look for repeated relationships among "
        "sleep, prior load, workouts, meals, caffeine, nicotine, wellbeing, and work metrics. Never claim "
        "causality from one day. Start with personal_state as the calculated readiness estimate and explain "
        "which components and baseline deviations affected it. Use confirmed_facts as user-confirmed facts; "
        "respect rejected feedback and use helpful/not_helpful feedback to improve recommendations. Do not "
        "store a new hypothesis without explicit confirmation. Review personal_factors and factor_signals "
        "with sample counts and controls; mention sensitive factors neutrally and only when relevant. Analyze "
        "gym progress using loads, reps, sets, volume, and RPE without treating a single change as progress. "
        "Use health.nutrition as the unified meal list. Treat FatSecret calories and macros as exact imported "
        "values, photo estimates as ranges, and old free-text meals as lacking exact nutrition. Relate meal "
        "timing to workouts and productivity where evidence supports it. Do not diagnose or prescribe "
        "treatment. Temporal proximity alone is not an association; require repeated observations. Return "
        "JSON only with summary, claims, recommendations, experiments, confidence. Every claim must use "
        "exactly statement, kind, evidence_count, confidence, alternatives, source_ids. kind must be fact, "
        "association, or hypothesis. confidence must be insufficient, low, medium, or high. source_ids must "
        "contain string source references. recommendations and experiments must each be JSON arrays of "
        "plain strings, never objects.\n\n"
        + json.dumps(context.as_dict(), default=str, ensure_ascii=False)
    )


def build_prompt(context: ReportContext, locale: Locale = "ru") -> str:
    if locale == "en":
        return _build_english_prompt(context)
    if context.report_type == "daily":
        output_budget = "Для дневного отчёта верни 4–6 claims, не больше 7; 3–4 рекомендации и 1–2 эксперимента. "
    elif context.report_type == "weekly":
        output_budget = "Для недельного отчёта верни 5–8 claims, не больше 8; 4–5 рекомендаций и 2–3 эксперимента. "
    else:
        output_budget = "Для месячного отчёта верни 6–10 claims, не больше 10; 4–6 рекомендаций и 2–4 эксперимента. "
    return (
        "Проанализируй только предоставленные данные пользователя. Ты работаешь как автономный "
        "личный аналитик, а не как анкета для пользователя: сам извлекай из контекста сон, "
        "средний и текущий пульс покоя, HRV/ВСР, активность, тренировки, питание, check-in и "
        "личные нормы. Никогда не проси пользователя повторно сообщить или подтвердить показатель, "
        "если он уже есть в предоставленных данных. Если показатель отсутствует, прямо напиши, "
        "что записи нет; не заменяй это вопросом о значении, которое уже можно найти в контексте. "
        "Отчёт должен быть самодостаточным и не содержать блока уточняющих вопросов пользователю. "
        "Не показывай технические названия полей, JSON-ключи или внутренние объекты вроде "
        "personal_state, baseline_28d, health_before_day, source_ids и data_completeness — "
        "переводи их в нормальный русский язык: личная норма, состояние перед днём, источники и полнота данных. "
        "Не пиши фразы вроде «какой у тебя средний пульс?» или «сообщи свой HRV», если ответ есть в данных. "
        "Не выдумывай "
        "отсутствующие значения. Весь текст полей summary, statement, recommendations "
        "и experiments напиши на русском языке. Разделяй факт, ассоциацию и гипотезу; "
        "учитывай сон, дневную активность, отдельные спортивные тренировки и их метрики, тренировки в зале из gym_training, питание, подтверждённые оценки еды, дневник, самочувствие и продуктивность. "
        "Оценки калорий и нутриентов по фотографиям являются приблизительными диапазонами, а не точными значениями; учитывай их только с указанной уверенностью. "
        + output_budget
        + "Это не журнал всех полей: в claims попадают только выводы, которые меняют решение, показывают персональный паттерн, существенное отклонение, конфликт данных или конкретный следующий шаг. "
        "Не превращай каждую метрику, отсутствие записи или нормальное значение в отдельный claim. Своди несколько показателей в один синтетический вывод: например, отсутствие сна, пульса и ВСР объедини в один вывод о неполноте данных, если это влияет на readiness. "
        "Не повторяй один и тот же вывод в нескольких формулировках. Простые фразы «сон был X минут», «шагов было Y», «тренировки нет», «веса нет» и перечисление обычных значений запрещены как отдельные claims, если они не являются частью важного отклонения или объяснения. "
        "Не включай низкоценные пункты только ради заполнения лимита: лучше 3 сильных вывода, чем 10 очевидных. Каждая рекомендация должна быть привязана к одному из сильных выводов, а эксперимент — проверять конкретную персональную гипотезу. "
        "Используй baselines как личную норму пользователя: сравнивай показатели текущего периода с окнами 7d, 14d и 28d. Всегда указывай число наблюдений; не делай уверенных выводов по baseline со статусом insufficient или limited и не используй общепопуляционные нормы. "
        "Учитывай weight_summary для динамики веса и data_completeness для оценки полноты данных; отсутствие записи не доказывает отсутствие события. В exercise_sessions используй details для анализа пауз, сплитов, темпа, скорости, набора высоты и GPS-метаданных. "
        "Используй productivity_context как временную картину дня: отдельно анализируй утренний и вечерний check-in, health_before_day, timeline и baseline_28d. Для режима сна используй health.sleep_timing_history за последние 28 дней и текущие start_time/end_time: сам сравнивай время засыпания и пробуждения, не спрашивай пользователя, когда он лёг или встал, если эти интервалы есть в данных. Ищи повторяющиеся связи между сном, нагрузкой предыдущего дня, тренировками, питанием, кофеином, никотином, самочувствием и рабочими метриками. Не утверждай причинность по одному дню и явно указывай, когда данных недостаточно. "
        "В первую очередь используй personal_state как рассчитанную персональную оценку состояния пользователя. Объясняй, какие компоненты повлияли на readiness, насколько они отклоняются от его baseline и что делать сегодня. Не заменяй этот разбор общими советами Fitbit. "
        "Используй confirmed_facts как факты, подтверждённые самим пользователем. Учитывай feedback: rejected выводы не повторяй как истину, а helpful/not_helpful используй для улучшения будущих рекомендаций. Не записывай новую гипотезу в память без явного подтверждения пользователя. "
        "Обязательно проверь personal_factors: это специально выделенные личные события пользователя, включая интимные и чувствительные записи. Не игнорируй их. Используй factor_signals с числом наблюдений и сравнением с контрольными днями; если confidence insufficient, не делай вывод. Упоминай интимные факторы нейтрально и конфиденциально, только если они действительно относятся к вопросу анализа. "
        "В gym_training анализируй прогресс по упражнениям: рабочие веса, повторы, количество подходов, общий объём и RPE. Сопоставляй тренировочную нагрузку со сном, восстановлением и следующими check-in. Не объявляй прогрессом одно случайное изменение; ищи повторяющуюся динамику и отмечай пропуски или неполный разбор. "
        "Используй health.nutrition как единый структурированный список приёмов пищи. Основной источник точного питания — записи source=fatsecret из дневного PDF FatSecret: используй продукты, порции, calories и macros как фактические значения и связывай их с сохранённым временем приёма пищи. Для старых фото учитывай items, диапазоны calories и macros, confidence и uncertainty; для старых текстовых записей не придумывай калории и нутриенты. Учитывай nutrition_summary, время и тип приёма пищи, а также связь еды с тренировкой и продуктивностью. "
        "Не ставь диагнозы и не назначай лечение. Временная близость двух событий сама "
        "по себе не является ассоциацией или доказательством причины; для ассоциации "
        "нужны повторяющиеся наблюдения. Учитывай исправления пользователя. Верни "
        "только JSON с полями summary, claims, recommendations, experiments, confidence. "
        "Для каждого claim используй ровно ключи statement, kind, evidence_count, "
        "confidence, alternatives, source_ids. source_ids — это строковые ссылки на "
        "источники, например health.sleep:2026-08-14 или event:1. Используй kind, а не type. Допустимые "
        "kind: fact, association, hypothesis. Допустимые confidence: insufficient, low, "
        "medium, high; используй insufficient, а не none. Используй alternatives, а не "
        "alternative_explanations. recommendations и experiments должны быть JSON-массивами "
        "обычных строк, а не объектов.\n\n"
        + json.dumps(context.as_dict(), default=str, ensure_ascii=False)
    )
