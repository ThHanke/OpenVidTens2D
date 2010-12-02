# -*- coding: cp1252 -*-
import wx

EVT_RESULT_ID = wx.NewId()

def EVT_RESULT(win, func):
    """Define Result Event."""
    win.Connect(-1, -1, EVT_RESULT_ID, func)
class ResultEvent(wx.PyEvent):
    """Simple event to carry arbitrary result data."""
    def __init__(self, msg,data):
#    def __init__(self, msg, data,elliplist):
        """Init Result Event."""
        wx.PyEvent.__init__(self)
        self.SetEventType(EVT_RESULT_ID)
        self.msg = msg
        self.data=data

class EllipPar:
    def __init__(self):
        self.Num=int
        self.MidPos=float,float
        self.Size=float,float
        self.Angle=float
        self.mov=float,float
class LinePar:
    def __init__(self):
        self.Num=int
        self.Pt1=int
        self.Pt2=int
        self.Pos=int,int
        
