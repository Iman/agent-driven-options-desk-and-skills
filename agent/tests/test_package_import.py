"""langgraph is an optional extra, and the package must import without it.

Absence is simulated by blocking the module in sys.modules rather than by
uninstalling it, so the test says something about the import graph without
depending on how the environment was built. Everything is restored
afterwards; a test that left langgraph blocked would silently change what
every later test was running against.
"""

import contextlib
import importlib
import sys

import pytest

PREFIXES = ("langgraph", "optiondesk_agent")


@contextlib.contextmanager
def langgraph_absent():
    """Make langgraph unimportable, and put sys.modules back afterwards."""
    saved = {name: module for name, module in sys.modules.items()
             if name.split(".")[0] in PREFIXES}
    for name in saved:
        del sys.modules[name]
    sys.modules["langgraph"] = None
    try:
        yield
    finally:
        for name in [n for n in sys.modules
                     if n.split(".")[0] in PREFIXES]:
            del sys.modules[name]
        sys.modules.update(saved)


def test_langgraph_is_actually_installed_here():
    """Guards the blocking tests below from passing vacuously.

    If langgraph were absent from the environment anyway, every assertion
    about simulated absence would hold for the wrong reason and prove
    nothing about the package's import graph.
    """
    assert importlib.import_module("langgraph") is not None


def test_the_package_imports_with_langgraph_blocked():
    """Catches the graph module being imported eagerly by __init__.

    langgraph is an optional extra. An eager import makes it mandatory, and
    the failure lands on every user of the tools and retrieval layers who
    never asked for the graph at all.
    """
    with langgraph_absent():
        package = importlib.import_module("optiondesk_agent")

        assert package.__version__ == "0.3.0"


def test_the_graph_module_is_not_pulled_in_on_import():
    """Catches a lazy path that is only lazy in name.

    An import chain that reaches optiondesk_agent.graph during package
    import has already paid the cost the __getattr__ shim exists to avoid.
    """
    with langgraph_absent():
        importlib.import_module("optiondesk_agent")

        assert "optiondesk_agent.graph" not in sys.modules


def test_the_eager_surface_works_with_langgraph_blocked():
    """Catches the tools and retrieval layers depending on the extra.

    These are the parts the package promises without langgraph, so each has
    to be usable, not merely importable.
    """
    with langgraph_absent():
        package = importlib.import_module("optiondesk_agent")

        assert package.desk_tools(include=["option_expiries"])[0].name \
            == "option_expiries"
        assert "degraded" in package.REPORTING_RULES
        assert package.ArtifactStore("/nonexistent-desk-dir").records() == []


def test_the_graph_names_still_fail_loudly_when_the_extra_is_missing():
    """Catches the missing extra surfacing as something other than ImportError.

    A caller who wants the graph without installing the extra must be told
    that, by an ImportError naming langgraph, rather than by an
    AttributeError that reads as a typo.
    """
    with langgraph_absent():
        package = importlib.import_module("optiondesk_agent")

        with pytest.raises(ImportError) as caught:
            package.build_desk_graph()

        assert "langgraph" in str(caught.value)


def test_an_unknown_attribute_is_an_attribute_error_not_an_import():
    """Catches __getattr__ trying to resolve any name through the graph.

    A shim that reaches for the graph module on every miss turns a typo
    into an ImportError about an optional extra, and hides the typo.
    """
    package = importlib.import_module("optiondesk_agent")

    with pytest.raises(AttributeError):
        package.definitely_not_a_real_name


def test_everything_declared_public_is_reachable():
    """Catches __all__ advertising a name that no longer resolves.

    __all__ is what a star import and the documentation both follow, so a
    stale entry is an advertised name that raises on access.
    """
    package = importlib.import_module("optiondesk_agent")

    for name in package.__all__:
        assert getattr(package, name) is not None, name


def test_the_lazy_names_are_the_graph_names():
    """Catches a name added to __all__ but never routed through __getattr__.

    Such a name is importable only if something else has already imported
    the graph module, so it works in one process and not the next.
    """
    package = importlib.import_module("optiondesk_agent")

    assert set(package.__lazy__) == {"build_desk_graph", "open_desk"}
    assert set(package.__lazy__) <= set(package.__all__)


def test_sys_modules_is_restored_after_the_block():
    """Catches the helper leaking a blocked langgraph into later tests.

    A test file that leaves None in sys.modules makes every later import of
    the graph fail for a reason that has nothing to do with the code.
    """
    with langgraph_absent():
        pass

    assert sys.modules.get("langgraph") is not None
    assert importlib.import_module("optiondesk_agent.graph") is not None
