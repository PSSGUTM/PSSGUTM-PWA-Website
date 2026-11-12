"""Logik susun kenderaan (tanpa database supaya senang diuji).

Peraturan (pekeliling + arahan BKK):
- Satu ahli = satu kenderaan yang sama untuk pergi DAN balik.
- Kereta diisi dahulu (penuh sebelum kereta seterusnya), baru motosikal.
  PENGECUALIAN: jika hanya ada SEORANG ahli lelaki (atau SEORANG perempuan) keseluruhannya, motosikal rider sama
  jantina diutamakan untuk dia; jika dua orang atau lebih bagi jantina itu, kereta diutamakan seperti biasa.
- Motosikal: seorang penumpang, MESTI sama jantina dengan rider.
- Kereta: driver lelaki -> penumpang lelaki boleh duduk di barisan hadapan, perempuan di belakang.
    * Satu baris mesti sama jantina (lelaki dan perempuan tak boleh sebaris / bersebelahan).
    * Lelaki tak boleh duduk di belakang perempuan (barisan lelaki sentiasa di hadapan).
    * Perempuan tak boleh duduk sebelah driver lelaki (baris pertama hanya untuk lelaki).
  Driver perempuan -> penumpang perempuan sahaja, tiada sekatan baris.
- Susunan seat dinilai untuk setiap arah (pergi / balik) secara berasingan.
- Kategori kolej: kenderaan yang pemandunya dari kolej JAUH ambil penumpang kolej jauh dahulu; pemandu kolej DEKAT
  ambil kolej dekat dahulu (kategori kenderaan None = neutral, boleh ambil mana-mana).
  Baki penumpang (kategori mereka tiada kenderaan/penuh) digabungkan ke kenderaan lain yang masih ada tempat,
  dan kenderaan yang bawa terlalu sedikit penumpang (<= combine_below) digabungkan ke kenderaan lain
  jika semua penumpangnya muat. Semua gabungan tetap tertakluk kepada peraturan adab tempat duduk di atas.

Zon (kumpulan kolej prebet/penumpang):
  dekat  : kolej dekat
  jauhA  : KDSE, KTGB, KLG, KDOJ (prebet kolej ini diutamakan ambil kolej dekat + empat kolej ini sahaja)
  jauhB  : kolej jauh lain (K9&K10, KTC, KP)
Susunan keutamaan (adab sentiasa dikuatkuasakan): 1) kumpulan sama jantina + sama kategori kolej; 2) kolej sama;
3) isi tempat kosong ikut ZONE_PREF (dekat -> empat kolej -> jauh lain, dsb.); 4) campur jantina hanya ikut adab seat;
5) selebihnya (penuh / melanggar adab, termasuk perempuan seorang diri dengan prebet lelaki) -> e-hailing.
Penumpang kolej sama (dan jantina sama) diletakkan dalam kenderaan yang sama dahulu untuk kurangkan hentian prebet.
Kereta pemandu lelaki: penumpang perempuan mesti 0 atau >= 2 (tidak boleh tepat seorang) jika no_lone_female.
"""

DIRS = ("going", "returning")

JAUH_A = {"KDSE", "KTGB", "KLG", "KDOJ"}
GROUP_K9K10 = {"K9", "K10"}


# Susunan zon penumpang bagi setiap zon prebet. Prebet empat kolej (jauhA) dianggap kategori dekat.
#   dekat : kolej dekat -> empat kolej -> kolej jauh lain
#   jauhA : empat kolej -> kolej dekat -> kolej jauh lain
#   jauhB : kolej jauh sendiri -> kolej dekat -> empat kolej
ZONE_PREF = {
    "dekat": ("dekat", "jauhA", "jauhB"),
    "jauhA": ("jauhA", "dekat", "jauhB"),
    "jauhB": ("jauhB", "dekat", "jauhA"),
    None: ("dekat", "jauhA", "jauhB"),
}


def zone_of(code, category):
    """Zon sesebuah kolej. category: 'dekat' | 'jauh' | None."""
    if category == "dekat":
        return "dekat"
    if category == "jauh":
        return "jauhA" if (code or "").upper() in JAUH_A else "jauhB"
    return None


def college_group(code):
    """Nama kumpulan kolej untuk paparan (K9 & K10 digabung)."""
    c = (code or "").upper()
    return "K9 & K10" if c in GROUP_K9K10 else c


def _zone(x):
    """Zon daripada kunci 'zone', atau daripada 'category' (jauh = jauhB) bagi data lama."""
    z = x.get("zone")
    if z:
        return z
    c = x.get("category")
    return {"dekat": "dekat", "jauh": "jauhB"}.get(c)


def parse_rows(text: str) -> list[int]:
    rows = [int(x) for x in str(text).split(",") if x.strip()]
    if not rows or any(r < 1 for r in rows):
        raise ValueError("Susun atur seat tak sah")
    return rows


def seat_configs(vtype: str, driver_gender: str, rows: list[int]) -> list[tuple[int, int]]:
    """Semua kombinasi (kapasiti_lelaki, kapasiti_perempuan) yang dibenarkan untuk satu kenderaan."""
    if vtype == "motorcycle":
        cap = rows[0] if rows else 1
        return [(cap, 0)] if driver_gender == "male" else [(0, cap)]
    if driver_gender == "female":
        return [(0, sum(rows))]
    configs = []
    for k in range(len(rows) + 1):  # k = bilangan baris (dari hadapan) untuk lelaki
        male_cap = sum(rows[:k])
        female_cap = sum(rows[max(k, 1):])  # baris pertama (sebelah driver lelaki) tak boleh perempuan
        if (male_cap, female_cap) not in configs:
            configs.append((male_cap, female_cap))
    return configs


def _fill(configs, forced, candidates, no_lone_female=False):
    """Pilih susunan yang memuatkan penumpang paling ramai.
    forced    : ahli yang sudah pasti dalam kenderaan ini (mesti muat)
    candidates: ahli yang boleh ditambah (ikut keutamaan)
    no_lone_female: perempuan yang ditambah tidak boleh tinggal seorang diri (tepat 1) dalam satu arah.
    Return list ahli tambahan, atau None kalau 'forced' tak muat dalam mana-mana susunan."""
    best = None
    for male_cap, female_cap in configs:
        cap = {"male": male_cap, "female": female_cap}
        used = {d: {"male": 0, "female": 0} for d in DIRS}
        ok = True
        for m in forced:
            for d in m["dirs"]:
                used[d][m["gender"]] += 1
        for d in DIRS:
            for g in ("male", "female"):
                if used[d][g] > cap[g]:
                    ok = False
        if not ok:
            continue
        added = []
        for m in candidates:
            g = m["gender"]
            if all(used[d][g] < cap[g] for d in m["dirs"]):
                for d in m["dirs"]:
                    used[d][g] += 1
                added.append(m)
        if no_lone_female:
            changed = True
            while changed:
                changed = False
                for d in DIRS:
                    if used[d]["female"] == 1:
                        lone = next((m for m in added if m["gender"] == "female" and d in m["dirs"]), None)
                        if lone is not None:
                            added.remove(lone)
                            for dd in lone["dirs"]:
                                used[dd]["female"] -= 1
                            changed = True
        if best is None or len(added) > len(best):
            best = added
    return best


def _configs_for(v):
    return seat_configs(v["type"], v["driver_gender"], v["rows"])


def _male_car(v) -> bool:
    return v["type"] == "car" and v["driver_gender"] == "male"


def has_lone_female(vehicle, members) -> bool:
    """Kereta pemandu lelaki dengan tepat seorang penumpang perempuan dalam sesuatu arah?"""
    if not _male_car(vehicle):
        return False
    for d in DIRS:
        if sum(1 for m in members if m["gender"] == "female" and d in m["dirs"]) == 1:
            return True
    return False


def can_add(vehicle, current_members, candidate, no_lone_female=False) -> bool:
    """Boleh tambah 'candidate' ke kenderaan ini (bersama ahli sedia ada) ikut peraturan seat?"""
    members = list(current_members) + [candidate]
    if _fill(_configs_for(vehicle), members, []) is None:
        return False
    return not (no_lone_female and has_lone_female(vehicle, members))


def _order_pool(pool, vehicle):
    """Susun calon: kolej pemandu dahulu, kemudian kolej paling ramai (kumpul kolej sama), jantina sama berkumpul."""
    count = {}
    for m in pool:
        k = m.get("college_group") or m.get("college") or ""
        count[k] = count.get(k, 0) + 1
    own = vehicle.get("college_group") or vehicle.get("college") or None
    gorder = {"male": 0, "female": 1} if vehicle["driver_gender"] == "male" else {"female": 0, "male": 1}

    def key(m):
        k = m.get("college_group") or m.get("college") or ""
        return (0 if own and k == own else 1, -count[k], k, gorder.get(m["gender"], 2), m["user_id"])
    return sorted(pool, key=key)


def plan_assignment(members, vehicles, keep_existing=False, combine_below=2, no_lone_female=False):
    """members : [{user_id, gender('male'|'female'), dirs:set, current_vehicle_id, category('dekat'|'jauh'|None),
                   zone(pilihan), college(pilihan), college_group(pilihan)}]  (sudah tersusun)
    vehicles: [{id, type('car'|'motorcycle'), driver_gender, rows:[int], category, zone(pilihan), college(pilihan)}]
    keep_existing: kekalkan ahli yang sudah ada kenderaan sah (selepas senarai disahkan);
                   hanya ahli tanpa kenderaan diisi ke seat kosong (tiada pemindahan).
    combine_below: kenderaan yang membawa <= N penumpang boleh dibubarkan jika penumpangnya muat di kenderaan lain
                   (hanya semasa susunan penuh, bukan selepas senarai dikunci). 0 = matikan.
    no_lone_female: kereta pemandu lelaki tak boleh ada tepat seorang penumpang perempuan.
    Return {user_id: vehicle_id | None}"""
    ordered = sorted(vehicles, key=lambda v: 0 if v["type"] == "car" else 1)  # kereta dahulu, kemudian motor
    valid = {v["id"] for v in ordered}
    result = {m["user_id"]: None for m in members}
    onboard = {v["id"]: [] for v in ordered}
    locked = set()
    by_id = {m["user_id"]: m for m in members}

    def pool(zone=None, any_zone=True):
        return [m for m in members if result[m["user_id"]] is None
                and (any_zone or _zone(m) == zone)]

    def fill(v, cands):
        lone = no_lone_female and _male_car(v)
        return _fill(_configs_for(v), onboard[v["id"]], _order_pool(cands, v), lone)

    def trim_partial(v, added, cands, later):
        """Kurangkan hentian prebet: jika kumpulan kolej terakhir cuma sebahagian muat dan masih ada prebet zon sama
        selepas ini, biarkan kumpulan itu kekal bersama untuk prebet seterusnya (baki dipenuhi semula di Fasa B)."""
        if not later or not added:
            return added
        key = lambda m: m.get("college_group") or m.get("college") or ""
        groups = []
        for m in added:
            if key(m) not in groups:
                groups.append(key(m))
        if len(groups) < 2:
            return added
        last = groups[-1]
        whole = [m for m in cands if key(m) == last]
        if len(whole) == len([m for m in added if key(m) == last]):
            return added  # kumpulan itu muat penuh
        kept = [m for m in added if key(m) != last]
        if no_lone_female and has_lone_female(v, onboard[v["id"]] + kept):
            return added
        return kept

    def place(v, added):
        for m in added or []:
            result[m["user_id"]] = v["id"]
            onboard[v["id"]].append(m)

    # Seorang sahaja bagi sesuatu jantina -> utamakan motosikal (rider sama jantina), bukan kereta
    lone_ids = set()
    for g in ("male", "female"):
        gm = [m for m in members if m["gender"] == g and m["dirs"]]
        if len(gm) == 1:
            lone_ids.add(gm[0]["user_id"])

    if keep_existing:
        for m in members:
            vid = m.get("current_vehicle_id")
            if vid in valid:
                onboard[vid].append(m)
                result[m["user_id"]] = vid
        for v in ordered:
            # Kalau ahli sedia ada tak muat langsung (cth: BKK tetapkan manual), kekalkan tetapi jangan tambah
            if onboard[v["id"]] and _fill(_configs_for(v), onboard[v["id"]], []) is None:
                locked.add(v["id"])

    for uid in sorted(lone_ids):
        m = by_id[uid]
        if result[uid] is not None:
            continue
        pref = ZONE_PREF.get(_zone(m), ZONE_PREF[None])
        motors = [v for v in ordered if v["type"] == "motorcycle" and v["id"] not in locked
                  and can_add(v, onboard[v["id"]], m)]
        motors.sort(key=lambda w: (pref.index(_zone(w)) if _zone(w) in pref else 3, w["id"]))
        if motors:
            place(motors[0], [m])

    for vtypes in (("car",), ("motorcycle",)):   # kereta penuh dahulu, baru motosikal
        group = [v for v in ordered if v["type"] in vtypes and v["id"] not in locked]
        # Keutamaan zon penumpang bagi setiap prebet (kolej prebet sendiri sentiasa didahulukan dalam setiap zon)
        for rank in range(3):
            if rank == 0:
                seq = [v for z in ("dekat", "jauhA", "jauhB") for v in group if _zone(v) == z] \
                    + [v for v in group if _zone(v) is None]
            else:   # kenderaan yang sudah berjalan dahulu (kurangkan bilangan kereta), baru yang masih kosong
                seq = [v for v in group if onboard[v["id"]]] + [v for v in group if not onboard[v["id"]]]
            for i, v in enumerate(seq):
                zone = ZONE_PREF.get(_zone(v), ZONE_PREF[None])[rank]
                if rank == 0 and _zone(v) is None:
                    pass
                cands = pool(zone, any_zone=False)
                if not cands:
                    continue
                later = rank == 0 and any(_zone(w) == _zone(v) for w in seq[i + 1:])
                place(v, trim_partial(v, fill(v, cands), cands, later))
        # Jalan terakhir: apa-apa baki yang masih ada (zon tak dikenali) mengikut adab
        for v in [x for x in group if onboard[x["id"]]] + [x for x in group if not onboard[x["id"]]]:
            if pool():
                place(v, fill(v, pool()))

    # Fasa C: bubarkan kenderaan yang membawa terlalu sedikit penumpang jika semuanya muat di kenderaan lain
    if combine_below and not keep_existing:
        changed = True
        while changed:
            changed = False
            for v in sorted((x for x in ordered if 0 < len(onboard[x["id"]]) <= combine_below),
                            key=lambda x: (len(onboard[x["id"]]), -x["id"])):
                if v["type"] == "motorcycle" and any(m["user_id"] in lone_ids for m in onboard[v["id"]]):
                    continue   # seorang sahaja jantina itu: kekal di motosikal
                targets = [w for w in ordered if w["id"] != v["id"] and w["id"] not in locked and onboard[w["id"]]]
                trial = {w["id"]: list(onboard[w["id"]]) for w in targets}
                moves = {}
                ok = True
                for m in onboard[v["id"]]:
                    # utamakan kenderaan sama zon, kemudian yang lain
                    cand = sorted(targets, key=lambda w: 0 if _zone(w) == _zone(m) else 1)
                    dest = next((w for w in cand if can_add(w, trial[w["id"]], m, no_lone_female)), None)
                    if dest is None:
                        ok = False
                        break
                    trial[dest["id"]].append(m)
                    moves[m["user_id"]] = dest["id"]
                if ok:
                    for uid, wid in moves.items():
                        result[uid] = wid
                        onboard[wid].append(by_id[uid])
                    onboard[v["id"]] = []
                    changed = True
                    break
    return result


def lone_female_cases(members, vehicles, result):
    """Ahli perempuan tanpa kenderaan yang SEBENARNYA muat dalam sesebuah kereta pemandu lelaki,
    tetapi akan jadi perempuan tunggal di situ (melanggar peraturan). Perlu keputusan admin.
    Return [user_id]."""
    onboard = {v["id"]: [m for m in members if result.get(m["user_id"]) == v["id"]] for v in vehicles}
    out = []
    for m in members:
        if result.get(m["user_id"]) is not None or m["gender"] != "female":
            continue
        for v in vehicles:
            if _male_car(v) and has_lone_female(v, onboard[v["id"]] + [m]) \
                    and _fill(_configs_for(v), onboard[v["id"]] + [m], []) is not None:
                out.append(m["user_id"])
                break
    return out


# ---------------------------------------------------------------- kerusi (paparan & susunan manual)

def seat_list(rows: list[int]) -> list[tuple[int, int]]:
    """Semua kerusi penumpang (baris, lajur), dari hadapan, kiri ke kanan. Baris 0 = sebelah driver."""
    return [(r, c) for r, n in enumerate(rows) for c in range(n)]


def check_layout(vtype: str, driver_gender: str, rows: list[int], occ: list[dict]) -> str | None:
    """occ: [{row, col, gender}] untuk SATU arah dalam SATU kenderaan. Return mesej ralat atau None jika sah."""
    seen = set()
    for o in occ:
        r, c = o["row"], o["col"]
        if r < 0 or r >= len(rows) or c < 0 or c >= rows[r]:
            return "Kerusi itu tak wujud dalam kenderaan ini"
        if (r, c) in seen:
            return "Kerusi itu sudah diduduki"
        seen.add((r, c))
    if vtype == "motorcycle":
        if any(o["gender"] != driver_gender for o in occ):
            return "Motosikal: penumpang mesti sama jantina dengan rider"
        return None
    if driver_gender == "female":
        if any(o["gender"] != "female" for o in occ):
            return "Driver perempuan: penumpang perempuan sahaja"
        return None
    row_gender: dict[int, str] = {}
    for o in occ:
        if row_gender.setdefault(o["row"], o["gender"]) != o["gender"]:
            return "Satu baris mesti sama jantina (lelaki dan perempuan tak boleh sebaris)"
    if any(o["gender"] == "female" and o["row"] == 0 for o in occ):
        return "Perempuan tak boleh duduk sebelah driver lelaki"
    male_rows = [r for r, g in row_gender.items() if g == "male"]
    female_rows = [r for r, g in row_gender.items() if g == "female"]
    if male_rows and female_rows and max(male_rows) > min(female_rows):
        return "Lelaki tak boleh duduk di belakang perempuan"
    return None


def auto_seat(vtype: str, driver_gender: str, rows: list[int], members: list[dict]) -> dict | None:
    """members: [{user_id, gender}] -> {user_id: (baris, lajur)} ikut peraturan, atau None jika tak muat."""
    seats = seat_list(rows)
    if vtype == "motorcycle" or driver_gender == "female":
        if len(members) > len(seats):
            return None
        out = {m["user_id"]: seats[i] for i, m in enumerate(members)}
    else:
        males = [m for m in members if m["gender"] == "male"]
        females = [m for m in members if m["gender"] != "male"]
        out = None
        for k in range(len(rows) + 1):
            start = max(k, 1)
            male_seats = [s for s in seats if s[0] < k]
            female_seats = [s for s in seats if s[0] >= start]
            if len(male_seats) >= len(males) and len(female_seats) >= len(females):
                out = {m["user_id"]: male_seats[i] for i, m in enumerate(males)}
                out.update({m["user_id"]: female_seats[i] for i, m in enumerate(females)})
                break
        if out is None:
            return None
    g = {m["user_id"]: m["gender"] for m in members}
    if check_layout(vtype, driver_gender, rows, [{"row": r, "col": c, "gender": g[u]} for u, (r, c) in out.items()]):
        return None
    return out


def complete_layout(vtype: str, driver_gender: str, rows: list[int], members: list[dict], stored: dict) -> dict | None:
    """Guna kerusi tersimpan (pilihan admin) yang sah; letak ahli lain di kerusi kosong yang dibenarkan.
    Jika gagal, susun semula sepenuhnya secara automatik. stored: {user_id: (r, c)}"""
    g = {m["user_id"]: m["gender"] for m in members}
    keep = {u: s for u, s in stored.items() if u in g}
    occ = [{"row": r, "col": c, "gender": g[u]} for u, (r, c) in keep.items()]
    if not check_layout(vtype, driver_gender, rows, occ):
        free = [s for s in seat_list(rows) if s not in set(keep.values())]
        ok = True
        for m in members:
            if m["user_id"] in keep:
                continue
            for s in free:
                trial = occ + [{"row": s[0], "col": s[1], "gender": m["gender"]}]
                if not check_layout(vtype, driver_gender, rows, trial):
                    keep[m["user_id"]] = s
                    occ = trial
                    free.remove(s)
                    break
            else:
                ok = False
                break
        if ok:
            return keep
    return auto_seat(vtype, driver_gender, rows, members)
