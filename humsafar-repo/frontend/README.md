# Humsafar Frontend — Task 0.4 Skeleton

This is the starting skeleton for Task 0.4 ("Flutter project skeleton — folder
structure, Riverpod setup, routing skeleton"), extracted from the Master
Roadmap and Talha's handbook. Drop this `frontend/` folder into the root of
the shared `humsafar` repo (alongside `backend/`).

## Why this folder structure

- **`lib/core/`** — cross-cutting concerns used by the whole app: routing,
  theming (Task 1.9 will fill in `core/theme/`), anything that isn't tied to
  one feature.
- **`lib/features/`** — one folder per product area (`splash`, `guardian`,
  `dependent`, and later `medication`, `panic_mode`, `wellness_check`,
  `records`, etc. as Phases 3–6 land). This is a "feature-first" layout —
  each folder holds everything for that feature (screens, and later its own
  widgets/providers), so two people working on different features almost
  never touch the same file. That matters here specifically because it's
  the same reasoning the repo-level `backend/` vs `frontend/` split uses,
  just one level down.
- **`lib/providers/`** — Riverpod providers that are genuinely global (auth
  state, app mode). Feature-specific providers will live inside their
  feature folder once those exist.
- **`lib/shared/widgets/`** — reusable widgets used across more than one
  feature (buttons, cards, form fields) — nothing here yet, added as
  duplication actually shows up.

## What's actually implemented right now

- `ProviderScope` + a working `MaterialApp.router` in `main.dart`.
- One placeholder route (`/`) rendering `SplashScreen`, wired through
  `go_router`.
- One example Riverpod provider (`appModeProvider`) proving state management
  is wired correctly end-to-end.

## What's intentionally NOT here yet (comes later, per the roadmap)

- Real Guardian/Dependent route trees → Task 1.8.
- Theming + large-text/high-contrast toggle → Task 1.9.
- Localization scaffold (English/Urdu) → Task 1.10.
- Any actual screens with real content → Task 1.11 onward.

## Running it

```bash
cd frontend
flutter pub get
flutter run
```

**Definition of done for Task 0.4** (per the handbook): the app runs on an
emulator/device and shows the empty navigation shell above. If you see the
"Humsafar / Navigation shell is live." screen, this task is complete.
