# this_file: tests/test_shared_table_items.py
"""Whole original methods, including failure and native lookup timing."""
from types import SimpleNamespace as NS

import fontlabapp.qt.tables.items as shared
import pytest
from table_item_originals import list__fill_row, list__flags, nstableview__place_item

from fontlab_glyport.ui.cocoa_table import NSTableView
from fontlab_glyport.ui.vanilla_controls import List, _cell_text


def trace(original,profile,value,editable,checkbox=False,fail=None):
    log=[]
    class Failure(Exception):pass
    def event(*v):
        log.append(v)
        if v[0]==fail:raise Failure()
    class Cell:
        def __init__(self,text):event('new',text)
        def setFlags(self,flags):event('flags',flags)
        def setCheckState(self,state):event('check',state)
    class Values(dict):
        def get(self,key):event('get',key);return super().get(key)
    class Gui:
        @property
        def QTableWidgetItem(self):event('factory');return Cell
    flags=NS(ItemIsSelectable=1,ItemIsEnabled=2,ItemIsEditable=4,ItemIsUserCheckable=8,Checked=2,Unchecked=0)
    table=NS(setItem=lambda row,col,cell:event('place',row,col))
    owner=NS(_env=NS(qt=NS(QtGui=Gui(),QtCore=NS(Qt=flags))),_qt=table,_view=table)
    owner._flags=lambda flag:(list__flags if original else List._flags)(owner,flag)
    owner._items=[Values(value=value)];owner._columns=[NS(key='value',cell_title='literal checkbox',checkbox=checkbox,editable=editable)]
    method=(nstableview__place_item if original else NSTableView._place_item) if profile=='cocoa' else (list__fill_row if original else List._fill_row)
    try:
        if profile=='cocoa':method(owner,-1,99,value,editable)
        else:method(owner,0)
    except Failure:log.append(('same-failure',))
    return log


@pytest.mark.parametrize('profile',['cocoa','vanilla'])
@pytest.mark.parametrize('value',[None,'',False,0,1,'literal @\u00a0\u2028\u2029\0','𐀀'])
@pytest.mark.parametrize('editable',[False,True])
@pytest.mark.parametrize('checkbox',[False,True])
@pytest.mark.parametrize('fail',[None,'factory','new','get','check','flags','place'])
def test_full_original_methods_when_all_branches_then_exact_order_values_and_failure(profile,value,editable,checkbox,fail):
    assert trace(False,profile,value,editable,checkbox,fail)==trace(True,profile,value,editable,checkbox,fail)


def test_historical_cell_formatter_when_imported_then_exact_shared_identity():
    assert _cell_text is shared.cell_text


def test_cocoa_when_value_conversion_replaces_table_then_replacement_receives_item():
    log=[];owner=NS(_env=NS(qt=NS(QtGui=NS(),QtCore=NS(Qt=NS(ItemIsSelectable=1,ItemIsEnabled=2,ItemIsEditable=4)))))
    owner._qt=NS(setItem=lambda *args:log.append('old'))
    class Item:
        def __init__(self,text):log.append(text)
        def setFlags(self,flags):pass
    owner._env.qt.QtGui.QTableWidgetItem=Item
    class Value:
        def __str__(self):owner._qt=NS(setItem=lambda *args:log.append('new'));return 'text'
    NSTableView._place_item(owner,0,0,Value(),True)
    assert log==['text','new']
