from django.urls import path

from .views import connector_overview

app_name = 'connectors'

urlpatterns = [
    path('', connector_overview, name='overview'),
]
