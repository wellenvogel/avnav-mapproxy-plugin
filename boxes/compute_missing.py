#! /usr/bin/env python3
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
'''
compute missing boxes to get a smoother experience when using the downloaded charts
there is a compromise between the # of tiles and the layers we can leave empty.
we start from the highest zoom level and ensure that we hav a box at zoom + MAX_EMPTY that covers the same are
'''
import importlib.util
import os
import sys


def loadModuleFromFile(fileName):
  if not os.path.isabs(fileName):
    fileName=os.path.join(os.path.dirname(__file__),fileName)
  moduleName=os.path.splitext(os.path.basename(fileName))[0]
  # see https://docs.python.org/3/library/importlib.html#module-importlib
  spec = importlib.util.spec_from_file_location(moduleName, fileName)
  module = importlib.util.module_from_spec(spec)
  spec.loader.exec_module(module)
  sys.modules[moduleName] = module
  return module

seedCreator=loadModuleFromFile(os.path.join('..','create_seed.py'))


class Log(object):
  def log(self, fmt, *args):
    print("I:%s" % (fmt % (args)))

  def debug(self, fmt, *args):
    print("D:%s" % (fmt % (args)))

  def error(self, fmt, *args):
    print("E:%s" % (fmt % (args)))

def findCompleteMatch(parsedBoxes,box,maxEmpty):
  zoomLevels = parsedBoxes.getZoomLevels()
  zoom=box.zoom-1
  down=1
  while zoom >= min(zoomLevels) and down <= (maxEmpty+1):
    intersecting=[]
    for compare in parsedBoxes.getZoomBounds(zoom):
      if compare.contains(box):
        return True
      intersection=compare.intersection(box)
      if intersection is not None:
        intersecting.append(intersection)
    if len(intersecting) > 0:
      tileList=box.getTileList(-down)
      foundTiles=[]
      for intersection in intersecting:
        foundTiles+=intersection.getTileList()
      allFound=True
      for tile in tileList:
        if tile not in foundTiles:
          allFound=False
          break
      if allFound:
        return True

    down+=1
    zoom-=1
  return False

class Combine(seedCreator.LogEnabled):
  def __init__(self,logHandler=None):
    super().__init__(logHandler=logHandler)

  def canCombine(self,box, next):
    '''
    we should be able to combine
    (1)if the ne edge of box is close to the nw edge of combine
    and the se edge of box is close to sw of combine
    (2)if the sw edge of box is close to nw of combine and
    se of box is close to ne of combine
    :param box:
    :param next:
    :return:
    '''
    MAXDIFF = 0.01
    nextNw = seedCreator.LatLng(next.northeast.lat, next.southwest.lng)
    boxSe = seedCreator.LatLng(box.southwest.lat, box.northeast.lng)
    if box.northeast.closeTo(nextNw, MAXDIFF) and boxSe.closeTo(next.southwest, MAXDIFF):
      return True
    if box.southwest.closeTo(nextNw, MAXDIFF) and boxSe.closeTo(next.northeast, MAXDIFF):
      return True
    return False

  def combineSorted(self,zoomBoxes):
    rt=[]
    combined = None
    for box in zoomBoxes:
      if combined is None:
        combined = box
        continue
      if self.canCombine(combined, box):
        self.logInfo("combine %s and %s",str(combined),str(box))
        combined.extend(box)
        continue
      rt.append(combined)
      combined = box
    if combined is not None:
      rt.append(combined)
    return rt

  def combineBoxes(self,boxList):
    parsed = seedCreator.Parsed(boxList)
    start=len(boxList)
    rt = []
    for zoom in range(min(parsed.getZoomLevels()), max(parsed.getZoomLevels()) + 1):
      zoomBoxes = parsed.getZoomBounds(zoom)
      if len(zoomBoxes) < 1:
        continue
      self.logInfo("%d boxes on zoom %s",len(zoomBoxes),zoom)
      zoomBoxes = sorted(zoomBoxes, key=lambda x: x.northeast.lat)
      zoomBoxes = sorted(zoomBoxes, key=lambda x: x.northeast.lng)
      zoomBoxes=self.combineSorted(zoomBoxes)
      self.logInfo("%d boxes on zoom %d after pass#1",len(zoomBoxes),zoom)
      zoomBoxes = sorted(zoomBoxes, key=lambda x: x.northeast.lng)
      zoomBoxes = sorted(zoomBoxes, key=lambda x: x.northeast.lat)
      zoomBoxes = self.combineSorted(zoomBoxes)
      self.logInfo("%d boxes on zoom %d after pass#2", len(zoomBoxes), zoom)
      zoomBoxes=sorted(zoomBoxes,key=lambda x:x.getSize(),reverse=True)
      reduced=[]
      for box in zoomBoxes:
        contained=False
        for red in reduced:
          if red.contains(box):
            contained=True
            break
        if contained:
          self.logInfo("skipping already contained %s",str(box))
          continue
        reduced.append(box)
      self.logInfo("%d boxes on zoom %d after pass#3", len(reduced), zoom)
      rt+=reduced
    self.logInfo("reduced from %d to %d boxes",start,len(rt))
    return rt


logHandler=Log()

def computeMissing(inFile,outFile,maxEmpty=1):
  boxReader=seedCreator.Boxes(boxes=inFile,logHandler=logHandler)
  boxReader.mergeBoxes()
  parsedBoxes=boxReader.getParsed()
  zoomLevels=parsedBoxes.getZoomLevels()
  additionalBoxes=[]
  #we go from max to min+1...
  for zoom in range(max(zoomLevels),min(zoomLevels),-1):
    zoomBoxes=parsedBoxes.getZoomBounds(zoom)
    for box in zoomBoxes:
      #currently simple approach:
      #check if we find a complete match - otherwise add a box
      hasUpper=findCompleteMatch(parsedBoxes,box,maxEmpty)
      if not hasUpper:
        upperZoom=box.zoom-maxEmpty-1
        while upperZoom < min(zoomLevels):
          upperZoom+=1
        if upperZoom >= box.zoom:
          #strange - should not happen
          logHandler.log("internal error, no upzoom for %d",box.zoom)
          continue
        upperBox=box.clone()
        upperBox.zoom=upperZoom
        upperBox.name="COMP%05d"%len(additionalBoxes)
        upperBox.isComputed=True
        logHandler.log("creating upperBox %s for %s",str(upperBox),str(box))
        additionalBoxes.append(upperBox)
        parsedBoxes.addBox(upperBox)
  logHandler.log("created %d additionalBoxes",len(additionalBoxes))
  combine=Combine(logHandler)
  additionalBoxes=combine.combineBoxes(additionalBoxes)
  logHandler.log("%d boxes after combination",len(additionalBoxes))
  with open(outFile,"w") as oh:
    for box in additionalBoxes:
      oh.write(boxReader.boxToLine(box))
      oh.write("\n")

def testCombine(boxFile):
  boxReader = seedCreator.Boxes(boxes=boxFile, logHandler=logHandler)
  (boxes,numTiles)=boxReader.mergeBoxes()
  logHandler.log("read %s boxes",len(boxes))
  combine=Combine(logHandler)
  combined=combine.combineBoxes(boxes)
  logHandler.log("combined %s boxes", len(combined))


def usage():
  print("usage: %s infile outfile [maxEmpty]"%sys.argv[0],file=sys.stderr)

if __name__ == '__main__':
  if len(sys.argv) < 3:
    usage()
    sys.exit(1)
  if (sys.argv[1] == '-t'):
    testCombine(sys.argv[2])
    sys.exit(0)
  infile = sys.argv[1]
  outfile= sys.argv[2]
  maxEmpty=1
  if len(sys.argv) > 3:
    maxEmpty=int(sys.argv[3])
  computeMissing(infile,outfile,maxEmpty)




