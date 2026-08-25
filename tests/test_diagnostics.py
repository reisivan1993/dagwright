from hypothesis import given
from hypothesis import strategies as st

from dagwright.diagnostics import MINIMUM_PYTHON, python_check


@given(
    major=st.integers(min_value=0, max_value=20),
    minor=st.integers(min_value=0, max_value=30),
)
def test_python_check_matches_tuple_ordering(major: int, minor: int) -> None:
    version = (major, minor)

    assert python_check(version).passed is (version >= MINIMUM_PYTHON)
