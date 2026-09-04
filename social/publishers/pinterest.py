"""Pinterest API v5: create a pin on the Vařto board from image bytes.
Trial access (granted to new apps on request) is enough to pin to your own account."""
import base64

import requests
from django.conf import settings

from . import PublishError

API = 'https://api.pinterest.com/v5/pins'
MAX_DESCRIPTION = 500


def publish(*, caption: str, link: str, image: bytes, title: str = '',
            post_fn=requests.post) -> str:
    token, board = settings.PINTEREST_ACCESS_TOKEN, settings.PINTEREST_BOARD_ID
    if not token or not board:
        raise PublishError('PINTEREST_ACCESS_TOKEN / PINTEREST_BOARD_ID not configured')
    body = {
        'board_id': board,
        'title': title[:100],
        'description': caption[:MAX_DESCRIPTION],
        'link': link,
        'media_source': {'source_type': 'image_base64', 'content_type': 'image/png',
                         'data': base64.b64encode(image).decode()},
    }
    try:
        response = post_fn(API, json=body, headers={'Authorization': f'Bearer {token}'}, timeout=60)
    except requests.RequestException as exc:
        raise PublishError(f'pinterest request failed: {exc}') from exc
    try:
        payload = response.json()
    except ValueError:
        payload = {}
    if response.status_code >= 400 or not payload.get('id'):
        raise PublishError(f"pinterest {response.status_code}: {payload.get('message') or response.text[:300]}")
    return payload['id']
