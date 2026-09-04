"""One function per channel: publish(caption, link, image, title='', post_fn=requests.post) -> external id.
All raise PublishError with the platform's own message; nothing else escapes."""


class PublishError(Exception):
    pass


def safe_json(response) -> dict:
    """Parse a response body as JSON, treating anything non-dict (or non-JSON) as empty."""
    try:
        data = response.json()
        return data if isinstance(data, dict) else {}
    except ValueError:
        return {}


def get_publisher(channel: str):
    from . import facebook, pinterest
    return {'facebook': facebook.publish, 'pinterest': pinterest.publish}[channel]
