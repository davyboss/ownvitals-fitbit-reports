import pytest

from fitbit_report.journal.fatsecret import (
    MAX_FATSECRET_PDF_BYTES,
    MAX_FATSECRET_PDF_PAGES,
    MAX_FATSECRET_PDF_TEXT_CHARS,
    FatSecretParseError,
    extract_fatsecret_pdf,
    import_fatsecret_pdf_bytes,
    import_fatsecret_url,
    parse_fatsecret_text,
)


def test_fatsecret_pdf_import_rejects_oversized_input_before_parsing(tmp_path):
    with pytest.raises(FatSecretParseError, match="слишком большой"):
        import_fatsecret_pdf_bytes(
            b"%PDF-" + b"x" * MAX_FATSECRET_PDF_BYTES,
            "telegram://fatsecret/test",
            object(),
            tmp_path,
            object(),
        )


def test_fatsecret_pdf_import_rejects_non_pdf_input_before_parsing(tmp_path):
    with pytest.raises(FatSecretParseError, match="не похож на PDF"):
        import_fatsecret_pdf_bytes(
            b"not a pdf",
            "telegram://fatsecret/test",
            object(),
            tmp_path,
            object(),
        )


def test_fatsecret_pdf_import_rejects_too_many_pages(tmp_path):
    from io import BytesIO

    from pypdf import PdfWriter

    writer = PdfWriter()
    for _ in range(MAX_FATSECRET_PDF_PAGES + 1):
        writer.add_blank_page(width=100, height=100)
    buffer = BytesIO()
    writer.write(buffer)

    with pytest.raises(FatSecretParseError, match="слишком много страниц"):
        import_fatsecret_pdf_bytes(
            buffer.getvalue(),
            "telegram://fatsecret/test",
            object(),
            tmp_path,
            object(),
        )


def test_fatsecret_pdf_extraction_rejects_excessive_text(monkeypatch):
    import pypdf

    class Page:
        def extract_text(self, *args, **kwargs):
            return "x" * (MAX_FATSECRET_PDF_TEXT_CHARS + 1)

    class Reader:
        is_encrypted = False
        pages = [Page()]

    monkeypatch.setattr(pypdf, "PdfReader", lambda stream: Reader())

    with pytest.raises(FatSecretParseError, match="слишком много текста"):
        extract_fatsecret_pdf(b"%PDF-test", "telegram://fatsecret/test")


def test_fatsecret_url_download_stops_when_stream_crosses_byte_limit(
    monkeypatch,
    tmp_path,
):
    import httpx

    class Response:
        headers = {}

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def raise_for_status(self):
            return None

        def iter_bytes(self):
            yield b"%PDF-" + b"x" * (MAX_FATSECRET_PDF_BYTES // 2)
            yield b"x" * (MAX_FATSECRET_PDF_BYTES // 2)

    class Client:
        def __init__(self, **kwargs):
            assert kwargs["follow_redirects"] is False

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def stream(self, method, url):
            return Response()

    monkeypatch.setattr(httpx, "Client", Client)

    with pytest.raises(FatSecretParseError, match="слишком большой"):
        import_fatsecret_url(
            "https://foods.fatsecret.com/report.pdf",
            object(),
            tmp_path,
            object(),
        )


def test_fatsecret_url_import_requires_https():
    from fitbit_report.journal.fatsecret import is_fatsecret_pdf_url

    assert is_fatsecret_pdf_url("https://foods.fatsecret.com/report.pdf")
    assert not is_fatsecret_pdf_url("http://foods.fatsecret.com/report.pdf")
    assert not is_fatsecret_pdf_url("https://fatsecret.example/report.pdf")


def test_fatsecret_parser_reads_meals_foods_and_nutrients():
    text = """
    Food Diary Report - Detailed Report
    Wednesday, August 20, 2026
    Cals Fat Sat Carbs Fiber Sugar Prot Sod Chol Potas
    Breakfast
    Овсянка с бананом
    420
    12.5
    2.1
    65.0
    8
    16
    18.5
    210
    0
    410
    1 порция, 350 г
    Total
    420
    12.5
    2.1
    65.0
    8
    16
    18.5
    210
    0
    410
    Dinner
    Курица с рисом
    650
    14
    4
    75
    3
    2
    45
    500
    90
    700
    1 тарелка
    """

    diary = parse_fatsecret_text(
        text,
        "https://foods.fatsecret.com/export/example-user/example-token/"
        "example-report/day/food/FoodDiary_260820_foods.pdf?lang=ru&mkt=RU",
    )

    assert diary.report_date.isoformat() == "2026-08-20"
    assert len(diary.foods) == 2
    assert diary.foods[0].meal_type == "breakfast"
    assert diary.foods[0].protein_g == 18.5
    assert diary.foods[1].serving == "1 тарелка"


def test_fatsecret_parser_accepts_serving_before_nutrients_and_inline_rows():
    text = """
    Food Diary Report - Detailed Report
    Breakfast
    Овсянка с бананом
    1 порция, 350 г
    420
    12.5
    2.1
    65
    8
    16
    18.5
    210
    0
    410
    Dinner
    Курица с рисом 1 тарелка 650 14 4 75 3 2 45 500 90 700
    """

    diary = parse_fatsecret_text(
        text,
        "https://foods.fatsecret.com/export/x/x/x/day/food/FoodDiary_260820_foods.pdf",
    )

    assert len(diary.foods) == 2
    assert diary.foods[0].serving == "1 порция, 350 г"
    assert diary.foods[1].food_name.startswith("Курица с рисом")
    assert diary.foods[1].calories == 650


def test_fatsecret_parser_treats_dash_nutrients_as_zero():
    diary = parse_fatsecret_text(
        """
        Breakfast
        Овсянка
        420 12.5 – 65 8 16 18.5 210 0 410
        """,
        "https://foods.fatsecret.com/export/x/x/x/day/food/FoodDiary_260820_foods.pdf",
    )

    assert diary.foods[0].saturated_fat_g == 0


def test_fatsecret_parser_excludes_russian_total_rows_and_keeps_partial_foods():
    diary = parse_fatsecret_text(
        """
        Завтрак
        Milbona Forest Fruits Dessert 415 145 52,5 2 48,5 13,5
        500 г
        Плов со Свининой 883 34,2 63,919 81,18 0,9 1,6 56,86 1081 790 3749
        Всего 1298 179,2 63,919 133,68 2,9 50,1 70,36 1081 790 3749
        Обед
        Стейк из Свинины или Котлета 273 15,67 5,63 0 0 0 30,8 437 103 407
        110 г
        Гречка Отварная 300 10,42 1,998 47,63 6,5 2,15 8,05 433 0 213
        250 г
        Всего 573 26,09 7,628 47,63 6,5 2,15 38,85 870 103 620
        Ужин
        Перекус/Другое
        Всего 1871 205,29 71,547 181,31 9,4 52,25 109,21 1951 893 4369
        """,
        "https://foods.fatsecret.com/export/x/x/x/day/food/FoodDiary_260824_foods.pdf",
    )

    assert [food.food_name for food in diary.foods] == [
        "Milbona Forest Fruits Dessert",
        "Плов со Свининой",
        "Стейк из Свинины или Котлета",
        "Гречка Отварная",
    ]
    assert sum(food.calories or 0 for food in diary.foods) == 1871
    assert diary.foods[0].calories == 415
    assert diary.foods[0].protein_g is None
