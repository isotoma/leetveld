# Copyright 2008 Google Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Views for Rietveld."""


### Imports ###


# Python imports
import binascii
import datetime
import email  # see incoming_mail()
import email.utils
import logging
import md5
import os
import random
import re
import urllib
from cStringIO import StringIO
from xml.etree import ElementTree

# AppEngine imports
from google.appengine.api import mail
from google.appengine.api import memcache
from google.appengine.api import users
from google.appengine.api import urlfetch
from google.appengine.api import xmpp
from google.appengine.ext import db
from google.appengine.ext.db import djangoforms
from google.appengine.runtime import DeadlineExceededError
from google.appengine.runtime import apiproxy_errors

# Django imports
# TODO(guido): Don't import classes/functions directly.
from django import forms
# Import settings as django_settings to avoid name conflict with settings().
from django.conf import settings as django_settings
from django.http import HttpResponse, HttpResponseRedirect
from django.http import HttpResponseForbidden, HttpResponseNotFound
from django.http import HttpResponseBadRequest
from django.shortcuts import render_to_response
import django.template
from django.template import RequestContext
from django.utils import simplejson
from django.utils.safestring import mark_safe
from django.core.urlresolvers import reverse

# Local imports
import models
import engine
import library
import patching

# Add our own template library.
_library_name = __name__.rsplit('.', 1)[0] + '.library'
if not django.template.libraries.get(_library_name, None):
  django.template.add_to_builtins(_library_name)


### Constants ###


IS_DEV = os.environ['SERVER_SOFTWARE'].startswith('Dev')  # Development server


### Form classes ###


class AccountInput(forms.TextInput):
  # Associates the necessary css/js files for the control.  See
  # http://docs.djangoproject.com/en/dev/topics/forms/media/.
  #
  # Don't forget to place {{formname.media}} into html header
  # when using this html control.
  class Media:
    css = {
      'all': ('autocomplete/jquery.autocomplete.css',)
    }
    js = (
      'autocomplete/lib/jquery.js',
      'autocomplete/lib/jquery.bgiframe.min.js',
      'autocomplete/lib/jquery.ajaxQueue.js',
      'autocomplete/jquery.autocomplete.js'
    )

  def render(self, name, value, attrs=None):
    output = super(AccountInput, self).render(name, value, attrs)
    if models.Account.current_user_account is not None:
      # TODO(anatoli): move this into .js media for this form
      data = {'name': name, 'url': reverse(account),
              'multiple': 'true'}
      if self.attrs.get('multiple', True) == False:
        data['multiple'] = 'false'
      output += mark_safe(u'''
      <script type="text/javascript">
          jQuery("#id_%(name)s").autocomplete("%(url)s", {
          max: 10,
          highlight: false,
          multiple: %(multiple)s,
          multipleSeparator: ", ",
          scroll: true,
          scrollHeight: 300,
          matchContains: true,
          formatResult : function(row) {
          return row[0].replace(/ .+/gi, '');
          }
          });
      </script>''' % data)
    return output


class IssueBaseForm(forms.Form):

  subject = forms.CharField(max_length=100,
                            widget=forms.TextInput(attrs={'size': 60}))
  description = forms.CharField(required=False,
                                max_length=10000,
                                widget=forms.Textarea(attrs={'cols': 60}))
  branch = forms.ChoiceField(required=False, label='Base URL')
  base = forms.CharField(required=False,
                         max_length=1000,
                         widget=forms.TextInput(attrs={'size': 60}))
  reviewers = forms.CharField(required=False,
                              max_length=1000,
                              widget=AccountInput(attrs={'size': 60}))
  cc = forms.CharField(required=False,
                       max_length=2000,
                       label = 'CC',
                       widget=AccountInput(attrs={'size': 60}))
  private = forms.BooleanField(required=False, initial=False)

  def set_branch_choices(self, base=None):
    branches = models.Branch.all()
    bound_field = self['branch']
    choices = []
    default = None
    for b in branches:
      if not b.repo_name:
        b.repo_name = b.repo.name
        b.put()
      pair = (b.key(), '%s - %s - %s' % (b.repo_name, b.category, b.name))
      choices.append(pair)
      if default is None and (base is None or b.url == base):
        default = b.key()
    choices.sort(key=lambda pair: pair[1].lower())
    choices.insert(0, ('', '[See Base]'))
    bound_field.field.choices = choices
    if default is not None:
      self.initial['branch'] = default

  def get_base(self):
    base = self.cleaned_data.get('base')
    if not base:
      key = self.cleaned_data['branch']
      if key:
        branch = models.Branch.get(key)
        if branch is not None:
          base = branch.url
    if not base:
      self.errors['base'] = ['You must specify a base']
    return base or None


class NewForm(IssueBaseForm):

  data = forms.FileField(required=False)
  url = forms.URLField(required=False,
                       max_length=2083,
                       widget=forms.TextInput(attrs={'size': 60}))
  send_mail = forms.BooleanField(required=False, initial=True)


class AddForm(forms.Form):

  message = forms.CharField(max_length=100,
                            widget=forms.TextInput(attrs={'size': 60}))
  data = forms.FileField(required=False)
  url = forms.URLField(required=False,
                       max_length=2083,
                       widget=forms.TextInput(attrs={'size': 60}))
  reviewers = forms.CharField(max_length=1000, required=False,
                              widget=AccountInput(attrs={'size': 60}))
  send_mail = forms.BooleanField(required=False, initial=True)


class UploadForm(forms.Form):

  subject = forms.CharField(max_length=100)
  description = forms.CharField(max_length=10000, required=False)
  content_upload = forms.BooleanField(required=False)
  separate_patches = forms.BooleanField(required=False)
  base = forms.CharField(max_length=2000, required=False)
  data = forms.FileField(required=False)
  issue = forms.IntegerField(required=False)
  description = forms.CharField(max_length=10000, required=False)
  reviewers = forms.CharField(max_length=1000, required=False)
  cc = forms.CharField(max_length=1000, required=False)
  private = forms.BooleanField(required=False, initial=False)
  send_mail = forms.BooleanField(required=False)
  base_hashes = forms.CharField(required=False)

  def clean_base(self):
    base = self.cleaned_data.get('base')
    if not base and not self.cleaned_data.get('content_upload', False):
      raise forms.ValidationError, 'Base URL is required.'
    return self.cleaned_data.get('base')

  def get_base(self):
    return self.cleaned_data.get('base')


class UploadContentForm(forms.Form):
  filename = forms.CharField(max_length=255)
  status = forms.CharField(required=False, max_length=20)
  checksum = forms.CharField(max_length=32)
  file_too_large = forms.BooleanField(required=False)
  is_binary = forms.BooleanField(required=False)
  is_current = forms.BooleanField(required=False)

  def clean(self):
    # Check presence of 'data'. We cannot use FileField because
    # it disallows empty files.
    super(UploadContentForm, self).clean()
    if not self.files and 'data' not in self.files:
      raise forms.ValidationError, 'No content uploaded.'
    return self.cleaned_data

  def get_uploaded_content(self):
    return self.files['data'].read()


class UploadPatchForm(forms.Form):
  filename = forms.CharField(max_length=255)
  content_upload = forms.BooleanField(required=False)

  def get_uploaded_patch(self):
    return self.files['data'].read()


class EditForm(IssueBaseForm):

  closed = forms.BooleanField(required=False)


class EditLocalBaseForm(forms.Form):
  subject = forms.CharField(max_length=100,
                            widget=forms.TextInput(attrs={'size': 60}))
  description = forms.CharField(required=False,
                                max_length=10000,
                                widget=forms.Textarea(attrs={'cols': 60}))
  reviewers = forms.CharField(required=False,
                              max_length=1000,
                              widget=AccountInput(attrs={'size': 60}))
  cc = forms.CharField(required=False,
                       max_length=1000,
                       label = 'CC',
                       widget=AccountInput(attrs={'size': 60}))
  private = forms.BooleanField(required=False, initial=False)
  closed = forms.BooleanField(required=False)

  def get_base(self):
    return None


class RepoForm(djangoforms.ModelForm):

  class Meta:
    model = models.Repository
    exclude = ['owner']


class BranchForm(djangoforms.ModelForm):

  class Meta:
    model = models.Branch
    exclude = ['owner', 'repo_name']


class PublishForm(forms.Form):

  subject = forms.CharField(max_length=100,
                            widget=forms.TextInput(attrs={'size': 60}))
  reviewers = forms.CharField(required=False,
                              max_length=1000,
                              widget=AccountInput(attrs={'size': 60}))
  cc = forms.CharField(required=False,
                       max_length=1000,
                       label = 'CC',
                       widget=AccountInput(attrs={'size': 60}))
  send_mail = forms.BooleanField(required=False)
  message = forms.CharField(required=False,
                            max_length=10000,
                            widget=forms.Textarea(attrs={'cols': 60}))
  message_only = forms.BooleanField(required=False,
                                    widget=forms.HiddenInput())
  no_redirect = forms.BooleanField(required=False,
                                   widget=forms.HiddenInput())


class MiniPublishForm(forms.Form):

  reviewers = forms.CharField(required=False,
                              max_length=1000,
                              widget=AccountInput(attrs={'size': 60}))
  cc = forms.CharField(required=False,
                       max_length=1000,
                       label = 'CC',
                       widget=AccountInput(attrs={'size': 60}))
  send_mail = forms.BooleanField(required=False)
  message = forms.CharField(required=False,
                            max_length=10000,
                            widget=forms.Textarea(attrs={'cols': 60}))
  message_only = forms.BooleanField(required=False,
                                    widget=forms.HiddenInput())
  no_redirect = forms.BooleanField(required=False,
                                   widget=forms.HiddenInput())


FORM_CONTEXT_VALUES = [(x, '%d lines' % x) for x in models.CONTEXT_CHOICES]
FORM_CONTEXT_VALUES.append(('', 'Whole file'))


class SettingsForm(forms.Form):

  nickname = forms.CharField(max_length=30)
  context = forms.IntegerField(
    widget=forms.Select(choices=FORM_CONTEXT_VALUES),
    required=False,
    label='Context')
  column_width = forms.IntegerField(initial=engine.DEFAULT_COLUMN_WIDTH,
                                    min_value=engine.MIN_COLUMN_WIDTH,
                                    max_value=engine.MAX_COLUMN_WIDTH)
  notify_by_email = forms.BooleanField(required=False,
                                       widget=forms.HiddenInput())
  notify_by_chat = forms.BooleanField(
    required=False,
    help_text='You must accept the invite for this to work.')

  def clean_nickname(self):
    nickname = self.cleaned_data.get('nickname')
    # Check for allowed characters
    match = re.match(r'[\w\.\-_\(\) ]+$', nickname, re.UNICODE|re.IGNORECASE)
    if not match:
      raise forms.ValidationError('Allowed characters are letters, digits, '
                                  '".-_()" and spaces.')
    # Check for sane whitespaces
    if re.search(r'\s{2,}', nickname):
      raise forms.ValidationError('Use single spaces between words.')
    if len(nickname) != len(nickname.strip()):
      raise forms.ValidationError('Leading and trailing whitespaces are '
                                  'not allowed.')

    if nickname.lower() == 'me':
      raise forms.ValidationError('Choose a different nickname.')

    # Look for existing nicknames
    accounts = list(models.Account.gql('WHERE lower_nickname = :1',
                                       nickname.lower()))
    for account in accounts:
      if account.key() == models.Account.current_user_account.key():
        continue
      raise forms.ValidationError('This nickname is already in use.')

    return nickname


class SearchForm(forms.Form):

  format = forms.ChoiceField(
      required=False,
      choices=(
        ('html', 'html'),
        ('json', 'json')),
      widget=forms.HiddenInput(attrs={'value': 'html'}))
  keys_only = forms.BooleanField(
      required=False,
      widget=forms.HiddenInput(attrs={'value': 'False'}))
  with_messages = forms.BooleanField(
      required=False,
      widget=forms.HiddenInput(attrs={'value': 'False'}))
  cursor = forms.CharField(
      required=False,
      widget=forms.HiddenInput(attrs={'value': ''}))
  limit = forms.IntegerField(
      required=False,
      min_value=1,
      max_value=1000,
      initial=10,
      widget=forms.HiddenInput(attrs={'value': '10'}))
  closed = forms.NullBooleanField(required=False)
  owner = forms.CharField(required=False,
                          max_length=1000,
                          widget=AccountInput(attrs={'size': 60,
                                                     'multiple': False}))
  reviewer = forms.CharField(required=False,
                             max_length=1000,
                             widget=AccountInput(attrs={'size': 60,
                                                        'multiple': False}))
  base = forms.CharField(required=False, max_length=550)
  private = forms.NullBooleanField(required=False)

  def _clean_accounts(self, key):
    """Cleans up autocomplete field.

    The input is validated to be zero or one name/email and it's
    validated that the users exists.

    Args:
      key: the field name.

    Returns an User instance or raises ValidationError.
    """
    accounts = filter(None,
                      (x.strip()
                       for x in self.cleaned_data.get(key, '').split(',')))
    if len(accounts) > 1:
      raise forms.ValidationError('Only one user name is allowed.')
    elif not accounts:
      return None
    account = accounts[0]
    if '@' in account:
      acct = models.Account.get_account_for_email(account)
    else:
      acct = models.Account.get_account_for_nickname(account)
    if not acct:
      raise forms.ValidationError('Unknown user')
    return acct.user

  def clean_owner(self):
    return self._clean_accounts('owner')

  def clean_reviewer(self):
    user = self._clean_accounts('reviewer')
    if user:
      return user.email()


### Exceptions ###


class InvalidIncomingEmailError(Exception):
  """Exception raised by incoming mail handler when a problem occurs."""


### Helper functions ###


# Counter displayed (by respond()) below) on every page showing how
# many requests the current incarnation has handled, not counting
# redirects.  Rendered by templates/base.html.
counter = 0


def respond(request, template, params=None):
  """Helper to render a response, passing standard stuff to the response.

  Args:
    request: The request object.
    template: The template name; '.html' is appended automatically.
    params: A dict giving the template parameters; modified in-place.

  Returns:
    Whatever render_to_response(template, params) returns.

  Raises:
    Whatever render_to_response(template, params) raises.
  """
  global counter
  counter += 1
  if params is None:
    params = {}
  must_choose_nickname = False
  uploadpy_hint = False
  if request.user is not None:
    account = models.Account.current_user_account
    must_choose_nickname = not account.user_has_selected_nickname()
    uploadpy_hint = account.uploadpy_hint
  params['request'] = request
  params['counter'] = counter
  params['user'] = request.user
  params['is_admin'] = request.user_is_admin
  params['is_dev'] = IS_DEV
  params['media_url'] = django_settings.MEDIA_URL
  full_path = request.get_full_path().encode('utf-8')
  if request.user is None:
    params['sign_in'] = users.create_login_url(full_path)
  else:
    params['sign_out'] = users.create_logout_url(full_path)
    account = models.Account.current_user_account
    if account is not None:
      params['xsrf_token'] = account.get_xsrf_token()
  params['must_choose_nickname'] = must_choose_nickname
  params['uploadpy_hint'] = uploadpy_hint
  params['rietveld_revision'] = django_settings.RIETVELD_REVISION
  try:
    return render_to_response(template, params,
                              context_instance=RequestContext(request))
  except DeadlineExceededError:
    logging.exception('DeadlineExceededError')
    return HttpResponse('DeadlineExceededError', status=503)
  except apiproxy_errors.CapabilityDisabledError, err:
    logging.exception('CapabilityDisabledError: %s', err)
    return HttpResponse('Rietveld: App Engine is undergoing maintenance. '
                        'Please try again in a while. ' + str(err),
                        status=503)
  except MemoryError:
    logging.exception('MemoryError')
    return HttpResponse('MemoryError', status=503)
  except AssertionError:
    logging.exception('AssertionError')
    return HttpResponse('AssertionError')
  finally:
    library.user_cache.clear() # don't want this sticking around


def _random_bytes(n):
  """Helper returning a string of random bytes of given length."""
  return ''.join(map(chr, (random.randrange(256) for i in xrange(n))))


def _clean_int(value, default, min_value=None, max_value=None):
  """Helper to cast value to int and to clip it to min or max_value.

  Args:
    value: Any value (preferably something that can be casted to int).
    default: Default value to be used when type casting fails.
    min_value: Minimum allowed value (default: None).
    max_value: Maximum allowed value (default: None).

  Returns:
    An integer between min_value and max_value.
  """
  if not isinstance(value, (int, long)):
    try:
      value = int(value)
    except (TypeError, ValueError), err:
      value = default
  if min_value is not None:
    value = max(min_value, value)
  if max_value is not None:
    value = min(value, max_value)
  return value


def _can_view_issue(user, issue):
  if user is None:
    return not issue.private
  user_email = db.Email(user.email().lower())
  return (not issue.private
          or issue.owner == user
          or user_email in issue.cc
          or user_email in issue.reviewers)


def _notify_issue(request, issue, message):
  """Try sending an XMPP (chat) message.

  Args:
    request: The request object.
    issue: Issue whose owner, reviewers, CC are to be notified.
    message: Text of message to send, e.g. 'Created'.

  The current user and the issue's subject and URL are appended to the message.

  Returns:
    True if the message was (apparently) delivered, False if not.
  """
  iid = issue.key().id()
  emails = [issue.owner.email()]
  if issue.reviewers:
    emails.extend(issue.reviewers)
  if issue.cc:
    emails.extend(issue.cc)
  accounts = models.Account.get_multiple_accounts_by_email(emails)
  jids = []
  for account in accounts.itervalues():
    logging.debug('email=%r,chat=%r', account.email, account.notify_by_chat)
    if account.notify_by_chat:
      jids.append(account.email)
  if not jids:
    logging.debug('No XMPP jids to send to for issue %d', iid)
    return True  # Nothing to do.
  jids_str = ', '.join(jids)
  logging.debug('Sending XMPP for issue %d to %s', iid, jids_str)
  sender = '?'
  if models.Account.current_user_account:
    sender = models.Account.current_user_account.nickname
  elif request.user:
    sender = request.user.email()
  message = '%s by %s: %s\n%s' % (message,
                                  sender,
                                  issue.subject,
                                  request.build_absolute_uri(
                                    reverse(show, args=[iid])))
  try:
    sts = xmpp.send_message(jids, message)
  except Exception, err:
    logging.exception('XMPP exception %s sending for issue %d to %s',
                      err, iid, jids_str)
    return False
  else:
    if sts == [xmpp.NO_ERROR] * len(jids):
      logging.info('XMPP message sent for issue %d to %s', iid, jids_str)
      return True
    else:
      logging.error('XMPP error %r sending for issue %d to %s',
                    sts, iid, jids_str)
      return False


### Decorators for request handlers ###


def post_required(func):
  """Decorator that returns an error unless request.method == 'POST'."""

  def post_wrapper(request, *args, **kwds):
    if request.method != 'POST':
      return HttpResponse('This requires a POST request.', status=405)
    return func(request, *args, **kwds)

  return post_wrapper


def login_required(func):
  """Decorator that redirects to the login page if you're not logged in."""

  def login_wrapper(request, *args, **kwds):
    if request.user is None:
      return HttpResponseRedirect(
          users.create_login_url(request.get_full_path().encode('utf-8')))
    return func(request, *args, **kwds)

  return login_wrapper


def xsrf_required(func):
  """Decorator to check XSRF token.

  This only checks if the method is POST; it lets other method go
  through unchallenged.  Apply after @login_required and (if
  applicable) @post_required.  This decorator is mutually exclusive
  with @upload_required.
  """

  def xsrf_wrapper(request, *args, **kwds):
    if request.method == 'POST':
      post_token = request.POST.get('xsrf_token')
      if not post_token:
        return HttpResponse('Missing XSRF token.', status=403)
      account = models.Account.current_user_account
      if not account:
        return HttpResponse('Must be logged in for XSRF check.', status=403)
      xsrf_token = account.get_xsrf_token()
      if post_token != xsrf_token:
        # Try the previous hour's token
        xsrf_token = account.get_xsrf_token(-1)
        if post_token != xsrf_token:
          return HttpResponse('Invalid XSRF token.', status=403)
    return func(request, *args, **kwds)

  return xsrf_wrapper


def upload_required(func):
  """Decorator for POST requests from the upload.py script.

  Right now this is for documentation only, but eventually we should
  change this to insist on a special header that JavaScript cannot
  add, to prevent XSRF attacks on these URLs.  This decorator is
  mutually exclusive with @xsrf_required.
  """
  return func


def admin_required(func):
  """Decorator that insists that you're logged in as administratior."""

  def admin_wrapper(request, *args, **kwds):
    if request.user is None:
      return HttpResponseRedirect(
          users.create_login_url(request.get_full_path().encode('utf-8')))
    if not request.user_is_admin:
      return HttpResponseForbidden('You must be admin in for this function')
    return func(request, *args, **kwds)

  return admin_wrapper


def issue_required(func):
  """Decorator that processes the issue_id handler argument."""

  def issue_wrapper(request, issue_id, *args, **kwds):
    issue = models.Issue.get_by_id(int(issue_id))
    if issue is None:
      return HttpResponseNotFound('No issue exists with that id (%s)' %
                                  issue_id)
    if issue.private:
      if request.user is None:
        return HttpResponseRedirect(
            users.create_login_url(request.get_full_path().encode('utf-8')))
      if not _can_view_issue(request.user, issue):
        return HttpResponseForbidden('You do not have permission to '
                                     'view this issue')
    request.issue = issue
    return func(request, *args, **kwds)

  return issue_wrapper


def user_key_required(func):
  """Decorator that processes the user handler argument."""

  def user_key_wrapper(request, user_key, *args, **kwds):
    user_key = urllib.unquote(user_key)
    if '@' in user_key:
      request.user_to_show = users.User(user_key)
    else:
      account = models.Account.get_account_for_nickname(user_key)
      if not account:
        logging.info("account not found for nickname %s" % user_key)
        return HttpResponseNotFound('No user found with that key (%s)' %
                                    urllib.quote(user_key))
      request.user_to_show = account.user
    return func(request, *args, **kwds)

  return user_key_wrapper


def owner_required(func):
  """Decorator that insists you own the issue.

  It must appear after issue_required or equivalent, like patchset_required.
  """

  @login_required
  def owner_wrapper(request, *args, **kwds):
    if request.issue.owner != request.user:
      return HttpResponseForbidden('You do not own this issue')
    return func(request, *args, **kwds)

  return owner_wrapper


def issue_owner_required(func):
  """Decorator that processes the issue_id argument and insists you own it."""

  @issue_required
  @owner_required
  def issue_owner_wrapper(request, *args, **kwds):
    return func(request, *args, **kwds)

  return issue_owner_wrapper


def issue_editor_required(func):
  """Decorator that processes the issue_id argument and insists the user has
  permission to edit it."""

  @login_required
  @issue_required
  def issue_editor_wrapper(request, *args, **kwds):
    if not request.issue.user_can_edit(request.user):
      return HttpResponseForbidden('You do not have permission to '
                                   'edit this issue')
    return func(request, *args, **kwds)

  return issue_editor_wrapper


def patchset_required(func):
  """Decorator that processes the patchset_id argument."""

  @issue_required
  def patchset_wrapper(request, patchset_id, *args, **kwds):
    patchset = models.PatchSet.get_by_id(int(patchset_id), parent=request.issue)
    if patchset is None:
      return HttpResponseNotFound('No patch set exists with that id (%s)' %
                                  patchset_id)
    patchset.issue = request.issue
    request.patchset = patchset
    return func(request, *args, **kwds)

  return patchset_wrapper


def patchset_owner_required(func):
  """Decorator that processes the patchset_id argument and insists you own the
  issue."""

  @patchset_required
  @owner_required
  def patchset_owner_wrapper(request, *args, **kwds):
    return func(request, *args, **kwds)

  return patchset_owner_wrapper


def patch_required(func):
  """Decorator that processes the patch_id argument."""

  @patchset_required
  def patch_wrapper(request, patch_id, *args, **kwds):
    patch = models.Patch.get_by_id(int(patch_id), parent=request.patchset)
    if patch is None:
      return HttpResponseNotFound('No patch exists with that id (%s/%s)' %
                                  (request.patchset.key().id(), patch_id))
    patch.patchset = request.patchset
    request.patch = patch
    return func(request, *args, **kwds)

  return patch_wrapper


def patch_filename_required(func):
  """Decorator that processes the patch_id argument."""

  @patchset_required
  def patch_wrapper(request, patch_filename, *args, **kwds):
    patch = models.Patch.gql('WHERE patchset = :1 AND filename = :2',
                             request.patchset, patch_filename).get()
    if patch is None and patch_filename.isdigit():
      # It could be an old URL which has a patch ID instead of a filename
      patch = models.Patch.get_by_id(int(patch_filename),
                                     parent=request.patchset)
    if patch is None:
      return respond(request, 'diff_missing.html',
                     {'issue': request.issue,
                      'patchset': request.patchset,
                      'patch': None,
                      'patchsets': request.issue.patchset_set,
                      'filename': patch_filename})
    patch.patchset = request.patchset
    request.patch = patch
    return func(request, *args, **kwds)

  return patch_wrapper


def image_required(func):
  """Decorator that processes the image argument.

  Attributes set on the request:
   content: a Content entity.
  """

  @patch_required
  def image_wrapper(request, image_type, *args, **kwds):
    content = None
    if image_type == "0":
      content = request.patch.content
    elif image_type == "1":
      content = request.patch.patched_content
    # Other values are erroneous so request.content won't be set.
    if not content or not content.data:
      return HttpResponseRedirect(django_settings.MEDIA_URL + "blank.jpg")
    request.content = content
    return func(request, *args, **kwds)

  return image_wrapper


def json_response(func):
  """Decorator that converts into JSON any returned value that is not an
  HttpResponse. It handles `pretty` URL parameter to tune JSON response for
  either performance or readability."""

  def json_wrapper(request, *args, **kwds):
    data = func(request, *args, **kwds)
    if isinstance(data, HttpResponse):
      return data
    if request.REQUEST.get('pretty','0').lower() in ('1', 'true', 'on'):
      data = simplejson.dumps(data, indent='  ', sort_keys=True)
    else:
      data = simplejson.dumps(data, separators=(',',':'))
    return HttpResponse(data, content_type='application/json')

  return json_wrapper


### Request handlers ###


def index(request):
  """/ - Show a list of patches."""
  if request.user is None:
    return all(request)
  else:
    return mine(request)


DEFAULT_LIMIT = 10


def _url(path, **kwargs):
  """Format parameters for query string.

  Args:
    path: Path of URL.
    kwargs: Keyword parameters are treated as values to add to the query
      parameter of the URL.  If empty no query parameters will be added to
      path and '?' omitted from the URL.
  """
  if kwargs:
    encoded_parameters = urllib.urlencode(kwargs)
    if path.endswith('?'):
      # Trailing ? on path.  Append parameters to end.
      return '%s%s' % (path, encoded_parameters)
    elif '?' in path:
      # Append additional parameters to existing query parameters.
      return '%s&%s' % (path, encoded_parameters)
    else:
      # Add query parameters to path with no query parameters.
      return '%s?%s' % (path, encoded_parameters)
  else:
    return path


def _inner_paginate(request, issues, template, extra_template_params):
  """Display paginated list of issues.

  Takes care of the private bit.

  Args:
    request: Request containing offset and limit parameters.
    issues: Issues to be displayed.
    template: Name of template that renders issue page.
    extra_template_params: Dictionary of extra parameters to pass to page
      rendering.

  Returns:
    Response for sending back to browser.
  """
  visible_issues = [i for i in issues if _can_view_issue(request.user, i)]
  _optimize_draft_counts(visible_issues)
  _load_users_for_issues(visible_issues)
  params = {
    'issues': visible_issues,
    'limit': None,
    'newest': None,
    'prev': None,
    'next': None,
    'nexttext': '',
    'first': '',
    'last': '',
  }
  if extra_template_params:
    params.update(extra_template_params)
  return respond(request, template, params)


def _paginate_issues(page_url,
                     request,
                     query,
                     template,
                     extra_nav_parameters=None,
                     extra_template_params=None):
  """Display paginated list of issues.

  Args:
    page_url: Base URL of issue page that is being paginated.  Typically
      generated by calling 'reverse' with a name and arguments of a view
      function.
    request: Request containing offset and limit parameters.
    query: Query over issues.
    template: Name of template that renders issue page.
    extra_nav_parameters: Dictionary of extra parameters to append to the
      navigation links.
    extra_template_params: Dictionary of extra parameters to pass to page
      rendering.

  Returns:
    Response for sending back to browser.
  """
  offset = _clean_int(request.GET.get('offset'), 0, 0)
  limit = _clean_int(request.GET.get('limit'), DEFAULT_LIMIT, 1, 100)

  nav_parameters = {'limit': str(limit)}
  if extra_nav_parameters is not None:
    nav_parameters.update(extra_nav_parameters)

  params = {
    'limit': limit,
    'first': offset + 1,
    'nexttext': 'Older',
  }
  # Fetch one more to see if there should be a 'next' link
  issues = query.fetch(limit+1, offset)
  if len(issues) > limit:
    del issues[limit:]
    params['next'] = _url(page_url, offset=offset + limit, **nav_parameters)
  params['last'] = len(issues) > 1 and offset+len(issues) or None
  if offset > 0:
    params['prev'] = _url(page_url, offset=max(0, offset - limit),
        **nav_parameters)
  if offset > limit:
    params['newest'] = _url(page_url, **nav_parameters)
  if extra_template_params:
    params.update(extra_template_params)
  return _inner_paginate(request, issues, template, params)


def _paginate_issues_with_cursor(page_url,
                                 request,
                                 query,
                                 limit,
                                 template,
                                 extra_nav_parameters=None,
                                 extra_template_params=None):
  """Display paginated list of issues using a cursor instead of offset.

  Args:
    page_url: Base URL of issue page that is being paginated.  Typically
      generated by calling 'reverse' with a name and arguments of a view
      function.
    request: Request containing offset and limit parameters.
    query: Query over issues.
    limit: Maximum number of issues to return.
    template: Name of template that renders issue page.
    extra_nav_parameters: Dictionary of extra parameters to append to the
      navigation links.
    extra_template_params: Dictionary of extra parameters to pass to page
      rendering.

  Returns:
    Response for sending back to browser.
  """
  issues = query.fetch(limit)
  nav_parameters = {}
  if extra_nav_parameters:
    nav_parameters.update(extra_nav_parameters)
  nav_parameters['cursor'] = query.cursor()

  params = {
    'limit': limit,
    'cursor': nav_parameters['cursor'],
    'nexttext': 'Newer',
  }
  # Fetch one more to see if there should be a 'next' link. Do it in a separate
  # request so we have a valid cursor.
  if query.fetch(1):
    params['next'] = _url(page_url, **nav_parameters)
  if extra_template_params:
    params.update(extra_template_params)
  return _inner_paginate(request, issues, template, params)


def all(request):
  """/all - Show a list of up to DEFAULT_LIMIT recent issues."""
  closed = request.GET.get('closed') or ''
  nav_parameters = {}
  if closed:
    nav_parameters['closed'] = '1'

  if closed:
    query = db.GqlQuery('SELECT * FROM Issue '
                        'WHERE private = FALSE '
                        'ORDER BY modified DESC')
  else:
    query = db.GqlQuery('SELECT * FROM Issue '
                        'WHERE closed = FALSE AND private = FALSE '
                        'ORDER BY modified DESC')

  return _paginate_issues(reverse(all),
                          request,
                          query,
                          'all.html',
                          extra_nav_parameters=nav_parameters,
                          extra_template_params=dict(closed=closed))


def _optimize_draft_counts(issues):
  """Force _num_drafts to zero for issues that are known to have no drafts.

  Args:
    issues: list of model.Issue instances.

  This inspects the drafts attribute of the current user's Account
  instance, and forces the draft count to zero of those issues in the
  list that aren't mentioned there.

  If there is no current user, all draft counts are forced to 0.
  """
  account = models.Account.current_user_account
  if account is None:
    issue_ids = None
  else:
    issue_ids = account.drafts
  for issue in issues:
    if issue_ids is None or issue.key().id() not in issue_ids:
      issue._num_drafts = 0


@login_required
def mine(request):
  """/mine - Show a list of issues created by the current user."""
  request.user_to_show = request.user
  return _show_user(request)


@login_required
def starred(request):
  """/starred - Show a list of issues starred by the current user."""
  stars = models.Account.current_user_account.stars
  if not stars:
    issues = []
  else:
    issues = [issue for issue in models.Issue.get_by_id(stars)
                    if issue is not None
                    and _can_view_issue(request.user, issue)]
    _load_users_for_issues(issues)
    _optimize_draft_counts(issues)
  return respond(request, 'starred.html', {'issues': issues})

def _load_users_for_issues(issues):
  """Load all user links for a list of issues in one go."""
  user_dict = {}
  for i in issues:
    for e in i.reviewers + i.cc + [i.owner.email()]:
      # keeping a count lets you track total vs. distinct if you want
      user_dict[e] = user_dict.setdefault(e, 0) + 1

  library.get_links_for_users(user_dict.keys())

@user_key_required
def show_user(request):
  """/user - Show the user's dashboard"""
  return _show_user(request)


def _show_user(request):
  user = request.user_to_show
  if user == request.user:
    query = models.Comment.all().filter('draft =', True)
    query = query.filter('author =', request.user).fetch(100)
    draft_keys = set(d.parent_key().parent().parent() for d in query)
    draft_issues = models.Issue.get(draft_keys)
  else:
    draft_issues = draft_keys = []
  my_issues = [
      issue for issue in db.GqlQuery(
          'SELECT * FROM Issue '
          'WHERE closed = FALSE AND owner = :1 '
          'ORDER BY modified DESC '
          'LIMIT 100',
          user)
      if issue.key() not in draft_keys and _can_view_issue(request.user, issue)]
  review_issues = [
      issue for issue in db.GqlQuery(
          'SELECT * FROM Issue '
          'WHERE closed = FALSE AND reviewers = :1 '
          'ORDER BY modified DESC '
          'LIMIT 100',
          user.email().lower())
      if (issue.key() not in draft_keys and issue.owner != user
          and _can_view_issue(request.user, issue))]
  closed_issues = [
      issue for issue in db.GqlQuery(
          'SELECT * FROM Issue '
          'WHERE closed = TRUE AND modified > :1 AND owner = :2 '
          'ORDER BY modified DESC '
          'LIMIT 100',
          datetime.datetime.now() - datetime.timedelta(days=7),
          user)
      if issue.key() not in draft_keys and _can_view_issue(request.user, issue)]
  cc_issues = [
      issue for issue in db.GqlQuery(
          'SELECT * FROM Issue '
          'WHERE closed = FALSE AND cc = :1 '
          'ORDER BY modified DESC '
          'LIMIT 100',
          user.email())
      if (issue.key() not in draft_keys and issue.owner != user
          and _can_view_issue(request.user, issue))]
  all_issues = my_issues + review_issues + closed_issues + cc_issues
  _load_users_for_issues(all_issues)
  _optimize_draft_counts(all_issues)
  return respond(request, 'user.html',
                 {'email': user.email(),
                  'my_issues': my_issues,
                  'review_issues': review_issues,
                  'closed_issues': closed_issues,
                  'cc_issues': cc_issues,
                  'draft_issues': draft_issues,
                  })


@login_required
@xsrf_required
def new(request):
  """/new - Upload a new patch set.

  GET shows a blank form, POST processes it.
  """
  if request.method != 'POST':
    form = NewForm()
    form.set_branch_choices()
    return respond(request, 'new.html', {'form': form})

  form = NewForm(request.POST, request.FILES)
  form.set_branch_choices()
  issue = _make_new(request, form)
  if issue is None:
    return respond(request, 'new.html', {'form': form})
  else:
    return HttpResponseRedirect(reverse(show, args=[issue.key().id()]))


@login_required
@xsrf_required
def use_uploadpy(request):
  """Show an intermediate page about upload.py."""
  if request.method == 'POST':
    if 'disable_msg' in request.POST:
      models.Account.current_user_account.uploadpy_hint = False
      models.Account.current_user_account.put()
    if 'download' in request.POST:
      url = reverse(customized_upload_py)
    else:
      url = reverse(new)
    return HttpResponseRedirect(url)
  return respond(request, 'use_uploadpy.html')


@post_required
@upload_required
def upload(request):
  """/upload - Like new() or add(), but from the upload.py script.

  This generates a text/plain response.
  """
  if request.user is None:
    if IS_DEV:
      request.user = users.User(request.POST.get('user', 'test@example.com'))
    else:
      return HttpResponse('Login required', status=401)
  # Check against old upload.py usage.
  if request.POST.get('num_parts') > 1:
    return HttpResponse('Upload.py is too old, get the latest version.',
                        content_type='text/plain')
  form = UploadForm(request.POST, request.FILES)
  issue = None
  patchset = None
  if form.is_valid():
    issue_id = form.cleaned_data['issue']
    if issue_id:
      action = 'updated'
      issue = models.Issue.get_by_id(issue_id)
      if issue is None:
        form.errors['issue'] = ['No issue exists with that id (%s)' %
                                issue_id]
      elif issue.local_base and not form.cleaned_data.get('content_upload'):
        form.errors['issue'] = ['Base files upload required for that issue.']
        issue = None
      else:
        if request.user != issue.owner:
          form.errors['user'] = ['You (%s) don\'t own this issue (%s)' %
                                 (request.user, issue_id)]
          issue = None
        else:
          patchset = _add_patchset_from_form(request, issue, form, 'subject',
                                             emails_add_only=True)
          if not patchset:
            issue = None
    else:
      action = 'created'
      issue = _make_new(request, form)
      if issue is not None:
        patchset = issue.patchset
  if issue is None:
    msg = 'Issue creation errors: %s' % repr(form.errors)
  else:
    msg = ('Issue %s. URL: %s' %
           (action,
            request.build_absolute_uri(
              reverse('show_bare_issue_number', args=[issue.key().id()]))))
    if (form.cleaned_data.get('content_upload') or
        form.cleaned_data.get('separate_patches')):
      # Extend the response message: 2nd line is patchset id.
      msg +="\n%d" % patchset.key().id()
      if form.cleaned_data.get('content_upload'):
        # Extend the response: additional lines are the expected filenames.
        issue.local_base = True
        issue.put()

        base_hashes = {}
        for file_info in form.cleaned_data.get('base_hashes').split("|"):
          if not file_info:
            break
          checksum, filename = file_info.split(":", 1)
          base_hashes[filename] = checksum

        content_entities = []
        new_content_entities = []
        patches = list(patchset.patch_set)
        existing_patches = {}
        patchsets = list(issue.patchset_set)
        if len(patchsets) > 1:
          # Only check the last uploaded patchset for speed.
          last_patch_set = patchsets[-2].patch_set
          patchsets = None  # Reduce memory usage.
          for opatch in last_patch_set:
            if opatch.content:
              existing_patches[opatch.filename] = opatch
        for patch in patches:
          content = None
          # Check if the base file is already uploaded in another patchset.
          if (patch.filename in base_hashes and
              patch.filename in existing_patches and
              (base_hashes[patch.filename] ==
               existing_patches[patch.filename].content.checksum)):
            content = existing_patches[patch.filename].content
            patch.status = existing_patches[patch.filename].status
            patch.is_binary = existing_patches[patch.filename].is_binary
          if not content:
            content = models.Content(is_uploaded=True, parent=patch)
            new_content_entities.append(content)
          content_entities.append(content)
        existing_patches = None  # Reduce memory usage.
        if new_content_entities:
          db.put(new_content_entities)

        for patch, content_entity in zip(patches, content_entities):
          patch.content = content_entity
          id_string = patch.key().id()
          if content_entity not in new_content_entities:
            # Base file not needed since we reused a previous upload.  Send its
            # patch id in case it's a binary file and the new content needs to
            # be uploaded.  We mark this by prepending 'nobase' to the id.
            id_string = "nobase_" + str(id_string)
          msg += "\n%s %s" % (id_string, patch.filename)
        db.put(patches)
  return HttpResponse(msg, content_type='text/plain')


@post_required
@patch_required
@upload_required
def upload_content(request):
  """/<issue>/upload_content/<patchset>/<patch> - Upload base file contents.

  Used by upload.py to upload base files.
  """
  form = UploadContentForm(request.POST, request.FILES)
  if not form.is_valid():
    return HttpResponse('ERROR: Upload content errors:\n%s' % repr(form.errors),
                        content_type='text/plain')
  if request.user is None:
    if IS_DEV:
      request.user = users.User(request.POST.get('user', 'test@example.com'))
    else:
      return HttpResponse('Error: Login required', status=401)
  if request.user != request.issue.owner:
    return HttpResponse('ERROR: You (%s) don\'t own this issue (%s).' %
                        (request.user, request.issue.key().id()))
  patch = request.patch
  patch.status = form.cleaned_data['status']
  patch.is_binary = form.cleaned_data['is_binary']
  patch.put()

  if form.cleaned_data['is_current']:
    if patch.patched_content:
      return HttpResponse('ERROR: Already have current content.')
    content = models.Content(is_uploaded=True, parent=patch)
    content.put()
    patch.patched_content = content
    patch.put()
  else:
    content = patch.content

  if form.cleaned_data['file_too_large']:
    content.file_too_large = True
  else:
    data = form.get_uploaded_content()
    checksum = md5.new(data).hexdigest()
    if checksum != request.POST.get('checksum'):
      content.is_bad = True
      content.put()
      return HttpResponse('ERROR: Checksum mismatch.',
                          content_type='text/plain')
    if patch.is_binary:
      content.data = data
    else:
      content.text = engine.ToText(engine.UnifyLinebreaks(data))
    content.checksum = checksum
  content.put()
  return HttpResponse('OK', content_type='text/plain')


@post_required
@patchset_required
@upload_required
def upload_patch(request):
  """/<issue>/upload_patch/<patchset> - Upload patch to patchset.

  Used by upload.py to upload a patch when the diff is too large to upload all
  together.
  """
  if request.user is None:
    if IS_DEV:
      request.user = users.User(request.POST.get('user', 'test@example.com'))
    else:
      return HttpResponse('Error: Login required', status=401)
  if request.user != request.issue.owner:
    return HttpResponse('ERROR: You (%s) don\'t own this issue (%s).' %
                        (request.user, request.issue.key().id()))
  form = UploadPatchForm(request.POST, request.FILES)
  if not form.is_valid():
    return HttpResponse('ERROR: Upload patch errors:\n%s' % repr(form.errors),
                        content_type='text/plain')
  patchset = request.patchset
  if patchset.data:
    return HttpResponse('ERROR: Can\'t upload patches to patchset with data.',
                        content_type='text/plain')
  text = engine.ToText(engine.UnifyLinebreaks(form.get_uploaded_patch()))
  patch = models.Patch(patchset=patchset,
                       text=text,
                       filename=form.cleaned_data['filename'], parent=patchset)
  patch.put()
  if form.cleaned_data.get('content_upload'):
    content = models.Content(is_uploaded=True, parent=patch)
    content.put()
    patch.content = content
    patch.put()

  msg = 'OK\n' + str(patch.key().id())
  return HttpResponse(msg, content_type='text/plain')


class EmptyPatchSet(Exception):
  """Exception used inside _make_new() to break out of the transaction."""


def _make_new(request, form):
  """Helper for new().

  Return a valid Issue, or None.
  """
  if not form.is_valid():
    return None

  data_url = _get_data_url(form)
  if data_url is None:
    return None
  data, url, separate_patches = data_url

  reviewers = _get_emails(form, 'reviewers')
  if not form.is_valid() or reviewers is None:
    return None

  cc = _get_emails(form, 'cc')
  if not form.is_valid():
    return None

  base = form.get_base()
  if base is None:
    return None

  def txn():
    issue = models.Issue(subject=form.cleaned_data['subject'],
                         description=form.cleaned_data['description'],
                         base=base,
                         reviewers=reviewers,
                         cc=cc,
                         private=form.cleaned_data.get('private', False),
                         n_comments=0)
    issue.put()

    patchset = models.PatchSet(issue=issue, data=data, url=url, parent=issue)
    patchset.put()
    issue.patchset = patchset

    if not separate_patches:
      patches = engine.ParsePatchSet(patchset)
      if not patches:
        raise EmptyPatchSet  # Abort the transaction
      db.put(patches)
    return issue

  try:
    issue = db.run_in_transaction(txn)
  except EmptyPatchSet:
    errkey = url and 'url' or 'data'
    form.errors[errkey] = ['Patch set contains no recognizable patches']
    return None

  if form.cleaned_data.get('send_mail'):
    msg = _make_message(request, issue, '', '', True)
    msg.put()
    _notify_issue(request, issue, 'Created')
  return issue


def _get_data_url(form):
  """Helper for _make_new() above and add() below.

  Args:
    form: Django form object.

  Returns:
    3-tuple (data, url, separate_patches).
      data: the diff content, if available.
      url: the url of the diff, if given.
      separate_patches: True iff the patches will be uploaded separately for
        each file.

  """
  cleaned_data = form.cleaned_data

  data = cleaned_data['data']
  url = cleaned_data.get('url')
  separate_patches = cleaned_data.get('separate_patches')
  if not (data or url or separate_patches):
    form.errors['data'] = ['You must specify a URL or upload a file (< 1 MB).']
    return None
  if data and url:
    form.errors['data'] = ['You must specify either a URL or upload a file '
                           'but not both.']
    return None
  if separate_patches and (data or url):
    form.errors['data'] = ['If the patches will be uploaded separately later, '
                           'you can\'t send some data or a url.']
    return None

  if data is not None:
    data = db.Blob(engine.UnifyLinebreaks(data.read()))
    url = None
  elif url:
    try:
      fetch_result = urlfetch.fetch(url)
    except Exception, err:
      form.errors['url'] = [str(err)]
      return None
    if fetch_result.status_code != 200:
      form.errors['url'] = ['HTTP status code %s' % fetch_result.status_code]
      return None
    data = db.Blob(engine.UnifyLinebreaks(fetch_result.content))

  return data, url, separate_patches


@post_required
@issue_owner_required
@xsrf_required
def add(request):
  """/<issue>/add - Add a new PatchSet to an existing Issue."""
  issue = request.issue
  form = AddForm(request.POST, request.FILES)
  if not _add_patchset_from_form(request, issue, form):
    return show(request, issue.key().id(), form)
  return HttpResponseRedirect(reverse(show, args=[issue.key().id()]))


def _add_patchset_from_form(request, issue, form, message_key='message',
                            emails_add_only=False):
  """Helper for add() and upload()."""
  # TODO(guido): use a transaction like in _make_new(); may be share more code?
  if form.is_valid():
    data_url = _get_data_url(form)
  if not form.is_valid():
    return None
  if request.user != issue.owner:
    # This check is done at each call site but check again as a safety measure.
    return None
  data, url, separate_patches = data_url
  message = form.cleaned_data[message_key]
  patchset = models.PatchSet(issue=issue, message=message, data=data, url=url,
                             parent=issue)
  patchset.put()

  if not separate_patches:
    patches = engine.ParsePatchSet(patchset)
    if not patches:
      patchset.delete()
      errkey = url and 'url' or 'data'
      form.errors[errkey] = ['Patch set contains no recognizable patches']
      return None
    db.put(patches)

  if emails_add_only:
    emails = _get_emails(form, 'reviewers')
    if not form.is_valid():
      return None
    issue.reviewers += [reviewer for reviewer in emails
                        if reviewer not in issue.reviewers]
    emails = _get_emails(form, 'cc')
    if not form.is_valid():
      return None
    issue.cc += [cc for cc in emails if cc not in issue.cc]
  else:
    issue.reviewers = _get_emails(form, 'reviewers')
    issue.cc = _get_emails(form, 'cc')
  issue.put()

  if form.cleaned_data.get('send_mail'):
    msg = _make_message(request, issue, message, '', True)
    msg.put()
    _notify_issue(request, issue, 'Updated')
  return patchset


def _get_emails(form, label):
  """Helper to return the list of reviewers, or None for error."""
  raw_emails = form.cleaned_data.get(label)
  if raw_emails:
    return _get_emails_from_raw(raw_emails.split(','), form=form, label=label)
  return []

def _get_emails_from_raw(raw_emails, form=None, label=None):
  emails = []
  for email in raw_emails:
    email = email.strip()
    if email:
      try:
        if '@' not in email:
          account = models.Account.get_account_for_nickname(email)
          if account is None:
            raise db.BadValueError('Unknown user: %s' % email)
          db_email = db.Email(account.user.email().lower())
        elif email.count('@') != 1:
          raise db.BadValueError('Invalid email address: %s' % email)
        else:
          head, tail = email.split('@')
          if '.' not in tail:
            raise db.BadValueError('Invalid email address: %s' % email)
          db_email = db.Email(email.lower())
      except db.BadValueError, err:
        if form:
          form.errors[label] = [unicode(err)]
        return None
      if db_email not in emails:
        emails.append(db_email)
  return emails


def _calculate_delta(patch, patchset_id, patchsets):
  """Calculates which files in earlier patchsets this file differs from.

  Args:
    patch: The file to compare.
    patchset_id: The file's patchset's key id.
    patchsets: A list of existing patchsets.

  Returns:
    A list of patchset ids.
  """
  delta = []
  if patch.no_base_file:
    return delta
  for other in patchsets:
    if patchset_id == other.key().id():
      break
    if other.data or other.parsed_patches:
      # Loading all the Patch entities in every PatchSet takes too long
      # (DeadLineExceeded) and consumes a lot of memory (MemoryError) so instead
      # just parse the patchset's data.  Note we can only do this if the
      # patchset was small enough to fit in the data property.
      if other.parsed_patches is None:
        # PatchSet.data is stored as db.Blob (str). Try to convert it
        # to unicode so that Python doesn't need to do this conversion
        # when comparing text and patch.text, which is db.Text
        # (unicode).
        try:
          other.parsed_patches = engine.SplitPatch(other.data.decode('utf-8'))
        except UnicodeDecodeError:  # Fallback to str - unicode comparison.
          other.parsed_patches = engine.SplitPatch(other.data)
        other.data = None  # Reduce memory usage.
      for filename, text in other.parsed_patches:
        if filename == patch.filename:
          if text != patch.text:
            delta.append(other.key().id())
          break
      else:
        # We could not find the file in the previous patchset. It must
        # be new wrt that patchset.
        delta.append(other.key().id())
    else:
      # other (patchset) is too big to hold all the patches inside itself, so
      # we need to go to the datastore.  Use the index to see if there's a
      # patch against our current file in other.
      query = models.Patch.all()
      query.filter("filename =", patch.filename)
      query.filter("patchset =", other.key())
      other_patches = query.fetch(100)
      if other_patches and len(other_patches) > 1:
        logging.info("Got %s patches with the same filename for a patchset",
                     len(other_patches))
      for op in other_patches:
        if op.text != patch.text:
          delta.append(other.key().id())
          break
      else:
        # We could not find the file in the previous patchset. It must
        # be new wrt that patchset.
        delta.append(other.key().id())

  return delta


def _get_patchset_info(request, patchset_id):
  """ Returns a list of patchsets for the issue.

  Args:
    request: Django Request object.
    patchset_id: The id of the patchset that the caller is interested in.  This
      is the one that we generate delta links to if they're not available.  We
      can't generate for all patchsets because it would take too long on issues
      with many patchsets.  Passing in None is equivalent to doing it for the
      last patchset.

  Returns:
    A 3-tuple of (issue, patchsets, HttpResponse).
    If HttpResponse is not None, further processing should stop and it should be
    returned.
  """
  issue = request.issue
  patchsets = list(issue.patchset_set.order('created'))
  response = None
  if not patchset_id and patchsets:
    patchset_id = patchsets[-1].key().id()

  if request.user:
    drafts = list(models.Comment.gql('WHERE ANCESTOR IS :1 AND draft = TRUE'
                                     '  AND author = :2',
                                     issue, request.user))
  else:
    drafts = []
  comments = list(models.Comment.gql('WHERE ANCESTOR IS :1 AND draft = FALSE',
                                     issue))
  issue.draft_count = len(drafts)
  for c in drafts:
    c.ps_key = c.patch.patchset.key()
  patchset_id_mapping = {}  # Maps from patchset id to its ordering number.
  for patchset in patchsets:
    patchset_id_mapping[patchset.key().id()] = len(patchset_id_mapping) + 1
    patchset.n_drafts = sum(c.ps_key == patchset.key() for c in drafts)
    patchset.patches = None
    patchset.parsed_patches = None
    if patchset_id == patchset.key().id():
      patchset.patches = list(patchset.patch_set.order('filename'))
      try:
        attempt = _clean_int(request.GET.get('attempt'), 0, 0)
        if attempt < 0:
          response = HttpResponse('Invalid parameter', status=404)
          break
        for patch in patchset.patches:
          pkey = patch.key()
          patch._num_comments = sum(c.parent_key() == pkey for c in comments)
          patch._num_drafts = sum(c.parent_key() == pkey for c in drafts)
          if not patch.delta_calculated:
            if attempt > 2:
              # Too many patchsets or files and we're not able to generate the
              # delta links.  Instead of giving a 500, try to render the page
              # without them.
              patch.delta = []
            else:
              # Compare each patch to the same file in earlier patchsets to see
              # if they differ, so that we can generate the delta patch urls.
              # We do this once and cache it after.  It's specifically not done
              # on upload because we're already doing too much processing there.
              # NOTE: this function will clear out patchset.data to reduce
              # memory so don't ever call patchset.put() after calling it.
              patch.delta = _calculate_delta(patch, patchset_id, patchsets)
              patch.delta_calculated = True
              # A multi-entity put would be quicker, but it fails when the
              # patches have content that is large.  App Engine throws
              # RequestTooLarge.  This way, although not as efficient, allows
              # multiple refreshes on an issue to get things done, as opposed to
              # an all-or-nothing approach.
              patch.put()
          # Reduce memory usage: if this patchset has lots of added/removed
          # files (i.e. > 100) then we'll get MemoryError when rendering the
          # response.  Each Patch entity is using a lot of memory if the files
          # are large, since it holds the entire contents.  Call num_chunks and
          # num_drafts first though since they depend on text.
          patch.num_chunks
          patch.num_drafts
          patch.num_added
          patch.num_removed
          patch.text = None
          patch._lines = None
          patch.parsed_deltas = []
          for delta in patch.delta:
            patch.parsed_deltas.append([patchset_id_mapping[delta], delta])
      except DeadlineExceededError:
        logging.exception('DeadlineExceededError in _get_patchset_info')
        if attempt > 2:
          response = HttpResponse('DeadlineExceededError - create a new issue.')
        else:
          response = HttpResponseRedirect('%s?attempt=%d' %
                                          (request.path, attempt + 1))
        break
  # Reduce memory usage (see above comment).
  for patchset in patchsets:
    patchset.parsed_patches = None
  return issue, patchsets, response


@issue_required
def show(request, form=None):
  """/<issue> - Show an issue."""
  issue, patchsets, response = _get_patchset_info(request, None)
  if response:
    return response
  if not form:
    form = AddForm(initial={'reviewers': ', '.join(issue.reviewers)})
  last_patchset = first_patch = None
  if patchsets:
    last_patchset = patchsets[-1]
    if last_patchset.patches:
      first_patch = last_patchset.patches[0]
  messages = []
  has_draft_message = False
  for msg in issue.message_set.order('date'):
    if not msg.draft:
      messages.append(msg)
    elif msg.draft and request.user and msg.sender == request.user.email():
      has_draft_message = True
  num_patchsets = len(patchsets)
  return respond(request, 'issue.html',
                 {'issue': issue, 'patchsets': patchsets,
                  'messages': messages, 'form': form,
                  'last_patchset': last_patchset,
                  'num_patchsets': num_patchsets,
                  'first_patch': first_patch,
                  'has_draft_message': has_draft_message,
                  })


@patchset_required
def patchset(request):
  """/patchset/<key> - Returns patchset information."""
  patchset = request.patchset
  issue, patchsets, response = _get_patchset_info(request, patchset.key().id())
  if response:
    return response
  for ps in patchsets:
    if ps.key().id() == patchset.key().id():
      patchset = ps
  return respond(request, 'patchset.html',
                 {'issue': issue,
                  'patchset': patchset,
                  'patchsets': patchsets,
                  })


@login_required
def account(request):
  """/account/?q=blah&limit=10&timestamp=blah - Used for autocomplete."""
  def searchAccounts(property, domain, added, response):
    query = request.GET.get('q').lower()
    limit = _clean_int(request.GET.get('limit'), 10, 10, 100)

    accounts = models.Account.all()
    accounts.filter("lower_%s >= " % property, query)
    accounts.filter("lower_%s < " % property, query + u"\ufffd")
    accounts.order("lower_%s" % property);
    for account in accounts:
      if account.key() in added:
        continue
      if domain and not account.email.endswith(domain):
        continue
      if len(added) >= limit:
        break
      added.add(account.key())
      response += '%s (%s)\n' % (account.email, account.nickname)
    return added, response

  added = set()
  response = ''
  domain = os.environ['AUTH_DOMAIN']
  if domain != 'gmail.com':
    # 'gmail.com' is the value AUTH_DOMAIN is set to if the app is running
    # on appspot.com and shouldn't prioritize the custom domain.
    added, response = searchAccounts("email", domain, added, response)
    added, response = searchAccounts("nickname", domain, added, response)
  added, response = searchAccounts("nickname", "", added, response)
  added, response = searchAccounts("email", "", added, response)
  return HttpResponse(response)


@issue_editor_required
@xsrf_required
def edit(request):
  """/<issue>/edit - Edit an issue."""
  issue = request.issue
  base = issue.base

  if issue.local_base:
    form_cls = EditLocalBaseForm
  else:
    form_cls = EditForm

  if request.method != 'POST':
    reviewers = [models.Account.get_nickname_for_email(reviewer,
                                                       default=reviewer)
                 for reviewer in issue.reviewers]
    ccs = [models.Account.get_nickname_for_email(cc, default=cc)
           for cc in issue.cc]
    form = form_cls(initial={'subject': issue.subject,
                             'description': issue.description,
                             'base': base,
                             'reviewers': ', '.join(reviewers),
                             'cc': ', '.join(ccs),
                             'closed': issue.closed,
                             'private': issue.private,
                             })
    if not issue.local_base:
      form.set_branch_choices(base)
    return respond(request, 'edit.html', {'issue': issue, 'form': form})

  form = form_cls(request.POST)
  if not issue.local_base:
    form.set_branch_choices()

  if form.is_valid():
    reviewers = _get_emails(form, 'reviewers')

  if form.is_valid():
    cc = _get_emails(form, 'cc')

  if form.is_valid() and not issue.local_base:
    base = form.get_base()

  if not form.is_valid():
    return respond(request, 'edit.html', {'issue': issue, 'form': form})
  cleaned_data = form.cleaned_data

  was_closed = issue.closed
  issue.subject = cleaned_data['subject']
  issue.description = cleaned_data['description']
  issue.closed = cleaned_data['closed']
  issue.private = cleaned_data.get('private', False)
  base_changed = (issue.base != base)
  issue.base = base
  issue.reviewers = reviewers
  issue.cc = cc
  if base_changed:
    for patchset in issue.patchset_set:
      db.run_in_transaction(_delete_cached_contents, list(patchset.patch_set))
  issue.put()
  if issue.closed == was_closed:
    message = 'Edited'
  elif issue.closed:
    message = 'Closed'
  else:
    message = 'Reopened'
  _notify_issue(request, issue, message)

  return HttpResponseRedirect(reverse(show, args=[issue.key().id()]))


def _delete_cached_contents(patch_set):
  """Transactional helper for edit() to delete cached contents."""
  # TODO(guido): No need to do this in a transaction.
  patches = []
  contents = []
  for patch in patch_set:
    try:
      content = patch.content
    except db.Error:
      content = None
    try:
      patched_content = patch.patched_content
    except db.Error:
      patched_content = None
    if content is not None:
      contents.append(content)
    if patched_content is not None:
      contents.append(patched_content)
    patch.content = None
    patch.patched_content = None
    patches.append(patch)
  if contents:
    logging.info("Deleting %d contents", len(contents))
    db.delete(contents)
  if patches:
    logging.info("Updating %d patches", len(patches))
    db.put(patches)


@post_required
@issue_owner_required
@xsrf_required
def delete(request):
  """/<issue>/delete - Delete an issue.  There is no way back."""
  issue = request.issue
  tbd = [issue]
  for cls in [models.PatchSet, models.Patch, models.Comment,
              models.Message, models.Content]:
    tbd += cls.gql('WHERE ANCESTOR IS :1', issue)
  db.delete(tbd)
  _notify_issue(request, issue, 'Deleted')
  return HttpResponseRedirect(reverse(mine))


@post_required
@patchset_owner_required
@xsrf_required
def delete_patchset(request):
  """/<issue>/patch/<patchset>/delete - Delete a patchset.

  There is no way back.
  """
  issue = request.issue
  ps_delete = request.patchset
  ps_id = ps_delete.key().id()
  patchsets_after = issue.patchset_set.filter('created >', ps_delete.created)
  patches = []
  for patchset in patchsets_after:
    for patch in patchset.patch_set:
      if patch.delta_calculated:
        if ps_id in patch.delta:
          patches.append(patch)
  db.run_in_transaction(_patchset_delete, ps_delete, patches)
  _notify_issue(request, issue, 'Patchset deleted')
  return HttpResponseRedirect(reverse(show, args=[issue.key().id()]))


def _patchset_delete(ps_delete, patches):
  """Transactional helper for delete_patchset.

  Args:
    ps_delete: The patchset to be deleted.
    patches: Patches that have delta against patches of ps_delete.

  """
  patchset_id = ps_delete.key().id()
  tbp = []
  for patch in patches:
    patch.delta.remove(patchset_id)
    tbp.append(patch)
  if tbp:
    db.put(tbp)
  tbd = [ps_delete]
  for cls in [models.Patch, models.Comment]:
    tbd += cls.gql('WHERE ANCESTOR IS :1', ps_delete)
  db.delete(tbd)


@post_required
@issue_editor_required
@xsrf_required
def close(request):
  """/<issue>/close - Close an issue."""
  issue = request.issue
  issue.closed = True
  if request.method == 'POST':
    new_description = request.POST.get('description')
    if new_description:
      issue.description = new_description
  issue.put()
  _notify_issue(request, issue, 'Closed')
  return HttpResponse('Closed', content_type='text/plain')


@post_required
@issue_required
@upload_required
def mailissue(request):
  """/<issue>/mail - Send mail for an issue.

  Used by upload.py.
  """
  if request.issue.owner != request.user:
    if not IS_DEV:
      return HttpResponse('Login required', status=401)
  issue = request.issue
  msg = _make_message(request, issue, '', '', True)
  msg.put()
  _notify_issue(request, issue, 'Mailed')

  return HttpResponse('OK', content_type='text/plain')


@patchset_required
def download(request):
  """/download/<issue>_<patchset>.diff - Download a patch set."""
  if request.patchset.data is None:
    return HttpResponseNotFound('Patch set (%s) is too large.'
                                % request.patchset.key().id())
  padding = ''
  user_agent = request.META.get('HTTP_USER_AGENT')
  if user_agent and 'MSIE' in user_agent:
    # Add 256+ bytes of padding to prevent XSS attacks on Internet Explorer.
    padding = ('='*67 + '\n') * 4
  return HttpResponse(padding + request.patchset.data,
                      content_type='text/plain')


@issue_required
@upload_required
def description(request):
  """/<issue>/description - Gets/Sets an issue's description.

  Used by upload.py or similar scripts.
  """
  if request.method != 'POST':
    description = request.issue.description or ""
    return HttpResponse(description, content_type='text/plain')
  if not request.issue.user_can_edit(request.user):
    if not IS_DEV:
      return HttpResponse('Login required', status=401)
  issue = request.issue
  issue.description = request.POST.get('description')
  issue.put()
  _notify_issue(request, issue, 'Changed')
  return HttpResponse('')


@issue_required
@upload_required
@json_response
def fields(request):
  """/<issue>/fields - Gets/Sets fields on the issue.

  Used by upload.py or similar scripts for partial updates of the issue
  without a patchset..
  """
  # Only recognizes a few fields for now.
  if request.method != 'POST':
    fields = request.GET.getlist('field')
    response = {}
    if 'reviewers' in fields:
      response['reviewers'] = request.issue.reviewers or []
    if 'description' in fields:
      response['description'] = request.issue.description
    if 'subject' in fields:
      response['subject'] = request.issue.subject
    return response

  if not request.issue.user_can_edit(request.user):
    if not IS_DEV:
      return HttpResponse('Login required', status=401)
  fields = simplejson.loads(request.POST.get('fields'))
  issue = request.issue
  if 'description' in fields:
    issue.description = fields['description']
  if 'reviewers' in fields:
    issue.reviewers = _get_emails_from_raw(fields['reviewers'])
  if 'subject' in fields:
    issue.subject = fields['subject']
  issue.put()
  _notify_issue(request, issue, 'Changed')
  return HttpResponse('')


@patch_required
def patch(request):
  """/<issue>/patch/<patchset>/<patch> - View a raw patch."""
  return patch_helper(request)


def patch_helper(request, nav_type='patch'):
  """Returns a unified diff.

  Args:
    request: Django Request object.
    nav_type: the navigation used in the url (i.e. patch/diff/diff2).  Normally
      the user looks at either unified or side-by-side diffs at one time, going
      through all the files in the same mode.  However, if side-by-side is not
      available for some files, we temporarly switch them to unified view, then
      switch them back when we can.  This way they don't miss any files.

  Returns:
    Whatever respond() returns.
  """
  _add_next_prev(request.patchset, request.patch)
  request.patch.nav_type = nav_type
  parsed_lines = patching.ParsePatchToLines(request.patch.lines)
  if parsed_lines is None:
    return HttpResponseNotFound('Can\'t parse the patch to lines')
  rows = engine.RenderUnifiedTableRows(request, parsed_lines)
  return respond(request, 'patch.html',
                 {'patch': request.patch,
                  'patchset': request.patchset,
                  'view_style': 'patch',
                  'rows': rows,
                  'issue': request.issue,
                  'context': _clean_int(request.GET.get('context'), -1),
                  'column_width': _clean_int(request.GET.get('column_width'),
                                             None),
                  })


@image_required
def image(request):
  """/<issue>/content/<patchset>/<patch>/<content> - Return patch's content."""
  return HttpResponse(request.content.data)


@patch_required
def download_patch(request):
  """/download/issue<issue>_<patchset>_<patch>.diff - Download patch."""
  return HttpResponse(request.patch.text, content_type='text/plain')


def _issue_as_dict(issue, messages, request=None):
  """Converts an issue into a dict."""
  values = {
    'owner': library.get_nickname(issue.owner, True, request),
    'owner_email': issue.owner.email(),
    'modified': str(issue.modified),
    'created': str(issue.created),
    'closed': issue.closed,
    'cc': issue.cc,
    'reviewers': issue.reviewers,
    'patchsets': [p.key().id() for p in issue.patchset_set.order('created')],
    'description': issue.description,
    'subject': issue.subject,
    'issue': issue.key().id(),
    'base_url': issue.base,
    'private': issue.private,
  }
  if messages:
    values['messages'] = [
      {
        'sender': m.sender,
        'recipients': m.recipients,
        'date': str(m.date),
        'text': m.text,
        'approval': m.approval,
      }
      for m in models.Message.gql('WHERE ANCESTOR IS :1', issue)
    ]
  return values


def _patchset_as_dict(patchset, request=None):
  """Converts a patchset into a dict."""
  values = {
    'patchset': patchset.key().id(),
    'issue': patchset.issue.key().id(),
    'owner': library.get_nickname(patchset.issue.owner, True, request),
    'owner_email': patchset.issue.owner.email(),
    'message': patchset.message,
    'url': patchset.url,
    'created': str(patchset.created),
    'modified': str(patchset.modified),
    'num_comments': patchset.num_comments,
    'files': {},
  }
  for patch in models.Patch.gql("WHERE patchset = :1", patchset):
    # num_comments and num_drafts are left out for performance reason:
    # they cause a datastore query on first access. They could be added
    # optionally if the need ever arises.
    values['files'][patch.filename] = {
        'id': patch.key().id(),
        'is_binary': patch.is_binary,
        'no_base_file': patch.no_base_file,
        'num_added': patch.num_added,
        'num_chunks': patch.num_chunks,
        'num_removed': patch.num_removed,
        'status': patch.status,
        'property_changes': '\n'.join(patch.property_changes),
    }
  return values


@issue_required
@json_response
def api_issue(request):
  """/api/<issue> - Gets issue's data as a JSON-encoded dictionary."""
  messages = ('messages' in request.GET and
      request.GET.get('messages').lower() == 'true')
  values = _issue_as_dict(request.issue, messages, request)
  return values


@patchset_required
@json_response
def api_patchset(request):
  """/api/<issue>/<patchset> - Gets an issue's patchset data as a JSON-encoded
  dictionary.
  """
  values = _patchset_as_dict(request.patchset, request)
  return values


def _get_context_for_user(request):
  """Returns the context setting for a user.

  The value is validated against models.CONTEXT_CHOICES.
  If an invalid value is found, the value is overwritten with
  engine.DEFAULT_CONTEXT.
  """
  get_param = request.GET.get('context') or None
  if 'context' in request.GET and get_param is None:
    # User wants to see whole file. No further processing is needed.
    return get_param
  if request.user:
    account = models.Account.current_user_account
    default_context = account.default_context
  else:
    default_context = engine.DEFAULT_CONTEXT
  context = _clean_int(get_param, default_context)
  if context is not None and context not in models.CONTEXT_CHOICES:
    context = engine.DEFAULT_CONTEXT
  return context

def _get_column_width_for_user(request):
  """Returns the column width setting for a user."""
  if request.user:
    account = models.Account.current_user_account
    default_column_width = account.default_column_width
  else:
    default_column_width = engine.DEFAULT_COLUMN_WIDTH
  column_width = _clean_int(request.GET.get('column_width'),
                            default_column_width,
                            engine.MIN_COLUMN_WIDTH, engine.MAX_COLUMN_WIDTH)
  return column_width


@patch_filename_required
def diff(request):
  """/<issue>/diff/<patchset>/<patch> - View a patch as a side-by-side diff"""
  if request.patch.no_base_file:
    # Can't show side-by-side diff since we don't have the base file.  Show the
    # unified diff instead.
    return patch_helper(request, 'diff')

  patchset = request.patchset
  patch = request.patch

  patchsets = list(request.issue.patchset_set.order('created'))

  context = _get_context_for_user(request)
  column_width = _get_column_width_for_user(request)
  if patch.is_binary:
    rows = None
  else:
    try:
      rows = _get_diff_table_rows(request, patch, context, column_width)
    except engine.FetchError, err:
      return HttpResponseNotFound(str(err))

  _add_next_prev(patchset, patch)
  return respond(request, 'diff.html',
                 {'issue': request.issue,
                  'patchset': patchset,
                  'patch': patch,
                  'view_style': 'diff',
                  'rows': rows,
                  'context': context,
                  'context_values': models.CONTEXT_CHOICES,
                  'column_width': column_width,
                  'patchsets': patchsets,
                  })


def _get_diff_table_rows(request, patch, context, column_width):
  """Helper function that returns rendered rows for a patch.

  Raises:
    engine.FetchError if patch parsing or download of base files fails.
  """
  chunks = patching.ParsePatchToChunks(patch.lines, patch.filename)
  if chunks is None:
    raise engine.FetchError('Can\'t parse the patch to chunks')

  # Possible engine.FetchErrors are handled in diff() and diff_skipped_lines().
  content = request.patch.get_content()

  rows = list(engine.RenderDiffTableRows(request, content.lines,
                                         chunks, patch,
                                         context=context,
                                         colwidth=column_width))
  if rows and rows[-1] is None:
    del rows[-1]
    # Get rid of content, which may be bad
    if content.is_uploaded and content.text != None:
      # Don't delete uploaded content, otherwise get_content()
      # will fetch it.
      content.is_bad = True
      content.text = None
      content.put()
    else:
      content.delete()
      request.patch.content = None
      request.patch.put()

  return rows


@patch_required
@json_response
def diff_skipped_lines(request, id_before, id_after, where, column_width):
  """/<issue>/diff/<patchset>/<patch> - Returns a fragment of skipped lines.

  *where* indicates which lines should be expanded:
    'b' - move marker line to bottom and expand above
    't' - move marker line to top and expand below
    'a' - expand all skipped lines
  """
  patchset = request.patchset
  patch = request.patch
  if where == 'a':
    context = None
  else:
    context = _get_context_for_user(request) or 100

  column_width = _clean_int(column_width, engine.DEFAULT_COLUMN_WIDTH,
                            engine.MIN_COLUMN_WIDTH, engine.MAX_COLUMN_WIDTH)

  try:
    rows = _get_diff_table_rows(request, patch, None, column_width)
  except engine.FetchError, err:
    return HttpResponse('Error: %s; please report!' % err, status=500)
  return _get_skipped_lines_response(rows, id_before, id_after, where, context)


# there's no easy way to put a control character into a regex, so brute-force it
# this is all control characters except \r, \n, and \t
_badchars_re = re.compile(r'[\000\001\002\003\004\005\006\007\010\013\014\016\017\020\021\022\023\024\025\026\027\030\031\032\033\034\035\036\037]')


def _strip_invalid_xml(s):
  """Remove control chars other than \r\n\t from a string to be put in XML."""
  if _badchars_re.search(s):
    return ''.join(c for c in s if c >= ' ' or c in '\r\n\t')
  else:
    return s


def _get_skipped_lines_response(rows, id_before, id_after, where, context):
  """Helper function that returns response data for skipped lines"""
  response_rows = []
  id_before_start = int(id_before)
  id_after_end = int(id_after)
  if context is not None:
    id_before_end = id_before_start+context
    id_after_start = id_after_end-context
  else:
    id_before_end = id_after_start = None

  for row in rows:
    m = re.match('^<tr( name="hook")? id="pair-(?P<rowcount>\d+)">', row)
    if m:
      curr_id = int(m.groupdict().get("rowcount"))
      # expand below marker line
      if (where == 'b'
          and curr_id > id_after_start and curr_id <= id_after_end):
        response_rows.append(row)
      # expand above marker line
      elif (where == 't'
            and curr_id >= id_before_start and curr_id < id_before_end):
        response_rows.append(row)
      # expand all skipped lines
      elif (where == 'a'
            and curr_id >= id_before_start and curr_id <= id_after_end):
        response_rows.append(row)
      if context is not None and len(response_rows) >= 2*context:
        break

  # Create a usable structure for the JS part
  response = []
  response_rows =  [_strip_invalid_xml(r) for r in response_rows]
  dom = ElementTree.parse(StringIO('<div>%s</div>' % "".join(response_rows)))
  for node in dom.getroot().getchildren():
    content = [[x.items(), x.text] for x in node.getchildren()]
    response.append([node.items(), content])
  return response


def _get_diff2_data(request, ps_left_id, ps_right_id, patch_id, context,
                    column_width, patch_filename=None):
  """Helper function that returns objects for diff2 views"""
  ps_left = models.PatchSet.get_by_id(int(ps_left_id), parent=request.issue)
  if ps_left is None:
    return HttpResponseNotFound('No patch set exists with that id (%s)' %
                                ps_left_id)
  ps_left.issue = request.issue
  ps_right = models.PatchSet.get_by_id(int(ps_right_id), parent=request.issue)
  if ps_right is None:
    return HttpResponseNotFound('No patch set exists with that id (%s)' %
                                ps_right_id)
  ps_right.issue = request.issue
  if patch_id is not None:
    patch_right = models.Patch.get_by_id(int(patch_id), parent=ps_right)
  else:
    patch_right = None
  if patch_right is not None:
    patch_right.patchset = ps_right
    if patch_filename is None:
      patch_filename = patch_right.filename
  # Now find the corresponding patch in ps_left
  patch_left = models.Patch.gql('WHERE patchset = :1 AND filename = :2',
                                ps_left, patch_filename).get()

  if patch_left:
    try:
      new_content_left = patch_left.get_patched_content()
    except engine.FetchError, err:
      return HttpResponseNotFound(str(err))
    lines_left = new_content_left.lines
  elif patch_right:
    lines_left = patch_right.get_content().lines
  else:
    lines_left = []

  if patch_right:
    try:
      new_content_right = patch_right.get_patched_content()
    except engine.FetchError, err:
      return HttpResponseNotFound(str(err))
    lines_right = new_content_right.lines
  elif patch_left:
    lines_right = patch_left.get_content().lines
  else:
    lines_right = []

  rows = engine.RenderDiff2TableRows(request,
                                     lines_left, patch_left,
                                     lines_right, patch_right,
                                     context=context,
                                     colwidth=column_width)
  rows = list(rows)
  if rows and rows[-1] is None:
    del rows[-1]

  return dict(patch_left=patch_left, patch_right=patch_right,
              ps_left=ps_left, ps_right=ps_right, rows=rows)


@issue_required
def diff2(request, ps_left_id, ps_right_id, patch_filename):
  """/<issue>/diff2/... - View the delta between two different patch sets."""
  context = _get_context_for_user(request)
  column_width = _get_column_width_for_user(request)

  ps_right = models.PatchSet.get_by_id(int(ps_right_id), parent=request.issue)
  patch_right = None

  if ps_right:
    patch_right = models.Patch.gql('WHERE patchset = :1 AND filename = :2',
                                   ps_right, patch_filename).get()

  if patch_right:
    patch_id = patch_right.key().id()
  elif patch_filename.isdigit():
    # Perhaps it's an ID that's passed in, based on the old URL scheme.
    patch_id = int(patch_filename)
  else:  # patch doesn't exist in this patchset
    patch_id = None

  data = _get_diff2_data(request, ps_left_id, ps_right_id, patch_id, context,
                         column_width, patch_filename)
  if isinstance(data, HttpResponseNotFound):
    return data

  patchsets = list(request.issue.patchset_set.order('created'))

  if data["patch_right"]:
    _add_next_prev2(data["ps_left"], data["ps_right"], data["patch_right"])
  return respond(request, 'diff2.html',
                 {'issue': request.issue,
                  'ps_left': data["ps_left"],
                  'patch_left': data["patch_left"],
                  'ps_right': data["ps_right"],
                  'patch_right': data["patch_right"],
                  'rows': data["rows"],
                  'patch_id': patch_id,
                  'context': context,
                  'context_values': models.CONTEXT_CHOICES,
                  'column_width': column_width,
                  'patchsets': patchsets,
                  'filename': patch_filename,
                  })


@issue_required
@json_response
def diff2_skipped_lines(request, ps_left_id, ps_right_id, patch_id,
                        id_before, id_after, where, column_width):
  """/<issue>/diff2/... - Returns a fragment of skipped lines"""
  column_width = _clean_int(column_width, engine.DEFAULT_COLUMN_WIDTH,
                            engine.MIN_COLUMN_WIDTH, engine.MAX_COLUMN_WIDTH)

  if where == 'a':
    context = None
  else:
    context = _get_context_for_user(request) or 100

  data = _get_diff2_data(request, ps_left_id, ps_right_id, patch_id, 10000,
                         column_width)
  if isinstance(data, HttpResponseNotFound):
    return data
  return _get_skipped_lines_response(data["rows"], id_before, id_after,
                                     where, context)


def _get_comment_counts(account, patchset):
  """Helper to get comment counts for all patches in a single query.

  The helper returns two dictionaries comments_by_patch and
  drafts_by_patch with patch key as key and comment count as
  value. Patches without comments or drafts are not present in those
  dictionaries.
  """
  # A key-only query won't work because we need to fetch the patch key
  # in the for loop further down.
  comment_query = models.Comment.all()
  comment_query.ancestor(patchset)

  # Get all comment counts with one query rather than one per patch.
  comments_by_patch = {}
  drafts_by_patch = {}
  for c in comment_query:
    pkey = models.Comment.patch.get_value_for_datastore(c)
    if not c.draft:
      comments_by_patch[pkey] = comments_by_patch.setdefault(pkey, 0) + 1
    elif account and c.author == account.user:
      drafts_by_patch[pkey] = drafts_by_patch.setdefault(pkey, 0) + 1

  return comments_by_patch, drafts_by_patch


def _add_next_prev(patchset, patch):
  """Helper to add .next and .prev attributes to a patch object."""
  patch.prev = patch.next = None
  patches = list(models.Patch.gql("WHERE patchset = :1 ORDER BY filename",
                                  patchset))
  patchset.patches = patches  # Required to render the jump to select.

  comments_by_patch, drafts_by_patch = _get_comment_counts(
     models.Account.current_user_account, patchset)

  last_patch = None
  next_patch = None
  last_patch_with_comment = None
  next_patch_with_comment = None

  found_patch = False
  for p in patches:
      if p.filename == patch.filename:
        found_patch = True
        continue

      p._num_comments = comments_by_patch.get(p.key(), 0)
      p._num_drafts = drafts_by_patch.get(p.key(), 0)

      if not found_patch:
          last_patch = p
          if p.num_comments > 0 or p.num_drafts > 0:
            last_patch_with_comment = p
      else:
          if next_patch is None:
            next_patch = p
          if p.num_comments > 0 or p.num_drafts > 0:
            next_patch_with_comment = p
            # safe to stop scanning now because the next with out a comment
            # will already have been filled in by some earlier patch
            break

  patch.prev = last_patch
  patch.next = next_patch
  patch.prev_with_comment = last_patch_with_comment
  patch.next_with_comment = next_patch_with_comment


def _add_next_prev2(ps_left, ps_right, patch_right):
  """Helper to add .next and .prev attributes to a patch object."""
  patch_right.prev = patch_right.next = None
  patches = list(models.Patch.gql("WHERE patchset = :1 ORDER BY filename",
                                  ps_right))
  ps_right.patches = patches  # Required to render the jump to select.

  n_comments, n_drafts = _get_comment_counts(
    models.Account.current_user_account, ps_right)

  last_patch = None
  next_patch = None
  last_patch_with_comment = None
  next_patch_with_comment = None

  found_patch = False
  for p in patches:
      if p.filename == patch_right.filename:
        found_patch = True
        continue

      p._num_comments = n_comments.get(p.key(), 0)
      p._num_drafts = n_drafts.get(p.key(), 0)

      if not found_patch:
          last_patch = p
          if ((p.num_comments > 0 or p.num_drafts > 0) and
              ps_left.key().id() in p.delta):
            last_patch_with_comment = p
      else:
          if next_patch is None:
            next_patch = p
          if ((p.num_comments > 0 or p.num_drafts > 0) and
              ps_left.key().id() in p.delta):
            next_patch_with_comment = p
            # safe to stop scanning now because the next with out a comment
            # will already have been filled in by some earlier patch
            break

  patch_right.prev = last_patch
  patch_right.next = next_patch
  patch_right.prev_with_comment = last_patch_with_comment
  patch_right.next_with_comment = next_patch_with_comment


@post_required
def inline_draft(request):
  """/inline_draft - Ajax handler to submit an in-line draft comment.

  This wraps _inline_draft(); all exceptions are logged and cause an
  abbreviated response indicating something went wrong.

  Note: creating or editing draft comments is *not* XSRF-protected,
  because it is not unusual to come back after hours; the XSRF tokens
  time out after 1 or 2 hours.  The final submit of the drafts for
  others to view *is* XSRF-protected.
  """
  try:
    return _inline_draft(request)
  except Exception, err:
    logging.exception('Exception in inline_draft processing:')
    # TODO(guido): return some kind of error instead?
    # Return HttpResponse for now because the JS part expects
    # a 200 status code.
    return HttpResponse('<font color="red">Error: %s; please report!</font>' %
                        err.__class__.__name__)


def _inline_draft(request):
  """Helper to submit an in-line draft comment."""
  # TODO(guido): turn asserts marked with XXX into errors
  # Don't use @login_required, since the JS doesn't understand redirects.
  if not request.user:
    # Don't log this, spammers have started abusing this.
    return HttpResponse('Not logged in')
  snapshot = request.POST.get('snapshot')
  assert snapshot in ('old', 'new'), repr(snapshot)
  left = (snapshot == 'old')
  side = request.POST.get('side')
  assert side in ('a', 'b'), repr(side)  # Display left (a) or right (b)
  issue_id = int(request.POST['issue'])
  issue = models.Issue.get_by_id(issue_id)
  assert issue  # XXX
  patchset_id = int(request.POST.get('patchset') or
                    request.POST[side == 'a' and 'ps_left' or 'ps_right'])
  patchset = models.PatchSet.get_by_id(int(patchset_id), parent=issue)
  assert patchset  # XXX
  patch_id = int(request.POST.get('patch') or
                 request.POST[side == 'a' and 'patch_left' or 'patch_right'])
  patch = models.Patch.get_by_id(int(patch_id), parent=patchset)
  assert patch  # XXX
  text = request.POST.get('text')
  lineno = int(request.POST['lineno'])
  message_id = request.POST.get('message_id')
  comment = None
  if message_id:
    comment = models.Comment.get_by_key_name(message_id, parent=patch)
    if comment is None or not comment.draft or comment.author != request.user:
      comment = None
      message_id = None
  if not message_id:
    # Prefix with 'z' to avoid key names starting with digits.
    message_id = 'z' + binascii.hexlify(_random_bytes(16))

  if not text.rstrip():
    if comment is not None:
      assert comment.draft and comment.author == request.user
      comment.delete()  # Deletion
      comment = None
      # Re-query the comment count.
      models.Account.current_user_account.update_drafts(issue)
  else:
    if comment is None:
      comment = models.Comment(key_name=message_id, parent=patch)
    comment.patch = patch
    comment.lineno = lineno
    comment.left = left
    comment.text = db.Text(text)
    comment.message_id = message_id
    comment.put()
    # The actual count doesn't matter, just that there's at least one.
    models.Account.current_user_account.update_drafts(issue, 1)

  query = models.Comment.gql(
      'WHERE patch = :patch AND lineno = :lineno AND left = :left '
      'ORDER BY date',
      patch=patch, lineno=lineno, left=left)
  comments = list(c for c in query if not c.draft or c.author == request.user)
  if comment is not None and comment.author is None:
    # Show anonymous draft even though we don't save it
    comments.append(comment)
  if not comments:
    return HttpResponse(' ')
  for c in comments:
    c.complete(patch)
  return render_to_response('inline_comment.html',
                            {'user': request.user,
                             'patch': patch,
                             'patchset': patchset,
                             'issue': issue,
                             'comments': comments,
                             'lineno': lineno,
                             'snapshot': snapshot,
                             'side': side,
                             },
                            context_instance=RequestContext(request))


def _get_affected_files(issue, full_diff=False):
  """Helper to return a list of affected files from the latest patchset.

  Args:
    issue: Issue instance.
    full_diff: If true, include the entire diff even if it exceeds 100 lines.

  Returns:
    2-tuple containing a list of affected files, and the diff contents if it
    is less than 100 lines (otherwise the second item is an empty string).
  """
  files = []
  modified_count = 0
  diff = ''
  patchsets = list(issue.patchset_set.order('created'))
  if len(patchsets):
    patchset = patchsets[-1]
    for patch in patchset.patch_set.order('filename'):
      file_str = ''
      if patch.status:
        file_str += patch.status + ' '
      file_str += patch.filename
      files.append(file_str)
      # No point in loading patches if the patchset is too large for email.
      if full_diff or modified_count < 100:
        modified_count += patch.num_added + patch.num_removed

    if full_diff or modified_count < 100:
      diff = patchset.data

  return files, diff


def _get_mail_template(request, issue, full_diff=False):
  """Helper to return the template and context for an email.

  If this is the first email sent by the owner, a template that lists the
  reviewers, description and files is used.
  """
  context = {}
  template = 'mails/comment.txt'
  if request.user == issue.owner:
    if db.GqlQuery('SELECT * FROM Message WHERE ANCESTOR IS :1 AND sender = :2',
                   issue, db.Email(request.user.email())).count(1) == 0:
      template = 'mails/review.txt'
      files, patch = _get_affected_files(issue, full_diff)
      context.update({'files': files, 'patch': patch, 'base': issue.base})
  return template, context


@login_required
@issue_required
@xsrf_required
def publish(request):
  """ /<issue>/publish - Publish draft comments and send mail."""
  issue = request.issue
  if request.user == issue.owner:
    form_class = PublishForm
  else:
    form_class = MiniPublishForm
  draft_message = None
  if not request.POST.get('message_only', None):
    query = models.Message.gql(('WHERE issue = :1 AND sender = :2 '
                                'AND draft = TRUE'), issue,
                               request.user.email())
    draft_message = query.get()
  if request.method != 'POST':
    reviewers = issue.reviewers[:]
    cc = issue.cc[:]
    if request.user != issue.owner and (request.user.email()
                                        not in issue.reviewers):
      reviewers.append(request.user.email())
      if request.user.email() in cc:
        cc.remove(request.user.email())
    reviewers = [models.Account.get_nickname_for_email(reviewer,
                                                       default=reviewer)
                 for reviewer in reviewers]
    ccs = [models.Account.get_nickname_for_email(cc, default=cc) for cc in cc]
    tbd, comments = _get_draft_comments(request, issue, True)
    preview = _get_draft_details(request, comments)
    if draft_message is None:
      msg = ''
    else:
      msg = draft_message.text
    form = form_class(initial={'subject': issue.subject,
                               'reviewers': ', '.join(reviewers),
                               'cc': ', '.join(ccs),
                               'send_mail': True,
                               'message': msg,
                               })
    return respond(request, 'publish.html', {'form': form,
                                             'issue': issue,
                                             'preview': preview,
                                             'draft_message': draft_message,
                                             })

  form = form_class(request.POST)
  if not form.is_valid():
    return respond(request, 'publish.html', {'form': form, 'issue': issue})
  if request.user == issue.owner:
    issue.subject = form.cleaned_data['subject']
  if form.is_valid() and not form.cleaned_data.get('message_only', False):
    reviewers = _get_emails(form, 'reviewers')
  else:
    reviewers = issue.reviewers
    if request.user != issue.owner and request.user.email() not in reviewers:
      reviewers.append(db.Email(request.user.email()))
  if form.is_valid() and not form.cleaned_data.get('message_only', False):
    cc = _get_emails(form, 'cc')
  else:
    cc = issue.cc
    # The user is in the reviewer list, remove them from CC if they're there.
    if request.user.email() in cc:
      cc.remove(request.user.email())
  if not form.is_valid():
    return respond(request, 'publish.html', {'form': form, 'issue': issue})
  issue.reviewers = reviewers
  issue.cc = cc
  if not form.cleaned_data.get('message_only', False):
    tbd, comments = _get_draft_comments(request, issue)
  else:
    tbd = []
    comments = []
  issue.update_comment_count(len(comments))
  tbd.append(issue)

  if comments:
    logging.warn('Publishing %d comments', len(comments))
  msg = _make_message(request, issue,
                      form.cleaned_data['message'],
                      comments,
                      form.cleaned_data['send_mail'],
                      draft=draft_message)
  tbd.append(msg)

  for obj in tbd:
    db.put(obj)

  _notify_issue(request, issue, 'Comments published')

  # There are now no comments here (modulo race conditions)
  models.Account.current_user_account.update_drafts(issue, 0)
  if form.cleaned_data.get('no_redirect', False):
    return HttpResponse('OK', content_type='text/plain')
  return HttpResponseRedirect(reverse(show, args=[issue.key().id()]))


def _encode_safely(s):
  """Helper to turn a unicode string into 8-bit bytes."""
  if isinstance(s, unicode):
    s = s.encode('utf-8')
  return s


def _get_draft_comments(request, issue, preview=False):
  """Helper to return objects to put() and a list of draft comments.

  If preview is True, the list of objects to put() is empty to avoid changes
  to the datastore.

  Args:
    request: Django Request object.
    issue: Issue instance.
    preview: Preview flag (default: False).

  Returns:
    2-tuple (put_objects, comments).
  """
  comments = []
  tbd = []
  # XXX Should request all drafts for this issue once, now we can.
  for patchset in issue.patchset_set.order('created'):
    ps_comments = list(models.Comment.gql(
        'WHERE ANCESTOR IS :1 AND author = :2 AND draft = TRUE',
        patchset, request.user))
    if ps_comments:
      patches = dict((p.key(), p) for p in patchset.patch_set)
      for p in patches.itervalues():
        p.patchset = patchset
      for c in ps_comments:
        c.draft = False
        # Get the patch key value without loading the patch entity.
        # NOTE: Unlike the old version of this code, this is the
        # recommended and documented way to do this!
        pkey = models.Comment.patch.get_value_for_datastore(c)
        if pkey in patches:
          patch = patches[pkey]
          c.patch = patch
      if not preview:
        tbd.append(ps_comments)
        patchset.update_comment_count(len(ps_comments))
        tbd.append(patchset)
      ps_comments.sort(key=lambda c: (c.patch.filename, not c.left,
                                      c.lineno, c.date))
      comments += ps_comments
  return tbd, comments


def _get_draft_details(request, comments):
  """Helper to display comments with context in the email message."""
  last_key = None
  output = []
  linecache = {}  # Maps (c.patch.key(), c.left) to list of lines
  modified_patches = []
  for c in comments:
    if (c.patch.key(), c.left) != last_key:
      url = request.build_absolute_uri(
        reverse(diff, args=[request.issue.key().id(),
                            c.patch.patchset.key().id(),
                            c.patch.filename]))
      output.append('\n%s\nFile %s (%s):' % (url, c.patch.filename,
                                             c.left and "left" or "right"))
      last_key = (c.patch.key(), c.left)
      patch = c.patch
      if patch.no_base_file:
        linecache[last_key] = patching.ParsePatchToLines(patch.lines)
      else:
        if c.left:
          old_lines = patch.get_content().text.splitlines(True)
          linecache[last_key] = old_lines
        else:
          new_lines = patch.get_patched_content().text.splitlines(True)
          linecache[last_key] = new_lines
    file_lines = linecache[last_key]
    context = ''
    if patch.no_base_file:
      for old_line_no, new_line_no, line_text in file_lines:
        if ((c.lineno == old_line_no and c.left) or
            (c.lineno == new_line_no and not c.left)):
          context = line_text.strip()
          break
    else:
      if 1 <= c.lineno <= len(file_lines):
        context = file_lines[c.lineno - 1].strip()
    url = request.build_absolute_uri(
      '%s#%scode%d' % (reverse(diff, args=[request.issue.key().id(),
                                           c.patch.patchset.key().id(),
                                           c.patch.filename]),
                       c.left and "old" or "new",
                       c.lineno))
    output.append('\n%s\n%s:%d: %s\n%s' % (url, c.patch.filename, c.lineno,
                                           context, c.text.rstrip()))
  if modified_patches:
    db.put(modified_patches)
  return '\n'.join(output)


def _make_message(request, issue, message, comments=None, send_mail=False,
                  draft=None):
  """Helper to create a Message instance and optionally send an email."""
  attach_patch = request.POST.get("attach_patch") == "yes"
  template, context = _get_mail_template(request, issue, full_diff=attach_patch)
  # Decide who should receive mail
  my_email = db.Email(request.user.email())
  to = [db.Email(issue.owner.email())] + issue.reviewers
  cc = issue.cc[:]
  if django_settings.RIETVELD_INCOMING_MAIL_ADDRESS:
    cc.append(db.Email(django_settings.RIETVELD_INCOMING_MAIL_ADDRESS))
  reply_to = to + cc
  if my_email in to and len(to) > 1:  # send_mail() wants a non-empty to list
    to.remove(my_email)
  if my_email in cc:
    cc.remove(my_email)
  subject = '%s (issue %d)' % (issue.subject, issue.key().id())
  patch = None
  if attach_patch:
    subject = 'PATCH: ' + subject
    if 'patch' in context:
      patch = context['patch']
      del context['patch']
  if issue.message_set.count(1) > 0:
    subject = 'Re: ' + subject
  if comments:
    details = _get_draft_details(request, comments)
  else:
    details = ''
  message = message.replace('\r\n', '\n')
  text = ((message.strip() + '\n\n' + details.strip())).strip()
  if draft is None:
    msg = models.Message(issue=issue,
                         subject=subject,
                         sender=my_email,
                         recipients=reply_to,
                         text=db.Text(text),
                         parent=issue)
  else:
    msg = draft
    msg.subject = subject
    msg.recipients = reply_to
    msg.text = db.Text(text)
    msg.draft = False
    msg.date = datetime.datetime.now()

  if send_mail:
    # Limit the list of files in the email to approximately 200
    if 'files' in context and len(context['files']) > 210:
      num_trimmed = len(context['files']) - 200
      del context['files'][200:]
      context['files'].append('[[ %d additional files ]]' % num_trimmed)
    url = request.build_absolute_uri(reverse(show, args=[issue.key().id()]))
    reviewer_nicknames = ', '.join(library.get_nickname(rev_temp, True,
                                                        request)
                                   for rev_temp in issue.reviewers)
    cc_nicknames = ', '.join(library.get_nickname(cc_temp, True, request)
                             for cc_temp in cc)
    my_nickname = library.get_nickname(request.user, True, request)
    reply_to = ', '.join(reply_to)
    description = (issue.description or '').replace('\r\n', '\n')
    home = request.build_absolute_uri(reverse(index))
    context.update({'reviewer_nicknames': reviewer_nicknames,
                    'cc_nicknames': cc_nicknames,
                    'my_nickname': my_nickname, 'url': url,
                    'message': message, 'details': details,
                    'description': description, 'home': home,
                    })
    body = django.template.loader.render_to_string(
      template, context, context_instance=RequestContext(request))
    logging.warn('Mail: to=%s; cc=%s', ', '.join(to), ', '.join(cc))
    send_args = {'sender': my_email,
                 'to': [_encode_safely(address) for address in to],
                 'subject': _encode_safely(subject),
                 'body': _encode_safely(body),
                 'reply_to': _encode_safely(reply_to)}
    if cc:
      send_args['cc'] = [_encode_safely(address) for address in cc]
    if patch:
      send_args['attachments'] = [('issue_%s_patch.diff' % issue.key().id(),
                                   patch)]

    attempts = 0
    while True:
      try:
        mail.send_mail(**send_args)
        break
      except apiproxy_errors.DeadlineExceededError:
        # apiproxy_errors.DeadlineExceededError is raised when the
        # deadline of an API call is reached (e.g. for mail it's
        # something about 5 seconds). It's not the same as the lethal
        # runtime.DeadlineExeededError.
        attempts += 1
        if attempts >= 3:
          raise
    if attempts:
      logging.warning("Retried sending email %s times", attempts)

  return msg


@post_required
@login_required
@xsrf_required
@issue_required
def star(request):
  """Add a star to an Issue."""
  account = models.Account.current_user_account
  account.user_has_selected_nickname()  # This will preserve account.fresh.
  if account.stars is None:
    account.stars = []
  id = request.issue.key().id()
  if id not in account.stars:
    account.stars.append(id)
    account.put()
  return respond(request, 'issue_star.html', {'issue': request.issue})


@post_required
@login_required
@issue_required
@xsrf_required
def unstar(request):
  """Remove the star from an Issue."""
  account = models.Account.current_user_account
  account.user_has_selected_nickname()  # This will preserve account.fresh.
  if account.stars is None:
    account.stars = []
  id = request.issue.key().id()
  if id in account.stars:
    account.stars[:] = [i for i in account.stars if i != id]
    account.put()
  return respond(request, 'issue_star.html', {'issue': request.issue})


@login_required
@issue_required
def draft_message(request):
  """/<issue>/draft_message - Retrieve, modify and delete draft messages.

  Note: creating or editing draft messages is *not* XSRF-protected,
  because it is not unusual to come back after hours; the XSRF tokens
  time out after 1 or 2 hours.  The final submit of the drafts for
  others to view *is* XSRF-protected.
  """
  query = models.Message.gql(('WHERE issue = :1 AND sender = :2 '
                              'AND draft = TRUE'),
                             request.issue, request.user.email())
  if query.count() == 0:
    draft_message = None
  else:
    draft_message = query.get()
  if request.method == 'GET':
    return _get_draft_message(request, draft_message)
  elif request.method == 'POST':
    return _post_draft_message(request, draft_message)
  elif request.method == 'DELETE':
    return _delete_draft_message(request, draft_message)
  return HttpResponse('An error occurred.', content_type='text/plain',
                      status=500)


def _get_draft_message(request, draft):
  """Handles GET requests to /<issue>/draft_message.

  Arguments:
    request: The current request.
    draft: A Message instance or None.

  Returns the content of a draft message or an empty string if draft is None.
  """
  if draft is None:
    return HttpResponse('', content_type='text/plain')
  return HttpResponse(draft.text, content_type='text/plain')


def _post_draft_message(request, draft):
  """Handles POST requests to /<issue>/draft_message.

  If draft is None a new message is created.

  Arguments:
    request: The current request.
    draft: A Message instance or None.
  """
  if draft is None:
    draft = models.Message(issue=request.issue, parent=request.issue,
                           sender=request.user.email(), draft=True)
  draft.text = request.POST.get('reviewmsg')
  draft.put()
  return HttpResponse(draft.text, content_type='text/plain')


def _delete_draft_message(request, draft):
  """Handles DELETE requests to /<issue>/draft_message.

  Deletes a draft message.

  Arguments:
    request: The current request.
    draft: A Message instance or None.
  """
  if draft is not None:
    draft.delete()
  return HttpResponse('OK', content_type='text/plain')


@json_response
def search(request):
  """/search - Search for issues or patchset."""
  if request.method == 'GET':
    form = SearchForm(request.GET)
    if not form.is_valid() or not request.GET:
      return respond(request, 'search.html', {'form': form})
  else:
    form = SearchForm(request.POST)
    if not form.is_valid():
      return HttpResponseBadRequest('Invalid arguments',
          content_type='text/plain')
  logging.info('%s' % form.cleaned_data)
  keys_only = form.cleaned_data['keys_only'] or False
  format = form.cleaned_data.get('format') or 'html'
  if format == 'html':
    keys_only = False
  q = models.Issue.all(keys_only=keys_only)
  if form.cleaned_data.get('cursor'):
    q.with_cursor(form.cleaned_data['cursor'])
  if form.cleaned_data.get('closed') != None:
    q.filter('closed = ', form.cleaned_data['closed'])
  if form.cleaned_data.get('owner'):
    q.filter('owner = ', form.cleaned_data['owner'])
  if form.cleaned_data.get('reviewer'):
    q.filter('reviewers = ', form.cleaned_data['reviewer'])
  if form.cleaned_data.get('private') != None:
    q.filter('private = ', form.cleaned_data['private'])
  if form.cleaned_data.get('base'):
    q.filter('base = ', form.cleaned_data['base'])
  # Update the cursor value in the result.
  if format == 'html':
    nav_params = dict(
        (k, v) for k, v in form.cleaned_data.iteritems() if v is not None)
    return _paginate_issues_with_cursor(
        reverse(search),
        request,
        q,
        form.cleaned_data['limit'] or DEFAULT_LIMIT,
        'search_results.html',
        extra_nav_parameters=nav_params)

  results = q.fetch(form.cleaned_data['limit'] or 100)
  form.cleaned_data['cursor'] = q.cursor()
  if keys_only:
    # There's not enough information to filter. The only thing that is leaked is
    # the issue's key.
    filtered_results = results
  else:
    filtered_results = [i for i in results if _can_view_issue(request.user, i)]
  data = {
    'cursor': form.cleaned_data['cursor'],
  }
  if keys_only:
    data['results'] = [i.id() for i in filtered_results]
  else:
    messages = form.cleaned_data['with_messages']
    data['results'] = [_issue_as_dict(i, messages, request)
                      for i in filtered_results],
  return data


### Repositories and Branches ###


def repos(request):
  """/repos - Show the list of known Subversion repositories."""
  # Clean up garbage created by buggy edits
  bad_branches = list(models.Branch.gql('WHERE owner = :1', None))
  if bad_branches:
    db.delete(bad_branches)
  repo_map = {}
  for repo in list(models.Repository.all()):
    repo_map[str(repo.key())] = repo
  branches = []
  for branch in models.Branch.all():
    branch.repository = repo_map[str(branch._repo)]
    branches.append(branch)
  branches.sort(key=lambda b: map(
    unicode.lower, (b.repository.name, b.category, b.name)))
  return respond(request, 'repos.html', {'branches': branches})


@login_required
@xsrf_required
def repo_new(request):
  """/repo_new - Create a new Subversion repository record."""
  if request.method != 'POST':
    form = RepoForm()
    return respond(request, 'repo_new.html', {'form': form})
  form = RepoForm(request.POST)
  errors = form.errors
  if not errors:
    try:
      repo = form.save(commit=False)
    except ValueError, err:
      errors['__all__'] = unicode(err)
  if errors:
    return respond(request, 'repo_new.html', {'form': form})
  repo.put()
  branch_url = repo.url
  if not branch_url.endswith('/'):
    branch_url += '/'
  branch_url += 'trunk/'
  branch = models.Branch(repo=repo, repo_name=repo.name,
                         category='*trunk*', name='Trunk',
                         url=branch_url)
  branch.put()
  return HttpResponseRedirect(reverse(repos))


SVN_ROOT = 'http://svn.python.org/view/*checkout*/python/'
BRANCHES = [
    # category, name, url suffix
    ('*trunk*', 'Trunk', 'trunk/'),
    ('branch', '2.5', 'branches/release25-maint/'),
    ('branch', 'py3k', 'branches/py3k/'),
    ]


# TODO: Make this a POST request to avoid XSRF attacks.
@admin_required
def repo_init(request):
  """/repo_init - Initialze the list of known Subversion repositories."""
  python = models.Repository.gql("WHERE name = 'Python'").get()
  if python is None:
    python = models.Repository(name='Python', url=SVN_ROOT)
    python.put()
    pybranches = []
  else:
    pybranches = list(models.Branch.gql('WHERE repo = :1', python))
  for category, name, url in BRANCHES:
    url = python.url + url
    for br in pybranches:
      if (br.category, br.name, br.url) == (category, name, url):
        break
    else:
      br = models.Branch(repo=python, repo_name='Python',
                         category=category, name=name, url=url)
      br.put()
  return HttpResponseRedirect(reverse(repos))


@login_required
@xsrf_required
def branch_new(request, repo_id):
  """/branch_new/<repo> - Add a new Branch to a Repository record."""
  repo = models.Repository.get_by_id(int(repo_id))
  if request.method != 'POST':
    # XXX Use repo.key() so that the default gets picked up
    form = BranchForm(initial={'repo': repo.key(),
                               'url': repo.url,
                               'category': 'branch',
                               })
    return respond(request, 'branch_new.html', {'form': form, 'repo': repo})
  form = BranchForm(request.POST)
  errors = form.errors
  if not errors:
    try:
      branch = form.save(commit=False)
    except ValueError, err:
      errors['__all__'] = unicode(err)
  if errors:
    return respond(request, 'branch_new.html', {'form': form, 'repo': repo})
  branch.repo_name = repo.name
  branch.put()
  return HttpResponseRedirect(reverse(repos))


@login_required
@xsrf_required
def branch_edit(request, branch_id):
  """/branch_edit/<branch> - Edit a Branch record."""
  branch = models.Branch.get_by_id(int(branch_id))
  if branch.owner != request.user:
    return HttpResponseForbidden('You do not own this branch')
  if request.method != 'POST':
    form = BranchForm(instance=branch)
    return respond(request, 'branch_edit.html',
                   {'branch': branch, 'form': form})

  form = BranchForm(request.POST, instance=branch)
  errors = form.errors
  if not errors:
    try:
      branch = form.save(commit=False)
    except ValueError, err:
      errors['__all__'] = unicode(err)
  if errors:
    return respond(request, 'branch_edit.html',
                   {'branch': branch, 'form': form})
  branch.repo_name = branch.repo.name
  branch.put()
  return HttpResponseRedirect(reverse(repos))


@post_required
@login_required
@xsrf_required
def branch_delete(request, branch_id):
  """/branch_delete/<branch> - Delete a Branch record."""
  branch = models.Branch.get_by_id(int(branch_id))
  if branch.owner != request.user:
    return HttpResponseForbidden('You do not own this branch')
  repo = branch.repo
  branch.delete()
  num_branches = models.Branch.gql('WHERE repo = :1', repo).count()
  if not num_branches:
    # Even if we don't own the repository?  Yes, I think so!  Empty
    # repositories have no representation on screen.
    repo.delete()
  return HttpResponseRedirect(reverse(repos))


### User Profiles ###


@login_required
@xsrf_required
def settings(request):
  account = models.Account.current_user_account
  if request.method != 'POST':
    nickname = account.nickname
    default_context = account.default_context
    default_column_width = account.default_column_width
    form = SettingsForm(initial={'nickname': nickname,
                                 'context': default_context,
                                 'column_width': default_column_width,
                                 'notify_by_email': account.notify_by_email,
                                 'notify_by_chat': account.notify_by_chat,
                                 })
    chat_status = None
    if account.notify_by_chat:
      try:
        presence = xmpp.get_presence(account.email)
      except Exception, err:
        logging.error('Exception getting XMPP presence: %s', err)
        chat_status = 'Error (%s)' % err
      else:
        if presence:
          chat_status = 'online'
        else:
          chat_status = 'offline'
    return respond(request, 'settings.html', {'form': form,
                                              'chat_status': chat_status})
  form = SettingsForm(request.POST)
  if form.is_valid():
    account.nickname = form.cleaned_data.get('nickname')
    account.default_context = form.cleaned_data.get('context')
    account.default_column_width = form.cleaned_data.get('column_width')
    account.notify_by_email = form.cleaned_data.get('notify_by_email')
    notify_by_chat = form.cleaned_data.get('notify_by_chat')
    must_invite = notify_by_chat and not account.notify_by_chat
    account.notify_by_chat = notify_by_chat
    account.fresh = False
    account.put()
    if must_invite:
      logging.info('Sending XMPP invite to %s', account.email)
      try:
        xmpp.send_invite(account.email)
      except Exception, err:
        # XXX How to tell user it failed?
        logging.error('XMPP invite to %s failed', account.email)
  else:
    return respond(request, 'settings.html', {'form': form})
  return HttpResponseRedirect(reverse(mine))


@post_required
@login_required
@xsrf_required
def account_delete(request):
  account = models.Account.current_user_account
  account.delete()
  return HttpResponseRedirect(users.create_logout_url(reverse(index)))


@user_key_required
def user_popup(request):
  """/user_popup - Pop up to show the user info."""
  try:
    return _user_popup(request)
  except Exception, err:
    logging.exception('Exception in user_popup processing:')
    # Return HttpResponse because the JS part expects a 200 status code.
    return HttpResponse('<font color="red">Error: %s; please report!</font>' %
                        err.__class__.__name__)


def _user_popup(request):
  user = request.user_to_show
  popup_html = memcache.get('user_popup:' + user.email())
  if popup_html is None:
    num_issues_created = db.GqlQuery(
      'SELECT * FROM Issue '
      'WHERE closed = FALSE AND owner = :1',
      user).count()
    num_issues_reviewed = db.GqlQuery(
      'SELECT * FROM Issue '
      'WHERE closed = FALSE AND reviewers = :1',
      user.email()).count()

    user.nickname = models.Account.get_nickname_for_email(user.email())
    popup_html = render_to_response('user_popup.html',
                            {'user': user,
                             'num_issues_created': num_issues_created,
                             'num_issues_reviewed': num_issues_reviewed,
                             },
                             context_instance=RequestContext(request))
    # Use time expired cache because the number of issues will change over time
    memcache.add('user_popup:' + user.email(), popup_html, 60)
  return popup_html


@post_required
def incoming_chat(request):
  """/_ah/xmpp/message/chat/

  This handles incoming XMPP (chat) messages.

  Just reply saying we ignored the chat.
  """
  try:
    msg = xmpp.Message(request.POST)
  except xmpp.InvalidMessageError, err:
    logging.warn('Incoming invalid chat message: %s' % err)
    return HttpResponse('')
  sts = msg.reply('Sorry, Rietveld does not support chat input')
  logging.debug('XMPP status %r', sts)
  return HttpResponse('')


@post_required
def incoming_mail(request, recipients):
  """/_ah/mail/(.*)

  Handle incoming mail messages.

  The issue is not modified. No reviewers or CC's will be added or removed.
  """
  try:
    _process_incoming_mail(request.raw_post_data, recipients)
  except InvalidIncomingEmailError, err:
    logging.debug(str(err))
  return HttpResponse('')


def _process_incoming_mail(raw_message, recipients):
  """Process an incoming email message."""
  recipients = [x[1] for x in email.utils.getaddresses([recipients])]

  incoming_msg = mail.InboundEmailMessage(raw_message)

  if 'X-Google-Appengine-App-Id' in incoming_msg.original:
    raise InvalidIncomingEmailError('Mail sent by App Engine')

  subject = incoming_msg.subject or ''
  match = re.search(r'\(issue *(?P<id>\d+)\)$', subject)
  if match is None:
    raise InvalidIncomingEmailError('No issue id found: %s', subject)
  issue_id = int(match.groupdict()['id'])
  issue = models.Issue.get_by_id(issue_id)
  if issue is None:
    raise InvalidIncomingEmailError('Unknown issue ID: %d' % issue_id)
  sender = email.utils.parseaddr(incoming_msg.sender)[1]

  body = None
  for content_type, payload in incoming_msg.bodies('text/plain'):
    body = payload.decode()
    break
  if body is None or not body.strip():
    raise InvalidIncomingEmailError('Ignoring empty message.')
  elif len(body) > django_settings.RIETVELD_INCOMING_MAIL_MAX_SIZE:
    # see issue325, truncate huge bodies
    trunc_msg = '... (message truncated)'
    body = body[:django_settings.RIETVELD_INCOMING_MAIL_MAX_SIZE - len(trunc_msg)]
    body += trunc_msg

  # If the subject is long, this might come wrapped into more than one line.
  subject = ' '.join([x.strip() for x in subject.splitlines()])
  msg = models.Message(issue=issue, parent=issue,
                       subject=subject,
                       sender=db.Email(sender),
                       recipients=[db.Email(x) for x in recipients],
                       date=datetime.datetime.now(),
                       text=db.Text(body),
                       draft=False)
  msg.put()

  # Add sender to reviewers if needed.
  all_emails = [str(x).lower()
                for x in [issue.owner.email()]+issue.reviewers+issue.cc]
  if sender.lower() not in all_emails:
    query = models.Account.all().filter('lower_email =', sender.lower())
    account = query.get()
    if account is not None:
      issue.reviewers.append(account.email)  # e.g. account.email is CamelCase
    else:
      issue.reviewers.append(db.Email(sender))
    issue.put()


@login_required
def xsrf_token(request):
  """/xsrf_token - Return the user's XSRF token.

  This is used by tools like git-cl that need to be able to interact with the
  site on the user's behalf.  A custom header named X-Requesting-XSRF-Token must
  be included in the HTTP request; an error is returned otherwise.
  """
  if not request.META.has_key('HTTP_X_REQUESTING_XSRF_TOKEN'):
    return HttpResponse('Please include a header named X-Requesting-XSRF-Token '
                        '(its content doesn\'t matter).', status=400)
  return HttpResponse(models.Account.current_user_account.get_xsrf_token(),
                      mimetype='text/plain')


def customized_upload_py(request):
  """/static/upload.py - Return patched upload.py with appropiate auth type and
  default review server setting.

  This is used to let the user download a customized upload.py script
  for hosted Rietveld instances.
  """
  f = open(django_settings.UPLOAD_PY_SOURCE)
  source = f.read()
  f.close()

  # When served from a Google Apps instance, the account namespace needs to be
  # switched to "Google Apps only".
  if ('AUTH_DOMAIN' in request.META
      and request.META['AUTH_DOMAIN'] != 'gmail.com'):
    source = source.replace('AUTH_ACCOUNT_TYPE = "GOOGLE"',
                            'AUTH_ACCOUNT_TYPE = "HOSTED"')

  # On a non-standard instance, the default review server is changed to the
  # current hostname. This might give weird results when using versioned appspot
  # URLs (eg. 1.latest.codereview.appspot.com), but this should only affect
  # testing.
  if request.META['HTTP_HOST'] != 'codereview.appspot.com':
    review_server = request.META['HTTP_HOST']
    if request.is_secure():
      review_server = 'https://' + review_server
    source = source.replace('DEFAULT_REVIEW_SERVER = "codereview.appspot.com"',
                            'DEFAULT_REVIEW_SERVER = "%s"' % review_server)

  return HttpResponse(source, content_type='text/x-python')
