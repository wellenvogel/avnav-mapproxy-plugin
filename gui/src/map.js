/*
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
*/
import L from 'leaflet';
export const getTileFromLatLon=(map,latLong,zoom)=>{
    let projected=map.project(latLong,zoom);
    let ts=L.point(256,256);
    let tcoord=projected.unscaleBy(ts).round();
    tcoord.z=zoom;
    return tcoord;
}
/**
 * get the intersection of 2 rectangles
 * @param first
 * @param second
 * returns undefined is no overlap
 */
export const getIntersectionBounds=(first,second)=>{
    let fne=first.getNorthEast();
    let fsw=first.getSouthWest();
    let sne=second.getNorthEast()
    let ssw=second.getSouthWest();
    let ne=L.latLng(Math.min(fne.lat,sne.lat),Math.min(fne.lng,sne.lng))
    let sw=L.latLng(Math.max(fsw.lat,ssw.lat),Math.max(fsw.lng,ssw.lng))
    if (ne.lat > sw.lat && ne.lng > sw.lng) return L.latLngBounds(ne,sw);
}
export const getBoundsFromSelections=(group,toPlain)=>{
    if (!group ) return [];
    let rt=[];
    group.getLayers().forEach(function(layer){
        let bounds=layer.getBounds();
        if (toPlain){
            rt.push({
                ne: bounds.getNorthEast(),
                sw: bounds.getSouthWest()
            })
        }
        else {
            rt.push(bounds);
        }
    })
    return rt;
}
export const tileCountForBounds=(map,bounds,z)=>{
    let netile=getTileFromLatLon(map,bounds.getNorthEast(),z);
    let swtile=getTileFromLatLon(map,bounds.getSouthWest(),z);
    let xdiff=Math.abs(netile.x-swtile.x)+1;
    let ydiff=Math.abs(netile.y-swtile.y)+1;
    let zTiles=xdiff*ydiff;
    return zTiles;
}
