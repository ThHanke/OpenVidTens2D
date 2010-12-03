# -*- coding: cp1252 -*-
import wx,cv
import threading
import Queue
import math
import pickle

#import globals
import config

from time import sleep

ID_CCAL=wx.NewId()
ID_CCALL=wx.NewId()
ID_CCALS=wx.NewId()

class LiveTrackWin(wx.Frame):
    def __init__(self,source):
        self.winsource=source
        screensize=wx.Display().GetGeometry()
        wx.Frame.__init__(self,None,wx.ID_ANY,title='LiveTrackWin',pos=(screensize[2]/2,0),size=(screensize[2]/2,screensize[3]/2),style= wx.DEFAULT_FRAME_STYLE ^ wx.CLOSE_BOX   )
        self.status=self.CreateStatusBar()
        
        self.panel=wx.Panel(self, wx.ID_ANY, style=wx.BORDER_SUNKEN)
        self.panelsizer=wx.BoxSizer(wx.HORIZONTAL)
        self.panelsizer.Add(self.panel,2,wx.EXPAND)
        self.SetSizer(self.panelsizer)

        menu=self.CreateMenu()
        self.SetMenuBar(menu)

        

        self.Bind(wx.EVT_MENU, self.CameraCalibration, id=ID_CCAL)
        self.Bind(wx.EVT_MENU, self.LoadCalibration, id=ID_CCALL)
        self.Bind(wx.EVT_MENU, self.SaveCalibration, id=ID_CCALS)

        self.panel.Bind(wx.EVT_MOUSEWHEEL, self.Mousewheel)
        self.panel.Bind(wx.EVT_ENTER_WINDOW,self.MouseInWindow)
        self.panel.Bind(wx.EVT_LEAVE_WINDOW,self.MouseOutWindow)
        self.panel.Bind(wx.EVT_LEFT_DOWN,self.MouseLeftClick)
        self.panel.Bind(wx.EVT_RIGHT_DOWN,self.MouseRightClick)
        self.panel.Bind(wx.EVT_MOTION,self.MouseMove)
        self.panel.Bind(wx.EVT_RIGHT_UP,self.MouseRightClick)

        config.EVT_RESULT(self, self.PicProcessed)

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

        self.CalibData=CalibData()
        self.calibrated=False
        
        self.childs=list()


        self.Show()

    def CreateMenu(self):
        Menubar =wx.MenuBar()
        Operate = wx.Menu()
        Menubar.Append(Operate,'&Operate')
        
        Operate.Append(ID_CCALL,'&Load Calibration','Load Camera Calibration')
        Operate.Append(ID_CCALS,'&Save Calibration','Save Camera Calibration')
        Operate.Append(ID_CCAL,'&Calibration','Camera Calibration')
        #Operate.Append(ID_CAMPROP,'&Properties','Camera Properties')
        return Menubar
    
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
                self.newcon=config.LinePar()
                self.newcon.Pt1=num
                self.newcon.Pt2=num
                self.newcon.Pos=self.rightdown[2]

                epar=self.GetEllipWithNum(self.elliplist,self.newcon.Pt1)
                cv.Line(self.image,(int(epar.MidPos[0]),int(epar.MidPos[1])),(int(self.newcon.Pos[0]),int(self.newcon.Pos[1])),cv.CV_RGB(0,255,0),1,8,0)
            else:
                self.rightdown=False, (None,None), (None,None)
                self.newcon=None
        if not self.rightdown[0] and isinstance(self.newcon,config.LinePar):
            
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
            self.status.SetStatusText('Aufl�sung='+str(self.zoomrect[2])+'x'+str(self.zoomrect[3]))

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
            wx.MessageBox('Put Chessboard Pattern ( %dx%d) into %d. Position' %(board_w,board_h,detectsuccsess+1), 'Calibration Procedure',style=wx.OK|wx.ICON_EXCLAMATION)
            raw = cv.CreateImage((self.image.width,self.image.height),8,1)
            cv.CvtColor(self.image,raw,cv.CV_RGB2GRAY)
            paternsize=(board_w,board_h)
            found, corners=cv.FindChessboardCorners(raw, paternsize, cv.CV_CALIB_CB_ADAPTIVE_THRESH)
            if found==0:
                self.SetStatusText('Chessboard Pattern could not be detected')
                continue
            else:
                #Get subpixel accuracy on those corners
                cv.FindCornerSubPix( raw, corners, ( 11, 11 ),( -1, -1 ), ( cv.CV_TERMCRIT_EPS+cv.CV_TERMCRIT_ITER, 30, 0.1))
                cv.DrawChessboardCorners(self.image, paternsize, corners, 1)
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
                sleep(1)
                if detectsuccsess>=n_boards:
                    needcalibpic = False
            #self.displayImage(self.image,self.imagepanel)
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
            cv.CalibrateCamera2( objekt_points_new,image_points_new, point_counts_new, cv.GetSize( self.image ),intrinsic_matrix,distortion_coeffs,rot,trans,0)
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
        #dlg = wx.FileDialog(self, "Save distortion camera matrix as", directory, filename, 'xml files (*.xml)|*.xml', wx.SAVE)
        #if (dlg.ShowModal()==wx.ID_OK):
        #    filename=dlg.GetFilename()
        #    directory=dlg.GetDirectory()
        #dlg.Destroy()
        #cv.Save( filename, self.CalibData.distortion )
    def CvMattoPythonArray(self,cvmat):
        array=list()
        for i in range(0,cvmat.rows):
            row=list()
            for j in range(0,cvmat.cols):
                row.append(cvmat[i,j])
                #print cvmat[i,j]
            array.append(row)
        print array
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
                    trackers.append(window)
                #    #if isinstance(window, LiveTrackWin)or isinstance(window, LivePlotWin):
                #    if isinstance(window, LiveTrackWin):
                #        trackers.append(window)
                #print len(trackers)
                
                for window in trackers:
                    #wx.PostEvent(self.tracker, ResultEvent("Pic processed!",self.image, self.elliplist))
                    self.out_queue.put((self.timestamp,self.image, self.newelliplist, self.newconnectlist))
                    wx.PostEvent(window, config.ResultEvent("Pic processed!",None))
                    self.out_queue.join()
                
                    
            self.queue.task_done()


        
    def ProcessImage(self, grayimage, rgbimage, ellipses,connections):
        #drawold

        
        for listpos, item in enumerate( ellipses):
            ellipPar=config.EllipPar()
            ellipPar=ellipses[listpos]
            self.DrawEllipMark(rgbimage,ellipPar,0,0,200)
        #track
        ellipses=self.TrackEllip(grayimage,ellipses)
        #draw new 
        for listpos, item in enumerate(ellipses):
            ellipPar=config.EllipPar()
            ellipPar=ellipses[listpos]
            
            self.DrawEllipMark(rgbimage,ellipPar,0,0,255)
               
        #draw connections
        for listpos, item in enumerate(connections):
                    
            linepar=config.LinePar()
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
            ellip=config.EllipPar()
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
        i=0
        for (x,y) in contour:
            mat[0,i]=x,y
            i+=1
            if i>len(contour):
                break
        box = cv.FitEllipse2(mat)
        epar=config.EllipPar()
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

class CalibData:
    def __init__(self):
        self.intrinsic=cv.CreateMat(3,3,cv.CV_32FC1)
        self.recti=cv.CreateMat(3,3,cv.CV_32FC1)
        cv.Set(self.recti,1)
