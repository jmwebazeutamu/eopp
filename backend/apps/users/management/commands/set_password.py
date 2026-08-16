"""Set or rotate account passwords.

The supported way to change a password outside the admin. It goes through
`set_password`, so the hash matches what the login view expects, and through
`AUTH_PASSWORD_VALIDATORS`, so a weak password is refused here exactly as it
would be in the UI. `django-simple-history` records the change against the
account with a rationale (§9), and the axes lockout counter for the account is
cleared, since a password reset is the remedy for a locked-out user.

The password is never taken as a command-line argument: argv is visible to
`ps` and lands in shell history. It is typed at a hidden prompt, piped in on
stdin, or generated here.

    python manage.py set_password cm1                    # prompt twice, hidden
    python manage.py set_password cm1 --generate         # random, printed once
    python manage.py set_password cm1 --stdin            # read from a pipe
    python manage.py set_password --role CASE_MANAGER --generate
    python manage.py set_password --all --generate --noinput

`docker compose exec` needs no `-T` for the interactive prompt and *does* need
`-T` for `--stdin`; `scripts/set-password.sh` picks the right one.
"""

import getpass
import secrets
import string
import sys

from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.users.models import Role, User

# Unambiguous alphabet: no I/l/1, no O/0. These passwords get read off a screen
# and typed on a phone during field training, and a rejected login that is
# really a misread character wastes a support call.
ALPHABET = "".join(c for c in string.ascii_letters + string.digits if c not in "Il1O0")
GENERATED_LENGTH = 16

CHANGE_REASON = "Password set via manage.py set_password"


def generate_password():
    """A password long enough to clear the 12-character floor with margin."""
    return "".join(secrets.choice(ALPHABET) for _ in range(GENERATED_LENGTH))


class Command(BaseCommand):
    help = "Set or rotate the password for one account, a role, or every account."

    def add_arguments(self, parser):
        parser.add_argument(
            "username",
            nargs="?",
            help="Account to change. Omit only with --all or --role.",
        )
        parser.add_argument(
            "--all",
            action="store_true",
            help="Every account, including inactive ones and the superuser.",
        )
        parser.add_argument(
            "--role",
            choices=[r.value for r in Role],
            help="Every account holding this role.",
        )
        parser.add_argument(
            "--generate",
            action="store_true",
            help="Generate a distinct random password per account and print it once.",
        )
        parser.add_argument(
            "--stdin",
            action="store_true",
            help="Read one password from stdin and apply it to every selected account.",
        )
        parser.add_argument(
            "--skip-validators",
            action="store_true",
            help="Bypass AUTH_PASSWORD_VALIDATORS. Local demo accounts only.",
        )
        parser.add_argument(
            "--noinput",
            "--no-input",
            action="store_false",
            dest="interactive",
            help="Do not ask for confirmation before a bulk change.",
        )

    def handle(self, *args, **options):
        users = self.select_users(options)
        source = self.password_source(options, count=len(users))

        if len(users) > 1 and options["interactive"]:
            self.confirm(users)

        issued = []
        with transaction.atomic():
            for user in users:
                password = source(user)
                if not options["skip_validators"]:
                    try:
                        validate_password(password, user=user)
                    except ValidationError as exc:
                        raise CommandError(f"Password rejected for {user.username}: " + " ".join(exc.messages))
                user.set_password(password)
                user._change_reason = CHANGE_REASON
                user.save(update_fields=["password"])
                issued.append((user, password))

        self.reset_lockouts(issued)
        self.report(issued, generated=options["generate"])

    # -- selection ---------------------------------------------------------

    def select_users(self, options):
        username, role, everyone = options["username"], options["role"], options["all"]

        if sum(bool(x) for x in (username, role, everyone)) != 1:
            raise CommandError("Give exactly one of: a username, --role, or --all.")

        if username:
            try:
                return [User.objects.get(username=username)]
            except User.DoesNotExist:
                raise CommandError(f"No account with username {username!r}.")

        queryset = User.objects.all() if everyone else User.objects.filter(role=role)
        users = list(queryset.order_by("username"))
        if not users:
            raise CommandError(f"No accounts match role {role!r}.")
        return users

    # -- where the password comes from -------------------------------------

    def password_source(self, options, count):
        """Return a callable that yields the password for a given user."""
        if sum(bool(options[k]) for k in ("generate", "stdin")) > 1:
            raise CommandError("--generate and --stdin are mutually exclusive.")

        if options["generate"]:
            return lambda user: generate_password()

        if options["stdin"]:
            password = sys.stdin.readline().rstrip("\n")
            if not password:
                raise CommandError("No password on stdin.")
            return lambda user: password

        if not sys.stdin.isatty():
            raise CommandError(
                "No terminal for the password prompt. Use --generate, or --stdin " "with `docker compose exec -T`."
            )
        if count > 1:
            self.stdout.write(self.style.WARNING(f"The password you type will be applied to all {count} accounts."))
        password = getpass.getpass("New password: ")
        if password != getpass.getpass("Confirm password: "):
            raise CommandError("The two entries do not match.")
        if not password:
            raise CommandError("Empty password.")
        return lambda user: password

    # -- confirmation, side effects, output ---------------------------------

    def confirm(self, users):
        if not sys.stdin.isatty():
            raise CommandError(
                f"Refusing to change {len(users)} accounts without confirmation. "
                "Re-run with --noinput if that is intended."
            )
        self.stdout.write(f"About to change the password for {len(users)} accounts:")
        for user in users:
            self.stdout.write(f"  {user.username} ({user.role})")
        if input("Type 'yes' to continue: ") != "yes":
            raise CommandError("Aborted.")

    def reset_lockouts(self, issued):
        """Clear axes failure records — a reset password should log in at once."""
        try:
            from axes.utils import reset
        except ImportError:  # axes is in the fixed stack, but do not hard-fail on it
            return
        for user, _ in issued:
            reset(username=user.username)

    def report(self, issued, generated):
        if generated:
            width = max(len(user.username) for user, _ in issued)
            self.stdout.write("")
            for user, password in issued:
                self.stdout.write(f"  {user.username:<{width}}  {password}")
            self.stdout.write("")
            self.stdout.write(
                self.style.WARNING(
                    "Shown once — only the hash is stored. Record these now, and hand "
                    "them over on a channel you would be willing to show an auditor."
                )
            )
        self.stdout.write(self.style.SUCCESS(f"Password changed for {len(issued)} account(s)."))
