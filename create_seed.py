###############################################################################
# Copyright (c) 2021, Andreas Vogel andreas@wellenvogel.net
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
###############################################################################
import math
import os
import re
import sys

import yaml

def deg2num(lat_deg, lon_deg, zoom):
  lat_rad = math.radians(lat_deg)
  n = 2.0 ** zoom
  xtile = int((lon_deg + 180.0) / 360.0 * n)
  ytile = int((1.0 - math.asinh(math.tan(lat_rad)) / math.pi) / 2.0 * n)
  return (xtile, ytile,zoom)

class LogEnabled(object):
  def __init__(self,logHandler=None):
    self.logHandler=logHandler

  def logDebug(self,fmt,*args):
    if (self.logHandler):
      self.logHandler.debug(fmt,*args)
  def logInfo(self,fmt,*args):
    if (self.logHandler):
      self.logHandler.log(fmt,*args)
  def logError(self,fmt,*args):
    if (self.logHandler):
      self.logHandler.error(fmt,*args)


class LatLng(object):
  def __init__(self,lat,lng):
    self.lat=lat
    self.lng=lng
  def __str__(self):
    return "lat=%f,lon=%f"%(self.lat,self.lng)
  @classmethod
  def fromDict(cls,d):
    return LatLng(d['lat'],d['lng'])

  def toDict(self):
    return self.__dict__

def getV(data,keys):
  for k in keys:
    rt=data.get(k)
    if rt is not None:
      return rt

class Box(object):
  def __init__(self,northeast,southwest,zoom=None,name=None):
    self.northeast=northeast # type: LatLng
    self.southwest=southwest # type: LatLng
    self.zoom=zoom # type: int
    self.name=name
  @classmethod
  def representYaml(cls,dumper,data):
    return dumper.represent_dict(data.toDict())
  @classmethod
  def fromDict(cls,d):
    ne=LatLng.fromDict(getV(d,['ne','northeast','_northEast']))
    sw=LatLng.fromDict(getV(d,['sw','southwest','_southWest']))
    zoom=getV(d,['z','zoom'])
    return Box(ne,sw,zoom=zoom)

  def toDict(self):
    return {'ne':self.northeast.toDict(),'sw':self.southwest.toDict(),'zoom':self.zoom}

  def __str__(self):
    return "Box: ne=[%s],sw=[%s],z=%s"%(str(self.northeast),str(self.southwest),str(self.zoom))

  def intersection(self,other):
    '''
    get the intersection beween 2 boxes
    :param other:
    :type other Box
    :return: Box or None if no intersection
    '''
    nelat=min(self.northeast.lat,other.northeast.lat)
    nelng=min(self.northeast.lng,other.northeast.lng)
    swlat=max(self.southwest.lat,other.southwest.lat)
    swlng=max(self.southwest.lng,other.southwest.lng)
    if nelat > swlat and nelng > swlng:
      return Box(LatLng(nelat,nelng),LatLng(swlat,swlng),zoom=self.zoom,name=self.name)

  def extend(self,other):
    '''
    extend a box to include the other boxlog
    :param other:
    :return:
    '''
    if other is None:
      return False
    hasChanged=False
    if other.northeast.lat > self.northeast.lat:
      self.northeast.lat=other.northeast.lat
      hasChanged=True
    if other.northeast.lng > self.northeast.lng:
      self.northeast.lng=other.northeast.lng
      hasChanged=True
    if other.southwest.lat < self.southwest.lat:
      self.southwest.lat=other.southwest.lat
      hasChanged=True
    if other.southwest.lng < self.southwest.lng:
      self.southwest.lng = other.southwest.lng
      hasChanged=True
    return hasChanged

  def getMpBounds(self):
    '''
    get the bounds as array for mapproxy seed
    it expects swlng,swlat,nelng,nelat
    :return:
    '''
    return [self.southwest.lng,self.southwest.lat,self.northeast.lng,self.northeast.lat]

  def getNumTiles(self):
    if self.zoom is None or self.zoom < 0:
      return 0
    netile=deg2num(self.northeast.lat,self.northeast.lng,self.zoom)
    swtile=deg2num(self.southwest.lat,self.southwest.lng,self.zoom)
    xdiff=abs(netile[0]-swtile[0])+1
    ydiff=abs(netile[1]-swtile[1])+1
    return xdiff*ydiff

yaml.add_representer(Box,Box.representYaml,Dumper=yaml.dumper.SafeDumper)
class Boxes(LogEnabled):
  BOXES=os.path.join(os.path.dirname(__file__),'boxes','allcountries.bbox')
  def __init__(self, boxes=None, logHandler=None):
    super().__init__(logHandler)
    self.boxesFile=boxes if boxes is not None else self.BOXES
    self.logHandler=logHandler
    self.merges=[]
    self.numTiles=0

  def getBoxes(self,nelat,nelng,swlat,swlng,minZoom=None,maxZoom=None):
    rt=[]
    if minZoom is None:
      minZoom=0
    else:
      minZoom=int(minZoom)
    if maxZoom is None:
      maxZoom=22
    else:
      maxZoom=int(maxZoom)
    #we duplicate some code here as we want to be fast and do not create
    #objects
    #and we directly return the lines as this most probably is much faster
    #and we return them as bytes to avoid any encode/decode
    with open(self.boxesFile,'rb') as fh:
      for bline in fh:
        parts = re.split(b'  *', bline.rstrip())
        if len(parts) != 6:
          continue
        z=int(parts[1])
        if z < minZoom or z > maxZoom:
          continue
        bnelat=float(parts[4])
        bnelng=float(parts[5])
        bswlat=float(parts[2])
        bswlng=float(parts[3])
        if bnelat < swlat or bnelng < swlng \
            or bswlat > nelat or bswlng > nelng:
          continue
        rt.append(bline)
    return rt

  #line from boxes:
  #         z   s    w     n    e
  #1U319240 12 24.0 119.0 25.0 120.0
  def mergeBoxes(self,boxesList,minZoom=0,maxZoom=20):
    rt=[]
    numTiles=0
    with open(self.boxesFile,"r") as fh:
      for bline in fh:
        parts=re.split('  *',bline.rstrip())
        if len(parts) != 6:
          self.logDebug("skipping invalid line %s",bline)
        try:
          chartBox=Box(LatLng(float(parts[4]),float(parts[5])),LatLng(float(parts[2]),float(parts[3])),int(parts[1]),name=parts[0])
          if chartBox.zoom < minZoom or chartBox.zoom > maxZoom:
            continue
          #first we intersect with all boxes we have and
          #extend this íntersection
          #at the end we intersect again with the box to ensure at most the complete box
          intersection=None
          for box in boxesList:
            currentIntersect=chartBox.intersection(box)
            if intersection is None:
              intersection=currentIntersect
            else:
              intersection.extend(currentIntersect)
          if intersection is not None:
            result=chartBox.intersection(intersection)
            if result is not None:
              self.logDebug("adding from %s: %s",str(chartBox),str(result))
              rt.append(result)
              #we assume that the boxes do not overlap at one level...
              numTiles+=result.getNumTiles()
        except Exception as e:
          self.logError("unable to parse %s:%s",bline,str(e))
    self.merges=rt
    self.numTiles=numTiles
    return (rt,numTiles)

  def getParsed(self,merged=None):
    if merged is None:
      merged=self.merges
    return Parsed(merged)

class Parsed(object):
  def __init__(self,mergedBoxes):
    self.bounds= {}
    for box in mergedBoxes:
      z = box.zoom
      if self.bounds.get(z) is None:
        self.bounds[z] = []
      self.bounds[z].append(box)
  def getZoomLevels(self):
    return list(self.bounds.keys())
  def getZoomBounds(self,z):
    return self.bounds.get(z,[])

class Bounding(object):
  def __init__(self,name,bounds):
    self.name=name
    self.bounds=bounds

class SeedWriter(LogEnabled):
  def __init__(self, logHandler=None):
    super().__init__(logHandler)

  def write(self,outfile,data,header=None):
    with open(outfile,"w") as fh:
      self.logInfo("writing %s",outfile)
      if header is not None:
        fh.write("#")
        fh.write(header)
        fh.write("\n")
      yaml.dump(data,fh)

  def buildOutput(self, parsed, name, parameters):
    '''
    create a mobac seed file from parsed boundings
    :param parsed:
    :type parsed: Parser
    :param name: the name prefix for the seeds
    :param parameters: dict of seed parameters, especially caches
    :return:
    '''
    out = {}
    coverages = {}
    seeds = {}
    for z in parsed.getZoomLevels():
      entry = {}
      for k, v in parameters.items():
        entry[k] = v
      bounds = parsed.getZoomBounds(z)
      entry['levels'] = [z]
      entry_coverages = []
      for bound in bounds:
        cvname = "%s_%03d_%s" % (name, z, bound.name)
        coverage = {
          'srs': 'EPSG:4326',
          'bbox': bound.getMpBounds()
        }
        coverages[cvname] = coverage
        entry_coverages.append(cvname)
      entry['coverages'] = entry_coverages
      sname = "%s_%03d" % (name, z)
      seeds[sname] = entry
    out['seeds'] = seeds
    out['coverages'] = coverages
    return out


def createSeed(boundsFile,name,caches,seedFile=None,logger=None):
  merger = Boxes(logHandler=logger)
  with open(boundsFile, 'r') as h:
    blist = yaml.safe_load(h)
  boxesList = []
  for b in blist:
    boxesList.append(Box.fromDict(b))
  res = merger.mergeBoxes(boxesList)
  writer = SeedWriter(logger)
  seeds = writer.buildOutput(merger.getParsed(), name, {'caches': caches})
  if seedFile is not None:
    writer.write(seedFile, seeds)
  return (merger.numTiles,seeds)

def countTiles(bounds,logger=None):
  merger = Boxes(logHandler=logger)
  boxesList = []
  for b in bounds:
    boxesList.append(Box.fromDict(b))
  merger.mergeBoxes(boxesList)
  return merger.numTiles

if __name__ == '__main__':
  def usage():
    print("usage: %s infile outfile name caches"%sys.argv[0],file=sys.stderr)
  class Log(object):
    def log(self,fmt,*args):
      print("I:%s"%(fmt%(args)))
    def debug(self,fmt,*args):
      print("D:%s"%(fmt%(args)))
    def error(self,fmt,*args):
      print("E:%s"%(fmt%(args)))

  if len(sys.argv) != 5:
    usage()
    sys.exit(1)
  merger=Boxes(logHandler=Log())
  with open(sys.argv[1],'r') as h:
    blist=yaml.safe_load(h)
  boxesList=[]
  for b in blist:
    boxesList.append(Box.fromDict(b))
  res=merger.mergeBoxes(boxesList)
  writer=SeedWriter(Log())
  caches = sys.argv[4].split(",")
  seeds=writer.buildOutput(merger.getParsed(),sys.argv[3],{'caches': caches})
  writer.write(sys.argv[2],seeds)