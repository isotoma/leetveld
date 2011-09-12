from django.http import HttpResponseRedirect

def admin_redirect(request):
    return HttpResponseRedirect('/admin/')
