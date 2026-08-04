from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
from datetime import date
from decimal import Decimal


class AccountBalance(models.Model):
    """Stores current bank, cash in hand, and credit card balances per user."""
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='balances', null=True, blank=True)
    bank_balance = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    cash_in_hand = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    credit_card_balance = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = "Account Balances"

    def __str__(self):
        return f"Bank: ₹{self.bank_balance} | Cash: ₹{self.cash_in_hand} | CC: ₹{self.credit_card_balance}"

    @classmethod
    def get_instance(cls, user=None):
        """Get or create account balance for a specific user."""
        if user and user.is_authenticated:
            obj, created = cls.objects.get_or_create(user=user)
        else:
            obj, created = cls.objects.get_or_create(pk=1)
        return obj

    @property
    def total_balance(self):
        return self.bank_balance + self.cash_in_hand - self.credit_card_balance

    @property
    def net_balance(self):
        return self.bank_balance + self.cash_in_hand - self.credit_card_balance


class MonthlyEMI(models.Model):
    """Tracks monthly EMI payments (personal + split)."""
    STATUS_CHOICES = [
        ('unpaid', 'Unpaid'),
        ('paid', 'Paid'),
        ('overdue', 'Overdue'),
    ]
    CATEGORY_CHOICES = [
        ('emi', 'EMI'),
        ('subscription', 'Subscription'),
        ('insurance', 'Insurance'),
        ('rent', 'Rent'),
        ('utilities', 'Utilities'),
        ('other', 'Other'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='emis', null=True, blank=True)
    title = models.CharField(max_length=200)
    due_day = models.IntegerField(help_text="Day of month (1-31)")
    full_amount = models.DecimalField(max_digits=10, decimal_places=2)
    personal_share = models.DecimalField(max_digits=10, decimal_places=2)
    split_with = models.CharField(max_length=200, blank=True, help_text="Comma-separated names")
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES, default='emi')
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='unpaid')
    month_year = models.CharField(max_length=7, help_text="Format: YYYY-MM")
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    paid_date = models.DateField(null=True, blank=True)

    # Optional Long-Term Loan Tracking Fields
    total_loan_amount = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True, help_text="Total loan amount")
    total_emis = models.IntegerField(null=True, blank=True, help_text="Total number of tenure EMIs")
    paid_emis = models.IntegerField(default=0, help_text="Number of EMIs paid so far")

    class Meta:
        verbose_name_plural = "Monthly EMIs"
        ordering = ['due_day']

    def __str__(self):
        return f"{self.title} - ₹{self.personal_share} (Day {self.due_day})"

    def mark_paid(self):
        self.status = 'paid'
        self.paid_date = date.today()
        self.paid_emis += 1
        self.save()
        # Deduct from user's account balance
        if self.user:
            balance = AccountBalance.get_instance(self.user)
        else:
            balance = AccountBalance.get_instance()
        balance.bank_balance -= self.personal_share
        balance.save()
        # Create transaction record
        TransactionHistory.objects.create(
            user=self.user,
            title=f"EMI Payment: {self.title}",
            amount=-self.personal_share,
            category='emi',
            description=f"EMI paid for {self.month_year}"
        )

    @property
    def split_amount(self):
        return self.full_amount - self.personal_share

    @property
    def remaining_emis(self):
        if self.total_emis is not None:
            return max(0, self.total_emis - self.paid_emis)
        return None

    @property
    def total_paid_amount(self):
        return Decimal(self.paid_emis) * self.full_amount

    @property
    def remaining_balance(self):
        if self.total_loan_amount is not None:
            rem = self.total_loan_amount - self.total_paid_amount
            return max(Decimal('0'), rem)
        return None

    @property
    def progress_percentage(self):
        if self.total_emis and self.total_emis > 0:
            pct = (self.paid_emis / self.total_emis) * 100
            return round(min(100.0, max(0.0, pct)), 1)
        return 0.0

    @property
    def formatted_due_day(self):
        d = self.due_day
        if 11 <= d <= 13:
            suffix = 'th'
        else:
            suffix = {1: 'st', 2: 'nd', 3: 'rd'}.get(d % 10, 'th')
        return f"{d}{suffix}"

    @property
    def next_due_date(self):
        today = date.today()
        day = min(max(1, self.due_day), 28)
        try:
            target = date(today.year, today.month, day)
            if target < today:
                if today.month == 12:
                    target = date(today.year + 1, 1, day)
                else:
                    target = date(today.year, today.month + 1, day)
            return target
        except Exception:
            return today

    @property
    def is_next_cycle_unlocked(self):
        today = date.today()
        return today.day >= 25

    @property
    def is_overdue(self):
        today = date.today()
        return (self.status == 'unpaid' and
                self.month_year == today.strftime('%Y-%m') and
                today.day > self.due_day)


class Beneficiary(models.Model):
    """Stores separate beneficiary / contact profiles."""
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='beneficiaries', null=True, blank=True)
    name = models.CharField(max_length=100)
    phone_number = models.CharField(max_length=20, blank=True, null=True, help_text="Phone number of beneficiary / contact")
    upi_id = models.CharField(max_length=50, blank=True, null=True, help_text="UPI ID / Bank details (Optional)")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name_plural = "Beneficiaries"
        ordering = ['name']

    def __str__(self):
        if self.phone_number:
            return f"{self.name} ({self.phone_number})"
        return self.name

    @property
    def active_debts(self):
        """Returns non-settled debts where I owe them."""
        return self.debts.filter(debt_type='debt').exclude(status='settled')

    @property
    def active_credits(self):
        """Returns non-settled credits where they owe me."""
        return self.debts.filter(debt_type='credit').exclude(status='settled')

    @property
    def total_debt_amount(self):
        """Total remaining debt I owe to this beneficiary."""
        return sum(d.remaining for d in self.active_debts)

    @property
    def total_credit_amount(self):
        """Total remaining credit owed to me by this beneficiary."""
        return sum(c.remaining for c in self.active_credits)

    @property
    def net_balance(self):
        """Positive means they owe me, negative means I owe them."""
        return self.total_credit_amount - self.total_debt_amount

    @property
    def has_active_debt(self):
        """True if there is any non-settled debt or credit."""
        return (self.active_debts.exists() or self.active_credits.exists())


class SplitDebt(models.Model):
    """Tracks money lent (credits) or borrowed (debts)."""
    DEBT_TYPE_CHOICES = [
        ('debt', 'I Owe (Debt)'),
        ('credit', 'They Owe Me (Credit)'),
    ]
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('partial', 'Partial'),
        ('settled', 'Settled'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='split_debts', null=True, blank=True)
    beneficiary = models.ForeignKey(Beneficiary, on_delete=models.SET_NULL, related_name='debts', null=True, blank=True)
    person_name = models.CharField(max_length=100)
    phone_number = models.CharField(max_length=20, blank=True, null=True, help_text="Phone number of beneficiary / contact")
    upi_id = models.CharField(max_length=50, blank=True, null=True, help_text="UPI ID / Bank details (Optional)")
    debt_type = models.CharField(max_length=6, choices=DEBT_TYPE_CHOICES)
    original_amount = models.DecimalField(max_digits=10, decimal_places=2)
    amount_paid = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    status = models.CharField(max_length=7, choices=STATUS_CHOICES, default='pending')
    reason = models.TextField(blank=True)
    date_created = models.DateField(auto_now_add=True)
    due_date = models.DateField(null=True, blank=True)
    settled_date = models.DateField(null=True, blank=True)

    class Meta:
        verbose_name_plural = "Split Debts"
        ordering = ['-date_created']

    def save(self, *args, **kwargs):
        if self.beneficiary:
            self.person_name = self.beneficiary.name
            if not self.phone_number and self.beneficiary.phone_number:
                self.phone_number = self.beneficiary.phone_number
            if not self.upi_id and self.beneficiary.upi_id:
                self.upi_id = self.beneficiary.upi_id
        super().save(*args, **kwargs)

    def __str__(self):
        symbol = "←" if self.debt_type == 'debt' else "→"
        return f"{self.person_name} {symbol} ₹{self.remaining}"

    @property
    def remaining(self):
        return self.original_amount - self.amount_paid

    def make_payment(self, amount, payment_mode='bank'):
        """Record a partial or full payment and update account balance."""
        self.amount_paid += amount
        if self.amount_paid >= self.original_amount:
            self.amount_paid = self.original_amount
            self.status = 'settled'
            self.settled_date = date.today()
        else:
            self.status = 'partial'
        self.save()

        pm_clean = payment_mode if payment_mode in ('bank', 'cash') else 'bank'

        # Update Account Balance (Bank or Cash only)
        if self.user:
            balance = AccountBalance.get_instance(self.user)
            if self.debt_type == 'debt':
                # Paying my debt -> Outflow from Bank/Cash
                if pm_clean == 'cash':
                    balance.cash_in_hand -= amount
                else:
                    balance.bank_balance -= amount
            else:
                # Collecting credit -> Inflow to Bank/Cash
                if pm_clean == 'cash':
                    balance.cash_in_hand += amount
                else:
                    balance.bank_balance += amount
            balance.save()

        # Create transaction record
        if self.debt_type == 'debt':
            TransactionHistory.objects.create(
                user=self.user,
                title=f"Debt Payment: {self.person_name}",
                amount=-amount,
                category='debt_payment',
                payment_mode=pm_clean,
                description=f"Payment towards {self.person_name} (debt)"
            )
        else:
            TransactionHistory.objects.create(
                user=self.user,
                title=f"Credit Received: {self.person_name}",
                amount=amount,
                category='credit_received',
                payment_mode=pm_clean,
                description=f"Payment from {self.person_name} (credit)"
            )



class Category(models.Model):
    """Dynamic categories for Expense and Income transactions."""
    TYPE_CHOICES = [
        ('expense', 'Expense'),
        ('income', 'Income'),
        ('both', 'Both'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='categories', null=True, blank=True)
    name = models.CharField(max_length=100)
    type = models.CharField(max_length=10, choices=TYPE_CHOICES, default='expense')
    is_default = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name_plural = "Categories"
        ordering = ['name']

    def __str__(self):
        return f"{self.name} ({self.get_type_display()})"

    @classmethod
    def get_user_categories(cls, user=None, cat_type='expense'):
        """Get categories for a user filtered by type. Only 'Others' is default; all other categories are user-added."""
        others_qs = cls.objects.filter(user__isnull=True, name='Others')
        if not others_qs.exists():
            cls.objects.create(user=None, name='Others', type='both', is_default=True)
        elif others_qs.count() > 1:
            first_pk = others_qs.first().pk
            cls.objects.filter(user__isnull=True, name='Others').exclude(pk=first_pk).delete()

        cls.objects.filter(user__isnull=True).exclude(name='Others').delete()

        if user and user.is_authenticated:
            qs = cls.objects.filter(
                models.Q(user=user) | models.Q(user__isnull=True),
                type__in=[cat_type, 'both']
            ).distinct()
        else:
            qs = cls.objects.filter(user__isnull=True, type__in=[cat_type, 'both'])

        return qs.order_by('name')


class TransactionHistory(models.Model):
    """Tracks all financial transactions."""
    CATEGORY_CHOICES = [
        ('emi', 'EMI Payment'),
        ('debt_payment', 'Debt Payment'),
        ('credit_received', 'Credit Received'),
        ('income', 'Income'),
        ('expense', 'Expense'),
        ('transfer', 'Transfer'),
        ('other', 'Others'),
    ]
    PAYMENT_MODE_CHOICES = [
        ('bank', 'Bank Account'),
        ('cash', 'Cash in Hand'),
        ('credit_card', 'Credit Card'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='transactions', null=True, blank=True)
    title = models.CharField(max_length=200)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    category = models.CharField(max_length=100, default='Others')
    payment_mode = models.CharField(max_length=20, choices=PAYMENT_MODE_CHOICES, default='bank')
    description = models.TextField(blank=True)
    date = models.DateField(default=date.today)
    is_split = models.BooleanField(default=False)
    is_edited = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name_plural = "Transaction History"
        ordering = ['-date', '-created_at']

    @property
    def abs_amount(self):
        return abs(self.amount)

    @property
    def display_category(self):
        if not self.category:
            return 'Others'
        legacy_map = {
            'emi': 'EMI Payment',
            'debt_payment': 'Debt Payment',
            'credit_received': 'Credit Received',
            'income': 'Income',
            'expense': 'Expense',
            'transfer': 'Transfer',
            'other': 'Others'
        }
        return legacy_map.get(self.category, self.category)

    def __str__(self):
        return f"{self.title}: ₹{self.amount} ({self.get_payment_mode_display()})"


class TransactionSplit(models.Model):
    """Tracks split shares per beneficiary for a specific transaction."""
    SPLIT_TYPE_CHOICES = [
        ('credit', 'They Owe Me (Credit)'),
        ('debt', 'I Owe Them (Debt)'),
    ]

    transaction = models.ForeignKey(TransactionHistory, on_delete=models.CASCADE, related_name='splits')
    beneficiary = models.ForeignKey(Beneficiary, on_delete=models.SET_NULL, null=True, blank=True)
    person_name = models.CharField(max_length=100)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    split_type = models.CharField(max_length=10, choices=SPLIT_TYPE_CHOICES, default='credit')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['id']

    def __str__(self):
        return f"{self.person_name}: ₹{self.amount} ({self.get_split_type_display()})"

