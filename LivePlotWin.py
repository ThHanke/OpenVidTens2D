# -*- coding: cp1252 -*-
import wx,cv2
import threading
import Queue
import multiprocessing

import os
import pickle

import wx.lib.plot as plot

from time import clock

#import globals
import config

class LivePlotWin(wx.Frame):
    def __init__(self,source):
        self.winsource=source
        screensize=wx.Display().GetGeometry()
        wx.Frame.__init__(self,None,wx.ID_ANY,title='LivePlotWin',pos=(0,screensize[3]/2),size=(screensize[2]/2,screensize[3]/2),style= wx.DEFAULT_FRAME_STYLE ^ wx.CLOSE_BOX )
        self.status=self.CreateStatusBar()
        self.status.SetFieldsCount(2)
        self.status.SetStatusWidths([-1,65])

        self.lasttime=0
        self.acttime=0
        self.framecount=0

        self.buttonpanel=wx.Panel(self, wx.ID_ANY, style=wx.NO_BORDER)
        self.buttonsizer = wx.BoxSizer(wx.HORIZONTAL)
        self.startbutton=wx.BitmapButton(self.buttonpanel,wx.ID_ANY,wx.Image('Startupsmall.png', wx.BITMAP_TYPE_PNG).ConvertToBitmap(),style=wx.BU_EXACTFIT)
        self.stopbutton=wx.BitmapButton(self.buttonpanel,wx.ID_ANY,wx.Image('Stopupsmall.png', wx.BITMAP_TYPE_PNG).ConvertToBitmap(),style=wx.BU_EXACTFIT)
        self.startbutton.SetBitmapSelected(wx.Image('Startdownsmall.png', wx.BITMAP_TYPE_PNG).ConvertToBitmap())
        self.stopbutton.SetBitmapSelected(wx.Image('Stopdownsmall.png', wx.BITMAP_TYPE_PNG).ConvertToBitmap())
        self.clearbutton=wx.Button(self.buttonpanel,wx.ID_ANY,'CLEAR',size=(60,28),style=wx.BU_EXACTFIT)
        
        self.checkwritevideo=wx.CheckBox(self.buttonpanel,wx.ID_ANY,'Write Video',size=(80,20),style=wx.BU_EXACTFIT)
        self.filetext=wx.TextCtrl(self.buttonpanel,wx.ID_ANY,size=(300,20),style=wx.BU_EXACTFIT)
        self.filetext.SetValue('data000.txt')
        
        
        self.buttonsizer.Add(self.startbutton,0)
        self.buttonsizer.Add(self.stopbutton,0)
        self.buttonsizer.Add(self.clearbutton,0,wx.ALIGN_CENTER_VERTICAL)
        self.buttonsizer.Add(self.checkwritevideo,0,wx.ALIGN_CENTER_VERTICAL)
        self.buttonsizer.Add(self.filetext,1,wx.ALIGN_CENTER_VERTICAL)
        
        self.buttonpanel.SetSizer(self.buttonsizer)

        self.splitter = wx.SplitterWindow(self, wx.ID_ANY, style=wx.SP_BORDER)
        self.splitter.SetMinimumPaneSize(50)
        self.panel=wx.Panel(self.splitter, wx.ID_ANY, size=(500,500),style=wx.BORDER_SUNKEN)
        self.plotter = plot.PlotCanvas(self.panel)
        self.plotter.SetEnableLegend(True)
        self.plotter.SetXSpec('min')
        self.plotter.SetYSpec('min') 
 
        self.toqueue=list()
        self.itemlist=list()
        
        self.plotlist=list()
        self.data = list()
        self.toplotlist=list()
        self.elliplist=list()
        self.connectlist=list()
        self.tofile=False
        self.shouldclear=False
        self.filename=None
        self.fp=None
        self.usevideowriter=False
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

        #spwan queue

        self.plotwritequeue=multiprocessing.Queue(1)
        self.parentendpipe,self.childendpipe=multiprocessing.Pipe()
        #spawn pool of threads
        DataProtoProcess(self.childendpipe,self.winsource.resultqueuePlot,self.plotwritequeue)
        self.SendStatustoBackgroundProcess()
        
        #spawn pool of threads
        PlotWriteThread(self,self.parentendpipe,self.plotwritequeue)

        self.startbutton.Bind(wx.EVT_BUTTON, self.OnStart)
        self.stopbutton.Bind(wx.EVT_BUTTON, self.OnStop)
        self.clearbutton.Bind(wx.EVT_BUTTON, self.OnClear)


        self.tree.Bind(wx.EVT_TREE_SEL_CHANGED,self.OnSelChanged)


        self.imageslist=wx.ImageList(16,16)


        
        self.imageslist.Add(wx.Bitmap('calicon.png'))
        self.tree.SetImageList(self.imageslist)

       
        self.splitter.SetSize (self.GetClientSize ())
        size = self.GetSize()
        self.splitter.SetSashPosition(size.x / 5)


        self.Layout()
        self.Show()
    def SendStatustoBackgroundProcess(self):
        if self.checkwritevideo.GetValue:
            self.usevideowriter=True
        else:
            self.usevideowriter=False
        self.parentendpipe.send((self.itemlist,self.toplotlist,self.tofile,self.filename,self.usevideowriter,self.winsource.calibrated,self.winsource.CalibData,self.shouldclear))
    def OnStart(self,event):
        self.tofile=True
        self.filename=self.filetext.GetValue()
        while os.path.isfile(self.filename):
            self.SetStatusText('File exists allready')
            comps=self.filename.rpartition('.')
            #print len(comps[0])
            string=''
            for i in range(len(comps[0])-1,0,-1):
                if comps[0][i].isdigit():
                    string=comps[0][i]+string
                else:
                    count=int( string)+1
                    newcountstring='%d'%count
                    if len(newcountstring)<=len(string):
                        newcountstring=str.zfill(newcountstring,len(string))
                    else:
                        newcountstring=str.zfill(newcountstring,len(string)+1)
                    break
            self.filename=comps[0][0:(i+1)]+newcountstring+comps[1]+comps[2]
            self.filetext.SetValue(self.filename)
            
        self.fp=open(self.filename,'w',0)
       
        self.WriteDataHead(self.fp)
        self.SetStatusText('Capturing')
        self.capturestarttime=clock()
        #self.data=list()
        #print 'send to background data process'
        self.SendStatustoBackgroundProcess()
        
    def WriteDataHead(self,fileinter):
        string=''
        for i in range(len(self.toplotlist)):
            if i==0:
                string='Time'+'\t'
            else:
                string=string+'\t'
            string= string+str(self.toplotlist[i])
        fileinter.writelines(string+'\n')
        
    def OnStop(self,event):
        
        self.tofile=False
        if self.fp!=None:
            self.fp.close()

        self.SendStatustoBackgroundProcess()
        
        try:
            del self.videowriter
        except:
            pass
        self.fp=None
        self.SetStatusText('Stopped Capturing')
    def OnClear(self,event):
        self.shouldclear=True
        self.SendStatustoBackgroundProcess()
        self.shouldclear=False
        self.SetStatusText('Cleared live plot')
        
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
    def GetConnectWithNum(self,liste,num):
        found=False
        for listpos, item in enumerate(liste):
            linepar=config.LinePar()
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

        if not self.tofile:
            treesel=self.tree.GetSelections()
            #print treesel
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
                
            self.SendStatustoBackgroundProcess()
            #print 'changes where send'
            

    def BuildTreeCtrl(self):

        if self.winsource.winsource.isfileinterface:
            if self.winsource.winsource.gothrough:
                self.winsource.winsource.gothrough=False
        
        self.tree.DeleteAllItems()
        Element = self.tree.AddRoot('Element')
        if len(self.itemlist)>0:
            for listpos, item in enumerate(self.itemlist):
                if isinstance(self.itemlist[listpos],config.EllipPar):
                    #print "is ellip"
                    par=config.EllipPar()
                    par=self.itemlist[listpos]
                    Ellipse=self.tree.AppendItem(Element,'Ellipse')
                    this=self.tree.AppendItem(Ellipse,str(par.Num))
                    c1=self.tree.AppendItem(this,'MidPos x')
                    if self.winsource.calibrated:
                        
                        self.tree.SetItemImage(c1,0)
                    c2=self.tree.AppendItem(this,'MidPos y')
                    if self.winsource.calibrated:
                        self.tree.SetItemImage(c2,0)
                    self.tree.AppendItem(this,'Size a')
                    self.tree.AppendItem(this,'Size b')
                    self.tree.AppendItem(this,'Angle')
                if isinstance(self.itemlist[listpos],config.LinePar):
                    #print  "is connect"
                    par=config.LinePar()
                    par=self.itemlist[listpos]
                    Connection=self.tree.AppendItem(Element,'Connection')
                    this=self.tree.AppendItem(Connection,str(par.Num))
                    c1=self.tree.AppendItem(this,'Range x')
                    if self.winsource.calibrated:
                        self.tree.SetItemImage(c1,0)
                    c2=self.tree.AppendItem(this,'Range y')
                    if self.winsource.calibrated:
                        self.tree.SetItemImage(c2,0)
                    c3=self.tree.AppendItem(this,'Lenght')
                    if self.winsource.calibrated:
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

    def OnClose(self,event):
        for item in self.childs:
            item.OnClose(True)
        self.Destroy()

class DataProtoProcess(multiprocessing.Process):
    """Background Worker Thread Class."""

    def __init__(self, pipeend,dataqueue,resultqueue):
        """Init Worker Thread Class."""
        multiprocessing.Process.__init__(self)
        self.pipeend=pipeend
        self.dataqueue=dataqueue
        self.resultqueue=resultqueue
        self.data=list()
##        self.tofile=False
##        self.filename=None
        self.fp=None
        self.videowriter=None
##        self.daemon=True
        self.itemlist=list()
        self.toplotlist=list()
        self.tofile=False
        self.calibrated=False
        self.calibdata=None
        self.elliplist, self.connectlist=list(),list()

        self.colours=('BLACK','RED','BLUE','GREEN','PINK','YELLOW','CYAN','PEACHPUFF','TURQUOSE','DARKRED','DARKBLUE','DARKGREEN','IVORY','MINTCREAM','NAVY','SEAGREEN','GOLD','SALMON','MAROON','PURPLE')
             
        self.start()
       
        
        # start the thread
    def run(self):
        #print "Aquirethread started "
        while True:
            

            #print 'get actuall data form WInPlot'
            if self.pipeend.poll():
                self.itemlist,self.toplotlist,self.tofile,self.filename,self.usevideowriter,self.calibrated,self.calibdata,self.shouldclear=self.pipeend.recv()
                #print self.itemlist,self.toplotlist,self.tofile,self.filename,self.calibrated,self.calibdata,self.shouldclear
                if self.calibrated:
                        filecalib=open('Calibration.cal','r')
                        intrinsic,distortion,distanceunit=pickle.load(filecalib)
                        filecalib.close()
                        self.intrinsic=intrinsic
                        self.distortion=distortion        
                        self.distanceunit=distanceunit
            
            try:
                (self.timestamp,self.image, self.elliplist, self.connectlist)=self.dataqueue.get(False)
                #print self.timestamp
            except:
                #print 'nothing to get'
                continue
            

               
            #print "DataProtothread got task"
            string=''

            if self.shouldclear:
                self.data=list()
                self.shouldclear=False
          
            #plot selection and write to file
            plotlist=list()
            self.plotmarkerlist=list()
       
            for listpos, item in enumerate(self.toplotlist):
                self.toplot=self.toplotlist[listpos]
                if listpos<len(self.data):
                    temp=self.data[listpos]
                else:
                    temp=list()
               
                time=self.timestamp
                if self.toplot[0]=='Connection':
                    
                    linepar=config.LinePar()
                    epar1=config.EllipPar()
                    epar2=config.EllipPar()
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

                    #correct position concerning cam calibration

                    if self.calibrated:
                        #x1,y1=self.KoordinatestoUndist(self.calibdata.intrinsic,self.calibdata.distortion,epar1.MidPos[0],epar1.MidPos[1])
                        #x2,y2=self.KoordinatestoUndist(self.calibdata.intrinsic,self.calibdata.distortion,epar2.MidPos[0],epar2.MidPos[1])
                        x1,y1=epar1.MidPos[0],epar1.MidPos[1]
                        x2,y2=epar2.MidPos[0],epar2.MidPos[1]
                        rx,ry=abs(x1-x2),abs(y1-y2)
                        
                    else:
                        rx,ry=abs(epar1.MidPos[0]-epar2.MidPos[0]),abs(epar1.MidPos[1]-epar2.MidPos[1])
                    
                        
                    c=(rx**2.0+ry**2.0)**0.5
                    if self.toplot[2]=='Range x':
                        this=rx
                    if self.toplot[2]=='Range y':
                        this=ry
                    if self.toplot[2]=='Lenght':
                        this=c
                    temp.append((time,this))
                if self.toplot[0]=='Ellipse':
                    if self.GetEllipWithNum(self.elliplist,self.toplot[1])== None:
                        continue
                    else:
                        epar=self.GetEllipWithNum(self.elliplist,self.toplot[1])
                        #correct position concerning cam calibration
                        if self.calibrated:
                            #epar.MidPos=self.KoordinatestoUndist(self.calibdata.intrinsic,self.calibdata.distortion,epar.MidPos[0],epar.MidPos[1])
                            #we undist picture
                            pass
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
                    
                line = plot.PolyLine(temp,colour=self.colours[listpos], width=1)
                self.plotmarkerlist.append(line)
                marker = plot.PolyMarker(temp, marker='circle',colour=self.colours[listpos],width=1, size=1)
                self.plotmarkerlist.append(marker)

            if self.tofile:
                self.fp=open(self.filename,'a',0)
                self.fp.writelines(string+'\n')

                if self.usevideowriter:
                    if self.videowriter==None:
                        self.videowriter=cv2.VideoWriter(self.filename[:-3]+'avi', 842289229 ,25,(640,480)) # 859189833 for H263I,827148624 for mpeg-1,1196444237 for mjpg, 541215044 for Uncompress RGB,842289229 for mpg4.2
                    self.videowriter.write(self.image)
            
            
            else:
                if self.videowriter!=None:
                    self.videowriter.release()
                    self.videowriter=None
   
            #resultstring=resultstring+string+'\n'

            
            


            for i in range(len(self.data)):
                
                line = plot.PolyLine(self.data[i],colour=self.colours[i], width=1)
                plotlist.append(line)
                marker = plot.PolyMarker(self.data[i], marker='circle',colour=self.colours[i],width=1, size=1)
                plotlist.append(marker)

            try:
                self.resultqueue.put((self.plotmarkerlist,self.elliplist, self.connectlist),False)
            except Queue.Full:
                #print 'WinPlot bmppaint thread is busy'
                pass
                    
            #self.dataqueue.task_done()
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
    def GetConnectWithNum(self,liste,num):
        found=False
        for listpos, item in enumerate(liste):
            linepar=config.LinePar()
            linepar=liste[listpos]
            if linepar.Num==num:
                found=True
                break
        if found:
            return linepar
        else:
            return None
class PlotWriteThread(threading.Thread):
    """Background Worker Thread Class."""

    def __init__(self, parent, pipeend,plotwritequeue):
        """Init Worker Thread Class."""
        threading.Thread.__init__(self)
        self.plotwritequeue=plotwritequeue
        self.parent=parent
        self.pipeend=pipeend
        self.setDaemon(True)
        self.start()
        self.elliplist=list()
        self.connectlist=list()
        # start the thread

    def run(self):
        #print "Aquirethread started "+str(self.num)
        while True:
            #print 'running'
            #update WinPlot treecontrol

            self.plotlist,self.elliplist,self.connectlist=self.plotwritequeue.get()
            #print plotlist

            if len(self.parent.itemlist)!=len(self.elliplist)+len(self.connectlist):
                #print "rebuild tree items and send " 
                self.parent.itemlist=list()
                self.parent.itemlist.extend(self.elliplist)
                self.parent.itemlist.extend(self.connectlist)
                self.parent.BuildTreeCtrl()

            if len(self.plotlist)>0:
                panelwidth,panelheight=self.parent.panel.GetSize()
                self.parent.plotter.SetSize(size=(panelwidth,panelheight))
                #print'to gc'
                gc = plot.PlotGraphics(self.plotlist, '', 'Time [s]', '[pixel]')
                #print'draw'
                self.parent.plotter.Draw(gc)
                #print'finished'
        #self.plotwritequeue.task_done()

