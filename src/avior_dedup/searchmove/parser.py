"""Pure parsing logic for search expressions and numeric conditions.

No I/O — these functions transform strings into structured data.
"""

from __future__ import annotations

import re
from collections.abc import Callable


def parse_search_expression(expr_list: list[str] | None) -> list[list[list[str]]]:
    """Parse boolean search expressions into a nested AND/OR structure.

    Input (from CLI)::

        ["a&b|c", "d&e"]

    Means::

        (a AND b) OR (c)
        (d AND e)

    Output::

        [
          [ ['a','b'], ['c'] ],    # first expression: OR of AND-groups
          [ ['d','e'] ]            # second expression
        ]

    The outer list contains one entry per CLI expression.
    Each entry is a list of OR-alternatives.
    Each OR-alternative is a list of AND-terms.
    """
    groups: list[list[list[str]]] = []
    for expr in expr_list or []:
        expr = (expr or "").strip()
        if not expr:
            continue
        or_parts = expr.split("|")
        group: list[list[str]] = []
        for part in or_parts:
            and_parts = [p.strip() for p in part.split("&") if p.strip()]
            if and_parts:
                group.append(and_parts)
        if group:
            groups.append(group)
    return groups


def parse_condition(condition_str: str) -> Callable[[float], bool] | None:
    """Parse a numeric condition string into a predicate function.

    Supported formats::

        >7        greater than
        >=7       greater or equal
        <5.5      less than
        <=5.5     less or equal
        ==6       equals
        >4<6      compound (greater than 4 AND less than 6)
        4-6       range (inclusive)
        4..6      range (inclusive)
        7         single value (equals)

    Returns ``None`` if the string cannot be parsed as a numeric condition.
    """
    s = (condition_str or "").strip()
    if not s:
        return None

    # Operator-number pairs like >4, <=5.5, ==6
    parts = re.findall(r"([<>]=?|==)\s*([0-9]+(?:\.[0-9]+)?)", s)
    if parts:
        conds: list[Callable[[float], bool]] = []
        for op, num in parts:
            n = float(num)
            if op == ">":
                conds.append(lambda v, n=n: v > n)
            elif op == ">=":
                conds.append(lambda v, n=n: v >= n)
            elif op == "<":
                conds.append(lambda v, n=n: v < n)
            elif op == "<=":
                conds.append(lambda v, n=n: v <= n)
            elif op == "==":
                conds.append(lambda v, n=n: v == n)
        return lambda v: all(c(v) for c in conds)

    # Range like 4-6 or 4..6
    m = re.match(
        r"^\s*([0-9]+(?:\.[0-9]+)?)\s*[-\u2013\u2014.]{1,2}\s*([0-9]+(?:\.[0-9]+)?)\s*$",
        s,
    )
    if m:
        lo, hi = float(m.group(1)), float(m.group(2))
        return lambda v: lo <= v <= hi

    # Single number equals
    m = re.match(r"^\s*([0-9]+(?:\.[0-9]+)?)\s*$", s)
    if m:
        n = float(m.group(1))
        return lambda v: v == n

    return None
