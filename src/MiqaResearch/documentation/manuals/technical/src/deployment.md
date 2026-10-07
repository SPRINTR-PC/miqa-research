(heading-deployment)=
# Deployment requirements

What the browser-facing edge and the static server must do for the DICOM viewer. The viewer
loads a series as one `/metadata` request plus one `/frames` request per image from the
DICOMweb (WADO-RS) root `/api/v1/dicom`: a 500-slice CT is about 500 requests. The app itself
needs no change for any of this.

(heading-deployment-http2)=
## TLS and HTTP/2 at the edge

- The browser-facing edge (a load balancer, or the Kubernetes ingress) terminates TLS and
  speaks **HTTP/2** to browsers. Over HTTP/1.1 the browser opens at most six connections per
  host, so frame requests queue and first render is several times slower.
- Granian stays on **HTTP/1.1** (plain HTTP on port 8000) behind the edge. Don't enable HTTP/2
  between the edge and Granian.
- Use **upstream keep-alive** from the edge to Granian, so frame requests reuse connections
  instead of opening one each.
- The viewer warns in the browser console when `/frames` come over HTTP/1.1
  (`nextHopProtocol` is `http/1.1`). That warning on a deployment means the edge isn't
  speaking HTTP/2.

(heading-deployment-headers)=
## Headers and caching

- Pass `Cache-Control`, `ETag`, `Vary` and `Clear-Site-Data` through **unchanged**. The app
  sets them on purpose:
  - `/frames`: `private, max-age=31536000, immutable`, a strong `ETag` and `Vary: Accept`.
    The browser keeps frames for good.
  - `/metadata`: `private, no-cache` and an `ETag`. The browser revalidates every time and
    gets a `304` when nothing changed.
  - Logout and session expiry send `Clear-Site-Data: "cache"`, which empties the browser cache
    of participant data.
- **No proxy cache on `/api/v1/dicom`** (the DICOMweb root). Every response is `private`
  and checked per user. A shared cache would hand one user's participant data to another.
- Don't compress `/frames` at the edge. Frames are compressed pixel data or raw pixels in a
  multipart body. Gzip costs CPU and changes the bytes the `ETag` describes.

(heading-deployment-static)=
## Static files

The viewer bundle is built in the image's `viewer` stage into `static/js/viewer/`. Whatever
serves `/static/` must:

- serve `.wasm` files as **`application/wasm`**. The image codecs are WebAssembly, and browsers
  refuse to compile them as streaming WebAssembly under any other type. Django's static view
  does this. On nginx, check that `mime.types` has `application/wasm wasm;`.
- If a Content Security Policy is added, it needs `'wasm-unsafe-eval'` in `script-src` and
  `worker-src 'self'` (the codecs decode in Web Workers).

(heading-deployment-ingress-nginx)=
## Example: Kubernetes ingress-nginx

ingress-nginx speaks HTTP/2 to browsers whenever TLS is on (`use-http2` is on by default) and
keeps upstream connections alive. It doesn't cache unless you configure a proxy cache, so
don't add one.

```yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: miqa-research
  # No annotations or snippets that add a proxy cache or rewrite response headers.
spec:
  ingressClassName: nginx
  tls:
    - hosts: [miqa.example.org]
      secretName: miqa-research-tls
  rules:
    - host: miqa.example.org
      http:
        paths:
          - path: /
            pathType: Prefix
            backend:
              service:
                name: miqa-research
                port:
                  number: 8000
```

In the controller's ConfigMap, keep `use-http2: "true"` (the default) and
`upstream-keepalive-connections` above zero (default `320`).

(heading-deployment-nginx)=
## Example: nginx load balancer

```nginx
upstream miqa_research {
    server 10.0.0.10:8000;
    server 10.0.0.11:8000;
    keepalive 64;                      # upstream keep-alive
}

server {
    listen 443 ssl;
    http2 on;                          # nginx >= 1.25.1; older: "listen 443 ssl http2;"
    server_name miqa.example.org;

    ssl_certificate     /etc/nginx/tls/miqa.crt;
    ssl_certificate_key /etc/nginx/tls/miqa.key;

    location / {
        proxy_pass http://miqa_research;
        proxy_http_version 1.1;        # HTTP/1.1 to Granian, needed for keep-alive
        proxy_set_header Connection "";
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $remote_addr;
        proxy_set_header X-Forwarded-Proto $scheme;
        # No proxy_cache, no proxy_hide_header / add_header for Cache-Control, ETag,
        # Vary or Clear-Site-Data: they pass through unchanged.
    }

    location /api/v1/dicom/ {
        proxy_pass http://miqa_research;
        proxy_http_version 1.1;
        proxy_set_header Connection "";
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $remote_addr;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_cache off;               # never cache participant data
        gzip off;
    }
}
```

(heading-deployment-check)=
## Checking a deployment

The edge must answer over HTTP/2, and the app's headers must arrive unchanged:

```sh
curl -sI --http2 https://miqa.example.org/accounts/login/ | head -1
# HTTP/2 200
```

The first line must say `HTTP/2`. To check a frame's headers, sign in in a browser and copy
the `sessionid` cookie:

```sh
curl -sI --http2 -H 'Cookie: sessionid=<id>' \
  -H 'Accept: multipart/related; type="application/octet-stream"; transfer-syntax=*' \
  https://miqa.example.org/api/v1/dicom/studies/<study>/series/<series>/instances/<sop>/frames/1
```

Expect `HTTP/2 200`, `cache-control: private, max-age=31536000, immutable`, an `etag` and
`vary: Accept`, and no `age` or `x-cache` header from a proxy cache.

(heading-deployment-first-render)=
## First-render targets

Acceptance-test values for each deployment, for a **500-slice CT** on the deployment network,
with a signed-in session and an empty browser cache:

| Stage | Target |
|---|---|
| First image | ≤ 1 s |
| Coarse MPR (interleaved stage done) | ≤ 2 s |
| Full volume loaded | ≤ 10 s |

The viewer measures them with `performance.mark`s (`mires-viewer:open`,
`mires-viewer:first-image`, `mires-viewer:interleaved`, `mires-viewer:volume-loaded`), shown
in the browser's Performance panel. When a series closes, it sends them to
`POST /api/v1/viewer/first-render`, which logs one record (`viewer first render` on the
`MiqaResearch.telemetry.viewer` logger) with these attributes:

| Attribute | Meaning |
|---|---|
| `viewer.first_image_ms` | open → first image, in ms |
| `viewer.interleaved_ms` | open → interleaved stage done, in ms |
| `viewer.volume_loaded_ms` | open → volume loaded, in ms |
| `viewer.slices` | images in the series |
| `viewer.bytes` | bytes of the series' `/frames` responses received by then |
| `viewer.transfer_syntax` | the series' Transfer Syntax UID |

Stages not reached (a stack view has no volume) are left out. The endpoint refuses any other
field with `422`, so UIDs and participant data never reach telemetry. With
`MIRES_OTLP_ENABLED` on, the record goes to the OTLP collector (see
[Logging](#heading-configuration-logging)).
