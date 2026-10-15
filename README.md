# VALTREXO — Shopify Admin API

Direkte Verbindung zur Shopify Admin API über den Client-Credentials-Grant.
Kein MCP, keine Browser-Automation.

- Store: `dts96w-r1.myshopify.com` (Valltrexo)
- App: `valtrexo-api`, Dev Dashboard, Organisation Valltrexo
- Admin API Version: `2026-10` (aktuelle Stable-Version seit 1. Oktober 2026,
  Quelle: https://shopify.dev/docs/api/usage/versioning)

## Secrets

Client ID, Client Secret und Tokens stehen **ausschliesslich** als
Umgebungsvariablen in der Cloud-Umgebung `valtrexo`. Sie gehören nie ins Repo.

| Variable | Inhalt |
|---|---|
| `SHOPIFY_STORE_DOMAIN` | permanente Store-Domain, ohne `https://` |
| `SHOPIFY_CLIENT_ID` | Client ID der App |
| `SHOPIFY_CLIENT_SECRET` | Client Secret der App |
| `SHOPIFY_API_VERSION` | optional, Default `2026-10` |

Das Skript gibt den Access Token nie aus, nur `scope`, `expires_in` und die
Zeichenlänge.

## Token holen

```
POST https://<SHOPIFY_STORE_DOMAIN>/admin/oauth/access_token
Content-Type: application/x-www-form-urlencoded

grant_type=client_credentials
client_id=<SHOPIFY_CLIENT_ID>
client_secret=<SHOPIFY_CLIENT_SECRET>
```

Antwort:

```json
{ "access_token": "...", "scope": "...", "expires_in": 86399 }
```

`expires_in` ist immer 86399, der Token gilt also 24 Stunden. Zum Erneuern
dieselbe Anfrage noch einmal schicken. Der Grant funktioniert nur, wenn App und
Store in derselben Shopify-Organisation liegen, sonst kommt
`shop_not_permitted`.

Quellen:
https://shopify.dev/docs/apps/build/authentication-authorization/access-tokens
https://shopify.dev/docs/apps/build/authentication-authorization/client-credentials-grant

Der Token kommt dann als Header `X-Shopify-Access-Token` an
`POST https://<SHOPIFY_STORE_DOMAIN>/admin/api/<version>/graphql.json`.

## Ausführen

```
python3 scripts/shopify_api.py
```

Gemessene Ausgabe am 2026-10-15:

```
token endpoint: HTTP 200
  scope:        read_orders,read_products,read_reports
  expires_in:   86399
  access_token: 38 chars (not printed)
graphql api version: 2026-10
{
  "shop": {
    "name": "Valltrexo",
    "myshopifyDomain": "dts96w-r1.myshopify.com"
  }
}
```

## Scopes

Aktive Version `valtrexo-api-1`:

```
read_orders, read_products, read_reports
```

Das Feld `scope` in der Token-Antwort ist ein Readback dieser Auswahl. Der
Token-Request fragt keine Scopes an.

Bekannte Grenzen:

- `read_orders` deckt nur Bestellungen der letzten 60 Tage ab. Für ältere
  zusätzlich `read_all_orders`, das bei Shopify beantragt werden muss.
  Quelle: https://shopify.dev/docs/api/usage/access-scopes
- `shopifyqlQuery` braucht `read_reports`, Level 2 Protected Customer Data und
  Admin API 2025-10 oder höher.
  Quelle: https://shopify.dev/docs/apps/build/shopifyql/graphql-admin-api

### Neue Scopes hinzufügen

1. Dev Dashboard → App `valtrexo-api` → **Versions** → **Create version**
2. Scopes ergänzen, Version **Release**
3. Im Shopify Admin die neuen Scopes für die bestehende Installation bestätigen
4. Neuen Token holen und das Feld `scope` prüfen

## Netzwerk

Die Cloud-Umgebung `valtrexo` steht auf Netzwerkzugriff **Benutzerdefiniert**.
Erlaubte Domains:

```
dts96w-r1.myshopify.com
api.ipify.org
shopify.dev
```

Ohne diese Freigabe antwortet der Egress mit `CONNECT tunnel failed, 403`.

## Ausgehende IP dieser Umgebung

Gemessen über `https://api.ipify.org`. Die IP ist nicht fest, sie stammt aus
einem Pool.

| Datum (UTC) | Beobachtete IPs | Zuordnung |
|---|---|---|
| 2026-10-15 00:17 | 160.79.106.20, .137, .140, .142, .143 | Anthropic, PBC (AS399358) |
| 2026-10-15 00:38 | 160.79.106.19, .21, .128, .131, .134 | Anthropic, PBC (AS399358) |

Zum Vergleich mit der Umgebung PNL-KIZORA dort dasselbe messen:

```
curl -sS https://api.ipify.org
```

Hinweis: Diese IP ist unabhängig vom Standort des Nutzers. Das Skript läuft im
Container, der eigene Laptop ist an der Verbindung zu Shopify nicht beteiligt.
Die Zuordnung zu Anthropic stammt aus öffentlichen ASN-Daten, nicht aus einer
Registry-Abfrage — `rdap.arin.net` ist in dieser Umgebung nicht freigegeben.
