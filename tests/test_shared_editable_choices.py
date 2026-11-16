# this_file: tests/test_shared_editable_choices.py
"""Foreign callback and continuous policy stay outside the shared commit mechanic."""
from types import SimpleNamespace as NS

import pytest

from fontlab_glyport.ui.cocoa_controls import NSComboBox, NSPathControl, NSTextField
from fontlab_glyport.ui.vanilla_controls import ComboBox


class Edit:
    def __init__(self, modified=True, fail=False):
        self.modified, self.fail, self.events = modified, fail, []
        self.text = ' /tmp/owned-example '
    def isModified(self):
        self.events.append('read')
        return self.modified
    def setModified(self, flag):
        self.events.append(('ack', flag))
        if self.fail: raise RuntimeError('ack')
        self.modified = flag
    def lineEdit(self): return self


@pytest.mark.parametrize('args', [(), (1,), ('choice',)])
def test_cocoa_activation_filters_string_and_acknowledges_before_send(args):
    edit = Edit()
    owner = NS(_qt=edit, _send=lambda: edit.events.append('send'))
    NSComboBox._activated(owner, *args)
    assert edit.events == ([] if args and isinstance(args[0], str) else [('ack',False),'send'])


@pytest.mark.parametrize('modified', [False, True])
@pytest.mark.parametrize('continuous', [False, True])
def test_textfield_commit_acknowledges_in_continuous_mode_without_duplicate_action(modified, continuous):
    edit = Edit(modified)
    owner = NS(_qt=edit, _continuous=continuous, _send=lambda: edit.events.append('send'))
    NSTextField._finished(owner)
    expected = ['read'] + ([('ack',False)] if modified else [])
    if modified and not continuous: expected += ['send']
    assert edit.events == expected
    NSTextField._finished(owner)
    assert edit.events == expected + ['read']


@pytest.mark.parametrize('cls', [NSComboBox, ComboBox])
@pytest.mark.parametrize('failure', [False, True])
def test_combo_commit_returns_or_reports_once_and_propagates_ack_error(cls, failure):
    edit = Edit(fail=failure)
    owner = NS(_qt=edit, _view=edit, _send=lambda: edit.events.append('send'))
    callback = (lambda: NSComboBox._finished(owner)) if cls is NSComboBox else (lambda: ComboBox._commit(owner, ()))
    if failure:
        with pytest.raises(RuntimeError, match='ack'): callback()
        assert edit.events == ['read',('ack',False)] and edit.modified
    else:
        result = callback()
        assert result is (None if cls is NSComboBox else True)
        assert edit.events == ['read',('ack',False)] + (['send'] if cls is NSComboBox else [])
        result = callback()
        assert result is (None if cls is NSComboBox else False)


def test_path_control_acknowledges_before_foreign_url_conversion_and_report():
    edit = Edit()
    owner = NS(_qt=edit, _url=None, _send=lambda: edit.events.append('send'))
    NSPathControl._edited(owner)
    assert edit.events == ['read',('ack',False),'send']
    assert owner._url.path() == '/tmp/owned-example'
    NSPathControl._edited(owner)
    assert edit.events[-1] == 'read'
