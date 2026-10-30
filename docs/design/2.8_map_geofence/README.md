# 2.8 — High-fidelity mockups: Live Map, location history, safe zones (v0.1)

**Task:** 2.8 · **Owner:** Sarim · **Source:** Figma *Humsafar – App Design*, page `02 · App Designs (Hi-Fi)`, section Guardian App. Same style as 1.12. For Talha's Task 2.6 (Live Map + geofence screens).

The third screen named in 2.8, **Dependent Mode home**, is already designed in 3.9 (`../3.9_safety_screens/`, screen 20).

| # | Screen | Requirements | Contract |
|---|---|---|---|
| 11 | Live Map — inside a safe zone, last update, battery, accuracy | FR-C1, FR-C2 | `location_contract.md`, `geofence_contract.md` (geofence-status) |
| 11b | Live Map — left all safe zones + low battery | FR-C2, FR-L1 | `geofence_contract.md`, `device_health_contract.md` |
| 11c | Location history — route + time slider + stops | FR-C4 | `location_contract.md` (location/history) |
| 12 | Safe zones list (3 of 10) | FR-C2, FR-C3 | `geofence_contract.md` |
| 12b | Edit safe zone — drag pin/edge, name, radius 50 m – 50 km | FR-C2 | `geofence_contract.md` |

## Notes for Talha (2.6)
- Status chip comes from `GET …/geofence-status`: `inside` (green "Inside: <zone>"), `outside` (amber banner), `no_zones` / `unknown` (show "No safe zones yet" / "Location not available").
- Leaving a zone is a **warning (amber)**, not red — red stays for Panic only.
- Only the **Primary** sees "Add / Edit / Delete"; a Secondary with `live_location` sees the same screens read-only.
- Battery chip turns amber at 15% or lower (low-battery alert rule, closes above 20%).
- "Updated … ago / moving / stationary" uses the latest fix; the next update follows `next_update_interval_s`.
- Map tiles are placeholders; any map package (e.g. Google Maps / OpenStreetMap) can sit underneath.

## Colour update (30 Oct 2026)
All screens in this folder now use the **style guide v0.2 colours**: old red `#DC2626` → `#B91C1C` and old grey `#64748B` → `#475569` (NFR-08 contrast fix). **Colours only, no layout or text change.** Updated screens:

| # | Screen | Version |
|---|---|---|
| 11 | Live Map | v0.1 → **v0.2** |
| 11b | Live Map | v0.1 → **v0.2** |
| 11c | Location history | v0.1 → **v0.2** |
| 12 | Safe zones | v0.1 → **v0.2** |
| 12b | Edit safe zone | v0.1 → **v0.2** |

Overview rebuilt from the latest versions: v0.1 → **v0.2**. Editable SVG sources of every screen in this folder are in `svg/` (same names as the PNGs, `.svg`); use them for Figma import.
