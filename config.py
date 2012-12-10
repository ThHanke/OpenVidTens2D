# -*- coding: cp1252 -*-
import wx,os,sys

ProgDir=os.path.dirname(sys.argv[0])


class EllipPar:
    def __init__(self):
        self.Num=int
        self.MidPos=float,float
        self.Size=float,float
        self.Angle=float
        self.mov=float,float
class LinePar:
    def __init__(self):
        self.Num=int
        self.Pt1=int
        self.Pt2=int
        self.Pos=int,int
        
