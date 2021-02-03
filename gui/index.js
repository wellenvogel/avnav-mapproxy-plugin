(function(){
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
    let buttonActions={
        test:function(){alert("test")}
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
                self.addEventListener('click',function(ev){
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
        selectTab('statustab');
    })
})();