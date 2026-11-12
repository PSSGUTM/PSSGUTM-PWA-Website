from app.services.assign import can_add, plan_assignment, seat_configs

BOTH = {"going", "returning"}


def m(uid, gender="male", dirs=BOTH, cur=None):
    return {"user_id": uid, "gender": gender, "dirs": set(dirs), "current_vehicle_id": cur}


def car(vid, rows=(1, 3), driver="male"):
    return {"id": vid, "type": "car", "driver_gender": driver, "rows": list(rows)}


def moto(vid, driver="male"):
    return {"id": vid, "type": "motorcycle", "driver_gender": driver, "rows": [1]}


def test_configs_match_circular_examples():
    # 5 seat, driver lelaki: semua lelaki (4) | 1 lelaki depan + 3 perempuan | 3 perempuan sahaja
    assert set(seat_configs("car", "male", [1, 3])) == {(0, 3), (1, 3), (4, 0)}
    # 7 seat: 1 driver + 5 pp belakang | 4 lelaki depan + 2 pp belakang | semua lelaki (6)
    c = set(seat_configs("car", "male", [1, 3, 2]))
    assert (0, 5) in c and (4, 2) in c and (6, 0) in c
    # Driver perempuan: semua perempuan
    assert seat_configs("car", "female", [1, 3, 2]) == [(0, 6)]


def test_male_driver_all_male_fills_four():
    res = plan_assignment([m(i) for i in range(1, 6)], [car(1)])
    assert [res[i] for i in range(1, 6)] == [1, 1, 1, 1, None]


def test_male_driver_three_females_in_back():
    res = plan_assignment([m(i, "female") for i in range(1, 5)], [car(1)])
    assert [res[i] for i in range(1, 5)] == [1, 1, 1, None]   # sebelah driver lelaki tak boleh perempuan


def test_mixed_prefers_more_people_and_keeps_rows_pure():
    # 1 lelaki + 3 perempuan muat (lelaki depan, perempuan belakang) = 4 orang
    members = [m(1, "male"), m(2, "female"), m(3, "female"), m(4, "female")]
    res = plan_assignment(members, [car(1)])
    assert all(res[i] == 1 for i in (1, 2, 3, 4))
    # 2 lelaki + 3 perempuan: tak boleh semua (lelaki ke-2 akan duduk belakang perempuan/sebaris)
    members = [m(1, "male"), m(2, "male"), m(3, "female"), m(4, "female"), m(5, "female")]
    res = plan_assignment(members, [car(1)])
    assigned = [i for i in res if res[i] == 1]
    assert len(assigned) == 4  # maksimum 4 orang, bukan 5


def test_female_driver_carries_only_females():
    res = plan_assignment([m(1, "male"), m(2, "female")], [car(1, driver="female")])
    assert res[1] is None and res[2] == 1


def test_seven_seater_male_front_female_back():
    members = [m(i, "male") for i in range(1, 5)] + [m(5, "female"), m(6, "female")]
    res = plan_assignment(members, [car(1, rows=(1, 3, 2))])
    assert all(res[i] == 1 for i in range(1, 7))   # 4 lelaki depan + 2 pp belakang


def test_cars_before_motorcycles():
    members = [m(i) for i in range(1, 7)]
    res = plan_assignment(members, [moto(9), car(1)])
    assert [res[i] for i in range(1, 5)] == [1, 1, 1, 1]
    assert res[5] == 9 and res[6] is None      # motor bawa seorang sahaja


def test_motorcycle_same_gender_only():
    res = plan_assignment([m(1, "female")], [moto(9, driver="male")])
    assert res[1] is None
    res = plan_assignment([m(1, "female")], [moto(9, driver="female")])
    assert res[1] == 9


def test_same_vehicle_both_ways_and_one_way_mix():
    members = [m(i, dirs={"going"}) for i in range(1, 5)] + [m(5)]
    res = plan_assignment(members, [car(1), car(2)])
    assert res[5] == 2   # kereta 1 penuh untuk arah 'going'


def test_keep_existing_only_fills_gaps():
    members = [m(1, cur=2), m(2, cur=2), m(3)]
    res = plan_assignment(members, [car(1, rows=(1, 1)), car(2, rows=(1, 1))], keep_existing=True)
    assert res[1] == 2 and res[2] == 2 and res[3] == 1


def test_keep_existing_unavailable_vehicle_reassigned():
    res = plan_assignment([m(1, cur=99)], [car(1)], keep_existing=True)
    assert res[1] == 1


def test_can_add_manual_rules():
    v = car(1)
    assert can_add(v, [m(1, "female"), m(2, "female")], m(3, "female"))
    assert can_add(v, [m(1, "female"), m(2, "female")], m(3, "male"))           # lelaki depan, pp belakang
    assert not can_add(v, [m(1, "male"), m(2, "male")], m(3, "female"))         # 2 lelaki -> baris belakang lelaki
    assert not can_add(v, [m(i, "female") for i in range(1, 4)], m(4, "female"))  # pp maksimum 3 (depan tak boleh)
    assert not can_add(v, [m(i, "male") for i in range(1, 5)], m(5, "male"))     # penuh


# ---------------------------------------------------------------- kategori kolej jauh / dekat

def mc(uid, cat, gender="male", dirs=BOTH, cur=None):
    return {**m(uid, gender, dirs, cur), "category": cat}


def cv(vid, cat, rows=(1, 3), driver="male", vtype="car"):
    base = car(vid, rows, driver) if vtype == "car" else moto(vid, driver)
    return {**base, "category": cat}


def test_far_car_takes_far_and_near_car_takes_near():
    members = [mc(1, "jauh"), mc(2, "jauh"), mc(3, "jauh"), mc(4, "dekat"), mc(5, "dekat"), mc(6, "dekat")]
    # kenderaan 1 = dekat (id lebih kecil sengaja), kenderaan 2 = jauh
    res = plan_assignment(members, [cv(1, "dekat"), cv(2, "jauh")])
    assert [res[i] for i in (1, 2, 3)] == [2, 2, 2]
    assert [res[i] for i in (4, 5, 6)] == [1, 1, 1]


def test_leftover_far_combined_into_near_car_with_space():
    # 5 jauh -> kereta jauh muat 4, seorang lagi digabung ke kereta dekat yang ada 2 penumpang dekat
    members = [mc(i, "jauh") for i in range(1, 6)] + [mc(6, "dekat"), mc(7, "dekat")]
    res = plan_assignment(members, [cv(1, "jauh"), cv(2, "dekat")])
    assert [res[i] for i in range(1, 5)] == [1, 1, 1, 1]
    assert res[5] == 2 and res[6] == 2 and res[7] == 2


def test_few_passengers_combined_and_idle_car_freed():
    # kereta jauh cuma ada 1 penumpang jauh; kereta dekat ada 2 dekat dan muat -> gabung, kereta jauh dibebaskan
    members = [mc(1, "jauh"), mc(2, "dekat"), mc(3, "dekat")]
    res = plan_assignment(members, [cv(1, "jauh"), cv(2, "dekat")])
    assert set(res.values()) == {2}


def test_no_combine_when_vehicle_carries_more_than_threshold():
    members = [mc(1, "jauh"), mc(2, "jauh"), mc(3, "jauh"), mc(4, "dekat"), mc(5, "dekat"), mc(6, "dekat")]
    res = plan_assignment(members, [cv(1, "jauh"), cv(2, "dekat")])
    assert [res[i] for i in (1, 2, 3)] == [1, 1, 1] and [res[i] for i in (4, 5, 6)] == [2, 2, 2]


def test_combine_threshold_can_be_disabled():
    members = [mc(1, "jauh"), mc(2, "dekat"), mc(3, "dekat")]
    res = plan_assignment(members, [cv(1, "jauh"), cv(2, "dekat")], combine_below=0)
    assert res[1] == 1 and res[2] == 2 and res[3] == 2


def test_combine_respects_seat_etiquette():
    # penumpang jauh perempuan tak boleh digabung ke kereta dekat (driver lelaki) yang baris belakangnya
    # sudah diduduki lelaki: lelaki tak boleh duduk di belakang perempuan
    members = [mc(1, "jauh", "female"), mc(2, "dekat", "male"), mc(3, "dekat", "male"), mc(4, "dekat", "male"),
               mc(5, "dekat", "male")]
    res = plan_assignment(members, [cv(1, "jauh"), cv(2, "dekat")])
    assert res[1] == 1                      # kekal di kenderaan jauh (tak muat dengan 4 lelaki)
    assert [res[i] for i in (2, 3, 4, 5)] == [2, 2, 2, 2]


def test_neutral_vehicle_takes_leftovers_of_any_category():
    members = [mc(1, "jauh"), mc(2, "dekat")]
    res = plan_assignment(members, [cv(1, None)])
    assert res[1] == 1 and res[2] == 1


def test_keep_existing_prefers_same_category_for_late_joiner():
    members = [mc(1, "jauh", cur=1), mc(2, "dekat", cur=2), mc(3, "jauh")]
    res = plan_assignment(members, [cv(1, "dekat"), cv(2, "jauh")], keep_existing=True)
    # 1 dan 2 kekal tidak berubah (walau kategori tak sepadan); 3 (jauh) masuk kenderaan jauh (id 2)
    assert res[1] == 1 and res[2] == 2 and res[3] == 2


def test_keep_existing_never_moves_people_even_if_few():
    members = [mc(1, "jauh", cur=1), mc(2, "dekat", cur=2)]
    res = plan_assignment(members, [cv(1, "jauh"), cv(2, "dekat")], keep_existing=True)
    assert res[1] == 1 and res[2] == 2


def test_motorcycles_still_after_cars_within_category():
    members = [mc(1, "dekat"), mc(2, "dekat")]
    res = plan_assignment(members, [cv(1, "dekat", vtype="moto"), cv(2, "dekat")])
    assert res[1] == 2 and res[2] == 2     # kereta diisi dahulu


# ---- kerusi ----
from app.services.assign import auto_seat, check_layout, complete_layout, seat_list


def occ(*items):
    return [{"row": r, "col": c, "gender": g} for r, c, g in items]


def test_check_layout_rules():
    rows = [1, 3]
    assert check_layout("car", "male", rows, occ((0, 0, "male"), (1, 0, "female"), (1, 1, "female"))) is None
    assert check_layout("car", "male", rows, occ((0, 0, "female"))) is not None            # sebelah driver lelaki
    assert check_layout("car", "male", rows, occ((1, 0, "male"), (1, 1, "female"))) is not None  # sebaris
    assert check_layout("car", "male", rows, occ((0, 0, "female"), (1, 0, "male"))) is not None
    # lelaki di belakang perempuan (7 seat)
    assert check_layout("car", "male", [1, 3, 2], occ((1, 0, "female"), (2, 0, "male"))) is not None
    assert check_layout("car", "male", rows, occ((1, 0, "male"), (1, 0, "male"))) is not None    # kerusi sama
    assert check_layout("car", "female", rows, occ((1, 0, "male"))) is not None
    assert check_layout("motorcycle", "male", [1], occ((0, 0, "female"))) is not None
    assert check_layout("motorcycle", "male", [1], occ((0, 0, "male"))) is None


def test_auto_seat_and_complete_layout():
    mem = [{"user_id": 1, "gender": "male"}, {"user_id": 2, "gender": "female"}, {"user_id": 3, "gender": "female"}]
    out = auto_seat("car", "male", [1, 3], mem)
    assert out[1] == (0, 0) and {out[2][0], out[3][0]} == {1}
    # 4 perempuan tak muat (baris depan tak boleh)
    assert auto_seat("car", "male", [1, 3], [{"user_id": i, "gender": "female"} for i in range(4)]) is None
    # kerusi tersimpan yang sah dikekalkan
    keep = complete_layout("car", "male", [1, 3], mem, {2: (1, 2)})
    assert keep[2] == (1, 2) and len(set(keep.values())) == 3
    # kerusi tersimpan yang melanggar peraturan diabaikan
    bad = complete_layout("car", "male", [1, 3], mem, {2: (0, 0)})
    assert bad[2][0] == 1
    assert len(seat_list([1, 3, 2])) == 6


# ---------------------------------------------------------------- fasa 6: zon kolej, kumpul kolej, perempuan tunggal
from app.services.assign import lone_female_cases, zone_of, college_group


def mz(uid, zone, gender="male", college=None, dirs=BOTH):
    x = m(uid, gender, dirs)
    x.update({"zone": zone, "college": college or zone, "college_group": college_group(college or zone)})
    return x


def cz(vid, zone, rows=(1, 3), driver="male", college=None):
    v = car(vid, rows, driver)
    v.update({"zone": zone, "college": college or zone, "college_group": college_group(college or zone)})
    return v


def test_zone_of_and_group():
    assert zone_of("KTR", "dekat") == "dekat"
    for c in ("KDSE", "KTGB", "KLG", "KDOJ"):
        assert zone_of(c, "jauh") == "jauhA"
    for c in ("K9", "K10", "KTC", "KP"):
        assert zone_of(c, "jauh") == "jauhB"
    assert college_group("K9") == college_group("K10") == "K9 & K10"


def test_dekat_prebet_has_priority_over_jauhA_for_dekat():
    members = [mz(i, "dekat") for i in range(1, 5)]
    res = plan_assignment(members, [cz(1, "jauhA"), cz(2, "dekat")])
    assert set(res.values()) == {2}   # prebet dekat ambil semua dekat; jauhA tak digunakan


def test_jauhA_prebet_takes_leftover_dekat_and_own_zone_first():
    members = [mz(1, "jauhA"), mz(2, "jauhA"), mz(3, "dekat"), mz(4, "dekat"), mz(5, "dekat")]
    res = plan_assignment(members, [cz(1, "jauhA"), cz(2, "dekat")], combine_below=0)
    assert res[1] == res[2] == 1            # jauhA ambil jauhA dahulu
    assert [res[i] for i in (3, 4, 5)].count(2) == 3


def test_jauhB_prebet_does_not_take_jauhA_when_jauhA_prebet_exists():
    members = [mz(1, "jauhA"), mz(2, "jauhA"), mz(3, "jauhB"), mz(4, "jauhB")]
    res = plan_assignment(members, [cz(1, "jauhB"), cz(2, "jauhA")], combine_below=0)
    assert res[1] == res[2] == 2 and res[3] == res[4] == 1


def test_same_college_grouped_in_same_car():
    members = [mz(1, "jauhB", college="KTC"), mz(2, "jauhB", college="K9"), mz(3, "jauhB", college="KTC"),
               mz(4, "jauhB", college="K10"), mz(5, "jauhB", college="KTC"), mz(6, "jauhB", college="K9")]
    res = plan_assignment(members, [cz(1, "jauhB", college="KTC"), cz(2, "jauhB", college="K9")], combine_below=0)
    assert res[1] == res[3] == res[5] == 1      # KTC bersama prebet KTC
    assert res[2] == res[6] == 2                # K9 bersama K10 (satu kumpulan)


def test_no_lone_female_in_male_driver_car():
    members = [m(1, "male"), m(2, "female")]
    res = plan_assignment(members, [car(1)], no_lone_female=True)
    assert res[1] == 1 and res[2] is None
    assert lone_female_cases(members, [car(1)], res) == [2]
    res2 = plan_assignment(members, [car(1)], no_lone_female=False)
    assert res2[1] == 1 and res2[2] == 1


def test_female_that_cannot_fit_anyway_is_not_flagged():
    members = [m(1), m(2), m(3), m(4), m(5, "female")]
    res = plan_assignment(members, [car(1)], no_lone_female=True)
    assert lone_female_cases(members, [car(1)], res) == []


def test_two_females_ok_and_female_driver_unlimited():
    members = [m(1, "male"), m(2, "female"), m(3, "female")]
    res = plan_assignment(members, [car(1)], no_lone_female=True)
    assert res[2] == res[3] == 1
    res = plan_assignment([m(1, "female")], [car(1, driver="female")], no_lone_female=True)
    assert res[1] == 1


def test_cars_before_motorcycles_across_zones():
    members = [mz(1, "dekat"), mz(2, "jauhB")]
    veh = [moto(1), cz(2, "jauhB")]
    veh[0]["zone"] = "dekat"
    res = plan_assignment(members, veh, combine_below=0)
    assert res[1] == 2 and res[2] == 2     # kereta penuh dahulu (muat) sebelum motosikal


# ---------------- keutamaan susunan baharu (Fasa 7)

def mz(uid, zone, gender="male", college=None, dirs=BOTH):
    return {"user_id": uid, "gender": gender, "dirs": set(dirs), "current_vehicle_id": None, "zone": zone,
            "college": college or zone, "college_group": college or zone}


def cz(vid, zone, college=None, driver="male", rows=(1, 3)):
    return {"id": vid, "type": "car", "driver_gender": driver, "rows": list(rows), "zone": zone,
            "college": college or zone, "college_group": college or zone}


def test_own_zone_first_then_four_colleges_before_other_jauh():
    # prebet dekat: 2 penumpang dekat dahulu, kemudian empat kolej (jauhA), jauhB paling akhir
    members = [mz(1, "jauhB", college="KTC"), mz(2, "jauhB", college="KTC"), mz(3, "jauhA", college="KLG"),
               mz(4, "dekat"), mz(5, "dekat"), mz(6, "dekat")]
    res = plan_assignment(members, [cz(1, "dekat")], combine_below=0)
    # 4 tempat: dekat x3 dahulu, kemudian empat kolej (KLG); kolej jauh lain tak muat
    assert res[4] == res[5] == res[6] == res[3] == 1 and res[1] is None and res[2] is None


def test_jauhA_prebet_takes_four_colleges_first():
    members = [mz(1, "dekat"), mz(2, "jauhA", college="KLG"), mz(3, "jauhA", college="KDSE")]
    res = plan_assignment(members, [cz(1, "jauhA", college="KLG")], combine_below=0)
    assert res[2] == 1 and res[3] == 1 and res[1] == 1


def test_jauhB_prebet_takes_dekat_before_four_colleges():
    members = [mz(i, "dekat") for i in (1, 2)] + [mz(i, "jauhA", college="KLG") for i in (3, 4, 5)]
    res = plan_assignment(members, [cz(1, "jauhB", college="KTC")], combine_below=0)
    assert res[1] == 1 and res[2] == 1 and sum(1 for i in (3, 4, 5) if res[i] == 1) == 2


def test_lone_female_with_male_driver_not_assigned():
    members = [mz(1, "dekat", gender="female")]
    res = plan_assignment(members, [cz(1, "dekat")], no_lone_female=True, combine_below=0)
    assert res[1] is None      # terus e-hailing


def test_two_females_with_male_driver_ok():
    members = [mz(1, "dekat", gender="female"), mz(2, "dekat", gender="female")]
    res = plan_assignment(members, [cz(1, "dekat")], no_lone_female=True, combine_below=0)
    assert res[1] == 1 and res[2] == 1


# ---- seorang sahaja bagi sesuatu jantina -> utamakan motosikal
def _mem(i, g):
    return {"user_id": i, "gender": g, "dirs": {"going", "returning"}, "current_vehicle_id": None, "category": "dekat"}


def test_single_member_prefers_motorcycle():
    car = {"id": 1, "type": "car", "driver_gender": "male", "rows": [1, 3], "category": "dekat"}
    moto = {"id": 2, "type": "motorcycle", "driver_gender": "male", "rows": [1], "category": "dekat"}
    assert plan_assignment([_mem(10, "male")], [car, moto]) == {10: 2}


def test_two_members_same_gender_prefer_car():
    car = {"id": 1, "type": "car", "driver_gender": "male", "rows": [1, 3], "category": "dekat"}
    moto = {"id": 2, "type": "motorcycle", "driver_gender": "male", "rows": [1], "category": "dekat"}
    assert plan_assignment([_mem(10, "male"), _mem(11, "male")], [car, moto]) == {10: 1, 11: 1}


def test_single_female_gets_female_rider_even_with_male_car():
    car = {"id": 1, "type": "car", "driver_gender": "male", "rows": [1, 3], "category": "dekat"}
    mf = {"id": 3, "type": "motorcycle", "driver_gender": "female", "rows": [1], "category": "dekat"}
    r = plan_assignment([_mem(10, "male"), _mem(11, "male"), _mem(12, "female")], [car, mf])
    assert r == {10: 1, 11: 1, 12: 3}
