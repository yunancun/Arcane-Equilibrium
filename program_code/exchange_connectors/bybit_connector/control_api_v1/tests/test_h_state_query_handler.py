"""Compatibility collector for the split h_state_query_handler tests.

The actual tests live in ``tests/h_state_query/``. This shim keeps the
historical pytest path working while avoiding a 2k+ LOC test file.
"""

from h_state_query.test_core import *  # noqa: F401,F403
from h_state_query.test_h_buckets import *  # noqa: F401,F403
from h_state_query.test_agent_states import *  # noqa: F401,F403
