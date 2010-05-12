from django.conf.urls.defaults import *
from django.contrib import admin
from django.conf import settings

from codereview.urls import urlpatterns

admin.autodiscover()

urlpatterns += patterns('',
        (r'^static/(?P<path>.*)$', 'django.views.static.serve',
            {'document_root': settings.MEDIA_ROOT}),
        (r'^accounts/login/$', 'rietveld_helper.views.login'),
        (r'^accounts/logout/$', 'django.contrib.auth.views.logout_then_login'),
        ('^admin/', include(admin.site.urls)),
        ('^_ah/admin', 'rietveld_helper.views.admin_redirect'),
    )

