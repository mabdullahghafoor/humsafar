# assets/brand/ — Humsafar brand v2.0

**Owner:** Sarim · **Design:** Sarim (v2, 22 Nov 2026; v1.0 by the team logo designer, 24 Oct) · **Status:** v2.0 final, replaces v1.0 everywhere

## The identity
- **Symbol:** two companions (a taller and a smaller figure) reaching for each other around an amber heart; together they form the letter **H**. It says "family care, together on the journey" (Humsafar = companion on a journey). **v2:** the arms now curve towards a larger heart, and a soft drop shadow was added.
- **Logo:** symbol + **Humsafar** + the Urdu slogan. **Wordmark:** Humsafar + the Urdu slogan.
- **Slogan (final):** Urdu **اپنوں کا ساتھ، ہر لمحہ** ("Your loved ones beside you, every moment"). The tall Urdu letter crossing into "Humsafar" is part of the wordmark design. English line: **[to confirm with the team]**.
- **Colours:** teal-blue `#0E7490` (main), amber `#F59E0B` (heart and slogan), white. No red (red = Panic in the app).
- **Shadow:** kept on the `white` and `white-amber` versions (made for teal); left off `colour` (made for light backgrounds).

## Folders
| Folder | What is in it |
|---|---|
| `app-icon/` | Android launcher icon (PNG): `full` (1024, teal square), `foreground` (1024, transparent) + `background` (1024, teal) for the adaptive icon, `playstore_512` |
| `splash/` | Android splash icon v2.0 (symbol white-amber, 1152 × 1152 transparent PNG); see `docs/design/1.12_identity_access/README.md` → Splash and launch |
| `logo/exports/symbol/` | Symbol only, SVG: `colour` (on light backgrounds), `white`, `white-amber` (on teal) |
| `logo/exports/wordmark/` | Humsafar + slogan, no symbol, SVG: `colour`, `white` (slogan stays amber) |
| `logo/exports/logo/` | Full logo (symbol + Humsafar + slogan), horizontal, SVG: `colour`, `white` |

**File naming:** `Humsafar_<Logo|Symbol|Wordmark|AppIcon>_v<version>_<layout>_<colour>_<size>.<ext>`. This folder holds only what the app is built from. All other exports (PNG sizes, black / teal / on-teal versions), the v1.0 files, the Illustrator masters and the logo brief are kept in the studio repo and in git history, not here.

## For Talha (app integration)
- **Launcher icon** (e.g. with `flutter_launcher_icons`): same settings as v1, only the file names change:
  ```yaml
  flutter_launcher_icons:
    android: true
    ios: false
    image_path: "assets/brand/app-icon/Humsafar_AppIcon_v2.0_full_1024.png"
    adaptive_icon_background: "#0E7490"
    adaptive_icon_foreground: "assets/brand/app-icon/Humsafar_AppIcon_v2.0_foreground_1024.png"
  ```
  The figures sit inside the central safe zone, so circle and squircle masks do not cut them.
- **Splash and launch (00 / 00b):** icon `splash/Humsafar_Splash_Icon_v2.0_1152.png`; details in `docs/design/1.12_identity_access/README.md`.
- **Welcome screen (01):** teal hero with `Humsafar_Symbol_v2.0_white-amber.svg` and `Humsafar_Wordmark_v2.0_white.svg`, the same pair as the launch screen. The mockup PNG still shows the old v1 logo; use these files.
- **In-app headers:** symbol `colour` at 32–48 px. Use the SVGs (e.g. `flutter_svg`) so they stay sharp.
- App name stays **Humsafar**; keep the Aa and EN|UR rules from the design handoff.
