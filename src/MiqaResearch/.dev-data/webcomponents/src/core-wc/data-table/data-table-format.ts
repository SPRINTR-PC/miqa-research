// Formatting of `date` and `datetime` cells. The server sends dates as YYYY-MM-DD and date-times as ISO 8601 with a UTC
// offset; both are formatted in the browser's locale (`locale` is only for tests). Values that are not valid dates are
// shown as they came.

const ISO_DATE = /^(\d{4})-(\d{2})-(\d{2})(?:[T ](.+))?$/;

function isEmpty(value: unknown): boolean {
  return value === null || value === undefined || value === "";
}

// Also accepts the space-separated form, which some browsers do not parse.
function parseInstant(text: string): Date {
  return new Date(text.replace(" ", "T"));
}

/** A real calendar day at UTC midnight, or undefined (no rolling over of 31 Feb, no mapping of year 50 to 1950). */
function utcCalendarDay(year: number, month: number, day: number): Date | undefined {
  const date = new Date(0);
  date.setUTCFullYear(year, month - 1, day);
  const isRealDay = date.getUTCFullYear() === year && date.getUTCMonth() === month - 1 && date.getUTCDate() === day;
  return isRealDay ? date : undefined;
}

/**
 * The calendar date, without a time. It is never converted between timezones: a date is the same day for everyone, and
 * `new Date("2026-03-01")` (UTC midnight) would show the previous day west of UTC.
 */
export function formatDate(value: unknown, locale?: string): string {
  if (isEmpty(value)) return "";
  const text = String(value);
  const match = ISO_DATE.exec(text);
  if (!match) return text;

  const [, year, month, day, time] = match;
  const calendarDay = utcCalendarDay(Number(year), Number(month), Number(day));
  if (!calendarDay || (time !== undefined && Number.isNaN(parseInstant(text).getTime()))) return text;
  return calendarDay.toLocaleDateString(locale, { dateStyle: "medium", timeZone: "UTC" });
}

/**
 * An instant converted to the browser's local timezone. A value with no time of day is a plain date, so it is not
 * converted.
 */
export function formatDateTime(value: unknown, locale?: string): string {
  if (isEmpty(value)) return "";
  const text = String(value);
  const match = ISO_DATE.exec(text);
  if (match && match[4] === undefined) return formatDate(text, locale);

  const instant = parseInstant(text);
  if (Number.isNaN(instant.getTime())) return text;
  return instant.toLocaleString(locale, { dateStyle: "medium", timeStyle: "short" });
}
