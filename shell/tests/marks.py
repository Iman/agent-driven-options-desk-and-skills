"""Skip markers shared by the shell tests.

WHY THIS IS NOT IN conftest.py. Eight test modules used to do
`from conftest import needs_engine`, which works only because pytest puts
each test directory on sys.path and the first `conftest` imported wins.
Run one suite at a time and it is fine. Run all three together, as anyone
would at the repository root, and the agent package's conftest is imported
first under that name, so nine shell modules fail to collect with
"cannot import name 'needs_engine' from 'conftest'". A person seeing nine
collection errors reasonably concludes the project is broken.

The name of this module is deliberately unique across the three suites.
"""

import pytest

from optiondesk import engine_bridge

needs_engine = pytest.mark.skipif(
    not engine_bridge.AVAILABLE,
    reason="analytics engine not installed")
