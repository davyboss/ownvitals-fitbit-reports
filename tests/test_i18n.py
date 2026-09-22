import pytest
import re

from fitbit_report.i18n import (
    SUPPORTED_LOCALES,
    catalog_texts,
    translate,
    validate_catalogs,
)


def test_translation_catalogs_cover_every_supported_locale():
    assert SUPPORTED_LOCALES == ("en", "ru")
    validate_catalogs()


def test_missing_translation_fails_loudly():
    with pytest.raises(KeyError, match="missing translation"):
        translate("missing.key", "en")


def test_english_catalog_contains_no_cyrillic_copy():
    assert not any(
        re.search(r"[А-Яа-яЁё]", text)
        for text in catalog_texts("en")
    )


def test_journal_saved_confirmation_has_no_emoji():
    assert translate("common.saved", "ru") == "Записал в дневник."
    assert translate("common.saved", "en") == "Saved to your journal."
