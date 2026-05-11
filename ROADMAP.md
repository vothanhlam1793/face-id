# Roadmap

File nay de theo doi trang thai du an va cac huong phat trien tiep theo.

## Da hoan thanh

- Webcam live stream tren `/`
- Review unknown groups tren `/review`
- YOLO face detection
- FaceNet embedding
- Unknown group theo tracking IoU cho webcam
- Import anh `JPG`, `PNG`, `HEIC`
- Import video `MP4`, `MOV`, `M4V`, `AVI`
- Video import theo stream offline co tracking, khong con sampling thua
- Auto merge pending groups neu embedding giong nhau tren nguong cao
- Xoa bot anh xau trong group
- Gan group vao nguoi moi hoac nguoi da co
- Doi anh da xac nhan vao thu muc `people/`
- Rebuild embeddings tu kho anh da luu
- Refactor code thanh `api / core / vision / templates / static`

## Trang thai hien tai

- App chay local voi `FastAPI`
- Database: `SQLite`
- Embedding hien tai: `FaceNet`
- Tracker hien tai: `IoU tracker` don gian
- Kho anh da luu theo tung nguoi trong `people/`

## Gioi han hien tai

- Tracker chua manh trong canh dong nguoi hoac chuyen dong nhanh
- Chua co person detail page
- Chua co progress bar khi import video lon
- Chua co cong cu split group neu merge nham
- Chua co setting UI de chinh threshold
- Chua co migration chinh quy khi doi schema lon

## Uu tien cao

1. Chuyen embedding sang ArcFace
2. Nang cap tracker tu IoU sang IoU + embedding hoac tracker manh hon
3. Them progress UI cho import video
4. Them person gallery page de xem kho anh cua tung nguoi

## Uu tien trung binh

1. Them merge group thu cong
2. Them split group thu cong
3. Cho phep chinh threshold tren UI
4. Luu them metadata nguon import: ten file, frame index, timestamp
5. Them export/import database

## Uu tien thap

1. Them test tu dong cho service/database
2. Them logging chi tiet hon
3. Them thong ke tong hop tren dashboard

## Goi y session tiep theo

Neu vao session moi va muon tiep tuc nhanh, uu tien lam theo thu tu:

1. ArcFace migration ma van giu `Rebuild embeddings`
2. Tracker video/webcam manh hon
3. Person detail page
4. Progress bar import video
