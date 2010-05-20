# Django settings for django_gae2django project.

import os
import gae2django
gae2django.install()

# NOTE: Keep the settings.py in examples directories in sync with this one!

DEBUG = True
TEMPLATE_DEBUG = DEBUG

ADMINS = (
    # ('Your Name', 'your_email@domain.com'),
)

MANAGERS = ADMINS

DATABASE_ENGINE = 'postgresql_psycopg2'    # 'postgresql_psycopg2', 'postgresql', 'mysql', 'sqlite3' or 'oracle'.
DATABASE_NAME = 'leetveld'       # Or path to database file if using sqlite3.
DATABASE_USER = 'leetveld'             # Not used with sqlite3.
DATABASE_PASSWORD = 'leetveld'         # Not used with sqlite3.
DATABASE_HOST = 'localhost'             # Set to empty string for . Not used with sqlite3.
DATABASE_PORT = '5432'             # Set to empty string for default. Not used with sqlite3.

# Local time zone for this installation. Choices can be found here:
# http://en.wikipedia.org/wiki/List_of_tz_zones_by_name
# although not all choices may be available on all operating systems.
# If running in a Windows environment this must be set to the same as your
# system time zone.
TIME_ZONE = 'Europe/London'

# Language code for this installation. All choices can be found here:
# http://www.i18nguy.com/unicode/language-identifiers.html
LANGUAGE_CODE = 'en-GB'

SITE_ID = 1

# If you set this to False, Django will make some optimizations so as not
# to load the internationalization machinery.
USE_I18N = True

# Absolute path to the directory that holds media.
# Example: "/home/media/media.lawrence.com/"
MEDIA_ROOT = os.path.join(os.path.dirname(__file__), '..', 'static')

# URL that handles the media served from MEDIA_ROOT. Make sure to use a
# trailing slash if there is a path component (optional in other cases).
# Examples: "http://media.lawrence.com", "http://example.com/media/"
MEDIA_URL = ''

# URL prefix for admin media -- CSS, JavaScript and images. Make sure to use a
# trailing slash.
# Examples: "http://foo.com/media/", "/media/".
ADMIN_MEDIA_PREFIX = '/media/'

# Make this unique, and don't share it with anybody.
SECRET_KEY = 'el@4s$*(idwm5-87teftxlksckmy8$tyo7(tm!n-5x)zeuheex'

# List of callables that know how to import templates from various sources.
TEMPLATE_LOADERS = (
    'django.template.loaders.filesystem.load_template_source',
    'django.template.loaders.app_directories.load_template_source',
#     'django.template.loaders.eggs.load_template_source',
)

MIDDLEWARE_CLASSES = (
    'django.middleware.common.CommonMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'gae2django.middleware.FixRequestUserMiddleware',
    'rietveld_helper.middleware.AddUserToRequestMiddleware',
    'django.middleware.doc.XViewMiddleware',
    'djangologging.middleware.LoggingMiddleware',
)

ROOT_URLCONF = 'rietveld_helper.urls'

INTERNAL_IPS = ('127.0.0.1',)

TEMPLATE_DIRS = (
    os.path.join(os.path.dirname(__file__), '..', 'templates'),
)

INSTALLED_APPS = (
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.sites',
    'django.contrib.admin',
    'gae2django',
    'rietveld_helper',
    'codereview',
)

AUTH_PROFILE_MODULE = 'codereview.Account'
LOGIN_REDIRECT_URL = '/'

# This won't work with gae2django.
RIETVELD_INCOMING_MAIL_ADDRESS = None

# Uncomment the following to lines to run unittests with coverage reports.
#TEST_RUNNER = 'gae2django.tests.test_runner_with_coverage'
#COVERAGE_HTML_DIR = 'coverage_report'
