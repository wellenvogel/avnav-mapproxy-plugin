#!/usr/bin/env python3
import http.client
import sys
import ssl
from urllib import request as urllib2
import time
import random
import threading
import getopt
M_SHARED="shared"
M_PRIV="private"
M_DEF="default"
MODES=[M_SHARED,M_DEF,M_PRIV]

class OpenerCache:
    def __init__(self,mode):
        self.cache={}
        self.mode=mode
        self.lock=threading.Lock()
    def _build(self):
        ctx = ssl.create_default_context()
        handler=urllib2.HTTPSHandler(context=ctx)
        handlers=[handler]
        opener = urllib2.build_opener(*handlers)
        version="1.15.1"
        #opener.addheaders = [('User-agent', 'MapProxy-%s' % (version,))]
        return opener
    def getOpener(self,key):
        if self.mode != M_PRIV:
            key=0
        with self.lock:
            if key in self.cache:
                return self.cache[key]
            opener=self._build()
            self.cache[key]=opener
            return opener
   
openerCache=None

def openUrl(url,mode,prfx=''):
    key=threading.get_native_id()
    req = urllib2.Request(url, data=None,method='GET')
    try:
        if mode != M_DEF:
            opener=openerCache.getOpener(key)
            result = opener.open(req,timeout=10)
        else:
            result=urllib2.urlopen(req,timeout=10)
        print("%s%s: %s"%(prfx,url,str(result.status)))
    except Exception as e:
        print("%s%s: [ERROR]%s"%(prfx,url,str(e)))


def testRunner(url,num,mode):
    id=threading.get_native_id()
    while num > 0:
        num-=1
        openUrl(url,mode,prfx="%s-%d "%(str(id),num))
        if num > 0:
            time.sleep(0.05)
   
def usage():
    print("usage: %s -m shared|private|default [-u url] numreq numthreads"%sys.argv[0]) 

url="https://docs.python.org"
mode=None
try:  
    opts,args=getopt.getopt(sys.argv[1:],'m:u:')
    for o, a in opts:
        if o == '-m':
            if not a in MODES:
                raise getopt.GetoptError("invalid -m %s, expected %s"%(a,"|".join(MODES)))
            openerCache=OpenerCache(a)
            mode=a
        elif o == '-u':
            url=a
        else:
            assert False, "unhandled option"
    if openerCache is None:
        raise getopt.GetoptError("missing parameter -m")
except getopt.GetoptError as err:
    print(err)
    usage()
    sys.exit(1)


if len(args) < 2:
    usage()
    sys.exit(1)
numreq=int(args[0])
numthr=int(args[1])
print("using url %s"%url)
allthreads=[]
for thr in range(0,numthr):
    print("start thread %d "%(thr))
    thread=threading.Thread(target=testRunner,args=[url,numreq,mode],daemon=True)
    allthreads.append(thread)
    thread.start()
for t in allthreads:
    t.join()
sys.exit(0)