// Humsafar design tokens: style guide v0.2
// Source: docs/design/1.12_identity_access/Humsafar_Design_00_Style_guide_v0.2.png
// and docs/design/handoff/Humsafar_Design_Handoff_v1.0.pdf.
//
// REFERENCE FILE from the design side (Sarim). It is not part of the app build.
// Talha decides how to bring it into lib/core/theme/ (copy, adapt or merge).
// Values here are the single source of truth for colour, type and size;
// if a mockup PNG shows a slightly different red or grey, these values win
// (older v0.1 PNGs were drawn before the NFR-08 contrast fix).

import 'package:flutter/material.dart';

/// Colours. Use these names instead of Colors.teal / Colors.red / Colors.grey.
class HumsafarColors {
  HumsafarColors._();

  // Brand
  static const Color primary = Color(0xFF0E7490); // teal-blue: buttons, links, active tab, app-bar pills
  static const Color primaryDark = Color(0xFF155E75); // pressed state, headings on tint, outline-button text
  static const Color primaryTint = Color(0xFFECFEFF); // pill background, info cards
  static const Color primarySoft = Color(0xFFCFFAFE); // subtitle on a primary button, light highlights

  // Neutrals
  static const Color background = Color(0xFFF8FAFC); // page background
  static const Color surface = Color(0xFFFFFFFF); // cards, app bar, fields
  static const Color text = Color(0xFF0F172A); // main text
  static const Color muted = Color(0xFF475569); // secondary text (v0.2, was #64748B)
  static const Color border = Color(0xFFCBD5E1); // card and field borders, dividers
  static const Color tabTrack = Color(0xFFE2E8F0); // segmented-tab background

  // Status
  static const Color success = Color(0xFF15803D); // verified, inside zone, taken
  static const Color successTint = Color(0xFFDCFCE7);
  static const Color warning = Color(0xFFB45309); // missed dose, left zone, urgent voice, band no data
  static const Color warningTint = Color(0xFFFEF3C7);
  static const Color danger = Color(0xFFB91C1C); // PANIC and critical alerts ONLY (v0.2, was #DC2626)
  static const Color dangerTint = Color(0xFFFEE2E2);
}

/// Sizes in logical pixels (design frame is 360 x 780).
class HumsafarSizes {
  HumsafarSizes._();

  static const double pagePadding = 20; // left / right page margin
  static const double gap = 12; // space between stacked components
  static const double appBarHeight = 56;
  static const double minTouchTarget = 48; // NFR-08 / accessibility

  static const double buttonHeight = 54;
  static const double buttonRadius = 14;
  static const double outlineWidth = 1.6; // secondary (outlined) button border

  static const double fieldHeight = 50;
  static const double fieldRadius = 12;

  static const double cardRadius = 14;
  static const double chipRadius = 14; // Aa and EN|UR pills, filter chips

  // Dependent Mode (screen 20)
  static const double panicButtonHeight = 200;
  static const double safetyButtonHeight = 130; // "I am OK", "My medicine"
  static const double bigButtonRadius = 22;
  static const double bigButtonOutline = 2.5;
}

/// Type scale. Font: Inter (google_fonts or bundled). Urdu falls back to a
/// Nastaliq / Naskh system font; see the handoff PDF, section 2.3.
class HumsafarText {
  HumsafarText._();

  static const String fontFamily = 'Inter';

  static const TextStyle title = TextStyle(fontSize: 26, fontWeight: FontWeight.w700, color: HumsafarColors.text);
  static const TextStyle heading = TextStyle(fontSize: 18, fontWeight: FontWeight.w700, color: HumsafarColors.text);
  static const TextStyle body = TextStyle(fontSize: 15, fontWeight: FontWeight.w400, color: HumsafarColors.text);
  static const TextStyle label = TextStyle(fontSize: 13, fontWeight: FontWeight.w600, color: HumsafarColors.text);
  static const TextStyle caption = TextStyle(fontSize: 12, fontWeight: FontWeight.w400, color: HumsafarColors.muted);
  static const TextStyle button = TextStyle(fontSize: 16, fontWeight: FontWeight.w700);

  // Dependent Mode big buttons
  static const TextStyle panicLabel = TextStyle(fontSize: 30, fontWeight: FontWeight.w800, color: Colors.white);
  static const TextStyle safetyLabel = TextStyle(fontSize: 26, fontWeight: FontWeight.w800);
  static const TextStyle safetySub = TextStyle(fontSize: 15, fontWeight: FontWeight.w500);
}

/// Example standard-mode theme built from the tokens.
/// Keep the existing high-contrast theme and its button-textStyle fix
/// (app_theme.dart, 2026-08-12 note): do not add a raw textStyle to
/// ElevatedButton.styleFrom here either.
ThemeData humsafarStandardTheme() {
  final scheme = ColorScheme.fromSeed(
    seedColor: HumsafarColors.primary,
    primary: HumsafarColors.primary,
    onPrimary: Colors.white,
    secondary: HumsafarColors.primaryDark,
    onSecondary: Colors.white,
    error: HumsafarColors.danger,
    onError: Colors.white,
    surface: HumsafarColors.surface,
    onSurface: HumsafarColors.text,
  );
  return ThemeData(
    useMaterial3: true,
    colorScheme: scheme,
    scaffoldBackgroundColor: HumsafarColors.background,
    appBarTheme: const AppBarTheme(
      backgroundColor: HumsafarColors.surface,
      foregroundColor: HumsafarColors.text,
      elevation: 0,
      scrolledUnderElevation: 0,
      toolbarHeight: HumsafarSizes.appBarHeight,
      titleTextStyle: HumsafarText.heading,
      shape: Border(bottom: BorderSide(color: HumsafarColors.border)),
    ),
    elevatedButtonTheme: ElevatedButtonThemeData(
      style: ElevatedButton.styleFrom(
        backgroundColor: HumsafarColors.primary,
        foregroundColor: Colors.white,
        minimumSize: const Size.fromHeight(HumsafarSizes.buttonHeight),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(HumsafarSizes.buttonRadius)),
      ),
    ),
    outlinedButtonTheme: OutlinedButtonThemeData(
      style: OutlinedButton.styleFrom(
        foregroundColor: HumsafarColors.primary,
        minimumSize: const Size.fromHeight(HumsafarSizes.buttonHeight),
        side: const BorderSide(color: HumsafarColors.primary, width: HumsafarSizes.outlineWidth),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(HumsafarSizes.buttonRadius)),
      ),
    ),
    inputDecorationTheme: InputDecorationTheme(
      filled: true,
      fillColor: HumsafarColors.surface,
      contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 15),
      enabledBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(HumsafarSizes.fieldRadius),
        borderSide: const BorderSide(color: HumsafarColors.border),
      ),
      focusedBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(HumsafarSizes.fieldRadius),
        borderSide: const BorderSide(color: HumsafarColors.primary, width: 2),
      ),
      errorBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(HumsafarSizes.fieldRadius),
        borderSide: const BorderSide(color: HumsafarColors.danger, width: 2),
      ),
      focusedErrorBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(HumsafarSizes.fieldRadius),
        borderSide: const BorderSide(color: HumsafarColors.danger, width: 2),
      ),
    ),
    cardTheme: CardThemeData(
      color: HumsafarColors.surface,
      elevation: 0,
      margin: EdgeInsets.zero,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(HumsafarSizes.cardRadius),
        side: const BorderSide(color: HumsafarColors.border),
      ),
    ),
    dividerTheme: const DividerThemeData(color: HumsafarColors.border, thickness: 1),
  );
}
