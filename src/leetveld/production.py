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

LOGGING = {
    'version': 1,
    'formatters': {
        'verbose': {
            'format': '%(levelname)s %(asctime)s %(name)s %(process)d %(message)s',
        },
        'simple': {
            'format': '%(levelname)s %(message)s',
        },
    },
    'handlers': {
        'log_file': {
            'level': 'INFO',
            'class': 'logging.handlers.WatchedFileHandler',
            'filename': LOG_FILE,
            'formatter': 'verbose',
        },
        'console': {
            'level': 'INFO',
            'class': 'logging.StreamHandler',
            'formatter': 'simple',
        },
    },
    'loggers': {
        'django': {
            'handlers':['console'],
            'propagate': True,
            'level':'INFO',
        },
        'django.request': {
            'handlers': ['log_file', 'console'],
            'level': 'ERROR',
            'propagate': False,
        },
        'leetveld': {
            'handlers': ['log_file'],
            'level': 'INFO',
            'propagate': True,
        }
    }
}

try:
    from private_settings import *
except ImportError:
    pass
