item_sizes = (
    (8, 17, 20, 11, 7, 7, 16, 16, 16, 16, 16, 16, 16, 16, 16, 16, 16),
    (8, 13, 20, 11, 7, 7, 17, 17, 17, 17, 17, 17, 17, 17, 17, 17, 17)
)

black_market_keys = (
    "rifle", "pistol", "launcher", "shotgun", "smg",
    "sniper", "grenade", "backpack", "bank"
)

clz_table = (
    32, 0, 1, 26, 2, 23, 27, 0, 3, 16, 24, 30, 28, 11, 0, 13, 4,
    7, 17, 0, 25, 22, 31, 15, 29, 10, 12, 6, 0, 21, 14, 9, 5,
    20, 8, 19, 18
)

item_header_sizes = (
    (("type", 8), ("balance", 10), ("manufacturer", 7)),
    (("type", 6), ("balance", 10), ("manufacturer", 7))
)
