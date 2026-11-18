from collections import Counter

from app.db.seeds.vinmec_floors_3_4.catalog import ZONES
from app.db.seeds.vinmec_floors_3_4.doctors import DUPLICATES, PER_FLOOR, doctor_slots
from app.db.seeds.vinmec_floors_3_4.layout import room_slots

ROOMS = {slot.code: slot for zone in ZONES for slot in room_slots(zone)}


def test_each_floor_has_doctors_in_real_rooms():
    doctors = doctor_slots()
    # Mã bác sĩ không trùng, mỗi tầng đủ số lượng, phòng gắn phải tồn tại.
    assert len({doctor.code for doctor in doctors}) == len(doctors)
    assert Counter(doctor.code.split("-")[1] for doctor in doctors) == {"3": PER_FLOOR, "4": PER_FLOOR}
    assert all(doctor.room_code in ROOMS for doctor in doctors)
    assert all(doctor.code.split("-")[1] == doctor.room_code.split("-")[0] for doctor in doctors)


def test_duplicate_names_are_placed_as_planned():
    doctors = doctor_slots()
    names = Counter(doctor.name for doctor in doctors)
    # Chỉ những tên khai báo trong DUPLICATES mới trùng họ tên đầy đủ.
    assert {name for name, count in names.items() if count > 1} == {name for name, _ in DUPLICATES}
    for name, places in DUPLICATES:
        found = sorted(
            (ROOMS[doctor.room_code].zone.floor, ROOMS[doctor.room_code].zone.number)
            for doctor in doctors if doctor.name == name
        )
        assert found == sorted(places)
    # Hai người cùng tên cùng khoa vẫn phân biệt được bằng phòng và học hàm.
    twins = [doctor for doctor in doctors if doctor.name == "Lê Minh Tuấn"]
    assert twins[0].room_code != twins[1].room_code and twins[0].title != twins[1].title
    assert doctor_slots() == doctors  # chạy lại ra đúng danh sách cũ
