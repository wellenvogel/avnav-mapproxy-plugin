let updateStatus=function(ctx,name,value){
    if (ctx[name] !== value){
        ctx[name]=value;
        return true;
    }
    return false;
}
let template='<div class="mpState"><span class="mpLabel">Proxy</span><span class="mpStatusText ${mapproxy}"></span></div>'+
    '<div class="mpState"><span class="mpLabel">Net</span><span class="mpStatusText ${network}"></span></div>'+
    '<div class="mpState"><span class="mpLabel">Seed</span><span class="mpStatusText ${seed}"></span></div>';
let statusQuery=function(ctx){
    fetch(AVNAV_BASE_URL+"/api/status")
    .then(function(r){return r.json()})
    .then(function(status){
        let needsUpdate=false;
        needsUpdate = needsUpdate | updateStatus(ctx,'mapproxy',(status.mapproxy||{}).status);
        needsUpdate = needsUpdate | updateStatus(ctx,'network',status.networkAvailable);
        needsUpdate = needsUpdate | updateStatus(ctx,'seed',(status.seed||{}).status)
        needsUpdate = needsUpdate | updateStatus(ctx,'mode',status.networkMode)
        if (needsUpdate){
           ctx.triggerRedraw(); 
        }
    })
}    
let statusWidget={
    name: 'mpStatusWidget',
    unit:'',
    caption: 'MapProxy',
    initFunction: function(ctx){
        ctx.timer=window.setInterval(function(){statusQuery(ctx)},2000);
        statusQuery(ctx);
    },
    finalizeFunction: function(ctx){
        window.clearInterval(ctx.timer);
    },
    renderHtml:function(props){
        return avnav.api.templateReplace(template,{
            'mapproxy':this.mapproxy,
            'seed':this.seed,
            'network': this.network?'ok':'error'
        })
    }
}
let extendedTemplate='<div class="mpWrapper"><div class="mpStateWrapper">'+template+'</div>'+
    '<div class="mpButtons"><button class="${autoSel}" onclick="netAuto">Auto</button>'+
    '<button class="${onSel}" onclick="netOn">On</button><button class="${offSel}" onclick="netOff">Off</button></div></div>';
let extendedWidget=Object.assign({},statusWidget);

let switchNet=function(mode,ctx){
    fetch(AVNAV_BASE_URL+"/api/setNetworkMode?mode="+encodeURIComponent(mode))
    .then(function(resp){return resp.json()})
    .then(function(data){
        if (!data.status || data.status !== 'OK') throw new Error(data.status);
        ctx.mode=mode;
        ctx.triggerRedraw();
        statusQuery(ctx);
    })
    .catch(function(error){
        avnav.api.showToast(error+"");
    })
};
extendedWidget.name="mpControlWidget";
extendedWidget.initFunction=function(ctx){
    statusWidget.initFunction(ctx);
    ctx.eventHandler.netAuto=function(){switchNet('auto',ctx)};
    ctx.eventHandler.netOff=function(){switchNet('off',ctx)};
    ctx.eventHandler.netOn=function(){switchNet('on',ctx)};
}
extendedWidget.renderHtml=function(props){
    return avnav.api.templateReplace(extendedTemplate,{
        'mapproxy':this.mapproxy,
        'seed':this.seed,
        'network': this.network?'ok':'error',
        'autoSel': this.mode === 'auto'?'selected':'',
        'onSel': this.mode === 'on'?'selected':'',
        'offSel': this.mode === 'off'?'selected':'',
    })
}

avnav.api.registerWidget(statusWidget,{unit:false,caption:false,formatter:false});
avnav.api.registerWidget(extendedWidget,{unit:false,caption:false,formatter:false});
