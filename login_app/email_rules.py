"""One free allowance per person (spec 2026-11-03): collapse address aliases
and refuse throwaway inboxes at registration."""
from functools import lru_cache
from pathlib import Path

_GMAIL = {'gmail.com', 'googlemail.com'}


def normalise_email(email: str) -> str:
    email = (email or '').strip().lower()
    if '@' not in email:
        return email
    local, domain = email.rsplit('@', 1)
    local = local.split('+', 1)[0]
    if domain in _GMAIL:
        local = local.replace('.', '')
        domain = 'gmail.com'
    return f'{local}@{domain}'


@lru_cache(maxsize=1)
def _disposable() -> frozenset:
    path = Path(__file__).parent / 'data' / 'disposable_domains.txt'
    return frozenset(line.strip().lower() for line in path.read_text().splitlines() if line.strip())


def is_disposable(email: str) -> bool:
    domain = (email or '').rsplit('@', 1)[-1].strip().lower()
    return domain in _disposable()


def normalised_email_taken(email: str) -> bool:
    from django.contrib.auth import get_user_model
    target = normalise_email(email)
    domain = target.rsplit('@', 1)[-1]
    users = get_user_model().objects
    candidates = users.filter(email__iregex=r'@(gmail|googlemail)\.com$') if domain == 'gmail.com' \
        else users.filter(email__iendswith='@' + domain)
    return any(normalise_email(u.email) == target for u in candidates.only('email'))
