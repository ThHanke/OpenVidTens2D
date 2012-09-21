# -*- coding: cp1252 -*-
import wx,cv
import threading


import math
import pickle
import Queue

import multiprocessing

#import globals
import config

from time import sleep
from time import clock

ID_CCAL=wx.NewId()
ID_CCALL=wx.NewId()
ID_CCALS=wx.NewId()
ID_PICKALL=wx.NewId()
ID_SRFACTOR=wx.NewId()

def contour_iterator(contour):
    while contour:
        yield contour
        contour = contour.h_next()

class LiveTrackWin(wx.Frame):
    def __init__(self,source):
        self.winsource=source
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

        self.panel.Bind(wx.EVT_MOUSEWHEEL, self.Mousewheel)
        self.panel.Bind(wx.EVT_ENTER_WINDOW,self.MouseInWindow)
        self.panel.Bind(wx.EVT_LEAVE_WINDOW,self.MouseOutWindow)
        self.panel.Bind(wx.EVT_LEFT_DOWN,self.MouseLeftClick)
        self.panel.Bind(wx.EVT_RIGHT_DOWN,self.MouseRightClick)
        self.panel.Bind(wx.EVT_MOTION,self.MouseMove)
        self.panel.Bind(wx.EVT_RIGHT_UP,self.MouseRightClick)

        #spwan queue

        self.resultqueueTrack=multiprocessing.Queue(1)
        self.resultqueuePlot=multiprocessing.Queue(1)

        self.parentendpipe,self.childendpipe=multiprocessing.Pipe()
        
        #StartVariablen
        self.zoomval=0
        aspect=1.0

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

        t=ProcessPicThread(self.childendpipe,self.winsource.totrackqueue,self.resultqueueTrack,self.resultqueuePlot,0)
        #init variables in backgroundprocess
        self.SendStatustoBackgroundProcess()

        t=WinTrackBmpPaintThread(self,self.resultqueueTrack)

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
        
        return Menubar   
    def Replot(self):
        #only used in fileinterface
        try:
            self.resultqueueTrack.put((self.timestamp,self.imagetuple, self.elliplist, self.connectlist,0),False)
        except Queue.Full:
            pass
    def SendStatustoBackgroundProcess(self):
        self.parentendpipe.send((self.newellip,self.PickAll,self.rightdown,self.seachrectfactor))
    def Mousewheel(self,event):
        if self.mousein:
            pt = event.GetPosition()
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
                width=int(float(self.imagetuple[1])/float(self.zoomval))
                height=int(float(self.imagetuple[2])/float(self.zoomval))
                orx=pos[0]-int(float(width)/2)
                ory=pos[1]-int(float(height)/2)
                self.zoomrect=(orx,ory,width,height)
                if not self.CheckSubRect(self.imagetuple,self.zoomrect):
                    self.zoomrect=self.GetProperSubRect(self.imagetuple,self.zoomrect,True)
            else:
                self.zoomrect=(0,0,self.imagetuple[1],self.imagetuple[2])
            if self.winsource.isfileinterface:
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
            self.newellip=self.Panel2ImageKoord(self.panelwidth,self.panelheight,self.zoomrect,pt)
            self.SendStatustoBackgroundProcess()
            self.newellip=None
            
            if self.winsource.isfileinterface:
                #print 'onSlider'
                self.winsource.OnSlider(True)            
    def MouseRightClick(self,event):
        if event.RightDown()and self.mousein:
            pt = event.GetPosition()
            pos=self.Panel2ImageKoord(self.panelwidth,self.panelheight,self.zoomrect,pt)
            #in ellip?
            self.rightdown=True, pos, pos
            #print self.rightdown
        if event.RightUp()and self.mousein:
            pt = event.GetPosition()
            #get mouse pic koords
            pos=self.Panel2ImageKoord(self.panelwidth,self.panelheight,self.zoomrect,pt)
            self.rightdown=False,self.rightdown[1],pos
            #send to background process
            self.SendStatustoBackgroundProcess()
            #print self.rightdown
            if self.winsource.isfileinterface:
                #print 'mouse right klicked'
                self.winsource.OnSlider(True)
    def MouseMove(self,event):
        if self.mousein:
            if self.parentendpipe.poll():
                #print 'polled and not empty'
                (self.timestamp, self.elliplist, self.connectlist)=self.parentendpipe.recv()
                #print 'update recevied'
            if event.RightIsDown()and self.rightdown[0]:
                pt = event.GetPosition()
                #get mouse pic koords
                self.rightdown=True,self.rightdown[1],self.Panel2ImageKoord(self.panelwidth,self.panelheight,self.zoomrect,pt)
                #print self.rightdown
                if self.winsource.isfileinterface:
                    self.Replot()
    def CameraCalibration(self,event):
        filters = 'Image files (*.gif;*.png;*.jpg;*.bmp)|*.gif;*.png;*.jpg;*.bmp' 
        
        n_boards=6 #Number of boards
        board_w=7
        board_h=7
        board_n = board_w * board_h
        board_sz =( board_w, board_h )

        image_points = cv.CreateMat(n_boards*board_n,2,cv.CV_32FC1)
        objekt_points = cv.CreateMat(n_boards*board_n,3,cv.CV_32FC1)
        point_counts = cv.CreateMat(n_boards,1,cv.CV_32SC1)
        intrinsic_matrix = cv.CreateMat(3,3,cv.CV_32FC1)
        distortion_coeffs = cv.CreateMat(5,1,cv.CV_32FC1)
        detectsuccsess=0
        needcalibpic = True
        #cv.NamedWindow('Calibration',0)
        #get screen resolution
        #screen=wx.Display().GetGeometry()
        #cv.MoveWindow('Calibration',int(screen[2]/3*2),0)
        #cv.ResizeWindow('Calibration',screen[2]-int(screen[2]/3*2)-12,int((screen[2]-int(screen[2]/3*2))*self.image.height/self.image.width))

        while needcalibpic:
            answer=wx.MessageBox('Put Chessboard Pattern ( %dx%d) into %d. Position' %(board_w,board_h,detectsuccsess+1), 'Calibration Procedure',style=wx.OK|wx.CANCEL|wx.ICON_EXCLAMATION)
            if answer==wx.OK:
                temp = cv.CreateImageHeader((self.imagetuple[1],self.imagetuple[2]),8,3)
                raw = cv.CreateImage((self.imagetuple[1],self.imagetuple[2]),8,1)
                cv.SetData(temp, self.imagetuple[0])
                cv.CvtColor(temp,raw,cv.CV_RGB2GRAY)
                paternsize=(board_w,board_h)
                #print 'try to find patern'
                found, corners=cv.FindChessboardCorners(raw, paternsize, cv.CV_CALIB_CB_ADAPTIVE_THRESH)
                #print found, corners
                ##break here
                #needcalibpic=False
                if found==0:
                    self.SetStatusText('Chessboard Pattern could not be detected')
                    continue
                else:
                    #Get subpixel accuracy on those corners
                    cv.FindCornerSubPix( raw, corners, ( 11, 11 ),( -1, -1 ), ( cv.CV_TERMCRIT_EPS+cv.CV_TERMCRIT_ITER, 30, 0.1))
                    cv.DrawChessboardCorners(temp, paternsize, corners, 1)
                    i= detectsuccsess*board_n
                    j= 0
                    stop=False
                    while not stop:
                        image_points[i,0] = corners[j][0]
                        image_points[i,1] = corners[j][1]
                        objekt_points[i,0] = j/board_w
                        objekt_points[i,1] = j%board_w
                        objekt_points[i,2] = 0.0
                        i+=1
                        j+=1
                        if j>=board_n:
                            stop=True
                    point_counts[detectsuccsess,0]=board_n
                    detectsuccsess+=1
                    self.SetStatusText('%.0f Chessboard Pattern successfully detected' % detectsuccsess)
                    #cv.ShowImage('Calibration',self.image)
                    self.Replot()
                    if detectsuccsess>=n_boards:
                        needcalibpic = False
                #self.displayImage(self.image,self.imagepanel)
            else:
                needcalibpic = False
                detectsuccsess=0
                    
        if (detectsuccsess>0):
            image_points_new = cv.CreateMat(detectsuccsess*board_n,2,cv.CV_32FC1)
            objekt_points_new = cv.CreateMat(detectsuccsess*board_n,3,cv.CV_32FC1)
            point_counts_new = cv.CreateMat(detectsuccsess,1,cv.CV_32SC1)
            for ii in range(0,detectsuccsess):
                i= ii*board_n
                j= 0
                stop=False
                while not stop:
                    image_points_new[i,0] = image_points[i,0]
                    image_points_new[i,1] = image_points[i,1]
                    objekt_points_new[i,0] = objekt_points[i,0]
                    objekt_points_new[i,1] = objekt_points[i,1]
                    objekt_points_new[i,2] = objekt_points[i,2]
                    i+=1
                    j+=1
                    if j>=board_n:
                        stop=True
                point_counts_new[ii,0]=point_counts[ii,0]
            intrinsic_matrix[0,0] = 1.0
            intrinsic_matrix[1,1] = 1.0
            #calibrate camera
            self.CalibData.intrinsic=None
            self.CalibData.distortion=None
            rot  = cv.CreateMat(detectsuccsess,3,cv.CV_32FC1)
            trans= cv.CreateMat(detectsuccsess,3,cv.CV_32FC1)
            #self.CalibData.intrinsic, self.CalibData.distortion = cv.CalibrateCamera2( objekt_points_new,image_points_new, point_counts_new, cv.GetSize( self.cvdistimage ),intrinsic_matrix)
            cv.CalibrateCamera2( objekt_points_new,image_points_new, point_counts_new, cv.GetSize( temp ),intrinsic_matrix,distortion_coeffs,rot,trans,0)
            self.CalibData.intrinsic=intrinsic_matrix
            self.CalibData.distortion=distortion_coeffs
            self.SetStatusText('Camera Calibration successfull')
            self.calibrated=True
            cv.DestroyWindow('Calibration')
            #cv.cvSave( "Intrinsics2.xml", self.CalibData.intrinsic )
            #cv.cvSave( "Distortion2.xml", self.CalibData.distortion )
    def SaveCalibration(self,event):
        
        directory=config.ProgDir
        filename="Calibration.cal"
        dlg = wx.FileDialog(self, "Save camera calibration data as", directory, filename, 'cal files (*.cal)|*.cal', wx.SAVE)
        if (dlg.ShowModal()==wx.ID_OK):
            filename=dlg.GetFilename()
            directory=dlg.GetDirectory()
        dlg.Destroy()
        #cv.Save( filename, self.CalibData.intrinsic)
        intrinsic=self.CvMattoPythonArray(self.CalibData.intrinsic)
        distortion=self.CvMattoPythonArray(self.CalibData.distortion)
        #print self.CalibData.intrinsic[0,0]
        filecalib=open(filename,'w')
        pickle.dump((intrinsic,distortion),filecalib)
        filecalib.close()
    
    def CvMattoPythonArray(self,cvmat):
        array=list()
        for i in range(0,cvmat.rows):
            row=list()
            for j in range(0,cvmat.cols):
                row.append(cvmat[i,j])
                #print cvmat[i,j]
            array.append(row)
        #print array
        return array
    def PythonArraytoCvMat(self,array):
        numrows=len(array)
        numcols=len(array[0])
        #check if homogen
        if numrows>1:
            for k in range(1,numrows-1):
                if numcols!=len(array[k]):
                    return None
        cvmat=cv.CreateMat(numrows,numcols,cv.CV_32FC1)
        for i in range(0,cvmat.rows):
            for j in range(0,cvmat.cols):
                cvmat[i,j]=array[i][j]
        return cvmat
    def LoadCalibration(self,event):
        self.SetStatusText('Select file with intrinsic camera matrix')
        dlg = wx.FileDialog(self, "Select file with intrinsic camera matrix", config.ProgDir, "", 'cal files (*.cal)|*.cal', wx.FD_OPEN)
        if dlg.ShowModal() == wx.ID_OK:
            filename=dlg.GetFilenames()
            dirname=dlg.GetDirectory()
            filecalib=open(filename[0],'r')
            intrinsic,distortion=pickle.load(filecalib)
            filecalib.close()
            #self.CalibData.intrinsic = cv.Load( filename[0] )
            dlg.Destroy()
            self.CalibData.intrinsic=self.PythonArraytoCvMat(intrinsic)
            self.CalibData.distortion=self.PythonArraytoCvMat(distortion)
            
            intrin=cv.GetSize(self.CalibData.intrinsic)
            distor=cv.GetSize(self.CalibData.distortion)
        if (intrin[0]==3 and intrin[1]==3 and distor[0]==1 and distor[1]==5):
            self.calibrated=True
            self.SetStatusText('Calibration successfully loaded')
        else:
            wx.MessageBox('False Input!',style= wx.OK | wx.ICON_ERROR)
            
    def PickAll(self,event):
        self.PickAll=True
        self.SendStatustoBackgroundProcess()
        self.PickAll=False
        self.SendStatustoBackgroundProcess()
    def ChangeSRFactor(self,event):
        dlg=wx.NumberEntryDialog(self,'Enter new SearchrectFactor','SRF:','SearchrectFactor',15,15,50)
        if dlg.ShowModal() == wx.ID_OK:
            self.seachrectfactor=dlg.GetValue()
            #print self.seachrectfactor
            self.SendStatustoBackgroundProcess()
            dlg.Destroy()
    def Panel2ImageKoord(self,panelwidth,panelheight,zoomrect,pt):
        pos=int(float(pt[0])/float(panelwidth)*zoomrect[2]+zoomrect[0]),int(float(pt[1])/float(panelheight)*zoomrect[3]+zoomrect[1])
        return pos
    def CheckSubRect(self,image,rect):
        if (rect[0]+rect[2])<=image[1] and (rect[1]+rect[3])<=image[2] and rect[0]>=0 and rect[1]>=0 and rect[2]>=20 and rect[3]>=20:
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
            if (rect[0]+rect[2])>image[1]:
                width=image[1]-rect[0]
                
            else:
                width=rect[2]    
            if (rect[1]+rect[3])>image[2]:
                height=image[2]-rect[1]
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
            if (rect[0]+rect[2])>image[1]:
                orx=image[1]-rect[2]
            if (rect[1]+rect[3])>image[2]:
                ory=image[2]-rect[3]  
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
        for item in self.childs:
            item.OnClose(True)
        self.Destroy()
        
##
class ProcessPicThread(multiprocessing.Process):
    """Background Worker Thread Class."""

    def __init__(self, pipeend, piclistqueue,resultqueuetrack, resultqueuedata, num=0):
        """Init Worker Thread Class."""
        multiprocessing.Process.__init__(self)
        #self.font=cv.InitFont(cv.CV_FONT_HERSHEY_DUPLEX,1,1,0,1,8)
        self.pipeend=pipeend
        self.queue=piclistqueue
        self.out_queue1=resultqueuetrack
        self.out_queue2=resultqueuedata

        self.lasttime=0
        self.framecount=0
        self.actframecount=0

        self.seachrectfactor=1.5
         
        self.num=num
        self.elliplist=list()
        self.connectlist=list()
        self.daemon=True
        self.start()

        # start the thread
    def run(self):
        while True:
            item=self.queue.get()
            self.timestamp=item[0]
            self.raw=item[1]
            #print type(self.raw)
            if self.pipeend.poll():
                self.newellip,self.pickall,self.rightdown,self.seachrectfactor=self.pipeend.recv()
            #print self.newellip,self.pickall,self.rightdown,self.seachrectfactor
            self.newelliplist=list()
            self.newconnectlist=list()
            self.acttime=clock()
            if self.acttime-self.lasttime<1:
                self.framecount+=1
            else:
                # full second
                self.actframecount=self.framecount
                self.framecount=1
                self.lasttime=self.acttime

            if not self.rightdown[0] and self.rightdown[1]!=(None,None) and self.rightdown[2]!=(None,None):
                #print self.parent.rightdown
                newcon=config.LinePar()
                isin, num=self.PosInFoundEllip(self.rightdown[1],self.elliplist)
                if isin:
                    newcon.Pt1=num
                else:
                    newcon.Pt1=None
                isin, num=self.PosInFoundEllip(self.rightdown[2],self.elliplist)
                if isin:
                    newcon.Pt2=num
                else:
                    newcon.Pt2=None

                if newcon.Pt1!=newcon.Pt2 and newcon.Pt1!=None and newcon.Pt1!=None:
                 
                    newcon.Num=self.NumConnect(self.connectlist)
                    #print "connection appended"
                    self.connectlist.append(newcon)

                    self.rightdown=False, (None,None), (None,None)
                
                if newcon.Pt1==newcon.Pt2 and newcon.Pt1!=None and newcon.Pt1!=None:
                    
                    epar=self.GetEllipWithNum(self.elliplist,newcon.Pt1)
                    self.elliplist.remove(epar)
                    #print 'ellip removed'
                    self.rightdown=False, (None,None), (None,None)
                else:
                    del newcon
                    self.rightdown=False, (None,None), (None,None)
    
            #print "before processing "+str(len(self.elliplist))+" "+str(self.timestamp)

            self.image=cv.CreateImage((self.raw[1],self.raw[2]),cv.IPL_DEPTH_8U,3)
            temp=cv.CreateImageHeader((self.raw[1],self.raw[2]), cv.IPL_DEPTH_8U, 1)
            cv.SetData(temp, self.raw[0])
            self.raw=temp
            cv.CvtColor(self.raw,self.image,cv.CV_GRAY2RGB)

            if self.pickall:
                #print 'pick all circles through hough transform'
                self.PickAll(self.raw)


            if self.newellip!=None:
                #check if in already found ellip
                isin,num=self.PosInFoundEllip(self.newellip,self.elliplist)
                if not isin:
                    #print 'pick ellip'
                    ellip=self.PickEllip(self.raw,self.newellip[0],self.newellip[1],self.elliplist)    
                    if not ellip==None:
                        self.elliplist.append(ellip)
                        #print 'new ellip found'
                    self.newellip=None
                        
            if len(self.elliplist)>0:
                self.newelliplist, self.newconnectlist, self.image=self.ProcessImage(self.raw,self.image, self.elliplist, self.connectlist)
                #update elements
                self.elliplist, self.connectlist=self.newelliplist, self.newconnectlist

            
            #print 'try to put in queue'

            try:
                self.out_queue1.put((self.timestamp,(self.image.tostring(),self.image.width,self.image.height), self.newelliplist, self.newconnectlist,self.actframecount),False)
            except Queue.Full:
                ##print 'trackresultqueue1 full'
                pass

            
            try:
                self.out_queue2.put((self.timestamp,(self.image.tostring(),self.image.width,self.image.height), self.newelliplist, self.newconnectlist),False)
            except Queue.Full:
                ##print 'trackresultqueue2 full'
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
        errcount=0
        #print 'create memstorage'
        stor = cv.CreateMemStorage(0)
        
        while found <1:
            #searchrectsize=int(searchrectsize+searchrectsize/10)
            searchrectsize=int(searchrectsize+firstsearchrectsize)
            #print searchrectsize
            
            searchrectr=(posx-searchrectsize,posy-searchrectsize,searchrectsize*2,searchrectsize*2)
            #print searchrectr

            if searchrectsize*2>image.width:
                break
            #print 'get search contour image'
            rectimage,searchrect=self.GetSearchCounturImage(image,searchrectr)

            
            #print 'search image created'
            if rectimage==None:
                continue
            #pixout,pixin=self.InOutVal(rectimage)
            if cv.CountNonZero(rectimage)<=10:
                continue

            stor = cv.CreateMemStorage(0)
            cont=cv.FindContours (rectimage, stor, cv.CV_RETR_LIST,cv.CV_CHAIN_APPROX_TC89_KCOS,(0, 0))
            found=0
            #print 'find contours'
            
            for c in contour_iterator(cont):
                if len(c) >= 6:
                    if cv.ContourArea(c)<=(rectimage.width*rectimage.height/50)or cv.ContourArea(c)>(rectimage.width*rectimage.height/2):
                        continue
                    #print 'process contours'
                    
                    # Fits ellipse to current contour.
                    EllipParnew=self.FitEllipOnContour(c)

                    

                    
                    #define Number
                    EllipParnew.Num=self.NumEllip(elliplist)
                    #korrekt pos and size to global
                    EllipParnew.MidPos=EllipParnew.MidPos[0]/rectimage.width*searchrect[2]+searchrect[0],EllipParnew.MidPos[1]/rectimage.height*searchrect[3]+searchrect[1]
                    EllipParnew.Size= EllipParnew.Size[0]/rectimage.width*searchrect[2]/2,EllipParnew.Size[1]/rectimage.height*searchrect[3]/2

                    
                    #EllipParnew.Angle=-EllipParnew.Angle
                    EllipParnew.mov=0,0

                    b,h=self.GetAABBEllip(EllipParnew)

                    left=int(EllipParnew.MidPos[0]-b/2)
                    low=int(EllipParnew.MidPos[1]-h/2)
                    

                    #if  EllipParnew.Size[1]>=1 and EllipParnew.Size[0]>=1 and EllipParnew.Size[1]<searchrect[3]/2 and EllipParnew.Size[0]<searchrect[2]/2 :
                    #if  EllipParnew.Size[1]!=0 and EllipParnew.Size[0]!=0  and (searchrect[0]+searchrect[2]*3/5.0)<EllipParnew.MidPos[0]<(searchrect[0]+searchrect[2]*4/5.0) and (searchrect[1]+searchrect[3]/3.0)<EllipParnew.MidPos[1]<(searchrect[1]+searchrect[3]/3.0*2.0):
                    if left>searchrect[0] and low>searchrect[1] and b<searchrect[2] and h<searchrect[3] and b>searchrect[2]/3 and h>searchrect[3]/3:
                        found=1
                        #print 'found ellip'
                        #cv.Rectangle(self.image,(searchrect[0],searchrect[1]),(int(searchrect[0]+searchrect[2]),int(searchrect[1]+searchrect[3])),cv.CV_RGB(255,0,255),1,8,0)
                        #cv.Rectangle(self.image,(left,low),(int(left+b),int(low+h)),cv.CV_RGB(0,255,255),1,8,0)
                        EllipParnew.searchrect=searchrect
                        break
            
            
            
        if found>=1:
            #print 'found ellip'
            return EllipParnew
        else:
            return None


    def PickAll(self,gray):
        storage = cv.CreateMat(50, 1, cv.CV_32FC3)
        try:
            cv.HoughCircles(gray, storage, cv.CV_HOUGH_GRADIENT, 2, int(gray.width/20), 192, 50)
        except:
            #print 'null pointer bla bla'
            return
        #print storage
        for i in range(0,storage.rows):
                row=list()
                for j in range(0,storage.cols):
                    #print 'pick ellip'
                    #print int(storage[i,j][0]),int(storage[i,j][1])
                    ellip=self.PickEllip(self.raw,int(storage[i,j][0]),int(storage[i,j][1]),self.elliplist)    
                    if not ellip==None:
                        #print 'is regular ellip'
                        self.elliplist.append(ellip)
        
        
    def TrackEllip(self,image,ellipses):
        
        elliplistnew=list()
        for listpos, item in enumerate(ellipses):
            #print 'track ellip'
            triedtorescue=False
            ellip=config.EllipPar()
            
            ellip=ellipses[listpos]
            
            
            b,h=self.GetAABBEllip(ellip)

            b,h=int(b*self.seachrectfactor/10),int(h*self.seachrectfactor/10)
##            if b<15:
##                b=15
##            if h<15:
##                h=15

            #with movement correction
            searchrecttr = (int(ellip.MidPos[0]+int(ellip.mov[0])-b/2),int(ellip.MidPos[1]+int(ellip.mov[1])-h/2),int(b),int(h))

            #print 'finish init %(listpos)d in frame %(framenum)d ' % vars()
            rectimage, searchrect=self.GetSearchCounturImage(image,searchrecttr)
            #print rectimage, searchrect

            if rectimage==None:
                continue

            #cv.Rectangle(self.image,(searchrect[0],searchrect[1]),(int(searchrect[0]+searchrect[2]),int(searchrect[1]+searchrect[3])),cv.CV_RGB(255,0,0),2,8,0)

            #pixout,pixin=self.InOutVal(rectimage)

            stor = cv.CreateMemStorage(0)
            cont=cv.FindContours (rectimage, stor, cv.CV_RETR_LIST,cv.CV_CHAIN_APPROX_TC89_KCOS,(0, 0))
            found=0
            for c in contour_iterator(cont):
                if len(c) >= 6:
                    if cv.ContourArea(c)<=(rectimage.width*rectimage.height/50)or cv.ContourArea(c)>(rectimage.width*rectimage.height/2):
                        continue
                    
                    # Fits ellipse to current contour.
                    EllipParnew=self.FitEllipOnContour(c)

                    
                    
                    #define Number
                    EllipParnew.Num=ellip.Num
                    #korrekt pos and size to global
                    EllipParnew.MidPos=EllipParnew.MidPos[0]/rectimage.width*searchrect[2]+searchrect[0],EllipParnew.MidPos[1]/rectimage.height*searchrect[3]+searchrect[1]
                    EllipParnew.Size= EllipParnew.Size[0]/rectimage.width*searchrect[2]/2,EllipParnew.Size[1]/rectimage.height*searchrect[3]/2

                    
                    #EllipParnew.Angle=-EllipParnew.Angle
                    EllipParnew.mov=EllipParnew.MidPos[0]-ellip.MidPos[0],EllipParnew.MidPos[1]-ellip.MidPos[1]

                    b,h=self.GetAABBEllip(EllipParnew)

                    left=int(EllipParnew.MidPos[0]-b/2)
                    low=int(EllipParnew.MidPos[1]-h/2)
                    

                    if left>searchrect[0] and low>searchrect[1] and b<searchrect[2] and h<searchrect[3] and b>searchrect[2]/3 and h>searchrect[3]/3:
                    #if  EllipParnew.Size[1]>=0 and EllipParnew.Size[0]>=0  :
                    #if  EllipParnew.Size[1]!=0 and EllipParnew.Size[0]!=0  and (searchrect[0]+searchrect[2]*3/5.0)<EllipParnew.MidPos[0]<(searchrect[0]+searchrect[2]*4/5.0) and (searchrect[1]+searchrect[3]/3.0)<EllipParnew.MidPos[1]<(searchrect[1]+searchrect[3]/3.0*2.0):
                        found=1
                        cv.Rectangle(self.image,(searchrecttr[0],searchrecttr[1]),(int(searchrecttr[0]+searchrecttr[2]),int(searchrecttr[1]+searchrecttr[3])),cv.CV_RGB(255,0,0),2,8,0)
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

                        #cv.Rectangle(self.image,(rect[0],rect[1]),(int(rect[0]+rect[2]),int(rect[1]+rect[3])),cv.CV_RGB(255,255,255),1,8,0)
                        
                        rectimage, searchrect=self.GetSearchCounturImage(image,rect)
                        if rectimage==None:
                            continue

                        if cv.CountNonZero(rectimage)<=10:
                            continue
                        
                        
                        stor = cv.CreateMemStorage(0)
                        #print 'get contours %(listpos)d in frame %(framenum)d ' % vars()
                        cont=cv.FindContours (rectimage, stor, cv.CV_RETR_LIST,cv.CV_CHAIN_APPROX_TC89_KCOS,(0, 0))
                        found=0
                        for c in contour_iterator(cont):
                            if len(c) >= 6:
                                if cv.ContourArea(c)<=(rectimage.width*rectimage.height/50)or cv.ContourArea(c)>(rectimage.width*rectimage.height/2):
                                    continue
                                
                                # Fits ellipse to current contour.
                                EllipParnew=self.FitEllipOnContour(c)

                                #define Number
                                EllipParnew.Num=ellip.Num
                                #korrekt pos and size to global
                                EllipParnew.MidPos=EllipParnew.MidPos[0]/rectimage.width*searchrect[2]+searchrect[0],EllipParnew.MidPos[1]/rectimage.height*searchrect[3]+searchrect[1]
                                EllipParnew.Size= EllipParnew.Size[0]/rectimage.width*searchrect[2]/2,EllipParnew.Size[1]/rectimage.height*searchrect[3]/2

                                
                                #EllipParnew.Angle=-EllipParnew.Angle
                                EllipParnew.mov=EllipParnew.MidPos[0]-ellip.MidPos[0],EllipParnew.MidPos[1]-ellip.MidPos[1]

                                b,h=self.GetAABBEllip(EllipParnew)

                                left=int(EllipParnew.MidPos[0]-b/2)
                                low=int(EllipParnew.MidPos[1]-h/2)
                                

                                if left>searchrect[0] and low>searchrect[1] and b<searchrect[2] and h<searchrect[3] and b>searchrect[2]/3 and h>searchrect[3]/3:
                               #if  EllipParnew.Size[1]<=1 and EllipParnew.Size[0]<=1 and (searchrect[0]+searchrect[2]*3/5.0)<EllipParnew.MidPos[0]<(searchrect[0]+searchrect[2]*4/5.0) and (searchrect[1]+searchrect[3]/3.0)<EllipParnew.MidPos[1]<(searchrect[1]+searchrect[3]/3.0*2.0):
                                #if  EllipParnew.Size[1]>=0 and EllipParnew.Size[0]>=0  and EllipParnew.Size[0]>ellip.Size[0]*0.9 and EllipParnew.Size[1]>ellip.Size[1]*0.9 and EllipParnew.Size[0]<ellip.Size[0]*1.1 and EllipParnew.Size[1]<ellip.Size[1]*1.1:
                                    cv.Rectangle(self.image,(searchrect[0],searchrect[1]),(int(searchrect[0]+searchrect[2]),int(searchrect[1]+searchrect[3])),cv.CV_RGB(0,255,0),1,8,0)
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
        mat=cv.CreateMat(1,len(contour),cv.CV_32SC2)
        for (i, (x, y)) in enumerate(contour):
                    mat[0, i] = (x, y)
        box = cv.FitEllipse2(mat)
        epar=config.EllipPar()
        epar.MidPos=box[0]
        epar.Size=box[1]
        epar.Angle=box[2]
        return epar
    def RescueList(self,searchrect,mov):
        #make searchrect bigger and move around
        rectlist=list()
        factors=range(1,3)
        bfactors=range(1,3)

        for factor in factors:
            #teilen=12
            teilen=8
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
        #print x,y, angle
      
        return y,x

    def GetSearchCounturImage(self,image,rect):
        #check subrect is in image
        if not self.CheckSubRect(image,rect):
            return None,rect
        else:
            #print 'init subimage'
            pyrimage=cv.CreateImage((rect[2]*2,rect[3]*2),8,1)
            temp=cv.CreateImage((rect[2],rect[3]),8,1)
            temp2=cv.CreateImage((rect[2],rect[3]),8,1)
            
            thresimg=cv.CreateImage((temp.width*5,temp.height*5),8,1)
            
            cv.SetImageROI(image,rect)
            #print 'copy subimage'
            cv.Copy(image,temp)
            cv.ResetImageROI(image)

            cv.PyrUp(temp,pyrimage)
            cv.PyrDown(pyrimage,temp)

            cv.Smooth(temp,temp,cv.CV_MEDIAN,3)
            #cv.Smooth(temp,temp2,cv.CV_BILATERAL,3,3,175,175)

            cv.Resize(temp,thresimg,cv.CV_INTER_CUBIC)
    
            #pixout,pixin=self.InOutVal(thresimg)
            #thres=int((pixin+pixout)/2)
            #cv.Threshold(thresimg,thresimg,thres,255,cv.CV_THRESH_BINARY)
            
            cv.Threshold(thresimg,thresimg,0,255,cv.CV_THRESH_OTSU)

            #print 'return subimage'
            return thresimg, rect
    def InOutVal(self,img):

        pixout=0
        pixin=0
        
        pixout=(img[0,0]+img[0,1]+img[1,0]
                 +img[0,img.width-1]+img[1,img.width-1]+img[0,img.width-2]
                 +img[img.height-1,0]+img[img.height-2,0]+img[img.height-1,1]
                 +img[img.height-1,img.width-1]+img[img.height-2,img.width-1]+img[img.height-1,img.width-2])
        pixout=pixout/12

        
        pixin=img[int(img.height/2),int(img.width/2)]+img[int(img.height/2)+1,int(img.width/2)]+img[int(img.height/2),int(img.width/2)+1]+img[int(img.height/2)+1,int(img.width/2)+1]
        pixin=pixin/4
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
        if (rect[0]+rect[2])<=image.width and (rect[1]+rect[3])<=image.height and rect[0]>=0 and rect[1]>=0 and rect[2]>=10 and rect[3]>=10:
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

class WinTrackBmpPaintThread(threading.Thread):
    """Background Worker Thread Class."""

    def __init__(self, parent,bmppaintqueue):
        """Init Worker Thread Class."""
        threading.Thread.__init__(self)
        self.parent=parent
        self.bmppaintqueue=bmppaintqueue
        

        self.font=cv.InitFont(cv.CV_FONT_HERSHEY_DUPLEX,1,1,0,1,8)
        self.ZoomImage=cv.CreateImage((100,100),8,3)
        self.ScaledImg=cv.CreateImage((100,100),8,3)
        
        self.Mask=cv.CreateImage((100,100),8,3)
        self.Mask=cv.CreateImage((100,100),8,1)
        self.Overlay=cv.CreateImage((100,100),8,3)
        self.Overlay2=cv.CreateImage((100,100),8,3)

        
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

            temp=cv.CreateImageHeader((image[1],image[2]), cv.IPL_DEPTH_8U, 3)
            cv.SetData(temp, image[0])
            image=temp
            
            zoomrect=self.parent.zoomrect
            zoomval=self.parent.zoomval
            if zoomrect==None or zoomval==0:
                zoomrect=(0,0,image.width,image.height)
                self.parent.zoomrect=zoomrect
            
            dc=wx.ClientDC(self.parent.panel)
            self.parent.panelwidth,self.parent.panelheight=dc.GetSize()
            rightdown=self.parent.rightdown

            #change mask size if necessary and set it zero
            if self.Mask.width!=image.width or self.Mask.height!=image.height:
                self.Mask=cv.CreateImage((image.width,image.height),8,3)
                self.Mask2=cv.CreateImage((image.width,image.height),8,1)
            self.Overlay=cv.CloneImage(image)
            cv.SetZero(self.Mask)
            cv.SetZero(self.Mask2)

            #draw all marks

            #first ellipses

            for listpos, item in enumerate(ellipses):
                ellipPar=config.EllipPar()
                ellipPar=ellipses[listpos]
                #determine thickness of mark
                thickness=(int((ellipPar.Size[0]+ellipPar.Size[1])/20))
                
                self.DrawEllipMark(self.Mask,ellipPar,0,0,255,thickness)

            #second connections

            for listpos, item in enumerate(connections):
                
                linepar=config.LinePar()
                linepar=connections[listpos]
                epar1=self.GetEllipWithNum(ellipses,linepar.Pt1)
                epar2=self.GetEllipWithNum(ellipses,linepar.Pt2)
                
                cv.Line(self.Mask,(int(epar1.MidPos[0]),int(epar1.MidPos[1])),(int(epar2.MidPos[0]),int(epar2.MidPos[1])),cv.CV_RGB(255,0,0),2,8,0)
                                        
                rx,ry=abs(epar1.MidPos[0]-epar2.MidPos[0]),abs(epar1.MidPos[1]-epar2.MidPos[1])
                if epar1.MidPos[0]<epar2.MidPos[0]:
                    posx=int(epar1.MidPos[0]+rx/2)
                else:
                    posx=int(epar2.MidPos[0]+rx/2)
                if epar1.MidPos[1]<epar2.MidPos[1]:
                    posy=int(epar1.MidPos[1]+ry/2)
                else:
                    posy=int(epar2.MidPos[1]+ry/2)

                cv.PutText(self.Mask,'C%d'%linepar.Num,(posx,posy),self.font,cv.CV_RGB(255,0,0))
  
            #connection in build
            if rightdown[0]:
                cv.Line(self.Mask,rightdown[1],rightdown[2],cv.CV_RGB(0,255,0),2,8,0)

            #overlay mask
            cv.CvtColor(self.Mask,self.Mask2,cv.CV_RGB2GRAY)

            alpha=10.0
            cv.AddS(image,cv.Scalar(-125.0,-125.0,-125.0),self.Overlay,self.Mask2)
            cv.Add(self.Overlay,self.Mask,self.Overlay)
            
            
            panelwidth,panelheight=dc.GetSize()
            if (panelwidth <=0) or (panelheight <=0):
                continue
            if self.ScaledImg.width!=panelwidth or self.ScaledImg.height!=panelheight:
                self.ScaledImg=cv.CreateImage((panelwidth,panelheight),8,3)

            #reset Zoom when image.size changed
            
            if (zoomrect[0]+zoomrect[2])>self.Overlay.width or (zoomrect[1]+zoomrect[3])>self.Overlay.height:
                zoomrect=(0,0,self.Overlay.width ,self.Overlay.height)
            if zoomrect[2]!=self.Overlay.width or zoomrect[3]!=self.Overlay.height:
                cv.SetImageROI(self.Overlay,zoomrect)
                if self.ZoomImage.width!=zoomrect[2] or self.ZoomImage.height!=zoomrect[3]:
                    self.ZoomImage=cv.CreateImage((zoomrect[2],zoomrect[3]),8,3)
                cv.Copy(self.Overlay,self.ZoomImage)
                cv.ResetImageROI(self.Overlay)
                cv.Resize(self.ZoomImage,self.ScaledImg,cv.CV_INTER_NN)
            else:
                cv.Resize(self.Overlay,self.ScaledImg,cv.CV_INTER_NN)

            self.bitmap=wx.BitmapFromBuffer(panelwidth,panelheight,self.ScaledImg.tostring()) 
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
        cv.Rectangle(image,(posx,posy),(int(posx+b),int(posy+h)),cv.CV_RGB(color1,color2,color3),thickness,8,0)
        
        cv.Ellipse(image, (int(epar.MidPos[0]),int(epar.MidPos[1])), (int(epar.Size[0]),int(epar.Size[1])),int(epar.Angle), 0, 360,cv.CV_RGB(color1,color2,color3), thickness, 8, 0);
        cv.Line(image,(int(epar.MidPos[0]-b/2),int(epar.MidPos[1])),(int(epar.MidPos[0]+b/2),int(epar.MidPos[1])),cv.CV_RGB(color1,color2,color3),thickness,8,0)
        cv.Line(image,(int(epar.MidPos[0]),int(epar.MidPos[1]-h/2)),(int(epar.MidPos[0]),int(epar.MidPos[1]+h/2)),cv.CV_RGB(color1,color2,color3),thickness,8,0)
        
        cv.PutText(image,'%d'%epar.Num,(int(posx+b),int(posy+h)),self.font,cv.CV_RGB(color1,color2,color3))

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

            cv.Line(image,(int(P5[0]),int(P5[1])),(int(P2[0]),int(P2[1])),cv.CV_RGB(color1,255,color3),thickness,8,0)

            P3=P1[0]-9*math.cos(angle+math.pi/4),P1[1]-9*math.sin(angle+math.pi/4)  
            P4=P1[0]-9*math.cos(angle-math.pi/4),P1[1]-9*math.sin(angle-math.pi/4)
  
            #print angle,lenght
        
            cv.FillPoly(image,
                        [[(int(P3[0]),int(P3[1])),
                         (int(P1[0]),int(P1[1])),
                         (int(P4[0]),int(P4[1]))]],
                        cv.CV_RGB(color1,255,color3),
                        8,0)
      
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

