# Web Bootstrap decisions

- FastAPI was chosen as the minimal server entrypoint, with a single `GET /` route.

- Jinja2 renders the HTML directly, keeping the first web interface server-side and read-only.

- PicoCSS is loaded from CDN to keep styling minimal without adding local asset tooling.

- HTMX is included from CDN to align with the frontend direction, even though the first page is static.

- A small application service provides dashboard data so FastAPI does not query the repository directly.
