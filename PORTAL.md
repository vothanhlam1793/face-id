# NOVA People & Image Quality Portal

Current implemented scope: personnel directory, create/edit personnel records,
API lookup by name/employee code, face detection and image quality assessment.
No face-to-identity matching or embeddings. The earlier README is a historical
proposal; this document describes the running application.

## Run

```bash
python3 -m pip install -r requirements.txt
npm --prefix web ci
npm --prefix web run build
bash run.sh
```

Default port: 8020. Override with HOST / PORT environment variables.
One FastAPI process serves both the compiled React frontend and API.
Swagger documentation: `/docs`. Health: `/api/v1/health`.

## Data

On first startup, import the NOVA active-directory snapshot into
`data/portal.sqlite3`. Future restarts preserve manual additions and edits.
The source JSON and original photos are never modified. The import contains
4,592 distinct source person IDs; 2,491 records have existing local photos.
Missing referenced images are not represented as available photos.
All employment records are retained in API results; displayed employment uses
the main assignment where available. The additional technology-center dataset
is not automatically merged because ambiguous identities require review.

Personnel creation requires a non-empty name and employee code; duplicate codes
are rejected. Searches are accent-insensitive. API results are paginated.
Image quality uploads are limited to 10 MB and 20 MP. The latest 100 successful
analysis cases (including images with no detected faces) are persisted in SQLite.
Original image bytes and immutable analysis results are stored together; inserting
case 101 deletes the oldest row and its image atomically. SQLite reuses freed
pages, so the database file need not shrink immediately. Invalid uploads do not
create cases. History offers image/box previews, review status, notes and manual
deletion. All history endpoints require authentication. Review edits do not change
the original analysis or retention order. Earlier uploads cannot be recovered.
Metrics are heuristic, not confidence probabilities. OpenCV Haar runs on CPU
and may miss profile, tiny or occluded faces. No GPU is required.

UI follows GTD Web v2 tokens: navy shell, slate canvas, teal actions; React,
Vite, Tailwind and Lucide. Native dialog provides focus trapping and Escape.

Public portal: https://novaface.nvlit.asia (SVR12 nginx -> 10.7.0.21:8020).
All routes require HTTP Basic authentication, including photos and Swagger.
The browser displays its native username/password prompt. Admin credentials
are stored as a salted scrypt hash in ignored `data/admin-auth.json` (mode 0600).
Use `python3 set_admin.py` to change the password interactively.
Use HTTPS for access. API clients use the standard Authorization Basic header.
The service listens on the private VPN address under systemd `novaface.service`,
enabled at boot with automatic restart on failure. Manage with:
`sudo systemctl restart novaface` / `sudo journalctl -u novaface`.
TLS is managed by Certbot on SVR12, initially valid until 2026-12-23.

## Tests

`python3 -m unittest test_portal.py` uses an isolated temporary SQLite database.

## Remaining improvements

- Add/update profile photos in the portal.
- CSV batch import with preview and duplicate resolution.
- A session-based login/logout UI (current login uses the browser prompt).
- Benchmark concurrent load and validate detector quality on representative images.

## Camera capture

Open the image-quality tab to use a live webcam/mobile camera, switch preferred
front/back camera, capture and preview, then explicitly submit for assessment.
Camera access requires HTTPS and browser permission. Tracks stop when leaving
the tab, hiding the page, closing the camera or taking a photo. A separate mobile
capture input opens the native camera/file picker depending on the browser.
The captured image is never submitted until the user confirms.
