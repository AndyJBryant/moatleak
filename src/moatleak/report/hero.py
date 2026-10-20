"""Hero section: the radial inference network plus the country-cluster share cards."""
from moatleak.report import svg
from moatleak.report.clusters import clusters_svg
from moatleak.report.network import radial_svg


def section(payload: dict) -> str:
    if payload.get("empty"):
        return ""
    return ('<section id="hero"><h2>Your inference network</h2>'
            + svg.figure("hero-radial", radial_svg(payload))
            + "<h3>Share cards</h3>"
            + svg.figure("hero", clusters_svg(payload))
            + svg.figure("hero-wide", clusters_svg(payload, wide=True)) + "</section>")
