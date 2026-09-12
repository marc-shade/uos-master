"""Send synthetic keys only to a caller-owned private VICE X display."""
import ctypes as C
from ctypes.util import find_library
import time


class Keyboard:
    def __init__(self,display):
        self.x=C.CDLL(find_library('X11'));self.t=C.CDLL(find_library('Xtst'))
        self.x.XOpenDisplay.argtypes=[C.c_char_p];self.x.XOpenDisplay.restype=C.c_void_p
        self.x.XDefaultRootWindow.argtypes=[C.c_void_p];self.x.XDefaultRootWindow.restype=C.c_ulong
        self.x.XQueryTree.argtypes=[C.c_void_p,C.c_ulong,C.POINTER(C.c_ulong),C.POINTER(C.c_ulong),
                                    C.POINTER(C.POINTER(C.c_ulong)),C.POINTER(C.c_uint)]
        self.x.XFetchName.argtypes=[C.c_void_p,C.c_ulong,C.POINTER(C.c_char_p)]
        self.x.XFree.argtypes=[C.c_void_p]
        self.x.XSetInputFocus.argtypes=[C.c_void_p,C.c_ulong,C.c_int,C.c_ulong]
        self.x.XStringToKeysym.argtypes=[C.c_char_p];self.x.XStringToKeysym.restype=C.c_ulong
        self.x.XKeysymToKeycode.argtypes=[C.c_void_p,C.c_ulong];self.x.XKeysymToKeycode.restype=C.c_uint
        self.x.XFlush.argtypes=[C.c_void_p];self.x.XCloseDisplay.argtypes=[C.c_void_p]
        self.t.XTestFakeKeyEvent.argtypes=[C.c_void_p,C.c_uint,C.c_int,C.c_ulong]
        self.display=self.x.XOpenDisplay(display.encode());assert self.display
        root=C.c_ulong();parent=C.c_ulong();children=C.POINTER(C.c_ulong)();count=C.c_uint()
        self.x.XQueryTree(self.display,self.x.XDefaultRootWindow(self.display),C.byref(root),C.byref(parent),C.byref(children),C.byref(count))
        found=[]
        for index in range(count.value):
            name=C.c_char_p()
            if self.x.XFetchName(self.display,children[index],C.byref(name)):
                if name.value and b'C128' in name.value:found.append((children[index],name.value.decode(errors='replace')))
                self.x.XFree(name)
        self.x.XFree(children)
        assert found,'private VICE window not found'
        self.window=found[0][0];self.windows=found
        self.x.XSetInputFocus(self.display,self.window,2,0);self.x.XFlush(self.display)

    def press(self,name):
        key=self.x.XKeysymToKeycode(self.display,self.x.XStringToKeysym(name.encode()))
        assert key
        self.t.XTestFakeKeyEvent(self.display,key,1,0);self.x.XFlush(self.display)
        time.sleep(.06)
        self.t.XTestFakeKeyEvent(self.display,key,0,0);self.x.XFlush(self.display)
        time.sleep(.12)

    def close(self):self.x.XCloseDisplay(self.display)

