# -*- coding: utf-8 -*-
# vim: ts=2 sw=2 et ai
###############################################################################
# Copyright (c) 2021 Andreas Vogel andreas@wellenvogel.net
#
#  Permission is hereby granted, free of charge, to any person obtaining a
#  copy of this software and associated documentation files (the "Software"),
#  to deal in the Software without restriction, including without limitation
#  the rights to use, copy, modify, merge, publish, distribute, sublicense,
#  and/or sell copies of the Software, and to permit persons to whom the
#  Software is furnished to do so, subject to the following conditions:
#
#  The above copyright notice and this permission notice shall be included
#  in all copies or substantial portions of the Software.
#
#  THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS
#  OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
#  FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL
#  THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
#  LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING
#  FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER
#  DEALINGS IN THE SOFTWARE.
#
###############################################################################
import socket
import threading
import time


class NetworkChecker(object):
  def __init__(self,host,port=443,checkInterval=10):
    self.host=host
    self.port=port
    self.lastCheck=None
    self.status=None
    self.checkInterval=checkInterval
    self.lastError=None
    self.lock=threading.Lock()

  def _checkInternal(self):
    try:
      s=socket.socket()
      s.settimeout(self.checkInterval/2)
      s.connect((self.host,self.port))
      s.getpeername()
      self.status=True
      self.lastError=None
    except Exception as e:
      self.lastError=str(e)
      self.status=False

  def available(self,triggerUpdate=True):
    self.lock.acquire()
    try:
      now=time.time()
      if self.lastCheck is None or \
          (((self.lastCheck + self.checkInterval) < now or self.lastCheck > now) and triggerUpdate):
        self.lastCheck = now
        checker=threading.Thread(target=self._checkInternal)
        checker.setDaemon(True)
        checker.start()
        return None
    finally:
      self.lock.release()
    return self.status

  def getError(self):
    return self.lastError


