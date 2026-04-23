from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse


class AccountTests(TestCase):
    def test_dashboard_requires_login(self):
        response = self.client.get(reverse('accounts:dashboard'))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse('account_login'), response.url)

    def test_user_can_log_in_and_view_dashboard(self):
        user = get_user_model().objects.create_user(email='hello@example.com', password='StrongPass123!', first_name='Test')
        self.client.login(email='hello@example.com', password='StrongPass123!')
        response = self.client.get(reverse('accounts:dashboard'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Account dashboard')
