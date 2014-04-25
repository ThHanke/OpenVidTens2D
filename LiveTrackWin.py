# -*- coding: cp1252 -*-
import wx,cv2,numpy,os
import threading


import math
import pickle
import Queue

import multiprocessing

#import globals
import config

#from time import sleep
from time import clock

ID_CCAL=wx.NewId()
ID_CCALL=wx.NewId()
ID_CCALS=wx.NewId()
ID_PICKALL=wx.NewId()
ID_SRFACTOR=wx.NewId()
ID_VSTREAM=wx.NewId()

def contour_iterator(contour):
    while contour:
        yield contour
        contour = contour.h_next()

class LiveTrackWin(wx.Frame):
    def __init__(self,totrackqueue,trackresultqueue,pipetocam,pipetoplot):
        self.totrackqueue=totrackqueue
        self.pipetocam=pipetocam
        self.pipetoplot=pipetoplot
        screensize=wx.Display().GetGeometry()
        wx.Frame.__init__(self,None,wx.ID_ANY,title='LiveTrackWin',pos=(screensize[2]/2,0),size=(screensize[2]/2,screensize[3]/2),style= wx.DEFAULT_FRAME_STYLE ^ wx.CLOSE_BOX   )
        self.status=self.CreateStatusBar()
        self.status.SetFieldsCount(2)
        self.status.SetStatusWidths([-1,65])

        self.lasttime=0
        self.acttime=0
        self.framecount=0
        
        self.panel=wx.Panel(self, wx.ID_ANY, style=wx.BORDER_SUNKEN)
        self.panelsizer=wx.BoxSizer(wx.HORIZONTAL)
        self.panelsizer.Add(self.panel,2,wx.EXPAND)
        self.SetSizer(self.panelsizer)

        menu=self.CreateMenu()
        self.SetMenuBar(menu)

        self.Bind(wx.EVT_MENU, self.CameraCalibration, id=ID_CCAL)
        self.Bind(wx.EVT_MENU, self.LoadCalibration, id=ID_CCALL)
        self.Bind(wx.EVT_MENU, self.SaveCalibration, id=ID_CCALS)
        self.Bind(wx.EVT_MENU, self.PickAll, id=ID_PICKALL)
        self.Bind(wx.EVT_MENU, self.ChangeSRFactor, id=ID_SRFACTOR)
        self.Bind(wx.EVT_MENU, self.EnableRecord, id=ID_VSTREAM)

        self.panel.Bind(wx.EVT_MOUSEWHEEL, self.Mousewheel)
        self.panel.Bind(wx.EVT_ENTER_WINDOW,self.MouseInWindow)
        self.panel.Bind(wx.EVT_LEAVE_WINDOW,self.MouseOutWindow)
        self.panel.Bind(wx.EVT_LEFT_DOWN,self.MouseLeftClick)
        self.panel.Bind(wx.EVT_RIGHT_DOWN,self.MouseRightClick)
        self.panel.Bind(wx.EVT_MOTION,self.MouseMove)
        self.panel.Bind(wx.EVT_RIGHT_UP,self.MouseRightClick)

        #spwan queue

        self.resultqueueTrack=multiprocessing.Queue(1)
        #self.resultqueuePlot=multiprocessing.Queue(5)
        self.resultqueuePlot=trackresultqueue
        
        self.parentendpipe,self.childendpipe=multiprocessing.Pipe()

        self.UpdateInfoTimer=wx.Timer(self)
        self.Bind(wx.EVT_TIMER,self.UpdateInfo)
        self.UpdateInfoTimer.Start(100)
        
        #StartVariablen
        self.zoomval=0

        self.zoomrect=None
        self.mousein=False
        self.newellip=None
        self.newcon=None
        self.timestamp=0
        self.elliplist=list()
        self.connectlist=list()
        self.rightdown=False, (None,None), (None,None)
        self.PickAll=False



        self.CalibData=CalibData()
        self.calibrated=False


        self.seachrectfactor=15
        
        self.childs=list()

        ProcessPicThread(self.childendpipe,self.pipetoplot,self.totrackqueue,self.resultqueueTrack,self.resultqueuePlot,0)
        #init variables in backgroundprocess
        #self.SendStatustoBackgroundProcess()

        WinTrackBmpPaintThread(self,self.resultqueueTrack,self.panel,0)

        self.Show()
    def CreateMenu(self):
        Menubar =wx.MenuBar()
        Operate = wx.Menu()
        Menubar.Append(Operate,'&Operate')
        
        Operate.Append(ID_CCALL,'&Load Calibration','Load camera calibration')
        Operate.Append(ID_CCALS,'&Save Calibration','Save camera calibration')
        Operate.Append(ID_CCAL,'&Calibration','Camera Calibration')
        Operate.Append(ID_PICKALL,'&Pick All','Try to pick all ellipses')
        Operate.Append(ID_SRFACTOR,'&SRFactor','Change SearchrectFaktor')
        Operate.Append(ID_VSTREAM, '&Record Video', 'Save Live STream when Capturing',kind=wx.ITEM_CHECK)
        
        return Menubar   
    def Replot(self):
##        #only used in fileinterface
        self.pipetocam.send('Replot')
    def EnableRecord(self,event):
        if event.IsChecked():
            self.parentendpipe.send('Enable Record')
        else:
            self.parentendpipe.send('Disable Record')
    def UpdateInfo(self,event):
        if self.parentendpipe.poll():
            msg=self.parentendpipe.recv()
            if msg=='Successfully calibrated!':
                filecalib=open("Calibration.cal",'r')
                self.CalibData.intrinsict,self.CalibData.distortion,self.CalibData.distanceunit=pickle.load(filecalib)
                filecalib.close()
            self.SetStatusText(msg)

        
        
#    def SendStatustoBackgroundProcess(self):
#        self.parentendpipe.send((self.newellip,self.PickAll,self.rightdown,self.seachrectfactor,self.calibrate))
    def Mousewheel(self,event):
        if self.mousein:
            pt = event.GetPosition()
            pos=self.Panel2ImageKoord(self.panel.Size[0],self.panel.Size[1],self.zoomrect,pt)
            rot= event.GetWheelRotation()
            rot=rot/event.GetWheelDelta()
            if self.zoomval+rot<0:
                self.zoomval=0
            else:
                self.zoomval+=rot
            self.status.SetStatusText('Pos='+str(pos)+ ' Zoom=' + str(self.zoomval))
            #newzoomrect
            if self.zoomval>0:
                width=int(float(self.imagetuple.shape[1])/float(self.zoomval))
                height=int(float(self.imagetuple.shape[0])/float(self.zoomval))
                orx=pos[0]-int(float(width)/2)
                ory=pos[1]-int(float(height)/2)
                self.zoomrect=(orx,ory,width,height)
                if not self.CheckSubRect(self.imagetuple,self.zoomrect):
                    self.zoomrect=self.GetProperSubRect(self.imagetuple,self.zoomrect,True)
            else:
                self.zoomrect=(0,0,self.imagetuple.shape[1],self.imagetuple.shape[0])
            self.Replot()
    def MouseInWindow(self,event):
        self.mousein=True
    def MouseOutWindow(self,event):
        self.mousein=False
    def MouseLeftClick(self,event):
        #print "left click"
        if self.mousein:
            pt = event.GetPosition()
            #get mouse pic koords
            self.newellip=self.Panel2ImageKoord(self.panel.Size[0],self.panel.Size[1],self.zoomrect,pt)
            self.parentendpipe.send(('New mark',self.newellip))
            #self.SendStatustoBackgroundProcess()
            self.newellip=None
            
            self.Replot()
    def MouseRightClick(self,event):
        if event.RightDown()and self.mousein:
            pt = event.GetPosition()
            pos=self.Panel2ImageKoord(self.panel.Size[0],self.panel.Size[1],self.zoomrect,pt)
            #in ellip?
            self.rightdown=True, pos, pos
            #print self.rightdown
        if event.RightUp()and self.mousein:
            pt = event.GetPosition()
            #get mouse pic koords
            pos=self.Panel2ImageKoord(self.panel.Size[0],self.panel.Size[1],self.zoomrect,pt)
            self.rightdown=False,self.rightdown[1],pos
            #send to background process
            self.parentendpipe.send(('New connection',self.rightdown))
            #self.SendStatustoBackgroundProcess()
            self.rightdown=False,(None,None),(None,None)
            #print self.rightdown

            self.Replot()
    def MouseMove(self,event):
        if self.mousein:
##            if self.parentendpipe.poll():
##                #print 'polled and not empty'
##                (self.timestamp, self.elliplist, self.connectlist)=self.parentendpipe.recv()
##                #print 'update recevied'
            if event.RightIsDown()and self.rightdown[0]:
                pt = event.GetPosition()
                #get mouse pic koords
                self.rightdown=True,self.rightdown[1],self.Panel2ImageKoord(self.panel.Size[0],self.panel.Size[1],self.zoomrect,pt)
                #print self.rightdown

                self.Replot()
    def CameraCalibration(self,event):
        #filters = 'Image files (*.gif;*.png;*.jpg;*.bmp)|*.gif;*.png;*.jpg;*.bmp'
        #print 'sendcommand'
        self.parentendpipe.send(('calibrate',None))
        #self.SendStatustoBackgroundProcess()
        

    def SaveCalibration(self,event):
        
        directory=config.ProgDir
        filename="Calibration.cal"
        dlg = wx.FileDialog(self, "Save camera calibration data as", directory, filename, 'cal files (*.cal)|*.cal', wx.SAVE)
        if (dlg.ShowModal()==wx.ID_OK):
            filename=dlg.GetFilename()
            directory=dlg.GetDirectory()
        dlg.Destroy()
        filecalib=open(filename,'w')
        pickle.dump((self.CalibData.intrinsic,self.CalibData.distortion,self.CalibData.distanceunit ),filecalib)
        filecalib.close()
    
    def LoadCalibration(self,event):
        self.SetStatusText('Select file with intrinsic camera matrix')
        dlg = wx.FileDialog(self, "Select file with intrinsic camera matrix", config.ProgDir, "", 'cal files (*.cal)|*.cal', wx.FD_OPEN)
        if dlg.ShowModal() == wx.ID_OK:
            filename=dlg.GetFilenames()
            filecalib=open(filename[0],'r')
            self.CalibData.intrinsic,self.CalibData.distortion,self.CalibData.distanceunit=pickle.load(filecalib)
            filecalib.close()
            dlg.Destroy()

            #self.calibrated=True
            #self.SendStatustoBackgroundProcess()
            self.parentendpipe.send(('new calibration',(self.CalibData.intrinsic,self.CalibData.distortion)))
            #self.childs[0].SendStatustoBackgroundProcess()
            self.SetStatusText('Calibration successfully loaded')
        else:
            wx.MessageBox('False Input!',style= wx.OK | wx.ICON_ERROR)
            
    def PickAll(self,event):

        self.parentendpipe.send(('pick all marks',None))

    def ChangeSRFactor(self,event):
        dlg=wx.NumberEntryDialog(self,'Enter new SearchrectFactor','SRF:','SearchrectFactor',15,15,50)
        if dlg.ShowModal() == wx.ID_OK:
            self.seachrectfactor=dlg.GetValue()
            #print self.seachrectfactor
            self.parentendpipe.send(('searchrectfactor',self.seachrectfactor))
            dlg.Destroy()
    def Panel2ImageKoord(self,panelwidth,panelheight,zoomrect,pt):
        pos=int(float(pt[0])/float(panelwidth)*zoomrect[2]+zoomrect[0]),int(float(pt[1])/float(panelheight)*zoomrect[3]+zoomrect[1])
        return pos
    def CheckSubRect(self,image,rect):
        if (rect[0]+rect[2])<=image.shape[1] and (rect[1]+rect[3])<=image.shape[0] and rect[0]>=0 and rect[1]>=0 and rect[2]>=20 and rect[3]>=20:
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
            if (rect[0]+rect[2])>image.shape[1]:
                width=image.shape[1]-rect[0]
                
            else:
                width=rect[2]    
            if (rect[1]+rect[3])>image.shape[0]:
                height=image.shape[0]-rect[1]
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
            if (rect[0]+rect[2])>image.shape[1]:
                orx=image.shape[1]-rect[2]
            if (rect[1]+rect[3])>image.shape[0]:
                ory=image.shape[0]-rect[3]  
            rect=(orx,ory,rect[2],rect[3])
        return rect
    def GetEllipWithNum(self,liste,num):
        found=False
        for listpos, item in enumerate(liste):
            epar=config.EllipPar()
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
            epar=config.EllipPar()
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
            linepar=config.LinePar()
            linepar=list[listpos]
            posiblenum.remove(linepar.Num)
        return posiblenum[0]
    def OnClose(self,event):
        #print 'closing TrackWin'
        self.parentendpipe.send('Exit')
        for item in self.childs:
            item.OnClose(True)
        self.Destroy()
        
##
class ProcessPicThread(multiprocessing.Process):
    """Background Worker Thread Class."""

    def __init__(self, pipeend, pipetoplot, piclistqueue,resultqueuetrack, resultqueuedata, num=0):
        """Init Worker Thread Class."""
        multiprocessing.Process.__init__(self)
        self.pipeend=pipeend
        self.pipetoplot=pipetoplot
        self.queue=piclistqueue
        self.bmpqueue=resultqueuetrack
        self.out_queue2=resultqueuedata

        self.recordstream=False
        self.capturing=False

        self.lasttime=0
        self.framecount=0
        self.actframecount=0

        self.seachrectfactor=15
         
        self.num=num
        self.elliplist=list()
        self.connectlist=list()
        self.intrinsic, self.distortion=None,None
        self.calibrated=False
        self.calibrate=False
        self.obj_points = []
        self.img_points = []

        self.videofilename=''
        self.videofilepart=1
        self.daemon=True


        #chessbordprops
        self.calpicnum=30 #Number of calpics
        self.chesssize=(9,7) # with,height,
        self.squaresize=18  # in mm

        

        self.start()

        # start the thread
    def run(self):
        while True:
            self.newelliplist=list()
            self.newconnectlist=list()


            #polling pipes
            
            if self.pipeend.poll():
                #self.newellip,self.pickall,self.rightdown,self.seachrectfactor,self.calibrate=self.pipeend.recv()
                msg=self.pipeend.recv()
                #print msg
                if msg[0]=='New mark':
                    self.newellip=msg[1]
                    #try to find a new ellip
                    if self.newellip!=None:
                        #check if in already found ellip
                        isin,num=self.PosInFoundEllip(self.newellip,self.elliplist)
                        if not isin:
                            #print 'pick ellip'
                            ellip=self.PickEllip(self.raw,self.newellip[0],self.newellip[1],self.elliplist)    
                            if not ellip==None:
                                self.elliplist.append(ellip)
                                #print 'new ellip found'
                                self.pipeend.send('New Mark found!')
                            self.newellip=None
                if msg[0]=='New connection':
                    #make a new connection
                    # format ('New connection',(False/True,(P1),(P2)))
                    if not msg[1][0] and msg[1][1]!=(None,None) and msg[1][2]!=(None,None):
                        #print msg
                        newcon=config.LinePar()
                        isin, num=self.PosInFoundEllip(msg[1][1],self.elliplist)
                        if isin:
                            newcon.Pt1=num
                        else:
                            newcon.Pt1=None
                        isin, num=self.PosInFoundEllip(msg[1][2],self.elliplist)
                        if isin:
                            newcon.Pt2=num
                        else:
                            newcon.Pt2=None

                        if newcon.Pt1!=newcon.Pt2 and newcon.Pt1!=None and newcon.Pt1!=None:
                         
                            newcon.Num=self.NumConnect(self.connectlist)
                            #print "connection appended"
                            self.pipeend.send('New connection in place!')
                            self.connectlist.append(newcon)

                        if newcon.Pt1==newcon.Pt2 and newcon.Pt1!=None and newcon.Pt1!=None:
                            
                            epar=self.GetEllipWithNum(self.elliplist,newcon.Pt1)
                            self.elliplist.remove(epar)
                            #print 'ellip removed'
                            self.pipeend.send('Mark removed!')
                if msg[0]=='calibrate':
                    #print 'calibrate'
                    self.calibrate=True
                    continue

                    
                if msg[0]=='pick all marks':
                    self.PickAll(self.raw)

                if msg[0]=='searchrectfactor':
                    self.seachrectfactor=msg[1]
                if msg[0]=='new calibration':
                    self.intrinsic, self.distortion=msg[1]
                    self.calibrated=True
                    self.mapx,self.mapy=cv2.initUndistortRectifyMap(self.intrinsic, self.distortion,None,self.intrinsic,(self.raw.shape[1], self.raw.shape[0]),cv2.CV_32FC1)
                    self.pipeend.send('Successfully loaded calibration!')
                if msg=='Enable Record':
                    self.recordstream=True
                if msg=='Disable Record':
                    self.recordstream=False
                if msg=='Exit':
                    #print 'killing process'
                    break
                
            if self.pipetoplot.poll():
                msg=self.pipetoplot.recv()
                #print msg
                if msg[0]=='Capturing':
                    fourcc= cv2.cv.CV_FOURCC('D','I','B',' ')
                    name=msg[1].split('.',1)[0]
                    #print name
                    self.videofilename=name
                    self.videowriter=cv2.VideoWriter(self.videofilename+'.avi',fourcc,30,(self.raw.shape[1],self.raw.shape[0]),isColor=False)
                    self.capturing=True
                if msg=='Stopped Capturing':
                    self.videowriter.release()
                    self.videofilepart=1
                    #print 'Stopped'
                    del self.videowriter
                    self.capturing=False


            #try getting images
            
            try:
                imagetuple=self.queue.get(False)
            except Queue.Empty:
                #print 'no pic: i continue'
                continue
            self.timestamp=imagetuple[0]
            self.raw=numpy.copy(imagetuple[1])

            temp=numpy.copy(self.raw)
            self.image=cv2.cvtColor(self.raw,cv2.COLOR_GRAY2RGB)

            self.acttime=clock()
            if self.acttime-self.lasttime<1:
                self.framecount+=1
            else:
                # full second
                self.actframecount=self.framecount
                self.framecount=1
                self.lasttime=self.acttime

            if self.calibrated:
                #print 'remap'
                self.raw=cv2.remap(temp,self.mapx,self.mapy,cv2.INTER_LINEAR)
                #self.raw=cv2.undistort(temp,self.intrinsic,self.distortion)
            else:
                self.raw=temp
                    
                
                        
            if self.calibrate:
                    pattern_points = numpy.zeros( (numpy.prod(self.chesssize), 3), numpy.float32)
                    pattern_points[:,:2] = numpy.indices(self.chesssize).T.reshape(-1, 2)
                    pattern_points *= self.squaresize

                    #print len(self.obj_points)
                    if len(self.obj_points)<self.calpicnum:
                        #process pics

                        #print 'try to find patern'
                        found, corners=cv2.findChessboardCorners(self.raw, self.chesssize,flags=cv2.CALIB_CB_ADAPTIVE_THRESH+cv2.CALIB_CB_NORMALIZE_IMAGE)

                        if found!=0:
                            #Get subpixel accuracy on those corners
                            cv2.cornerSubPix(self.raw,corners,(11,11),(-1,-1),(cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_COUNT, 30, 0.1))
                            cv2.drawChessboardCorners(self.image, self.chesssize, corners, found)
                            
                            self.img_points.append(corners.reshape(-1, 2))              
                            self.obj_points.append(pattern_points)
                            
                    else:
                        #datacollection complete
                        rms1, intrinsic, distortion, rvecs, tvecs = cv2.calibrateCamera(self.obj_points, self.img_points, (temp.shape[1], temp.shape[0]),criteria=(cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_COUNT, 300, 1E-6),flags=cv2.CALIB_FIX_ASPECT_RATIO+cv2.CALIB_ZERO_TANGENT_DIST)

                        #print 'save to file'
                        filecalib=open("Calibration.cal",'w')
                        pickle.dump((intrinsic,distortion,(self.squaresize,'mm') ),filecalib)
                        filecalib.close()

                        
                        self.mapx,self.mapy=cv2.initUndistortRectifyMap(intrinsic,distortion,None,intrinsic,(self.raw.shape[1], self.raw.shape[0]),cv2.CV_32FC1)
                        self.calibrated=True
                        self.calibrate=False
                        self.obj_points = []
                        self.img_points = []
                        self.pipeend.send('Successfully calibrated!')
                        
            #print self.newellip,self.pickall,self.rightdown,self.seachrectfactor
            if self.calibrated:
                if self.intrinsic==None and self.distortion==None:
                    filecalib=open('Calibration.cal','r')
                    intrinsic,distortion,distanceunit=pickle.load(filecalib)
                    filecalib.close()
                    self.mapx,self.mapy=cv2.initUndistortRectifyMap(intrinsic,distortion,None,intrinsic,(self.raw.shape[1], self.raw.shape[0]),cv2.CV_32FC1)
            else:
                self.intrinsic, self.distortion=None,None
                self.mapx,self.mapy=None,None


            #print len(self.raw)

            #track all existing ellips
            #print self.elliplist
            if len(self.elliplist)>0:
                self.newelliplist, self.newconnectlist, self.image=self.ProcessImage(self.raw,self.image, self.elliplist, self.connectlist)
                #update elements
                self.elliplist, self.connectlist=self.newelliplist, self.newconnectlist

            #cature videostream
            if self.recordstream and self.capturing:
                #check filesize
                if self.videofilepart==1:
                    filesize=os.path.getsize(self.videofilename+'.avi')
                else:
                    filesize=os.path.getsize(self.videofilename+'part'+str(self.videofilepart)+'.avi')
                    
                if filesize>=4294967296: #4GB
                    self.videowriter.release()
                    self.videofilepart+=1
                    self.videowriter=cv2.VideoWriter(self.videofilename+'part'+str(self.videofilepart)+'.avi',fourcc,30,(self.raw.shape[1],self.raw.shape[0]),isColor=False)
                    
                self.videowriter.write(self.raw)
                print 'recording'
                #print self.videowriter

            #show in frame - put it to paintqueue
            try:
                self.bmpqueue.put((self.timestamp,self.image, self.newelliplist, self.newconnectlist,self.actframecount),False)
            except Queue.Full:
                ##print 'trackresultqueue1 full'
                pass

            #show in winplot - put it to winplotqueue
            try:
                self.out_queue2.put((self.timestamp,self.image, self.newelliplist, self.newconnectlist),False)
            except Queue.Full:
                ##print 'trackresultqueue3 full'
                pass


    def ProcessImage(self, grayimage, rgbimage, ellipses,connections):
        #track ellipses
        ellipses=self.TrackEllip(grayimage,ellipses)
        #print 'remove lost connections'
        for i in range(len(connections),0,-1): 
            linepar=config.LinePar()
            linepar=connections[i-1]
            if self.GetEllipWithNum(ellipses,linepar.Pt1)==None or self.GetEllipWithNum(ellipses,linepar.Pt2)==None:
                #print "connection removed"
                connections.remove(linepar)
        return ellipses, connections, rgbimage
    def PickEllip(self,image,posx,posy,elliplist):
        found=0
        firstsearchrectsize=5
        searchrectsize=5
        #print 'create memstorage'
        
        while found <1:
            #searchrectsize=int(searchrectsize+searchrectsize/10)
            searchrectsize=int(searchrectsize+firstsearchrectsize)
            #print searchrectsize
            
            searchrectr=(posx-searchrectsize,posy-searchrectsize,searchrectsize*2,searchrectsize*2)
            #print searchrectr

            if searchrectsize*2>image.shape[1]:
                break
            #print 'get search contour image'
            rectimage,searchrect=self.GetSearchCounturImage(image,searchrectr)

            
            #print 'search image created'
            if rectimage==None:
                continue
            #pixout,pixin=self.InOutVal(rectimage)
            if cv2.countNonZero(rectimage)<=10:
                continue

            contours,hier=cv2.findContours (rectimage,cv2.RETR_LIST,cv2.CHAIN_APPROX_TC89_KCOS)
            found=0
            #print 'find contours'
            
            for contour in contours:
                #print contour
                if len(contour) >= 6:
                    if cv2.contourArea(contour)<=(rectimage.shape[1]*rectimage.shape[0]/50)or cv2.contourArea(contour)>(rectimage.shape[1]*rectimage.shape[0]/2):
                        continue
                    #print 'process contours' 
                    # Fits ellipse to current contour.
                    EllipParnew=self.FitEllipOnContour(contour)

                    #define Number
                    EllipParnew.Num=self.NumEllip(elliplist)
                    #korrekt pos and size to global
                    EllipParnew.MidPos=EllipParnew.MidPos[0]/rectimage.shape[1]*searchrect[2]+searchrect[0],EllipParnew.MidPos[1]/rectimage.shape[0]*searchrect[3]+searchrect[1]
                    EllipParnew.Size= EllipParnew.Size[0]/rectimage.shape[1]*searchrect[2]/2,EllipParnew.Size[1]/rectimage.shape[0]*searchrect[3]/2

                    #EllipParnew.Angle=-EllipParnew.Angle
                    EllipParnew.mov=0,0

                    b,h=self.GetAABBEllip(EllipParnew)

                    left=int(EllipParnew.MidPos[0]-b/2)
                    low=int(EllipParnew.MidPos[1]-h/2)
                    

                    if left>searchrect[0] and low>searchrect[1] and b<searchrect[2] and h<searchrect[3] and b>searchrect[2]/3 and h>searchrect[3]/3:
                        found=1
                        #print 'found ellip'
                        #print left,searchrect[0],low,searchrect[1],b,searchrect[2],h,searchrect[3],b,searchrect[2]/3,h,searchrect[3]/3
                        cv2.rectangle(self.image,(searchrect[0],searchrect[1]),(int(searchrect[0]+searchrect[2]),int(searchrect[1]+searchrect[3])),(50,50,255),1)
                        EllipParnew.searchrect=searchrect
                        break
            
            
            
        if found>=1:
            #print 'found ellip'
            return EllipParnew
        else:
            return None


    def PickAll(self,gray):
        try:
            circles=cv2.HoughCircles(gray, cv2.CV_HOUGH_GRADIENT,2,int(gray.shape[1]/20), 192, 50)
            print circles
        except:
            #print 'null pointer bla bla'
            return
##        for i in range(0,storage.rows):
##                row=list()
##                for j in range(0,storage.cols):
##                    ellip=self.PickEllip(self.raw,int(storage[i,j][0]),int(storage[i,j][1]),self.elliplist)    
##                    if not ellip==None:
##                        #print 'is regular ellip'
##                        self.elliplist.append(ellip)
        
        
    def TrackEllip(self,image,ellipses):
        
        elliplistnew=list()
        #print len(ellipses)
        for listpos, item in enumerate(ellipses):
            #print 'track ellip'
            triedtorescue=False
            ellip=config.EllipPar()
            
            ellip=ellipses[listpos]
            
            
            b,h=self.GetAABBEllip(ellip)
            #print b,h

            b,h=int(b*self.seachrectfactor/10),int(h*self.seachrectfactor/10)
            #if b<15:
            #    b=15
            #if h<15:
            #    h=15

            #with movement correction
            searchrecttr = (int(ellip.MidPos[0]+int(ellip.mov[0])-b/2),int(ellip.MidPos[1]+int(ellip.mov[1])-h/2),int(b),int(h))
            #print searchrecttr
            #print 'finish init %(listpos)d in frame %(framenum)d ' % vars()
            #print len(image)
            rectimage, searchrect=self.GetSearchCounturImage(image,searchrecttr)
            #print searchrect,searchrecttr
            #print rectimage, searchrect

            if rectimage==None:
                continue


            contours,hier=cv2.findContours (rectimage, cv2.RETR_LIST,cv2.CHAIN_APPROX_TC89_KCOS)
            found=0
            for contour in contours:
                #print contour
                #print len(contour)
                if len(contour) >= 6 :
                    if cv2.contourArea(contour)<=(rectimage.shape[1]*rectimage.shape[0]/50)or cv2.contourArea(contour)>(rectimage.shape[1]*rectimage.shape[0]/2):
                        #print 'kicked'
                        continue
                    
                    # Fits ellipse to current contour.
                    EllipParnew=self.FitEllipOnContour(contour)

                    
                    
                    #define Number
                    EllipParnew.Num=ellip.Num
                    #korrekt pos and size to global
                    EllipParnew.MidPos=EllipParnew.MidPos[0]/rectimage.shape[1]*searchrect[2]+searchrect[0],EllipParnew.MidPos[1]/rectimage.shape[0]*searchrect[3]+searchrect[1]
                    EllipParnew.Size= EllipParnew.Size[0]/rectimage.shape[1]*searchrect[2]/2,EllipParnew.Size[1]/rectimage.shape[0]*searchrect[3]/2

                    
                    #EllipParnew.Angle=-EllipParnew.Angle
                    EllipParnew.mov=EllipParnew.MidPos[0]-ellip.MidPos[0],EllipParnew.MidPos[1]-ellip.MidPos[1]

                    b,h=self.GetAABBEllip(EllipParnew)

                    left=int(EllipParnew.MidPos[0]-b/2)
                    low=int(EllipParnew.MidPos[1]-h/2)
               
                    #print left,searchrect[0],low,searchrect[1],b,searchrect[2],h,searchrect[3],b,searchrect[2]/3,h,searchrect[3]/3
                    if left>searchrect[0] and low>searchrect[1] and b<searchrect[2] and h<searchrect[3] and b>searchrect[2]/5 and h>searchrect[3]/5:
                        found=1
                        cv2.rectangle(self.image,(searchrecttr[0],searchrecttr[1]),(int(searchrecttr[0]+searchrecttr[2]),int(searchrecttr[1]+searchrecttr[3])),(0,0,255),1)
                        #print found
                        EllipParnew.searchrect=searchrect
                        break            

            if found>=1:
                #print 'add found %(listpos)d ' % vars()
                elliplistnew.append(EllipParnew)            
            else:
                ##dont try to rescue we are live
                #print triedtorescue
                #triedtorescue=True
                if not triedtorescue:
                    #print 'try to rescue'
                    
                    triedtorescue=True
                    rectlist=self.RescueList(searchrecttr,ellip.mov)
                    for rect in rectlist:

                        rectimage, searchrect=self.GetSearchCounturImage(image,rect)
                        if rectimage==None:
                            continue

                        if cv2.countNonZero(rectimage)<=10:
                            continue
                        
                        contours,hier=cv2.findContours (rectimage, cv2.RETR_LIST,cv2.CHAIN_APPROX_TC89_KCOS)
                        found=0
                        for contour in contours:
                        #print contour
                            if len(contour) >= 6:
                                if cv2.contourArea(contour)<=(rectimage.shape[1]*rectimage.shape[0]/50)or cv2.contourArea(contour)>(rectimage.shape[1]*rectimage.shape[0]/2):
                                    continue
                                
                                # Fits ellipse to current contour.
                                EllipParnew=self.FitEllipOnContour(contour)

                                #define Number
                                EllipParnew.Num=ellip.Num
                                #korrekt pos and size to global
                                EllipParnew.MidPos=EllipParnew.MidPos[0]/rectimage.shape[1]*searchrect[2]+searchrect[0],EllipParnew.MidPos[1]/rectimage.shape[0]*searchrect[3]+searchrect[1]
                                EllipParnew.Size= EllipParnew.Size[0]/rectimage.shape[1]*searchrect[2]/2,EllipParnew.Size[1]/rectimage.shape[0]*searchrect[3]/2
                                
                                
                                #EllipParnew.Angle=-EllipParnew.Angle
                                EllipParnew.mov=EllipParnew.MidPos[0]-ellip.MidPos[0],EllipParnew.MidPos[1]-ellip.MidPos[1]

                                b,h=self.GetAABBEllip(EllipParnew)

                                left=int(EllipParnew.MidPos[0]-b/2)
                                low=int(EllipParnew.MidPos[1]-h/2)
                                

                                if left>searchrect[0] and low>searchrect[1] and b<searchrect[2] and h<searchrect[3] and b>searchrect[2]/5 and h>searchrect[3]/5:
                                    cv2.rectangle(self.image,(searchrecttr[0],searchrecttr[1]),(int(searchrecttr[0]+searchrecttr[2]),int(searchrecttr[1]+searchrecttr[3])),(0,255,0),1)
                                    found=1
                                    EllipParnew.searchrect=searchrect
                                    break
                            
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
            epar=config.EllipPar()
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
            epar=config.EllipPar()
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
        box = cv2.fitEllipse(contour)
        #print box
        epar=config.EllipPar()
        epar.MidPos=box[0]
        epar.Size=box[1]
        epar.Angle=box[2]
        return epar
    def RescueList(self,searchrect,mov):
        #make searchrect bigger and move around
        rectlist=list()
        factors=range(1,5)
        bfactors=range(1,5)

        for factor in factors:
            teilen=12
            #teilen=8
            for bfactor in bfactors:

                radius=(searchrect[2]+searchrect[3])/20.0*bfactor
                #radius=(math.sqrt(mov[0]**2+mov[1]**2))/5.0*bfactor
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
        if angle==0:
            x=a
            y=b
        else:
            t=math.atan(-b*math.tan(angle)/a)
            x=abs(a*math.cos(t)*math.cos(angle)-b*math.sin(t)*math.sin(angle))
            t=math.atan(a*(1/math.tan(angle))/b)
            y=abs(b*math.sin(t)*math.cos(angle)+a*math.cos(t)*math.sin(angle))
        #print ellip.Size[0],ellip.Size[1],y,x, angle
      
        return y,x

    def GetSearchCounturImage(self,image,rect):
        #check subrect is in image
        if not self.CheckSubRect(image,rect):
            return None,rect
        else:
            #print 'copy subimage'

            temp=image[rect[1]:(rect[1]+rect[3]),rect[0]:(rect[0]+rect[2])]
            pyrimage=cv2.pyrUp(temp)
            temp=cv2.pyrDown(pyrimage)
            temp=cv2.medianBlur(temp,3)
            thresimg=cv2.resize(temp,(temp.shape[1]*5,temp.shape[0]*5),interpolation=cv2.INTER_CUBIC)

            ret,thresimg=cv2.threshold(thresimg,0,255,cv2.THRESH_BINARY+cv2.THRESH_OTSU)
            #pixin, pixout=self.InOutVal(thresimg)
            #ret,thresimg=cv2.threshold(thresimg,int((pixin+pixout)/2),255,cv2.THRESH_BINARY)
            #print 'return subimage'
            return thresimg, rect
    def InOutVal(self,img):

        pixout=0
        pixin=0
        width=img.shape[1]
        height=img.shape[0]
        
        pixout=(img[0,0]+img[0,1]+img[1,0]
                 +img[0,width-1]+img[1,width-1]+img[0,width-2]
                 +img[height-1,0]+img[height-2,0]+img[height-1,1]
                 +img[height-1,width-1]+img[height-2,width-1]+img[height-1,width-2])
        pixout=pixout/12

        
        pixin=img[int(height/2),int(width/2)]+img[int(height/2)+1,int(width/2)]+img[int(height/2),int(width/2)+1]+img[int(height/2)+1,int(width/2)+1]
        pixin=pixin/4
        #print pixout,pixin
        return pixout,pixin
    def NumEllip(self, elliplist):
        posiblenum=range(len(elliplist)+10)
        for listpos, item in enumerate(elliplist):
            ellipPar=config.EllipPar()
            ellipPar=elliplist[listpos]
            posiblenum.remove(ellipPar.Num)
        return posiblenum[0]
    def NumConnect(self,list):
        posiblenum=range(len(list)+10)
        for listpos, item in enumerate(list):
            linepar=config.LinePar()
            linepar=list[listpos]
            posiblenum.remove(linepar.Num)
        return posiblenum[0]
    def CheckSubRect(self,image,rect):
        #print rect[2],rect[3],image.shape[0],image.shape[1]
        if (rect[0]+rect[2])<=image.shape[1] and (rect[1]+rect[3])<=image.shape[0] and rect[0]>=0 and rect[1]>=0 and rect[2]>=20 and rect[3]>=20:
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
            if (rect[0]+rect[2])>image.shape[1]:
                width=image.shape[1]-rect[0]
                
            else:
                width=rect[2]    
            if (rect[1]+rect[3])>image.shape[0]:
                height=image.shape[0]-rect[1]
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
            if (rect[0]+rect[2])>image.shape[1]:
                orx=image.shape[1]-rect[2]
            if (rect[1]+rect[3])>image.shape[0]:
                ory=image.shape[0]-rect[3]  
            rect=(orx,ory,rect[2],rect[3])
        return rect

class WinTrackBmpPaintThread(threading.Thread):
    """Background Worker Thread Class."""

    def __init__(self, parent,bmppaintqueue,panel,num=0):
        """Init Worker Thread Class."""
        threading.Thread.__init__(self)
        self.parent=parent
        self.bmppaintqueue=bmppaintqueue
        self.panel=panel
        self.num=num
        
        self.ZoomImage=numpy.zeros((100,100,3),numpy.uint8)
        self.ScaledImg=numpy.zeros((100,100,3),numpy.uint8)
        
        self.setDaemon(True)
        self.start()
        # start the thread
    def run(self):
        #print "Aquirethread started "
        while True:
            self.timestamp,image, ellipses, connections, framecount=self.bmppaintqueue.get()
            #print framecount
            self.parent.SetStatusText('FPS: '+str(framecount),1)
            #print "WinTrackBmphread got task"

            #update WinTrack data
            self.parent.imagetuple,  self.parent.elliplist, self.parent.connectlist, self.timestamp= image, ellipses, connections, self.timestamp


            
            zoomrect=self.parent.zoomrect
            zoomval=self.parent.zoomval
            if zoomrect==None or zoomval==0:
                zoomrect=(0,0,image.shape[1],image.shape[0])
                self.parent.zoomrect=zoomrect
            
            dc=wx.ClientDC(self.parent.panel)
            rightdown=self.parent.rightdown

            self.Overlay=numpy.copy(image)

            #draw all marks

            #first ellipses

            for listpos, item in enumerate(ellipses):
                ellipPar=config.EllipPar()
                ellipPar=ellipses[listpos]
                #determine thickness of mark
                thickness=(int((ellipPar.Size[0]+ellipPar.Size[1])/20))
                
                self.DrawEllipMark(self.Overlay,ellipPar,255,0,0,thickness)

            #second connections

            for listpos, item in enumerate(connections):
                
                linepar=config.LinePar()
                linepar=connections[listpos]
                epar1=self.GetEllipWithNum(ellipses,linepar.Pt1)
                epar2=self.GetEllipWithNum(ellipses,linepar.Pt2)
                
                cv2.line(self.Overlay,(int(epar1.MidPos[0]),int(epar1.MidPos[1])),(int(epar2.MidPos[0]),int(epar2.MidPos[1])),(0,0,255),1)
                                        
                rx,ry=abs(epar1.MidPos[0]-epar2.MidPos[0]),abs(epar1.MidPos[1]-epar2.MidPos[1])
                if epar1.MidPos[0]<epar2.MidPos[0]:
                    posx=int(epar1.MidPos[0]+rx/2)
                else:
                    posx=int(epar2.MidPos[0]+rx/2)
                if epar1.MidPos[1]<epar2.MidPos[1]:
                    posy=int(epar1.MidPos[1]+ry/2)
                else:
                    posy=int(epar2.MidPos[1]+ry/2)

                cv2.putText(self.Overlay,'C%d'%linepar.Num,(posx,posy),cv2.FONT_HERSHEY_COMPLEX,1,(0,0,255),1)
  
            #connection in build
            if rightdown[0]:
                cv2.line(self.Overlay,rightdown[1],rightdown[2],(0,255,0),1)

            #overlay mask
            opacity=0.7
            self.Overlay=cv2.addWeighted(self.Overlay,opacity,image,1-opacity,0)

            panelwidth,panelheight=dc.GetSize()
            if (panelwidth <=0) or (panelheight <=0):
                continue

            #reset Zoom when image.size changed
            
            if (zoomrect[0]+zoomrect[2])>self.Overlay.shape[1] or (zoomrect[1]+zoomrect[3])>self.Overlay.shape[0]:
                zoomrect=(0,0,self.Overlay.shape[1] ,self.Overlay.shape[0])
            if (zoomrect[3],zoomrect[2])!=self.Overlay.shape:
                self.ZoomImage=self.Overlay[zoomrect[1]:(zoomrect[1]+zoomrect[3]),zoomrect[0]:(zoomrect[0]+zoomrect[2])]
                self.ScaledImg=cv2.resize(self.ZoomImage,( panelwidth,panelheight))
            else:
                self.ScaledImg=cv2.resize(self.Overlay,( panelwidth,panelheight))

            #numpy array to bitmap
            wximage=wx.EmptyImage(panelwidth,panelheight)
            wximage.SetData( self.ScaledImg.tostring())
            self.bitmap=wximage.ConvertToBitmap()

            
            dc.DrawBitmap(self.bitmap, 0, 0, False)
                
        self.bmppaintqueue.task_done()
        
    def GetAABBEllip(self,ellip):
        angle=-math.radians(ellip.Angle)
        if ellip.Size[0]<ellip.Size[1]:
            a=2*ellip.Size[1]
            b=2*ellip.Size[0]
        else:
            b=2*ellip.Size[1]
            a=2*ellip.Size[0]
        if angle==0:
            x=a
            y=b
        else:
            t=math.atan(-b*math.tan(angle)/a)
            x=abs(a*math.cos(t)*math.cos(angle)-b*math.sin(t)*math.sin(angle))
            t=math.atan(a*(1/math.tan(angle))/b)
            y=abs(b*math.sin(t)*math.cos(angle)+a*math.cos(t)*math.sin(angle))
        #print x,y, angle
        return y,x
            
    def DrawEllipMark(self,image,epar,color1,color2,color3,thickness):
        b,h=self.GetAABBEllip(epar)
        b,h=int(b*1.5),int(h*1.5)
        if b<20:
            b=20
        if h<20:
            h=20

        posx=int(epar.MidPos[0]-b/2)
        posy=int(epar.MidPos[1]-h/2)
        cv2.rectangle(image,(posx,posy),(int(posx+b),int(posy+h)),(color1,color2,color3),thickness)
        cv2.ellipse(image,(int(epar.MidPos[0]),int(epar.MidPos[1])), (int(epar.Size[0]),int(epar.Size[1])),epar.Angle,0,360,(color1,color2,color3),thickness)
        cv2.line(image,(int(epar.MidPos[0]-b/2),int(epar.MidPos[1])),(int(epar.MidPos[0]+b/2),int(epar.MidPos[1])),(color1,color2,color3),thickness)
        cv2.line(image,(int(epar.MidPos[0]),int(epar.MidPos[1]-h/2)),(int(epar.MidPos[0]),int(epar.MidPos[1]+h/2)),(color1,color2,color3),thickness)
        cv2.putText(image,'%d'%epar.Num,(int(posx+b),int(posy+h)),cv2.FONT_HERSHEY_COMPLEX,1,(color1,color2,color3),thickness)

        #add movement vectors

        if epar.mov[0]!=0 and epar.mov[1]!=0:

            #start and endpoint
            
            P1=epar.MidPos[0],epar.MidPos[1]
            P2=epar.MidPos[0]-epar.mov[0],epar.MidPos[1]-epar.mov[1]

            angle=math.atan2((P1[1]-P2[1]),(P1[0]-P2[0]))
            lenght=math.sqrt((P1[0]-P2[0])**2+(P1[1]-P2[1])**2)

            #enlongen vector

            P2=P1[0]-10*lenght*math.cos(angle),P1[1]-10*lenght*math.sin(angle)
            P5=P1[0]-thickness*math.cos(angle),P1[1]-thickness*math.sin(angle)

            #draw main line

            cv2.line(image,(int(P5[0]),int(P5[1])),(int(P2[0]),int(P2[1])),(color1,255,color3),thickness)

      
    def GetEllipWithNum(self,liste,num):
        found=False
        for listpos, item in enumerate(liste):
            epar=config.EllipPar()
            epar=liste[listpos]
            if epar.Num==num:
                found=True
                break
        if found:
            return epar
        else:
            return None

class CalibData:
    def __init__(self):
        self.intrinsic=None
        self.distortion=None
        self.distanceunit=None

