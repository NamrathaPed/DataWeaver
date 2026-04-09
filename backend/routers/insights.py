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
    """Run the full LLM insight pipeline for a session.

    Insights are cached. Set force_refresh=true to re-run the LLM.

    Returns all insight sections plus token usage metadata.
    """
    if not force_refresh and session_id in _insight_cache:
        return {
            "session_id": session_id,
            "insights": _insight_cache[session_id],
            "cached": True,
        }

    eda = get_cached_eda(session_id)
    session = get_session_df(session_id)
    filename = session["filename"]

    insights = generate_insights(
        eda,
        filename,
        model=model or None,
    )

    # Validate correlation claims against actual computed r values
    if insights.get("correlations"):
        insights["correlations"] = validate_correlation_claims(
            insights["correlations"],
            eda["correlations"]["strong_pairs"],
        )

    # Pin actual null percentages to anomaly insights
    if insights.get("anomalies"):
        insights["anomalies"] = validate_null_claims(
            insights["anomalies"],
            eda["summary"],
        )

    _insight_cache[session_id] = insights

    # Update Supabase results cache
    upload_id = session.get("upload_id")
    if upload_id:
        sb.save_results(upload_id, eda, insights)

    return {
        "session_id": session_id,
        "insights": insights,
        "cached": False,
    }


@router.post("/section")
def regenerate_section(
    session_id: str,
    section: str,
    model: str = "",
):
    """Regenerate a single insight section without re-running the full pipeline.

    Parameters
    ----------
    section:
        One of: overview | statistics | correlations | distributions |
                categorical | time_series | anomalies
    """
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

    # Update cache
    if session_id in _insight_cache:
        _insight_cache[session_id][section] = result

    return {"session_id": session_id, "section": section, "insights": result}


@router.get("")
def get_insights(session_id: str):
    """Return cached insights for a session."""
    cached = _insight_cache.get(session_id)
    if cached is None:
        raise ValueError(
            f"No insights found for session '{session_id}'. "
            "Call POST /api/insights/generate first."
        )
    return {"session_id": session_id, "insights": cached}
