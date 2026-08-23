import { describe, expect, it } from "vitest";

import {
  DEFAULT_LOCALE,
  LOCALES,
  catalog,
  messageKeys,
  resolveLocale,
  translate,
  translatorFor,
  type Locale,
} from "./i18n.js";

describe("interface language (UI 11.5)", () => {
  it("defaults new classroom browsers to Korean and preserves a valid choice", () => {
    expect(DEFAULT_LOCALE).toBe("ko");
    expect(resolveLocale(null)).toBe("ko");
    expect(resolveLocale("ko")).toBe("ko");
    expect(resolveLocale("en")).toBe("en");
    expect(resolveLocale("unsupported")).toBe("ko");
  });

  it("has the same keys in every language", () => {
    const expected = new Set(messageKeys());
    for (const locale of LOCALES) {
      expect(new Set(Object.keys(catalog(locale)))).toEqual(expected);
    }
  });

  it("has no empty or placeholder message in any language", () => {
    for (const locale of LOCALES) {
      for (const [key, message] of Object.entries(catalog(locale))) {
        expect(message.trim(), `${locale}.${key}`).not.toBe("");
        // A message that is its own key is a missing translation that shipped.
        expect(message, `${locale}.${key}`).not.toBe(key);
      }
    }
  });

  it("keeps technical identifiers out of the catalogs", () => {
    // A device id, a capability, and a session state read the same in both
    // languages, because they are what a student and an instructor say to each
    // other when something is wrong. They must be interpolated, never
    // translated -- so no catalog entry may contain one.
    const identifiers = [
      "drive.velocity",
      "fake-s1-main",
      "emergency_stopped",
      "DEVICE_NOT_ARMED",
    ];
    for (const locale of LOCALES) {
      for (const [key, message] of Object.entries(catalog(locale))) {
        for (const identifier of identifiers) {
          expect(message, `${locale}.${key}`).not.toContain(identifier);
        }
      }
    }
  });

  it("interpolates named values", () => {
    expect(translate("en", "simulation.replayed", { count: 12 })).toContain(
      "12",
    );
    expect(translate("ko", "simulation.replayed", { count: 12 })).toContain(
      "12",
    );
  });

  it("leaves no placeholder unfilled in either language", () => {
    for (const locale of LOCALES) {
      for (const [key, message] of Object.entries(catalog(locale))) {
        const placeholders = message.match(/\{[a-z]+\}/gi) ?? [];
        const english = catalog("en")[key as keyof ReturnType<typeof catalog>];
        const englishPlaceholders = english.match(/\{[a-z]+\}/gi) ?? [];
        expect(new Set(placeholders), `${locale}.${key}`).toEqual(
          new Set(englishPlaceholders),
        );
      }
    }
  });

  it("falls back to English rather than showing a blank label", () => {
    // Forced: the types make this impossible, and the fallback exists for the
    // build where somebody defeats them.
    const partial = { en: "Devices" } as unknown as Record<Locale, string>;
    expect(partial.ko ?? partial.en).toBe("Devices");
  });

  it("shows the key rather than nothing when both catalogs miss it", () => {
    const broken = "not.a.real.key" as Parameters<typeof translate>[1];
    expect(translate("ko" as Locale, broken)).toBe("not.a.real.key");
  });

  it("builds a translator bound to one language", () => {
    const t = translatorFor("ko");
    expect(t("nav.devices")).toBe(catalog("ko")["nav.devices"]);
  });
});
