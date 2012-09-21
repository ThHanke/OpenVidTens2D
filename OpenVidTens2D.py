# -*- coding: cp1252 -*-
import wx,cv

from time import clock
from time import sleep

import multiprocessing

#globals
import config

#modules
import LiveCamWin
import LiveTrackWin
import LivePlotWin




class InitFrame(wx.Frame):
    def __init__(self,parent):
        screensize=wx.Display().GetGeometry()
        self.winsize = 510,340
        wx.Frame.__init__(self,None,wx.ID_ANY,title='Test',pos=(int(screensize[2]/2-self.winsize[0]/2),int(screensize[3]/2-self.winsize[1]/2)),size=self.winsize,style= wx.BORDER_RAISED |wx.STAY_ON_TOP  )
        self.logopanel=wx.Panel(self, wx.ID_ANY, style=wx.BORDER_RAISED)
        wx.StaticBitmap(self.logopanel, -1, wx.Image('logoOpenVidTens.png', wx.BITMAP_TYPE_PNG).ConvertToBitmap(), (0, 0))
        
        self.panelsizer=wx.BoxSizer(wx.HORIZONTAL)
        self.panelsizer.Add(self.logopanel,2,wx.EXPAND)
        self.SetSizer(self.panelsizer)
        self.status=self.CreateStatusBar()
        self.status.SetFieldsCount(2)
        self.status.SetStatusWidths([-1,int(self.winsize[0]/3)])
        rect = self.status.GetFieldRect(1)
        self.status.progressbar = wx.Gauge(self.status, -1, 100,wx.Point(rect.x + 2, rect.y + 2), wx.Size(int(self.winsize[0]/3)-4 , rect.height - 4) )
        
        self.Show(True)
        self.logopanel.Update()
        
        #try to init camera
        self.status.SetStatusText('Init Camera Interface')
        self.CreateLiveCamView(parent)
        self.status.progressbar.SetValue(33)
        #init tracking module 
        self.status.SetStatusText('Init Tracking Module ')
        self.CreateLiveTrackView(parent,parent.LiveCamWin)
        self.status.progressbar.SetValue(66)
        #init dataplotting module 
        self.status.SetStatusText('Init Data Aquisition Module ')
        self.CreateLivePlotView(parent,parent.LiveTrackWin)
        self.status.progressbar.SetValue(100)
        
        self.status.SetStatusText('Initilization succeeded')
        sleep(0.1)
        self.Destroy()
    def CreateLiveCamView(self,parent):
        parent.LiveCamWin=LiveCamWin.LiveCamWin()
    def CreateLiveTrackView(self,parent,source):
        parent.LiveTrackWin=LiveTrackWin.LiveTrackWin(source)
        source.childs.append(parent.LiveTrackWin)
    def CreateLivePlotView(self,parent,source):
        parent.LivePlotWin=LivePlotWin.LivePlotWin(source)
        source.childs.append(parent.LivePlotWin)



        
        
class App(wx.App):
    def OnInit(self):
        
        self.InitFrame=InitFrame(self)
        return True

if __name__=="__main__":
    multiprocessing.freeze_support()    
    #app = App(redirect=False)
    app = App(redirect=0)
    app.MainLoop()
