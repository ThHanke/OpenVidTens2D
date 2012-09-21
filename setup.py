from distutils.core import setup
import py2exe


import sys
sys.argv = ["blah","py2exe"]

includes = []
excludes = ['_gtkagg', '_tkagg', 'bsddb', 'curses', 'email', 'pywin.debugger',
            'pywin.debugger.dbgcon', 'pywin.dialogs', 'tcl',
            'Tkconstants', 'Tkinter']
#excludes = []

packages = []
#dll_excludes = ['libgdk-win32-2.0-0.dll', 'libgobject-2.0-0.dll', 'tcl84.dll','tk84.dll']
dll_excludes = ['MSVCR80.dll','MSVCP80.dll','MSVCR90.dll','MSVCP90.dll','vcomp.dll']

setup(data_files = [('', ['calicon.png',
                          'logoOpenVidTens.png',
                          'Startdownsmall.png',
                          'Startupsmall.png',
                          'Stopupsmall.png',
                          'Stopdownsmall.png',
                          'C:\Python27\Lib\helvetica-10.pil',
                          'C:\Python27\Lib\helvB08.pil',
                          'C:\Python27\Lib\helvetica-10.png',
                          'C:\Python27\Lib\helvB08.png',
                          
                                                
                          ])],

      options = {"py2exe": {"compressed": 0,"optimize": 0,
                            "includes": includes,
                            "excludes": excludes,
                            "packages": packages,
                            "dll_excludes": dll_excludes,
                            "bundle_files": 3,
                            "dist_dir": "64bit",
                            "xref": False,
                            
                            "skip_archive": False,
                            "ascii": False,
                            "custom_boot_script": '',
                            }
                 },
      zipfile=None,
      console=['OpenVidTens2D.py']
      
      )

#     zipfile=None,
