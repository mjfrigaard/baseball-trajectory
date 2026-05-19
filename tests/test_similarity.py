"""Tests for baseball_trajectory.similarity."""

import polars as pl

from baseball_trajectory.similarity import (
    POSITION_VALUE,
    find_similar_players,
    position_value,
    similarity_score,
)


def test_identical_careers_score_1000():
    a = {
        "G": 2401,
        "AB": 8102,
        "R": 1677,
        "H": 2415,
        "2B": 344,
        "3B": 72,
        "HR": 536,
        "RBI": 1509,
        "BB": 1733,
        "SO": 1710,
        "SB": 153,
        "AVG": 0.298,
        "SLG": 0.557,
        "POS": "OF",
    }
    assert similarity_score(a, a) == 1000


def test_position_value_lookup():
    assert position_value("C") == POSITION_VALUE["C"]
    assert position_value("SS") == 168
    assert position_value("1B") == 12
    assert position_value("P") == 0  # not in table
    assert position_value(None) == 0
    assert position_value("") == 0


def test_position_gap_subtracts():
    base = {"AVG": 0.300, "SLG": 0.500, "POS": "1B"}
    catcher = {**base, "POS": "C"}
    # Only difference is position: 1B=12, C=240 → gap of 228.
    assert similarity_score(base, catcher) == 1000 - (240 - 12)


def test_counting_stat_floor_division():
    a = {"AB": 1000, "AVG": 0.300, "SLG": 0.500, "POS": "OF"}
    # 1149 AB diff / 75 = 15.32 → floor 15
    b = {"AB": 2149, "AVG": 0.300, "SLG": 0.500, "POS": "OF"}
    assert similarity_score(a, b) == 1000 - 15


def test_find_similar_ranks_top_n_in_order():
    target = {
        "G": 2401,
        "AB": 8102,
        "R": 1677,
        "H": 2415,
        "2B": 344,
        "3B": 72,
        "HR": 536,
        "RBI": 1509,
        "BB": 1733,
        "SO": 1710,
        "SB": 153,
        "AVG": 0.298,
        "SLG": 0.557,
        "POS": "OF",
    }
    # Three candidates with progressively larger deltas.
    candidates = pl.DataFrame(
        [
            {
                "playerID": "near",
                "AB": 8102,
                "H": 2415,
                "HR": 536,
                "AVG": 0.298,
                "SLG": 0.557,
                "POS": "OF",
                "G": 2401,
                "R": 1677,
                "2B": 344,
                "3B": 72,
                "RBI": 1509,
                "BB": 1733,
                "SO": 1710,
                "SB": 153,
            },
            {
                "playerID": "mid",
                "AB": 7000,
                "H": 2200,
                "HR": 400,
                "AVG": 0.280,
                "SLG": 0.500,
                "POS": "OF",
                "G": 2200,
                "R": 1500,
                "2B": 320,
                "3B": 70,
                "RBI": 1300,
                "BB": 1500,
                "SO": 1500,
                "SB": 150,
            },
            {
                "playerID": "far",
                "AB": 5000,
                "H": 1000,
                "HR": 50,
                "AVG": 0.200,
                "SLG": 0.300,
                "POS": "C",
                "G": 1500,
                "R": 800,
                "2B": 100,
                "3B": 20,
                "RBI": 400,
                "BB": 500,
                "SO": 1000,
                "SB": 30,
            },
        ]
    )
    ranked = find_similar_players(target, candidates, n=3)
    assert ranked["playerID"].to_list() == ["near", "mid", "far"]
    # Scores must be monotonically non-increasing.
    scores = ranked["sim_score"].to_list()
    assert scores == sorted(scores, reverse=True)
    assert scores[0] == 1000  # exact match
