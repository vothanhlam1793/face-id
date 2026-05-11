# Face ID Local Web App

Ung dung local de:

- Doc webcam realtime
- Detect khuon mat bang YOLO
- Nhan dien bang face embedding
- Gom khuon mat chua ro thanh `unknown groups`
- Review va gan ten qua web UI
- Import anh/video de quet khuon mat offline
- Luu kho anh theo tung nguoi de sau nay rebuild embedding khi doi model

## Trang thai hien tai

Project da hoat dong voi cac kha nang chinh:

- Webcam stream tren trang `/`
- Review unknown groups tren `/review`
- Tracking toi gian theo IoU cho webcam va video import
- Import anh `JPG`, `PNG`, `HEIC`
- Import video `MP4`, `MOV`, `M4V`, `AVI`
- Auto merge pending groups neu embedding giong nhau tren nguong cao
- Sau khi gan ten, anh duoc doi vao thu muc rieng trong `people/`
- Co nut `Rebuild embeddings` de tao lai vector nhan dien tu kho anh da luu

## Cau truc du an

```text
face-id/
  app/
    api/
      dependencies.py
      routes_groups.py
      routes_pages.py
      routes_state.py
    core/
      database.py
      models.py
      services.py
    vision/
      detector.py
      embedder.py
      recognizer.py
      tracker.py
    config.py
    main.py
  static/
    camera.js
    review.js
    styles.css
  templates/
    index.html
    review.html
  models/
  people/
  snapshots/
  requirements.txt
  README.md
  SESSION_HANDOFF.md
  ROADMAP.md
```

## Doc code theo thu tu

De vao session moi, doc theo thu tu nay:

1. `SESSION_HANDOFF.md`
2. `README.md`
3. `ROADMAP.md`
4. `app/main.py`
5. `app/config.py`
6. `app/core/services.py`
7. `app/core/database.py`
8. `app/vision/tracker.py`
9. `app/vision/recognizer.py`
10. `app/api/routes_groups.py`
11. `templates/review.html` va `static/review.js`

## Cai dat

```bash
cd /Users/macos/Documents/Linh-tinh/face-id
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
mkdir -p models
curl -L "https://github.com/YapaLab/yolo-face/releases/download/1.0.0/yolov8n-face.pt" -o models/yolov8n-face.pt
```

## Chay app

```bash
cd /Users/macos/Documents/Linh-tinh/face-id
source .venv/bin/activate
uvicorn app.main:app --reload
```

Mo trinh duyet tai `http://127.0.0.1:8000`

## Luong su dung

1. Mo `/` de xem webcam va ket qua nhan dien.
2. Khi gap khuon mat chua chac chan, he thong tao `unknown group`.
3. Neu la webcam hoac video, nhieu frame cua cung nguoi se duoc gom vao cung group.
4. Mo `/review` de xu ly.
5. Tai `/review`, ban co the:
   - `Tao moi`
   - `Gan nguoi cu`
   - `Nhan goi y`
   - `Xoa anh` xau trong group
   - `Import anh`
   - `Nhan dien hang loat groups`
   - `Rebuild embeddings`
6. Khi group duoc gan ten, toan bo anh trong group se duoc doi vao thu muc cua nguoi do trong `people/`.

## Luong import du lieu

### Import anh

- Ho tro: `JPG`, `PNG`, `HEIC`
- Moi khuon mat detect duoc tu anh se tao group moi luc dau
- Sau do he thong co gang auto merge cac group pending neu giong nhau

### Import video

- Ho tro: `MP4`, `MOV`, `M4V`, `AVI`
- Video duoc xu ly nhu stream offline
- He thong doc frame lien tuc
- Detect tat ca khuon mat trong frame
- Tracker bam theo IoU de giu cung track/group cho cung nguoi
- Tot hon cach lay mau 12 frame mot lan

## Kho du lieu anh

Co 2 vung luu anh:

- `snapshots/`: anh tam, unknown, anh moi crop ra truoc khi gan ten
- `people/`: kho anh chinh thuc theo tung nguoi sau khi da gan ten

Sau khi da gan ten:

- DB van luu `snapshot_path`
- Nhung file anh se nam trong `people/<ten-nguoi>-<id>/`
- Day la nguon du lieu de rebuild embedding sau nay

## Rebuild embeddings

Nut `Rebuild embeddings` tren `/review` se:

1. Doc tung thu muc trong `people/`
2. Load tung anh da luu
3. Tinh lai embedding bang model hien tai
4. Xoa embedding cu trong `face_samples`
5. Ghi lai embedding moi

Y nghia:

- Neu sau nay doi tu `FaceNet` sang `ArcFace`
- Van co the dung kho anh cu de tao lai toan bo he thong nhan dien

## Luu y ky thuat

- Tracker hien tai la tracker nhe dua tren IoU
- Face embedding hien tai dang dung `facenet-pytorch`
- Detect dang dung `yolov8n-face.pt`
- Auto merge group import dang dung nguong `0.80`
- Nhan dien tu dong nguoi da biet dung nguong cao hon

## Cac file quan trong nhat

- `app/core/services.py`: logic nghiep vu trung tam
- `app/core/database.py`: schema va thao tac SQLite
- `app/vision/tracker.py`: logic track ID
- `app/vision/recognizer.py`: best match va suggestion
- `app/api/routes_groups.py`: action quan ly group/import/rebuild

## Viec nen lam tiep neu mo rong

1. Doi embedding sang ArcFace
2. Nang cap tracker tu IoU sang IoU + embedding hoac tracker manh hon
3. Them progress bar cho import video lon
4. Them trang xem chi tiet tung nguoi va kho anh cua ho
