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
import '../style/index.less';
import '../lib/codeflask.css';
import SeedMap from "./map";
import Prismjs from 'prismjs';
import CodeFlask from "codeflask";
import yaml from 'js-yaml';
import 'whatwg-fetch';
import {
    buttonEnable,
    safeName,
    showHideOverlay,
    setCloseOverlayActions,
    showSelectOverlay,
    setStateDisplay,
    setTextContent,
    apiRequest,
    showError,
    forEachEl,
    getDateString,
    showToast,
    buildSelect,
    buildRadio,
    changeRadio, addEl
} from "./util";
(function(){
    let activeTab=undefined;
    let base=window.location.href.replace(/mapproxy\/gui.*/,'mapproxy');
    let map=undefined;
    let flask;
    let ignoreNextChanged=false;
    let lastSequence=undefined;
    let reloadDays=undefined;
    let hasReloadTime=false;
    let networkModeSt=undefined;
    let networkModeDl=undefined;
    let editedConfig=undefined;
    let codeChanged=function(changed){
        buttonEnable('saveEditOverlay',changed && ! ignoreNextChanged);
        ignoreNextChanged=false;
    }
    let getAndCheckConfig=()=>{
        if (! flask) return;
        let data=flask.getCode();
        let o;
        try{
            o=yaml.load(data,{schema:yaml.JSON_SCHEMA});
        }catch(e){
            showError("yaml error: "+e);
            return;
        }
        return data
    }
    let downloadConfig=(filename)=>{
        if (! filename) filename=editedConfig;
        if (! filename) return;
        let data=getAndCheckConfig();
        if (! data) return;
        downloadData(data,filename);
    }
    let saveConfig=function(){
        let data=getAndCheckConfig();
        if (! data) return;
        let name=editedConfig;
        if (! name) return;
        if (confirm("Really overwrite config "+name+"?")){
            apiRequest(base,'saveLayer?name='+encodeURIComponent(name)+'&data='+encodeURIComponent(data))
            .then((result)=>{
                showHideOverlay('editOverlay',false);
                updateLayers();
            })
            .catch(function(error){
                showError(error);
            })
            return ;
        }
    }
    let downloadData=function(data,name){
        const url="downloadData?data="+encodeURIComponent(data)+"&name="+encodeURIComponent(name);
        document.getElementById('downloadFrame').setAttribute('src',base+"/api/"+url);
    }
    let saveSelections=function(seedFor){
        let name="default";
        let ne=document.getElementById('selectionName');
        if (ne) name=ne.value;
        let bounds=map.getSelectionBounds();
        name=safeName(name);
        let url="saveSelection?data="+
            encodeURIComponent(JSON.stringify(bounds))+
            "&name="+encodeURIComponent(name);
        if (seedFor){
            url+="&startSeed="+encodeURIComponent(map.getSelectedLayer().name);
            if (reloadDays !== undefined){
                url+="&reloadDays="+encodeURIComponent(reloadDays);
            }
            let addBase=document.getElementById('includeBase');
            if (addBase && addBase.checked){
                url+="&baseLayer="+encodeURIComponent("base");
            }
        }
        apiRequest(base,url
        )
        .then((res)=>{
            showHideOverlay('spinnerOverlay',false);
            if (res.numTiles !== undefined){
                showToast("seed started with "+res.numTiles+" tiles");
            }
        })
        .catch((e)=>{
            showHideOverlay('spinnerOverlay',false);
            showError(e);
        });
    }
    let downloadSelection=()=>{
        let name="default";
        let ne=document.getElementById('selectionName');
        if (ne) name=ne.value;
        let bounds=map.getSelectionBounds();
        name=safeName(name)+".yaml";
        let data=yaml.dump(bounds,{schema:yaml.JSON_SCHEMA});
        if (! data) return;
        downloadData(data,name);
    }
    let uploadSelection=()=>{
        let fi=document.getElementById('uploadInput');
        fi.value='';
        fi.setAttribute('data-function','uploadSelection')
        fi.click();
    }
    let uploadHandlers={
        uploadSelection: (el)=>{
            if (! el.files || el.files.length < 1) return;
            let input=el.files[0];
            let reader=new FileReader();
            reader.onload=(data)=>{
                let code=reader.result;
                try {
                    let parsed = yaml.load(code, {schema: yaml.JSON_SCHEMA});
                    setTextContent('#selectionName',input.name.replace(/\.yaml/,''));
                    map.setSelections(parsed);
                }catch (e){
                    showError(e)
                }
            }
            reader.onerror=(e)=>showError(e);
            reader.readAsText(input);
        }
    }
    let fileInputSelectHandler=(ev)=>{
        let callback=uploadHandlers[ev.target.getAttribute('data-function')];
        if (! callback) return;
        callback(ev.target);
    }
    let startSeed=()=>{
        showHideOverlay('spinnerOverlay',true)
        saveSelections(true);
    }
    let showSelection=(name)=>{
        apiRequest(base,'loadSelection?name='+encodeURIComponent(name))
            .then((data)=>{
                setTextContent('#selectionName',name);
                map.setSelections(data.data);
            })
            .catch((e)=>showError(e));
    };
    let loadSelection=()=>{
        apiRequest(base,'listSelections')
            .then((data)=>{
                showSelectOverlay(data.data,"load selection")
                    .then((selected)=>showSelection(selected))
                    .catch(()=>{})
            })
            .catch((e)=>showError(e));
    }
    let deleteSelection=()=>{
        apiRequest(base,'listSelections')
            .then((data)=>{
                showSelectOverlay(data.data,"delete selection")
                    .then((selected)=>{
                        apiRequest(base,'deleteSelection?name='+encodeURIComponent(selected))
                            .then(()=>{})
                            .catch((e)=>showError(e))
                    })
                    .catch(()=>{})
            })
            .catch((e)=>showError(e));
    }
    let stopSeed=()=>{
        apiRequest(base,'killSeed')
            .then(()=>{})
            .catch((e)=>showError(e));
    }
    let showLog=()=>{
        fetch(base+"/api/getLog").then((resp)=>resp.text())
            .then((txt)=>{
                let logel=document.querySelector('#logOverlay .overlayContent');
                if (! logel) return;
                logel.textContent=txt;
                logel.scrollTop=logel.scrollHeight;
                showHideOverlay('logOverlay',true)
            })
            .catch((e)=>showError(e))
    }
    let editConfig=(name)=>{
        editedConfig=name;
        apiRequest(base,'editLayer?name='+encodeURIComponent(name))
            .then((data)=>{
                if (flask) flask.updateCode(data.data);
                codeChanged(false);
                ignoreNextChanged=true;
                showHideOverlay('editOverlay',true);
            })
            .catch((e)=>showError(e));
    }
    let changeNetworkMode=(mode)=>{
        apiRequest(base,'setNetworkMode?mode='+encodeURIComponent(mode))
            .then(()=>{})
            .catch((e)=>showError(e));
    }
    let downloadLog=()=>{
        let url=base+"/api/getLog?attach=true";
        document.getElementById('downloadFrame').setAttribute('src',url)
    };
    let addConfig=()=>{
        let nameEl=document.getElementById('configName');
        if (! nameEl) return;
        if (!nameEl.value) {
            showError("config name must not be empty");
            return;
        }
        apiRequest(base,'createLayer?name='+encodeURIComponent(nameEl.value))
            .then((data)=>{
                updateLayers();
                editConfig(nameEl.value);
            })
            .catch((e)=>showError(e));
    };
    let buttonActions={
        checkEditOverlay: getAndCheckConfig,
        downloadEditOverlay: ()=>downloadConfig(),
        saveEditOverlay: saveConfig,
        showLog: showLog,
        downloadLog: downloadLog,
        reloadLog: showLog,
        killSeed: stopSeed,
        stopSeed: stopSeed,
        save:()=>saveSelections(false),
        loadSelection: loadSelection,
        deleteSelection:deleteSelection,
        startSeed: startSeed,
        downloadSelection:downloadSelection,
        uploadSelection: uploadSelection,
        addConfig: addConfig
    }
    let buildLayerInfo=(layer,parent)=>{
        let lf=addEl('div','layerInfo',parent);
        addEl('span','label',lf,'Layer');
        addEl('span','value',lf,(layer.name||'').replace(/^mp-/,''));
        let caches=layer.caches;
        if (caches){
            let cf=addEl('div','cacheDownloadFrame',lf);
            for (let cname in caches){
                let cache=caches[cname];
                let ccfg=cache.cache ||{};
                if (ccfg && ccfg.type === 'mbtiles' && ccfg.filename){
                    let el=addEl('div','cacheDownload inlineButton',cf,cache.name||'');
                    el.setAttribute('data-href',base+'/api/getCacheFile?name='+encodeURIComponent(cache.name));
                    el.addEventListener('click',(ev)=>{
                        let url=ev.target.getAttribute('data-href');
                        document.getElementById('downloadFrame').setAttribute('src',url);
                    });
                }
                else{
                    addEl('span','cacheName',cf,cache.name);
                }
            }
        }
        return lf;
    }
    let buildConfigInfo=(config,parent)=>{
        let name=config.name;
        let lf=addEl('div','layerInfo',parent);
        addEl('span','label',lf,'Config');
        addEl('span','value',lf,(config.name||''));
        let ena=addEl('input','configEnable',lf);
        ena.setAttribute('type','checkbox');
        if (config.enabled) ena.checked=true;
        ena.addEventListener('change',(ev)=>{
            if (ev.target.checked) {
                apiRequest(base, 'enableLayer?name='+encodeURIComponent(name))
                    .then((x)=>{})
                    .catch((e)=> {
                        showError(e);
                        ena.checked = false;
                    });
            }
            else{
                apiRequest(base, 'disableLayer?name='+encodeURIComponent(name))
                    .then((x)=>{})
                    .catch((e)=> {
                        showError(e);
                        ena.checked = true;
                    });
            }
        });
        if (config.editable) {
            let edit = addEl('div', 'inlineButton', lf, 'Edit');
            edit.addEventListener('click',(ev)=>{
                editConfig(name);
            });
            let del = addEl('div','inlineButton',lf,'Delete');
            del.addEventListener('click',(ev)=>{
                if (! confirm("Really delete config "+name+"?")) return;
               apiRequest(base,'deleteLayer?name='+encodeURIComponent(name))
                   .then((d)=>updateLayers())
                   .catch((e)=>showError(e));
            });
        }
        return lf;
    }
    let updateLayers=()=>{
        if (activeTab === 'downloadtab') {
            map.loadLayers('#layerList');
            let sb=document.getElementById('showBoxes');
            if (sb){
                map.setShowBoxes(sb.checked);
            }
        }
        else {
            if (activeTab === 'statustab') {
                setTextContent('#statusLayers','');
                let parent=document.getElementById('statusLayers');
                if (! parent) return;
                apiRequest(base, 'layers')
                    .then((data) => {
                        if (! data.data) return;
                        for (let i in data.data){
                            let layer=data.data[i];
                            buildLayerInfo(layer,parent);
                        }
                    })
                    .catch((e) => showError(e));
                let cparent=document.getElementById('statusConfigs');
                if (! cparent) return;
                cparent.innerText='';
                apiRequest(base,'listConfigs')
                    .then((data)=>{
                        if (! data.data) return;
                        for (let i in data.data){
                            let config=data.data[i];
                            buildConfigInfo(config,cparent);
                        }
                    })
                    .catch((e)=>showError(e));
            }
        }
    }

    let selectTab=function(id){
        forEachEl('.tab',(tab)=>{
            tab.classList.remove('active');
        })
        forEachEl('.tabSelect .selector',(tab)=>{
            if (tab.getAttribute('data-tabid') === id){
                tab.classList.add('active');
            }
            else {
                tab.classList.remove('active');
            }
        })
        forEachEl('#'+id,(tab)=>{
            tab.classList.add('active');
        })
        activeTab=id;
        updateLayers();
    }
    let buildReloadSelect=(full)=>{
        let reloadSelectFull=[
            {label:'never',value:undefined,selected:true},
            {label: '1 year',value:360},
            {label: '6 month', value: 180},
            {label: '3 month',value: 90},
            {label: '4 weeks',value:28},
            {label: '1 week',value:7},
            {label: '1 day',value:1},
            {label: 'all',value:0}
        ]
        let reloadSelect=[
            {label:'never',value:undefined,selected:true},
            {label: 'all',value:0}
        ]
        buildSelect('#reloadTime',full?reloadSelectFull:reloadSelect,(ev)=>{
            let v=ev.target.options[ev.target.selectedIndex].value;
            if (v === 'undefined') v =undefined;
            reloadDays=v;
        });
        reloadDays=undefined;
    }
    let buildNetworkMode=()=>{
        let modes=[
            {label:'auto',value:'auto',checked:true},
            {label:'on',value:'on'},
            {label:'off',value:'off'}
        ]
        networkModeSt=buildRadio('#networkModeSt',modes,changeNetworkMode);
        networkModeDl=buildRadio('#networkModeDl',modes,changeNetworkMode);
    }
    let selectionChanged=()=>{
        let canSave = map && map.hasDrawnItems();
        buttonEnable('downloadSelection',canSave);
        buttonEnable('save',canSave);
    }

    window.addEventListener('load',function(){
        let title=document.getElementById('title');
        if (window.location.search.match(/title=no/)){
            if (title) title.style.display="none";
        }
        let toast=document.getElementById('toast');
        if (toast){
            toast.addEventListener('click',()=>showHideOverlay('toast'))
        }
        let demo=document.getElementById('demoFrame');
        if (demo) {
            demo.setAttribute('src',base+"/api/mapproxy/demo/");
        }
        let sb=document.getElementById('showBoxes');
        if (sb){
            sb.addEventListener('change',(ev)=>{
               map.setShowBoxes(ev.target.checked);
            });
        }
        let downloadFrame=document.getElementById('downloadFrame');
        if (downloadFrame){
            //if our download frame finishes laading this must be an error...
            downloadFrame.addEventListener('load',(e)=>{
                let etxt=undefined;
                try{
                    etxt=e.target.contentDocument.body.textContent;
                }catch (e){}
                showError((etxt !== undefined)?etxt.replace("\n"," "):"unable to download");
            });
        }
        let fileInput=document.getElementById('uploadInput');
        if (fileInput){
            fileInput.addEventListener('change',fileInputSelectHandler);
        }
        forEachEl('button,.button',(bt)=> {
                let handler = buttonActions[bt.getAttribute('id')] ||
                    buttonActions[bt.getAttribute('name')];
                if (handler) {
                    bt.addEventListener('click', handler);
                }
            });
        forEachEl('.tabSelect .selector',(sel)=>{
                sel.addEventListener('click',function(ev){
                    ev.preventDefault();
                    let id=ev.target.getAttribute('data-tabid');
                    if (id) selectTab(id);
                })
            });
        setCloseOverlayActions();
        buildReloadSelect();
        buildNetworkMode();
        flask=new CodeFlask('#editOverlay .overlayContent',{
            language: 'yaml',
            lineNumbers: true,
            defaultTheme: false
        });
        flask.addLanguage('yaml',Prismjs.languages['yaml']);
        flask.onUpdate(function(){codeChanged(true)});
        let networkState=document.getElementById('networkStatus');
        let selName=document.getElementById('selectionName');
        let d=new Date()
        if (selName) selName.value="selection-"+getDateString();
        let first=true;
        this.window.setInterval(function () {
            let canSave = map && map.hasDrawnItems();
            let url = 'status';
            apiRequest(base,url)
                .then(function (data) {
                    setStateDisplay('.networkState', data.network);
                    let seed=data.seed || {};
                    let seedStatus=seed.status;
                    let mapproxy=data.mapproxy||{};
                    setStateDisplay('.seedStatus',seedStatus);
                    setStateDisplay('.proxyStatus',mapproxy.status);
                    setTextContent('.proxySequence', (! mapproxy.lastError)?
                        "sequence "+parseInt(data.sequence):'');
                    setTextContent('.proxyError',mapproxy.lastError);

                    buttonEnable('startSeed',seedStatus !== 'running' && canSave
                        && ! seed.paused && data.networkAvailable);
                    buttonEnable('killSeed',seedStatus === 'running' || seed.paused);
                    buttonEnable('showLog',seed.logFile);
                    buttonEnable('downloadSelection',canSave);
                    buttonEnable('save',canSave);
                    changeRadio(networkModeSt,data.networkMode);
                    changeRadio(networkModeDl,data.networkMode);
                    let networkState='unknown';
                    if (data.networkAvailable !== undefined){
                        networkState=data.networkAvailable?'ok':'error';
                    }
                    setStateDisplay('.networkState',networkState);
                    let name=seed.name||'';
                    if (name instanceof Array) name=name.join(',');
                    name=(seed.selection||'')+' '+name;
                    setTextContent('.seedInfo',name+" "+(data.seed || {}).info)
                    forEachEl('#stopSeed',(el)=>{
                        el.style.display=(seedStatus === 'running')?'inline-block':'none'
                    })
                    if (data.sequence !== lastSequence){
                        if (lastSequence !== undefined) updateLayers();
                        lastSequence=data.sequence;
                    }
                    //check if we need to change the reload selection
                    let layerCaches=map.getSelectedLayer().caches;
                    let fullConfig=false;
                    if (layerCaches){
                        fullConfig=true;
                        layerCaches.forEach((lc)=>{
                            if (! lc.hasBefore) fullConfig=false;
                        })
                    }
                    if (hasReloadTime !== fullConfig){
                        buildReloadSelect(fullConfig);
                        hasReloadTime=fullConfig;
                    }
                })
                .catch(function (error) {
                    console.log(error);
                })
        }, 1000);
        map=new SeedMap('map',base,selectionChanged);
        selectTab('statustab');
    })
})();