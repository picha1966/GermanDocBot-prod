# Analysis: Bundesland / State Selection

**Scope:** Where Bundesland (federal state) is implemented, how it is determined, and which documents trigger it.  
**No code was modified.**

---

## 1. How Bundesland Is Determined

Bundesland is **not** selected by the user in a dedicated step. It is **derived from the postal code (PLZ)**:

- User enters **PLZ** (Postleitzahl) in the address.
- Code calls `get_bundesland(plz)` to get the federal state name.
- There is **no separate “Bundesland selection” screen** in the bot flow; state is always computed from PLZ.

---

## 2. Files and Functions Involved

### 2.1 Core: PLZ → Bundesland

| File | Function / item | Role |
|------|-----------------|------|
| **backend/geo_intelligence.py** | `PLZ_TO_BUNDESLAND` | Dict mapping 2-digit PLZ prefix → state name (e.g. `'10': 'Berlin'`). |
| **backend/geo_intelligence.py** | `get_bundesland(plz: str) -> str` | Returns state name for a 5-digit PLZ (uses first 2 digits). |
| **backend/geo_helper.py** | `get_bundesland(plz: str)` | Alternative implementation using PLZ ranges. |
| **backend/authority_manager.py** | `get_bundesland(plz)` | Alternative implementation; returns state or `None`. |

**Used in PDF flow:** `pdf_generator` imports **backend.geo_intelligence** (`get_bundesland`, `get_authority_address`). The other two modules are used elsewhere (e.g. logic_handler, tests).

### 2.2 Authority Address (uses Bundesland)

| File | Function | Role |
|------|----------|------|
| **backend/geo_intelligence.py** | `get_authority_address(doc_type, plz) -> Dict` | Uses `get_bundesland(plz)` and `doc_type` to resolve authority (Familienkasse, Jobcenter, Bürgeramt, etc.). |
| **backend/geo_intelligence.py** | `get_city_by_plz(plz)` | City from PLZ; used with authority lookup. |
| **backend/geo_intelligence.py** | `get_full_location_info(plz, doc_type)` | Returns `(bundesland, city, authority_info)`. |
| **backend/authority_manager.py** | `get_authority_address(doc_type, plz)` | Different implementation: uses `get_bundesland(plz)` for Wohngeld fallback and `AUTHORITIES_BY_PLZ` for other docs. |

### 2.3 PDF Generation (Bundesland in PDF and user_data)

| File | Function / location | Role |
|------|----------------------|------|
| **backend/pdf_generator.py** | `_get_geo_block_text(bundesland, authority_type, lang)` | Localized text for the “geo” block (state + authority type). |
| **backend/pdf_generator.py** | `enrich_user_data_with_authority(user_data, doc_type, plz)` | Calls `get_authority_address(doc_type, plz)` and `get_bundesland(plz)`; sets `user_data['bundesland']` and authority_* fields. |
| **backend/pdf_generator.py** | `_render_pdf(...)` (GEO block, ~960–990) | If authority address was not drawn and `plz` exists: calls `get_bundesland(plz)`, maps `doc_type` to `authority_type` (Bürgeramt, Familienkasse, etc.), then `_get_geo_block_text(bundesland, authority_type, text_lang)`. |
| **backend/pdf_generator.py** | `process_document(user_data, doc_type, plz)` | Gets `plz` from user_data if not passed; calls `enrich_user_data_with_authority` and `get_authority_address`. |
| **backend/pdf_generator.py** | Filtering of keys | `bundesland` (and authority_*) are excluded from “meaningful” fields when checking what to render (e.g. ~580, ~1150, ~1693, ~1810). |

Imports at top of **backend/pdf_generator.py**: `from backend.geo_intelligence import get_authority_address, get_bundesland` (with fallback stubs if import fails).

### 2.4 Preview / Explanatory Text

| File | Location | Role |
|------|----------|------|
| **backend/preview_texts.py** | `GEO_BLOCK_TEXTS` (per language) | Template text with `{bundesland}` and `{authority_type}` placeholders (e.g. “Your residence is in the federal state {bundesland}…”). |

### 2.5 Handlers and WebApp

| File | Location | Role |
|------|----------|------|
| **handlers/docs_new.py** | `_has_meaningful_user_data` / filtering | Excludes `'bundesland'` (and authority_*, doc_type, lang, etc.) from “meaningful” form fields. |
| **handlers/docs_new.py** | Import | `from backend.geo_intelligence import get_authority_address, format_authority_info`. |
| **handlers/docs_new.py** | Preview / pending | Uses `pending.get("authority_info")` when calling `create_preview`; does not set `authority_info` on submit (it can be None; PDF then uses plz inside _render_pdf for GEO block). |
| **webapp/index.html** | Section `land`, type `land`, `landParam`, `useLand` | **Optional** “Bundesland” dropdown: list of German states (Berlin, Brandenburg, …). Shown only if `landParam` is in URL or `docCfg.sections` includes `'land'`. |
| **webapp/index.html** | `DOC_CONFIG` | anmeldung, abmeldung, kindergeld do **not** include `'land'` in `sections`, so **no document currently forces** the land selector; it only appears when URL has `?land=...`. |
| **webapp/index.html** | Labels | `land` / “Bundesland” / “Federal state” etc. for the optional state field. |

So: **Bundesland selection in the UI** exists only as an optional WebApp “land” field, driven by URL or schema; **no document type** in `DOC_CONFIG` currently adds the `land` section by default.

### 2.6 Other References

| File | Role |
|------|------|
| **backend/logic_handler.py** | Imports `get_bundesland`, `get_authority_address`, `format_authority` from `backend.geo_helper`. |
| **backend/authority_manager.py** | Uses `get_bundesland(plz)` for Wohngeld address resolution. |
| **tests/test_v45_modules.py** | Tests for `get_bundesland`, `get_authority_address`, `BundeslandInfo`. |
| **templates/OFFICIAL_FORMS_LINKS.md** | Mentions that many forms differ by Bundesland. |

---

## 3. Which Documents Trigger Bundesland / Authority Logic

### 3.1 Any document with PLZ in user_data

- **enrich_user_data_with_authority** and **GEO block** in `_render_pdf` run for **any** `doc_type` when `plz` is present.
- So **every document type** that collects address/PLZ and goes through `create_preview` / `process_document` can get:
  - `user_data['bundesland']` set (in `enrich_user_data_with_authority`),
  - and the GEO block in the PDF (state + authority type) when no specific authority address is rendered.

### 3.2 Authority lookup by document type (geo_intelligence.get_authority_address)

Explicit handling (and thus use of Bundesland for authority resolution):

- **kindergeld**, **kinderzuschlag** → Familienkasse (by Bundesland).
- **elterngeld** → Elterngeldstelle (by Bundesland).
- **buergergeld**, **erstausstattung** → Jobcenter (by Bundesland).
- **wohngeld** → Wohngeldstelle (by Bundesland).
- **anmeldung**, **abmeldung** → Bürgeramt (by city from PLZ; Bundesland still used in fallback / logging).

So these **8 document types** explicitly drive authority (and thus Bundesland) in **backend/geo_intelligence.py**. Other doc types still get Bundesland in user_data and in the GEO block if they have PLZ and no authority block is shown.

### 3.3 Authority type label in PDF GEO block (pdf_generator)

In `_render_pdf`, `authority_type_map` assigns a label for:

- **anmeldung**, **abmeldung** → Bürgeramt  
- **kindergeld** → Familienkasse  
- **buergergeld** → Jobcenter  
- **wohngeld** → Wohngeldstelle  

Any other `doc_type` falls back to `"Bürgeramt"` for the GEO block text.

---

## 4. Summary Table

| Topic | Where | What |
|-------|--------|------|
| **Bundesland derivation** | geo_intelligence, geo_helper, authority_manager | `get_bundesland(plz)` (PLZ → state name). |
| **Authority from state/doc** | geo_intelligence, authority_manager | `get_authority_address(doc_type, plz)` (uses Bundesland). |
| **Bundesland in PDF** | pdf_generator | GEO block text via `_get_geo_block_text(bundesland, authority_type, lang)`; `user_data['bundesland']` set in `enrich_user_data_with_authority`. |
| **Documents that trigger it** | All docs with PLZ | Any doc with `plz` in user_data; 8 doc types explicitly drive authority (anmeldung, abmeldung, kindergeld, kinderzuschlag, elterngeld, buergergeld, erstausstattung, wohngeld). |
| **Optional state selection (UI)** | webapp/index.html | Optional “land” (Bundesland) dropdown; no doc in DOC_CONFIG currently adds `sections: ['..., land']`, so only URL `?land=...` triggers it. |

---

**End of analysis. No code was modified.**
