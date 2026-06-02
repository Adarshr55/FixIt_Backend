from abc    import ABC, abstractmethod
from math   import radians, cos, sin, asin, sqrt
from .ranking import calculate_ranking_score


class LocationBackend(ABC):
    """
    Abstract base — swap Haversine for PostGIS in Phase 5
    without touching any view or service code.
    """
    @abstractmethod
    def find_nearby(self, services, customer_lat, customer_lng):
        """
        Returns list of:
        [{ 'service': ProviderService, 'distance_km': float, 'score': float }]
        sorted by score descending.
        """
        raise NotImplementedError


class HaversineLocationBackend(LocationBackend):
    """
    Pure Python distance calculation.
    Used until PostGIS is set up in Phase 5.
    Accurate enough for city-level radius queries.
    O(n) — fine for hundreds of providers, needs PostGIS at scale.
    """

    def _distance_km(self, lat1, lon1, lat2, lon2):
        R = 6371.0
        lat1, lon1, lat2, lon2 = map(float,    [lat1, lon1, lat2, lon2])
        lat1, lon1, lat2, lon2 = map(radians,  [lat1, lon1, lat2, lon2])
        dlat = lat2 - lat1
        dlon = lon2 - lon1
        a = (
            sin(dlat / 2) ** 2 +
            cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
        )
        return R * 2 * asin(sqrt(a))

    def find_nearby(self, services, customer_lat, customer_lng):
        results = []
        for service in services:
            provider = service.provider

            # skip providers without location set
            if provider.latitude is None or provider.longitude is None:
                continue

            distance_km = self._distance_km(
                customer_lat, customer_lng,
                float(provider.latitude), float(provider.longitude)
            )

            # only include if customer is within provider's service radius
            if distance_km > float(provider.service_radius_km or 10):
                continue

            results.append({
                'service':     service,
                'distance_km': round(distance_km, 1),
                'score':       calculate_ranking_score(service, distance_km),
            })

        results.sort(key=lambda x: x['score'], reverse=True)
        return results


class PostGISLocationBackend(LocationBackend):
    """
    Phase 5 — replaces HaversineLocationBackend.
    Uses PostgreSQL PostGIS ST_DWithin for DB-level geo filtering.
    Much faster at scale — filters in SQL before Python loop.

    To activate:
    1. pip install psycopg2 django.contrib.gis
    2. Add 'django.contrib.gis' to INSTALLED_APPS
    3. Add PointField to ProviderProfile model
    4. Change ProviderDiscoveryService to use PostGISLocationBackend()

    Nothing else changes — views, serializers, services stay identical.
    """

    def find_nearby(self, services, customer_lat, customer_lng):
        from django.contrib.gis.geos    import Point
        from django.contrib.gis.db.models.functions import Distance
        from django.contrib.gis.measure import D

        customer_point = Point(customer_lng, customer_lat, srid=4326)

        # Single DB query — no Python loop needed
        nearby = services.filter(
            provider__location__dwithin=(customer_point, D(km=50))
        ).annotate(
            distance=Distance('provider__location', customer_point)
        ).order_by('distance')

        results = []
        for service in nearby:
            distance_km = round(service.distance.km, 1)
            if distance_km > float(service.provider.service_radius_km or 10):
                continue
            results.append({
                'service':     service,
                'distance_km': distance_km,
                'score':       calculate_ranking_score(service, distance_km),
            })

        results.sort(key=lambda x: x['score'], reverse=True)
        return results