from distutils.core import setup
import py2exe
import sys
sys.argv = ["blah","py2exe","--dll-excludes=MSVCP80.dll,MSVCR80.dll,vcomp.dll","py2exe"]
setup(console=['OpenVidTenspara.py'])
