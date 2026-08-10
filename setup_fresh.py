"""Run this script to reset and setup the finance app fresh.
Usage: python setup_fresh.py
"""
import os, sys

# Setup Django
os.environ['DJANGO_SETTINGS_MODULE'] = 'finance_tracker.settings'
import django
django.setup()

from django.db import connection
from django.core.management import call_command

cursor = connection.cursor()

# Drop old tables
tables = [
    'finance_transactionhistory',
    'finance_splitdebt',
    'finance_monthlyemi',
    'finance_accountbalance',
]

for t in tables:
    try:
        cursor.execute(f'DROP TABLE IF EXISTS "{t}"')
        print(f'  Dropped table: {t}')
    except Exception as e:
        print(f'  Skip {t}: {e}')

# Clear old migration records
cursor.execute("DELETE FROM django_migrations WHERE app='finance'")
print('\n  Cleared migration history')

print('\n--- Running makemigrations ---')
call_command('makemigrations', 'finance')

print('\n--- Running migrate ---')
call_command('migrate')

print('\n--- Creating superuser (admin/admin123) ---')
from django.contrib.auth.models import User
if not User.objects.filter(username='admin').exists():
    User.objects.create_superuser('admin', 'admin@example.com', 'admin123')
    print('  Superuser created: admin / admin123')
else:
    print('  Superuser already exists')

print('\n--- Seeding data ---')
call_command('seed_data')

print('\n=== SETUP COMPLETE ===')
print('Run: python manage.py runserver')
print('Login: admin / admin123')
