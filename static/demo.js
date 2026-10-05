import * as THREE from './vendor/three.module.js';
import {createStage} from './avatar.js?v=20261006-paper1';
import {Speech} from './speech.js?v=20261006-paper1';
import {MotionSequence} from './gesture-library.js?v=20261006-paper1';
import {prepareApplicationMotion,gestureSummary} from './application-gesture.js?v=20261006-paper1';
const $=id=>document.getElementById(id);let audioBus=null,stage=createStage($('stage')),speech=newSpeech();
const variant=document.documentElement.dataset.variant||'journal';let timeline=null,actors={},props3d={},room=null,now=0,playing=false,last=0,spoken=new Set(),captures=[],format='txt',sceneGeneration=0,playbackGeneration=0,motionTrace=[],motionByEvent=new Map(),played=new Map();
let cameraTrack=[],cameraMode='auto',recorder=null,recordedBlob=null,xrSession=null;
// Co-speech retrieval per variant: journal = GestureCLR wild-pose matching; ISMAR = automatic rule map;
// Live = wild-pose matching with multilingual support (source language passed per line).
const GESTURE_MODE={journal:'wild',ismar:'automatic',live:'multilingual'}[variant]||'wild';
const EMOTIONS=['neutral','anger','disgust','fear','joy','sadness','surprise'];
const TTS_LANG={en:'en-US',ko:'ko-KR',ja:'ja-JP',zh:'zh-CN',es:'es-ES',fr:'fr-FR',de:'de-DE'};
$('heading').textContent={journal:'ASAP: screenplay to storyboard and 3D previsualization',ismar:'ASAP: scene playback and storyboard capture',live:'ASAP: live screenplay playback'}[variant];
// Camera presets, video recording and the VR view are journal outputs; the earlier variants offer them as demo extras.
$('outputs-note').textContent=variant==='journal'?'Multi-camera shots, WebM recording and the immersive VR view are the journal paper\'s previsualization outputs, rebuilt for the browser.':`Multi-camera shots, WebM recording and the VR view come from the later ASAP journal paper; the ${variant==='ismar'?'ISMAR':'Real-Time Live!'} paper does not describe them, so they are web-demo extras here.`;
function newSpeech(){const s=new Speech(stage);if(audioBus)s.context=audioBus.context;return s;}
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
function label(e){const p=e.payload;if(e.kind==='emotion')return `${p.emotion} ${p.level}${p.method==='manual'?' (manual)':''}`;if(e.kind==='narration')return `no action (${p.rejected}): ${p.text}`;if(e.kind==='move')return `→ ${p.target} (${p.path?p.path.length-2+' turns, ':''}${p.distance_m} m)`;if(e.kind==='action')return `${p.combination}${p.target?' @ '+p.target:''}${p.effect?' → '+p.effect.state:''}`;return p.text||p.heading||'';}

// ---------------------------------------------------------------------------
// Basic procedural room (authored here, CC0) sized to the stage, and props whose
// on/off or open/closed state is driven by the action events' effect field.
const ON_STATES=new Set(['on','open','opened','lit','active']);
const stateLevel=s=>ON_STATES.has(String(s??'').toLowerCase())?1:0;
const PROP_KINDS=[['lamp',/lamp|light/],['window',/window|curtain/],['door',/door|gate/],['fireplace',/fireplace|hearth|fire/],['tv',/^tv$|television|screen|monitor/],['seat',/sofa|couch|chair|bench|seat|stool/]];
const TRANSITION={lamp:.25,tv:.4,fireplace:.8,window:1.1,door:1,seat:.3,box:.3};
function propKind(name,p){const c=String(p.class||name.replace(/[_\-\s]*\d+$/,'')).toLowerCase();return PROP_KINDS.find(([,re])=>re.test(c))?.[0]||(p.seat_height!=null?'seat':'box');}
const material=(color,extra={})=>new THREE.MeshStandardMaterial({color,roughness:.8,...extra});
function box(group,size,pos,mat){const m=new THREE.Mesh(new THREE.BoxGeometry(...size),mat);m.position.set(...pos);group.add(m);return m;}
function buildRoom(data){
 const width=(data.stage?.width||960)/140,depth=(data.stage?.height||540)/140,height=2.8,x0=coord(0,480),z0=coord(0,350),group=new THREE.Group();group.name='asap-room';
 const wall=material('#3a3346',{roughness:.95}),floor=material('#4a3a2f',{roughness:.9});
 const back=new THREE.Mesh(new THREE.PlaneGeometry(width,height),wall);back.position.set(x0+width/2,height/2,z0);group.add(back);
 for(const side of [0,1]){const w=new THREE.Mesh(new THREE.PlaneGeometry(depth,height),wall);w.rotation.y=side?-Math.PI/2:Math.PI/2;w.position.set(x0+side*width,height/2,z0+depth/2);group.add(w);}
 const boards=new THREE.Mesh(new THREE.PlaneGeometry(width,depth),floor);boards.rotation.x=-Math.PI/2;boards.position.set(x0+width/2,.003,z0+depth/2);group.add(boards);
 box(group,[width,.12,.03],[x0+width/2,.06,z0+.015],material('#2a2433'));
 stage.scene.add(group);return group;
}
function buildProp(name,p){
 const kind=propKind(name,p),[w,h,d]=Array.isArray(p.size)?p.size.map(Number):[.55,.65,.55],color=p.color||'#e0b572',group=new THREE.Group();
 group.position.set(coord(p.x,480),0,coord(p.y,350));group.name=`prop:${name}`;let apply=()=>{};
 if(kind==='lamp'){
  box(group,[w*.8,.04,d*.8],[0,.02,0],material('#2c2c30'));
  const pole=new THREE.Mesh(new THREE.CylinderGeometry(.018,.018,h*.8,10),material('#3a3a40'));pole.position.y=h*.4;group.add(pole);
  const shade=new THREE.Mesh(new THREE.CylinderGeometry(w*.32,w*.5,h*.2,20,1,true),material(color,{side:THREE.DoubleSide,emissive:new THREE.Color('#ffc66e')}));shade.position.y=h*.88;group.add(shade);
  const bulb=new THREE.Mesh(new THREE.SphereGeometry(.05,12,8),material('#fff3d6',{emissive:new THREE.Color('#ffdc9a')}));bulb.position.y=h*.84;group.add(bulb);
  const light=new THREE.PointLight('#ffcf8a',0,5,1.2);light.position.y=h*.84;group.add(light);
  const lit=shade.material.color.clone(),dim=lit.clone().multiplyScalar(.35);
  apply=level=>{shade.material.color.copy(dim).lerp(lit,level);shade.material.emissiveIntensity=.04+1.6*level;bulb.material.emissiveIntensity=.05+3*level;light.intensity=9*level;};
 }else if(kind==='window'){
  const sill=Number(p.elevation??.8),frame=material('#d8d2c4');group.position.y=sill;
  for(const [sx,sy,px,py] of [[w,.06,0,0],[w,.06,0,h],[.06,h,-w/2,h/2],[.06,h,w/2,h/2],[.04,h,0,h/2]])box(group,[sx,sy,d],[px,py,0],frame);
  const glass=new THREE.Mesh(new THREE.PlaneGeometry(w,h),material('#0d1a33',{emissive:new THREE.Color('#5d86c9')}));glass.position.set(0,h/2,-d/2+.005);group.add(glass);
  const curtains=[-1,1].map(s=>box(group,[w/2,h*1.05,.04],[s*w/4,h/2,d/2+.04],material(color,{roughness:1})));
  const moon=new THREE.PointLight('#9ab8ff',0,4,1.4);moon.position.set(0,h/2,.6);group.add(moon);
  apply=level=>{curtains.forEach((c,i)=>{const s=i?1:-1,k=1-.78*level;c.scale.x=k;c.position.x=s*(w/2-w/4*k);});glass.material.emissiveIntensity=.15+.85*level;moon.intensity=2.5*level;};
 }else if(kind==='door'){
  const frame=material('#cfc5b4');for(const [sx,sy,px,py] of [[.06,h,-w/2,h/2],[.06,h,w/2,h/2],[w+.06,.06,0,h]])box(group,[sx,sy,d],[px,py,0],frame);
  const hinge=new THREE.Group();hinge.position.set(-w/2,0,0);group.add(hinge);
  box(hinge,[w*.96,h*.98,.05],[w*.48,h*.49,0],material(color));box(hinge,[.04,.04,.08],[w*.86,h*.48,.05],material('#d4b25a',{metalness:.6}));
  apply=level=>{hinge.rotation.y=-1.35*level;};
 }else if(kind==='fireplace'){
  box(group,[w,h,d],[0,h/2,0],material(color||'#7b4a3a'));const mouth=box(group,[w*.6,h*.5,.04],[0,h*.3,d/2+.001],material('#120c0a'));
  const fire=new THREE.Mesh(new THREE.ConeGeometry(w*.16,h*.32,10),material('#ff7a1a',{emissive:new THREE.Color('#ff6a00'),transparent:true}));fire.position.set(0,h*.2,d/2-.02);group.add(fire);
  const light=new THREE.PointLight('#ff8a3d',0,5,1.2);light.position.set(0,h*.35,d/2+.3);group.add(light);mouth.material.emissive=new THREE.Color('#ff5a00');
  apply=(level,t)=>{const flicker=1+.18*Math.sin(t*13)+.1*Math.sin(t*29+1);fire.visible=level>.02;fire.scale.set(level,level*flicker,level);fire.material.emissiveIntensity=2*level;mouth.material.emissiveIntensity=.6*level*flicker;light.intensity=8*level*flicker;};
 }else if(kind==='tv'){
  const cabinetH=h*.42,screenH=Math.min(h-cabinetH-.04,w*.56);
  box(group,[w,cabinetH,d],[0,cabinetH/2,0],material('#3b302b'));box(group,[w*.94,screenH+.05,.06],[0,cabinetH+.02+screenH/2,0],material(color||'#202228'));
  const screen=new THREE.Mesh(new THREE.PlaneGeometry(w*.88,screenH*.92),material('#050608',{emissive:new THREE.Color('#6fb4ff'),roughness:.3}));screen.position.set(0,cabinetH+.02+screenH/2,.031);group.add(screen);
  const light=new THREE.PointLight('#8cc4ff',0,4,1.3);light.position.set(0,cabinetH+screenH/2,.5);group.add(light);
  apply=(level,t)=>{const flicker=1+.08*Math.sin(t*7)+.05*Math.sin(t*17);screen.material.emissiveIntensity=1.4*level*flicker;light.intensity=4*level*flicker;};
 }else if(kind==='seat'){
  const seat=Number(p.seat_height??h),body=material(color||'#8a6a5c'),cushion=material(new THREE.Color(color||'#8a6a5c').offsetHSL(0,0,.06));
  box(group,[w,seat-.08,d*.78],[0,(seat-.08)/2,d*.11],body);box(group,[w*.94,.08,d*.7],[0,seat-.04,d*.13],cushion);
  box(group,[w,seat+.42,d*.24],[0,(seat+.42)/2,-d*.38],body);
  for(const s of [-1,1])box(group,[.12,seat+.16,d],[s*(w/2-.06),(seat+.16)/2,0],body);
 }else{
  const mesh=stage.addProp(name,group.position.x,group.position.z,color,[w,h,d]);
  apply=level=>{mesh.material.emissive=new THREE.Color(color);mesh.material.emissiveIntensity=.45*level;};
  return {kind,group:mesh,apply};
 }
 stage.scene.add(group);return {kind,group,apply};
}
// The effect switches when the hand reaches the prop, part-way through the action.
function propLevel(name,kind){let level=stateLevel(timeline.props[name]?.state);
 for(const e of timeline.events){const fx=e.kind==='action'?e.payload.effect:null;if(!fx||fx.prop!==name)continue;
  const at=e.start+e.duration*.45;if(now<at)break;const target=fx.state==='toggle'?1-Math.round(level):stateLevel(fx.state);
  level+=(target-level)*Math.min(1,(now-at)/(TRANSITION[kind]||.3));}
 return level;}

// ---------------------------------------------------------------------------
// Camera presets and an auto-cut camera track derived from the compiled events.
const SHOT_NAMES={wide:'Wide',closeup:'Close-up',ots:'Over the shoulder',medium:'Medium',free:'Free orbit'};
function shotLabel(s){if(!s)return '';if(s.type==='ots')return `Over the shoulder on ${s.subject} (past ${s.listener})`;return SHOT_NAMES[s.type]+(s.subject?` on ${s.subject}`:'');}
function buildCameraTrack(data){const names=Object.keys(data.characters),shots=[];
 const listener=(n,g)=>g&&g!==n&&data.characters[g]?g:names.find(m=>m!==n)||null;
 for(const e of data.events){if(!(e.duration>0))continue;let s={type:'wide'};
  if(e.kind==='speech'&&e.actor){const l=listener(e.actor,e.payload.gaze);s=l?{type:'ots',subject:e.actor,listener:l}:{type:'closeup',subject:e.actor};}
  else if(e.kind==='emotion'&&e.actor)s={type:'closeup',subject:e.actor};
  else if((e.kind==='move'||e.kind==='action')&&e.actor)s={type:'medium',subject:e.actor};
  shots.push({...s,start:e.start,end:e.start+e.duration,events:[e.id]});}
 const out=[];
 for(const s of shots){const prev=out.at(-1);
  if(prev&&prev.type===s.type&&prev.subject===s.subject&&prev.listener===s.listener&&s.start-prev.end<.05){prev.end=Math.max(prev.end,s.end);prev.events.push(...s.events);continue;}
  const gapFrom=prev?prev.end:0;if(s.start-gapFrom>.05)out.push({type:'wide',start:gapFrom,end:s.start,events:[]});out.push(s);}
 if(out.length&&data.duration-out.at(-1).end>.05)out.push({type:'wide',start:out.at(-1).end,end:data.duration,events:[]});
 if(out.length)out.at(-1).end=Math.max(out.at(-1).end,data.duration);return out.map(s=>({...s,start:+s.start.toFixed(3),end:+s.end.toFixed(3)}));}
function currentShot(){if(cameraMode==='auto')return cameraTrack.find(s=>s.start<=now&&now<s.end)||cameraTrack.at(-1)||{type:'wide'};
 if(cameraMode==='wide'||cameraMode==='free')return {type:cameraMode};const [type,subject]=cameraMode.split(':');
 if(type==='ots'){const listener=Object.keys(actors).find(n=>n!==subject);return listener?{type,subject,listener}:{type:'closeup',subject};}
 return {type,subject};}
function headPoint(a){const head=a.rig?.bones.get('head');if(head&&a.rig.model.visible!==false)return head.getWorldPosition(new THREE.Vector3());return a.root.position.clone().add(new THREE.Vector3(0,1.62,0));}
function placeCamera(shot){const cam=stage.camera,a=actors[shot.subject];
 if(shot.type==='free'){const angle=Number($('camera-angle').value)/100;cam.position.set(6*Math.sin(angle),1.8,6*Math.cos(angle));cam.lookAt(0,1,0);return;}
 if(!a||shot.type==='wide'){cam.position.set(0,2.35,6.4);cam.lookAt(0,1,-.6);return;}
 const h=headPoint(a),forward=new THREE.Vector3(Math.sin(a.root.rotation.y),0,Math.cos(a.root.rotation.y));
 if(shot.type==='closeup'){cam.position.copy(h).addScaledVector(forward,1.05).add(new THREE.Vector3(0,.04,0));cam.lookAt(h.x,h.y-.05,h.z);return;}
 if(shot.type==='ots'&&actors[shot.listener]){
  // Over the shoulder: the camera sits just behind the listener's head, which frames one side of the shot, and
  // the aim is swung so the speaker stays inside the other side for the current field of view and aspect ratio.
  const l=headPoint(actors[shot.listener]),dir=l.clone().sub(h).setY(0).normalize(),right=new THREE.Vector3(-dir.z,0,dir.x);
  const halfH=Math.atan(Math.tan(THREE.MathUtils.degToRad(cam.fov)/2)*cam.aspect),side=.45,dist=Math.hypot(l.x-h.x,l.z-h.z);
  const spread=b=>Math.atan2(side,b)-Math.atan2(side,b+dist);let back=1;while(back<3&&spread(back)>1.3*halfH)back+=.1;
  // A seated speaker is seen from slightly higher, over the standing listener's shoulder.
  cam.position.copy(l).addScaledVector(dir,back).addScaledVector(right,side);cam.position.y=l.y+.12+Math.max(0,l.y-h.y)*.5;
  const yaw=Math.atan2(side,back)-.7*halfH,aim=dir.clone().negate().multiplyScalar(Math.cos(yaw)).addScaledVector(right,-Math.sin(yaw)),reach=back+dist;
  const pitch=(Math.atan2(h.y-.05-cam.position.y,reach)+Math.atan2(l.y-.1-cam.position.y,back))/2;
  cam.lookAt(cam.position.x+aim.x*reach,cam.position.y+Math.tan(pitch)*reach,cam.position.z+aim.z*reach);return;}
 // Medium: from the actor's facing side, swung toward the open front of the set so the action stays visible.
 const p=a.root.position,side=new THREE.Vector3(forward.x,0,Math.max(forward.z,0));if(side.length()<.5)side.set(forward.x>=0?.8:-.8,0,.6);side.normalize();
 cam.position.set(Math.max(-3.3,Math.min(3.3,p.x+side.x*2.7)),1.55,p.z+side.z*2.7+.4);cam.lookAt(p.x,1.0,p.z);}
function renderCameraOptions(){const select=$('camera-mode'),keep=cameraMode;select.replaceChildren(new Option('Auto-cut (camera track)','auto'),new Option('Wide','wide'),new Option('Free orbit (angle slider)','free'));
 for(const name of Object.keys(actors))for(const type of ['closeup','ots','medium'])select.append(new Option(shotLabel(currentShotFor(type,name)),`${type}:${name}`));
 cameraMode=[...select.options].some(o=>o.value===keep)?keep:'auto';select.value=cameraMode;}
function currentShotFor(type,subject){if(type!=='ots')return {type,subject};return {type,subject,listener:Object.keys(actors).find(n=>n!==subject)||'—'};}
function renderCameraTrack(){const strip=$('camera-track');strip.replaceChildren();if(!timeline)return;
 cameraTrack.forEach((s,i)=>{const seg=document.createElement('button');seg.type='button';seg.dataset.index=String(i);seg.className=`shot shot-${s.type}`;seg.style.left=`${s.start/timeline.duration*100}%`;seg.style.width=`${Math.max(.4,(s.end-s.start)/timeline.duration*100)}%`;
  seg.textContent=s.type==='wide'?'W':s.type==='ots'?`OTS ${s.subject}`:`${s.type==='closeup'?'CU':'MS'} ${s.subject}`;seg.title=`${s.start.toFixed(1)}–${s.end.toFixed(1)} s · ${shotLabel(s)}`;
  seg.onclick=()=>seek(s.start+.01);strip.append(seg);});
 const head=document.createElement('span');head.className='playhead';head.id='camera-playhead';strip.append(head);}

// ---------------------------------------------------------------------------
function build(data){sceneGeneration++;playbackGeneration++;timeline=data;now=0;playing=false;spoken.clear();speech.cancel();captures=[];motionTrace=[];motionByEvent=new Map();played=new Map();$('storyboard').replaceChildren();
 if(recorder?.state==='recording')stopRecording();xrSession?.end().catch(()=>{});
 stage.dispose();stage=createStage($('stage'));speech=newSpeech();actors={};props3d={};stage.avatar.root.visible=false;
 room=buildRoom(data);
 for(const [name,c] of Object.entries(data.characters)){const cast=c.avatar&&(/^[a-z0-9_-]+$/i.test(c.avatar)?new URL(`./avatars/${c.avatar}.glb`,location.href).href:/\.glb$/i.test(c.avatar)?c.avatar:undefined);
  actors[name]=cast?stage.makeAvatar(c.color||'#60c8d9',coord(c.x,480),coord(c.y,350),cast):stage.makeAvatar(c.color||'#60c8d9',coord(c.x,480),coord(c.y,350));}
 for(const [name,p] of Object.entries(data.props))props3d[name]=buildProp(name,p);
 cameraTrack=buildCameraTrack(data);renderCameraOptions();renderCameraTrack();
 $('scrub').max=data.duration;$('events').replaceChildren();for(const e of data.events){const li=document.createElement('li');li.textContent=`${e.start.toFixed(1)}s · ${e.actor||'SCENE'} · ${e.kind} · ${label(e)}`;$('events').append(li);}
 renderOverrides(data);updateTrace();for(const id of ['play','restart','capture','export','export-board','export-board-json','record'])$(id).disabled=false;
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
 return {...timeline,events,gesture_mode:GESTURE_MODE,played_gestures:[...played.values()],camera_mode:cameraMode,camera_track:cameraTrack};}
function updateTrace(){$('trace').textContent=JSON.stringify({paragraphs:timeline?.paragraphs,resolved_events:exportTimeline()?.events,camera_track:cameraTrack,selected_gesture_sequences:motionTrace},null,2);}
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
// Walk along the planned (obstacle-avoiding) path by arc length; next is the waypoint ahead.
function along(path,k){const lengths=path.slice(1).map((p,i)=>Math.hypot(p[0]-path[i][0],p[1]-path[i][1])),total=lengths.reduce((s,v)=>s+v,0);let d=k*total;
 for(let i=0;i<lengths.length;i++){if(d<=lengths[i]||i===lengths.length-1){const f=lengths[i]?Math.min(1,d/lengths[i]):1,a=path[i],b=path[i+1];return {point:[a[0]+(b[0]-a[0])*f,a[1]+(b[1]-a[1])*f],next:f<.999||i===lengths.length-1?b:path[i+2]};}d-=lengths[i];}
 return {point:path.at(-1),next:path.at(-1)};}
// Position, facing and seating replayed from the compiled move/action events.
function actorState(name){const c=timeline.characters[name];let pos=[c.x,c.y],toward=null,walking=false,seat=null;
 for(const e of timeline.events){if(e.actor!==name||e.start>now)continue;
  if(e.kind==='move'){const k=Math.min(1,(now-e.start)/Math.max(.001,e.duration)),step=along(e.payload.path||[e.payload.from||pos,e.payload.anchor],k);pos=step.point;walking=k<1;toward=walking?step.next:e.payload.face;seat=null;}
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
  // Interactions keep a neutral body pose; the reaching hand is placed by IK below.
  stage.gesture(s.walking?'walk':s.seat?'sit':action?.payload.interaction?'idle':(action?.payload.motion||'idle'),a,now);
  // Seat height comes from the prop; the renderer keeps the seated legs while clips drive the upper body.
  if(typeof stage.sit==='function')stage.sit(s.seat&&!s.walking?s.seat.height:null,a);
  // Two-bone IK puts the nearer hand on the prop's interaction point during the action.
  const reach=action?.payload.interaction,point=reach?[coord(reach[0],480),Number(reach[2]??1),coord(reach[1],350)]:null;
  if(typeof stage.reachTo==='function')stage.reachTo(point,a);else if(point)stage.pointAt(point,a);
  const utterance=active.find(e=>e.actor===name&&e.kind==='speech');
  // Listeners turn toward the current speaker when idle and follow them with their gaze.
  const heard=!utterance&&active.find(e=>e.kind==='speech'&&e.actor!==name&&actors[e.actor]),speaker=heard?actors[heard.actor].root.position:null;
  if(speaker&&!s.walking&&!s.seat&&!action)face(a,speaker.x,speaker.z);
  const look=utterance?gazePoint(name,utterance):speaker?[speaker.x,1.5,speaker.z]:null;
  // An idle speaker also turns the body toward whoever they address.
  if(utterance&&look&&!s.walking&&!s.seat&&!action)face(a,look[0],look[2]);
  if(typeof stage.lookAt==='function')stage.lookAt(look,a);
  if(utterance){caption=`${name}: ${utterance.payload.text}`;
   const selected=motionByEvent.get(utterance.id);
   if(selected?.motion&&(!playing||!a.speaking)){
    const elapsed=Math.max(0,now-utterance.start),duration=Math.max(.001,utterance.duration);
    selected.motion.draw(Math.min(.999,elapsed/duration),{elapsed,duration});markPlayed(utterance,selected);
   }
   if(playing&&$('voice').checked&&!spoken.has(utterance.id)){spoken.add(utterance.id);speakEvent(utterance,a);}
  }else if(a.motionActive&&!a.speaking)stage.clearMotion(a);
 }
 const t=performance.now()/1000;for(const [name,p] of Object.entries(props3d))p.apply(propLevel(name,p.kind),t);
 const shot=currentShot();if(!xrSession)placeCamera(shot);
 $('shot-label').textContent=(recorder?.state==='recording'?'● REC · ':'')+(xrSession?'VR view':shotLabel(shot));
 const head=$('camera-playhead');if(head)head.style.left=`${now/timeline.duration*100}%`;
 const activeShot=cameraMode==='auto'?String(cameraTrack.indexOf(shot)):'';for(const seg of $('camera-track').querySelectorAll('.shot'))seg.classList.toggle('active',seg.dataset.index===activeShot);
 const narration=active.find(e=>e.kind==='narration');
 $('caption').textContent=caption||(narration?narration.payload.text:'')||active.find(e=>e.kind==='scene')?.payload.heading||'Scene continues…';$('clock').textContent=now.toFixed(1)+' s';$('scrub').value=now;
 [...$('events').children].forEach((li,i)=>li.classList.toggle('active',active.includes(timeline.events[i])));$('play').textContent=playing?'Pause':'Play';
}
function tick(t){if(playing&&timeline){now=Math.min(timeline.duration,now+(last?(t-last)/1000:0));if(now>=timeline.duration){playing=false;playbackGeneration++;speech.cancel();if(recorder?.state==='recording')setTimeout(stopRecording,400);}}last=t;draw();requestAnimationFrame(tick);}requestAnimationFrame(tick);
function seek(time){now=Math.max(0,Math.min(timeline?.duration||0,time));playing=false;playbackGeneration++;speech.cancel();draw();}
async function compile(){playing=false;speech.cancel();try{const library=JSON.parse($('library').value),resolver=library.resolver||{};if($('resolver').value==='semantic')library.resolver={...resolver,backend:'sentence-transformer',emotion_model:$('emotion-model').value,action_model:$('action-model').value};else library.resolver={...resolver,backend:'tfidf'};const r=await fetch('/api/compile',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({script:$('script').value,format,library})});const data=await r.json();if(!r.ok)throw new Error(data.error);$('status').textContent=`Compiled ${data.events.length} events, ${data.duration.toFixed(1)} seconds.`;build(data);}catch(e){$('status').textContent=e.message;}}
$('compile').onclick=compile;
$('resolver').onchange=()=>$('model-options').hidden=$('resolver').value!=='semantic';
$('script-file').onchange=async e=>{const file=e.target.files[0];if(file){$('script').value=await file.text();format=file.name.endsWith('.fdx')?'fdx':'txt';}};
$('play').onclick=()=>{if(now>=timeline.duration){now=0;spoken.clear();}playing=!playing;if(!playing){playbackGeneration++;speech.cancel();}};$('restart').onclick=()=>{now=0;spoken.clear();playbackGeneration++;speech.cancel();playing=true;};$('scrub').oninput=()=>seek(Number($('scrub').value));
function download(name,body,type='application/json'){const url=URL.createObjectURL(body instanceof Blob?body:new Blob([body],{type})),a=Object.assign(document.createElement('a'),{href:url,download:name});a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}
$('export').onclick=()=>download('asap-timeline.json',JSON.stringify(exportTimeline(),null,2));
$('camera-mode').onchange=()=>{cameraMode=$('camera-mode').value;};
$('camera-angle').oninput=()=>{cameraMode='free';$('camera-mode').value='free';};

// ---------------------------------------------------------------------------
// Storyboard: captured frames with editable descriptions, exported as HTML or JSON.
const escapeHtml=s=>String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
function renderStoryboard(){const board=$('storyboard');board.replaceChildren();
 captures.forEach((c,i)=>{const card=document.createElement('article'),img=new Image(),p=document.createElement('p'),text=document.createElement('textarea'),remove=document.createElement('button');
  img.src=c.image;img.alt=`Scene at ${c.time.toFixed(1)} seconds`;p.textContent=`${c.time.toFixed(1)} s · ${c.shot} — ${c.caption}`;
  text.rows=2;text.value=c.description;text.placeholder='Describe this frame (shot notes, blocking, mood)…';text.setAttribute('aria-label',`Description for the frame at ${c.time.toFixed(1)} seconds`);text.oninput=()=>{c.description=text.value;};
  remove.type='button';remove.className='small';remove.textContent='Remove';remove.onclick=()=>{captures.splice(i,1);renderStoryboard();};
  card.append(img,p,text,remove);board.append(card);});}
// Redraw first so the caption, camera and frame match the current time even if no animation frame ran since a seek.
$('capture').onclick=()=>{draw();captures.push({time:now,caption:$('caption').textContent,shot:xrSession?'VR view':shotLabel(currentShot()),description:'',image:stage.capture()});renderStoryboard();};
const boardFrames=()=>captures.map(c=>({time:+c.time.toFixed(3),caption:c.caption,description:c.description,camera:c.shot,image:c.image}));
$('export-board').onclick=()=>download('asap-storyboard.html','<!doctype html><meta charset="utf-8"><title>ASAP captured storyboard</title><style>body{font:16px system-ui}img{width:420px;max-width:100%}article{display:inline-block;padding:15px;vertical-align:top;max-width:450px}.desc{white-space:pre-wrap}</style>'+captures.map(c=>`<article><img src="${c.image}" alt="Captured scene"><p>${c.time.toFixed(1)} s · ${escapeHtml(c.shot)} · ${escapeHtml(c.caption)}</p>${c.description?`<p class="desc">${escapeHtml(c.description)}</p>`:''}</article>`).join(''),'text/html');
$('export-board-json').onclick=()=>download('asap-storyboard.json',JSON.stringify({schema:'paperreach.asap.storyboard.v1',variant,frames:boardFrames()},null,2));

// ---------------------------------------------------------------------------
// WebM recording of the stage canvas. Local Kokoro audio is routed through a
// WebAudio bus into the recording; browser speechSynthesis output cannot be captured.
function ensureAudioBus(){if(audioBus)return audioBus;const AC=window.AudioContext||window.webkitAudioContext;if(!AC)return null;
 try{const context=new AC(),mix=context.createGain(),tap=context.createMediaStreamDestination();mix.connect(context.destination);mix.connect(tap);
  Object.defineProperty(context,'destination',{value:mix,configurable:true});audioBus={context,tap};speech.context=context;return audioBus;}catch{return null;}}
function startRecording(){const canvas=stage.renderer.domElement;
 if(!canvas.captureStream||!window.MediaRecorder){$('record-note').textContent='This browser cannot record the canvas (MediaRecorder or captureStream is unavailable).';return;}
 const stream=canvas.captureStream(30),bus=ensureAudioBus();if(bus){bus.context.resume().catch(()=>{});for(const track of bus.tap.stream.getAudioTracks())stream.addTrack(track);}
 const type=['video/webm;codecs=vp9,opus','video/webm;codecs=vp8,opus','video/webm'].find(t=>MediaRecorder.isTypeSupported(t));const chunks=[];
 recorder=new MediaRecorder(stream,type?{mimeType:type,videoBitsPerSecond:6e6}:undefined);
 recorder.ondataavailable=e=>{if(e.data.size)chunks.push(e.data);};
 recorder.onstop=()=>{recordedBlob=new Blob(chunks,{type:(recorder?.mimeType||'video/webm').split(';')[0]});stream.getVideoTracks().forEach(t=>t.stop());$('record').textContent='Record video';$('download-video').disabled=!recordedBlob.size;$('record-note').textContent=`Recorded ${(recordedBlob.size/1e6).toFixed(1)} MB WebM${bus?' with the WebAudio speech track':''}.`;};
 recorder.start(250);$('record').textContent='Stop recording';$('download-video').disabled=true;
 const browserVoice=$('voice').checked&&$('speech-backend').value==='browser';
 $('record-note').textContent=browserVoice?'Recording… Browser speechSynthesis audio cannot be captured, so this take has no dialogue audio; choose Local Kokoro to record speech.':'Recording the full take from the start…';
 now=0;spoken.clear();playbackGeneration++;speech.cancel();playing=true;}
function stopRecording(){if(recorder?.state==='recording')recorder.stop();}
$('record').onclick=()=>recorder?.state==='recording'?stopRecording():startRecording();
$('download-video').onclick=()=>{if(recordedBlob)download('asap-previz.webm',recordedBlob);};

// ---------------------------------------------------------------------------
// Immersive VR view (three.js VRButton pattern). The shared renderer drives its
// frames with window.requestAnimationFrame, which headsets pause while presenting,
// so those callbacks are run from the XR frame loop for the session's lifetime.
const nativeRAF=window.requestAnimationFrame.bind(window),nativeCAF=window.cancelAnimationFrame.bind(window);let xrQueue=new Map(),xrIds=0;
function bridgeFrames(renderer,on){
 if(on){window.requestAnimationFrame=cb=>{const id=-(++xrIds);xrQueue.set(id,cb);return id;};window.cancelAnimationFrame=id=>id<0?xrQueue.delete(id):nativeCAF(id);
  renderer.xr.setAnimationLoop(time=>{const queue=[...xrQueue.values()];xrQueue.clear();for(const cb of queue){try{cb(time);}catch(error){console.error(error);}}});return;}
 renderer.xr.setAnimationLoop(null);window.requestAnimationFrame=nativeRAF;window.cancelAnimationFrame=nativeCAF;const queue=[...xrQueue.values()];xrQueue.clear();queue.forEach(cb=>nativeRAF(cb));}
async function toggleVR(){if(xrSession){await xrSession.end().catch(()=>{});return;}
 try{const session=await navigator.xr.requestSession('immersive-vr',{optionalFeatures:['local-floor','bounded-floor']}),renderer=stage.renderer;
  renderer.xr.enabled=true;renderer.xr.setReferenceSpaceType('local-floor');await renderer.xr.setSession(session);xrSession=session;
  // Stand the viewer in front of the stage, facing the set.
  const base=renderer.xr.getReferenceSpace();if(base&&window.XRRigidTransform)renderer.xr.setReferenceSpace(base.getOffsetReferenceSpace(new XRRigidTransform({x:0,y:0,z:-3.4})));
  bridgeFrames(renderer,true);$('vr').textContent='Exit VR';
  session.addEventListener('end',()=>{bridgeFrames(renderer,false);renderer.xr.enabled=false;xrSession=null;$('vr').textContent='Enter VR';});
 }catch(error){$('vr-note').textContent=`The VR session could not start: ${error.message}`;}}
async function setupVR(){const button=$('vr');
 if(!navigator.xr||!window.isSecureContext){button.disabled=true;button.textContent='VR unavailable';$('vr-note').textContent='WebXR is unavailable in this browser or page context; the 3D stage stays in the page. Open the demo on localhost or HTTPS in a WebXR browser with a headset.';return;}
 let supported=false;try{supported=await navigator.xr.isSessionSupported('immersive-vr');}catch{}
 if(!supported){button.disabled=true;button.textContent='VR not supported';$('vr-note').textContent='No immersive-VR device or runtime was found; the 3D stage stays in the page.';return;}
 button.disabled=false;button.textContent='Enter VR';$('vr-note').textContent='';button.onclick=toggleVR;}
setupVR();

async function loadExample(name=''){const r=await fetch('/api/example'+(name?`?name=${encodeURIComponent(name)}`:''));const example=await r.json();if(!r.ok)throw new Error(example.error);$('script').value=example.script;$('library').value=JSON.stringify(example.library,null,2);format='txt';await compile();}
if($('example'))$('example').onchange=()=>loadExample($('example').value).catch(e=>$('status').textContent=e.message);
loadExample($('example')?.value||'').catch(e=>$('status').textContent=e.message);
window.addEventListener('pagehide',()=>{speech.cancel();stopRecording();xrSession?.end().catch(()=>{});stage.dispose();});
