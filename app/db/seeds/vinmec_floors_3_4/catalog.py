"""Synthetic room programs based on the department signs on floors 3 and 4."""

from dataclasses import dataclass

SITE_CODE = "VINMEC-DEMO-F34"

# Lễ tân hỏi "đã đặt lịch chưa" trước khi chỉ đến khoa/phòng khám; chưa có lịch thì mời đến quầy này.
BOOKING_DESK = "Tư vấn dịch vụ và đặt lịch"
# Không hỏi lịch hẹn: quầy dịch vụ (nhà thuốc, thanh toán, lễ tân – tư vấn) và nơi nộp mẫu.
# shortcut: danh sách cố định cho cơ sở mô phỏng, chuyển thành cột trong bảng khoa/phòng khi có dữ liệu bệnh viện thật.
WALK_IN_ZONES = frozenset({"3-04", "3-10", "4-01", "4-14"})
WALK_IN_ROOMS = frozenset({"Tiếp nhận mẫu nước tiểu", "Tiếp nhận mẫu gửi", "Tiếp nhận mẫu lưu trữ"})
# Cách khách gọi tắt một khoa mà tên đầy đủ không chứa ("khám tổng quát", "cardiology").
# shortcut: hằng số cho cơ sở mô phỏng, chuyển thành bảng bí danh khoa khi có dữ liệu bệnh viện thật.
DEPARTMENT_ALIASES = {
    "3-01": ("khám tim", "cardiology", "heart center"),
    "3-03": ("ung thư", "oncology", "cancer center"),
    "3-05": ("sức khỏe tinh thần", "tâm lý", "tâm thần", "mental health", "psychology", "psychiatry"),
    "3-07": ("chỉnh hình", "orthopedics", "sports medicine"),
    "4-08": ("khám tổng quát", "khám sức khỏe", "health check", "check up", "checkup"),
    "4-10": ("thần kinh", "neurology"),
    "4-13": ("nha khoa", "dentist", "ent"),
}


@dataclass(frozen=True)
class Zone:
    floor: int
    number: int
    side: str
    row: int
    name: str
    rooms: tuple[str, ...]
    signed: bool = True  # có số trên bảng mặt bằng thật hay không

    @property
    def code(self) -> str:
        return f"{self.floor}-{self.number:02d}"

    @property
    def entry_code(self) -> str:
        return f"ENTRY-{self.code}"

    @property
    def sign_label(self) -> str:
        """Cách gọi khu trong câu chỉ đường: có số thì kèm "khu số N"."""
        return f"khu số {self.number} — {self.name}" if self.signed else self.name


def zone(floor: int, number: int, side: str, row: int, name: str, rooms: str, *, signed: bool = True) -> Zone:
    return Zone(floor, number, side, row, name, tuple(part.strip() for part in rooms.split("|")), signed)


ZONES = (
    zone(3, 1, "west", 5, "Trung tâm Tim mạch", """
        Tiếp đón tim mạch | Khám tim mạch tổng quát | Khám tăng huyết áp | Khám suy tim |
        Khám rối loạn nhịp | Khám bệnh van tim | Khám mạch vành | Khám mạch máu ngoại biên |
        Điện tâm đồ | Siêu âm tim qua thành ngực | Siêu âm Doppler mạch |
        Gắn Holter điện tim | Gắn máy đo huyết áp 24 giờ | Kiểm tra máy tạo nhịp |
        Nghiệm pháp gắng sức | Tư vấn phòng ngừa bệnh tim | Tư vấn dinh dưỡng tim mạch |
        Giáo dục tự theo dõi huyết áp | Theo dõi sau can thiệp tim mạch | Hẹn tái khám tim mạch
    """),
    zone(3, 2, "west", 4, "Trung tâm Tế bào gốc", """
        Tiếp đón tế bào gốc | Tư vấn lưu trữ máu cuống rốn | Tư vấn lưu trữ mô dây rốn |
        Tư vấn đăng ký lưu trữ | Tư vấn người hiến | Sàng lọc người hiến |
        Tư vấn gia đình trước ghép | Khám đánh giá trước ghép | Tư vấn tương hợp HLA |
        Lấy mẫu sàng lọc | Thu mẫu kiểm tra tương hợp | Tiếp nhận hồ sơ người hiến |
        Kiểm tra giấy tờ lưu trữ | Bàn giao bộ thu mẫu | Tiếp nhận mẫu lưu trữ |
        Trả kết quả sàng lọc | Tư vấn theo dõi người hiến | Theo dõi sau ghép |
        Hỗ trợ điều phối lịch khám | Tư vấn cập nhật hồ sơ lưu trữ
    """),
    zone(3, 3, "west", 3, "Trung tâm Ung bướu Vinmec", """
        Tiếp đón ung bướu | Khám ung bướu lần đầu | Khám ung bướu tái khám |
        Tư vấn nguy cơ ung thư | Tư vấn tầm soát ung bướu | Khám ung bướu tuyến vú |
        Khám ung bướu tiêu hóa | Khám ung bướu hô hấp | Tư vấn điều trị nội khoa ung bướu |
        Tư vấn xạ trị | Lấy mẫu xét nghiệm ung bướu | Đánh giá trước buổi điều trị |
        Điều trị ban ngày A | Điều trị ban ngày B | Theo dõi sau buổi điều trị |
        Tư vấn dinh dưỡng ung bướu | Tư vấn kiểm soát triệu chứng | Tư vấn chăm sóc giảm nhẹ |
        Hỗ trợ tâm lý người bệnh ung bướu | Trả kết quả và hẹn tái khám ung bướu
    """),
    zone(3, 4, "west", 2, "Nhà thuốc", """
        Tiếp nhận đơn thuốc | Nhận thuốc theo đơn A | Nhận thuốc theo đơn B |
        Tư vấn sử dụng thuốc | Tư vấn bảo quản thuốc | Hỗ trợ đối chiếu đơn thuốc
    """),
    zone(3, 5, "west", 1, "Trung tâm Chăm sóc Sức khỏe Tinh thần", """
        Tiếp đón sức khỏe tinh thần | Đánh giá tâm lý ban đầu | Khám sức khỏe tinh thần người lớn |
        Khám sức khỏe tinh thần vị thành niên | Đánh giá lo âu | Đánh giá khí sắc |
        Đánh giá khó ngủ | Đánh giá căng thẳng công việc | Đánh giá chức năng nhận thức |
        Trị liệu tâm lý cá nhân A | Trị liệu tâm lý cá nhân B | Trị liệu gia đình |
        Trị liệu nhóm | Tư vấn cha mẹ | Tư vấn kỹ năng ứng phó |
        Tư vấn vệ sinh giấc ngủ | Theo dõi điều trị | Giáo dục sức khỏe tinh thần |
        Tư vấn hỗ trợ người chăm sóc | Hẹn tái khám sức khỏe tinh thần
    """),
    zone(3, 6, "west", 0, "Trung tâm Vú", """
        Tiếp đón trung tâm vú | Khám vú tổng quát | Khám vú theo dõi |
        Khám thay đổi tuyến vú lành tính | Tư vấn nguy cơ ung thư vú | Tư vấn tầm soát tuyến vú |
        Siêu âm vú A | Siêu âm vú B | Chụp nhũ ảnh | Tư vấn trước chụp nhũ ảnh |
        Đánh giá trước sinh thiết | Sinh thiết tuyến vú | Theo dõi sau sinh thiết |
        Đọc và tư vấn kết quả hình ảnh | Trả kết quả mô bệnh học | Tư vấn trước mổ tuyến vú |
        Chăm sóc vết mổ tuyến vú | Tư vấn tái tạo tuyến vú | Tư vấn theo dõi phù bạch huyết |
        Hẹn tái khám trung tâm vú
    """),
    zone(3, 7, "east", 0, "Trung tâm Chấn thương Chỉnh hình – Y học Thể thao", """
        Tiếp đón chỉnh hình | Khám vai | Khám khuỷu tay | Khám bàn tay và cổ tay |
        Khám khớp háng | Khám đầu gối | Khám bàn chân và cổ chân | Khám cột sống |
        Khám chấn thương thể thao | Đánh giá vận động viên trước mùa giải |
        Đánh giá trước mổ chỉnh hình | Tư vấn phẫu thuật khớp | Thay băng chỉnh hình |
        Bó bột | Tháo bột và kiểm tra | Tư vấn nẹp chỉnh hình | Siêu âm cơ xương khớp |
        Đánh giá chức năng khớp sau mổ | Tư vấn trở lại tập luyện | Hẹn tái khám chỉnh hình
    """),
    zone(3, 8, "east", 1, "Khoa Gây mê và Giảm đau", """
        Tiếp đón gây mê và giảm đau | Khám tiền mê người lớn | Khám tiền mê nhi |
        Đánh giá đường thở | Đối chiếu hồ sơ tiền mê | Tư vấn gây tê vùng |
        Tư vấn gây mê ngoại trú | Tư vấn an thần khi làm thủ thuật | Đánh giá đau cấp |
        Đánh giá đau mạn | Khám đau thần kinh | Khám đau cơ xương |
        Khám đau sau phẫu thuật | Tư vấn kế hoạch kiểm soát đau | Tư vấn dùng thuốc giảm đau |
        Siêu âm hỗ trợ đánh giá vùng đau | Thủ thuật giảm đau A | Thủ thuật giảm đau B |
        Theo dõi sau thủ thuật giảm đau | Hẹn tái khám giảm đau
    """),
    zone(3, 9, "east", 2, "Trung tâm Y học Tái tạo và Trị liệu Tế bào", """
        Tiếp đón y học tái tạo | Tư vấn y học tái tạo ban đầu | Rà soát hồ sơ điều trị |
        Tư vấn tiêu chí tham gia chương trình | Tư vấn lợi ích và nguy cơ | Tư vấn quyền người tham gia |
        Đánh giá sức khỏe nền | Đo chỉ số sinh tồn | Đánh giá chức năng khớp |
        Đánh giá khả năng sinh hoạt | Lấy mẫu kiểm tra trước đợt điều trị |
        Đối chiếu kết quả sàng lọc | Tư vấn kế hoạch theo dõi | Điều phối lịch chương trình |
        Theo dõi ngày điều trị A | Theo dõi ngày điều trị B | Nộp phiếu theo dõi tại nhà |
        Ghi nhận triệu chứng sau điều trị | Đánh giá kết quả theo hẹn | Hẹn tái khám y học tái tạo
    """),
    zone(3, 10, "east", 3, "Quầy Thanh toán tầng 3", """
        Thanh toán viện phí | Hỗ trợ hóa đơn và chứng từ
    """),
    zone(3, 11, "east", 4, "Khoa Phục hồi Chức năng", """
        Tiếp đón phục hồi chức năng | Khám phục hồi chức năng | Lượng giá vận động |
        Lượng giá thăng bằng | Phục hồi sau đột quỵ | Phục hồi chi trên |
        Phục hồi chi dưới | Phục hồi cột sống | Phục hồi hô hấp | Phục hồi sau mổ khớp |
        Vật lý trị liệu A | Vật lý trị liệu B | Hoạt động trị liệu cá nhân |
        Tập sinh hoạt hằng ngày | Tập dáng đi | Luyện giao tiếp |
        Lượng giá nuốt | Thử dụng cụ trợ giúp đi lại | Hướng dẫn bài tập tại nhà |
        Hẹn tái lượng giá phục hồi chức năng
    """),
    zone(3, 12, "east", 5, "Motion Lab", """
        Tiếp đón Motion Lab | Đo nhân trắc | Đánh giá tư thế đứng | Hiệu chuẩn cho buổi đo vận động |
        Gắn cảm biến chuyển động | Ghi hình dáng đi | Đo lực nền khi bước |
        Phân tích áp lực bàn chân | Kiểm tra thăng bằng tĩnh | Kiểm tra thăng bằng động |
        Phân tích dáng chạy | Phân tích động tác đổi hướng | Đánh giá tiếp đất khi nhảy |
        Đánh giá phạm vi chuyển động khớp | Kiểm tra sức mạnh đẳng động |
        Kiểm tra độ đối xứng chi dưới | Ghi điện cơ bề mặt | Đo lại sau bài tập |
        Giải thích báo cáo vận động | Tư vấn chương trình tập theo kết quả đo
    """),
    zone(4, 1, "east", 0, "Quầy Thanh toán tầng 4", """
        Thanh toán viện phí | Hỗ trợ bảo lãnh viện phí
    """),
    zone(4, 2, "east", 1, "Trung tâm Bệnh lý Tuyến giáp", """
        Tiếp đón tuyến giáp | Khám tuyến giáp lần đầu | Khám tuyến giáp tái khám |
        Khám cường giáp | Khám suy giáp | Khám bướu giáp | Khám nhân tuyến giáp |
        Tư vấn viêm tuyến giáp | Tư vấn tuyến giáp trong thai kỳ | Siêu âm tuyến giáp A |
        Siêu âm tuyến giáp B | Lấy mẫu xét nghiệm chức năng tuyến giáp |
        Tư vấn trước chọc hút | Chọc hút tế bào tuyến giáp | Theo dõi sau chọc hút |
        Đọc và tư vấn kết quả tế bào học | Đánh giá trước mổ tuyến giáp |
        Theo dõi sau mổ tuyến giáp | Tư vấn theo dõi hormon tuyến giáp | Hẹn tái khám tuyến giáp
    """),
    zone(4, 3, "east", 2, "Trung tâm Công nghệ Gen", """
        Tiếp đón công nghệ gen | Tư vấn di truyền ban đầu | Lập phả hệ gia đình |
        Tư vấn nguy cơ bệnh di truyền | Tư vấn di truyền trước thai kỳ |
        Tư vấn xét nghiệm người mang gen | Tư vấn di truyền nhi khoa |
        Tư vấn nguy cơ ung thư di truyền | Tư vấn xét nghiệm gen tim mạch |
        Tư vấn dược di truyền | Tư vấn phạm vi đồng ý xét nghiệm | Đối chiếu hồ sơ xét nghiệm gen |
        Lấy mẫu máu xét nghiệm gen | Hướng dẫn lấy mẫu niêm mạc miệng |
        Tiếp nhận mẫu gửi | Hỗ trợ yêu cầu lấy mẫu lại | Trả kết quả xét nghiệm gen |
        Tư vấn giải thích biến thể | Tư vấn xét nghiệm cho người thân | Hẹn tái tư vấn di truyền
    """),
    zone(4, 4, "east", 3, "Đơn vị Nội soi", """
        Tiếp đón nội soi | Tư vấn nội soi lần đầu | Kiểm tra phiếu chỉ định |
        Hướng dẫn chuẩn bị nội soi dạ dày | Hướng dẫn chuẩn bị nội soi đại tràng |
        Đánh giá trước an thần | Đo chỉ số trước nội soi | Khu thay đồ nội soi A |
        Khu thay đồ nội soi B | Nội soi dạ dày A | Nội soi dạ dày B |
        Nội soi đại tràng A | Nội soi đại tràng B | Nội soi siêu âm |
        Tiếp nhận nội soi viên nang | Theo dõi hồi tỉnh A | Theo dõi hồi tỉnh B |
        Trả báo cáo nội soi | Hướng dẫn chăm sóc sau nội soi | Hẹn tái khám nội soi
    """),
    zone(4, 5, "east", 5, "Trung tâm Tiêu hóa – Gan mật – Tiết niệu", """
        Tiếp đón tiêu hóa, gan mật và tiết niệu | Khám tiêu hóa tổng quát |
        Khám trào ngược dạ dày | Khám rối loạn tiêu hóa | Khám bệnh viêm ruột |
        Khám gan nhiễm mỡ | Khám viêm gan | Khám túi mật | Khám tiết niệu tổng quát |
        Khám sỏi tiết niệu | Khám rối loạn tiểu tiện | Siêu âm bụng |
        Siêu âm đường tiết niệu | Đo độ đàn hồi gan | Đo lưu lượng nước tiểu |
        Tiếp nhận mẫu nước tiểu | Tư vấn dinh dưỡng tiêu hóa | Tư vấn theo dõi bệnh gan mạn |
        Trả kết quả xét nghiệm tiêu hóa | Hẹn tái khám tiêu hóa, gan mật và tiết niệu
    """),
    zone(4, 6, "east", 6, "Phòng khám Nội Tổng hợp", """
        Tiếp đón nội tổng hợp | Khám nội tổng hợp lần đầu | Khám nội tổng hợp tái khám |
        Khám người cao tuổi | Khám triệu chứng hô hấp | Khám đau đầu và chóng mặt |
        Khám sốt kéo dài | Khám mệt mỏi | Khám rối loạn mỡ máu | Khám bệnh mạn phối hợp |
        Đo dấu hiệu sinh tồn | Đo độ bão hòa oxy | Lấy mẫu máu nội tổng hợp |
        Tiếp nhận mẫu nước tiểu | Đối chiếu danh mục thuốc | Tư vấn dự phòng |
        Tư vấn chăm sóc tại nhà | Đọc kết quả xét nghiệm nội tổng hợp |
        Điều phối khám chuyên khoa | Hẹn tái khám nội tổng hợp
    """),
    zone(4, 7, "west", 6, "Khoa Nội tiết – Đái tháo đường", """
        Tiếp đón nội tiết | Khám đái tháo đường típ 1 | Khám đái tháo đường típ 2 |
        Khám đái tháo đường thai kỳ | Khám tiền đái tháo đường | Khám nội tiết thượng thận |
        Khám nội tiết tuyến yên | Khám rối loạn chuyển hóa xương | Khám bàn chân đái tháo đường |
        Đo glucose tại chỗ | Lấy mẫu HbA1c | Gắn cảm biến glucose |
        Đọc dữ liệu cảm biến glucose | Hướng dẫn bút tiêm insulin | Hướng dẫn máy đo đường huyết |
        Tư vấn dinh dưỡng đái tháo đường | Giáo dục nhận biết hạ đường huyết |
        Đánh giá nguy cơ biến chứng | Tư vấn mục tiêu vận động | Hẹn tái khám nội tiết
    """),
    zone(4, 8, "west", 5, "Trung tâm Khám Sức khỏe Tổng quát", """
        Tiếp đón khám sức khỏe | Tư vấn gói khám | Xác nhận danh mục gói khám |
        Khám nội theo gói | Khám ngoại theo gói | Khám cơ xương theo gói |
        Đo chiều cao và cân nặng | Đo huyết áp theo gói | Lấy mẫu máu khám sức khỏe |
        Tiếp nhận mẫu nước tiểu | Đo thị lực theo gói | Đo thính lực theo gói |
        Đo điện tâm đồ theo gói | Đo chức năng hô hấp | Siêu âm tổng quát |
        Khám sức khỏe doanh nghiệp | Tư vấn yếu tố nguy cơ | Đọc báo cáo khám sức khỏe |
        Trả hồ sơ khám sức khỏe | Điều phối tái kiểm tra theo kết quả
    """),
    zone(4, 9, "west", 4, "Trung tâm Dị ứng – Miễn dịch Lâm sàng", """
        Tiếp đón dị ứng | Khám viêm mũi dị ứng | Khám dị ứng thức ăn | Khám dị ứng thuốc |
        Khám mày đay | Khám viêm da cơ địa | Khám phù mạch | Khám miễn dịch lâm sàng |
        Tư vấn dị ứng côn trùng | Lấy mẫu xét nghiệm dị ứng | Test da hô hấp |
        Test áp da | Đọc kết quả test da | Đánh giá trước thử nghiệm dị ứng |
        Theo dõi sau kiểm tra dị ứng A | Theo dõi sau kiểm tra dị ứng B |
        Tư vấn nhận biết phản vệ | Hướng dẫn tránh tác nhân dị ứng |
        Tư vấn kế hoạch theo dõi miễn dịch | Hẹn tái khám dị ứng
    """),
    zone(4, 10, "west", 3, "Phòng khám Thần kinh và Đột quỵ", """
        Tiếp đón thần kinh | Khám đau đầu | Khám động kinh | Khám rối loạn vận động |
        Khám thần kinh ngoại biên | Khám suy giảm trí nhớ | Khám sau đột quỵ |
        Tư vấn dự phòng đột quỵ | Khám rối loạn thăng bằng | Khám bệnh cơ |
        Đánh giá nhận thức | Đánh giá chức năng thần kinh | Điện não đồ |
        Điện cơ và dẫn truyền thần kinh | Siêu âm Doppler xuyên sọ |
        Đọc kết quả khảo sát thần kinh | Tư vấn chăm sóc sau đột quỵ |
        Tư vấn theo dõi cơn động kinh | Điều phối phục hồi thần kinh | Hẹn tái khám thần kinh
    """),
    zone(4, 11, "west", 2, "Đơn vị Y học Cổ truyền Tác động Cột sống", """
        Tiếp đón y học cổ truyền | Khám y học cổ truyền | Đánh giá đau cổ vai gáy |
        Đánh giá đau lưng | Đánh giá tư thế cột sống | Lượng giá độ linh hoạt cột sống |
        Tư vấn trước trị liệu cột sống | Xoa bóp trị liệu A | Xoa bóp trị liệu B |
        Châm cứu A | Châm cứu B | Day ấn huyệt | Tác động cột sống A | Tác động cột sống B |
        Nhiệt trị liệu | Hướng dẫn vận động cột sống | Hướng dẫn tư thế làm việc |
        Nghỉ sau buổi trị liệu | Đánh giá đáp ứng sau trị liệu | Hẹn tái khám y học cổ truyền
    """),
    zone(4, 12, "west", 1, "Đơn vị Lọc máu", """
        Tiếp đón lọc máu | Khám trước buổi lọc máu | Đo cân nặng trước lọc |
        Đo huyết áp trước lọc | Đánh giá đường vào mạch máu | Lấy mẫu theo dõi lọc máu |
        Lọc máu ca A | Lọc máu ca B | Lọc máu ca C | Lọc máu ca D |
        Theo dõi chỉ số sau lọc | Nghỉ sau buổi lọc | Chăm sóc đường vào mạch máu |
        Tư vấn lựa chọn phương thức lọc | Tư vấn dinh dưỡng người lọc máu |
        Hướng dẫn theo dõi dịch tại nhà | Tư vấn lọc màng bụng |
        Đọc kết quả xét nghiệm định kỳ | Điều phối đổi ca lọc | Hẹn tái khám lọc máu
    """),
    zone(4, 13, "west", 0, "Phòng khám Tai Mũi Họng – Răng Hàm Mặt – Mắt", """
        Tiếp đón liên chuyên khoa | Khám tai | Khám mũi xoang | Khám họng và thanh quản |
        Nội soi tai mũi họng | Đo thính lực | Đo nhĩ lượng | Tư vấn kết quả thính lực |
        Khám răng tổng quát | Khám hàm mặt | Vệ sinh răng | Chụp X-quang răng |
        Tư vấn chỉnh nha | Tư vấn chăm sóc răng sau thủ thuật | Khám mắt tổng quát |
        Đo khúc xạ | Đo nhãn áp | Chụp đáy mắt | Tư vấn kính và chăm sóc mắt |
        Hẹn tái khám liên chuyên khoa
    """),
    # Quầy lễ tân – tư vấn ở cửa Trung tâm KSK Tổng quát (không có số trên bảng thật).
    zone(4, 14, "west", 7, "Quầy Lễ tân – Tư vấn dịch vụ", """
        Lễ tân và hướng dẫn | Tư vấn dịch vụ và đặt lịch
    """, signed=False),
)

ENGLISH_ZONE_NAMES = {
    "3-01": "Cardiovascular Center",
    "3-02": "Stem Cell Center",
    "3-03": "Vinmec Cancer Center",
    "3-04": "Pharmacy",
    "3-05": "Integrated Mental Health Care Center",
    "3-06": "Breast Center",
    "3-07": "Center for Orthopaedic and Sports Medicine",
    "3-08": "Anaesthesiology and Pain Management",
    "3-09": "Center for Regenerative Medicine and Cell Therapy",
    "3-10": "Cashier Counter",
    "3-11": "Rehabilitation Department",
    "3-12": "Motion Lab",
    "4-01": "Cashier Counter",
    "4-02": "Thyroid Center",
    "4-03": "Gene Technology Center",
    "4-04": "Endoscopy Unit",
    "4-05": "Gastroenterology, Hepatology and Urology Center",
    "4-06": "Internal Medicine Clinic",
    "4-07": "Endocrinology and Diabetes",
    "4-08": "Health Check-up Center",
    "4-09": "Allergy and Clinical Immunology Center",
    "4-10": "Neurology and Stroke Clinic",
    "4-11": "Spinal Intervention Unit",
    "4-12": "Hemodialysis Unit",
    "4-13": "ENT, Dentistry and Ophthalmology Clinic",
    "4-14": "Reception and Service Advice Desk",
}
