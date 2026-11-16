# this_file: src/fontlab_glyport/model/bulk.py
"""Stage collection inputs, then publish one reversible layer edit."""

from contextlib import nullcontext

from ..errors import PartialFailure
from .backend import AnchorInfo, ComponentInfo, GuideInfo, PathInfo


def validate_infos(field, infos, component_exists):
    allowed = {
        "paths": (PathInfo,),
        "components": (ComponentInfo,),
        "shapes": (PathInfo, ComponentInfo),
        "anchors": (AnchorInfo,),
        "guides": (GuideInfo,),
    }[field]
    names = set()
    for info in infos:
        if not isinstance(info, allowed):
            raise TypeError(f"Invalid {field} item")
        if isinstance(info, ComponentInfo) and not component_exists(info.componentName):
            raise ValueError(f"No glyph named {info.componentName!r}")
        if isinstance(info, AnchorInfo):
            if info.name in names:
                raise ValueError("Duplicate anchor name")
            names.add(info.name)
        if isinstance(info, PathInfo):
            for node in info.nodes:
                if node.type not in ("line", "curve", "offcurve", "qcurve"):
                    raise ValueError(f"Unknown node type {node.type!r}")


def replace_collection(layer, field, values):
    from .proxies import GSAnchor, GSComponent, GSGuide, GSPath

    types = {
        "paths": (GSPath,),
        "components": (GSComponent,),
        "shapes": (GSPath, GSComponent),
        "anchors": (GSAnchor,),
        "guides": (GSGuide,),
    }[field]
    values = list(values or ())
    if any(not isinstance(value, types) for value in values):
        raise TypeError(
            f"{field} requires {' or '.join(cls.__name__ for cls in types)}"
        )
    staged = [value.copy() for value in values]
    layer._check()
    backend = layer._font._model._backend
    backend.validate_collection(layer._id, field, tuple(v._data() for v in staged))
    grouping = getattr(backend, "path_grouping", None)
    groups = grouping(layer._id) if field == "paths" and grouping else ()
    staging = getattr(backend, "stage_collection", None)
    scope = (
        staging(layer._id, field, tuple(v._data() for v in staged))
        if staging
        else nullcontext()
    )
    with scope:
        state = backend.snapshot_collection(layer._id, stage=True)
        with layer._font.undo_group(f"Glyport {field}"):
            try:
                backend.prepare_collection(layer._id, field, state=state)
                target = getattr(layer, field)
                for item in list(target):
                    target._remove(item)  # membership was snapshotted before mutation
                for item in staged:
                    target.append(item)
                if groups:
                    backend.restore_path_grouping(layer._id, groups)
            except BaseException as error:
                try:
                    backend.restore_collection(layer._id, state)
                except BaseException as recovery:
                    failure = PartialFailure(
                        f"Could not restore {field}: {recovery}",
                        capability=f"GSLayer.{field}",
                    )
                    failure.errors = (error, recovery)
                    raise failure from recovery
                raise
