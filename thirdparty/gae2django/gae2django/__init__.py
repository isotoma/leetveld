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

"""Provides a pure Django implementation of Google's App Engine API."""

import logging
import os
import sys

from gae2django.utils import CallableString


def install(server_software='gae2django'):
    """Imports the API and makes it available as 'google.appengine'."""
    import gaeapi
    sys.modules['google'] = gaeapi
    sys.modules['gaeapi'] = gaeapi
    os.environ['SERVER_SOFTWARE'] = server_software
    _install_pg_adapter()


def _install_pg_adapter():
    """Install a psycopg2 adapter to make use of callable strings."""
    # We cannot access settings during install() of gae2django.
    # So let's get proactive and try to register the adapter anyway.
    # See: http://code.djangoproject.com/ticket/5996
    try:
        import psycopg2.extensions
    except ImportError, err:
        return
    psycopg2.extensions.register_adapter(CallableString,
                                         psycopg2.extensions.QuotedString)
