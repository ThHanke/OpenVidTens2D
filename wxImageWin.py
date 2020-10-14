import wx,cv2
import threading
import queue
import numpy as np

class Frame(wx.Frame):
    def __init__(self,images,size=None,pos=(0,0),title=''):
        self.images=images
        self.zoomval = 0
        self.zoomrect = None
        if size==None:
            screensize=wx.Display().GetGeometry()
            size=(screensize[2],screensize[3])
        wx.Frame.__init__(self, None, wx.ID_ANY, title=title, pos=pos,size=size, style=wx.DEFAULT_FRAME_STYLE)
        self.panel = wx.Panel(self, wx.ID_ANY,size=size, style=wx.BORDER_SUNKEN)
        self.panelsizer = wx.BoxSizer(wx.HORIZONTAL)
        self.panelsizer.Add(self.panel, 2, wx.EXPAND)
        self.SetSizer(self.panelsizer)
        self.Bind(wx.EVT_CLOSE, self.OnClose, id=wx.ID_ANY)
        self.panel.Bind(wx.EVT_MOUSEWHEEL, self.Zoom)
        self.PaintThread=PaintPicThread(self.panel,self.images)
        self.CreateMenu()
        self.Show()
        #self.Layout()
    def CreateMenu(self):
            Menubar =wx.MenuBar()
            self.SetMenuBar(Menubar)
    def Zoom(self, event):

        pt = event.GetPosition()
        #pos = self.panel2imagekoord(self.panel, pt,self.zoomrect)
        rot = event.GetWheelRotation()
        rot = rot / event.GetWheelDelta()
        if self.zoomval + rot < 0:
            self.zoomval = 0
        else:
            self.zoomval += rot

        self.images.put(('zoom',self.zoomval,pt))
    def OnClose(self, event):
        self.PaintThread.stop=True
        self.Destroy()

class PaintPicThread(threading.Thread):
    """Background Paint Thread Class."""

    def __init__(self, panel,images):
        """Init Worker Thread Class."""
        threading.Thread.__init__(self)
        self.bmppaintqueue=images
        self.panel=panel
        self.parent=wx.GetTopLevelParent(self.panel)
        self.image=np.zeros((100,100,3), dtype=np.uint8)
        self.panel.Bind(wx.EVT_PAINT, self.onPaint)
        self.stop=False
        self.start()
    def run(self):
        dc = wx.ClientDC(self.panel)
        while True:
            if self.stop:
                break
            #if not isinstance(self.image, np.ndarray):
            data = self.bmppaintqueue.get()
            if isinstance(data,str):
                print(data)
            if isinstance(data,tuple):
                #print(data)
                if data[0]=='zoom':
                    zoomval=data[1]
                    zoommid = self.panel2imagekoord(self.panel, data[2],self.zoomrect)
                    if zoomval > 0:
                        width = int(float(self.image.shape[1]) / float(zoomval))
                        height = int(float(self.image.shape[0]) / float(zoomval))
                        orx = zoommid[0] - int(float(width) / 2)
                        ory = zoommid[1] - int(float(height) / 2)
                        self.zoomrect = (orx, ory, width, height)
                        if not self.checksubrect(self.image, self.zoomrect):
                            self.zoomrect = self.getpropersubrect(self.image, self.zoomrect, True)
                    else:
                        self.zoomrect = (0, 0, self.image.shape[1], self.image.shape[0])
                
            elif isinstance(data,np.ndarray):
                #reset zoom
                if data.shape!=self.image.shape:
                    self.zoomrect = (0, 0, data.shape[1], data.shape[0])
                self.image = cv2.cvtColor(data, cv2.COLOR_BGR2RGB)
            self.Draw(self.panel,self.image,zoomrect=self.zoomrect)
            self.bmppaintqueue.task_done()

    def onPaint(self,event):
        #print 'Panel Paint event'
        self.Draw(self.panel, self.image)
        event.Skip()
    def Draw(self, panel,img, zoomrect=None):
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
    def panel2imagekoord(self, panel,pt,zoomrect=None):
        panelwidth,panelheight=panel.Size
        if zoomrect==None:
            zoomrect=(0,0,1,1)
        pos = int(float(pt[0]) / float(panelwidth) * zoomrect[2] + zoomrect[0]), int(
            float(pt[1]) / float(panelheight) * zoomrect[3] + zoomrect[1])
        return pos


class App(wx.App):
    def OnInit(self):
        images=queue.Queue()
        print(images)
        self.Frame=Frame(images)
        images.put(cv2.imread('logoOpenVidTens.png'))
        return True

if __name__=="__main__":
    #multiprocessing.freeze_support()
    #app = App(redirect=False)
    app = App(redirect=0)
    app.MainLoop()
