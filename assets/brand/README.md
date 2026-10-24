# assets/brand/ — Humsafar brand v1.0

**Owner:** Sarim · **Design:** team logo designer · **Status:** v1.0 final logo in (24 Oct 2026)

## The identity
- **Symbol:** two companions (a taller and a smaller figure) holding hands around an amber heart; together they form the letter **H**. It says "family care, together on the journey" (Humsafar = companion on a journey).
- **Logo:** symbol + **Humsafar** + the Urdu slogan.
- **Slogan (final):** Urdu **اپنوں کا ساتھ، ہر لمحہ** ("Your loved ones beside you, every moment"). English line: **[to confirm with the team]**.
- **Colours:** teal-blue `#0E7490` (main), amber `#F59E0B` (heart only), white. No red (red = Panic in the app).

## Folders
| Folder | What is in it |
|---|---|
| `logo/exports/logo/` | Full logo (symbol + Humsafar + slogan), horizontal: `colour` (on light backgrounds), `white` (on dark / teal, transparent), `on-teal` (with its teal background). SVG + PNG 2048 / 1024 / 512 |
| `logo/exports/symbol/` | Symbol only: `colour`, `teal` (one colour), `white`, `white-amber`, `black`. SVG + PNG 1024 / 512 / 192 / 48 |
| `logo/exports/wordmark/` | Humsafar + slogan, no symbol: `on-teal`, `white`, `colour` |
| `logo/exports/alternatives/` | Slogans not chosen (ہر قدم، ساتھ ساتھ · دور رہ کر بھی قریب) and a near-identical second on-teal logo. Not for use; kept for the record |
| `logo/source/` | Designer's Illustrator masters (`.ai`) — edit these, then re-export |
| `app-icon/` | Android launcher icon: `full` (1024, teal square), `foreground` (1024, transparent) + `background` (1024, teal) for the adaptive icon, `playstore_512`, and the designer's original rounded version |
| `brief/` | Logo & Slogan Brief v1.0 and the Gemini prompts used |
| `concepts/` | Gemini and draft concepts, and the slogan-options board (record only) |

**File naming:** `Humsafar_<Logo|Symbol|Wordmark|AppIcon>_v<version>_<layout>_<colour>_<size>.<ext>`

## For Talha (app integration)
- **Launcher icon** (e.g. with `flutter_launcher_icons`): copy the app-icon PNGs into the app's assets and use
  ```yaml
  flutter_launcher_icons:
    android: true
    ios: false
    image_path: "assets/brand/Humsafar_AppIcon_v1.0_full_1024.png"
    adaptive_icon_background: "#0E7490"
    adaptive_icon_foreground: "assets/brand/Humsafar_AppIcon_v1.0_foreground_1024.png"
  ```
  The figures sit inside the central 66 % safe zone, so circle and squircle masks do not cut them.
- **Splash / Welcome screen (01):** `Humsafar_Symbol_v1.0_white-amber.svg` on teal, or `Humsafar_Logo_v1.0_horizontal_colour.svg` on white.
- **In-app headers:** symbol `colour` at 32–48 px. Use the SVGs (e.g. `flutter_svg`) so they stay sharp.
- App name stays **Humsafar**; keep the Aa and EN|UR rules from the design handoff.

## Notes from the check (24 Oct)
- In the full logo and the wordmark, the tall strokes of the Urdu slogan touch the letters of "Humsafar". Ask the designer for a little more space in v1.1 (does not block use).
- The arms used `#0E6E90`; exports here are corrected to the brand `#0E7490`. A stray dot outside the symbol canvas was removed. Masters in `logo/source/` are unchanged.
