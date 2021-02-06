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
import {apiRequest, forEach, setTextContent, showError} from "./util";
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

export default class SeedMap{
    constructor(mapdiv,apiBase) {
        this.updateZoom=this.updateZoom.bind(this);
        this.updateTileCount=this.updateTileCount.bind(this);
        this.mapdiv=mapdiv;
        this.apiBase=apiBase;
        this.map=L.map('map').setView([54,13],6);
        this.drawnItems=new L.FeatureGroup();
        this.map.addLayer(this.drawnItems);
        this.updateZoom();
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
                    shapeOptions: {
                        clickable: true
                    }
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
        this.map.on('zoomend',this.updateZoom)
    }
    getSelectedLayer(){
        return this.selectedLayer;
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
    updateZoom(){
        setTextContent('#currentZoom',this.map.getZoom());
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
            let rect=L.rectangle([L.latLng(box._southWest),L.latLng(box._northEast)]);
            this.drawnItems.addLayer(rect);
        }
        this.updateTileCount();
    }

    loadLayers(listParentId) {
        for (let k in this.layers) {
            this.map.removeLayer(this.layers[k]);
        }
        apiRequest(this.apiBase, 'layers')
            .then((resp) => {
                if (resp && resp.data && resp.data.base) {
                    let cfg = resp.data.base;
                    let name = cfg.name;
                    let url = cfg.url;
                    let layer = L.tileLayer(url + '/{z}/{x}/{y}.png', {});
                    layer.addTo(this.map);
                }
                if (resp && resp.data) {
                    let layerList = document.getElementById(listParentId);
                    if (layerList) {
                        layerList.innerText = '';
                        let first = true;
                        for (let lname in resp.data) {
                            if (lname === 'base') continue;
                            let lconfig = resp.data[lname];
                            let item = document.createElement('div');
                            item.classList.add('layerSelect');
                            let rb = document.createElement('input');
                            rb.setAttribute('type', 'radio');
                            rb.setAttribute('name', 'layer');
                            if (first) {
                                rb.checked = true;
                                this.selectedLayer = lname;
                            }
                            let layer = L.tileLayer(lconfig.url + '/{z}/{x}/{y}.png');
                            this.layers[lname] = layer;
                            if (first) this.map.addLayer(layer);
                            rb.setAttribute('value', lname);
                            rb.addEventListener('change', ()=> {
                                forEach(layerList.querySelectorAll('input[type="radio"]'),
                                    (el) => {
                                        let layer = this.layers[el.getAttribute('value')];
                                        if (layer) {
                                            if (el.checked) {
                                                this.map.addLayer(layer);
                                                this.selectedLayer = el.getAttribute('value');
                                            } else this.map.removeLayer(layer);
                                        }
                                    })
                            });
                            first = false;
                            item.appendChild(rb);
                            let label = document.createElement('span');
                            label.innerText = lconfig.name;
                            item.appendChild(label);
                            layerList.appendChild(item);
                        }
                    }
                }
                this.map.invalidateSize();
            })
            .catch((e)=>showError(e));
    }

}