# Research: RustFS capabilities for the ETL orchestrator

Resolves issue #142 (parent map #140; related #108). **Findings + one recommendation; no application code.**

Sources (primary):
- **[src]**: RustFS source, `rustfs/rustfs` main @ `077b961` (2026-09-21, workspace version 1.0.1). Paths relative to that repo's root.
- **[doc]**: RustFS in-repo docs (`docs/architecture/s3-compatibility-matrix.md`, `docs/operations/outbound-connection-policy.md`).
- **[gh]**: RustFS GitHub issues (state/dates via `gh`).
- This repo pins `rustfs/rustfs:1.0.0` in `docker-compose.dev-test.yml`; main is ahead (1.0.1-preview.8 released 2026-09-21). Behavior below is main; some cited fixes landed after 1.0.0 betas/rcs. **Nothing was run against the container**; verify with section 7.

## 1. Paginated listing with prefix
- ListObjects/ListObjectsV2 with prefix, delimiter, marker, max-keys: "Supported" [doc s3-compatibility-matrix.md:28]. V2 returns `NextContinuationToken` [src rustfs/src/app/bucket_usecase.rs:1153-1165]; e2e `crates/e2e_test/src/list_objects_v2_pagination_test.rs` exists.
- Past listing bugs, all closed [gh]: #1596 (V1 NextMarker instead of V2 token), #2439 (duplicate keys with directory markers), #3217 (`IsTruncated=false` with many delete markers), #5051 (empty result for shallow prefixes), #5792 (same continuation token reissued; cause a 5 s walk timeout, removed after beta.12 per #5684), #6174 (perf regression on nested prefixes), #6218 (ghost keys after partial delete-marker).
- Implication: usable, but a steady bug stream. Poller must be idempotent, tolerate duplicates, and never treat one listing as authoritative for "deleted". Continuation token is a cursor within one scan only; the processed ledger (map Notes) is the durable cursor.
- Directory-marker keys (ending `/`) are stored as null version [doc :107]; skip zero-size keys ending in `/`.
- `metadata=true` listing extension is MinIO-style, non-standard [doc :45]. Do not use.

## 2. Server-side CopyObject (incl. large)
- Implemented [src rustfs/src/app/object/copy.rs:153 `execute_copy_object`]. Supports `MetadataDirective`, `TaggingDirective`, copy-source `If-Match`/`If-None-Match`, source `versionId`, SSE, object lock, storage class. Access-point/Outpost sources: NotImplemented.
- "Server-side" means server-internal, not a metadata-only rename: the handler opens a read stream on the source and rewrites it via a `HashReader` into a new object (copy.rs ~660-680). Cost is a full read+write of every byte, including cross-bucket. No size cap or automatic multipart split found in the handler (searched for 5 GiB / EntityTooLarge: none). Huge objects run as one long request: use generous client read timeouts.
- `UploadPartCopy` exists [src rustfs/src/app/multipart_usecase.rs:1570]. Fallback for huge objects (boto3 managed `copy()` switches to it above its multipart threshold).
- #7056 (closed 2026-09-02; a reporter reproduced on 1.0.0-rc.6 after fix PR #7065): `CopyObject` failing "part missing or corrupt" right after `CompleteMultipartUpload`. Mitigation: ETL sources are settled (quiescence wait in design); retry copy with backoff.
- Response echoes source version in `x-amz-copy-source-version-id` (#4976, fixed).

## 3. ETag / checksum verification
- **Do not compare ETags across a copy.** Destination is written from a fresh reader with no expected MD5 (copy.rs ~660-680); its ETag is resolved from the streamed data [src crates/ecstore/src/set_disk/ops/object.rs:3824 `try_resolve_etag`]. A multipart source ETag is `md5-of-part-md5s-N` [src crates/ecstore/src/set_disk/mod.rs:7076 `get_complete_multipart_md5`]; the copy will differ. Inferred from source, confirm empirically.
- Checksum on copy [src copy.rs ~495-505, 660-690; doc :27; e2e `copy_object_checksum_test.rs`]:
  - `ChecksumAlgorithm` requested (CRC32, CRC32C, CRC64NVME, SHA1, SHA256, MD5, SHA512, XXHASH3/64/128): **computed fresh over the copied bytes**, returned in `CopyObjectResult` and later HEAD with `ChecksumMode=ENABLED`. Unknown algorithm -> `InvalidArgument`, destination untouched.
  - None requested: source's stored checksum is **carried over, not recomputed** (#4996); multipart source keeps its composite value. A source/destination match in this mode proves nothing about the copied bytes.
- Multipart-checksum bug class (from #108, closed [gh]): #3506, #4800, #7678 (fixed PR #7748, 2026-09-14), #1731, #2282 (CRC64NVME full-object mismatch on multipart). Pin the tag; stored source checksums may be wrong or dropped, so verification must not trust them.
- ETag formatting bugs, closed: #1771 (HTML-entity quotes in CopyObjectResult), #6185, #611. Strip quotes/entities before logging or comparing.

## 4. Scoped credentials / policies
- IAM users and service accounts exist (`crates/iam`, `crates/madmin/src/user.rs`, `account.rs`); bucket policies put/get/delete "Supported" [doc :31]. Policy engine supports `s3:prefix` `StringLike` conditions on `s3:ListBucket`/`s3:ListBucketVersions` and prefix-scoped resource ARNs [src crates/policy/src/policy/policy.rs:1108-1240 tests].
- Gaps: "Tenanted bucket policy edge cases: needs investigation" [doc :94]; ACL authorization intentionally unsupported [doc "Intentional Exclusions"].
- Fit: orchestrator identity gets `s3:ListBucket` (prefix condition), `s3:GetObject`, `s3:DeleteObject` on source bucket; `s3:PutObject`, `s3:GetObject` on raw bucket. Sandbox gets nothing (already decided). Copy needs read on source AND write on destination; test both.

## 5. Bucket event notifications
- Implemented via S3 `PutBucketNotificationConfiguration` [src rustfs/src/app/bucket_usecase.rs:2458]. Events include `s3:ObjectCreated:Put/Post/Copy/CompleteMultipartUpload` [src crates/s3-types/src/event_name.rs]. Targets: webhook, AMQP, Kafka, MQTT, NATS, Pulsar, Redis, MySQL, Postgres [src crates/targets/src/target/]. ARN form `arn:rustfs:sqs:<region>:<name>:webhook` [e2e notification_webhook_test.rs:72]. Webhook/AMQP support `queue_dir` + `queue_limit` on-disk retry queue [src target/webhook.rs:128-177, amqp.rs:71].
- Requirements: notify enabled (`RUSTFS_NOTIFY_ENABLE`); private/compose-network webhook endpoints need `RUSTFS_OUTBOUND_ALLOW_ORIGINS` = exact origin; redirects and proxies disabled [doc outbound-connection-policy.md:17,37-43].
- History (closed): webhooks silently not firing beta.1 (#2756) and beta.9+ (#5387, outbound-origin policy); AWS event schema mismatch (#1154).
- No documented exactly-once or ordering guarantee found. Treat as at-least-once, unordered, silently absent on misconfig. Matches the map: events = optimization, polling stays authoritative.

## 6. Recommendation: move-with-verify
Per Job, after script success and platform validation/load committed:

1. **Snapshot**: HEAD source; record size, ETag, LastModified. Fail if changed vs the job's recorded input snapshot. Reference hash = SHA-256 the orchestrator computed when staging `/input` (job already records input keys+checksums per map Notes). Do not use stored RustFS checksums.
2. **Copy** source -> raw bucket with `CopySourceIfMatch=<source ETag>` and `ChecksumAlgorithm=SHA256` (forces fresh hash over copied bytes). Deterministic raw key (e.g. `<project>/<binding>/<job_id>/<orig key>`) so retries are idempotent; if it already exists, skip to step 3. Retry with backoff on 5xx / "part missing or corrupt" (#7056). Above a size threshold use boto3 managed copy (`UploadPartCopy`), verified identically.
3. **Verify**: HEAD destination with `ChecksumMode=ENABLED`; require `ContentLength == source size` and destination SHA-256 == reference hash. Never compare ETags. Fallback if the pinned build does not compute fresh SHA-256 on copy: GET the destination and hash it (one extra read).
4. **Delete source** only after step 3 passes and the binding keep toggle is off; re-HEAD source ETag right before delete (DeleteObject has no If-Match). Record raw key, checksum, delete outcome on the Job. Delete failure after verified copy = job succeeded with `source_cleanup_pending`; ledger prevents reprocessing.
5. **Failure**: any step failing leaves source intact; a raw copy may exist (retry overwrites idempotently; orphan cleanup optional).

Rejected: ETag compare (differs for multipart sources), copy-without-algorithm compare (carries stored value, verifies nothing), delete-before-verify.

## 7. Verify against the pinned image before relying
1. Copy multipart-uploaded object (>=100 MB, SHA-256 at upload) with `ChecksumAlgorithm=SHA256`: destination hash equals independent hash; ETag differs from source.
2. Same copy with no algorithm: confirm stored composite carried over.
3. Multi-GB copy: duration, timeouts, memory.
4. `CopySourceIfMatch` mismatch -> 412, destination absent.
5. Policy: credential with `s3:ListBucket` + `s3:prefix` condition cannot list other prefixes; copy denied without destination write.
6. ListObjectsV2 over >5,000 keys with concurrent uploads: duplicates/skips within tolerance.
7. Webhook target on compose network with `RUSTFS_OUTBOUND_ALLOW_ORIGINS`: event per multipart complete.

## Open items
- `UploadPartCopy` large-object limits not documented; e2e `multipart_copy_readiness_test.rs` not read.
- 1.0.0 tag vs main not diffed.
