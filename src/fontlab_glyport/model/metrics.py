# this_file: src/fontlab_glyport/model/metrics.py
"""Read-only Glyphs metric definitions for FontLab's native master metrics.

No synthetic Small Caps/custom definitions or overshoot values are invented.
"""

from .proxies import ProxySequence, _Explicit, _unsupported

_METRICS = (
    (1, "Ascender", "ascender"),
    (2, "Cap Height", "capHeight"),
    (4, "x-Height", "xHeight"),
    (7, "Descender", "descender"),
    (8, "Baseline", None),
    (9, "Italic Angle", "italicAngle"),
)


class GSMetric(_Explicit):
    def __init__(self, kind, name, field):
        self._kind, self._name, self._field = kind, name, field

    id = property(lambda self: f"glyport.metric.{self._kind}")
    type = property(lambda self: self._kind)
    name = property(lambda self: self._name)
    filter = property(lambda self: None)


class GSMetricValue(_Explicit):
    def __init__(self, master, metric):
        self._master, self._metric = master, metric

    @property
    def position(self):
        values = self._master._metrics()
        return getattr(values, self._metric._field) if self._metric._field else 0.0

    @property
    def overshoot(self):
        _unsupported("GSMetricValue.overshoot")


def font_metrics(font):
    def values():
        font._check()
        return [GSMetric(*record) for record in _METRICS]

    return ProxySequence(values, lambda metric: (metric.id, metric.name))


def master_metrics(master):
    return {metric.id: GSMetricValue(master, metric) for metric in master._font.metrics}
