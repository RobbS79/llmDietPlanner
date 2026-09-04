"""ISO-week helpers. A post batch is keyed by the ISO week it publishes in;
the generator runs on Sunday and prepares the *following* week."""
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

KIND_OFFSETS = {'deals': 0, 'recipe': 2, 'showcase': 4}   # Mon, Wed, Fri

PRAGUE = ZoneInfo('Europe/Prague')


def iso_week(d: date) -> str:
    year, week, _ = d.isocalendar()
    return f'{year}-W{week:02d}'


def week_start(iso: str) -> date:
    """Raises ValueError for a week the year does not have."""
    year, week = iso.split('-W')
    return date.fromisocalendar(int(year), int(week), 1)


def next_iso_week(today: date) -> str:
    """Returns the ISO week after the one containing `today`; a run that
    slips past Monday targets a different week (pass --week to recover)."""
    return iso_week(today + timedelta(days=7))


def scheduled_date(iso: str, kind: str) -> date:
    return week_start(iso) + timedelta(days=KIND_OFFSETS[kind])


def prague_today() -> date:
    """Calendar date in Prague. The container runs UTC and settings define no
    TIME_ZONE, so a 23:30 UTC job would otherwise think it is still yesterday."""
    return datetime.now(PRAGUE).date()
