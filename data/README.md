# Snapshot PostgreSQL dùng chung

`carewayv.dump` được xuất từ container `carewayv-db-1` ngày 17/11/2026,
bằng `pg_dump` của PostgreSQL 17, định dạng custom. Snapshot gồm schema,
dữ liệu, sequence, index, khóa ngoại và revision Alembic `0004`.
Owner và quyền truy cập riêng của máy xuất được loại bỏ để dùng với user khác.

## Import trên máy teammate

Cần Docker Engine / Docker Desktop đang chạy và Docker Compose v2.
Tại thư mục gốc repo, chạy:

```bash
bash script/import-db.sh
```

Script tự tạo `.env` từ `.env.example` nếu chưa có, khởi động service `db`
và chờ PostgreSQL sẵn sàng. Database đích là service `db` trong `compose.yaml`,
với cấu hình `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_PORT` của checkout đó.
Nếu cần cấu hình khác mặc định, sửa `.env` trước khi chạy. Không cần cài
Python, PostgreSQL client hoặc chạy migration/seed trước khi import.

**Dữ liệu hiện có trong các bảng thuộc snapshot sẽ được thay thế.** Trước
khi import, script lưu bản sao database đích tại
`data/backups/before-import-<UTC timestamp>-<PID>.dump` và in đường dẫn ra màn hình.
Nếu backup thất bại thì dừng import. Restore schema và dữ liệu chạy trong một
transaction; khi restore lỗi, PostgreSQL rollback các thay đổi.
Có thể chạy lại script để đưa các bảng về trạng thái trong snapshot.

Sau khi import, khởi động ứng dụng:

```bash
docker compose up -d --build --wait
```

Import một snapshot khác hoặc khôi phục bản backup:

```bash
bash script/import-db.sh /duong/dan/backup.dump
```

Đường dẫn truyền vào được tính từ thư mục đang chạy lệnh. Snapshot mặc định
luôn được tìm theo vị trí script nên có thể gọi script từ thư mục khác.
Thư mục `backups/` được gitignore để các bản sao local không bị commit.

## Dữ liệu trong snapshot

| Bảng | Số bản ghi |
| --- | ---: |
| alembic_version | 1 |
| buildings | 1 |
| departments | 25 |
| floors | 2 |
| hospital_sites | 1 |
| kiosks | 2 |
| navigation_edges | 1476 |
| navigation_nodes | 737 |
| rooms | 450 |
| service_aliases | 29 |
| service_locations | 450 |
| services | 428 |

SHA-256 của `carewayv.dump`:

```text
f0e48cae9ed6b47293280e42b6009c3ae011013bef5cb5d43550b32184114cd0
```
