"""NOVA directory, image quality & face recognition portal."""
import io
import json
import os
import sqlite3
import time
import unicodedata
import uuid
import secrets
import base64
import hashlib
import hmac
import threading
from pathlib import Path
from contextlib import asynccontextmanager
from typing import Optional

import cv2
import numpy as np
from PIL import Image, ImageOps, UnidentifiedImageError
from fastapi import FastAPI, HTTPException, UploadFile, Query, Request
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parent
DATA = ROOT / 'data'
_default_gallery = ROOT / 'gallery/NOVA/organization-org-chart'
if not _default_gallery.exists() and Path('/home/leco/speaker/face/gallery/NOVA/organization-org-chart').exists():
    _default_gallery = Path('/home/leco/speaker/face/gallery/NOVA/organization-org-chart')
GALLERY = Path(os.getenv('GALLERY_DIR', _default_gallery))
MODELS = ROOT / 'models'
DB = DATA / 'portal.sqlite3'

YUNET_PATH = MODELS / 'face_detection_yunet_2023mar.onnx'
SFACE_PATH = MODELS / 'face_recognition_sface_2021dec.onnx'
AUTH_FILE = DATA / 'admin-auth.json'

def hash_password(password: str, salt: bytes = None) -> tuple[str, str]:
    if salt is None:
        salt = os.urandom(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=16384, r=8, p=1).hex()
    return salt.hex(), digest

def verify_user_password(username: str, password: str) -> Optional[dict]:
    # 1. If admin, check AUTH_FILE first
    if username == 'admin' and AUTH_FILE.exists():
        try:
            config = json.loads(AUTH_FILE.read_text())
            digest = hashlib.scrypt(password.encode(), salt=bytes.fromhex(config['salt']), n=16384, r=8, p=1).hex()
            if hmac.compare_digest(digest, config['hash']):
                return {"username": "admin", "role": "admin"}
        except Exception:
            pass

    # 2. Check app_users table
    try:
        with connect() as db:
            row = db.execute("SELECT username, role, salt, hash FROM app_users WHERE username = ?", (username,)).fetchone()
            if row:
                salt_bytes = bytes.fromhex(row['salt'])
                digest = hashlib.scrypt(password.encode(), salt=salt_bytes, n=16384, r=8, p=1).hex()
                if hmac.compare_digest(digest, row['hash']):
                    return {"username": row['username'], "role": row['role']}
    except Exception:
        pass

    return None

def update_user_password(username: str, password: str):
    salt_hex, digest = hash_password(password)
    now = time.time()
    role = 'admin' if username == 'admin' else 'user'
    with connect() as db:
        db.execute("""
            INSERT INTO app_users (username, role, salt, hash, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(username) DO UPDATE SET salt=excluded.salt, hash=excluded.hash, updated_at=excluded.updated_at
        """, (username, role, salt_hex, digest, now, now))
    if username == 'admin':
        data = {'username': 'admin', 'salt': salt_hex, 'hash': digest}
        DATA.mkdir(exist_ok=True)
        try:
            fd = os.open(AUTH_FILE, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(fd, 'w') as f:
                json.dump(data, f)
            os.chmod(AUTH_FILE, 0o600)
        except Exception:
            pass

class EmbeddingIndex:
    def __init__(self):
        self.lock = threading.Lock()
        self.ids = []
        self.matrix = None  # (N, 128) float32
        self.people = {}    # id -> dict

    def load(self, db_conn):
        with self.lock:
            try:
                rows = db_conn.execute("""
                    SELECT p.id, p.name, p.employee_id, p.title, p.department, p.division, p.photo, f.embedding
                    FROM people p JOIN face_embeddings f ON p.id = f.person_id
                """).fetchall()
                self.ids = [r[0] for r in rows]
                self.people = {
                    r[0]: {
                        'id': r[0],
                        'name': r[1],
                        'employee_id': r[2],
                        'title': r[3],
                        'department': r[4],
                        'division': r[5],
                        'photo_url': f"/api/v1/persons/{r[0]}/photo" if r[6] else None
                    } for r in rows
                }
                if rows:
                    self.matrix = np.vstack([np.frombuffer(r[7], dtype=np.float32) for r in rows])
                else:
                    self.matrix = None
            except Exception:
                self.ids = []
                self.matrix = None
                self.people = {}

    def search(self, feature: np.ndarray, top_k: int = 3, min_score: float = 0.36):
        with self.lock:
            if self.matrix is None or len(self.ids) == 0:
                return []
            feat = feature.flatten().astype(np.float32)
            norm = np.linalg.norm(feat)
            if norm > 1e-6:
                feat = feat / norm
            scores = np.dot(self.matrix, feat)
            top_indices = np.argsort(scores)[::-1][:top_k]
            results = []
            for idx in top_indices:
                score = float(scores[idx])
                if score < min_score:
                    continue
                pid = self.ids[idx]
                pdata = self.people.get(pid, {'id': pid})
                results.append({
                    **pdata,
                    'similarity': round(score, 4),
                    'confidence': round(score * 100, 1)
                })
            return results

EMBEDDINGS_INDEX = EmbeddingIndex()

def fold(text):
    return ''.join(c for c in unicodedata.normalize('NFD', text.lower().replace('đ', 'd')) if unicodedata.category(c) != 'Mn')

def connect():
    db = sqlite3.connect(DB, timeout=10)
    db.row_factory = sqlite3.Row
    return db

def sync_embeddings_background():
    """Background task to extract and cache face embeddings for all personnel photos."""
    if not SFACE_PATH.is_file() or not YUNET_PATH.is_file():
        return
    if 'test' in str(DB).lower() or 'tmp' in str(DB).lower():
        return
    try:
        with connect() as db:
            rows = db.execute("SELECT id, photo FROM people WHERE photo IS NOT NULL").fetchall()
            indexed = set(r[0] for r in db.execute("SELECT person_id FROM face_embeddings").fetchall())
            missing = [r for r in rows if r['id'] not in indexed]
            if not missing:
                EMBEDDINGS_INDEX.load(db)
                return

        detector = cv2.FaceDetectorYN.create(str(YUNET_PATH), '', (320, 320), 0.6, 0.3)
        recognizer = cv2.FaceRecognizerSF.create(str(SFACE_PATH), '')
        now_iso = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())

        for r in missing:
            p_path = (GALLERY / r['photo']).resolve()
            if not p_path.is_file():
                continue
            bgr = cv2.imread(str(p_path))
            if bgr is None:
                continue
            h, w, _ = bgr.shape
            detector.setInputSize((w, h))
            _, faces = detector.detect(bgr)
            if faces is not None and len(faces) > 0:
                aligned = recognizer.alignCrop(bgr, faces[0])
                feat = recognizer.feature(aligned)
                norm = np.linalg.norm(feat)
                if norm > 1e-6:
                    feat /= norm
                with connect() as db:
                    db.execute("INSERT OR REPLACE INTO face_embeddings VALUES (?,?,?)",
                               (r['id'], feat.tobytes(), now_iso))
        with connect() as db:
            EMBEDDINGS_INDEX.load(db)
    except Exception:
        pass

def initialize():
    DATA.mkdir(exist_ok=True)
    with connect() as db:
        db.execute('PRAGMA journal_mode=WAL')
        db.execute('CREATE TABLE IF NOT EXISTS scan_cases (seq INTEGER PRIMARY KEY AUTOINCREMENT, id TEXT UNIQUE NOT NULL, created_at TEXT NOT NULL, image BLOB NOT NULL, result TEXT NOT NULL, status TEXT NOT NULL DEFAULT "unreviewed", note TEXT NOT NULL DEFAULT "")')
        db.execute('CREATE TABLE IF NOT EXISTS people (id TEXT PRIMARY KEY, name TEXT NOT NULL, employee_id TEXT, title TEXT, department TEXT, division TEXT, photo TEXT, source TEXT, updated_at TEXT, search TEXT, employments TEXT)')
        db.execute('CREATE TABLE IF NOT EXISTS face_embeddings (person_id TEXT PRIMARY KEY, embedding BLOB NOT NULL, updated_at TEXT NOT NULL)')
        db.execute('CREATE TABLE IF NOT EXISTS app_users (username TEXT PRIMARY KEY, role TEXT NOT NULL, salt TEXT NOT NULL, hash TEXT NOT NULL, created_at REAL NOT NULL, updated_at REAL NOT NULL)')
        db.execute('CREATE TABLE IF NOT EXISTS auth_sessions (session_id TEXT PRIMARY KEY, username TEXT NOT NULL, role TEXT NOT NULL DEFAULT "user", created_at REAL NOT NULL, expires_at REAL NOT NULL)')
        # Ensure role column exists if auth_sessions was created earlier
        cols = [c[1] for c in db.execute('PRAGMA table_info(auth_sessions)').fetchall()]
        if 'role' not in cols:
            db.execute('ALTER TABLE auth_sessions ADD COLUMN role TEXT NOT NULL DEFAULT "user"')
        db.execute('CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT)')

        # Seed default admin if not exists
        if not db.execute("SELECT 1 FROM app_users WHERE username='admin'").fetchone():
            if AUTH_FILE.exists():
                try:
                    c = json.loads(AUTH_FILE.read_text())
                    now = time.time()
                    db.execute("INSERT INTO app_users VALUES ('admin', 'admin', ?, ?, ?, ?)", (c['salt'], c['hash'], now, now))
                except Exception:
                    salt_hex, digest = hash_password('admin123')
                    now = time.time()
                    db.execute("INSERT INTO app_users VALUES ('admin', 'admin', ?, ?, ?, ?)", (salt_hex, digest, now, now))
            else:
                salt_hex, digest = hash_password('admin123')
                now = time.time()
                db.execute("INSERT INTO app_users VALUES ('admin', 'admin', ?, ?, ?, ?)", (salt_hex, digest, now, now))
                data = {'username': 'admin', 'salt': salt_hex, 'hash': digest}
                DATA.mkdir(exist_ok=True)
                try:
                    fd = os.open(AUTH_FILE, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
                    with os.fdopen(fd, 'w') as f:
                        json.dump(data, f)
                    os.chmod(AUTH_FILE, 0o600)
                except Exception:
                    pass

        # Seed default normal user if not exists
        if not db.execute("SELECT 1 FROM app_users WHERE username='user'").fetchone():
            salt_hex, digest = hash_password('user123')
            now = time.time()
            db.execute("INSERT INTO app_users VALUES ('user', 'user', ?, ?, ?, ?)", (salt_hex, digest, now, now))

        if not db.execute("SELECT 1 FROM meta WHERE key='imported'").fetchone():
            ad_json_file = GALLERY / 'active-directory.json'
            if ad_json_file.is_file():
                source = json.loads(ad_json_file.read_text())
                for person in source['people']:
                    jobs = person.get('employments', [])
                    job = next((j for j in jobs if j.get('assignmentId') == person.get('mainAssignmentId')), jobs[0] if jobs else {})
                    photo = next((j['photoPath'] for j in jobs if j.get('photoPath') and (GALLERY / j['photoPath']).is_file()), None)
                    values = [person['personId'], person['name'], job.get('employeeId') or '', job.get('title') or '', job.get('department') or '', job.get('division') or '', photo, 'NOVA / SAP snapshot', source['capturedAt']]
                    db.execute('INSERT OR IGNORE INTO people VALUES (?,?,?,?,?,?,?,?,?,?,?)', (*values, fold(' '.join(str(v or '') for v in values[:6])), json.dumps(jobs, ensure_ascii=False)))
                db.execute("INSERT INTO meta VALUES ('imported', ?)", (source['capturedAt'],))
            else:
                db.execute("INSERT INTO meta VALUES ('imported', ?)", (time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),))
        EMBEDDINGS_INDEX.load(db)

    # Start background sync if any embeddings are missing
    threading.Thread(target=sync_embeddings_background, daemon=True).start()

def get_session_user(request: Request) -> Optional[dict]:
    # 1. Check session cookie
    session_id = request.cookies.get("novaface_session")
    auth_hdr = request.headers.get("authorization", "").strip()

    # 2. Check Bearer token
    if not session_id and auth_hdr.lower().startswith("bearer "):
        session_id = auth_hdr.split(" ", 1)[1].strip()

    if session_id:
        try:
            with connect() as db:
                row = db.execute(
                    "SELECT username, role FROM auth_sessions WHERE session_id = ? AND expires_at > ?",
                    (session_id, time.time())
                ).fetchone()
                if row:
                    return {"username": row[0], "role": row[1]}
        except Exception:
            pass

    # 3. Check Basic Auth (for curl / API clients)
    if auth_hdr.lower().startswith("basic "):
        try:
            encoded = auth_hdr.split(" ", 1)[1].strip()
            user, pwd = base64.b64decode(encoded).decode().split(":", 1)
            verified = verify_user_password(user, pwd)
            if verified:
                return verified
        except Exception:
            pass

    return None

def require_admin(request: Request) -> dict:
    user = get_session_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Vui lòng đăng nhập")
    if user.get('role') != 'admin':
        raise HTTPException(status_code=403, detail="Chỉ quản trị viên (admin) mới có quyền truy cập danh bạ nhân sự")
    return user

@asynccontextmanager
async def lifespan(app):
    initialize()
    yield

app = FastAPI(title='NOVA People, Image Quality & Face Recognition', version='1.0.0', lifespan=lifespan)

PUBLIC_EXACT_PATHS = {
    "/", "/index.html", "/favicon.ico",
    "/api/v1/health", "/api/v1/auth/login", "/api/v1/auth/me"
}

@app.middleware('http')
async def authenticate(request: Request, call_next):
    path = request.url.path
    # Public assets & endpoints that can be reached without login
    is_public = (
        path in PUBLIC_EXACT_PATHS or
        path.startswith("/assets/") or
        path.startswith("/docs") or
        path.startswith("/openapi.json")
    )

    if not is_public:
        user = get_session_user(request)
        if not user:
            return Response(
                content=json.dumps({"detail": "Vui lòng đăng nhập"}),
                status_code=401,
                media_type="application/json",
                headers={
                    'Cache-Control': 'no-store',
                    'X-Content-Type-Options': 'nosniff',
                    'X-Frame-Options': 'DENY'
                }
            )

    response = await call_next(request)
    response.headers['Cache-Control'] = 'no-store'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'DENY'
    return response

class LoginInput(BaseModel):
    username: str
    password: str

class ChangePasswordInput(BaseModel):
    old_password: str
    new_password: str = Field(min_length=4, max_length=200)

@app.post('/api/v1/auth/login')
def auth_login(body: LoginInput, response: Response):
    user_info = verify_user_password(body.username.strip(), body.password)
    if not user_info:
        raise HTTPException(status_code=401, detail="Tên đăng nhập hoặc mật khẩu không chính xác")
    
    session_id = secrets.token_urlsafe(32)
    now = time.time()
    expires_at = now + 7 * 86400  # 7 days
    
    with connect() as db:
        db.execute("INSERT INTO auth_sessions (session_id, username, role, created_at, expires_at) VALUES (?,?,?,?,?)",
                   (session_id, user_info['username'], user_info['role'], now, expires_at))
    
    response.set_cookie(
        key="novaface_session",
        value=session_id,
        max_age=int(7 * 86400),
        httponly=True,
        samesite="lax",
        path="/"
    )
    return {
        "status": "ok",
        "user": user_info,
        "session_id": session_id,
        "expires_at": expires_at
    }

@app.post('/api/v1/auth/logout')
def auth_logout(request: Request, response: Response):
    session_id = request.cookies.get("novaface_session")
    auth_hdr = request.headers.get("authorization", "")
    if not session_id and auth_hdr.lower().startswith("bearer "):
        session_id = auth_hdr.split(" ", 1)[1].strip()
    
    if session_id:
        try:
            with connect() as db:
                db.execute("DELETE FROM auth_sessions WHERE session_id = ?", (session_id,))
        except Exception:
            pass
    
    response.delete_cookie(key="novaface_session", path="/")
    return {"status": "ok"}

@app.get('/api/v1/auth/me')
def auth_me(request: Request):
    user = get_session_user(request)
    if user:
        return {"authenticated": True, "user": user}
    return {"authenticated": False}

@app.post('/api/v1/auth/change-password')
def auth_change_password(request: Request, body: ChangePasswordInput):
    user = get_session_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Chưa đăng nhập")
    verified = verify_user_password(user['username'], body.old_password)
    if not verified:
        raise HTTPException(status_code=400, detail="Mật khẩu hiện tại không chính xác")
    update_user_password(user['username'], body.new_password)
    return {"status": "ok", "message": "Đã đổi mật khẩu thành công"}

def output(row):
    d = dict(row)
    d.pop('search', None)
    d['photo_url'] = f"/api/v1/persons/{d['id']}/photo" if d.pop('photo') else None
    d['employments'] = json.loads(d['employments'])
    return d

@app.get('/api/v1/health')
def health():
    with connect() as db:
        total, photos = db.execute('SELECT count(*),count(photo) FROM people').fetchone()
        imported = db.execute("SELECT value FROM meta WHERE key='imported'").fetchone()[0]
        try:
            indexed = db.execute("SELECT count(*) FROM face_embeddings").fetchone()[0]
        except Exception:
            indexed = 0
    detector_name = 'OpenCV YuNet (CPU)' if YUNET_PATH.is_file() else 'OpenCV Haar frontalface (fallback)'
    return dict(
        status='ok',
        persons=total,
        persons_with_photo=photos,
        indexed_embeddings=indexed,
        source_snapshot=imported,
        detector=detector_name,
        recognizer='OpenCV SFace 128-d (CPU)' if SFACE_PATH.is_file() else 'Disabled',
        identity_matching=bool(SFACE_PATH.is_file())
    )

@app.get('/api/v1/persons')
def persons(request: Request, q: str = Query('', max_length=200), offset: int = Query(0, ge=0), limit: int = Query(24, ge=1, le=100)):
    require_admin(request)
    query = '%' + fold(q).replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_') + '%'
    with connect() as db:
        total = db.execute("SELECT count(*) FROM people WHERE search LIKE ? ESCAPE '\\'", (query,)).fetchone()[0]
        rows = db.execute("SELECT * FROM people WHERE search LIKE ? ESCAPE '\\' ORDER BY name,id LIMIT ? OFFSET ?", (query, limit, offset)).fetchall()
    return dict(total=total, items=[output(r) for r in rows], offset=offset, limit=limit)

@app.get('/api/v1/persons/{person_id}')
def person(request: Request, person_id: str):
    require_admin(request)
    with connect() as db:
        row = db.execute('SELECT * FROM people WHERE id=?', (person_id,)).fetchone()
    if not row:
        raise HTTPException(404, 'Không tìm thấy hồ sơ')
    return output(row)

@app.get('/api/v1/persons/{person_id}/photo')
def photo(person_id: str):
    with connect() as db:
        row = db.execute('SELECT photo FROM people WHERE id=?', (person_id,)).fetchone()
    if not row or not row['photo']:
        raise HTTPException(404, 'Chưa có ảnh')
    path = (GALLERY / row['photo']).resolve()
    if not path.is_relative_to(GALLERY.resolve()) or not path.is_file():
        raise HTTPException(404, 'Không có tệp ảnh')
    return FileResponse(path)

class PersonInput(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    employee_id: str = Field(min_length=1, max_length=100)
    title: str = Field('', max_length=300)
    department: str = Field('', max_length=300)
    division: str = Field('', max_length=300)

def save_person(body, person_id=None):
    fields = {k: v.strip() for k, v in body.model_dump().items()}
    if not fields['name'] or not fields['employee_id']:
        raise HTTPException(422, 'Tên và mã nhân viên không được để trống')
    with connect() as db:
        db.execute('BEGIN IMMEDIATE')
        if person_id and not db.execute('SELECT 1 FROM people WHERE id=?', (person_id,)).fetchone():
            raise HTTPException(404, 'Không tìm thấy hồ sơ')
        if db.execute('SELECT 1 FROM people WHERE employee_id=? AND id!=?', (fields['employee_id'], person_id or '')).fetchone():
            raise HTTPException(409, 'Mã nhân viên đã tồn tại')
        pid = person_id or 'local-' + uuid.uuid4().hex
        values = [*fields.values(), time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()), fold(' '.join(fields.values()))]
        if person_id:
            db.execute("UPDATE people SET name=?,employee_id=?,title=?,department=?,division=?,updated_at=?,search=?,source='Portal (edited)' WHERE id=?", (*values, pid))
        else:
            db.execute("INSERT INTO people (id,name,employee_id,title,department,division,updated_at,search,source,employments) VALUES (?,?,?,?,?,?,?,?, 'Portal','[]')", (pid, *values))
    return output(dict(id=pid, name=fields['name'], employee_id=fields['employee_id'], title=fields['title'], department=fields['department'], division=fields['division'], photo=None, source='Portal', updated_at=values[-2], employments='[]'))

@app.post('/api/v1/persons', status_code=201)
def create_person(request: Request, body: PersonInput):
    require_admin(request)
    return save_person(body)

@app.put('/api/v1/persons/{person_id}')
def update_person(request: Request, person_id: str, body: PersonInput):
    require_admin(request)
    return save_person(body, person_id)

def _detect_and_evaluate_faces(bgr_image: np.ndarray, gray_image: np.ndarray, orig_w: int, orig_h: int):
    """Detect faces with YuNet (or Haar fallback), measure quality metrics and match identities."""
    faces = []
    recognizer = cv2.FaceRecognizerSF.create(str(SFACE_PATH), '') if SFACE_PATH.is_file() else None
    detector_engine = 'OpenCV Haar frontalface'

    if YUNET_PATH.is_file():
        try:
            # Scale down large images for faster & stable inference if needed
            max_dim = max(orig_w, orig_h)
            scale = 1.0
            if max_dim > 1200:
                scale = 1200.0 / max_dim
                infer_w = int(orig_w * scale)
                infer_h = int(orig_h * scale)
                infer_bgr = cv2.resize(bgr_image, (infer_w, infer_h))
            else:
                infer_w, infer_h = orig_w, orig_h
                infer_bgr = bgr_image

            detector = cv2.FaceDetectorYN.create(str(YUNET_PATH), '', (infer_w, infer_h), 0.6, 0.3, 5000)
            _, raw_faces = detector.detect(infer_bgr)
            detector_engine = 'OpenCV YuNet'

            if raw_faces is not None:
                for raw_face in raw_faces:
                    # Map box back to original coordinates
                    rx, ry, rw, rh = raw_face[0:4]
                    x = max(0, int(rx / scale))
                    y = max(0, int(ry / scale))
                    w = min(orig_w - x, int(rw / scale))
                    h = min(orig_h - y, int(rh / scale))
                    if w <= 0 or h <= 0:
                        continue

                    # Unscaled face landmarks for alignment
                    face_orig = raw_face.copy()
                    face_orig[0:14] = face_orig[0:14] / scale

                    # Face crop for blur and light calculation
                    crop_gray = gray_image[y:y+h, x:x+w]
                    if recognizer is not None:
                        try:
                            aligned = recognizer.alignCrop(bgr_image, face_orig)
                            aligned_gray = cv2.cvtColor(aligned, cv2.COLOR_BGR2GRAY)
                            blur = float(cv2.Laplacian(aligned_gray, cv2.CV_64F).var())
                            light = float(aligned_gray.mean())
                        except Exception:
                            blur = float(cv2.Laplacian(crop_gray, cv2.CV_64F).var()) if crop_gray.size > 0 else 0.0
                            light = float(crop_gray.mean()) if crop_gray.size > 0 else 0.0
                    else:
                        blur = float(cv2.Laplacian(crop_gray, cv2.CV_64F).var()) if crop_gray.size > 0 else 0.0
                        light = float(crop_gray.mean()) if crop_gray.size > 0 else 0.0

                    reasons = []
                    if min(w, h) < 80:
                        reasons.append('Khuôn mặt nhỏ hơn 80 px')
                    if blur < 60:
                        reasons.append('Độ nét thấp / có thể bị nhòe')
                    if light < 45:
                        reasons.append('Thiếu sáng')
                    if light > 220:
                        reasons.append('Quá sáng')

                    face_dict = {
                        'box': [x, y, w, h],
                        'status': 'needs_review' if reasons else 'acceptable',
                        'reasons': reasons,
                        'metrics': {
                            'width_px': w,
                            'height_px': h,
                            'laplacian_variance': round(blur, 2),
                            'brightness': round(light, 2),
                            'detection_score': round(float(raw_face[14]), 3)
                        }
                    }

                    # Face Identity Matching
                    if recognizer is not None:
                        try:
                            aligned = recognizer.alignCrop(bgr_image, face_orig)
                            feat = recognizer.feature(aligned)
                            matches = EMBEDDINGS_INDEX.search(feat, top_k=3, min_score=0.36)
                            if matches:
                                face_dict['matched_person'] = matches[0]
                                face_dict['candidates'] = matches
                        except Exception:
                            pass

                    faces.append(face_dict)
        except Exception:
            faces = []

    # Fallback to Haar Cascade if YuNet produced nothing or failed
    if not faces and YUNET_PATH.is_file() is False:
        ratio = min(1, 1200 / max(orig_w, orig_h))
        small = cv2.resize(gray_image, None, fx=ratio, fy=ratio) if ratio < 1 else gray_image
        detector = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')
        boxes = detector.detectMultiScale(small, scaleFactor=1.1, minNeighbors=5, minSize=(24, 24))
        for box in boxes:
            x, y, w, h = [int(v / ratio) for v in box]
            crop = gray_image[y:y+h, x:x+w]
            blur = float(cv2.Laplacian(crop, cv2.CV_64F).var()) if crop.size > 0 else 0.0
            light = float(crop.mean()) if crop.size > 0 else 0.0
            reasons = []
            if min(w, h) < 80: reasons.append('Khuôn mặt nhỏ hơn 80 px')
            if blur < 80: reasons.append('Độ nét thấp / có thể bị nhòe')
            if light < 50: reasons.append('Thiếu sáng')
            if light > 210: reasons.append('Quá sáng')
            faces.append(dict(box=[x, y, w, h], status='needs_review' if reasons else 'acceptable', reasons=reasons, metrics=dict(width_px=w, height_px=h, laplacian_variance=round(blur, 2), brightness=round(light, 2))))

    return faces, detector_engine

@app.post('/api/v1/image-quality')
def quality(file: UploadFile):
    started = time.perf_counter()
    raw = file.file.read(10 * 1024 * 1024 + 1)
    if len(raw) > 10 * 1024 * 1024:
        raise HTTPException(413, 'Ảnh tối đa 10 MB')
    try:
        image = Image.open(io.BytesIO(raw))
        if image.width * image.height > 20_000_000:
            raise HTTPException(413, 'Ảnh tối đa 20 megapixel')
        image = ImageOps.exif_transpose(image).convert('RGB')
        rgb_array = np.array(image)
        gray = cv2.cvtColor(rgb_array, cv2.COLOR_RGB2GRAY)
        bgr = cv2.cvtColor(rgb_array, cv2.COLOR_RGB2BGR)
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError):
        raise HTTPException(422, 'Tệp không phải ảnh hợp lệ')

    faces, detector_engine = _detect_and_evaluate_faces(bgr, gray, image.width, image.height)

    result = dict(
        width=image.width,
        height=image.height,
        faces=faces,
        total_faces=len(faces),
        elapsed_ms=round((time.perf_counter() - started) * 1000, 1),
        engine=dict(
            version='quality-v2-yunet-sface',
            detector=detector_engine,
            opencv=cv2.__version__,
            thresholds=dict(min_face_px=80, min_laplacian=60, min_brightness=45, max_brightness=220)
        ),
        note='Định vị khuôn mặt với YuNet, thẩm định chất lượng & nhận diện danh tính nhân sự. Lưu trong 100 case gần nhất.'
    )
    case_id = uuid.uuid4().hex
    result['case_id'] = case_id
    with connect() as db:
        db.execute('BEGIN IMMEDIATE')
        db.execute('INSERT INTO scan_cases (id,created_at,image,result) VALUES (?,?,?,?)', (case_id, time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()), raw, json.dumps(result, ensure_ascii=False)))
        # Image bytes and metadata share a transaction: pruning cannot orphan files.
        db.execute('DELETE FROM scan_cases WHERE seq NOT IN (SELECT seq FROM scan_cases ORDER BY seq DESC LIMIT 100)')
    return result

@app.post('/api/v1/recognize')
def recognize(file: UploadFile):
    """Explicit Face Recognition endpoint returning detected faces and matched identities."""
    return quality(file)

@app.get('/api/v1/cases')
def cases():
    with connect() as db:
        rows = db.execute('SELECT id,created_at,result,status,note FROM scan_cases ORDER BY seq DESC').fetchall()
    return {'limit': 100, 'items': [dict(id=r['id'], created_at=r['created_at'], result=json.loads(r['result']), status=r['status'], note=r['note']) for r in rows]}

@app.get('/api/v1/cases/{case_id}/image')
def case_image(case_id: str, original: bool = False):
    with connect() as db:
        row = db.execute('SELECT image FROM scan_cases WHERE id=?', (case_id,)).fetchone()
    if not row:
        raise HTTPException(404, 'Case đã bị xóa hoặc không tồn tại')
    if original:
        return Response(bytes(row['image']), media_type='application/octet-stream', headers={'Content-Disposition': f'attachment; filename="{case_id}.bin"'})
    # Normalize orientation for an exact overlay and never serve active uploads inline.
    img = ImageOps.exif_transpose(Image.open(io.BytesIO(row['image']))).convert('RGB')
    out = io.BytesIO()
    img.save(out, format='JPEG', quality=92)
    return Response(out.getvalue(), media_type='image/jpeg')

class CaseReview(BaseModel):
    status: str = Field(pattern='^(unreviewed|correct|needs_fix)$')
    note: str = Field('', max_length=4000)

@app.patch('/api/v1/cases/{case_id}')
def review_case(case_id: str, body: CaseReview):
    with connect() as db:
        changed = db.execute('UPDATE scan_cases SET status=?,note=? WHERE id=?', (body.status, body.note, case_id)).rowcount
        if not changed:
            raise HTTPException(404, 'Case đã bị xóa hoặc không tồn tại')
    return {'status': 'ok'}

@app.delete('/api/v1/cases/{case_id}')
def delete_case(case_id: str):
    with connect() as db:
        changed = db.execute('DELETE FROM scan_cases WHERE id=?', (case_id,)).rowcount
        if not changed:
            raise HTTPException(404, 'Case đã bị xóa hoặc không tồn tại')
    return {'status': 'deleted'}

if (ROOT / 'web/dist').exists():
    app.mount('/', StaticFiles(directory=ROOT / 'web/dist', html=True), name='portal')

