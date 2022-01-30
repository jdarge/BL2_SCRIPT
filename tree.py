from bisect import insort


def read_huffman_tree(b):
    node_type = b.read_bit()
    if node_type == 0:
        return None, (read_huffman_tree(b), read_huffman_tree(b))
    else:
        return None, b.read_byte()


def write_huffman_tree(node, b):
    if type(node[1]) is int:
        b.write_bit(1)
        b.write_byte(node[1])
    else:
        b.write_bit(0)
        write_huffman_tree(node[1][0], b)
        write_huffman_tree(node[1][1], b)


def make_huffman_tree(data):
    frequencies = [0] * 256
    for c in data:
        frequencies[ord(c)] += 1

    nodes = [[f, i] for (i, f) in enumerate(frequencies) if f != 0]
    nodes.sort()

    while len(nodes) > 1:
        l, r = nodes[: 2]
        nodes = nodes[2:]
        insort(nodes, [l[0] + r[0], [l, r]])

    return nodes[0]


def invert_tree(node, code=0, bits=0):
    if type(node[1]) is int:
        return {chr(node[1]): (code, bits)}
    else:
        d = {}
        d.update(invert_tree(node[1][0], code << 1, bits + 1))
        d.update(invert_tree(node[1][1], (code << 1) | 1, bits + 1))
        return d


def huffman_decompress(tree, bitstream, size):
    output = ""
    while len(output) < size:
        node = tree
        while 1:
            b = bitstream.read_bit()
            node = node[1][b]
            if type(node[1]) is int:
                output += chr(node[1])
                break
    return output


def huffman_compress(encoding, data, bitstream):
    for c in data:
        code, nbits = encoding[c]
        bitstream.write_bits(code, nbits)
