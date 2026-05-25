# Termin Endpoint Research Snapshot

**Last confirmed:** 2026-02-26  
**Do NOT re-research** unless a URL returns consistent 404/502 in production.

---

## Cities — Current Status

| City | Code | Checker Type | Status |
|------|------|-------------|--------|
| Berlin | `berlin` | HTML GET (service.berlin.de) | ✅ Working |
| Frankfurt | `frankfurt` | TeVIS GET (tevis.ekom21.de) | ✅ Working |
| Köln | `koeln` | TeVIS GET (tevis.krzn.de) | ✅ Working |
| Düsseldorf | `duesseldorf` | TeVIS GET (termine.duesseldorf.de) | ✅ Working |
| München | `muenchen` | KVR POST (www*.muenchen.de) | ⚠️ Geo-gated (502 outside DE) |
| Hamburg | `hamburg` | JS SPA (DigiTermin) | ❌ Not scrapable (SPA) |

---

## Confirmed Endpoints

### Berlin
```
Ausländerbehörde: https://service.berlin.de/terminvereinbarung/termin/all/324/
Bürgeramt/Anmeldung: https://service.berlin.de/terminvereinbarung/termin/all/120686/?termin=1
Abmeldung: https://service.berlin.de/terminvereinbarung/termin/all/121598/?termin=1
```
- Protocol: HTTP GET, static HTML
- Anti-bot: Cloudflare (handled with HTTP/2 + headers)

### Frankfurt
```
Bürgeramt/Anmeldung: https://tevis.ekom21.de/fra/select2?md=13
Ausländerbehörde: https://tevis.ekom21.de/fra/select2?md=5
```
- Protocol: HTTP GET, TeVIS static HTML
- Slot indicator: `data-count="[1-9]` or `class="buchbar"`

### Köln
```
Bürgeramt/Ausländerbehörde: https://tevis.krzn.de/tevisweb190/select2?md=1
```
- Protocol: HTTP GET, TeVIS static HTML

### Düsseldorf ✅ CONFIRMED 2026-02-26
```
Bürgeramt/Einwohnerangelegenheiten: https://termine.duesseldorf.de/select2?md=4
Ausländerbehörde: https://termine.duesseldorf.de/select2?md=1
```
- Protocol: HTTP GET, TeVIS-compatible static HTML
- Verified: `md=4` page loaded and contains TeVIS service list (Einwohnerangelegenheiten)
- Note: `md=1` confirmed via official city page `termine.duesseldorf.de/auslaenderamt.html`

### München ⚠️ CONFIRMED 2026-02-26 (geo-gated)
```
Bürgerbüro (Bürgeramt): https://www56.muenchen.de/termin/index.php?loc=BB
Ausländerbehörde (KVR ABH): https://www46.muenchen.de/termin/index.php?loc=ABH
```
- Protocol: **POST** (not GET) — requires two-step POST with CASETYPES form data
- Response: HTML page containing `jsonAppoints = '...'` JSON string
- Source: Reverse-engineered from https://github.com/mjmirza/KVR-Munich (termin_api.py)
- **LIMITATION**: These servers return **502 Bad Gateway** when accessed from outside Germany
  (CDN geo-gate). The checker will consistently return NOT_AVAILABLE in dev/staging
  environments hosted outside DE. Production servers in Germany should work normally.
- CASETYPES mapping (stable across years):
  - Bürgeramt: `"An- oder Ummeldung - Einzelperson"`
  - Abmeldung: `"Abmeldung - Einzelperson"`
  - Ausländerbehörde: `"Niederlassungserlaubnis allgemein"`

### Hamburg ❌ NOT SCRAPABLE
```
SPA entry: https://serviceportal.hamburg.de/hamburggateway/fvp/fv/bezirke/digitermin
```
- System: **DigiTermin** — fully JavaScript Single-Page Application (React/Angular)
- No static HTML endpoints available
- All slot data loaded via JS after page render
- **Cannot be scraped** with static HTTP requests (httpx/requests)
- Alternative: Puppeteer/Playwright browser automation (not in current stack)
- Status: **Beta / manual check only** — users directed to official portal

---

## Implementation Notes

### check_city_slots() compatibility
The generic `check_city_slots()` function works for cities that:
- Use TeVIS or similar static HTML booking pages
- Return slot availability via HTML attributes (`data-count`, `class="buchbar"`, etc.)

**Compatible**: Berlin, Frankfurt, Köln, Düsseldorf  
**Incompatible**: München (POST-based), Hamburg (SPA)

### München dedicated checker
`check_muenchen_slots()` in `utils/termin_checker.py` implements the full KVR POST flow.
It is geo-gated — returns `{"available": False}` with 502 from outside Germany.
No special handling needed; the standard NOT_AVAILABLE path covers this correctly.

### Hamburg path forward
To add Hamburg monitoring, options are:
1. **Puppeteer/Playwright** browser automation (significant complexity, separate process)
2. **Official Hamburg API** — check if `serviceportal.hamburg.de` exposes a JSON API
3. **Partner integration** — Hamburg.de sometimes provides iFrame embed URLs

Until one of these is implemented, Hamburg shows a "beta/manual" note in pre-payment UI.

---

## Do NOT change without re-verification
- Berlin URL changed from `all/5/` to `all/324/` in 2025 — always re-verify on 404
- TeVIS `md=` IDs are stable but can change on city portal migrations
- München `www56/www46/www22/www46` subdomains are load-balancer variants — all equivalent
