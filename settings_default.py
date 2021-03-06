# -*- coding: utf-8 -*-

import os.path


DEBUG = False
TEMPLATE_DEBUG = DEBUG
THUMBNAIL_DEBUG = DEBUG

PROJECT_PATH = os.path.dirname(os.path.abspath(__file__))

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.mysql',
        'NAME': 'ibidgames-local',
        'USER': 'root',
        'PASSWORD': '',
        'HOST': 'localhost',
        'PORT': '',
    }
}

DEFAULT_FROM_EMAIL = 'info@ibidgames.com'
SERVER_EMAIL = 'info@ibidgames.com'

EMAIL_HOST = 'smtp.gmail.com'
EMAIL_PORT = 587
EMAIL_HOST_USER = 'test@nuske.com.ar'
EMAIL_HOST_PASSWORD = 'test test'
EMAIL_USE_TLS = True

ADMINS = (
    ('Daniel', 'dnuske@gmail.com'),
)
MANAGERS = ADMINS

ALLOWED_HOSTS = ('localhost:8000', 'localhost', '127.0.0.1','dev.ibidgames.com')

#AUTHENTICATION_BACKENDS = ('django.contrib.auth.backends.ModelBackend',
#                           'django_facebook.auth_backends.FacebookBackend',)

AUTHENTICATION_BACKENDS = (
    'django_facebook.auth_backends.FacebookBackend',
    'django.contrib.auth.backends.ModelBackend',
    'social_auth.backends.google.GoogleOAuth2Backend',
    

)
AUTH_USER_MODEL="bidding.Member"
SOCIAL_AUTH_USER_MODEL = 'bidding.Member'
#AUTH_USER_MODEL="auth.User"
#AUTH_PROFILE_MODULE = 'bidding.member'
#ABSOLUTE_URL_OVERRIDES = {
#    'auth.user': lambda o: '/bids/user/%s/' % o.username
#}

# Local time zone for this installation. Choices can be found here:
# http://en.wikipedia.org/wiki/List_of_tz_zones_by_name
# although not all choices may be available on all operating systems.
# If running in a Windows environment this must be set to the same as your
# system time zone.
TIME_ZONE = 'UTC'

# Language code for this installation. All choices can be found here:
# http://www.i18nguy.com/unicode/language-identifiers.html
LANGUAGE_CODE = 'en-us'

# If you set this to False, Django will make some optimizations so as not
# to load the internationalization machinery.
USE_I18N = False

SITE_ID = 1

# Media files
MEDIA_ROOT = os.path.join(PROJECT_PATH, 'media')
MEDIA_URL = '/media/'

# Static files
STATICFILES_DIRS = (
    os.path.join(PROJECT_PATH, 'static'),
)
STATIC_ROOT = os.path.join(PROJECT_PATH, 'public_static')
STATIC_URL = '/static/'
STATICFILES_STORAGE = 'django.contrib.staticfiles.storage.CachedStaticFilesStorage'

# Admin Static Files
ADMIN_MEDIA_PREFIX = '/static/admin/'

# Make this unique, and don't share it with anybody.
SECRET_KEY = 'q0zs)p0r6h2u1^b5ak55z)nuu^mvi*rd4jx6$!=++_xqv6s(aa'

# Cache backends
CACHE = {
    'staticfiles': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
        'LOCATION': 'public_static'
    }
}


TEMPLATE_LOADERS = (
    'django.template.loaders.filesystem.Loader',
    'django.template.loaders.app_directories.Loader',

)

MIDDLEWARE_CLASSES = (
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'bidding.middleware.SSLRedirect',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.contrib.flatpages.middleware.FlatpageFallbackMiddleware',
    'bidding.middleware.P3PHeaderMiddleware',
    'django.middleware.transaction.TransactionMiddleware',
    #'django_facebook.middleware.FacebookCanvasMiddleWare',
)

MESSAGE_STORAGE = 'django.contrib.messages.storage.cookie.CookieStorage'

TEMPLATE_CONTEXT_PROCESSORS = (
    'django.contrib.auth.context_processors.auth',
    'django.core.context_processors.debug',
    'django.core.context_processors.i18n',
    'django.core.context_processors.media',
    'django.core.context_processors.static',
    'django.core.context_processors.tz',
    'django.core.context_processors.request',
    'django.contrib.messages.context_processors.messages',
    'django_facebook.context_processors.facebook',
)

ROOT_URLCONF = 'urls'

TEMPLATE_DIRS = (
    os.path.join(PROJECT_PATH, 'templates'),
)

FIXTURE_DIRS = (
    os.path.join(PROJECT_PATH, 'data/fixtures'),
)

INSTALLED_APPS = (
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.flatpages',
    'django.contrib.messages',
    'django.contrib.sessions',
    'django.contrib.sites',
    'bidding',
    'south',
    'chat',
    'message',
    'admin_tools.theming',
    'admin_tools.menu',
    'admin_tools.dashboard',
    'paypal.standard.ipn',
    'sorl.thumbnail',
    'django_facebook',
    'django.contrib.staticfiles',
    'apps.audit',
    'apps.main',
    'tastypie',
    'rest_framework',
    'rest_framework_swagger',
    'social_auth',

)



LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '%(levelname)s [%(asctime)s] %(module)s %(message)s'
        },
        'simple': {
            'format': '%(levelname)s %(message)s'
        },
    },
    'filters': {
        'require_debug_false': {
                 '()': 'django.utils.log.RequireDebugFalse',
        }
    },
    'handlers': {
        'console': {
            'level': 'DEBUG',
            'class': 'logging.StreamHandler',
            'formatter': 'simple'
        },
        'file': {
            'class': 'logging.handlers.RotatingFileHandler',
            'formatter': 'verbose',
            'filename': '/var/www/facebook.ibidgames.com/logs/ibiddjango.log',
            'maxBytes': 1024000,
            'backupCount': 3,
        },
        'sql': {
            'class': 'logging.handlers.RotatingFileHandler',
            'formatter': 'verbose',
            'filename': '/var/www/facebook.ibidgames.com/logs/sql.log',
            'maxBytes': 102400,
            'backupCount': 3,
        },
        'commands': {
            'class': 'logging.handlers.RotatingFileHandler',
            'formatter': 'verbose',
            'filename': '/var/www/facebook.ibidgames.com/logs/commands.log',
            'maxBytes': 10240,
            'backupCount': 3,
        },
        'mail_admins': {
             'level': 'ERROR',
             'filters': ['require_debug_false'],
             'class': 'django.utils.log.AdminEmailHandler'
        },
        'open_facebook.api': {
             'level': 'INFO',
             'class': 'django.utils.log.AdminEmailHandler'
        }
    },
    'loggers': {
        'django': {
            'handlers': ['file', 'console', 'mail_admins'],
            'propagate': True,
            'level': 'DEBUG',
        },
        'django.db.backends': {
            'handlers': ['sql', 'console'],
            'propagate': False,
            'level': 'WARNING',
        },
        'scheduling': {
            'handlers': ['commands', 'console'],
            'propagate': True,
            'level': 'DEBUG',
        },
    }
}


LOGIN_REDIRECT_URL = "/"
EMAIL_CONFIRMATION_DAYS = 5
PERSISTENT_SESSION_KEY = 'sessionpersistent'


# SSL Configuration
CSRF_COOKIE_SECURE = True
SESSION_COOKIE_SECURE = True


ADMIN_TOOLS_MENU = 'lib.admtools.menu.CustomMenu'
ADMIN_TOOLS_INDEX_DASHBOARD = 'lib.admtools.dashboard.CustomIndexDashboard'


# Facebook settings
FACEBOOK_API_KEY = ''
FACEBOOK_APP_ID = ''
FACEBOOK_APP_SECRET = ''
FACEBOOK_APP_NAME = 'ibidgames'
FACEBOOK_FORCE_PROFILE_UPDATE_ON_LOGIN = True
FACEBOOK_REGISTRATION_BACKEND = 'authbackends.YambidRegistration'
FACEBOOK_AUTH_URL          = 'https://www.facebook.com/dialog/oauth?client_id={app}&redirect_uri={url}'
FACEBOOK_APP_URL           = 'https://apps.facebook.com/{appname}/'
FACEBOOK_CANVAS_HOME_URL   = 'https://apps.facebook.com/{appname}/canvashome/'
FACEBOOK_AUTH_REDIRECT_URL = FACEBOOK_CANVAS_HOME_URL
FACEBOOK_DEFAULT_SCOPE = ['public_profile', 'user_friends']
# Needed by django-facebook to use the middleware with the canvas (django_facebook.canvas.py)
# It's the redirect url that the middleware sends when asking facebook for the permissions dialog
FACEBOOK_CANVAS_PAGE       = 'https://apps.facebook.com/ibidgames/canvashome/'


# PubNub settings
PUBNUB_PUB = 'pub-c-50278d15-1317-4bcb-92e2-d2981d99dcb8'
PUBNUB_SUB = 'sub-c-43c0f9be-df39-11e2-ab32-02ee2ddab7fe'
PUBNUB_SECRET = ''


# Application Urls
SITE_NAME = "https://apps.facebook.ibidgames.com/"
SITE_NAME_WOUT_BACKSLASH = "https://apps.facebook.ibidgames.com"
IMAGES_SITE = SITE_NAME_WOUT_BACKSLASH


# App Settings
AUDIT_ENABLED = False
ERROR_REPORT_TITLE = "IBG ERROR REPORT"
PAGINATED_BY = 20
TODO_BID_PRICE = 5
TOKENS_TO_BIDS_RATE = 0.0001
PAYPAL_RECEIVER_EMAIL = 'payment@ibidgames.com'

AUCTION_MAX_TOKENS = 120;

# Analytics keys
MIXPANEL_TOKEN = ''

# Tastypie settings (API)
TASTYPIE_DEFAULT_FORMATS = ['json']


# Swagger settings
SWAGGER_SETTINGS = {
     "exclude_namespaces": [],    #  List URL namespaces to ignore
     "enabled_methods": [ # Methods to enable in UI
         'get',
         'post',
         'put',
         'patch',
         'delete'
     ],
     "is_authenticated": True,
     "api_path": "/api/v1",
     
}

REST_FRAMEWORK = {
    # Use hyperlinked styles by default.
    # Only used if the `serializer_class` attribute is not set on a view.
    'DEFAULT_MODEL_SERIALIZER_CLASS':
        'rest_framework.serializers.HyperlinkedModelSerializer',

    # Use Django's standard `django.contrib.auth` permissions,
    # or allow read-only access for unauthenticated users.
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.DjangoModelPermissionsOrAnonReadOnly'
    ]
}

