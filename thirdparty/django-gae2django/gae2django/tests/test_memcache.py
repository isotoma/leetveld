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

from gae2django.gaeapi.appengine.api import memcache


class MemcacheTest(unittest.TestCase):
    """Tests memcache API."""

    def test_set_get(self):
        memcache.set('foo', 'bar')
        assert memcache.get('foo') == 'bar'
        assert memcache.get('DOES_NOT_EXIST') == None

    def test_set_multi(self):
        memcache.set_multi({'multi1': 1, 'multi2': 2})
        assert memcache.get('multi1') == 1
        assert memcache.get('multi2') == 2
        memcache.set_multi({'multi1': 3, 'multi2': 4}, key_prefix='x_')
        assert memcache.get('multi1') == 1
        assert memcache.get('multi2') == 2
        assert memcache.get('x_multi1') == 3
        assert memcache.get('x_multi2') == 4

    def test_get_multi(self):
        memcache.delete('DOES_NOT_EXIST')
        memcache.set('foo', 'bar')
        memcache.set('bar', 'foo')
        result = memcache.get_multi(['foo', 'bar', 'DOES_NOT_EXIST'])
        assert result['foo'] == 'bar'
        assert result['bar'] == 'foo'
        assert ('DOES_NOT_EXIST' in result) == False
        memcache.delete('foo')
        memcache.delete('bar')
        memcache.set('x_foo', 'bar')
        memcache.set('x_bar', 'foo')
        result = memcache.get_multi(['foo', 'bar'], key_prefix='x_')
        assert result['foo'] == 'bar'
        assert result['bar'] == 'foo'

    def test_delete(self):
        memcache.set('foo', 'bar')
        assert memcache.delete('foo') == 2
        assert memcache.delete('DOES_NOT_EXIST') == 1

    def test_delete_multi(self):
        memcache.set('foo', 'bar')
        assert memcache.delete_multi(['foo']) == True
        memcache.set('foo', 'bar')
        assert memcache.delete_multi(['foo', 'DOES_NOT_EXIST']) == False
        assert memcache.get('foo') == None

    def test_add(self):
        memcache.delete('foo') # make sure it doesn't exist
        assert memcache.add('foo', 'bar') == True
        assert memcache.get('foo') == 'bar'
        assert memcache.add('foo', 'bar2') == False
        assert memcache.get('foo') == 'bar'

    def test_replace(self):
        memcache.add('foo', 'bar')
        assert memcache.replace('foo', 123) == True
        assert memcache.get('foo') == 123
        assert memcache.replace('DOES_NOT_EXIST', 123) == False

    def test_incr(self):
        memcache.set('incr', 1L)
        assert memcache.incr('incr', 1) == 2L
        assert memcache.incr('incr', 2) == 4L
        assert memcache.incr('DOES_NOT_EXIST', 1) == None
        memcache.set('foo', 'bar')
        assert memcache.incr('foo', 1) == None

    def test_decr(self):
        memcache.set('decr', 2)
        assert memcache.decr('decr', 1) == 1
        assert memcache.decr('DOES_NOT_EXIST', 1) == None

    def test_flush_all(self):
        assert memcache.flush_all() == False

    def test_get_stats(self):
        stats = memcache.get_stats()
        assert type(stats) == types.DictType
        assert 'hits' in stats
        assert 'misses' in stats
        assert 'byte_hits' in stats
        assert 'items' in stats
        assert 'bytes' in stats
        assert 'oldest_item_age' in stats
        assert len(stats) == 6

    def test_client(self):
        client = memcache.Client()
        assert isinstance(client, memcache.Client)
