from django.http import HttpResponse
from django.template import Context, Template

from gaeapi.appengine.api import users

def test(request):
    t = Template('Test view')
    c = Context({'user': request.user,
                 'is_admin': users.is_current_user_admin()})
    return HttpResponse(t.render(c))
