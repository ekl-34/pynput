# coding=utf-8
# pynput
# Copyright (C) 2015 Moses Palmér
#
# This program is free software: you can redistribute it and/or modify it under
# the terms of the GNU General Public License as published by the Free Software
# Foundation, either version 3 of the License, or (at your option) any later
# version.
#
# This program is distributed in the hope that it will be useful, but WITHOUT
# ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS
# FOR A PARTICULAR PURPOSE. See the GNU General Public License for more
# details.
#
# You should have received a copy of the GNU General Public License along with
# this program. If not, see <http://www.gnu.org/licenses/>.

import ctypes
import threading

from ctypes import windll, wintypes

from . import AbstractListener


class MessageLoop(object):
    """A class representing a message loop.
    """
    #: The message that signals this loop to terminate
    WM_STOP = 0x0401

    _GetMessage = windll.user32.GetMessageW
    _PeekMessage = windll.user32.PeekMessageW
    _PostThreadMessage = windll.user32.PostThreadMessageW

    PM_NOREMOVE = 0

    def __init__(
            self,
            initialize=lambda message_loop: None,
            finalize=lambda message_loop: None):
        self._threadid = None
        self._initialize = initialize
        self._finalize = finalize
        self._event = threading.Event()
        self.thread = None

    def __iter__(self):
        """Initialises the message loop and yields all messages until
        :meth:`stop` is called.

        :raises AssertionError: if :meth:`start` has not been called
        """
        assert self._threadid is not None

        try:
            # Pump messages until WM_STOP
            while True:
                msg = wintypes.MSG()
                lpmsg = ctypes.byref(msg)
                r = self._GetMessage(lpmsg, None, 0, 0)
                if r <= 0 or msg.message == self.WM_STOP:
                    break
                else:
                    yield msg

        finally:
            self._finalize(self)
            self._threadid = None
            self.thread = None

    def start(self):
        """Starts the message loop.

        This method must be called before iterating over messages, and it must
        be called from the same thread.
        """
        self._threadid = GetCurrentThreadId()
        self.thread = threading.current_thread()

        # Create the message loop
        msg = wintypes.MSG()
        lpmsg = ctypes.byref(msg)
        self._PeekMessage(lpmsg, None, 0x0400, 0x0400, self.PM_NOREMOVE)

        # Let the called perform initialisation
        self._initialize(self)

        # Set the event to signal to other threads that the loop is created
        self._event.set()

    def stop(self):
        """Stops the message loop.
        """
        self._event.wait()
        self._PostThreadMessage(self._threadid, self.WM_STOP, 0, 0)
        if self.thread != threading.current_thread():
            self.thread.join()


class SystemHook(object):
    """A class to handle Windows hooks.
    """
    _SetWindowsHookEx = windll.user32.SetWindowsHookExW
    _UnhookWindowsHookEx = windll.user32.UnhookWindowsHookEx
    _CallNextHookEx = windll.user32.CallNextHookEx

    _HOOKPROC = wintypes.WINFUNCTYPE(
        wintypes.LPARAM,
        ctypes.c_int32, wintypes.WPARAM, wintypes.LPARAM)

    #: The registered hook procedures
    _HOOKS = {}

    def __init__(self, hook_id, on_hook=lambda code, msg, lpdata: None):
        self.hook_id = hook_id
        self.on_hook = on_hook
        self._hook = None

    def __enter__(self):
        key = threading.current_thread()
        assert key not in self._HOOKS

        # Add ourself to lookup table and install the hook
        self._HOOKS[key] = self
        self._hook = self._SetWindowsHookEx(
            self.hook_id,
            self._handler,
            None,
            0)

        return self

    def __exit__(self, type, value, traceback):
        key = threading.current_thread()
        assert key in self._HOOKS

        if self._hook is not None:
            # Uninstall the hook and remove ourself from lookup table
            self._UnhookWindowsHookEx(self._hook)
            del self._HOOKS[key]

    @staticmethod
    @_HOOKPROC
    def _handler(code, msg, lpdata):
        key = threading.current_thread()
        self = SystemHook._HOOKS.get(key, None)
        if self:
            self.on_hook(code, msg, lpdata)

        # Always call the next hook
        return SystemHook._CallNextHookEx(0, code, msg, lpdata)


GetCurrentThreadId = windll.kernel32.GetCurrentThreadId


SendInput = windll.user32.SendInput


VkKeyScan = windll.user32.VkKeyScanW


class MOUSEINPUT(ctypes.Structure):
    """Contains information about a simulated mouse event.
    """
    MOVE = 0x0001
    LEFTDOWN = 0x0002
    LEFTUP = 0x0004
    RIGHTDOWN = 0x0008
    RIGHTUP = 0x0010
    MIDDLEDOWN = 0x0020
    MIDDLEUP = 0x0040
    XDOWN = 0x0080
    XUP = 0x0100
    WHEEL = 0x0800
    HWHEEL = 0x1000
    ABSOLUTE = 0x8000

    XBUTTON1 = 0x0001
    XBUTTON2 = 0x0002

    _fields_ = [
        ('dx', wintypes.LONG),
        ('dy', wintypes.LONG),
        ('mouseData', wintypes.DWORD),
        ('dwFlags', wintypes.DWORD),
        ('time', wintypes.DWORD),
        ('dwExtraInfo', ctypes.c_void_p)]


class KEYBDINPUT(ctypes.Structure):
    """Contains information about a simulated keyboard event.
    """
    EXTENDEDKEY = 0x0001
    KEYUP = 0x0002
    SCANCODE = 0x0008
    UNICODE = 0x0004

    _fields_ = [
        ('wVk', wintypes.WORD),
        ('wScan', wintypes.WORD),
        ('dwFlags', wintypes.DWORD),
        ('time', wintypes.DWORD),
        ('dwExtraInfo', ctypes.c_void_p)]


class HARDWAREINPUT(ctypes.Structure):
    """Contains information about a simulated message generated by an input
    device other than a keyboard or mouse.
    """
    _fields_ = [
        ('uMsg', wintypes.DWORD),
        ('wParamL', wintypes.WORD),
        ('wParamH', wintypes.WORD)]


class INPUT_union(ctypes.Union):
    """Represents the union of input types in :class:`INPUT`.
    """
    _fields_ = [
        ('mi', MOUSEINPUT),
        ('ki', KEYBDINPUT),
        ('hi', HARDWAREINPUT)]


class INPUT(ctypes.Structure):
    """Used by :attr:`SendInput` to store information for synthesizing input
    events such as keystrokes, mouse movement, and mouse clicks.
    """
    MOUSE = 0
    KEYBOARD = 1
    HARDWARE = 2

    _fields_ = [
        ('type', wintypes.DWORD),
        ('value', INPUT_union)]


class ListenerMixin(object):
    """A mixin for *win32* event listeners.

    Subclasses should set a value for :attr:`_EVENTS` and implement
    :meth:`_handle`.
    """
    #: The Windows hook ID for the events to capture
    _EVENTS = None

    def _run(self):
        self._message_loop = MessageLoop()
        self._add_listener()
        try:
            self._message_loop.start()

            with SystemHook(self._EVENTS, self._handler):
                # Just pump messages
                for msg in self._message_loop:
                    if not self.running:
                        break

        finally:
            self._remove_listener()

    def _stop(self):
        try:
            self._message_loop.stop()
        except AttributeError:
            # The loop may not have been created
            pass

    @classmethod
    def receiver(self, cls):
        """A decorator to make a class able to receive fake events from a
        controller.

        :param cls: The class whose instances are to receive fake events.
        """
        cls._listeners = set()
        cls._listener_lock = threading.Lock()
        return cls

    @AbstractListener._emitter
    def _handler(self, code, msg, lpdata):
        """The callback registered with *Windows* for events.

        This method will call the callbacks registered on initialisation.
        """
        self._handle(code, msg, lpdata)

    def _add_listener(self):
        """Adds this listener to the set of running listeners.
        """
        with self.__class__._listener_lock:
            self.__class__._listeners.add(self)

    def _remove_listener(self):
        """Removes this listener from the set of running listeners.
        """
        with self.__class__._listener_lock:
            self.__class__._listeners.remove(self)

    @classmethod
    def listeners(self):
        """Iterates over the set of running listeners.

        This method will quit without acquiring the lock if the set is empty,
        so there is potential for race conditions. This is an optimisation,
        since :class:`Controller` will need to call this method for every
        control event.
        """
        if not self._listeners:
            return
        with self._listener_lock:
            for listener in self._listeners:
                yield listener

    def _handle(self, code, msg, lpdata):
        """The device specific callback handler.

        This method calls the appropriate callback registered when this
        listener was created based on the event.
        """
        raise NotImplementedError()
