"""
ASGI config for core project.

It exposes the ASGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/5.2/howto/deployment/asgi/
"""

import os

from django.core.asgi import get_asgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')

application = get_asgi_application()

# Step 6 ruling 5: the phone-home fires on app open and close — wired HERE
# because asgi.py is imported only by the server process, so manage.py
# commands, tests and celery never send anything. One total, silent offline.
from core.phone_home import wire_open_and_close  # noqa: E402

wire_open_and_close()
