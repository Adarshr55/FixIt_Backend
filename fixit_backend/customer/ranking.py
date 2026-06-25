# def calculate_ranking_score(service, distance_km):
#     """
#     Smart ranking — from project docs:
#     score = rating*0.4 + completion_rate*0.25 + experience_bonus*0.20 - distance_penalty*0.15

#     All inputs normalized to 0-1 range so weights stay meaningful.
#     response_speed added in Phase 3 when we track accepted_at timestamps.
#     """
#     rating           = float(service.service_rating  or 0)
#     completion_rate  = float(service.completion_rate or 0)
#     total_jobs       = float(service.total_jobs      or 0)

#     # caps at 1.0 when provider has 100+ jobs
#     experience_bonus = min(total_jobs / 100.0, 1.0)

#     # caps at 1.0 when provider is 10+ km away
#     distance_penalty = min(distance_km / 10.0, 1.0)

#     score = (
#         rating          * 0.40 +
#         completion_rate * 0.25 +
#         experience_bonus * 0.20 -
#         distance_penalty * 0.15
#     )
#     return round(score, 4)


from ai_engine.ranking import calculate_ranking_score

__all__ = ['calculate_ranking_score']