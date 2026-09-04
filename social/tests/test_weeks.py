from datetime import date

from social.weeks import (
    KIND_OFFSETS, iso_week, next_iso_week, scheduled_date, week_start,
)


def test_iso_week_formats_year_and_zero_padded_week():
    assert iso_week(date(2026, 9, 7)) == '2026-W37'
    assert iso_week(date(2026, 1, 1)) == '2026-W01'


def test_week_start_is_monday():
    assert week_start('2026-W37') == date(2026, 9, 7)
    assert week_start('2026-W37').weekday() == 0


def test_next_iso_week_from_sunday_is_the_coming_week():
    assert next_iso_week(date(2026, 9, 6)) == '2026-W37'   # Sunday
    assert next_iso_week(date(2026, 9, 9)) == '2026-W38'   # Wednesday


def test_scheduled_dates_land_on_mon_wed_fri():
    assert scheduled_date('2026-W37', 'deals') == date(2026, 9, 7)
    assert scheduled_date('2026-W37', 'recipe') == date(2026, 9, 9)
    assert scheduled_date('2026-W37', 'showcase') == date(2026, 9, 11)
    assert set(KIND_OFFSETS) == {'deals', 'recipe', 'showcase'}
