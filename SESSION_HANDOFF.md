# Session Handoff

File nay dung de vao session moi nhanh.

## Muc tieu du an

Dung webcam, anh, hoac video de:

- phat hien khuon mat
- nhan dien nguoi da biet
- gom khuon mat chua ro thanh group
- review va gan ten thu cong
- luu kho anh theo tung nguoi
- co kha nang rebuild embedding khi doi model

## Kien truc tong quat

- `FastAPI` + `Uvicorn`: web app local
- `OpenCV`: webcam, video, image decode
- `YOLO`: detect face
- `FaceNet`: embedding hien tai
- `SQLite`: luu metadata va embedding

## Route chinh

- `/`: camera live
- `/review`: review unknown groups
- `/api/state`: state camera
- `/api/review_state`: danh sach groups + people
- `/api/groups/*`: create/attach/dismiss/delete/recheck/import
- `/api/system/rebuild_embeddings`: rebuild vector tu kho anh `people/`

## Hanh vi hien tai

### Webcam

- detect theo frame
- tracker IoU bam track
- nguoi la -> unknown group
- nhieu goc mat cua cung mot nguoi -> cung group

### Import anh

- detect tat ca mat trong anh
- tao group
- auto merge pending groups neu giong nhau
- ho tro `HEIC`

### Import video

- xu ly video nhu stream offline
- track theo IoU qua frame
- khong con lay mau 12 frame mot lan
- cung nguoi trong video co xu huong vao cung group

## Kho du lieu can nho

- `snapshots/`: anh tam va unknown
- `people/`: anh da xac nhan theo tung nguoi

Sau khi gan:

- anh duoc doi vao `people/<slug-name>-<id>/`
- DB cap nhat `snapshot_path`

## Rebuild embeddings

Nut rebuild hien tai:

- doc anh trong `people/`
- tinh lai embedding bang model hien tai
- cap nhat lai `face_samples`

Day la co so de doi sang ArcFace sau nay.

## File can doc khi tiep tuc code

1. `app/core/services.py`
2. `app/core/database.py`
3. `app/vision/tracker.py`
4. `app/api/routes_groups.py`
5. `static/review.js`

## Ranh gioi hien tai

- Tracker van la IoU tracker, chua phai tracker manh
- Embedding van la FaceNet
- Chua co progress UI cho import video dai
- Chua co person detail page

## Cach chay

```bash
cd /Users/macos/Documents/Linh-tinh/face-id
source .venv/bin/activate
uvicorn app.main:app --reload
```

## Neu vao session moi va can mo rong

Huong uu tien:

1. ArcFace migration
2. Tracker manh hon
3. Import video co progress
4. Person gallery page
