#!/usr/bin/env python3
"""Orders and revenue per product per day, computed from Order.lineItems."""
import argparse
import csv
import sys
from collections import defaultdict
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from shopify_api import graphql

ORDERS_QUERY = """
query($cursor: String, $query: String!) {
  orders(first: 50, after: $cursor, query: $query, sortKey: CREATED_AT) {
    pageInfo { hasNextPage endCursor }
    edges {
      node {
        name
        createdAt
        test
        cancelledAt
        lineItems(first: 100) {
          edges {
            node {
              title
              quantity
              product { id }
              discountedTotalSet { shopMoney { amount currencyCode } }
            }
          }
        }
      }
    }
  }
}
"""


def fetch_orders(since):
    cursor = None
    query = f"created_at:>={since}" if since else ""
    while True:
        page = graphql(ORDERS_QUERY, {"cursor": cursor, "query": query})["orders"]
        for edge in page["edges"]:
            yield edge["node"]
        if not page["pageInfo"]["hasNextPage"]:
            return
        cursor = page["pageInfo"]["endCursor"]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=60)
    parser.add_argument("--include-cancelled", action="store_true")
    parser.add_argument("--include-test", action="store_true")
    parser.add_argument("--csv")
    args = parser.parse_args()

    shop = graphql("{ shop { ianaTimezone currencyCode } }")["shop"]
    tz = ZoneInfo(shop["ianaTimezone"])
    since = (datetime.now(tz) - timedelta(days=args.days)).date().isoformat()

    rows = defaultdict(lambda: {"orders": set(), "units": 0, "revenue": 0.0})
    skipped = {"test": 0, "cancelled": 0}

    for order in fetch_orders(since):
        if order["test"] and not args.include_test:
            skipped["test"] += 1
            continue
        if order["cancelledAt"] and not args.include_cancelled:
            skipped["cancelled"] += 1
            continue
        day = datetime.fromisoformat(order["createdAt"]).astimezone(tz).date().isoformat()
        for edge in order["lineItems"]["edges"]:
            item = edge["node"]
            money = item["discountedTotalSet"]["shopMoney"]
            row = rows[(day, item["title"], money["currencyCode"])]
            row["orders"].add(order["name"])
            row["units"] += item["quantity"]
            row["revenue"] += float(money["amount"])

    header = ("date", "product", "currency", "orders", "units", "revenue")
    table = [
        (day, product, currency, len(value["orders"]), value["units"], round(value["revenue"], 2))
        for (day, product, currency), value in sorted(rows.items())
    ]

    if args.csv:
        with open(args.csv, "w", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(header)
            writer.writerows(table)
        print(f"wrote {args.csv} ({len(table)} rows)")
        return

    print(f"shop timezone: {shop['ianaTimezone']}   shop currency: {shop['currencyCode']}   since: {since}")
    print(f"skipped: {skipped['test']} test, {skipped['cancelled']} cancelled")
    if not table:
        print("no line items in range")
        return
    widths = [max(len(str(r[i])) for r in (header, *table)) for i in range(len(header))]
    for row in (header, *table):
        print("  ".join(str(cell).ljust(widths[i]) for i, cell in enumerate(row)))


if __name__ == "__main__":
    main()
