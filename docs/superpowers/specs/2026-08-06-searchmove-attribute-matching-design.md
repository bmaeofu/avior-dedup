# Design: XML-Attribut-Matching in searchmove (Ansatz 1)

Datum: 2026-08-06
Status: genehmigt (User-Review ausstehend)
Scope: `avior_dedup/searchmove` — Expression-Sprache für `.nfo`-Dateien

## Problem

Die searchmove-Expression-Sprache kann bei `.nfo`-Dateien (XML) nur
Element-**Text**, Existenz und numerische Bedingungen matchen. XML-**Attribute**
wie `name="themoviedb"` in `<rating name="themoviedb" max="10">` sind nicht
adressierbar. `rating@name:themoviedb` crasht heute sogar (`KeyError: '@'`,
ungültiger XPath-Token in `findall`).

Anwendungsfall des Users: Film-Sets (`.mkv` + Siblings) verschieben, wenn die
zugehörige `.nfo` ein `<rating name="themoviedb">` enthält, optional mit
Wert-Bedingung auf das gematchte Element (z. B. themoviedb-Rating > 5.4).

## Syntax

Neue Termform (nur für XML-Dateien):

```
path@selector:cond[@selector:cond...]
```

- `path` — Elementpfad (siehe Rekursion).
- `selector` — Attributname des Elements **oder** Name eines Kind-Elements.
- `cond` — Vergleichsbedingung, identische Kette wie bei `tag:value`:
  - numerisch: `>5.4`, `<=6`, `4-6`, `>4<6`, `==7`, `7` (via `parse_condition`)
  - `exists` / `!exists`
  - Wildcard: `*imdb*`, `themo*`, `*db`
  - exakt (case-insensitiv)
- `@selector` ohne `cond` = Existenz-Check (Attribut oder Kind vorhanden).

Mehrere `@selector:cond`-Spezifikationen müssen **auf demselben Element**
erfüllt sein (element-gescoptes UND).

## Semantik

### Routing

In `search_xml_file._xml_match` wird ein Term nur dann auf den neuen Pfad
geroutet, wenn er ein `@` enthält. Reihenfolge der Prüfungen pro Term:

1. Metadaten-Terme (`fileext:`, `sibling:`, `errors:`) — unverändert zuerst.
2. `@`-Term → `_xml_attr_match` (neu).
3. `tag:value`-Term → bestehende Logik unverändert.

Terms ohne `@` laufen durch exakt denselben Code wie heute. Der `rating:`
-Sonderfall (`_select_rating`, numerisch) bleibt unberührt, ebenso der Parser
(`parse_search_expression` mit `&`/`|`) — dort gibt es **keine** Änderung.

### Parsing eines `@`-Terms

```
path, spec_str = term.split("@", 1)   # nur das ERSTE @ trennt path ab
specs = spec_str.split("@")           # weitere @ trennen die Spezifikationen
# jede spec: selector[:cond] via partition(":")
```

Dadurch überleben `@`-Zeichen im `cond`-Teil (z. B. `@name:*@*`).

Ungültige Terme matchen **nie** und werfen **keine** Exception:
- leerer `path` (`@name:x`)
- leerer `selector` (`rating@:x`)
- leere `spec` (trailing `@`, z. B. `rating@name:x@`)

### Rekursion

- `path` **ohne** `/` → rekursive Suche `findall(".//" + path)`. Damit matcht
  `rating@name:themoviedb` das verschachtelte `<ratings><rating>…` ohne
  Pfadkenntnis. (Verifiziert: `findall("rating")` = 0 Treffer,
  `findall(".//rating")` = 2 Treffer bei verschachtelten Ratings.)
- `path` **mit** `/` → unverändert als Pfad: `findall(path)`, z. B.
  `ratings/rating@name:themoviedb`. Pfade, die bereits `.//` enthalten, werden
  ebenfalls direkt verwendet.
- Die Rekursion gilt **nur** für `@`-Terme. Bestehende `tag:value`-Terme
  behalten ihre Direkt-Kind-Semantik (kein Verhaltensbruch).

### Selector-Auflösung

`selector` wird zuerst als Attribut gesucht (case-insensitiv über
`node.attrib`), sonst als Kind-Element (case-insensitiv über die Kinder).
Attribut gewinnt bei Namensgleichheit. Bei NFO-Daten kollidieren Attribut- und
Kind-Namen praktisch nie (`name`, `max`, `default` vs. `value`, `votes`).

### Vergleichskette (`_match_value`)

Gemeinsamer Helfer, genutzt von der neuen Logik und (refaktoriert) von der
bestehenden generischen Tag-Logik:

1. `parse_condition(cond)` → numerisch: Text als `float` parsen, Prädikat
   prüfen. Parse-Fehler → kein Match.
2. `exists` (oder leere `cond`, nur `@selector`) → Attribut/Kind vorhanden.
3. `!exists` → nicht vorhanden.
4. Wildcards (`*` am Anfang/Ende) → contains / endswith / startswith auf
   lowercased Wert.
5. Exakt: `wert.lower() == cond`.

Rückgabewerte für `found_values`: numerisch/exakt/Wildcard → der gematchte
Wert (Attributwert bzw. Kind-Text); Existenz-Checks → die Literale
`"exists"` / `"!exists"` (Konsistenz mit bestehenden Existenz-Checks in
`_xml_tag_match` und `_match_metadata`). Ein vorhandenes Attribut mit
leerem Wert zählt als `exists` (kein Falsy-Problem). `None` = kein Match.

## Beispiele (gegen das Beispiel-NFO des Users)

```xml
<movie>
  <title>Wild Christmas</title>
  <ratings>
    <rating name="themoviedb" max="10"><value>5.705</value><votes>719</votes></rating>
    <rating name="imdb" max="10" default="true"><value>5.8</value><votes>43965</votes></rating>
  </ratings>
</movie>
```

| Expression | Ergebnis |
|---|---|
| `rating@name:themoviedb` | Match (Rekursion) |
| `ratings/rating@name:themoviedb` | Match (Pfad) |
| `rating@name:imdb` | Match (imdb-Element) |
| `rating@name:*imdb*` | Match (Wildcard) |
| `rating@default:true` | Match (nur imdb-Element) |
| `rating@name` / `rating@name:exists` | Match |
| `rating@votes:!exists` | kein Match (votes-Kind existiert) |
| `rating@max:10` | Match (numerisch auf Attribut) |
| `ratings/rating@name:themoviedb@value:>5.4` | Match (Kind numerisch, gescopt) |
| `ratings/rating@name:themoviedb@value:>6` | kein Match |
| `rating@name:themoviedb&rating:>0` | Match (UND mit bestehendem Term) |
| `title:Wild Christmas` | unverändert Match (kein `@`) |

## Rückwärtskompatibilität

- Terms ohne `@` (inkl. `rating:>7&year:2020|rating:>8`, `nfostatus:!exists`,
  `sibling:.nfo:exists`, `errors:>1`) verhalten sich identisch.
- Parser (`parse_search_expression`, `parse_condition`) unverändert.
- `search_text_file` (Plaintext-Suche für `.txt`/`.log`) unverändert — die
  neue Logik lebt nur im XML-Pfad.
- Kein Crash mehr bei `@`-haltigen Termen (vorher `KeyError`).

## Fehlerbehandlung

- Fehlerhafte `@`-Terme → kein Match, keine Exception (siehe Parsing).
- Nicht parsebares XML / nicht lesbare Datei → wie bisher `None`
  (bestehender `parse_failed`-Pfad).

## Änderungen

| Datei | Änderung |
|---|---|
| `src/avior_dedup/searchmove/searcher.py` | `@`-Routing in `_xml_match`; neue `_xml_attr_match` + `_match_value`; generische Tag-Logik auf `_match_value` refaktorieren (Duplikat vermeiden); `rating:`-Sonderfall unverändert |
| `tests/test_searchmove.py` | Neue Testklasse mit Inline-NFO-Fixtures (deterministisch, kein Testdata-Umbau): exakt, Wildcard, exists/!exists, numerisch (Attribut + Kind), Pfad, Rekursion, Mehrfach-Spezifikationen, case-insensitiv, kaputte Terme (kein Crash), Negativfälle |
| `src/avior_dedup/searchmove/cli.py` | `--search_strings`-Help um `@`-Syntax + Beispiel erweitern |
| `src/avior_dedup/config/searchmove_templates.yaml` | Template „Has themoviedb rating" (`rating@name:themoviedb`) und „themoviedb rating above 5.4" (`ratings/rating@name:themoviedb@value:>5.4`), jeweils `.nfo` |
| `frontend/src/components/SearchMoveForm.vue` | Raw-Mode-Placeholder um `rating@name:themoviedb`-Beispiel ergänzen |

## Tests (Verifikation)

- `pytest tests/test_searchmove.py tests/test_searchmove_mover.py` — bestehende
  Tests müssen grün bleiben (Rückwärtskompatibilität) plus neue Testklasse.
- Smoke: `avior-searchmove test` (bzw. direkte Searcher-Aufrufe) gegen ein
  NFO mit verschachtelten Ratings — Expression aus der Tabelle oben.

## Out of Scope

- Rekursion für bestehende `tag:value`-Terme (bewusst nur für `@`-Terme).
- Namespace-Handling (Kodi-NFOs sind plain XML; Verhalten wie bisher).
- Element-selektive `found_values`-Semantik über den gematchten Wert hinaus.
- UI-Builder-Umbau (Raw-Mode erlaubt bereits freie Eingabe).
