"""Pinterest API v5: create a pin on the Vařto board from image bytes.
Trial access (granted to new apps on request) is enough to pin to your own account."""
import base64

import requests
from django.conf import settings

from . import PublishError, safe_json

API = 'https://api.pinterest.com/v5/pins'
MAX_DESCRIPTION = 800  # v5 spec limit


def publish(*, caption: str, link: str, image: bytes, title: str = '',
            post_fn=requests.post) -> str:
    token, board = settings.PINTEREST_ACCESS_TOKEN, settings.PINTEREST_BOARD_ID
    if not token or not board:
        raise PublishError('PINTEREST_ACCESS_TOKEN / PINTEREST_BOARD_ID not configured')
    body = {
        'board_id': board,
        'title': title[:100],
        'description': _truncate_description(caption, MAX_DESCRIPTION),
        'link': link,
        'alt_text': title[:500],
        'media_source': {'source_type': 'image_base64', 'content_type': 'image/png',
                         'data': base64.b64encode(image).decode()},
    }
    try:
        response = post_fn(API, json=body, headers={'Authorization': f'Bearer {token}'}, timeout=60)
    except requests.RequestException as exc:
        raise PublishError(f'pinterest request failed: {exc}') from exc
    payload = safe_json(response)
    if response.status_code >= 400 or not payload.get('id'):
        raise PublishError(f"pinterest {response.status_code}: {payload.get('message') or response.text[:300]}")
    return payload['id']


def _truncate_description(text: str, limit: int) -> str:
    """Cut at the last sentence end before `limit` if one exists past 60% of it,
    else at the last space, and append an ellipsis. Result length stays <= limit."""
    if len(text) <= limit:
        return text
    cut = text[:limit - 1]  # leave room for the appended ellipsis character
    threshold = int(limit * 0.6)
    sentence_end = max(cut.rfind('.'), cut.rfind('!'), cut.rfind('?'))
    if sentence_end >= threshold:
        return cut[:sentence_end + 1] + '…'
    space = cut.rfind(' ')
    if space > 0:
        return cut[:space] + '…'
    return cut + '…'
