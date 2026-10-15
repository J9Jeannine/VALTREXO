#!/usr/bin/env python3
"""Shopify's own sales numbers per product per day via shopifyqlQuery.

Requires read_reports, Level 2 protected customer data and Admin API 2025-10+.
Source: https://shopify.dev/docs/apps/build/shopifyql/graphql-admin-api
"""
import argparse
import csv
import sys

from shopify_api import graphql

QUERY = """
query($ql: String!) {
  shopifyqlQuery(query: $ql) {
    parseErrors
    parseWarnings
    tableData { columns { name dataType displayName } rows }
  }
}
"""


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=60)
    parser.add_argument("--csv")
    args = parser.parse_args()

    ql = (
        "FROM sales SHOW total_sales, net_sales, gross_sales, discounts, sales_reversals, orders "
        f"GROUP BY day, product_title SINCE -{args.days}d UNTIL today ORDER BY day"
    )
    result = graphql(QUERY, {"ql": ql})["shopifyqlQuery"]

    if result["parseErrors"]:
        sys.exit(f"shopifyql parse errors: {result['parseErrors']}")
    for warning in result["parseWarnings"]:
        print(f"warning: {warning}", file=sys.stderr)

    table = result["tableData"]
    if table is None:
        sys.exit("shopifyqlQuery returned no table")

    columns = [column["name"] for column in table["columns"]]
    rows = [[row.get(column, "") for column in columns] for row in table["rows"]]

    if args.csv:
        with open(args.csv, "w", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(columns)
            writer.writerows(rows)
        print(f"wrote {args.csv} ({len(rows)} rows)")
        return

    print(ql)
    if not rows:
        print("no rows in range")
        return
    widths = [max(len(str(r[i])) for r in (columns, *rows)) for i in range(len(columns))]
    for row in (columns, *rows):
        print("  ".join(str(cell).ljust(widths[i]) for i, cell in enumerate(row)))


if __name__ == "__main__":
    main()
