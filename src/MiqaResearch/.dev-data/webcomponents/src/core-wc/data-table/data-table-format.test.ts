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

describe("formatDate (yyyy-mm-dd)", () => {
  for (const timeZone of ["America/Los_Angeles", "Asia/Tokyo", "UTC"]) {
    describe(`in ${timeZone}`, () => {
      inTimeZone(timeZone);

      it("renders a date-only value as that calendar date, never shifted by the timezone", () => {
        expect(formatDate("2026-03-01")).toBe("2026-03-01");
      });

      it("renders only the date of a value that also carries a time, without converting it", () => {
        expect(formatDate("2026-03-01T23:30:00+00:00")).toBe("2026-03-01");
      });
    });
  }

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
    expect(formatDate("2028-02-29")).toBe("2028-02-29");
  });

  it("keeps a four digit year for years before 1000 and does not map years before 100 into the 1900s", () => {
    expect(formatDate("0050-01-01")).toBe("0050-01-01");
  });

  it("does not accept trailing garbage after the date", () => {
    expect(formatDate("2026-03-01 garbage")).toBe("2026-03-01 garbage");
  });
});

describe("formatDateTime (yyyy-mm-dd HH:MM:SS, local time)", () => {
  describe("in Asia/Tokyo (UTC+9)", () => {
    inTimeZone("Asia/Tokyo");

    it("converts a UTC instant to the local date and time", () => {
      expect(formatDateTime("2026-03-01T23:30:00+00:00")).toBe("2026-03-02 08:30:00");
    });

    it("converts an instant given with another offset", () => {
      expect(formatDateTime("2026-03-01T10:15:00+02:00")).toBe("2026-03-01 17:15:00");
    });

    it("keeps the seconds and truncates fractions of a second", () => {
      expect(formatDateTime("2026-03-01T23:30:45.999+00:00")).toBe("2026-03-02 08:30:45");
    });

    it("renders local midnight as 00:00:00 in 24 hour time", () => {
      expect(formatDateTime("2026-03-01T15:00:00+00:00")).toBe("2026-03-02 00:00:00");
      expect(formatDateTime("2026-03-01T03:04:05+00:00")).toBe("2026-03-01 12:04:05");
    });

    it("accepts a space-separated date and time", () => {
      expect(formatDateTime("2026-03-01 23:30:00+00:00")).toBe("2026-03-02 08:30:00");
    });
  });

  describe("in Asia/Kolkata (UTC+5:30)", () => {
    inTimeZone("Asia/Kolkata");

    it("converts across a half-hour offset", () => {
      expect(formatDateTime("2026-03-01T10:15:00+00:00")).toBe("2026-03-01 15:45:00");
    });
  });

  describe("in Europe/Stockholm across the spring DST change (2026-03-29)", () => {
    inTimeZone("Europe/Stockholm");

    it("uses the offset in force at that instant", () => {
      expect(formatDateTime("2026-03-28T12:00:00+00:00")).toBe("2026-03-28 13:00:00"); // CET, UTC+1
      expect(formatDateTime("2026-03-30T12:00:00+00:00")).toBe("2026-03-30 14:00:00"); // CEST, UTC+2
    });
  });

  describe("in America/Los_Angeles (UTC-8 in March before DST)", () => {
    inTimeZone("America/Los_Angeles");

    it("converts a UTC instant to the local date and time", () => {
      expect(formatDateTime("2026-03-01T23:30:00+00:00")).toBe("2026-03-01 15:30:00");
    });

    it("renders a date-only value as a date rather than shifting it to the previous day", () => {
      expect(formatDateTime("2026-03-01")).toBe("2026-03-01");
    });
  });

  it.each([null, undefined, ""])("renders %j as an empty cell", (value) => {
    expect(formatDateTime(value)).toBe("");
  });

  it("falls back to the raw text for a value that is not a date", () => {
    expect(formatDateTime("not a date")).toBe("not a date");
  });
});
