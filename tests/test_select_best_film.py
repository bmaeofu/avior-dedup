"""Tests for select_best_film with configurable priority list and max_errors_when_mc."""

from __future__ import annotations

import pytest

from avior_dedup.dedup.models import FileRecord, SelectionPriority
from avior_dedup.dedup.planner import select_best_film


def _rec(
    name: str,
    *,
    multichannel: bool = False,
    error_count: int = 0,
    video_duration: float = 3600,
    rec_duration: int = 3600,
    mod_date: float = 1000.0,
) -> FileRecord:
    """Helper to build a FileRecord with sensible defaults."""
    return FileRecord(
        file=name,
        video_exists=True,
        error_count=error_count,
        mod_date=mod_date,
        multichannel=multichannel,
        video_duration=video_duration,
        rec_duration=rec_duration,
    )


# ---------------------------------------------------------------------------
# 1. At least one film is always kept
# ---------------------------------------------------------------------------


class TestAlwaysKeepOne:
    def test_all_outside_duration_window_still_keeps_one(self):
        """Even if every recording exceeds the duration window, one must be kept."""
        records = [
            _rec("a.ts", video_duration=9999, rec_duration=100),
            _rec("b.ts", video_duration=9998, rec_duration=100),
        ]
        best = select_best_film(records, max_duration_diff_longer=10, max_duration_diff_shorter=10)
        assert best is not None, "Must keep at least one film"
        assert best.file in ("a.ts", "b.ts")
        print(f"  PASS: kept '{best.file}' even though all candidates are outside duration window")

    def test_single_record_always_kept(self):
        """A single recording must always be kept regardless of quality."""
        records = [_rec("only.ts", error_count=999, multichannel=False)]
        best = select_best_film(records)
        assert best.file == "only.ts"
        print("  PASS: single record is always kept")


# ---------------------------------------------------------------------------
# 2. MC priority respects max_errors_when_mc threshold
# ---------------------------------------------------------------------------


class TestMcErrorThreshold:
    def test_mc_with_acceptable_errors_wins(self):
        """MC recording with errors <= threshold should be preferred."""
        mc = _rec("mc.ts", multichannel=True, error_count=2)
        stereo = _rec("stereo.ts", multichannel=False, error_count=0)
        best = select_best_film(
            [mc, stereo],
            selection_priorities=[SelectionPriority.MULTICHANNEL, SelectionPriority.FEWER_ERRORS],
            max_errors_when_mc=3,
        )
        assert best.file == "mc.ts"
        print(f"  PASS: MC with {mc.error_count} errors (threshold=3) wins over error-free stereo")

    def test_mc_with_too_many_errors_loses_mc_advantage(self):
        """MC recording with errors > threshold should lose its multichannel advantage."""
        mc = _rec("mc.ts", multichannel=True, error_count=5)
        stereo = _rec("stereo.ts", multichannel=False, error_count=0)
        best = select_best_film(
            [mc, stereo],
            selection_priorities=[SelectionPriority.MULTICHANNEL, SelectionPriority.FEWER_ERRORS],
            max_errors_when_mc=3,
        )
        assert best.file == "stereo.ts"
        print(
            f"  PASS: MC with {mc.error_count} errors (threshold=3) loses MC advantage -> "
            f"stereo with 0 errors wins via FEWER_ERRORS fallback"
        )

    def test_mc_exactly_at_threshold_still_wins(self):
        """MC recording with errors == threshold should still be preferred."""
        mc = _rec("mc.ts", multichannel=True, error_count=3)
        stereo = _rec("stereo.ts", multichannel=False, error_count=0)
        best = select_best_film(
            [mc, stereo],
            selection_priorities=[SelectionPriority.MULTICHANNEL, SelectionPriority.FEWER_ERRORS],
            max_errors_when_mc=3,
        )
        assert best.file == "mc.ts"
        print(f"  PASS: MC with exactly {mc.error_count} errors (threshold=3) still wins")

    def test_mc_one_over_threshold_loses(self):
        """MC recording with errors == threshold+1 should lose MC advantage."""
        mc = _rec("mc.ts", multichannel=True, error_count=4)
        stereo = _rec("stereo.ts", multichannel=False, error_count=1)
        best = select_best_film(
            [mc, stereo],
            selection_priorities=[SelectionPriority.MULTICHANNEL, SelectionPriority.FEWER_ERRORS],
            max_errors_when_mc=3,
        )
        assert best.file == "stereo.ts"
        print(
            f"  PASS: MC with {mc.error_count} errors (threshold=3) loses advantage -> "
            f"stereo with {stereo.error_count} error wins via FEWER_ERRORS"
        )

    def test_no_threshold_means_mc_always_wins(self):
        """Without max_errors_when_mc, any MC recording keeps its advantage."""
        mc = _rec("mc.ts", multichannel=True, error_count=100)
        stereo = _rec("stereo.ts", multichannel=False, error_count=0)
        best = select_best_film(
            [mc, stereo],
            selection_priorities=[SelectionPriority.MULTICHANNEL, SelectionPriority.FEWER_ERRORS],
            max_errors_when_mc=None,
        )
        assert best.file == "mc.ts"
        print(f"  PASS: no threshold -> MC with {mc.error_count} errors still wins")

    def test_two_mc_one_over_threshold_picks_good_mc(self):
        """Among two MC recordings, the one within the error threshold wins."""
        mc_bad = _rec("mc_bad.ts", multichannel=True, error_count=10)
        mc_good = _rec("mc_good.ts", multichannel=True, error_count=2)
        best = select_best_film(
            [mc_bad, mc_good],
            selection_priorities=[SelectionPriority.MULTICHANNEL, SelectionPriority.FEWER_ERRORS],
            max_errors_when_mc=5,
        )
        assert best.file == "mc_good.ts"
        print(
            f"  PASS: two MC files -> mc_bad ({mc_bad.error_count} errors, over threshold=5) "
            f"treated as non-MC, mc_good ({mc_good.error_count} errors) wins"
        )


# ---------------------------------------------------------------------------
# 3. Priority order is respected
# ---------------------------------------------------------------------------


class TestPriorityOrder:
    def test_fewer_errors_first_ignores_mc(self):
        """When FEWER_ERRORS is top priority, error count matters more than MC."""
        mc = _rec("mc.ts", multichannel=True, error_count=5)
        stereo = _rec("stereo.ts", multichannel=False, error_count=0)
        best = select_best_film(
            [mc, stereo],
            selection_priorities=[SelectionPriority.FEWER_ERRORS, SelectionPriority.MULTICHANNEL],
        )
        assert best.file == "stereo.ts"
        print("  PASS: FEWER_ERRORS first -> stereo with 0 errors beats MC with 5 errors")

    def test_closest_duration_first(self):
        """When CLOSEST_DURATION is top priority, duration match matters most."""
        close = _rec("close.ts", video_duration=3610, rec_duration=3600, error_count=5)
        far = _rec("far.ts", video_duration=4000, rec_duration=3600, error_count=0, multichannel=True)
        best = select_best_film(
            [close, far],
            selection_priorities=[SelectionPriority.CLOSEST_DURATION, SelectionPriority.MULTICHANNEL],
        )
        assert best.file == "close.ts"
        print(
            f"  PASS: CLOSEST_DURATION first -> close (diff={abs(3610-3600)}s) "
            f"beats far MC (diff={abs(4000-3600)}s)"
        )

    def test_mc_first_then_closest_duration(self):
        """MC first, then duration as tiebreaker among MC files."""
        mc_far = _rec("mc_far.ts", multichannel=True, video_duration=4000, rec_duration=3600)
        mc_close = _rec("mc_close.ts", multichannel=True, video_duration=3610, rec_duration=3600)
        stereo_exact = _rec("stereo.ts", multichannel=False, video_duration=3600, rec_duration=3600)
        best = select_best_film(
            [mc_far, mc_close, stereo_exact],
            selection_priorities=[SelectionPriority.MULTICHANNEL, SelectionPriority.CLOSEST_DURATION],
        )
        assert best.file == "mc_close.ts"
        print(
            "  PASS: MC first -> both MC files preferred over perfect-duration stereo, "
            "then CLOSEST_DURATION picks mc_close"
        )

    def test_single_priority(self):
        """A priority list with only one criterion still works."""
        a = _rec("a.ts", error_count=10, multichannel=True)
        b = _rec("b.ts", error_count=1, multichannel=False)
        best = select_best_film(
            [a, b],
            selection_priorities=[SelectionPriority.FEWER_ERRORS],
        )
        assert best.file == "b.ts"
        print("  PASS: single priority (FEWER_ERRORS) -> b with 1 error beats a with 10")


# ---------------------------------------------------------------------------
# 4. Tiebreaker: newest file wins
# ---------------------------------------------------------------------------


class TestTiebreaker:
    def test_equal_criteria_picks_newest(self):
        """When all priority criteria are equal, the newest file wins."""
        old = _rec("old.ts", mod_date=1000.0)
        new = _rec("new.ts", mod_date=2000.0)
        best = select_best_film(
            [old, new],
            selection_priorities=[SelectionPriority.FEWER_ERRORS],
        )
        assert best.file == "new.ts"
        print("  PASS: equal criteria -> newest file (mod_date=2000) wins")


# ---------------------------------------------------------------------------
# 5. Duration window filtering with guarantee
# ---------------------------------------------------------------------------


class TestDurationWindow:
    def test_in_window_preferred_over_out_of_window(self):
        """Recordings within the duration window are preferred."""
        in_window = _rec("in.ts", video_duration=3700, rec_duration=3600, error_count=3)
        out_window = _rec("out.ts", video_duration=5000, rec_duration=3600, error_count=0, multichannel=True)
        best = select_best_film(
            [in_window, out_window],
            max_duration_diff_longer=600,
            max_duration_diff_shorter=120,
            selection_priorities=[SelectionPriority.MULTICHANNEL, SelectionPriority.FEWER_ERRORS],
        )
        assert best.file == "in.ts"
        print(
            "  PASS: in-window (diff=100s, 3 errors) beats out-of-window MC (diff=1400s, 0 errors)"
        )

    def test_fallback_when_all_out_of_window(self):
        """When all are out of window, fall back to full list and apply priorities."""
        mc = _rec("mc.ts", multichannel=True, video_duration=9000, rec_duration=3600, error_count=0)
        stereo = _rec("stereo.ts", multichannel=False, video_duration=8000, rec_duration=3600, error_count=0)
        best = select_best_film(
            [mc, stereo],
            max_duration_diff_longer=10,
            selection_priorities=[SelectionPriority.MULTICHANNEL],
        )
        assert best.file == "mc.ts"
        print("  PASS: all out of window -> fallback to full list, MC wins by priority")
