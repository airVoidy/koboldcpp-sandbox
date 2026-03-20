from __future__ import annotations

from dataclasses import dataclass
from itertools import permutations

HOUSE_INDEXES = (0, 1, 2, 3, 4)

COLOR_ORDER = ("red", "green", "white", "yellow", "blue")
NATION_ORDER = ("englishman", "spaniard", "ukrainian", "norwegian", "japanese")
DRINK_ORDER = ("coffee", "tea", "milk", "orange-juice", "water")
SMOKE_ORDER = ("old-gold", "kool", "chesterfield", "lucky-strike", "parliament")
PET_ORDER = ("dog", "snails", "fox", "horse", "zebra")


@dataclass(frozen=True)
class EinsteinReferenceSolution:
    color: tuple[str, ...]
    nation: tuple[str, ...]
    drink: tuple[str, ...]
    smoke: tuple[str, ...]
    pet: tuple[str, ...]

    def as_state(self) -> dict[str, list[str]]:
        return {
            "color": list(self.color),
            "nation": list(self.nation),
            "drink": list(self.drink),
            "smoke": list(self.smoke),
            "pet": list(self.pet),
        }

    def house_rows(self) -> list[dict[str, str]]:
        return [
            {
                "house": f"house-{index + 1}",
                "color": self.color[index],
                "nation": self.nation[index],
                "drink": self.drink[index],
                "smoke": self.smoke[index],
                "pet": self.pet[index],
            }
            for index in HOUSE_INDEXES
        ]


def _invert_positions(order: tuple[str, ...], positions: tuple[int, ...]) -> tuple[str, ...]:
    values = [""] * len(order)
    for value, house_index in zip(order, positions, strict=True):
        values[house_index] = value
    return tuple(values)


def solve_einstein_reference() -> EinsteinReferenceSolution:
    first = 0
    middle = 2

    for colors in permutations(HOUSE_INDEXES):
        red, green, white, yellow, blue = colors
        if green != white + 1:
            continue

        for nations in permutations(HOUSE_INDEXES):
            englishman, spaniard, ukrainian, norwegian, japanese = nations
            if norwegian != first:
                continue
            if englishman != red:
                continue
            if abs(norwegian - blue) != 1:
                continue

            for drinks in permutations(HOUSE_INDEXES):
                coffee, tea, milk, orange_juice, water = drinks
                if milk != middle:
                    continue
                if coffee != green:
                    continue
                if tea != ukrainian:
                    continue

                for smokes in permutations(HOUSE_INDEXES):
                    old_gold, kool, chesterfield, lucky_strike, parliament = smokes
                    if kool != yellow:
                        continue
                    if lucky_strike != orange_juice:
                        continue
                    if japanese != parliament:
                        continue

                    for pets in permutations(HOUSE_INDEXES):
                        dog, snails, fox, horse, zebra = pets
                        if spaniard != dog:
                            continue
                        if old_gold != snails:
                            continue
                        if abs(chesterfield - fox) != 1:
                            continue
                        if abs(kool - horse) != 1:
                            continue

                        return EinsteinReferenceSolution(
                            color=_invert_positions(COLOR_ORDER, colors),
                            nation=_invert_positions(NATION_ORDER, nations),
                            drink=_invert_positions(DRINK_ORDER, drinks),
                            smoke=_invert_positions(SMOKE_ORDER, smokes),
                            pet=_invert_positions(PET_ORDER, pets),
                        )

    raise RuntimeError("No Einstein solution found.")


def solve_einstein_reference_staged() -> EinsteinReferenceSolution:
    idx = lambda houses, value_idx: houses.index(value_idx)
    all_permutations = tuple(permutations(HOUSE_INDEXES))

    solve_step = lambda current_states, next_perms, filter_func: [
        state + (permutation,)
        for state in current_states
        for permutation in next_perms
        if filter_func(state + (permutation,))
    ]

    f_colors = lambda state: idx(state[0], 1) == idx(state[0], 2) + 1
    f_nations = lambda state: (
        idx(state[1], 3) == 0
        and idx(state[1], 0) == idx(state[0], 0)
        and abs(idx(state[1], 3) - idx(state[0], 4)) == 1
    )
    f_drinks = lambda state: (
        state[2][2] == 2
        and idx(state[2], 0) == idx(state[0], 1)
        and idx(state[2], 1) == idx(state[1], 2)
    )
    f_smokes = lambda state: (
        idx(state[3], 1) == idx(state[0], 3)
        and idx(state[3], 3) == idx(state[2], 3)
        and idx(state[1], 4) == idx(state[3], 4)
    )
    f_pets = lambda state: (
        idx(state[1], 1) == idx(state[4], 0)
        and idx(state[3], 0) == idx(state[4], 1)
        and abs(idx(state[3], 2) - idx(state[4], 2)) == 1
        and abs(idx(state[3], 1) - idx(state[4], 3)) == 1
    )

    states: list[tuple[tuple[int, ...], ...]] = [()]
    states = solve_step(states, all_permutations, f_colors)
    states = solve_step(states, all_permutations, f_nations)
    states = solve_step(states, all_permutations, f_drinks)
    states = solve_step(states, all_permutations, f_smokes)
    states = solve_step(states, all_permutations, f_pets)

    if len(states) != 1:
        raise RuntimeError(f"Expected exactly one staged Einstein solution, got {len(states)}.")

    color_houses, nation_houses, drink_houses, smoke_houses, pet_houses = states[0]
    return EinsteinReferenceSolution(
        color=tuple(COLOR_ORDER[value_index] for value_index in color_houses),
        nation=tuple(NATION_ORDER[value_index] for value_index in nation_houses),
        drink=tuple(DRINK_ORDER[value_index] for value_index in drink_houses),
        smoke=tuple(SMOKE_ORDER[value_index] for value_index in smoke_houses),
        pet=tuple(PET_ORDER[value_index] for value_index in pet_houses),
    )


def render_reference_stage_counts() -> str:
    idx = lambda positions, value_idx: positions.index(value_idx)
    all_permutations = tuple(permutations(HOUSE_INDEXES))

    solve_step = lambda current_states, next_perms, filter_func: [
        state + (permutation,)
        for state in current_states
        for permutation in next_perms
        if filter_func(state + (permutation,))
    ]

    f_colors = lambda state: idx(state[0], 1) == idx(state[0], 2) + 1
    f_nations = lambda state: (
        idx(state[1], 3) == 0
        and idx(state[1], 0) == idx(state[0], 0)
        and abs(idx(state[1], 3) - idx(state[0], 4)) == 1
    )
    f_drinks = lambda state: (
        state[2][2] == 2
        and idx(state[2], 0) == idx(state[0], 1)
        and idx(state[2], 1) == idx(state[1], 2)
    )
    f_smokes = lambda state: (
        idx(state[3], 1) == idx(state[0], 3)
        and idx(state[3], 3) == idx(state[2], 3)
        and idx(state[1], 4) == idx(state[3], 4)
    )
    f_pets = lambda state: (
        idx(state[1], 1) == idx(state[4], 0)
        and idx(state[3], 0) == idx(state[4], 1)
        and abs(idx(state[3], 2) - idx(state[4], 2)) == 1
        and abs(idx(state[3], 1) - idx(state[4], 3)) == 1
    )

    steps = (
        ("colors", f_colors),
        ("nations", f_nations),
        ("drinks", f_drinks),
        ("smokes", f_smokes),
        ("pets", f_pets),
    )

    states: list[tuple[tuple[int, ...], ...]] = [()]
    lines = [
        "# Einstein Reference Stage Counts",
        "",
        "| step | surviving_states |",
        "| --- | ---: |",
    ]
    for name, filter_func in steps:
        states = solve_step(states, all_permutations, filter_func)
        lines.append(f"| {name} | {len(states)} |")
    return "\n".join(lines)


def render_reference_solution_markdown(solution: EinsteinReferenceSolution | None = None) -> str:
    solved = solution or solve_einstein_reference()
    lines = [
        "# Einstein Reference Solution",
        "",
        "| house | nation | color | drink | smoke | pet |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for row in solved.house_rows():
        lines.append(
            f"| {row['house']} | {row['nation']} | {row['color']} | {row['drink']} | {row['smoke']} | {row['pet']} |"
        )
    return "\n".join(lines)
