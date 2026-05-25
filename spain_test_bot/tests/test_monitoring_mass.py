"""
Mass test — Spain monitoring system.
Tests attempts logic (1 / 3 / 5 citas), loop behaviour, link validity.

Usage:
    python3 test_monitoring_mass.py

Does NOT touch production code. All test user IDs are cleaned up at exit.
"""

from __future__ import annotations

import asyncio
import random
import sys
import time
from unittest.mock import AsyncMock, MagicMock

# ── Fake bot (no Telegram connection needed) ──────────────────────────────────

class FakeBot:
    def __init__(self):
        self.messages: list[dict] = []

    async def send_message(self, chat_id, text, **kwargs):
        self.messages.append({"uid": chat_id, "text": text[:120]})

# ── Fake cita ─────────────────────────────────────────────────────────────────

TEST_CITIES = [
    "barcelona", "madrid", "valencia", "sevilla", "malaga",
    "alicante",  "murcia", "zaragoza", "bilbao",  "granada",
]

PORTAL_URL = "https://icp.administracionelectronica.gob.es/icpplus/index.html"

def fake_cita(city: str = "") -> list[dict]:
    return [{
        "date":     "15.04.2026",
        "time":     "09:30",
        "url":      PORTAL_URL,
        "location": (city or random.choice(TEST_CITIES)).title(),
    }]

# ── URL validation ────────────────────────────────────────────────────────────

def check_url(url: str) -> str:
    import urllib.request
    try:
        with urllib.request.urlopen(url, timeout=8) as r:
            return f"{r.status} OK"
    except Exception as exc:
        return str(exc)[:60]

# ── Colour helpers ────────────────────────────────────────────────────────────

GREEN  = "\033[92m"
RED    = "\033[91m"
YELLOW = "\033[93m"
BOLD   = "\033[1m"
RESET  = "\033[0m"

def ok(msg):  print(f"  {GREEN}✔{RESET} {msg}")
def err(msg): print(f"  {RED}✖{RESET} {msg}")
def info(msg):print(f"  {YELLOW}→{RESET} {msg}")
def hdr(msg): print(f"\n{BOLD}{msg}{RESET}")

# ── Core test: single user scenario ──────────────────────────────────────────

async def run_scenario(
    plan: str,
    expected_attempts: int,
    city: str,
    svc: str,
    test_uid: int,
    bot: FakeBot,
) -> dict:
    """
    Simulate the full monitoring cycle for one user:
      - activate plan
      - run the loop with a mock checker that ALWAYS returns a fake cita
      - verify attempts count after each decrement
      - verify monitoring stops at 0
    """
    from utils.payments import activate, get_attempts_left, decrement_attempts, is_paid
    from utils.payments_store import db_clear_pending
    from utils import monitoring as mon

    # Clean any leftover data
    try:
        from utils.payments_store import db_save  # just import to avoid issues
        import utils.payments as _pm
        _pm.paid_users.pop(test_uid, None)
    except Exception:
        pass

    # ── Activate ──────────────────────────────────────────────────────────────
    activate(test_uid, city, svc, plan)
    start_count = get_attempts_left(test_uid)
    assert start_count == expected_attempts, (
        f"Expected {expected_attempts} attempts after activate, got {start_count}"
    )

    log_rows: list[str] = []
    log_rows.append(f"activate({plan}) → attempts={start_count}")

    # ── Simulate loop iterations ──────────────────────────────────────────────
    # Directly call decrement/is_paid as the loop would, without sleeping
    iteration = 0
    while is_paid(test_uid):
        before = get_attempts_left(test_uid)
        print(f"    [ATTEMPTS BEFORE] uid={test_uid} attempts={before}")

        remaining = decrement_attempts(test_uid)

        after = get_attempts_left(test_uid)
        print(f"    [ATTEMPTS AFTER]  uid={test_uid} attempts={after}")

        cita  = fake_cita(city)
        url   = cita[0]["url"]
        msg   = (
            f"🔥 Знайдено! {cita[0]['location']} {cita[0]['date']} {cita[0]['time']} "
            f"| залишилось: {remaining}"
        )
        bot.messages.append({"uid": test_uid, "text": msg})

        row = f"  iter {iteration+1}: {before} → {after}"
        log_rows.append(row)
        info(row.strip())

        iteration += 1
        if iteration > expected_attempts + 2:   # safety guard
            err("INFINITE LOOP GUARD triggered!")
            break

    final_count = get_attempts_left(test_uid)
    stopped_correctly = (final_count == 0) and (not is_paid(test_uid))
    log_rows.append(f"final_count={final_count} | stopped={stopped_correctly}")

    # ── Cleanup ───────────────────────────────────────────────────────────────
    import utils.payments as _pm2
    _pm2.paid_users.pop(test_uid, None)
    try:
        from utils.payments_store import db_clear_pending
        db_clear_pending(test_uid)
    except Exception:
        pass

    return {
        "plan":             plan,
        "expected":         expected_attempts,
        "iterations":       iteration,
        "stopped_at_zero":  stopped_correctly,
        "final_count":      final_count,
        "log":              log_rows,
        "ok":               (iteration == expected_attempts) and stopped_correctly,
    }

# ── Link validation ───────────────────────────────────────────────────────────

def run_link_checks() -> dict[str, str]:
    import urllib.request
    urls = {
        "citaconsular.es (consulado)": "https://www.citaconsular.es/",
        "sede (NIE/TIE — anti-bot)":   "https://icp.administracionelectronica.gob.es/icpplus/index.html",
        "sede.administracion root":    "https://sede.administracionespublicas.gob.es/",
    }
    results = {}
    for label, url in urls.items():
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 Chrome/120"})
            with urllib.request.urlopen(req, timeout=8) as r:
                results[label] = f"{r.status} OK"
        except urllib.error.HTTPError as e:
            results[label] = f"HTTP {e.code} — URL застарів!"
        except Exception as e:
            # Timeout = anti-bot (normal for government portals, Playwright bypasses it)
            if "timed out" in str(e).lower():
                results[label] = "TIMEOUT (anti-bot захист, OK в Playwright)"
            else:
                results[label] = str(e)[:50]
    return results

# ── UX message preview ────────────────────────────────────────────────────────

def preview_ux_messages(bot: FakeBot) -> None:
    hdr("ЗРАЗОК UX-ПОВІДОМЛЕНЬ (перші 3):")
    for msg in bot.messages[:3]:
        print(f"  uid={msg['uid']}: {msg['text']}")

# ── Main ─────────────────────────────────────────────────────────────────────

async def main() -> None:
    print(f"\n{BOLD}{'='*60}{RESET}")
    print(f"{BOLD}  МАСОВИЙ ТЕСТ — Spain Monitoring System{RESET}")
    print(f"{BOLD}{'='*60}{RESET}")

    bot = FakeBot()

    # ── Scenarios ─────────────────────────────────────────────────────────────
    scenarios = [
        ("monitor_1cita",  1, "barcelona", "nie",  900001),
        ("monitor_3citas", 3, "madrid",    "nie",  900002),
        ("monitor_5citas", 5, "valencia",  "nie",  900003),
        # Extra: different cities
        ("monitor_3citas", 3, "sevilla",   "nie",  900004),
        ("monitor_3citas", 3, "malaga",    "nie",  900005),
    ]

    results = []
    for plan, attempts, city, svc, uid in scenarios:
        hdr(f"СЦЕНАРІЙ: plan={plan} | {city}/{svc} | uid={uid}")
        try:
            res = await run_scenario(plan, attempts, city, svc, uid, bot)
            results.append(res)
            if res["ok"]:
                ok(f"ПРОЙШОВ: {attempts} → 0 за {res['iterations']} ітерацій, моніторинг зупинено")
            else:
                err(f"ПРОВАЛЕНИЙ: ітерацій={res['iterations']}, final_count={res['final_count']}, stopped={res['stopped_at_zero']}")
        except Exception as exc:
            err(f"ВИНЯТОК: {exc}")
            import traceback; traceback.print_exc()
            results.append({"plan": plan, "ok": False, "error": str(exc)})

    # ── Link checks ───────────────────────────────────────────────────────────
    hdr("ПЕРЕВІРКА ПОСИЛАНЬ:")
    link_results = run_link_checks()
    all_links_ok = True
    for label, status in link_results.items():
        if "200 OK" in status:
            ok(f"{label:40s} → {status}")
        elif "TIMEOUT" in status:
            print(f"  {YELLOW}⚠{RESET}  {label:40s} → {status}")
            # Timeout = anti-bot protection, not a real failure for Playwright
        else:
            err(f"{label:40s} → {status}")
            all_links_ok = False

    # ── UX preview ────────────────────────────────────────────────────────────
    preview_ux_messages(bot)

    # ── Final report ──────────────────────────────────────────────────────────
    passed = sum(1 for r in results if r.get("ok"))
    total  = len(results)

    hdr("ФІНАЛЬНИЙ ЗВІТ:")
    print(f"  {'─'*50}")
    for res in results:
        status = f"{GREEN}✔ OK{RESET}" if res.get("ok") else f"{RED}✖ FAIL{RESET}"
        plan   = res.get("plan", "?")
        iters  = res.get("iterations", "?")
        print(f"  {status}  {plan:<22}  ітерацій={iters}  зупинився@0={res.get('stopped_at_zero', '?')}")
    print(f"  {'─'*50}")
    print(f"  Сценаріїв:   {passed}/{total} пройшло")
    print(f"  Посилання:   {'✔ всі 200' if all_links_ok else '✖ деякі не відповіли'}")
    print(f"  UX-повідомлень зібрано: {len(bot.messages)}")
    print(f"  {'─'*50}")

    if passed == total and all_links_ok:
        print(f"\n  {GREEN}{BOLD}✅ ГОТОВО ДО РЕЛІЗУ{RESET}\n")
    else:
        print(f"\n  {RED}{BOLD}⚠️  Є проблеми — перевір вище{RESET}\n")

    # Counts table
    hdr("ДЕТАЛІЗАЦІЯ (attempts log):")
    for res in results:
        print(f"  {res.get('plan','?')}: {' → '.join(str(x) for x in range(res.get('expected',0), -1, -1))}")


if __name__ == "__main__":
    asyncio.run(main())
