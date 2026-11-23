"""Positive and negative cases for every metric (RoboCurve-style scorer tests)."""
import math

from avsim.metrics import assist_metrics, ems_metrics, halt_metrics, overlap, request_metrics


def test_overlap():
    assert overlap(0, 10, 5, 20) == 5
    assert overlap(0, 10, 10, 20) == 0
    assert overlap(5, 6, 0, 100) == 1


def _inc(iid, tc, td, ta, ff=100, blocked=0):
    return {"iid": iid, "t_call": tc, "t_dispatch": td, "t_arrive": ta, "response_s": ta - tc,
            "route_est_s": ff, "blocked_s": blocked}


def test_ems_basic_and_window():
    incs = [_inc("a", 100, 130, 400), _inc("b", 200, 230, 330)]
    m = ems_metrics(incs, [("a", 100), ("b", 200), ("c", 9999)], 0, 1000, 5000, 900)
    assert m["n_calls"] == 2 and m["n_censored"] == 0
    assert math.isclose(m["resp_mean_s"], (300 + 130) / 2)
    assert m["frac_over_p90_target"] == 0
    assert math.isclose(m["unit_wait_mean_s"], 30) and math.isclose(m["travel_mean_s"], (270 + 100) / 2)


def test_ems_never_arrived_is_kept_not_dropped():
    # survivorship: a call with no arrival must count, with response censored at the end of the run
    m = ems_metrics([], [("a", 1000)], 0, 2000, 5400, 900)
    assert m["n_calls"] == 1 and m["n_censored"] == 1
    assert m["resp_mean_s"] == 4400 and m["frac_over_p90_target"] == 1.0


def test_halts_censored_and_split():
    halts = [{"kind": "lane", "cause": "link", "start": 0, "end": 600, "with_passenger": True},
             {"kind": "kerb", "cause": "assist_hold", "start": 100, "end": 160, "with_passenger": False},
             {"kind": "lane", "cause": "link", "start": 5000, "end": 6000, "with_passenger": False}]
    m = halt_metrics(halts, 300, 5400)
    assert math.isclose(m["lane_block_min"], 5 + 400 / 60)  # first clipped at window start, last at window end
    assert m["kerb_halt_min"] == 0  # outside window
    assert math.isclose(m["stranded_pax_min"], 5)
    assert m["n_halts_link"] == 2 and m["n_halts_assist"] == 0


def test_lane_dwell_counted_as_blocking_but_not_as_halt():
    halts = [{"kind": "lane", "cause": "dwell_fake", "start": 0, "end": 300, "with_passenger": False}]
    m = halt_metrics(halts, 0, 1000)
    assert m["lane_block_min"] == 5 and m["lane_block_dwell_min"] == 5
    assert m["n_lane_dwells"] == 1 and m["n_halts_link"] == 0 and m["n_halts_assist"] == 0


def test_assist_counts_censored_queue():
    w = [{"t_req": 5, "wait": 50, "kind": "recovery"}, {"t_req": 6, "wait": 4000, "kind": "recovery", "censored": True}]
    m = assist_metrics(w, 0, 10)
    assert m["assist_n_censored"] == 1 and m["assist_wait_max_s"] == 4000


def test_requests_exclude_fake():
    reqs = [{"t": 10, "fake": False, "status": "completed"}, {"t": 20, "fake": True, "status": "no_show"},
            {"t": 30, "fake": False, "status": "app_down"}]
    m = request_metrics(reqs, 0, 100)
    assert m["n_requests"] == 2 and m["completed"] == 1 and m["unserved_frac"] == 0.5


def test_assist_excludes_fake():
    w = [{"t_req": 5, "wait": 100, "kind": "recovery"}, {"t_req": 6, "wait": 999, "kind": "fake"}]
    assert assist_metrics(w, 0, 10)["assist_wait_max_s"] == 100
