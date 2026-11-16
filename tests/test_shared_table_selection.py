# this_file: tests/test_shared_table_selection.py
"""Compatibility wrappers retain guards and observable native signal timing."""
from types import SimpleNamespace as NS

import pytest

from fontlab_glyport.ui.cocoa_table import NSTableView
from fontlab_glyport.ui.vanilla_controls import List


@pytest.mark.parametrize('fail', [False, True])
def test_cocoa_selection_guards_native_callbacks_and_restores_counter(fail):
    events = []
    owner = NS(_selecting=2)
    class Widget:
        def clearSelection(self): events.append(('clear', owner._selecting))
        def model(self): return self
        def selectionModel(self): return self
        def index(self, row, col): return (row, col)
        def select(self, index, flags):
            events.append(('select', index, flags, owner._selecting))
            if fail: raise RuntimeError('native')
    owner._qt = Widget()
    owner.numberOfRows = lambda: 3
    owner._selection_changed = lambda: events.append(('changed', owner._selecting))
    owner._env = NS(qt=NS(QtGui=NS(QItemSelectionModel=NS(Select=1, Rows=32))))
    if fail:
        with pytest.raises(RuntimeError, match='native'):
            NSTableView._select(owner, [1, 2], extend=False)
        assert events == [('clear', 3), ('select', (1, 0), 33, 3)]
    else:
        NSTableView._select(owner, [1, 2], extend=False)
        assert events == [('clear', 3), ('select', (1, 0), 33, 3),
                          ('select', (2, 0), 33, 3), ('changed', 2)]
    assert owner._selecting == 2


@pytest.mark.parametrize('fail', [False, True])
@pytest.mark.parametrize('quiet', [False, True])
def test_vanilla_selection_keeps_quiet_state_and_original_explicit_notification(fail, quiet):
    events = []
    owner = NS(_quiet=quiet, _columns=['first', 'second'])
    class Widget:
        def clearSelection(self): events.append(('clear', owner._quiet))
        def setRangeSelected(self, selected, flag):
            events.append(('range', selected, flag, owner._quiet))
            if fail: raise RuntimeError('native')
    owner._view = Widget()
    owner._env = NS(qt=NS(QtGui=NS(QTableWidgetSelectionRange=lambda *args: args)))
    owner._quietly = lambda action: List._quietly(owner, action)
    owner._select = lambda rows: List._select(owner, rows)
    owner._report_selection = lambda: events.append(('report', owner._quiet))
    if fail:
        with pytest.raises(RuntimeError, match='native'):
            List.setSelection(owner, [2, 0, 2])
        assert events == [('clear', True), ('range', (0, 0, 0, 1), True, True)]
    else:
        List.setSelection(owner, [2, 0, 2])
        assert events == [('clear', True), ('range', (0, 0, 0, 1), True, True),
                          ('range', (2, 0, 2, 1), True, True), ('report', quiet)]
    assert owner._quiet is quiet


@pytest.mark.parametrize('mode', ['unbound', 'missing', 'item', 'plain-view',
                                  'setter-view', 'stale-getter', 'stale-setter'])
def test_bound_row_refresh_preserves_reentrant_generation_and_cell_policy(mode):
    events = []
    table = NS(_generation=4, _filling=2, _columns=[], _cell_views={})
    def value():
        events.append('read')
        if mode == 'stale-getter': table._generation += 1
        return 'changed'
    def set_value(text):
        events.append(('view', text))
        if mode == 'stale-setter': table._generation += 1
    column = NS() if mode == 'unbound' else NS(_value_binding=(None, 'label'))
    table._columns = [column]
    table._bound_rows = lambda: [NS(label=value)]
    table._stale = lambda generation: generation != table._generation
    table._resync = lambda generation: events.append(('resync', generation))
    item = NS(setText=lambda text: events.append(('item', text)))
    table._qt = NS(item=lambda row, column: None if mode == 'missing' else item)
    if mode in ('plain-view', 'setter-view', 'stale-setter'):
        table._cell_views[(0, 0)] = NS() if mode == 'plain-view' else NS(setObjectValue_=set_value)
    NSTableView._rows_changed(table)
    assert table._filling == 2, 'Programmatic fill state must be restored'
    expected = [] if mode == 'unbound' else ['read']
    if mode in ('setter-view', 'stale-setter'): expected += [('view', 'changed')]
    if mode == 'item': expected += [('item', 'changed')]
    if not mode.startswith('stale-'): expected += [('resync', 4)]
    assert events == expected


def test_bound_row_native_write_failure_restores_fill_depth_and_stops_resync():
    events = []
    def fail(text):
        events.append(text)
        raise RuntimeError('native cell')
    table = NS(_generation=4, _filling=2,
               _columns=[NS(_value_binding=(None, 'label'))], _cell_views={},
               _bound_rows=lambda: [{'label': 'changed'}], _stale=lambda generation: False,
               _qt=NS(item=lambda *args: NS(setText=fail)),
               _resync=lambda generation: events.append('resync'))
    with pytest.raises(RuntimeError, match='native cell'):
        NSTableView._rows_changed(table)
    assert table._filling == 2 and events == ['changed']


@pytest.mark.parametrize('phase', ['count', 'value', 'view'])
def test_reload_invalidated_by_callback_retires_unplaced_view_and_restores_guard(phase):
    from test_ui_nib_table import NIB, _load
    kit, owner, _instance = _load(NIB)
    table = owner.plainTable
    table.setDelegate_(owner)
    child = kit['NSTextField'].alloc().initWithFrame_(((0, 0), (20, 20)))
    def stale_count(target):
        target._generation += phase == 'count'
        return 3
    def stale_value(target, column, row):
        target._generation += phase == 'value'
        return 'unchanged'
    def stale_view(target, column, row):
        target._generation += phase == 'view'
        return child
    owner.numberOfRowsInTableView_ = stale_count
    owner.tableView_objectValueForTableColumn_row_ = stale_value
    owner.tableView_viewForTableColumn_row_ = stale_view
    table.reloadData()
    assert table._filling == 0
    assert not table._cell_views
    if phase == 'view': assert child._qt._deleted
    kit['close']()
