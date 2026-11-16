# this_file: src/fontlab_glyport/model/outline_ops.py
"""Shared backend outline edits; geometry is staged before existing guarded writes."""

from contextlib import nullcontext

from ..errors import PartialFailure
from .outline_geometry import _direction_paths, _draft, _extreme_paths
from .pens import draw_info, path_info


class OutlineOperations:
    """Operations implemented by both native and in-memory backends."""

    def draw_layer(
        self, layer_id, pen, *, points=False, contours=True, components=True
    ):
        """Read through the backend boundary, then emit the pen protocol."""
        draw_info(
            self.outline_layer(layer_id),
            pen,
            points=points,
            contours=contours,
            components=components,
        )

    def _replace_outline_paths(self, layer_id, paths, *, undo_group=nullcontext):
        old = self.outline_layer(layer_id)
        if old.paths == tuple(paths):
            return
        self.validate_collection(layer_id, "paths", tuple(paths))
        old_ids = {path.id for path in old.paths}
        positions = [i for i, token in enumerate(old.shape_ids) if token in old_ids]
        grouping = getattr(self, "path_grouping", None)
        groups = grouping(layer_id) if grouping else ()
        staging = getattr(self, "stage_collection", None)
        scope = staging(layer_id, "paths", tuple(paths)) if staging else nullcontext()
        with scope, undo_group():
            state = self.snapshot_collection(layer_id, stage=True)
            try:
                self.prepare_collection(layer_id, "paths", state=state)
                for path in old.paths:
                    self.remove_path(layer_id, path.id)
                for index, path in enumerate(paths):
                    if index < len(positions):
                        self.insert_path(layer_id, positions[index], path)
                    else:
                        self.append_path(layer_id, path)
                if groups:
                    self.restore_path_grouping(layer_id, groups)
            except BaseException as error:
                self._restore_outlines(layer_id, state, error)
                raise

    def _restore_outlines(self, layer_id, state, error):
        try:
            self.restore_collection(layer_id, state)
        except BaseException as recovery:
            failure = PartialFailure(
                f"Could not restore layer outlines: {recovery}",
                capability="GSLayer.outlines.rollback",
            )
            failure.errors = error, recovery
            raise failure from recovery

    def remove_layer_overlap(
        self, layer_id, *, check_selection=False, undo_group=nullcontext
    ):
        """Join selected or all closed contours with the existing boolean extra."""
        from .copies import DetachedLayer
        from .detached_geometry import remove_overlap

        info = self.outline_layer(layer_id)
        chosen = [
            p
            for p in info.paths
            if not check_selection or any(n.selected for n in p.nodes)
        ]
        if not chosen:
            return
        detached = DetachedLayer()
        detached.shapes = [_draft(p) for p in chosen]
        paths = tuple(path_info(p) for p in remove_overlap(detached))
        if _same_outlines(chosen, paths):
            return
        self._replace_outline_paths(
            layer_id,
            (*[p for p in info.paths if p not in chosen], *paths),
            undo_group=undo_group,
        )

    def correct_layer_direction(self, layer_id):
        """Correct closed-contour winding; retain open paths and components."""
        self._replace_outline_paths(
            layer_id, _direction_paths(self.outline_layer(layer_id).paths)
        )

    def add_layer_extrema(
        self, layer_id, *, force=False, check_selection=False, undo_group=nullcontext
    ):
        """Insert exact extrema; force is accepted because no grid rounding occurs."""
        self._replace_outline_paths(
            layer_id,
            _extreme_paths(self.outline_layer(layer_id).paths, check_selection),
            undo_group=undo_group,
        )

    def decompose_layer_components(self, layer_id):
        """Expand component outlines recursively using each backend's existing route."""
        # Preflight references before removing the first component (cycles too).
        info = self.outline_layer(layer_id)
        self.validate_component_expansion(layer_id, info.components)
        if not info.components:
            return
        state = self.snapshot_collection(layer_id, stage=True)
        try:
            while info.components:
                for component in info.components:
                    self.decompose_component(
                        layer_id, component.id, on_detach=lambda: None
                    )
                info = self.outline_layer(layer_id)
        except BaseException as error:
            self._restore_outlines(layer_id, state, error)
            raise


def _same_outlines(first, second):
    """Compare geometry independently of new tokens and closed-path rotation."""

    def signature(path):
        nodes = tuple((node.x, node.y, node.type) for node in path.nodes)
        if path.closed and nodes:
            nodes = min(nodes[index:] + nodes[:index] for index in range(len(nodes)))
        return path.closed, nodes

    return sorted(map(signature, first)) == sorted(map(signature, second))
