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


from django.core import mail as _mail
from django.test import TestCase

from gae2django.gaeapi.appengine.api import mail

class MailFunctionsTest(TestCase):

    def test_send_mail(self):
        mail.send_mail('foo@example.com', 'bar@example.com',
                       'Subject', 'Body')
        self.assertEqual(len(_mail.outbox), 1)
        msg = _mail.outbox[0]
        self.assertEqual(msg.from_email, 'foo@example.com')
        self.assertEqual(msg.to, ['bar@example.com'])
        self.assertEqual(msg.subject, 'Subject')
        self.assertEqual(msg.body, 'Body')

    def test_send_mail_multi_to(self):
        mail.send_mail('foo@example.com',
                       ['bar1@example.com', 'bar2@example.com'],
                       'Subject', 'Body')
        self.assertEqual(len(_mail.outbox), 1)
        msg = _mail.outbox[0]
        self.assertEqual(msg.from_email, 'foo@example.com')
        self.assertEqual(msg.to, ['bar1@example.com', 'bar2@example.com'])
        self.assertEqual(msg.subject, 'Subject')
        self.assertEqual(msg.body, 'Body')

    def test_send_mail_keywords(self):
        kw = {'cc' : ['cc@example.com'],
              'bcc' : ['bcc@example.com'],
              'reply_to' : ['reply@example.com']}
        headers = {'Cc' : 'cc@example.com',
                   'Reply-To' : 'reply@example.com'}
        mail.send_mail('foo@example.com', 'bar@example.com',
                       'Subject', 'Body', **kw)
        self.assertEqual(len(_mail.outbox), 1)
        msg = _mail.outbox[0]
        self.assertEqual(msg.from_email, 'foo@example.com')
        self.assertEqual(msg.to, ['bar@example.com'])
        self.assertEqual(msg.subject, 'Subject')
        self.assertEqual(msg.body, 'Body')
        self.assertEqual(msg.extra_headers , headers)

    def test_send_mail_cc(self):
        kw = {'cc': 'cc@example.com'}
        mail.send_mail('foo@example.com', 'bar@example.com',
                       'Subject', 'Body', **kw)
        self.assertEqual(len(_mail.outbox), 1)
        msg = _mail.outbox[0]
        self.assert_('Cc' in msg.extra_headers)
        self.assertEqual(msg.extra_headers['Cc'], 'cc@example.com')
        msg_str = msg.message().as_string()
        found = False
        for line in msg_str.splitlines():
            if line == 'Cc: cc@example.com':
                found = True
                break
        if not found:
            raise AssertionError('Cc header not found in message.')

    def test_send_mail_multi_cc(self):
        kw = {'cc': ['cc1@example.com', 'cc2@example.com']}
        mail.send_mail('foo@example.com', 'bar@example.com',
                       'Subject', 'Body', **kw)
        self.assertEqual(len(_mail.outbox), 1)
        msg = _mail.outbox[0]
        self.assert_('Cc' in msg.extra_headers)
        self.assertEqual(msg.extra_headers['Cc'],
                         'cc1@example.com, cc2@example.com')

    def test_send_mail_reply_to(self):
        kw = {'reply_to': 'other@example.com'}
        mail.send_mail('foo@example.com', 'bar@example.com',
                       'Subject', 'Body', **kw)
        self.assertEqual(len(_mail.outbox), 1)
        msg = _mail.outbox[0]
        self.assert_('Reply-To' in msg.extra_headers)
        self.assertEqual(msg.extra_headers['Reply-To'], 'other@example.com')

    def test_send_mail_multi_reply_to(self):
        kw = {'reply_to': ['other1@example.com', 'other2@example.com']}
        mail.send_mail('foo@example.com', 'bar@example.com',
                       'Subject', 'Body', **kw)
        self.assertEqual(len(_mail.outbox), 1)
        msg = _mail.outbox[0]
        self.assert_('Reply-To' in msg.extra_headers)
        self.assertEqual(msg.extra_headers['Reply-To'],
                         'other1@example.com, other2@example.com')
