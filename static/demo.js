import {createStage} from './avatar.js?v=20261005-beat2';
import {Speech} from './speech.js?v=20261005-beat2';
import {MotionSequence} from './gesture-library.js?v=20261005-beat2';
import {prepareApplicationMotion,gestureSummary} from './application-gesture.js?v=20261005-beat2';
const $=id=>document.getElementById(id);let stage=createStage($('stage')),speech=new Speech(stage);
const variant=document.documentElement.dataset.variant||'journal';let timeline=null,actors={},now=0,playing=false,last=0,spoken=new Set(),captures=[],format='txt',sceneGeneration=0,playbackGeneration=0,motionTrace=[],motionByEvent=new Map(),played=new Map();
// Co-speech retrieval per variant: journal = GestureCLR wild-pose matching; ISMAR = automatic rule map;
// Live = wild-pose matching with multilingual support (source language passed per line).
const GESTURE_MODE={journal:'wild',ismar:'automatic',live:'multilingual'}[variant]||'wild';
const EMOTIONS=['neutral','anger','disgust','fear','joy','sadness','surprise'];
const TTS_LANG={en:'en-US',ko:'ko-KR',ja:'ja-JP',zh:'zh-CN',es:'es-ES',fr:'fr-FR',de:'de-DE'};
$('heading').textContent={journal:'ASAP: screenplay to storyboard and 3D previsualization',ismar:'ASAP: scene playback and storyboard capture',live:'ASAP: live screenplay playback'}[variant];
if(variant!=='journal')$('camera-controls').hidden=true;
function coord(v,center,scale=140){return (Number(v)-center)/scale;}
function clipsOf(data){return (data?.slots||[]).map(slot=>({id:slot.gesture_id||slot.id,matched_text:slot.text,route:slot.route,confidence:slot.confidence}));}
function routeOf(data){return data?.trace?.route||data?.trace?.routes||data?.route||null;}
async function prepareMotion(text,actor,language){
 if(GESTURE_MODE!=='multilingual')return prepareApplicationMotion(stage,text,{actor,mode:GESTURE_MODE});
 const response=await fetch('/api/beat-query',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({text,mode:GESTURE_MODE,source_language:language||'en'})});
 const data=await response.json().catch(()=>null);
 if(data?.ready&&Array.isArray(data.slots)&&!data.slots.length)throw new Error('No local recorded gesture matched this utterance; speech will play without co-speech motion.');
 if(!response.ok||!data?.ready||!Array.isArray(data.slots))throw new Error(data?.error||data?.reason||'Prepare the local BEAT gesture library to enable recorded co-speech motion.');
 return {motion:new MotionSequence(stage,{actor}).load(data,text),data};
}
function label(e){const p=e.payload;if(e.kind==='emotion')return `${p.emotion} ${p.level}${p.method==='manual'?' (manual)':''}`;if(e.kind==='narration')return `no action (${p.rejected}): ${p.text}`;if(e.kind==='move')return `→ ${p.target}`;if(e.kind==='action')return `${p.combination}${p.target?' @ '+p.target:''}`;return p.text||p.heading||'';}
function build(data){sceneGeneration++;playbackGeneration++;timeline=data;now=0;playing=false;spoken.clear();speech.cancel();captures=[];motionTrace=[];motionByEvent=new Map();played=new Map();$('storyboard').replaceChildren();
 stage.dispose();stage=createStage($('stage'));speech=new Speech(stage);actors={};stage.avatar.root.visible=false;
 for(const [name,c] of Object.entries(data.characters)){actors[name]=stage.makeAvatar(c.color||'#60c8d9',coord(c.x,480),coord(c.y,350));}
 for(const [name,p] of Object.entries(data.props))stage.addProp(name,coord(p.x,480),coord(p.y,350),p.color||undefined,Array.isArray(p.size)?p.size:undefined);
 $('scrub').max=data.duration;$('events').replaceChildren();for(const e of data.events){const li=document.createElement('li');li.textContent=`${e.start.toFixed(1)}s · ${e.actor||'SCENE'} · ${e.kind} · ${label(e)}`;$('events').append(li);}
 renderOverrides(data);updateTrace();for(const id of ['play','restart','capture','export','export-board'])$(id).disabled=false;
 draw();
 const generation=sceneGeneration;
 Promise.all(data.events.filter(e=>e.kind==='speech'&&actors[e.actor]).map(async e=>{
  const actor=actors[e.actor],promise=prepareMotion(e.payload.text,actor,e.payload.language);
  motionByEvent.set(e.id,promise);
  try{const selected=await promise;if(generation!==sceneGeneration)return;
   motionByEvent.set(e.id,selected);
   motionTrace.push({event_id:e.id,actor:e.actor,text:e.payload.text,language:e.payload.language,route:routeOf(selected.data),trace:selected.data.trace,clips:clipsOf(selected.data)});
   updateTrace();if(!playing)draw();
  }catch(error){if(generation===sceneGeneration){motionByEvent.delete(e.id);$('status').textContent=`Recorded co-speech unavailable: ${error.message}`;}}
 }));
 if(variant==='live'){playing=true;$('status').textContent+=' Live playback started.';}
}
// The exported schedule records the BEAT clips that actually played, per speech event.
function markPlayed(e,selected){if(!selected?.data||played.has(e.id))return;played.set(e.id,{event_id:e.id,actor:e.actor,start:e.start,mode:GESTURE_MODE,route:routeOf(selected.data),clips:clipsOf(selected.data)});updateTrace();}
function exportTimeline(){if(!timeline)return null;
 const events=timeline.events.map(e=>{if(e.kind!=='speech')return e;const p=played.get(e.id);return {...e,payload:{...e.payload,gesture:p?{played:true,mode:GESTURE_MODE,route:p.route,clips:p.clips}:null}};});
 return {...timeline,events,gesture_mode:GESTURE_MODE,played_gestures:[...played.values()]};}
function updateTrace(){$('trace').textContent=JSON.stringify({paragraphs:timeline?.paragraphs,resolved_events:exportTimeline()?.events,selected_gesture_sequences:motionTrace},null,2);}
function renderOverrides(data){const box=$('overrides');if(!box)return;box.replaceChildren();let library={};try{library=JSON.parse($('library').value);}catch{}
 const current=library.emotion_overrides||{};
 data.paragraphs.forEach((p,i)=>{if(!['parenthetical','dialogue','action'].includes(p.kind))return;
  const row=document.createElement('div');row.className='override-row';const text=document.createElement('span');text.textContent=`#${i} ${p.speaker?p.speaker+' ':''}${p.kind}: ${p.text.slice(0,60)}`;
  const emotion=document.createElement('select'),level=document.createElement('select');emotion.setAttribute('aria-label',`Facial expression for paragraph ${i}`);level.setAttribute('aria-label',`Expression level for paragraph ${i}`);
  emotion.append(new Option(p.emotion?`Script tag (${p.emotion.emotion} ${p.emotion.level})`:'Automatic','auto'));for(const name of EMOTIONS)emotion.append(new Option(name,name));['weak','medium','strong'].forEach((n,k)=>level.append(new Option(n,String(k+1))));
  const chosen=current[i]||current[String(i)];
  if(chosen){emotion.value=chosen.emotion;level.value=String(chosen.level||2);}else{emotion.value='auto';level.value='2';level.disabled=true;}
  const apply=()=>{let lib;try{lib=JSON.parse($('library').value);}catch{$('status').textContent='Fix the catalog JSON before overriding expressions.';return;}
   const overrides=lib.emotion_overrides||{};if(emotion.value==='auto')delete overrides[i];else overrides[i]={emotion:emotion.value,level:Number(level.value)};
   if(Object.keys(overrides).length)lib.emotion_overrides=overrides;else delete lib.emotion_overrides;$('library').value=JSON.stringify(lib,null,2);compile();};
  emotion.onchange=apply;level.onchange=apply;row.append(text,emotion,level);box.append(row);});}
async function speakEvent(utterance,actor){
 const generation=sceneGeneration,playback=playbackGeneration,text=utterance.payload.text,language=utterance.payload.language||'en';let selected=null;
 try{selected=await motionByEvent.get(utterance.id);}
 catch(error){$('status').textContent=`Recorded co-speech unavailable: ${error.message}`;}
 if(generation!==sceneGeneration||playback!==playbackGeneration||!playing)return;
 if(selected)$('status').textContent=gestureSummary(selected.data);
 speech.speak(text,{backend:$('speech-backend').value,actor,language:TTS_LANG[language.slice(0,2)]||language,
  onStart:()=>{markPlayed(utterance,selected);selected?.motion.onStart();},onProgress:clock=>selected?.motion.onProgress(clock),
  onEnd:()=>{selected?.motion.onEnd();stage.clearMotion(actor);}
 }).catch(error=>$('status').textContent=error.message);
}
function face(a,x,z){const dx=x-a.root.position.x,dz=z-a.root.position.z;if(Math.hypot(dx,dz)>.05)a.root.rotation.y=Math.atan2(dx,dz);}
// Position, facing and seating replayed from the compiled move/action events.
function actorState(name){const c=timeline.characters[name];let pos=[c.x,c.y],toward=null,walking=false,seat=null;
 for(const e of timeline.events){if(e.actor!==name||e.start>now)continue;
  if(e.kind==='move'){const k=Math.min(1,(now-e.start)/Math.max(.001,e.duration)),from=e.payload.from||pos,to=e.payload.anchor;pos=[from[0]+(to[0]-from[0])*k,from[1]+(to[1]-from[1])*k];walking=k<1;toward=walking?to:e.payload.face;seat=null;}
  else if(e.kind==='action'){toward=e.payload.face||toward;seat=e.payload.verb==='sit'?{height:e.payload.seat_height??.45}:null;if(seat)toward=null;}
 }
 return {pos,toward,walking,seat};}
function gazePoint(name,utterance){const target=utterance.payload.gaze;
 if(target&&target!=='group'&&actors[target]){const p=actors[target].root.position;return [p.x,1.5,p.z];}
 const others=Object.entries(actors).filter(([n])=>n!==name).map(([,a])=>a.root.position);
 if(others.length)return [others.reduce((s,p)=>s+p.x,0)/others.length,1.5,others.reduce((s,p)=>s+p.z,0)/others.length];
 const g=utterance.payload.gaze_point;return g?[coord(g[0],480),1.5,coord(g[1],350)]:null;}
function draw(){if(!timeline)return;const active=timeline.events.filter(e=>e.start<=now&&now<e.start+e.duration);let caption='';
 const states=Object.fromEntries(Object.keys(actors).map(name=>[name,actorState(name)]));
 for(const [name,a] of Object.entries(actors)){const s=states[name];a.root.position.x=coord(s.pos[0],480);a.root.position.z=coord(s.pos[1],350);}
 for(const [name,a] of Object.entries(actors)){const s=states[name];
  a.root.rotation.y=0;if(s.toward)face(a,coord(s.toward[0],480),coord(s.toward[1],350));
  const previous=timeline.events.filter(e=>e.actor===name&&e.kind==='emotion'&&e.start<=now).at(-1),emotion=previous?.payload.emotion||'neutral',level=previous?.payload.level||1;
  if(typeof stage.setExpression==='function')stage.setExpression(emotion,level,a);else stage.expression(emotion,level/3,a);
  const action=active.find(e=>e.actor===name&&e.kind==='action'&&e.payload.verb!=='sit');
  stage.gesture(s.walking?'walk':s.seat?'sit':(action?.payload.motion||'idle'),a,now);
  if(typeof stage.sit==='function')stage.sit(s.seat&&!s.walking?s.seat.height:null,a);
  const reach=action?.payload.interaction,point=reach?[coord(reach[0],480),Number(reach[2]??1),coord(reach[1],350)]:null;
  if(typeof stage.reachTo==='function')stage.reachTo(point,a);else if(point)stage.pointAt(point,a);
  const utterance=active.find(e=>e.actor===name&&e.kind==='speech');
  const look=utterance?gazePoint(name,utterance):null;
  if(typeof stage.lookAt==='function')stage.lookAt(look,a);else if(look&&!s.walking&&!s.seat&&!action)face(a,look[0],look[2]);
  if(utterance){caption=`${name}: ${utterance.payload.text}`;
   const selected=motionByEvent.get(utterance.id);
   if(selected?.motion&&(!playing||!a.speaking)){
    const elapsed=Math.max(0,now-utterance.start),duration=Math.max(.001,utterance.duration);
    selected.motion.draw(Math.min(.999,elapsed/duration),{elapsed,duration});markPlayed(utterance,selected);
   }
   if(playing&&$('voice').checked&&!spoken.has(utterance.id)){spoken.add(utterance.id);speakEvent(utterance,a);}
  }else if(a.motionActive&&!a.speaking)stage.clearMotion(a);
 }
 const narration=active.find(e=>e.kind==='narration');
 $('caption').textContent=caption||(narration?narration.payload.text:'')||active.find(e=>e.kind==='scene')?.payload.heading||'Scene continues…';$('clock').textContent=now.toFixed(1)+' s';$('scrub').value=now;
 [...$('events').children].forEach((li,i)=>li.classList.toggle('active',active.includes(timeline.events[i])));$('play').textContent=playing?'Pause':'Play';
}
function tick(t){if(playing&&timeline){now=Math.min(timeline.duration,now+(last?(t-last)/1000:0));if(now>=timeline.duration){playing=false;playbackGeneration++;speech.cancel();}}last=t;draw();requestAnimationFrame(tick);}requestAnimationFrame(tick);
async function compile(){playing=false;speech.cancel();try{const library=JSON.parse($('library').value),resolver=library.resolver||{};if($('resolver').value==='semantic')library.resolver={...resolver,backend:'sentence-transformer',emotion_model:$('emotion-model').value,action_model:$('action-model').value};else library.resolver={...resolver,backend:'tfidf'};const r=await fetch('/api/compile',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({script:$('script').value,format,library})});const data=await r.json();if(!r.ok)throw new Error(data.error);$('status').textContent=`Compiled ${data.events.length} events, ${data.duration.toFixed(1)} seconds.`;build(data);}catch(e){$('status').textContent=e.message;}}
$('compile').onclick=compile;
$('resolver').onchange=()=>$('model-options').hidden=$('resolver').value!=='semantic';
$('script-file').onchange=async e=>{const file=e.target.files[0];if(file){$('script').value=await file.text();format=file.name.endsWith('.fdx')?'fdx':'txt';}};
$('play').onclick=()=>{if(now>=timeline.duration){now=0;spoken.clear();}playing=!playing;if(!playing){playbackGeneration++;speech.cancel();}};$('restart').onclick=()=>{now=0;spoken.clear();playbackGeneration++;speech.cancel();playing=true;};$('scrub').oninput=()=>{now=Number($('scrub').value);playing=false;playbackGeneration++;speech.cancel();};
function download(name,body,type='application/json'){const url=URL.createObjectURL(new Blob([body],{type})),a=Object.assign(document.createElement('a'),{href:url,download:name});a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}
$('export').onclick=()=>download('asap-timeline.json',JSON.stringify(exportTimeline(),null,2));
$('capture').onclick=()=>{const image=stage.capture();captures.push({time:now,caption:$('caption').textContent,image});const card=document.createElement('article'),img=new Image(),p=document.createElement('p');img.src=image;img.alt=`Scene at ${now.toFixed(1)} seconds`;p.textContent=`${now.toFixed(1)} s — ${$('caption').textContent}`;card.append(img,p);$('storyboard').append(card);};
$('export-board').onclick=()=>{const escape=s=>s.replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));download('asap-storyboard.html','<!doctype html><meta charset="utf-8"><title>ASAP captured storyboard</title><style>body{font:16px system-ui}img{width:420px;max-width:100%}article{display:inline-block;padding:15px;vertical-align:top}</style>'+captures.map(c=>`<article><img src="${c.image}" alt="Captured scene"><p>${c.time.toFixed(1)} s · ${escape(c.caption)}</p></article>`).join(''),'text/html');};
$('camera-angle').oninput=()=>{const angle=Number($('camera-angle').value)/100;stage.camera.position.set(6*Math.sin(angle),1.8,6*Math.cos(angle));stage.camera.lookAt(0,1,0);};
async function loadExample(name=''){const r=await fetch('/api/example'+(name?`?name=${encodeURIComponent(name)}`:''));const example=await r.json();if(!r.ok)throw new Error(example.error);$('script').value=example.script;$('library').value=JSON.stringify(example.library,null,2);format='txt';await compile();}
if($('example'))$('example').onchange=()=>loadExample($('example').value).catch(e=>$('status').textContent=e.message);
loadExample($('example')?.value||'').catch(e=>$('status').textContent=e.message);
window.addEventListener('pagehide',()=>{speech.cancel();stage.dispose();});
