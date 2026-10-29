/**
 * Continuous volumetric waving limb, rendered with WebGL.
 * The sleeve is one deformed tube (not rotating image cutouts). Its texture is
 * sampled from the reference render. Palm and five fingers have rounded 3D
 * geometry, joint bends, and real surface normals. No external dependencies.
 */
const add=(a,b)=>a.map((v,i)=>v+b[i]);
const sub=(a,b)=>a.map((v,i)=>v-b[i]);
const mul=(a,t)=>a.map(v=>v*t);
const mix=(a,b,t)=>a.map((v,i)=>v+(b[i]-v)*t);
const unit=a=>mul(a,1/(Math.hypot(...a)||1));
const cross=(a,b)=>[a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0]];
const radians=v=>v*Math.PI/180;
const rotateZ=(v,a)=>[v[0]*Math.cos(a)-v[1]*Math.sin(a),v[0]*Math.sin(a)+v[1]*Math.cos(a),v[2]];
const clamp=(v,a=0,b=1)=>Math.min(b,Math.max(a,v));
// Minimum-jerk interpolation: both velocity and acceleration stop at each end.
const ease=t=>{t=clamp(t);return t*t*t*(10+t*(-15+6*t));};

export function waveMotion(ms) {
  const up=ease((ms-130)/920);
  const down=ease((ms-3300)/1250);
  const lift=up*(1-down);
  const greeting=ease((ms-1100)/270)*(1-ease((ms-2970)/300));
  const phase=(ms-1150)/780*Math.PI*2;
  const handSwing=Math.sin(phase)*greeting;
  const shoulder=17*lift-1.6*Math.sin(clamp(ms/400)*Math.PI)*(1-up);
  // Elbow follows the shoulder by 120 ms, then comes down slightly before it.
  const bend=137*ease((ms-250)/960)*(1-ease((ms-3220)/1210));
  return {
    active:ms>=0&&ms<4700,
    lift, shoulder, bend,
    wrist:handSwing*11.5,
    forearmSwing:Math.sin(phase-.35)*greeting*2.4,
    twist:(163+Math.sin(phase-.55)*7)*lift,
    fingers:ease((ms-450)/650)*(1-ease((ms-3450)/950)),
    flutter:Math.sin(phase-.7)*greeting,
    opacity:ease(ms/160)*(1-ease((ms-4490)/150)),
    lean:-.33*lift,
  };
}

const VERTEX=`
attribute vec3 aPosition;
attribute vec3 aNormal;
attribute vec2 aUV;
attribute float aMaterial;
varying vec3 vNormal;
varying vec2 vUV;
varying float vMaterial;
void main(){
  gl_Position=vec4((aPosition.x-140.0)/460.0*2.0-1.0,1.0-(aPosition.y-260.0)/660.0*2.0,-aPosition.z/300.0,1.0);
  vNormal=aNormal;vUV=aUV;vMaterial=aMaterial;
}`;
const FRAGMENT=`
precision mediump float;
varying vec3 vNormal;
varying vec2 vUV;
varying float vMaterial;
uniform sampler2D uTexture;
void main(){
  vec3 n=normalize(vNormal);
  vec3 key=normalize(vec3(-0.52,-0.65,1.1));
  float light=max(0.0,dot(n,key));
  float rim=pow(1.0-max(n.z,0.0),2.0);
  vec3 color;
  if(vMaterial<0.5){
    vec4 tex=texture2D(uTexture,vUV);
    vec3 fabric=mix(vec3(.52,.345,.71),tex.rgb,smoothstep(.1,.9,tex.a));
    color=fabric*(.77+.27*light);
    color+=vec3(.13,.09,.18)*pow(max(0.0,dot(reflect(-key,n),vec3(0.,0.,1.))),24.0)*.1;
  }else if(vMaterial<1.5){
    color=vec3(1.0,.73,.60)*(.76+.25*light);
    color+=vec3(.10,.052,.034)*rim*.22;
    color+=vec3(.12,.09,.07)*pow(max(0.,dot(reflect(-key,n),vec3(0.,0.,1.))),19.)*.25;
  }else if(vMaterial<2.5){
    color=vec3(.94,.92,.96)*(.72+.28*light);
  }else{
    color=vec3(.95,.69,.58)*(.78+.22*light);
  }
  gl_FragColor=vec4(color,1.0);
}`;

function shader(gl,type,source){
  const s=gl.createShader(type);gl.shaderSource(s,source);gl.compileShader(s);
  if(!gl.getShaderParameter(s,gl.COMPILE_STATUS))throw new Error(gl.getShaderInfoLog(s));
  return s;
}

export class WaveRig {
  constructor(canvas,image){
    this.canvas=canvas;
    const gl=this.gl=canvas.getContext('webgl',{alpha:true,antialias:true,premultipliedAlpha:true,preserveDrawingBuffer:false});
    // 2× oversampling gives clean fingertips and the same scale as the SVG.
    canvas.width=920;canvas.height=1320;
    this.vertices=[];
    if(!gl){
      this.ctx=canvas.getContext('2d',{alpha:true});
      if(!this.ctx)throw new Error('Canvas unavailable');
      const textureCanvas=document.createElement('canvas');
      textureCanvas.width=image.width;textureCanvas.height=image.height;
      const context=textureCanvas.getContext('2d',{willReadFrequently:true});
      context.drawImage(image,0,0);
      this.texturePixels=context.getImageData(0,0,image.width,image.height);
      return;
    }
    const program=this.program=gl.createProgram();
    const vs=shader(gl,gl.VERTEX_SHADER,VERTEX),fs=shader(gl,gl.FRAGMENT_SHADER,FRAGMENT);
    gl.attachShader(program,vs);gl.attachShader(program,fs);gl.linkProgram(program);
    gl.deleteShader(vs);gl.deleteShader(fs);
    if(!gl.getProgramParameter(program,gl.LINK_STATUS))throw new Error(gl.getProgramInfoLog(program));
    gl.useProgram(program);
    this.buffer=gl.createBuffer();gl.bindBuffer(gl.ARRAY_BUFFER,this.buffer);
    const attributes=[['aPosition',3,0],['aNormal',3,12],['aUV',2,24],['aMaterial',1,32]];
    attributes.forEach(([name,size,offset])=>{const location=gl.getAttribLocation(program,name);gl.enableVertexAttribArray(location);gl.vertexAttribPointer(location,size,gl.FLOAT,false,36,offset);});
    this.texture=gl.createTexture();gl.bindTexture(gl.TEXTURE_2D,this.texture);
    gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_WRAP_S,gl.CLAMP_TO_EDGE);gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_WRAP_T,gl.CLAMP_TO_EDGE);
    gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_MIN_FILTER,gl.LINEAR);gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_MAG_FILTER,gl.LINEAR);
    gl.texImage2D(gl.TEXTURE_2D,0,gl.RGBA,gl.RGBA,gl.UNSIGNED_BYTE,image);
    gl.uniform1i(gl.getUniformLocation(program,'uTexture'),0);
    gl.enable(gl.DEPTH_TEST);gl.depthFunc(gl.LEQUAL);gl.disable(gl.CULL_FACE);
    gl.clearColor(0,0,0,0);
  }
  vertex(p,n,uv=[0,0],material=0){return [...p,...n,...uv,material];}
  triangle(a,b,c){this.vertices.push(...a,...b,...c);}
  grid(rows){
    for(let y=0;y<rows.length-1;y++)for(let x=0;x<rows[y].length-1;x++){
      this.triangle(rows[y][x],rows[y+1][x],rows[y][x+1]);
      this.triangle(rows[y][x+1],rows[y+1][x],rows[y+1][x+1]);
    }
  }
  ellipsoid(center,radii,basis,material=1,slices=20,bands=14){
    if(!this.gl){slices=Math.min(slices,14);bands=Math.min(bands,10);}
    const rows=[];
    for(let j=0;j<=bands;j++){
      const p=-Math.PI/2+j/bands*Math.PI,row=[];
      for(let i=0;i<=slices;i++){
        const a=i/slices*Math.PI*2,n=[Math.cos(p)*Math.cos(a),Math.sin(p),Math.cos(p)*Math.sin(a)];
        const point=add(center,add(add(mul(basis[0],n[0]*radii[0]),mul(basis[1],n[1]*radii[1])),mul(basis[2],n[2]*radii[2])));
        const normal=unit(add(add(mul(basis[0],n[0]/radii[0]),mul(basis[1],n[1]/radii[1])),mul(basis[2],n[2]/radii[2])));
        row.push(this.vertex(point,normal,[0,0],material));
      }rows.push(row);
    }this.grid(rows);
  }
  tube(points,radii,material=1,uvAt=null,sides=16){
    if(!this.gl)sides=Math.min(sides,14);
    const rows=[];
    for(let j=0;j<points.length;j++){
      const tangent=unit(sub(points[Math.min(j+1,points.length-1)],points[Math.max(j-1,0)]));
      const x=unit(cross(tangent,[0,0,1])),z=unit(cross(x,tangent)),row=[];
      for(let i=0;i<=sides;i++){
        const a=i/sides*Math.PI*2;
        const normal=unit(add(mul(x,Math.cos(a)),mul(z,Math.sin(a))));
        const point=add(points[j],mul(normal,radii[j]));
        row.push(this.vertex(point,normal,uvAt?uvAt(j/(points.length-1),Math.cos(a)):[0,0],material));
      }rows.push(row);
    }this.grid(rows);
  }
  finger(start,direction,length,radius,basis,curl){
    const points=[],radii=[];
    // A continuous curved finger with a relaxed distal joint, not three capsules.
    const rings=this.gl?10:8;
    for(let i=0;i<=rings;i++){
      const t=i/rings;
      const forward=length*(Math.sin(curl*t)/(curl||1));
      const straight=curl<.001?length*t:forward;
      const depth=length*(1-Math.cos(curl*t))/(curl||1);
      points.push(add(start,add(mul(direction,straight),mul(basis[2],depth))));
      radii.push(radius*(1-.17*t)*Math.sqrt(Math.max(.015,1-Math.pow(Math.max(0,(t-.81)/.19),2))));
    }
    this.tube(points,radii,1,null,12);
    const cap=points[points.length-1];
    this.ellipsoid(cap,[radius*.37,radius*.37,radius*.37],basis,1,8,6);
  }
  render(m){
    const renderStart=performance.now();
    this.vertices.length=0;
    const shoulder=[508,459,0];
    const angle=radians(m.shoulder);
    const upper=rotateZ([-29,152,0],angle);
    upper[2]=m.lift*14;
    const elbow=add(shoulder,upper);
    const fore=rotateZ([-20,148,0],angle+radians(m.bend+m.forearmSwing));
    fore[2]=m.lift*16;
    const wrist=add(elbow,fore);
    const u=unit(upper),f=unit(fore);
    const shoulderX=unit(cross(u,[0,0,1]));
    this.ellipsoid(add(shoulder,mul(u,3)),[33,22,29],[shoulderX,u,[0,0,1]],0);
    const reach=36+24*m.lift;
    const a=sub(elbow,mul(u,reach)),b=add(elbow,mul(f,reach));
    const points=[],radii=[];
    // The entire sleeve shares one smooth centerline and continuous cross-sections.
    const sleeveRings=this.gl?48:36;
    for(let i=0;i<=sleeveRings;i++){
      const t=i/sleeveRings;let p;
      if(t<.31)p=mix(shoulder,a,t/.31);
      else if(t<.69){const q=(t-.31)/.38;p=add(add(mul(a,(1-q)*(1-q)),mul(elbow,2*q*(1-q))),mul(b,q*q));}
      else p=mix(b,wrist,(t-.69)/.31);
      points.push(p);
      const radius=31-(t*4.5)+3*Math.exp(-Math.pow((t-.07)*8,2));
      const folds=1+Math.sin(t*47)*Math.exp(-Math.pow((t-.53)*12,2))*.018*m.lift;
      radii.push(radius*folds);
    }
    this.tube(points,radii,0,(t,lateral)=>{
      const cx=508-49*t,cy=463+290*t;
      return[(cx+lateral*(31-4*t))/1218,cy/1291];
    },20);
    const side=unit(cross(f,[0,0,1]));
    const front=unit(cross(side,f));
    const cuffEnd=add(wrist,mul(f,8));
    this.tube([sub(wrist,mul(f,2)),wrist,cuffEnd],[26.7,26.9,25.4],2,null,24);
    // Wrist follows the forearm with a small delay and rotates in depth.
    const wristAngle=radians(m.wrist);
    const handY=unit(add(mul(f,Math.cos(wristAngle)),mul(side,-Math.sin(wristAngle))));
    const handX=unit(cross(handY,front));
    const twist=radians(m.twist);
    const palmX=add(mul(handX,Math.cos(twist)),mul(front,Math.sin(twist)));
    const palmZ=add(mul(front,Math.cos(twist)),mul(handX,-Math.sin(twist)));
    const basis=[palmX,handY,palmZ];
    const palm=add(cuffEnd,mul(handY,26));
    // Broad palm, tapered wrist and thenar pad; fingers emerge from the palm.
    this.ellipsoid(add(cuffEnd,mul(handY,5)),[19,15,10],basis,1);
    this.ellipsoid(palm,[24,30,11.5],basis,1);
    const spreads=[-.19,-.07,.055,.18];
    const lengths=[35,48,45,34],xs=[-18,-6,7,19];
    for(let i=0;i<4;i++){
      const spread=spreads[i]*(.3+.7*m.fingers);
      const direction=unit(add(mul(handY,Math.cos(spread)),mul(palmX,Math.sin(spread))));
      const start=add(palm,add(mul(palmX,xs[i]),mul(handY,20-Math.abs(xs[i])*.15)));
      const curl=(1-m.fingers)*1.13 + .055 + .035*Math.sin(i*.8+m.flutter*.8);
      this.finger(start,direction,lengths[i],i===3?5.1:5.8,basis,curl);
    }
    const thumbStart=add(palm,add(mul(palmX,17),mul(handY,-9)));
    this.ellipsoid(thumbStart,[10,16,10],basis,1);
    const thumbDirection=unit(add(mul(palmX,.68+.16*m.fingers),mul(handY,.68-.1*m.fingers)));
    this.finger(thumbStart,thumbDirection,33,7,basis,.4-.2*m.fingers);
    if(!this.gl){this.renderSoftware();this.canvas.dataset.renderMs=(performance.now()-renderStart).toFixed(1);return;}
    const gl=this.gl;
    gl.viewport(0,0,this.canvas.width,this.canvas.height);
    gl.clear(gl.COLOR_BUFFER_BIT|gl.DEPTH_BUFFER_BIT);
    gl.useProgram(this.program);gl.bindBuffer(gl.ARRAY_BUFFER,this.buffer);
    gl.bufferData(gl.ARRAY_BUFFER,new Float32Array(this.vertices),gl.DYNAMIC_DRAW);
    gl.drawArrays(gl.TRIANGLES,0,this.vertices.length/9);
    this.canvas.dataset.renderMs=(performance.now()-renderStart).toFixed(1);
  }
  renderSoftware(){
    // Same 3D geometry and normals, projected with a painter's algorithm.
    // This supports browsers without a WebGL context; it is not a cutout rig.
    const ctx=this.ctx,vertices=this.vertices,triangles=[];
    const light=unit([-.52,-.65,1.1]);
    for(let i=0;i<vertices.length;i+=27){
      const nz=vertices[i+5]+vertices[i+14]+vertices[i+23];
      if(nz<-.15)continue;
      triangles.push([i,(vertices[i+2]+vertices[i+11]+vertices[i+20])/3]);
    }
    triangles.sort((a,b)=>a[1]-b[1]);
    ctx.setTransform(1,0,0,1,0,0);ctx.clearRect(0,0,920,1320);
    ctx.setTransform(2,0,0,2,-280,-520);
    const pixels=this.texturePixels;
    for(const [i] of triangles){
      const n=unit([vertices[i+3]+vertices[i+12]+vertices[i+21],vertices[i+4]+vertices[i+13]+vertices[i+22],vertices[i+5]+vertices[i+14]+vertices[i+23]]);
      const diffuse=Math.max(0,n[0]*light[0]+n[1]*light[1]+n[2]*light[2]);
      const material=vertices[i+8];let rgb;
      if(material<.5){
        const u=(vertices[i+6]+vertices[i+15]+vertices[i+24])/3;
        const v=(vertices[i+7]+vertices[i+16]+vertices[i+25])/3;
        const x=Math.round(clamp(u)* (pixels.width-1)),y=Math.round(clamp(v)*(pixels.height-1));
        const p=(y*pixels.width+x)*4;
        const color=pixels.data[p+3]>90?[pixels.data[p],pixels.data[p+1],pixels.data[p+2]]:[133,88,181];
        rgb=color.map(c=>c*(.77+.27*diffuse));
      }else if(material<1.5){rgb=[255,186,153].map(c=>c*(.76+.25*diffuse));}
      else if(material<2.5){rgb=[240,235,245].map(c=>c*(.72+.28*diffuse));}
      else{rgb=[242,176,148].map(c=>c*(.78+.22*diffuse));}
      ctx.fillStyle=`rgb(${rgb.map(c=>Math.round(clamp(c,0,255))).join(',')})`;
      const cx=(vertices[i]+vertices[i+9]+vertices[i+18])/3,cy=(vertices[i+1]+vertices[i+10]+vertices[i+19])/3;
      ctx.beginPath();
      for(let j=0;j<3;j++){
        const x=vertices[i+j*9],y=vertices[i+j*9+1],length=Math.hypot(x-cx,y-cy)||1;
        const px=x+(x-cx)/length*.28,py=y+(y-cy)/length*.28;
        if(!j)ctx.moveTo(px,py);else ctx.lineTo(px,py);
      }
      ctx.closePath();ctx.fill();
    }
  }
  dispose(){const gl=this.gl;if(!gl)return;gl.deleteBuffer(this.buffer);gl.deleteTexture(this.texture);gl.deleteProgram(this.program);}
}
