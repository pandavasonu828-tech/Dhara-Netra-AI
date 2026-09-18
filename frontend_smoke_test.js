const fs = require('fs');
const vm = require('vm');

const source = fs.readFileSync(__dirname + '/Frontend/script.js', 'utf8');
const ids = new Set();
for (const m of source.matchAll(/\$\(['"]([^'"]+)['"]\)/g)) ids.add(m[1]);
const elements = {};
function element(id) {
  if (!elements[id]) elements[id] = {
    id, value:'', textContent:'', innerHTML:'', className:'', disabled:false,
    style:{}, files:[], src:'', dataset:{},
    classList:{add(){},remove(){},toggle(){}},
    addEventListener(){}, focus(){}, scrollIntoView(){}, remove(){},
  };
  return elements[id];
}
const document = {
  getElementById:id=>element(id),
  querySelectorAll:()=>[],
  createElement:()=>element('created'),
};
const storage = {data:{},getItem(k){return this.data[k] ?? null},setItem(k,v){this.data[k]=String(v)},removeItem(k){delete this.data[k]}};
const window = {location:{protocol:'https:',origin:'https://example.test'},addEventListener(){},scrollTo(){}};
const responses = new Map();
function jsonResponse(obj,status=200){return {status,ok:status>=200&&status<300,headers:{get:()=> 'application/json'},text:async()=>JSON.stringify(obj)}}
responses.set('/api/request-otp', jsonResponse({status:'success',challenge_id:'challenge-1',demo_otp:'123456',expires_in:120}));
responses.set('/api/verify-otp', jsonResponse({status:'success',auth_token:'token-1'}));
responses.set('/api/test', jsonResponse({status:'success'}));
const fetch = async (url)=>responses.get(new URL(url).pathname) || jsonResponse({status:'success'});
const ctx={window,document,localStorage:storage,console,setTimeout,clearTimeout,setInterval,clearInterval,fetch,requestAnimationFrame:fn=>fn()};
window.window=window;
vm.createContext(ctx);
vm.runInContext(source,ctx,{filename:'Frontend/script.js'});

(async()=>{
  element('aadhaarInput').value='123456789012';
  await ctx.requestOtp();
 if (element('demoOtp').textContent !== '123456') throw new Error('OTP request flow failed');
  element('otpInput').value='123456';
  await ctx.verifyOtp();
  if (storage.getItem('dharaAuthToken') !== 'token-1') throw new Error('OTP verification flow failed');
  console.log('PASS: frontend startup');
  console.log('PASS: request OTP JSON response parsing');
  console.log('PASS: verify OTP JSON response parsing');
  console.log('ALL FRONTEND SMOKE TESTS PASSED');
})().catch(err=>{console.error(err);process.exit(1)});
