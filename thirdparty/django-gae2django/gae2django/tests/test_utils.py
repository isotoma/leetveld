# -*- coding: utf-8 -*-

import unittest

from gae2django.models import RegressionTestModel
from gae2django.utils import CallableString


class TestCallableString(unittest.TestCase):

    def test_unicode(self):
        x = CallableString(u"möhrenbrei")
        self.assertTrue(x == u"möhrenbrei")

    def test_callable(self):
        x = CallableString("foo")
        self.assertEqual(x(), "foo")
        self.assertEqual(x(), x)

    def test_dbwrite(self):
        # Note: This test mainly makes sense with PostgreSQL backend.
        obj = RegressionTestModel()
        obj.xstring = CallableString(u"möhrenbrei")
        obj.save()
