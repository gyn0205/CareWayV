# Cấu hình PostgreSQL và chạy migration

## Chạy bằng Docker Compose

Tại thư mục gốc của repo, chạy các lệnh sau để khởi động nhóm `carewayv` trong Docker Desktop. Compose đợi PostgreSQL sẵn sàng. Container `api` chạy `alembic upgrade head` rồi khởi động FastAPI khi migration thành công. [Docker Compose — thứ tự khởi động](https://docs.docker.com/compose/how-tos/startup-order/)

```bash
test -f .env || cp .env.example .env
docker compose up -d --build --wait --remove-orphans
docker compose ps -a
```

Mở Swagger UI tại [127.0.0.1:8000/docs](http://127.0.0.1:8000/docs). Có thể đổi cổng API bằng `CAREWAYV_API_PORT` trong `.env`. Compose lưu dữ liệu trong volume `carewayv_pgdata`. Lệnh `docker compose down` xóa các container trong stack và giữ volume.

Kết nối từ máy host bằng địa chỉ `127.0.0.1:55432`, database và user `carewayv`, mật khẩu mặc định `carewayv_dev` cho môi trường phát triển. Compose dùng `DB_PORT`, `DB_NAME`, `DB_USER` và `DB_PASSWORD` trong `.env`. Trong mạng Compose, API kết nối bằng địa chỉ `db:5432`. Nếu đã có volume, đổi mật khẩu của role trong PostgreSQL trước khi cập nhật biến mật khẩu.

```bash
docker compose logs api db
docker compose exec api python -m alembic current
docker compose exec api python -m alembic check
```

## Chạy Alembic từ máy host

Cần Python 3.11 trở lên và một database PostgreSQL. Với Compose mặc định, Alembic trên máy host kết nối tới `127.0.0.1:55432`. Nếu chưa có `.env`, sao chép từ `.env.example` để đặt cổng và mật khẩu dùng chung với Compose. Khi kết nối PostgreSQL khác, đặt `DB_HOST`, `DB_PORT`, `DB_USER`, `DB_PASSWORD` và `DB_NAME` trong `.env`. `DATABASE_URL` ưu tiên cả chuỗi kết nối. Biến môi trường hệ thống có độ ưu tiên cao hơn cùng biến trong `.env`. [Pydantic Settings](https://docs.pydantic.dev/latest/concepts/pydantic_settings/)

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m alembic upgrade head
python -m alembic current
python -m alembic check
```

## Tạo migration khi thay đổi model

Sau khi database thử nghiệm đã chạy đến revision mới nhất hiện có, sửa model, rồi chạy các lệnh sau trong virtualenv từ thư mục gốc. Xem lại revision được sinh ra trong `migration/versions/` trước khi áp dụng. [Alembic — Autogenerate](https://alembic.sqlalchemy.org/en/latest/autogenerate.html)

`file_template` trong `alembic.ini` đặt tên file mới theo mẫu `YYYYMMDD_HHMMSS_<revision_id>_<mo_ta>.py` với giờ địa phương của máy chạy lệnh. Alembic lấy phần mô tả từ tham số `-m`. [Alembic — File template](https://alembic.sqlalchemy.org/en/latest/tutorial.html#editing-the-ini-file)

```bash
alembic revision --autogenerate -m "describe schema change"
alembic upgrade head
alembic check
```

Migration `0001` tạo 11 bảng. Revision `0002` bổ sung các cột audit và soft delete. `created_at` và `updated_at` của dữ liệu có sẵn nhận thời điểm chạy migration. `alembic downgrade base` xóa các bảng nghiệp vụ và dữ liệu trong bảng.

## Cấu trúc backend

- `app/main.py` là entry point FastAPI. Chạy `python -m uvicorn app.main:app --reload` để mở Swagger UI tại `http://127.0.0.1:8000/docs`.
- `app/core/config.py` khởi tạo `settings = Settings()`. `app/db/session.py` tạo engine và `SessionLocal` từ `settings.SQLALCHEMY_DATABASE_URI`. Route import `DbSession` từ `app.core.dependencies` và khai báo `db: DbSession` để FastAPI mở và đóng session theo request. Khi cần đọc lại thay đổi trong cùng giao dịch trước khi commit, gọi `db.flush()`.
- `app/db/base.py` khai báo SQLAlchemy Base. `app/db/base_model.py` import models và cung cấp metadata cho `migration/env.py`.
- Mỗi bảng có một file trong `app/models/`. Khi thêm bảng, import model trong `app/models/__init__.py` để đăng ký vào metadata.
- `migration/` được khởi tạo bằng `alembic init migration`. Alembic ghi revision mới vào `migration/versions/`.

## Soft delete

Các model kế thừa `created_at`, `updated_at` và mixin do `sqlalchemy-easy-softdelete` sinh. Gọi `record.delete()` để đánh dấu xóa hoặc `record.undelete()` để khôi phục, rồi commit session. Có thể gọi `soft_delete()` và `restore()` theo API của CareWayV. Dùng `.execution_options(include_deleted=True)` khi cần truy vấn bản ghi đã xóa. Các khóa chính và ràng buộc duy nhất tiếp tục áp dụng cho bản ghi đã xóa mềm. [SQLAlchemy Easy Soft-Delete](https://pypi.org/project/sqlalchemy-easy-softdelete/)

Với `select(aliased(Model))`, bản 0.9.1 có thể báo `NotImplementedError` khi áp dụng bộ lọc tự động. Dùng `.execution_options(include_deleted=True)` và thêm `.where(alias.deleted_at.is_(None))` nếu truy vấn alias chỉ cần bản ghi còn hiệu lực.

Xem [thiết kế bảng và sơ đồ quan hệ](wayfinding-database.md).
