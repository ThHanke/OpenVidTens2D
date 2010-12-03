# -*- coding: cp1252 -*-
import wx,cv
import threading
import Queue

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

        config.EVT_RESULT(self, self.PicProcessed)

        
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
                    c3=self.tree.AppendItem(this,'Size a')
                    c4=self.tree.AppendItem(this,'Size b')
                    c5=self.tree.AppendItem(this,'Angle')
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
                        ellip=config.EllipPar()
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

                
            wx.PostEvent(self.parent, config.ResultEvent("Data ready!",self.plotlist))
                    
                    
            self.dataqueue.task_done()
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
    
