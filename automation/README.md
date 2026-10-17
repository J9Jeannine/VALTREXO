# PnL VALLTREXO — Routine einrichten

Das Sheet liegt im selben Drive-Ordner wie `PnL KIZORA`:

https://docs.google.com/spreadsheets/d/1PKX11uGNclncm_B-Ai-OJ-1C5K3sEIuANo9mjBRAq0E/edit

Die Routine läuft als Apps Script **im Sheet selbst**, auf Googles Servern.
Damit ist sie unabhängig von der Cloud-Umgebung `valtrexo`: sie läuft auch,
wenn hier keine Session offen ist, und braucht keine Netzwerkfreigabe.

## Warum nicht aus dieser Umgebung heraus

Zum Schreiben in ein Google Sheet bräuchte es die Google Sheets API. Dafür
fehlen hier zwei Dinge: ein Service-Account-Key als Umgebungsvariable und die
Domains `sheets.googleapis.com` und `oauth2.googleapis.com` in der
Netzwerkfreigabe. Der Drive-Connector in der Session kann Dateien anlegen und
lesen, aber keine Zellen schreiben. Apps Script umgeht beides.

## Einrichtung, einmalig

1. Sheet öffnen → **Erweiterungen** → **Apps Script**
2. Inhalt von `automation/pnl_valtrexo.gs` in die Datei `Code.gs` einfügen,
   alles Vorhandene ersetzen, speichern
3. Links auf das Zahnrad **Projekteinstellungen** → ganz unten
   **Skripteigenschaften** → diese drei anlegen:

   | Eigenschaft | Wert |
   |---|---|
   | `SHOPIFY_STORE_DOMAIN` | `dts96w-r1.myshopify.com` |
   | `SHOPIFY_CLIENT_ID` | Client ID der App `valtrexo-api` |
   | `SHOPIFY_CLIENT_SECRET` | Client Secret der App `valtrexo-api` |

   Client ID und Secret stehen im Dev Dashboard bei der App `valtrexo-api`
   und als Umgebungsvariablen in der Cloud-Umgebung `valtrexo`.

4. Oben die Funktion `setupAndBackfill` auswählen und **Ausführen**. Beim
   ersten Mal fragt Google nach der Freigabe — bestätigen. Das Skript legt
   `Settings` und die Monatstabs ab Juni 26 an und holt die Umsätze.
5. Funktion `installDailyTrigger` auswählen und **Ausführen**. Danach läuft
   `dailySync` jeden Morgen zwischen 6 und 7 Uhr Amsterdamer Zeit.

Im Sheet erscheint nach einem Reload ein Menü **PnL** mit denselben
Funktionen plus **Verbindung testen**.

## Ad-Spend von Meta

Solange kein Meta-Token gesetzt ist, bleibt `Adspend FB` eine Spalte von
Hand — genau wie heute in `PnL KIZORA`. Für die Automatik zwei weitere
Skripteigenschaften anlegen:

| Eigenschaft | Wert |
|---|---|
| `META_ACCESS_TOKEN` | System-User-Token mit `ads_read` |
| `META_AD_ACCOUNT_ID` | z.B. `act_1234567890` |
| `META_API_VERSION` | optional, Default `v23.0` |

Den Token im Meta Business Manager unter **Systembenutzer** erzeugen und ein
langlebiges Token wählen, sonst läuft er nach rund 60 Tagen ab. Antwortet
Meta mit einem Fehler zur API-Version, `META_API_VERSION` auf eine aktuelle
Version setzen.

`Adspend Pint` bleibt in jedem Fall von Hand, für Pinterest gibt es hier
keinen Zugang.

## Was die Routine schreibt

Nur drei Spalten, alles andere bleibt unangetastet:

| Spalte | Quelle |
|---|---|
| `B` Revenue | Shopify, `total_sales` pro Tag |
| `C` Adspend FB | Meta, `spend` pro Tag, wenn Token gesetzt |
| `I` Refunds | Shopify, `sales_reversals` pro Tag |

`dailySync` schreibt jedes Mal die letzten 7 Tage neu, damit späte Refunds
und Adspend-Korrekturen noch ankommen. Beginnt ein neuer Monat, legt die
Routine den Tab selbst an.

Revenue ist Shopifys eigene Zahl in **EUR**, inklusive Umrechnung von
Bestellungen in Fremdwährung. Die Tagesgrenze ist die Shop-Zeitzone
`Europe/Amsterdam`.

## Spaltenfarben

- **grün** — trägt die Routine ein, nicht von Hand überschreiben
- **gelb** — von Hand: `Adspend Pint` und die Raten im Tab `Settings`
- **weiß** — Formel

## Raten im Tab Settings

Cogs, Gebühren und Fixkosten sind Formeln auf die Werte in `Settings`, nicht
fest eingetippt. Die Startwerte sind aus `PnL KIZORA` übernommen und als
Platzhalter zu verstehen:

| Rate | Startwert |
|---|---|
| Cogs % | 20.00% |
| SP fee % | 7.00% |
| Transaction % | 4.35% |
| FB fee % | 6.00% |
| Abo's, extra Costs, Team Costs, Payouts, Invoices, Extra Expenses pro Tag | € 0.00 |

Die Werte in `Settings` gelten für alle Monatstabs gleichzeitig. Wer einen
echten Einkaufspreis pro Produkt rechnen will, überschreibt die Formel in
Spalte `E` des jeweiligen Tages.

## Fallback ohne Apps Script

`scripts/build_pnl_workbook.py` baut dieselbe Mappe als `.xlsx`, inklusive
Umsatzhistorie, zum Hochladen nach Drive. Dann fehlt aber die Routine, die
Zahlen müssten von Hand kommen.

```
python3 scripts/pnl_revenue.py --since 2026-06-01 --json > seed.json
python3 scripts/build_pnl_workbook.py --out PnL_VALLTREXO.xlsx \
    --start 2026-06 --months 7 --seed seed.json
```
