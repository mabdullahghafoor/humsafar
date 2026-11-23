# 1.12 — High-fidelity mockups: Identity & Access (v0.1)

**Task:** 1.12 · **Owner:** Sarim · **Source:** Figma *Humsafar – App Design*, page `02 · App Designs (Hi-Fi)` (link in `../README.md`). Built on the 0.7 wireframes.

| # | Screen | Used by | Requirements | Section in Figma |
|---|---|---|---|---|
| 00 | Style guide (colours, type, buttons, rules) — **v0.2** | — | NFR-07, NFR-08 | Components & Styles |
| 00 | Splash (Android system splash) — **v0.1** | both | NFR-07 | Launch · Splash |
| 00b | Launch (first app screen, login check) — **v0.1** | both | NFR-07 | Launch · Splash |
| 01 | Welcome (role choice) | both | FR-A1 | Guardian App |
| 02 | Log in (incl. error state) | both | FR-A1 | Guardian App |
| 03 | Create account (incl. field validation states) — **v0.3** (consent line) | both | FR-A1 | Guardian App |
| 03b | Privacy Policy (text screen) — **v0.1** | both | FR-A1 | Guardian App |
| 03c | Terms (text screen) — **v0.1** | both | FR-A1 | Guardian App |
| 04 | Verify identity — CNIC + live photo | Dependent | FR-A2 | Dependent App |
| 05 | Share my ID (QR + copy/share) | Dependent | FR-B1 | Dependent App |
| 06 | Verify your account — phone OTP + CNIC | Guardian | FR-A3 | Guardian App |
| 09 | Link a Dependent (scan or type ID) | Primary Guardian | FR-B1, FR-B2 | Guardian App |
| 10 | Permissions per Secondary Guardian | Primary Guardian | FR-A4 | Guardian App |

## Design direction (decided 2026-10-19)
- **Colours:** calm teal-blue. Primary `#0E7490`, dark `#155E75`, tint `#ECFEFF`; text `#0F172A`, muted `#475569`, border `#CBD5E1`; success `#15803D`, warning `#B45309`. **Red `#B91C1C` is reserved for Panic and critical alerts only.** *(Style guide v0.2, 21 Oct 2026: danger `#DC2626` → `#B91C1C` and muted `#64748B` → `#475569` so all text meets WCAG AA contrast, NFR-08; see `docs/qa/results/design/Humsafar_QA_NFR-08_Contrast_Check_v1.0.pdf`. Since 30 Oct 2026 every mockup PNG uses these colours too, see "Colour update" below.)*
- **Type:** Inter — title 26 bold, heading 18 bold, body 15, caption 12.
- **Components:** buttons 54 px tall, 14 px radius; inputs 50 px, 12 px radius; touch targets at least 48 × 48; text contrast at least 4.5 : 1 (WCAG 2.1 AA).
- Every app bar keeps the **Aa** (large text / high contrast) toggle and the **EN|UR** language switch (team UI convention).

## Notes for Talha (Task 2.5)
- Field rules shown match the contracts: CNIC `12345-1234567-1`, Pakistani phone, password at least 8 characters.
- Log in shows one message for wrong email and wrong password (by design, auth contract).
- Screen 05/09: the Dependent's `user_id` is shared as QR or text (linkage contract §3).
- The logo on screen 01 Welcome is still the early **placeholder**; build with the brand files in `assets/brand/` (logo **v2.0 final**, 22 Nov 2026). The mockups 00, 00b and 01 in this folder still show the **old v1 logo**; build the logo, app icon and splash icon from `assets/brand/` (v2.0), not from the mockup pictures.

## Colour update (30 Oct 2026)
All screens in this folder now use the **style guide v0.2 colours**: old red `#DC2626` → `#B91C1C` and old grey `#64748B` → `#475569` (NFR-08 contrast fix). **Colours only, no layout or text change.** Updated screens:

| # | Screen | Version |
|---|---|---|
| 01 | Welcome | v0.1 → **v0.2** |
| 02 | Log in | v0.1 → **v0.2** |
| 03 | Create account | v0.1 → **v0.2** |
| 04 | Verify identity | v0.1 → **v0.2** |
| 05 | Share my ID | v0.1 → **v0.2** |
| 06 | Verify your account | v0.1 → **v0.2** |
| 09 | Link a Dependent | v0.1 → **v0.2** |
| 10 | Permissions | v0.1 → **v0.2** |

Overview rebuilt from the latest versions: v0.2 → **v0.3**. Editable SVG sources of every screen in this folder are in `svg/` (same names as the PNGs, `.svg`); use them for Figma import.

## Splash and launch (8 Nov 2026)
Two screens shown before Welcome / Home, the same in both apps: **00 Splash** (`Humsafar_Design_00_Splash_v0.1`) and **00b Launch** (`Humsafar_Design_00b_Launch_v0.1`). Figma: section *Launch · Splash (both apps)*; prototype flow *Splash → Launch*.

**For Talha:**
- **00 Splash** is the Android system splash: teal `#0E7490` with the white-amber symbol only (Android 12+ allows one icon on one colour). Icon file: `assets/brand/splash/Humsafar_Splash_Icon_v2.0_1152.png` (1152 × 1152 transparent = 288 dp; the symbol stays inside the 192 dp circle). With `flutter_native_splash`:
  ```yaml
  flutter_native_splash:
    color: "#0E7490"
    image: assets/brand/splash/Humsafar_Splash_Icon_v2.0_1152.png
    android_12:
      color: "#0E7490"
      image: assets/brand/splash/Humsafar_Splash_Icon_v2.0_1152.png
  ```
- **00b Launch** is the first Flutter screen while the app reads the saved login, then it goes straight to Welcome (signed out) or Home (signed in). Teal background, white status-bar icons; symbol 112 px wide centred at y 300; `Humsafar_Wordmark_v2.0_white.svg` with its visible part 230 px wide, top at y 384; white loader 28 px (30 % white track) at y 678, shown only if the check takes longer than about 300 ms. Screen-reader label: "Humsafar, loading".
- **Animation:** symbol moves up and shrinks (128 → 112 px), wordmark and loader fade in; 0.6 s ease in-out. The 1 s before it in the prototype is only Figma's timer.
- **Never wait for the internet** on either screen. The login check reads the token stored on the phone; refresh it in the background after Home opens. Offline: open Home with the offline banner. On the Dependent app PANIC must be on screen within a couple of seconds, signal or not. Do not hold the splash (`FlutterNativeSplash.preserve`) for network or data.
- No red on either screen (red = Panic).

## Consent line, Privacy Policy and Terms (23 Nov 2026)
**03 Create account v0.3** adds one line under the button: "By creating an account you agree to the **Privacy Policy** and **Terms**." (links in teal 600, underlined; 12 px muted text). The two links open **03b Privacy Policy v0.1** and **03c Terms v0.1**: plain scrolling text screens with the usual app bar (back, title, Aa, EN|UR) and a version line. Everything else on 03 is unchanged from v0.2. The text of both pages (English and Urdu) and the string keys are in `../ui_text/Humsafar_Privacy_and_Terms_v0.2.pdf`. No tick box (tapping Create account counts as agreeing); the draft needs a supervisor read. The overview picture (v0.3) still shows 03 v0.2 and is not rebuilt for this.
