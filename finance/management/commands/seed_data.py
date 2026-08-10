from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from finance.models import AccountBalance, MonthlyEMI, SplitDebt
from datetime import date


class Command(BaseCommand):
    help = 'Seed database with initial financial data'

    def handle(self, *args, **options):
        current_month = date.today().strftime('%Y-%m')

        # Get or create first superuser
        user = User.objects.filter(is_superuser=True).first()
        if not user:
            user = User.objects.create_superuser('admin', 'admin@example.com', 'admin123')
            self.stdout.write(self.style.SUCCESS(f'Created superuser: {user.username}'))
        else:
            self.stdout.write(f'Using superuser: {user.username}')

        # Account Balance
        balance, created = AccountBalance.objects.get_or_create(user=user)
        balance.bank_balance = 3460.97
        balance.credit_card_balance = 0
        balance.save()
        self.stdout.write(self.style.SUCCESS(f'Bank balance set to Rs.{balance.bank_balance}'))

        # EMI Data
        emis = [
            {'title': 'Sundru Navi', 'due_day': 1, 'full_amount': 9800, 'personal_share': 4900, 'category': 'emi'},
            {'title': 'Aniyan Phone', 'due_day': 3, 'full_amount': 5585, 'personal_share': 0, 'category': 'emi'},
            {'title': 'Aniyan Money View', 'due_day': 3, 'full_amount': 2000, 'personal_share': 1000, 'category': 'emi'},
            {'title': 'Amma Money View', 'due_day': 5, 'full_amount': 2000, 'personal_share': 2000, 'category': 'emi'},
            {'title': 'Branch EMI', 'due_day': 5, 'full_amount': 5524, 'personal_share': 2762, 'category': 'emi'},
            {'title': 'Kissht Loan', 'due_day': 5, 'full_amount': 7917, 'personal_share': 7917, 'category': 'emi'},
            {'title': 'Navi Myself', 'due_day': 7, 'full_amount': 2272, 'personal_share': 2272, 'category': 'emi'},
            {'title': 'Kredit Bee', 'due_day': 8, 'full_amount': 5307, 'personal_share': 0, 'category': 'emi'},
        ]

        for emi_data in emis:
            emi, created = MonthlyEMI.objects.get_or_create(
                user=user,
                title=emi_data['title'],
                month_year=current_month,
                defaults={
                    'due_day': emi_data['due_day'],
                    'full_amount': emi_data['full_amount'],
                    'personal_share': emi_data['personal_share'],
                    'category': emi_data['category'],
                    'status': 'unpaid',
                }
            )
            if created:
                self.stdout.write(f'  Created EMI: {emi.title} - Rs.{emi.full_amount}')
            else:
                self.stdout.write(f'  EMI exists: {emi.title}')

        # Debts Owed
        debts = [
            {'person_name': 'Amma', 'amount': 2250, 'reason': 'Money borrowed from Amma'},
            {'person_name': 'Kavatta Split', 'amount': 333, 'reason': 'Shared expense split'},
        ]

        for debt_data in debts:
            obj, created = SplitDebt.objects.get_or_create(
                user=user,
                person_name=debt_data['person_name'],
                debt_type='debt',
                status='pending',
                defaults={
                    'original_amount': debt_data['amount'],
                    'reason': debt_data['reason'],
                }
            )
            if created:
                self.stdout.write(f'  Created debt: {obj.person_name} - Rs.{obj.original_amount}')

        # Credits Due
        credits = [
            {'person_name': 'Home Split', 'amount': 3757.67, 'reason': 'Home expense split'},
            {'person_name': 'Aarathi', 'amount': 2000, 'reason': 'Money owed by Aarathi'},
            {'person_name': 'YouTube Split', 'amount': 149.49, 'reason': 'YouTube subscription split'},
            {'person_name': 'Lulu Split', 'amount': 500, 'reason': 'Lulu expense split'},
            {'person_name': 'Misc Split', 'amount': 2188.18, 'reason': 'Miscellaneous splits'},
            {'person_name': 'Achu', 'amount': 182, 'reason': 'Money owed by Achu'},
        ]

        for credit_data in credits:
            obj, created = SplitDebt.objects.get_or_create(
                user=user,
                person_name=credit_data['person_name'],
                debt_type='credit',
                status='pending',
                defaults={
                    'original_amount': credit_data['amount'],
                    'reason': credit_data['reason'],
                }
            )
            if created:
                self.stdout.write(f'  Created credit: {obj.person_name} - Rs.{obj.original_amount}')

        self.stdout.write(self.style.SUCCESS('\nSeed data loaded successfully!'))
