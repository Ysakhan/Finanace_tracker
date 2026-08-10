from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from finance.models import MonthlyEMI
from datetime import date
from dateutil.relativedelta import relativedelta


class Command(BaseCommand):
    help = 'Rollover unpaid EMIs to new month and generate next month schedule'

    def add_arguments(self, parser):
        parser.add_argument(
            '--force', action='store_true',
            help='Force rollover even if not 1st of month'
        )
        parser.add_argument(
            '--user', type=str, default=None,
            help='Username to rollover (default: all users)'
        )

    def handle(self, *args, **options):
        today = date.today()

        # Only run on 1st of month unless forced
        if today.day != 1 and not options['force']:
            self.stdout.write(self.style.WARNING(
                'Not the 1st of month. Use --force to run anyway.'
            ))
            return

        # Previous month
        prev_month = (today - relativedelta(months=1)).strftime('%Y-%m')
        current_month = today.strftime('%Y-%m')

        self.stdout.write(f'Rollover: {prev_month} → {current_month}')

        # Filter by user if specified
        if options['user']:
            users = User.objects.filter(username=options['user'])
            if not users.exists():
                self.stdout.write(self.style.ERROR(f'User "{options["user"]}" not found'))
                return
        else:
            users = User.objects.all()

        for user in users:
            self.stdout.write(f'\nProcessing user: {user.username}')

            # Get unpaid EMIs from previous month
            unpaid_emis = MonthlyEMI.objects.filter(
                user=user, month_year=prev_month, status='unpaid'
            )

            rollover_count = 0
            for emi in unpaid_emis:
                # Check if already exists in current month
                exists = MonthlyEMI.objects.filter(
                    user=user, title=emi.title, month_year=current_month
                ).exists()

                if not exists:
                    # Create overdue copy for current month
                    MonthlyEMI.objects.create(
                        user=user,
                        title=emi.title,
                        due_day=emi.due_day,
                        full_amount=emi.full_amount,
                        personal_share=emi.personal_share,
                        split_with=emi.split_with,
                        category=emi.category,
                        status='overdue',
                        month_year=current_month,
                        notes=f'Rolled over from {prev_month}. {emi.notes}',
                    )
                    rollover_count += 1
                    self.stdout.write(f'  Rolled over: {emi.title} (overdue)')

            # Also mark remaining previous month EMIs as overdue
            unpaid_emis.update(status='overdue')

            # Generate fresh schedule for paid EMIs from prev month
            paid_emis = MonthlyEMI.objects.filter(
                user=user, month_year=prev_month, status='paid'
            )

            new_count = 0
            for emi in paid_emis:
                exists = MonthlyEMI.objects.filter(
                    user=user, title=emi.title, month_year=current_month
                ).exists()

                if not exists:
                    MonthlyEMI.objects.create(
                        user=user,
                        title=emi.title,
                        due_day=emi.due_day,
                        full_amount=emi.full_amount,
                        personal_share=emi.personal_share,
                        split_with=emi.split_with,
                        category=emi.category,
                        status='unpaid',
                        month_year=current_month,
                    )
                    new_count += 1
                    self.stdout.write(f'  New schedule: {emi.title} (unpaid)')

            self.stdout.write(self.style.SUCCESS(
                f'  ✅ {rollover_count} overdue, {new_count} new schedules'
            ))

        self.stdout.write(self.style.SUCCESS('\n✅ Rollover complete!'))
