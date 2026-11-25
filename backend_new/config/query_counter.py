"""
Development-only: count database queries for every request.

Turned on only when BOTH are set in .env:
    DJANGO_DEBUG=True
    QUERY_COUNTER=True

For every request it:
  * prints one line in the backend window, e.g.
        [queries]  GET /api/notifications/?unread=true  200  queries=6  db=4.1ms  total=19.8ms
  * adds response headers (read by the load test):
        X-DB-Queries, X-DB-Time-ms, X-Total-Time-ms
"""
import time

from django.db import connection


class QueryCountMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        stats = {"queries": 0, "db_seconds": 0.0}

        def count_query(execute, sql, params, many, context):
            started = time.perf_counter()
            try:
                return execute(sql, params, many, context)
            finally:
                stats["queries"] += 1
                stats["db_seconds"] += time.perf_counter() - started

        started = time.perf_counter()
        with connection.execute_wrapper(count_query):
            response = self.get_response(request)
        total_ms = (time.perf_counter() - started) * 1000
        db_ms = stats["db_seconds"] * 1000

        response["X-DB-Queries"] = str(stats["queries"])
        response["X-DB-Time-ms"] = f"{db_ms:.1f}"
        response["X-Total-Time-ms"] = f"{total_ms:.1f}"

        print(f"[queries]  {request.method} {request.get_full_path()}  {response.status_code}  "
              f"queries={stats['queries']}  db={db_ms:.1f}ms  total={total_ms:.1f}ms", flush=True)
        return response