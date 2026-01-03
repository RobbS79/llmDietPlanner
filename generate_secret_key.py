#!/usr/bin/env python
"""Generate a Django secret key for production use."""
from django.core.management.utils import get_random_secret_key

if __name__ == '__main__':
    print(get_random_secret_key())


