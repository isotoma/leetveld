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

from django.contrib.auth.models import User
from django.test.client import Client

from gae2django.gaeapi.appengine.ext import db
from gae2django.models import RegressionTestModel as TestModel
from gae2django.models import RefTestModel as TestModel2


class DatastoreModelTest(unittest.TestCase):

    def setUp(self):
        self.item1 = TestModel(key_name='foo1')
        self.item1.put()

    def tearDown(self):
        self.item1.delete()
        self.item1 = None

    # Class methods

    def test_get(self):
        item1 = TestModel(key_name='test1')
        item1.put()
        self.assertEqual(TestModel.get('test1'), item1)
        self.assertEqual(TestModel.get('foo'), None)
        self.assertEqual(TestModel.get(['test1', 'test2']), [item1, None])
        item2 = TestModel(key_name='test2')
        item2.put()
        self.assertEqual(TestModel.get(['test1', 'test2']), [item1, item2])
        item1.delete()
        item2.delete()

    def test_get_by_id(self):
        item1 = TestModel(xstring='test1')
        item1.put()
        self.assertEqual(TestModel.get_by_id(item1.key().id()), item1)
        self.assertEqual(TestModel.get_by_id(-1), None)
        self.assertEqual(TestModel.get_by_id([item1.key().id(), -1]),
                         [item1, None])
        item2 = TestModel(xstring='test2')
        item2.put()
        self.assertEqual(TestModel.get_by_id([item1.key().id(),
                                              item2.key().id()]),
                         [item1, item2])
        item1.delete()
        item2.delete()


    def test_get_by_key_name(self):
        self.assertEqual(TestModel.get_by_key_name('foo'), None)
        self.assertEqual(TestModel.get_by_key_name(['foo', 'bar']),
                         [None, None])
        item1 = TestModel(key_name='test1')
        item1.put()
        self.assertEqual(TestModel.get_by_key_name('test1'), item1)
        self.assertEqual(TestModel.get_by_key_name(['test1', 'test2']),
                         [item1, None])
        item2 = TestModel(key_name='test2')
        item2.put()
        self.assertEqual(TestModel.get_by_key_name(['test1', 'test2']),
                         [item1, item2])
        self.assertEqual(TestModel.get_by_key_name(['test1']),
                         [item1])
        item1.delete()
        item2.delete()

    def test_get_or_insert(self):
        item1 = TestModel.get_or_insert('test1', xstring='foo')
        self.assert_(isinstance(item1, TestModel))
        test = TestModel.get_or_insert('test1')
        self.assertEqual(item1, test)
        self.assertEqual(item1.xstring, 'foo')
        item1.delete()

    def test_all(self):
        self.assertEqual(len(TestModel.all()), 1)
        item1 = TestModel.get_or_insert('test1')
        self.assertEqual(len(TestModel.all()), 2)
        self.assert_(item1 in TestModel.all())
        item1.delete()

    def test_gql(self):
        item1 = TestModel.get_or_insert('test1', xstring='foo')
        item2 = TestModel.get_or_insert('test2', xstring='foo')
        results = TestModel.gql('WHERE xstring = \'foo\'')
        self.assertEqual(results.count(), 2)
        self.assert_(item1 in results)
        self.assert_(item2 in results)
        item1.delete()
        item2.delete()

    def test_kind(self):
        self.assertEqual(TestModel.kind(), TestModel._meta.db_table)

    def test_properties(self):
        props = TestModel.properties()
        self.assert_('xstring' in props)
        self.assert_(isinstance(props['xstring'], db.StringProperty))
        self.assert_('gae_parent_id' not in props)

    # Instance methods

    def test_key(self):
        key = self.item1.key()
        self.assert_(isinstance(key, db.Key))

    def test_key_multiple_calls(self):
        # make sure multiple calls to key() return the same instance of Key
        # see issue8
        key1 = self.item1.key()
        key2 = self.item1.key()
        self.assertEqual(id(key1), id(key2),
                         ('Multiple calls to Model.key() returned different'
                          ' objects: %s %s.' % (id(key1), id(key2))))


class TestListProperty(unittest.TestCase):

    def test_listproperty_save_restore(self):
        obj = TestModel()
        obj.xlist = ["foo", "bar", "baz"]
        obj.save()
        tobj = TestModel.get_by_id(obj.key().id())
        self.assertEqual(tobj, obj)
        self.assertEqual(tobj.xlist, ["foo", "bar", "baz"])


class TestUserProperty(unittest.TestCase):

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

    def test_auto_current_user_add(self):
        c = Client()
        c.login(username='test', password='testpw')
        response = c.get('/')
        user = response.context['user']
        self.assert_(user is not None)
        obj = TestModel()
        obj.save()
        self.assertEqual(obj.xuser, user)

    def test_user_property_patched(self):
        c = Client()
        c.login(username='test', password='testpw')
        response = c.get('/')
        user = response.context['user']
        obj = TestModel()
        obj.save()
        self.assert_(callable(obj.xuser.email))
        self.assert_(hasattr(obj.xuser, 'nickname'))
        self.assert_(callable(obj.xuser.nickname))


class TestReferenceProperty(unittest.TestCase):

    def test_protected_attr(self):
        m = TestModel()
        m2 = TestModel2()
        m2.put()
        m.ref = m2
        m.put()
        self.assert_(hasattr(m, '_ref'))
        self.assert_(isinstance(m._ref, db.Key))
        self.assertEqual(m._ref, m2.key())
