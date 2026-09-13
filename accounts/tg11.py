# SPDX-License-Identifier: AGPL-3.0-or-later
"""The shop's TG11 hook.

allauth requires a verified email address before an account counts as usable
(ACCOUNT_EMAIL_VERIFICATION = 'mandatory'). When TG11 has already verified the
address, saying so here keeps the two systems agreeing: the customer is not
asked to confirm an address a moment after TG11 confirmed it, and allauth's own
email page shows the truth.

The CustomerProfile row is created by the existing post_save signal, so there is
nothing to do for it.
"""
from __future__ import annotations


def on_tg11_login(*, user, claims, created, link, request=None) -> None:
    if not claims.email_verified or not user.email:
        return
    try:
        from allauth.account.models import EmailAddress
    except Exception:       # allauth absent or mid-upgrade: never break a sign-in
        return
    EmailAddress.objects.update_or_create(
        user=user,
        email=user.email,
        defaults={"verified": True, "primary": True},
    )
