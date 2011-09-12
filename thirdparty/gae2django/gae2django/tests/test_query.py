#
# Copyright 2010 Andi Albrecht <albrecht.andi@gmail.com>
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

from gae2django.models import RegressionTestModel as TestModel
from gae2django.models import RefTestModel as TestModel2


class QueryTest(unittest.TestCase):

    def setUp(self):
        TestModel.all().delete()
        self.item1 = TestModel(key_name='foo1')
        self.item1.put()

    def tearDown(self):
        self.item1.delete()
        self.item1 = None

    def test_refkey(self):
        # Regression for issue23.
        i1 = TestModel2()
        i1.put()
        i2 = TestModel()
        i2.ref = i1
        i2.put()
        q = TestModel.all()
        q.filter('ref =', i1.key())
        res = list(q.fetch(1000))
        self.assertEqual(len(res), 1)
        self.assertEqual(str(res[0].key()), str(i2.key()))
