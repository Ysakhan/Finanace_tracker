import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'finance_tracker.settings')
django.setup()

from django.test import Client
from django.contrib.auth.models import User
import json

c = Client()

# Create test user if not exists
user, created = User.objects.get_or_create(username='testuser')
if created:
    user.set_password('testpass123')
    user.save()
    print('Created test user')

# Login
login_ok = c.login(username='testuser', password='testpass123')
print(f'Login: {login_ok}')

# Test all pages
pages = [
    ('/', 'Dashboard'),
    ('/emis/', 'EMI List'),
    ('/emis/add/', 'EMI Add'),
    ('/debts/', 'Debts/Credits'),
    ('/debts/add/', 'Debt Add'),
    ('/balance/update/', 'Balance Update'),
    ('/transactions/', 'Transactions'),
    ('/transactions/add/', 'Transaction Add'),
    ('/assistant/', 'AI Assistant'),
    ('/export/', 'Export'),
    ('/login/', 'Login'),
    ('/register/', 'Register'),
]

all_ok = True
for url, name in pages:
    resp = c.get(url)
    status = 'OK' if resp.status_code == 200 else 'FAIL'
    if resp.status_code != 200:
        all_ok = False
    print(f'  [{status}] {name:20s} {url:25s} -> {resp.status_code}')

# Test AI API endpoints
ai_queries = [
    'all details of emi and loans and debts credits',
    'this month emi',
    'all debts and credits',
    'balance'
]
for query in ai_queries:
    resp = c.post('/assistant/api/',
        data=json.dumps({'message': query}),
        content_type='application/json')
    status = "OK" if resp.status_code == 200 else "FAIL"
    print(f'  [{status}] AI Query "{query[:20]}..." -> {resp.status_code}')
    if resp.status_code == 200:
        data = json.loads(resp.content)
        txt = data.get('response', '')
        print(f'     Snippet: {txt[:80]}...')

# Test export downloads & print
export_urls = [
    ('/export/text/', 'Export Text'),
    ('/export/pdf/', 'Export PDF'),
    ('/export/print/', 'Export Print'),
]
for url, name in export_urls:
    resp = c.get(url)
    status = "OK" if resp.status_code in (200, 302) else "FAIL"
    print(f'  [{status}] {name:20s} {url:25s} -> {resp.status_code}')


print()
if all_ok:
    print('ALL PAGES WORKING!')
else:
    print('SOME PAGES FAILED - see above')
