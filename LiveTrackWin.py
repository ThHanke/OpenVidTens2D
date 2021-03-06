# -*- coding: cp1252 -*-
import threading
import math
import pickle
import queue
import multiprocessing
from multiprocessing.pool import ThreadPool

import wx
import cv2
import numpy as np
import VideoWriter


# import globals
import config

# from time import sleep
from time import perf_counter

ID_CCAL = wx.NewId()
ID_CCALL = wx.NewId()
ID_CCALS = wx.NewId()
ID_PICKALL = wx.NewId()
ID_SRFACTOR = wx.NewId()
ID_VSTREAM = wx.NewId()
ID_RFRAMERATE = wx.NewId()


def contour_iterator(contour):
    while contour:
        yield contour
        contour = contour.h_next()


class LiveTrackWin(wx.Frame):
    def __init__(self, totrackqueue, toplotqueue, pipetocam, pipetoplot):
        self.totrackqueue = totrackqueue
        self.pipetocam = pipetocam
        self.pipetoplot = pipetoplot
        screensize = wx.Display().GetGeometry()
        wx.Frame.__init__(self, None, wx.ID_ANY, title='LiveTrackWin', pos=(screensize[2] / 2, 0),
                          size=(screensize[2] / 2, screensize[3] / 2), style=wx.DEFAULT_FRAME_STYLE ^ wx.CLOSE_BOX)
        self.status = self.CreateStatusBar()
        self.status.SetFieldsCount(2)
        self.status.SetStatusWidths([-1, 65])

        self.lasttime = 0
        self.acttime = 0
        self.framecount = 0

        self.panel = wx.Panel(self, wx.ID_ANY, style=wx.BORDER_SUNKEN)
        self.panelsizer = wx.BoxSizer(wx.HORIZONTAL)
        self.panelsizer.Add(self.panel, 2, wx.EXPAND)
        self.SetSizer(self.panelsizer)

        menu = self.createmenu()
        self.SetMenuBar(menu)

        self.Bind(wx.EVT_MENU, self.cameracalibration, id=ID_CCAL)
        self.Bind(wx.EVT_MENU, self.loadcalibration, id=ID_CCALL)
        self.Bind(wx.EVT_MENU, self.savecalibration, id=ID_CCALS)
        self.Bind(wx.EVT_MENU, self.pickall, id=ID_PICKALL)
        self.Bind(wx.EVT_MENU, self.changesrfactor, id=ID_SRFACTOR)
        self.Bind(wx.EVT_MENU, self.enablerecord, id=ID_VSTREAM)
        self.Bind(wx.EVT_MENU, self.reduceframerate, id=ID_RFRAMERATE)

        self.panel.Bind(wx.EVT_MOUSEWHEEL, self.mousewheel)
        self.panel.Bind(wx.EVT_ENTER_WINDOW, self.mouseinwindow)
        self.panel.Bind(wx.EVT_LEAVE_WINDOW, self.mouseoutwindow)
        self.panel.Bind(wx.EVT_LEFT_DOWN, self.mouseleftclick)
        self.panel.Bind(wx.EVT_RIGHT_DOWN, self.mouserightclick)
        self.panel.Bind(wx.EVT_MOTION, self.mousemove)
        self.panel.Bind(wx.EVT_RIGHT_UP, self.mouserightclick)


        # spawn queue

        self.bmpplotqueue = multiprocessing.Queue(1)
        self.toplotqueue = toplotqueue

        self.parentendpipe, self.childendpipe = multiprocessing.Pipe()

        self.UpdateInfoTimer = wx.Timer(self)
        self.Bind(wx.EVT_TIMER, self.updateinfo)
        self.UpdateInfoTimer.Start(20)

        # StartVariablen
        self.zoomval = 0

        self.zoomrect = None
        self.mousein = False
        self.newellip = None
        self.newcon = None
        self.timestamp = 0
        self.elliplist = list()
        self.connectlist = list()
        self.rightdown = False, (None, None), (None, None)
        self.PickAll = False
        self.framerate = None

        self.CalibData = CalibData()
        self.calibrated = False

        self.seachrectfactor = 15

        self.childs = list()

        #add an otional viewer for dev pupose
        # import wxImageView
        # self.tracktoview, self.viewtotrack = multiprocessing.Pipe()
        # self.viewqueue = multiprocessing.Queue(5)
        # self.TestView=wxImageView.Frame(self.viewqueue,self.viewtotrack)
        # self.childs.append(self.TestView)
        # ProcessPicThread(self.childendpipe, self.pipetoplot, self.totrackqueue, self.bmpplotqueue, self.toplotqueue, self.viewqueue)

        #without viever
        ProcessPicThread(self.childendpipe, self.pipetoplot, self.totrackqueue, self.bmpplotqueue, self.toplotqueue,
                         None)
        # init variables in backgroundprocess
        # self.sendstatustobackgroundprocess()

        WinTrackBmpPaintThread(self, self.bmpplotqueue, self.panel, 0)



        self.Show()

    def createmenu(self):
        menubar = wx.MenuBar()
        operate = wx.Menu()
        menubar.Append(operate, '&Operate')

        operate.Append(ID_CCALL, '&Load Calibration', 'Load camera calibration')
        operate.Append(ID_CCALS, '&Save Calibration', 'Save camera calibration')
        operate.Append(ID_CCAL, '&Calibration', 'Camera Calibration')
        operate.Append(ID_PICKALL, '&Pick All', 'Try to pick all ellipses')
        operate.Append(ID_SRFACTOR, '&SRFactor', 'Change SearchrectFaktor')
        operate.Append(ID_VSTREAM, '&Record Video', 'Save Live Stream when Capturing', kind=wx.ITEM_CHECK)
        operate.Append(ID_RFRAMERATE, '&Reduce Framerate', 'Reduce acquisition framerate')

        return menubar

    def replot(self):
        self.parentendpipe.send(('replot', None))

    def enablerecord(self, event):
        if event.IsChecked():
            self.parentendpipe.send('Enable Record')
        else:
            self.parentendpipe.send('Disable Record')

    def reduceframerate(self,event):
        framerate=wx.GetTextFromUser("Set framerate to [per second]", default_value='max')
        try:
            framerate=float(framerate)
        except ValueError:
            framerate='max'
        self.parentendpipe.send(('framerate', framerate))
        #print framerate, type(framerate)
        return

    def updateinfo(self, event):
        if self.parentendpipe.poll():
            msg = self.parentendpipe.recv()
            if msg == 'Successfully calibrated!':
                filecalib = open("Calibration.cal", 'r')
                self.CalibData.intrinsict, self.CalibData.distortion, self.CalibData.distanceunit = pickle.load(
                    filecalib)
                filecalib.close()
                self.SetStatusText(msg)
            if msg == 'Mark lost!':
                self.pipetocam.send('Stop gothrough')
                self.SetStatusText(msg)
            if msg == 'Frame processed!':
                self.pipetocam.send('Next Frame pls')

                # def sendstatustobackgroundprocess(self):
                # self.parentendpipe.send((self.newellip,self.pickall,self.rightdown,self.seachrectfactor,self.calibrate))

    def mousewheel(self, event):
        if self.mousein:
            pt = event.GetPosition()
            pos = self.panel2imagekoord(self.panel.Size[0], self.panel.Size[1], self.zoomrect, pt)
            rot = event.GetWheelRotation()
            rot = rot / event.GetWheelDelta()
            if self.zoomval + rot < 0:
                self.zoomval = 0
            else:
                self.zoomval += rot
            self.status.SetStatusText('Pos=' + str(pos) + ' Zoom=' + str(self.zoomval))
            # newzoomrect
            if self.zoomval > 0:
                width = int(float(self.imagetuple.shape[1]) / float(self.zoomval))
                height = int(float(self.imagetuple.shape[0]) / float(self.zoomval))
                orx = pos[0] - int(float(width) / 2)
                ory = pos[1] - int(float(height) / 2)
                self.zoomrect = (orx, ory, width, height)
                if not self.checksubrect(self.imagetuple, self.zoomrect):
                    self.zoomrect = self.getpropersubrect(self.imagetuple, self.zoomrect, True)
            else:
                self.zoomrect = (0, 0, self.imagetuple.shape[1], self.imagetuple.shape[0])
            self.replot()

    def mouseinwindow(self, event):
        self.mousein = True

    def mouseoutwindow(self, event):
        self.mousein = False

    def mouseleftclick(self, event):
        # print "left click"
        if self.mousein:
            pt = event.GetPosition()
            # get mouse pic koords
            self.newellip = self.panel2imagekoord(self.panel.Size[0], self.panel.Size[1], self.zoomrect, pt)
            self.parentendpipe.send(('New mark', self.newellip))
            # self.sendstatustobackgroundprocess()
            self.newellip = None

            self.replot()

    def mouserightclick(self, event):
        if event.RightDown() and self.mousein:
            pt = event.GetPosition()
            pos = self.panel2imagekoord(self.panel.Size[0], self.panel.Size[1], self.zoomrect, pt)
            # in ellip?
            self.rightdown = True, pos, pos
            # print self.rightdown
        if event.RightUp() and self.mousein:
            pt = event.GetPosition()
            # get mouse pic koords
            pos = self.panel2imagekoord(self.panel.Size[0], self.panel.Size[1], self.zoomrect, pt)
            self.rightdown = False, self.rightdown[1], pos
            # send to background process
            self.parentendpipe.send(('New connection', self.rightdown))
            # self.sendstatustobackgroundprocess()
            self.rightdown = False, (None, None), (None, None)
            # print self.rightdown

            self.replot()

    def mousemove(self, event):
        if self.mousein:
            if event.RightIsDown() and self.rightdown[0]:
                pt = event.GetPosition()
                # get mouse pic koords
                self.rightdown = True, self.rightdown[1], self.panel2imagekoord(self.panel.Size[0], self.panel.Size[1],
                                                                                self.zoomrect, pt)
                # print self.rightdown

                self.replot()

    def cameracalibration(self, event):
        # filters = 'Image files (*.gif;*.png;*.jpg;*.bmp)|*.gif;*.png;*.jpg;*.bmp'
        # print 'sendcommand'
        self.parentendpipe.send(('calibrate', None))
        # self.sendstatustobackgroundprocess()

    def savecalibration(self, event):

        directory = config.ProgDir
        filename = "Calibration.cal"
        dlg = wx.FileDialog(self, "Save camera calibration data as", directory, filename, 'cal files (*.cal)|*.cal',
                            wx.SAVE)
        if dlg.ShowModal() == wx.ID_OK:
            filename = dlg.GetFilename()
            directory = dlg.GetDirectory()
        dlg.Destroy()
        filecalib = open(filename, 'w')
        pickle.dump((self.CalibData.intrinsic, self.CalibData.distortion, self.CalibData.distanceunit), filecalib)
        filecalib.close()

    def loadcalibration(self, event):
        self.SetStatusText('Select file with intrinsic camera matrix')
        dlg = wx.FileDialog(self, "Select file with intrinsic camera matrix", config.ProgDir, "",
                            'cal files (*.cal)|*.cal', wx.FD_OPEN)
        if dlg.ShowModal() == wx.ID_OK:
            filename = dlg.GetFilenames()
            filecalib = open(filename[0], 'r')
            self.CalibData.intrinsic, self.CalibData.distortion, self.CalibData.distanceunit = pickle.load(filecalib)
            filecalib.close()
            dlg.Destroy()

            # self.calibrated=True
            # self.sendstatustobackgroundprocess()
            self.parentendpipe.send(('new calibration', (self.CalibData.intrinsic, self.CalibData.distortion)))
            # self.childs[0].sendstatustobackgroundprocess()
            self.SetStatusText('Calibration successfully loaded')
        else:
            wx.MessageBox('False Input!', style=wx.OK | wx.ICON_ERROR)

    def pickall(self, event):

        self.parentendpipe.send(('pick all marks', None))

    def changesrfactor(self, event):
        dlg = wx.NumberEntryDialog(self, 'Enter new SearchrectFactor', 'SRF:', 'SearchrectFactor', 15, 15, 50)
        if dlg.ShowModal() == wx.ID_OK:
            self.seachrectfactor = dlg.GetValue()
            # print self.seachrectfactor
            self.parentendpipe.send(('searchrectfactor', self.seachrectfactor))
            dlg.Destroy()

    def panel2imagekoord(self, panelwidth, panelheight, zoomrect, pt):
        pos = int(float(pt[0]) / float(panelwidth) * zoomrect[2] + zoomrect[0]), int(
            float(pt[1]) / float(panelheight) * zoomrect[3] + zoomrect[1])
        return pos

    def checksubrect(self, image, rect):
        if (rect[0] + rect[2]) <= image.shape[1] and (rect[1] + rect[3]) <= image.shape[0] and rect[0] >= 0 and rect[
                1] >= 0 and rect[2] >= 20 and rect[3] >= 20:
            return True
        else:
            return False

    def getpropersubrect(self, image, rect, keepsize):
        if not keepsize:
            if rect[0] < 0:
                orx = 0
            else:
                orx = rect[0]
            if rect[1] < 0:
                ory = 0
            else:
                ory = rect[1]
            if (rect[0] + rect[2]) > image.shape[1]:
                width = image.shape[1] - rect[0]

            else:
                width = rect[2]
            if (rect[1] + rect[3]) > image.shape[0]:
                height = image.shape[0] - rect[1]
            else:
                height = rect[3]
            rect = (orx, ory, width, height)
        else:
            if rect[0] < 0:
                orx = 0
            else:
                orx = rect[0]
            if rect[1] < 0:
                ory = 0
            else:
                ory = rect[1]
            if (rect[0] + rect[2]) > image.shape[1]:
                orx = image.shape[1] - rect[2]
            if (rect[1] + rect[3]) > image.shape[0]:
                ory = image.shape[0] - rect[3]
            rect = (orx, ory, rect[2], rect[3])
        return rect

    def getellipwithnum(self, liste, num):
        for listpos, item in enumerate(liste):
            epar = config.EllipPar()
            epar = liste[listpos]
            if epar.Num == num:
                return epar
        return None

    def getaabbellip(self, ellip):
        angle = -math.radians(ellip.Angle)
        if ellip.Size[0] < ellip.Size[1]:
            a = 2 * ellip.Size[1]
            b = 2 * ellip.Size[0]
        else:
            b = 2 * ellip.Size[1]
            a = 2 * ellip.Size[0]
        t = math.atan(-b * math.tan(angle) / a)
        x = abs(a * math.cos(t) * math.cos(angle) - b * math.sin(t) * math.sin(angle))
        t = math.atan(a * (1 / math.tan(angle)) / b)
        y = abs(b * math.sin(t) * math.cos(angle) + a * math.cos(t) * math.sin(angle))
        return y, x

    def posinfoundellip(self, pt, elliplist):
        for listpos, item in enumerate(elliplist):
            epar = config.EllipPar()
            epar = elliplist[listpos]
            b, h = self.getaabbellip(epar)
            rect = (int(epar.MidPos[0] - b / 2), int(epar.MidPos[1] - h / 2), int(b), int(h))
            if rect[0] < pt[0] < rect[0] + rect[2] and rect[1] < pt[1] < rect[1] + rect[3]:
                return True, epar.Num
        return False, None

    def numconnect(self, liste):
        posiblenum = range(len(liste) + 10)
        for listpos, item in enumerate(liste):
            linepar = config.LinePar()
            linepar = liste[listpos]
            posiblenum.remove(linepar.Num)
        return posiblenum[0]

    def onclose(self, event):
        # print 'closing TrackWin'
        self.parentendpipe.send('Exit')
        for item in self.childs:
            item.onclose(True)
        self.Destroy()


##
# noinspection PyAttributeOutsideInit
class ProcessPicThread(multiprocessing.Process):
	"""Background Worker Thread Class."""

	def __init__(self, pipeend, pipetoplot, piclistqueue, bmpplotqueue, resultqueuedata, viewqueue):
		"""Init Worker Thread Class."""
		multiprocessing.Process.__init__(self)
		self.pipeend = pipeend
		self.pipetoplot = pipetoplot
		self.queue = piclistqueue
		self.bmpqueue = bmpplotqueue
		self.out_queue2 = resultqueuedata
		self.viewqueue=viewqueue

		self.threadn = cv2.getNumberOfCPUs()

		self.recordstream = False
		self.capturing = False
		self.recordqueue = multiprocessing.Queue()
		self.replot = False

		self.framerate = 'max'
		self.lasttime = 0
		self.framecount = 0
		self.actframecount = 0

		self.lastcalibtime = 0

		self.seachrectfactor = 15

		self.elliplist = list()
		self.connectlist = list()
		self.intrinsic, self.distortion = None, None
		self.calibrated = False
		self.calibrate = False
		self.obj_points = []
		self.img_points = []
		self.raw = None
		self.videofilename = ''
		# self.daemon=True

		# chessbordprops
		self.calpicnum = 30  # Number of calpics
		self.chesssize = (9, 7)  # with,height,
		self.squaresize = 18  # in mm

		self.start()

		# start the thread

	def run(self):
		self.threadpool=ThreadPool(self.threadn)
		#self.threadpool = ThreadPool(1)
		#print 'created pool of ' + str(self.threadn) + ' workers!'
		while True:
			self.newelliplist = list()
			self.newconnectlist = list()

			# polling pipes

			if self.pipeend.poll():
				# self.newellip,self.pickall,self.rightdown,self.seachrectfactor,self.calibrate=self.pipeend.recv()
				msg = self.pipeend.recv()
				# print msg
				if msg[0] == 'replot':
					self.replot = True
					# print 'replot'
				if msg[0] == 'framerate':
					self.framerate=msg[1]
				if msg[0] == 'New mark':
					self.newellip = msg[1]
					# try to find a new ellip
					if self.newellip is not None:
						# check if in already found ellip
						isin, num = self.posinfoundellip(self.newellip, self.elliplist)
						if not isin:
							# print 'pick ellip'
							ellip = self.pickellip(self.raw, self.newellip[0], self.newellip[1], self.elliplist)
							if ellip is not None:

								if len(self.elliplist) <= ellip.Num:
									self.elliplist.append(ellip)
								else:
									# put in in right sequenz
									for listpos, item in enumerate(self.elliplist):
										if item.Num > ellip.Num:
											self.elliplist.insert(listpos, ellip)
											break

								# print 'new ellip found'
								self.pipeend.send('New Mark found!')
							self.newellip = None
				if msg[0] == 'New connection':
					# make a new connection
					# format ('New connection',(False/True,(P1),(P2)))
					if not msg[1][0] and msg[1][1] != (None, None) and msg[1][2] != (None, None):
						# print msg
						newcon = config.LinePar()
						isin, num = self.posinfoundellip(msg[1][1], self.elliplist)
						if isin:
							newcon.Pt1 = num
						else:
							newcon.Pt1 = None
						isin, num = self.posinfoundellip(msg[1][2], self.elliplist)
						if isin:
							newcon.Pt2 = num
						else:
							newcon.Pt2 = None

						if newcon.Pt1 != newcon.Pt2 and newcon.Pt1 is not None and newcon.Pt1 is not None:

							newcon.Num = self.numconnect(self.connectlist)
							# print "connection appended"
							self.pipeend.send('New connection in place!')

							if len(self.connectlist) <= newcon.Num:
								self.connectlist.append(newcon)
							else:
								# put in in right sequenz
								for listpos, item in enumerate(self.connectlist):
									if item.Num > newcon.Num:
										self.connectlist.insert(listpos, newcon)
										break

						if newcon.Pt1 == newcon.Pt2 and newcon.Pt1 is not None and newcon.Pt1 is not None:
							epar = self.getellipwithnum(self.elliplist, newcon.Pt1)
							self.elliplist.remove(epar)
							# print 'ellip removed'
							self.pipeend.send('Mark removed!')
				if msg[0] == 'calibrate':
					# print 'calibrate'
					self.calibrate = True
					continue

				if msg[0] == 'pick all marks':
					self.pickall(self.raw)

				if msg[0] == 'searchrectfactor':
					self.seachrectfactor = msg[1]
				if msg[0] == 'new calibration':
					self.intrinsic, self.distortion = msg[1]
					self.calibrated = True
					self.mapx, self.mapy = cv2.initUndistortRectifyMap(self.intrinsic, self.distortion, None,
																	   self.intrinsic,
																	   (self.raw.shape[1], self.raw.shape[0]),
																	   cv2.CV_32FC1)
					self.pipeend.send('Successfully loaded calibration!')
				if msg == 'Enable Record':
					self.recordstream = True
				if msg == 'Disable Record':
					self.recordstream = False
				if msg == 'Exit':
					self.threadpool.close()
					self.threadpool.join()
					# print 'killing process'
					break

			if self.pipetoplot.poll():
				msg = self.pipetoplot.recv()
				# print msg
				if msg[0] == 'Capturing':
					fourcc = cv2.VideoWriter_fourcc('D', 'I', 'B', ' ')
					#fourcc= -1
					# fourcc= cv2.VideoWriter_fourcc('X','2','6','4')
					name = msg[1].split('.', 1)[0]
					# print name
					self.videofilename = name
					# save last frame as overview of markers
					overview = np.copy(self.image)
					self.drawallmarks(overview, self.elliplist, self.connectlist)
					overview = cv2.cvtColor(overview, cv2.COLOR_BGR2RGB)
					cv2.imwrite(name + '_Overview' + '.png', overview)
					if self.recordstream:
						self.videowriterProcess = VideoWriter.VideoWriterProcess(self.videofilename, fourcc,
																				 self.recordqueue)
					self.capturing = True
				if msg == 'Stopped Capturing':
					if self.recordstream:

						self.recordqueue.put('TERMINATE')
						self.videofilepart = 1
					# print 'Stopped'
					self.capturing = False
			# try getting images

			if not self.replot:
				try:
					imagetuple = self.queue.get(False)
					#print type(imagetuple[1])
					self.timestamp = imagetuple[0]
					if isinstance(self.raw, np.ndarray):
						self.oldimage = np.copy(self.raw)
					else:
						self.oldimage = np.copy(imagetuple[1])
					self.raw = np.copy(imagetuple[1])
				except queue.Empty:
					#print 'no pic: i continue'
					continue

			temp = np.copy(self.raw)

			self.acttime = perf_counter()
			if self.framerate=='max':
				if self.acttime - self.lasttime < 1:
					self.framecount += 1
				else:
					# full second
					self.actframecount = self.framecount
					self.framecount = 1
					self.lasttime = self.acttime
			else:
				if self.acttime - self.lasttime < 1/self.framerate:
					continue
				else:
					self.actframecount =self.framerate
					self.lasttime = self.acttime


			if self.calibrated:
				# print 'remap'
				self.raw = cv2.remap(temp, self.mapx, self.mapy, cv2.INTER_LINEAR)
				# self.raw=cv2.undistort(temp,self.intrinsic,self.distortion)
			else:
				self.raw = temp

			self.image = cv2.cvtColor(self.raw, cv2.COLOR_GRAY2RGB)
			#self.image=self.raw

			if self.calibrate and self.lasttime != self.lastcalibtime:
				pattern_points = np.zeros((np.prod(self.chesssize), 3), np.float32)
				pattern_points[:, :2] = np.indices(self.chesssize).T.reshape(-1, 2)
				pattern_points *= self.squaresize

				# print len(self.obj_points)
				if len(self.obj_points) < self.calpicnum:
					self.lastcalibtime = self.lasttime
					# process pics

					# print 'try to find patern'
					found, corners = cv2.findChessboardCorners(self.raw, self.chesssize,
															   flags=cv2.CALIB_CB_ADAPTIVE_THRESH + cv2.CALIB_CB_NORMALIZE_IMAGE)

					if found != 0:
						# Get subpixel accuracy on those corners
						cv2.cornerSubPix(self.raw, corners, (11, 11), (-1, -1),
										 (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_COUNT, 30, 0.1))
						cv2.drawChessboardCorners(self.image, self.chesssize, corners, found)

						self.img_points.append(corners.reshape(-1, 2))
						self.obj_points.append(pattern_points)

				else:
					# datacollection complete
					rms1, intrinsic, distortion, rvecs, tvecs = cv2.calibrateCamera(self.obj_points, self.img_points, (
						self.raw.shape[1], self.raw.shape[0]), None, None, criteria=(
						cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_COUNT, 300, 1E-6),
						flags=cv2.CALIB_FIX_ASPECT_RATIO + cv2.CALIB_ZERO_TANGENT_DIST)

					# print 'save to file'
					filecalib = open("Calibration.cal", 'w')
					pickle.dump((intrinsic, distortion, (self.squaresize, 'mm')), filecalib)
					filecalib.close()

					self.mapx, self.mapy = cv2.initUndistortRectifyMap(intrinsic, distortion, None, intrinsic,
																	   (self.raw.shape[1], self.raw.shape[0]),
																	   cv2.CV_32FC1)
					self.calibrated = True
					self.calibrate = False
					self.obj_points = []
					self.img_points = []
					self.pipeend.send('Successfully calibrated!')
					self.lastcalibtime = 0

			# print self.newellip,self.pickall,self.rightdown,self.seachrectfactor
			if self.calibrated:
				if self.intrinsic is None and self.distortion is None:
					filecalib = open('Calibration.cal', 'r')
					intrinsic, distortion, distanceunit = pickle.load(filecalib)
					filecalib.close()
					self.mapx, self.mapy = cv2.initUndistortRectifyMap(intrinsic, distortion, None, intrinsic,
																	   (self.raw.shape[1], self.raw.shape[0]),
																	   cv2.CV_32FC1)
			else:
				self.intrinsic, self.distortion = None, None
				self.mapx, self.mapy = None, None

			# track all existing ellips
			# print self.elliplist

			#dont do anything if framerate is set and time between images is short



			if len(self.elliplist) > 0:
				self.newelliplist, self.newconnectlist, self.image = self.processimage(self.raw, self.elliplist,
																					   self.connectlist)
				# update elements
				if len(self.newelliplist) != len(self.elliplist):
					# we lost marks -> send a msg
					self.pipeend.send('Mark lost!')
				self.elliplist, self.connectlist = self.newelliplist, self.newconnectlist
			# capture videostream

			if self.recordstream and self.capturing:

				#if self.videowriter.isOpened():
				#self.videowriter.write(self.raw)
				if isinstance(self.videowriterProcess, VideoWriter.VideoWriterProcess):
					self.recordqueue.put(np.copy(self.raw))
					# print 'recording'
					# print self.videowriter
				#print self.raw.ndim

				# #print self.videopipe.poll()
				# #self.videopipe.stdin.write(self.raw.tostring())
				# self.videopipe.stdin.write(self.image.tostring())
				# # self.videopipe.communicate (self.raw.tostring())

			# show in frame - put it to paintqueue
			try:
				self.bmpqueue.put(
					(self.timestamp, self.image, self.newelliplist, self.newconnectlist, self.actframecount), False)
			except queue.Full:
				#print 'toplotqueue1 full'
				pass

			# show in winplot - put it to winplotqueue
			# print('putting new element to winplot')
			#self.out_queue2.put((self.timestamp, self.image, self.newelliplist, self.newconnectlist), False)
			try:
			   self.out_queue2.put((self.timestamp, self.image, self.newelliplist, self.newconnectlist), False)
			except queue.Full:
			   #print 'toplotqueue2 full'
			   pass

			self.replot = False
			# Frame is done let WinTrack know
			#comment out massiv framedrop and not necessary pipe is flooded with spam
			self.pipeend.send('Frame processed!')

	def drawoptflow(self, img, flow, step=16):
		h, w = img.shape[:2]
		y, x = np.mgrid[step / 2:h:step, step / 2:w:step].reshape(2, -1)
		fx, fy = flow[y, x].T
		lines = np.vstack([x, y, x + fx, y + fy]).T.reshape(-1, 2, 2)
		lines = np.int32(lines + 0.5)
		# vis = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
		vis = np.copy(img)
		cv2.polylines(vis, lines, 0, (255, 255, 255))
		# for (x1, y1), (x2, y2) in lines:
		# cv2.circle(vis, (x1, y1), 1,(0, 255, 0), -1)
		return vis

	def processimage(self, grayimage, ellipses, connections):
		# track ellipses
		ellipses, grayimage = self.trackellip(grayimage, ellipses)
		# print 'remove lost connections'
		for i in range(len(connections), 0, -1):
			linepar = config.LinePar()
			linepar = connections[i - 1]
			if self.getellipwithnum(ellipses, linepar.Pt1) is None or self.getellipwithnum(ellipses,
																						   linepar.Pt2) is None:
				# print "connection removed"
				connections.remove(linepar)
		rgbimage = cv2.cvtColor(grayimage, cv2.COLOR_GRAY2RGB)
		return ellipses, connections, rgbimage

	def pickellip(self, image, posx, posy, elliplist):
		firstsearchrectsize = 15
		searchrectsize = 2
		# print 'create memstorage'

		while True:
			# searchrectsize=int(searchrectsize+searchrectsize/10)
			searchrectsize = int(searchrectsize + firstsearchrectsize)
			# print searchrectsize

			searchrectr = (posx - searchrectsize, posy - searchrectsize, searchrectsize * 2, searchrectsize * 2)
			# print searchrectr

			if searchrectsize * 2 > image.shape[1]:
				break
			# print 'get search contour image'
			rectimage, searchrect = self.getsearchcounturimage(image, searchrectr)
			if not isinstance(rectimage, np.ndarray):
				continue

			# print 'search image created'
			if not isinstance(self.image, np.ndarray):
				continue
			# pixout,pixin=self.inoutval(rectimage)
			if cv2.countNonZero(rectimage) <= 10:
				continue

			#img2, contours, hier = cv2.findContours(rectimage, cv2.RETR_LIST, cv2.CHAIN_APPROX_TC89_KCOS)
			contours, hier = cv2.findContours(rectimage, cv2.RETR_LIST, cv2.CHAIN_APPROX_NONE)
			#print 'find contours'


			for contour in contours:
				# print contour

				if len(contour) >= 6:
					# print type(contour),len(contour)
					if cv2.contourArea(contour) <= (rectimage.shape[1] * rectimage.shape[0] / 50) or cv2.contourArea(
							contour) > (rectimage.shape[1] * rectimage.shape[0] / 2):
						continue
					# print 'process contours'
					# Fits ellipse to current contour.
					ellipparnew = self.fitelliponcontour(contour)

					# define Number
					ellipparnew.Num = self.numellip(elliplist)
					# korrekt pos and size to global
					ellipparnew.MidPos = ellipparnew.MidPos[0] / rectimage.shape[1] * searchrect[2] + searchrect[0], \
						ellipparnew.MidPos[1] / rectimage.shape[0] * searchrect[3] + searchrect[1]
					ellipparnew.Size = ellipparnew.Size[0] / rectimage.shape[1] * searchrect[2], ellipparnew.Size[1] / \
						rectimage.shape[0] * searchrect[3]

					# EllipParnew.Angle=-EllipParnew.Angle
					ellipparnew.mov = 0, 0

					b, h = self.getaabbellip(ellipparnew)

					left = int(ellipparnew.MidPos[0] - b / 2)
					low = int(ellipparnew.MidPos[1] - h / 2)

					# check if ellip is in searchrect
					if left > searchrect[0] and low > searchrect[1] and b < searchrect[2] and h < searchrect[3]:
						# check if ellip is bigger then 1/5 of searchrect size
						if b > searchrect[2] / 5 and h > searchrect[3] / 5:
							# check if movment is not too big
							# print EllipParnew.mov,ellip.mov
							# if (EllipParnew.mov[0]-ellip.mov[0]>EllipParnew.Size[0]/2)
							#       or (EllipParnew.mov[1]-ellip.mov[1]>EllipParnew.Size[0]/2):
							# print 'to fast to be true'
							# continue
							# cv2.rectangle(self.image,(searchrecttr[0],searchrecttr[1]),(int(searchrecttr[0]+searchrecttr[2]),int(searchrecttr[1]+searchrecttr[3])),(0,255,0),1)
							print('found')
							ellipparnew.searchrect = searchrect

							return ellipparnew
						else:
							# print 'ellip smaller then 1/5 of searchrect'
							pass
					else:
						# print 'ellip not in searchrect'
						pass

		return None

	def pickall(self, gray):
		circles = cv2.HoughCircles(gray, cv2.HOUGH_GRADIENT, 2, int(gray.shape[1] / 25), 192, 50,
								   int(gray.shape[0] / 150),int(gray.shape[0] / 5))
		#print circles

		for i in circles[0, :]:
			ellip = self.pickellip(self.raw, int(i[0]), int(i[1]), self.elliplist)
			if ellip is not None:
				#print self.posinfoundellip(ellip.MidPos,self.elliplist)[0]
				if not self.posinfoundellip(ellip.MidPos,self.elliplist)[0]:
					# print 'is regular ellip'
					self.elliplist.append(ellip)

	def trackellip(self, image, ellipses):
		elliplistnew = list()
		# print len(ellipses)
		tasklist = list()
		# print 'start tracking'
		# start = perf_counter()
		for listpos, item in enumerate(ellipses):
			# print 'track ellip'

			triedtorescue = False
			ellip = config.EllipPar()

			ellip = ellipses[listpos]

			b, h = self.getaabbellip(ellip)

			b, h = int(b * self.seachrectfactor / 10), int(h * self.seachrectfactor / 10)

			if b < 10:
				b = 10
			if h < 10:
				h = 10
			# print b,h

			# with movement correction
			# firstsearchrect = (int(ellip.MidPos[0]+int(ellip.mov[0])-b/2),
			#   int(ellip.MidPos[1]+int(ellip.mov[1])-h/2),int(b),int(h))

			# try to get opt flow of region and determine movement of ellip

			try:
				flowrectscale = 4
				flowrect = (int(ellip.MidPos[0] - b / 2 * flowrectscale), int(ellip.MidPos[1] - h / 2 * flowrectscale),
							int(b * flowrectscale), int(h * flowrectscale))
				# make sure its not bigger then image
				flowrect = self.getpropersubrect(image, flowrect, True)
				# scale down to make it faster
				# oldimg = cv2.resize(
				#     self.oldimage[flowrect[1]:flowrect[1] + flowrect[3], flowrect[0]:flowrect[0] + flowrect[2]], None,
				#     fx=0.25, fy=0.25)
				# newimg = cv2.resize(
				#     self.raw[flowrect[1]:flowrect[1] + flowrect[3], flowrect[0]:flowrect[0] + flowrect[2]], None,
				#     fx=0.25, fy=0.25)
				# print 'get views for flow'
				# print (perf_counter() - start) * 1000
				#only get reduced size
				scale=flowrect[2]//20
				oldimg = self.oldimage[flowrect[1]:flowrect[1] + flowrect[3]:scale, flowrect[0]:flowrect[0] + flowrect[2]:scale]
				newimg = self.raw[flowrect[1]:flowrect[1] + flowrect[3]:scale, flowrect[0]:flowrect[0] + flowrect[2]:scale]
				#print oldimg.shape
				# print 'got views'
				# print (perf_counter() - start) * 1000
				flow = cv2.calcOpticalFlowFarneback(oldimg, newimg, None, 0.5, 3, 15, 3, 5, 1.2, 0)
				# print 'calculated opt flow'
				# print (perf_counter() - start) * 1000

				# x,y=int(newimg.shape[1]/2),int(newimg.shape[0]/2)
				# fx, fy = flow[y,x].T
				# fxm,fym=flow[:,:,0].mean(),flow[:,:,1].mean()
				fxmean, fymean = 4 * flow[int(flow.shape[0] / 2 - 2):int(flow.shape[0] / 2 + 2),
									 int(flow.shape[1] / 2 - 2):int(flow.shape[1] / 2 + 2), 0].mean(),\
								 4 * flow[int(flow.shape[0] / 2 - 2):int(flow.shape[0] / 2 + 2),
									 int(flow.shape[1] / 2 - 2):int(flow.shape[1] / 2 + 2), 1].mean()
				# print fx, fy,flow[int(flow.shape[0]/2-2):int(flow.shape[0]/2+2),int(flow.shape[1]/2-2):int(flow.shape[1]/2+2),0].mean(),flow[int(flow.shape[0]/2-2):int(flow.shape[0]/2+2),int(flow.shape[1]/2-2):int(flow.shape[1]/2+2),1].mean()

				# print ellip.mov[0],ellip.mov[1],fxmean,fymean
				firstsearchrect = (
					int(ellip.MidPos[0] + int(fxmean) - b / 2), int(ellip.MidPos[1] + int(fymean) - h / 2), int(b),
					int(h))
				# newimg=self.drawoptflow(newimg,flow,int(newimg.shape[1]/10))
				# image[flowrect[1]:flowrect[1]+flowrect[3], flowrect[0]:flowrect[0]+flowrect[2]]=cv2.resize(newimg,None,fx=4,fy=4)
				rectlist = self.searchrectlist(firstsearchrect, (fxmean, fymean))
			except:
				firstsearchrect = (int(ellip.MidPos[0] - b / 2), int(ellip.MidPos[1] - h / 2), int(b), int(h))
				rectlist = self.searchrectlist(firstsearchrect, (0, 0))
			# print 'calculated flows'
			# print (perf_counter()-start)*1000
			task = self.threadpool.apply_async(self.findellip, (rectlist, ellip, image))
			tasklist.append(task)
		##            ellipnew=self.findellip(rectlist,ellip,image)
		##            #print ellipnew
		##            if ellipnew!=None:
		##                #print ellipnew.mov[0],ellipnew.mov[1],fxmean,fymean,fx,fy
		##                #print ellipnew.mov[0]-fxmean,ellipnew.mov[1]-fymean,ellipnew.mov[0]-fx,ellipnew.mov[1]-fy,ellipnew.mov[0]-fxm,ellipnew.mov[1]-fym
		##                elliplistnew.append(ellipnew)
		##            else:
		##                #print 'lost mark'
		##                pass
		##
		# print 'tasks set'
		# print (perf_counter()-start)*1000
		for task in tasklist:
			#task.wait()  # wait till task is completed and result available
			# print task.get()
			ellipnew = task.get()
			if ellipnew is not None:
				if not self.posinfoundellip(ellipnew.MidPos,elliplistnew)[0]:
					elliplistnew.append(ellipnew)
			else:
				# print 'lost mark'
				pass

				# for rect in rectlist:
				# cv2.rectangle(image,(rect[0],rect[1]),(int(rect[0]+rect[2]),int(rect[1]+rect[3])),(255,255,255),1)

		# print 'copy list'
		# print 'got all results'
		# print (perf_counter()-start)*1000
		return elliplistnew, image

	def findellip(self, rectlist, ellip, image):
		#print "try to find ellip"
		for pos, rect in enumerate(rectlist):
			#print pos
			scale=1
			rectimage, searchrect = self.getsearchcounturimage(image, rect,scale)
			if not isinstance(rectimage, np.ndarray):
				print('no image returned from getsearchcounturimage')
				continue

			# if cv2.countNonZero(rectimage)<=10:
			# continue
			#self.viewqueue.put((0, rectimage), False)

			#im2, contours, hier =cv2.findContours(rectimage.copy(), cv2.RETR_LIST,cv2.CHAIN_APPROX_TC89_KCOS)
			contours, hier = cv2.findContours(rectimage.copy(), cv2.RETR_LIST,cv2.CHAIN_APPROX_NONE)
			#im2, contours, hier = cv2.findContours(rectimage.copy(), cv2.RETR_CCOMP, cv2.CHAIN_APPROX_TC89_KCOS)
			#contimage = np.zeros_like(rectimage)
			#print contimage.dtype
			#cv2.drawContours(contimage, contours, -1, (255, 255, 255))
			# hier[3] is here always -1 for white spots on black ground and 0 for black spots on white ground
			# print hier
			i=0
			for contour in contours:
				i+=1
				if len(contour) <= 5:
					print('too few countour points')
					continue

				if cv2.contourArea(contour) <= (rectimage.shape[1] * rectimage.shape[0] / 20):
					print('contour area to small')
					continue
				if cv2.contourArea(contour) > (rectimage.shape[1] * rectimage.shape[0]):
					print('contour area to big')
					continue

				# find bounding box of contour
				conrect = cv2.boundingRect(contour)
				# # print conrect
				# cv2.rectangle(contimage, (conrect[0], conrect[1]), (conrect[0] + conrect[2], conrect[1] + conrect[3]),
				#               (125, 255, 125))
				# # print self.checksubrect(contimage,conrect)
				#print i
				arcscale=cv2.arcLength(contour,True)/(2*(conrect[2]+conrect[3]))
				if arcscale>=0.9 or arcscale<0.3:
					print('skipped')
					continue


				# Fits ellipse to current contour.

				ellipparnew = self.fitelliponcontour(contour)

				#show filtered image in viewer
				#self.viewqueue.put((0,contimage),False)

				if conrect[0] < 0 or conrect[1] < 0 or conrect[0] + conrect[2] >= rectimage.shape[1] or \
					conrect[1] + conrect[3] >= rectimage.shape[0] or conrect[2] < (
						rectimage.shape[1] / 3) or conrect[3] < (rectimage.shape[0] / 3):
					print('fitted shape in contact with border or excedes')
					continue
				else:
					# define Number
					ellipparnew.Num = ellip.Num
					# korrekt pos and size to global
					ellipparnew.MidPos = ellipparnew.MidPos[0] / rectimage.shape[1] * searchrect[2] + searchrect[0], \
						ellipparnew.MidPos[1] / rectimage.shape[0] * searchrect[3] + searchrect[1]
					ellipparnew.Size = ellipparnew.Size[0] / rectimage.shape[1] * searchrect[2], ellipparnew.Size[1] / \
						rectimage.shape[0] * searchrect[3]

					# EllipParnew.Angle=-EllipParnew.Angle
					ellipparnew.mov = ellipparnew.MidPos[0] - ellip.MidPos[0], ellipparnew.MidPos[1] - ellip.MidPos[1]

					#print 'found'
					ellipparnew.searchrect = searchrect
					#print cv2.isContourConvex(contour)
					return ellipparnew
		return None

	def drawallmarks(self, image, ellipses, connections):
		# first ellipses

		for listpos, item in enumerate(ellipses):
			ellippar = config.EllipPar()
			ellippar = ellipses[listpos]
			# determine thickness of mark
			thickness = (int((ellippar.Size[0] + ellippar.Size[1]) / 40))

			self.drawellipmark(image, ellippar, 255, 0, 0, thickness)

		# second connections

		for listpos, item in enumerate(connections):

			linepar = config.LinePar()
			linepar = connections[listpos]
			epar1 = self.getellipwithnum(ellipses, linepar.Pt1)
			epar2 = self.getellipwithnum(ellipses, linepar.Pt2)

			cv2.line(image, (int(epar1.MidPos[0]), int(epar1.MidPos[1])), (int(epar2.MidPos[0]), int(epar2.MidPos[1])),
					 (0, 0, 255), 1)

			rx, ry = abs(epar1.MidPos[0] - epar2.MidPos[0]), abs(epar1.MidPos[1] - epar2.MidPos[1])
			if epar1.MidPos[0] < epar2.MidPos[0]:
				posx = int(epar1.MidPos[0] + rx / 2)
			else:
				posx = int(epar2.MidPos[0] + rx / 2)
			if epar1.MidPos[1] < epar2.MidPos[1]:
				posy = int(epar1.MidPos[1] + ry / 2)
			else:
				posy = int(epar2.MidPos[1] + ry / 2)

			cv2.putText(image, 'C%d' % linepar.Num, (posx, posy), cv2.FONT_HERSHEY_COMPLEX, 1, (0, 0, 255), 1)

	def drawellipmark(self, image, epar, color1, color2, color3, thickness):
		b, h = self.getaabbellip(epar)
		b, h = int(b * 1.5), int(h * 1.5)
		if b < 20:
			b = 20
		if h < 20:
			h = 20

		posx = int(epar.MidPos[0] - b / 2)
		posy = int(epar.MidPos[1] - h / 2)
		cv2.rectangle(image, (posx, posy), (int(posx + b), int(posy + h)), (color1, color2, color3), thickness)
		cv2.ellipse(image, (int(epar.MidPos[0]), int(epar.MidPos[1])), (int(epar.Size[0] / 2), int(epar.Size[1] / 2)),
					epar.Angle, 0, 360, (color1, color2, color3), thickness)
		cv2.line(image, (int(epar.MidPos[0] - b / 2), int(epar.MidPos[1])),
				 (int(epar.MidPos[0] + b / 2), int(epar.MidPos[1])), (color1, color2, color3), thickness)
		cv2.line(image, (int(epar.MidPos[0]), int(epar.MidPos[1] - h / 2)),
				 (int(epar.MidPos[0]), int(epar.MidPos[1] + h / 2)), (color1, color2, color3), thickness)
		cv2.putText(image, '%d' % epar.Num, (int(posx + b), int(posy + h)), cv2.FONT_HERSHEY_COMPLEX, 1,
					(color1, color2, color3), thickness)

		# add movement vectors

		if epar.mov[0] != 0 and epar.mov[1] != 0:
			# start and endpoint

			p1 = epar.MidPos[0], epar.MidPos[1]
			p2 = epar.MidPos[0] - epar.mov[0], epar.MidPos[1] - epar.mov[1]

			angle = math.atan2((p1[1] - p2[1]), (p1[0] - p2[0]))
			lenght = math.sqrt((p1[0] - p2[0]) ** 2 + (p1[1] - p2[1]) ** 2)

			# enlongen vector

			p2 = p1[0] - 10 * lenght * math.cos(angle), p1[1] - 10 * lenght * math.sin(angle)
			p5 = p1[0] - thickness * math.cos(angle), p1[1] - thickness * math.sin(angle)

			# draw main line

			cv2.line(image, (int(p5[0]), int(p5[1])), (int(p2[0]), int(p2[1])), (color1, 255, color3), thickness)

	def getellipwithnum(self, liste, num):
		for listpos, item in enumerate(liste):
			epar = config.EllipPar()
			epar = liste[listpos]
			if epar.Num == num:
				return epar
		return None

	def posinfoundellip(self, pt, elliplist):
		for listpos, item in enumerate(elliplist):
			epar = config.EllipPar()
			epar = elliplist[listpos]
			b, h = self.getaabbellip(epar)
			rect = (int(epar.MidPos[0] - b / 2), int(epar.MidPos[1] - h / 2), int(b), int(h))
			if rect[0] < pt[0] < rect[0] + rect[2] and rect[1] < pt[1] < rect[1] + rect[3]:
				return True, epar.Num
		return False, None

	def fitelliponcontour(self, contour):
		# scale=len(contour)//50
		# if scale>1:
		#     tofit = np.copy(contour[::scale, ::1, ::1])
		# else:
		#     tofit = contour
		# box = cv2.fitEllipse(tofit)
		box = cv2.fitEllipse(contour)
		# print box
		epar = config.EllipPar()
		epar.MidPos = box[0]
		epar.Size = box[1]
		epar.Angle = box[2]
		return epar

	def rescuelist(self, searchrect, mov):
		# make searchrect bigger and move around
		rectlist = list()
		factors = range(1, 3)
		bfactors = range(1, 5)

		rectlist.append(searchrect)

		# serchrect in first track try
		# b,h=self.getaabbellip(ellip)
		# b,h=int(b*self.seachrectfactor/10),int(h*self.seachrectfactor/10)
		# searchrecttr = (int(ellip.MidPos[0]+int(ellip.mov[0])-b/2),int(ellip.MidPos[1]+int(ellip.mov[1])-h/2),int(b),int(h))

		for factor in factors:
			teilen = 24
			# teilen=8
			for bfactor in bfactors:

				radius = (searchrect[2] + searchrect[3]) / 30.0 * bfactor
				# radius=(math.sqrt(mov[0]**2+mov[1]**2))/5.0*bfactor
				newb = int(searchrect[2] * (0.9 + 0.05 * factor))
				newh = int(searchrect[3] * (0.9 + 0.05 * factor))

				temp = int(searchrect[0] - int((newb - searchrect[2]) / 2.0)), searchrect[1] - int(
					(newh - searchrect[3]) / 2.0), newb, newh
				rectlist.append(temp)

				temp = searchrect[0] - int((newb - searchrect[2]) / 2.0 + radius), searchrect[1] - int(
					(newh - searchrect[3]) / 2.0), newb, newh
				rectlist.append(temp)
				for i in range(teilen):
					winkel = i * 360.0 / teilen

					pox = searchrect[0] + int(searchrect[2] / 2.0) + int(math.cos(winkel) * radius)
					poy = searchrect[1] + int(searchrect[3] / 2.0) - int(math.sin(winkel) * radius)
					temp = int(pox - int(newb / 2.0)), int(poy - int(newh / 2.0)), newb, newh
					rectlist.append(temp)

		return rectlist

	def rescuelist2(self, searchrect, mov):
		# make searchrect move around in circular
		rectlist = list()
		# factors=range(1,5)
		bfactors = range(1, 20)

		# serchrect in first track try
		# b,h=self.getaabbellip(ellip)
		# b,h=int(b*self.seachrectfactor/10),int(h*self.seachrectfactor/10)
		# searchrecttr = (int(ellip.MidPos[0]+int(ellip.mov[0])-b/2),int(ellip.MidPos[1]+int(ellip.mov[1])-h/2),int(b),int(h))

		teilen = 16
		# teilen=8
		for bfactor in bfactors:

			radius = (math.sqrt(mov[0] ** 2 + mov[1] ** 2)) / 10.0 * bfactor
			newb = searchrect[2]
			newh = searchrect[3]

			temp = int(searchrect[0] + radius), searchrect[1], newb, newh
			rectlist.append(temp)
			for i in range(teilen):
				winkel = i * 360.0 / teilen

				pox = searchrect[0] + math.cos(winkel) * radius
				poy = searchrect[1] - math.sin(winkel) * radius
				temp = int(pox), int(poy), newb, newh
				rectlist.append(temp)

		return rectlist

	def searchrectlist(self, searchrect, mov):
		# make searchrect in movement direction and make it slightly bigger the bigger distance
		rectlist = list()

		# add original rect
		rectlist.append(searchrect)
		# rectlist=self.rescuelist(searchrect,mov)

		return rectlist

	def rescuelist4(self, searchrect, mov):
		# make searchrect move around in circular
		rectlist = list()
		# factors=range(1,5)
		bfactors = range(1, 20)

		# serchrect in first track try
		# b,h=self.getaabbellip(ellip)
		# b,h=int(b*self.seachrectfactor/10),int(h*self.seachrectfactor/10)
		# searchrecttr = (int(ellip.MidPos[0]+int(ellip.mov[0])-b/2),int(ellip.MidPos[1]+int(ellip.mov[1])-h/2),int(b),int(h))

		teilen = 12
		# teilen=8
		for bfactor in bfactors:

			radius = (searchrect[2] + searchrect[3]) / 2.0 / 3.0 * bfactor / 20
			newb = searchrect[2]
			newh = searchrect[3]

			temp = int(searchrect[0] + radius), searchrect[1], newb, newh
			rectlist.append(temp)
			for i in range(teilen):
				winkel = i * 360.0 / teilen

				pox = searchrect[0] + math.cos(winkel) * radius
				poy = searchrect[1] - math.sin(winkel) * radius
				temp = int(pox), int(poy), newb, newh
				rectlist.append(temp)

		return rectlist

	def getaabbellip(self, ellip):
		angle = -math.radians(ellip.Angle)
		if ellip.Size[0] < ellip.Size[1]:
			a = ellip.Size[1]
			b = ellip.Size[0]
		else:
			b = ellip.Size[1]
			a = ellip.Size[0]
		if angle == 0:
			x = a
			y = b
		else:
			if math.tan(angle)==0.0:
				t=0
				x=abs(a * math.cos(t) * math.cos(angle) - b * math.sin(t) * math.sin(angle))
				t=math.atan(a * (1 / 1E-9) / b)
				y = abs(b * math.sin(t) * math.cos(angle) + a * math.cos(t) * math.sin(angle))
			else:
				t = math.atan(-b * math.tan(angle) / a)
				x = abs(a * math.cos(t) * math.cos(angle) - b * math.sin(t) * math.sin(angle))
				t = math.atan(a * (1 / math.tan(angle)) / b)
				y = abs(b * math.sin(t) * math.cos(angle) + a * math.cos(t) * math.sin(angle))
		# print ellip.Size[0],ellip.Size[1],y,x, angle

		return y, x

	def getsearchcounturimage(self, image, rect,scale=1):
		# check subrect is in image
		if not self.checksubrect(image, rect):
			print('checksubrect failed')
			return None, rect
		else:
			# print 'copy subimage'
			temp = image[rect[1]:(rect[1] + rect[3]), rect[0]:(rect[0] + rect[2])]
			# print 'image mid pos'
			# print  rect[1]+rect[3]/2,rect[0]+rect[2]/2

			pyrimage = cv2.pyrUp(temp)
			temp = cv2.pyrDown(pyrimage)


			thresimg = cv2.resize(temp, (temp.shape[1] * scale, temp.shape[0] * scale), interpolation=cv2.INTER_CUBIC)
			# get threshold value
			#Methode 1
			pixin, pixout = self.inoutval(temp)
			if abs(pixin - pixout) < 10:
			   # print 'grayscale gradient <10'
			   return None, None
			ret, thresimg = cv2.threshold(thresimg, int((pixin + pixout) / 2), 255, cv2.THRESH_BINARY)

			#Methode 2
			#ret,thresimg=cv2.threshold(thresimg,0,255,cv2.THRESH_BINARY+cv2.THRESH_OTSU)


			# print 'return subimage'
			return thresimg, rect

	def inoutval(self, img):
		height,width=img.shape[0],img.shape[1]
		y,x = np.ogrid[-int(height/3)-1:height-int(height/3)-1,-int(width/3)-1:width-int(width/3)-1,]
		img_mask = ellipse(0,0,int(width/3),int(height/3),0,x,y)
		#outer value
		img_masked=np.ma.array(img, mask=img_mask)
		thres_in=img_masked.mean()
		img_masked=np.ma.array(img, mask=np.logical_not(img_mask))
		thres_out=img_masked.mean()
		#print thres_out,thres_in

		return thres_out, thres_in



		# width = img.shape[1]
		# height = img.shape[0]
		#
		# pixout = img[0:2, width - 2:width].mean() + img[height - 2:height, width - 2:width].mean() \
		#          + img[0:height, 0:2].mean() + img[0:height, width - 2:width].mean()
		# pixout = int(pixout / 4)
		# # print 'some values'
		# # print img[0,0],img[0,1],img[1,0],img[0,width-1],img[1,width-1],img[0,width-2]
		#
		# pixin = int(img[int(height / 2) - int(height / 5):int(height / 2) + int(height / 5), int(width / 2) - int(width / 5):int(width / 2) + int(width / 5)].mean())
		# #pixin = int(img[int(height / 2) - 5:int(height / 2) + 5, int(width / 2) - 5:int(width / 2) + 5].mean())
		# # print 'some values'
		# # print img[int(height/2),int(width/2)],img[int(height/2)+1,int(width/2)],img[int(height/2),int(width/2)+1],img[int(height/2)+1,int(width/2)+1]
		#
		# # print'pixout/in
		# # print pixout,pixin
		# return pixout, pixin

	def numellip(self, elliplist):
		ellipnumbers=set()
		checknumbers=set(range(len(elliplist)+1))
		for listpos, item in enumerate(elliplist):
			ellippar = config.EllipPar()
			ellippar = elliplist[listpos]
			ellipnumbers.add(ellippar.Num)
		checknumbers.difference_update(ellipnumbers)
		return checknumbers.pop()

	def numconnect(self, liste):
		connectnumbers=set()
		checknumbers=set(range(len(liste)+1))
		for listpos, item in enumerate(liste):
			linepar = config.LinePar()
			linepar = liste[listpos]
			connectnumbers.add(linepar.Num)
		checknumbers.difference_update(connectnumbers)
		return checknumbers.pop()

	def checksubrect(self, image, rect):
		#print rect[2],rect[3],image.shape[0],image.shape[1]
		if (rect[0] + rect[2]) <= image.shape[1] and (rect[1] + rect[3]) <= image.shape[0] and rect[0] >= 0 and rect[
				1] >= 0 and rect[2] >= 15 and rect[3] >= 15:
			return True
		else:
			return False

	def getpropersubrect(self, image, rect, keepsize):
		if not keepsize:
			if rect[0] < 0:
				orx = 0
			else:
				orx = rect[0]
			if rect[1] < 0:
				ory = 0
			else:
				ory = rect[1]
			if (rect[0] + rect[2]) > image.shape[1]:
				width = image.shape[1] - rect[0]

			else:
				width = rect[2]
			if (rect[1] + rect[3]) > image.shape[0]:
				height = image.shape[0] - rect[1]
			else:
				height = rect[3]
			rect = (orx, ory, width, height)
		else:
			if rect[0] < 0:
				orx = 0
			else:
				orx = rect[0]
			if rect[1] < 0:
				ory = 0
			else:
				ory = rect[1]
			if (rect[0] + rect[2]) > image.shape[1]:
				orx = image.shape[1] - rect[2]
			if (rect[1] + rect[3]) > image.shape[0]:
				ory = image.shape[0] - rect[3]
			rect = (orx, ory, rect[2], rect[3])
		return rect


class WinTrackBmpPaintThread(threading.Thread):
    """Background Worker Thread Class."""

    def __init__(self, parent, bmppaintqueue, panel, num=0):
        """Init Worker Thread Class."""
        threading.Thread.__init__(self)
        self.parent = parent
        self.bmppaintqueue = bmppaintqueue
        self.panel = panel
        self.panel.Bind(wx.EVT_PAINT, self.onpaint)
        self.num = num
        self.zoomrect = None
        self.Overlay = np.zeros((100, 100, 3))

        self.timestamp = None

        self.setDaemon(True)
        self.start()
        # start the thread

    def run(self):
        # print "Aquirethread started "
        while True:
            self.timestamp, image, ellipses, connections, framecount = self.bmppaintqueue.get()
            # print framecount
            self.parent.SetStatusText('FPS: ' + str(framecount), 1)
            # print "WinTrackBmphread got task"

            # update WinTrack data
            self.parent.imagetuple, self.parent.elliplist, self.parent.connectlist, self.timestamp = image, ellipses, connections, self.timestamp

            self.zoomrect = self.parent.zoomrect
            zoomval = self.parent.zoomval
            if self.zoomrect is None or zoomval == 0:
                self.zoomrect = (0, 0, image.shape[1], image.shape[0])
                self.parent.zoomrect = self.zoomrect

            rightdown = self.parent.rightdown

            self.Overlay = np.copy(image)

            self.drawallmarks(self.Overlay, ellipses, connections)

            # connection in build
            if rightdown[0]:
                cv2.line(self.Overlay, rightdown[1], rightdown[2], (0, 255, 0), 1)

            # overlay mask
            opacity = 0.7
            self.Overlay = cv2.addWeighted(self.Overlay, opacity, image, 1 - opacity, 0)

            self.resizezoomanddraw(self.panel, self.zoomrect, self.Overlay)

        self.bmppaintqueue.task_done()

    def onpaint(self, event):
        # print 'Panel Paint event'
        self.resizezoomanddraw(self.panel, self.zoomrect, self.Overlay)

    def resizezoomanddraw(self, panel, zoomrect, img):
        dc = wx.ClientDC(panel)
        panelwidth, panelheight = dc.GetSize()
        if (panelwidth <= 0) or (panelheight <= 0):
            return
        # reset Zoom when image.size changed
        if zoomrect is not None:
            if (zoomrect[0] + zoomrect[2]) > img.shape[1] or (zoomrect[1] + zoomrect[3]) > img.shape[0]:
                zoomrect = (0, 0, img.shape[1], img.shape[0])
            if (zoomrect[3], zoomrect[2]) != img.shape:
                zoomimage = img[zoomrect[1]:(zoomrect[1] + zoomrect[3]), zoomrect[0]:(zoomrect[0] + zoomrect[2])]
                scaledimg = cv2.resize(zoomimage, (panelwidth, panelheight))
        else:
            scaledimg = cv2.resize(img, (panelwidth, panelheight))

        row, col= scaledimg.shape[0],scaledimg.shape[1]
        bitmap = wx.Bitmap.FromBuffer(col, row, scaledimg)
        dc.DrawBitmap(bitmap, 0, 0, False)

    def getaabbellip(self, ellip):
        angle = -math.radians(ellip.Angle)
        if ellip.Size[0] < ellip.Size[1]:
            a = ellip.Size[1]
            b = ellip.Size[0]
        else:
            b = ellip.Size[1]
            a = ellip.Size[0]
        if angle == 0:
            x = a
            y = b
        else:
            t = math.atan(-b * math.tan(angle) / a)
            x = abs(a * math.cos(t) * math.cos(angle) - b * math.sin(t) * math.sin(angle))
            t = math.atan(a * (1 / math.tan(angle)) / b)
            y = abs(b * math.sin(t) * math.cos(angle) + a * math.cos(t) * math.sin(angle))
        # print x,y, angle
        return y, x

    def drawallmarks(self, image, ellipses, connections):
        # first ellipses

        for listpos, item in enumerate(ellipses):
            ellippar = config.EllipPar()
            ellippar = ellipses[listpos]
            # determine thickness of mark
            thickness = (int((ellippar.Size[0] + ellippar.Size[1]) / 40))

            self.drawellipmark(image, ellippar, 255, 0, 0, thickness)

        # second connections

        for listpos, item in enumerate(connections):

            linepar = config.LinePar()
            linepar = connections[listpos]
            epar1 = self.getellipwithnum(ellipses, linepar.Pt1)
            epar2 = self.getellipwithnum(ellipses, linepar.Pt2)

            cv2.line(image, (int(epar1.MidPos[0]), int(epar1.MidPos[1])), (int(epar2.MidPos[0]), int(epar2.MidPos[1])),
                     (0, 0, 255), 1)

            rx, ry = abs(epar1.MidPos[0] - epar2.MidPos[0]), abs(epar1.MidPos[1] - epar2.MidPos[1])
            if epar1.MidPos[0] < epar2.MidPos[0]:
                posx = int(epar1.MidPos[0] + rx / 2)
            else:
                posx = int(epar2.MidPos[0] + rx / 2)
            if epar1.MidPos[1] < epar2.MidPos[1]:
                posy = int(epar1.MidPos[1] + ry / 2)
            else:
                posy = int(epar2.MidPos[1] + ry / 2)

            cv2.putText(image, 'C%d' % linepar.Num, (posx, posy), cv2.FONT_HERSHEY_COMPLEX, 1, (0, 0, 255), 1)

    def drawellipmark(self, image, epar, color1, color2, color3, thickness):
        b, h = self.getaabbellip(epar)
        b, h = int(b * 1.5), int(h * 1.5)
        if b < 20:
            b = 20
        if h < 20:
            h = 20
        #print(thickness)
        if thickness > 5:
            thickness=5
        thickness=1
        posx = int(epar.MidPos[0] - b / 2)
        posy = int(epar.MidPos[1] - h / 2)
        cv2.rectangle(image, (posx, posy), (int(posx + b), int(posy + h)), (color1, color2, color3), thickness)
        cv2.ellipse(image, (int(epar.MidPos[0]), int(epar.MidPos[1])), (int(epar.Size[0] / 2), int(epar.Size[1] / 2)),
                    epar.Angle, 0, 360, (color1, color2, color3), thickness)
        cv2.line(image, (int(epar.MidPos[0] - b / 2), int(epar.MidPos[1])),
                 (int(epar.MidPos[0] + b / 2), int(epar.MidPos[1])), (color1, color2, color3), thickness)
        cv2.line(image, (int(epar.MidPos[0]), int(epar.MidPos[1] - h / 2)),
                 (int(epar.MidPos[0]), int(epar.MidPos[1] + h / 2)), (color1, color2, color3), thickness)
        cv2.putText(image, '%d' % epar.Num, (int(posx + b), int(posy + h)), cv2.FONT_HERSHEY_COMPLEX, 1,
                    (color1, color2, color3), thickness)

        # add movement vectors

        if epar.mov[0] != 0 and epar.mov[1] != 0:
            # start and endpoint

            p2 = epar.MidPos[0], epar.MidPos[1]
            p2 = epar.MidPos[0] - epar.mov[0], epar.MidPos[1] - epar.mov[1]

            angle = math.atan2((p2[1] - p2[1]), (p2[0] - p2[0]))
            lenght = math.sqrt((p2[0] - p2[0]) ** 2 + (p2[1] - p2[1]) ** 2)

            # enlongen vector

            p2 = p2[0] - 10 * lenght * math.cos(angle), p2[1] - 10 * lenght * math.sin(angle)
            p5 = p2[0] - thickness * math.cos(angle), p2[1] - thickness * math.sin(angle)

            # draw main line

            cv2.line(image, (int(p5[0]), int(p5[1])), (int(p2[0]), int(p2[1])), (color1, 255, color3), thickness)

    def getellipwithnum(self, liste, num):
        for listpos, item in enumerate(liste):
            epar = config.EllipPar()
            epar = liste[listpos]
            if epar.Num == num:
                return epar
        return None


class CalibData:
    def __init__(self):
        self.intrinsic = None
        self.distortion = None
        self.distanceunit = None

def ellipse(h, k, a, b, phi, x, y):
    xp = (x-h)*math.cos(phi) + (y-k)*math.sin(phi)
    yp = -(x-h)*math.sin(phi) + (y-k)*math.cos(phi)
    return (xp/a)**2 + (yp/b)**2 <= 1
