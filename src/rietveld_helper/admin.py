from django import template
from django.conf import settings
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.models import User
from django.contrib.sites.models import Site
from django.contrib import messages
from django.utils.translation import ugettext_lazy as _
from django.utils.translation import ugettext
from django.http import HttpResponseRedirect, Http404
from django.shortcuts import render_to_response
from django.contrib.auth.forms import UserCreationForm
from django import forms

from django.db import models

class FakeIssue(models.Model):
    """Fake Issue model that admin will understand
    """
    subject = models.CharField()
    description = models.CharField()
    base = models.CharField()
    local_base = models.BooleanField(default=False)
    owner = models.ForeignKey(User)
    created = models.DateTimeField(auto_now_add=True)
    modified = models.DateTimeField(auto_now=True)
    reviewers = models.ManyToManyField(User)
    cc = models.ManyToManyField(User)
    closed = models.BooleanField(default=False)
    private = models.BooleanField(default=False)
    n_comments = models.IntegerField(default=0,
                                     verbose_name="Number of comments")

    class Meta:
        db_table = 'leetveld_issue'
        verbose_name = "Issue"
        verbose_name_plural = "Issues"

class FakePatchSet(models.Model):
    """Fake PatchSet model that admin will understand
    """
    issue = models.ForeignKey(FakeIssue)  # == parent
    message = models.CharField()
    data = models.FileField()
    url = models.URLField()
    owner = models.ForeignKey(User)
    created = models.DateTimeField(auto_now_add=True)
    modified = models.DateTimeField(auto_now=True)
    n_comments = models.IntegerField(default=0,
                                     verbose_name="Number of comments")

    class Meta:
        db_table = 'leetveld_patchset'
        verbose_name = "PatchSet"
        verbose_name_plural = "PatchSets"

# Patch in some simple lambda's, Django uses them.
FakeIssue.__unicode__ = lambda self: self.subject
FakePatchSet.__unicode__ = lambda self: self.message or ''

class PatchSetInlineAdmin(admin.TabularInline):
    model = FakePatchSet

class PatchSetAdmin(admin.ModelAdmin):
    list_filter = ('issue', 'owner')
    list_display = ('issue', 'message')
    search_fields = ('issue__subject', 'message')

class IssueAdmin(admin.ModelAdmin):
    list_filter = ('closed', 'owner')
    list_display = ('id', 'subject', 'owner', 'modified', 'n_comments')
    list_display_links = ('id', 'subject')
    inlines = [PatchSetInlineAdmin]

admin.site.register(FakeIssue, IssueAdmin)
admin.site.register(FakePatchSet, PatchSetAdmin)

admin.site.unregister(Site)

#################################################
# Overide User creation to add mandatory email
#################################################

class UserCreationFormWithEmail(UserCreationForm):
    email = forms.EmailField(label=_("E-mail"), max_length=75)

class UserAdminWithEmail(UserAdmin):

    def add_view(self, request):
        # It's an error for a user to have add permission but NOT change
        # permission for users. If we allowed such users to add users, they
        # could create superusers, which would mean they would essentially have
        # the permission to change users. To avoid the problem entirely, we
        # disallow users from adding users if they don't have change
        # permission.
        if not self.has_change_permission(request):
            if self.has_add_permission(request) and settings.DEBUG:
                # Raise Http404 in debug mode so that the user gets a helpful
                # error message.
                raise Http404('Your user does not have the "Change user" permission. In order to add users, Django requires that your user account have both the "Add user" and "Change user" permissions set.')
            raise PermissionDenied
        if request.method == 'POST':
            form = UserCreationFormWithEmail(request.POST)
            if form.is_valid():
                new_user = form.save()
                # TODO: can't get these from the form for some reason,
                # the ModelForm doesn't like being inherited or something,
                # so we're just going to grab them from the POST collection
                # It'll get sorted out one day no doubt ;)
                new_user.email = request.POST.get('email')
                new_user.set_password(request.POST.get('password1'))
                new_user.save()

                msg = _('The %(name)s "%(obj)s" was added successfully.') % {'name': 'user', 'obj': new_user}
                self.log_addition(request, new_user)
                if "_addanother" in request.POST:
                    messages.success(request, msg)
                    return HttpResponseRedirect(request.path)
                elif '_popup' in request.REQUEST:
                    return self.response_add(request, new_user)
                else:
                    messages.success(request, msg + ' ' +
                                     ugettext("You may edit it again below."))
                    return HttpResponseRedirect('../%s/' % new_user.id)
        else:
            form = UserCreationFormWithEmail()

        return render_to_response('add_form.html', {
            'title': _('Add user'),
            'form': form,
            'is_popup': '_popup' in request.REQUEST,
            'add': True,
            'change': False,
            'has_add_permission': True,
            'has_delete_permission': False,
            'has_change_permission': True,
            'has_file_field': False,
            'has_absolute_url': False,
            'auto_populated_fields': (),
            'opts': self.model._meta,
            'save_as': False,
            'username_help_text': self.model._meta.get_field('username').help_text,
            'root_path': self.admin_site.root_path,
            'app_label': self.model._meta.app_label,
        }, context_instance=template.RequestContext(request))

admin.site.unregister(User)
admin.site.register(User, UserAdminWithEmail)
