import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { formatDate, formatDateTime } from "./data-table-format";

function inTimeZone(timeZone: string) {
  beforeEach(() => {
    vi.stubEnv("TZ", timeZone);
  });
  afterEach(() => {
    vi.unstubAllEnvs();
  });
}

describe("formatDate", () => {
  for (const timeZone of ["America/Los_Angeles", "Asia/Tokyo", "UTC"]) {
    describe(`in ${timeZone}`, () => {
      inTimeZone(timeZone);

      it("renders a date-only value as that calendar date, never shifted by the timezone", () => {
        expect(formatDate("2026-03-01", "en-GB")).toBe("1 Mar 2026");
      });

      it("renders only the date of a value that also carries a time, without converting it", () => {
        expect(formatDate("2026-03-01T23:30:00+00:00", "en-GB")).toBe("1 Mar 2026");
      });
    });
  }

  it("formats in the given locale", () => {
    expect(formatDate("2026-03-01", "sv-SE")).toBe("1 mars 2026");
  });

  it.each([null, undefined, ""])("renders %j as an empty cell", (value) => {
    expect(formatDate(value)).toBe("");
  });

  it("falls back to the raw text for a value that is not a date", () => {
    expect(formatDate("not a date")).toBe("not a date");
  });

  it.each(["2026-02-31", "2026-13-01", "2026-00-10", "2026-04-31", "2026-01-32", "2025-02-29"])(
    "falls back to the raw text for the impossible date %s instead of rolling over",
    (value) => {
      expect(formatDate(value)).toBe(value);
    }
  );

  it("accepts a real leap day", () => {
    expect(formatDate("2028-02-29", "en-GB")).toBe("29 Feb 2028");
  });

  it("does not map years before 100 into the 1900s", () => {
    expect(formatDate("0050-01-01", "en-GB")).toContain("50");
    expect(formatDate("0050-01-01", "en-GB")).not.toContain("1950");
  });

  it("does not accept trailing garbage after the date", () => {
    expect(formatDate("2026-03-01 garbage")).toBe("2026-03-01 garbage");
  });
});

describe("formatDateTime", () => {
  describe("in Asia/Tokyo (UTC+9)", () => {
    inTimeZone("Asia/Tokyo");

    it("converts a UTC instant to the local date and time", () => {
      expect(formatDateTime("2026-03-01T23:30:00+00:00", "en-GB")).toBe("2 Mar 2026, 08:30");
    });

    it("converts an instant given with another offset", () => {
      expect(formatDateTime("2026-03-01T10:15:00+02:00", "en-GB")).toBe("1 Mar 2026, 17:15");
    });
  });

  describe("in Asia/Kolkata (UTC+5:30)", () => {
    inTimeZone("Asia/Kolkata");

    it("converts across a half-hour offset", () => {
      expect(formatDateTime("2026-03-01T10:15:00+00:00", "en-GB")).toBe("1 Mar 2026, 15:45");
    });
  });

  describe("in Europe/Stockholm across the spring DST change (2026-03-29)", () => {
    inTimeZone("Europe/Stockholm");

    it("uses the offset in force at that instant", () => {
      expect(formatDateTime("2026-03-28T12:00:00+00:00", "en-GB")).toBe("28 Mar 2026, 13:00"); // CET, UTC+1
      expect(formatDateTime("2026-03-30T12:00:00+00:00", "en-GB")).toBe("30 Mar 2026, 14:00"); // CEST, UTC+2
    });
  });

  it("accepts a space-separated date and time and fractional seconds", () => {
    vi.stubEnv("TZ", "Asia/Tokyo");
    expect(formatDateTime("2026-03-01 23:30:00+00:00", "en-GB")).toBe("2 Mar 2026, 08:30");
    expect(formatDateTime("2026-03-01T23:30:00.123456+00:00", "en-GB")).toBe("2 Mar 2026, 08:30");
    vi.unstubAllEnvs();
  });

  describe("in America/Los_Angeles (UTC-8 in March before DST)", () => {
    inTimeZone("America/Los_Angeles");

    it("converts a UTC instant to the local date and time", () => {
      expect(formatDateTime("2026-03-01T23:30:00+00:00", "en-GB")).toBe("1 Mar 2026, 15:30");
    });

    it("renders a date-only value as a date rather than shifting it to the previous day", () => {
      expect(formatDateTime("2026-03-01", "en-GB")).toBe("1 Mar 2026");
    });
  });

  it.each([null, undefined, ""])("renders %j as an empty cell", (value) => {
    expect(formatDateTime(value)).toBe("");
  });

  it("falls back to the raw text for a value that is not a date", () => {
    expect(formatDateTime("not a date")).toBe("not a date");
  });
});
