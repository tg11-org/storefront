from __future__ import annotations

import logging

from django.conf import settings
from django.core.mail import mail_admins

logger = logging.getLogger(__name__)


def alert_ops(subject: str, message: str, *, level: str = 'warning') -> None:
    log_method = getattr(logger, level, logger.warning)
    log_method(subject, extra={'alert_message': message})
    if getattr(settings, 'PRICING_ALERT_EMAILS_ENABLED', False):
        mail_admins(subject, message, fail_silently=True)
