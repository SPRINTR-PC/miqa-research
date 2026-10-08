// #291 Drafts: the store keyed per user × participant × series × kind, with a 7-day TTL.
// Seam: DraftStore over the in-memory backend (happy-dom has no IndexedDB; the IndexedDB backend
// runs in the browser harness, browser-tests/drafts.spec.ts).
import { describe, expect, it } from "vitest";

import { DRAFT_TTL_MS, DraftStore, memoryDraftBackend, type DraftKey } from "./drafts.ts";

const DAY = 24 * 3600 * 1000;
const key = (extra: Partial<DraftKey> = {}): DraftKey => ({
  user: "7",
  participant: "p1",
  seriesUid: "2.25.200",
  kind: "annotation",
  ...extra,
});

function store(start = Date.UTC(2026, 9, 8)) {
  const clock = { now: start };
  const backend = memoryDraftBackend();
  return { clock, backend, drafts: new DraftStore(backend, () => clock.now) };
}

describe("draft store", () => {
  it("keeps a draft with the head it was based on", async () => {
    const { drafts, clock } = store();
    const head = { id: "v3", chain_id: "c1", kind: "annotation", version: 3, author: "bertil", created_at: "2026-10-01T10:00:00Z", series_instance_uid: "2.25.sr3" };
    await drafts.save(key(), { head, canChange: true }, { lines: 2 });

    const draft = await drafts.load(key());

    expect(draft).toMatchObject({ base: { head: { id: "v3", version: 3 }, canChange: true }, data: { lines: 2 }, savedAt: clock.now });
  });

  it("is per user: another user never sees it", async () => {
    const { drafts } = store();
    await drafts.save(key(), undefined, { lines: 1 });

    expect(await drafts.load(key({ user: "8" }))).toBeUndefined();
    expect(await drafts.load(key())).toBeDefined();
  });

  it("is per participant, series and kind", async () => {
    const { drafts } = store();
    await drafts.save(key(), undefined, "mine");

    expect(await drafts.load(key({ participant: "p2" }))).toBeUndefined();
    expect(await drafts.load(key({ seriesUid: "2.25.201" }))).toBeUndefined();
    expect(await drafts.load(key({ kind: "segmentation" }))).toBeUndefined();
  });

  it("expires after 7 days and is then deleted", async () => {
    const { drafts, clock, backend } = store();
    await drafts.save(key(), undefined, "old");

    clock.now += DRAFT_TTL_MS - 1;
    expect(await drafts.load(key())).toBeDefined();

    clock.now += 2;
    expect(await drafts.load(key())).toBeUndefined();
    expect(await backend.all()).toEqual([]);
  });

  it("saving again restarts the 7 days", async () => {
    const { drafts, clock } = store();
    await drafts.save(key(), undefined, "v1");
    clock.now += 6 * DAY;
    await drafts.save(key(), undefined, "v2");
    clock.now += 6 * DAY;

    expect((await drafts.load(key()))?.data).toBe("v2");
  });

  it("purges every expired draft, of any user", async () => {
    const { drafts, clock, backend } = store();
    await drafts.save(key({ user: "8" }), undefined, "theirs");
    clock.now += 3 * DAY;
    await drafts.save(key(), undefined, "mine");
    clock.now += 5 * DAY;

    await drafts.purgeExpired();

    expect((await backend.all()).map((d) => d.data)).toEqual(["mine"]);
  });

  it("discard deletes it", async () => {
    const { drafts } = store();
    await drafts.save(key(), undefined, "x");

    await drafts.discard(key());

    expect(await drafts.load(key())).toBeUndefined();
  });
});
