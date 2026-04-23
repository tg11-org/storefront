from django.contrib.admin.views.decorators import staff_member_required
from django.shortcuts import render

from .models import ChannelAccount, SyncJob


@staff_member_required
def connector_overview(request):
    return render(request, 'connectors/overview.html', {'accounts': ChannelAccount.objects.all(), 'jobs': SyncJob.objects.all()[:20]})
