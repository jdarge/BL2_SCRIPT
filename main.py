import json
import optparse
import sys

from data import modify_save, export_items, import_items, apply_structure, remove_structure, invert_structure
from presents import unwrap_player_data, save_structure, wrap_player_data
from read import read_protobuf
from write import write_protobuf


def main():
    if len(args) >= 2 and args[0] != "-" and args[0] == args[1]:
        print >> sys.stderr, "Cannot overwrite the save file, please use a different filename for the new save."
        return

    if len(args) < 1 or args[0] == "-":
        input = sys.stdin
    else:
        input = open(args[0], "rb")

    if len(args) < 2 or args[1] == "-":
        output = sys.stdout
    else:
        output = open(args[1], "wb")

    if options.modify is not None:
        changes = {}
        if options.modify:
            for m in options.modify.split(","):
                k, v = (m.split("=", 1) + [None])[: 2]
                changes[k] = v
        output.write(modify_save(input.read(), changes))
    elif options.export_items:
        output = open(options.export_items, "w")
        export_items(input.read(), output)
    elif options.import_items:
        itemlist = open(options.import_items, "r")
        output.write(import_items(input.read(), itemlist.read()))
    elif options.decode:
        savegame = input.read()
        player = unwrap_player_data(savegame)
        if options.json:
            data = read_protobuf(player)
            if options.parse:
                data = apply_structure(data, save_structure)
            player = json.dumps(data, encoding="latin1", sort_keys=True, indent=4)
        output.write(player)
    else:
        player = input.read()
        if options.json:
            data = json.loads(player, encoding="latin1")
            if not data.has_key("1"):
                data = remove_structure(data, invert_structure(save_structure))
            player = write_protobuf(data)
        savegame = wrap_player_data(player)
        output.write(savegame)


def parse_args():
    p = optparse.OptionParser()
    p.add_option(
        "-d", "--decode",
        action="store_true",
        help="read from a save game, rather than creating one"
    )
    p.add_option(
        "-e", "--export-items", metavar="FILENAME",
        help="save out codes for all bank and inventory items"
    )
    p.add_option(
        "-i", "--import-items", metavar="FILENAME",
        help="read in codes for items and add them to the bank and inventory"
    )
    p.add_option(
        "-j", "--json",
        action="store_true",
        help="read or write save game data in JSON format, rather than raw protobufs"
    )
    p.add_option(
        "-m", "--modify", metavar="MODIFICATIONS",
        help="comma separated list of modifications to make, eg money=99999999,eridium=99"
    )
    p.add_option(
        "-p", "--parse",
        action="store_true",
        help="parse the protocol buffer data further and generate more readable JSON"
    )
    return p.parse_args()


if __name__ == "__main__":
    options, args = parse_args()
    try:
        main()
    except Exception:
        print >> sys.stderr, repr(sys.argv)
        raise
