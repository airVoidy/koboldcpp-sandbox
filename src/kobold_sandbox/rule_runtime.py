from __future__ import annotations


def rule_eq(left, right) -> bool:
    return left == right


def rule_ne(left, right) -> bool:
    return left != right


def rule_next_to(left, right) -> bool:
    return abs(left - right) == 1


def rule_right_of(left, right, distance: int = 1) -> bool:
    return left == right + distance


def rule_all_different(*items) -> bool:
    return len(set(items)) == len(items)


def rule_exactly_one(*items) -> bool:
    return sum(1 for value in items if value) == 1
