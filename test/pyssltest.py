#!/usr/bin/env python3
import http.client
import sys
import ssl
from urllib import request as urllib2
import time
import random
import threading
openerCache={}
def getOpener(key):
    if not key in openerCache:
        ctx = ssl.create_default_context()
        handler=urllib2.HTTPSHandler(context=ctx)
        handlers=[handler]
        opener = urllib2.build_opener(*handlers)
        version="1.15.1"
        opener.addheaders = [('User-agent', 'MapProxy-%s' % (version,))]
        openerCache[key]=opener
        return opener
    return openerCache[key]

def openUrl(url,key=0):
    opener=getOpener(key)
    req = urllib2.Request(url, data=None)
    result = opener.open(req)
    print("%s: %s"%(url,str(result.status)))

def buildUrl(base,z,y,x):
    values={'x':x,'y':y,'z':z}
    return base%values

def nextV(v,zoom):
    v+=1
    if v > (1 << zoom):
        v=0
    return v
def testRunner(base,zoom,y,x,num,crash):
    key=0
    if not crash:
        key=threading.get_native_id()
    while num > 0:
        num-=1
        openUrl(buildUrl(url,zoom,y,x),key=key)
        x=nextV(x,zoom)
        if num > 0:
            time.sleep(0.05)
if len(sys.argv) < 3:
    print("usage: %s [-c] base numreq [numthr] [zoom]"%sys.argv[0])
    sys.exit(1)
crash=False
start=1
if sys.argv[1] == '-c':
    crash=True
    start=2
url=sys.argv[start]
numreq=int(sys.argv[start+1])
numthr=1
zoom=12
if len(sys.argv) > start+3:
    zoom=int(sys.argv[start+3])

if len(sys.argv) > start+2:
    numthr=int(sys.argv[start+2])
allthreads=[]
for thr in range(0,numthr):
    x=random.randrange(0,(1 << zoom)-1)
    y=random.randrange(0,(1 << zoom)-1)
    print("start thread %d x=%d,y=%d"%(thr,x,y))
    thread=threading.Thread(target=testRunner,args=[url,zoom,y,x,numreq,crash],daemon=True)
    allthreads.append(thread)
    thread.start()
for t in allthreads:
    t.join()
sys.exit(0)
host=sys.argv[1]
conn = http.client.HTTPSConnection(host)
conn.request("GET", "/", headers={"Host": host})
response = conn.getresponse()
print(response.status, response.reason)