# -*- coding: cp1252 -*-
import wx,cv,AVTCam
import threading
import Queue
from time import clock
from time import sleep
import ctypes
import math
import wx.lib.plot as plot

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
        #self.progressbar = wx.Gauge(self.status, -1, 100,wx.Point(rect.x + 2, rect.y + 2), wx.Size(rect.width - 4, rect.height - 4) )
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
        parent.LiveCamWin=LiveCamWin()
    def CreateLiveTrackView(self,parent,source):
        parent.LiveTrackWin=LiveTrackWin(source)
        source.childs.append(parent.LiveTrackWin)
    def CreateLivePlotView(self,parent,source):
        parent.LivePlotWin=LivePlotWin(source)
        source.childs.append(parent.LivePlotWin)
class LiveCamWin(wx.Frame):
    def __init__(self):
        screensize=wx.Display().GetGeometry()
        wx.Frame.__init__(self,None,wx.ID_ANY,title='LiveCamWin',pos=(0,0),size=(screensize[2]/2,screensize[3]/2),style= wx.BORDER_RAISED  | wx.DEFAULT_FRAME_STYLE )
        self.status=self.CreateStatusBar()
        self.status.SetFieldsCount(2)
        self.status.SetStatusWidths([-1,65])

        wx.EVT_CLOSE(self, self.OnClose)

        #startwerte
        self.datatoqueue=list()
        self.rawimage = cv.CreateImage((100,100),8,3)
        self.image = cv.CreateImage((100,100),8,3)
        cv.Set(self.rawimage,0)
        cv.Set(self.image,0)

        self.CalibData=CalibData()
        self.calibrated=False
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

        self.InitAVTCamera()
        
        self.Show()
        
    def InitAVTCamera(self):
         #print CamObj._get_Camera()
        try:
            self.caminterface=AVTCam.AVTCam(self,wx.ID_ANY,wx.DefaultPosition,wx.DefaultSize,0,'AVT')
            self.SetStatusText('AVT Interface&Driver found')
            self.Bind(AVTCam.EVT_CameraUnplugged, self.CamPlugUnplug)
            self.Bind(AVTCam.EVT_CameraPlugged, self.CamPlugUnplug)
            #self.Bind(wx.EVT_MENU, self.CameraProperties, id=ID_CPROP)
            self.Bind(AVTCam.EVT_FrameAcquired, self.GrabAVT)
            
            self.panel=wx.Panel(self, wx.ID_ANY, style=wx.BORDER_SUNKEN)
            self.panelsizer=wx.BoxSizer(wx.HORIZONTAL)
            self.panelsizer.Add(self.caminterface,2,wx.EXPAND)
            self.SetSizer(self.panelsizer)
    
        except:
            return False

        self.caminterface._set_Camera(0)
        self.aquire=self.caminterface._get_Acquire()
        self.caminterface._set_Acquire(False)
        self.caminterface._set_Mode(4)
        self.caminterface._set_GainControl(1)
        self.caminterface._set_Magnification(0)
        self.caminterface._set_ShutterControl(1)
        self.caminterface._set_Palette(0)

        self.caminterface._set_Acquire(True)
        return True
     
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
    def OnClose(self, event):
        self.caminterface._set_Acquire(False)
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

                #print rawdatapointer, width, height
                try:
                    self.memstring=ctypes.string_at(rawdatapointer,width*height)
                except:
                    break

                self.raw= cv.CreateImageHeader((width,height),cv.IPL_DEPTH_8U, 1)
                #self.raw=cv.CreateImage((width,height),cv.IPL_DEPTH_8U,1)
                cv.SetData(self.raw, self.memstring,width)
                #cv.Copy(raw,self.raw)
                #self.raw=cv.CloneImage(raw)
                
                
                for window in trackers:
                    wx.PostEvent(window, ResultEvent("Pic to Queue!",(self.timestamp,self.raw)))
                    
            self.aquirequeue.task_done()

class LiveTrackWin(wx.Frame):
    def __init__(self,source):
        self.winsource=source
        screensize=wx.Display().GetGeometry()
        wx.Frame.__init__(self,None,wx.ID_ANY,title='LiveTrackWin',pos=(screensize[2]/2,0),size=(screensize[2]/2,screensize[3]/2),style= wx.BORDER_RAISED  |  wx.RESIZE_BORDER |  wx.CAPTION   )
        self.status=self.CreateStatusBar()
        
        self.panel=wx.Panel(self, wx.ID_ANY, style=wx.BORDER_SUNKEN)
        self.panelsizer=wx.BoxSizer(wx.HORIZONTAL)
        self.panelsizer.Add(self.panel,2,wx.EXPAND)
        self.SetSizer(self.panelsizer)

        self.panel.Bind(wx.EVT_MOUSEWHEEL, self.Mousewheel)
        self.panel.Bind(wx.EVT_ENTER_WINDOW,self.MouseInWindow)
        self.panel.Bind(wx.EVT_LEAVE_WINDOW,self.MouseOutWindow)
        self.panel.Bind(wx.EVT_LEFT_DOWN,self.MouseLeftClick)
        self.panel.Bind(wx.EVT_RIGHT_DOWN,self.MouseRightClick)
        self.panel.Bind(wx.EVT_MOTION,self.MouseMove)
        self.panel.Bind(wx.EVT_RIGHT_UP,self.MouseRightClick)

        EVT_RESULT(self, self.PicProcessed)

        #spwan queue
        self.piclistqueue=Queue.PriorityQueue(-1)
        self.resultqueue=Queue.PriorityQueue(-1)
        self.bmppaintqueue=Queue.PriorityQueue(-1)
        #spawn pool of threads
        for i in range(1):
            t=ProcessPicThread(self,self.piclistqueue,self.resultqueue,i)

        #spawn pool of threads
        for i in range(1):
            t=BmpPaintThread(self.bmppaintqueue,i)
        
        
        #StartVariablen
        self.zoomval=0
        aspect=1.0

        self.zoomrect=None
        self.mousein=False
        self.newellip=None
        self.newcon=None
        self.elliplist=list()
        self.connectlist=list()
        self.rightdown=False, (None,None), (None,None)
        
        self.childs=list()


        self.Show()
        
    def PicProcessed(self, event):
        if event.msg=="Pic to Queue!":
            #print 'got pics'
            datatoqueue=list()
            datatoqueue.append((event.data[0],event.data[1], self.elliplist, self.connectlist,self.newellip,self.childs))
            self.piclistqueue.put(datatoqueue,True)
            self.newellip=None
        if event.msg=="Pic processed!":
            
            fromqueue=self.resultqueue.get()
            self.timestamp, self.image,  self.elliplist, self.connectlist,   =fromqueue[0],fromqueue[1],fromqueue[2], fromqueue[3]
            self.resultqueue.task_done()
            #print self.timestamp, len(self.elliplist)
            #print self.resultqueue.qsize()
            self.Replot()

    def Replot(self):
        winsize=self.GetSize()
        #print "start replot"+" "+str(len(self.elliplist))+" time "+str(self.timestamp)
        
        #draw connection in build
        #print self.rightmouse
        if self.rightdown[0]:
            isin,num=self.PosInFoundEllip(self.rightdown[1],self.elliplist)
            if isin:
                epar=self.GetEllipWithNum(self.elliplist,num)
                self.newcon=LinePar()
                self.newcon.Pt1=num
                self.newcon.Pt2=num
                self.newcon.Pos=self.rightdown[2]

                epar=self.GetEllipWithNum(self.elliplist,self.newcon.Pt1)
                cv.Line(self.image,(int(epar.MidPos[0]),int(epar.MidPos[1])),(int(self.newcon.Pos[0]),int(self.newcon.Pos[1])),cv.CV_RGB(0,255,0),1,8,0)
            else:
                self.rightdown=False, (None,None), (None,None)
                self.newcon=None
        if not self.rightdown[0] and isinstance(self.newcon,LinePar):
            
            isin,num=self.PosInFoundEllip(self.rightdown[2],self.elliplist)
            if isin:
                self.newcon.Pt2=num
                if self.newcon.Pt1==self.newcon.Pt2:
                    
                    epar=self.GetEllipWithNum(self.elliplist,self.newcon.Pt1)
                    self.elliplist.remove(epar)
                   
                    self.newcon=None
                    self.rightdown=False, (None,None), (None,None)
                else:
                 
                    self.newcon.Num=self.NumConnect(self.connectlist)
                    #print "connection appended"
                    self.connectlist.append(self.newcon)
                    self.newcon=None
                    self.rightdown=False, (None,None), (None,None)
            else:

                self.rightdown=False, (None,None), (None,None)
                self.newcon=None

        if self.zoomrect==None:
            self.zoomrect=(0,0,self.image.width,self.image.height)
            self.status.SetStatusText('Auflösung='+str(self.zoomrect[2])+'x'+str(self.zoomrect[3]))

        gc=wx.ClientDC(self.panel)
        self.panelwidth,self.panelheight=gc.GetSize()
        datatoqueue=list()
        datatoqueue.append((self.image,self.zoomrect, gc))
        self.bmppaintqueue.put(datatoqueue,True)
    def Mousewheel(self,event):
        if self.mousein:
            pt = event.GetPosition()
            #get mouse pic koords
            
            pos=self.Panel2ImageKoord(self.panelwidth,self.panelheight,self.zoomrect,pt)
            rot= event.GetWheelRotation()
            rot=rot/event.GetWheelDelta()
            if self.zoomval+rot<0:
                self.zoomval=0
            else:
                self.zoomval+=rot
            self.status.SetStatusText('Pos='+str(pos)+ ' Zoom=' + str(self.zoomval))
            #newzoomrect
            if self.zoomval>0:
                width=int(float(self.image.width)/float(self.zoomval))
                height=int(float(self.image.height)/float(self.zoomval))
                orx=pos[0]-int(float(width)/2)
                ory=pos[1]-int(float(height)/2)
                self.zoomrect=(orx,ory,width,height)
                if not self.CheckSubRect(self.image,self.zoomrect):
                    self.zoomrect=self.GetProperSubRect(self.image,self.zoomrect,True)
            else:
                self.zoomrect=(0,0,self.image.width,self.image.height)
            
    def MouseInWindow(self,event):
        self.mousein=True
    def MouseOutWindow(self,event):
        self.mousein=False
    def MouseLeftClick(self,event):
        #print "left click"
        if self.mousein:
            pt = event.GetPosition()
            #get mouse pic koords
            self.newellip=self.Panel2ImageKoord(self.panelwidth,self.panelheight,self.zoomrect,pt)



                    
    def MouseRightClick(self,event):
 

        if event.RightDown()and self.mousein:
            pt = event.GetPosition()
            #get mouse pic koords
            pos=self.Panel2ImageKoord(self.panelwidth,self.panelheight,self.zoomrect,pt)
            #in ellip?
            
            self.rightdown=True, pos, pos
            #print rightdown
        if event.RightUp()and self.mousein:
            pt = event.GetPosition()
            #get mouse pic koords
            pos=self.Panel2ImageKoord(self.panelwidth,self.panelheight,self.zoomrect,pt)
            self.rightdown=False,self.rightdown[1],pos
            #print self.rightdown
            
##            

    def MouseMove(self,event):
        if self.mousein:
            if event.RightIsDown()and self.rightdown[0]:
                pt = event.GetPosition()
                #get mouse pic koords
                self.rightdown=True,self.rightdown[1],self.Panel2ImageKoord(self.panelwidth,self.panelheight,self.zoomrect,pt)
                #print rightdown
                
    def Panel2ImageKoord(self,panelwidth,panelheight,zoomrect,pt):
        pos=int(float(pt[0])/float(panelwidth)*zoomrect[2]+zoomrect[0]),int(float(pt[1])/float(panelheight)*zoomrect[3]+zoomrect[1])
        return pos
    def CheckSubRect(self,image,rect):
        if (rect[0]+rect[2])<=image.width and (rect[1]+rect[3])<=image.height and rect[0]>=0 and rect[1]>=0 and rect[2]>=20 and rect[3]>=20:
            return True
        else:
            return False
    def GetProperSubRect(self,image,rect,keepsize):
        if keepsize==False:
            if rect[0]<0:
                orx=0
            else:
                orx=rect[0]
            if rect[1]<0:
                ory=0
            else:
                ory=rect[1]
            if (rect[0]+rect[2])>image.width:
                width=image.width-rect[0]
                
            else:
                width=rect[2]    
            if (rect[1]+rect[3])>image.height:
                height=image.height-rect[1]
            else:
                height=rect[3]   
            rect=(orx,ory,width,height)
        if keepsize==True:
            
            if rect[0]<0:
                orx=0
            else:
                orx=rect[0]
            if rect[1]<0:
                ory=0
            else:
                ory=rect[1]
            if (rect[0]+rect[2])>image.width:
                orx=image.width-rect[2]
            if (rect[1]+rect[3])>image.height:
                ory=image.height-rect[3]  
            rect=(orx,ory,rect[2],rect[3])
        return rect
    def GetEllipWithNum(self,liste,num):
        found=False
        for listpos, item in enumerate(liste):
            epar=EllipPar()
            epar=liste[listpos]
            if epar.Num==num:
                found=True
                break
        if found:
            return epar
        else:
            return None
    def GetAABBEllip(self,ellip):
        angle=-math.radians(ellip.Angle)
        if ellip.Size[0]<ellip.Size[1]:
            a=2*ellip.Size[1]
            b=2*ellip.Size[0]
        else:
            b=2*ellip.Size[1]
            a=2*ellip.Size[0]
        t=math.atan(-b*math.tan(angle)/a)
        x=abs(a*math.cos(t)*math.cos(angle)-b*math.sin(t)*math.sin(angle))
        t=math.atan(a*(1/math.tan(angle))/b)
        y=abs(b*math.sin(t)*math.cos(angle)+a*math.cos(t)*math.sin(angle))
        return y,x

    def PosInFoundEllip(self,pt,elliplist):
        isin=False
        for listpos, item in enumerate(elliplist):
            epar=EllipPar()
            epar=elliplist[listpos]
            b,h=self.GetAABBEllip(epar)
            rect = (int(epar.MidPos[0]-b/2),int(epar.MidPos[1]-h/2),int(b),int(h))
            if rect[0]<pt[0]<rect[0]+rect[2] and rect[1]<pt[1]<rect[1]+rect[3]:
                isin=True
                break
        if isin:
            return True, epar.Num
        else:
            return False,None
    def NumConnect(self,list):
        posiblenum=range(len(list)+10)
        for listpos, item in enumerate(list):
            linepar=LinePar()
            linepar=list[listpos]
            posiblenum.remove(linepar.Num)
        return posiblenum[0]
    def OnClose(self,event):
        for item in self.childs:
            item.OnClose(True)
        self.Destroy()
        
##
class ProcessPicThread(threading.Thread):
    """Background Worker Thread Class."""

    def __init__(self, parent, piclistqueue,resultqueue, num):
        """Init Worker Thread Class."""
        threading.Thread.__init__(self)
        self.font=cv.InitFont(cv.CV_FONT_HERSHEY_DUPLEX,1,1,0,1,8)
        self.parent=parent
        self.queue=piclistqueue
        self.out_queue=resultqueue
        self.num=num
        self.elliplist=list()
        self.connectlist=list()
        self.setDaemon(True)
        self.start()
        # start the thread
        
 
    def run(self):
        #print "Picthread started "+str(self.num)
        while True:
            pointerlist=self.queue.get()
            #print "Picthread got task"+ " "+str(self.num)+" "+str(len(pointerlist))

            for item in pointerlist:

                #print item
                self.timestamp=item[0]
                self.raw=item[1]
                self.elliplist=item[2]
                self.connectlist=item[3]
                self.newellip=item[4]
                self.CamChildren=item[5]
                self.newelliplist=list()
                self.newconnectlist=list()

                if len(self.parent.elliplist)!=len(self.elliplist):
                    numlist=list()
                    for item in self.parent.elliplist:
                        numlist.append(item.Num)
                    for item in self.elliplist:
                        if item.Num not in numlist:
                            self.elliplist.remove(item)
                            #print "item removed"
                    #print numlist

        
                #print "before processing "+str(len(self.elliplist))+" "+str(self.timestamp)

                self.image=cv.CreateImage((self.raw.width,self.raw.height),cv.IPL_DEPTH_8U,3)
                cv.CvtColor(self.raw,self.image,cv.CV_GRAY2RGB)
                

##
##                for i in range(10,500,20): 
##                    stor = cv.CreateMat(1, 2, cv.CV_32FC3)
##                    print i
##                    #circles=cv.HoughCircles(temp,stor,cv.CV_HOUGH_GRADIENT,2,self.raw.height/4,200, 100)
##                    try:
##                        circles=cv.HoughCircles(temp,stor,cv.CV_HOUGH_GRADIENT,1,i,130,100)
##                        print "found"
##                    except:
##                        pass
                if self.newellip!=None:
                    #check if in already found ellip
                    isin,num=self.PosInFoundEllip(self.newellip,self.elliplist)
                    if not isin:
                        #find ellip
                        ellip=self.PickEllip(self.raw,self.newellip[0],self.newellip[1],self.elliplist)    
                        if not ellip==None:
                            self.elliplist.append(ellip)
                            
                #print "thread "+str(self.num)+" ellip items to track"+ " "+str(len(self.elliplist))
                if len(self.elliplist)>0:
                    self.newelliplist, self.newconnectlist, self.image=self.ProcessImage(self.raw,self.image, self.elliplist, self.connectlist)
                    #print "after processing "+str(len(self.newelliplist))
                #print "thread "+str(self.num)+" ellip items tracked"+ " "+str(len(self.elliplist))

                
                
                trackers=list()
                trackers.append(self.parent) #put it to source
                for window in self.CamChildren:
                    if isinstance(window, LiveTrackWin)or isinstance(window, LivePlotWin):
                        trackers.append(window)

                for window in trackers:
                    #wx.PostEvent(self.tracker, ResultEvent("Pic processed!",self.image, self.elliplist))
                    self.out_queue.put((self.timestamp,self.image, self.newelliplist, self.newconnectlist))
                    wx.PostEvent(window, ResultEvent("Pic processed!",None))
                    self.out_queue.join()
                
                    
            self.queue.task_done()


        
    def ProcessImage(self, grayimage, rgbimage, ellipses,connections):
        #drawold

        
        for listpos, item in enumerate( ellipses):
            ellipPar=EllipPar()
            ellipPar=ellipses[listpos]
            self.DrawEllipMark(rgbimage,ellipPar,0,0,200)
        #track
        ellipses=self.TrackEllip(grayimage,ellipses)
        #draw new 
        for listpos, item in enumerate(ellipses):
            ellipPar=EllipPar()
            ellipPar=ellipses[listpos]
            
            self.DrawEllipMark(rgbimage,ellipPar,0,0,255)
               
        #draw connections
        for listpos, item in enumerate(connections):
                    
            linepar=LinePar()
            linepar=connections[listpos]
            epar1=self.GetEllipWithNum(ellipses,linepar.Pt1)
            epar2=self.GetEllipWithNum(ellipses,linepar.Pt2)
            if epar1==None or epar2==None:
                #print "connection removed"
                connections.remove(linepar)
            else:
                cv.Line(rgbimage,(int(epar1.MidPos[0]),int(epar1.MidPos[1])),(int(epar2.MidPos[0]),int(epar2.MidPos[1])),cv.CV_RGB(255,0,0),1,8,0)
                
                rx,ry=abs(epar1.MidPos[0]-epar2.MidPos[0]),abs(epar1.MidPos[1]-epar2.MidPos[1])
                if epar1.MidPos[0]<epar2.MidPos[0]:
                    posx=int(epar1.MidPos[0]+rx/2)
                else:
                    posx=int(epar2.MidPos[0]+rx/2)
                if epar1.MidPos[1]<epar2.MidPos[1]:
                    posy=int(epar1.MidPos[1]+ry/2)
                else:
                    posy=int(epar2.MidPos[1]+ry/2)

                cv.PutText(rgbimage,'C%d'%linepar.Num,(posx,posy),self.font,cv.CV_RGB(255,0,0))

                
                c=(rx**2.0+ry**2.0)**0.5
                
        return ellipses, connections, rgbimage


    def PickEllip(self,image,posx,posy,elliplist):
        found=0
        searchrectsize=20
        errcount=0
        stor = cv.CreateMemStorage(0)
        while found <1:
            searchrectsize=int(searchrectsize+searchrectsize/10)
            if searchrectsize>image.width/4:
                break
            searchrectr=(posx-searchrectsize,posy-searchrectsize,searchrectsize*2,searchrectsize*2)
            rectimage,searchrect=self.GetSearchCounturImage(image,searchrectr)
            if rectimage==None:
                break
            #cv.ShowImage('rect',rectimage)
            pixout,pixin=self.InOutVal(rectimage)
            if pixout==pixin:
                continue
            #print pixout,pixin
            cont=cv.FindContours (rectimage, stor, mode=cv.CV_RETR_LIST,method=cv.CV_CHAIN_APPROX_SIMPLE)
            morecont=True
            #print 'ok'
            while morecont:
               # print 'points?'
                if( len(cont) < 10):
                    ##print 'low points'
                    #print len(cont)
                    if len(cont)==0:
                        
                        break
                    cont=cont.h_next()
                    #print 'low pointss'
                    if cont==None:
                        morecont=False
                        #print 'low pointso'
                    #print 'low pointsc'
                    continue
                #print 'enought points'
                ellipPar=self.FitEllipOnContour(cont)
                #print 'oka'
                #define Number
                ellipPar.Num=self.NumEllip(elliplist)
                #print 'okb'
                #korrekt pos and size to global
                ellipPar.MidPos=ellipPar.MidPos[0]/rectimage.width*searchrect[2]+searchrect[0],ellipPar.MidPos[1]/rectimage.height*searchrect[3]+searchrect[1]
                ellipPar.Size= ellipPar.Size[0]/rectimage.width*searchrect[2]/2,ellipPar.Size[1]/rectimage.height*searchrect[3]/2
                ellipPar.Angle=-ellipPar.Angle
                ellipPar.mov=0,0
                
                if ellipPar.Size[1]!=0 and ellipPar.Size[0]!=0 and ellipPar.Size[1]<searchrect[3]/2 and ellipPar.Size[0]<searchrect[2]/2 and (pixin>pixout+254 or pixin<pixout-254):
                    found=1
                    
                
                cont=cont.h_next()
                if cont==None:
                        morecont=False
                if found==1:
                    break
            if searchrectsize*2>image.width:
                break
            
        if found>=1:
            #print 'okoo'
            return ellipPar
        else:
            return None



    def TrackEllip(self,image,ellipses):
        
        elliplistnew=list()
        for listpos, item in enumerate(ellipses):
            triedtorescue=False
            ellip=EllipPar()
            ellip=ellipses[listpos]
            b,h=self.GetAABBEllip(ellip)
            #b,h=b+20,h+20
            b,h=int(b+b/2),int(h+h/2)
            #b,h=int(b+20),int(h+20)
            
            if b<20 or h<20:
                aspect=float(b)/float(h)
                if aspect<1:
                    b=20
                    h=int(b/aspect)
                else:
                    h=20
                    b=int(h*aspect)
            
            #with movement correction
            searchrecttr = (int(ellip.MidPos[0]+int(ellip.mov[0])-b/2),int(ellip.MidPos[1]+int(ellip.mov[1])-h/2),int(b),int(h))
           
            #print 'finish init %(listpos)d in frame %(framenum)d ' % vars()
            rectimage, searchrect=self.GetSearchCounturImage(image,searchrecttr)
            if rectimage==None:
                continue
            #print 'get rectimage %(listpos)d in frame %(framenum)d ' % vars()
            #cv.ShowImage('rect',rectimage)
            pixout,pixin=self.InOutVal(rectimage)
            stor = cv.CreateMemStorage(0)
            cont=cv.FindContours (rectimage, stor, mode=cv.CV_RETR_LIST,method=cv.CV_CHAIN_APPROX_SIMPLE)
            morecont=True
            found=0
            while morecont:
                if( len(cont) < 5 or len(cont) >10000):
                    #print 'low points'
                    cont=cont.h_next()
                    if cont==None:
                        morecont=False
                    continue
                #print 'enought points'
                #print 'fit ellip %(listpos)d in frame %(framenum)d ' % vars()
                EllipParnew=self.FitEllipOnContour(cont)
                #define Number
                EllipParnew.Num=ellip.Num
                #korrekt pos and size to global

                EllipParnew.MidPos=EllipParnew.MidPos[0]+searchrect[0],EllipParnew.MidPos[1]+searchrect[1]
                EllipParnew.Size= EllipParnew.Size[0]/2,EllipParnew.Size[1]/2
                EllipParnew.Angle=-EllipParnew.Angle
                EllipParnew.mov=EllipParnew.MidPos[0]-ellip.MidPos[0],EllipParnew.MidPos[1]-ellip.MidPos[1]

                if EllipParnew.Size[1]!=0 and EllipParnew.Size[0]!=0  and 0.8<=ellip.Size[0]/EllipParnew.Size[0]<=1.2 and 0.8<=ellip.Size[1]/EllipParnew.Size[1]<=1.2 and 0.5<=ellip.Angle/EllipParnew.Angle<=1.5 and (pixin>pixout+254 or pixin<pixout-254):
                    found=1
                    #print 'found %(listpos)d in frame %(framenum)d ' % vars()
                    #print 'movement',EllipParnew.mov
                    break
                
                cont=cont.h_next()
                if cont==None:
                        morecont=False
            if found>=1:
                #print 'add found %(listpos)d in frame %(framenum)d ' % vars()
                elliplistnew.append(EllipParnew)            
            else:
                ##dont try to rescue we are live
                #triedtorescue=True
                if not triedtorescue:
                    #print 'rescue %(listpos)d in frame %(framenum)d ' % vars()
                    triedtorescue=True
                    #print 'create searchrects %(listpos)d in frame %(framenum)d ' % vars()
                    rectlist=self.RescueList(searchrect,ellip.mov)
                    for rect in rectlist:
                        #print 'get rectimage %(listpos)d in frame %(framenum)d ' % vars()
                        rectimage, searchrect=self.GetSearchCounturImage(image,rect)
                        if rectimage==None:
                            continue
                        #print 'got rectimage now show%(listpos)d in frame %(framenum)d ' % vars()
                        #cv.ShowImage('rect',rectimage)
                        pixout,pixin=self.InOutVal(rectimage)
                        if not (pixin>pixout+254 or pixin<pixout-254):
                            #print 'false treshold %(listpos)d in frame %(framenum)d ' % vars()
                            continue
                        cv.Rectangle(self.image,(searchrect[0],searchrect[1]),(int(searchrect[0]+searchrect[2]),int(searchrect[1]+searchrect[3])),cv.CV_RGB(0,255,0),1,8,0)
                        stor = cv.CreateMemStorage(0)
                        #print 'get contours %(listpos)d in frame %(framenum)d ' % vars()
                        cont=cv.FindContours (rectimage, stor, mode=cv.CV_RETR_LIST,method=cv.CV_CHAIN_APPROX_SIMPLE)
                        morecont=True
                        found=0
                        while morecont:
                            if( len(cont) < 5 or len(cont) >10000):
                                #print 'low points'
                                cont=cont.h_next()
                                if cont==None:
                                    morecont=False
                                continue
                            #print 'enought points'
                            #print 'fit ellip %(listpos)d in frame %(framenum)d ' % vars()
                            EllipParnew=self.FitEllipOnContour(cont)
                            #define Number
                            EllipParnew.Num=ellip.Num
                            #korrekt pos and size to global
                            EllipParnew.MidPos=EllipParnew.MidPos[0]+searchrect[0],EllipParnew.MidPos[1]+searchrect[1]
                            EllipParnew.Size= EllipParnew.Size[0]/2,EllipParnew.Size[1]/2
                            
                            EllipParnew.Angle=-EllipParnew.Angle
                            EllipParnew.mov=EllipParnew.MidPos[0]-ellip.MidPos[0],EllipParnew.MidPos[1]-ellip.MidPos[1]

                            if  EllipParnew.Size[1]!=0 and EllipParnew.Size[0]!=0  and (searchrect[0]+searchrect[2]*3/5.0)<EllipParnew.MidPos[0]<(searchrect[0]+searchrect[2]*4/5.0) and (searchrect[1]+searchrect[3]/3.0)<EllipParnew.MidPos[1]<(searchrect[1]+searchrect[3]/3.0*2.0) and (pixin>pixout+254 or pixin<pixout-254):
                                found=1
                                #print 'found %(listpos)d in frame %(framenum)d ' % vars()
                                break
                            
                            cont=cont.h_next()
                            if cont==None:
                                    morecont=False
                        if found>=1:
                            #print 'add found %(listpos)d in frame %(framenum)d ' % vars()
                            elliplistnew.append(EllipParnew)
                            break
                        #else:
                            #print 'rescue failed %(listpos)d in frame %(framenum)d ' % vars()

        #print 'copy list'             
        return elliplistnew

    
    def GetEllipWithNum(self,liste,num):
        found=False
        for listpos, item in enumerate(liste):
            epar=EllipPar()
            epar=liste[listpos]
            if epar.Num==num:
                found=True
                break
        if found:
            return epar
        else:
            return None
    def PosInFoundEllip(self,pt,elliplist):
        isin=False
        for listpos, item in enumerate(elliplist):
            epar=EllipPar()
            epar=elliplist[listpos]
            b,h=self.GetAABBEllip(epar)
            rect = (int(epar.MidPos[0]-b/2),int(epar.MidPos[1]-h/2),int(b),int(h))
            if rect[0]<pt[0]<rect[0]+rect[2] and rect[1]<pt[1]<rect[1]+rect[3]:
                isin=True
                break
        if isin:
            return True, epar.Num
        else:
            return False,None
            
    def FitEllipOnContour(self,contour):
        mat=cv.CreateMat(1,len(contour),cv.CV_32SC2)
        i=0
        for (x,y) in contour:
            mat[0,i]=x,y
            i+=1
            if i>len(contour):
                break
        box = cv.FitEllipse2(mat)
        epar=EllipPar()
        epar.MidPos=box[0]
        epar.Size=box[1]
        epar.Angle=box[2]
        return epar
    def RescueList(self,searchrect,mov):
        #make searchrect bigger and move around
        rectlist=list()
        #factors=range(1,5)
        factors=range(1,5)
        #bfactors=range(1,5)
        bfactors=range(1,5)
        #bfactors=range(1,10)

        for factor in factors:
            #teilen=12
            teilen=4
            for bfactor in bfactors:
                
                radius=(searchrect[2]+searchrect[3])/20.0*bfactor
                newb=int(searchrect[2]*(0.9+0.1*factor))
                newh=int(searchrect[3]*(0.9+0.1*factor))

                temp=int(searchrect[0]-int((newb-searchrect[2])/2.0)),searchrect[1]-int((newh-searchrect[3])/2.0),newb,newh
                rectlist.append(temp)

                temp=searchrect[0]-int((newb-searchrect[2])/2.0+radius),searchrect[1]-int((newh-searchrect[3])/2.0),newb,newh
                rectlist.append(temp)
                for i in range(teilen):
                    winkel=i*360.0/teilen
                   
                    pox=searchrect[0]+int(searchrect[2]/2.0)+int(math.cos(winkel)*radius)
                    poy=searchrect[1]+int(searchrect[3]/2.0)-int(math.sin(winkel)*radius)
                    temp=int(pox-int(newb/2.0)),int(poy-int(newh/2.0)),newb,newh
                    rectlist.append(temp)
                 
        return rectlist

    def GetAABBEllip(self,ellip):
        angle=-math.radians(ellip.Angle)
        if ellip.Size[0]<ellip.Size[1]:
            a=2*ellip.Size[1]
            b=2*ellip.Size[0]
        else:
            b=2*ellip.Size[1]
            a=2*ellip.Size[0]
        t=math.atan(-b*math.tan(angle)/a)
        x=abs(a*math.cos(t)*math.cos(angle)-b*math.sin(t)*math.sin(angle))
        t=math.atan(a*(1/math.tan(angle))/b)
        y=abs(b*math.sin(t)*math.cos(angle)+a*math.cos(t)*math.sin(angle))
        return y,x

    def DrawEllipMark(self,image,epar,color1,color2,color3):
        b,h=self.GetAABBEllip(epar)
        #b,h=b+20,h+20
        b,h=int(b+b/2),int(h+h/2)
        #b,h=int(b+10),int(h+10)
        if b<20 or h<20:
            aspect=float(b)/float(h)
            if aspect<1:
                b=20
                h=int(b/aspect)
            else:
                h=20
                b=int(h*aspect)
        #b,h=b+5,h+5
        posx=int(epar.MidPos[0]-b/2)
        posy=int(epar.MidPos[1]-h/2)
        cv.Rectangle(self.image,(posx,posy),(int(posx+b),int(posy+h)),cv.CV_RGB(color1,color2,color3),1,8,0)
        
        cv.Ellipse(image, (int(epar.MidPos[0]),int(epar.MidPos[1])), (int(epar.Size[0]),int(epar.Size[1])),int(epar.Angle), 0, 360,cv.CV_RGB(color1,color2,color3), 1, 8, 0);
        cv.Line(image,(int(epar.MidPos[0]-b/2),int(epar.MidPos[1])),(int(epar.MidPos[0]+b/2),int(epar.MidPos[1])),cv.CV_RGB(color1,color2,color3),1,8,0)
        cv.Line(image,(int(epar.MidPos[0]),int(epar.MidPos[1]-h/2)),(int(epar.MidPos[0]),int(epar.MidPos[1]+h/2)),cv.CV_RGB(color1,color2,color3),1,8,0)
        
        cv.PutText(image,'%d'%epar.Num,(int(posx+b),int(posy+h)),self.font,cv.CV_RGB(color1,color2,color3))
    def GetSearchCounturImage(self,image,rect):
        #print rect
        #if not self.CheckSubRect(image,rect):
            #print 'rect is corrected'
            #rect=self.GetProperSubRect(image,rect,False)
        #print rect
        # check again
        if not self.CheckSubRect(image,rect):
            return None,rect
        else:
            #print 'init subimage'
            pyrimage=cv.CreateImage((rect[2]*2,rect[3]*2),8,1)
            temp=cv.CreateImage((rect[2],rect[3]),8,1)
            thresimg=cv.CreateImage((rect[2],rect[3]),8,1)
            cv.SetImageROI(image,rect)
            #print 'copy subimage'
            cv.Copy(image,temp)
            cv.ResetImageROI(image)
            #print 'pyr subimage'
            cv.PyrUp(temp,pyrimage)
            cv.PyrDown(pyrimage,temp)
            #print 'calc thres subimage'
            pixout,pixin=self.InOutVal(temp)
            thres=int((pixin+pixout)/2)
            #print 'do thres subimage'
            cv.Threshold(temp,thresimg,thres,255,cv.CV_THRESH_BINARY)
            #print 'return subimage'
            return thresimg, rect
    def InOutVal(self,img):
        pixout=0
        pixin=0
        
        for i in range(img.width):
            pixout += img[0,i]+img[img.height-1,i]
        for i in range(img.height):
            pixout += img[i,0]+img[i,img.width-1]
        pixin=img[int(img.height/2),int(img.width/2)]+img[int(img.height/2)+1,int(img.width/2)]+img[int(img.height/2),int(img.width/2)+1]+img[int(img.height/2)+1,int(img.width/2)+1]
        pixout=pixout/(img.width*2+img.height*2)
        pixin=pixin/4
        return pixout,pixin
    def NumEllip(self, elliplist):
        posiblenum=range(len(elliplist)+10)
        for listpos, item in enumerate(elliplist):
            ellipPar=EllipPar()
            ellipPar=elliplist[listpos]
            posiblenum.remove(ellipPar.Num)
        return posiblenum[0]
    def NumConnect(self,list):
        posiblenum=range(len(list)+10)
        for listpos, item in enumerate(list):
            linepar=LinePar()
            linepar=list[listpos]
            posiblenum.remove(linepar.Num)
        return posiblenum[0]
    def CheckSubRect(self,image,rect):
        if (rect[0]+rect[2])<=image.width and (rect[1]+rect[3])<=image.height and rect[0]>=0 and rect[1]>=0 and rect[2]>=20 and rect[3]>=20:
            return True
        else:
            return False
    def GetProperSubRect(self,image,rect,keepsize):
        if keepsize==False:
            if rect[0]<0:
                orx=0
            else:
                orx=rect[0]
            if rect[1]<0:
                ory=0
            else:
                ory=rect[1]
            if (rect[0]+rect[2])>image.width:
                width=image.width-rect[0]
                
            else:
                width=rect[2]    
            if (rect[1]+rect[3])>image.height:
                height=image.height-rect[1]
            else:
                height=rect[3]   
            rect=(orx,ory,width,height)
        if keepsize==True:
            
            if rect[0]<0:
                orx=0
            else:
                orx=rect[0]
            if rect[1]<0:
                ory=0
            else:
                ory=rect[1]
            if (rect[0]+rect[2])>image.width:
                orx=image.width-rect[2]
            if (rect[1]+rect[3])>image.height:
                ory=image.height-rect[3]  
            rect=(orx,ory,rect[2],rect[3])
        return rect

class BmpPaintThread(threading.Thread):
    """Background Worker Thread Class."""

    def __init__(self, bmppaintqueue, num):
        """Init Worker Thread Class."""
        threading.Thread.__init__(self)
        self.bmppaintqueue=bmppaintqueue
        #self.piclistqueue=piclistqueue
        self.num=num
        self.ZoomImage=cv.CreateImage((100,100),8,3)
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
                zoomrect=item[1]
                dc=item[2]

                
                panelwidth,panelheight=dc.GetSize()
                if (panelwidth <=0) or (panelheight <=0):
                    continue
                if self.ScaledImg.width!=panelwidth or self.ScaledImg.height!=panelheight:
                    self.ScaledImg=cv.CreateImage((panelwidth,panelheight),8,3)
                #print "start"
                #print clock()
                if zoomrect[2]!=image.width or zoomrect[3]!=image.height:
                    cv.SetImageROI(image,zoomrect)
                    if self.ZoomImage.width!=zoomrect[2] or self.ZoomImage.height!=zoomrect[3]:
                        self.ZoomImage=cv.CreateImage((zoomrect[2],zoomrect[3]),8,3)
                    cv.Copy(image,self.ZoomImage)
                    cv.ResetImageROI(image)
                    cv.Resize(self.ZoomImage,self.ScaledImg,cv.CV_INTER_NN)
                else:
                    cv.Resize(image,self.ScaledImg,cv.CV_INTER_NN)
                
                #print "next bitmap"
                #print clock()
                
                self.bitmap=wx.BitmapFromBuffer(panelwidth,panelheight,self.ScaledImg.tostring()) 
                dc.DrawBitmap(self.bitmap, 0, 0, False)
                #print "finish"
                #print clock()
                
                    
            self.bmppaintqueue.task_done()

class LivePlotWin(wx.Frame):
    def __init__(self,source):
        self.winsource=source
        screensize=wx.Display().GetGeometry()
        wx.Frame.__init__(self,None,wx.ID_ANY,title='LiveCamWin',pos=(0,screensize[3]/2),size=(screensize[2]/2,screensize[3]/2),style= wx.BORDER_RAISED  |  wx.RESIZE_BORDER |  wx.CAPTION   )
        self.status=self.CreateStatusBar()

        self.buttonpanel=wx.Panel(self, wx.ID_ANY, style=wx.NO_BORDER)
        self.buttonsizer = wx.BoxSizer(wx.HORIZONTAL)
        self.startbutton=wx.BitmapButton(self.buttonpanel,wx.ID_ANY,wx.Image('Startupsmall.png', wx.BITMAP_TYPE_PNG).ConvertToBitmap(),style=wx.BU_EXACTFIT)
        self.stopbutton=wx.BitmapButton(self.buttonpanel,wx.ID_ANY,wx.Image('Stopupsmall.png', wx.BITMAP_TYPE_PNG).ConvertToBitmap(),style=wx.BU_EXACTFIT)
        self.startbutton.SetBitmapSelected(wx.Image('Startdownsmall.png', wx.BITMAP_TYPE_PNG).ConvertToBitmap())
        self.stopbutton.SetBitmapSelected(wx.Image('Stopdownsmall.png', wx.BITMAP_TYPE_PNG).ConvertToBitmap())
        self.buttonsizer.Add(self.startbutton,0)
        self.buttonsizer.Add(self.stopbutton,0)
        self.buttonpanel.SetSizer(self.buttonsizer)

        self.splitter = wx.SplitterWindow(self, wx.ID_ANY, style=wx.SP_BORDER)
        self.splitter.SetMinimumPaneSize(50)
        self.panel=wx.Panel(self.splitter, wx.ID_ANY, size=(500,500),style=wx.BORDER_SUNKEN)
        self.plotter = plot.PlotCanvas(self.panel)
        self.plotter.SetEnableLegend(True)

        #spwan queue
        self.dataqueue=Queue.PriorityQueue(-1)
        #spawn pool of threads
        for i in range(1):
            t=DataProtoThread(self,self.dataqueue,i)

        
        self.toqueue=list()
        self.itemlist=list()
        
        self.plotlist=list()
        self.data = list()
        self.toplotlist=list()
        self.elliplist=list()
        self.connectlist=list()
        self.tofile=False
        self.filename=None
        self.fp=None
        self.count=0
        self.called=0
        self.plotstarttime=clock()
        self.childs=list()
       
        self.tree = wx.TreeCtrl(self.splitter,style=wx.TR_HIDE_ROOT+wx.TR_MULTIPLE)
        self.splitter.SplitVertically(self.tree,self.panel)
      

        self.sizer = wx.BoxSizer(wx.VERTICAL)
        self.sizer.Add(self.buttonpanel,0,wx.EXPAND)
        self.sizer.Add(self.splitter,1,wx.EXPAND)
        self.SetSizer(self.sizer)
        
        #menu=self.CreateMenu(self.parent)
        #self.SetMenuBar(menu)

        
        #elf.Bind(wx.EVT_CLOSE, self.OnClose)
        #self.Bind(wx.EVT_MENU, self.CreateVidFace, id=ID_VIDFACE)

        EVT_RESULT(self, self.PicProcessed)

        
        self.startbutton.Bind(wx.EVT_BUTTON, self.OnStart)
        self.stopbutton.Bind(wx.EVT_BUTTON, self.OnStop)

        self.tree.Bind(wx.EVT_MOUSE_EVENTS,self.OnSelChanged)
        self.tree.Bind(wx.EVT_TREE_SEL_CHANGED,self.OnSelChanged)
        self.tree.Bind(wx.EVT_TREE_SEL_CHANGING,self.OnSelChanging)

        self.imageslist=wx.ImageList(16,16)


        
        self.imageslist.Add(wx.Bitmap('calicon.png'))
        self.tree.SetImageList(self.imageslist)

       
        self.splitter.SetSize (self.GetClientSize ())
        size = self.GetSize()
        self.splitter.SetSashPosition(size.x / 5)


        self.Layout()
        self.Show()
        self.panel.Update()
    def OnStart(self,event):
        self.tofile=True
        self.filename='test.txt'
        self.fp=open('test.txt','w',1)
        self.WriteDataHead(self.fp)
        self.parent.SetStatusText('Capturing')
        self.capturestarttime=clock()
        self.data=list()
    def WriteDataHead(self,fileinter):
        for i in range(len(self.toplotlist)):
            if i==0:
                string='Time'+'\t'
            else:
                string=string+'\t'
            string= string+str(self.toplotlist[i])
        fileinter.writelines(string+'\n')
    def OnStop(self,event):
        
        self.tofile=False
        self.filename=None
        try:
            del self.videowriter
        except:
            pass
        self.fp=None
        self.parent.SetStatusText('Stopped Capturing')
    def GetEllipWithNum(self,liste,num):
        found=False
        for listpos, item in enumerate(liste):
            epar=EllipPar()
            epar=liste[listpos]
            if epar.Num==num:
                found=True
                break
        if found:
            return epar
        else:
            return None
    def GetConnectWithNum(self,liste,num):
        found=False
        for listpos, item in enumerate(liste):
            linepar=LinePar()
            linepar=liste[listpos]
            if linepar.Num==num:
                found=True
                break
        if found:
            return linepar
        else:
            return None
    def OnSelChanging(self,event):
        pass
    def OnSelChanged(self,event):
        if isinstance(event,wx.TreeEvent) or event.LeftUp():
    
       
            if not self.tofile:
                treesel=self.tree.GetSelections()
                self.toplotlist=list()
                for subitem in treesel:
                    if self.tree.ItemHasChildren(subitem ):
                        self.tree.UnselectItem(subitem )
                        continue
                    if subitem.IsOk():
                        #self.tree.SetItemImage(subitem,0)
                        item=self.tree.GetItemParent(subitem)
                        if item.IsOk():
                            parent = self.tree.GetItemParent(item)            
                            if parent.IsOk():
                                if self.tree.GetItemText(parent)=='Ellipse' or self.tree.GetItemText(parent)=='Connection':
                                    self.data = list()
                                    this=str(self.tree.GetItemText(parent)),int(self.tree.GetItemText(item)),str(self.tree.GetItemText(subitem))
                                    self.toplotlist.append(this)
        #self.BuildTreeCtrl()

    def BuildTreeCtrl(self):
        
        self.tree.DeleteAllItems()
        Element = self.tree.AddRoot('Element')
        if len(self.itemlist)>0:
            for listpos, item in enumerate(self.itemlist):
                if isinstance(self.itemlist[listpos],EllipPar):
                    #print "is ellip"
                    par=EllipPar()
                    par=self.itemlist[listpos]
                    Ellipse=self.tree.AppendItem(Element,'Ellipse')
                    this=self.tree.AppendItem(Ellipse,str(par.Num))
                    c1=self.tree.AppendItem(this,'MidPos x')
                    if self.winsource.winsource.calibrated:
                        self.tree.SetItemImage(c1,0)
                    c2=self.tree.AppendItem(this,'MidPos y')
                    if self.winsource.winsource.calibrated:
                        self.tree.SetItemImage(c2,0)
                    c3=self.tree.AppendItem(this,'Size a')
                    c4=self.tree.AppendItem(this,'Size b')
                    c5=self.tree.AppendItem(this,'Angle')
                if isinstance(self.itemlist[listpos],LinePar):
                    #print  "is connect"
                    par=LinePar()
                    par=self.itemlist[listpos]
                    Connection=self.tree.AppendItem(Element,'Connection')
                    this=self.tree.AppendItem(Connection,str(par.Num))
                    c1=self.tree.AppendItem(this,'Range x')
                    if self.winsource.winsource.calibrated:
                        self.tree.SetItemImage(c1,0)
                    c2=self.tree.AppendItem(this,'Range y')
                    if self.winsource.winsource.calibrated:
                        self.tree.SetItemImage(c2,0)
                    c3=self.tree.AppendItem(this,'Lenght')
                    if self.winsource.winsource.calibrated:
                        self.tree.SetItemImage(c3,0)
                    #print len(self.itemlist),len(elliplist),len(connectlist)
        self.RecallTreeSelection()
        self.tree.ExpandAll()

    def RecallTreeSelection(self):
        self.tree.UnselectAll()
        root=self.tree.GetRootItem()
        if root.IsOk():
            child=self.tree.GetFirstChild(root)
            while child[0].IsOk():
                grandchild=self.tree.GetFirstChild(child[0])
                while grandchild[0].IsOk():
                    grandgrandchild=self.tree.GetFirstChild(grandchild[0])
                    while grandgrandchild[0].IsOk():
                        if (str(self.tree.GetItemText(child[0])),int(self.tree.GetItemText(grandchild[0])),str(self.tree.GetItemText(grandgrandchild[0]))) in self.toplotlist:
                            self.tree.SelectItem(grandgrandchild[0])    
                        grandgrandchild=self.tree.GetNextChild(grandgrandchild[0],grandgrandchild[1])
                    grandchild=self.tree.GetNextChild(grandchild[0],grandchild[1])
                child=self.tree.GetNextChild(child[0],child[1])
    def PicProcessed(self,event):
        if event.msg=="Pic processed!":
            fromqueue=self.winsource.resultqueue.get()
            self.winsource.resultqueue.task_done()
            timestamp, self.elliplist, self.connectlist  =fromqueue[0],fromqueue[2], fromqueue[3]
            if len(self.itemlist)!=len(self.elliplist)+len(self.connectlist):
                #print "rebuild tree 1" 
                self.itemlist=list()
                self.itemlist.extend(self.elliplist)
                self.itemlist.extend(self.connectlist)
                self.BuildTreeCtrl()
            if len(self.itemlist)>0:
                self.toqueue.append((timestamp, self.elliplist, self.connectlist,self.toplotlist,self.tofile,self.filename))
                if len(self.toqueue)>=5:
                    self.dataqueue.put(self.toqueue)
                    self.toqueue=list()
            if len(self.itemlist)!=len(self.elliplist)+len(self.connectlist):
                #print "rebuild tree 2"
                self.itemlist=list()
                self.itemlist.extend(self.elliplist)
                self.itemlist.extend(self.connectlist)
                self.BuildTreeCtrl()
            #print self.timestamp, len(self.elliplist)
            #print self.resultqueue.qsize()
            #self.Replot()
        if event.msg=="Data ready!":
            
            #print "Data received"
                #print len(self.itemlist),len(elliplist),len(connectlist)
            #print event.data
            self.called+=1
            if self.called<=1:
                #for plotting
                panelwidth,panelheight=self.panel.GetSize()
                self.plotter.SetSize(size=(panelwidth,panelheight))
                
                if len(event.data)>0:
                    gc = plot.PlotGraphics(event.data, '', 'Time [s]', '[pixel]')
                    self.plotter.Draw(gc)
                    self.plotter.SetXSpec('min')
                    self.plotter.SetYSpec('min')   
                    self.plotter.Redraw()
                self.called=0
    def KoordinatestoUndist(self,winsource,x,y):
        src=cv.CreateMat(1,1,cv.CV_64FC2)
        dst=cv.CreateMat(1,1,cv.CV_64FC2)
        cv.Set1D(src,0,cv.Scalar(x,y,0,0));
        new=cv.Get1D(src,0)
        newx=new[0]
        newy=new[1]
        #must be camera matrix at last position to give accurate results
        
        cv.UndistortPoints(src,dst,winsource.CalibData.intrinsic,winsource.CalibData.distortion,P=winsource.CalibData.intrinsic)
        new=cv.Get1D(dst,0)
        newx=new[0]
        newy=new[1]
        return newx,newy
    def OnClose(self,event):
        for item in self.childs:
            item.OnClose(True)
        self.Destroy()

class DataProtoThread(threading.Thread):
    """Background Worker Thread Class."""

    def __init__(self, parent,dataqueue,num):
        """Init Worker Thread Class."""
        threading.Thread.__init__(self)
        self.parent=parent
        self.dataqueue=dataqueue
        #self.piclistqueue=piclistqueue
        self.num=num
        self.data=list()
        self.plotlist=list()
        self.colours=('BLACK','RED','BLUE','GREEN','PINK','YELLOW','CYAN','PEACHPUFF','TURQUOSE','DARKRED','DARKBLUE','DARKGREEN')
        self.tofile=False
        self.filename=None
        self.fp=None
        self.setDaemon(True)
        self.start()
        # start the thread
        
 
    def run(self):
        #print "Aquirethread started "+str(self.num)
        while True:
        
            pointerlist=self.dataqueue.get()
            #print "DataProtothread got task"+ " "+str(self.num)+" "+str(len(pointerlist))
            
            for item in pointerlist:

                self.timestamp=item[0]
                self.elliplist=item[1]
                self.connectlist=item[2]
                self.toplotlist=item[3]
                self.tofile=item[4]
                self.filename=item[5]

                
                
                #plot selection and to write file
                plotlist=list()
                if self.tofile and self.fp==None:
                    self.fp=open(self.filename,'w',1)
                    #write header
                    for i in range(len(self.toplotlist)):
                        if i==0:
                            string='Time'+'\t'
                        else:
                            string=string+'\t'
                        string= string+str(self.toplotlist[i])
                    self.fp.writelines(string+'\n')
               
                for listpos, item in enumerate(self.toplotlist):
                    self.toplot=self.toplotlist[listpos]
                    if listpos<len(self.data):
                        temp=self.data[listpos]
                    else:
                        temp=list()
                   
                    time=self.timestamp
                    if self.toplot[0]=='Connection':
                        
                        linepar=LinePar()
                        epar1=EllipPar()
                        epar2=EllipPar()
                        if self.GetConnectWithNum(self.connectlist,self.toplot[1]) == None:
                            #print 'no connect'
                            continue
                        else:
                            linepar=self.GetConnectWithNum(self.connectlist,self.toplot[1])
                        
                        if self.GetEllipWithNum(self.elliplist,linepar.Pt1)== None or self.GetEllipWithNum(self.elliplist,linepar.Pt2) == None:
                            #print 'no points'
                            continue
                        else:
                            epar1=self.GetEllipWithNum(self.elliplist,linepar.Pt1)
                            epar2=self.GetEllipWithNum(self.elliplist,linepar.Pt2)
                            

                        rx,ry=abs(epar1.MidPos[0]-epar2.MidPos[0]),abs(epar1.MidPos[1]-epar2.MidPos[1])
                        
                        #if self.winsource.winsource.calibrated:
                        #    rx,ry=self.KoordinatestoUndist(self.winsource.winsource,rx,ry)
                            
                        c=(rx**2.0+ry**2.0)**0.5
                        if self.toplot[2]=='Range x':
                            this=rx
                        if self.toplot[2]=='Range y':
                            this=ry
                        if self.toplot[2]=='Lenght':
                            this=c
                        temp.append((time,this))
                    if self.toplot[0]=='Ellipse':
                        ellip=EllipPar()
                        if self.GetEllipWithNum(self.elliplist,self.toplot[1])== None:
                            continue
                        else:
                            epar=self.GetEllipWithNum(self.elliplist,self.toplot[1])
                            if self.toplot[2]=='MidPos x':
                                this=epar.MidPos[0]
                            if self.toplot[2]=='MidPos y':
                                this=epar.MidPos[1]
                            if self.toplot[2]=='Size a':
                                this=epar.Size[0]
                            if self.toplot[2]=='Size b':
                                this=epar.Size[1]
                            if self.toplot[2]=='Angle':
                                this=epar.Angle
                            temp.append((time,this))
                    if self.tofile:
                        if listpos==0:
                            string=str(time)+'\t'
                        else:
                            string=string+'\t'
                        string= string+str(this)

                    
                    if len(temp)>200:
                        delelem=temp.pop(0)
                        del delelem
                    if listpos<len(self.data):
                        self.data[listpos]=temp
                    else:
                        self.data.append(temp)
                if self.tofile:
                    self.fp.writelines(string+'\n')
        ##        if self.tofile:
        ##            self.fp.writelines(string+'\n')
        ##            
        ##            try:
        ##                #scale down to 720x560
        ##                cv.Resize(self.winsource.image,self.vidframe,cv.CV_INTER_NN)
        ##                cv.CvtColor(self.vidframe,self.vidframe,cv.CV_RGB2BGR)
        ##                cv.WriteFrame(self.videowriter,self.vidframe)
        ##            except:
        ##                pass
                for i in range(len(self.data)):
                    line = plot.PolyLine(self.data[i], colour=self.colours[i], width=1,legend=self.toplotlist[i][0]+' '+str(self.toplotlist[i][1]))
                    plotlist.append(line)
                    marker = plot.PolyMarker(self.data[i], colour=self.colours[i] ,marker='circle',width=1, size=1,legend=self.toplotlist[i][2])
                    plotlist.append(marker)
                    self.plotlist=plotlist

                
            wx.PostEvent(self.parent, ResultEvent("Data ready!",self.plotlist))
                    
                    
            self.dataqueue.task_done()
    def GetEllipWithNum(self,liste,num):
        found=False
        for listpos, item in enumerate(liste):
            epar=EllipPar()
            epar=liste[listpos]
            if epar.Num==num:
                found=True
                break
        if found:
            return epar
        else:
            return None
    def GetConnectWithNum(self,liste,num):
        found=False
        for listpos, item in enumerate(liste):
            linepar=LinePar()
            linepar=liste[listpos]
            if linepar.Num==num:
                found=True
                break
        if found:
            return linepar
        else:
            return None
    




class CalibData:
    def __init__(self):
        self.intrinsic=cv.CreateMat(3,3,cv.CV_32FC1)
        self.recti=cv.CreateMat(3,3,cv.CV_32FC1)
        cv.Set(self.recti,1)
        
        self.distortion=cv.CreateMat(5,1,cv.CV_32FC1)    

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
        
        
        
class App(wx.App):
    def OnInit(self):
        
        self.InitFrame=InitFrame(self)
        return True

if __name__=="__main__":
    
    #app = App(redirect=False)
    app = App(redirect=1)
    app.MainLoop()
