#!/usr/bin/env python3
"""Traegt den Valltrexo-Tagesumsatz in den Valtrexo-Block des Sheets "PnL" ein.

Das ist die Routine. Sie laeuft in der Umgebung valtrexo und schreibt ueber
die Google Sheets API, authentifiziert als Service Account.

Geschrieben werden genau zwei Spalten im Block "Valtrexo":

    "Revenue Vall"   Tagesumsatz aus Shopify
    "Refunds"        Erstattungen des Tages, nur wenn es welche gab

Alles andere bleibt unberuehrt. Spalte "Revenue" ist dort die Formel
'=C+D' und wird nie beschrieben.

Sicherungen, die nicht entfernt werden duerfen:

  * Der Block wird ueber sein Label in Spalte A UND eine Pflichtspalte in
    seiner Kopfzeile gesucht. Fehlt eines, wird fuer diesen Tab nichts
    geschrieben - lieber ein leerer Lauf als ein Schreibvorgang im
    falschen Block.
  * Zeilennummern werden nie angenommen, sondern ueber das Datum in
    Spalte A aufgeloest.
  * Zellen, die eine Formel enthalten, werden nie ueberschrieben.
  * Ein Tag ohne Erstattung wird nicht geschrieben, damit Handwerte nicht
    mit 0.00 ueberschrieben werden.

Aufruf:
    python3 scripts/pnl_sheet_sync.py --days 7 --dry-run
    python3 scripts/pnl_sheet_sync.py --days 7
"""
import argparse
import base64
import calendar
import datetime as dt
import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request

from pnl_revenue import fetch_daily

SPREADSHEET_ID = "1reNOsgEOBzIrL9hH3pXBhLcIBQIoJUwD78iRlS_o_mU"
SHEETS_API = "https://sheets.googleapis.com/v4/spreadsheets"
TOKEN_URL = "https://oauth2.googleapis.com/token"
SCOPE = "https://www.googleapis.com/auth/spreadsheets"

BLOCK_LABEL = "Valtrexo"
REVENUE_COLUMN = "Revenue Vall"
REFUNDS_COLUMN = "Refunds"

# Der Block endet im laengsten Monat mit der Summenzeile 71.
SCAN_ROWS = 140
SCAN_LAST_COLUMN = "Z"
# Soweit darf die Kopfzeile unter dem Label stehen (Label 38, Kopfzeile 39).
HEADER_SEARCH_DEPTH = 5

MONTH_NAMES = list(calendar.month_name)  # [''], 'January', ...

# Der Schluessel kann unter verschiedenen Namen hinterlegt sein. Roh-JSON und
# base64 werden beide erkannt, ein Pfad ebenfalls.
KEY_ENV_NAMES = (
    "GOOGLE_SERVICE_ACCOUNT_JSON",
    "GOOGLE_SA_KEY_B64",
    "GOOGLE_SA_KEY",
    "GOOGLE_SHEETS_SA_JSON",
    "GOOGLE_SHEETS_CREDENTIALS",
    "GCP_SERVICE_ACCOUNT_JSON",
    "SERVICE_ACCOUNT_JSON",
)
KEY_PATH_ENV_NAMES = ("GOOGLE_APPLICATION_CREDENTIALS",)


class SheetError(Exception):
    pass


# --------------------------------------------------------------- Auth

def load_service_account():
    """Liest den Service-Account-Schluessel aus der Umgebung."""
    for name in KEY_ENV_NAMES:
        raw = os.environ.get(name)
        if not raw:
            continue
        text = raw.strip()
        if not text.startswith("{"):
            try:
                text = base64.b64decode(text).decode()
            except Exception:
                raise SheetError(
                    "{} ist weder JSON noch base64-kodiertes JSON".format(name))
        try:
            info = json.loads(text)
        except json.JSONDecodeError as err:
            raise SheetError("{} enthaelt kein gueltiges JSON: {}".format(name, err))
        if not info.get("client_email") or not info.get("private_key"):
            raise SheetError(
                "{} hat kein 'client_email'/'private_key' - das ist kein "
                "Service-Account-Schluessel".format(name))
        print("Service Account aus {}: {}".format(name, info["client_email"]))
        return info

    for name in KEY_PATH_ENV_NAMES:
        path = os.environ.get(name)
        if path and os.path.exists(path):
            with open(path) as handle:
                info = json.load(handle)
            print("Service Account aus Datei {}: {}".format(path, info["client_email"]))
            return info

    raise SheetError(
        "Kein Service-Account-Schluessel gefunden. Gesucht wurde in: {} sowie "
        "als Dateipfad in {}. Den Schluessel als Umgebungsvariable der Umgebung "
        "valtrexo hinterlegen und das Sheet fuer die client_email des Service "
        "Accounts als Bearbeiter freigeben.".format(
            ", ".join(KEY_ENV_NAMES), ", ".join(KEY_PATH_ENV_NAMES)))


def _b64url(data):
    return base64.urlsafe_b64encode(data).rstrip(b"=")


def _sign_rs256(private_key_pem, data):
    """RS256-Signatur, mit openssl als Rueckfallebene.

    Die Debian-Version von `cryptography` ist in frischen Containern
    regelmaessig kaputt (ModuleNotFoundError: _cffi_backend). Statt im
    Routinelauf ein pip install vorauszusetzen, faellt die Signatur dann auf
    das openssl-Kommando zurueck, das immer da ist.
    """
    try:
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import padding

        key = serialization.load_pem_private_key(private_key_pem.encode(), password=None)
        return key.sign(data, padding.PKCS1v15(), hashes.SHA256())
    except Exception as err:
        print("cryptography nicht nutzbar ({}), signiere mit openssl".format(
            type(err).__name__))

    handle, path = tempfile.mkstemp(suffix=".pem")
    try:
        os.fchmod(handle, 0o600)
        with os.fdopen(handle, "w") as key_file:
            key_file.write(private_key_pem)
        result = subprocess.run(
            ["openssl", "dgst", "-sha256", "-sign", path],
            input=data, capture_output=True)
        if result.returncode != 0:
            raise SheetError("openssl konnte nicht signieren: {}".format(
                result.stderr.decode(errors="replace")[:300]))
        return result.stdout
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass


def access_token(info):
    """Signiert ein JWT und tauscht es gegen einen Access Token."""
    now = int(time.time())
    header = {"alg": "RS256", "typ": "JWT"}
    claims = {
        "iss": info["client_email"],
        "scope": SCOPE,
        "aud": TOKEN_URL,
        "iat": now,
        "exp": now + 3600,
    }
    signing_input = (_b64url(json.dumps(header).encode()) + b"." +
                     _b64url(json.dumps(claims).encode()))

    signature = _sign_rs256(info["private_key"], signing_input)
    assertion = (signing_input + b"." + _b64url(signature)).decode()

    body = urllib.parse.urlencode({
        "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
        "assertion": assertion,
    }).encode()
    request = urllib.request.Request(
        TOKEN_URL, data=body,
        headers={"Content-Type": "application/x-www-form-urlencoded"})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            payload = json.loads(response.read().decode())
    except urllib.error.HTTPError as err:
        raise SheetError("Token-Anfrage fehlgeschlagen: HTTP {} {}".format(
            err.code, err.read().decode(errors="replace")[:300]))
    return payload["access_token"]


# ------------------------------------------------------------- Sheets

def _call(token, path, params=None, method="GET", payload=None):
    url = SHEETS_API + "/" + SPREADSHEET_ID + path
    if params:
        url += "?" + urllib.parse.urlencode(params)
    data = json.dumps(payload).encode() if payload is not None else None
    request = urllib.request.Request(
        url, data=data, method=method,
        headers={"Authorization": "Bearer " + token,
                 "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            return json.loads(response.read().decode())
    except urllib.error.HTTPError as err:
        body = err.read().decode(errors="replace")[:500]
        if err.code == 403:
            raise SheetError(
                "HTTP 403 vom Sheet. Der Service Account braucht Bearbeiter-"
                "Rechte auf dem Sheet - teile es mit seiner client_email. "
                "Antwort: {}".format(body))
        raise SheetError("Sheets API HTTP {}: {}".format(err.code, body))


def get_values(token, range_a1, render=None):
    params = {}
    if render:
        params["valueRenderOption"] = render
    data = _call(token, "/values/" + urllib.parse.quote(range_a1), params=params)
    return data.get("values", [])


def tab_names(token):
    data = _call(token, "", params={"fields": "sheets.properties.title"})
    return [sheet["properties"]["title"] for sheet in data.get("sheets", [])]


# -------------------------------------------------------- Blockaufloesung

def normalize(text):
    return " ".join(str(text or "").split())


def column_letter(index):
    letters = ""
    index += 1
    while index:
        index, rest = divmod(index - 1, 26)
        letters = chr(65 + rest) + letters
    return letters


DATE_FORMATS = ("%d-%m-%Y", "%d.%m.%Y", "%Y-%m-%d", "%d/%m/%Y")


def parse_date(value):
    text = normalize(value)
    for fmt in DATE_FORMATS:
        try:
            return dt.datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


class Block(object):
    def __init__(self, tab, header_row, columns, rows, formulas):
        self.tab = tab
        self.header_row = header_row
        self.columns = columns
        self.rows = rows
        self.formulas = formulas

    def has(self, name):
        return name in self.columns

    def letter(self, name):
        return column_letter(self.columns[name])

    def is_formula(self, name, row):
        return self.formulas.get((row, self.columns[name]), False)

    def cell(self, name, row):
        return "'{}'!{}{}".format(self.tab, self.letter(name), row)


def load_block(token, tab):
    """Loest den Valtrexo-Block eines Monatstabs auf."""
    values = get_values(token, "'{}'!A1:{}{}".format(tab, SCAN_LAST_COLUMN, SCAN_ROWS))
    if not values:
        raise SheetError("Tab '{}' ist leer".format(tab))

    wanted_label = BLOCK_LABEL.casefold()
    label_row = None
    for number, row in enumerate(values, start=1):
        if row and normalize(row[0]).casefold() == wanted_label:
            label_row = number
            break
    if label_row is None:
        raise SheetError(
            "keine Zeile '{}' in '{}' - den Block gibt es dort nicht".format(
                BLOCK_LABEL, tab))

    header_row, header = None, None
    for number in range(label_row + 1,
                        min(label_row + HEADER_SEARCH_DEPTH, len(values)) + 1):
        row = values[number - 1]
        if REVENUE_COLUMN in {normalize(cell) for cell in row}:
            header_row, header = number, row
            break
    if header_row is None:
        raise SheetError("unter '{}' in '{}' keine Kopfzeile mit '{}'".format(
            BLOCK_LABEL, tab, REVENUE_COLUMN))

    columns = {}
    for index, cell in enumerate(header):
        name = normalize(cell)
        if name and name not in columns:
            columns[name] = index

    rows = {}
    for number in range(header_row + 1, len(values) + 1):
        row = values[number - 1]
        day = parse_date(row[0]) if row else None
        if day is None:
            break
        rows[day] = number
    if not rows:
        raise SheetError("keine Tageszeilen unter '{}' in '{}'".format(BLOCK_LABEL, tab))

    last_row = max(rows.values())
    formula_rows = get_values(token, "'{}'!A{}:{}{}".format(
        tab, header_row + 1, SCAN_LAST_COLUMN, last_row), render="FORMULA")
    formulas = {}
    for offset, row in enumerate(formula_rows):
        number = header_row + 1 + offset
        for index, cell in enumerate(row):
            if str(cell).startswith("="):
                formulas[(number, index)] = True

    return Block(tab, header_row, columns, rows, formulas)


def tab_for(day, known):
    """'October 26' - der Monatstab, englisch benannt."""
    wanted = "{} {:02d}".format(MONTH_NAMES[day.month], day.year % 100)
    for title in known:
        if normalize(title).casefold() == wanted.casefold():
            return title
    return None


# ---------------------------------------------------------------- Main

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=7,
                        help="Fenster, das neu geschrieben wird")
    parser.add_argument("--start")
    parser.add_argument("--end")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    today = dt.date.today()
    end = dt.date.fromisoformat(args.end) if args.end else today
    start = (dt.date.fromisoformat(args.start) if args.start
             else end - dt.timedelta(days=args.days - 1))
    if start > end:
        sys.exit("Startdatum liegt hinter dem Enddatum.")

    print("Zeitraum: {} bis {}".format(start, end))

    rows = fetch_daily(start.isoformat(), end.isoformat())
    by_day = {}
    for row in rows:
        day = parse_date(row["date"]) or dt.date.fromisoformat(row["date"])
        by_day[day] = row

    print("\nUmsatz je Tag (EUR), Quelle Shopify:")
    for day in sorted(by_day):
        row = by_day[day]
        print("  {}  Revenue {:>9.2f}   Refunds {:>8.2f}   Orders {}".format(
            day, row["revenue"], row["refunds"], row["orders"]))
    if not by_day:
        print("  keine Tage im Zeitraum")

    if args.dry_run:
        print("\n--dry-run: es wird nichts ins Sheet geschrieben.")
        return 0

    print("\nVerbinde mit Google Sheets...")
    token = access_token(load_service_account())
    known = tab_names(token)

    updates, misses, blocks, written = [], [], {}, {}
    for day in sorted(by_day):
        tab = tab_for(day, known)
        if not tab:
            misses.append("{}: kein Tab gefunden".format(day))
            continue
        if tab not in blocks:
            try:
                block = load_block(token, tab)
                blocks[tab] = block
                print("  Tab '{}': Kopfzeile Zeile {}, Tageszeilen {}-{}, "
                      "{} = Spalte {}".format(
                          tab, block.header_row, min(block.rows.values()),
                          max(block.rows.values()), REVENUE_COLUMN,
                          block.letter(REVENUE_COLUMN)
                          if block.has(REVENUE_COLUMN) else "FEHLT"))
            except SheetError as err:
                blocks[tab] = err
        block = blocks[tab]
        if isinstance(block, SheetError):
            misses.append("{}: Tab '{}' uebersprungen - {}".format(day, tab, block))
            continue
        row_number = block.rows.get(day)
        if not row_number:
            misses.append("{}: keine Zeile im Tab '{}'".format(day, tab))
            continue

        targets = [(REVENUE_COLUMN, by_day[day]["revenue"])]
        # Nur Tage MIT Erstattung anfassen, sonst bleibt die Zelle stehen.
        if by_day[day]["refunds"]:
            targets.append((REFUNDS_COLUMN, by_day[day]["refunds"]))

        for column, value in targets:
            if not block.has(column):
                misses.append("{}: Spalte '{}' fehlt in der Kopfzeile von '{}' - "
                              "uebersprungen".format(day, column, tab))
                continue
            if block.is_formula(column, row_number):
                misses.append("{}: {}{} in '{}' enthaelt eine Formel - nicht "
                              "ueberschrieben".format(
                                  day, block.letter(column), row_number, tab))
                continue
            updates.append({"range": block.cell(column, row_number),
                            "values": [[round(value, 2)]]})
            written[column] = written.get(column, 0) + 1

    if misses:
        print("\nNicht zugeordnet:")
        for line in misses:
            print("  " + line)

    if not updates:
        print("\nNichts zu schreiben.")
        return 0

    _call(token, "/values:batchUpdate", method="POST", payload={
        "valueInputOption": "USER_ENTERED", "data": updates})
    print("\n{} Zellen aktualisiert ({}).".format(
        len(updates), ", ".join("{} x{}".format(name, count)
                                for name, count in sorted(written.items()))))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SheetError as error:
        sys.exit("FEHLER: {}".format(error))
