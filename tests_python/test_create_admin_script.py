"""Unit tests for server/scripts/create_admin.py: the §18.2 CLI admin
bootstrap. `main()` itself (real getpass + real Database) is thin glue and
not covered here, matching how bootstrap_initial_admin's real caller
(server/main.py's lifespan) isn't unit tested either -- only the
underlying logic (`create_admin_via_cli`, `read_password`, `parse_args`)."""

import pytest

from server.scripts.create_admin import create_admin_via_cli, parse_args, read_password
from tests_python.test_auth_service import FakeUserRepo


class TestParseArgs:
    def test_parses_required_and_optional_arguments(self):
        args = parse_args(["--email", "a@example.com", "--display-name", "Boss", "--username", "boss"])
        assert args.email == "a@example.com"
        assert args.display_name == "Boss"
        assert args.username == "boss"

    def test_username_defaults_to_none(self):
        args = parse_args(["--email", "a@example.com", "--display-name", "Boss"])
        assert args.username is None

    def test_missing_required_argument_exits(self):
        with pytest.raises(SystemExit):
            parse_args(["--display-name", "Boss"])


class TestReadPassword:
    def test_returns_the_password_when_confirmation_matches(self):
        prompts = iter(["Str0ngPass!", "Str0ngPass!"])
        result = read_password(prompt_fn=lambda _: next(prompts))
        assert result == "Str0ngPass!"

    def test_reprompts_until_confirmation_matches(self):
        prompts = iter(["Str0ngPass!", "Typo!", "Str0ngPass!", "Str0ngPass!"])
        result = read_password(prompt_fn=lambda _: next(prompts))
        assert result == "Str0ngPass!"


class TestCreateAdminViaCli:
    async def test_returns_zero_on_success(self):
        repo = FakeUserRepo()
        exit_code = await create_admin_via_cli(
            repo, email="admin@example.com", display_name="Boss", password="Str0ngAdminPass!",
        )
        assert exit_code == 0
        assert len(repo.users) == 1

    async def test_returns_one_for_a_weak_password(self):
        repo = FakeUserRepo()
        exit_code = await create_admin_via_cli(
            repo, email="admin@example.com", display_name="Boss", password="weak",
        )
        assert exit_code == 1
        assert repo.users == {}

    async def test_returns_one_for_a_duplicate_email(self):
        repo = FakeUserRepo()
        await create_admin_via_cli(repo, email="admin@example.com", display_name="Boss", password="Str0ngAdminPass!")
        exit_code = await create_admin_via_cli(
            repo, email="admin@example.com", display_name="Boss 2", password="An0therPass!",
        )
        assert exit_code == 1
