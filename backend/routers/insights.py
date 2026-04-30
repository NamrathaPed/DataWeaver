"""
Insights Router
---------------
POST /api/insights/generate  — Run the full insight pipeline.
POST /api/insights/section   — Regenerate a single insight section.
GET  /api/insights            — Retrieve cached insights for a session.
"""

from __future__ import annotations

from fastapi import APIRouter

from engine.insight_engine import (
    generate_insights,
    generate_single_insight,
    validate_correlation_claims,
    validate_null_claims,
)
from utils import supabase_client as sb
from routers.analyze import get_cached_eda
from routers.upload import get_session_df

router = APIRouter()

_insight_cache: dict[str, dict] = {}


@router.post("/generate")
def generate(
    session_id: str,
    model: str = "",
    force_refresh: bool = False,
):
    """Run the full LLM insight pipeline for a session. Cached after first run."""
    if not force_refresh:
        # L1: memory
        if session_id in _insight_cache:
            return {"session_id": session_id, "insights": _insight_cache[session_id], "cached": True}
        # L2: Supabase
        state = sb.get_session_state(session_id)
        if state and state.get("insight_cache"):
            _insight_cache[session_id] = state["insight_cache"]
            return {"session_id": session_id, "insights": state["insight_cache"], "cached": True}

    eda = get_cached_eda(session_id)
    session = get_session_df(session_id)
    filename = session["filename"]

    insights = generate_insights(eda, filename, model=model or None)

    if insights.get("correlations"):
        insights["correlations"] = validate_correlation_claims(
            insights["correlations"],
            eda["correlations"]["strong_pairs"],
        )

    if insights.get("anomalies"):
        insights["anomalies"] = validate_null_claims(
            insights["anomalies"],
            eda["summary"],
        )

    _insight_cache[session_id] = insights
    sb.save_session_state(session_id, insight_cache=insights)

    return {"session_id": session_id, "insights": insights, "cached": False}


@router.post("/section")
def regenerate_section(
    session_id: str,
    section: str,
    model: str = "",
):
    """Regenerate a single insight section without re-running the full pipeline."""
    from prompts.insight_prompts import (
        build_overview_prompt,
        build_statistics_prompt,
        build_correlation_prompt,
        build_distribution_prompt,
        build_categorical_prompt,
        build_timeseries_prompt,
        build_anomaly_prompt,
    )

    eda = get_cached_eda(session_id)
    session = get_session_df(session_id)
    filename = session["filename"]

    section_map = {
        "overview": (
            build_overview_prompt(filename, eda["dataset_overview"], eda["column_types"]),
            "overview",
        ),
        "statistics": (build_statistics_prompt(eda["summary"]), "statistics_insights"),
        "correlations": (build_correlation_prompt(eda["correlations"]), "correlation_insights"),
        "distributions": (build_distribution_prompt(eda["distributions"]), "distribution_insights"),
        "categorical": (build_categorical_prompt(eda["categorical"]), "categorical_insights"),
        "time_series": (build_timeseries_prompt(eda["time_series"]), "timeseries_insights"),
        "anomalies": (
            build_anomaly_prompt(eda["summary"], eda["distributions"]),
            "anomaly_insights",
        ),
    }

    if section not in section_map:
        raise ValueError(
            f"Unknown section '{section}'. "
            f"Choose from: {', '.join(section_map.keys())}."
        )

    prompt, key = section_map[section]
    result = generate_single_insight(prompt, key, model=model or None)

    # Update both L1 and L2 caches
    cached = _insight_cache.setdefault(session_id, {})
    cached[section] = result
    sb.save_session_state(session_id, insight_cache=cached)

    return {"session_id": session_id, "section": section, "insights": result}


@router.get("")
def get_insights(session_id: str):
    """Return cached insights for a session."""
    # L1
    cached = _insight_cache.get(session_id)
    if cached is not None:
        return {"session_id": session_id, "insights": cached}
    # L2
    state = sb.get_session_state(session_id)
    if state and state.get("insight_cache"):
        _insight_cache[session_id] = state["insight_cache"]
        return {"session_id": session_id, "insights": state["insight_cache"]}
    raise ValueError(
        f"No insights found for session '{session_id}'. "
        "Call POST /api/insights/generate first."
    )
