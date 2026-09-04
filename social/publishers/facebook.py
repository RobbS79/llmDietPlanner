"""Meta Graph API: publish a photo post to the Vařto Page.
Needs a long-lived Page access token with pages_manage_posts + pages_read_engagement;
the app may stay in Development mode because the token owner admins the Page."""
import requests
from django.conf import settings

from . import PublishError

GRAPH = 'https://graph.facebook.com/v21.0'


def publish(*, caption: str, link: str, image: bytes, title: str = '',
            post_fn=requests.post) -> str:
    page_id, token = settings.FB_PAGE_ID, settings.FB_PAGE_ACCESS_TOKEN
    if not page_id or not token:
        raise PublishError('FB_PAGE_ID / FB_PAGE_ACCESS_TOKEN not configured')
    try:
        response = post_fn(
            f'{GRAPH}/{page_id}/photos',
            data={'message': f'{caption}\n\n{link}', 'published': 'true', 'access_token': token},
            files={'source': ('card.png', image, 'image/png')},
            timeout=60,
        )
    except requests.RequestException as exc:
        raise PublishError(f'facebook request failed: {exc}') from exc
    payload = _json(response)
    if response.status_code >= 400 or 'error' in payload:
        raise PublishError(f"facebook {response.status_code}: {payload.get('error', {}).get('message') or response.text[:300]}")
    return payload.get('post_id') or payload.get('id') or ''


def _json(response) -> dict:
    try:
        data = response.json()
        return data if isinstance(data, dict) else {}
    except ValueError:
        return {}
