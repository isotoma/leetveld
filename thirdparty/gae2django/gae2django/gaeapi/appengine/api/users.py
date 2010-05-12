from django.conf import settings
from django.contrib.auth.models import User


def get_current_user():
    from gae2django import middleware
    return middleware.get_current_user()


def is_current_user_admin():
    user = get_current_user()
    if user:
        return user.is_superuser
    return False


def create_login_url(redirect):
    return settings.LOGIN_URL+'?next='+redirect


def create_logout_url(redirect):
    return settings.LOGOUT_URL+'?next='+redirect


class Error(Exception):
    """Base class for all exceptions in this package."""


class UserNotFoundError(Error):
    """Raised if a User doesn't exist."""


class RedirectTooLongError(Error):
    """Raised if the redirect URL is too long."""
