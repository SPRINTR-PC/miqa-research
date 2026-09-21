// Formatting of `date` and `datetime` cells: `yyyy-mm-dd` and `yyyy-mm-dd HH:MM:SS` (24 hour), the same in every locale.
// The server sends dates as YYYY-MM-DD and date-times as ISO 8601 with a UTC offset. Values that are not valid dates are
// shown as they came.

const ISO_DATE = /^(\d{4})-(\d{2})-(\d{2})(?:[T ](.+))?$/;

function isEmpty(value: unknown): boolean {
  return value === null || value === undefined || value === "";
}

function pad(value: number, length = 2): string {
  return String(value).padStart(length, "0");
}

// Also accepts the space-separated form, which some browsers do not parse.
function parseInstant(text: string): Date {
  return new Date(text.replace(" ", "T"));
}

function isRealCalendarDay(year: number, month: number, day: number): boolean {
  // No rolling over of 31 Feb, and no mapping of year 50 to 1950 (which `Date.UTC` does).
  const date = new Date(0);
  date.setUTCFullYear(year, month - 1, day);
  return date.getUTCFullYear() === year && date.getUTCMonth() === month - 1 && date.getUTCDate() === day;
}

/**
 * The calendar date as `yyyy-mm-dd`, without a time. It is never converted between timezones: a date is the same day
 * for everyone, and `new Date("2026-03-01")` (UTC midnight) would show the previous day west of UTC.
 */
export function formatDate(value: unknown): string {
  if (isEmpty(value)) return "";
  const text = String(value);
  const match = ISO_DATE.exec(text);
  if (!match) return text;

  const [, year, month, day, time] = match;
  if (!isRealCalendarDay(Number(year), Number(month), Number(day))) return text;
  if (time !== undefined && Number.isNaN(parseInstant(text).getTime())) return text;
  return `${year}-${month}-${day}`;
}

/**
 * An instant as `yyyy-mm-dd HH:MM:SS` in the browser's local timezone. A value with no time of day is a plain date, so it
 * is shown as a date and not converted.
 */
export function formatDateTime(value: unknown): string {
  if (isEmpty(value)) return "";
  const text = String(value);
  const match = ISO_DATE.exec(text);
  if (match && match[4] === undefined) return formatDate(text);

  const instant = parseInstant(text);
  if (Number.isNaN(instant.getTime())) return text;
  const date = `${pad(instant.getFullYear(), 4)}-${pad(instant.getMonth() + 1)}-${pad(instant.getDate())}`;
  const time = `${pad(instant.getHours())}:${pad(instant.getMinutes())}:${pad(instant.getSeconds())}`;
  return `${date} ${time}`;
}
