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

import unittest
import types

from django.contrib.auth.models import User
from django.test.client import Client

from gae2django.gaeapi.appengine.api import users


class UsersTest(unittest.TestCase):
    """Tests users API."""

    def setUp(self):
        try:
            self._u = User.objects.get(username='test')
        except User.DoesNotExist:
            self._u = User.objects.create_user('test',
                                               'test@example.com', 'testpw')
            self._u.save()
        try:
            self._a = User.objects.get(username='admin')
        except User.DoesNotExist:
            self._a = User.objects.create_superuser('admin',
                                                    'admin@example.com',
                                                    'testpw')

    def test_create_login_url(self):
        self.assertEqual(users.create_login_url('foo'),
                         '/accounts/login/?next=foo')

    def test_create_logout_url(self):
        self.assertEqual(users.create_logout_url('foo'),
                         '/accounts/logout/?next=foo')

    def test_get_current_user(self):
        c = Client()
        c.logout()
        c.get('/')
        self.assertEqual(users.get_current_user(), None)
        c.login(username='test', password='testpw')
        response = c.get('/')
        user = response.context['user']
        self.assert_(callable(user.email))
        self.assert_(hasattr(user, 'nickname'))
        self.assertEqual(users.get_current_user(), user)

    def test_is_current_user_admin(self):
        self.assertEqual(users.is_current_user_admin(), False)
        c = Client()
        c.login(username='test', password='testpw')
        response = c.get('/')
        self.assertEqual(users.is_current_user_admin(), False)
        c = Client()
        c.login(username='admin', password='testpw')
        response = c.get('/')
        self.assertEqual(users.is_current_user_admin(), True)

    def test_api(self):
        for name in ['create_login_url', 'create_logout_url',
                     'get_current_user', 'is_current_user_admin']:
            assert hasattr(users, name)
            assert callable(getattr(users, name))
        assert hasattr(users, 'User')
        for name in ['Error', 'UserNotFoundError',
                     'RedirectTooLongError']:
            assert hasattr(users, name)
            assert issubclass(getattr(users, name), Exception)

