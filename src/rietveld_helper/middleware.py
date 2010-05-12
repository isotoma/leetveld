
from codereview import models

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
            request.user = None
        response = view_func(request, *view_args, **view_kwargs)
        request.user = user
        return response
