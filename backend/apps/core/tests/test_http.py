"""parse_datetime_range — shared query-param range parsing, normalized to UTC.

Django's query-string parser decodes an unencoded '+' as a space, so a
'+00:00' offset reaches the view as ' 00:00' and used to 400. Aware values
must be CONVERTED to UTC (astimezone), never reinterpreted (replace clobbers
the offset and shifts the instant).
"""

from datetime import UTC, datetime, timedelta

import pytest
from django.test import RequestFactory
from rest_framework.request import Request

from apps.core.http import parse_datetime_range

rf = RequestFactory()


def test_naive_iso_values_get_utc_attached():
    req = rf.get("/x?start=2026-08-01T00:00:00&end=2026-08-02T00:00:00")
    start, end = parse_datetime_range(req, default_days=30)
    assert start == datetime(2026, 8, 1, tzinfo=UTC)
    assert end == datetime(2026, 8, 2, tzinfo=UTC)


def test_space_mangled_plus_offset_parses():
    # Raw query string: Django's QueryDict decodes the unencoded '+' to a space.
    req = rf.get("/x?end=2026-08-01T12:00:00+00:00")
    _, end = parse_datetime_range(req, default_days=30)
    assert end == datetime(2026, 8, 1, 12, tzinfo=UTC)


def test_encoded_aware_offset_converts_to_utc_instant():
    # %2B decodes to '+': an aware +05:00 value must convert (same instant),
    # not be reinterpreted as UTC wall-clock time.
    req = rf.get("/x?start=2026-08-01T12:00:00%2B05:00")
    start, _ = parse_datetime_range(req, default_days=30)
    assert start == datetime(2026, 8, 1, 7, tzinfo=UTC)
    assert start.tzinfo is UTC
    assert start != datetime(2026, 8, 1, 12, tzinfo=UTC)


def test_defaults_window():
    before = datetime.now(tz=UTC)
    start, end = parse_datetime_range(rf.get("/x"), default_days=7)
    after = datetime.now(tz=UTC)
    assert before <= end <= after
    assert end - start == timedelta(days=7)


def test_custom_param_names():
    req = rf.get("/x?from=2026-08-01T00:00:00&to=2026-08-03T00:00:00")
    start, end = parse_datetime_range(req, start_param="from", end_param="to", default_days=30)
    assert start == datetime(2026, 8, 1, tzinfo=UTC)
    assert end == datetime(2026, 8, 3, tzinfo=UTC)


def test_drf_request_query_params_path():
    req = Request(rf.get("/x?start=2026-08-01T00:00:00"))
    start, _ = parse_datetime_range(req, default_days=30)
    assert start == datetime(2026, 8, 1, tzinfo=UTC)


def test_malformed_value_raises_value_error():
    # Callers rely on ValueError surfacing (DRF views 400 via the exception handler).
    with pytest.raises(ValueError):
        parse_datetime_range(rf.get("/x?end=not-a-date"), default_days=30)
