import {createStage} from './avatar.js?v=20261005-gesture7';
import {Speech} from './speech.js?v=20261005-gesture7';
const $=id=>document.getElementById(id);let stage=createStage($('stage')),speech=new Speech(stage);
const variant=document.documentElement.dataset.variant||'journal';let timeline=null,actors={},now=0,playing=false,last=0,spoken=new Set(),captures=[],format='txt';
$('heading').textContent={journal:'ASAP: screenplay to storyboard and 3D previsualization',ismar:'ASAP: scene playback and storyboard capture',live:'ASAP: live screenplay playback'}[variant];
if(variant!=='journal')$('camera-controls').hidden=true;
function coord(v,center,scale=140){return (Number(v)-center)/scale;}
function build(data){timeline=data;now=0;playing=false;spoken.clear();speech.cancel();captures=[];$('storyboard').replaceChildren();
 stage.dispose();stage=createStage($('stage'));speech=new Speech(stage);actors={};stage.avatar.root.visible=false;
 for(const [name,c] of Object.entries(data.characters)){actors[name]=stage.makeAvatar(c.color||'#60c8d9',coord(c.x,480),coord(c.y,350));}
 for(const [name,p] of Object.entries(data.props))stage.addProp(name,coord(p.x,480),coord(p.y,350));
 $('scrub').max=data.duration;$('events').replaceChildren();for(const e of data.events){const li=document.createElement('li');li.textContent=`${e.start.toFixed(1)}s · ${e.actor||'SCENE'} · ${e.kind} · ${e.payload.motion||e.payload.emotion||e.payload.text||e.payload.heading||e.payload.target||''}`;$('events').append(li);}
 $('trace').textContent=JSON.stringify({paragraphs:data.paragraphs,resolved_events:data.events},null,2);for(const id of ['play','restart','capture','export','export-board'])$(id).disabled=false;
 draw();
}
function draw(){if(!timeline)return;const active=timeline.events.filter(e=>e.start<=now&&now<e.start+e.duration);let caption='';
 for(const [name,a] of Object.entries(actors)){
  const initial=timeline.characters[name];a.root.position.x=coord(initial.x,480);a.root.position.z=coord(initial.y,350);
  for(const e of timeline.events.filter(e=>e.actor===name&&e.kind==='move'&&e.start<=now)){
   const k=Math.min(1,(now-e.start)/e.duration),target=e.payload.anchor;
   const from=a.root.position.clone();a.root.position.x=from.x+(coord(target[0],480)-1.2-from.x)*k;a.root.position.z=from.z+(coord(target[1],350)-from.z)*k;
  }
  const previous=timeline.events.filter(e=>e.actor===name&&e.kind==='emotion'&&e.start<=now).at(-1);stage.expression(previous?.payload.emotion||'neutral',previous?.payload.intensity||.5,a);
  const g=active.find(e=>e.actor===name&&(e.kind==='gesture'||e.kind==='action'));const moving=active.some(e=>e.actor===name&&e.kind==='move');stage.gesture(g?.payload.motion||g?.payload.verb||(moving?'walk':'idle'),a,now);
  const utterance=active.find(e=>e.actor===name&&e.kind==='speech');
  if(utterance){caption=`${name}: ${utterance.payload.text}`;if(playing&&$('voice').checked&&!spoken.has(utterance.id)){spoken.add(utterance.id);speech.speak(utterance.payload.text,{backend:$('speech-backend').value,actor:a}).catch(e=>$('status').textContent=e.message);}}
 }
 $('caption').textContent=caption||active.find(e=>e.kind==='scene')?.payload.heading||'Scene continues…';$('clock').textContent=now.toFixed(1)+' s';$('scrub').value=now;
 [...$('events').children].forEach((li,i)=>li.classList.toggle('active',active.includes(timeline.events[i])));$('play').textContent=playing?'Pause':'Play';
}
function tick(t){if(playing&&timeline){now=Math.min(timeline.duration,now+(last?(t-last)/1000:0));if(now>=timeline.duration){playing=false;speech.cancel();}}last=t;draw();requestAnimationFrame(tick);}requestAnimationFrame(tick);
$('compile').onclick=async()=>{playing=false;speech.cancel();try{const library=JSON.parse($('library').value);if($('resolver').value==='semantic')library.resolver={backend:'sentence-transformer',model:$('gesture-model').value,action_model:$('action-model').value};else library.resolver={backend:'tfidf'};const r=await fetch('/api/compile',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({script:$('script').value,format,library})});const data=await r.json();if(!r.ok)throw new Error(data.error);build(data);$('status').textContent=`Compiled ${data.events.length} events, ${data.duration.toFixed(1)} seconds.`;}catch(e){$('status').textContent=e.message;}};
$('resolver').onchange=()=>$('model-options').hidden=$('resolver').value!=='semantic';
$('script-file').onchange=async e=>{const file=e.target.files[0];if(file){$('script').value=await file.text();format=file.name.endsWith('.fdx')?'fdx':'txt';}};
$('play').onclick=()=>{if(now>=timeline.duration){now=0;spoken.clear();}playing=!playing;if(!playing)speech.cancel();};$('restart').onclick=()=>{now=0;spoken.clear();speech.cancel();playing=true;};$('scrub').oninput=()=>{now=Number($('scrub').value);playing=false;speech.cancel();};
function download(name,body,type='application/json'){const url=URL.createObjectURL(new Blob([body],{type})),a=Object.assign(document.createElement('a'),{href:url,download:name});a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}
$('export').onclick=()=>download('asap-timeline.json',JSON.stringify(timeline,null,2));
$('capture').onclick=()=>{const image=stage.capture();captures.push({time:now,caption:$('caption').textContent,image});const card=document.createElement('article'),img=new Image(),p=document.createElement('p');img.src=image;img.alt=`Scene at ${now.toFixed(1)} seconds`;p.textContent=`${now.toFixed(1)} s — ${$('caption').textContent}`;card.append(img,p);$('storyboard').append(card);};
$('export-board').onclick=()=>{const escape=s=>s.replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));download('asap-storyboard.html','<!doctype html><meta charset="utf-8"><title>ASAP captured storyboard</title><style>body{font:16px system-ui}img{width:420px;max-width:100%}article{display:inline-block;padding:15px;vertical-align:top}</style>'+captures.map(c=>`<article><img src="${c.image}" alt="Captured scene"><p>${c.time.toFixed(1)} s · ${escape(c.caption)}</p></article>`).join(''),'text/html');};
$('camera-angle').oninput=()=>{const angle=Number($('camera-angle').value)/100;stage.camera.position.set(6*Math.sin(angle),1.8,6*Math.cos(angle));stage.camera.lookAt(0,1,0);};
fetch('/api/example').then(r=>r.json()).then(example=>{$('script').value=example.script;$('library').value=JSON.stringify(example.library,null,2);$('compile').click();}).catch(e=>$('status').textContent=e.message);
window.addEventListener('pagehide',()=>{speech.cancel();stage.dispose();});
