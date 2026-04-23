from django.urls import path

from .views import AccountDashboardView

app_name = 'accounts'

urlpatterns = [
    path('', AccountDashboardView.as_view(), name='dashboard'),
]
