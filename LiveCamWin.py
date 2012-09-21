
import wx,cv,ctypes,os
import threading
import Queue
import VideoCapture
import ImageChops

from PIL import Image

import multiprocessing


from time import clock
from time import sleep

#import globals
import config

ID_CAM1=wx.NewId()
ID_CAM2=wx.NewId()
ID_CAM3=wx.NewId()
ID_FILE=wx.NewId()
ID_CPROP=wx.NewId()

ID_LSERIES=wx.NewId()
ID_LFOLDER=wx.NewId()
ID_GOTHROUGH=wx.NewId()

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

        self.aquirequeue=Queue.Queue(1)
        self.totrackqueue=multiprocessing.Queue(1)
        self.bmppaintqueue=Queue.LifoQueue(1)

        self.lasttime=0
        self.acttime=0
        self.framecount=0

        self.childs=list()
        self.panel=None
        
        
        

        if self.InitVidCapCamera():
            self.SetStatusText('VidCap Interface initiated ')
        else:
            if self.InitOpenCVCamera():
                self.SetStatusText('OpenCV Interface initiated ')
            else:
                if self.InitFileInterface():
                    self.SetStatusText('File Interface initiated ')

        self.CreateMenu()

        

        self.Show()
    def CreateMenu(self):
        self.Menubar =wx.MenuBar()
        Source = wx.Menu()

        self.Menubar.Append(Source,'&Source')
        Source.Append(ID_CAM1,'&Cam 1','Set camera 1')
        Source.Append(ID_CAM2,'&Cam 2','Set camera 2')
        Source.Append(ID_CAM3,'&Cam 3','Set camera 3')
        Source.Append(ID_FILE,'&File','Set file interface')

        
        self.Bind(wx.EVT_MENU, self.VidCapSetCamera, id=ID_CAM1)
        self.Bind(wx.EVT_MENU, self.VidCapSetCamera, id=ID_CAM2)
        self.Bind(wx.EVT_MENU, self.VidCapSetCamera, id=ID_CAM3)
        self.Bind(wx.EVT_MENU, self.SetFilemode, id=ID_FILE)

        if isinstance(self.caminterface,VideoCapture.Device):
            Config = wx.Menu()
            self.Menubar.Append(Config,'&Config')
            Config.Append(ID_CPROP,'&Properties','Camera Properties')
            self.Bind(wx.EVT_MENU, self.VidCapProperties, id=ID_CPROP)

        if self.isfileinterface:
            Operate = wx.Menu()
            self.Menubar.Append(Operate,'&Operate')
            Operate.Append(ID_LSERIES,'&Load Series','Load image series')
            Operate.Append(ID_LFOLDER,'&Load Directory','Load image series from Directory')
            Operate.Append(ID_GOTHROUGH,'&Gothrough','Go through series')
            self.Bind(wx.EVT_MENU, self.LoadSeries, id=ID_LSERIES)
            self.Bind(wx.EVT_MENU, self.LoadDir, id=ID_LFOLDER)
            self.Bind(wx.EVT_MENU, self.GoThrough, id=ID_GOTHROUGH)

        self.SetMenuBar(self.Menubar)
    def CleanUpBeforeInterfaceSwitch(self):
        if isinstance(self.caminterface,VideoCapture.Device):
            #print 'stop aquiring'
            self.aquirequeue.put((self,None,False),False)
            #print 'stopped aquiring'
            del self.caminterface
            self.caminterface=None

        #kill threads

        for item in threading.enumerate():
            #print item
            if isinstance(item,VidCapQueuePicThread):
                #print 'found one! kill it!'
                self.aquirequeue.put((self,None,True),True)
                sleep(0.1)
                self.aquirequeue.queue.clear()
                #print self.aquirequeue.queue
            if isinstance(item,QueuePicThread):
                #print 'found one! kill it!'
                self.aquirequeue.put((self,None,None,None,None,True),True)
                sleep(0.1)
                self.aquirequeue.queue.clear()
                #print self.aquirequeue.queue


        if self.isfileinterface:
            self.sliderpanel.Destroy()

        if isinstance(self.panel,wx.Panel):
            self.panel.Destroy()
            self.panel=None
    
        
            

    
    def InitVidCapCamera(self,num=-1):
        #DirectShowDevice
        self.isfileinterface=False
        self.CleanUpBeforeInterfaceSwitch()
        if num<0:
            for i in range(0,2):
                try:
                    self.caminterface = VideoCapture.Device(i)
                    break
                except:
                    self.caminterface=None
                    continue
            if self.caminterface==None:
                return False
        else:          
            try:
                self.caminterface = VideoCapture.Device(num)
                #print self.caminterface
            except:
                self.caminterface=None
                return False

        

        t=VidCapQueuePicThread(self.aquirequeue,self.bmppaintqueue)
        t=WinCamBmpPaintThread(self.bmppaintqueue)
            
                

        #print threading.enumerate()

        self.ScaledImg=cv.CreateImage((100,100),8,3)
        
        self.panel=wx.Panel(self, wx.ID_ANY, style=wx.BORDER_SUNKEN)
        self.panelsizer=wx.BoxSizer(wx.HORIZONTAL)
        self.panelsizer.Add(self.panel,2,wx.EXPAND)
        self.SetSizer(self.panelsizer)

        self.Layout()
        self.CreateMenu()
        #print 'start aquiring'
        self.aquirequeue.put((self,self.caminterface,False),False)
        return True
    def VidCapSetCamera(self,event):
        
        if event.GetId()==ID_CAM1:
            self.InitVidCapCamera(0)
        if event.GetId()==ID_CAM2:
            self.InitVidCapCamera(1)
        if event.GetId()==ID_CAM3:
            self.InitVidCapCamera(2)
        
    def VidCapProperties(self,event):
        #stop aquiring
        self.aquirequeue.put((self,None,False),True)
        self.caminterface.displayCaptureFilterProperties()
        #start again
        self.aquirequeue.put((self,self.caminterface,False),True)
        
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
##            t=WinCamBmpPaintThread(self.bmppaintqueue,i)
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

        self.CleanUpBeforeInterfaceSwitch()
        
        t=QueuePicThread(self.aquirequeue)


        self.dirname=config.ProgDir
        self.ScaledImg=cv.CreateImage((100,100),8,3)

        t=WinCamBmpPaintThread(self.bmppaintqueue)

        
        self.ID_FTIMER=wx.NewId()
        self.Timer=wx.Timer(self, self.ID_FTIMER)
        self.Timer.Start(0.01)
        self.Bind(wx.EVT_TIMER,self.GotoNextFile,id=self.ID_FTIMER)
        self.Bind(wx.EVT_SCROLL_CHANGED,self.OnSlider)
        
        

        
        self.sliderpanel=wx.Panel(self, wx.ID_ANY)
        self.imageslider=wx.Slider(self.sliderpanel,wx.ID_ANY,1, 100, 100000, (-1, -1), (-1, -1),wx.SL_AUTOTICKS |wx.SL_HORIZONTAL |wx.SL_LABELS | wx.BORDER_SUNKEN)
        #self.imageslider.Enable(False)
        self.slidersizer=wx.BoxSizer(wx.VERTICAL)
        self.slidersizer.Add(self.imageslider,0,wx.EXPAND)
        self.sliderpanel.SetSizer(self.slidersizer)
        self.panel=wx.Panel(self, wx.ID_ANY, style=wx.NO_BORDER)
        
        self.panelsizer=wx.BoxSizer(wx.VERTICAL)
        self.panelsizer.Add(self.sliderpanel,0,wx.EXPAND)
        self.panelsizer.Add(self.panel,2,wx.EXPAND)

        self.SetSizer(self.panelsizer)

        self.gothrough=False

        self.Layout()

        self.isfileinterface=True
        self.CreateMenu()
        return True

    def SetFilemode(self,event):
        self.InitFileInterface()
        self.imageslider.Enable(True)
        #print self.imageslider.Enabled


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
            for item in self.filenames:
                filend= item[-4:].lower()
                if filend not in ('.tif','.jpg','.bmp','.jpk','.gif','.png'):
                    self.filenames.remove(item)
                    
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
        #if event 
        if picnum==None:
            picnum=(self.imageslider.GetValue())
        else:
            #print 'set value'
            self.imageslider.SetValue(picnum)
        
        #print picnum
        #print self.dirname+'\\'+self.filenames[picnum-1]
        #have to use open and PIL bcause opnecv cant handle unicode filenames
        try:
            fp=open(self.dirname+'\\'+self.filenames[picnum-1],'rb')
            temp=Image.open(fp)
            if temp.mode!='RGB':
                #print 'convert from '+test2.mode+' to RGB'
                temp=temp.convert('RGB')
        
            self.image=cv.CreateImage(temp.size,cv.IPL_DEPTH_8U,3)
            cv.SetData(self.image,temp.tostring())
            cv.CvtColor( self.image, self.image, cv.CV_BGR2RGB)
        except:
            #print 'failed to load with PIL load with opencv'
            self.image = cv.LoadImage(self.dirname+'\\'+self.filenames[picnum-1])
        

        self.acttime=clock()

        #print 'send file to aquire'
        self.aquirequeue.put((self,self.imageslider.GetValue(), self.image, self.image.width, self.image.height, False),False)

    def GotoNextFile(self,event):
        #print 'go to next file'
        if self.gothrough:
            if self.imageslider.GetValue()<self.imageslider.GetMax():
                self.OnSlider(True,self.imageslider.GetValue()+1)
                #self.aquirequeue.join()
            else:
                self.gothrough=False
            
        
    def GoThrough(self,event):
        self.OnSlider(True,self.imageslider.GetValue())
        self.gothrough=True

    def OnClose(self, event):
        if self.caminterface!=None:
            self.aquirequeue.put((self,None,False),True)
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
            #print self.aquirequeue.queue
            (parent,self.timestamp, rawdatapointer ,width, height,plsexit)=self.aquirequeue.get()
            if plsexit:
                #print 'return'
                return
            #print "Aquirethread got task"
            
            if isinstance(rawdatapointer,cv.iplimage):
                self.raw=cv.CreateImage((rawdatapointer.width,rawdatapointer.height),cv.IPL_DEPTH_8U,1)
                cv.CvtColor(rawdatapointer,self.raw,cv.CV_RGB2GRAY)

                gc=wx.ClientDC(parent.panel)
                try:
                    parent.bmppaintqueue.put((rawdatapointer, gc),False)
                except Queue.Full:
                    pass
                    #print 'winCam1 bmppaintqueue is full'
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
                    pass
                    #print 'winCam2 bmppaintqueue is full'

            try:
                parent.totrackqueue.put((self.timestamp,(self.raw.tostring(),self.raw.width,self.raw.height)),False)
            except Queue.Full:
                pass
                #print 'totrackqueue is full'

                    
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
        plsexit=False

        while True:
            if not self.aquirequeue.empty():
                (parent,self.caminterface,plsexit) =self.aquirequeue.get()
                
            if plsexit:
                #print 'return'
                return

        
            
            
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
                        pass
                        #print 'totrackqueue is full'

                    gc=wx.ClientDC(parent.panel)
                    try:
                        self.bmppaintqueue.put((temp, gc),False)
                    except Queue.Full:
                        pass
                        #print 'winCam bmppaintqueue3 is full'
                    
                #sleep(0.005)
                

class WinCamBmpPaintThread(threading.Thread):
    """Background Worker Thread Class."""

    def __init__(self, bmppaintqueue):
        """Init Worker Thread Class."""
        threading.Thread.__init__(self)
        self.bmppaintqueue=bmppaintqueue
 

        self.ScaledImg=cv.CreateImage((100,100),8,3)
        #self.setDaemon(True)
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

