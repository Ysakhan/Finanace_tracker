"""Reset finance app - drop old tables and clear migration history."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ['DJANGO_SETTINGS_MODULE'] = 'finance_tracker.settings'

import django
django.setup()

from django.db import connection
cursor = connection.cursor()

tables = [
    'finance_transactionhistory',
    'finance_splitdebt', 
    'finance_monthlyemi',
    'finance_accountbalance'
]

for t in tables:
    try:
        cursor.execute(f'DROP TABLE IF EXISTS {t}')
        print(f'Dropped {t}')
    except Exception as e:
        print(f'Error dropping {t}: {e}')

cursor.execute("DELETE FROM django_migrations WHERE app='finance'")
print('Cleared migration history')
print('Done - ready for fresh migrations')
