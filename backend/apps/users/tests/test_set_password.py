"""Tests for `manage.py set_password`.

The guards matter more than the happy path here: this command can rewrite the
credentials of every account in the system in one call, so the cases that must
*refuse* are the ones worth pinning down.
"""

import io

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from apps.users.models import Role

pytestmark = pytest.mark.django_db


def run(*args, **options):
    out = io.StringIO()
    call_command("set_password", *args, stdout=out, stderr=out, **options)
    return out.getvalue()


# ---------------------------------------------------------------------------
# Setting a password
# ---------------------------------------------------------------------------


def test_stdin_password_is_applied(case_manager, monkeypatch):
    monkeypatch.setattr("sys.stdin", io.StringIO("Zebra-Marmalade-77\n"))
    run("cm-a", stdin=True)

    case_manager.refresh_from_db()
    assert case_manager.check_password("Zebra-Marmalade-77")
    assert not case_manager.check_password("pw-Test-12345")


def test_generate_prints_the_password_once_and_it_works(case_manager):
    output = run("cm-a", generate=True)

    password = output.split("cm-a")[1].split()[0]
    case_manager.refresh_from_db()
    assert case_manager.check_password(password)


def test_generated_passwords_differ_per_account(case_manager, other_case_manager):
    output = run(role=Role.CASE_MANAGER, generate=True, interactive=False)

    printed = [line.split()[1] for line in output.splitlines() if line.startswith("  cm-")]
    assert len(printed) == 2
    assert printed[0] != printed[1]


def test_change_is_recorded_in_history_with_a_rationale(case_manager):
    """§9 wants an actor and a rationale on record changes, not just a new hash."""
    run("cm-a", generate=True)

    latest = case_manager.history.order_by("-history_date").first()
    assert latest.history_change_reason == "Password set via manage.py set_password"


def test_role_selector_leaves_other_roles_alone(case_manager, supervisor):
    run(role=Role.CASE_MANAGER, generate=True, interactive=False)

    supervisor.refresh_from_db()
    assert supervisor.check_password("pw-Test-12345")


# ---------------------------------------------------------------------------
# Guards
# ---------------------------------------------------------------------------


def test_weak_password_is_rejected(case_manager, monkeypatch):
    monkeypatch.setattr("sys.stdin", io.StringIO("password\n"))
    with pytest.raises(CommandError, match="too short"):
        run("cm-a", stdin=True)

    case_manager.refresh_from_db()
    assert case_manager.check_password("pw-Test-12345")


def test_skip_validators_allows_a_weak_demo_password(case_manager, monkeypatch):
    monkeypatch.setattr("sys.stdin", io.StringIO("password\n"))
    run("cm-a", stdin=True, skip_validators=True)

    case_manager.refresh_from_db()
    assert case_manager.check_password("password")


def test_unknown_username_is_an_error(case_manager):
    with pytest.raises(CommandError, match="No account with username"):
        run("nosuchuser", generate=True)


def test_selectors_are_mutually_exclusive(case_manager):
    with pytest.raises(CommandError, match="exactly one"):
        run("cm-a", all=True, generate=True)


def test_no_selector_is_an_error(case_manager):
    with pytest.raises(CommandError, match="exactly one"):
        run(generate=True)


def test_bulk_change_refuses_without_a_terminal(case_manager, other_case_manager, monkeypatch):
    """The confirmation cannot be asked for over a pipe, so the change does not happen."""
    monkeypatch.setattr("sys.stdin", io.StringIO(""))
    with pytest.raises(CommandError, match="without confirmation"):
        run(all=True, generate=True)

    case_manager.refresh_from_db()
    assert case_manager.check_password("pw-Test-12345")


def test_all_includes_every_account(case_manager, supervisor, system_admin):
    run(all=True, generate=True, interactive=False)

    for user in (case_manager, supervisor, system_admin):
        user.refresh_from_db()
        assert not user.check_password("pw-Test-12345")


def test_generate_and_stdin_conflict(case_manager):
    with pytest.raises(CommandError, match="mutually exclusive"):
        run("cm-a", generate=True, stdin=True)


def test_empty_stdin_is_an_error(case_manager, monkeypatch):
    monkeypatch.setattr("sys.stdin", io.StringIO("\n"))
    with pytest.raises(CommandError, match="No password on stdin"):
        run("cm-a", stdin=True)


def test_generated_password_avoids_ambiguous_characters(case_manager):
    from apps.users.management.commands.set_password import generate_password

    for _ in range(50):
        assert not set(generate_password()) & set("Il1O0")


def test_password_is_never_read_from_argv(case_manager):
    """A password on the command line would land in `ps` output and shell history."""
    from apps.users.management.commands.set_password import Command

    parser = Command().create_parser("manage.py", "set_password")
    positionals = [a.dest for a in parser._actions if not a.option_strings]
    assert positionals == ["username"]


def test_lockout_counter_is_cleared(case_manager, monkeypatch):
    cleared = []
    monkeypatch.setattr("axes.utils.reset", lambda **kwargs: cleared.append(kwargs))
    run("cm-a", generate=True)

    assert cleared == [{"username": "cm-a"}]


def test_no_account_matches_role(db):
    with pytest.raises(CommandError, match="No accounts match role"):
        run(role=Role.TRAINER, generate=True)


def test_nothing_is_written_when_one_account_in_a_batch_fails(case_manager, other_case_manager, monkeypatch):
    """The batch is one transaction — a rejected password rolls the whole run back."""
    monkeypatch.setattr("sys.stdin", io.StringIO("Valid-Passphrase-9\n"))
    monkeypatch.setattr(
        "apps.users.management.commands.set_password.validate_password",
        lambda password, user=None: (_ for _ in ()).throw(AssertionError()) if user.username == "cm-b" else None,
    )
    with pytest.raises(AssertionError):
        run(role=Role.CASE_MANAGER, stdin=True, interactive=False)

    case_manager.refresh_from_db()
    assert case_manager.check_password("pw-Test-12345")


def test_system_admin_is_not_silently_excluded(system_admin, monkeypatch):
    """No role is special-cased out; the admin account is reachable by name."""
    monkeypatch.setattr("sys.stdin", io.StringIO("Rotated-Admin-42\n"))
    run(system_admin.username, stdin=True)

    system_admin.refresh_from_db()
    assert system_admin.check_password("Rotated-Admin-42")


def test_validators_receive_the_user(case_manager, monkeypatch):
    """UserAttributeSimilarityValidator only catches a password echoing the username
    or full name if the user object is handed to it — validating the string alone
    silently drops one of the four configured validators."""
    seen = {}
    monkeypatch.setattr(
        "apps.users.management.commands.set_password.validate_password",
        lambda password, user=None: seen.update(password=password, user=user),
    )
    monkeypatch.setattr("sys.stdin", io.StringIO("Valid-Passphrase-9\n"))
    run("cm-a", stdin=True)

    assert seen == {"password": "Valid-Passphrase-9", "user": case_manager}
