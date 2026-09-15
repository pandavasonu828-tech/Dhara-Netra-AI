const API = (window.location.protocol === 'file:') ? 'http://127.0.0.1:5000' : window.location.origin;
const $=id=>document.getElementById(id);
let selectedFile=null,citizen={},result=null,verified=false;
try{result=JSON.parse(localStorage.getItem('dharaLastResult')||'null');}catch(_){result=null;}
let authToken=localStorage.getItem('dharaAuthToken')||'';
let currentRole=localStorage.getItem('dharaRole')||'';
let challengeId=''; let otpTimer=null;
let session=JSON.parse(localStorage.getItem('dharaSession')||'{"processed":0,"matches":0,"reviews":0,"verified":0}');
const labels={record_name:'Name',owner_name:'Owner Name',khata_number:'Khata Number',survey_number:'Survey Number',village:'Village',mandal:'Mandal',district:'District',address:'Address',extent:'Area (Acres)',land_type:'Type of Land',assessment_number:'Assessment Number',document_number:'Document Number',date:'Date',father_husband_name:'Father/Husband Name'};
const officerPages=['dashboard','metrics','compare','lrms','audit','gis','duplicate','reviewQueue'];
const citizenPages=['register','upload','processing','verification','human','record'];
function isLoggedIn(){return !!authToken}
function updateNavForRole(){document.querySelectorAll('.navlinks button[data-role]').forEach(b=>{const r=b.dataset.role; b.style.display=(r==='both'||(r===currentRole))?'':'none'});}
function go(page){
  if(citizenPages.includes(page)){if(!isLoggedIn()){page='login'}else if(currentRole!=='citizen'){page='home'}}
  if(officerPages.includes(page)){if(!isLoggedIn()){page='officerLogin'}else if(currentRole!=='officer'){page='home'}}
  document.querySelectorAll('.page').forEach(x=>x.classList.remove('active'));
  const p=$(page);if(p)p.classList.add('active');
  updateNavForRole();
  document.querySelectorAll('.navlinks button').forEach(b=>b.classList.toggle('active',b.dataset.page===page));
  window.scrollTo({top:0,behavior:'smooth'});
  if(page==='dashboard')updateDashboard(); if(page==='metrics')renderMetricsLab(); if(page==='reviewQueue')loadReviewQueue(); if(page==='audit')loadAudit(); if(page==='lrms' && ($('lrmsSurvey')?.value||'').trim())loadLRMS(); if(page==='gis' && ($('gisSurvey')?.value||'').trim())loadGIS();
}
function startCitizen(){currentRole='citizen';localStorage.setItem('dharaRole','citizen');go('login')}
function startOfficer(){currentRole='officer';localStorage.setItem('dharaRole','officer');go('officerLogin')}
function startApp(){startCitizen()}
function maskAadhaar(v){const d=String(v||'').replace(/\D/g,'');return d.length===12?'XXXX-XXXX-'+d.slice(-4):'XXXX-XXXX-XXXX'}
function setAuthStatus(t,ok=false){if($('authStatus')){$('authStatus').textContent=t;$('authStatus').className=ok?'successbox':'notice'}}
async function requestOtp(){const raw=($('aadhaarInput').value||'').replace(/\D/g,'');if(raw.length!==12){setAuthStatus('Please enter a valid 12-digit Aadhaar number.');return} $('requestOtpBtn').disabled=true;setAuthStatus('Generating OTP…');try{const r=await fetch(API+'/api/request-otp',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({aadhaar:raw})});const d=await r.json();if(!r.ok||d.status!=='success')throw new Error(d.message||'Unable to generate OTP');challengeId=d.challenge_id;$('otpPanel').classList.remove('hidden');$('demoOtp').textContent=d.demo_otp;$('demoOtpBox').classList.remove('hidden');startOtpTimer(d.expires_in||120);setAuthStatus('OTP generated. For this local prototype, the demo OTP is displayed below. In production it would be delivered by an authorized OTP provider.',true);$('otpInput').focus();}catch(e){setAuthStatus(e.message)}finally{$('requestOtpBtn').disabled=false}}
function startOtpTimer(seconds){clearInterval(otpTimer);let left=seconds;const tick=()=>{const m=String(Math.floor(left/60)).padStart(2,'0'),s=String(left%60).padStart(2,'0');$('otpTimer').textContent=`OTP expires in ${m}:${s}`;if(left<=0){clearInterval(otpTimer);$('otpTimer').textContent='OTP expired — request a new OTP.';$('verifyOtpBtn').disabled=true}else left--};tick();otpTimer=setInterval(tick,1000);$('verifyOtpBtn').disabled=false}
async function verifyOtp(){const otp=($('otpInput').value||'').replace(/\D/g,'');if(otp.length!==6){setAuthStatus('Enter the 6-digit OTP.');return} $('verifyOtpBtn').disabled=true;try{const r=await fetch(API+'/api/verify-otp',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({challenge_id:challengeId,otp})});const d=await r.json();if(!r.ok||d.status!=='success')throw new Error(d.message||'Invalid OTP');authToken=d.auth_token;currentRole='citizen';localStorage.setItem('dharaAuthToken',authToken);localStorage.setItem('dharaRole','citizen');clearInterval(otpTimer);setAuthStatus('✓ OTP verified successfully. Registration is now unlocked.',true);$('otpPanel').classList.add('hidden');$('demoOtpBox').classList.add('hidden');setTimeout(()=>go('register'),350);}catch(e){setAuthStatus(e.message);$('verifyOtpBtn').disabled=false}}
async function officerLogin(){const employee=($('officerId')?.value||'').trim();const password=$('officerPassword')?.value||'';if(employee.length<3||password.length<6){$('officerStatus').className='dangerbox';$('officerStatus').textContent='Enter an employee ID and a password of at least 6 characters.';return}try{const r=await fetch(API+'/api/officer/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({employee_id:employee,password})});const d=await r.json();if(!r.ok||d.status!=='success')throw new Error(d.message||'Officer login failed');authToken=d.auth_token;currentRole='officer';localStorage.setItem('dharaAuthToken',authToken);localStorage.setItem('dharaRole','officer');$('officerStatus').className='successbox';$('officerStatus').textContent='✓ Officer session created for this local prototype.';setTimeout(()=>go('dashboard'),300)}catch(e){$('officerStatus').className='dangerbox';$('officerStatus').textContent=e.message}}
function resendOtp(){$('otpInput').value='';requestOtp()}
function logout(){if(authToken){fetch(API+'/api/logout',{method:'POST',headers:{'X-Auth-Token':authToken}}).catch(()=>{})}authToken='';challengeId='';clearInterval(otpTimer);otpTimer=null;citizen={};result=null;verified=false;selectedFile=null;localStorage.removeItem('dharaAuthToken');localStorage.removeItem('dharaCitizen');localStorage.removeItem('dharaRole');currentRole='';go('home')}
function saveCitizen(){citizen={owner_name:$('owner_name').value.trim(),khata_number:$('khata_number').value.trim(),survey_number:$('survey_number').value.trim(),village:$('village').value.trim(),district:$('district').value.trim(),area:$('area').value.trim(),land_type:$('land_type').value.trim(),address:$('address').value.trim()};return citizen;}
const drop=$('drop'),file=$('file');
if(drop&&file){drop.addEventListener('click',()=>file.click());file.addEventListener('change',()=>selectFile(file.files[0]));['dragenter','dragover'].forEach(e=>drop.addEventListener(e,x=>{x.preventDefault();drop.style.borderColor='#1769aa'}));['dragleave','drop'].forEach(e=>drop.addEventListener(e,x=>{x.preventDefault();drop.style.borderColor='#b6cadb'}));drop.addEventListener('drop',e=>selectFile(e.dataTransfer.files[0]));}
$('docA')?.addEventListener('change',e=>{ $('docAName').textContent=e.target.files[0]?`Selected: ${e.target.files[0].name}`:'No file selected'; }); $('docB')?.addEventListener('change',e=>{ $('docBName').textContent=e.target.files[0]?`Selected: ${e.target.files[0].name}`:'No file selected'; });
function selectFile(f){if(!f)return;if(!['image/jpeg','image/png'].includes(f.type)){alert('For the current OCR prototype, choose JPG, JPEG or PNG.');return}selectedFile=f;$('process').disabled=false;$('fileInfo').textContent=`Selected: ${f.name} · ${(f.size/1024/1024).toFixed(2)} MB`;const r=new FileReader();r.onload=e=>{$('preview').src=e.target.result;$('preview').style.display='block'};r.readAsDataURL(f);}
async function processBundledLegacyDemo(){
  if(!authToken){go('login');return}
  saveCitizen(); go('processing'); $('progress').classList.remove('hidden'); $('process').disabled=true;
  setProgress(25,'Loading bundled legacy handwritten form…');
  try{
    const r=await fetch(API+'/api/process-test-document',{method:'POST',headers:{'Content-Type':'application/json','X-Auth-Token':authToken},body:JSON.stringify({filename:'legacy_handwritten_land_record.jpg',citizen})});
    const data=await r.json();
    if(!r.ok||data.status!=='success')throw new Error(data.message||'Demo processing failed');
    setProgress(70,'Running handwriting-aware field extraction and validation…'); await new Promise(r=>setTimeout(r,300));
    result=data; localStorage.setItem('dharaLastResult',JSON.stringify({filename:data.filename,fields:data.fields||{},comparisons:data.comparisons||{},confidence:data.confidence||{},validation:data.validation||{},lrms_link:data.lrms_link||{}})); const comps=Object.values(data.comparisons||{}); session.processed++; session.matches+=comps.filter(x=>x.status==='MATCH').length; session.reviews+=Object.values(data.confidence||{}).filter(x=>x.status==='NEEDS_REVIEW').length; localStorage.setItem('dharaSession',JSON.stringify(session));
    setProgress(100,'Legacy handwritten demo completed ✓'); displayResult(); setTimeout(()=>go('verification'),300);
  }catch(e){alert('Legacy demo failed: '+e.message+'\n\nThe hosted Dhara-Netra AI service is unavailable or returned an error. Open /health to check the OCR service.');go('upload');setProgress(0,'Processing failed');}
  finally{$('process').disabled=false}
}

async function processDocument(){if(!authToken){go('login');return}if(!selectedFile)return;saveCitizen();go('processing');$('progress').classList.remove('hidden');$('process').disabled=true;setProgress(20,'Uploading actual document…');const fd=new FormData();fd.append('document',selectedFile);Object.entries(citizen).forEach(([k,v])=>fd.append(k,v));try{setProgress(45,'Running OCR and field extraction…');const res=await fetch(API+'/api/process',{method:'POST',headers:{'X-Auth-Token':authToken},body:fd});const data=await res.json();if(res.status===401){logout();throw new Error('Your authentication session expired. Please verify OTP again.')}if(!res.ok||data.status!=='success')throw new Error(data.message||'Processing failed');setProgress(75,'Validating and comparing…');await new Promise(r=>setTimeout(r,250));result=data;localStorage.setItem('dharaLastResult',JSON.stringify({filename:data.filename,fields:data.fields||{},comparisons:data.comparisons||{},confidence:data.confidence||{},validation:data.validation||{},lrms_link:data.lrms_link||{}}));const comps=Object.values(data.comparisons||{});session.processed++;session.matches+=comps.filter(x=>x.status==='MATCH').length;session.reviews+=Object.values(data.confidence||{}).filter(x=>x.status==='NEEDS_REVIEW').length;localStorage.setItem('dharaSession',JSON.stringify(session));setProgress(100,'Processing completed ✓');displayResult();setTimeout(()=>go('verification'),300);}catch(e){alert('Document processing failed: '+e.message+'\n\nThis is the hosted Dhara-Netra AI service. If the problem continues, open the service /health page and check the Render logs.');go('upload');setProgress(0,'Processing failed');}finally{$('process').disabled=false;}}
function setProgress(v,t){$('bar').style.width=v+'%';$('progressLabel').textContent=t}
function esc(v){return String(v??'—').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]))}
function displayResult(){if(!result)return;const f=result.fields||{},c=result.comparisons||{},conf=result.confidence||{};const order=['record_name','owner_name','father_husband_name','khata_number','survey_number','village','mandal','district','address','extent','land_type','assessment_number','document_number','date'];let rows='';order.forEach(k=>{const citizenKey=k==='extent'?'area':k;const citizenVal=citizen[citizenKey]||'—',extracted=f[k]||'Not extracted',comp=c[k];let status=!citizen[citizenKey]?(f[k]?'NOT COMPARED':'NEEDS REVIEW'):comp?.status==='MATCH'?'MATCH':comp?.status==='MISMATCH'?'MISMATCH':(!f[k]?'NEEDS REVIEW':'REVIEW');let cls=status==='MATCH'?'match':status==='MISMATCH'?'mismatch':status==='NOT COMPARED'?'':'review';const compInfo=conf[k]?.components?`<div class="muted" style="font-size:10px;margin-top:4px">OCR evidence ${conf[k].components.ocr_evidence}% · Rule validation ${conf[k].components.rule_validation}% · Cross-source ${esc(conf[k].components.cross_source)}</div>`:'';rows+=`<tr><td><b>${labels[k]}</b></td><td>${esc(citizenVal)}</td><td>${esc(extracted)}${compInfo}</td><td><span class="status ${cls}">${status}</span></td><td class="confidence">${conf[k]?.score??0}%</td></tr>`});$('comparisonBody').innerHTML=rows;$('resultMessage').innerHTML=`<b>Actual file processed:</b> ${esc(result.filename)} · ${esc(result.validation?.summary?.message||'')}`+(result.lrms_link?.linked?`<div class="notice" style="margin-top:10px"><b>LRMS history link:</b> matched survey <b>${esc(result.lrms_link.best_match?.survey_number)}</b> to ${esc(result.lrms_link.matches?.length||0)} historical record(s). Best match: <b>${esc(result.lrms_link.best_match?.owner_name)}</b>, ${esc(result.lrms_link.best_match?.area)} acres.</div>`:'')+(result.handwriting_evidence&&Object.keys(result.handwriting_evidence).length?`<div class="notice" style="margin-top:10px"><b>Handwriting-aware mode:</b> This legacy form used field-crop OCR plus a verified demo-template transcript fallback. Values are extracted for the supplied fixture, but remain review-priority and this mode is not a claim of general handwriting recognition.</div>`:'');const review=Object.entries(conf).filter(([k,v])=>v.status==='NEEDS_REVIEW'||c[k]?.status==='MISMATCH');$('reviewFields').innerHTML=review.length?review.map(([k,v])=>`<div class="review-item"><b>${labels[k]||k}</b><div class="muted">OCR extracted: <b>${esc(f[k]||'Not extracted')}</b> · Confidence: <b>${v.score}%</b> ${c[k]?.status==='MISMATCH'?'· Citizen mismatch':''}</div><input data-edit="${k}" value="${esc(f[k]||'')}"></div>`).join(''):'<div class="successbox">No fields were flagged by the current prototype rules.</div>';verified=false;$('reviewMsg').textContent='Check flagged values against the original document before approval.';$('lastRun').innerHTML=`Last run: <b>${esc(result.filename)}</b> · ${Object.keys(f).length} extracted fields.`;renderRuntimeMetrics();}
async function recordAuditEvent(action,recordId,details){
  if(!authToken)return;
  try{await fetch(API+'/api/audit/event',{method:'POST',headers:{'Content-Type':'application/json','X-Auth-Token':authToken},body:JSON.stringify({action,record_id:recordId||null,details:details||''})});}catch(e){console.log('Audit event could not be recorded:',e.message)}
}
async function approveReview(){if(!result)return;verified=true;session.verified++;localStorage.setItem('dharaSession',JSON.stringify(session));const rid='DHR-'+Date.now().toString().slice(-8);result.verified_record_id=rid;await recordAuditEvent('HUMAN_APPROVAL',rid,`Approved document ${result.filename}; LRMS link checked=${!!result.lrms_link?.linked}`);buildFinal(false);go('record')}
async function editReview(){if(!result)return;document.querySelectorAll('[data-edit]').forEach(inp=>{const k=inp.dataset.edit;if(inp.value.trim())result.fields[k]=inp.value.trim()});verified=true;session.verified++;localStorage.setItem('dharaSession',JSON.stringify(session));const rid='DHR-'+Date.now().toString().slice(-8);result.verified_record_id=rid;await recordAuditEvent('HUMAN_CORRECTION_AND_APPROVAL',rid,`Corrected and approved document ${result.filename}`);buildFinal(true);go('record')}
function buildFinal(edited){const f=result.fields||{};const order=['owner_name','father_husband_name','khata_number','survey_number','village','mandal','district','address','extent','land_type','assessment_number','document_number','date'];let rows=order.map(k=>`<tr><td><b>${labels[k]||k}</b></td><td>${esc(f[k]||'Not available')}</td><td>${esc(result.validation?.[k]?.status||'—')}</td><td>${esc((result.confidence?.[k]?.score??0)+'%')}</td></tr>`).join('');const officerActions=currentRole==='officer'?`<button class="btn primary" onclick="go('lrms')">View LRMS History</button><button class="btn" onclick="go('gis')">View GIS Map</button><button class="btn" onclick="go('audit')">View Audit Trail</button>`:'<div class="officer-note" style="margin-top:12px"><b>Officer workspace:</b> Authorized government officers can use the separate Officer Portal to link the verified record with LRMS history, audit tracking and GIS mapping.</div>';$('finalBox').innerHTML=`<div class="successbox"><h3 style="margin:0 0 6px">✓ Digital Land Record Generated</h3><p style="margin:0">Source: <b>${esc(result.filename)}</b> · ${edited?'Human corrected':'Human approved'} · Record ID: <b>${esc(result.verified_record_id||('DHR-'+Date.now().toString().slice(-8)))}</b></p></div><div class="card" style="margin-top:15px"><div class="table-wrap"><table class="final-table"><thead><tr><th>Field</th><th>Verified Value</th><th>Validation</th><th>Confidence</th></tr></thead><tbody>${rows}</tbody></table></div></div><div class="notice" style="margin-top:15px">Prototype output only. This does not legally certify ownership, authenticity or fraud status.</div><div class="actions">${officerActions}<button class="btn" onclick="window.print()">Print / Save PDF</button></div>`}
function updateDashboard(){$('statProcessed').textContent=session.processed;$('statMatches').textContent=session.matches;$('statReviews').textContent=session.reviews;$('statVerified').textContent=session.verified}
function renderRuntimeMetrics(){if(!result||!$('runtimeMetrics'))return;const comps=Object.values(result.comparisons||{});const compared=comps.filter(x=>x.status==='MATCH'||x.status==='MISMATCH');const matches=compared.filter(x=>x.status==='MATCH').length;const mismatch=compared.filter(x=>x.status==='MISMATCH').length;const fields=Object.values(result.fields||{});const required=['district','mandal','village','survey_number','extent','land_type','owner_name','document_number'];const complete=required.filter(k=>result.fields?.[k]).length;const exact=fields.length?fields.filter(v=>v).length:0;const exactRate=fields.length?100:0;$('runtimeMetrics').innerHTML=`<div class="stats"><div class="stat"><span>Field Matches</span><b>${matches}</b></div><div class="stat"><span>Mismatch Rate</span><b>${compared.length?(mismatch/compared.length*100).toFixed(1):'0.0'}%</b></div><div class="stat"><span>Completeness</span><b>${(complete/required.length*100).toFixed(1)}%</b></div><div class="stat"><span>Extracted Fields</span><b>${exact}</b></div></div><div class="notice" style="margin-top:14px"><b>Evaluation note:</b> CER/WER, precision, recall and F1 require a labeled ground-truth dataset. This screen does not invent those numbers from a single uploaded document.</div>`}
async function loadReviewQueue(){
  const box=$('reviewQueueResult'); if(!box)return;
  box.innerHTML='<div class="notice"><b>Loading pending officer review cases…</b></div>';
  try{const r=await fetch(API+'/api/review-queue?status=PENDING&_='+Date.now(),{headers:{'X-Auth-Token':authToken,'Cache-Control':'no-cache'},cache:'no-store'});const d=await r.json();if(!r.ok||d.status!=='success')throw new Error(d.message||'Review queue lookup failed');
    const count=d.count||0; const summary=d.summary||{};
    let rows=d.cases.map(c=>`<tr><td><b>${esc(c.case_id)}</b></td><td>${new Date(c.created_at*1000).toLocaleString()}</td><td>${esc(c.source_filename)}</td><td>${esc((c.review_fields||[]).map(k=>labels[k]||k).join(', ')||'Review')}</td><td><span class="status review">PENDING</span></td><td><button class="btn primary" style="padding:7px 10px" onclick="openReviewCase('${esc(c.case_id)}')">Open Review</button></td></tr>`).join('');
    box.innerHTML=`<div class="stats"><div class="stat"><span>Pending Cases</span><b>${count}</b></div><div class="stat"><span>Approved Cases</span><b>${summary.APPROVED||0}</b></div><div class="stat"><span>Review Model</span><b style="font-size:17px">Human-in-loop</b></div><div class="stat"><span>Decision</span><b style="font-size:17px">Officer</b></div></div><div class="notice" style="margin-top:14px"><b>Persistent queue:</b> flagged processing cases are stored in the local prototype database. An officer can inspect the original document, citizen submission, extracted fields and validation signals before approving or correcting the case.</div><div class="table-wrap" style="margin-top:14px"><table class="table"><thead><tr><th>Case</th><th>Created</th><th>Document</th><th>Flagged fields</th><th>Status</th><th>Action</th></tr></thead><tbody>${rows||'<tr><td colspan="6">No pending human-verification cases.</td></tr>'}</tbody></table></div>`;
  }catch(e){box.innerHTML=`<div class="dangerbox">${esc(e.message)}</div>`}
}
async function openReviewCase(caseId){
  const box=$('reviewCaseDetail'); if(!box)return; box.classList.remove('hidden'); box.innerHTML='<div class="notice"><b>Loading review case…</b></div>';
  try{const r=await fetch(API+'/api/review-queue/'+encodeURIComponent(caseId),{headers:{'X-Auth-Token':authToken}});const d=await r.json();if(!r.ok||d.status!=='success')throw new Error(d.message||'Could not load case');const c=d.case||{}, res=c.result||{}, f=res.fields||{}, citizenData=c.citizen||{};
    const order=['owner_name','father_husband_name','khata_number','survey_number','village','mandal','district','address','extent','land_type','assessment_number','document_number','date'];
    const flagged=new Set(c.review_fields||[]); let rows=order.filter(k=>f[k]||citizenData[k==='extent'?'area':k]||flagged.has(k)).map(k=>{const cv=citizenData[k==='extent'?'area':k]||'—';const ev=f[k]||'Not extracted';const st=res.comparisons?.[k]?.status||res.validation?.[k]?.status||'—';const cls=st==='MATCH'?'match':(st==='MISMATCH'?'mismatch':(flagged.has(k)?'review':''));return `<tr><td><b>${labels[k]||k}</b></td><td>${esc(cv)}</td><td><input class="review-edit" data-case-edit="${k}" value="${esc(ev)}"></td><td><span class="status ${cls}">${esc(st)}</span></td><td>${esc((res.confidence?.[k]?.score??'—')+'%')}</td></tr>`}).join('');
    box.innerHTML=`<div class="card"><div class="section-title"><h3 style="margin-bottom:5px">Review Case ${esc(c.case_id)}</h3><p>Officer review of the original uploaded document and extracted/compared evidence.</p></div><div class="review-detail-grid"><div><div class="review-original"><img src="${API}${esc(c.document_url||('/api/uploads/'+c.source_filename))}" alt="Original uploaded land document"></div><p class="muted" style="font-size:11px">Original source: <b>${esc(c.source_filename)}</b></p></div><div><div class="table-wrap"><table class="table"><thead><tr><th>Field</th><th>Citizen</th><th>Extracted / Editable</th><th>Validation</th><th>Confidence</th></tr></thead><tbody>${rows}</tbody></table></div></div></div><div class="field" style="margin-top:15px"><label>Officer Remarks</label><textarea id="officerReviewRemarks" placeholder="Record why the case was approved or corrected..."></textarea></div><div class="notice" style="margin-top:12px"><b>Officer decision rule:</b> verify flagged values against the original document and available authorized records. Family relationships are not treated as ownership history unless an explicit registered LRMS record exists.</div><div class="actions"><button class="btn success" onclick="decideReviewCase('${esc(c.case_id)}','APPROVED')">✓ Approve Case</button><button class="btn primary" onclick="decideReviewCase('${esc(c.case_id)}','CORRECTED')">✎ Correct & Approve</button><button class="btn" onclick="$('reviewCaseDetail').classList.add('hidden')">Close</button></div></div>`;
    box.scrollIntoView({behavior:'smooth',block:'start'});
  }catch(e){box.innerHTML=`<div class="dangerbox">${esc(e.message)}</div>`}
}
async function decideReviewCase(caseId,decision){
  const payload={decision,remarks:$('officerReviewRemarks')?.value||''};
  if(decision==='CORRECTED'){document.querySelectorAll('[data-case-edit]').forEach(i=>{payload.fields=payload.fields||{};payload.fields[i.dataset.caseEdit]=i.value.trim()});}
  try{const r=await fetch(API+'/api/review-queue/'+encodeURIComponent(caseId)+'/decision',{method:'POST',headers:{'Content-Type':'application/json','X-Auth-Token':authToken},body:JSON.stringify(payload)});const d=await r.json();if(!r.ok||d.status!=='success')throw new Error(d.message||'Could not record decision');alert('Officer decision recorded successfully.');$('reviewCaseDetail').classList.add('hidden');await loadReviewQueue();}catch(e){alert(e.message)}
}

async function compareDocs(){if(!authToken){go('login');return}const a=$('docA').files[0],b=$('docB').files[0];if(!a||!b){alert('Choose both documents first.');return}const fd=new FormData();fd.append('document_a',a);fd.append('document_b',b);const box=$('compareResult');box.classList.remove('hidden');box.innerHTML='<b>Processing both documents…</b><p class="muted">Each file is OCR-processed independently before comparison.</p>';try{const r=await fetch(API+'/api/compare-documents',{method:'POST',headers:{'X-Auth-Token':authToken},body:fd});const d=await r.json();if(r.status===401){logout();throw new Error('Authentication session expired. Please verify OTP again.')}if(!r.ok||d.status!=='success')throw new Error(d.message||'Comparison failed');let rows='';for(const [k,v] of Object.entries(d.comparison||{})){const cls=v.status==='MATCH'?'match':v.status==='MISMATCH'?'mismatch':(v.status==='NOT_PRESENT'?'':'review');rows+=`<tr><td><b>${labels[k]||k}</b></td><td>${esc(v.a||'Not extracted')}</td><td>${esc(v.b||'Not extracted')}</td><td><span class="status ${cls}">${v.status}</span></td></tr>`}box.innerHTML=`<h3>Comparison Result</h3><p><b>${d.difference_count}</b> field(s) differ or need review.</p><div class="diff"><table><thead><tr><th>Field</th><th>Document A</th><th>Document B</th><th>Status</th></tr></thead><tbody>${rows}</tbody></table></div>`}catch(e){box.innerHTML=`<div class="dangerbox">${esc(e.message)}</div>`}}
function latestExtractedLines(){
  if(!result?.fields)return [];
  const preferred=['survey_number','owner_name','khata_number','village','mandal','district','address','extent','land_type','assessment_number','document_number','date'];
  return preferred.map(k=>String(result.fields[k]||'').trim()).filter(Boolean);
}
function renderMetricsLab(){
  const box=$('liveMetrics'); if(!box)return;
  if(!result){
    box.innerHTML='<div class="notice"><b>No processed document yet.</b> Process a document in the Citizen Portal first. Runtime metrics will then be calculated from that actual extraction. No sample/default values are inserted.</div>';
    return;
  }
  const f=result.fields||{}, c=result.comparisons||{}, conf=result.confidence||{};
  const keys=Object.keys(f).filter(k=>String(f[k]||'').trim());
  const compared=Object.values(c).filter(x=>x&&(x.status==='MATCH'||x.status==='MISMATCH'));
  const matches=compared.filter(x=>x.status==='MATCH').length;
  const mismatch=compared.filter(x=>x.status==='MISMATCH').length;
  const required=['district','mandal','village','survey_number','extent','land_type','owner_name','document_number'];
  const complete=required.filter(k=>String(f[k]||'').trim()).length;
  const scores=Object.values(conf).map(x=>Number(x?.score)).filter(Number.isFinite);
  const avg=scores.length?scores.reduce((a,b)=>a+b,0)/scores.length:null;
  box.innerHTML=`<div class="successbox"><b>Live evaluation from latest uploaded document:</b> ${esc(result.filename||'processed document')}</div>
  <div class="stats" style="margin-top:14px">
    <div class="stat"><span>Extracted Fields</span><b>${keys.length}</b></div>
    <div class="stat"><span>Required-field Completeness</span><b>${(complete/required.length*100).toFixed(1)}%</b></div>
    <div class="stat"><span>Citizen/Document Matches</span><b>${matches}</b></div>
    <div class="stat"><span>Field Mismatch Rate</span><b>${compared.length?(mismatch/compared.length*100).toFixed(1):'N/A'}%</b></div>
  </div>
  <div class="notice" style="margin-top:14px"><b>Average field confidence:</b> ${avg===null?'Not available':avg.toFixed(1)+'%'} · <b>Compared fields:</b> ${compared.length}. These are runtime prototype measurements from the actual processing result.</div>
  <div class="notice" style="margin-top:10px"><b>Important:</b> CER/WER, precision/recall/F1 and ECE require verified labels or a labeled evaluation set. The system will not invent those values from one document.</div>`;
  const pred=$('metricPreds');
  if(pred && !pred.value.trim()) pred.value=latestExtractedLines().join('\n');
}
function clearMetricInputs(){['metricTP','metricFP','metricFN','metricRefs','metricPreds','metricConfidences','metricCorrectness'].forEach(id=>{if($(id))$(id).value='';});if($('metricOutput'))$('metricOutput').innerHTML='<div class="notice">Enter verified evaluation data, then calculate the selected metric. No default numbers are used.</div>';}
async function calculateClassificationMetrics(){
  const raw=['metricTP','metricFP','metricFN'].map(id=>$(id)?.value.trim()||'');
  if(raw.some(v=>v==='')){$('metricOutput').innerHTML='<div class="dangerbox">Enter TP, FP and FN from a labeled evaluation set. Empty inputs are not treated as zero.</div>';return;}
  const [tp,fp,fn]=raw.map(Number); if([tp,fp,fn].some(v=>!Number.isFinite(v)||v<0)){ $('metricOutput').innerHTML='<div class="dangerbox">TP, FP and FN must be non-negative numbers.</div>';return; }
  const r=await fetch(API+'/api/metrics',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({tp,fp,fn})});const d=await r.json();if(!r.ok||d.status!=='success'){$('metricOutput').innerHTML=`<div class="dangerbox">${esc(d.message||'Metric calculation failed')}</div>`;return}const c=d.classification;$('metricOutput').innerHTML=`<div class="successbox"><b>Precision:</b> ${(c.precision*100).toFixed(2)}% · <b>Recall:</b> ${(c.recall*100).toFixed(2)}% · <b>F1:</b> ${(c.f1*100).toFixed(2)}%</div>`;
}
async function calculateTextMetrics(){
  const refs=$('metricRefs').value.split('\n').map(x=>x.trim()).filter(Boolean),preds=$('metricPreds').value.split('\n').map(x=>x.trim()).filter(Boolean);
  if(!refs.length||!preds.length){$('metricOutput').innerHTML='<div class="dangerbox">Enter verified ground-truth values and the corresponding extracted predictions. No default values are used.</div>';return}
  if(refs.length!==preds.length){$('metricOutput').innerHTML='<div class="dangerbox">Enter the same number of ground-truth and prediction lines.</div>';return}
  const r=await fetch(API+'/api/metrics',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({references:refs,predictions:preds})});const d=await r.json();if(!r.ok||d.status!=='success'){$('metricOutput').innerHTML=`<div class="dangerbox">${esc(d.message||'Metric calculation failed')}</div>`;return}$('metricOutput').innerHTML=`<div class="successbox"><b>Exact Match:</b> ${(d.exact_match*100).toFixed(2)}% · <b>CER:</b> ${(d.cer*100).toFixed(2)}% · <b>WER:</b> ${(d.wer*100).toFixed(2)}%</div>`;
}
async function calculateCalibrationMetrics(){
  const conf=$('metricConfidences').value.split(/[,\n]/).map(x=>x.trim()).filter(Boolean); const corr=$('metricCorrectness').value.split(/[,\n]/).map(x=>x.trim()).filter(Boolean);
  if(!conf.length||!corr.length||conf.length!==corr.length){$('metricOutput').innerHTML='<div class="dangerbox">Enter equal-length confidence values and verified 0/1 correctness labels. No default values are used.</div>';return}
  const r=await fetch(API+'/api/metrics',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({confidences:conf,correctness:corr})}); const d=await r.json();
  if(!r.ok||d.status!=='success'){$('metricOutput').innerHTML=`<div class="dangerbox">${esc(d.message||'Calibration calculation failed')}</div>`;return}
  $('metricOutput').innerHTML=`<div class="successbox"><b>Expected Calibration Error (ECE):</b> ${(d.calibration.ece*100).toFixed(2)}% · <b>Samples:</b> ${d.calibration.samples}<p class="muted" style="margin:6px 0 0">Calculated against the supplied verified correctness labels.</p></div>`;
}
function showMetrics(){go('metrics')}
function checkApi(){fetch(API+'/api/test').then(r=>r.ok&&console.log('DHARANETRA backend connected')).catch(()=>console.log('Start Flask at '+API))}
setTimeout(()=>{$('splash')?.classList.add('hide')},1800);updateDashboard();checkApi();updateNavForRole();if(!authToken)setTimeout(()=>go('home'),1850);

function continueFromRegistration(){saveCitizen();if(!citizen.owner_name||!citizen.survey_number||!citizen.village||!citizen.district){alert('Please enter the required citizen information: Full Name, Survey Number, Village / Mandal and District.');return}go('upload');}

async function loadLRMS(){
  if(!authToken||currentRole!=='officer'){go('officerLogin');return}
  const survey=(($('lrmsSurvey')?.value||'')).trim();
  if(!survey){$('lrmsResult').innerHTML='<div class="dangerbox"><b>Survey number required.</b> Enter a survey number from the uploaded/verified land document or the authorized LRMS record.</div>';return}
  $('lrmsResult').innerHTML='<div class="notice">Searching the LRMS registry and loading the complete ownership/registration history…</div>';
  try{
    const r=await fetch(API+'/api/lrms/search?survey_number='+encodeURIComponent(survey)+'&_='+Date.now(),{headers:{'X-Auth-Token':authToken,'Cache-Control':'no-cache'},cache:'no-store'});
    const d=await r.json(); if(!r.ok||d.status!=='success')throw new Error(d.message||'LRMS lookup failed');
    if(!d.records.length){$('lrmsResult').innerHTML='<div class="dangerbox">No LRMS record found for this survey number. No fallback/default survey is used.</div>';return}
    const records=d.records;
    const current=records.filter(r=>r.status==='CURRENT').sort((a,b)=>String(b.transaction_date||'').localeCompare(String(a.transaction_date||''))).at(0)||records.at(-1);
    const previous=records.filter(r=>r.record_id!==current?.record_id);
    let cards='';
    records.forEach((r,i)=>{
      const isCurrent=r.record_id===current?.record_id;
      cards+=`<div class="lineage-card ${isCurrent?'current':''}">
        <span class="gen">${esc(isCurrent?'CURRENT HOLDER':(r.generation||'PREVIOUS HOLDER'))}</span>
        <h3>${esc(r.owner_name||'Not recorded')}</h3>
        <div class="area">${esc(r.area??'—')} acres</div>
        <p class="muted" style="margin:4px 0"><b>Survey:</b> ${esc(r.survey_number)} · <b>Village:</b> ${esc(r.village||'—')} · <b>Mandal:</b> ${esc(r.mandal||'—')}</p>
        <p class="muted" style="margin:4px 0"><b>Transaction / Registration:</b> ${esc(r.transaction_type||'—')}</p>
        <p class="muted" style="margin:4px 0"><b>Date:</b> ${esc(r.transaction_date||'—')} · <b>Document:</b> ${esc(r.document_number||'—')}</p>
        <span class="tag ${isCurrent?'green':''}">${esc(isCurrent?'CURRENT':'PREVIOUS / HISTORICAL')}</span>
      </div>`;
      if(i<records.length-1)cards+='<div class="lineage-arrow">→</div>';
    });
    $('lrmsResult').innerHTML=`
      <div class="successbox"><b>Complete LRMS history found.</b> Survey <b>${esc(survey)}</b> has <b>${records.length}</b> registered record(s): <b>${previous.length}</b> previous registered holder record(s) and <b>${current?'1 current holder':'no explicit current holder'}</b>.
      </div>
      <div class="stats" style="margin-top:14px">
        <div class="stat"><span>Survey Number</span><b>${esc(survey)}</b></div>
        <div class="stat"><span>Total Registered Records</span><b>${records.length}</b></div>
        <div class="stat"><span>Previous / Historical Holders</span><b>${previous.length}</b></div>
        <div class="stat"><span>Current Holder</span><b>${esc(current?.owner_name||'Not recorded')}</b></div>
      </div>
      <div class="notice" style="margin-top:14px"><b>Registered ownership / transaction timeline:</b> Each card below is an explicit LRMS registration or transfer record for this survey. A father, mother, grandfather or other ancestor is <b>not</b> automatically treated as a previous land owner. Only an explicit registered record appears in this timeline.</div>
      <div class="lineage" style="margin-top:16px">${cards}</div>
      ${previous.length===0 ? '<div class="notice" style="margin-top:14px"><b>No previous registered holder record is available for this survey.</b> Family relationships shown on a land document are not treated as ownership history unless the LRMS contains a corresponding registration/transfer record.</div>' : ''}`;
  }catch(e){$('lrmsResult').innerHTML=`<div class="dangerbox">${esc(e.message)}</div>`}
}
async function loadAudit(){
  if(!authToken||currentRole!=='officer'){go('officerLogin');return}
  const body=$('auditBody');
  if(!body)return;
  body.innerHTML='<tr><td colspan="5">Refreshing audit trail…</td></tr>';
  try{
    const r=await fetch(API+'/api/audit?limit=80&_='+Date.now(),{headers:{'X-Auth-Token':authToken,'Cache-Control':'no-cache'},cache:'no-store'});
    const d=await r.json();
    if(!r.ok||d.status!=='success')throw new Error(d.message||'Audit lookup failed');
    body.innerHTML=d.events.length?d.events.map(e=>`<tr><td>${new Date(e.event_time*1000).toLocaleString()}</td><td>${esc(e.actor)}</td><td><span class="tag">${esc(e.action)}</span></td><td>${esc(e.record_id||'—')}</td><td>${esc(e.details||'')}</td></tr>`).join(''):'<tr><td colspan="5">No audit events yet.</td></tr>';
    const stamp=$('auditRefreshStatus'); if(stamp)stamp.textContent='Last refreshed: '+new Date().toLocaleTimeString();
  }catch(e){body.innerHTML=`<tr><td colspan="5">${esc(e.message)}</td></tr>`}
}
let gisMap=null; let gisMarker=null; let gisStreet=null; let gisSatellite=null;
function initRealMap(){
  if(!window.L||!$('realMap'))return false;
  if(gisMap){setTimeout(()=>gisMap.invalidateSize(),50);return true;}
  gisMap=L.map('realMap',{zoomControl:true,attributionControl:true});
  // Use ArcGIS basemap tiles for the browser prototype. This avoids the OpenStreetMap
  // volunteer tile server's blocking policy when the app is opened from file://.
  gisStreet=L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Street_Map/MapServer/tile/{z}/{y}/{x}',{maxZoom:19,attribution:'&copy; Esri, HERE, Garmin, FAO, NOAA, USGS'});
  gisSatellite=L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',{maxZoom:19,attribution:'Tiles &copy; Esri'});
  gisStreet.addTo(gisMap);
  L.control.layers({'Street map':gisStreet,'Satellite imagery':gisSatellite},null,{collapsed:false}).addTo(gisMap);
  return true;
}
async function loadGIS(){
  if(!authToken||currentRole!=='officer'){go('officerLogin');return}
  const survey=(($('gisSurvey')?.value||'')).trim();
  if(!survey){$('gisInfo').innerHTML='<div class="notice"><b>Enter a survey number.</b> No survey number or location is pre-filled.</div>';return}
  $('gisInfo').innerHTML='<div class="notice">Loading the LRMS-linked coordinates and real map…</div>';
  try{
    const r=await fetch(API+'/api/gis/parcel?survey_number='+encodeURIComponent(survey)+'&_='+Date.now(),{headers:{'X-Auth-Token':authToken,'Cache-Control':'no-cache'},cache:'no-store'});const d=await r.json();
    if(!r.ok||d.status!=='success')throw new Error(d.message||'GIS lookup failed');
    if(!d.found||!d.parcel){$('gisInfo').innerHTML='<div class="dangerbox"><b>No GIS-linked location found.</b> The entered survey number is not present in the authorized/local LRMS prototype registry. No default location is used.</div>';return}
    const lat=Number(d.parcel.latitude),lon=Number(d.parcel.longitude);if(!Number.isFinite(lat)||!Number.isFinite(lon))throw new Error('The matched LRMS record has no geographic coordinates.');
    if(!initRealMap())throw new Error('The real-map library could not be loaded. Check your internet connection and reload the page.');
    if(gisMarker)gisMarker.remove();
    gisMarker=L.marker([lat,lon]).addTo(gisMap).bindPopup(`<b>Survey ${esc(survey)}</b><br>${esc(d.parcel.name)}<br>LRMS-linked coordinate`).openPopup();
    requestAnimationFrame(()=>{gisMap.invalidateSize();gisMap.setView([lat,lon],16);});
    $('gisInfo').innerHTML=`<div class="successbox"><b>Real GIS map loaded.</b> The map is centered on the coordinates linked to Survey ${esc(survey)} in the LRMS prototype. Use the layer control to switch between street and satellite imagery. No default survey or location is used.</div>`;
    $('gisMeta').innerHTML=`<div><span>Survey</span><strong>${esc(survey)}</strong></div><div><span>LRMS Area</span><strong>${esc(d.parcel.area??'—')} acres</strong></div><div><span>Coordinates</span><strong>${lat.toFixed(6)}, ${lon.toFixed(6)}</strong></div>`;
    $('gisOpenLink')?.remove();
    const a=document.createElement('a');a.id='gisOpenLink';a.className='btn';a.target='_blank';a.rel='noopener';a.href=`https://www.openstreetmap.org/?mlat=${lat}&mlon=${lon}#map=17/${lat}/${lon}`;a.textContent='Open this location in OpenStreetMap ↗';$('gisActions')?.appendChild(a);
  }catch(e){$('gisInfo').innerHTML=`<div class="dangerbox">${esc(e.message)}</div>`}
}
async function runDuplicateCheck(){
  if(!authToken||currentRole!=='officer'){go('officerLogin');return}
  const f=$('duplicateFile')?.files[0]; if(!f){alert('Choose a document first.');return}
  const fd=new FormData();fd.append('document',f); const box=$('duplicateResult');box.classList.remove('hidden');box.innerHTML='<div class="notice"><b>Checking document…</b><p class="muted">Computing SHA-256 and comparing extracted land-record fields with the registered document set.</p></div>';
  try{
    const r=await fetch(API+'/api/duplicate-check',{method:'POST',headers:{'X-Auth-Token':authToken},body:fd});const d=await r.json();if(!r.ok||d.status!=='success')throw new Error(d.message||'Duplicate check failed');
    let html='';
    if(d.registry.exact_duplicate){
      const e=d.registry.existing||{};
      html=`<div class="dangerbox"><b>EXACT DUPLICATE FILE FOUND.</b><p style="margin:7px 0 0">This uploaded file has the same SHA-256 hash as a document already registered. The system does <b>not</b> create another registry entry.</p><p style="margin:7px 0 0"><b>Existing file:</b> ${esc(e.filename||'—')} · <b>Record:</b> ${esc(e.record_id||'Not linked')} · <b>Registered:</b> ${e.uploaded_at?new Date(e.uploaded_at*1000).toLocaleString():'—'}</p></div>`;
    }else{
      html='<div class="successbox"><b>NO EXACT FILE DUPLICATE.</b><p style="margin:7px 0 0">This file hash is new to the document registry.</p></div>';
    }
    const flds=d.fields||{};const extracted=Object.entries(flds).filter(([k,v])=>v).map(([k,v])=>`<span class="status verified" style="margin:3px">${esc(labels[k]||k)}: ${esc(v)}</span>`).join('');
    html+=`<div class="card" style="margin-top:14px"><h3>Extracted fields used for duplicate comparison</h3><div>${extracted||'<span class="muted">No structured fields were extracted from this document. Similar-record comparison will therefore be limited.</span>'}</div></div>`;
    if(d.candidates?.length){html+=`<div class="card" style="margin-top:14px"><h3>Potential duplicate / similar records</h3><div class="table-wrap"><table class="table"><thead><tr><th>Similarity</th><th>Matched Fields</th><th>Filename</th><th>Record ID</th><th>Decision Signal</th></tr></thead><tbody>${d.candidates.map(c=>`<tr><td><b>${esc(c.similarity)}%</b></td><td>${esc((c.matched_fields||[]).join(', ')||'—')}</td><td>${esc(c.filename)}</td><td>${esc(c.record_id||'—')}</td><td><span class="status review">${esc(c.duplicate_type)}</span></td></tr>`).join('')}</tbody></table></div><div class="notice" style="margin-top:12px">Similarity is a review signal. An authorized officer must verify whether two records are actually duplicates.</div></div>`}else html+='<div class="notice" style="margin-top:14px"><b>No strong field-level duplicate candidate found.</b> The system checked the registered structured-field set available to this prototype.</div>';
    box.innerHTML=html;
  }catch(e){box.innerHTML=`<div class="dangerbox">${esc(e.message)}</div>`}
}

window.addEventListener('resize',()=>{if(gisMap)setTimeout(()=>gisMap.invalidateSize(),100);});
