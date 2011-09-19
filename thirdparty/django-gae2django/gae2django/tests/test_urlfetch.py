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

from gae2django.gaeapi.appengine.api import urlfetch


class URLFetchTest(unittest.TestCase):
    """Tests URL fetch API."""

    def test_response(self):
        """Tests the Resonse object."""
        response = urlfetch.fetch('http://www.google.com')
        assert 'Google' in response.content
        assert response.content_was_truncated == False
        assert response.status_code == 200
        assert type(response.headers) == types.DictType

    def test_response404(self):
        response = urlfetch.fetch('http://www.google.com/404')
        assert response.status_code == 404

    def test_invalid_protocol(self):
        self.assertRaises(urlfetch.InvalidURLError,
                          urlfetch.fetch, 'ftp://example.com/README.txt')
