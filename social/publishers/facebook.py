"""Meta Graph API: publish a photo post to the Vařto Page.
Needs a long-lived Page access token with pages_show_list, pages_manage_posts, and
pages_read_engagement; the token owner needs the CREATE_CONTENT task on the Page."""
import requests
from django.conf import settings

from . import PublishError, safe_json

GRAPH = 'https://graph.facebook.com/v24.0'


def publish(*, caption: str, link: str, image: bytes, title: str = '',
            post_fn=requests.post) -> str:
    page_id, token = settings.FB_PAGE_ID, settings.FB_PAGE_ACCESS_TOKEN
    if not page_id or not token:
        raise PublishError('FB_PAGE_ID / FB_PAGE_ACCESS_TOKEN not configured')
    text = f'{caption}\n\n{link}'
    try:
        response = post_fn(
            f'{GRAPH}/{page_id}/photos',
            # Meta deprecated `message` on /photos in favour of `caption`; send both
            # so the post renders correctly whichever field the API honours.
            data={'caption': text, 'message': text, 'published': 'true', 'access_token': token},
            files={'source': ('card.png', image, 'image/png')},
            timeout=60,
        )
    except requests.RequestException as exc:
        raise PublishError(f'facebook request failed: {exc}') from exc
    payload = safe_json(response)
    if response.status_code >= 400 or 'error' in payload:
        err = payload.get('error')
        detail = err.get('message') if isinstance(err, dict) else err
        raise PublishError(f'facebook {response.status_code}: {detail or response.text[:300]}')
    external_id = payload.get('post_id') or payload.get('id')
    if not external_id:
        raise PublishError(f'facebook {response.status_code}: no post id in response ({response.text[:200]})')
    return external_id
