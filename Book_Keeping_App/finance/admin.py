from django.contrib import admin
from .models import AccountBalance, MonthlyEMI, SplitDebt, TransactionHistory, Beneficiary, TransactionSplit


@admin.register(Beneficiary)
class BeneficiaryAdmin(admin.ModelAdmin):
    list_display = ['name', 'user', 'phone_number', 'upi_id', 'created_at']
    search_fields = ['name', 'phone_number', 'upi_id']
    list_filter = ['user']


@admin.register(AccountBalance)
class AccountBalanceAdmin(admin.ModelAdmin):
    list_display = ['user', 'bank_balance', 'credit_card_balance', 'updated_at']
    list_filter = ['user']
    readonly_fields = ['updated_at']


@admin.register(MonthlyEMI)
class MonthlyEMIAdmin(admin.ModelAdmin):
    list_display = ['user', 'title', 'due_day', 'full_amount', 'personal_share', 'status', 'month_year']
    list_filter = ['user', 'status', 'month_year', 'category']
    search_fields = ['title']
    list_editable = ['status']


@admin.register(SplitDebt)
class SplitDebtAdmin(admin.ModelAdmin):
    list_display = ['user', 'person_name', 'original_amount', 'amount_paid', 'debt_type', 'status']
    list_filter = ['user', 'debt_type', 'status']
    search_fields = ['person_name']


class TransactionSplitInline(admin.TabularInline):
    model = TransactionSplit
    extra = 1


@admin.register(TransactionHistory)
class TransactionHistoryAdmin(admin.ModelAdmin):
    list_display = ['user', 'title', 'amount', 'category', 'payment_mode', 'date', 'is_split', 'created_at']
    list_filter = ['user', 'category', 'payment_mode', 'date', 'is_split']
    search_fields = ['title', 'description']
    readonly_fields = ['created_at']
    inlines = [TransactionSplitInline]


@admin.register(TransactionSplit)
class TransactionSplitAdmin(admin.ModelAdmin):
    list_display = ['transaction', 'person_name', 'amount', 'split_type', 'created_at']
    list_filter = ['split_type']
    search_fields = ['person_name']

