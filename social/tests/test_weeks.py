from datetime import date, datetime, timezone
from unittest.mock import patch

from social.personas import PERSONA_PROMPTS, persona_for_week
from social.weeks import (
    KIND_OFFSETS, iso_week, next_iso_week, prague_today, scheduled_date,
    week_start,
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


def test_iso_year_can_differ_from_calendar_year():
    assert iso_week(date(2021, 1, 1)) == '2020-W53'
    assert iso_week(date(2024, 12, 30)) == '2025-W01'
    assert week_start('2026-W53') == date(2026, 12, 28)
    assert next_iso_week(date(2026, 12, 27)) == '2026-W53'
    assert scheduled_date('2026-W53', 'showcase') == date(2027, 1, 1)


def test_persona_for_week_returns_a_known_prompt():
    result = persona_for_week('2026-W37')
    assert result in PERSONA_PROMPTS
    assert persona_for_week('2026-W37') == result


def test_persona_for_week_covers_all_prompts_across_three_consecutive_weeks():
    results = {
        persona_for_week('2026-W37'),
        persona_for_week('2026-W38'),
        persona_for_week('2026-W39'),
    }
    assert results == set(PERSONA_PROMPTS)


def test_persona_for_week_does_not_repeat_across_year_boundary():
    assert persona_for_week('2025-W52') != persona_for_week('2026-W01')


def test_prague_today_rolls_over_before_utc_midnight():
    fixed = datetime(2026, 9, 6, 22, 30, tzinfo=timezone.utc)
    with patch('social.weeks.datetime') as mock_datetime:
        mock_datetime.now.side_effect = lambda tz=None: fixed.astimezone(tz)
        assert prague_today() == date(2026, 9, 7)
