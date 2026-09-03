"""What gets published has to be what we think it is.

WHAT WOULD BREAK. The zips and the plugin bundle are what other people
install. Nothing else in the suite opens them, so a marker file, a stale
copy, a manifest that is valid JSON but wrong, or frontmatter that only our
own parser accepts would all ship without complaint. Two of those have
already happened once each in this project.
"""

import json
import pathlib
import struct
import zipfile

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
DIST = ROOT / "dist"
BUNDLE = ROOT / "plugins" / "option-desk"
SOURCE = ROOT / "shell" / "skills"
HOSTED_SOURCE = ROOT / "openai-skills"
OPENAI_ARCHIVE = "option-desk-openai-skills.zip"
SKILLS_ARCHIVE = "option-desk-skills.zip"
LOCAL_SKILLS_ARCHIVE = "option-desk-local-skills.zip"

# Written by install.sh into an installed skill so its uninstall knows what
# it owns. It has no business inside anything we publish.
MARKER = ".installed-by-optiondesk"
IGNORED = {MARKER, ".DS_Store", "__pycache__"}


def _skill_names():
    return sorted(p.parent.name for p in SOURCE.glob("*/SKILL.md"))


def _hosted_skill_names():
    return sorted(p.parent.name for p in HOSTED_SOURCE.glob("*/SKILL.md"))


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    """Build with the CURRENT packager, into a directory of our own.

    Reading the committed dist/ and plugins/ instead would test whatever
    was last built rather than what the code now builds: mutation testing
    broke the packager so it dropped every nested resource, and this file
    passed, because the artifacts on disk were still the good ones.
    """
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "desk_package", ROOT / "scripts" / "package.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    out = tmp_path_factory.mktemp("packaged")
    module.DIST = out / "dist"
    module.PLUGIN = out / "plugins" / "option-desk"
    module.build_zips()
    module.build_plugin()
    return module


@pytest.fixture(scope="module")
def dist(built):
    return built.DIST


@pytest.fixture(scope="module")
def bundle(built):
    return built.PLUGIN


def test_there_is_one_archive_per_skill_plus_the_bundle(dist):
    archives = sorted(p.stem for p in (dist / "skills").glob("*.zip"))
    assert archives == _skill_names(), (
        "the archives and the skills have diverged: {} against {}".format(
            archives, _skill_names()))


def test_every_archive_holds_the_skill_under_its_own_directory(dist):
    """The uploader takes the directory name as the skill name.

    Loose files, or a nested extra level, produce a skill named after
    whatever the first path component happens to be.
    """
    for archive in sorted((dist / "skills").glob("*.zip")):
        with zipfile.ZipFile(archive) as zipped:
            names = zipped.namelist()
        assert names, "{} is empty".format(archive.name)
        tops = {n.split("/")[0] for n in names}
        assert tops == {archive.stem}, (
            "{} contains {} rather than one directory named {}".format(
                archive.name, sorted(tops), archive.stem))
        assert "{}/SKILL.md".format(archive.stem) in names, (
            "{} has no SKILL.md at its root".format(archive.name))


def test_combined_skills_archive_contains_only_skill_roots(dist):
    with zipfile.ZipFile(dist / SKILLS_ARCHIVE) as zipped:
        names = zipped.namelist()

    tops = {name.split("/", 1)[0] for name in names}
    assert tops == set(_hosted_skill_names())
    assert all("/" in name for name in names)
    for skill in _hosted_skill_names():
        assert "{}/SKILL.md".format(skill) in names


def test_local_skills_archive_keeps_the_six_local_workflows(dist):
    with zipfile.ZipFile(dist / LOCAL_SKILLS_ARCHIVE) as zipped:
        names = zipped.namelist()

    tops = {name.split("/", 1)[0] for name in names}
    assert tops == set(_skill_names())
    for skill in _skill_names():
        assert "{}/SKILL.md".format(skill) in names


def test_hosted_skills_do_not_claim_local_or_live_provider_access(dist):
    with zipfile.ZipFile(dist / SKILLS_ARCHIVE) as zipped:
        text = "\n".join(
            zipped.read(name).decode("utf-8")
            for name in zipped.namelist()
            if name.endswith("/SKILL.md")
        ).lower()

    assert "optiondesk chain" not in text
    assert "optiondesk-mcp" not in text
    assert "fetch from yahoo" not in text
    assert "ask for an api key" not in text
    assert "set an api key" not in text
    assert "option_plots_from_snapshot" in text


def test_the_frontmatter_in_every_archive_is_valid_yaml(dist):
    """Not our line splitter: the parser everyone else uses.

    options-strategy once carried an unquoted colon in its description,
    which our generator accepted and every real YAML parser rejected. It
    was invisible until a third-party CLI listed four skills of five.
    """
    yaml = pytest.importorskip("yaml")

    for archive in sorted((dist / "skills").glob("*.zip")):
        with zipfile.ZipFile(archive) as zipped:
            text = zipped.read("{}/SKILL.md".format(archive.stem)).decode()
        fields = yaml.safe_load(text.split("---", 2)[1])
        assert fields["name"] == archive.stem, (
            "{} declares the name {}".format(archive.name, fields["name"]))
        assert fields.get("description"), (
            "{} has no description, so nothing will trigger it".format(
                archive.name))


def test_the_bundled_resources_survive_packaging(dist):
    """A skill that references a workflow it does not carry is broken."""
    for archive in sorted((dist / "skills").glob("*.zip")):
        source = SOURCE / archive.stem
        expected = {str(p.relative_to(source)) for p in source.rglob("*")
                    if p.is_file() and not IGNORED.intersection(p.parts)
                    and p.suffix != ".pyc"}
        with zipfile.ZipFile(archive) as zipped:
            got = {n.split("/", 1)[1] for n in zipped.namelist()
                   if "/" in n}
        missing = expected - got
        assert not missing, (
            "{} left behind {}".format(archive.name, sorted(missing)))


def test_openai_archive_has_the_supported_skills_only_layout(dist):
    path = dist / OPENAI_ARCHIVE
    with zipfile.ZipFile(path) as zipped:
        names = set(zipped.namelist())

    expected = {
        ".codex-plugin/plugin.json",
        "DISCLAIMER.md",
        "assets/openai-directory-icon.png",
        "assets/openai-composer-icon.png",
    }
    for skill in SOURCE.iterdir():
        if not (skill / "SKILL.md").is_file():
            continue
        expected.update(
            str(pathlib.Path("skills") / skill.name / item.relative_to(skill))
            for item in skill.rglob("*")
            if item.is_file() and not IGNORED.intersection(item.parts)
            and item.suffix != ".pyc"
        )
    assert names == expected


def test_openai_archive_excludes_all_mcp_configuration(dist):
    with zipfile.ZipFile(dist / OPENAI_ARCHIVE) as zipped:
        names = set(zipped.namelist())
        manifest = json.loads(
            zipped.read(".codex-plugin/plugin.json").decode("utf-8"))

    assert not any(path.endswith(".mcp.json") for path in names)
    assert "mcpServers" not in manifest
    assert "mcp_servers" not in manifest


def test_openai_archive_carries_declared_branding(dist):
    with zipfile.ZipFile(dist / OPENAI_ARCHIVE) as zipped:
        names = set(zipped.namelist())
        manifest = json.loads(
            zipped.read(".codex-plugin/plugin.json").decode("utf-8"))
        archived_assets = {
            field: zipped.read(manifest["interface"][field][2:])
            for field in ("logo", "composerIcon")
        }

    interface = manifest["interface"]
    assert interface["brandColor"] == "#2F6FEB"
    for field in ("logo", "composerIcon"):
        target = interface[field]
        assert target.startswith("./assets/")
        assert target[2:] in names
        data = archived_assets[field]
        assert data == (ROOT / target[2:]).read_bytes()
        assert data[:8] == b"\x89PNG\r\n\x1a\n"
        width, height = struct.unpack(">II", data[16:24])
        assert width == height
        assert width >= 48


def test_codex_manifests_meet_listing_description_limit(dist, bundle):
    manifests = [json.loads(
        (bundle / ".codex-plugin" / "plugin.json").read_text())]
    with zipfile.ZipFile(dist / OPENAI_ARCHIVE) as zipped:
        manifests.append(json.loads(
            zipped.read(".codex-plugin/plugin.json").decode("utf-8")))

    for manifest in manifests:
        assert len(manifest["interface"]["shortDescription"]) <= 30
        assert manifest["interface"]["brandColor"] == "#2F6FEB"


def test_openai_manifest_promises_only_browser_safe_analysis(dist):
    with zipfile.ZipFile(dist / OPENAI_ARCHIVE) as zipped:
        manifest = json.loads(
            zipped.read(".codex-plugin/plugin.json").decode("utf-8"))

    interface = manifest["interface"]
    assert "user-provided option research" in interface["longDescription"]
    assert "without fetching live data" in interface["longDescription"]
    assert interface["defaultPrompt"] == [
        "Explain the main risks in this option-chain snapshot.",
        "Compare these option structures and their trade-offs.",
        "Review this backtest for weak evidence and overlap.",
    ]


def test_no_installer_marker_reaches_anything_published(dist, bundle):
    """The marker tells install.sh what it may delete.

    Shipping it means a later uninstall believes it owns a directory a user
    put there, which is the one mistake an uninstaller must never make.
    """
    for archive in sorted(dist.rglob("*.zip")):
        with zipfile.ZipFile(archive) as zipped:
            leaked = [n for n in zipped.namelist() if n.endswith(MARKER)]
        assert not leaked, "{} carries {}".format(archive.name, leaked)

    leaked = [str(p.relative_to(ROOT)) for p in bundle.rglob(MARKER)]
    assert not leaked, "the plugin bundle carries {}".format(leaked)


def test_both_manifests_parse_and_agree_on_the_essentials(bundle):
    claude = json.loads(
        (bundle / ".claude-plugin" / "plugin.json").read_text())
    codex = json.loads(
        (bundle / ".codex-plugin" / "plugin.json").read_text())

    for name, manifest in (("claude", claude), ("codex", codex)):
        for field in ("name", "version", "description"):
            assert manifest.get(field), (
                "the {} manifest has no {}".format(name, field))
    assert claude["name"] == codex["name"] == bundle.name, (
        "the manifests and the directory disagree about the plugin name")
    assert claude["version"] == codex["version"], (
        "the two manifests declare different versions")

    for field in ("logo", "composerIcon"):
        target = codex["interface"][field]
        relative = target[2:] if target.startswith("./") else target
        assert (bundle / relative).is_file(), (
            "the codex manifest points at missing branding {}".format(target))

    # The Codex manifest points at its parts by path. They have to exist.
    for field in ("skills", "mcpServers"):
        target = codex.get(field)
        if not target:
            continue
        # Strip the "./" prefix, not the character set: lstrip("./") turns
        # "./.mcp.json" into "mcp.json", because it removes every leading
        # dot and slash rather than the two-character prefix.
        relative = target[2:] if target.startswith("./") else target
        assert (bundle / relative).exists(), (
            "the codex manifest points at {}, which is not in the "
            "bundle".format(target))


def test_the_bundle_carries_every_skill_the_source_has(bundle):
    packaged = sorted(p.parent.name
                      for p in (bundle / "skills").glob("*/SKILL.md"))
    assert packaged == _skill_names(), (
        "the bundle has {} and the source has {}".format(packaged,
                                                         _skill_names()))


def test_the_mcp_descriptor_names_a_command_the_installer_creates(bundle):
    """A descriptor naming a binary nothing installs is a dead tool entry."""
    descriptor = json.loads((bundle / ".mcp.json").read_text())
    servers = descriptor.get("mcpServers") or {}
    assert servers, "the bundle declares no MCP server"
    commands = {entry.get("command") for entry in servers.values()}
    installer = (ROOT / "install.sh").read_text(encoding="utf-8")
    for command in commands:
        assert command in installer, (
            "{} is declared in .mcp.json and install.sh never creates "
            "it".format(command))


# --------------------------------------------------------- the hosted plugin


@pytest.fixture(scope="module")
def hosted(built, tmp_path_factory):
    """The hosted plugin, built by the same packager into our own tree."""
    built.HOSTED_PLUGIN = built.PLUGIN.parent / "option-desk-hosted"
    return built.build_hosted_plugin()


def test_the_hosted_plugin_declares_one_remote_http_server_and_no_command(
        hosted, built):
    """A remote server is a URL and a type; a command would be a stdio
    server nothing on a browser can run."""
    descriptor = json.loads((hosted / ".mcp.json").read_text())
    servers = descriptor["mcpServers"]

    assert list(servers) == ["optiondesk-hosted"]
    server = servers["optiondesk-hosted"]
    assert server == {"type": "http", "url": built.HOSTED_MCP_URL}
    assert server["url"].startswith("https://")


def test_the_hosted_plugin_carries_the_hosted_skills_and_nothing_local(
        hosted):
    """The four hosted-safe skills, and none of the six local workflows:
    a skill that says optiondesk chain would send a browser user to a
    command it cannot run."""
    packaged = sorted(p.parent.name
                      for p in (hosted / "skills").glob("*/SKILL.md"))
    assert packaged == _hosted_skill_names()
    assert not (hosted / "commands").exists()
    assert not (hosted / "agents").exists()
    text = "\n".join(p.read_text(encoding="utf-8")
                     for p in (hosted / "skills").glob("*/SKILL.md")).lower()
    assert "optiondesk chain" not in text
    assert "optiondesk-mcp" not in text


def test_the_hosted_manifests_agree_and_name_a_different_plugin(hosted,
                                                                bundle):
    claude = json.loads(
        (hosted / ".claude-plugin" / "plugin.json").read_text())
    codex = json.loads((hosted / ".codex-plugin" / "plugin.json").read_text())
    local = json.loads(
        (bundle / ".claude-plugin" / "plugin.json").read_text())

    assert claude["name"] == codex["name"] == hosted.name
    assert claude["name"] != local["name"]
    assert claude["version"] == codex["version"] == local["version"]
    assert "not investment advice" in claude["description"]
    assert "No market data is fetched" in claude["description"]
    assert codex["mcpServers"] == "./.mcp.json"
    assert len(codex["interface"]["shortDescription"]) <= 30
    assert len(codex["interface"]["defaultPrompt"]) <= 3
    for field in ("logo", "composerIcon"):
        assert (hosted / codex["interface"][field][2:]).is_file()
    assert (hosted / "DISCLAIMER.md").is_file()


def test_both_marketplaces_list_both_plugins(built, tmp_path):
    """Two plugins, listed in the same order by both hosts."""
    built.ROOT = tmp_path
    (tmp_path / ".claude-plugin").mkdir()
    (tmp_path / ".agents" / "plugins").mkdir(parents=True)
    claude_path, codex_path = built.build_marketplaces()

    claude = json.loads(claude_path.read_text())
    codex = json.loads(codex_path.read_text())
    assert [p["name"] for p in claude["plugins"]] == [
        "option-desk", "option-desk-hosted"]
    assert [p["name"] for p in codex["plugins"]] == [
        "option-desk", "option-desk-hosted"]
    assert claude["plugins"][1]["source"] == "./plugins/option-desk-hosted"
    assert codex["plugins"][1]["source"]["path"] == \
        "./plugins/option-desk-hosted"
