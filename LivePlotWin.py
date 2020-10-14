# -*- coding: cp1252 -*-
import wx
import threading
import queue
import multiprocessing

try:
    import u12
except:
    print('LabJack U12 driver not found')
    LABJACKDRIVER = False
else:
    LABJACKDRIVER = True

try:
    import u3
except:
    print('LabJack U3 driver not found')
    LABJACKDRIVER = False
else:
    LABJACKDRIVER = True

import os
import wx.lib.plot as plot

from time import clock

# import globals
import config


class LivePlotWin(wx.Frame):
    def __init__(self, trackresultqueue, pipetotrack):
        self.trackresultqueue = trackresultqueue
        self.pipetotrack = pipetotrack
        screensize = wx.Display().GetGeometry()
        wx.Frame.__init__(self, None, wx.ID_ANY, title='LivePlotWin', pos=(0, screensize[3] / 2),
                          size=(screensize[2] / 2, screensize[3] / 2), style=wx.DEFAULT_FRAME_STYLE ^ wx.CLOSE_BOX)
        self.status = self.CreateStatusBar()
        self.status.SetFieldsCount(2)
        self.status.SetStatusWidths([-1, 65])

        self.lasttime = 0
        self.acttime = 0
        self.framecount = 0

        self.buttonpanel = wx.Panel(self, wx.ID_ANY, style=wx.NO_BORDER)
        self.buttonsizer = wx.BoxSizer(wx.HORIZONTAL)
        self.startbutton = wx.BitmapButton(self.buttonpanel, wx.ID_ANY,
                                           wx.Image('Startupsmall.png', wx.BITMAP_TYPE_PNG).ConvertToBitmap(),
                                           style=wx.BU_EXACTFIT)
        self.stopbutton = wx.BitmapButton(self.buttonpanel, wx.ID_ANY,
                                          wx.Image('Stopupsmall.png', wx.BITMAP_TYPE_PNG).ConvertToBitmap(),
                                          style=wx.BU_EXACTFIT)
        #self.startbutton.SetBitmapSelected(wx.Image('Startdownsmall.png', wx.BITMAP_TYPE_PNG).ConvertToBitmap())
        #self.stopbutton.SetBitmapSelected(wx.Image('Stopdownsmall.png', wx.BITMAP_TYPE_PNG).ConvertToBitmap())
        self.clearbutton = wx.Button(self.buttonpanel, wx.ID_ANY, 'CLEAR', size=(60, 28), style=wx.BU_EXACTFIT)
        self.usbmodulbox = wx.Choice(self.buttonpanel, wx.ID_ANY, choices=('None',))
        if LABJACKDRIVER:
            self.usbmodulbox.Append('LabJack U12')
            self.usbmodulbox.Append('LabJack U3')

        self.usbmodulbox.SetSelection(0)
        self.USBModul = self.usbmodulbox.GetString(0)

        self.filetext = wx.TextCtrl(self.buttonpanel, wx.ID_ANY, size=(300, 20), style=wx.BU_EXACTFIT)
        self.filetext.SetValue('data000.txt')

        self.buttonsizer.Add(self.startbutton, 0)
        self.buttonsizer.Add(self.stopbutton, 0)
        self.buttonsizer.Add(self.clearbutton, 0, wx.ALIGN_CENTER_VERTICAL)
        self.buttonsizer.Add(self.usbmodulbox, 0, wx.ALIGN_CENTER_VERTICAL)
        self.buttonsizer.Add(self.filetext, 1, wx.ALIGN_CENTER_VERTICAL)

        self.buttonpanel.SetSizer(self.buttonsizer)

        self.splitter = wx.SplitterWindow(self, wx.ID_ANY, style=wx.SP_BORDER)
        self.splitter.SetMinimumPaneSize(50)
        self.panel = wx.Panel(self.splitter, wx.ID_ANY, size=(500, 500), style=wx.BORDER_SUNKEN)
        self.plotter = plot.PlotCanvas(self.panel)
        self.plotter.enableLegend=True
        self.plotter.xSpec='min'
        self.plotter.ySpec='min'

        self.toqueue = list()
        self.itemlist = list()

        self.plotlist = list()
        self.data = list()
        self.toplotlist = list()
        self.elliplist = list()
        self.connectlist = list()
        self.tofile = False
        self.shouldclear = False
        self.filename = None
        self.fp = None
        self.count = 0
        self.called = 0
        self.plotstarttime = clock()
        self.childs = list()

        self.tree = wx.TreeCtrl(self.splitter, style=wx.TR_HIDE_ROOT + wx.TR_MULTIPLE)
        self.splitter.SplitVertically(self.tree, self.panel)

        self.sizer = wx.BoxSizer(wx.VERTICAL)
        self.sizer.Add(self.buttonpanel, 0, wx.EXPAND)
        self.sizer.Add(self.splitter, 1, wx.EXPAND)
        self.SetSizer(self.sizer)

        # spwan queue

        self.plotwritequeue = multiprocessing.Queue(1)
        self.parentendpipe, self.childendpipe = multiprocessing.Pipe()
        # spawn pool of threads
        DataProtoProcess(self.childendpipe, self.trackresultqueue, self.plotwritequeue)
        self.ExitBackground = False
        self.sendstatustobackgroundprocess()

        # spawn pool of threads
        PlotWriteThread(self, self.parentendpipe, self.plotwritequeue)

        self.startbutton.Bind(wx.EVT_BUTTON, self.onstart)
        self.stopbutton.Bind(wx.EVT_BUTTON, self.onstop)
        self.clearbutton.Bind(wx.EVT_BUTTON, self.onclear)
        self.usbmodulbox.Bind(wx.EVT_CHOICE, self.onusbmodul)

        self.tree.Bind(wx.EVT_TREE_SEL_CHANGED, self.onselchanged)

        self.imageslist = wx.ImageList(16, 16)

        self.imageslist.Add(wx.Bitmap('calicon.png'))
        self.tree.SetImageList(self.imageslist)

        self.splitter.SetSize(self.GetClientSize())
        size = self.GetSize()
        self.splitter.SetSashPosition(size.x / 5)

        self.Layout()
        self.Show()

    def sendstatustobackgroundprocess(self):
        # print self.tofile,self.filename
        self.parentendpipe.send((
            self.itemlist, self.toplotlist, self.tofile, self.filename, self.shouldclear, self.USBModul,
            self.ExitBackground))

    def onstart(self, event):

        self.tofile = True
        self.filename = self.filetext.GetValue()
        if os.path.isfile(self.filename):
            self.SetStatusText('File exists allready')
            comps = self.filename.rpartition('.')
            # print len(comps[0])
            string = ''
            for i in range(len(comps[0]) - 1, 0, -1):
                if comps[0][i].isdigit():
                    string = comps[0][i] + string
                else:
                    count = int(string) + 1
                    newcountstring = '%d' % count
                    if len(newcountstring) <= len(string):
                        newcountstring = str.zfill(newcountstring, len(string))
                    else:
                        newcountstring = str.zfill(newcountstring, len(string) + 1)
                    break
            self.filename = comps[0][0:(i + 1)] + newcountstring + comps[1] + comps[2]
            self.filetext.SetValue(self.filename)

        # self.SetStatusText('Capturing - freezing Selection ')
        self.pipetotrack.send(('Capturing', self.filename))
        self.capturestarttime = clock()
        # self.data=list()
        # print 'send to background data process'
        self.sendstatustobackgroundprocess()

    def writedatahead(self, fileinter):
        string = ''
        for i in range(len(self.toplotlist)):
            if i == 0:
                string = 'Time' + '\t'
            else:
                string += '\t'
            string += str(self.toplotlist[i])
        fileinter.writelines(string + '\n')

    def onstop(self, event):
        self.pipetotrack.send('Stopped Capturing')
        self.tofile = False

        self.sendstatustobackgroundprocess()

        self.fp = None
        self.SetStatusText('Stopped Capturing')

    def onclear(self, event):
        self.shouldclear = True
        self.sendstatustobackgroundprocess()
        self.shouldclear = False
        self.SetStatusText('Cleared live plot')

    def onusbmodul(self, event):
        self.USBModul = event.GetString()
        self.buildtreectrl()

    def onselchanging(self, event):
        pass

    def onselchanged(self, event):
        try:
            treesel = self.tree.GetSelections()
        except:
            return
        self.toplotlist = list()
        for subitem in treesel:
            if self.tree.ItemHasChildren(subitem):
                self.tree.UnselectItem(subitem)
                continue
            if subitem.IsOk():
                # self.tree.SetItemImage(subitem,0)
                item = self.tree.GetItemParent(subitem)
                if item.IsOk():
                    parent = self.tree.GetItemParent(item)
                    if parent.IsOk():
                        if self.tree.GetItemText(parent) in ('Ellipse', 'Connection', 'LabJack U12', 'LabJack U3'):
                            self.data = list()
                            this = self.tree.GetItemText(parent), self.tree.GetItemText(item), self.tree.GetItemText(
                                subitem)
                            self.toplotlist.append(this)
        # print self.toplotlist
        self.sendstatustobackgroundprocess()
        # print 'changes where send'

    def buildtreectrl(self):
        # print "rebuild tree items"
        # print self.itemlist
        # add measure modul signals
        if self.USBModul == 'LabJack U12':
            self.itemlist.insert(0, 'LabJack U12')
        if self.USBModul == 'LabJack U3':
            self.itemlist.insert(0, 'LabJack U3')
        if self.USBModul == 'None' and ('LabJack U12' in self.itemlist):
            self.itemlist.remove('LabJack U12')
        if self.USBModul == 'None' and ('LabJack U3' in self.itemlist):
            self.itemlist.remove('LabJack U3')
        self.tree.DeleteAllItems()
        element = self.tree.AddRoot('Element')
        if len(self.itemlist) > 0:
            for listpos, item in enumerate(self.itemlist):
                if isinstance(self.itemlist[listpos], config.EllipPar):
                    # print "is ellip"
                    par = config.EllipPar()
                    par = self.itemlist[listpos]
                    ellipse = self.tree.AppendItem(element, 'Ellipse')
                    this = self.tree.AppendItem(ellipse, str(par.Num))
                    c1 = self.tree.AppendItem(this, 'MidPos x')

                    c2 = self.tree.AppendItem(this, 'MidPos y')

                    self.tree.AppendItem(this, 'Size a')
                    self.tree.AppendItem(this, 'Size b')
                    self.tree.AppendItem(this, 'Angle')
                if isinstance(self.itemlist[listpos], config.LinePar):
                    # print  "is connect"
                    par = config.LinePar()
                    par = self.itemlist[listpos]
                    connection = self.tree.AppendItem(element, 'Connection')
                    this = self.tree.AppendItem(connection, str(par.Num))
                    c1 = self.tree.AppendItem(this, 'Range x')

                    c2 = self.tree.AppendItem(this, 'Range y')

                    c3 = self.tree.AppendItem(this, 'Lenght')
                if item == 'LabJack U12':
                    modul = self.tree.AppendItem(element, 'LabJack U12')
                    this = self.tree.AppendItem(modul, 'Analog')
                    c1 = self.tree.AppendItem(this, 'Diff1')
                    c2 = self.tree.AppendItem(this, 'Diff2')
                if item == 'LabJack U3':
                        modul = self.tree.AppendItem(element, 'LabJack U3')
                        this = self.tree.AppendItem(modul, 'Analog')
                        c1 = self.tree.AppendItem(this, 'Diff1')
                        c2 = self.tree.AppendItem(this, 'Diff2')

                    # print len(self.itemlist),len(elliplist),len(connectlist)
        self.recalltreeselection()
        self.tree.ExpandAll()

    def recalltreeselection(self):
        # print 'mark previously selected'
        self.tree.UnselectAll()
        root = self.tree.GetRootItem()
        if root.IsOk():
            child = self.tree.GetFirstChild(root)
            while child[0].IsOk():
                grandchild = self.tree.GetFirstChild(child[0])
                while grandchild[0].IsOk():
                    grandgrandchild = self.tree.GetFirstChild(grandchild[0])
                    while grandgrandchild[0].IsOk():

                        if (self.tree.GetItemText(child[0]), self.tree.GetItemText(grandchild[0]),
                                self.tree.GetItemText(grandgrandchild[0])) in self.toplotlist:
                            # self.tree.SelectItem(grandgrandchild[0])
                            self.tree.SetItemBold(grandgrandchild[0])
                        grandgrandchild = self.tree.GetNextChild(grandgrandchild[0], grandgrandchild[1])
                    grandchild = self.tree.GetNextChild(grandchild[0], grandchild[1])
                child = self.tree.GetNextChild(child[0], child[1])

    def onclose(self, event):
        self.ExitBackground = True
        self.sendstatustobackgroundprocess()
        for item in self.childs:
            item.onclose(True)
        self.Destroy()


class DataProtoProcess(multiprocessing.Process):
    """Background Worker Thread Class."""

    def __init__(self, pipeend, dataqueue, resultqueue):
        """Init Worker Thread Class."""
        multiprocessing.Process.__init__(self)
        self.pipeend = pipeend
        self.dataqueue = dataqueue
        self.resultqueue = resultqueue
        self.availabledatalist = list()
        self.data = list()
        # self.tofile=False
        self.filename = None
        self.image = None
        self.fp = None
        # self.daemon=True
        self.itemlist = list()
        self.toplotlist = list()
        self.tofile = False
        self.shouldclear = False
        self.USBdevice = None

        self.elliplist, self.connectlist = list(), list()

        self.colours = (
            'BLACK', 'RED', 'BLUE', 'GREEN', 'PINK', 'YELLOW', 'CYAN', 'PEACHPUFF', 'TURQUOSE', 'DARKRED', 'DARKBLUE',
            'DARKGREEN', 'IVORY', 'MINTCREAM', 'NAVY', 'SEAGREEN', 'GOLD', 'SALMON', 'MAROON', 'PURPLE')
        self.plotmarkerlist = list()

        self.start()

        # start the thread

    def run(self):
        # print "Aquirethread started "
        while True:
            plsexit = False

            # print 'get actuall data form WInPlot'
            if self.pipeend.poll():
                self.itemlist, self.toplotlist, self.tofile, self.filename, self.shouldclear, USBModul, plsexit\
                    = self.pipeend.recv()
                # print self.itemlist
                # print self.itemlist,self.toplotlist,self.tofile,self.filename,self.shouldclear,self.USBModul

                self.availabledatalist = list()

                if len(self.itemlist) > 0:

                    for listpos, item in enumerate(self.itemlist):
                        if isinstance(self.itemlist[listpos], config.EllipPar):
                            # print "is ellip"
                            par = config.EllipPar()
                            par = self.itemlist[listpos]
                            self.availabledatalist.append(
                                (('Ellipse'), (str(par.Num)), ('MidPos x')))
                            self.availabledatalist.append(
                                (('Ellipse'), (str(par.Num)), ('MidPos y')))
                            self.availabledatalist.append(
                                (('Ellipse'), (str(par.Num)), ('Size a')))
                            self.availabledatalist.append(
                                (('Ellipse'), (str(par.Num)), ('Size b')))
                            self.availabledatalist.append((('Ellipse'), (str(par.Num)), ('Angle')))

                        if isinstance(self.itemlist[listpos], config.LinePar):
                            # print  "is connect"
                            par = config.LinePar()
                            par = self.itemlist[listpos]
                            self.availabledatalist.append(
                                (('Connection'), (str(par.Num)), ('Range x')))
                            self.availabledatalist.append(
                                (('Connection'), (str(par.Num)), ('Range y')))
                            self.availabledatalist.append(
                                (('Connection'), (str(par.Num)), ('Lenght')))

                        if item == 'LabJack U12':
                            self.availabledatalist.append((('LabJack U12'), ('Analog'), ('Diff1')))
                            self.availabledatalist.append((('LabJack U12'), ('Analog'), ('Diff2')))
                        if item == 'LabJack U3':
                            self.availabledatalist.append((('LabJack U3'), ('Analog'), ('Diff1')))
                            self.availabledatalist.append((('LabJack U3'), ('Analog'), ('Diff2')))


                if self.tofile:
                    if not os.path.isfile(self.filename):
                        print('open file')
                        self.fp = open(self.filename, 'w')
                        self.writedatahead(self.fp, self.availabledatalist)
                else:
                    if self.fp:
                        self.fp.close()
                        self.fp = None

                        # print 'availabledatalist'
                        # print self.availabledatalist
                        # print 'toplotlist'
                        # print self.toplotlist

            if USBModul == 'LabJack U12':
                # print 'get first device'
                self.USBdevice = u12.U12()
            if USBModul == 'LabJack U3':
                # print 'get first device'
                self.USBdevice = u3.U3()
            if USBModul is 'None' and self.USBdevice is not None:
                self.USBdevice = None
            if plsexit:
                # print 'killing myself'
                break

            try:
                (self.timestamp, self.image, self.elliplist, self.connectlist) = self.dataqueue.get(False)
                # print self.timestamp
            except:
                # print 'nothing to get'
                continue

            # print "DataProtothread got task"
            string = ''

            if self.shouldclear:
                self.data = list()
                self.shouldclear = False

            # plot selection and write to file
            self.plotmarkerlist = list()
            # print self.toplotlist

            # for listpos, item in enumerate(self.toplotlist):
            for listpos, item in enumerate(self.availabledatalist):
                if listpos < len(self.data):
                    temp = self.data[listpos]
                else:
                    temp = list()

                time = self.timestamp
                if item[0] == 'Connection':

                    linepar = config.LinePar()
                    epar1 = config.EllipPar()
                    epar2 = config.EllipPar()
                    if self.getconnectwithnum(self.connectlist, int(item[1])) is None:
                        # print 'no connect'
                        continue
                    else:
                        linepar = self.getconnectwithnum(self.connectlist, int(item[1]))

                    if self.getellipwithnum(self.elliplist, linepar.Pt1) is None \
                            or self.getellipwithnum(self.elliplist,linepar.Pt2) is None:
                        # print 'no points'
                        continue
                    else:
                        epar1 = self.getellipwithnum(self.elliplist, linepar.Pt1)
                        epar2 = self.getellipwithnum(self.elliplist, linepar.Pt2)

                    rx, ry = abs(epar1.MidPos[0] - epar2.MidPos[0]), abs(epar1.MidPos[1] - epar2.MidPos[1])

                    c = (rx ** 2.0 + ry ** 2.0) ** 0.5
                    if item[2] == 'Range x':
                        this = rx
                    if item[2] == 'Range y':
                        this = ry
                    if item[2] == 'Lenght':
                        this = c
                    temp.append((time, this))
                if item[0] == 'Ellipse':
                    if self.getellipwithnum(self.elliplist, int(item[1])) is None:
                        continue
                    else:
                        epar = self.getellipwithnum(self.elliplist, int(item[1]))
                        # correct position concerning cam calibration

                        if item[2] == 'MidPos x':
                            this = epar.MidPos[0]
                        if item[2] == 'MidPos y':
                            this = epar.MidPos[1]
                        if item[2] == 'Size a':
                            this = epar.Size[0]
                        if item[2] == 'Size b':
                            this = epar.Size[1]
                        if item[2] == 'Angle':
                            this = epar.Angle
                        temp.append((time, this))

                if item[0] == 'LabJack U12':

                    if item[2] == 'Diff1':
                        result = self.USBdevice.eAnalogIn(8)
                        this = result['voltage']
                    if item[2] == 'Diff2':
                        result = self.USBdevice.eAnalogIn(9)
                        this = result['voltage']
                    temp.append((time, this))
                if item[0] == 'LabJack U3':

                    if item[2] == 'Diff1':
                        result = self.USBdevice.getAIN(0)
                        this = result
                    if item[2] == 'Diff2':
                        result = self.USBdevice.getAIN(1)
                        this = result
                    temp.append((time, this))

                if self.tofile:
                    if listpos == 0:
                        string = str(time) + '\t'
                    else:
                        string += '\t'
                    string += str(this)

                if len(temp) > 200:
                    delelem = temp.pop(0)
                    del delelem
                if listpos < len(self.data):
                    self.data[listpos] = temp
                else:
                    self.data.append(temp)
                    # if listpos<=1:
                    #   line = plot.PolyLine(temp,colour=self.colours[listpos], width=1)
                    #   self.plotmarkerlist.append(line)
                    #   marker = plot.PolyMarker(temp, marker='circle',colour=self.colours[listpos],width=1, size=1)
                    #   self.plotmarkerlist.append(marker)

            if self.fp:
                # print 'write data'
                self.fp.writelines(string + '\n')

            # resultstring=resultstring+string+'\n'

            for i, itemtoplot in enumerate(self.toplotlist):
                try:
                    datapos = self.availabledatalist.index(itemtoplot)
                except ValueError:
                    break
                # print datapos
                line = plot.PolyLine(self.data[datapos], colour=self.colours[i], width=1)
                self.plotmarkerlist.append(line)
                marker = plot.PolyMarker(self.data[datapos], marker='circle', colour=self.colours[i], width=1, size=1)
                self.plotmarkerlist.append(marker)

            try:
                self.resultqueue.put((self.plotmarkerlist, self.elliplist, self.connectlist), False)
            except queue.Full:
                # print 'WinPlot bmppaint thread is busy'
                pass

                # self.dataqueue.task_done()

    def writedatahead(self, fileinter, itemlist):
        string = ''
        for i in range(len(itemlist)):
            if i == 0:
                string = 'Time' + '\t'
            else:
                string += '\t'
            string += str(itemlist[i])
        fileinter.writelines(string + '\n')

    def getellipwithnum(self, liste, num):
        for listpos, item in enumerate(liste):
            epar = config.EllipPar()
            epar = liste[listpos]
            if epar.Num == num:
                return epar
        return None

    def getconnectwithnum(self, liste, num):
        for listpos, item in enumerate(liste):
            linepar = config.LinePar()
            linepar = liste[listpos]
            if linepar.Num == num:
                return linepar
        return None


class PlotWriteThread(threading.Thread):
    """Background Worker Thread Class."""

    def __init__(self, parent, pipeend, plotwritequeue):
        """Init Worker Thread Class."""
        threading.Thread.__init__(self)
        self.plotwritequeue = plotwritequeue
        self.parent = parent
        self.pipeend = pipeend
        self.setDaemon(True)
        self.start()
        self.elliplist = list()
        self.connectlist = list()

        self.plotlist = list()
        self.listlength = 0
        # start the thread

    def run(self):
        # print "Aquirethread started "+str(self.num)
        while True:
            # print 'running'
            # update WinPlot treecontrol

            self.plotlist, self.elliplist, self.connectlist = self.plotwritequeue.get()
            # print plotlist

            # check change in list lenght

            if self.listlength != len(self.elliplist) + len(self.connectlist):
                # print "rebuild tree items and send "
                self.parent.itemlist = list()
                self.parent.itemlist.extend(self.elliplist)
                self.parent.itemlist.extend(self.connectlist)
                self.parent.buildtreectrl()
                self.listlength = len(self.elliplist) + len(self.connectlist)

            if len(self.plotlist) > 0:
                panelwidth, panelheight = self.parent.panel.GetSize()
                self.parent.plotter.SetSize(size=(panelwidth, panelheight))
                # print'to gc'
                gc = plot.PlotGraphics(self.plotlist, '', 'Time [s]', '[pixel]')
                # print'draw'
                self.parent.plotter.Draw(gc)
                # print'finished'
                # self.plotwritequeue.task_done()

