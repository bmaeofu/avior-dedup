"""Dedup tool: scanning, planning, reporting."""

from avior_dedup.dedup.models import FileRecord, MoveAction
from avior_dedup.dedup.planner import build_move_plan, execute_move_plan
from avior_dedup.dedup.reporting import sort_and_finalize_log
from avior_dedup.dedup.scanner import find_duplicates
