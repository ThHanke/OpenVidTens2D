# -*- coding: cp1252 -*-
import wx,cv,ctypes
import threading
import Queue

from time import clock
from time import sleep

#submodule activex wrapper avt camera driver activex element
import AVTCam

#import globals
import config

ID_CPROP=wx.NewId()



class LiveCamWin(wx.Frame):
    def __init__(self):
        screensize=wx.Display().GetGeometry()
        wx.Frame.__init__(self,None,wx.ID_ANY,title='LiveCamWin',pos=(0,0),size=(screensize[2]/2,screensize[3]/2),style= wx.DEFAULT_FRAME_STYLE )
        self.status=self.CreateStatusBar()
        self.status.SetFieldsCount(2)
        self.status.SetStatusWidths([-1,65])

        

        wx.EVT_CLOSE(self, self.OnClose)

        menu=self.CreateMenu()
        self.SetMenuBar(menu)

        

        #startwerte
        self.caminterface=None
        self.datatoqueue=list()
##        self.rawimage = cv.CreateImage((100,100),8,3)
##        self.image = cv.CreateImage((100,100),8,3)
##        cv.Set(self.rawimage,0)
##        cv.Set(self.image,0)

        
        self.lasttime=0
        self.acttime=0
        self.framecount=0
        

        self.childs=list()

        #spwan queue
        self.aquirequeue=Queue.Queue(-1)
        self.piclistqueue=Queue.PriorityQueue(-1)
        #spawn pool of threads
        for i in range(1):
            t=QueuePicThread(self.aquirequeue, i)

        if self.InitAVTCamera():
            self.SetStatusText('AVT Interface initiated ')
        else:
            self.SetStatusText('No AVT Camera found')
            self.caminterface.Close()
            self.caminterface=None
            if self.InitOpenCVCamera():
                self.SetStatusText('OpenCV Interface initiated ')
                
            
        
        self.Show()
        
    def CreateMenu(self):
        Menubar =wx.MenuBar()
        Config = wx.Menu()
        Menubar.Append(Config,'&Config')
        Config.Append(ID_CPROP,'&Properties','Camera Properties')
        
        return Menubar

    def InitAVTCamera(self):
        #print CamObj._get_Camera()
        #if not isinstance(self.caminterface,AVTCam.AVTCam):
        try:
            self.caminterface=AVTCam.AVTCam(self,wx.ID_ANY,wx.DefaultPosition,wx.DefaultSize,0,'AVT')
            self.SetStatusText('AVT Interface&Driver found')
            
        except:
            return False

        self.caminterface._set_Camera(0)
        if self.caminterface._get_Camera()<0:
                self.caminterface.Close()
                self.SetStatusText('Camera Initilization failed or unplugged')
                return False

        self.Bind(AVTCam.EVT_CameraUnplugged, self.CamPlugUnplug)
        self.Bind(AVTCam.EVT_CameraPlugged, self.CamPlugUnplug)
        self.Bind(wx.EVT_MENU, self.CameraProperties, id=ID_CPROP)

        self.Bind(AVTCam.EVT_FrameAcquired, self.GrabAVT)
        
        self.panel=wx.Panel(self, wx.ID_ANY, style=wx.BORDER_SUNKEN)
        self.panelsizer=wx.BoxSizer(wx.HORIZONTAL)
        self.panelsizer.Add(self.caminterface,2,wx.EXPAND)
        self.SetSizer(self.panelsizer)
        
        self.aquire=self.caminterface._get_Acquire()
        self.caminterface._set_Acquire(False)
        self.caminterface._set_Mode(4)
        self.caminterface._set_GainControl(1)
        self.caminterface._set_Magnification(0)
        self.caminterface._set_ShutterControl(1)
        self.caminterface._set_Palette(0)
        self.caminterface._set_Acquire(True)
        return True
    def CameraProperties(self,event):
        self.caminterface.ShowProperties(True,1)
     
    def CamPlugUnplug(self,event):
        self.InitAVTCamera()
    def GrabAVT(self,event):
        width=self.caminterface._get_SizeX()
        height=self.caminterface._get_SizeY()
        intrawdatapointer=self.caminterface.GetRawData(True)

        winsize=self.GetSize()
        self.acttime=clock()
        if self.acttime-self.lasttime<1:
            self.framecount+=1
        else:
            self.SetStatusText('FPS: '+str(self.framecount),1)
            self.framecount=1
            self.lasttime=self.acttime

        #print len(self.childs)
        if len(self.childs)>=1:
            self.datatoqueue.append((self.acttime, intrawdatapointer,width,height,self.childs))
        

        
        if len(self.datatoqueue)>=3:
            self.aquirequeue.put(self.datatoqueue,True)
            self.datatoqueue=list()
            #self.parent.queue.join()

        #print "Put to pic list to queue!"
        #print threading.activeCount()
    def InitOpenCVCamera(self):
        self.caminterface=cv.CreateCameraCapture(0)
        
        self.image=cv.QueryFrame( self.caminterface)
        if self.image==None:
            self.SetStatusText('OpenCVCamera Initilization failed')
            return

        self.ID_FTIMER=wx.NewId()
        self.Timer=wx.Timer(self, self.ID_FTIMER)
        self.Timer.Start(30)
        self.Bind(wx.EVT_TIMER,self.GrabOpenCV,id=self.ID_FTIMER)

        self.panel=wx.Panel(self, wx.ID_ANY, style=wx.BORDER_SUNKEN)
        self.panelsizer=wx.BoxSizer(wx.HORIZONTAL)
        self.panelsizer.Add(self.panel,2,wx.EXPAND)
        self.SetSizer(self.panelsizer)

    def GrabOpenCV(self,event):
        try:
            self.image=cv.QueryFrame( self.CamInterface )
            self.acttime=clock()
            if self.acttime-self.lasttime<1:
                self.framecount+=1
            else:
                self.SetStatusText('FPS: '+str(self.framecount),1)
                self.framecount=1
                self.lasttime=self.acttime
            if len(self.childs)>=1:
                self.datatoqueue.append((self.acttime, self.image,self.image.width,self.image.height,self.childs))
            if len(self.datatoqueue)>=3:
                self.aquirequeue.put(self.datatoqueue,True)
                self.datatoqueue=list()
        except:
            return



    def OnClose(self, event):
        #self.caminterface._set_Acquire(False)
        for item in self.childs:
            item.OnClose(True)
        self.Destroy()

class QueuePicThread(threading.Thread):
    """Background Worker Thread Class."""

    def __init__(self, aquirequeue, num):
        """Init Worker Thread Class."""
        threading.Thread.__init__(self)
        self.aquirequeue=aquirequeue
        #self.piclistqueue=piclistqueue
        self.num=num
        self.setDaemon(True)
        self.start()
        # start the thread
        


    def run(self):
        #print "Aquirethread started "+str(self.num)
        while True:
            pointerlist=self.aquirequeue.get()
            #print "Aquirethread got task"+ " "+str(self.num)+" "+str(len(pointerlist))

            for item in pointerlist:

                self.timestamp=item[0]
                rawdatapointer=item[1]
                width=item[2]
                height=item[3]
                trackers=item[4]

                if isinstance(rawdatapointer,cv.cvmat):
                    self.raw=cv.CreateImage((self.raw.width,self.raw.height),cv.IPL_DEPTH_8U,1)
                    cv.CvtColor(self.image,self.raw,cv.CV_RGB2GRAY)
                else:
                    
                    #print rawdatapointer, width, height
                    try:
                        self.memstring=ctypes.string_at(rawdatapointer,width*height)
                    except:
                        break

                    self.raw= cv.CreateImageHeader((width,height),cv.IPL_DEPTH_8U, 1)
                    #self.raw=cv.CreateImage((width,height),cv.IPL_DEPTH_8U,1)
                    cv.SetData(self.raw, self.memstring,width)

                #print len(trackers)
                
                for window in trackers:
                    #print window
                    wx.PostEvent(window, config.ResultEvent("Pic to Queue!",(self.timestamp,self.raw)))
                    
            self.aquirequeue.task_done()



