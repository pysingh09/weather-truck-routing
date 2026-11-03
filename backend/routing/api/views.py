from rest_framework.response import Response
from rest_framework.views import APIView

from ..services import photon, planner
from ..services.errors import UpstreamError
from .serializers import HeatmapRequestSerializer, PlanRequestSerializer, first_error


def _bad_request(serializer) -> Response:
    msg, field = first_error(serializer.errors)
    return Response({"error": msg, "field": field}, status=400)


def _upstream(exc: Exception) -> Response:
    return Response({"error": str(exc)}, status=502)


class HealthView(APIView):
    def get(self, request):
        return Response({"ok": True})


class GeocodeView(APIView):
    def get(self, request):
        q = request.query_params.get("q", "").strip()
        if len(q) < 3:
            return Response({"results": []})
        try:
            return Response({"results": photon.geocode(q)})
        except UpstreamError as exc:
            return _upstream(exc)


class PlanView(APIView):
    def post(self, request):
        s = PlanRequestSerializer(data=request.data)
        if not s.is_valid():
            return _bad_request(s)
        d = s.validated_data
        try:
            data = planner.build_plan(
                dict(d["origin"]),
                dict(d["destination"]),
                d["departure"],
                d["load_lb"],
                d["interval_mi"],
            )
        except UpstreamError as exc:
            return _upstream(exc)
        return Response(data)


class HeatmapView(APIView):
    def post(self, request):
        s = HeatmapRequestSerializer(data=request.data)
        if not s.is_valid():
            return _bad_request(s)
        d = s.validated_data
        geoms = [g["coordinates"] for g in d["route_geometries"]]
        try:
            return Response(planner.build_heatmap(d["departure"], geoms))
        except UpstreamError as exc:
            return _upstream(exc)
