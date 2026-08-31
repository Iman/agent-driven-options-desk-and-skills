"""LangChain bindings for the option desk.

MIT licensed. This package is a language layer over the shell: it turns
commands into tools, artifacts into documents, and questions into prompts
that can only be answered from what is on disk.

It never computes a number. Everything quantitative comes from the engine,
which does not depend on this package.
"""

from optiondesk_agent.artifacts import ArtifactStore
from optiondesk_agent.prompts import (
    REPORTING_RULES,
    build_answer_prompt,
    build_router_prompt,
)
from optiondesk_agent.tools import desk_tools, tool_specs

# Imported lazily by name: the graph needs langgraph, which is an optional
# extra, and importing it here would make the whole package require it.
__lazy__ = ("build_desk_graph", "open_desk")


def __getattr__(name):
    if name in __lazy__:
        from optiondesk_agent import graph

        return getattr(graph, name)
    raise AttributeError(name)

__version__ = "0.2.0"

__all__ = ["ArtifactStore", "desk_tools", "tool_specs",
           "build_answer_prompt", "build_router_prompt", "REPORTING_RULES",
           "build_desk_graph", "open_desk", "__version__"]
