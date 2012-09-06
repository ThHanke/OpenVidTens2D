
import wx,cv,ctypes,os
import threading
import Queue
import VideoCapture
import ImageChops

import multiprocessing


from time import clock
from time import sleep

#import globals
import config


class LiveCamWin(wx.Frame):
    def __init__(self):
        screensize=wx.Display().GetGeometry()
        wx.Frame.__init__(self,None,wx.ID_ANY,title='LiveCamWin',pos=(0,0),size=(screensize[2]/2,screensize[3]/2),style= wx.DEFAULT_FRAME_STYLE )
        self.status=self.CreateStatusBar()
        self.status.SetFieldsCount(2)
        self.status.SetStatusWidths([-1,65])

        wx.EVT_CLOSE(self, self.OnClose)

        #startwerte
        self.caminterface=None
        self.isfileinterface=False
        self.datatoqueue=list()

        self.lasttime=0
        self.acttime=0
        self.framecount=0

        self.childs=list()


        if self.InitVidCapCamera():
            self.SetStatusText('VidCap Interface initiated ')
        else:
            if self.InitOpenCVCamera():
                self.SetStatusText('OpenCV Interface initiated ')
            else:
                if self.InitFileInterface():
                    self.isfileinterface=True
                    self.SetStatusText('File Interface initiated ')

        self.Show()
    def InitVidCapCamera(self):
        #DirectShowDevice
        try:
            self.caminterface = VideoCapture.Device(0)
        except:
            return False
        self.aquirequeue=Queue.Queue(3)
        self.totrackqueue=multiprocessing.Queue(1)
        self.bmppaintqueue=Queue.LifoQueue(1)

        t=VidCapQueuePicThread(self.aquirequeue,self.bmppaintqueue)

        ID_CPROP=wx.NewId()
      
        Menubar =wx.MenuBar()
        Config = wx.Menu()
        Menubar.Append(Config,'&Config')
        Config.Append(ID_CPROP,'&Properties','Camera Properties')
        self.SetMenuBar(Menubar)
        self.Bind(wx.EVT_MENU, self.VidCapProperties, id=ID_CPROP)
        
        t=BmpPaintThread(self.bmppaintqueue)
            

        self.ScaledImg=cv.CreateImage((100,100),8,3)
        
        self.panel=wx.Panel(self, wx.ID_ANY, style=wx.BORDER_SUNKEN)
        self.panelsizer=wx.BoxSizer(wx.HORIZONTAL)
        self.panelsizer.Add(self.panel,2,wx.EXPAND)
        self.SetSizer(self.panelsizer)

        
        #print 'start aquiring'
        self.aquirequeue.put((self,self.caminterface),False)
        return True
        
    def VidCapProperties(self,event):
        #stop aquiring
        self.aquirequeue.put((self,None,list()),False)
        self.caminterface.displayCaptureFilterProperties()
        #start again
        self.aquirequeue.put((self,self.caminterface),False)
        
    def InitOpenCVCamera(self):
        # is broken
        pass

##        self.CamInterface=cv.CreateCameraCapture(0)
##		
##        width = 800 #leave None for auto-detection
##        height = 600 #leave None for auto-detection
##
##        if width is None:
##                width = int(cv.GetCaptureProperty(self.CamInterface, cv.CV_CAP_PROP_FRAME_WIDTH))
##        else:
##                cv.SetCaptureProperty(self.CamInterface,cv.CV_CAP_PROP_FRAME_WIDTH,width)    
##
##        if height is None:
##                height = int(cv.GetCaptureProperty(self.CamInterface, cv.CV_CAP_PROP_FRAME_HEIGHT))
##        else:
##                cv.SetCaptureProperty(self.CamInterface,cv.CV_CAP_PROP_FRAME_HEIGHT,height) 
##        #cv.SetCaptureProperty(self.CamInterface,cv.CV_CAP_PROP_FPS,30)
##        #cv.GetCaptureProperty(self.CamInterface,cv.CV_CAP_PROP_MODE)
##
##        #print cv.GetCaptureProperty(self.CamInterface, cv.CV_CAP_PROP_FRAME_WIDTH)
##        #print cv.GetCaptureProperty(self.CamInterface, cv.CV_CAP_PROP_FRAME_HEIGHT)
##        #print cv.GetCaptureProperty(self.CamInterface, cv.CV_CAP_PROP_FORMAT)
##        #print cv.GetCaptureProperty(self.CamInterface, cv.CV_CAP_PROP_FPS)
##        #print cv.GetCaptureProperty(self.CamInterface, cv.CV_CAP_PROP_FRAME_COUNT)
##        #print cv.GetCaptureProperty(self.CamInterface, cv.CV_CAP_PROP_MODE)
##        #print cv.GetCaptureProperty(self.CamInterface, cv.CV_CAP_PROP_GAIN)
##
##        ID_CPROP=wx.NewId()
##        
##        Menubar =wx.MenuBar()
##        Config = wx.Menu()
##        Menubar.Append(Config,'&Config')
##        Config.Append(ID_CPROP,'&Properties','Camera Properties')
##        self.SetMenuBar(Menubar)
##        self.Bind(wx.EVT_MENU, self.OpenCVCamProp, id=ID_CPROP)
##        
##        print width,height
##
##        self.image=cv.QueryFrame( self.CamInterface)
##        if self.image==None:
##            self.SetStatusText('OpenCVCamera Initilization failed')
##            return False
##
##        self.aquirequeue=Queue.PriorityQueue(-1)
##        for i in range(1):
##           t=QueuePicThread(self.aquirequeue, i)
##        
##
##
##        self.ID_FTIMER=wx.NewId()
##        self.Timer=wx.Timer(self, self.ID_FTIMER)
##        self.Timer.Start(int(cv.GetCaptureProperty(self.CamInterface,cv.CV_CAP_PROP_FPS)))
##        self.Bind(wx.EVT_TIMER,self.GrabOpenCV,id=self.ID_FTIMER)
##
##        
##        #spwan queue
##        self.bmppaintqueue=Queue.LifoQueue(1)
##
##        #spawn pool of threads
##        for i in range(1):
##            t=BmpPaintThread(self.bmppaintqueue,i)
##
##        self.panel=wx.Panel(self, wx.ID_ANY, style=wx.BORDER_SUNKEN)
##        self.panelsizer=wx.BoxSizer(wx.HORIZONTAL)
##        self.panelsizer.Add(self.panel,2,wx.EXPAND)
##        self.SetSizer(self.panelsizer)
##
##        self.ScaledImg=cv.CreateImage((100,100),8,3)
##
##        return True

    def OpenCVCamProp(self,event):
        # is broken
        pass
        
##        print cv.GetCaptureProperty(self.CamInterface, cv.CV_CAP_PROP_FRAME_WIDTH)
##        print cv.GetCaptureProperty(self.CamInterface, cv.CV_CAP_PROP_FRAME_HEIGHT)
##        print cv.GetCaptureProperty(self.CamInterface, cv.CV_CAP_PROP_FORMAT)
##        print cv.GetCaptureProperty(self.CamInterface, cv.CV_CAP_PROP_FPS)
##        print cv.GetCaptureProperty(self.CamInterface, cv.CV_CAP_PROP_FRAME_COUNT)
##        print cv.GetCaptureProperty(self.CamInterface, cv.CV_CAP_PROP_MODE)
##        print cv.GetCaptureProperty(self.CamInterface, cv.CV_CAP_PROP_GAIN)


    def GrabOpenCV(self,event):
        # is broken
        pass
##        self.image=cv.QueryFrame( self.CamInterface )
##        self.acttime=clock()
##        if self.acttime-self.lasttime<1:
##            self.framecount+=1
##        else:
##            self.SetStatusText('FPS: '+str(self.framecount),1)
##            self.framecount=1
##            self.lasttime=self.acttime
##        if len(self.childs)>=1:
##            self.datatoqueue.append((self.acttime, self.image,self.image.width,self.image.height,self.childs))
##        if len(self.datatoqueue)>=1:
##            self.aquirequeue.put(self.datatoqueue,False)
##            self.datatoqueue=list()
##
##        gc=wx.ClientDC(self.panel)
##        self.panelwidth,self.panelheight=gc.GetSize()
##        datatoqueue=list()
##        datatoqueue.append((self.image, gc))
##        try:
##            self.bmppaintqueue.put(datatoqueue,False)
##        except:
##            pass
        
    def InitFileInterface(self):

        self.aquirequeue=Queue.PriorityQueue(-1)
        self.totrackqueue=multiprocessing.Queue(3)
        self.bmppaintqueue=Queue.PriorityQueue(-1)

        t=QueuePicThread(self.aquirequeue)

        ID_LSERIES=wx.NewId()
        ID_LFOLDER=wx.NewId()
        ID_GOTHROUGH=wx.NewId()
        self.dirname=config.ProgDir
        self.ScaledImg=cv.CreateImage((100,100),8,3)

        t=BmpPaintThread(self.bmppaintqueue)

        Menubar =wx.MenuBar()
        Operate = wx.Menu()
        Menubar.Append(Operate,'&Operate')
        Operate.Append(ID_LSERIES,'&Load Series','Load image series')
        Operate.Append(ID_LFOLDER,'&Load Directory','Load image series from Directory')
        Operate.Append(ID_GOTHROUGH,'&Gothrough','Go through series')
        self.SetMenuBar(Menubar)
        
        self.ID_FTIMER=wx.NewId()
        self.Timer=wx.Timer(self, self.ID_FTIMER)
        self.Timer.Start(0.01)
        self.Bind(wx.EVT_TIMER,self.GotoNextFile,id=self.ID_FTIMER)

        self.Bind(wx.EVT_MENU, self.LoadSeries, id=ID_LSERIES)
        self.Bind(wx.EVT_MENU, self.LoadDir, id=ID_LFOLDER)
        self.Bind(wx.EVT_SLIDER,self.OnSlider)
        self.Bind(wx.EVT_MENU, self.GoThrough, id=ID_GOTHROUGH)
        

        
        self.sliderpanel=wx.Panel(self, wx.ID_ANY)
        self.imageslider=wx.Slider(self.sliderpanel,wx.ID_ANY,1, 100, 100000, (-1, -1), (-1, -1),wx.SL_AUTOTICKS |wx.SL_HORIZONTAL |wx.SL_LABELS | wx.BORDER_SUNKEN)
        self.imageslider.Enable(False)
        self.slidersizer=wx.BoxSizer(wx.VERTICAL)
        self.slidersizer.Add(self.imageslider,0,wx.EXPAND)
        self.sliderpanel.SetSizer(self.slidersizer)
        self.panel=wx.Panel(self, wx.ID_ANY, style=wx.NO_BORDER)
        
        self.panelsizer=wx.BoxSizer(wx.VERTICAL)
        self.panelsizer.Add(self.sliderpanel,0,wx.EXPAND)
        self.panelsizer.Add(self.panel,2,wx.EXPAND)

        self.SetSizer(self.panelsizer)

        self.gothrough=False
        
        return True

    def LoadSeries(self, event):
        
        filters = 'Image files (*.gif;*.png;*.jpg;*.tif;*.bmp)|*.gif;*.png;*.jpg;*.tif;*.bmp' 
        dlg = wx.FileDialog(self, "Select files", self.dirname, "", filters, wx.FD_MULTIPLE)
        if dlg.ShowModal() == wx.ID_OK:
            try:
                
                self.filenames=dlg.GetFilenames()

                self.dirname=dlg.GetDirectory()
            except:
                dlg.Destroy()
                return False
   
            
            piccount=len(self.filenames)
            self.imageslider.SetMin(1)
            self.imageslider.SetMax(piccount)
            self.imageslider.SetValue(piccount)
            self.imageslider.Enable(True)
            dlg.Destroy()
            self.imageslider.SetValue(1)
            self.OnSlider(True)
        return True
    def LoadDir(self, event):
        dlg = wx.DirDialog(self, "Select Directory", self.dirname,  wx.DD_DEFAULT_STYLE | wx.DD_DIR_MUST_EXIST)
        if dlg.ShowModal() == wx.ID_OK:
            try:
                self.dirname=dlg.GetPath()
            except:
                dlg.Destroy()
                return False
            self.filenames=os.listdir(self.dirname)
            piccount=len(self.filenames)
            self.imageslider.SetMin(1)
            self.imageslider.SetMax(piccount)
            self.imageslider.SetValue(piccount)
            self.imageslider.Enable(True)
            dlg.Destroy()
            self.imageslider.SetValue(1)
            self.OnSlider(True)
        return True    
                
        
    def OnSlider(self, event, picnum=None):
        if picnum==None:
            picnum=(self.imageslider.GetValue())
        else:
            self.imageslider.SetValue(picnum)
        self.image = cv.LoadImage(self.dirname+'\\'+self.filenames[picnum-1])

        self.acttime=clock()


        self.aquirequeue.put((self,self.imageslider.GetValue(), self.image, self.image.width, self.image.height),False)

    def GotoNextFile(self,event):
        if self.gothrough:
            if self.imageslider.GetValue()<self.imageslider.GetMax():
                self.OnSlider(True,self.imageslider.GetValue()+1)
                self.aquirequeue.join()
            else:
                self.gothrough=False
            
        
    def GoThrough(self,event):
        self.OnSlider(True,self.imageslider.GetValue())
        self.aquirequeue.join()
        self.gothrough=True

    def OnClose(self, event):
        self.aquirequeue.put((self,None,list()),False)
        sleep(0.3)
        try:
            del self.caminterface
        except:
            print 'cant close cam interface'
            pass
        for item in self.childs:
            item.OnClose(True)
        self.Destroy()

class QueuePicThread(threading.Thread):
    """Background Worker Thread Class."""

    def __init__(self, aquirequeue):
        """Init Worker Thread Class."""
        threading.Thread.__init__(self)
        self.aquirequeue=aquirequeue
        self.setDaemon(True)
        self.start()
        # start the thread

    def run(self):
        #print "Aquirethread started "
        while True:
            (parent,self.timestamp, rawdatapointer ,width, height)=self.aquirequeue.get()
            #print "Aquirethread got task"
            
            if isinstance(rawdatapointer,cv.iplimage):
                self.raw=cv.CreateImage((rawdatapointer.width,rawdatapointer.height),cv.IPL_DEPTH_8U,1)
                cv.CvtColor(rawdatapointer,self.raw,cv.CV_RGB2GRAY)

                gc=wx.ClientDC(parent.panel)
                try:
                    parent.bmppaintqueue.put((rawdatapointer, gc),False)
                except Queue.Full:
                    print 'winCam1 bmppaintqueue is full'
            else:
                
                #print rawdatapointer, width, height
                try:
                    self.memstring=ctypes.string_at(rawdatapointer,width*height)
                except:
                    break

                # is avt-camera like input
                self.raw= cv.CreateImageHeader((width,height),cv.IPL_DEPTH_8U, 1)
                cv.SetData(self.raw, self.memstring,width)

                gc=wx.ClientDC(parent.panel)
                try:
                    parent.bmppaintqueue.put((self.raw, gc),False)
                except Queue.Full:
                    print 'winCam2 bmppaintqueue is full'

            try:
                parent.totrackqueue.put((self.timestamp,(self.raw.tostring(),self.raw.width,self.raw.height)),False)
            except Queue.Full:
                print 'totrackqueue is full'

                    
            self.aquirequeue.task_done()
class VidCapQueuePicThread(threading.Thread):
    """Background Worker Thread Class."""

    def __init__(self, aquirequeue, bmppaintqueue, num=0):
        """Init Worker Thread Class."""
        threading.Thread.__init__(self)
        self.aquirequeue=aquirequeue
        self.bmppaintqueue=bmppaintqueue
        self.num=num
        self.caminterface=None
        self.lasthash=0
        self.oldhistmax=0.0
        

        self.lasttime=0
        self.framecount=0
        
        self.setDaemon(True)
        self.start()
        # start the thread
     


    def run(self):
        #print "Aquirethread started "+str(self.num)
        while True:
            if not self.aquirequeue.empty():
                (parent,self.caminterface) =self.aquirequeue.get()
            if self.caminterface is not None:
                rawdata=self.caminterface.getBuffer()  #datastring, width, height
                newhash=hash(rawdata)
                if newhash!=self.lasthash:
                    self.lasthash=newhash
                    self.timestamp=clock()

                    

                    
                    if self.timestamp-self.lasttime<1:
                        self.framecount+=1
                    else:
                        parent.SetStatusText('FPS: '+str(self.framecount),1)
                        self.framecount=1
                        self.lasttime=self.timestamp
                        
                    temp=cv.CreateImageHeader((rawdata[1],rawdata[2]), cv.IPL_DEPTH_8U, 3)
                    cv.SetData(temp, rawdata[0])

                    self.raw=cv.CreateImage((rawdata[1],rawdata[2]),cv.IPL_DEPTH_8U,1)
                    cv.CvtColor(temp,self.raw,cv.CV_RGB2GRAY)

                    try:
                        #parent.totrackqueue.put((self.timestamp,self.raw),False)
                        parent.totrackqueue.put((self.timestamp,(self.raw.tostring(),self.raw.width,self.raw.height)),False)
                    except Queue.Full:
                        print 'totrackqueue is full'

                    gc=wx.ClientDC(parent.panel)
                    try:
                        self.bmppaintqueue.put((temp, gc),False)
                    except Queue.Full:
                        print 'winCam bmppaintqueue3 is full'
                    
                #sleep(0.005)
                

class BmpPaintThread(threading.Thread):
    """Background Worker Thread Class."""

    def __init__(self, bmppaintqueue):
        """Init Worker Thread Class."""
        threading.Thread.__init__(self)
        self.bmppaintqueue=bmppaintqueue
 

        self.ScaledImg=cv.CreateImage((100,100),8,3)
        self.setDaemon(True)
        self.start()
        # start the thread

    def run(self):
        while True:
            (image, dc)=self.bmppaintqueue.get()
            #print "Bmpthread got task"
            panelwidth,panelheight=dc.GetSize()
            if (panelwidth <=0) or (panelheight <=0):
                continue
            if self.ScaledImg.width!=panelwidth or self.ScaledImg.height!=panelheight:
                self.ScaledImg=cv.CreateImage((panelwidth,panelheight),8,3)
            #print "start"
            cv.Resize(image,self.ScaledImg,cv.CV_INTER_NN)
            
            cv.CvtColor(self.ScaledImg,self.ScaledImg,cv.CV_RGB2BGR)
            self.bitmap=wx.BitmapFromBuffer(panelwidth,panelheight,self.ScaledImg.tostring()) 
            dc.DrawBitmap(self.bitmap, 0, 0, False)

                    
            self.bmppaintqueue.task_done()

