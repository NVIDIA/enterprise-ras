# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: MIT
"""Shared budget formatting helpers."""

from __future__ import annotations


def format_budget_row(label: str, used: int, total: int, unit: str) -> str:
    """Format a single budget row: Label  used/total unit  (pct%)  N available."""
    unit_str = f" {unit}" if unit else ""
    if total == 0:
        if used == 0:
            return f"  {label:14s} 0{unit_str}  (no quota)"
        return f"  {label:14s} {used}/{total}{unit_str}  (OVER QUOTA)"
    pct = used / total * 100
    available = max(total - used, 0)
    return f"  {label:14s} {used}/{total}{unit_str}  ({pct:.0f}%)  {available} available"
