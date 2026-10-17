# Routine: Valtrexo-Revenue ins Sheet "PnL"

Verfahren für den täglichen Lauf. Die geplante Aufgabe verweist auf diese
Datei, damit die Logik im Repo liegt und nicht im Prompt.

## Ziel

Sheet **PnL**, ID `1reNOsgEOBzIrL9hH3pXBhLcIBQIoJUwD78iRlS_o_mU`

https://docs.google.com/spreadsheets/d/1reNOsgEOBzIrL9hH3pXBhLcIBQIoJUwD78iRlS_o_mU/edit

Ein Tab pro Monat, englisch benannt: `October 26`, `November 26`, …
Jeder Monatstab enthält mehrere Blöcke untereinander, einen pro Company.

Stand 2026-10-17 im Tab `October 26`:

| Zeile | Inhalt |
|---|---|
| 1 | Header Block 1, `Kizora` |
| 2–32 | Tage 01.–31.10., Kizora |
| 33 | Monatssumme Kizora |
| 37 | Label `COMPANY 2` |
| 38 | Label `Valtrexo` |
| 39 | Header Block 2 |
| **40–70** | **Tage 01.–31.10., Valtrexo** |
| 71 | Monatssumme Valtrexo |
| 76 | Label `COMPANY 3`, dann `Dravonyxion` |
| 78–108 | Tage, Dravonyxion |
| 109 | Monatssumme Dravonyxion |

## Wohin der Umsatz gehört

Im Valtrexo-Block:

| Spalte | Header | Rolle |
|---|---|---|
| **C** | `Revenue Vall` | **hier den Tagesumsatz eintragen** |
| B | `Revenue` | Formel `=C+D`, nicht anfassen |
| M | `Refunds` | optional, Rückerstattungen des Tages |
| E | `Adspend FB` | von Hand, kein Zugang zu Meta |

Tageszeile im Oktober: **Zeile = 39 + Tag**. Der 17.10. ist Zeile 56.

Alle anderen Spalten sind Formeln und bleiben unberührt, ebenso die Blöcke
von Kizora und Dravonyxion.

## Zeilen nicht hart annehmen

Die Offsets hängen an der Monatslänge und daran, wie viele Label-Zeilen über
dem Block stehen. Im Juli und August liegt der zweite Block ebenfalls auf
40–70, im September auf 39–68. Deshalb vor dem Schreiben prüfen:

1. Spalte A des Monatstabs lesen, z.B. `A1:C120`
2. Die Zeile mit `COMPANY 2` suchen, darunter die Headerzeile mit `Revenue`
3. Erste Tageszeile ist die Zeile nach dem Header
4. Gegenprüfen, dass in Spalte A dieser Zeile der 1. des Monats steht
5. Erst dann schreiben, und nur die Zellen der Tage, die wirklich vorliegen

## Quelle der Zahlen

```
python3 scripts/pnl_revenue.py --since 2026-10-11 --json
```

Liefert pro Tag `revenue` und `refunds` aus `shopifyqlQuery`, in EUR und auf
die Tagesgrenze der Shop-Zeitzone `Europe/Amsterdam`. Der Store ist
Valltrexo, `dts96w-r1.myshopify.com`.

## Fenster

Jeden Lauf die **letzten 7 Tage** neu schreiben, nicht nur den Vortag. Späte
Refunds und nachgebuchte Bestellungen ändern ältere Tage noch.

Beginnt ein neuer Monat, gibt es den Tab vielleicht noch nicht. Dann nichts
anlegen, sondern melden — die Monatstabs kommen aus Jeannines Vorlage, nicht
aus dieser Routine.

## Offene Punkte im Sheet

Stand 2026-10-17, bewusst nicht eigenmächtig geändert:

- `J` **SP fee** im Valtrexo-Block rechnet `=D*0.07`. Spalte `D` ist dort
  leer, der Umsatz steht in `C`. Die SP fee bleibt damit 0. Im Kizora-Block
  passt die Formel, weil dort `D` die Umsatzspalte ist. Müsste für Valtrexo
  auf `C` oder `B` zeigen.
- `R` **Profit after DRA + VAL** ist im Valtrexo-Block leer, im Kizora-Block
  steht dort `=Q-F`.
- Block 3 heisst im Oktober `Dravonyxion`, im Juli und August dagegen
  `TOTAL (alle Companies)`. Zwei verschiedene Bedeutungen am selben Platz.
- `June 26` hat gar keinen Valtrexo-Block. Der Umsatz vom 27.06.2026
  (€ 79.99) ist dort nicht eintragbar.

## Historie Valltrexo

Vollständig, über `shopifyqlQuery` gemessen am 2026-10-17:

| Tag | Revenue | Produkt | im Sheet |
|---|---|---|---|
| 27.06.2026 | € 79.99 | Dizzora™ | kein Block in `June 26` |
| 01.07.2026 | € 36.97 | Hylon™ | `July 26!C40` |
| 09.07.2026 | € 49.39 | Botiza™ | `July 26!C48` |
| 08.08.2026 | € 49.53 | Orthix™ | `August 26!C47` |
| 29.08.2026 | € 52.65 | DermaFlex™ | `August 26!C68` |

September und Oktober bis 17.10.: kein Umsatz.
