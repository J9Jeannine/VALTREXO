#!/usr/bin/env python3
"""Taegliche Umsatzzahlen von Valltrexo, die Quelle fuer das PnL-Sheet.

Holt pro Tag Orders, Revenue und Refunds ueber shopifyqlQuery. Das sind
Shopifys eigene Zahlen in Shop-Waehrung (EUR), umgerechnet aus
Fremdwaehrungs-Bestellungen, und sie folgen der Tagesgrenze der
Shop-Zeitzone.

    python3 scripts/pnl_revenue.py --since 2026-06-01
    python3 scripts/pnl_revenue.py --day 2026-10-17 --json
    python3 scripts/pnl_revenue.py --since 2026-06-01 --csv revenue.csv
"""
import argparse
import csv
import datetime as dt
import json
import sys
import time

from shopify_api import graphql

QUERY = """
query($ql: String!) {
  shopifyqlQuery(query: $ql) {
    parseErrors
    parseWarnings
    tableData { columns { name } rows }
  }
}
"""

# Eine shopifyqlQuery kostet rund 900 der 1000 Punkte pro Fenster, deshalb
# nur eine Abfrage pro Lauf und bei THROTTLED warten.
RETRIES = 6
RETRY_WAIT = 25


def fetch_daily(since, until='today'):
    """Liefert eine Liste von Dicts, sortiert nach Datum."""
    ql = (
        'FROM sales SHOW orders, total_sales, sales_reversals, gross_sales, discounts '
        f'TIMESERIES day SINCE {since} UNTIL {until} ORDER BY day'
    )

    for attempt in range(RETRIES):
        try:
            result = graphql(QUERY, {'ql': ql})['shopifyqlQuery']
            break
        except SystemExit as error:
            if 'THROTTLED' not in str(error) or attempt == RETRIES - 1:
                raise
            print(f'rate limited, warte {RETRY_WAIT}s', file=sys.stderr)
            time.sleep(RETRY_WAIT)

    if result['parseErrors']:
        sys.exit(f"shopifyql parse errors: {result['parseErrors']}")
    for warning in result['parseWarnings']:
        print(f'warning: {warning}', file=sys.stderr)
    if result['tableData'] is None:
        sys.exit('shopifyqlQuery lieferte keine Tabelle')

    rows = []
    for row in result['tableData']['rows']:
        rows.append({
            'date': row.get('day'),
            'orders': int(float(row.get('orders') or 0)),
            'revenue': round(float(row.get('total_sales') or 0), 2),
            'refunds': round(abs(float(row.get('sales_reversals') or 0)), 2),
            'gross_sales': round(float(row.get('gross_sales') or 0), 2),
            'discounts': round(float(row.get('discounts') or 0), 2),
        })
    rows.sort(key=lambda item: item['date'])
    return rows


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--since', help='Startdatum YYYY-MM-DD oder -30d')
    parser.add_argument('--until', default='today')
    parser.add_argument('--day', help='genau ein Tag, YYYY-MM-DD')
    parser.add_argument('--json', action='store_true')
    parser.add_argument('--csv')
    parser.add_argument('--only-nonzero', action='store_true')
    args = parser.parse_args()

    if args.day:
        since = until = args.day
    elif args.since:
        since, until = args.since, args.until
    else:
        since = (dt.date.today() - dt.timedelta(days=1)).isoformat()
        until = since

    rows = fetch_daily(since, until)
    if args.only_nonzero:
        rows = [row for row in rows if row['orders'] or row['revenue']]

    fields = ['date', 'orders', 'revenue', 'refunds', 'gross_sales', 'discounts']

    if args.json:
        print(json.dumps(rows, indent=2))
    elif args.csv:
        with open(args.csv, 'w', newline='') as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)
        print(f'wrote {args.csv} ({len(rows)} rows)')
    else:
        print('  '.join(field.ljust(12) for field in fields))
        for row in rows:
            print('  '.join(str(row[field]).ljust(12) for field in fields))
        print(f"\n{len(rows)} Tage, Revenue {sum(r['revenue'] for r in rows):.2f} EUR, "
              f"Orders {sum(r['orders'] for r in rows)}")


if __name__ == '__main__':
    main()
