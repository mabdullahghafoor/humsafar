# handoff/ — Design handoff for integration

**Owner:** Sarim · **For:** Talha (Flutter app), integration step and Task 7.5

| File | What it is |
|---|---|
| `Humsafar_Design_Handoff_v1.0.pdf` | The one design document for integration: what to follow, design tokens (colours, type, sizes), rules, theme fixes in the app, design → app screen map, screens designed but not built, screen overviews |
| `humsafar_design_tokens.dart` | The same tokens as Dart constants plus a sample standard theme. Reference only: Talha decides how to bring it into `lib/core/theme/`; run `flutter analyze` after (it was not compiled in the design workspace) |

**Order of truth:** tokens → latest hi-fi screen (Figma page 02 / highest PNG version) → folder README → wireframes (history only, do not build from them).

**Checked against:** `dev` at PR #81 and the app repo `main` at `5591848`.

## Loading states (skeleton screens, 22 Nov 2026)
Screens 07s, 08s (3.9), 26s, 15s (5.9), 17s, 17bs (4.9) show what each screen looks like while its data loads: grey shapes in the place of the real content, like Facebook or YouTube, instead of a spinner.
- **Stay real:** app bar, Aa / EN|UR, tabs, section headings, static buttons and the bottom nav. Counts in tabs are hidden until loaded ("Open", not "Open (3)").
- **Grey shapes:** `tabTrack #E2E8F0` on `surface #FFFFFF` cards with the `border #CBD5E1` outline; text lines are rounded bars, avatars circles. No teal, amber or red in a skeleton.
- **Shimmer:** a soft white band sweeping left → right (right → left in Urdu), about 1.2 s, looping (layer "Shimmer" in the SVGs). High contrast mode: no sweep, a slow pulse or nothing.
- **Never on the Dependent's safety screens** (20, 21, 22, 23, 24): the big buttons always show at once, even offline. A known open Panic on Guardian Home shows at once, never as a skeleton.
- **Time limit:** after about 10 s the skeleton becomes the normal "Can't reach the server" message (F-21), never an endless shimmer.
- **Flutter:** the `shimmer` package or a small custom widget; one skeleton widget per list row type keeps it simple.
