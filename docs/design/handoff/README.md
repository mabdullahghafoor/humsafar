# handoff/ — Design handoff for integration

**Owner:** Sarim · **For:** Talha (Flutter app), integration step and Task 7.5

| File | What it is |
|---|---|
| `Humsafar_Design_Handoff_v1.0.pdf` | The one design document for integration: what to follow, design tokens (colours, type, sizes), rules, theme fixes in the app, design → app screen map, screens designed but not built, screen overviews |
| `humsafar_design_tokens.dart` | The same tokens as Dart constants plus a sample standard theme. Reference only: Talha decides how to bring it into `lib/core/theme/`; run `flutter analyze` after (it was not compiled in the design workspace) |

**Order of truth:** tokens → latest hi-fi screen (Figma page 02 / highest PNG version) → folder README → wireframes (history only, do not build from them).

**Checked against:** `dev` at PR #81 and the app repo `main` at `5591848`.
