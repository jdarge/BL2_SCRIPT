import binascii
import hashlib
import struct

from compress import compress, decompress
from data import xor_data, rotate_data_left, rotate_data_right
from error import ERRNO
from read import ReadBitstream, read_repeated_protobuf_value
from table import item_header_sizes, black_market_keys, item_sizes
from tree import *
from write import WriteBitstream, write_repeated_protobuf_value


def pack_item_values(is_weapon, values):
    i = 0
    input_bytes = [0] * 32
    for value, size in zip(values, item_sizes[is_weapon]):
        if value is None:
            break
        j = i >> 3
        value = value << (i & 7)
        while value != 0:
            input_bytes[j] |= value & 0xff
            value = value >> 8
            j = j + 1
        i = i + size
    if (i & 7) != 0:
        value = 0xff << (i & 7)
        input_bytes[i >> 3] |= (value & 0xff)
    return "".join(map(chr, input_bytes[: (i + 7) >> 3]))


def unpack_item_values(is_weapon, data):
    i = 8
    data = " " + data
    values = []
    end = len(data) * 8
    for size in item_sizes[is_weapon]:
        j = i + size
        if j > end:
            values.append(None)
            continue
        value = 0
        for b in data[j >> 3: (i >> 3) - 1: -1]:
            value = (value << 8) | ord(b)
        values.append((value >> (i & 7)) & ~ (0xff << size))
        i = j
    return values


def wrap_item(is_weapon, values, key):
    item = pack_item_values(is_weapon, values)
    header = struct.pack(">Bi", (is_weapon << 7) | 7, key)
    padding = "\xff" * (33 - len(item))
    h = binascii.crc32(header + "\xff\xff" + item + padding) & 0xffffffff
    checksum = struct.pack(">H", ((h >> 16) ^ h) & 0xffff)
    body = xor_data(rotate_data_left(checksum + item, key & 31), key >> 5)
    return header + body


def unwrap_item(data):
    version_type, key = struct.unpack(">Bi", data[: 5])
    is_weapon = version_type >> 7
    raw = rotate_data_right(xor_data(data[5:], key >> 5), key & 31)
    return is_weapon, unpack_item_values(is_weapon, raw[2:]), key


def unwrap_bytes(value):
    return [ord(d) for d in value]


def wrap_bytes(value):
    return "".join(map(chr, value))


def unwrap_float(v):
    return struct.unpack("<f", struct.pack("<I", v))[0]


def wrap_float(v):
    return [5, struct.unpack("<I", struct.pack("<f", v))[0]]


def unwrap_item_info(value):
    is_weapon, item, key = unwrap_item(value)
    data = {
        "is_weapon": is_weapon,
        "key": key,
        "set": item[0],
        "level": [item[4], item[5]]
    }
    for i, (k, bits) in enumerate(item_header_sizes[is_weapon]):
        lib = item[1 + i] >> bits
        asset = item[1 + i] & ~ (lib << bits)
        data[k] = {"lib": lib, "asset": asset}
    bits = 10 + is_weapon
    parts = []
    for value in item[6:]:
        if value is None:
            parts.append(None)
        else:
            lib = value >> bits
            asset = value & ~ (lib << bits)
            parts.append({"lib": lib, "asset": asset})
    data["parts"] = parts
    return data


def wrap_item_info(value):
    item = [value["set"]]
    for key, bits in item_header_sizes[value["is_weapon"]]:
        v = value[key]
        item.append((v["lib"] << bits) | v["asset"])
    item.extend(value["level"])
    bits = 10 + value["is_weapon"]
    for v in value["parts"]:
        if v is None:
            item.append(None)
        else:
            item.append((v["lib"] << bits) | v["asset"])
    return wrap_item(value["is_weapon"], item, value["key"])


def unwrap_player_data(data):
    if data[: 20] != hashlib.sha1(data[20:]).digest():
        raise ERRNO("Invalid save file")

    data = decompress("\xf0" + data[20:])
    size, wsg, version = struct.unpack(">I3sI", data[: 11])
    if version != 2 and version != 0x02000000:
        raise ERRNO("Unknown save version " + str(version))

    if version == 2:
        crc, size = struct.unpack(">II", data[11: 19])
    else:
        crc, size = struct.unpack("<II", data[11: 19])

    bitstream = ReadBitstream(data[19:])
    tree = read_huffman_tree(bitstream)
    player = huffman_decompress(tree, bitstream, size)

    if (binascii.crc32(player) & 0xffffffff) != crc:
        raise ERRNO("CRC check failed")

    return player


def wrap_player_data(player):
    crc = binascii.crc32(player) & 0xffffffff

    bitstream = WriteBitstream()
    tree = make_huffman_tree(player)
    write_huffman_tree(tree, bitstream)
    huffman_compress(invert_tree(tree), player, bitstream)
    data = bitstream.getvalue() + "\x00\x00\x00\x00"

    header = struct.pack(">I3s", len(data) + 15, "WSG")
    header = header + struct.pack("<III", 2, crc, len(player))

    data = compress(header + data)[1:]

    return hashlib.sha1(data).digest() + data


def unwrap_black_market(value):
    sdus = read_repeated_protobuf_value(value, 0)
    return dict(zip(black_market_keys, sdus))


def wrap_black_market(value):
    sdus = [value[k] for k in black_market_keys[: len(value)]]
    return write_repeated_protobuf_value(sdus, 0)


save_structure = {
    1: "class",
    2: "level",
    3: "experience",
    4: "skill_points",
    6: ("currency", True, 0),
    7: "playthroughs_completed",
    8: ("skills", True, {
        1: "name",
        2: "level",
        3: "unknown3",
        4: "unknown4"
    }),
    11: ("resources", True, {
        1: "resource",
        2: "pool",
        3: ("amount", False, (unwrap_float, wrap_float)),
        4: "level"
    }),
    13: ("sizes", False, {
        1: "inventory",
        2: "weapon_slots",
        3: "weapon_slots_shown"
    }),
    15: ("stats", False, (unwrap_bytes, wrap_bytes)),
    16: ("active_fast_travel", True, None),
    17: "last_fast_travel",
    18: ("missions", True, {
        1: "playthrough",
        2: "active",
        3: ("data", True, {
            1: "name",
            2: "status",
            3: "is_from_dlc",
            4: "dlc_id",
            5: ("unknown5", False, (unwrap_bytes, wrap_bytes)),
            6: "unknown6",
            7: ("unknown7", False, (unwrap_bytes, wrap_bytes)),
            8: "unknown8",
            9: "unknown9",
            10: "unknown10",
            11: "level",
        }),
    }),
    19: ("appearance", False, {
        1: "name",
        2: ("color1", False, {1: "a", 2: "r", 3: "g", 4: "b"}),
        3: ("color2", False, {1: "a", 2: "r", 3: "g", 4: "b"}),
        4: ("color3", False, {1: "a", 2: "r", 3: "g", 4: "b"}),
    }),
    20: "save_game_id",
    21: "mission_number",
    23: ("unlocks", False, (unwrap_bytes, wrap_bytes)),
    24: ("unlock_notifications", False, (unwrap_bytes, wrap_bytes)),
    25: "time_played",
    26: "save_timestamp",
    29: ("game_stages", True, {
        1: "name",
        2: "level",
        3: "is_from_dlc",
        4: "dlc_id",
        5: "playthrough",
    }),
    30: ("areas", True, {
        1: "name",
        2: "unknown2"
    }),
    34: ("id", False, {
        1: ("a", False, 5),
        2: ("b", False, 5),
        3: ("c", False, 5),
        4: ("d", False, 5),
    }),
    35: ("wearing", True, None),
    36: ("black_market", False, (unwrap_black_market, wrap_black_market)),
    37: "active_mission",
    38: ("challenges", True, {
        1: "name",
        2: "is_from_dlc",
        3: "dlc_id"
    }),
    41: ("bank", True, {
        1: ("data", False, (unwrap_item_info, wrap_item_info)),
    }),
    43: ("lockouts", True, {
        1: "name",
        2: "time",
        3: "is_from_dlc",
        4: "dlc_id"
    }),
    46: ("explored_areas", True, None),
    49: "active_playthrough",
    53: ("items", True, {
        1: ("data", False, (unwrap_item_info, wrap_item_info)),
        2: "unknown2",
        3: "is_equipped",
        4: "star"
    }),
    54: ("weapons", True, {
        1: ("data", False, (unwrap_item_info, wrap_item_info)),
        2: "slot",
        3: "star",
        4: "unknown4",
    }),
    55: "stats_bonuses_disabled",
    56: "bank_size",
}
