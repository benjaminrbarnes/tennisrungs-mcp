"""Typed result wrappers around anonymous, allowlisted consumer reads."""
from datetime import date, datetime, timezone
from urllib.parse import urlencode

from .iparcs_consumer import BASE, ConsumerAdapter, covers
from .models import ReadResult


class IParcsReads:
    def __init__(self, adapter=None):
        self.adapter = adapter or ConsumerAdapter()

    def result(self, path, rows):
        return ReadResult(BASE + path, datetime.now(timezone.utc).isoformat(), rows, True,
                          ["Anonymous consumer read; availability is not a hold or booking"])

    def search(self, keyword):
        return self.result("/rest/reservation/resource?locale=en-US", self.adapter.search(keyword))

    def detail(self, resource_id):
        return self.result(f"/rest/reservation/resource/detail/{resource_id}", [self.adapter.detail(resource_id)])

    def availability(self, resource_id, start_date, end_date):
        start, end = date.fromisoformat(start_date), date.fromisoformat(end_date)
        rows = self.adapter.availability(resource_id, start, end)
        query = urlencode({"start_date": start.isoformat(), "end_date": end.isoformat(), "customer_id": 0, "company_id": 0, "locale": "en-US"})
        return self.result(f"/rest/reservation/resource/availability/daily/{resource_id}?{query}", rows)

    def check_slot(self, resource_id, day, start_time, end_time):
        r = self.availability(resource_id, day, day)
        row = {"resource_id": resource_id, "date": day, "start_time": start_time,
               "end_time": end_time, "timezone": "America/New_York",
               "whole_block_available": covers(r.rows[0], start_time, end_time)}
        return ReadResult(r.source_url, r.observed_at, [row], r.complete, r.warnings)
