# Research: Cornerstone3D performance limits for large volumes and very large WSI

Resolves issue #206 (parent map #176). **Findings and recommended defaults. Open choices are listed at the end.**

Pinned versions: **@cornerstonejs/* 5.10.11** (tag `v5.10.11`, commit `66740e9`), **dicom-microscopy-viewer (dmv) 0.48.24** (tag `v0.48.24`), and **@kitware/vtk.js 36.4.1** (the version CS3D core pins in `packages/core/package.json`).

Sources:
- **[cs]**: cornerstone3D source at `v5.10.11`. Paths are relative to `packages/`.
- **[docs]**: cornerstone3D docs in the same tag (`packages/docs/docs/...`), published at https://www.cornerstonejs.org/docs/. Where the docs and the source differ, the source wins, and each such case is flagged.
- **[dmv]**: dicom-microscopy-viewer source at `v0.48.24`, `src/`.
- **[vtk]**: `@kitware/vtk.js@36.4.1` npm package, `Rendering/OpenGL/`.
- **[repo]**: this repository. Prior decisions: #185 (packaging), #186 (WSI), #187 (MPR and fusion), #190 (WADO-RS fixes).

Sizes use MiB/GiB. "Voxel" means one sample of one component.

---

## 1. CPU cache: size and eviction

**One byte budget, counted over images only.**
- `Cache._maxCacheSize = 3 * ONE_GB` (3 GiB). The class comment says the value is "tuned to the chromium garbage collection cycle" [cs `core/src/cache/cache.ts:24,48,26-34`].
- `cache.setMaxCacheSize(bytes)` changes the limit. Its doc comment says to set it **before** data is added. Shrinking the limit below the current usage "will cause issues" [cs `cache.ts:81-97`].
- Since 2.x, volumes hold no voxel buffer of their own. All pixel data lives in the **image** cache, and a volume streams image by image to the GPU [docs `concepts/cornerstone-core/cahce.md` "Cache Optimizations"]. `getCacheSize()` returns `_imageCacheSize` only [cs `cache.ts:140`]. Geometry (contours and surfaces) has its own counter.

**Eviction is LRU over "volatile" images only.**
- `decacheIfNecessaryUntilBytesAvailable` sorts cached images by `timeStamp` and removes the oldest first. When it makes room for a volume, it first evicts images that don't belong to that volume [cs `cache.ts:310-381`].
- Images belonging to a cached volume carry `sharedCacheKey = volumeId` and are **never** auto-evicted. `isCacheable()` only counts free space plus images without a `sharedCacheKey` [cs `cache.ts:109-126, 322-324`]. Such images are released only when the volume itself is removed (`removeVolumeLoadObject` / `purgeVolumeCache`), which clears the keys [cs `cache.ts:199-243`].
- When an image doesn't fit, `_putImageCommon` throws `Error(Events.CACHE_SIZE_EXCEEDED)` [cs `cache.ts:417-418`]. Derived volumes, which is how labelmaps are created, check `isCacheable` up front and throw `"... is not cacheable"` [cs `core/src/loaders/volumeLoader.ts:402-408`].
- Consequence: the 3 GiB limit is a **hard cap on everything that is open at once**, meaning the volumes in the viewer plus their labelmaps. LRU eviction only helps stack viewports and closed volumes.

**Sizing examples (bytes in cache per volume).** Data types come from `_determineDataType` [cs `core/src/utilities/generateVolumePropsFromImageIds.ts:128-151`]: 16-bit with integer rescale → `Int16Array`/`Uint16Array`; 16-bit with float rescale (PET SUV) → `Float32Array`; 8-bit → `Uint8Array`.

| Series | Voxels | Type | Cache |
|---|---|---|---|
| CT 512×512×1000 | 262 M | Int16 | 500 MiB |
| CT 512×512×2000 (thin-slice or whole-body) | 524 M | Int16 | 1000 MiB |
| PET 192×192×600 (SUV pre-scaled) | 22 M | Float32 | 84 MiB |
| Labelmap on the CT 512×512×1000 grid | 262 M | Uint8 | 250 MiB |
| MR 512×512×300 | 79 M | Int16/Uint16 | 150 MiB |

A fused CT(1000) + PET plus one labelmap needs about 835 MiB, which fits comfortably. **Two thin-slice 2000-slice CTs plus labelmaps would exceed 3 GiB.**

## 2. GPU textures and memory

- On WebGL2, each volume becomes **one 3D texture**, created with `texStorage3D`/`texImage3D` [vtk `Texture.js:841-884`]. Slices stream in with `texSubImage3D` as frames arrive [cs `core/src/RenderingEngine/vtkClasses/vtkStreamingOpenGLTexture.js:157,230`]. The three MPR viewports of one volume share a single texture through `vtkSharedVolumeMapper` [cs `RenderingEngine/vtkClasses/`].
- **Bytes per voxel on the GPU** [vtk `RenderWindow.js:230-242`, `Texture.js:253-316`]:
  - 8-bit: 1 B.
  - 16-bit: 2 B **only if** `EXT_texture_norm16` works (CS3D checks this with a probe [cs `core/src/utilities/textureSupport.ts`, `init.ts:99`]) or half-float is exact. **Otherwise 4 B (float)**.
  - Float32 (PET): 4 B.
  - So the CT 512×512×1000 above uses 500 MiB of VRAM with norm16, or 1000 MiB without it.
- `rendering.preferSizeOverAccuracy` (default `false` [cs `core/src/init.ts:28`]) lets vtk use half-float even when that loses precision [vtk `Texture.js:762-771`]. That halves VRAM on devices without norm16, but costs accuracy in the high bits. CS3D only uses it automatically on iOS, and only when the flag is set [cs `init.ts:140-147`].
- **No size guard.** Neither CS3D nor vtk checks `MAX_3D_TEXTURE_SIZE` on the WebGL2 path. CS3D only reads `MAX_TEXTURE_SIZE`, for 2D textures [cs `grep MAX_3D` → none; `vtkStreamingOpenGLVolumeMapper.js:191,283,455`]. WebGL2 guarantees only 256 per axis. Typical desktop GPUs report 2048 (an external fact, not verified in these sources). **A volume with more than 2048 slices (or rows/columns) may therefore fail to allocate, with no clear error.** The only mitigation built in is k-decimation (§3).
- WebGL contexts: the default `renderingEngineMode: ContextPool` with `webGlContextCount: 7`. `isMobile: true` forces 1 [cs `init.ts:38-44, 136-138`]. WSI (OpenLayers `WebGLTile`) uses its own context on top of these.

## 3. Progressive and decimated volume loading

**Progressive retrieval** is set per `'volume'`/`'stack'` (or per volumeId or transfer syntax) through `utilities.imageRetrieveMetadataProvider.add('volume', config)` [cs `core/src/utilities/imageRetrieveMetadataProvider.ts`; example `tools/examples/volumeProgressive/index.ts:386`]. If nothing is registered, the volume loads its images in plain order [cs `core/src/cache/classes/BaseStreamingImageVolume.ts:284-297`].

- `ProgressiveRetrieveImages.interleavedRetrieveStages` fetches, in order:
  1. the first, middle and last slices;
  2. every 4th slice (offset 3, then offset 1);
  3. the rest.
  Missing slices are filled by **replicating** nearby frames (`nearbyFrames`), so a coarse MPR appears early [cs `core/src/loaders/configuration/interleavedRetrieve.ts`; docs `concepts/progressive-loading/volumeProgressive.md`]. **This interleaving works with any transfer syntax** [docs same page: "Interleaving the images applies to any encoding for a volume"].
- Lossy or partial-resolution first passes (`multipleFast`/`singleFast` with `rangeIndex`, `streaming`, `framesPath`) need server support: HTJ2K RPCL with HTTP `Range`, streamed responses, or a second rendition at another path [docs `progressive-loading/requirements.md`, `non-htj2k-progressive.md`; cs `dicomImageLoader/src/imageLoader/wadors/getPixelData.ts:22-50`, `internal/rangeRequest.ts:129-175`]. #190 decided "stored syntax, never transcoded", so **this part is not available to us**. Without it, the `*Fast` stages just fetch full frames.
- Measured gain in the docs: for 512×512×174 over 4G, first render was 1.0–2.5 s against 8.8 s for a full load, using HTJ2K [docs `volumeProgressive.md`]. There is no published figure for interleaving without HTJ2K.

**Decimated volumes** use `decimatedVolumeLoader` (scheme id in the example: `'decimatedVolumeLoader'`, option `ijkDecimation: [i, j, k]`, default `[1,1,1]`) [cs `core/src/loaders/decimatedVolumeLoader.ts:76-135`; example `tools/examples/volumeDecimatedLoading`].
- **k** (slice) decimation drops slices *before* any fetch, so it saves network, decode, cache and VRAM alike, and spacing is recomputed [cs `decimatedVolumeLoader.ts:122-135`].
- **i/j** (in-plane) decimation only appends a URL fragment `#decimation=N`, which is not sent to the server [cs `:110-118`]. Full frames are still fetched and decoded, then resized in the worker to `targetBuffer` rows/columns (`replicate` by default, or `bilinear`) [cs `BaseStreamingImageVolume.ts:391-395`; `dicomImageLoader/src/decodeImageFrameWorker.js:339-349`]. It saves **cache and VRAM only**.
- Decimated volumes are a separate cache entry. Annotations and segmentations on them use the coarser grid. A SEG built on a decimated grid won't match the source geometry, so segmentation should always run on the full-resolution volume.

## 4. Decode workers and request concurrency

- **CS3D image-loader workers:** `dicomImageLoader.init({ maxWebWorkers })`. The default is `max(1, floor(navigator.hardwareConcurrency / 2))` [cs `dicomImageLoader/src/init.ts:21-36`]. The docs example shows `hardwareConcurrency || 1` [docs `concepts/cornerstone-core/imageLoader.md:41`]; the source default is half of that. Workers are managed by core's `webWorkerManager` (`maxWorkerInstances`, optional `autoTerminateOnIdle`) [cs `core/src/webWorkerManager/webWorkerManager.ts:16-60`].
- **dmv workers (WSI):** a separate pool with default `min(navigator.hardwareConcurrency || 1, 7)`, "to avoid memory problems in certain browsers" [dmv `src/webWorker/webWorkerManager.js:13-19`]. CS3D's `WSIViewport` exposes no way to change this.
- **Request pools** (defaults in source; the docs are stale) [cs `core/src/requestPool/requestPoolManager.ts:119-130`, `imageRetrievalPoolManager.ts:14-22`, `imageLoadPoolManager.ts:36-38`]:
  - `imageRetrievalPoolManager` (XHR): 200 each for interaction, thumbnail and prefetch. The docs say 20 [docs `requestPoolManager.md`].
  - `imageLoadPoolManager` (decode): 1000 each.
  - Base class defaults: 6/6/5.
  - Adjust with `setMaxSimultaneousRequests(type, n)`.
- The practical limit is therefore the **browser's per-host connection limit**: 6 on HTTP/1.1, while HTTP/2 multiplexes. A single-frame CT of 1000 slices means **1000 `/frames` requests plus one series `/metadata`**. Each passes session auth, the Participant Visibility check (#190) and a ranged S3 GET. Over HTTP/1.1 they queue six at a time.
- The app server is Granian (ASGI) [repo `src/MiqaResearch/Dockerfile:48`]. No TLS/HTTP-2 edge config is checked into the repo.

## 5. WSI (very large slides, 100k² px)

- **Scale:** at 100k×100k with 512² tiles, level 0 has about 38k tiles and the whole pyramid about 51k. With 256² tiles that becomes about 153k and 204k. Only visible tiles are requested, **one `/frames/{n}` request per tile** [#186]. A 1920×1080 view at native level needs roughly 8–40 tiles, depending on tile size and zoom.
- **Tile cache:** dmv option `tilesCacheSize` (default **1000 tiles**) is passed as `cacheSize` to OpenLayers `WebGLTile` layers. `preload` defaults to off (0 levels) [dmv `src/viewer.js:784-796, 912-920, 1384-1388`]. Decoded RGBA costs 1 MiB per 512² tile, so **1000 tiles is about 1 GiB** (CPU and GPU texture). For 256² tiles it is about 250 MiB. This memory is **outside** CS3D's 3 GiB cache.
- **CS3D hardcodes the dmv options:** `new VolumeImageViewer({ client, metadata, controls: ['overview','position'], retrieveRendered: false, bindings: {} })` [cs `core/src/RenderingEngine/WSIViewport.ts:607-613`]. So `tilesCacheSize`, `preload` and worker count **cannot be set without a subclass or patch**.
- Frame requests use `Accept: multipart/related; type="application/octet-stream"; transfer-syntax=*`, and dmv sniffs the codec from the payload [dmv `src/pyramid.js:440-478`].

## 6. HTTP caching for `/frames` (given #190: immutable caching and ranged S3 GETs)

- The loaders use plain `XMLHttpRequest`/`fetch` GETs with no cache-busting and no cache headers of their own [cs `dicomImageLoader/src/imageLoader/internal/xhrRequest.ts:41-52`, `wadors/getPixelData.ts:17-64`]. The browser HTTP cache therefore applies as-is.
- Frame URLs are built from pseudonymized UIDs plus the frame number. Derived objects are never changed in place (#189 Supersede chain), so a URL's bytes never change and `immutable` is sound.
- **Header detail:** `immutable` only has an effect together with a freshness lifetime. It needs `max-age`, otherwise the response is revalidated or treated as heuristically fresh (RFC 8246 §2).
- The two clients send **different `Accept` strings**:
  - CS3D stack/volume: `multipart/related; type=application/octet-stream; transfer-syntax=*` [cs `wadors/loadImage.ts:125-126`].
  - dmv: `type="application/octet-stream"`, quoted, via dicomweb-client.
  If the response varies on `Accept` (it does whenever a 406 is possible, #190), send `Vary: Accept`. The same frame then gets up to two cache entries, which is harmless.
- **`Range` on `/frames`:** not needed. CS3D only sends `Range` when a `rangeIndex` retrieve stage is configured (HTJ2K progressive), and we don't configure one. Ranged reads stay server-side, against S3 (#190).
- **Series `/metadata`:** it is rebuilt on every call (sanitized at serve time). For 1000 instances it is a large JSON document. It is *not* immutable, because it can change if the PHI or UID rules change, so a short `private, max-age` plus an ETag is appropriate.

---

## Recommended defaults

| Knob | Default | Why |
|---|---|---|
| `cache.setMaxCacheSize` | keep **3 GiB** on desktop; set once at init, before loading | upstream-tuned. All open volumes and labelmaps must fit, since there is no eviction |
| On `CACHE_SIZE_EXCEEDED` / "not cacheable" | catch and show "series too large to open with the current views", with an offer to close other volumes | the cache throws instead of degrading |
| `rendering.preferSizeOverAccuracy` | `false` | diagnostic accuracy. Only halves VRAM on devices without norm16 |
| `dicomImageLoader.init({ maxWebWorkers })` | leave at default (`cores/2`) | good balance with dmv's own pool |
| dmv worker pool | leave at default (≤7) | not configurable through CS3D |
| Request pools | leave at defaults (200 retrieval, 1000 decode) | the browser connection limit dominates |
| Volume retrieve config | `imageRetrieveMetadataProvider.add('volume', ProgressiveRetrieveImages.interleavedRetrieveStages)` | quick coarse MPR with any syntax, no server work |
| Decimation | off. Auto k-decimation (`[1,1,2]`, or more) only when a guard trips (see below) | k is the only knob that saves network and VRAM |
| Size guard (client, before loading) | estimate bytes = rows×cols×slices×bytes-per-voxel (Float32 for PET). If slices or rows/cols > `MAX_3D_TEXTURE_SIZE` (query `gl.getParameter`), or the sum across open volumes > about 2.5 GiB, apply k-decimation for **viewing** and turn off segmentation on that volume | prevents a silent 3D-texture failure and cache errors |
| WSI `tilesCacheSize` | upstream 1000 (see decision 4) | reasonable for 256² tiles, heavy for 512² |
| `/frames` response | `Cache-Control: private, max-age=31536000, immutable`, strong `ETag`, `Vary: Accept` | URL content never changes, and the session carries auth |
| `/metadata` response | `Cache-Control: private, max-age=300`, `ETag` | rebuilt at serve time, and can change |
| Transport | HTTP/2 at the browser-facing edge | 1000+ small requests per volume, and tiles |

## Cases that need a decision

1. **Oversized series policy.** When a series exceeds the 3D-texture limit or the cache budget: (a) refuse to open it, (b) auto-k-decimate for viewing only, with segmentation disabled (recommended), or (c) always load it at full resolution and accept the risk of failure. Also decide the thresholds.
2. **Browser-cache lifetime vs. access revocation.** A one-year `private` cache keeps pixel data on the client after Participant Visibility is revoked or the user logs out on a shared workstation. Options: accept this (pseudonymized pixels only), send `Clear-Site-Data: "cache"` on logout, or use a shorter `max-age`.
3. **HTTP/2 at the edge.** It isn't configured in the repo (Granian behind an unknown ingress). Confirm the deployment serves h2 to browsers. Otherwise loading is capped at 6 concurrent requests.
4. **WSI tile cache size.** CS3D's `WSIViewport` hardcodes dmv options. Keep dmv's defaults (1000 tiles, about 1 GiB at 512² tiles), or subclass/patch `WSIViewport` to pass `tilesCacheSize` (e.g. 300–500) and `preload`. This depends on the tile size our WSI ingestion produces.
5. **Per-request server cost on `/frames`.** A 1000-slice volume makes 1000 authenticated requests, each with a visibility check and an S3 range GET. Decide whether to memoize the visibility result per session and series (short TTL), or accept a DB hit per frame.
6. **Mobile and low-end devices.** Decide whether they are in scope. If so, use `isMobile: true` (1 GL context), a lower `setMaxCacheSize` (about 1 GiB) and a stricter size guard.
7. **Faster first render beyond interleaving.** This needs HTJ2K or reduced-resolution renditions, which conflicts with #190's "no transcoding". Record it as out of scope unless load times prove unacceptable.
