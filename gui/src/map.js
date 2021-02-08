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
import 'leaflet/dist/leaflet.css';
import 'leaflet-draw/dist/leaflet.draw.css';
import L from 'leaflet';
import 'leaflet-draw';
import {apiRequest, buildSelect, forEach, setTextContent, showError, showToast} from "./util";
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
//one entry for each zoom level
const COLOR_0='#04781d';
const COLOR_1='#d49311';
const COLOR_2='#ea3964';
const COLOR_3='#1f7cef';
const COLORMAP=[
    COLOR_0,  //0
    COLOR_0,
    COLOR_0,
    COLOR_0,
    COLOR_0,
    COLOR_0, //5
    COLOR_0,
    COLOR_0,
    COLOR_0,
    COLOR_0,
    COLOR_0, //10
    COLOR_1,
    COLOR_1,
    COLOR_1,
    COLOR_2,
    COLOR_2, //15
    COLOR_2,
    COLOR_3,
    COLOR_3,
    COLOR_3,
    COLOR_3 //20
]

const getBoxStyle=(zoom)=>{
    if (!zoom) zoom=0;
    if (zoom < 0) zoom=0;
    if (zoom >= COLORMAP.length) zoom=COLORMAP.length-1;
    let color=COLORMAP[zoom];
    let opacity=0.0;
    if (zoom >= 15) opacity=0.1;
    return {
        color: color,
        weight: 1,
        fillOpacity: opacity
    }
}

class ZoomInfo extends L.Control{
    constructor(options) {
        super(options);
        this.zoomChange=this.zoomChange.bind(this);
        this.el=undefined;
        this.map=undefined;
    }
    zoomChange(){
        if (! this.el || ! this.map) return;
        this.el.textContent=this.map.getZoom();
    }
    onAdd(map){
        this.map=map;
        let fr=document.createElement('div');
        fr.classList.add('zoomInfoControl');
        let sp=document.createElement('span');
        sp.classList.add('label');
        sp.textContent="Zoom";
        fr.appendChild(sp);
        this.el=document.createElement('span');
        this.el.classList.add('value');
        this.el.textContent=map.getZoom();
        fr.appendChild(this.el);
        map.on('zoom',this.zoomChange);
        return fr;
    }
    onRemove(){
        if (this.map) this.map.off('zoom',this.zoomChange);
        this.el=undefined;
    }
}

const SELECT_OPTIONS = {
    pane: 'selections',
    clickable: true,
    interactive: true,
}

export default class SeedMap{
    constructor(mapdiv,apiBase,showBoxes) {
        this.updateTileCount=this.updateTileCount.bind(this);
        this.mapdiv=mapdiv;
        this.boxesTimer=undefined;
        this.boxesSequence=1;
        this.boxesTimeout=500; //mms to wait for boxes update
        this.inZoom=false;
        this.apiBase=apiBase;
        this.showBoxes=showBoxes;
        this.map=L.map('map').setView([54,13],6);
        this.boxesLayer=new L.FeatureGroup();
        this.map.addLayer(this.boxesLayer);
        this.zoomControl=new ZoomInfo({position:'bottomleft'});
        this.zoomControl.addTo(this.map);
        this.boxesLayer.on('click',(ev)=>{
            let topmost=undefined;
            this.boxesLayer.eachLayer((layer)=>{
                if (layer.getBounds().contains(ev.latlng)){
                    if (layer.avzoom !== undefined && layer.avname) {
                        if (! topmost) topmost = layer;
                        else{
                            if (topmost.avzoom < layer.avzoom) topmost=layer;
                        }
                    }
                }
            })
            if (topmost) {
                showToast(topmost.avname+", zoom="+topmost.avzoom);
            }
        })
        this.drawPane=this.map.createPane('selections');
        this.drawPane.style.zIndex=450; //between overlay and marker
        this.drawnItems=new L.FeatureGroup([],{pane:'selections'});
        this.map.addLayer(this.drawnItems);
        this.selectedLayer=undefined;
        this.layers={};
        this.drawControl = new L.Control.Draw({
            position: 'topright',
            draw: {
                polyline: false,
                polygon: false,
                circle: false,
                circlemarker: false,
                marker: false,
                rectangle: {
                    shapeOptions: SELECT_OPTIONS
                }
            },
            edit: {
                featureGroup: this.drawnItems,
                remove: true
            }
        });
        this.map.addControl(this.drawControl);
        this.map.on(L.Draw.Event.CREATED, (e)=> {
            let layer = e.layer;
            this.drawnItems.addLayer(layer);
            this.updateTileCount();
        });
        this.map.on(L.Draw.Event.DELETED,this.updateTileCount);
        this.map.on(L.Draw.Event.EDITED,this.updateTileCount);
        this.map.on('zoomstart',()=>this.inZoom=true)
        this.map.on('zoomend',()=>{
            this.inZoom=false;
            this.getBoxes();
        })
        this.map.on('moveend',()=>{
            if (this.inZoom) return;
            this.getBoxes()
        });
        this.map.on('loadend',()=>this.getBoxes())
        this.map.on('draw:created',(e)=>{
            e.layer.addEventParent(this.boxesLayer);
        })
    }
    setShowBoxes(on){
        let old=this.showBoxes;
        this.showBoxes=on;
        if (old !== on) this.getBoxes();
    }
    getSelectedLayer(){
        return (this.layers[this.selectedLayer] ||{}).config ||{};
    }
    hasDrawnItems(){
        return this.drawnItems.getLayers().length>0;
    }
    getMap(){
        return this.map;
    }
    getDrawn(){
        return this.drawnItems;
    }
    updateTileCount(){
        let te=document.getElementById('numTiles');
        if (! te) return;
        te.classList.add('blink');
        let bounds=getBoundsFromSelections(this.drawnItems);
        apiRequest(this.apiBase,'countTiles?data='+encodeURIComponent(JSON.stringify(bounds)))
            .then((resp)=>{
                te.classList.remove('blink');
                if (resp.numTiles > resp.allowed){
                    te.classList.add('textError')
                }
                else{
                    te.classList.remove('textError');
                }
                te.textContent=resp.numTiles;
            })
            .catch((e)=>showError(e));
    }

    getSelectionBounds(){
        return getBoundsFromSelections(this.drawnItems);
    }
    getTileCount(bounds,z){
        let numTiles=0;
        let alreadyCounted=[];
        //tile counting - only for mode current zoom
        bounds.forEach((bound)=>{
            let maxTiles=tileCountForBounds(map,bound,z);
            //subtract intersections
            alreadyCounted.forEach((other)=>{
                let intersect=getIntersectionBounds(bound,other);
                if (intersect){
                    let intersectNum=tileCountForBounds(this.map,intersect,z);
                    maxTiles-=intersectNum;
                    if (maxTiles < 0) maxTiles=0; //hmmm
                }
            })
            numTiles+=maxTiles;
            alreadyCounted.push(bound);
        })
        return numTiles;
    }
    setSelections(selections){
        this.drawnItems.clearLayers();
        for (let i in selections){
            let box=selections[i];
            let rect=L.rectangle(
                [L.latLng(box._southWest),L.latLng(box._northEast)],
                SELECT_OPTIONS
            );
            rect.addEventParent(this.boxesLayer);
            this.drawnItems.addLayer(rect);
        }
        this.updateTileCount();
    }

    loadLayers(listParent) {
        for (let k in this.layers) {
            this.map.removeLayer(this.layers[k].map);
        }
        let suffix=encodeURIComponent((new Date()).getTime());
        apiRequest(this.apiBase, 'layers')
            .then((resp) => {
                if (resp && resp.data && resp.data.base) {
                    let cfg = resp.data.base;
                    let name = cfg.name;
                    let url = cfg.url;
                    let layer = L.tileLayer(url + '/{z}/{x}/{y}.png?_='+suffix, {});
                    layer.addTo(this.map);
                }
                if (resp && resp.data) {
                    let selectList=[];
                    let foundLayer=false;
                    for (let lname in resp.data) {
                        if (lname === 'base') continue;
                        let lconfig = resp.data[lname];
                        lconfig.name=lname;
                        let layer = L.tileLayer(lconfig.url + '/{z}/{x}/{y}.png?_='+suffix);
                        this.layers[lname] = {map:layer,config:lconfig};
                        selectList.push({
                            label:lname,
                            value:lname,
                            selected: lname === this.selectedLayer
                        });
                        if (lname === this.selectedLayer) {
                            foundLayer=true;
                            this.map.addLayer(layer);
                        }
                    }
                    if (! foundLayer){
                        if (selectList.length > 0){
                            this.selectedLayer=selectList[0].value;
                            selectList[0].selected=true;
                            this.map.addLayer(this.layers[this.selectedLayer].map);
                        }
                    }
                    buildSelect(listParent,selectList,(ev)=>{
                        let select=ev.target;
                        let selectedLayer=select.options[select.selectedIndex].value;
                        if (! selectedLayer) return;
                        let layer=this.layers[selectedLayer];
                        if (! layer || ! layer.map) return;
                        let old=this.layers[this.selectedLayer];
                        this.selectedLayer=selectedLayer;
                        if (old && old.map) this.map.removeLayer(old.map);
                        this.map.addLayer(layer.map);
                    });
                }
                this.map.invalidateSize();
            })
            .catch((e)=>showError(e));
    }

    getBoxes(){
        if (! this.showBoxes){
            this.boxesLayer.clearLayers();
            return;
        }
        this.boxesSequence++;
        let sequence=this.boxesSequence;
        if (this.boxesTimer) window.clearTimeout(this.boxesTimer);
        this.boxesTimer = window.setTimeout(() => {
            let z = this.map.getZoom();
            if (z !== Math.floor(z)){
                this.getBoxes();
                return;
            }
            let bound = this.map.getBounds();
            let url = this.apiBase + "/api/getBoxes?nelat=" + encodeURIComponent(bound.getNorthEast().lat) +
                "&nelng=" + encodeURIComponent(bound.getNorthEast().lng) +
                "&swlat=" + encodeURIComponent(bound.getSouthWest().lat) +
                "&swlng=" + encodeURIComponent(bound.getSouthWest().lng);
            let minZoom = z - 4;
            if (minZoom < 0) minZoom = 0;
            let maxZoom = z + 6;
            url += "&minZoom=" + encodeURIComponent(minZoom) +
                "&maxZoom=" + encodeURIComponent(maxZoom);
            fetch(url)
                .then((r) => r.text())
                .then((boxes) => {
                    if (sequence !== this.boxesSequence) return;
                    this.boxesLayer.clearLayers();
                    boxes = boxes.split("\n");
                    boxes.forEach((box) => {
                        let parts = box.split(/  */);
                        if (parts.length !== 6) return;
                        let zoom = parseInt(parts[1]);
                        let name = parts[0];
                        let rect = L.rectangle([
                            L.latLng(parseFloat(parts[2]), parseFloat(parts[3])),
                            L.latLng(parseFloat(parts[4]), parseFloat(parts[5]))
                        ], getBoxStyle(zoom));
                        rect.avzoom = zoom;
                        rect.avname = name;
                        /*
                        rect.on('click',()=>{
                            showToast(name+", zoom="+zoom);
                        })*/
                        this.boxesLayer.addLayer(rect);
                    })
                })
                .catch((e) => {
                });
        }, this.boxesTimeout);
    }

}