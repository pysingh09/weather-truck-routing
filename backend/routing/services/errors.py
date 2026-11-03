class UpstreamError(Exception):
    """An upstream provider (Valhalla / Photon / Open-Meteo) failed or timed out -> HTTP 502."""
