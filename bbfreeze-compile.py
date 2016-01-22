#!/usr/bin/env python

from bbfreeze import Freezer
from shutil import copy

foldername = 'OpenVidTens2D64bit'

f = Freezer(foldername, includes=('_strptime', '_imaging'))
f.addScript("OpenVidTens2D.py")
f.use_compression = True
f()  # starts the freezing process

fileslist = ('calicon.png',
             'logoOpenVidTens.png',
             'Startdownsmall.png',
             'Startupsmall.png',
             'Stopupsmall.png',
             'Stopdownsmall.png',
             'C:\Python27\Lib\helvetica-10.pil',
             'C:\Python27\Lib\helvB08.pil',
             'C:\Python27\Lib\helvetica-10.png',
             'C:\Python27\Lib\helvB08.png',
             )

for item in fileslist:
    copy(item, foldername)
