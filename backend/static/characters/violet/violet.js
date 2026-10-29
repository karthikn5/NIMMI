/**
 * Violet, Nimmi's animated character, as a chat launcher: <nimmi-violet>. Loaded by nimmi-widget.js and the builder
 * preview when an assistant's launcher is the character "violet". From the owner's Violet design (violet-source,
 * avatar.js): a reference-based 2.5D figure (rendered picture, animated SVG eyes, a volumetric WebGL arm), changed for
 * a small figure in the corner of any website:
 * - framed to her outline (VIEW); the waving arm reaches outside the frame (overflow is visible);
 * - a whole copy of the upper body under the arm and torso layers at rest, so their shared edge shows no seam;
 * - one WebP picture loaded with CORS (the 3D arm reads it as a texture on the customer's site);
 * - no loading or error text (the launcher shows the plain picture instead); fades in when ready;
 * - about 30 updates a second, and a larger look (eyes, head turn) when drawn small.
 * Public API: wave(), blink(), nod(), speak(ms), stopSpeaking(), setThinking(bool), setOptions({...}).
 * Events: avatar-ready, avatar-state ({ state }), avatar-error.
 */
import {WaveRig, waveMotion} from './wave-rig.js';
const PICTURE = new URL('./character.webp', import.meta.url).href;
const VIEW = {x: 418, y: 80, w: 390, h: 1170};
const clamp = (v, a, b) => Math.min(b, Math.max(a, v));
const smooth = v => { const x = clamp(v, 0, 1); return x*x*(3-2*x); };
let serial = 0;

function artwork(id) {
  const ref = name => `${id}-${name}`;
  const eye = (side, x, shape) => `
    <g class="eye-unit" data-eye="${side}">
      <ellipse class="lid-surface" cx="${x}" cy="275" rx="35" ry="27" fill="url(#${ref(`skin-${side}`)})" filter="url(#${ref('lid-soft')})" opacity="0"/>
      <g class="eye-frame" data-center="${x}">
      <g clip-path="url(#${ref(`whole-eye-${side}`)})"><use href="#${ref('photo')}"/></g>
      <g clip-path="url(#${ref(`eye-${side}`)})">
        <path d="${shape}" fill="url(#${ref('white')})"/>
        <g class="iris" data-iris="${side}"><g clip-path="url(#${ref(`iris-${side}`)})"><use href="#${ref('photo')}"/></g></g>
      </g>
      </g>
      <g class="lid" data-lid="${side}" opacity="0">
        <path d="M${x-26} 277 Q${x} 290 ${x+24} 277" fill="none" stroke="#42233c" stroke-width="3.6" stroke-linecap="round"/>
        <path d="M${x-25} 278 l-5 -2 M${x+23} 278 l5 -3" fill="none" stroke="#42233c" stroke-width="2.2" stroke-linecap="round"/>
      </g>
    </g>`;
  const leftEye = 'M541 271 C545 259 558 256 566 258 C579 259 586 270 587 288 C574 297 551 294 544 283 Q540 277 541 271Z';
  const rightEye = 'M638 288 C639 273 645 261 656 258 C668 254 682 263 685 273 C690 290 660 300 641 290Z';
  const armHole = 'M484 438 Q510 434 535 453 L532 514 Q519 575 510 628 L491 751 L500 878 L417 885 L413 740 L450 540Z';
  return `<style>
    :host{display:block;position:relative;-webkit-tap-highlight-color:transparent;opacity:0;transition:opacity .4s ease}
    :host([data-ready]){opacity:1}
    svg{width:100%;height:100%;overflow:visible;display:block;pointer-events:none}
    @media(prefers-reduced-motion:reduce){:host{transition:none}}
  </style>
  <svg xmlns="http://www.w3.org/2000/svg" viewBox="${VIEW.x} ${VIEW.y} ${VIEW.w} ${VIEW.h}" aria-hidden="true">
    <defs>
      <image id="${ref('photo')}" href="${PICTURE}" width="1218" height="1291"/>
      <radialGradient id="${ref('shadow')}"><stop offset="0" stop-color="#45304f" stop-opacity=".24"/><stop offset=".5" stop-color="#45304f" stop-opacity=".12"/><stop offset="1" stop-color="#45304f" stop-opacity="0"/></radialGradient>
      <radialGradient id="${ref('white')}" cx="58%" cy="65%" r="80%"><stop stop-color="#fffdfc"/><stop offset=".62" stop-color="#efebee"/><stop offset="1" stop-color="#9f879a"/></radialGradient>
      <radialGradient id="${ref('skin-left')}" cx="70%" cy="35%" r="85%"><stop stop-color="#f7bb9c"/><stop offset="1" stop-color="#df967e"/></radialGradient>
      <radialGradient id="${ref('skin-right')}" cx="25%" cy="35%" r="85%"><stop stop-color="#f6bb9d"/><stop offset="1" stop-color="#e9a38b"/></radialGradient>
      <filter id="${ref('lid-soft')}" x="-20%" y="-20%" width="140%" height="140%"><feGaussianBlur stdDeviation="1.7"/></filter>
      <clipPath id="${ref('legs')}"><path d="M489 749 H735 V1133 L754 1240 H478 V1133Z"/></clipPath>
      <clipPath id="${ref('upper')}"><path d="M350 405 H860 V903 H735 V752 H490 V903 H350Z"/></clipPath>
      <mask id="${ref('torso')}"><rect width="1218" height="1291" fill="white"/><path d="${armHole}" fill="black"/></mask>
      <clipPath id="${ref('head')}"><path d="M410 50 H813 V414 H410Z"/></clipPath>
      <clipPath id="${ref('rest-arm')}"><path d="${armHole}"/></clipPath>
      <clipPath id="${ref('eye-left')}"><path d="${leftEye}"/></clipPath>
      <clipPath id="${ref('eye-right')}"><path d="${rightEye}"/></clipPath>
      <clipPath id="${ref('whole-eye-left')}"><ellipse cx="568" cy="275" rx="35" ry="26"/></clipPath>
      <clipPath id="${ref('whole-eye-right')}"><ellipse cx="657" cy="275" rx="35" ry="26"/></clipPath>
      <clipPath id="${ref('iris-left')}"><ellipse cx="568" cy="277" rx="16.4" ry="17.3"/></clipPath>
      <clipPath id="${ref('iris-right')}"><ellipse cx="657" cy="277" rx="16.3" ry="17.3"/></clipPath>
      <clipPath id="${ref('mouth')}"><ellipse cx="612" cy="340" rx="39" ry="12"/></clipPath>
    </defs>
    <g id="floor-shadow"><ellipse cx="611" cy="1219" rx="182" ry="30" fill="url(#${ref('shadow')})"/><ellipse cx="549" cy="1210" rx="63" ry="10" fill="url(#${ref('shadow')})"/><ellipse cx="678" cy="1210" rx="65" ry="10" fill="url(#${ref('shadow')})"/></g>
    <g id="figure">
      <g clip-path="url(#${ref('legs')})"><use href="#${ref('photo')}"/></g>
      <g id="upper-body">
        <g id="rest-base" clip-path="url(#${ref('upper')})"><use href="#${ref('photo')}"/></g>
        <g id="rest-arm" clip-path="url(#${ref('rest-arm')})"><use href="#${ref('photo')}"/></g>
        <foreignObject id="volume-arm" x="140" y="260" width="460" height="660" opacity="0"><canvas xmlns="http://www.w3.org/1999/xhtml" id="arm-canvas" style="width:460px;height:660px;display:block;pointer-events:none"></canvas></foreignObject>
        <g clip-path="url(#${ref('upper')})" mask="url(#${ref('torso')})"><use href="#${ref('photo')}"/></g>
        <g id="head">
          <g clip-path="url(#${ref('head')})"><use href="#${ref('photo')}"/></g>
          ${eye('left',568,leftEye)}${eye('right',657,rightEye)}
          <g id="mouth" opacity="0"><g clip-path="url(#${ref('mouth')})"><use href="#${ref('photo')}"/></g></g>
        </g>
      </g>
    </g>
  </svg>`;
}

export class NimmiViolet extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({mode:'open'});
    this.options = { ambient:true, gaze:true, reducedMotion:matchMedia('(prefers-reduced-motion: reduce)').matches };
    this.pointer = {x:0,y:0,active:false};
    this.gaze = {x:0,y:0};
    this.times = {wave:-1e9,blink:-1e9,nod:-1e9,speaking:0};
    this.ready = false; this.thinking = false; this.state = 'idle';
    this.nextBlink = performance.now()+2500+Math.random()*2500;
    this.nextWave = performance.now()+18000+Math.random()*12000;
    this._frame = this._frame.bind(this);
  }
  connectedCallback() {
    const loadToken = this.loadToken = (this.loadToken || 0) + 1;
    this.controller = new AbortController();
    const {signal} = this.controller;
    this.shadowRoot.innerHTML = artwork(`violet-${++serial}`);
    this.parts = Object.fromEntries(['head','figure','upper-body','rest-base','rest-arm','volume-arm','mouth','floor-shadow'].map(id=>[id,this.shadowRoot.getElementById(id)]));
    this.irises = [...this.shadowRoot.querySelectorAll('.iris')];
    this.lids = [...this.shadowRoot.querySelectorAll('.lid')];
    this.lidSurfaces = [...this.shadowRoot.querySelectorAll('.lid-surface')];
    this.eyeFrames = [...this.shadowRoot.querySelectorAll('.eye-frame')];
    window.addEventListener('pointermove',e=>{ if(e.pointerType==='touch')return; this.pointer={x:e.clientX,y:e.clientY,active:true}; },{passive:true,signal});
    document.addEventListener('pointerout',e=>{if(!e.relatedTarget)this.pointer.active=false;},{signal});
    window.addEventListener('blur',()=>{this.pointer.active=false;},{signal});
    this.addEventListener('click',()=>this.wave(),{signal});
    document.addEventListener('visibilitychange',()=>{
      cancelAnimationFrame(this.raf);
      if(!document.hidden){this.last=0;this.nextBlink=performance.now()+2000;this.nextWave=performance.now()+20000;this.raf=requestAnimationFrame(this._frame);}
    },{signal});
    this.observer = new IntersectionObserver(entries=>{this.visible=entries[0].isIntersecting;},{threshold:0});
    this.observer.observe(this);
    new Promise((resolve,reject)=>{const im=new Image();im.crossOrigin='anonymous';im.onload=()=>resolve(im);im.onerror=reject;im.src=PICTURE;}).then(neutral=>{
      if(!this.isConnected||loadToken!==this.loadToken)return;
      try{this.rig=new WaveRig(this.shadowRoot.getElementById('arm-canvas'),neutral);this.dataset.renderer=this.rig.gl?'webgl':'software-3d';}catch(error){this.rig=null;this.dataset.rendererError=String(error.message);}
      this.ready=true;this.setAttribute('data-ready','');
      this.dispatchEvent(new CustomEvent('avatar-ready',{bubbles:true}));
      this.raf=requestAnimationFrame(this._frame);
    }).catch(()=>{
      if(loadToken===this.loadToken)this.dispatchEvent(new CustomEvent('avatar-error',{bubbles:true}));
    });
  }
  disconnectedCallback(){this.loadToken=(this.loadToken||0)+1;this.controller?.abort();this.observer?.disconnect();cancelAnimationFrame(this.raf);this.rig?.dispose();}
  setOptions(options){Object.assign(this.options,options);if(options.reducedMotion){this.times.wave=-1e9;this.times.nod=-1e9;this.times.blink=-1e9;}this.nextWave=performance.now()+22000;return this;}
  wave(){if(!this.ready||this.options.reducedMotion||!this.rig)return;if(performance.now()-this.times.wave<4700)return;this.times.wave=performance.now();this.nextWave=performance.now()+22000+Math.random()*14000;this._setState('waving');}
  blink(){if(!this.ready)return;this.times.blink=performance.now();this.nextBlink=performance.now()+2800+Math.random()*3200;}
  nod(){if(!this.ready)return;this.times.nod=performance.now();}
  speak(duration=3000){this.thinking=false;this.times.speaking=performance.now()+duration;}
  stopSpeaking(){this.times.speaking=0;}
  setThinking(value){this.thinking=!!value;}
  _setState(state){if(this.state!==state){this.state=state;this.dataset.state=state;this.dispatchEvent(new CustomEvent('avatar-state',{detail:{state},bubbles:true}));}}
  _frame(now){
    this.raf=requestAnimationFrame(this._frame);
    if(document.hidden||this.visible===false)return;
    if(this.last&&now-this.last<30)return; // about 30 updates a second is plenty for a small figure
    const dt=this.last?Math.min(64,now-this.last):16;this.last=now;
    const time=now/1000, reduced=this.options.reducedMotion;
    if(this.options.ambient&&!reduced){
      if(now>=this.nextBlink)this.blink();
      if(now>=this.nextWave&&!this.thinking&&now>this.times.speaking)this.wave();
    }
    const rect=this.getBoundingClientRect();
    const scale=Math.min(rect.width/VIEW.w,rect.height/VIEW.h);
    const xOffset=(rect.width-VIEW.w*scale)/2;
    const yOffset=(rect.height-VIEW.h*scale)/2;
    const headX=rect.left+xOffset+(611-VIEW.x)*scale,headY=rect.top+yOffset+(277-VIEW.y)*scale;
    const charLeft=headX-190*scale,charRight=headX+190*scale;
    const charTop=rect.top+yOffset+(85-VIEW.y)*scale,charBottom=rect.top+yOffset+(1220-VIEW.y)*scale;
    const px=this.pointer.x,py=this.pointer.y;
    const distance=Math.hypot(Math.max(charLeft-px,0,px-charRight),Math.max(charTop-py,0,py-charBottom));
    const near=this.options.gaze&&this.pointer.active&&distance<140&&!reduced;
    const tx=near?clamp((px-headX)/150,-1,1):0,ty=near?clamp((py-headY)/170,-1,1):0;
    const ease=1-Math.exp(-dt/130);
    this.gaze.x+=(tx-this.gaze.x)*ease;this.gaze.y+=(ty-this.gaze.y)*ease;
    // Drawn small (a launcher is ~140px tall), the same look would move the eyes by half a pixel.
    const look=clamp(540/Math.max(rect.height,1),1,1.8);
    const waveTime=now-this.times.wave;
    const gesture=waveMotion(waveTime);
    const waving=gesture.active&&!reduced;
    const motion=reduced?0:1;
    const wave=gesture.lift*motion;
    const armOpacity=waving?gesture.opacity:0;
    this.parts['volume-arm'].setAttribute('opacity',armOpacity);
    this.parts['rest-arm'].setAttribute('opacity',1-armOpacity);
    this.parts['rest-base'].setAttribute('opacity',1-armOpacity);
    if(waving&&this.rig&&(!this.lastRigFrame||now-this.lastRigFrame>30)){this.rig.render(gesture);this.lastRigFrame=now;}
    const breathing=this.options.ambient&&!reduced?Math.sin(time*1.65):0;
    const sway=this.options.ambient&&!reduced?Math.sin(time*.63)*.22:0;
    const nodTime=now-this.times.nod;
    const nod=nodTime<1150?Math.sin(nodTime/1150*Math.PI*2)*Math.sin(nodTime/1150*Math.PI)*motion:0;
    const speaking=now<this.times.speaking;
    const headTurn=this.gaze.x*1.35*Math.min(look,1.5)+sway-(wave*1.3);
    this.parts['upper-body'].setAttribute('transform',`translate(0 ${-.75*breathing}) rotate(${gesture.lean*motion} 611 752) translate(611 752) scale(1 ${1+.0016*breathing}) translate(-611 -752)`);
    this.parts.head.setAttribute('transform',`translate(${this.gaze.x*1.7} ${this.gaze.y*.8+nod*3}) rotate(${headTurn} 611 405)`);
    this.parts['floor-shadow'].setAttribute('opacity',.96+breathing*.025);
    let blink=0;
    const blinkTime=now-this.times.blink;
    if(blinkTime<220)blink=blinkTime<80?smooth(blinkTime/80):1-smooth((blinkTime-80)/140);
    this.lidSurfaces.forEach(el=>el.setAttribute('opacity',smooth(blink/.13)));
    this.eyeFrames.forEach(el=>el.setAttribute('transform',`translate(${el.dataset.center} 277) scale(1 ${Math.max(.015,1-blink)}) translate(-${el.dataset.center} -277)`));
    this.lids.forEach(el=>el.setAttribute('opacity',smooth((blink-.8)/.2)));
    this.irises.forEach(el=>el.setAttribute('transform',`translate(${this.gaze.x*4.6*look} ${this.gaze.y*2.7*look})`));
    this.parts.mouth.setAttribute('opacity',speaking&&!reduced?.85:0);
    this.parts.mouth.setAttribute('transform',`translate(612 336) scale(1 ${1+(speaking?Math.abs(Math.sin(time*9))*.25:0)}) translate(-612 -336)`);
    this._setState(waving?'waving':nodTime<1150?'nodding':speaking?'speaking':this.thinking?'thinking':near?'attentive':'idle');
  }
}
if(!customElements.get('nimmi-violet'))customElements.define('nimmi-violet',NimmiViolet);
