import os
import threading
import Queue
import VideoCapture
from time import clock
#from time import sleep

import wx
import cv2
import numpy as np


# import globals
import config

ID_CAM = wx.NewId()
ID_FILE = wx.NewId()
ID_CNEXT = wx.NewId()
ID_CPROP = wx.NewId()

ID_LSERIES = wx.NewId()
ID_LFOLDER = wx.NewId()
ID_LMOVIE = wx.NewId()
ID_GOTHROUGH = wx.NewId()
# noinspection PyAttributeOutsideInit


class LiveCamWin(wx.Frame):
    def __init__(self, totrackqueue, pipetotrack):
        screensize = wx.Display().GetGeometry()
        wx.Frame.__init__(self, None, wx.ID_ANY, title='LiveCamWin', pos=(0, 0),
                          size=(screensize[2] / 2, screensize[3] / 2), style=wx.DEFAULT_FRAME_STYLE)
        self.status = self.CreateStatusBar()
        self.status.SetFieldsCount(2)
        self.status.SetStatusWidths([-1, 65])

        wx.EVT_CLOSE(self, self.onclose)

        # startwerte
        self.caminterface = None
        self.isfileinterface = False
        self.fileismovie = False
        self.datatoqueue = list()

        self.aquirequeue = Queue.Queue(3)
        self.totrackqueue = totrackqueue
        self.pipetotrack = pipetotrack
        self.bmppaintqueue = Queue.LifoQueue(1)

        self.lasttime = 0
        self.acttime = 0
        self.framecount = 0

        self.childs = list()
        self.panel = None

        self.pollpipetotracktimer = wx.Timer(self)
        self.Bind(wx.EVT_TIMER, self.pollpipetotrack, self.pollpipetotracktimer)
        self.pollpipetotracktimer.Start(20)

        self.initcam()

        self.createmenu()

        self.Show()

    def createmenu(self):
        self.Menubar = wx.MenuBar()
        source = wx.Menu()

        self.Menubar.Append(source, '&Source')
        source.Append(ID_CAM, '&Cam', 'Set Camera')
        source.Append(ID_FILE, '&File', 'Set file interface')

        self.Bind(wx.EVT_MENU, self.vidcapsetcamera, id=ID_CAM)
        self.Bind(wx.EVT_MENU, self.setfilemode, id=ID_FILE)

        if isinstance(self.caminterface, VideoCapture.Device):
            configmenu = wx.Menu()
            self.Menubar.Append(configmenu, '&Config')
            configmenu.Append(ID_CPROP, '&Properties', 'Camera Properties')
            self.Bind(wx.EVT_MENU, self.vidcapproperties, id=ID_CPROP)
            configmenu.Append(ID_CNEXT, '&Next CAM', 'next Camera')
            self.Bind(wx.EVT_MENU, self.initcam, id=ID_CNEXT)

        if self.isfileinterface:
            operate = wx.Menu()
            self.Menubar.Append(operate, '&Operate')
            operate.Append(ID_LSERIES, '&Load Series', 'Load image series')
            operate.Append(ID_LFOLDER, '&Load Directory', 'Load image series from Directory')
            operate.Append(ID_LMOVIE, '&Load Movie', 'Load movie from avi')
            operate.Append(ID_GOTHROUGH, '&Gothrough', 'Go through series')
            self.Bind(wx.EVT_MENU, self.loadseries, id=ID_LSERIES)
            self.Bind(wx.EVT_MENU, self.loaddir, id=ID_LFOLDER)
            self.Bind(wx.EVT_MENU, self.gothrough, id=ID_GOTHROUGH)
            self.Bind(wx.EVT_MENU, self.loadmovie, id=ID_LMOVIE)

        self.SetMenuBar(self.Menubar)

    def initcam(self):
        if self.initvidcapcamera():
            self.SetStatusText('VidCap Interface initiated ')
        else:
            if self.initopencvcamera():
                self.SetStatusText('OpenCV Interface initiated ')
            else:
                if self.initfileinterface():
                    self.SetStatusText('File Interface initiated ')

    def pollpipetotrack(self, event):
        if self.pipetotrack.poll():
            result = self.pipetotrack.recv()
            # print result
            if result == 'replot':
                if self.isfileinterface:
                    self.onslider(True, self.imageslider.GetValue())
            if result == 'Stop gothrough':
                self.goingthrough = False
            if result == 'Next Frame pls':
                if self.isfileinterface:
                    if self.goingthrough:
                        if self.imageslider.GetValue() < self.imageslider.GetMax():
                            self.onslider(True, self.imageslider.GetValue() + 1)
                        else:
                            self.goingthrough = False

    def cleanupbeforeinterfaceswitch(self):
        if isinstance(self.caminterface, VideoCapture.Device):
            # print 'stop aquiring'
            self.aquirequeue.put((self, self.caminterface, True))
            # print 'stopped aquiring'
            del self.caminterface
            self.caminterface = None
        if self.caminterface is not None:
            print 'stop aquiring'
            self.aquirequeue.put((self, self.caminterface, True))
            print 'stopped aquiring'
            # self.caminterface.release()
            del self.caminterface
            self.caminterface = None

        # kill threads

        for item in threading.enumerate():
            # print item
            if isinstance(item, VidCapQueuePicThread):
                # print 'found one! kill it!'
                self.aquirequeue.put((self, None, True))
                wx.Usleep(100)
                #sleep(0.1)
                self.aquirequeue.queue.clear()
                # print self.aquirequeue.queue
            if isinstance(item, CVCapQueuePicThread):
                # print 'found one! kill it!'
                self.aquirequeue.put((self, None, True))
                wx.Usleep(100)
                #sleep(0.1)
                self.aquirequeue.queue.clear()
                # print self.aquirequeue.queue
            if isinstance(item, QueuePicThread):
                # print 'found one! kill it!'
                self.aquirequeue.put((None, None, True))
                wx.Usleep(100)
                #sleep(0.1)
                self.aquirequeue.queue.clear()
                # print self.aquirequeue.queue
            if isinstance(item, WinCamBmpPaintThread):
                # print 'found one! kill it!'
                self.bmppaintqueue.put(None)
                wx.Usleep(100)
                #sleep(0.1)
                self.aquirequeue.queue.clear()

        if self.isfileinterface:
            # print 'delete widgets'
            self.imageslider.Destroy()
            self.sliderpanel.Destroy()
            self.sliderpanel = None
            self.filecapture = None
            self.isfileinterface = False
            self.fileismovie = False

        if isinstance(self.panel, wx.Panel):
            self.panel.Destroy()
            self.panel = None

    def initvidcapcamera(self, num=-1):
        # DirectShowDevice
        #return False

        if isinstance(self.caminterface, VideoCapture.Device):
            print 'cam active'
            for i in range(0, 2):
                nextcam = VideoCapture.Device(i)
                if self.caminterface != nextcam:
                    self.caminterface = nextcam

        self.cleanupbeforeinterfaceswitch()
        self.isfileinterface = False
        if num < 0:
            for i in range(0, 2):
                try:
                    self.caminterface = VideoCapture.Device(i)
                    # print 'a'
                    test = self.caminterface.getImage()
                    print test.size
                    # self.caminterface.setResolution(1000,1000)
                    break
                except:
                    print 'oh no no camera interface failed'
                    self.caminterface = None
                    continue
            if self.caminterface is None:
                return False
        else:
            try:
                self.caminterface = VideoCapture.Device(num)
                # print self.caminterface
            except:
                self.caminterface = None
                return False

        # self.ScaledImg=cv.CreateImage((100,100),8,3)
        self.ScaledImg = np.zeros((100, 100, 3), dtype=np.uint8)

        self.panel = wx.Panel(self, wx.ID_ANY, style=wx.BORDER_SUNKEN)
        self.panelsizer = wx.BoxSizer(wx.HORIZONTAL)
        self.panelsizer.Add(self.panel, 2, wx.EXPAND)
        self.SetSizer(self.panelsizer)

        self.Layout()
        self.createmenu()

        VidCapQueuePicThread(self.aquirequeue, self.bmppaintqueue, self.totrackqueue, 0)
        WinCamBmpPaintThread(self.bmppaintqueue, self.panel)
        # print threading.enumerate()

        # print 'start aquiring'
        self.aquirequeue.put((self, self.caminterface, False), False)
        return True

    def vidcapsetcamera(self, event):
        self.initvidcapcamera()

    def vidcapproperties(self, event):
        # stop aquiring
        self.aquirequeue.put((self, None, False), True)
        self.caminterface.displayCaptureFilterProperties()
        # start again
        self.aquirequeue.put((self, self.caminterface, False), True)

    def initopencvcamera(self):

        # return False
        self.caminterface = cv2.VideoCapture(0)
        if not self.caminterface.isOpened():
            self.SetStatusText('OpenCVCamera Initilization failed')
            return False

        width = self.caminterface.get(cv2.CAP_PROP_FRAME_WIDTH)
        height = self.caminterface.get(cv2.CAP_PROP_FRAME_HEIGHT)
        print self.caminterface.get(cv2.CAP_PROP_FORMAT)
        print self.caminterface.get(cv2.CAP_PROP_FPS)
        print self.caminterface.get(cv2.CAP_PROP_FRAME_COUNT)
        print self.caminterface.get(cv2.CAP_PROP_MODE)
        print self.caminterface.get(cv2.CAP_PROP_GAIN)

        print width, height

        self.ScaledImg = np.zeros((100, 100, 3), dtype=np.uint8)

        self.panel = wx.Panel(self, wx.ID_ANY, style=wx.BORDER_SUNKEN)
        self.panelsizer = wx.BoxSizer(wx.HORIZONTAL)
        self.panelsizer.Add(self.panel, 2, wx.EXPAND)
        self.SetSizer(self.panelsizer)

        self.Layout()
        self.createmenu()

        CVCapQueuePicThread(self.aquirequeue, self.bmppaintqueue, self.totrackqueue, 0)
        WinCamBmpPaintThread(self.bmppaintqueue, self.panel)

        self.aquirequeue.put((self, self.caminterface, False), True)
        return True

    def opencvcamprop(self, event):
        # is broken
        pass

    # print cv.GetCaptureProperty(self.CamInterface, cv.CV_CAP_PROP_FRAME_WIDTH)
    # print cv.GetCaptureProperty(self.CamInterface, cv.CV_CAP_PROP_FRAME_HEIGHT)
    # print cv.GetCaptureProperty(self.CamInterface, cv.CV_CAP_PROP_FORMAT)
    # print cv.GetCaptureProperty(self.CamInterface, cv.CV_CAP_PROP_FPS)
    # print cv.GetCaptureProperty(self.CamInterface, cv.CV_CAP_PROP_FRAME_COUNT)
    # print cv.GetCaptureProperty(self.CamInterface, cv.CV_CAP_PROP_MODE)
    # print cv.GetCaptureProperty(self.CamInterface, cv.CV_CAP_PROP_GAIN)

    def initfileinterface(self):

        self.cleanupbeforeinterfaceswitch()
        self.isfileinterface = True
        self.ismovie = False

        self.dirname = config.ProgDir
        # self.ScaledImg=cv.CreateImage((100,100),8,3)
        self.ScaledImg = np.zeros((100, 100, 3), dtype=np.uint8)

        self.Bind(wx.EVT_SCROLL_CHANGED, self.onslider)

        self.sliderpanel = wx.Panel(self, wx.ID_ANY)
        self.imageslider = wx.Slider(self.sliderpanel, wx.ID_ANY, 1, 100, 100000, (-1, -1), (-1, -1),
                                     wx.SL_AUTOTICKS | wx.SL_HORIZONTAL | wx.SL_LABELS | wx.BORDER_SUNKEN)
        # self.imageslider.Enable(False)
        self.slidersizer = wx.BoxSizer(wx.VERTICAL)
        self.slidersizer.Add(self.imageslider, 0, wx.EXPAND)
        self.sliderpanel.SetSizer(self.slidersizer)
        self.panel = wx.Panel(self, wx.ID_ANY, style=wx.NO_BORDER)

        self.panelsizer = wx.BoxSizer(wx.VERTICAL)
        self.panelsizer.Add(self.sliderpanel, 0, wx.EXPAND)
        self.panelsizer.Add(self.panel, 2, wx.EXPAND)

        self.SetSizer(self.panelsizer)

        self.goingthrough = False
        QueuePicThread(self.aquirequeue, self.bmppaintqueue, self.totrackqueue)
        WinCamBmpPaintThread(self.bmppaintqueue, self.panel)

        self.Layout()

        self.createmenu()
        return True

    def setfilemode(self, event):
        self.initfileinterface()
        self.imageslider.Enable(True)
        # print self.imageslider.Enabled

    def loadseries(self, event):

        filters = 'Image files (*.gif;*.png;*.jpg;*.tif;*.bmp)|*.gif;*.png;*.jpg;*.tif;*.bmp'
        dlg = wx.FileDialog(self, "Select files", self.dirname, "", filters, wx.FD_MULTIPLE)
        if dlg.ShowModal() == wx.ID_OK:
            try:

                self.filenames = dlg.GetFilenames()

                self.dirname = dlg.GetDirectory()
            except:
                dlg.Destroy()
                return False

            piccount = len(self.filenames)
            self.imageslider.SetMin(1)
            self.imageslider.SetMax(piccount)
            self.imageslider.SetValue(piccount)
            self.imageslider.Enable(True)
            dlg.Destroy()
            self.imageslider.SetValue(1)
            self.onslider(True)
        return True

    def loaddir(self, event):
        dlg = wx.DirDialog(self, "Select Directory", self.dirname, wx.DD_DEFAULT_STYLE | wx.DD_DIR_MUST_EXIST)
        if dlg.ShowModal() == wx.ID_OK:
            try:
                self.dirname = dlg.GetPath()
            except:
                dlg.Destroy()
                return False
            self.filenames = os.listdir(self.dirname)
            for item in self.filenames:
                filend = item[-4:].lower()
                if filend not in ('.tif', '.jpg', '.bmp', '.jpk', '.gif', '.png'):
                    self.filenames.remove(item)

            piccount = len(self.filenames)
            self.imageslider.SetMin(1)
            self.imageslider.SetMax(piccount)
            self.imageslider.SetValue(piccount)
            self.imageslider.Enable(True)
            dlg.Destroy()
            self.imageslider.SetValue(1)
            self.onslider(True)
        return True

    def loadmovie(self, event):
        filters = 'Video file (*.avi; *.mkv)|*.avi; *.mkv'
        dlg = wx.FileDialog(self, "Select files", self.dirname, "", filters, wx.FD_MULTIPLE)
        if dlg.ShowModal() == wx.ID_OK:
            try:

                self.filenames = dlg.GetFilenames()

                self.dirname = dlg.GetDirectory()
            except:
                dlg.Destroy()
                return False
        from os.path import abspath, join

        moviepath = abspath(join(self.dirname, self.filenames[0]))
        self.SetStatusText(moviepath)
        self.filecapture = cv2.VideoCapture(moviepath)
        piccount = int(self.filecapture.get(cv2.CAP_PROP_FRAME_COUNT))
        print self.filecapture.get(cv2.CAP_PROP_FORMAT)
        print self.filecapture.get(cv2.CAP_PROP_FOURCC)
        # next print must be called except image while be tiled

        print str(self.filecapture.get(cv2.CAP_PROP_FRAME_WIDTH)) + 'x' + str(
            self.filecapture.get(cv2.CAP_PROP_FRAME_HEIGHT))
        self.imageslider.SetMin(1)
        self.imageslider.SetMax(piccount - 1)
        self.imageslider.SetValue(piccount)
        self.imageslider.Enable(True)
        dlg.Destroy()
        self.imageslider.SetValue(1)
        self.fileismovie = True
        self.onslider(True)

    def onslider(self, event, picnum=None):
        # if event
        if picnum is None:
            picnum = (self.imageslider.GetValue())
        else:
            # print 'set value'
            self.imageslider.SetValue(picnum)
        # print picnum
        if self.fileismovie:
            self.filecapture.set(cv2.CAP_PROP_POS_FRAMES, picnum - 1)
            err, temp = self.filecapture.read()
            #print err
            #print temp.dtype
            self.image = np.copy(temp)
            print self.image.dtype,self.image.shape
            self.acttime = clock()
        else:
            from os.path import abspath, join

            # print self.dirname

            imagepath = abspath(join(self.dirname, self.filenames[picnum - 1]))
            self.SetStatusText(imagepath)
            self.image = cv2.imread(imagepath, 3)
            self.image = cv2.cvtColor(self.image, cv2.COLOR_BGR2RGB)

            self.acttime = clock()

        # print 'send file to aquire'
        self.aquirequeue.put((self.imageslider.GetValue(), self.image, False), False)

    def gothrough(self, event):
        self.onslider(True, self.imageslider.GetValue())
        self.goingthrough = True

    def onclose(self, event):
        if self.caminterface is not None:
            self.aquirequeue.put((self, None, False), False)
            wx.Usleep(300)
            #sleep(0.3)
        try:
            del self.caminterface
        except:
            print 'cant close cam interface'
            pass
        for item in self.childs:
            item.onclose(True)
        self.Destroy()


class QueuePicThread(threading.Thread):
    """Background Worker Thread Class."""

    def __init__(self, aquirequeue, bmppaintqueue, totrackqueue):
        """Init Worker Thread Class."""
        threading.Thread.__init__(self)
        self.aquirequeue = aquirequeue
        self.bmppaintqueue = bmppaintqueue
        self.totrackqueue = totrackqueue

        self.setDaemon(True)
        self.start()
        # start the thread

    def run(self):
        # print "Aquirethread started "
        while True:
            # print self.aquirequeue.queue
            (self.timestamp, image, plsexit) = self.aquirequeue.get(block=True)
            if plsexit:
                # print 'QueuePicThread exiting'
                break
            # print "Aquirethread got task"

            if len(image.shape) >= 3:
                self.gray = cv2.cvtColor(image, cv2.COLOR_RGB2GRAY)
                #print 'not gray'
            else:
                self.gray = image
                #print 'is gray'
            try:
                self.bmppaintqueue.put(image, False)
            except Queue.Full:
                pass
                print 'winCam1 bmppaintqueue is full'

            try:
                self.totrackqueue.put((self.timestamp, self.gray), False)
            except Queue.Full:
                pass
                # print 'totrackqueue is full'

            self.aquirequeue.task_done()


class VidCapQueuePicThread(threading.Thread):
    """Background Worker Thread Class."""

    def __init__(self, aquirequeue, bmppaintqueue, totrackqueue, num=0):
        """Init Worker Thread Class."""
        threading.Thread.__init__(self)
        self.aquirequeue = aquirequeue
        self.bmppaintqueue = bmppaintqueue
        self.totrackqueue = totrackqueue

        self.num = num
        self.caminterface = None
        self.lasthash = 0

        self.lasttime = 0
        self.framecount = 0
        self.plsexit = False

        self.setDaemon(True)
        self.start()
        # start the thread

    def run(self):
        # print "Aquirethread started "+str(self.num)
        parent = None

        while True:
            if not self.aquirequeue.empty():
                (parent, self.caminterface, self.plsexit) = self.aquirequeue.get(True)

            if self.plsexit:
                # print 'vidcap is exiting'
                break

            if self.caminterface is not None:
                rawdata = self.caminterface.getBuffer()  # datastring, width, height
                newhash = hash(rawdata)
                if newhash != self.lasthash:
                    self.lasthash = newhash
                    self.timestamp = clock()

                    if self.timestamp - self.lasttime < 1:
                        self.framecount += 1
                    else:
                        parent.SetStatusText('FPS: ' + str(self.framecount), 1)
                        self.framecount = 1
                        self.lasttime = self.timestamp

                    # create np array
                    temp_np = np.fromstring(rawdata[0], np.uint8)
                    np_temp = np.reshape(temp_np, (rawdata[2], rawdata[1], 3))
                    temp_np = cv2.flip(np_temp, 0)
                    temp_np = cv2.cvtColor(temp_np, cv2.COLOR_BGR2RGB)
                    self.gray = cv2.cvtColor(temp_np, cv2.COLOR_RGB2GRAY)

                    try:
                        # self.totrackqueue.put((self.timestamp,(self.raw.tostring(),self.raw.width,self.raw.height)),False)
                        self.totrackqueue.put((self.timestamp, self.gray), False)
                        # print self.timestamp
                    except Queue.Full:
                        pass
                        # print 'totrackqueue is full'

                    try:
                        # self.bmppaintqueue.put((temp),False)
                        self.bmppaintqueue.put(temp_np, False)
                    except Queue.Full:
                        pass
                        # print 'winCam bmppaintqueue3 is full'


class CVCapQueuePicThread(threading.Thread):
    """Background Worker Thread Class."""

    def __init__(self, aquirequeue, bmppaintqueue, totrackqueue, num=0):
        """Init Worker Thread Class."""
        threading.Thread.__init__(self)
        self.aquirequeue = aquirequeue
        self.bmppaintqueue = bmppaintqueue
        self.totrackqueue = totrackqueue

        self.num = num
        self.caminterface = None

        self.lasttime = 0
        self.framecount = 0
        self.plsexit = False

        self.setDaemon(True)
        self.start()
        print 'thread started'
        # start the thread

    def run(self):
        # print "Aquirethread started "+str(self.num)
        parent = None

        while True:
            rawdata = None
            if not self.aquirequeue.empty():
                (parent, self.caminterface, self.plsexit) = self.aquirequeue.get()

            if self.plsexit:
                # print 'vidcap is exiting'
                break
            if self.caminterface is not None:
                ret, newdata = self.caminterface.read()  # datastring, width, height
                # print ret
                if newdata is not rawdata:
                    rawdata = newdata
                    self.timestamp = clock()

                    if self.timestamp - self.lasttime < 1:
                        self.framecount += 1
                    else:
                        parent.SetStatusText('FPS: ' + str(self.framecount), 1)
                        self.framecount = 1
                        self.lasttime = self.timestamp

                    # create np array
                    # temp_np=np.fromstring(rawdata[0],np.uint8)
                    # np_temp=np.reshape(temp_np, (rawdata[2],rawdata[1],3))
                    # temp_np=cv2.flip(np_temp,0)
                    temp_np = cv2.cvtColor(rawdata, cv2.COLOR_BGR2RGB)
                    self.gray = cv2.cvtColor(temp_np, cv2.COLOR_RGB2GRAY)

                    try:
                        # self.totrackqueue.put((self.timestamp,(self.raw.tostring(),self.raw.width,self.raw.height)),False)
                        self.totrackqueue.put((self.timestamp, self.gray), False)
                        # print self.timestamp
                    except Queue.Full:
                        pass
                        # print 'totrackqueue is full'

                    try:
                        # self.bmppaintqueue.put((temp),False)
                        self.bmppaintqueue.put(temp_np, False)
                    except Queue.Full:
                        pass
                        # print 'winCam bmppaintqueue3 is full'


class WinCamBmpPaintThread(threading.Thread):
    """Background Worker Thread Class."""

    def __init__(self, bmppaintqueue, panel):
        """Init Worker Thread Class."""
        threading.Thread.__init__(self)
        self.bmppaintqueue = bmppaintqueue
        self.panel = panel

        # self.ScaledImg=cv.CreateImage((100,100),8,3)
        self.ScaledImg = np.zeros((100, 100), dtype=np.uint8)
        self.setDaemon(True)
        self.start()
        # start the thread
        self.panel.Bind(wx.EVT_PAINT, self.onpaint)

    def run(self):
        while True:
            self.image = self.bmppaintqueue.get()
            if not isinstance(self.image, np.ndarray):
                break
            self.resizeanddraw(self.panel, self.image)
            self.bmppaintqueue.task_done()

    def onpaint(self, event):
        # print 'Panel Paint event'
        try:
            self.resizeanddraw(self.panel, self.image)
        except:
            pass
        event.Skip()

    def resizeanddraw(self, panel, img):
        dc = wx.ClientDC(panel)
        panelwidth, panelheight = dc.GetSize()
        if (panelwidth <= 0) or (panelheight <= 0):
            return
        scaledimg = cv2.resize(img, (panelwidth, panelheight))
        if len(scaledimg.shape) >= 3:
            row, col, x = scaledimg.shape
            bitmap = wx.BitmapFromBuffer(col, row, scaledimg)
            dc.DrawBitmap(bitmap, 0, 0, False)
        else:
            row, col = scaledimg.shape
            # test=np.zeros((row,col), dtype=np.uint8)
            # print scaledimg.dtype
            test = cv2.cvtColor(scaledimg, cv2.COLOR_GRAY2RGB)
            bitmap = wx.BitmapFromBuffer(col, row, test)
            dc.DrawBitmap(bitmap, 0, 0, False)
        



