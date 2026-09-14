from django.urls import path

from . import views

app_name = 'sitepages'

urlpatterns = [
    path('about/', views.about, name='about'),
    path('terms/', views.terms, name='terms'),
    path('privacy/', views.privacy, name='privacy'),
    path('guidelines/', views.guidelines, name='guidelines'),
    path('faq/', views.faq, name='faq'),
    path('support/', views.support, name='support'),
    path('status/', views.status, name='status'),
    path('changelog/', views.changelog, name='changelog'),
]
