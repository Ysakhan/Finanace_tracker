from django import forms
from .models import AccountBalance, MonthlyEMI, SplitDebt, TransactionHistory
from datetime import date


class AccountBalanceForm(forms.ModelForm):
    class Meta:
        model = AccountBalance
        fields = ['bank_balance', 'cash_in_hand', 'credit_card_balance']
        widgets = {
            'bank_balance': forms.NumberInput(attrs={
                'class': 'form-input',
                'placeholder': 'Enter bank balance',
                'step': '0.01'
            }),
            'cash_in_hand': forms.NumberInput(attrs={
                'class': 'form-input',
                'placeholder': 'Enter cash in hand',
                'step': '0.01'
            }),
            'credit_card_balance': forms.NumberInput(attrs={
                'class': 'form-input',
                'placeholder': 'Enter credit card balance',
                'step': '0.01'
            }),
        }


class EMIForm(forms.ModelForm):
    class Meta:
        model = MonthlyEMI
        fields = ['title', 'due_day', 'full_amount', 'personal_share', 'split_with', 'category', 'total_loan_amount', 'total_emis', 'paid_emis', 'notes']
        widgets = {
            'title': forms.TextInput(attrs={
                'class': 'form-input',
                'placeholder': 'e.g., Car Loan EMI'
            }),
            'due_day': forms.NumberInput(attrs={
                'class': 'form-input',
                'min': '1',
                'max': '31',
                'placeholder': 'Day of month (1-31)'
            }),
            'full_amount': forms.NumberInput(attrs={
                'class': 'form-input',
                'placeholder': 'Total EMI amount',
                'step': '0.01'
            }),
            'personal_share': forms.NumberInput(attrs={
                'class': 'form-input',
                'placeholder': 'Your share',
                'step': '0.01'
            }),
            'split_with': forms.TextInput(attrs={
                'class': 'form-input',
                'placeholder': 'Person to pay split (e.g., Rahul)'
            }),
            'category': forms.Select(attrs={
                'class': 'form-input'
            }),
            'total_loan_amount': forms.NumberInput(attrs={
                'class': 'form-input',
                'placeholder': 'Full Loan Amount (Optional)',
                'step': '0.01'
            }),
            'total_emis': forms.NumberInput(attrs={
                'class': 'form-input',
                'placeholder': 'Total Tenure EMIs e.g. 24 (Optional)',
                'min': '1'
            }),
            'paid_emis': forms.NumberInput(attrs={
                'class': 'form-input',
                'placeholder': 'EMIs Paid So Far e.g. 5',
                'min': '0'
            }),
            'notes': forms.Textarea(attrs={
                'class': 'form-input',
                'rows': 3,
                'placeholder': 'Optional notes...'
            }),
        }


class EMIFormWithMonth(forms.ModelForm):
    """EMI form that includes month_year field."""
    class Meta:
        model = MonthlyEMI
        fields = ['title', 'due_day', 'full_amount', 'personal_share', 'split_with', 'category', 'total_loan_amount', 'total_emis', 'paid_emis', 'month_year', 'notes']
        widgets = {
            'title': forms.TextInput(attrs={
                'class': 'form-input',
                'placeholder': 'e.g., Car Loan EMI'
            }),
            'due_day': forms.NumberInput(attrs={
                'class': 'form-input',
                'min': '1',
                'max': '31',
                'placeholder': 'Day of month (1-31)'
            }),
            'full_amount': forms.NumberInput(attrs={
                'class': 'form-input',
                'placeholder': 'Total EMI amount',
                'step': '0.01'
            }),
            'personal_share': forms.NumberInput(attrs={
                'class': 'form-input',
                'placeholder': 'Your share',
                'step': '0.01'
            }),
            'split_with': forms.TextInput(attrs={
                'class': 'form-input',
                'placeholder': 'Person to pay split (e.g., Rahul)'
            }),
            'category': forms.Select(attrs={
                'class': 'form-input'
            }),
            'total_loan_amount': forms.NumberInput(attrs={
                'class': 'form-input',
                'placeholder': 'Full Loan Amount (Optional)',
                'step': '0.01'
            }),
            'total_emis': forms.NumberInput(attrs={
                'class': 'form-input',
                'placeholder': 'Total Tenure EMIs e.g. 24 (Optional)',
                'min': '1'
            }),
            'paid_emis': forms.NumberInput(attrs={
                'class': 'form-input',
                'placeholder': 'EMIs Paid So Far e.g. 5',
                'min': '0'
            }),
            'month_year': forms.TextInput(attrs={
                'class': 'form-input',
                'placeholder': 'YYYY-MM'
            }),
            'notes': forms.Textarea(attrs={
                'class': 'form-input',
                'rows': 3,
                'placeholder': 'Optional notes...'
            }),
        }


from .models import AccountBalance, MonthlyEMI, SplitDebt, TransactionHistory, Beneficiary


class BeneficiaryForm(forms.ModelForm):
    class Meta:
        model = Beneficiary
        fields = ['name', 'phone_number', 'upi_id']
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'form-input',
                'placeholder': 'Beneficiary Full Name',
                'required': True,
            }),
            'phone_number': forms.TextInput(attrs={
                'class': 'form-input',
                'placeholder': 'Phone Number (e.g. +91 9876543210)'
            }),
            'upi_id': forms.TextInput(attrs={
                'class': 'form-input',
                'placeholder': 'UPI ID / Bank details'
            }),
        }


class SplitDebtForm(forms.ModelForm):
    class Meta:
        model = SplitDebt
        fields = ['beneficiary', 'debt_type', 'original_amount', 'reason']
        widgets = {
            'beneficiary': forms.Select(attrs={
                'class': 'form-input searchable-select',
                'id': 'id_beneficiary',
                'required': True,
            }),
            'debt_type': forms.Select(attrs={
                'class': 'form-input'
            }),
            'original_amount': forms.NumberInput(attrs={
                'class': 'form-input',
                'placeholder': 'Amount in ₹',
                'step': '0.01'
            }),
            'reason': forms.Textarea(attrs={
                'class': 'form-input',
                'rows': 3,
                'placeholder': 'Description / Reason for debt or credit'
            }),
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        if user and user.is_authenticated:
            self.fields['beneficiary'].queryset = Beneficiary.objects.filter(user=user)
        self.fields['beneficiary'].required = True
        self.fields['beneficiary'].empty_label = "-- Select Beneficiary (Required) --"


class PartialPaymentForm(forms.Form):
    """Form for making partial payments on debts/credits."""
    PAYMENT_MODE_CHOICES = [
        ('bank', 'Bank Account'),
        ('cash', 'Cash in Hand'),
    ]
    amount = forms.DecimalField(
        max_digits=12,
        decimal_places=2,
        min_value=0.01,
        label='Payment Amount (₹)',
        widget=forms.NumberInput(attrs={
            'class': 'form-input',
            'placeholder': 'Payment amount in ₹',
            'step': '0.01',
            'required': True
        })
    )
    payment_mode = forms.ChoiceField(
        choices=PAYMENT_MODE_CHOICES,
        initial='bank',
        label='Account (Bank or Cash)',
        widget=forms.Select(attrs={'class': 'form-input'})
    )


class TransferForm(forms.Form):
    """Form for transferring money between accounts."""
    FROM_CHOICES = [
        ('cash', 'Cash in Hand'),
        ('bank', 'Bank Account'),
    ]
    TO_CHOICES = [
        ('bank', 'Bank Account'),
        ('cash', 'Cash in Hand'),
        ('credit_card', 'Credit Card'),
    ]

    from_account = forms.ChoiceField(
        choices=FROM_CHOICES,
        initial='bank',
        label='From Account',
        widget=forms.Select(attrs={'class': 'form-input'})
    )
    to_account = forms.ChoiceField(
        choices=TO_CHOICES,
        initial='cash',
        label='To Account',
        widget=forms.Select(attrs={'class': 'form-input'})
    )
    amount = forms.DecimalField(
        max_digits=12,
        decimal_places=2,
        min_value=0.01,
        label='Transfer Amount (₹)',
        widget=forms.NumberInput(attrs={
            'class': 'form-input',
            'placeholder': 'Amount in ₹',
            'step': '0.01',
            'required': True
        })
    )
    date = forms.DateField(
        initial=date.today,
        label='Transfer Date',
        widget=forms.DateInput(attrs={'class': 'form-input', 'type': 'date'})
    )
    description = forms.CharField(
        required=False,
        label='Notes / Reason (Optional)',
        widget=forms.Textarea(attrs={
            'class': 'form-input',
            'rows': 3,
            'placeholder': 'e.g., ATM Cash Withdrawal, Credit Card Payment'
        })
    )

    def clean(self):
        cleaned_data = super().clean()
        from_acc = cleaned_data.get('from_account')
        to_acc = cleaned_data.get('to_account')
        if from_acc and to_acc and from_acc == to_acc:
            raise forms.ValidationError('Source and destination accounts must be different!')
        return cleaned_data



class TransactionForm(forms.ModelForm):
    txn_type = forms.ChoiceField(
        choices=[('expense', 'Expense (Money Out)'), ('income', 'Income (Money In)')],
        initial='expense',
        label='Transaction Type',
        widget=forms.Select(attrs={'class': 'form-input', 'id': 'id_txn_type'})
    )
    custom_category = forms.CharField(
        required=False,
        label='New Category Name',
        widget=forms.TextInput(attrs={
            'class': 'form-input',
            'placeholder': 'Type new category name...',
            'id': 'id_custom_category'
        })
    )

    class Meta:
        model = TransactionHistory
        fields = ['title', 'amount', 'category', 'payment_mode', 'date', 'description']
        widgets = {
            'title': forms.TextInput(attrs={
                'class': 'form-input',
                'placeholder': 'Transaction title / short description',
                'required': True
            }),
            'amount': forms.NumberInput(attrs={
                'class': 'form-input',
                'placeholder': 'Amount in ₹',
                'step': '0.01',
                'min': '0.01',
                'required': True
            }),
            'category': forms.Select(attrs={
                'class': 'form-input',
                'id': 'id_category'
            }),
            'payment_mode': forms.Select(attrs={
                'class': 'form-input'
            }),
            'date': forms.DateInput(attrs={
                'class': 'form-input',
                'type': 'date'
            }),
            'description': forms.Textarea(attrs={
                'class': 'form-input',
                'rows': 3,
                'placeholder': 'Optional notes or reference...'
            }),
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.initial.get('date'):
            self.initial['date'] = date.today().strftime('%Y-%m-%d')

        if not self.initial.get('category') and (not self.instance or not self.instance.pk):
            self.initial['category'] = 'Others'

        from .models import Category
        expense_cats = list(Category.get_user_categories(user, 'expense').values_list('name', flat=True))
        income_cats = list(Category.get_user_categories(user, 'income').values_list('name', flat=True))

        all_cats = list(dict.fromkeys(expense_cats + income_cats))
        if 'Others' not in all_cats:
            all_cats.append('Others')

        choices = [(cat, cat) for cat in all_cats]
        choices.append(('__add_new__', '+ Add New Category...'))

        self.fields['category'].choices = choices

