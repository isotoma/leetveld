from django.contrib.messages.api import get_messages

from codereview import models


class DisableCSRFMiddleware(object):
    """This is a BAD middleware. It disables CSRF protection.

    If someone comes up with a smart approach to make upload.py work
    with Django's CSRF protection, please submit a patch!
    """

    def process_request(self, request):
        setattr(request, '_dont_enforce_csrf_checks', True)


class AddUserToRequestMiddleware(object):
    """Just add the account..."""

    def process_request(self, request):
        account = None
        is_admin = False
        if not request.user.is_anonymous():
            account = models.Account.get_account_for_user(request.user)
            is_admin = request.user.is_superuser
        models.Account.current_user_account = account
        request.user_is_admin = is_admin

    def process_view(self, request, view_func, view_args, view_kwargs):
        is_rietveld = view_func.__module__.startswith('codereview')
        user = request.user
        if is_rietveld and user.is_anonymous():
            # Pre-fetch messages before changing request.user so that
            # they're cached (for Django 1.2.5 and above).
            request._messages = get_messages(request)
            request.user = None
        response = view_func(request, *view_args, **view_kwargs)
        request.user = user
        return response
