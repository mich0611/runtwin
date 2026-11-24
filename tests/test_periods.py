from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from runtwin.reporting.periods import week_bounds


@pytest.mark.parametrize("reference,start,end", [
    (datetime(2026, 9, 3, 12, tzinfo=ZoneInfo("Asia/Taipei")), "2026-08-24T00:00:00+08:00", "2026-08-31T00:00:00+08:00"),
    (datetime(2026, 3, 2, 9, tzinfo=ZoneInfo("Asia/Taipei")), "2026-02-23T00:00:00+08:00", "2026-03-02T00:00:00+08:00"),
    (datetime(2027, 1, 4, 9, tzinfo=ZoneInfo("Asia/Taipei")), "2026-12-28T00:00:00+08:00", "2027-01-04T00:00:00+08:00"),
])
def test_previous_complete_week_boundaries(reference, start, end):
    actual_start, actual_end = week_bounds(reference, previous_complete=True)
    assert actual_start.isoformat() == start
    assert actual_end.isoformat() == end
