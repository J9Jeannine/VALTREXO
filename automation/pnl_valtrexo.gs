/**
 * PnL VALLTREXO — Routine im Google Sheet selbst.
 *
 * Baut die Monatstabs im Layout von "PnL KIZORA" und traegt jeden Tag
 * Revenue und Refunds aus der Shopify Admin API ein, dazu den Adspend aus
 * der Meta Marketing API, sobald dafuer ein Token gesetzt ist.
 *
 * Laeuft auf Googles Servern, also unabhaengig von der Cloud-Umgebung und
 * ohne Netzwerkfreigabe.
 *
 * Einrichtung: siehe automation/README.md im Repo J9Jeannine/VALTREXO.
 *
 * Script Properties:
 *   SHOPIFY_STORE_DOMAIN    dts96w-r1.myshopify.com
 *   SHOPIFY_CLIENT_ID       Client ID der App valtrexo-api
 *   SHOPIFY_CLIENT_SECRET   Client Secret der App valtrexo-api
 *   SHOPIFY_API_VERSION     optional, Default 2026-10
 *   META_ACCESS_TOKEN       optional, sonst bleibt Adspend FB von Hand
 *   META_AD_ACCOUNT_ID      optional, z.B. act_1234567890 oder 1234567890
 *   META_API_VERSION        optional, Default v23.0
 */

var SETTINGS_TAB = 'Settings';
var START_MONTH = '2026-06';   // erster Monat, den setupSheet anlegt
var SYNC_DAYS = 7;             // Fenster, das dailySync jedes Mal neu schreibt

// Spaltenlayout. Reihenfolge wie in scripts/build_pnl_workbook.py.
var HEADERS = [
  'Date', 'Revenue', 'Adspend FB', 'Adspend Pint', 'Cogs', 'SP fee', 'FB fee',
  'Transaction', 'Refunds', "Abo's", 'extra Costs', 'Team Costs', 'Profit',
  'ROAS', 'Profit %', 'Cogs %', '', 'Payouts', 'Invoices', 'Extra Expenses',
  'Profit after Expenses'
];

var COL = {
  DATE: 1, REVENUE: 2, ADSPEND_FB: 3, ADSPEND_PINT: 4, COGS: 5, SP_FEE: 6,
  FB_FEE: 7, TRANSACTION: 8, REFUNDS: 9, ABOS: 10, EXTRA: 11, TEAM: 12,
  PROFIT: 13, ROAS: 14, PROFIT_PCT: 15, COGS_PCT: 16, SPACER: 17,
  PAYOUTS: 18, INVOICES: 19, EXTRA_EXPENSES: 20, PROFIT_AFTER: 21
};

var FIRST_DATA_ROW = 2;

// Settings-Zeilen. Muessen zu scripts/build_pnl_workbook.py passen.
var SETTINGS_ROWS = [
  ['Store', 'Valltrexo', 'dts96w-r1.myshopify.com'],
  ['Currency', 'EUR', 'Shop-Waehrung'],
  ['Timezone', 'Europe/Amsterdam', 'Tagesgrenze der Umsatzzahlen'],
  ['Cogs %', 0.20, 'Anteil vom Revenue, bis echte Einkaufspreise stehen'],
  ['SP fee %', 0.07, 'Shopify Payments'],
  ['FB fee %', 0.06, 'Anteil vom Adspend'],
  ['Transaction %', 0.0435, 'Zahlungsgebuehren'],
  ["Abo's per day", 0, 'Tools und Abos pro Tag'],
  ['extra Costs per day', 0, 'sonstige laufende Kosten pro Tag'],
  ['Team Costs per day', 0, 'Team pro Tag'],
  ['Payouts per day', 0, 'Auszahlungen pro Tag'],
  ['Invoices per day', 0, 'Rechnungen pro Tag'],
  ['Extra Expenses per day', 0, 'Einmalkosten pro Tag umgelegt']
];

var SETTING_ROW = {};   // Label -> Zeilennummer im Settings-Tab
for (var i = 0; i < SETTINGS_ROWS.length; i++) {
  SETTING_ROW[SETTINGS_ROWS[i][0]] = i + 2;
}

var EURO_FORMAT = '"€ "#,##0.00';
var RATIO_FORMAT = '0.00';
var PERCENT_FORMAT = '0.00%';
var DATE_FORMAT = 'dd-mm-yyyy';

var AUTO_COLOR = '#e2efda';     // traegt die Routine ein
var MANUAL_COLOR = '#fff2cc';   // von Hand
var HEADER_COLOR = '#1f3864';

/* ------------------------------------------------------------------ Menu */

function onOpen() {
  SpreadsheetApp.getUi()
    .createMenu('PnL')
    .addItem('Heute und letzte Tage aktualisieren', 'dailySync')
    .addItem('Alles neu aufbauen und backfillen', 'setupAndBackfill')
    .addSeparator()
    .addItem('Taeglichen Trigger einrichten', 'installDailyTrigger')
    .addItem('Verbindung testen', 'testConnection')
    .addToUi();
}

/* ------------------------------------------------------- Oeffentliche Jobs */

/**
 * Laeuft taeglich per Trigger. Schreibt die letzten SYNC_DAYS Tage neu,
 * damit spaete Refunds und Adspend-Korrekturen noch ankommen.
 */
function dailySync() {
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  var tz = ss.getSpreadsheetTimeZone();
  var until = new Date();
  var since = new Date(until.getTime() - (SYNC_DAYS - 1) * 86400000);

  ensureSettings_(ss);
  ensureTabsForRange_(ss, since, until);

  var revenue = fetchRevenue_(ymd_(since, tz), ymd_(until, tz));
  var spend = fetchMetaSpend_(ymd_(since, tz), ymd_(until, tz));

  var written = applyData_(ss, tz, revenue, spend);
  Logger.log('dailySync: ' + written + ' Tageszeilen geschrieben');
  return written;
}

/** Baut alle Tabs ab START_MONTH und holt die komplette Historie. */
function setupAndBackfill() {
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  var tz = ss.getSpreadsheetTimeZone();

  // Der leere Standardtab heisst je nach Locale anders, deshalb vorher merken.
  var preexisting = ss.getSheets();

  ensureSettings_(ss);

  var start = monthStart_(START_MONTH);
  var today = new Date();
  ensureTabsForRange_(ss, start, today);

  var revenue = fetchRevenue_(ymd_(start, tz), ymd_(today, tz));
  var spend = fetchMetaSpend_(ymd_(start, tz), ymd_(today, tz));

  var written = applyData_(ss, tz, revenue, spend);

  // Leere Standardtabs raeumen, aber nur wenn wirklich nichts drinsteht.
  for (var i = 0; i < preexisting.length; i++) {
    var sheet = preexisting[i];
    if (sheet.getName() !== SETTINGS_TAB && sheet.getLastRow() === 0 &&
        ss.getSheets().length > 1) {
      ss.deleteSheet(sheet);
    }
  }
  ss.setActiveSheet(ss.getSheetByName(tabNameFor_(today, tz)));

  Logger.log('setupAndBackfill: ' + written + ' Tageszeilen geschrieben');
  return written;
}

/** Legt den taeglichen Trigger an, ohne Duplikate. */
function installDailyTrigger() {
  var existing = ScriptApp.getProjectTriggers();
  for (var i = 0; i < existing.length; i++) {
    if (existing[i].getHandlerFunction() === 'dailySync') {
      ScriptApp.deleteTrigger(existing[i]);
    }
  }
  ScriptApp.newTrigger('dailySync')
    .timeBased()
    .atHour(6)
    .everyDays(1)
    .inTimezone(SpreadsheetApp.getActiveSpreadsheet().getSpreadsheetTimeZone())
    .create();
  Logger.log('Trigger dailySync laeuft jetzt taeglich zwischen 6 und 7 Uhr');
}

/** Prueft Shopify und, wenn konfiguriert, Meta. Schreibt nichts. */
function testConnection() {
  var lines = [];

  try {
    var token = shopifyToken_();
    lines.push('Shopify Token: ok (' + token.length + ' Zeichen)');
    var shop = shopifyGraphQL_('{ shop { name currencyCode ianaTimezone } }').shop;
    lines.push('Shop: ' + shop.name + ', ' + shop.currencyCode + ', ' + shop.ianaTimezone);
  } catch (error) {
    lines.push('Shopify FEHLER: ' + error.message);
  }

  var props = PropertiesService.getScriptProperties();
  if (props.getProperty('META_ACCESS_TOKEN') && props.getProperty('META_AD_ACCOUNT_ID')) {
    try {
      var tz = SpreadsheetApp.getActiveSpreadsheet().getSpreadsheetTimeZone();
      var today = ymd_(new Date(), tz);
      var spend = fetchMetaSpend_(today, today);
      lines.push('Meta: ok, ' + Object.keys(spend).length + ' Tage geliefert');
    } catch (metaError) {
      lines.push('Meta FEHLER: ' + metaError.message);
    }
  } else {
    lines.push('Meta: nicht konfiguriert, Adspend FB bleibt von Hand');
  }

  var text = lines.join('\n');
  Logger.log(text);
  try {
    SpreadsheetApp.getUi().alert(text);
  } catch (uiError) {
    // kein UI-Kontext, z.B. aus einem Trigger heraus
  }
  return text;
}

/* ------------------------------------------------------------- Shopify */

function requiredProp_(name) {
  var value = PropertiesService.getScriptProperties().getProperty(name);
  if (!value) {
    throw new Error('Script Property fehlt: ' + name);
  }
  return value;
}

/**
 * Client-Credentials-Grant. Der Token gilt 24 Stunden, wir cachen ihn 6.
 * https://shopify.dev/docs/apps/build/authentication-authorization/client-credentials-grant
 */
function shopifyToken_() {
  var cache = CacheService.getScriptCache();
  var cached = cache.get('shopify_token');
  if (cached) {
    return cached;
  }

  var domain = requiredProp_('SHOPIFY_STORE_DOMAIN');
  var response = UrlFetchApp.fetch('https://' + domain + '/admin/oauth/access_token', {
    method: 'post',
    payload: {
      grant_type: 'client_credentials',
      client_id: requiredProp_('SHOPIFY_CLIENT_ID'),
      client_secret: requiredProp_('SHOPIFY_CLIENT_SECRET')
    },
    muteHttpExceptions: true
  });

  if (response.getResponseCode() !== 200) {
    throw new Error('Shopify Token HTTP ' + response.getResponseCode() + ': ' +
                    response.getContentText().slice(0, 200));
  }

  var token = JSON.parse(response.getContentText()).access_token;
  if (!token) {
    throw new Error('Shopify Token fehlt in der Antwort');
  }
  cache.put('shopify_token', token, 21600);
  return token;
}

function shopifyGraphQL_(query, variables) {
  var domain = requiredProp_('SHOPIFY_STORE_DOMAIN');
  var version = PropertiesService.getScriptProperties()
    .getProperty('SHOPIFY_API_VERSION') || '2026-10';
  var url = 'https://' + domain + '/admin/api/' + version + '/graphql.json';

  // shopifyqlQuery kostet rund 900 der 1000 Punkte pro Fenster.
  for (var attempt = 0; attempt < 5; attempt++) {
    var response = UrlFetchApp.fetch(url, {
      method: 'post',
      contentType: 'application/json',
      headers: { 'X-Shopify-Access-Token': shopifyToken_() },
      payload: JSON.stringify({ query: query, variables: variables || {} }),
      muteHttpExceptions: true
    });

    var body = response.getContentText();
    if (response.getResponseCode() !== 200) {
      throw new Error('Shopify GraphQL HTTP ' + response.getResponseCode() + ': ' +
                      body.slice(0, 200));
    }

    var payload = JSON.parse(body);
    if (payload.errors) {
      var throttled = JSON.stringify(payload.errors).indexOf('THROTTLED') !== -1;
      if (throttled && attempt < 4) {
        Utilities.sleep(20000);
        continue;
      }
      throw new Error('Shopify GraphQL: ' + JSON.stringify(payload.errors).slice(0, 300));
    }
    return payload.data;
  }
  throw new Error('Shopify GraphQL: dauerhaft rate limited');
}

/**
 * Taegliche Umsatzzahlen. Shopifys eigene Werte in Shop-Waehrung, inklusive
 * Umrechnung von Fremdwaehrungs-Bestellungen.
 * Liefert { 'yyyy-MM-dd': { revenue: Number, refunds: Number } }
 */
function fetchRevenue_(since, until) {
  var ql = 'FROM sales SHOW total_sales, sales_reversals ' +
           'TIMESERIES day SINCE ' + since + ' UNTIL ' + until + ' ORDER BY day';

  var query = 'query($ql: String!) { shopifyqlQuery(query: $ql) { parseErrors ' +
              'tableData { columns { name } rows } } }';

  var result = shopifyGraphQL_(query, { ql: ql }).shopifyqlQuery;
  if (result.parseErrors && result.parseErrors.length) {
    throw new Error('ShopifyQL: ' + result.parseErrors.join('; '));
  }
  if (!result.tableData) {
    return {};
  }

  var out = {};
  var rows = result.tableData.rows;
  for (var i = 0; i < rows.length; i++) {
    var row = rows[i];
    out[row.day] = {
      revenue: round2_(Number(row.total_sales || 0)),
      refunds: round2_(Math.abs(Number(row.sales_reversals || 0)))
    };
  }
  return out;
}

/* ---------------------------------------------------------------- Meta */

/**
 * Taeglicher Adspend. Ohne Token leer, dann bleibt die Spalte von Hand.
 * Liefert { 'yyyy-MM-dd': Number }
 */
function fetchMetaSpend_(since, until) {
  var props = PropertiesService.getScriptProperties();
  var token = props.getProperty('META_ACCESS_TOKEN');
  var account = props.getProperty('META_AD_ACCOUNT_ID');
  if (!token || !account) {
    return {};
  }

  if (account.indexOf('act_') !== 0) {
    account = 'act_' + account;
  }
  var version = props.getProperty('META_API_VERSION') || 'v23.0';

  var out = {};
  var url = 'https://graph.facebook.com/' + version + '/' + account + '/insights' +
            '?fields=spend' +
            '&time_increment=1' +
            '&level=account' +
            '&time_range=' + encodeURIComponent(JSON.stringify({ since: since, until: until })) +
            '&limit=500' +
            '&access_token=' + encodeURIComponent(token);

  while (url) {
    var response = UrlFetchApp.fetch(url, { muteHttpExceptions: true });
    var body = response.getContentText();
    if (response.getResponseCode() !== 200) {
      throw new Error('Meta HTTP ' + response.getResponseCode() + ': ' + body.slice(0, 300));
    }
    var payload = JSON.parse(body);
    var data = payload.data || [];
    for (var i = 0; i < data.length; i++) {
      out[data[i].date_start] = round2_(Number(data[i].spend || 0));
    }
    url = payload.paging && payload.paging.next ? payload.paging.next : null;
  }
  return out;
}

/* --------------------------------------------------------- Sheet-Aufbau */

function ensureSettings_(ss) {
  var sheet = ss.getSheetByName(SETTINGS_TAB);
  if (sheet) {
    return sheet;
  }

  sheet = ss.insertSheet(SETTINGS_TAB, 0);
  sheet.getRange('A1:C1').setValues([['Setting', 'Value', 'Note']])
    .setBackground(HEADER_COLOR).setFontColor('#ffffff').setFontWeight('bold');

  sheet.getRange(2, 1, SETTINGS_ROWS.length, 3).setValues(SETTINGS_ROWS);

  for (var i = 0; i < SETTINGS_ROWS.length; i++) {
    var label = SETTINGS_ROWS[i][0];
    var cell = sheet.getRange(i + 2, 2).setBackground(MANUAL_COLOR);
    if (label.slice(-1) === '%') {
      cell.setNumberFormat(PERCENT_FORMAT);
    } else if (label.indexOf('per day') !== -1) {
      cell.setNumberFormat(EURO_FORMAT);
    }
  }

  var legend = SETTINGS_ROWS.length + 4;
  sheet.getRange(legend, 1).setValue('Legende').setFontWeight('bold');
  sheet.getRange(legend + 1, 1).setValue('gruen').setBackground(AUTO_COLOR);
  sheet.getRange(legend + 1, 2).setValue('traegt die Routine ein (Revenue, Adspend FB, Refunds)');
  sheet.getRange(legend + 2, 1).setValue('gelb').setBackground(MANUAL_COLOR);
  sheet.getRange(legend + 2, 2).setValue('von Hand eintragen');
  sheet.getRange(legend + 3, 1).setValue('weiss');
  sheet.getRange(legend + 3, 2).setValue('Formel, nicht ueberschreiben');

  sheet.setColumnWidth(1, 170);
  sheet.setColumnWidth(2, 170);
  sheet.setColumnWidth(3, 360);
  return sheet;
}

function settingRef_(label) {
  return SETTINGS_TAB + '!$B$' + SETTING_ROW[label];
}

/** Legt fuer jeden Monat zwischen since und until einen Tab an. */
function ensureTabsForRange_(ss, since, until) {
  var tz = ss.getSpreadsheetTimeZone();
  var year = Number(Utilities.formatDate(since, tz, 'yyyy'));
  var month = Number(Utilities.formatDate(since, tz, 'MM'));
  var lastYear = Number(Utilities.formatDate(until, tz, 'yyyy'));
  var lastMonth = Number(Utilities.formatDate(until, tz, 'MM'));

  while (year * 12 + month <= lastYear * 12 + lastMonth) {
    ensureMonthTab_(ss, year, month);
    month++;
    if (month === 13) {
      year++;
      month = 1;
    }
  }
}

function ensureMonthTab_(ss, year, month) {
  var tz = ss.getSpreadsheetTimeZone();
  var name = tabNameFor_(new Date(year, month - 1, 1), tz);
  var existing = ss.getSheetByName(name);
  if (existing) {
    return existing;
  }

  var sheet = ss.insertSheet(name);
  var days = new Date(year, month, 0).getDate();

  sheet.getRange(1, 1, 1, HEADERS.length).setValues([HEADERS])
    .setBackground(HEADER_COLOR).setFontColor('#ffffff').setFontWeight('bold')
    .setWrap(true).setHorizontalAlignment('center');

  var dates = [];
  var formulas = [];
  for (var day = 1; day <= days; day++) {
    var row = FIRST_DATA_ROW + day - 1;
    dates.push([new Date(year, month - 1, day)]);
    formulas.push(dayFormulaRow_(row));
  }

  sheet.getRange(FIRST_DATA_ROW, COL.DATE, days, 1)
    .setValues(dates).setNumberFormat(DATE_FORMAT);

  // Formelspalten E bis P und R bis U, in einem Rutsch.
  sheet.getRange(FIRST_DATA_ROW, COL.COGS, days, COL.PROFIT_AFTER - COL.COGS + 1)
    .setFormulas(formulas);

  // Spalten, die die Routine fuellt, und die von Hand.
  sheet.getRange(FIRST_DATA_ROW, COL.REVENUE, days, 1).setBackground(AUTO_COLOR);
  sheet.getRange(FIRST_DATA_ROW, COL.ADSPEND_FB, days, 1).setBackground(AUTO_COLOR);
  sheet.getRange(FIRST_DATA_ROW, COL.REFUNDS, days, 1).setBackground(AUTO_COLOR);
  sheet.getRange(FIRST_DATA_ROW, COL.ADSPEND_PINT, days, 1).setBackground(MANUAL_COLOR);

  applyNumberFormats_(sheet, FIRST_DATA_ROW, days);
  writeTotalRow_(sheet, days);

  sheet.setColumnWidth(COL.DATE, 95);
  sheet.setColumnWidth(COL.SPACER, 24);
  sheet.setColumnWidth(COL.PROFIT_AFTER, 150);
  sheet.setFrozenRows(1);
  sheet.setFrozenColumns(1);
  return sheet;
}

/** Formeln einer Tageszeile, Spalten E bis U. */
function dayFormulaRow_(row) {
  return [
    '=ROUND(B' + row + '*' + settingRef_('Cogs %') + ',2)',                    // E Cogs
    '=ROUND(B' + row + '*' + settingRef_('SP fee %') + ',2)',                  // F SP fee
    '=ROUND((C' + row + '+D' + row + ')*' + settingRef_('FB fee %') + ',2)',   // G FB fee
    '=ROUND(B' + row + '*' + settingRef_('Transaction %') + ',2)',             // H Transaction
    '',                                                                        // I Refunds
    '=' + settingRef_("Abo's per day"),                                        // J
    '=' + settingRef_('extra Costs per day'),                                  // K
    '=' + settingRef_('Team Costs per day'),                                   // L
    '=B' + row + '-C' + row + '-D' + row + '-E' + row + '-F' + row + '-G' +
      row + '-H' + row + '-I' + row + '-J' + row + '-K' + row + '-L' + row,    // M Profit
    '=IF((C' + row + '+D' + row + ')=0,0,B' + row + '/(C' + row + '+D' + row + '))', // N ROAS
    '=IF(B' + row + '=0,0,M' + row + '/B' + row + ')',                         // O Profit %
    '=IF(B' + row + '=0,0,E' + row + '/B' + row + ')',                         // P Cogs %
    '',                                                                        // Q Spacer
    '=' + settingRef_('Payouts per day'),                                      // R
    '=' + settingRef_('Invoices per day'),                                     // S
    '=' + settingRef_('Extra Expenses per day'),                               // T
    '=M' + row + '-R' + row + '-S' + row + '-T' + row                          // U
  ];
}

function writeTotalRow_(sheet, days) {
  var firstRow = FIRST_DATA_ROW;
  var lastRow = FIRST_DATA_ROW + days - 1;
  var totalRow = lastRow + 1;

  sheet.getRange(totalRow, COL.DATE).setValue('TOTAL').setFontWeight('bold');

  var moneyColumns = [
    COL.REVENUE, COL.ADSPEND_FB, COL.ADSPEND_PINT, COL.COGS, COL.SP_FEE,
    COL.FB_FEE, COL.TRANSACTION, COL.REFUNDS, COL.ABOS, COL.EXTRA, COL.TEAM,
    COL.PROFIT, COL.PAYOUTS, COL.INVOICES, COL.EXTRA_EXPENSES, COL.PROFIT_AFTER
  ];

  for (var i = 0; i < moneyColumns.length; i++) {
    var letter = columnLetter_(moneyColumns[i]);
    sheet.getRange(totalRow, moneyColumns[i])
      .setFormula('=SUM(' + letter + firstRow + ':' + letter + lastRow + ')')
      .setNumberFormat(EURO_FORMAT).setFontWeight('bold');
  }

  sheet.getRange(totalRow, COL.ROAS)
    .setFormula('=IF((C' + totalRow + '+D' + totalRow + ')=0,0,B' + totalRow +
                '/(C' + totalRow + '+D' + totalRow + '))')
    .setNumberFormat(RATIO_FORMAT).setFontWeight('bold');
  sheet.getRange(totalRow, COL.PROFIT_PCT)
    .setFormula('=IF(B' + totalRow + '=0,0,M' + totalRow + '/B' + totalRow + ')')
    .setNumberFormat(PERCENT_FORMAT).setFontWeight('bold');
  sheet.getRange(totalRow, COL.COGS_PCT)
    .setFormula('=IF(B' + totalRow + '=0,0,E' + totalRow + '/B' + totalRow + ')')
    .setNumberFormat(PERCENT_FORMAT).setFontWeight('bold');
}

function applyNumberFormats_(sheet, startRow, rowCount) {
  var money = [
    COL.REVENUE, COL.ADSPEND_FB, COL.ADSPEND_PINT, COL.COGS, COL.SP_FEE,
    COL.FB_FEE, COL.TRANSACTION, COL.REFUNDS, COL.ABOS, COL.EXTRA, COL.TEAM,
    COL.PROFIT, COL.PAYOUTS, COL.INVOICES, COL.EXTRA_EXPENSES, COL.PROFIT_AFTER
  ];
  for (var i = 0; i < money.length; i++) {
    sheet.getRange(startRow, money[i], rowCount, 1).setNumberFormat(EURO_FORMAT);
  }
  sheet.getRange(startRow, COL.ROAS, rowCount, 1).setNumberFormat(RATIO_FORMAT);
  sheet.getRange(startRow, COL.PROFIT_PCT, rowCount, 1).setNumberFormat(PERCENT_FORMAT);
  sheet.getRange(startRow, COL.COGS_PCT, rowCount, 1).setNumberFormat(PERCENT_FORMAT);
}

/* ------------------------------------------------------- Daten schreiben */

/**
 * Traegt Revenue, Refunds und Adspend in die passenden Monatstabs ein.
 * Schreibt nur diese drei Spalten, alles andere bleibt unberuehrt.
 */
function applyData_(ss, tz, revenue, spend) {
  var dates = {};
  Object.keys(revenue).forEach(function (date) { dates[date] = true; });
  Object.keys(spend).forEach(function (date) { dates[date] = true; });

  var sorted = Object.keys(dates).sort();
  var written = 0;

  for (var i = 0; i < sorted.length; i++) {
    var date = sorted[i];
    var parts = date.split('-');
    var asDate = new Date(Number(parts[0]), Number(parts[1]) - 1, Number(parts[2]));
    var sheet = ss.getSheetByName(tabNameFor_(asDate, tz));
    if (!sheet) {
      continue;
    }

    var row = FIRST_DATA_ROW + Number(parts[2]) - 1;

    if (revenue[date]) {
      sheet.getRange(row, COL.REVENUE).setValue(revenue[date].revenue);
      sheet.getRange(row, COL.REFUNDS).setValue(revenue[date].refunds);
    }
    if (spend[date] !== undefined) {
      sheet.getRange(row, COL.ADSPEND_FB).setValue(spend[date]);
    }
    written++;
  }

  SpreadsheetApp.flush();
  return written;
}

/* ------------------------------------------------------------- Helpers */

// Feste englische Monatsnamen, damit die Tabs heissen wie in "PnL KIZORA".
// Utilities.formatDate haengt an der Locale und wuerde sonst "Juni 26" liefern.
var MONTH_NAMES = [
  'January', 'February', 'March', 'April', 'May', 'June',
  'July', 'August', 'September', 'October', 'November', 'December'
];

function tabNameFor_(date, tz) {
  var zone = tz || SpreadsheetApp.getActiveSpreadsheet().getSpreadsheetTimeZone();
  var month = Number(Utilities.formatDate(date, zone, 'MM'));
  var year = Utilities.formatDate(date, zone, 'yy');
  return MONTH_NAMES[month - 1] + ' ' + year;
}

function ymd_(date, tz) {
  return Utilities.formatDate(date, tz, 'yyyy-MM-dd');
}

function monthStart_(yyyyMM) {
  var parts = yyyyMM.split('-');
  return new Date(Number(parts[0]), Number(parts[1]) - 1, 1);
}

function round2_(value) {
  return Math.round(value * 100) / 100;
}

function columnLetter_(index) {
  var letter = '';
  while (index > 0) {
    var remainder = (index - 1) % 26;
    letter = String.fromCharCode(65 + remainder) + letter;
    index = Math.floor((index - 1) / 26);
  }
  return letter;
}
