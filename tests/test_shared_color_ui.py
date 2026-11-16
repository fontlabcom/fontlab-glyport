# this_file: tests/test_shared_color_ui.py
"""Complete original color methods, observable order and retained foreign policy."""
from types import MethodType
from types import SimpleNamespace as NS

import color_ui_originals as old
import fontlabapp.qt.colors as shared
import pytest

from fontlab_glyport.ui.cocoa_controls import NSTextField
from fontlab_glyport.ui.vanilla_controls import Box, ColorWell, _rgba_css


def palette_trace(original,label,background,color_present,profile,fail,replace):
    log=[]
    class Fault(Exception):pass
    def event(*v):
        log.append(v)
        if v[0]==fail:raise Fault()
    class Meta(type):
        def __getattribute__(cls,name):
            if name in ('Window','Base','WindowText','Text'):event('role',name)
            return type.__getattribute__(cls,name)
    class Palette(metaclass=Meta):
        Window,Base,WindowText,Text='window','base','windowtext','text'
        def __init__(self):event('default')
        @property
        def setColor(self):
            event('setter-read')
            return lambda role,color:event('setColor',role,color)
    current=object.__new__(Palette)
    class Widget:
        def __init__(self,name):self.name=name
        @property
        def palette(self):
            event('palette-read',self.name)
            def get():event('palette-call');return current
            return current if profile=='property' else get
        def setPalette(self,palette):event('setPalette',self.name,palette is current)
        def setAutoFillBackground(self,flag):event('autofill',self.name,flag)
    class Gui:
        @property
        def QPalette(self):event('factory');return Palette
    owner=NS(_env=NS(qt=NS(QtGui=Gui())),_qt=Widget('first'),_label=label)
    class Color:
        def qcolor(self,qt):
            event('convert')
            if replace:owner._qt=Widget('replacement')
            return 'native-alpha'
    color=Color() if color_present else None
    method=(old.NSTextField__setBackgroundColor_ if background else old.NSTextField__setTextColor_) if original else (NSTextField.setBackgroundColor_ if background else NSTextField.setTextColor_)
    try:method(owner,color)
    except Fault:log.append(('same-failure',))
    log.append(('text-cache',getattr(owner,'_text_color','unset') is color))
    return log

@pytest.mark.parametrize('label',[False,True])
@pytest.mark.parametrize('background',[False,True])
@pytest.mark.parametrize('present',[False,True])
@pytest.mark.parametrize('profile',['property','method'])
@pytest.mark.parametrize('fail',[None,'factory','default','palette-read','palette-call','role','convert','setColor','setter-read','autofill','setPalette'])
@pytest.mark.parametrize('replace',[False,True])
def test_full_original_palette_methods_when_all_profiles_and_failures_then_identical(label,background,present,profile,fail,replace):
    args=(label,background,present,profile,fail,replace)
    assert palette_trace(False,*args)==palette_trace(True,*args)


def box_trace(original,fill,border,width,radius,fail):
    log=[]
    class Fault(Exception):pass
    def event(*v):
        log.append(v)
        if v[0]==fail:raise Fault()
    class Color:
        def __init__(self,name):self.name=name
        @property
        def rgba(self):event(self.name);return (0.5,0,1,0.25)
    owner=NS(_view=NS(setStyleSheet=lambda sheet:event('style',sheet)))
    try:(old.Box___style_box if original else Box._style_box)(owner,Color('fill') if fill else None,Color('border') if border else None,width,radius)
    except Fault:log.append(('same-failure',))
    return log

@pytest.mark.parametrize('fill',[False,True])
@pytest.mark.parametrize('border',[False,True])
@pytest.mark.parametrize('width',[None,0,0.5,2.5,-1])
@pytest.mark.parametrize('radius',[None,0,2.5])
@pytest.mark.parametrize('fail',[None,'fill','border','style'])
def test_full_original_box_when_all_optional_rules_then_exact_order_and_errors(fill,border,width,radius,fail):
    args=(fill,border,width,radius,fail)
    assert box_trace(False,*args)==box_trace(True,*args)


def well_trace(original,quiet,fail,repeat):
    log=[]
    class Fault(Exception):pass
    def event(*v):
        log.append(v)
        if v[0]==fail:raise Fault()
    owner=object.__new__(ColorWell);owner._color_dialog=shared.ColorDialog()
    class QColor:
        def __init__(self,*v):event('qcolor',v)
    class Dialog:
        def __init__(self,color,parent):event('dialog');self.colorSelected='colorSelected'
        def open(self):event('open')
        def deleteLater(self):event('delete')
    class Gui:
        @property
        def QColor(self):event('color-factory');return QColor
        @property
        def QColorDialog(self):event('dialog-factory');return Dialog
    owner._env=NS(qt=NS(QtGui=Gui()),report=lambda callback,sender:event('report',sender is owner))
    owner._view=NS(setStyleSheet=lambda sheet:event('style',sheet));owner._quiet=quiet;owner._callback=lambda sender:None
    owner._track=lambda signal,slot:event('track',signal,owner._dialog is not None)
    owner._color=NS(rgba=(0.5,0.1,0.9,0.25))
    owner._rgba255=MethodType(old.ColorWell___rgba255 if original else ColorWell._rgba255,owner)
    owner.set=MethodType(old.ColorWell__set if original else ColorWell.set,owner)
    owner._picked=MethodType(old.ColorWell___picked if original else ColorWell._picked,owner)
    pick=old.ColorWell___pick if original else ColorWell._pick
    picked=NS(redF=lambda:0.1,greenF=lambda:0.2,blueF=lambda:0.3,alphaF=lambda:0.4)
    try:
        pick(owner)
        if repeat:pick(owner)
        owner._picked(picked)
    except Fault:log.append(('same-failure',))
    log.append(('owned-dialog',owner._dialog is not None))
    return log

@pytest.mark.parametrize('quiet',[False,True])
@pytest.mark.parametrize('fail',[None,'dialog-factory','color-factory','qcolor','dialog','track','open','style','report'])
@pytest.mark.parametrize('repeat',[False,True])
def test_full_original_well_when_selection_repeated_open_and_failures_then_exact(quiet,fail,repeat):
    assert well_trace(False,quiet,fail,repeat)==well_trace(True,quiet,fail,repeat)


def test_foreign_color_conversion_when_none_then_original_failure_no_clamping_added():
    with pytest.raises(AttributeError):_rgba_css(None)
    color=NS(rgba=(-1,2,0.5,0))
    assert _rgba_css(color)==old._rgba_css(color)=='rgba(-255, 510, 128, 0)'


@pytest.mark.parametrize('fail',[None,'dialog-factory','color-factory','channels-method'])
def test_original_picker_when_factory_and_channel_lookup_are_observable_then_exact(fail):
    def trace(original):
        log=[]
        def event(name):
            log.append(name)
            if name==fail:raise RuntimeError(name)
        class Well(ColorWell):
            @property
            def _rgba255(self):
                event('channels-method')
                return lambda:(1,2,3,4)
        class Dialog:
            colorSelected='selected'
            def __init__(self,*args):log.append('construct')
            def open(self):log.append('open')
        class Gui:
            @property
            def QColorDialog(self):event('dialog-factory');return Dialog
            @property
            def QColor(self):event('color-factory');return lambda *v:v
        owner=object.__new__(Well);owner._color_dialog=shared.ColorDialog();owner._view=None
        owner._env=NS(qt=NS(QtGui=Gui()));owner._track=lambda *args:log.append('track')
        try:(old.ColorWell___pick if original else ColorWell._pick)(owner)
        except RuntimeError:log.append('same-failure')
        return log
    assert trace(False)==trace(True)
