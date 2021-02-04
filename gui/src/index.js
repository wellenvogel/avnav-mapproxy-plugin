(function(){
    let map=undefined;
    let drawnItems = undefined;
    const forEach = function (array, callback, scope) {
        for (let i = 0; i < array.length; i++) {
            callback.call(scope, i, array[i]); // passes back stuff we need
        }
    };
    let flask;
    let apiRequest=function(command){
        let url="../api/"+command;
        return new Promise(function(resolve,reject){
            fetch(url)
            .then(function(r){
                return r.json();
            })
            .then(function(data){
                if (! data.status || data.status !== 'OK'){
                    reject("status: "+data.status);
                    retturn;
                }
                resolve(data);
                return;
            })
            .catch(function(error){
                reject(error);
            });
        });
    }

    let showHideOverlay=function(id,show){
        let ovl=id;
        if (typeof(id) === 'string'){
            ovl=document.getElementById(id);
        }
        if (!ovl) return;
        ovl.style.visibility=show?'unset':'hidden';
        return ovl;
    }
    let closeOverlayFromButton=function(btEvent){
        let target=btEvent.target;
        while (target && target.parentElement){
            target=target.parentElement;
            if (target.classList.contains('overlayFrame')){
                showHideOverlay(target,false);
                return;
            }
        }
    }
    let buttonEnable=function(id,enable){
        let bt=id;
        if (typeof(id) === 'string'){
            bt=document.getElementById(id);
        }
        if (! bt) return;
        if (enable){
            bt.removeAttribute('disabled');
        }
        else{
            bt.setAttribute('disabled','');
        }

    }

    let ignoreNextChanged=false;
    let codeChanged=function(changed){
        buttonEnable('saveEditOverlay',changed && ! ignoreNextChanged);
        ignoreNextChanged=false;
    }
    let showError=function(error){
        alert(error);
    }
    let showEdit=function(){
        showHideOverlay('editOverlay',true);
        fetch('../api/getConfig')
        .then(function(resp){
            return resp.text();
        })
        .then(function(text){
            if (flask) flask.updateCode(text);
            codeChanged(false);
            ignoreNextChanged=true;
        })
        .catch(function(error){
            showError(error);
        })
    }

    let saveConfig=function(){
        if (! flask) return;
        let data=flask.getCode();
        try{
            //validate data
        }catch(e){
            showError("internal error: "+e);
            return;
        }
        if (confirm("Really overwrite AvNav config and restart AvNav?")){
            fetch('../api/uploadConfig',{
                method: 'POST',
                headers:{
                    'Content-Type':'text/plain'
                },
                body: data
            })
            .then(function(resp){
                return resp.json();
            })
            .then(function(result){
                if (! result.status || result.status !== 'OK'){
                    showError(result.status);
                    return;
                }
                showHideOverlay('editOverlay',false);
                startAction('restart');
            })
            .catch(function(error){
                showError(error);
            })
            return ;
        }
    }
    let getTileFromLatLon=function(latLong,zoom){
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
    let getIntersectionBounds=function(first,second){
        let fne=first.getNorthEast();
        let fsw=first.getSouthWest();
        let sne=second.getNorthEast()
        let ssw=second.getSouthWest();
        let ne=L.latLng(Math.min(fne.lat,sne.lat),Math.min(fne.lng,sne.lng))
        let sw=L.latLng(Math.max(fsw.lat,ssw.lat),Math.max(fsw.lng,ssw.lng))
        if (ne.lat > sw.lat && ne.lng > sw.lng) return L.latLngBounds(ne,sw);
    }
    let getBoundsFromSelections=function(toPlain){
        if (! drawnItems) return [];
        let rt=[];
        drawnItems.getLayers().forEach(function(layer){
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
    let tileCountForBounds=function(bounds,z){
        let netile=getTileFromLatLon(bounds.getNorthEast(),z);
        let swtile=getTileFromLatLon(bounds.getSouthWest(),z);
        let xdiff=Math.abs(netile.x-swtile.x)+1;
        let ydiff=Math.abs(netile.y-swtile.y)+1;
        let zTiles=xdiff*ydiff;
        return zTiles;
    }
    let saveSelections=function(){
        let current=drawnItems;
        let name="default";
        let ne=document.getElementById('selectionName');
        if (ne) name=ne.value;
        let bounds=getBoundsFromSelections();
        let numTiles=0;
        let z=map.getZoom();
        let alreadyCounted=[];
        bounds.forEach(function(bound){
            let maxTiles=tileCountForBounds(bound,z);
            //subtract intersections
            alreadyCounted.forEach(function(other){
                let intersect=getIntersectionBounds(bound,other);
                if (intersect){
                    let intersectNum=tileCountForBounds(intersect,z);
                    maxTiles-=intersectNum;
                    if (maxTiles < 0) maxTiles=0; //hmmm
                }
            })
            numTiles+=maxTiles;
            alreadyCounted.push(bound);
        })
        alert("saving to "+name+", "+numTiles+" tiles on current zoom "+z);
    }
    let buttonActions={
        save:saveSelections
    }
    let selectTab=function(id){
        forEach(document.querySelectorAll('.tab'),function(i,tab){
            tab.classList.remove('active');
        })
        forEach(document.querySelectorAll('.tabSelect .selector'),function(i,tab){
            if (tab.getAttribute('data-tabid') === id){
                tab.classList.add('active');
            }
            else {
                tab.classList.remove('active');
            }
        })
        forEach(document.querySelectorAll('#'+id),function(i,tab){
            tab.classList.add('active');
        })
        map.invalidateSize();
    }
    window.addEventListener('load',function(){
        let title=document.getElementById('title');
        if (window.location.search.match(/title=no/)){
            if (title) title.style.display="none";
        }
        forEach(document.querySelectorAll('button'),
            function(i,bt) {
                let handler = buttonActions[bt.getAttribute('id')] ||
                    buttonActions[bt.getAttribute('name')];
                if (handler) {
                    bt.addEventListener('click', handler);
                }
            });
        forEach(document.querySelectorAll('.tabSelect .selector'),
            function (i,sel){
                sel.addEventListener('click',function(ev){
                    ev.preventDefault();
                    let id=ev.target.getAttribute('data-tabid');
                    if (id) selectTab(id);
                })
            });
        flask=new CodeFlask('#editOverlay .overlayContent',{
            language: 'markup',
            lineNumbers: true,
            defaultTheme: false
        });
        flask.onUpdate(function(){codeChanged(true)});
        let networkState=document.getElementById('networkStatus');
        let selName=document.getElementById('selectionName');
        let d=new Date()
        if (selName) selName.value="selection-"+d.getFullYear()+"-"+d.getMonth()+"-"+d.getDate();
        let first=true;
        this.window.setInterval(function(){
            let url='status';
            apiRequest(url)
            .then(function(data){
                if (networkState){
                    let newState='unknown';
                    if (data.network !== undefined){
                        if (data.network) newState='ok';
                        else newState='error';
                    }
                    if (! networkState.classList.contains(newState)){
                        let states=['unknown','error','ok'];
                        states.forEach(function(state){
                            if (state !== newState){
                                networkState.classList.remove(state);
                            }
                            else{
                                networkState.classList.add(state);
                            }
                        });
                    }
                }

            })
            .catch(function(error){
                console.log(error);
            })
        },1000);
        map=L.map('map').setView([54,13],6);
        drawnItems=new L.FeatureGroup();
        map.addLayer(drawnItems);

        let drawControl = new L.Control.Draw({
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
                featureGroup: drawnItems,
                remove: true
            }
        });
        map.addControl(drawControl);
        map.on(L.Draw.Event.CREATED, function (e) {
            let layer = e.layer;
            drawnItems.addLayer(layer);
        });
        let layers={};
        apiRequest('layers')
            .then(function(resp){
                if (resp && resp.data && resp.data.base){
                    let cfg=resp.data.base;
                    let name=cfg.name;
                    let url=cfg.url;
                    let layer = L.tileLayer(url+'/{z}/{x}/{y}.png',{
                        });
                    layer.addTo(map);
                }
                if (resp && resp.data){
                    let layerList=document.getElementById('layerFrame');
                    if (layerList){
                        layerList.innerText='';
                        let first=true;
                        for (let lname in resp.data) {
                            if (lname === 'base') continue;
                            let lconfig = resp.data[lname];
                            let item = document.createElement('div');
                            item.classList.add('layerSelect');
                            let rb = document.createElement('input');
                            rb.setAttribute('type', 'radio');
                            rb.setAttribute('name', 'layer');
                            if (first) rb.checked = true;
                            let layer=L.tileLayer(lconfig.url+'/{z}/{x}/{y}.png');
                            layers[lname]=layer;
                            if (first) map.addLayer(layer);
                            rb.setAttribute('value',lname);
                            rb.addEventListener('change',function(){
                                forEach(layerList.querySelectorAll('input[type="radio"]'),
                                    function(idx,el){
                                    let layer=layers[el.getAttribute('value')];
                                    if (layer) {
                                        if (el.checked) map.addLayer(layer);
                                        else map.removeLayer(layer);
                                    }
                                    })
                                map.invalidateSize();
                            });
                            first=false;
                            item.appendChild(rb);
                            let label = document.createElement('span');
                            label.innerText = lconfig.name;
                            item.appendChild(label);
                            layerList.appendChild(item);
                        }
                    }
                }
            })
            .catch(function(error){
                showError(error);
            })
        selectTab('statustab');
    })
})();