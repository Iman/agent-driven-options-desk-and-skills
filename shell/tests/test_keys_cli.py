"""The four promises made about credential handling, checked.

INSTALL.md and the keys module both tell the reader that a key is never
printed in full, that it is stored in a file only its owner can read, that
resolution runs flag, environment, .env, user config in that order, and
that no key value ever reaches an artifact. Until this file existed all four
were prose. The module was 25 percent covered and nothing tested behaviour:
the only mentions of it in the suite were documentation contracts asserting
that the command is listed, not that it does what it says.

The distinction matters more here than elsewhere in this repository. A bug
in the Greek ladder produces a wrong number that the next run corrects. A
bug in masking produces a key on a screen, in a screenshot, or in a pasted
bug report, and no later run takes that back.

Nothing here touches the real ~/.optiondesk. The fixture repoints the config
path in both modules that hold a reference to it, clears the dotenv cache on
the way in and the way out, and moves the working directory so that a .env
belonging to whoever runs the tests cannot reach the assertions.
"""

import json
import os
import stat

import pytest

from optiondesk import config
from optiondesk.cli import keys

# Lower case on purpose. The repository's own house-rules scan looks for
# key-shaped strings, sixteen or more characters of upper case and digits,
# and a realistic looking fixture trips it. This value exercises the same
# masking arithmetic without planting something the scanner must then be
# taught to ignore.
SECRET = "zzzz1111yyyy2222"
KEY_VARS = ("ALPHAVANTAGE_API_KEY", "TRADIER_API_KEY", "FMP_API_KEY",
            "POLYGON_API_KEY", "ALPACA_API_KEY", "FINVIZ_API_KEY")


@pytest.fixture
def store(tmp_path, monkeypatch):
    """An isolated config file, with the dotenv cache neutralised."""
    monkeypatch.chdir(tmp_path)
    path = tmp_path / "config.env"
    monkeypatch.setattr(config, "USER_CONFIG", path)
    monkeypatch.setattr(keys, "USER_CONFIG", path)
    for variable in KEY_VARS:
        monkeypatch.delenv(variable, raising=False)
    monkeypatch.setattr(config, "_DOTENV_CACHE", None)
    yield path
    config._DOTENV_CACHE = None


def args(**kwargs):
    """An argparse namespace with the defaults the parser would supply."""
    base = {"action": "list", "provider": None, "value": None}
    base.update(kwargs)
    return type("Args", (), base)()


def test_a_set_key_is_never_returned_in_full(store):
    """The whole point of the module. Asserted against the serialised reply
    rather than one field, because a key leaking through a field nobody
    thought to check is exactly how this goes wrong.
    """
    keys.run(args(action="set", provider="alphavantage", value=SECRET))
    config._DOTENV_CACHE = None
    listed = keys.run(args(action="list"))
    assert SECRET not in json.dumps(listed, default=str)
    row = [r for r in listed["providers"] if r["provider"] == "alphavantage"][0]
    assert row["configured"] is True
    assert row["masked"] == "zz************22"


def test_the_reply_to_set_carries_no_key_either(store):
    """set returns a mask and a path. An early version returned the value so
    the caller could confirm it, which put the key in the shell's scrollback.
    """
    result = keys.run(args(action="set", provider="fmp", value=SECRET))
    assert SECRET not in json.dumps(result, default=str)
    assert result["masked"] == "zz************22"
    assert result["permissions"] == "0o600"


@pytest.mark.parametrize("value,expected", [
    ("", None),
    ("a", "*"),
    ("abcd", "****"),
    ("abcde", "ab*de"),
    (SECRET, "zz************22"),
])
def test_short_values_are_hidden_entirely(value, expected):
    """A value of four characters or fewer is masked completely rather than
    having its middle removed, since with two characters shown at each end
    there would be nothing left to hide.
    """
    assert keys._mask(value) == expected


def test_the_file_is_owner_only_after_a_write(store):
    """INSTALL.md says readable only by you. This is that sentence."""
    keys.run(args(action="set", provider="tradier", value=SECRET))
    mode = stat.S_IMODE(os.stat(store).st_mode)
    assert mode == 0o600
    assert not mode & 0o077


def test_a_loose_pre_existing_file_is_tightened(store):
    """A config file created by hand, or by an older version, or restored
    from a backup, arrives world readable. Writing to it must not leave it
    that way.
    """
    store.write_text("SOMETHING_ELSE=1\n", encoding="utf-8")
    os.chmod(store, 0o644)
    keys.run(args(action="set", provider="polygon", value=SECRET))
    assert stat.S_IMODE(os.stat(store).st_mode) == 0o600


def test_unset_removes_one_variable_and_leaves_the_rest(store):
    """The rewrite drops every line starting with the variable name. An
    earlier shape of this function rewrote the file from the value it had
    just parsed, which lost anything it did not understand.
    """
    keys.run(args(action="set", provider="alphavantage", value=SECRET))
    keys.run(args(action="set", provider="polygon", value="otherkey123456"))
    config._DOTENV_CACHE = None
    keys.run(args(action="unset", provider="alphavantage"))
    text = store.read_text(encoding="utf-8")
    assert "ALPHAVANTAGE_API_KEY" not in text
    assert "POLYGON_API_KEY=otherkey123456" in text


def test_unset_says_when_the_key_survives_elsewhere(store, monkeypatch):
    """Removing it from the file does not remove it from the environment, and
    a user who is told only "removed" will not understand why it still works.
    """
    keys.run(args(action="set", provider="fmp", value=SECRET))
    monkeypatch.setenv("FMP_API_KEY", "from_the_environment")
    config._DOTENV_CACHE = None
    result = keys.run(args(action="unset", provider="fmp"))
    assert result["still_set_elsewhere"] is True
    assert "FMP_API_KEY" not in store.read_text(encoding="utf-8")


def test_path_reports_the_documented_resolution_order(store):
    """The order in the reply is the order the code resolves in. They are
    written in two places, so they can disagree, and a user debugging a key
    that will not take is reading this list to decide where to look.
    """
    result = keys.run(args(action="path"))
    assert result["config"] == str(store)
    assert result["exists"] is False
    order = result["resolution_order"]
    assert order[0].endswith("flag")
    assert "environment" in order[1]
    assert order[2].startswith(".env")
    assert order[3] == str(store)


def test_resolution_really_runs_in_that_order(store, monkeypatch):
    """Four sources, each shadowing the one below it, checked one layer at a
    time. Asserting the final answer alone would pass even if two layers were
    swapped.
    """
    store.write_text("TRADIER_API_KEY=from_user_config\n", encoding="utf-8")
    config._DOTENV_CACHE = None
    assert config.setting("TRADIER_API_KEY") == "from_user_config"

    (store.parent / ".env").write_text("TRADIER_API_KEY=from_dotenv\n",
                                       encoding="utf-8")
    config._DOTENV_CACHE = None
    assert config.setting("TRADIER_API_KEY") == "from_dotenv"

    monkeypatch.setenv("TRADIER_API_KEY", "from_environment")
    assert config.setting("TRADIER_API_KEY") == "from_environment"
    assert config.setting("TRADIER_API_KEY", override="from_flag") == \
        "from_flag"


def test_no_key_value_reaches_the_credential_report(store, monkeypatch):
    """doctor and the dashboard both render configured_providers. It reports
    presence as a boolean and must never carry the value that made it true.
    """
    monkeypatch.setenv("ALPHAVANTAGE_API_KEY", SECRET)
    config._DOTENV_CACHE = None
    report = config.configured_providers()
    assert report["alphavantage"] == {"requires_key": True,
                                      "key_present": True}
    assert SECRET not in json.dumps(report)


def test_the_prompt_is_used_when_no_value_is_given(store, monkeypatch):
    """--value puts the key in shell history, so omitting it is the intended
    path and the one most likely to be left untested.
    """
    asked = []

    def fake_getpass(prompt):
        asked.append(prompt)
        return "  " + SECRET + "  "

    monkeypatch.setattr(keys.getpass, "getpass", fake_getpass)
    result = keys.run(args(action="set", provider="alpaca"))
    assert asked and "alpaca" in asked[0]
    assert result["masked"] == "zz************22"
    assert "ALPACA_API_KEY=" + SECRET in store.read_text(encoding="utf-8")


def test_an_empty_answer_writes_nothing(store, monkeypatch):
    """Enter pressed at the prompt by mistake. Writing an empty value would
    leave a variable set to nothing, which reads as configured everywhere
    that checks presence.
    """
    monkeypatch.setattr(keys.getpass, "getpass", lambda prompt: "")
    with pytest.raises(ValueError, match="nothing was written"):
        keys.run(args(action="set", provider="alpaca"))
    assert not store.exists()


def test_unknown_and_keyless_providers_are_refused_by_name(store):
    """Both messages name the thing that was wrong and what to try instead,
    because this command is the first one a new user runs.
    """
    with pytest.raises(ValueError, match="unknown provider"):
        keys.run(args(action="set", provider="nosuchvendor", value=SECRET))
    with pytest.raises(ValueError, match="needs no key"):
        keys.run(args(action="set", provider="yahoo", value=SECRET))
    with pytest.raises(ValueError, match="which provider"):
        keys.run(args(action="set"))


def test_list_reports_the_free_provider_as_needing_nothing(store):
    """yahoo has no key variable. Reporting it as unconfigured would send a
    reader hunting for a key that does not exist.
    """
    listed = keys.run(args(action="list"))
    row = [r for r in listed["providers"] if r["provider"] == "yahoo"][0]
    assert row["needs_key"] is False
    assert row["configured"] is True
    assert row["masked"] is None
