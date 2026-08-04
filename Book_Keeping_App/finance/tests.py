from django.test import TestCase, Client
from django.contrib.auth.models import User
from decimal import Decimal
from datetime import date
from finance.models import AccountBalance, Beneficiary, TransactionHistory, TransactionSplit, SplitDebt


class TransactionFeatureTestCase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='testuser', password='password123')
        self.client = Client()
        self.client.login(username='testuser', password='password123')
        self.balance = AccountBalance.get_instance(self.user)
        self.balance.bank_balance = Decimal('10000.00')
        self.balance.cash_in_hand = Decimal('5000.00')
        self.balance.credit_card_balance = Decimal('1000.00')
        self.balance.save()

        self.b1 = Beneficiary.objects.create(user=self.user, name='Alice', phone_number='9876543210')
        self.b2 = Beneficiary.objects.create(user=self.user, name='Bob', phone_number='9876543211')

    def test_bank_expense_updates_balance(self):
        response = self.client.post('/transactions/add/', {
            'title': 'Dinner Expense',
            'amount': '1200.00',
            'txn_type': 'expense',
            'payment_mode': 'bank',
            'date': '2026-08-01',
            'category': 'expense',
            'description': 'Team dinner'
        })
        self.assertEqual(response.status_code, 302)
        
        # Verify transaction
        txn = TransactionHistory.objects.get(title='Dinner Expense')
        self.assertEqual(txn.amount, Decimal('-1200.00'))
        self.assertEqual(txn.payment_mode, 'bank')
        self.assertEqual(txn.date, date(2026, 8, 1))

        # Verify balance updated
        self.balance.refresh_from_db()
        self.assertEqual(self.balance.bank_balance, Decimal('8800.00'))

    def test_cash_expense_updates_balance(self):
        self.client.post('/transactions/add/', {
            'title': 'Groceries',
            'amount': '500.00',
            'txn_type': 'expense',
            'payment_mode': 'cash',
            'date': '2026-08-02',
            'category': 'expense'
        })
        self.balance.refresh_from_db()
        self.assertEqual(self.balance.cash_in_hand, Decimal('4500.00'))

    def test_credit_card_expense_updates_balance(self):
        self.client.post('/transactions/add/', {
            'title': 'Gadget Store',
            'amount': '2000.00',
            'txn_type': 'expense',
            'payment_mode': 'credit_card',
            'date': '2026-08-03',
            'category': 'expense'
        })
        self.balance.refresh_from_db()
        self.assertEqual(self.balance.credit_card_balance, Decimal('3000.00'))

    def test_split_transaction_creates_split_debts(self):
        response = self.client.post('/transactions/add/', {
            'title': 'Group Party',
            'amount': '3000.00',
            'txn_type': 'expense',
            'payment_mode': 'bank',
            'date': '2026-08-04',
            'category': 'expense',
            'enable_split': 'on',
            'split_beneficiary_id[]': [str(self.b1.id), str(self.b2.id)],
            'split_person_name[]': ['Alice', 'Bob'],
            'split_amount[]': ['1000.00', '1000.00'],
            'split_type[]': ['credit', 'credit']
        })
        self.assertEqual(response.status_code, 302)

        txn = TransactionHistory.objects.get(title='Group Party')
        self.assertTrue(txn.is_split)
        self.assertEqual(txn.splits.count(), 2)

        # Verify SplitDebt entries
        debts = SplitDebt.objects.filter(user=self.user)
        self.assertEqual(debts.count(), 2)
        alice_debt = debts.get(person_name='Alice')
        self.assertEqual(alice_debt.original_amount, Decimal('1000.00'))
        self.assertEqual(alice_debt.debt_type, 'credit')

    def test_debt_settlement_cash_updates_cash_balance(self):
        # Create credit (They owe me ₹1500)
        debt = SplitDebt.objects.create(
            user=self.user, beneficiary=self.b1, person_name='Alice',
            debt_type='credit', original_amount=Decimal('1500.00')
        )

        # Collect ₹1000 cash from Alice
        response = self.client.post(f'/debts/{debt.pk}/settle/', {
            'amount': '1000.00',
            'payment_mode': 'cash'
        })
        self.assertEqual(response.status_code, 302)

        debt.refresh_from_db()
        self.assertEqual(debt.amount_paid, Decimal('1000.00'))
        self.assertEqual(debt.remaining, Decimal('500.00'))

        # Cash in hand should increase from 5000 to 6000
        self.balance.refresh_from_db()
        self.assertEqual(self.balance.cash_in_hand, Decimal('6000.00'))

    def test_transfer_cash_to_bank(self):
        response = self.client.post('/transfer/', {
            'from_account': 'cash',
            'to_account': 'bank',
            'amount': '2000.00',
            'date': '2026-08-04',
            'description': 'ATM Deposit'
        })
        self.assertEqual(response.status_code, 302)

        self.balance.refresh_from_db()
        self.assertEqual(self.balance.cash_in_hand, Decimal('3000.00'))
        self.assertEqual(self.balance.bank_balance, Decimal('12000.00'))

    def test_transfer_bank_to_credit_card(self):
        response = self.client.post('/transfer/', {
            'from_account': 'bank',
            'to_account': 'credit_card',
            'amount': '500.00',
            'date': '2026-08-04',
            'description': 'CC Bill Pay'
        })
        self.assertEqual(response.status_code, 302)

        self.balance.refresh_from_db()
        self.assertEqual(self.balance.bank_balance, Decimal('9500.00'))
        self.assertEqual(self.balance.credit_card_balance, Decimal('500.00'))

    def test_emi_mark_paid_by_me_cash(self):
        from finance.models import MonthlyEMI
        emi = MonthlyEMI.objects.create(
            user=self.user, title='WiFi Bill', due_day=5,
            full_amount=Decimal('1000.00'), personal_share=Decimal('1000.00'),
            category='other', month_year='2026-08'
        )
        response = self.client.post(f'/emis/{emi.pk}/mark-paid/', {
            'paid_by': 'me',
            'payment_mode': 'cash'
        })
        self.assertEqual(response.status_code, 302)

        emi.refresh_from_db()
        self.assertEqual(emi.status, 'paid')
        self.balance.refresh_from_db()
        self.assertEqual(self.balance.cash_in_hand, Decimal('4000.00'))

        txn = TransactionHistory.objects.get(title='EMI Paid: WiFi Bill')
        self.assertEqual(txn.payment_mode, 'cash')
        self.assertEqual(txn.amount, Decimal('-1000.00'))

    def test_emi_mark_paid_by_me_credit_card(self):
        from finance.models import MonthlyEMI
        emi = MonthlyEMI.objects.create(
            user=self.user, title='Laptop EMI', due_day=10,
            full_amount=Decimal('3000.00'), personal_share=Decimal('3000.00'),
            category='emi', month_year='2026-08'
        )
        response = self.client.post(f'/emis/{emi.pk}/mark-paid/', {
            'paid_by': 'me',
            'payment_mode': 'credit_card'
        })
        self.assertEqual(response.status_code, 302)

        emi.refresh_from_db()
        self.assertEqual(emi.status, 'paid')
        self.balance.refresh_from_db()
        self.assertEqual(self.balance.credit_card_balance, Decimal('4000.00'))

    def test_emi_mark_paid_by_split_person(self):
        from finance.models import MonthlyEMI
        emi = MonthlyEMI.objects.create(
            user=self.user, title='Rent Share', due_day=1,
            full_amount=Decimal('12000.00'), personal_share=Decimal('6000.00'),
            split_with='Roommate', category='rent', month_year='2026-08'
        )
        response = self.client.post(f'/emis/{emi.pk}/mark-paid/', {
            'paid_by': 'split_person',
            'payer_name': 'Roommate'
        })
        self.assertEqual(response.status_code, 302)

        emi.refresh_from_db()
        self.assertEqual(emi.status, 'paid')

        # Balances MUST be unchanged!
        self.balance.refresh_from_db()
        self.assertEqual(self.balance.bank_balance, Decimal('10000.00'))
        self.assertEqual(self.balance.cash_in_hand, Decimal('5000.00'))
        self.assertEqual(self.balance.credit_card_balance, Decimal('1000.00'))

        txn = TransactionHistory.objects.get(title='EMI Paid by Roommate: Rent Share')
        self.assertEqual(txn.amount, Decimal('0.00'))

    def test_emi_reversal(self):
        from finance.models import MonthlyEMI
        emi = MonthlyEMI.objects.create(
            user=self.user, title='Gym Sub', due_day=15,
            full_amount=Decimal('500.00'), personal_share=Decimal('500.00'),
            category='subscription', month_year='2026-08'
        )
        # Pay via cash
        self.client.post(f'/emis/{emi.pk}/mark-paid/', {'paid_by': 'me', 'payment_mode': 'cash'})
        self.balance.refresh_from_db()
        self.assertEqual(self.balance.cash_in_hand, Decimal('4500.00'))

        # Revert to unpaid
        self.client.post(f'/emis/{emi.pk}/mark-paid/')
        emi.refresh_from_db()
        self.assertEqual(emi.status, 'unpaid')
        self.balance.refresh_from_db()
        self.assertEqual(self.balance.cash_in_hand, Decimal('5000.00'))

    def test_custom_category_creation_on_the_fly(self):
        from finance.models import Category
        response = self.client.post('/transactions/add/', {
            'title': 'Pet Food',
            'amount': '1500.00',
            'txn_type': 'expense',
            'category': '__add_new__',
            'custom_category': 'Pet Supplies',
            'payment_mode': 'bank',
            'date': '2026-08-04'
        })
        self.assertEqual(response.status_code, 302)

        cat_exists = Category.objects.filter(user=self.user, name='Pet Supplies').exists()
        self.assertTrue(cat_exists)

        txn = TransactionHistory.objects.get(title='Pet Food')
        self.assertEqual(txn.display_category, 'Pet Supplies')

    def test_transaction_history_category_breakdown(self):
        self.client.post('/transactions/add/', {
            'title': 'Restaurant', 'amount': '2000.00', 'txn_type': 'expense',
            'category': 'Food & Dining', 'payment_mode': 'bank', 'date': '2026-08-04'
        })
        self.client.post('/transactions/add/', {
            'title': 'Shirt', 'amount': '1000.00', 'txn_type': 'expense',
            'category': 'Shopping', 'payment_mode': 'bank', 'date': '2026-08-04'
        })

        response = self.client.get('/transactions/?month=2026-08')
        self.assertEqual(response.status_code, 200)
        self.assertIn('category_breakdown', response.context)
        self.assertIn('top_category', response.context)
        self.assertEqual(response.context['top_category']['name'], 'Food & Dining')

    def test_transaction_edit_marks_edited(self):
        txn = TransactionHistory.objects.create(
            user=self.user, title='Grocery', amount=Decimal('-500.00'),
            category='Food & Dining', payment_mode='bank', date='2026-08-01'
        )
        self.balance.bank_balance -= Decimal('500.00')
        self.balance.save()

        response = self.client.post(f'/transactions/{txn.pk}/edit/', {
            'title': 'Supermarket Grocery',
            'amount': '800.00',
            'txn_type': 'expense',
            'category': 'Food & Dining',
            'payment_mode': 'bank',
            'date': '2026-08-01'
        })
        self.assertEqual(response.status_code, 302)

        txn.refresh_from_db()
        self.assertEqual(txn.title, 'Supermarket Grocery')
        self.assertEqual(txn.amount, Decimal('-800.00'))
        self.assertTrue(txn.is_edited)

        # Balance updated (9200.00)
        self.balance.refresh_from_db()
        self.assertEqual(self.balance.bank_balance, Decimal('9200.00'))

    def test_category_delete_reassigns_transactions(self):
        from finance.models import Category
        cat = Category.objects.create(user=self.user, name='Gaming', type='expense')
        txn = TransactionHistory.objects.create(
            user=self.user, title='Steam Game', amount=Decimal('-1200.00'),
            category='Gaming', payment_mode='bank', date='2026-08-02'
        )

        response = self.client.post(f'/categories/{cat.pk}/delete/', {
            'reassign_action': 'transfer',
            'target_category': 'Entertainment'
        })
        self.assertEqual(response.status_code, 302)

        # Category deleted
        self.assertFalse(Category.objects.filter(pk=cat.pk).exists())

        # Transaction reassigned to Entertainment
        txn.refresh_from_db()
        self.assertEqual(txn.category, 'Entertainment')

    def test_transaction_history_custom_date_filter(self):
        TransactionHistory.objects.create(
            user=self.user, title='Jan Expense', amount=Decimal('-300.00'),
            category='Bills', payment_mode='bank', date='2026-01-15'
        )
        TransactionHistory.objects.create(
            user=self.user, title='Aug Expense', amount=Decimal('-400.00'),
            category='Bills', payment_mode='bank', date='2026-08-04'
        )

        response = self.client.get('/transactions/?date_mode=custom&date_from=2026-01-01&date_to=2026-01-31')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['total_count'], 1)
        self.assertEqual(response.context['transactions'][0].title, 'Jan Expense')



