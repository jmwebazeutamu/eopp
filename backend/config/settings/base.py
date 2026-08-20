"""
Shared settings for the Economic Opportunities Pathway Platform (EOPP).

Spec: docs/YOUTH_EMPLOYMENT_PLATFORM_DEV_SPEC.md
Environment-specific overrides live in development.py and production.py.
"""

from pathlib import Path

from celery.schedules import crontab
from decouple import Csv, config

BASE_DIR = Path(__file__).resolve().parent.parent.parent

# --------------------------------------------------------------------------
# Core
# --------------------------------------------------------------------------

SECRET_KEY = config("DJANGO_SECRET_KEY")
DEBUG = config("DJANGO_DEBUG", default=False, cast=bool)
ALLOWED_HOSTS = config("DJANGO_ALLOWED_HOSTS", default="localhost,127.0.0.1", cast=Csv())

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Spec §4: every entity's `System ID` is a UUID primary key. Model definitions
# set this explicitly via apps.common.models.UUIDModel — the setting above only
# covers implicit keys on through-tables and third-party models.

AUTH_USER_MODEL = "users.User"

# --------------------------------------------------------------------------
# Applications
# --------------------------------------------------------------------------

DJANGO_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.postgres",
]

THIRD_PARTY_APPS = [
    "rest_framework",
    "rest_framework_simplejwt",
    "corsheaders",
    "django_filters",
    "drf_spectacular",
    "simple_history",
    "django_celery_beat",
    "axes",
]

# One Django app per entity group, built in the order spec §10 introduces them.
# Apps are added here as their sprint lands — an empty entry would break checks.
LOCAL_APPS = [
    "apps.common",  # abstract base models + shared enums (not a spec entity)
    "apps.users",  # Spec §4.12 User (Actor), §7 role model — Sprint 0
    "apps.locations",  # Location reference data — Sprint 1
    "apps.youth",  # Spec §4.1 Youth (Participant) — Sprint 1
    "apps.partners",  # Spec §4.11 Partner / Provider Organisation — Sprint 2
    "apps.cases",  # Spec §4.2 Case, §4.3 Profiling, §4.4 Pathway — Sprints 1-2
    "apps.referrals",  # Spec §4.6 Referral, §5 taxonomy, §6 state machine — Sprint 3
    "apps.alerts",  # Spec §4.13 Alert / Task, §6 system actions — Sprint 4
    "apps.training",  # Spec §4.5 Training Enrolment — Sprint 5
    "apps.placements",  # Spec §4.7 Placement + retention checkpoints — Sprint 5
    "apps.enterprises",  # Spec §4.8 Enterprise + milestones — Sprint 6
    "apps.followups",  # Spec §4.9 Follow-Up / Contact Log — Sprint 6
    "apps.grievances",  # Spec §4.10 Grievance — Sprint 6
    "apps.dashboard",  # Programme dashboard aggregation — no models of its own
    # PSNP 6 Women's Livelihoods Transformation. A second programme on the same
    # platform, not a later sprint of the first: its subject is a savings group
    # rather than a young person. See docs/wlt_module_handoff/ and the WLT
    # section of CLAUDE.md.
    "apps.wlt",
]

INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS

MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "simple_history.middleware.HistoryRequestMiddleware",  # §9: records the actor on every change
    "axes.middleware.AxesMiddleware",
]

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

# --------------------------------------------------------------------------
# Database
# --------------------------------------------------------------------------

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": config("DB_NAME", default="yep"),
        "USER": config("DB_USER", default="yep"),
        "PASSWORD": config("DB_PASSWORD"),
        "HOST": config("DB_HOST", default="db"),
        "PORT": config("DB_PORT", default="5432"),
        "CONN_MAX_AGE": config("DB_CONN_MAX_AGE", default=60, cast=int),
    }
}

# --------------------------------------------------------------------------
# Authentication
# --------------------------------------------------------------------------

AUTHENTICATION_BACKENDS = [
    "axes.backends.AxesStandaloneBackend",  # must precede the model backend
    "django.contrib.auth.backends.ModelBackend",
]

PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.Argon2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2PasswordHasher",
]

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 12}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

AXES_FAILURE_LIMIT = config("AXES_FAILURE_LIMIT", default=5, cast=int)
AXES_COOLOFF_TIME = config("AXES_COOLOFF_TIME", default=1, cast=int)  # hours
AXES_LOCKOUT_PARAMETERS = ["ip_address", "username"]

# --------------------------------------------------------------------------
# REST framework — spec §2 (DRF, JWT, drf-spectacular)
# --------------------------------------------------------------------------

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        # Refuses tokens issued before the password last changed, so changing
        # a password signs other devices out. See apps/users/authentication.py.
        "apps.users.authentication.PasswordChangeAwareJWTAuthentication",
        "rest_framework.authentication.SessionAuthentication",
    ),
    "DEFAULT_PERMISSION_CLASSES": ("rest_framework.permissions.IsAuthenticated",),
    "DEFAULT_FILTER_BACKENDS": (
        "django_filters.rest_framework.DjangoFilterBackend",
        "rest_framework.filters.SearchFilter",
        "rest_framework.filters.OrderingFilter",
    ),
    "DEFAULT_PAGINATION_CLASS": "apps.common.pagination.StandardPagination",
    "PAGE_SIZE": 25,
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "DEFAULT_VERSIONING_CLASS": "rest_framework.versioning.NamespaceVersioning",
}

from datetime import timedelta  # noqa: E402

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=config("JWT_ACCESS_MINUTES", default=60, cast=int)),
    # Long refresh window: §9 field staff work offline for extended stretches and
    # must not be forced to re-authenticate mid-visit in a low-connectivity woreda.
    "REFRESH_TOKEN_LIFETIME": timedelta(days=config("JWT_REFRESH_DAYS", default=14, cast=int)),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": False,
    "UPDATE_LAST_LOGIN": True,
    "USER_ID_FIELD": "id",
    "USER_ID_CLAIM": "user_id",
}

SPECTACULAR_SETTINGS = {
    "TITLE": "Economic Opportunities Pathway Platform API",
    "DESCRIPTION": (
        "Case management and referral engine for the Ethiopia youth employment "
        "pilot. See docs/YOUTH_EMPLOYMENT_PLATFORM_DEV_SPEC.md."
    ),
    "VERSION": "0.1.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "COMPONENT_SPLIT_REQUEST": True,
    "SCHEMA_PATH_PREFIX": "/api/v1",
}

CORS_ALLOWED_ORIGINS = config(
    "CORS_ALLOWED_ORIGINS",
    default="http://localhost:8100,http://127.0.0.1:8100",
    cast=Csv(),
)

# --------------------------------------------------------------------------
# Celery — spec §2: stall detection, onward/replacement prompts, retention reminders
# --------------------------------------------------------------------------

CELERY_BROKER_URL = config("CELERY_BROKER_URL", default="redis://redis:6379/0")
CELERY_RESULT_BACKEND = config("CELERY_RESULT_BACKEND", default="redis://redis:6379/1")
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TIMEZONE = "Africa/Addis_Ababa"
CELERY_TASK_TRACK_STARTED = True
CELERY_TASK_TIME_LIMIT = 30 * 60
CELERY_BEAT_SCHEDULER = "django_celery_beat.schedulers:DatabaseScheduler"
CELERY_TASK_DEFAULT_QUEUE = "default"

# Spec §10 Sprint 4. DatabaseScheduler syncs these into django_celery_beat's
# tables on startup, so they are version-controlled here rather than typed into
# the admin, while remaining adjustable there without a deploy.
#
# Daily rather than hourly: every condition these detect is measured in days
# (§4.13 thresholds), so a tighter cadence would only add load. Times are EAT
# and sit before the working day so an alert is waiting when staff log in.
CELERY_BEAT_SCHEDULE = {
    "detect-stalled-cases": {
        "task": "alerts.detect_stalled_cases",
        "schedule": crontab(hour=5, minute=0),
    },
    "detect-overdue-confirmations": {
        "task": "alerts.detect_overdue_confirmations",
        "schedule": crontab(hour=5, minute=10),
    },
    "generate-onward-prompts": {
        "task": "alerts.generate_onward_prompts",
        "schedule": crontab(hour=5, minute=20),
    },
    "generate-replacement-prompts": {
        "task": "alerts.generate_replacement_prompts",
        "schedule": crontab(hour=5, minute=30),
    },
    # Closes referrals no partner ever answered. A no-op until
    # REFERRAL_ABANDONMENT_DAYS is set (OQ-13), so it is safe to schedule now:
    # the threshold is programme management's decision, not a deploy.
    "fail-abandoned-referrals": {
        "task": "alerts.fail_abandoned_referrals",
        "schedule": crontab(hour=5, minute=40),
    },
    # Sprint 5. Both read a condition and materialise it; neither creates case
    # data, per §5.2 — a retention check is answered by the person who makes the
    # call, and an onward referral is a case manager's decision.
    # Sprint 6. §4.13's last undetected type: an Active referral nobody has
    # followed up. Reads a condition and materialises it; it does not contact
    # anybody, which is the case manager's job and the point of the alert.
    "detect-follow-ups-due": {
        "task": "alerts.detect_follow_ups_due",
        "schedule": crontab(hour=5, minute=50),
    },
    "detect-retention-checks-due": {
        "task": "alerts.detect_retention_checks_due",
        "schedule": crontab(hour=5, minute=45),
    },
    "generate-training-onward-prompts": {
        "task": "alerts.generate_training_onward_prompts",
        "schedule": crontab(hour=5, minute=25),
    },
    # Runs more often than detection: clearing a resolved alert out of somebody's
    # inbox promptly is what stops the inbox being ignored.
    "resolve-cleared-alerts": {
        "task": "alerts.resolve_cleared_alerts",
        "schedule": crontab(minute=0, hour="*/4"),
    },
    # WLT group module. Every one of these observes; none of them decides.
    # Dormancy and at-risk are descriptions of the data and reverse themselves
    # when the data changes; nothing here graduates a group or fails a linkage
    # a person has not looked at.
    #
    # Later in the morning than the alert jobs so the two do not contend for the
    # same worker, and because nobody reads a group's readiness before dawn.
    "wlt-refresh-group-indicators": {
        "task": "apps.wlt.tasks.refresh_group_indicators",
        "schedule": crontab(hour=6, minute=0),
    },
    "wlt-expire-formations": {
        "task": "apps.wlt.tasks.expire_formations",
        "schedule": crontab(hour=6, minute=15),
    },
    "wlt-lapse-linkages": {
        "task": "apps.wlt.tasks.lapse_linkages",
        "schedule": crontab(hour=6, minute=20),
    },
    "wlt-review-blacklisted-providers": {
        "task": "apps.wlt.tasks.review_blacklisted_providers",
        "schedule": crontab(hour=6, minute=25),
    },
    # After the sweeps, so the views describe the state the sweeps left.
    "wlt-refresh-reporting": {
        "task": "apps.wlt.tasks.refresh_reporting_views",
        "schedule": crontab(hour=6, minute=40),
    },
}

# --------------------------------------------------------------------------
# Object storage — spec §2: MinIO, self-hosted, data stays in-country
# --------------------------------------------------------------------------

STORAGES = {
    "default": {
        "BACKEND": "storages.backends.s3.S3Storage",
        "OPTIONS": {
            "endpoint_url": config("MINIO_ENDPOINT_URL", default="http://minio:9000"),
            "access_key": config("MINIO_ACCESS_KEY", default="minioadmin"),
            "secret_key": config("MINIO_SECRET_KEY", default="minioadmin"),
            "bucket_name": config("MINIO_BUCKET", default="yep-media"),
            "default_acl": None,
            "querystring_auth": True,
            "file_overwrite": False,
        },
    },
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
}

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_URL = "/media/"

# --------------------------------------------------------------------------
# Internationalisation
# --------------------------------------------------------------------------

LANGUAGE_CODE = "en-us"
TIME_ZONE = "Africa/Addis_Ababa"
USE_I18N = True
USE_TZ = True

# Amharic and regional-language locales are not in scope for the pilot, but every
# user-facing string goes through gettext so adding them later is a translation
# job rather than a code change.
LANGUAGES = [("en", "English")]
LOCALE_PATHS = [BASE_DIR / "locale"]

# --------------------------------------------------------------------------
# Platform business rules (configurable — spec §11 leaves these to Phase 1)
# --------------------------------------------------------------------------

# Spec §11. STALL_ALERT_THRESHOLD_DAYS is still a placeholder; the other two
# were settled with programme management on 2026-08-18 and carry their reasons
# below. All three remain one-line changes.
# TODO(open-question): STALL_ALERT_THRESHOLD_DAYS is not yet agreed.
STALL_ALERT_THRESHOLD_DAYS = config("STALL_ALERT_THRESHOLD_DAYS", default=30, cast=int)
# Settled 2026-08-18 at 14 days, from the pilot's own evidence rather than the
# original placeholder of 7.
#
# Partners answer in a median of 8-10 days when they answer at all. A 7-day
# threshold therefore flags most referrals as overdue — the review measured 418
# open alerts against 540 cases, four in five — and a queue where almost
# everything is overdue prioritises nothing. 14 days flags roughly the slowest
# quartile, which is what a threshold is for. It also removes a contradiction:
# the dashboards stated a 14-day programme standard while the alert engine used
# 7, so the same referral was simultaneously on time and overdue.
REFERRAL_CONFIRMATION_OVERDUE_DAYS = config("REFERRAL_CONFIRMATION_OVERDUE_DAYS", default=14, cast=int)
CASELOAD_CEILING = config("CASELOAD_CEILING", default=50, cast=int)

# OQ-13, settled 2026-08-18. §6.2 offers no exit from
# Pending Confirmation except partner action or a case manager cancelling, so a
# referral nobody answers sits there forever — holding a slot against the §6.3
# parallel cap and dragging the loop-closure denominator down permanently.
#
# Settled 2026-08-18 at 60 days — four times the 14-day standard.
#
# Chosen to sit far enough past the threshold that it cannot catch a partner who
# is merely slow: at a median response of 8-10 days, 60 days is six medians. It
# is also inside a quarter, so a stranded referral frees its §6.3 slot within the
# reporting period rather than after it.
#
# Failing a referral is recoverable, which is what makes an automatic rule
# acceptable: the case keeps its history, `PARTNER_NON_RESPONSIVE` records why,
# and §6.2 allows a replacement referral immediately. Set to 0 or empty to
# disable the sweep.
REFERRAL_ABANDONMENT_DAYS = config("REFERRAL_ABANDONMENT_DAYS", default=60, cast=lambda v: int(v) if v else None)

# TODO(open-question): the dashboard's headline card reads "N of TARGET this
# quarter". The handoff's mockup shows 180, which is mockup data — the real
# quarterly placement target is a programme commitment nobody has stated to us.
# Set to 0 to hide the target and show the count alone rather than measure the
# programme against a number we invented.
PLACEMENT_TARGET_PER_QUARTER = config("PLACEMENT_TARGET_PER_QUARTER", default=0, cast=int)

# §4.13 alert thresholds. Both entities now exist; the values do not.
#
# TODO(open-question): §11 — neither of these is an agreed programme standard.
# 14 days is the referral confirmation standard reused for follow-up, and 30 is
# the first retention checkpoint. Both want the same conversation the
# confirmation threshold had on 2026-08-18, and both are one-line changes.
FOLLOW_UP_DUE_DAYS = config("FOLLOW_UP_DUE_DAYS", default=14, cast=int)  # Follow-Up (§4.9)
RETENTION_CHECK_DUE_DAYS = config("RETENTION_CHECK_DUE_DAYS", default=30, cast=int)  # Placement (§4.7)

# How long a grievance may sit before it is overdue (§4.10).
#
# TODO(open-question): §11 — there is no stated grievance service standard. 21
# days is the working default, chosen because it is inside a month and outside a
# fortnight: a complaints channel that answers in three weeks is slow but real,
# and one that has not answered in six is not a channel.
GRIEVANCE_RESPONSE_DAYS = config("GRIEVANCE_RESPONSE_DAYS", default=21, cast=int)

# CM-4's fourth at-risk condition (§5): how many failed contact attempts before
# a youth counts as unreachable. The spec says "4+", which is where this comes
# from — it is the one CM-4 threshold the spec actually states.
FAILED_CONTACT_ATTEMPTS_AT_RISK = config("FAILED_CONTACT_ATTEMPTS_AT_RISK", default=4, cast=int)

# Spec §6.3: at most two Active referrals may share a parallel_group_id.
MAX_PARALLEL_ACTIVE_REFERRALS = 2

# TODO(open-question): spec §4.1 says date_of_birth confirms "youth age band
# eligibility" but never states the band. 15-29 is the common Ethiopian
# definition; confirm with programme management. Registration outside the band
# is warned about, not blocked — see apps.youth.serializers.
YOUTH_AGE_MIN = config("YOUTH_AGE_MIN", default=15, cast=int)
YOUTH_AGE_MAX = config("YOUTH_AGE_MAX", default=29, cast=int)

# TODO(open-question): spec §6.3 / §11 — working default is that Complementary
# Service referrals sit OUTSIDE the two-referral cap as a third concurrent
# stream. Flagged as a policy decision pending Phase 1 sign-off.
COMPLEMENTARY_SERVICE_EXEMPT_FROM_PARALLEL_CAP = True

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {"verbose": {"format": "{levelname} {asctime} {name} {message}", "style": "{"}},
    "handlers": {"console": {"class": "logging.StreamHandler", "formatter": "verbose"}},
    "root": {"handlers": ["console"], "level": config("DJANGO_LOG_LEVEL", default="INFO")},
}
