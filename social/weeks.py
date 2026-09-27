"""ISO-week helpers. A post is keyed by the ISO week it publishes in; the
generator runs the evening before each publish day and drafts that one post."""
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

KIND_OFFSETS = {'deals': 0, 'recipe': 2, 'showcase': 4}   # Mon, Wed, Fri
WEEKDAYS_CS = ('pondělí', 'úterý', 'středa', 'čtvrtek', 'pátek', 'sobota', 'neděle')

PRAGUE = ZoneInfo('Europe/Prague')


def iso_week(d: date) -> str:
    year, week, _ = d.isocalendar()
    return f'{year}-W{week:02d}'


def week_start(iso: str) -> date:
    """Raises ValueError for a week the year does not have."""
    year, week = iso.split('-W')
    return date.fromisocalendar(int(year), int(week), 1)


def due_tomorrow(today: date):
    """(kind, iso_week) whose publish day is tomorrow, or None. The generator
    runs the evening before each publish day and drafts exactly that post."""
    tomorrow = today + timedelta(days=1)
    week = iso_week(tomorrow)
    for kind in KIND_OFFSETS:
        if scheduled_date(week, kind) == tomorrow:
            return kind, week
    return None


def cs_day(d: date) -> str:
    """Czech weekday + day.month, e.g. 'středa 23. 9.' — how the card names a day."""
    return f'{WEEKDAYS_CS[d.weekday()]} {d.day}. {d.month}.'


def scheduled_date(iso: str, kind: str) -> date:
    return week_start(iso) + timedelta(days=KIND_OFFSETS[kind])


def prague_today() -> date:
    """Calendar date in Prague. The container runs UTC and settings define no
    TIME_ZONE, so a 23:30 UTC job would otherwise think it is still yesterday."""
    return datetime.now(PRAGUE).date()
