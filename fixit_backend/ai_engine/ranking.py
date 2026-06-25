"""
FixIt AI Ranking Engine — Phase 1 (corrected)
Pure Python, zero external dependencies, zero per-call DB queries.

The four behavioral signals below — response_speed, cancellation_rate,
repeat_bonus, recency — are precomputed by
ai_engine.tasks.update_provider_ranking_signals (Celery Beat, every 6h)
and stored on ProviderProfile as cached_* fields. This module never
queries the DB itself: it only reads fields already present on the
`service` / `service.provider` objects passed in, so it stays safe to
call in a tight loop over nearby-provider search results.
"""

# ── Signal weights ────────────────────────────────────────────────
# These add up to 1.0
WEIGHTS = {
    'service_rating':     0.30,  # star rating of this specific service
    'overall_rating':     0.10,  # provider's overall rating across all services
    'completion_rate':    0.15,  # completed / total accepted jobs
    'response_speed':     0.15,  # how fast they accept bookings (cached)
    'experience':         0.10,  # total jobs completed (capped)
    'distance':          -0.10,  # closer is better (negative weight)
    'cancellation':      -0.10,  # high cancellation = lower rank (cached)
    'repeat_bookings':    0.05,  # customers who rebook = trust signal (cached)
    'recency':            0.05,  # recently active providers rank higher (cached)
}


def calculate_ranking_score(service, distance_km, request_user=None):
    """
    Main ranking function.
    Called by HaversineLocationBackend for every provider in search results.

    Zero DB queries — all behavioral signals are read from cached fields
    on `service.provider`, refreshed periodically by Celery Beat.

    Returns a float score — higher is better.
    All inputs normalized to 0.0-1.0 range.
    """
    provider = service.provider

    # ── Signal 1: Service rating (0-5 → 0.0-1.0) ─────────────────
    service_rating = float(service.service_rating or 0) / 5.0

    # ── Signal 2: Overall provider rating (0-5 → 0.0-1.0) ────────
    overall_rating = float(provider.overall_rating or 0) / 5.0

    # ── Signal 3: Completion rate (already 0.0-1.0) ───────────────
    completion_rate = float(service.completion_rate or 0)

    # ── Signal 4: Response speed (cached, refreshed every 6h) ────
    response_speed = float(provider.cached_response_speed or 0.5)

    # ── Signal 5: Experience bonus ────────────────────────────────
    # caps at 1.0 when provider has 200+ completed jobs
    total_jobs = float(service.total_jobs or 0)
    experience = min(total_jobs / 200.0, 1.0)

    # ── Signal 6: Distance penalty ────────────────────────────────
    # caps at 1.0 when provider is 20+ km away
    distance_penalty = min(distance_km / 20.0, 1.0)

    # ── Signal 7: Cancellation penalty (cached, refreshed every 6h) ─
    cancellation_rate = float(provider.cached_cancellation_rate or 0.0)

    # ── Signal 8: Repeat booking bonus (cached, refreshed every 6h) ─
    repeat_bonus = float(provider.cached_repeat_bonus or 0.0)

    # ── Signal 9: Recency bonus (cached, refreshed every 6h) ──────
    recency = float(provider.cached_recency_score or 0.1)

    # ── Final weighted score ──────────────────────────────────────
    score = (
        service_rating    * WEIGHTS['service_rating']  +
        overall_rating    * WEIGHTS['overall_rating']  +
        completion_rate   * WEIGHTS['completion_rate'] +
        response_speed    * WEIGHTS['response_speed']  +
        experience        * WEIGHTS['experience']      +
        distance_penalty  * WEIGHTS['distance']         +  # negative weight
        cancellation_rate * WEIGHTS['cancellation']     +  # negative weight
        repeat_bonus      * WEIGHTS['repeat_bookings']  +
        recency           * WEIGHTS['recency']
    )

    return round(score, 4)


def get_provider_score_breakdown(service, distance_km):
    """
    Returns detailed breakdown of a provider's ranking score.
    Used by admin panel to understand why a provider ranks where they do.

    GET /api/ai/admin/score/{id}/?lat=..&lng=..

    Zero DB queries beyond whatever the view already did to fetch
    `service` — same cached-field contract as calculate_ranking_score.
    """
    provider = service.provider

    service_rating    = float(service.service_rating or 0) / 5.0
    overall_rating    = float(provider.overall_rating or 0) / 5.0
    completion_rate   = float(service.completion_rate or 0)
    response_speed    = float(provider.cached_response_speed or 0.5)
    experience        = min(float(service.total_jobs or 0) / 200.0, 1.0)
    distance_penalty  = min(distance_km / 20.0, 1.0)
    cancellation_rate = float(provider.cached_cancellation_rate or 0.0)
    repeat_bonus      = float(provider.cached_repeat_bonus or 0.0)
    recency           = float(provider.cached_recency_score or 0.1)

    final_score = calculate_ranking_score(service, distance_km)

    return {
        'final_score': final_score,
        'signals': {
            'service_rating':    {'raw': service_rating,    'weighted': round(service_rating * WEIGHTS['service_rating'], 4)},
            'overall_rating':    {'raw': overall_rating,    'weighted': round(overall_rating * WEIGHTS['overall_rating'], 4)},
            'completion_rate':   {'raw': completion_rate,   'weighted': round(completion_rate * WEIGHTS['completion_rate'], 4)},
            'response_speed':    {'raw': response_speed,    'weighted': round(response_speed * WEIGHTS['response_speed'], 4)},
            'experience':        {'raw': experience,        'weighted': round(experience * WEIGHTS['experience'], 4)},
            'distance_penalty':  {'raw': distance_penalty,  'weighted': round(distance_penalty * WEIGHTS['distance'], 4)},
            'cancellation_rate': {'raw': cancellation_rate, 'weighted': round(cancellation_rate * WEIGHTS['cancellation'], 4)},
            'repeat_bonus':      {'raw': repeat_bonus,      'weighted': round(repeat_bonus * WEIGHTS['repeat_bookings'], 4)},
            'recency':           {'raw': recency,           'weighted': round(recency * WEIGHTS['recency'], 4)},
        },
        'weights': WEIGHTS,
        'signals_last_updated': (
            provider.ranking_signals_updated_at.isoformat()
            if provider.ranking_signals_updated_at else None
        ),
    }