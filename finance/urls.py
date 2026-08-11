from django.urls import path
from django.contrib.auth import views as auth_views
from . import views

app_name = 'finance'

urlpatterns = [
    # Auth
    path('register/', views.register_view, name='register'),
    path('login/', auth_views.LoginView.as_view(template_name='finance/login.html'), name='login'),
    path('logout/', views.logout_view, name='logout'),

    # Dashboard
    path('', views.dashboard, name='dashboard'),

    # EMI
    path('emis/', views.emi_list, name='emi_list'),
    path('emis/add/', views.emi_add, name='emi_add'),
    path('emis/<int:pk>/mark-paid/', views.emi_mark_paid, name='emi_mark_paid'),
    path('emis/<int:pk>/edit/', views.emi_edit, name='emi_edit'),
    path('emis/<int:pk>/delete/', views.emi_delete, name='emi_delete'),

    # Debts & Credits
    path('debts/', views.debts_credits, name='debts_credits'),
    path('debts/add/', views.debt_add, name='debt_add'),
    path('debts/<int:pk>/settle/', views.debt_settle, name='debt_settle'),
    path('debts/<int:pk>/edit/', views.debt_edit, name='debt_edit'),
    path('debts/<int:pk>/delete/', views.debt_delete, name='debt_delete'),

    # Beneficiaries
    path('beneficiaries/', views.beneficiary_list, name='beneficiary_list'),
    path('beneficiaries/add/', views.beneficiary_add, name='beneficiary_add'),
    path('beneficiaries/<int:pk>/edit/', views.beneficiary_edit, name='beneficiary_edit'),
    path('beneficiaries/<int:pk>/delete/', views.beneficiary_delete, name='beneficiary_delete'),

    # Profile & Security
    path('profile/', views.profile_view, name='profile'),
    path('profile/send-otp/', views.send_profile_otp, name='send_profile_otp'),
    path('profile/verify-otp/', views.verify_profile_otp, name='verify_profile_otp'),

    # Balance & Transfer & Adjustment
    path('balance/update/', views.balance_update, name='balance_update'),
    path('balance/adjust/', views.adjust_balance_view, name='adjust_balance'),
    path('transfer/', views.transfer_funds, name='transfer_funds'),

    # Transactions
    path('transactions/', views.transaction_list, name='transaction_list'),
    path('transactions/add/', views.transaction_add, name='transaction_add'),
    path('transactions/bulk-action/', views.transaction_bulk_action, name='transaction_bulk_action'),
    path('transactions/<int:pk>/edit/', views.transaction_edit, name='transaction_edit'),
    path('transactions/<int:pk>/delete/', views.transaction_delete, name='transaction_delete'),

    # Categories
    path('categories/', views.category_list, name='category_list'),
    path('categories/<int:pk>/delete/', views.category_delete, name='category_delete'),

    # Notifications
    path('dismiss-notification/', views.dismiss_notification, name='dismiss_notification'),

    # AI Assistant
    path('assistant/', views.assistant, name='assistant'),
    path('assistant/api/', views.assistant_api, name='assistant_api'),

    # Export
    path('export/', views.export_page, name='export_page'),
    path('export/text/', views.export_text, name='export_text'),
    path('export/csv/', views.export_csv, name='export_csv'),
    path('export/pdf/', views.export_pdf, name='export_pdf'),
    path('export/print/', views.export_print, name='export_print'),
]

