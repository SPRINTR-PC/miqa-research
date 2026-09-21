function isPlainObject(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function snakeToCamelKey(key: string): string {
  return key.replace(/_([a-z0-9])/g, (_match, char: string) => char.toUpperCase());
}

/**
 * Recursively converts snake_case object keys to camelCase, leaving arrays,
 * primitives, and already-camelCase keys untouched. Chart API endpoints
 * render plain snake_case JSON like every other endpoint in this codebase
 * (CONTEXT.md, ADR 0020's amendment) — this is applied once per fetched
 * response, before it's treated as a `ChartResponse`.
 */
export function snakeToCamelDeep<T = unknown>(value: unknown): T {
  if (Array.isArray(value)) {
    return value.map((item) => snakeToCamelDeep(item)) as T;
  }
  if (isPlainObject(value)) {
    const result: Record<string, unknown> = {};
    for (const [key, val] of Object.entries(value)) {
      result[snakeToCamelKey(key)] = snakeToCamelDeep(val);
    }
    return result as T;
  }
  return value as T;
}
