from settings import *

DEBUG = False

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql_psycopg2',
        'NAME': 'leetveld',
        'USER': 'leetveld',
        'PASSWORD': 'leetveld',
        'HOST': '',
        'PORT': '',
    }
}

LOG_FILE = '/var/log/leetveld/leetveld.log'

try:
    from private_settings import *
except ImportError:
    pass
