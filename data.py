import binascii
import math
import struct
import random
from cStringIO import StringIO

from error import ERRNO
from presents import unwrap_player_data, unwrap_item, wrap_item, wrap_player_data
from read import read_repeated_protobuf_value, read_protobuf, read_protobuf_value
from write import write_protobuf_value, write_protobuf, write_repeated_protobuf_value


def rotate_data_right(data, steps):
    steps = steps % len(data)
    return data[-steps:] + data[: -steps]


def rotate_data_left(data, steps):
    steps = steps % len(data)
    return data[steps:] + data[: steps]


def xor_data(data, key):
    key = key & 0xffffffff
    output = ""
    for c in data:
        key = (key * 279470273) % 4294967291
        output += chr((ord(c) ^ key) & 0xff)
    return output


def replace_raw_item_key(data, key):
    old_key = struct.unpack(">i", data[1: 5])[0]
    item = rotate_data_right(xor_data(data[5:], old_key >> 5), old_key & 31)[2:]
    header = data[0] + struct.pack(">i", key)
    padding = "\xff" * (33 - len(item))
    h = binascii.crc32(header + "\xff\xff" + item + padding) & 0xffffffff
    checksum = struct.pack(">H", ((h >> 16) ^ h) & 0xffff)
    body = xor_data(rotate_data_left(checksum + item, key & 31), key >> 5)
    return header + body


def parse_zigzag(i):
    if i & 1:
        return -1 ^ (i >> 1)
    else:
        return i >> 1


def apply_structure(pbdata, s):
    fields = {}
    raw = {}
    for k, data in pbdata.items():
        mapping = s.get(k)
        if mapping is None:
            raw[k] = data
            continue
        elif type(mapping) is str:
            fields[mapping] = data[0][1]
            continue
        key, repeated, child_s = mapping
        if child_s is None:
            values = [d[1] for d in data]
            fields[key] = values if repeated else values[0]
        elif type(child_s) is int:
            if repeated:
                fields[key] = read_repeated_protobuf_value(data[0][1], child_s)
            else:
                fields[key] = data[0][1]
        elif type(child_s) is tuple:
            values = [child_s[0](d[1]) for d in data]
            fields[key] = values if repeated else values[0]
        elif type(child_s) is dict:
            values = [apply_structure(read_protobuf(d[1]), child_s) for d in data]
            fields[key] = values if repeated else values[0]
        else:
            raise Exception("Invalid mapping %r for %r: %r" % (mapping, k, data))
    if len(raw) != 0:
        fields["_raw"] = {}
        for k, values in raw.items():
            safe_values = []
            for (wire_type, v) in values:
                if wire_type == 2:
                    v = [ord(c) for c in v]
                safe_values.append([wire_type, v])
            fields["_raw"][k] = safe_values
    return fields


def remove_structure(data, inv):
    pbdata = {}
    pbdata.update(data.get("_raw", {}))
    for k, value in data.items():
        if k == "_raw":
            continue
        mapping = inv.get(k)
        if mapping is None:
            raise ERRNO("Unknown key %r in data" % (k,))
        elif type(mapping) is int:
            pbdata[mapping] = [[guess_wire_type(value), value]]
            continue
        key, repeated, child_inv = mapping
        if child_inv is None:
            value = [value] if not repeated else value
            pbdata[key] = [[guess_wire_type(v), v] for v in value]
        elif type(child_inv) is int:
            if repeated:
                b = StringIO()
                for v in value:
                    write_protobuf_value(b, child_inv, v)
                pbdata[key] = [[2, b.getvalue()]]
            else:
                pbdata[key] = [[child_inv, value]]
        elif type(child_inv) is tuple:
            value = [value] if not repeated else value
            values = []
            for v in map(child_inv[1], value):
                if type(v) is list:
                    values.append(v)
                else:
                    values.append([guess_wire_type(v), v])
            pbdata[key] = values
        elif type(child_inv) is dict:
            value = [value] if not repeated else value
            values = []
            for d in [remove_structure(v, child_inv) for v in value]:
                values.append([2, write_protobuf(d)])
            pbdata[key] = values
        else:
            raise Exception("Invalid mapping %r for %r: %r" % (mapping, k, value))
    return pbdata


def guess_wire_type(value):
    return 2 if isinstance(value, basestring) else 0


def invert_structure(structure):
    inv = {}
    for k, v in structure.items():
        if type(v) is tuple:
            if type(v[2]) is dict:
                inv[v[0]] = (k, v[1], invert_structure(v[2]))
            else:
                inv[v[0]] = (k,) + v[1:]
        else:
            inv[v] = k
    return inv


def expand_zeroes(src, ip, extra):
    start = ip
    while src[ip] == 0:
        ip = ip + 1
    v = ((ip - start) * 255) + src[ip]
    return v + extra, ip + 1


def copy_earlier(b, offset, n):
    i = len(b) - offset
    end = i + n
    while i < end:
        chunk = b[i: i + n]
        i = i + len(chunk)
        n = n - len(chunk)
        b.extend(chunk)


def modify_save(data, changes):
    player = read_protobuf(unwrap_player_data(data))

    if changes.has_key("level"):
        level = int(changes["level"])
        lower = int(60 * (level ** 2.8) - 59.2)
        upper = int(60 * ((level + 1) ** 2.8) - 59.2)
        if player[3][0][1] not in range(lower, upper):
            player[3][0][1] = lower
        player[2] = [[0, int(changes["level"])]]

    if changes.has_key("skillpoints"):
        player[4] = [[0, int(changes["skillpoints"])]]

    if any(map(changes.has_key, ("money", "eridium", "seraph", "tokens"))):
        raw = player[6][0][1]
        b = StringIO(raw)
        values = []
        while b.tell() < len(raw):
            values.append(read_protobuf_value(b, 0))
        if changes.has_key("money"):
            values[0] = int(changes["money"])
        if changes.has_key("eridium"):
            values[1] = int(changes["eridium"])
        if changes.has_key("seraph"):
            values[2] = int(changes["seraph"])
        if changes.has_key("tokens"):
            values[4] = int(changes["tokens"])
        player[6][0] = [0, values]

    if changes.has_key("itemlevels"):
        if changes["itemlevels"]:
            level = int(changes["itemlevels"])
        else:
            level = player[2][0][1]
        for field_number in (53, 54):
            for field in player[field_number]:
                field_data = read_protobuf(field[1])
                is_weapon, item, key = unwrap_item(field_data[1][0][1])
                if item[4] > 1:
                    item = item[: 4] + [level, level] + item[6:]
                    field_data[1][0][1] = wrap_item(is_weapon, item, key)
                    field[1] = write_protobuf(field_data)

    if changes.has_key("backpack"):
        size = int(changes["backpack"])
        sdus = int(math.ceil((size - 12) / 3.0))
        size = 12 + (sdus * 3)
        slots = read_protobuf(player[13][0][1])
        slots[1][0][1] = size
        player[13][0][1] = write_protobuf(slots)
        s = read_repeated_protobuf_value(player[36][0][1], 0)
        player[36][0][1] = write_repeated_protobuf_value(s[: 7] + [sdus] + s[8:], 0)

    if changes.has_key("bank"):
        size = int(changes["bank"])
        sdus = min(255, int(math.ceil((size - 6) / 2.0)))
        size = 6 + (sdus * 2)
        if player.has_key(56):
            player[56][0][1] = size
        else:
            player[56] = [[0, size]]
        s = read_repeated_protobuf_value(player[36][0][1], 0)
        if len(s) < 9:
            s = s + (9 - len(s)) * [0]
        player[36][0][1] = write_repeated_protobuf_value(s[: 8] + [sdus] + s[9:], 0)

    if changes.get("gunslots", "0") in "234":
        n = int(changes["gunslots"])
        slots = read_protobuf(player[13][0][1])
        slots[2][0][1] = n
        if slots[3][0][1] > n - 2:
            slots[3][0][1] = n - 2
        player[13][0][1] = write_protobuf(slots)

    if changes.has_key("unlocks"):
        unlocked, notifications = [], []
        if player.has_key(23):
            unlocked = map(ord, player[23][0][1])
        if player.has_key(24):
            notifications = map(ord, player[24][0][1])
        unlocks = changes["unlocks"].split(":")
        if "slaughterdome" in unlocks:
            if 1 not in unlocked:
                unlocked.append(1)
            if 1 not in notifications:
                notifications.append(1)
        if unlocked:
            player[23] = [[2, "".join(map(chr, unlocked))]]
        if notifications:
            player[24] = [[2, "".join(map(chr, notifications))]]
        if "truevaulthunter" in unlocks:
            if player[7][0][1] < 1:
                player[7][0][1] = 1

    return wrap_player_data(write_protobuf(player))


def export_items(data, output):
    player = read_protobuf(unwrap_player_data(data))
    for i, name in ((41, "Bank"), (53, "Items"), (54, "Weapons")):
        content = player.get(i)
        if content is None:
            continue
        print >> output, "; " + name
        for field in content:
            raw = read_protobuf(field[1])[1][0][1]
            raw = replace_raw_item_key(raw, 0)
            code = "BL2(" + raw.encode("base64").strip() + ")"
            print >> output, code


def import_items(data, codelist):
    player = read_protobuf(unwrap_player_data(data))

    to_bank = False
    for line in codelist.splitlines():
        line = line.strip()
        if line.startswith(";"):
            name = line[1:].strip().lower()
            if name == "bank":
                to_bank = True
            elif name in ("items", "weapons"):
                to_bank = False
            continue
        elif line[: 4] + line[-1:] != "BL2()":
            continue

        code = line[4: -1]
        try:
            raw = code.decode("base64")
        except binascii.Error:
            continue

        key = random.randrange(0x100000000) - 0x80000000
        raw = replace_raw_item_key(raw, key)
        if to_bank:
            field = 41
            entry = {1: [[2, raw]]}
        elif (ord(raw[0]) & 0x80) == 0:
            field = 53
            entry = {1: [[2, raw]], 2: [[0, 1]], 3: [[0, 0]], 4: [[0, 1]]}
        else:
            field = 53
            entry = {1: [[2, raw]], 2: [[0, 0]], 3: [[0, 1]]}

        player.setdefault(field, []).append([2, write_protobuf(entry)])

    return wrap_player_data(write_protobuf(player))
