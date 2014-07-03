from cv2 import VideoWriter
from multiprocessing import Process
import os

class VideoWriterProcess(Process):
    def __init__(self, filename,fourcc, queue):
        Process.__init__(self)
        self.filename=filename
        self.queue=queue
        self.daemon=True

        self.fourcc=fourcc        
        self.videofilepart=1
        self.videowriter=None

        self.start()
        
    def run(self):
        while True:
##            
            msg=self.queue.get()
            if msg=='TERMINATE':
                if self.videowriter!=None:
                    self.videowriter.release()
                    while self.videowriter.isOpened():
                        print 'wait till videowriter is released'
                print 'i have been terminated'
                break
            
            else:
                if self.videowriter==None:
                    print 'open video writer'
                    self.videowriter=VideoWriter(self.filename+'.'+str(self.videofilepart).rjust(2,'0')+'.avi',self.fourcc,30,(msg.shape[1],msg.shape[0]),isColor=False)
                    #self.videowriter.open(self.filename+'.'+str(self.videofilepart).rjust(2,'0')+'.avi',fourcc,30,(self.raw.shape[1],self.raw.shape[0]),isColor=False)
                    while not self.videowriter.isOpened():
                        print 'wait till videowriter is ready'
                #check filesize
                filesize=os.path.getsize(self.filename+'.'+str(self.videofilepart).rjust(2,'0')+'.avi')
                print filesize
                #if filesize>=4294967296: #4GB
                if filesize>=4294967296: #4GB
                    self.videofilepart+=1
                    self.videowriter.open(self.filename+'.'+str(self.videofilepart).rjust(2,'0')+'.avi',self.fourcc,30,(msg.shape[1],msg.shape[0]),isColor=False)
                    while not self.videowriter.isOpened():
                        print 'wait till videowriter is ready'
                self.videowriter.write(msg)
                
                
        
