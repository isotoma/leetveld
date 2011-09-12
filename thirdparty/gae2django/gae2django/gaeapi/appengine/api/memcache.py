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

"""Implements the URL fetch API.

http://code.google.com/appengine/docs/memcache/
"""

from django.core.cache import cache


class Client(object):

    def set(self, key, value, time=0, min_compress_len=0):
        cache.set(key, value)
        return True

    def set_multi(self, mapping, time=0, key_prefix='', min_compress_len=0):
        [self.set('%s%s' % (key_prefix, key), mapping[key],
                  time, min_compress_len) for key in mapping]
        return []

    def get(self, key):
        return cache.get(key)

    def get_multi(self, keys, key_prefix=''):
        mapping = {}
        [mapping.setdefault(key, self.get('%s%s' % (key_prefix, key)))
         for key in keys
         if '%s%s' % (key_prefix, key) in cache]
        return mapping

    def delete(self, key, seconds=0):
        # TODO: Implement locking (seconds keyword).
        if key not in cache:
            return 1
        cache.delete(key)
        return 2

    def delete_multi(self, keys, seconds=0, key_prefix=''):
        succeeded = True
        for key in keys:
            if self.delete('%s%s' % (key_prefix, key), seconds) != 2:
                succeeded = False
        return succeeded

    def add(self, key, value, time=0, min_compress_len=0):
        return cache.add(key, value, time or None)

    def replace(self, key, value, time=0, min_compress_len=0):
        if key in cache:
            self.set(key, value, time, min_compress_len)
            return True
        return False

    def incr(self, key, delta=1):
        if key in cache:
            try:
                old = long(cache.get(key))
                new = old+delta
                cache.set(key, new)
                return new
            except ValueError:
                return None
        return None

    def decr(self, key, delta=1):
        return self.incr(key, delta*-1)

    def flush_all(self):
        # Django doesn't know all keys in cache. So let's raise an RPC error...
        return False

    def get_stats(self):
        # Again, Django doesn't have this information.
        return {'hits': 0,
                'misses': 0,
                'byte_hits': 0,
                'items': 0,
                'bytes': 0,
                'oldest_item_age': 0}

    def set_servers(self, servers):
        pass

    def disconnect_all(self):
        pass

    def forget_dead_hosts(self):
        pass

    def debuglog(self):
        pass


_CLIENT = None


def setup_cache(client_obj):
    global _CLIENT
    var_dict = globals()

    _CLIENT = client_obj
    var_dict['set_servers'] = _CLIENT.set_servers
    var_dict['disconnect_all'] = _CLIENT.disconnect_all
    var_dict['forget_dead_hosts'] = _CLIENT.forget_dead_hosts
    var_dict['debuglog'] = _CLIENT.debuglog
    var_dict['get'] = _CLIENT.get
    var_dict['get_multi'] = _CLIENT.get_multi
    var_dict['set'] = _CLIENT.set
    var_dict['set_multi'] = _CLIENT.set_multi
    var_dict['add'] = _CLIENT.add
    var_dict['replace'] = _CLIENT.replace
    var_dict['delete'] = _CLIENT.delete
    var_dict['delete_multi'] = _CLIENT.delete_multi
    var_dict['incr'] = _CLIENT.incr
    var_dict['decr'] = _CLIENT.decr
    var_dict['flush_all'] = _CLIENT.flush_all
    var_dict['get_stats'] = _CLIENT.get_stats

setup_cache(Client())
