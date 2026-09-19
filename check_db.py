import os
import sys
from pathlib import Path
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.development')
django.setup()

from django.db import connection

try:
    with connection.cursor() as cursor:
        cursor.execute("SELECT 1;")
    print("MYSQL_CONNECTION_SUCCESS")
except Exception as e:
    print(f"MYSQL_CONNECTION_FAILURE: {e}")
