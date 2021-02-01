let upload=require('./sftpUpload');

async function f(){
let res=await upload('x','y','z','aha','uhu');

console.log("res="+res);
}

f().then(()=>console.log("done"));