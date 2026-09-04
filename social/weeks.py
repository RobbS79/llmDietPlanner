"""ISO-week helpers. A post batch is keyed by the ISO week it publishes in;
the generator runs on Sunday and prepares the *following* week."""
from datetime import date, timedelta

KIND_OFFSETS = {'deals': 0, 'recipe': 2, 'showcase': 4}   # Mon, Wed, Fri


def iso_week(d: date) -> str:
    year, week, _ = d.isocalendar()
    return f'{year}-W{week:02d}'


def week_start(iso: str) -> date:
    year, week = iso.split('-W')
    return date.fromisocalendar(int(year), int(week), 1)


def next_iso_week(today: date) -> str:
    return iso_week(today + timedelta(days=7))


def scheduled_date(iso: str, kind: str) -> date:
    return week_start(iso) + timedelta(days=KIND_OFFSETS[kind])
