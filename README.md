# Face-ID For Tibo

## Purpose

Face-ID is the perception layer that lets Tibo immediately recognize who is
physically in front of its PTZ camera. It is not primarily an attendance
system. Identity should give Tibo social awareness, correct forms of address,
and a reliable authorization signal for sensitive commands.

Primary interaction:

> "Tibo chao anh Ai di."

Expected behavior:

1. Resolve `Anh Ai` to `person_ai` and the `seat_ai` spatial anchor.
2. Move the A42 PTZ to the stored seat angle: pan `42.0`, tilt `14.5`.
3. Wait for the camera to settle, capture a current go2rtc frame, and run
   face recognition.
4. Only greet if the face match confirms Anh Ai.
5. If the seat is empty, occupied by someone else, or the match is uncertain,
   report that fact instead of greeting an empty chair or misidentifying a
   person.

When speaker output is enabled, a successful greeting should be short and
natural, for example: "Em chao anh Ai. Chuc anh lam viec vui ve a."

## Desired Capabilities

- Identify all known faces visible in the current A42 frame.
- Answer "Ai dang truoc mat em?" with a name, score, and `unknown` state.
- Verify the intended person after PTZ moves to a known seat.
- Pass the confirmed identity into voice conversations rather than assuming
  every speaker is Anh Lam.
- Update the spatial presence model only after sufficient confidence.
- Enforce Master-only actions with confirmed identity, not a hardcoded default.

## Existing Tibo Assets

### Camera and spatial model

- PTZ camera: IMOU Ranger 2 / IPC-A42-L.
- Current A42 image source: go2rtc frame endpoint, exposed by StationWatch as
  `GET /api/camera/frame` in `backend/main.py`.
- PTZ actions: `POST /api/camera/goto_angle`.
- Spatial profiles and presence data live in the external spatial SQLite model
  used by `onvif-ptz-control`.
- Person profiles already have a `face_gallery` field.
- Seat anchors documented in the existing spatial system:

| Person | Person ID | Seat | Pan | Tilt |
| --- | --- | --- | ---: | ---: |
| Vo Thanh Lam | `person_lam` | `seat_lam` | 114.4 | 5.9 |
| Vinh | `person_vinh` | `seat_vinh` | 32.0 | 14.5 |
| Ai | `person_ai` | `seat_ai` | 42.0 | 14.5 |
| Thanh | `person_thanh` | `seat_thanh` | 54.0 | 14.5 |

### Tibo modules to integrate

- `backend/agent/listener_worker.py`: point to identify the person who spoke
  after a wake word is detected.
- `backend/agent/robot_brain.py`: receives confirmed identity and produces the
  appropriate personalized answer.
- `backend/agent/master_verifier.py`: must replace its current permissive
  behavior with actual face-backed authorization.
- `backend/agent/tools/perception_tools.py`: add tools for current-frame face
  identification and look-at-person-and-verify.
- `web/src/components/VideoPTZPanel.tsx`: add an operator-triggered "Ai dang
  truoc mat?" action and an identity overlay on the live frame.

## Face-ID Model & Architecture

Face recognition is built directly from the official **NOVA Dataset** (`face/gallery/NOVA/`):

Pipeline:

```text
YOLOv8n-face + ByteTrack -> InsightFace buffalo_l / ArcFace -> 512D embedding
-> cosine similarity against known face embeddings
```

Important: do not mix embeddings generated from different preprocessing
pipelines. The enrollment gallery and runtime recognition must use the same
chosen pipeline.

## Official Gallery Dataset (NOVA)

The gallery dataset has been imported and structured under `face/gallery/NOVA/`:

1. **Technology Center (Core Scope)**:
   - Path: `face/gallery/NOVA/technology-center-org-chart/photos/`
   - Total photos: 77 members (including Lam, Ai, Vinh, Thanh, Chinh, Trang, etc.)
   - Metadata: `org-chart.json` with Vietnamese full names, roles, and hierarchy.

2. **Organization-wide (Extended Scope)**:
   - Path: `face/gallery/NOVA/organization-org-chart/photos/`
   - Total photos: 2,491 members across the group.
   - Metadata: `active-directory.json`, `unit-manifest.json`.

## Integration Design

### Phase 1: on-demand recognition

Implement a narrow local recognition API, for example:

```text
POST /api/face/identify-current-frame
-> {
     "faces": [
       {
         "person_id": "person_ai",
         "name": "Anh Ai",
         "score": 0.78,
         "bbox": [x1, y1, x2, y2],
         "status": "confirmed"
       }
     ]
   }
```

This endpoint should fetch the current go2rtc JPEG internally. It must be
read-only: no attendance writes, no automatic creation of unknown-face groups.

Recognition result policy:

- `confirmed`: score meets the operational threshold and is sufficiently ahead
  of the runner-up candidate.
- `uncertain`: face exists but score/margin is insufficient; do not speak the
  candidate name as fact.
- `unknown`: a usable face has no known match.
- `no_face`: no usable face is present in the frame.

### Phase 2: social PTZ action

Add a compound tool along these lines:

```text
look_at_person_and_verify(person_id)
  -> resolve anchor
  -> PTZ goto pan/tilt
  -> wait for settling
  -> identify current frame
  -> return expected-person verification result
```

The Brain should call this before responding to requests to greet, find, or
address a named person. TTS happens only after the tool confirms the target.

### Phase 3: voice identity and presence

- After a wake word, recognize the current person before calling the Brain.
- Pass the actual `person_id` and display name to the conversation session.
- Require a confirmed `person_lam` match for Master-only operations.
- Use temporal smoothing (multiple consistent frames) before updating
  `daily_presence` or treating a person as present.

## Current Gaps To Fix

- `backend/agent/master_verifier.py` currently grants access unconditionally.
- `backend/agent/listener_worker.py` currently passes `user_name="Anh Lam"`
  for every voice interaction.
- The current StationWatch runtime in `backend/main.py` still uses the older
  `onvif-ptz-control` spatial agent directly, while the newer independent
  Tibo agent modules exist alongside it. Reconcile this before wiring Face-ID
  into production flow.
- `face.besen.vn` is unavailable: its TLS certificate expired on 2026-08-26
  and its reverse proxy returned HTTP 502 during verification. Its local
  source and model assets remain usable at `/home/leco/hr-face-id`.
- StationWatch needs authentication, session-scoped WebSocket events, and
  tighter CORS before exposing face identity data beyond a trusted local
  network.

## Next Implementation Steps

1. Extract and index embeddings from `face/gallery/NOVA/` using InsightFace buffalo_l.
2. Implement on-demand current-frame recognition endpoint with result overlays.
3. Implement `look_at_person_and_verify` and the greet-person behavior.
4. Calibrate thresholds with real A42 frames at each seat.
5. Connect verified identity to voice sessions and Master authorization.
