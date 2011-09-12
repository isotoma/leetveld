#
# Copyright 2008 Andi Albrecht <albrecht.andi@gmail.com>
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

"""Implements the mail fetch API.

http://code.google.com/appengine/docs/mail/
"""

from django.conf import settings
from django.core.mail import EmailMessage as _EmailMessage


class Error(Exception):
    """Base class for all exceptions in this module."""


class BadRequestError(Error):
    pass


class InvalidSenderError(Error):
    pass


class InvalidEmailError(Error):
    pass


class InvalidAttachmentTypeError(Error):
    pass


class MissingRecipientsError(Error):
    pass


class MissingSenderError(Error):
    pass


class MissingSubjectError(Error):
    pass


class MissingBodyError(Error):
    pass


class EmailMessage(object):

    def __init__(self, **kw):
        self.sender = None
        self.to = None
        self.cc = []
        self.bcc = []
        self.reply_to = None
        self.subject = None
        self.body = None
        self.html = None
        self.attachments = []
        self.initialize(**kw)

    def initialize(self, **kw):
        list_fields = ('to', 'cc', 'bcc', 'reply_to')
        for field in ('sender', 'to', 'cc', 'bcc', 'reply_to',
                      'subject', 'body', 'html', 'attachments'):
            value = kw.get(field, None)
            if value is not None:
                if field in list_fields and isinstance(value, basestring):
                    value = [value]
                setattr(self, field, value)

    def check_initialized(self):
        if not self.sender:
            raise MissingSenderError()
        if not self.to and not self.cc and not self.bcc:
            raise MissingRecipientsError()
        if not self.subject:
            raise MissingSubjectError()
        if not self.body:
            raise MissingBodyError()

    def is_initialized(self):
        try:
            self.check_intitialized()
            return True
        except Error:
            pass
        return False

    def send(self):
        headers = {}
        if self.cc:
            headers['Cc'] = ', '.join(self.cc)
        if self.reply_to:
            headers['Reply-To'] = ', '.join(self.reply_to)
        msg = _EmailMessage(self.subject, self.body, self.sender,
                            self.to, self.cc + self.bcc, headers=headers)
        msg.send(fail_silently=True)


def send_mail(sender, to, subject, body, **kw):
    """Send an email.

    To mimic the behavior of Google's App Engine the email
    is send with fail_silently=True as this function shouldn't
    raise an exception.

    Args:
      sender: The senders email address.
      to: List of recipients or single recipient address as string.
      subject: The email's subject.
      body: The email's body.
      kw: Additional header keywords.
    """
    if isinstance(to, basestring):
        to = [to]
    msg = EmailMessage(**kw)
    msg.sender = sender
    msg.to = to
    msg.subject = subject
    msg.body = body
    msg.send()


def check_email_valid(email_address, field):
    pass


def invalid_email_reason(email_address, field):
    pass


def is_email_valid(email_address):
    return True


def send_mail_to_admins(sender, subject, body, **kw):
    _EmailMessage(settings.EMAIL_SUBJECT_PREFIX + subject, body,
                  settings.SERVER_EMAIL, [a[1] for a in settings.ADMINS],
                  headers=kw).send(fail_silently=True)
