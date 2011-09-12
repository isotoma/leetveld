#!/usr/bin/python2.4
#
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

"""Loads all the _test.py files into the top level of the package.

This file is a hack around the fact that Django expects the tests "module" to
be a single tests.py file and cannot handle a tests package inside an
application.

All _test.py files inside this package are imported and any classes derived
from unittest.TestCase are then referenced from this file itself so that they
appear at the top level of the tests "module" that Django will import.
"""


import os
import re
import sys
import types
import unittest

from django.conf import settings


TEST_RE = r"^test_.*.py$"


# Search through every file inside this package.
test_names = []
test_dir = os.path.dirname(__file__)
for filename in os.listdir(test_dir):
    if not re.match(TEST_RE, filename):
        continue
    # Import the test file and find all TestClass clases inside it.
    test_module = __import__('gae2django.tests.%s' %
                             filename[:-3], {}, {},
                             filename[:-3])
    for name in dir(test_module):
        item = getattr(test_module, name)
        if not (isinstance(item, (type, types.ClassType)) and
                issubclass(item, unittest.TestCase)):
            continue
        # Found a test, bring into the module namespace.
        exec "%s = item" % name
        test_names.append(name)


# Hide everything other than the test cases from other modules.
__all__ = test_names



def test_runner_with_coverage(test_labels, verbosity=1, interactive=True,
                              extra_tests=[]):
    # This doesn't work with Django 1.4
    from django.test.simple import run_tests as django_test_runner
    import coverage

    coverage.use_cache(0)
    coverage.start()

    test_results = django_test_runner(test_labels, verbosity, interactive,
                                      extra_tests)

    coverage.stop()
    coverage_modules = [m.__file__ for k, m in sys.modules.iteritems()
                        if m and k.split('.')[0] in test_labels
                        and 'test' not in k]
    print
    print '='*80
    print 'Coverage results for %s' % ', '.join(test_labels)
    print '='*80
    coverage.report(coverage_modules, show_missing=1)
    coverage_html_dir = getattr(settings, 'COVERAGE_HTML_DIR', None)
    if coverage_html_dir is not None:
        coverage._the_coverage.html_report(coverage_modules,
                                           coverage_html_dir)

    return test_results
