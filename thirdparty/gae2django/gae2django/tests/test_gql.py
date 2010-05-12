# -*- coding: utf-8 -*-

import unittest

from gae2django.gaeapi.appengine.ext import db
from gae2django.models import RegressionTestModel as TestModel


class TestGQL(unittest.TestCase):

    def setUp(self):
        TestModel.objects.all().delete()

    def tearDown(self):
        TestModel.objects.all().delete()

    def test_query_listproperty(self):
        obj = TestModel()
        obj.xlist = ['foo', 'bar', 'baz']
        obj.save()
        query = db.GqlQuery(('SELECT * FROM RegressionTestModel'
                             ' WHERE xlist = :1'), 'foo')
        self.assertEqual(query.count(), 1)
        tobj = query.get()
        self.assertEqual(tobj.xlist, ['foo', 'bar', 'baz'])
        query = db.GqlQuery(('SELECT * FROM RegressionTestModel'
                             ' WHERE xlist = :1'), 'nomatch')
        self.assertEqual(query.count(), 0)
        tobj.xlist = ['bar', 'baz']
        tobj.save()
        query = db.GqlQuery(('SELECT * FROM RegressionTestModel'
                             ' WHERE xlist = :1'), 'foo')
        self.assertEqual(query.count(), 0)
