"""Bounded sequential pagination; errors never cause automatic retries."""
import time


def collect_pages(get_page, filters, error_type):
    rows = []
    cursors = set()
    query = dict(filters)
    for _ in range(1000):
        page, cursor = get_page(query)
        rows.extend(page)
        if cursor is None:
            return rows
        if not isinstance(cursor, str) or not cursor or len(cursor) > 8192 or cursor in cursors:
            raise error_type("Invalid pagination cursor; no partial catalog returned.")
        cursors.add(cursor)
        query = {**filters, "cursor": cursor}
        # Successful continuation pages are paced below the 180/min read budget.
        # A failed request still aborts immediately, without an automatic retry.
        time.sleep(0.4)
    raise error_type("Pagination limit reached; narrow the system filter.")
