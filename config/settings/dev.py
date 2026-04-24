from .base import *

DEBUG = True
SECURE_SSL_REDIRECT = False
SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False
SECURE_HSTS_SECONDS = 0
EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'
STATICFILES_STORAGE = 'django.contrib.staticfiles.storage.StaticFilesStorage'
