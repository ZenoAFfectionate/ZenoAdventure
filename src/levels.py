"""Hand-authored level layouts assembled on a fixed tile grid.

The small builder keeps routes aligned while the placement lists make each
challenge and optional reward path easy to audit. Every level is completable
without a character skill; skills provide safer or faster alternatives.
"""


def _make_level(width, ground_row, gaps, platforms, objects, fills=()):
    height = 12
    grid = [[" " for _ in range(width)] for _ in range(height)]
    gap_cols = {col for start, length in gaps for col in range(start, start + length)}
    for row in range(ground_row, height):
        for col in range(width):
            if col not in gap_cols:
                grid[row][col] = "#"
    for row, start, length, tile in fills:
        for col in range(start, min(width, start + length)):
            grid[row][col] = tile
    for row, start, length, tile in platforms:
        for col in range(start, min(width, start + length)):
            grid[row][col] = tile
    for col, row, tile in objects:
        grid[row][col] = tile
    return ["".join(row).rstrip() for row in grid]


LEVELS = [
    {
        "name": "Green Hills",
        "theme": "grass",
        "time_limit": 130,
        "map": _make_level(
            92, 9, [(8, 3), (34, 2), (60, 3)],
            [(6, 17, 7, "-"), (6, 39, 5, "-"), (6, 66, 6, "~")],
            [
                (2, 8, "P"), (6, 8, "o"), (9, 7, "O"), (12, 8, "e"),
                (15, 8, "j"), (18, 5, "o"), (20, 5, "g"), (22, 5, "o"),
                (20, 8, "@"),
                (28, 8, "e"), (32, 8, "c"), (38, 8, "F"),
                (40, 5, "b"), (42, 5, "0"), (44, 6, "o"),
                (45, 7, "o"), (46, 8, "*"), (47, 8, "n"), (50, 8, "@"),
                (54, 8, "K"), (58, 8, "k"), (61, 8, "j"),
                (65, 8, "F"),
                (67, 5, "o"), (69, 5, "r"), (71, 5, "o"),
                (75, 8, "@"), (76, 8, "e"), (82, 8, "H"), (88, 8, "D"),
            ],
        ),
    },
    {
        "name": "Desert Dash",
        "theme": "desert",
        "time_limit": 145,
        # Conveyor teaching combo (cols 32-43): safe ground -> right belt ->
        # small pit -> left belt (never followed by a pit) -> single spike ->
        # safe zone.  Belts stay weak enough to counter-steer.
        "map": _make_level(
            100, 9, [(11, 3), (36, 2), (50, 3), (76, 3)],
            [(6, 15, 6, "-"), (5, 44, 7, "-"), (6, 57, 5, "~"), (4, 80, 8, "-")],
            [
                (2, 8, "P"), (4, 8, "K"), (6, 8, "+"), (7, 6, "q"), (10, 8, "j"),
                (16, 5, "o"), (18, 5, "O"), (20, 5, "g"), (24, 3, "q"),
                (24, 8, "F"),
                (32, 9, ">"), (33, 9, ">"), (34, 9, ">"), (35, 9, ">"),
                (38, 9, "<"), (39, 9, "<"), (40, 9, "<"), (42, 8, "^"),
                (44, 8, "+"), (45, 4, "b"), (48, 4, "0"), (45, 3, "v"),
                (52, 8, "c"),
                (55, 8, "F"), (56, 8, "c"), (58, 5, "o"), (60, 5, "r"),
                (64, 3, "v"), (66, 3, "q"), (68, 9, "<"), (69, 9, "<"),
                (74, 8, "k"),
                (78, 8, "j"), (80, 8, "o"), (81, 3, "*"), (84, 3, "y"),
                (82, 8, "F"), (87, 3, "0"), (88, 8, "H"), (90, 8, "+"),
                (91, 8, "^"), (96, 8, "D"),
            ],
        ),
    },
    {
        "name": "Crystal Cave",
        "theme": "cave",
        "time_limit": 165,
        # Pool teaching curve: a raised shelf (cols 43-44, waist-deep water)
        # demonstrates the slow-down before the deep zone (cols 45-48).
        # A submerged one-way ledge (row 9, cols 47-48) guarantees a way out
        # even without bouncing off the fish.  No oxygen timer by design.
        "map": _make_level(
            104, 9, [(18, 2), (43, 6), (69, 2), (89, 3)],
            [(6, 10, 8, "-"), (4, 26, 8, "-"), (6, 42, 16, "~"),
             (9, 47, 2, "-"), (4, 73, 9, "-"), (6, 94, 7, "~")],
            [
                (2, 8, "P"), (7, 8, "n"), (10, 5, "o"), (12, 5, "b"),
                (15, 8, "m"), (16, 8, "j"), (22, 8, "e"), (27, 3, "g"),
                (30, 3, "0"), (32, 3, "z"),
                (33, 8, "I"), (33, 7, "I"), (33, 6, "I"), (33, 5, "I"),
                (36, 8, "^"), (37, 8, "T"),
                (41, 8, "c"), (45, 8, "u"), (46, 9, "w"), (47, 10, "f"),
                (48, 8, "F"), (51, 5, "o"), (54, 5, "r"),
                (50, 8, "K"), (55, 8, "m"), (59, 8, "a"), (63, 8, "e"),
                (72, 8, "I"), (72, 7, "I"), (72, 6, "I"),
                (72, 5, "I"), (75, 3, "*"), (78, 3, "y"),
                (83, 3, "q"), (87, 8, "k"), (92, 8, "F"), (93, 8, "o"),
                (95, 8, "T"), (96, 5, "0"), (97, 8, "H"), (98, 8, "D"),
            ],
            [(8, 43, 2, "W"), (9, 43, 2, "W"), (10, 43, 2, "X"),
             (8, 45, 4, "W"), (9, 45, 4, "W"), (10, 45, 4, "W"),
             (11, 43, 6, "X")],
        ),
    },
    {
        "name": "Lava Lake",
        "theme": "lava",
        "time_limit": 175,
        # Second-half rhythm change: a flush spring (95,9) launches the player
        # over the final lava pit through a coin arc instead of adding more
        # pits; a frog guards the landing zone.
        "map": _make_level(
            112, 9, [(13, 3), (31, 3), (52, 3), (74, 3), (96, 3)],
            [(6, 17, 7, "-"), (5, 37, 8, "~"), (6, 58, 8, "-"),
             (4, 79, 9, "-"), (6, 101, 7, "~")],
            [
                (2, 8, "P"), (8, 8, "a"), (10, 8, "T"), (12, 8, "j"),
                (18, 5, "o"),
                (21, 5, "r"), (26, 8, "s"), (30, 8, "j"),
                (38, 4, "b"), (41, 4, "*"), (45, 8, "T"), (46, 8, "q"),
                (49, 8, "c"),
                (57, 8, "F"), (60, 5, "O"), (63, 5, "g"), (68, 8, "h"),
                (70, 8, "T"), (73, 8, "j"), (80, 3, "0"), (83, 3, "y"),
                (86, 3, "H"),
                (88, 8, "F"),
                (91, 8, "z"), (94, 8, "K"), (95, 9, "j"),
                (96, 5, "o"), (97, 4, "0"), (98, 5, "o"),
                (100, 8, "k"),
                (103, 5, "o"), (105, 8, "h"), (106, 5, "0"), (108, 8, "T"),
                (110, 8, "D"),
            ],
            [(9, 13, 3, "L"), (9, 31, 3, "L"), (9, 52, 3, "L"),
             (9, 74, 3, "L"), (9, 96, 3, "L")],
        ),
    },
    {
        "name": "Sky Temple",
        "theme": "sky",
        "time_limit": 220,
        # Anti-bypass rework: the bottom floor is split into four recovery
        # islands separated by unjumpable voids, so falling no longer offers
        # a free ride to the exit.  Each island carries springs that launch
        # the player back onto the aerial route (recoverable, never a soft
        # lock).  Lock and door live on the upper route.  'V' vertical
        # shuttles debut at low speed.  The finale (cols 98-119) pairs a
        # tracked saw and an armoured slime with the Block Guardian
        # mini-boss, which seals the exit door until it falls.
        "map": _make_level(
            120, 11, [(14, 6), (36, 6), (57, 7), (79, 41)],
            [(8, 0, 10, "#"), (8, 13, 8, "-"), (7, 25, 7, "-"),
             (8, 36, 6, "#"), (7, 46, 7, "~"), (8, 56, 7, "#"),
             (6, 69, 7, "-"), (6, 79, 8, "-"), (8, 90, 8, "#"),
             (8, 101, 18, "#")],
            [
                (1, 7, "T"), (2, 7, "P"), (5, 7, "K"), (7, 7, "o"),
                (11, 7, "M"),
                (16, 7, "q"), (19, 7, "O"), (22, 7, "M"),
                (27, 6, "e"), (30, 6, "c"), (33, 7, "M"),
                (38, 7, "F"), (41, 7, "s"), (44, 7, "M"),
                (48, 5, "b"), (50, 5, "*"), (52, 5, "g"), (55, 7, "M"),
                (58, 7, "a"), (65, 8, "V"),
                (70, 5, "F"), (75, 4, "r"),
                (80, 5, "0"), (83, 5, "y"), (85, 5, "H"),
                (92, 7, "Z"), (95, 7, "k"), (97, 7, "F"), (100, 8, "V"),
                (110, 7, "G"),
                (113, 6, "0"), (117, 7, "T"), (118, 7, "D"),
                # Recovery-island springs (mid + right edge, so anyone
                # running along an island meets one before the void).
                (5, 11, "j"), (13, 11, "j"),
                (24, 11, "j"), (33, 11, "j"),
                (46, 11, "j"), (56, 11, "j"),
                (68, 11, "j"), (78, 11, "j"),
            ],
        ),
    },
]
