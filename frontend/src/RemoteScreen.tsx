import {useCallback,useEffect,useRef,useState} from 'react';

type Mode='click'|'drag'|'scroll';
type Send=(o:object)=>void;
const MODES:{id:Mode;label:string;hint:string}[]=[
 {id:'click',label:'Click',hint:'Drag = move the pointer · tap = click where the pointer is · long-press = right click · two fingers = scroll'},
 {id:'drag',label:'Drag',hint:'Drag = hold left button (select text, move windows)'},
 {id:'scroll',label:'Scroll',hint:'Drag up/down to scroll the page'},
];
const QUICK:{label:string;msg:object}[]=[
 {label:'Esc',msg:{type:'key',key:'ESC'}},{label:'Tab',msg:{type:'key',key:'TAB'}},
 {label:'⌫',msg:{type:'key',key:'BACKSPACE'}},{label:'Enter',msg:{type:'key',key:'ENTER'}},
 {label:'←',msg:{type:'key',key:'LEFT'}},{label:'↑',msg:{type:'key',key:'UP'}},{label:'↓',msg:{type:'key',key:'DOWN'}},{label:'→',msg:{type:'key',key:'RIGHT'}},
 {label:'Win',msg:{type:'key',key:'WIN'}},{label:'Alt+Tab',msg:{type:'hotkey',keys:['ALT','TAB']}},
 {label:'Ctrl+C',msg:{type:'hotkey',keys:['CTRL','C']}},{label:'Ctrl+V',msg:{type:'hotkey',keys:['CTRL','V']}},
 {label:'Ctrl+A',msg:{type:'hotkey',keys:['CTRL','A']}},{label:'Ctrl+Z',msg:{type:'hotkey',keys:['CTRL','Z']}},
];
const LIFT_PX=104,LONG_PRESS_MS=500,TAP_SLOP=10,MOVE_INTERVAL_MS=16,SCROLL_STEP_PX=24;
const clamp01=(v:number)=>Math.min(1,Math.max(0,v));

export default function RemoteScreen({frame,send}:{frame:string;send:Send}){
 const wrap=useRef<HTMLDivElement>(null),img=useRef<HTMLImageElement>(null);
 const [mode,setMode]=useState<Mode>('click'),[full,setFull]=useState(false),[showKeys,setShowKeys]=useState(false);
 const pointers=useRef(new Map<number,{x:number;y:number}>());
 const g=useRef({start:{x:0,y:0},moved:false,long:false,timer:0 as number,down:false,multi:false,lastMove:0,scrollAcc:0,lastPos:{nx:.5,ny:.5}});

 // Map a touch point to 0..1 coordinates of the *visible picture* (object-fit: contain adds letterbox bars).
 const norm=useCallback((cx:number,cy:number)=>{
  const el=img.current;if(!el)return g.current.lastPos;
  const r=el.getBoundingClientRect(),nw=el.naturalWidth||r.width,nh=el.naturalHeight||r.height;
  const s=Math.min(r.width/nw,r.height/nh),w=nw*s,h=nh*s,ox=r.left+(r.width-w)/2,oy=r.top+(r.height-h)/2;
  const p={nx:clamp01((cx-ox)/w),ny:clamp01((cy-oy)/h)};g.current.lastPos=p;return p;
 },[]);

 // Click mode: the pointer sits above the fingertip so the finger never hides it; the gap shrinks to 0 only over the bottom 20%.
 const lifted=(cx:number,cy:number)=>{const el=img.current;if(!el)return norm(cx,cy);const r=el.getBoundingClientRect();const t=clamp01((cy-r.top)/r.height);return norm(cx,cy-LIFT_PX*Math.min(1,(1-t)/0.2))};

 useEffect(()=>{const h=()=>setFull(document.fullscreenElement===wrap.current);document.addEventListener('fullscreenchange',h);return()=>document.removeEventListener('fullscreenchange',h)},[]);
 useEffect(()=>()=>window.clearTimeout(g.current.timer),[]);

 const toggleFull=async()=>{
  try{
   if(document.fullscreenElement){await document.exitFullscreen();(screen.orientation as any)?.unlock?.()}
   else{await wrap.current?.requestFullscreen();try{await (screen.orientation as any)?.lock?.('landscape')}catch{}}
  }catch{}
 };

 const endDrag=(e:{clientX:number;clientY:number})=>{if(g.current.down){send({type:'up',button:'left',...norm(e.clientX,e.clientY)});g.current.down=false}};

 const onDown=(e:React.PointerEvent)=>{
  e.preventDefault();e.currentTarget.setPointerCapture(e.pointerId);
  const st=g.current;
  if(e.pointerType==='mouse'&&e.button===2){send({type:'click',button:'right',...norm(e.clientX,e.clientY)});return}
  pointers.current.set(e.pointerId,{x:e.clientX,y:e.clientY});
  if(pointers.current.size>=2){ // second finger: switch to two-finger scrolling, cancel anything in flight
   window.clearTimeout(st.timer);endDrag(e);st.multi=true;st.scrollAcc=0;return;
  }
  st.start={x:e.clientX,y:e.clientY};st.moved=false;st.long=false;st.multi=false;st.scrollAcc=0;
  if(mode==='drag'){send({type:'down',button:'left',...norm(e.clientX,e.clientY)});st.down=true}
  if(mode==='click'){st.timer=window.setTimeout(()=>{
   if(!st.moved&&pointers.current.size===1){st.long=true;send({type:'click',button:'right'});navigator.vibrate?.(30)}
  },LONG_PRESS_MS)}
 };

 const onMove=(e:React.PointerEvent)=>{
  const prev=pointers.current.get(e.pointerId);if(!prev)return;
  const st=g.current,dy=e.clientY-prev.y;pointers.current.set(e.pointerId,{x:e.clientX,y:e.clientY});
  if(st.multi){ // two-finger scroll: use the average vertical movement of both fingers
   st.scrollAcc+=dy/pointers.current.size;scrollBy(st);return;
  }
  if(!st.moved&&Math.hypot(e.clientX-st.start.x,e.clientY-st.start.y)>TAP_SLOP){st.moved=true;window.clearTimeout(st.timer)}
  if(mode==='scroll'){st.scrollAcc+=dy;scrollBy(st);return}
  if(mode==='click'||mode==='drag'){
   const now=performance.now();if(now-st.lastMove<MOVE_INTERVAL_MS)return;st.lastMove=now;
   send({type:'move',...(mode==='click'?lifted(e.clientX,e.clientY):norm(e.clientX,e.clientY))});
  }
 };
 // Finger down the screen (dy>0) scrolls up on the PC, like a phone: the content follows the finger.
 const scrollBy=(st:typeof g.current)=>{const steps=Math.trunc(st.scrollAcc/SCROLL_STEP_PX);if(steps){send({type:'scroll',dy:steps});st.scrollAcc-=steps*SCROLL_STEP_PX}};

 const onUp=(e:React.PointerEvent)=>{
  const st=g.current;if(!pointers.current.has(e.pointerId))return;
  pointers.current.delete(e.pointerId);window.clearTimeout(st.timer);
  if(st.multi){if(pointers.current.size===0)st.multi=false;return}
  if(mode==='drag'){endDrag(e);return}
  if(mode==='click'&&!st.moved&&!st.long&&e.type==='pointerup')send({type:'click',button:'left'});
 };
 const onCancel=(e:React.PointerEvent)=>{pointers.current.delete(e.pointerId);window.clearTimeout(g.current.timer);endDrag(e);g.current.multi=pointers.current.size>0};
 const onWheel=(e:React.WheelEvent)=>{if(e.deltaY)send({type:'scroll',dy:e.deltaY>0?-2:2})};

 const hint=MODES.find(m=>m.id===mode)?.hint;
 return <div ref={wrap} className={'remote'+(full?' full':'')}>
  <div className="modes">
   {MODES.map(m=><button key={m.id} className={mode===m.id?'':'secondary'} onClick={()=>setMode(m.id)}>{m.label}</button>)}
   <button className="secondary" onClick={()=>send({type:'click',count:2,...g.current.lastPos})}>Double-click</button>
   <button className="secondary" onClick={()=>setShowKeys(v=>!v)}>Keys</button>
   <button className="secondary" onClick={()=>void toggleFull()}>{full?'Exit fullscreen':'Fullscreen'}</button>
  </div>
  <div className="stage" onPointerDown={onDown} onPointerMove={onMove} onPointerUp={onUp} onPointerCancel={onCancel} onWheel={onWheel} onContextMenu={e=>e.preventDefault()}>
   {frame?<img ref={img} className="screen" src={frame} draggable={false} alt="Live PC screen"/>:<div className="waiting">Waiting for the PC screen…</div>}
  </div>
  <small className="muted hint">{hint}</small>
  {showKeys&&<div className="keys">{QUICK.map(k=><button key={k.label} className="secondary" onClick={()=>send(k.msg)}>{k.label}</button>)}</div>}
  <div className="row"><input placeholder="Type text, then press Enter" onKeyDown={e=>{if(e.key==='Enter'&&e.currentTarget.value){send({type:'type',text:e.currentTarget.value});e.currentTarget.value=''}}}/><button onClick={()=>send({type:'key',key:'ENTER'})}>Enter</button></div>
 </div>;
}
