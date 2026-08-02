"""
Degradation level manager.

Levels (L0 → L4) control how the pipeline generates a draft response:
  L0 — normal: full LLM generation (retrieval context + prompt)
  L1 — high load: LLM batch mode (multiple tickets per API call)
  L2 — LLM overloaded / slow: TF-IDF retrieval template, no LLM
  L3 — LLM unavailable (circuit-breaker open): retrieval template
  L4 — critical: route to operator, no draft at all

In the PoC the level can be set manually via the debug UI or
simulated_queue_size parameter in the API.
"""

THRESHOLDS = {
    "L0": (0, 49),
    "L1": (50, 199),
    "L2": (200, 499),
    "L3": (500, 9999),
    "L4": (10000, float("inf")),
}

LEVEL_LABELS = {
    "L0": "normal",
    "L1": "high_load_batch",
    "L2": "llm_overloaded",
    "L3": "llm_unavailable",
    "L4": "critical",
}


def get_level(queue_size: int, llm_available: bool = True) -> dict:
    """
    Determine degradation level from queue size and LLM availability.
    LLM unavailability forces at least L3.
    """
    level = "L0"
    for lvl, (lo, hi) in THRESHOLDS.items():
        if lo <= queue_size <= hi:
            level = lvl
            break

    if not llm_available and level in ("L0", "L1"):
        level = "L3"

    return {
        "level": level,
        "label": LEVEL_LABELS[level],
        "queue_size": queue_size,
        "llm_available": llm_available,
        "use_llm": level in ("L0", "L1"),
        "use_batch": level == "L1",
        "use_retrieval_only": level in ("L2", "L3"),
        "escalate_only": level == "L4",
    }
