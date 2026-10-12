#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: MIT
"""Read intake-form worksheets into plain Python structures.

Owns the intake form's physical quirks and nothing else: two-row grouped
headers, tables stacked vertically inside one sheet, and `#` instruction
rows. It carries NO ERA semantics — callers decide what the data means.
"""


def _norm(value):
    """Lowercase and collapse whitespace, for header matching."""
    if value is None:
        return ""
    return " ".join(str(value).split()).lower()


# Row 1 holds group labels rather than column names on the sheets that use
# a banded header. Detect that rather than hardcoding a row number, so a
# sheet with a plain single-row header still works.
_GROUP_LABELS = {"source", "destination", "switch", "switch ip's", "l3", "l2"}


def header_row(ws):
    """Return the 1-based row index holding real column names.

    Ambiguity raises rather than guesses. Row 1's non-empty values must be
    either entirely known group labels (banded header, real names on row
    2) or have no overlap with them at all (plain header, real names on
    row 1) -- a *partial* overlap (e.g. a template edit adds one more band
    label than `_GROUP_LABELS` knows about) can't be told apart from a
    plain header that happens to reuse a group-label word, and guessing
    either way risks mapping the wrong row as headers and silently
    returning zero columns downstream.
    """
    first = {_norm(ws.cell(1, c).value) for c in range(1, ws.max_column + 1)}
    first.discard("")
    if not first:
        return 1
    if first <= _GROUP_LABELS:
        return 2
    overlap = first & _GROUP_LABELS
    if overlap:
        raise ValueError(
            f"Sheet '{ws.title}': row 1 mixes known group labels "
            f"{sorted(overlap)} with unrecognised value(s) "
            f"{sorted(first - overlap)} -- ambiguous whether row 1 is a "
            "banded header (real column names on row 2) or a plain header "
            "(real column names on row 1). Make row 1 either entirely "
            "known group labels or entirely real column names.")
    return 1


def column_map(ws):
    """Map normalised header text -> 1-based column index."""
    row = header_row(ws)
    cols = {}
    for c in range(1, ws.max_column + 1):
        name = _norm(ws.cell(row, c).value)
        if name:
            cols[name] = c
    return cols


def find_section(ws, title):
    """Return the 1-based row whose first cell is `title`, else None.

    Scans rather than using a fixed offset: section positions shift as the
    table above them grows.
    """
    want = _norm(title)
    for r in range(1, ws.max_row + 1):
        if _norm(ws.cell(r, 1).value) == want:
            return r
    return None


def read_section(ws, title, columns):
    """Read the rows under `title`'s header row into dicts.

    Layout: `title` on one row, column names on the next, data below.
    Stops at the next section title — a row whose column A is set while
    every *other* mapped column is empty — never merely at a blank row,
    since a blank row inside a section is a gap, not a terminator.
    """
    # Normalise the caller's names too. Sheet headers go through `_norm`,
    # so a caller passing "VRF Name" instead of "vrf name" matched nothing
    # and got back zero rows with no error -- a silent empty result, not a
    # failure. Every current caller happens to pass lowercase; that made the
    # contract implicit rather than safe.
    wanted = {_norm(c) for c in columns}
    start = find_section(ws, title)
    if start is None:
        return []
    header = start + 1
    cols = {}
    for c in range(1, ws.max_column + 1):
        name = _norm(ws.cell(header, c).value)
        if name in wanted:
            cols[name] = c
    rows = []
    for r in range(header + 1, ws.max_row + 1):
        values = {name: ws.cell(r, c).value for name, c in cols.items()}
        if all(v in (None, "") for v in values.values()):
            continue                      # gap row, keep scanning
        first = ws.cell(r, 1).value
        others_empty = all(
            v in (None, "") for name, v in values.items() if cols[name] != 1
        )
        if first not in (None, "") and others_empty:
            break                         # next section title
        rows.append(values)
    return rows


# Section banners carried over from the legacy `Settings` sheet: a name in
# column A with NO value in column B. They give the sheet its structure and
# are reproduced in `Deployment` so it reads as grouped sections rather than
# one flat list.
#
# Matched by NAME, explicitly -- NOT by "column B is empty". `netq_ip` is a
# real setting that ships with a blank value in the shipped workbooks, so a
# shape-based rule would silently drop it.
SECTION_BANNERS = frozenset({
    "general", "network", "management", "telemetry", "advanced",
    "air deployment", "versions", "setting", "switch function",
})


def is_section_banner(name):
    """True if `name` is one of the known section-title names.

    Necessary but NOT sufficient -- callers must also check the row has no
    value. See read_deployment.
    """
    return str(name).strip().lower() in SECTION_BANNERS


def read_deployment(ws):
    """Read the Deployment sheet into a settings dict.

    Skips `#` instruction rows and blank rows. A blank row is a gap, not a
    terminator — the sheet groups settings into sections. The Air image block
    uses version strings as setting names (e.g., "5.18.0" -> "cumulus-vx-5.18.0"),
    so the returned dict mixes real setting names with version keys; Task 9 will
    separate them.

    Raises ValueError if a key appears more than once.
    """
    settings = {}
    for r in range(1, ws.max_row + 1):
        name = ws.cell(r, 1).value
        if name is None or str(name).lstrip().startswith("#"):
            continue
        # Skip the header row: only when BOTH cells 1 and 2 are "Setting" and "Value".
        value = ws.cell(r, 2).value
        if _norm(name) == "setting" and _norm(value) == "value":
            continue
        # Skip section banners (see SECTION_BANNERS). BOTH conditions are
        # required. Name alone would swallow a legitimate setting that
        # happens to be called "Setting" (covered by a test); empty-value
        # alone would swallow `netq_ip`, which ships blank in the shipped
        # workbooks. A banner is a known name AND no value.
        if is_section_banner(name) and value in (None, ""):
            continue
        key = str(name).strip()
        if key in settings:
            raise ValueError(
                f"Duplicate key '{key}': first '{settings[key]}', then '{value}'"
            )
        settings[key] = value
    return settings
