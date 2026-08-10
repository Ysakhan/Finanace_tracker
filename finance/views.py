"""
Finance Tracker Views — Complete CRUD + Auth + AI Assistant + Export
"""
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib.auth import login, logout
from django.contrib.auth.forms import UserCreationForm
from django.contrib import messages
from django.http import HttpResponse, JsonResponse
from django.db.models import Sum, Q
from datetime import date, timedelta
from decimal import Decimal
import json
import io
import csv

from .models import AccountBalance, MonthlyEMI, SplitDebt, TransactionHistory, Beneficiary, TransactionSplit
from .forms import (
    AccountBalanceForm, EMIFormWithMonth, SplitDebtForm,
    PartialPaymentForm, TransactionForm, BeneficiaryForm, TransferForm
)


# AUTH

def register_view(request):
    if request.user.is_authenticated:
        return redirect('finance:dashboard')
    if request.method == 'POST':
        form = UserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            messages.success(request, f'Welcome, {user.username}!')
            return redirect('finance:dashboard')
    else:
        form = UserCreationForm()
    return render(request, 'finance/register.html', {'form': form})


def logout_view(request):
    logout(request)
    messages.info(request, 'You have been logged out.')
    return redirect('finance:login')


def compute_financial_health_insights(user):
    today = date.today()
    current_month = today.strftime('%Y-%m')
    balance = AccountBalance.get_instance(user)

    # 1. Date ranges for week-over-week comparison
    this_week_start = today - timedelta(days=7)
    last_week_start = today - timedelta(days=14)

    txns_this_week = TransactionHistory.objects.filter(user=user, date__gte=this_week_start, date__lte=today).exclude(category__in=['income', 'credit_received'])
    txns_last_week = TransactionHistory.objects.filter(user=user, date__gte=last_week_start, date__lt=this_week_start).exclude(category__in=['income', 'credit_received'])

    this_week_total = sum(abs(t.amount) for t in txns_this_week) or Decimal('0')
    last_week_total = sum(abs(t.amount) for t in txns_last_week) or Decimal('0')

    pct_change = 0.0
    if last_week_total > 0:
        pct_change = float((this_week_total - last_week_total) / last_week_total * 100)

    # Category breakdown comparison for this week
    cats_this_week = txns_this_week.values('category').annotate(cat_total=Sum('amount')).order_by('-cat_total')
    top_cat_name = None
    top_cat_amount = Decimal('0')
    if cats_this_week.exists():
        top_cat_name = cats_this_week[0]['category']
        top_cat_amount = abs(cats_this_week[0]['cat_total'])

    # 2. EMIs & Debts health
    current_emis = MonthlyEMI.objects.filter(user=user, month_year=current_month)
    cur_personal_emi = current_emis.aggregate(t=Sum('personal_share'))['t'] or Decimal('0')
    overdue_count = current_emis.filter(status='overdue').count()

    active_debts = SplitDebt.objects.filter(user=user, debt_type='debt').exclude(status='settled')
    total_debt_rem = sum(d.remaining for d in active_debts)

    active_credits = SplitDebt.objects.filter(user=user, debt_type='credit').exclude(status='settled')
    total_credit_rem = sum(c.remaining for c in active_credits)

    liquidity = balance.bank_balance - cur_personal_emi

    # 3. Calculate Health Score (0-100)
    score = 0

    # Liquidity score (max 30 pts)
    if liquidity > Decimal('10000'):
        score += 30
    elif liquidity > Decimal('0'):
        score += 20
    elif liquidity == Decimal('0'):
        score += 10

    # EMI timeliness (max 30 pts)
    if overdue_count == 0:
        score += 30
    else:
        score += max(0, 30 - (overdue_count * 10))

    # Debt ratio (max 20 pts)
    bank_bal = balance.bank_balance if balance.bank_balance > 0 else Decimal('1')
    debt_ratio = (Decimal(str(total_debt_rem)) / bank_bal) if bank_bal > 0 else Decimal('1')
    if debt_ratio < Decimal('0.25'):
        score += 20
    elif debt_ratio < Decimal('0.50'):
        score += 12
    elif debt_ratio < Decimal('1.0'):
        score += 5

    # Expense trend (max 20 pts)
    if pct_change <= 0:
        score += 20
    elif pct_change <= 15:
        score += 12
    else:
        score += 5

    score = min(100, max(0, score))

    # Rating & Badges
    if score >= 85:
        rating = "Excellent"
        rating_color = "success"
    elif score >= 70:
        rating = "Good"
        rating_color = "success"
    elif score >= 50:
        rating = "Fair"
        rating_color = "warning"
    else:
        rating = "Needs Attention"
        rating_color = "danger"

    # Insights list
    insights = []
    if pct_change < 0:
        insights.append(f"Spending Pace: You spent {abs(pct_change):.1f}% LESS this week compared to last week (₹{this_week_total:,.2f} vs ₹{last_week_total:,.2f}). Excellent control!")
    elif pct_change > 0:
        insights.append(f"Spending Pace: Expenses increased by {pct_change:.1f}% this week (₹{this_week_total:,.2f} vs ₹{last_week_total:,.2f}).")
    else:
        insights.append(f"Spending Pace: Weekly spending is steady at ₹{this_week_total:,.2f}.")

    if top_cat_name:
        cat_pct = float(top_cat_amount / this_week_total * 100) if this_week_total > 0 else 0
        insights.append(f"Top Category: '{top_cat_name.title()}' was your highest expense this week (₹{top_cat_amount:,.2f}, {cat_pct:.0f}% of weekly spend).")

    if liquidity > Decimal('10000'):
        insights.append(f"Liquidity Buffer: Healthy ₹{liquidity:,.2f} buffer remaining after all monthly EMIs.")
    elif liquidity >= Decimal('0'):
        insights.append(f"Liquidity Buffer: Low buffer of ₹{liquidity:,.2f}. Keep non-essential spending minimal.")
    else:
        insights.append(f"Liquidity Alert: Negative liquidity buffer (₹{liquidity:,.2f})! Outstanding EMIs exceed current bank balance.")

    if overdue_count > 0:
        insights.append(f"Overdue Alert: You have {overdue_count} overdue EMI(s). Pay them promptly to avoid penalty fees.")
    else:
        insights.append("EMI Track Record: 100% on-time payment record this month!")

    if total_credit_rem > Decimal('0'):
        insights.append(f"Receivables: You have ₹{total_credit_rem:,.2f} in active credits to collect from beneficiaries.")

    return {
        'score': score,
        'rating': rating,
        'rating_color': rating_color,
        'insights': insights,
        'this_week_total': this_week_total,
        'last_week_total': last_week_total,
        'pct_change': pct_change,
        'top_cat_name': top_cat_name,
        'top_cat_amount': top_cat_amount,
        'liquidity': liquidity,
        'overdue_count': overdue_count,
        'total_debt_rem': total_debt_rem,
        'total_credit_rem': total_credit_rem,
    }


# DASHBOARD

@login_required
def dashboard(request):
    today = date.today()
    current_month = today.strftime('%Y-%m')
    balance = AccountBalance.get_instance(request.user)
    emis = MonthlyEMI.objects.filter(user=request.user, month_year=current_month)
    debts = SplitDebt.objects.filter(user=request.user, debt_type='debt').exclude(status='settled')
    credits = SplitDebt.objects.filter(user=request.user, debt_type='credit').exclude(status='settled')
    recent_transactions = TransactionHistory.objects.filter(user=request.user)[:10]

    total_emi = emis.aggregate(t=Sum('full_amount'))['t'] or Decimal('0')
    total_personal = emis.aggregate(t=Sum('personal_share'))['t'] or Decimal('0')
    total_reimbursable = total_emi - total_personal
    paid_count = emis.filter(status='paid').count()
    unpaid_count = emis.filter(status='unpaid').count() + emis.filter(status='overdue').count()
    total_debt = debts.aggregate(t=Sum('original_amount'))['t'] or Decimal('0')
    total_credit = credits.aggregate(t=Sum('original_amount'))['t'] or Decimal('0')
    liquidity = balance.bank_balance - total_personal

    upcoming = emis.filter(status='unpaid', due_day__gte=today.day, due_day__lte=today.day + 3)
    overdue_reminders = emis.filter(status='overdue')

    health_insights = compute_financial_health_insights(request.user)

    context = {
        'balance': balance,
        'emis': emis,
        'total_emi': total_emi,
        'total_personal': total_personal,
        'total_reimbursable': total_reimbursable,
        'paid_count': paid_count,
        'unpaid_count': unpaid_count,
        'total_debt': total_debt,
        'total_credit': total_credit,
        'liquidity': liquidity,
        'upcoming': upcoming,
        'overdue_reminders': overdue_reminders,
        'recent_transactions': recent_transactions,
        'debts': debts,
        'credits': credits,
        'current_month': current_month,
        'health': health_insights,
    }
    return render(request, 'finance/dashboard.html', context)


# EMI CRUD

@login_required
def emi_list(request):
    month = request.GET.get('month', date.today().strftime('%Y-%m'))
    status_filter = request.GET.get('status', 'all')
    
    all_emis = MonthlyEMI.objects.filter(user=request.user, month_year=month)
    
    paid_count = all_emis.filter(status='paid').count()
    unpaid_count = all_emis.filter(status__in=['unpaid', 'overdue']).count()
    
    total = all_emis.aggregate(t=Sum('full_amount'))['t'] or Decimal('0')
    paid_total = all_emis.filter(status='paid').aggregate(t=Sum('full_amount'))['t'] or Decimal('0')
    unpaid_total = all_emis.filter(status__in=['unpaid', 'overdue']).aggregate(t=Sum('full_amount'))['t'] or Decimal('0')
    
    if status_filter == 'paid':
        emis = all_emis.filter(status='paid')
    elif status_filter == 'unpaid':
        emis = all_emis.filter(status__in=['unpaid', 'overdue'])
    else:
        emis = all_emis

    months = list(MonthlyEMI.objects.filter(user=request.user).values_list('month_year', flat=True).distinct().order_by('-month_year'))
    if month and month not in months:
        months.append(month)
        months.sort(reverse=True)

    balance = AccountBalance.get_instance(request.user)
    return render(request, 'finance/emi_list.html', {
        'emis': emis,
        'total': total,
        'paid_total': paid_total,
        'unpaid_total': unpaid_total,
        'paid_count': paid_count,
        'unpaid_count': unpaid_count,
        'total_count': all_emis.count(),
        'selected_month': month,
        'months': months,
        'status_filter': status_filter,
        'current_month': month,
        'balance': balance,
    })


@login_required
def emi_add(request):
    beneficiaries = Beneficiary.objects.filter(user=request.user)
    if request.method == 'POST':
        form = EMIFormWithMonth(request.POST)
        if form.is_valid():
            emi = form.save(commit=False)
            emi.user = request.user

            # Process multi-split beneficiary entries
            ben_ids = request.POST.getlist('split_beneficiary_id[]')
            split_amts = request.POST.getlist('split_amount[]')
            split_entries = []
            total_split = Decimal('0.00')

            for b_id, amt_str in zip(ben_ids, split_amts):
                if not b_id or not amt_str:
                    continue
                try:
                    amt = Decimal(amt_str)
                except (ValueError, TypeError):
                    continue
                if amt <= 0:
                    continue

                ben_obj = beneficiaries.filter(pk=b_id).first()
                if not ben_obj:
                    continue

                split_entries.append(f"{ben_obj.name}: ₹{amt:.2f}")
                total_split += amt

            if split_entries:
                emi.split_with = ", ".join(split_entries)
                emi.personal_share = max(Decimal('0.00'), emi.full_amount - total_split)

            emi.save()
            messages.success(request, 'EMI added successfully!')
            return redirect('finance:emi_list')
    else:
        form = EMIFormWithMonth(initial={'month_year': date.today().strftime('%Y-%m')})
    return render(request, 'finance/emi_form.html', {'form': form, 'action': 'Add', 'beneficiaries': beneficiaries})


def _create_emi_split_debts(user, emi):
    """Helper to parse split_with entries and create individual credit entries for split beneficiaries."""
    if not emi.split_with or emi.split_amount <= 0:
        return 0

    created = 0
    parts = [p.strip() for p in emi.split_with.split(',') if p.strip()]
    for p in parts:
        p_name = p.strip()
        p_amt = Decimal('0.00')

        if ':' in p and '₹' in p:
            try:
                name_part, amt_part = p.split(':', 1)
                p_name = name_part.strip()
                amt_clean = amt_part.replace('₹', '').strip()
                p_amt = Decimal(amt_clean)
            except Exception:
                p_amt = emi.split_amount / len(parts)
        else:
            p_amt = emi.split_amount / len(parts)

        if p_amt <= 0:
            continue

        ben_obj = Beneficiary.objects.filter(user=user, name__iexact=p_name).first()
        SplitDebt.objects.create(
            user=user,
            beneficiary=ben_obj,
            person_name=ben_obj.name if ben_obj else p_name,
            phone_number=ben_obj.phone_number if ben_obj else None,
            upi_id=ben_obj.upi_id if ben_obj else None,
            debt_type='credit',
            original_amount=p_amt,
            reason=f'EMI split share for {emi.title} ({emi.month_year})'
        )
        created += 1

    return created


@login_required
def emi_mark_paid(request, pk):
    emi = get_object_or_404(MonthlyEMI, pk=pk, user=request.user)
    balance = AccountBalance.get_instance(request.user)
    if emi.status in ('unpaid', 'overdue'):
        paid_by = request.POST.get('paid_by', 'me')
        payment_mode = request.POST.get('payment_mode', 'bank')
        debit_option = request.POST.get('debit_option', 'full')
        payer_name = request.POST.get('payer_name', '').strip() or emi.split_with or 'Split Person'

        emi.status = 'paid'
        emi.paid_date = date.today()
        emi.paid_emis += 1

        if paid_by == 'split_person':
            TransactionHistory.objects.create(
                user=request.user,
                title=f'EMI Paid by {payer_name}: {emi.title}',
                amount=Decimal('0.00'),
                category='emi',
                payment_mode='bank',
                description=f'Full EMI amount ₹{emi.full_amount} paid directly by {payer_name}. Account balance unaffected.'
            )
            messages.success(request, f'{emi.title} marked PAID by {payer_name}! No funds were debited from your account.')
        else:
            pm_clean = payment_mode if payment_mode in ('bank', 'cash', 'credit_card') else 'bank'
            pm_names = {'bank': 'Bank Account', 'cash': 'Cash in Hand', 'credit_card': 'Credit Card'}
            pm_display = pm_names.get(pm_clean, 'Bank Account')

            if debit_option == 'personal' or not (emi.split_with and emi.split_amount > 0):
                debit_amount = emi.personal_share
                is_full_debit = False
            else:
                debit_amount = emi.full_amount
                is_full_debit = True

            if pm_clean == 'cash':
                balance.cash_in_hand -= debit_amount
            elif pm_clean == 'credit_card':
                balance.credit_card_balance += debit_amount
            else:
                balance.bank_balance -= debit_amount
            balance.save()

            TransactionHistory.objects.create(
                user=request.user,
                title=f'EMI Paid: {emi.title}',
                amount=-debit_amount,
                category='emi',
                payment_mode=pm_clean,
                description=f'Paid by Me via {pm_display}. Debited: ₹{debit_amount} (Full: ₹{emi.full_amount}, Personal Share: ₹{emi.personal_share})'
            )

            # Auto-add split share to SplitDebt (Credits: They Owe Me) if full amount was debited and split exists
            if is_full_debit and emi.split_with and emi.split_amount > 0:
                count = _create_emi_split_debts(request.user, emi)
                messages.success(request, f'{emi.title} marked PAID! ₹{debit_amount} debited from {pm_display}. Added ₹{emi.split_amount} to Credits across {count} beneficiary(ies).')
            else:
                messages.success(request, f'{emi.title} marked PAID! ₹{debit_amount} debited from {pm_display}.')
    else:
        emi.status = 'unpaid'
        emi.paid_date = None
        emi.paid_emis = max(0, emi.paid_emis - 1)

        last_txn = TransactionHistory.objects.filter(
            user=request.user,
            category='emi',
            title__icontains=emi.title
        ).order_by('-created_at').first()

        refund_msg = ""
        if last_txn and last_txn.amount == Decimal('0.00'):
            refund_msg = "No balance refund required (was paid by split person)."
        else:
            refund_amount = abs(last_txn.amount) if last_txn else emi.personal_share
            pm_clean = last_txn.payment_mode if last_txn else 'bank'

            if pm_clean == 'cash':
                balance.cash_in_hand += refund_amount
                refund_msg = f"₹{refund_amount} credited back to Cash in Hand."
            elif pm_clean == 'credit_card':
                balance.credit_card_balance -= refund_amount
                refund_msg = f"₹{refund_amount} removed from Credit Card balance."
            else:
                balance.bank_balance += refund_amount
                refund_msg = f"₹{refund_amount} credited back to Bank Account."
            balance.save()

        TransactionHistory.objects.create(
            user=request.user,
            title=f'EMI Reversed: {emi.title}',
            amount=refund_amount if (last_txn and last_txn.amount != Decimal('0.00')) else Decimal('0.00'),
            category='other',
            description='PAID to UNPAID reversal'
        )
        if emi.split_with:
            SplitDebt.objects.filter(
                user=request.user,
                debt_type='credit',
                reason__icontains=emi.title
            ).delete()
        messages.warning(request, f'{emi.title} marked UNPAID! {refund_msg}')
    emi.save()
    return redirect(request.META.get('HTTP_REFERER', 'finance:emi_list'))


@login_required
def emi_edit(request, pk):
    emi = get_object_or_404(MonthlyEMI, pk=pk, user=request.user)
    beneficiaries = Beneficiary.objects.filter(user=request.user)
    if request.method == 'POST':
        form = EMIFormWithMonth(request.POST, instance=emi)
        if form.is_valid():
            emi = form.save(commit=False)

            # Process multi-split beneficiary entries
            ben_ids = request.POST.getlist('split_beneficiary_id[]')
            split_amts = request.POST.getlist('split_amount[]')
            split_entries = []
            total_split = Decimal('0.00')

            for b_id, amt_str in zip(ben_ids, split_amts):
                if not b_id or not amt_str:
                    continue
                try:
                    amt = Decimal(amt_str)
                except (ValueError, TypeError):
                    continue
                if amt <= 0:
                    continue

                ben_obj = beneficiaries.filter(pk=b_id).first()
                if not ben_obj:
                    continue

                split_entries.append(f"{ben_obj.name}: ₹{amt:.2f}")
                total_split += amt

            if split_entries:
                emi.split_with = ", ".join(split_entries)
                emi.personal_share = max(Decimal('0.00'), emi.full_amount - total_split)

            emi.save()
            messages.success(request, f'EMI "{emi.title}" updated!')
            return redirect('finance:emi_list')
    else:
        form = EMIFormWithMonth(instance=emi)
    return render(request, 'finance/emi_form.html', {'form': form, 'action': 'Edit', 'emi': emi, 'beneficiaries': beneficiaries})



@login_required
def emi_delete(request, pk):
    emi = get_object_or_404(MonthlyEMI, pk=pk, user=request.user)
    if request.method == 'POST':
        title = emi.title
        emi.delete()
        messages.success(request, f'EMI "{title}" deleted.')
        return redirect('finance:emi_list')
    return render(request, 'finance/confirm_delete.html', {'object': emi, 'type': 'EMI'})


# DEBTS & CREDITS

@login_required
def debts_credits(request):
    query = request.GET.get('q', '').strip()
    
    active_debts_qs = SplitDebt.objects.filter(user=request.user).exclude(status='settled')
    if query:
        search_filter = Q(person_name__icontains=query) | Q(reason__icontains=query) | Q(phone_number__icontains=query) | Q(upi_id__icontains=query)
        try:
            val = Decimal(query)
            search_filter |= Q(original_amount=val) | Q(amount_paid=val)
        except Exception:
            pass
        active_debts_qs = active_debts_qs.filter(search_filter)

    # Auto-link unlinked active debts to Beneficiary model
    unlinked = active_debts_qs.filter(beneficiary__isnull=True)
    for ud in unlinked:
        if ud.person_name:
            ben, _ = Beneficiary.objects.get_or_create(
                user=request.user,
                name=ud.person_name.strip(),
                defaults={'phone_number': ud.phone_number, 'upi_id': ud.upi_id}
            )
            ud.beneficiary = ben
            ud.save()

    all_beneficiaries = Beneficiary.objects.filter(user=request.user)

    # 1. Debts You Owe (I Owe) Groups
    debt_groups = []
    debts_bens = all_beneficiaries.filter(debts__in=active_debts_qs.filter(debt_type='debt')).distinct()
    for b in debts_bens:
        b_debts = active_debts_qs.filter(beneficiary=b, debt_type='debt')
        t_debt = sum(d.remaining for d in b_debts)
        if t_debt > 0 or query:
            debt_groups.append({
                'beneficiary': b,
                'debts': b_debts,
                'total_debt': t_debt,
            })

    # 2. Credits Owed to You (They Owe Me) Groups
    credit_groups = []
    credits_bens = all_beneficiaries.filter(debts__in=active_debts_qs.filter(debt_type='credit')).distinct()
    for b in credits_bens:
        b_credits = active_debts_qs.filter(beneficiary=b, debt_type='credit')
        t_credit = sum(c.remaining for c in b_credits)
        if t_credit > 0 or query:
            credit_groups.append({
                'beneficiary': b,
                'credits': b_credits,
                'total_credit': t_credit,
            })

    total_debt = sum(d.remaining for d in SplitDebt.objects.filter(user=request.user, debt_type='debt').exclude(status='settled'))
    total_credit = sum(c.remaining for c in SplitDebt.objects.filter(user=request.user, debt_type='credit').exclude(status='settled'))
    
    return render(request, 'finance/debts_credits.html', {
        'debt_groups': debt_groups,
        'credit_groups': credit_groups,
        'total_debt': total_debt,
        'total_credit': total_credit,
        'query': query,
        'has_beneficiaries': all_beneficiaries.exists(),
        'cleared_count': SplitDebt.objects.filter(user=request.user, status='settled').count(),
    })


@login_required
def debt_add(request):
    beneficiaries = Beneficiary.objects.filter(user=request.user)
    if not beneficiaries.exists():
        messages.warning(request, 'Please add at least one Beneficiary first in Beneficiary Details before creating debts or credits!')
        return redirect('finance:beneficiary_add')

    initial_b_id = request.GET.get('beneficiary_id')
    initial_data = {}
    if initial_b_id:
        try:
            b_obj = Beneficiary.objects.get(pk=initial_b_id, user=request.user)
            initial_data['beneficiary'] = b_obj
        except Beneficiary.DoesNotExist:
            pass

    if request.method == 'POST':
        # Check if multi-split rows were submitted
        ben_ids = request.POST.getlist('beneficiary_id[]')
        debt_types = request.POST.getlist('debt_type[]')
        amounts = request.POST.getlist('original_amount[]')
        reasons = request.POST.getlist('reason[]')

        if ben_ids and len(ben_ids) > 0 and any(b_id for b_id in ben_ids):
            created_count = 0
            for b_id, dtype, amt_str, rsn in zip(ben_ids, debt_types, amounts, reasons):
                if not b_id or not amt_str:
                    continue
                try:
                    amt = Decimal(amt_str)
                except (ValueError, TypeError):
                    continue
                if amt <= 0:
                    continue

                ben_obj = beneficiaries.filter(pk=b_id).first()
                if not ben_obj:
                    continue

                d_type_clean = 'debt' if dtype == 'debt' else 'credit'
                SplitDebt.objects.create(
                    user=request.user,
                    beneficiary=ben_obj,
                    person_name=ben_obj.name,
                    phone_number=ben_obj.phone_number,
                    upi_id=ben_obj.upi_id,
                    debt_type=d_type_clean,
                    original_amount=amt,
                    reason=rsn.strip()
                )
                created_count += 1

            if created_count > 0:
                messages.success(request, f'Successfully recorded {created_count} debt/credit entry(ies) for beneficiaries!')
                return redirect('finance:debts_credits')
            else:
                messages.error(request, 'Please select a valid beneficiary and enter an amount for each split row.')

        # Standard form submission
        form = SplitDebtForm(request.POST, user=request.user)
        if form.is_valid():
            d = form.save(commit=False)
            d.user = request.user
            ben = form.cleaned_data['beneficiary']
            d.beneficiary = ben
            d.person_name = ben.name
            d.phone_number = ben.phone_number
            d.upi_id = ben.upi_id
            d.save()
            messages.success(request, f'{d.get_debt_type_display()} added for {d.person_name}: ₹{d.original_amount}')
            return redirect('finance:debts_credits')
    else:
        form = SplitDebtForm(user=request.user, initial=initial_data)

    return render(request, 'finance/debt_form.html', {
        'form': form,
        'action': 'Add',
        'beneficiaries': beneficiaries,
    })



@login_required
def debt_settle(request, pk):
    debt = get_object_or_404(SplitDebt, pk=pk, user=request.user)
    if request.method == 'POST':
        form = PartialPaymentForm(request.POST)
        if form.is_valid():
            amount = form.cleaned_data['amount']
            payment_mode = form.cleaned_data.get('payment_mode', 'bank')
            try:
                debt.make_payment(amount, payment_mode=payment_mode)
                pm_label = "Cash in Hand" if payment_mode == 'cash' else "Bank Account"
                action_label = "collected to" if debt.debt_type == 'credit' else "paid from"
                messages.success(request, f'₹{amount} {action_label} {pm_label} for {debt.person_name}. Remaining: ₹{debt.remaining}')
            except ValueError as e:
                messages.error(request, str(e))
            return redirect('finance:debts_credits')
    else:
        form = PartialPaymentForm()
    return render(request, 'finance/settle_form.html', {'form': form, 'debt': debt})


@login_required
def transfer_funds(request):
    if request.method == 'POST':
        form = TransferForm(request.POST)
        if form.is_valid():
            from_acc = form.cleaned_data['from_account']
            to_acc = form.cleaned_data['to_account']
            amount = form.cleaned_data['amount']
            txn_date = form.cleaned_data['date']
            desc = form.cleaned_data['description']

            balance = AccountBalance.get_instance(request.user)

            # Deduct from source account
            if from_acc == 'cash':
                balance.cash_in_hand -= amount
            else:
                balance.bank_balance -= amount

            # Credit/adjust destination account
            if to_acc == 'bank':
                balance.bank_balance += amount
            elif to_acc == 'cash':
                balance.cash_in_hand += amount
            elif to_acc == 'credit_card':
                # Paying off credit card reduces credit_card_balance
                balance.credit_card_balance -= amount

            balance.save()

            names = {'bank': 'Bank Account', 'cash': 'Cash in Hand', 'credit_card': 'Credit Card'}
            from_name = names.get(from_acc, from_acc)
            to_name = names.get(to_acc, to_acc)

            # Log to TransactionHistory
            TransactionHistory.objects.create(
                user=request.user,
                title=f"Transfer: {from_name} ➔ {to_name}",
                amount=-abs(amount),
                category='transfer',
                payment_mode=from_acc,
                date=txn_date,
                description=desc or f"Transferred ₹{amount} from {from_name} to {to_name}"
            )

            messages.success(request, f"Successfully transferred ₹{amount} from {from_name} to {to_name}!")
            return redirect('finance:dashboard')
    else:
        form = TransferForm()

    return render(request, 'finance/transfer_form.html', {'form': form})



@login_required
def debt_edit(request, pk):
    debt = get_object_or_404(SplitDebt, pk=pk, user=request.user)
    if request.method == 'POST':
        form = SplitDebtForm(request.POST, instance=debt, user=request.user)
        if form.is_valid():
            d = form.save(commit=False)
            ben = form.cleaned_data['beneficiary']
            d.beneficiary = ben
            d.person_name = ben.name
            d.phone_number = ben.phone_number
            d.upi_id = ben.upi_id
            d.save()
            messages.success(request, f'Entry for "{d.person_name}" updated!')
            return redirect('finance:debts_credits')
    else:
        form = SplitDebtForm(instance=debt, user=request.user)

    return render(request, 'finance/debt_form.html', {
        'form': form,
        'action': 'Edit',
    })


@login_required
def debt_delete(request, pk):
    debt = get_object_or_404(SplitDebt, pk=pk, user=request.user)
    if request.method == 'POST':
        person = debt.person_name
        debt.delete()
        messages.success(request, f'Entry for "{person}" deleted.')
        return redirect('finance:debts_credits')
    return render(request, 'finance/confirm_delete.html', {'object': debt, 'type': 'Debt/Credit Entry'})


# BENEFICIARIES

@login_required
def beneficiary_list(request):
    beneficiaries = Beneficiary.objects.filter(user=request.user)
    return render(request, 'finance/beneficiary_list.html', {'beneficiaries': beneficiaries})


@login_required
def beneficiary_add(request):
    if request.method == 'POST':
        form = BeneficiaryForm(request.POST)
        if form.is_valid():
            b = form.save(commit=False)
            b.user = request.user
            b.save()
            messages.success(request, f'Beneficiary "{b.name}" added successfully!')
            return redirect('finance:beneficiary_list')
    else:
        form = BeneficiaryForm()
    return render(request, 'finance/beneficiary_form.html', {'form': form, 'action': 'Add'})


@login_required
def beneficiary_edit(request, pk):
    b = get_object_or_404(Beneficiary, pk=pk, user=request.user)
    if request.method == 'POST':
        form = BeneficiaryForm(request.POST, instance=b)
        if form.is_valid():
            form.save()
            messages.success(request, f'Beneficiary "{b.name}" updated!')
            return redirect('finance:beneficiary_list')
    else:
        form = BeneficiaryForm(instance=b)
    return render(request, 'finance/beneficiary_form.html', {'form': form, 'action': 'Edit'})


@login_required
def beneficiary_delete(request, pk):
    b = get_object_or_404(Beneficiary, pk=pk, user=request.user)
    if request.method == 'POST':
        name = b.name
        b.delete()
        messages.success(request, f'Beneficiary "{name}" deleted.')
        return redirect('finance:beneficiary_list')
    return render(request, 'finance/confirm_delete.html', {'object': b, 'type': 'Beneficiary'})


# BALANCE

@login_required
def balance_update(request):
    balance = AccountBalance.get_instance(request.user)
    if request.method == 'POST':
        form = AccountBalanceForm(request.POST, instance=balance)
        if form.is_valid():
            old_bank = balance.bank_balance
            form.save()
            diff = balance.bank_balance - old_bank
            if diff != 0:
                TransactionHistory.objects.create(
                    user=request.user,
                    title='Balance Manual Update',
                    amount=diff,
                    category='other',
                    description=f'Bank: {old_bank} -> {balance.bank_balance}'
                )
            messages.success(request, 'Balance updated!')
            return redirect('finance:dashboard')
    else:
        form = AccountBalanceForm(instance=balance)
    return render(request, 'finance/balance_form.html', {'form': form, 'balance': balance})


# CATEGORIES

@login_required
def category_list(request):
    from .models import Category
    all_cats = Category.objects.filter(
        Q(user=request.user) | Q(user__isnull=True)
    ).distinct().order_by('name')

    categories_data = []
    for c in all_cats:
        count = TransactionHistory.objects.filter(user=request.user, category=c.name).count()
        categories_data.append({
            'category': c,
            'txn_count': count,
        })

    return render(request, 'finance/category_list.html', {
        'categories_data': categories_data
    })


@login_required
def category_delete(request, pk):
    from .models import Category
    cat = get_object_or_404(Category, pk=pk)
    if cat.user and cat.user != request.user:
        messages.error(request, 'Permission denied.')
        return redirect('finance:category_list')

    txn_count = TransactionHistory.objects.filter(user=request.user, category=cat.name).count()

    if request.method == 'POST':
        reassign_action = request.POST.get('reassign_action', 'transfer')
        target_cat = request.POST.get('target_category', 'Others').strip() or 'Others'

        if txn_count > 0:
            if reassign_action == 'transfer':
                TransactionHistory.objects.filter(user=request.user, category=cat.name).update(category=target_cat)
                messages.success(request, f'Re-assigned {txn_count} transaction(s) from "{cat.name}" to "{target_cat}".')
            else:
                TransactionHistory.objects.filter(user=request.user, category=cat.name).update(category='Others')
                messages.success(request, f'Set {txn_count} transaction(s) from "{cat.name}" to "Others".')

        cat_name = cat.name
        cat.delete()
        messages.success(request, f'Category "{cat_name}" deleted.')
        return redirect('finance:category_list')

    other_cats = Category.objects.filter(
        Q(user=request.user) | Q(user__isnull=True)
    ).exclude(pk=cat.pk).values_list('name', flat=True).distinct()

    return render(request, 'finance/category_confirm_delete.html', {
        'category': cat,
        'txn_count': txn_count,
        'other_cats': list(other_cats),
    })


# TRANSACTIONS

@login_required
def transaction_list(request):
    date_mode = request.GET.get('date_mode', 'monthly')
    month = request.GET.get('month', date.today().strftime('%Y-%m'))
    date_from = request.GET.get('date_from', '')
    date_to = request.GET.get('date_to', '')

    all_txns = TransactionHistory.objects.filter(user=request.user).prefetch_related('splits')

    dates = all_txns.values_list('date', flat=True)
    months = sorted(list(set(d.strftime('%Y-%m') for d in dates if d)), reverse=True)
    if month not in months:
        months.insert(0, month)

    if date_mode == 'custom' and date_from and date_to:
        try:
            d_from = date.fromisoformat(date_from)
            d_to = date.fromisoformat(date_to)
            filtered_txns = [t for t in all_txns if d_from <= t.date <= d_to]
        except ValueError:
            filtered_txns = [t for t in all_txns if t.date.strftime('%Y-%m') == month]
            date_mode = 'monthly'
    elif date_mode == 'all':
        filtered_txns = list(all_txns)
    else:
        date_mode = 'monthly'
        filtered_txns = [t for t in all_txns if t.date.strftime('%Y-%m') == month]

    expense_txns = [t for t in filtered_txns if t.amount < 0]
    total_monthly_expense = sum(abs(t.amount) for t in expense_txns) or Decimal('0.00')

    category_totals = {}
    for t in expense_txns:
        cat = t.display_category
        category_totals[cat] = category_totals.get(cat, Decimal('0.00')) + abs(t.amount)

    sorted_cat_totals = sorted(category_totals.items(), key=lambda x: x[1], reverse=True)

    category_breakdown = []
    top_category = None
    if total_monthly_expense > 0:
        for cat_name, amt in sorted_cat_totals:
            pct = round((amt / total_monthly_expense) * 100, 1)
            category_breakdown.append({
                'name': cat_name,
                'amount': amt,
                'percentage': pct,
            })
        if category_breakdown:
            top_category = category_breakdown[0]

    return render(request, 'finance/transactions.html', {
        'transactions': filtered_txns[:200],
        'total_count': len(filtered_txns),
        'category_breakdown': category_breakdown,
        'top_category': top_category,
        'total_monthly_expense': total_monthly_expense,
        'selected_month': month,
        'months': months,
        'date_mode': date_mode,
        'date_from': date_from,
        'date_to': date_to,
    })


@login_required
def transaction_edit(request, pk):
    txn = get_object_or_404(TransactionHistory, pk=pk, user=request.user)
    beneficiaries = Beneficiary.objects.filter(user=request.user)

    if request.method == 'POST':
        old_signed_amount = txn.amount
        old_payment_mode = txn.payment_mode

        form = TransactionForm(request.POST, instance=txn, user=request.user)
        if form.is_valid():
            txn = form.save(commit=False)

            txn_type = form.cleaned_data.get('txn_type', 'expense')
            raw_amount = abs(txn.amount)
            new_signed_amount = -raw_amount if txn_type == 'expense' else raw_amount
            txn.amount = new_signed_amount

            sel_cat = request.POST.get('category', '').strip()
            custom_cat = request.POST.get('custom_category', '').strip()

            if sel_cat == '__add_new__' or custom_cat:
                from .models import Category
                final_cat = custom_cat.title() if custom_cat else 'Others'
                Category.objects.get_or_create(user=request.user, name=final_cat, type=txn_type)
                txn.category = final_cat
            elif sel_cat:
                txn.category = sel_cat

            is_split = request.POST.get('enable_split') == 'on'
            txn.is_split = is_split
            txn.is_edited = True
            txn.save()

            balance = AccountBalance.get_instance(request.user)
            if old_payment_mode == 'bank':
                balance.bank_balance -= old_signed_amount
            elif old_payment_mode == 'cash':
                balance.cash_in_hand -= old_signed_amount
            elif old_payment_mode == 'credit_card':
                if old_signed_amount < 0:
                    balance.credit_card_balance -= abs(old_signed_amount)
                else:
                    balance.credit_card_balance += abs(old_signed_amount)

            new_pm = txn.payment_mode
            if new_pm == 'bank':
                balance.bank_balance += new_signed_amount
            elif new_pm == 'cash':
                balance.cash_in_hand += new_signed_amount
            elif new_pm == 'credit_card':
                if new_signed_amount < 0:
                    balance.credit_card_balance += abs(new_signed_amount)
                else:
                    balance.credit_card_balance -= abs(new_signed_amount)
            balance.save()

            # Remove old splits and recreate updated splits
            txn.splits.all().delete()

            split_count = 0
            if is_split:
                split_ben_ids = request.POST.getlist('split_beneficiary_id[]')
                split_amounts = request.POST.getlist('split_amount[]')
                split_types = request.POST.getlist('split_type[]')

                for ben_id, amt_str, stype in zip(split_ben_ids, split_amounts, split_types):
                    try:
                        amt = Decimal(amt_str)
                    except (ValueError, TypeError):
                        amt = Decimal('0')

                    if amt <= 0:
                        continue

                    ben_obj = None
                    if ben_id and str(ben_id).isdigit():
                        ben_obj = beneficiaries.filter(pk=int(ben_id)).first()

                    if not ben_obj:
                        continue

                    split_type_clean = 'credit' if stype == 'credit' else 'debt'

                    TransactionSplit.objects.create(
                        transaction=txn,
                        beneficiary=ben_obj,
                        person_name=ben_obj.name,
                        amount=amt,
                        split_type=split_type_clean
                    )
                    split_count += 1

                    SplitDebt.objects.create(
                        user=request.user,
                        beneficiary=ben_obj,
                        person_name=ben_obj.name,
                        phone_number=ben_obj.phone_number,
                        upi_id=ben_obj.upi_id,
                        debt_type=split_type_clean,
                        original_amount=amt,
                        reason=f"Split for transaction '{txn.title}' on {txn.date.strftime('%Y-%m-%d')}"
                    )

            messages.success(request, f'Transaction "{txn.title}" updated successfully!')
            return redirect('finance:transaction_list')
    else:
        initial_type = 'expense' if txn.amount < 0 else 'income'
        form = TransactionForm(instance=txn, user=request.user, initial={'txn_type': initial_type, 'amount': abs(txn.amount)})

    from .models import Category
    import json
    exp_cats = list(Category.get_user_categories(request.user, 'expense').values_list('name', flat=True))
    inc_cats = list(Category.get_user_categories(request.user, 'income').values_list('name', flat=True))
    
    exp_cats = ['Others'] + [c for c in exp_cats if c != 'Others']
    inc_cats = ['Others'] + [c for c in inc_cats if c != 'Others']

    existing_splits = []
    for s in txn.splits.all():
        existing_splits.append({
            'beneficiary_id': s.beneficiary_id or '',
            'person_name': s.person_name,
            'amount': str(s.amount),
            'split_type': s.split_type
        })

    return render(request, 'finance/transaction_form.html', {
        'form': form,
        'txn': txn,
        'action': 'Edit',
        'beneficiaries': beneficiaries,
        'expense_categories_json': json.dumps(exp_cats),
        'income_categories_json': json.dumps(inc_cats),
        'existing_splits_json': json.dumps(existing_splits),
    })


@login_required
def transaction_delete(request, pk):
    txn = get_object_or_404(TransactionHistory, pk=pk, user=request.user)
    if request.method == 'POST':
        title = txn.title
        signed_amount = txn.amount
        pm = txn.payment_mode

        balance = AccountBalance.get_instance(request.user)
        if pm == 'bank':
            balance.bank_balance -= signed_amount
        elif pm == 'cash':
            balance.cash_in_hand -= signed_amount
        elif pm == 'credit_card':
            if signed_amount < 0:
                balance.credit_card_balance -= abs(signed_amount)
            else:
                balance.credit_card_balance += abs(signed_amount)
        balance.save()

        txn.delete()
        messages.success(request, f'Transaction "{title}" deleted successfully.')
        return redirect('finance:transaction_list')
    return render(request, 'finance/confirm_delete.html', {'object': txn, 'type': 'Transaction'})


@login_required
def transaction_add(request):
    beneficiaries = Beneficiary.objects.filter(user=request.user)

    if request.method == 'POST':
        form = TransactionForm(request.POST, user=request.user)
        if form.is_valid():
            txn = form.save(commit=False)
            txn.user = request.user

            txn_type = form.cleaned_data.get('txn_type', 'expense')
            raw_amount = abs(txn.amount)
            if txn_type == 'expense':
                signed_amount = -raw_amount
            else:
                signed_amount = raw_amount
            txn.amount = signed_amount

            # Handle dynamic Category creation & assignment
            from .models import Category
            sel_cat = request.POST.get('category', '').strip()
            custom_cat = request.POST.get('custom_category', '').strip()

            if sel_cat == '__add_new__' or custom_cat:
                final_cat = custom_cat.title() if custom_cat else 'Others'
                Category.objects.get_or_create(
                    user=request.user,
                    name=final_cat,
                    type=txn_type
                )
                txn.category = final_cat
            elif sel_cat:
                txn.category = sel_cat
            else:
                txn.category = 'Others'

            is_split = request.POST.get('enable_split') == 'on'
            txn.is_split = is_split
            txn.save()

            balance = AccountBalance.get_instance(request.user)
            pm = txn.payment_mode
            if pm == 'bank':
                balance.bank_balance += signed_amount
            elif pm == 'cash':
                balance.cash_in_hand += signed_amount
            elif pm == 'credit_card':
                if signed_amount < 0:
                    balance.credit_card_balance += abs(signed_amount)
                else:
                    balance.credit_card_balance -= abs(signed_amount)
            balance.save()

            # Process Beneficiary Splits (Requires valid Beneficiary)
            split_count = 0
            if is_split:
                split_ben_ids = request.POST.getlist('split_beneficiary_id[]')
                split_amounts = request.POST.getlist('split_amount[]')
                split_types = request.POST.getlist('split_type[]')

                for ben_id, amt_str, stype in zip(split_ben_ids, split_amounts, split_types):
                    try:
                        amt = Decimal(amt_str)
                    except (ValueError, TypeError):
                        amt = Decimal('0')

                    if amt <= 0:
                        continue

                    ben_obj = None
                    if ben_id and str(ben_id).isdigit():
                        ben_obj = beneficiaries.filter(pk=int(ben_id)).first()

                    if not ben_obj:
                        continue

                    split_type_clean = 'credit' if stype == 'credit' else 'debt'

                    TransactionSplit.objects.create(
                        transaction=txn,
                        beneficiary=ben_obj,
                        person_name=ben_obj.name,
                        amount=amt,
                        split_type=split_type_clean
                    )
                    split_count += 1

                    SplitDebt.objects.create(
                        user=request.user,
                        beneficiary=ben_obj,
                        person_name=ben_obj.name,
                        phone_number=ben_obj.phone_number,
                        upi_id=ben_obj.upi_id,
                        debt_type=split_type_clean,
                        original_amount=amt,
                        reason=f"Split for transaction '{txn.title}' on {txn.date.strftime('%Y-%m-%d')}"
                    )

            pm_display = txn.get_payment_mode_display()
            type_label = "Expense" if txn_type == "expense" else "Income"
            msg = f"{type_label} transaction of ₹{raw_amount} logged via {pm_display}! Account balance updated."
            if split_count > 0:
                msg += f" Split recorded and debt entries created for {split_count} beneficiary(ies)."
            messages.success(request, msg)
            return redirect('finance:transaction_list')
    else:
        form = TransactionForm(user=request.user)

    from .models import Category
    import json
    exp_cats = list(Category.get_user_categories(request.user, 'expense').values_list('name', flat=True))
    inc_cats = list(Category.get_user_categories(request.user, 'income').values_list('name', flat=True))

    exp_cats = ['Others'] + [c for c in exp_cats if c != 'Others']
    inc_cats = ['Others'] + [c for c in inc_cats if c != 'Others']

    return render(request, 'finance/transaction_form.html', {
        'form': form,
        'beneficiaries': beneficiaries,
        'expense_categories_json': json.dumps(exp_cats),
        'income_categories_json': json.dumps(inc_cats),
        'existing_splits_json': '[]',
    })




# NOTIFICATIONS

@login_required
def dismiss_notification(request):
    if request.method == 'POST':
        messages.success(request, 'Notification dismissed.')
    return redirect('finance:dashboard')


# AI ASSISTANT

@login_required
def assistant(request):
    return render(request, 'finance/assistant.html')


@login_required
def assistant_api(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'POST only'}, status=405)
    try:
        data = json.loads(request.body)
        user_msg = data.get('message', '').strip().lower()
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    if not user_msg:
        return JsonResponse({'response': 'Please type a question!'})

    # Gather live data for THIS user
    balance = AccountBalance.get_instance(request.user)
    today = date.today()
    current_month = today.strftime('%Y-%m')

    # Datasets
    all_emis = MonthlyEMI.objects.filter(user=request.user).order_by('-month_year', 'due_day')
    current_emis = all_emis.filter(month_year=current_month)
    
    all_debts = SplitDebt.objects.filter(user=request.user, debt_type='debt').order_by('-date_created')
    all_credits = SplitDebt.objects.filter(user=request.user, debt_type='credit').order_by('-date_created')
    active_debts = all_debts.exclude(status='settled')
    active_credits = all_credits.exclude(status='settled')

    # Aggregates for current month
    cur_total_emi = current_emis.aggregate(t=Sum('full_amount'))['t'] or Decimal('0')
    cur_total_personal = current_emis.aggregate(t=Sum('personal_share'))['t'] or Decimal('0')

    # Aggregates overall
    all_total_emi = all_emis.aggregate(t=Sum('full_amount'))['t'] or Decimal('0')
    all_total_personal = all_emis.aggregate(t=Sum('personal_share'))['t'] or Decimal('0')
    
    total_debt_rem = sum(d.remaining for d in active_debts)
    total_credit_rem = sum(c.remaining for c in active_credits)
    liquidity = balance.bank_balance - cur_total_personal

    is_this_month = any(phrase in user_msg for phrase in ['this month', 'current month', 'present month', 'this-month'])
    is_all_explicit = any(phrase in user_msg for phrase in ['all', 'every', 'full', 'history', 'entire', 'overall', 'complete', 'across'])

    has_emi_keyword = any(w in user_msg for w in ['emi', 'emis', 'loan', 'loans', 'installment', 'installments', 'monthly', 'burden'])
    has_debt_keyword = any(w in user_msg for w in ['debt', 'debts', 'owe', 'owes', 'borrow', 'borrowed'])
    has_credit_keyword = any(w in user_msg for w in ['credit', 'credits', 'collect', 'lend', 'lent'])
    has_balance_keyword = any(w in user_msg for w in ['balance', 'bank', 'cash', 'money', 'how much'])
    has_summary_keyword = any(w in user_msg for w in ['summary', 'overview', 'report', 'all details', 'details', 'everything', 'status'])
    has_afford_keyword = any(w in user_msg for w in ['afford', 'buy', 'purchase', 'spend'])
    has_priority_keyword = any(w in user_msg for w in ['pay first', 'priority', 'suggest', 'advice', 'recommend'])
    has_health_keyword = any(w in user_msg for w in ['health', 'insight', 'insights', 'analysis', 'how am i doing', 'score', 'pace', 'health check'])

    resp = ""

    # 0. Financial Health Check & Insights
    if has_health_keyword:
        h = compute_financial_health_insights(request.user)
        resp = f"FINANCIAL HEALTH CHECK & INSIGHTS\n{'='*45}\n\n"
        resp += f"Health Score: {h['score']}/100 ({h['rating']})\n"
        resp += f"Liquidity Buffer: Rs.{h['liquidity']:,.2f}\n"
        resp += f"This Week Spending: Rs.{h['this_week_total']:,.2f}\n\n"
        resp += "SMART INSIGHTS:\n"
        for item in h['insights']:
            resp += f"• {item}\n"

    # 1. Combined request (e.g., "all details of emi and loans and debts credits" or summary)
    elif (has_emi_keyword and (has_debt_keyword or has_credit_keyword)) or (has_summary_keyword and not is_this_month):
        if is_this_month and not is_all_explicit:
            resp = f"FINANCIAL SUMMARY — {current_month} (This Month Only)\n{'='*45}\n\n"
            resp += f"BANK BALANCE: Rs.{balance.bank_balance}\nEFFECTIVE LIQUIDITY: Rs.{liquidity}\n\n"
            resp += f"EMIs ({current_month}):\n"
            resp += f"  Total: Rs.{cur_total_emi} | Personal Share: Rs.{cur_total_personal}\n"
            resp += f"  Paid: {current_emis.filter(status='paid').count()} | Unpaid: {current_emis.filter(status='unpaid').count()}\n"
            for e in current_emis:
                tag = '[PAID]' if e.status == 'paid' else ('[OVERDUE]' if e.is_overdue else '[UNPAID]')
                resp += f"  • {e.title}: Rs.{e.full_amount} (Your Share: Rs.{e.personal_share}) {tag}\n"
            resp += f"\nACTIVE DEBTS (I Owe): Rs.{total_debt_rem}\n"
            for d in active_debts:
                resp += f"  • {d.person_name}: Remaining Rs.{d.remaining} / Original Rs.{d.original_amount}\n"
            resp += f"\nACTIVE CREDITS (They Owe Me): Rs.{total_credit_rem}\n"
            for c in active_credits:
                resp += f"  • {c.person_name}: Remaining Rs.{c.remaining} / Original Rs.{c.original_amount}\n"
            net = total_credit_rem - total_debt_rem
            resp += f"\nNET POSITION: {'+' if net >= 0 else ''}Rs.{net}"
        else:
            resp = f"ALL FINANCIAL DETAILS (All Months & All Records)\n{'='*45}\n\n"
            resp += f"BANK BALANCE: Rs.{balance.bank_balance}\nCASH IN HAND: Rs.{balance.cash_in_hand}\nCREDIT CARD: Rs.{balance.credit_card_balance}\nEFFECTIVE LIQUIDITY: Rs.{liquidity}\n\n"
            
            resp += "--- ALL MONTHLY EMIs & LOANS ---\n"
            if all_emis.exists():
                months_dict = {}
                for e in all_emis:
                    months_dict.setdefault(e.month_year, []).append(e)
                for m_y, e_list in months_dict.items():
                    resp += f"\nMonth [{m_y}]:\n"
                    for e in e_list:
                        status_str = f"[{e.status.upper()}]"
                        loan_info = ""
                        if e.total_loan_amount is not None:
                            loan_info = f" (Loan: Paid {e.paid_emis}/{e.total_emis or '?'} EMIs, Rem Bal: Rs.{e.remaining_balance})"
                        resp += f"  • {e.title} (Day {e.due_day}): Full Rs.{e.full_amount} | Personal Rs.{e.personal_share} {status_str}{loan_info}\n"
                resp += f"\nTotal Recorded EMIs: {all_emis.count()} entries across {len(months_dict)} month(s)\n"
                resp += f"Total EMI Amount: Rs.{all_total_emi} | Total Personal Share: Rs.{all_total_personal}\n"
            else:
                resp += "No EMI or Loan entries recorded.\n"
                
            resp += "\n--- ALL DEBTS (Money You Owe) ---\n"
            if all_debts.exists():
                for d in all_debts:
                    resp += f"  • {d.person_name}: Original Rs.{d.original_amount} | Paid Rs.{d.amount_paid} | Remaining Rs.{d.remaining} [{d.status.upper()}]\n"
                    if d.reason:
                        resp += f"    Reason: {d.reason}\n"
                resp += f"Total Active Debt Remaining: Rs.{total_debt_rem}\n"
            else:
                resp += "No Debt records found.\n"
                
            resp += "\n--- ALL CREDITS (Money Owed to You) ---\n"
            if all_credits.exists():
                for c in all_credits:
                    resp += f"  • {c.person_name}: Original Rs.{c.original_amount} | Paid Rs.{c.amount_paid} | Remaining Rs.{c.remaining} [{c.status.upper()}]\n"
                    if c.reason:
                        resp += f"    Reason: {c.reason}\n"
                resp += f"Total Active Credit Remaining: Rs.{total_credit_rem}\n"
            else:
                resp += "No Credit records found.\n"
                
            net = total_credit_rem - total_debt_rem
            resp += f"\nOVERALL NET DEBT/CREDIT POSITION: {'+' if net >= 0 else ''}Rs.{net}"

    # 2. Balance specific
    elif has_balance_keyword and not has_emi_keyword and not has_debt_keyword:
        resp = f"Bank Balance: Rs.{balance.bank_balance}\n"
        resp += f"Cash in Hand: Rs.{balance.cash_in_hand}\n"
        resp += f"Credit Card Balance: Rs.{balance.credit_card_balance}\n"
        resp += f"Current Month EMI Share: Rs.{cur_total_personal}\n"
        resp += f"Effective Liquidity: Rs.{liquidity}\n\n"
        if liquidity < 0:
            resp += "WARNING: Negative liquidity! Limit spending."
        elif liquidity < 5000:
            resp += "CAUTION: Low cash buffer."
        else:
            resp += "Healthy liquidity buffer."

    # 3. EMI / Loans specific
    elif has_emi_keyword:
        if is_this_month and not is_all_explicit:
            resp = f"EMIs for Current Month ({current_month}):\n\n"
            resp += f"Total Amount: Rs.{cur_total_emi}\nYour Personal Share: Rs.{cur_total_personal}\n"
            resp += f"Reimbursable Split: Rs.{cur_total_emi - cur_total_personal}\n"
            resp += f"Paid: {current_emis.filter(status='paid').count()} | Unpaid: {current_emis.filter(status='unpaid').count()}\n\n"
            for e in current_emis.order_by('due_day'):
                tag = '[PAID]' if e.status == 'paid' else ('[OVERDUE]' if e.is_overdue else '[UNPAID]')
                loan_txt = f" (Rem Loan Bal: Rs.{e.remaining_balance})" if e.total_loan_amount else ""
                resp += f"  • Day {e.due_day}: {e.title} — Rs.{e.full_amount} (Personal: Rs.{e.personal_share}) {tag}{loan_txt}\n"
        else:
            resp = f"ALL EMI & LOAN DETAILS (Across All Months):\n\n"
            if all_emis.exists():
                months_dict = {}
                for e in all_emis:
                    months_dict.setdefault(e.month_year, []).append(e)
                for m_y, e_list in months_dict.items():
                    resp += f"Month [{m_y}]:\n"
                    for e in e_list:
                        status_str = f"[{e.status.upper()}]"
                        loan_info = f" | Loan Rem: Rs.{e.remaining_balance}" if e.total_loan_amount else ""
                        resp += f"  • Day {e.due_day}: {e.title} — Full Rs.{e.full_amount} (Personal Rs.{e.personal_share}) {status_str}{loan_info}\n"
                    resp += "\n"
                resp += f"Total EMI Count: {all_emis.count()} across {len(months_dict)} month(s)\n"
                resp += f"Total Amount Sum: Rs.{all_total_emi} | Personal Share Sum: Rs.{all_total_personal}\n"
                resp += "\n(Tip: Ask 'this month emi' to view only current month's EMIs)"
            else:
                resp += "No EMI entries found."

    # 4. Debts / Credits specific
    elif has_debt_keyword or has_credit_keyword:
        if is_this_month and not is_all_explicit:
            resp = f"DEBTS & CREDITS (Current Active Status):\n\n"
            resp += f"Debts You Owe (Active): Rs.{total_debt_rem}\n"
            for d in active_debts:
                resp += f"  • {d.person_name}: Rs.{d.remaining} remaining (Original Rs.{d.original_amount})\n"
            resp += f"\nCredits Owed To You (Active): Rs.{total_credit_rem}\n"
            for c in active_credits:
                resp += f"  • {c.person_name}: Rs.{c.remaining} remaining (Original Rs.{c.original_amount})\n"
        else:
            resp = f"ALL DEBTS & CREDITS DETAILS (All Records):\n\n"
            resp += "DEBTS (Money You Owe):\n"
            if all_debts.exists():
                for d in all_debts:
                    resp += f"  • {d.person_name}: Original Rs.{d.original_amount} | Paid Rs.{d.amount_paid} | Remaining Rs.{d.remaining} [{d.status.upper()}]\n"
                    if d.reason:
                        resp += f"    Reason: {d.reason}\n"
                resp += f"Total Active Remaining Debt: Rs.{total_debt_rem}\n\n"
            else:
                resp += "  No debt records.\n\n"
                
            resp += "CREDITS (Money Owed to You):\n"
            if all_credits.exists():
                for c in all_credits:
                    resp += f"  • {c.person_name}: Original Rs.{c.original_amount} | Paid Rs.{c.amount_paid} | Remaining Rs.{c.remaining} [{c.status.upper()}]\n"
                    if c.reason:
                        resp += f"    Reason: {c.reason}\n"
                resp += f"Total Active Remaining Credit: Rs.{total_credit_rem}\n"
            else:
                resp += "  No credit records.\n"
            resp += "\n(Tip: Ask 'this month debts' to view only active pending debts)"

    # 5. Affordability
    elif has_afford_keyword:
        resp = f"Balance: Rs.{balance.bank_balance}\nLiquidity: Rs.{liquidity}\n"
        resp += f"Active Debts: Rs.{total_debt_rem}\n\n"
        if liquidity > 10000:
            resp += "Comfortable buffer. Moderate purchases OK."
        elif liquidity > 0:
            resp += "Limited buffer. Essentials only."
        else:
            resp += "WARNING: Negative liquidity! Avoid unnecessary spending."

    # 6. Payment priority recommendations
    elif has_priority_keyword:
        resp = "Recommendations:\n\n"
        overdue_emis = current_emis.filter(status='overdue')
        if overdue_emis.exists():
            resp += "1. URGENT - Overdue EMIs:\n"
            for e in overdue_emis:
                resp += f"   {e.title}: Rs.{e.personal_share}\n"
        if active_debts.exists():
            smallest = active_debts.order_by('original_amount').first()
            resp += f"\n2. Quick win: Pay {smallest.person_name} Rs.{smallest.remaining}\n"
        unpaid = current_emis.filter(status='unpaid').order_by('due_day')
        if unpaid.exists():
            resp += "\n3. Upcoming EMIs this month:\n"
            for e in unpaid[:3]:
                resp += f"   Day {e.due_day}: {e.title} Rs.{e.personal_share}\n"
        resp += f"\n4. After current EMIs, liquidity buffer: Rs.{liquidity}"

    elif any(w in user_msg for w in ['hello', 'hi', 'hey', 'help']):
        resp = "Hello! I'm your Finance Companion.\n\n"
        resp += "Ask me:\n- 'All details of EMI and loans'\n"
        resp += "- 'This month EMI'\n- 'All debts and credits'\n"
        resp += "- 'What's my balance?'\n- 'Full financial summary'"

    else:
        resp = "Try asking:\n- 'All details of EMI and loans'\n"
        resp += "- 'This month EMI'\n- 'All debts and credits'\n"
        resp += "- 'What's my balance?'\n- 'Full financial summary'"

    return JsonResponse({'response': resp})


# EXPORT

@login_required
def export_page(request):
    return render(request, 'finance/export.html')


@login_required
def export_text(request):
    today = date.today()
    cm = today.strftime('%Y-%m')
    balance = AccountBalance.get_instance(request.user)
    
    # Fetch ALL data across all months and records
    all_emis = MonthlyEMI.objects.filter(user=request.user).order_by('-month_year', 'due_day')
    all_debts = SplitDebt.objects.filter(user=request.user, debt_type='debt').order_by('-date_created')
    all_credits = SplitDebt.objects.filter(user=request.user, debt_type='credit').order_by('-date_created')
    all_txns = TransactionHistory.objects.filter(user=request.user).order_by('-date', '-created_at')

    cur_emis = all_emis.filter(month_year=cm)
    cur_personal = cur_emis.aggregate(t=Sum('personal_share'))['t'] or Decimal('0')
    liquidity = balance.bank_balance - cur_personal

    total_emi_full = all_emis.aggregate(t=Sum('full_amount'))['t'] or Decimal('0')
    total_emi_personal = all_emis.aggregate(t=Sum('personal_share'))['t'] or Decimal('0')
    total_debt_orig = all_debts.aggregate(t=Sum('original_amount'))['t'] or Decimal('0')
    total_debt_paid = all_debts.aggregate(t=Sum('amount_paid'))['t'] or Decimal('0')
    total_debt_rem = sum(d.remaining for d in all_debts.exclude(status='settled'))

    total_credit_orig = all_credits.aggregate(t=Sum('original_amount'))['t'] or Decimal('0')
    total_credit_paid = all_credits.aggregate(t=Sum('amount_paid'))['t'] or Decimal('0')
    total_credit_rem = sum(c.remaining for c in all_credits.exclude(status='settled'))

    lines = [
        "=" * 115,
        "     COMPLETE PERSONAL FINANCIAL STATUS REPORT (FULL EMI & LOAN DETAILS + TENURE TRACKING)",
        f"     Generated: {today.strftime('%d %B %Y')} | User: {request.user.username}",
        "=" * 115, "",
        "ACCOUNT BALANCE", "-" * 115,
        f"  Bank Balance:            Rs.{balance.bank_balance}",
        f"  Cash in Hand:            Rs.{balance.cash_in_hand}",
        f"  Credit Card Balance:     Rs.{balance.credit_card_balance}",
        f"  Current Month EMI Share: Rs.{cur_personal}",
        f"  Effective Liquidity:     Rs.{liquidity}", "",
        "ALL MONTHLY EMIs & LOANS (ALL MONTHS - INCLUDING TENURE & REMAINING TENURE)", "-" * 115,
        f"  {'Month':<8} {'Title':<20} {'Category':<10} {'Due':<6} {'Full EMI':>10} {'Personal':>10} {'Total Loan':>12} {'Tenure':>7} {'Paid':>5} {'Rem Ten':>8} {'Rem Loan Bal':>14} {'Status':<8}",
        f"  {'-'*8} {'-'*20} {'-'*10} {'-'*6} {'-'*10} {'-'*10} {'-'*12} {'-'*7} {'-'*5} {'-'*8} {'-'*14} {'-'*8}",
    ]

    for emi in all_emis:
        t_loan = f"Rs.{emi.total_loan_amount}" if emi.total_loan_amount is not None else "-"
        tenure = f"{emi.total_emis}m" if emi.total_emis is not None else "-"
        paid = f"{emi.paid_emis}"
        rem_ten = f"{emi.remaining_emis}m" if emi.remaining_emis is not None else "-"
        rem_bal = f"Rs.{emi.remaining_balance}" if emi.remaining_balance is not None else "-"
        cat = emi.get_category_display()[:10]
        due = f"Day {emi.due_day}"
        lines.append(f"  {emi.month_year:<8} {emi.title[:20]:<20} {cat:<10} {due:<6} {str(emi.full_amount):>10} {str(emi.personal_share):>10} {t_loan:>12} {tenure:>7} {paid:>5} {rem_ten:>8} {rem_bal:>14} {emi.status.upper():<8}")
        
        extras = []
        if emi.split_with:
            extras.append(f"Split with {emi.split_with} (Shared: Rs.{emi.split_amount})")
        if emi.paid_date:
            extras.append(f"Paid on {emi.paid_date.strftime('%d %b %Y')}")
        if emi.progress_percentage > 0:
            extras.append(f"Payoff Progress: {emi.progress_percentage}%")
        if emi.notes:
            extras.append(f"Notes: {emi.notes}")
        if extras:
            lines.append(f"           --> {' | '.join(extras)}")

    if not all_emis.exists():
        lines.append("  No EMI records found.")
    else:
        lines.append(f"  {'TOTAL':<8} {'All Entries':<20} {'-':<10} {'-':<6} {str(total_emi_full):>10} {str(total_emi_personal):>10}")

    lines += ["", "DEBTS (Money You Owe - All Records)", "-" * 115,
        f"  {'Person':<25} {'Original':>12} {'Paid':>12} {'Remaining':>12} {'Status':<10}",
        f"  {'-'*25} {'-'*12} {'-'*12} {'-'*12} {'-'*10}"]
    for d in all_debts:
        lines.append(f"  {d.person_name[:25]:<25} {str(d.original_amount):>12} {str(d.amount_paid):>12} {str(d.remaining):>12} [{d.status}]")
    if not all_debts.exists():
        lines.append("  No debt records found.")
    else:
        lines.append(f"  {'TOTAL OUTSTANDING DEBT':<51} Rs.{total_debt_rem:>12}")

    lines += ["", "CREDITS (Money Owed To You - All Records)", "-" * 115,
        f"  {'Person':<25} {'Original':>12} {'Paid':>12} {'Remaining':>12} {'Status':<10}",
        f"  {'-'*25} {'-'*12} {'-'*12} {'-'*12} {'-'*10}"]
    for c in all_credits:
        lines.append(f"  {c.person_name[:25]:<25} {str(c.original_amount):>12} {str(c.amount_paid):>12} {str(c.remaining):>12} [{c.status}]")
    if not all_credits.exists():
        lines.append("  No credit records found.")
    else:
        lines.append(f"  {'TOTAL OUTSTANDING CREDIT':<51} Rs.{total_credit_rem:>12}")

    lines += ["", "TRANSACTION HISTORY (ALL RECORDS)", "-" * 115]
    for txn in all_txns:
        lines.append(f"  {txn.date.strftime('%Y-%m-%d')} | {txn.title[:35]:<35} | {txn.category:<15} | Rs.{txn.amount}")
    if not all_txns.exists():
        lines.append("  No transaction history.")

    net = total_credit_rem - total_debt_rem
    lines += ["", "=" * 115,
        f"  OVERALL NET OUTSTANDING POSITION (Credits - Debts): {'+' if net >= 0 else ''}Rs.{net}",
        "=" * 115]

    response = HttpResponse("\n".join(lines), content_type='text/plain')
    response['Content-Disposition'] = f'attachment; filename="finance_full_report_{today.strftime("%Y%m%d")}.txt"'
    return response


@login_required
def export_csv(request):
    """Exports full financial data including tenure, remaining tenure, and loan breakdown as CSV."""
    today = date.today()
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="finance_full_report_{today.strftime("%Y%m%d")}.csv"'
    writer = csv.writer(response)

    balance = AccountBalance.get_instance(request.user)
    all_emis = MonthlyEMI.objects.filter(user=request.user).order_by('-month_year', 'due_day')
    all_debts = SplitDebt.objects.filter(user=request.user, debt_type='debt').order_by('-date_created')
    all_credits = SplitDebt.objects.filter(user=request.user, debt_type='credit').order_by('-date_created')
    all_txns = TransactionHistory.objects.filter(user=request.user).order_by('-date', '-created_at')

    # 1. ACCOUNT BALANCES
    writer.writerow(["=== ACCOUNT BALANCES ==="])
    writer.writerow(["Bank Balance", float(balance.bank_balance)])
    writer.writerow(["Cash In Hand", float(balance.cash_in_hand)])
    writer.writerow(["Credit Card Balance", float(balance.credit_card_balance)])
    writer.writerow([])

    # 2. ALL MONTHLY EMIS & LOANS
    writer.writerow(["=== ALL MONTHLY EMIs & LOANS (ALL MONTHS) ==="])
    writer.writerow([
        "Month", "Title", "Category", "Due Day", "Full Amount (Rs)", "Personal Share (Rs)",
        "Split Amount (Rs)", "Split With", "Total Loan Amount (Rs)", "Total Tenure (EMIs)",
        "Paid EMIs", "Remaining Tenure (EMIs)", "Total Paid Amount (Rs)", "Remaining Loan Balance (Rs)",
        "Progress (%)", "Status", "Paid Date", "Notes"
    ])

    for emi in all_emis:
        writer.writerow([
            emi.month_year,
            emi.title,
            emi.get_category_display(),
            emi.due_day,
            float(emi.full_amount),
            float(emi.personal_share),
            float(emi.split_amount),
            emi.split_with or "",
            float(emi.total_loan_amount) if emi.total_loan_amount is not None else "",
            emi.total_emis if emi.total_emis is not None else "",
            emi.paid_emis,
            emi.remaining_emis if emi.remaining_emis is not None else "",
            float(emi.total_paid_amount),
            float(emi.remaining_balance) if emi.remaining_balance is not None else "",
            f"{emi.progress_percentage}%",
            emi.status.upper(),
            emi.paid_date.strftime('%Y-%m-%d') if emi.paid_date else "",
            emi.notes or ""
        ])
    writer.writerow([])

    # 3. DEBTS
    writer.writerow(["=== DEBTS (MONEY YOU OWE) ==="])
    writer.writerow(["Person Name", "Original Amount (Rs)", "Amount Paid (Rs)", "Remaining Balance (Rs)", "Status", "Reason"])
    for d in all_debts:
        writer.writerow([d.person_name, float(d.original_amount), float(d.amount_paid), float(d.remaining), d.status.upper(), d.reason or ""])
    writer.writerow([])

    # 4. CREDITS
    writer.writerow(["=== CREDITS (MONEY OWED TO YOU) ==="])
    writer.writerow(["Person Name", "Original Amount (Rs)", "Amount Paid (Rs)", "Remaining Balance (Rs)", "Status", "Reason"])
    for c in all_credits:
        writer.writerow([c.person_name, float(c.original_amount), float(c.amount_paid), float(c.remaining), c.status.upper(), c.reason or ""])
    writer.writerow([])

    # 5. TRANSACTIONS
    writer.writerow(["=== TRANSACTION HISTORY ==="])
    writer.writerow(["Date", "Title", "Category", "Payment Mode", "Amount (Rs)", "Description"])
    for txn in all_txns:
        writer.writerow([txn.date.strftime('%Y-%m-%d'), txn.title, txn.display_category, txn.get_payment_mode_display(), float(txn.amount), txn.description or ""])


    return response


@login_required
def export_pdf(request):
    try:
        from reportlab.lib.pagesizes import A4, landscape
        from reportlab.lib import colors
        from reportlab.lib.units import inch
        from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    except ImportError:
        messages.error(request, 'PDF generation requires reportlab package.')
        return redirect('finance:export_page')

    today = date.today()
    cm = today.strftime('%Y-%m')
    balance = AccountBalance.get_instance(request.user)

    all_emis = MonthlyEMI.objects.filter(user=request.user).order_by('-month_year', 'due_day')
    all_debts = SplitDebt.objects.filter(user=request.user, debt_type='debt').order_by('-date_created')
    all_credits = SplitDebt.objects.filter(user=request.user, debt_type='credit').order_by('-date_created')
    all_txns = TransactionHistory.objects.filter(user=request.user).order_by('-date', '-created_at')

    cur_personal = all_emis.filter(month_year=cm).aggregate(t=Sum('personal_share'))['t'] or Decimal('0')
    total_emi_full = all_emis.aggregate(t=Sum('full_amount'))['t'] or Decimal('0')
    total_emi_personal = all_emis.aggregate(t=Sum('personal_share'))['t'] or Decimal('0')

    total_debt_rem = sum(d.remaining for d in all_debts.exclude(status='settled'))
    total_credit_rem = sum(c.remaining for c in all_credits.exclude(status='settled'))

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=landscape(A4), topMargin=0.4 * inch, bottomMargin=0.4 * inch, leftMargin=0.4 * inch, rightMargin=0.4 * inch)
    styles = getSampleStyleSheet()
    els = []

    title_s = ParagraphStyle('T', parent=styles['Title'], fontSize=16, spaceAfter=10)
    cell_s = ParagraphStyle('Cell', parent=styles['Normal'], fontSize=7.5, leading=9)
    cell_hdr_s = ParagraphStyle('CellHdr', parent=styles['Normal'], fontSize=8, leading=9, textColor=colors.white)

    els.append(Paragraph("Complete Financial Status Report (Full Details + Tenure Tracking)", title_s))
    els.append(Paragraph(f"Date: {today.strftime('%d %B %Y')} | User: {request.user.username}", styles['Normal']))
    els.append(Spacer(1, 10))

    # Balance Table
    els.append(Paragraph("Account Balance", styles['Heading2']))
    bd = [
        ['Bank Balance', f'Rs.{balance.bank_balance}'],
        ['Cash In Hand', f'Rs.{balance.cash_in_hand}'],
        ['Credit Card Balance', f'Rs.{balance.credit_card_balance}'],
        ['Effective Liquidity', f'Rs.{balance.bank_balance - cur_personal}']
    ]
    t_bal = Table(bd, colWidths=[3 * inch, 3.2 * inch])
    t_bal.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#1e1e2e')),
        ('TEXTCOLOR', (0, 0), (-1, -1), colors.white),
        ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#444')),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        ('TOPPADDING', (0, 0), (-1, -1), 5),
    ]))
    els += [t_bal, Spacer(1, 12)]

    # EMIs Table
    els.append(Paragraph("Monthly EMIs & Loans (All Months - Including Tenure & Remaining Tenure)", styles['Heading2']))
    ed = [[
        Paragraph('<b>Month</b>', cell_hdr_s),
        Paragraph('<b>Title</b>', cell_hdr_s),
        Paragraph('<b>Category</b>', cell_hdr_s),
        Paragraph('<b>Due</b>', cell_hdr_s),
        Paragraph('<b>Full EMI</b>', cell_hdr_s),
        Paragraph('<b>Personal</b>', cell_hdr_s),
        Paragraph('<b>Total Loan</b>', cell_hdr_s),
        Paragraph('<b>Tenure</b>', cell_hdr_s),
        Paragraph('<b>Paid</b>', cell_hdr_s),
        Paragraph('<b>Rem Ten</b>', cell_hdr_s),
        Paragraph('<b>Rem Loan Bal</b>', cell_hdr_s),
        Paragraph('<b>Status</b>', cell_hdr_s),
    ]]
    for e in all_emis:
        t_loan = f'Rs.{e.total_loan_amount}' if e.total_loan_amount is not None else '-'
        tenure = f'{e.total_emis} m' if e.total_emis is not None else '-'
        paid = f'{e.paid_emis}'
        rem_ten = f'{e.remaining_emis} m' if e.remaining_emis is not None else '-'
        rem_bal = f'Rs.{e.remaining_balance}' if e.remaining_balance is not None else '-'
        
        ed.append([
            Paragraph(e.month_year, cell_s),
            Paragraph(e.title, cell_s),
            Paragraph(e.get_category_display(), cell_s),
            Paragraph(f"Day {e.due_day}", cell_s),
            Paragraph(f'Rs.{e.full_amount}', cell_s),
            Paragraph(f'Rs.{e.personal_share}', cell_s),
            Paragraph(t_loan, cell_s),
            Paragraph(tenure, cell_s),
            Paragraph(paid, cell_s),
            Paragraph(rem_ten, cell_s),
            Paragraph(rem_bal, cell_s),
            Paragraph(e.status.upper(), cell_s),
        ])
    if not all_emis.exists():
        ed.append(['-', 'No EMI records found', '-', '-', '-', '-', '-', '-', '-', '-', '-', '-'])
    else:
        ed.append(['TOTAL', 'All Entries', '-', '-', f'Rs.{total_emi_full}', f'Rs.{total_emi_personal}', '-', '-', '-', '-', '-', ''])
    
    t_emi = Table(ed, colWidths=[0.8*inch, 1.7*inch, 0.9*inch, 0.6*inch, 0.9*inch, 0.9*inch, 1.1*inch, 0.6*inch, 0.5*inch, 0.7*inch, 1.1*inch, 0.7*inch])
    t_emi.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#4a90d9')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('BACKGROUND', (0, 1), (-1, -2), colors.HexColor('#1e1e2e')),
        ('TEXTCOLOR', (0, 1), (-1, -2), colors.white),
        ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#333')),
        ('TEXTCOLOR', (0, -1), (-1, -1), colors.yellow),
        ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#444')),
        ('FONTSIZE', (0, 0), (-1, -1), 7.5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
    ]))
    els += [t_emi, Spacer(1, 12)]

    # Debts & Credits Table
    els.append(Paragraph("Debts & Credits (All Records)", styles['Heading2']))
    dd = [['Type', 'Person', 'Original Amount', 'Amount Paid', 'Remaining Balance', 'Status']]
    for d in all_debts:
        dd.append(['DEBT', d.person_name, f'Rs.{d.original_amount}', f'Rs.{d.amount_paid}', f'Rs.{d.remaining}', d.status.upper()])
    for c in all_credits:
        dd.append(['CREDIT', c.person_name, f'Rs.{c.original_amount}', f'Rs.{c.amount_paid}', f'Rs.{c.remaining}', c.status.upper()])
    if not all_debts.exists() and not all_credits.exists():
        dd.append(['-', 'No debt/credit records', '-', '-', '-', '-'])

    t_dc = Table(dd, colWidths=[1.0 * inch, 2.5 * inch, 1.5 * inch, 1.5 * inch, 1.5 * inch, 1.2 * inch])
    t_dc.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#4a90d9')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('BACKGROUND', (0, 1), (-1, -1), colors.HexColor('#1e1e2e')),
        ('TEXTCOLOR', (0, 1), (-1, -1), colors.white),
        ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#444')),
        ('FONTSIZE', (0, 0), (-1, -1), 8),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ]))
    els += [t_dc, Spacer(1, 12)]

    # Transactions Table
    els.append(Paragraph("Transaction History (All Records)", styles['Heading2']))
    td = [['Date', 'Title', 'Category', 'Amount']]
    for txn in all_txns:
        td.append([txn.date.strftime('%Y-%m-%d'), txn.title[:35], txn.display_category, f'Rs.{txn.amount}'])

    if not all_txns.exists():
        td.append(['-', 'No transactions', '-', '-'])

    t_txn = Table(td, colWidths=[1.5 * inch, 4.0 * inch, 2.0 * inch, 1.7 * inch])
    t_txn.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#2c3e50')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('BACKGROUND', (0, 1), (-1, -1), colors.HexColor('#1e1e2e')),
        ('TEXTCOLOR', (0, 1), (-1, -1), colors.white),
        ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#444')),
        ('FONTSIZE', (0, 0), (-1, -1), 8),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ]))
    els.append(t_txn)

    doc.build(els)
    buffer.seek(0)
    response = HttpResponse(buffer, content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="finance_full_report_{today.strftime("%Y%m%d")}.pdf"'
    return response



@login_required
def export_print(request):
    """Render full financial details formatted for print view."""
    today = date.today()
    cm = today.strftime('%Y-%m')
    balance = AccountBalance.get_instance(request.user)

    all_emis = MonthlyEMI.objects.filter(user=request.user).order_by('-month_year', 'due_day')
    all_debts = SplitDebt.objects.filter(user=request.user, debt_type='debt').order_by('-date_created')
    all_credits = SplitDebt.objects.filter(user=request.user, debt_type='credit').order_by('-date_created')
    all_txns = TransactionHistory.objects.filter(user=request.user).order_by('-date', '-created_at')

    cur_personal = all_emis.filter(month_year=cm).aggregate(t=Sum('personal_share'))['t'] or Decimal('0')
    total_emi_full = all_emis.aggregate(t=Sum('full_amount'))['t'] or Decimal('0')
    total_emi_personal = all_emis.aggregate(t=Sum('personal_share'))['t'] or Decimal('0')

    total_debt_rem = sum(d.remaining for d in all_debts.exclude(status='settled'))
    total_credit_rem = sum(c.remaining for c in all_credits.exclude(status='settled'))

    context = {
        'today': today,
        'balance': balance,
        'liquidity': balance.bank_balance - cur_personal,
        'all_emis': all_emis,
        'total_emi_full': total_emi_full,
        'total_emi_personal': total_emi_personal,
        'all_debts': all_debts,
        'all_credits': all_credits,
        'total_debt_rem': total_debt_rem,
        'total_credit_rem': total_credit_rem,
        'net_position': total_credit_rem - total_debt_rem,
        'all_txns': all_txns,
    }
    return render(request, 'finance/export_print.html', context)


# ERROR HANDLERS & CSRF FAILURE

def csrf_failure(request, reason=""):
    return render(request, '403.html', {
        'error_title': 'Security Verification Failed (CSRF Error)',
        'error_message': 'Your security session or CSRF token expired or failed verification. Please refresh the page or sign in again.',
        'error_detail': reason,
        'status_code': 403
    }, status=403)


def custom_handler404(request, exception=None):
    return render(request, '404.html', {
        'error_title': 'Page Not Set',
        'error_message': 'The page or link you requested is not set, invalid, or has been moved.',
        'status_code': 404
    }, status=404)


def custom_handler500(request):
    return render(request, '500.html', {
        'error_title': 'Page Not Set (Server Error)',
        'error_message': 'An internal system error occurred while loading this page.',
        'status_code': 500
    }, status=500)


def custom_handler403(request, exception=None):
    return render(request, '403.html', {
        'error_title': 'Page Not Set (Access Forbidden)',
        'error_message': 'You do not have permission to access this page.',
        'status_code': 403
    }, status=403)


def custom_handler400(request, exception=None):
    return render(request, 'error.html', {
        'error_title': 'Page Not Set (Bad Request)',
        'error_message': 'The request sent to the server was invalid.',
        'status_code': 400
    }, status=400)


