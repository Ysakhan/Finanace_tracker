"""Quick end-to-end test of all pages and POST operations."""
import os, sys, django, json
os.environ['DJANGO_SETTINGS_MODULE'] = 'finance_tracker.settings'
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
django.setup()

from django.test import Client
from django.contrib.auth.models import User
from datetime import date

client = Client()
user, created = User.objects.get_or_create(username='testall')
user.set_password('testpass123')
user.save()
client.login(username='testall', password='testpass123')

current_month = date.today().strftime('%Y-%m')

# GET pages
print("=== GET PAGES ===")
get_pages = [
    ('/', 'dashboard'),
    ('/login/', 'login'),
    ('/register/', 'register'),
    ('/emis/', 'emi list'),
    ('/emis/add/', 'emi add form'),
    ('/beneficiaries/', 'beneficiary list'),
    ('/beneficiaries/add/', 'beneficiary add form'),
    ('/debts/', 'debts credits'),
    ('/debts/add/', 'debt add form'),
    ('/balance/update/', 'balance form'),
    ('/transactions/', 'transactions'),
    ('/transactions/add/', 'txn add form'),
    ('/assistant/', 'AI assistant'),
    ('/export/', 'export page'),
    ('/export/text/', 'export text'),
    ('/export/csv/', 'export csv'),
    ('/export/pdf/', 'export pdf'),
    ('/export/print/', 'export print'),
    ('/static/css/style.css', 'style.css static'),
    ('/static/js/app.js', 'app.js static'),
]

all_ok = True
for url, name in get_pages:
    r = client.get(url)
    ok = r.status_code in (200, 302)
    if not ok:
        all_ok = False
    mark = 'OK' if ok else 'FAIL'
    print(f'  [{mark}] {url:25s} -> {r.status_code} ({name})')

# POST operations
print()
print("=== POST OPERATIONS ===")
from finance.models import Beneficiary
test_ben = Beneficiary.objects.create(user=user, name='Test Person', phone_number='9876543210')

posts = [
    ('/emis/add/', {
        'title': 'Test EMI', 'due_day': 15, 'full_amount': 5000,
        'personal_share': 2500, 'split_with': 'Friend', 'shared_amount': 2500,
        'category': 'loan', 'month_year': current_month, 'notes': 'test'
    }, 'emi add'),
    ('/debts/add/', {
        'beneficiary': test_ben.id, 'debt_type': 'debt', 'original_amount': 1000,
        'reason': 'test debt'
    }, 'debt add'),

    ('/transactions/add/', {
        'title': 'Test Transaction', 'amount': 500, 'txn_type': 'expense',
        'category': 'expense', 'payment_mode': 'bank', 'date': '2026-07-21', 'description': 'test'
    }, 'txn add'),
    ('/balance/update/', {
        'bank_balance': 5000, 'cash_in_hand': 1200, 'credit_card_balance': -500
    }, 'balance update'),
]

for url, data, name in posts:
    r = client.post(url, data)
    ok = r.status_code in (200, 302)
    if not ok:
        all_ok = False
    mark = 'OK' if ok else 'FAIL'
    print(f'  [{mark}] {url:25s} -> {r.status_code} ({name})')

# Create a sample EMI with long-term loan & tenure tracking
from finance.models import MonthlyEMI
loan_emi = MonthlyEMI.objects.create(
    user=user,
    title='Home Loan EMI',
    due_day=10,
    full_amount=25000,
    personal_share=25000,
    category='emi',
    month_year=current_month,
    total_loan_amount=3000000,
    total_emis=120,
    paid_emis=15,
)

print("\n=== VERIFYING EXPORT CONTENTS ===")
res_txt = client.get('/export/text/')
assert b'Tenure' in res_txt.content and b'Rem Ten' in res_txt.content, "Text export missing tenure columns!"
print("  [OK] Text Export contains Tenure & Rem Ten headers")

res_csv = client.get('/export/csv/')
assert b'Total Tenure (EMIs)' in res_csv.content and b'Remaining Tenure (EMIs)' in res_csv.content, "CSV export missing tenure columns!"
print("  [OK] CSV Export contains Tenure & Rem Ten headers")

res_pdf = client.get('/export/pdf/')
assert res_pdf.status_code == 200, "PDF Export failed!"
print("  [OK] PDF Export returns status 200")

res_print = client.get('/export/print/')
assert b'Rem Tenure' in res_print.content, "Print export missing Rem Tenure!"
print("  [OK] Print Export contains Rem Tenure header")

print("\n=== VERIFYING FINANCIAL HEALTH ASSISTANT API ===")
res_health = client.post('/assistant/api/', data=json.dumps({'message': 'financial health check'}), content_type='application/json')
assert res_health.status_code == 200 and 'Health Score' in res_health.json().get('response', ''), "Assistant Health Check API failed!"
print("  [OK] Assistant Health Check API returns 200 and Health Score")

print()
if all_ok:
    print('ALL PAGES AND OPERATIONS PASS')
else:
    print('SOME FAILED')

user.delete()

