"""JWT authentication that respects a password change.

simplejwt issues tokens that stay valid until they expire — here, an hour for
an access token and fourteen days for a refresh token. Nothing in that scheme
knows the password has changed, so before this a compromised session survived
the account holder changing their password, which is the one action a person
takes *because* they think they are compromised.

The blacklist app would only be half an answer: it records refresh tokens, so
a stolen access token would keep working for its remaining hour. Comparing the
token's issue time against `password_changed_at` covers both, needs no extra
tables and no cleanup job.
"""

from datetime import datetime, timedelta
from datetime import timezone as dt_timezone

from django.utils.translation import gettext_lazy as _
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import AuthenticationFailed

# A JWT's `iat` is whole seconds; `password_changed_at` carries microseconds.
# A token minted in the same second as the change therefore looks *older* than
# it, and without this the fresh pair handed back by the password-change
# endpoint would be refused on its first use — signing the user out at the
# exact moment they did the right thing.
CLOCK_GRANULARITY = timedelta(seconds=1)


class PasswordChangeAwareJWTAuthentication(JWTAuthentication):
    """Refuses any token issued before the account's password last changed."""

    def get_user(self, validated_token):
        user = super().get_user(validated_token)
        changed_at = getattr(user, "password_changed_at", None)
        if not changed_at:
            # Never changed since the column was added. Nothing to compare
            # against, so existing sessions are left alone rather than every
            # account being signed out by a deployment.
            return user

        issued_at = validated_token.get("iat")
        if issued_at is None:
            # A token with no issue time cannot be shown to post-date the
            # change, and this is the one place where "cannot tell" has to mean
            # "no".
            raise AuthenticationFailed(_("This session is no longer valid. Please sign in again."), code="stale_token")

        if datetime.fromtimestamp(issued_at, tz=dt_timezone.utc) < changed_at - CLOCK_GRANULARITY:
            raise AuthenticationFailed(_("This session is no longer valid. Please sign in again."), code="stale_token")

        return user
