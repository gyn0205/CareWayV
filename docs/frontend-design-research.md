# Tham chiếu thiết kế frontend CareWayV

Khảo sát ngày 16/11/2026. Giao diện công khai của Vinmec là nguồn tham chiếu chính cho kiosk. Các trang Vingroup, Vincom và VinWonders cung cấp thêm ví dụ về cách đặt điều hướng, tìm địa điểm và chọn tác vụ.

## Quan sát từ các trang chính thức

| Nguồn | Quan sát | Áp dụng cho CareWayV |
| --- | --- | --- |
| Vinmec | Trang chủ có thanh tiện ích xanh lam chuyển sắc, nền điều hướng trắng, biểu tượng nét xanh, điểm nhấn vàng ở nhận diện và ảnh tông xanh sáng. Các tác vụ cho khách hàng nằm trong một cụm thẻ trắng nổi bật, với nút gọi tổng đài, đặt lịch và tìm bác sĩ. Công tắc ngôn ngữ nằm ở đầu trang. [Trang chủ Vinmec](https://www.vinmec.com/vie/) | Dùng xanh lam đậm, xanh nhạt và trắng cho giao diện. Dành vàng cho điểm nhấn nhỏ. Đặt tìm đường bằng văn bản, microphone và điều khiển ngôn ngữ ở vị trí dễ thấy. |
| Vinmec Healthcare System và Online Vinmec | Trang hệ thống đặt các tác vụ tư vấn, đặt lịch và tìm bác sĩ cạnh thông tin cơ sở. Danh mục trình bày tên cơ sở, địa chỉ và hành động theo từng mục. Hướng dẫn Online Vinmec mô tả việc chọn bác sĩ, chuyên khoa hoặc thời gian trong luồng đặt lịch. [Hệ thống Vinmec](https://www.vinmec.com/eng/hospital/vinmec-healthcare-system), [Danh mục cơ sở](https://www.vinmec.com/eng/hospital/), [Hướng dẫn Online Vinmec](https://www.vinmec.com/vie/bai-viet/huong-dan-su-dung-online-vinmec-dat-lich-mua-goi) | Khi có nhiều kết quả, hiển thị lựa chọn theo tên, tầng và mã điểm đến. Sau khi chọn, dùng một vùng riêng để trình bày điểm xuất phát, điểm đến và các bước chỉ đường. |
| Vingroup | Trang chủ có hình ảnh kiến trúc quy mô lớn, một tiêu đề chính và cụm điều hướng riêng gồm menu và chuyển ngôn ngữ. Hồ sơ công bố của tập đoàn cho thấy nhận diện đỏ–vàng của Vingroup và xanh–vàng của Vinmec. [Trang chủ Vingroup](https://vingroup.net/), [Hồ sơ công bố nhãn hiệu](https://ircdn.vingroup.net/storage/uploads/0_Quan%20he%20co%20dong/0_Vingroup_2016/03/Ban%20cao%20bach.pdf) | Giữ một tiêu đề chức năng rõ ràng, đủ khoảng trống quanh vùng thao tác và hình ảnh bối cảnh có vai trò phụ. Dùng nhận diện CareWayV trên ứng dụng. |
| Vincom và VinWonders | Vincom cho phép tìm theo tên trung tâm hoặc gian hàng. VinWonders đưa lựa chọn điểm đến vào luồng đặt vé và sử dụng biểu tượng có chú giải trong bản đồ công viên. [Tìm kiếm Vincom](https://vincom.com.vn/trang-chu), [Trang đặt vé VinWonders](https://booking.vinwonders.com/en/), [Bản đồ VinWonders Phú Quốc](https://static.vinwonders.com/2022/05/220504_Guide-map-VW-PQ_TiengViet_view.pdf) | Dùng ô tìm kiếm chấp nhận tên khoa, mã phòng hay tên dịch vụ. Phân biệt các bước đi bộ, thang máy và cầu thang bằng cả biểu tượng lẫn nhãn. |

## Quyết định cho kiosk

- Ưu tiên chữ rõ dấu tiếng Việt, nút đủ lớn để bấm trên màn hình cảm ứng và thứ tự tab tự nhiên. Hiển thị trạng thái ghi âm, tải và lỗi tại vùng thao tác liên quan.
- Dùng lộ trình theo tầng và hướng dẫn từ API để biểu diễn tuyến. Chỉ hiển thị ảnh mặt bằng khi backend cung cấp URL ảnh. Với dữ liệu mô phỏng, ghi nhãn cho phần sơ đồ minh họa.
- Hiển thị nguồn gốc tuyến là kiosk đã chọn. Giữ yêu cầu xe lăn trong lượt hỏi làm rõ và mở lại câu hỏi mới khi người dùng kết thúc phiên.

## Ảnh minh họa

Ảnh sảnh hư cấu được tạo bằng ImageGen tích hợp và lưu tại `frontend/public/hospital-lobby.jpg`.

> Use case: photorealistic-natural. Asset type: hero banner photograph for a hospital indoor wayfinding kiosk. Wide 3:2 landscape, ultra realistic interior architecture editorial photograph of a contemporary international hospital reception lobby in Vietnam. Daylight, a double height glazed atrium with mist blue decorative glass, clean pale limestone, cream curved welcome desk on the right with a fine muted champagne-metal trim, subtle greenery and glossy ivory floor. One Vietnamese receptionist and one visitor in candid conversation on the far right, small in frame with no identifiable faces needed. Let the left third be softly lit quiet pale blue glass architecture with very little detail, and keep the main visual interest at center-right. Airy, approachable, polished but believable, slightly cool clinical-blue palette balanced by warm pale beige materials, clean bright daylight, realistic architectural photography. No writing, signs, letters, logos, signage or composited UI. This is a fictional lobby illustration, not a depiction of an actual named institution.
