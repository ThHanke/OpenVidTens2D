
import wx,cv,ctypes,os
import threading
import Queue

from time import clock
from time import sleep

#submodule activex wrapper avt camera driver activex element
import AVTCam

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
##        self.rawimage = cv.CreateImage((100,100),8,3)
##        self.image = cv.CreateImage((100,100),8,3)
##        cv.Set(self.rawimage,0)
##        cv.Set(self.image,0)

        
        self.lasttime=0
        self.acttime=0
        self.framecount=0
        

        self.childs=list()

        #spwan queue
        self.aquirequeue=Queue.PriorityQueue(-1)
        self.piclistqueue=Queue.PriorityQueue(-1)
        #spawn pool of threads
        for i in range(1):
            t=QueuePicThread(self.aquirequeue, i)

        #if False:
        if self.InitAVTCamera():
            self.SetStatusText('AVT Interface initiated ')
        else:
            self.SetStatusText('No AVT Camera found')
            
            
            if self.InitOpenCVCamera():
                self.SetStatusText('OpenCV Interface initiated ')
            else:
                if self.InitFileInterface():
                    self.isfileinterface=True
                    self.SetStatusText('File Interface initiated ')
                
                
            
        
        self.Show()
        
    def InitAVTCamera(self):
        #print CamObj._get_Camera()
        if not isinstance(self.caminterface,AVTCam.AVTCam):
            try:
                self.caminterface=AVTCam.AVTCam(self,wx.ID_ANY,wx.DefaultPosition,wx.DefaultSize,0,'AVT')
                self.SetStatusText('AVT Interface&Driver found')
                
                
            except wx.PyAssertionError:
                #have to destroy useless activex window
                print self.GetChildren()
                for item in self.GetChildren():
                    if isinstance(item,wx.activex.ActiveXWindow):
                        item.Destroy()
                return False

        self.caminterface._set_Camera(0)
        if self.caminterface._get_Camera()<0:
                print 'closing'
                self.SetStatusText('Camera Initilization failed or unplugged')
                self.caminterface.Close()
                self.caminterface.Destroy()
                return False

        ID_CPROP=wx.NewId()
        
        Menubar =wx.MenuBar()
        Config = wx.Menu()
        Menubar.Append(Config,'&Config')
        Config.Append(ID_CPROP,'&Properties','Camera Properties')
        self.SetMenuBar(Menubar)
        
        self.Bind(AVTCam.EVT_CameraUnplugged, self.CamPlugUnplug)
        self.Bind(AVTCam.EVT_CameraPlugged, self.CamPlugUnplug)
        self.Bind(wx.EVT_MENU, self.CameraProperties, id=ID_CPROP)

        self.Bind(AVTCam.EVT_FrameAcquired, self.GrabAVT)

        #self.panel=wx.Panel(self, wx.ID_ANY, style=wx.BORDER_SUNKEN)
        #self.panelsizer=wx.BoxSizer(wx.HORIZONTAL)
        #self.SetSizer(self.panelsizer)
        
        
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
            self.aquirequeue.put(self.datatoqueue,False)
            self.datatoqueue=list()
            #self.parent.queue.join()

        #print "Put to pic list to queue!"
        #print threading.activeCount()
    def InitOpenCVCamera(self):
        self.caminterface=cv.CreateCameraCapture(0)
        
        self.image=cv.QueryFrame( self.caminterface)
        if self.image==None:
            self.SetStatusText('OpenCVCamera Initilization failed')
            return False

        self.ID_FTIMER=wx.NewId()
        self.Timer=wx.Timer(self, self.ID_FTIMER)
        self.Timer.Start(30)
        self.Bind(wx.EVT_TIMER,self.GrabOpenCV,id=self.ID_FTIMER)

        Menubar =wx.MenuBar()
        Config = wx.Menu()
        Menubar.Append(Config,'&Config')
        #Config.Append(ID_CPROP,'&Properties','Camera Properties')
        self.SetMenuBar(Menubar)

        #spwan queue
        self.bmppaintqueue=Queue.PriorityQueue(-1)

        #spawn pool of threads
        for i in range(1):
            t=BmpPaintThread(self.bmppaintqueue,i)

        self.panel=wx.Panel(self, wx.ID_ANY, style=wx.BORDER_SUNKEN)
        self.panelsizer=wx.BoxSizer(wx.HORIZONTAL)
        self.panelsizer.Add(self.panel,2,wx.EXPAND)
        self.SetSizer(self.panelsizer)

        self.ScaledImg=cv.CreateImage((100,100),8,3)

        return True

        


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
                self.aquirequeue.put(self.datatoqueue,False)
                self.datatoqueue=list()

            gc=wx.ClientDC(self.imagepanel)
            self.panelwidth,self.panelheight=gc.GetSize()
            datatoqueue=list()
            datatoqueue.append((self.image, gc))
            self.bmppaintqueue.put(datatoqueue,False)
            
        except:
            return
    def InitFileInterface(self):

        ID_LSERIES=wx.NewId()
        ID_LFOLDER=wx.NewId()
        ID_GOTHROUGH=wx.NewId()
        self.dirname=config.ProgDir
        self.ScaledImg=cv.CreateImage((100,100),8,3)

        #spwan queue
        self.bmppaintqueue=Queue.PriorityQueue(-1)

        #spawn pool of threads
        for i in range(1):
            t=BmpPaintThread(self.bmppaintqueue,i)

        Menubar =wx.MenuBar()
        Operate = wx.Menu()
        Menubar.Append(Operate,'&Operate')
        Operate.Append(ID_LSERIES,'&Load Series','Load image series')
        Operate.Append(ID_LFOLDER,'&Load Directory','Load image series from Directory')
        Operate.Append(ID_GOTHROUGH,'&Gothrough','Go through series')
        self.SetMenuBar(Menubar)
        
        self.ID_FTIMER=wx.NewId()
        self.Timer=wx.Timer(self, self.ID_FTIMER)
        self.Timer.Start(30)
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
        self.imagepanel=wx.Panel(self, wx.ID_ANY, style=wx.NO_BORDER)
        
        self.panelsizer=wx.BoxSizer(wx.VERTICAL)
        self.panelsizer.Add(self.sliderpanel,0,wx.EXPAND)
        self.panelsizer.Add(self.imagepanel,2,wx.EXPAND)

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
        if len(self.childs)>=1:
            
            self.datatoqueue.append((self.imageslider.GetValue(), self.image,self.image.width,self.image.height,self.childs))
            
        if len(self.datatoqueue)>=1:
            self.aquirequeue.put(self.datatoqueue,False)
            self.datatoqueue=list()
            #print picnum

        gc=wx.ClientDC(self.imagepanel)
        self.panelwidth,self.panelheight=gc.GetSize()
        datatoqueue=list()
        datatoqueue.append((self.image, gc))
        self.bmppaintqueue.put(datatoqueue,False)
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
                

                if isinstance(rawdatapointer,cv.iplimage):
                    self.raw=cv.CreateImage((rawdatapointer.width,rawdatapointer.height),cv.IPL_DEPTH_8U,1)
                    cv.CvtColor(rawdatapointer,self.raw,cv.CV_RGB2GRAY)
                else:
                    
                    #print rawdatapointer, width, height
                    try:
                        self.memstring=ctypes.string_at(rawdatapointer,width*height)
                    except:
                        break

                    # is avt-camera like input

                    #self.raw= cv.CreateImageHeader((width,height),cv.IPL_DEPTH_8U, 1)
                    self.raw= cv.CreateImageHeader((width,height),cv.IPL_DEPTH_8U, 1)
                    
                    #self.raw=cv.CreateImage((width,height),cv.IPL_DEPTH_8U,1)
                    cv.SetData(self.raw, self.memstring,width)

                    
                    

                #print len(trackers)
                
                for window in trackers:
                    #print window
                    wx.PostEvent(window, config.ResultEvent("Pic to Queue!",(self.timestamp,self.raw)))
                    
            self.aquirequeue.task_done()

class BmpPaintThread(threading.Thread):
    """Background Worker Thread Class."""

    def __init__(self, bmppaintqueue, num):
        """Init Worker Thread Class."""
        threading.Thread.__init__(self)
        self.bmppaintqueue=bmppaintqueue
        #self.piclistqueue=piclistqueue

              
        self.num=num

        self.ScaledImg=cv.CreateImage((100,100),8,3)
        self.setDaemon(True)
        self.start()
        # start the thread

    def run(self):
        #print "Aquirethread started "+str(self.num)
        while True:
            pointerlist=self.bmppaintqueue.get()
            #print "Aquirethread got task"+ " "+str(self.num)+" "+str(len(pointerlist))

            for item in pointerlist:

                image=item[0]
                dc=item[1]

                
                panelwidth,panelheight=dc.GetSize()
                if (panelwidth <=0) or (panelheight <=0):
                    continue
                if self.ScaledImg.width!=panelwidth or self.ScaledImg.height!=panelheight:
                    self.ScaledImg=cv.CreateImage((panelwidth,panelheight),8,3)
                #print "start"

                cv.Resize(image,self.ScaledImg,cv.CV_INTER_NN)
                
               
                self.bitmap=wx.BitmapFromBuffer(panelwidth,panelheight,self.ScaledImg.tostring()) 
                dc.DrawBitmap(self.bitmap, 0, 0, False)
                #print "finish"
                #print clock()
                
                    
            self.bmppaintqueue.task_done()
