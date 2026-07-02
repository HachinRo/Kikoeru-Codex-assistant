# Neokikoeru `/fs/list` encryption scheme

**Class:** payload-encryption reference for any agent that needs to
call Neokikoeru v3.7.1's encrypted `POST /api/v1/fs/list` endpoint
(e.g. to build a custom file-list client that mimics the licensed
WebUI). Reverse-engineered from the JS bundle `fs-BdEOkugY.js` and
the Go binary's `neokikoeru/internal/server/handler.FsList` + `fsListReq`
struct on 2026-06-22.

**Don't reach for this unless you have a real reason to call
`/fs/list` directly.** The unencrypted `GET /api/v1/fs/download?file_id=X`
endpoint serves audio, and the unencrypted `GET /api/v1/work/RJ{id}`
returns metadata — together they cover 99% of use cases. The SQLite
DB at `~/Library/Application Support/neokikoeru/neokikoeru.db` is
the authoritative file list for any process with FS access. The
encrypted endpoint only matters if you're building a remote client
that needs the full file tree per work without DB access.

## Why the endpoint is encrypted

The Go server's `Handler.FsList` requires an encrypted request body
whose payload can only be verified as coming from a client that has
the public key. This is **not** a license-gate by itself — the
public key is hard-coded in the JS bundle (so any client has it) —
but the server's `valid()` method also checks
`license.Activated` and returns 400 if the license is inactive. So
encrypted + unlicensed = 400. Encrypted + licensed = 200 with the
file list.

The encryption is **client-side** (the public key is shipped in the
JS bundle, not generated per-session). The server's matching private
key is in `~/Library/Application Support/neokikoeru/neokikoeru.db`
or a config file alongside it — the `license` package handles the
RSA key pair.

## Public key (PEM, base64-decoded from `fs-BdEOkugY.js`)

```
-----BEGIN PUBLIC KEY-----
MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEAweVajaLmSXTH4tWAN3+E
kjbzdWldAQ38dyCR4Hpty38bYBKoZKWveY4/U+6qM6cE0b4lRJOO4mWYaF0vEsQw
MnJw8qn0m40N4QqnHQitcA+6YnyNdD4fUFzoc08X+OoJmOrUoX4hJbRX3cICXmyC
xLtG0KtlO5w9xJy4brkGxZjY2V3s18WbSVQ4ZMLXy4a2Ooz4K2HdTRUdZTxkII20
spOMFdoLsAX+FFp2Ekg0OMqgFlgmi7BtAfrTHv2kQJKNkE6gzC5oj59TAJMI8+36
smzvsslsmmh5bFDMtpHfHl5B+QCo+G/Q9kYpIRkvxsg7LJ8DQrFK8SoWQgU5Zwwd
cQIDAQAB
-----END PUBLIC KEY-----
```

## Wire format

Request: `POST /api/v1/fs/list`, `Authorization: Bearer <jwt>`, body
`{"params": "<b64>", "enc_key": "<b64>"}` where:

- `params` = base64( `IV(12) || ciphertext || auth_tag(16)` ) — the
  AES-256-GCM encryption of `JSON.stringify(payload)` with a 128-bit
  auth tag appended.
- `enc_key` = base64( RSA-OAEP-SHA256( AES_key ) ) — the AES key
  wrapped with the server's RSA public key.

`payload` (decrypted JSON) is an object like:

```json
{"work_id": "RJ01010222", "folder_path": "/RJ01010222", "refresh": false}
```

Field names from the Go struct (`fsListReq`):
- `work_id` (string, required)
- `folder_path` (string, required; use `"/" + work_id` for root)
- `refresh` (bool, optional; forces re-scan)
- `lastFileId` (string, optional; for cursor pagination of large folders)

## Python implementation (verified working)

```python
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives import serialization, hashes
from cryptography.hazmat.backends import default_backend
import base64, json, os

PUBKEY_PEM = b"""-----BEGIN PUBLIC KEY-----
MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEAweVajaLmSXTH4tWAN3+E
kjbzdWldAQ38dyCR4Hpty38bYBKoZKWveY4/U+6qM6cE0b4lRJOO4mWYaF0vEsQw
MnJw8qn0m40N4QqnHQitcA+6YnyNdD4fUFzoc08X+OoJmOrUoX4hJbRX3cICXmyC
xLtG0KtlO5w9xJy4brkGxZjY2V3s18WbSVQ4ZMLXy4a2Ooz4K2HdTRUdZTxkII20
spOMFdoLsAX+FFp2Ekg0OMqgFlgmi7BtAfrTHv2kQJKNkE6gzC5oj59TAJMI8+36
smzvsslsmmh5bFDMtpHfHl5B+QCo+G/Q9kYpIRkvxsg7LJ8DQrFK8SoWQgU5Zwwd
cQIDAQAB
-----END PUBLIC KEY-----"""

def encrypt_fs_list_payload(payload: dict) -> dict:
    pub = serialization.load_pem_public_key(PUBKEY_PEM, backend=default_backend())
    aes_key = os.urandom(32)
    iv = os.urandom(12)
    aesgcm = AESGCM(aes_key)
    pt = json.dumps(payload).encode()
    ct_with_tag = aesgcm.encrypt(iv, pt, None)  # ct || tag(16)
    params_bytes = iv + ct_with_tag
    enc_key = pub.encrypt(
        aes_key,
        padding.OAEP(
            mgf=padding.MGF1(algorithm=hashes.SHA256()),
            algorithm=hashes.SHA256(),
            label=None
        )
    )
    return {
        "params": base64.b64encode(params_bytes).decode(),
        "enc_key": base64.b64encode(enc_key).decode()
    }
```

The server's response (after successful decryption + license check) is:

```json
{
  "data": [
    {"id": "abc123", "name": "01_耳舐め.mp3", "size": 28201466,
     "duration": 1800.5, "is_folder": false, "path": "...",
     "parent_id": "xyz789", "work_id": "RJ01010222"},
    {"id": "xyz789", "name": "(mp3)_ストーリー", "is_folder": true, ...},
    ...
  ]
}
```

The `WorkFiles` component sorts folders first, then files alphabetically
(`n.is_folder && !r.is_folder ? -1 : !n.is_folder && r.is_folder ? 1 : qh.compare(n.name, r.name)`).

## JS implementation (for browser-based custom clients)

The bundle uses Web Crypto API (secure context) or `forge.js` (fallback):

```js
const PUBKEY_PEM = `-----BEGIN PUBLIC KEY-----\n...same as above...\n-----END PUBLIC KEY-----`;

async function encryptPayload(payload) {
  const pubKey = await crypto.subtle.importKey(
    "spki",
    pemToBuffer(PUBKEY_PEM),
    {name: "RSA-OAEP", hash: "SHA-256"},
    false, ["encrypt"]
  );
  const aesKey = await crypto.subtle.generateKey(
    {name: "AES-GCM", length: 256}, true, ["encrypt"]
  );
  const iv = crypto.getRandomValues(new Uint8Array(12));
  const pt = new TextEncoder().encode(JSON.stringify(payload));
  const ct = await crypto.subtle.encrypt({name: "AES-GCM", iv}, aesKey, pt);
  // ct is ct || tag(16)
  const paramsBytes = new Uint8Array(iv.length + ct.byteLength);
  paramsBytes.set(iv); paramsBytes.set(new Uint8Array(ct), iv.length);
  const rawAes = await crypto.subtle.exportKey("raw", aesKey);
  const wrapped = await crypto.subtle.encrypt({name: "RSA-OAEP"}, pubKey, rawAes);
  return {
    params: btoa(String.fromCharCode(...paramsBytes)),
    enc_key: btoa(String.fromCharCode(...new Uint8Array(wrapped)))
  };
}
```

## Server response shape (when license is active)

```json
{
  "data": [
    {
      "id": "abc123...",         // file_id, used in /fs/download?file_id=...
      "name": "01_耳舐め.mp3",
      "size": 28201466,
      "duration": 1800.5,        // seconds, may be 0 if not yet probed
      "is_folder": false,
      "path": "/RJ01010222/(mp3)_ストーリー/01_耳舐め.mp3",
      "parent_id": "xyz789...",
      "work_id": "RJ01010222"
    }
  ]
}
```

The `fsListReq.valid()` method on the Go side checks `work_id` and
`folder_path` are non-empty and that the caller is authenticated
(JWT). The license check is in the handler itself, not in `valid()`.

## Pitfalls observed

- **Tag length must be 128 bits.** Web Crypto's `subtle.encrypt` for
  AES-GCM defaults to 128; Python's `AESGCM.encrypt` is also 128.
  forge.js's `At.cipher.createCipher("AES-GCM", key)` requires
  `tagLength: 128` in the `start()` call or the auth tag is missing.
- **No tag in the `params` base64 if the cipher library doesn't append
  it.** forge.js puts the tag in `r.mode.tag` separately and appends
  it manually. Python's `AESGCM.encrypt` returns `ct || tag` already
  concatenated. Web Crypto's `subtle.encrypt` does the same.
- **`enc_key` is the raw 32-byte AES key, not a derived key.** Don't
  pass it through KDF or hash it before RSA-wrapping.
- **The `folder_path` separator is `/`.** Subfolder names contain
  Japanese characters and parentheses — URL-encode them when testing
  via curl, or use the unencrypted API.
- **Empty `data: []` is a valid response** (means folder exists but
  has no indexed children). Don't treat it as an error.
- **Server returns 400 even with correct encryption when license is
  inactive.** The 400 doesn't say "license required" — it just says
  `{"message":"Bad Request"}`. To distinguish license-gate from
  format-gate, check `/sysinfo` first.

## Why this is a `references/` doc, not a class-level skill

This is one specific server's encrypted API scheme. It changes
between Neokikoeru versions and is not a generalizable pattern.
General encryption knowledge (RSA-OAEP, AES-GCM, MGF1) belongs in
general-purpose skills; this doc captures only what's needed to
talk to *this* server.
