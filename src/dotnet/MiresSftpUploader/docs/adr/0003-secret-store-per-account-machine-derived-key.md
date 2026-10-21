# Secrets are stored encrypted per account, with a machine-derived key

Besides environment variables, a Secret can live in a **Secret Store**: a small SQLite file (`secrets.db`) in each account's own application-data folder, apart from the Upload State. Values are encrypted with AES-256-GCM, the Secret's name bound in as associated data. The key is derived with HKDF from the OS machine identifier, the account name and a random salt kept in the file. The environment variable still wins. A value that cannot be decrypted (another machine or account, a damaged file) reads as "not set" and is reported as unreadable; a machine with no stable identifier cannot use the store at all, and it never falls back to a fixed key.

This is protection against a Secret leaking off the machine (a copied or backed-up file, a support bundle) and against casual reading. It is **not** protection against anything running as the same account on the same machine, which can derive the same key. We chose it anyway because the real alternatives each cost something here: DPAPI, the Keychain and libsecret are the strong answer but are three different APIs with no headless story on Linux and a wrapper script per system; a user-supplied master password needs typing at every scheduled Run. Those patterns stay supported and documented for anyone who needs more.

Three choices a reader might question:

- **A separate file, not the Upload State.** The Upload State is machine-wide, shared by a group, backed up before migrations, pruned, and documented as disposable ("losing it costs a full re-upload, not correctness"). A Secret Store is none of those. Per account matches how environment variables already work: one account, one set of Secrets.
- **AES-256-GCM, not Fernet.** Fernet is a Python format and nothing else reads this store. In .NET it would be hand-written AES-CBC plus HMAC; the BCL already provides authenticated encryption.
- **HKDF over PBKDF2 or a slow KDF.** The input is not a low-entropy password but a machine identifier that anyone with local access can read, so stretching it adds no protection. Honesty about the threat model matters more than a costlier-looking derivation.
