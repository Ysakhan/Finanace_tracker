from django.core.management.base import BaseCommand
from django.core.mail import send_mail
from django.conf import settings
from django.contrib.auth.models import User
from finance.models import AccountBalance, MonthlyEMI, SplitDebt
from datetime import date
from django.db.models import Sum


class Command(BaseCommand):
    help = 'Send email reminders for upcoming EMIs and debts'

    def add_arguments(self, parser):
        parser.add_argument(
            '--email', type=str, default=None,
            help='Recipient email address (default: user email)'
        )
        parser.add_argument(
            '--user', type=str, default=None,
            help='Username to send reminders for (default: all users)'
        )
        parser.add_argument(
            '--dry-run', action='store_true',
            help='Print email content without sending'
        )

    def handle(self, *args, **options):
        today = date.today()
        current_month = today.strftime('%Y-%m')

        # Filter by user if specified
        if options['user']:
            users = User.objects.filter(username=options['user'])
            if not users.exists():
                self.stdout.write(self.style.ERROR(f'User "{options["user"]}" not found'))
                return
        else:
            users = User.objects.filter(is_active=True)

        for user in users:
            self.stdout.write(f'\nProcessing user: {user.username}')

            balance = AccountBalance.get_instance(user)
            recipient = options['email'] or user.email

            # Get unpaid EMIs
            unpaid_emis = MonthlyEMI.objects.filter(
                user=user, month_year=current_month, status='unpaid'
            )

            # EMIs due in next 2 days
            upcoming = []
            overdue = []
            for emi in unpaid_emis:
                days_until = emi.due_day - today.day
                if days_until < 0:
                    overdue.append(emi)
                elif days_until <= 2:
                    upcoming.append(emi)

            # People who owe you for upcoming EMIs
            people_owe = []
            for emi in upcoming:
                collect = float(emi.full_amount) - float(emi.personal_share)
                if collect > 0:
                    people_owe.append(f"  • {emi.title}: Collect ₹{collect:,.2f}")

            # Outstanding credits
            credits = SplitDebt.objects.filter(
                user=user, debt_type='credit', status__in=['pending', 'partial']
            )
            total_credits = credits.aggregate(total=Sum('original_amount'))['total'] or 0

            # Build email content
            subject = f'💰 Finance Reminder - {today.strftime("%B %d, %Y")}'

            lines = [
                f'📊 FINANCE TRACKER - DAILY REMINDER',
                f'Date: {today.strftime("%A, %B %d, %Y")}',
                f'User: {user.username}',
                f'',
                f'💳 BALANCE:',
                f'  Bank: ₹{float(balance.bank_balance):,.2f}',
                f'  Credit Card: ₹{float(balance.credit_card_balance):,.2f}',
                f'',
            ]

            if overdue:
                lines.append(f'🔴 OVERDUE EMIs ({len(overdue)}):')
                for emi in overdue:
                    lines.append(f'  ❌ {emi.title} - ₹{float(emi.personal_share):,.2f} (Due Day {emi.due_day})')
                lines.append('')

            if upcoming:
                lines.append(f'🟡 UPCOMING EMIs (Next 2 Days - {len(upcoming)}):')
                for emi in upcoming:
                    lines.append(f'  ⏰ {emi.title} - ₹{float(emi.full_amount):,.2f} (Day {emi.due_day})')
                lines.append('')

            if people_owe:
                lines.append('👥 PEOPLE WHO OWE YOU FOR UPCOMING EMIs:')
                lines.extend(people_owe)
                lines.append('')

            if total_credits > 0:
                lines.append(f'💰 OUTSTANDING CREDITS: ₹{float(total_credits):,.2f}')
                for c in credits:
                    lines.append(f'  • {c.person_name}: ₹{float(c.remaining):,.2f}')
                lines.append('')

            remaining_total = unpaid_emis.aggregate(
                total=Sum('personal_share'))['total'] or 0
            lines.append(f'📋 TOTAL REMAINING EMIs THIS MONTH: ₹{float(remaining_total):,.2f}')

            message = '\n'.join(lines)

            if options['dry_run']:
                self.stdout.write(self.style.WARNING('DRY RUN - Email content:'))
                self.stdout.write(message)
                continue

            if not recipient:
                self.stdout.write(self.style.WARNING(
                    f'  No email for {user.username}. Use --email or set user email.'
                ))
                continue

            try:
                send_mail(
                    subject=subject,
                    message=message,
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    recipient_list=[recipient],
                    fail_silently=False,
                )
                self.stdout.write(self.style.SUCCESS(
                    f'  ✅ Reminder sent to {recipient}'
                ))
            except Exception as e:
                self.stdout.write(self.style.ERROR(
                    f'  ❌ Failed to send email: {e}'
                ))
                self.stdout.write(self.style.WARNING(
                    '  Tip: Configure EMAIL settings in settings.py or use --dry-run to preview'
                ))
