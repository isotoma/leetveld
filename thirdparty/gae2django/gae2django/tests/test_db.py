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

from gae2django.gaeapi.appengine.ext import db
from gae2django.models import RegressionTestModel as TestModel


class KeyTest(unittest.TestCase):

    def setUp(self):
        self._test = TestModel(xstring="foo")
        self._test.put()
        self._key = self._test.key()
        self._test_name = TestModel(xstring="foo", key_name="fookey")
        self._test_name.put()
        self._key_name = self._test_name.key()

    def tearDown(self):
        self._test.delete()
        self._test_name.delete()
        self._test = self._key = None
        self._test_name = self._key_name = None

    # constructor

    def test_constructor(self):
        self.assertRaises(TypeError, db.Key, ('foo',), {'should': 'fail'})
        self.assertRaises(db.BadArgumentError, db.Key, (123,))
        self.assertRaises(db.BadArgumentError, db.Key, (range(2),))

    # class methods

    def test_from_path(self):
        self.assertRaises(db.BadArgumentError, db.Key.from_path,
                          ('foo', 1), should='fail')
        self.assertRaises(db.BadArgumentError, db.Key.from_path,
                          ('foo',))
        self.assertEqual(db.Key.from_path('RegressionTestModel',
                                          self._test.id), self._key)
        k = db.Key.from_path('RegressionTestModel', 'fookey')
        self.assertEqual(db.Key.from_path('RegressionTestModel', 'fookey'),
                         self._key_name)

    # instance methods

    def test_app(self):
        self.assertEqual(self._key.app(), 'gae2django')

    def test_kind(self):
        self.assertEqual(self._key.kind(), 'RegressionTestModel')

    def test_id(self):
        self.assertEqual(self._key.id(), self._test.id)
        self.assertEqual(self._key_name.id(), None)

    def test_name(self):
        self.assertEqual(self._key_name.name(), 'fookey')
        self.assertEqual(self._key.name(), None)

    def test_id_or_name(self):
        self.assertEqual(self._key.id_or_name(), self._test.id)
        self.assertEqual(self._key_name.id_or_name(), 'fookey')

    def test_has_id_or_name(self):
        self.assertEqual(self._key.has_id_or_name(), True)
        self.assertEqual(self._key_name.has_id_or_name(), True)

    def test_parent(self):
        t1 = TestModel(xstring="child", parent=self._test)
        t1.put()
        self.assertEqual(t1.key().parent(), self._key)
        t1.delete()
        t2 = TestModel(xstring="child", parent=self._test_name)
        t2.put()
        self.assertEqual(t2.key().parent(), self._key_name)
        t2.delete()

    # internals

    def test_compare(self):
        # see issue8
        k1 = db.Key('foo1')
        k2 = db.Key('foo1')
        self.assert_(k1 == k2, '%r doesn\'t compare equal to %r' % (k1, k2))
        self.assert_(k2 in set([k1]), 'set comparsion failed')
        self.assert_(not k1 is k2, 'is comparsion failed')

    def test__str__(self):
        k1 = db.Key('foo1')
        self.assertEqual('foo1', str(k1))


class TestQuery(unittest.TestCase):

    def setUp(self):
        TestModel.objects.all().delete()
        for i in range(3):
            obj = TestModel()
            obj.xstring = 'foo%d' % i
            obj.save()

    def tearDown(self):
        TestModel.objects.all().delete()

    def test_filter(self):
        q = TestModel.all()
        self.assert_(isinstance(q, db.Query))
        q = q.filter('xstring =', 'foo1')
        self.assert_(isinstance(q, db.Query))
        self.assertEqual(len(list(q)), 1)
        q = TestModel.all().filter('xstring =', 'foo')
        self.assert_(isinstance(q, db.Query))
        self.assertEqual(len(list(q)), 0)

    def test_query_get(self):
        q = TestModel.all()
        q = q.filter('xstring =', 'foo1')
        item = q.get()
        self.assert_(isinstance(item, TestModel))
        self.assertEqual(item.xstring, 'foo1')

    def test_query_get_empy(self):  # issue 11
        q = TestModel.all()
        q = q.filter('xstring =', 'doesnotexist')
        item = q.get()
        self.assertEqual(item, None)


class TestGqlQuery(unittest.TestCase):

    def setUp(self):
        TestModel.objects.all().delete()
        for i in range(10):
            obj = TestModel()
            obj.xstring = 'foo%d' % i
            obj.save()

    def tearDown(self):
        TestModel.objects.all().delete()

    def test_fetch(self):
        q = db.GqlQuery('SELECT * FROM RegressionTestModel')
        items = q.fetch(1000)
        self.assert_(isinstance(items, list))
        self.assertEqual(len(items), 10)
        q = db.GqlQuery('SELECT * FROM RegressionTestModel ORDER BY xstring')
        items = q.fetch(2)
        self.assertEqual(len(items), 2)
        q = db.GqlQuery('SELECT * FROM RegressionTestModel ORDER BY xstring')
        items = q.fetch(2)
        for i in range(2):
            self.assertEqual(items[i].xstring, 'foo%d' % i)
        # once again with offset
        q = db.GqlQuery('SELECT * FROM RegressionTestModel ORDER BY xstring')
        items = q.fetch(2, 4)
        for i in range(2):
            self.assertEqual(items[i].xstring, 'foo%d' % (i+4))
        q = db.GqlQuery('SELECT * FROM RegressionTestModel ORDER BY xstring')
        items = q.fetch(2, 100)
        self.assertEqual(len(items), 0)
