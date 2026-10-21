# UI text — English and Urdu (v0.3)

**Owner:** Sarim · **For:** Talha's Task 7.4 (full Urdu, NFR-09) and every screen built before it.

`Humsafar_UI_Text_EN_UR_v0.3.xlsx` lists the fixed text of all high-fidelity screens (1.12, 2.8, 3.9, 4.9, 5.9 v0.2, 6.11, and the coverage screens 07b, 16, 30, 30b, 31, 32 with Home 20 v0.2) — 525 lines, one row per string, with:

| Column | Meaning |
|---|---|
| Key | Suggested localisation key (`area.name`), usable as the Flutter `.arb` key |
| Screen(s) | Mockup screen numbers where it appears |
| English / Urdu | The text; `{name}`, `{time}`, `{n}` … are filled in by the app and must stay in both |
| Note | Context for the translator or developer |
| Check / Better Urdu | Sarim's review (OK / Change + correction) |

Sample data on the mockups (names, times, medicine names, numbers) is not included.

Draft rules: simple polite Urdu (آپ form); Primary / Secondary kept as پرائمری / سیکنڈری; SMS, PDF, Wi-Fi, PIN, QR in English letters; arrows right-to-left. **Open point:** the big red button says مدد (help) in Urdu rather than a transliteration of PANIC — team to agree.

v0.3 (21 Oct 2026): 64 new lines for the coverage screens and the dose-due button on Home 20 v0.2.
