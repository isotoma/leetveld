from django.contrib import admin
from django.contrib.auth.models import User
from django.contrib.sites.models import Site

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
        db_table = 'codereview_issue'
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
        db_table = 'codereview_patchset'
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


