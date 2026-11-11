# -*- coding: utf-8 -*-
"""按运行时实测几何生成主题预览画廊。
   窗口 1508x856 基准：
   - 立绘 280x826 @ (0,30)  → 宽 18.57%、高 96.5%
   - 玻璃层 1132x856 @ (328,0) → left 21.75%、宽 75.07%、高 100%
   - 壁纸铺满整窗
"""
import os, base64, json

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 主题 → 仓库内素材文件名（与运行时实际使用的完全一致）
ASSETS = {
    'nagisa': ('nagisa.jpg',        'nagisa.png'),
    'kyou':   ('kyou.jpg',          'kyou.png'),
    'ryou':   ('ryou.jpg',          'ryou.png'),
    'fuko':   ('fuko-wp.png',       'fuko.png'),
    'tomoyo': ('tomoyo.jpg',        'tomoyo.png'),
    'sakura': ('sakura-petals.jpg', 'sakura-petals.png'),
}

THEMES = [
    ('nagisa', '古河渚',   'petal', '#d96a92'),
    ('kyou',   '藤林杏',   'rain',  '#9a6ab8'),
    ('ryou',   '藤林椋',   'orb',   '#6a8ac8'),
    ('fuko',   '伊吹风子', 'orb',   '#4a9a6a'),
    ('tomoyo', '坂上智代', 'snow',  '#668fb5'),
    ('sakura', '樱花坡道', 'petal', '#d96a92'),
]
PLABEL = {'petal': '花瓣飘落 🌸', 'rain': '雨滴 ☔', 'orb': '光玉 ☀', 'snow': '雪花 ❄️'}


def datauri(path):
    with open(path, 'rb') as f:
        raw = f.read()
    ext = 'png' if path.lower().endswith('.png') else 'jpeg'
    return 'data:image/%s;base64,%s' % (ext, base64.b64encode(raw).decode())


def find(key, kind):
    """kind: 'wall' | 'portrait'"""
    idx = 0 if kind == 'wall' else 1
    folder = os.path.join(ROOT, 'assets', 'wallpapers' if kind == 'wall' else 'portraits')
    name = ASSETS[key][idx]
    p = os.path.join(folder, name)
    if not os.path.exists(p):
        raise FileNotFoundError('%s -> %s' % (key, p))
    return p


cards = []
total_kb = 0
for key, label, particle, accent in THEMES:
    wp = find(key, 'wall')
    po = find(key, 'portrait')
    ws_uri = datauri(wp)
    po_uri = datauri(po)
    total_kb += (os.path.getsize(wp) + os.path.getsize(po)) // 1024
    cards.append(
        '  <figure class="card" data-particle="{p}" data-accent="{a}">\n'
        '    <div class="stage">\n'
        '      <img class="wallpaper" src="{w}" alt="{l}">\n'
        '      <div class="glass"></div>\n'
        '      <img class="portrait" src="{po}" alt="">\n'
        '      <canvas class="fx"></canvas>\n'
        '    </div>\n'
        '    <figcaption><strong>{l}</strong><span>{pl}</span></figcaption>\n'
        '  </figure>'.format(p=particle, a=accent, w=ws_uri, po=po_uri,
                            l=label, pl=PLABEL[particle]))
    print('  %-8s %-24s %6d KB + %6d KB' % (key, os.path.basename(wp),
          os.path.getsize(wp) // 1024, os.path.getsize(po) // 1024))

html = '''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Clannad Theme — 主题预览</title>
<style>
  :root{--accent:#d96a92}
  *{box-sizing:border-box;margin:0;padding:0}
  body{
    font-family:"PingFang SC","Microsoft YaHei",system-ui,sans-serif;
    background:#f4f1f3;color:#3a2a34;min-height:100vh;
    display:flex;flex-direction:column;align-items:center;
  }
  header{padding:32px 20px 4px;text-align:center}
  header h1{font-size:1.4rem;letter-spacing:.08em;font-weight:600}
  header p{color:#9a8794;font-size:.83rem;margin-top:5px}

  .viewer{width:min(900px,95vw);margin:20px auto 0}
  .viewport{position:relative;overflow:hidden;border-radius:12px;
    box-shadow:0 16px 44px -20px rgba(70,40,60,.45);background:#e9e2e7}
  .slides{display:flex;transition:transform .45s cubic-bezier(.4,0,.2,1)}
  .card{flex:0 0 100%;position:relative}

  /* 真实窗口比例 1508 x 856 */
  .stage{position:relative;aspect-ratio:1508/856;overflow:hidden;background:#e9e2e7}

  /* 1) 壁纸：铺满整窗 */
  .wallpaper{position:absolute;inset:0;width:100%;height:100%;object-fit:cover;display:block}

  /* 2) 磨砂玻璃层：实测 1132x856 @ (328,0)
         left = 328/1508 = 21.75%，width = 1132/1508 = 75.07%，top 0，高 100% */
  .glass{position:absolute;left:21.75%;top:0;width:75.07%;height:100%;
    background:rgba(255,255,255,.42);
    backdrop-filter:blur(14px) saturate(1.1);
    -webkit-backdrop-filter:blur(14px) saturate(1.1);
    -webkit-mask-image:linear-gradient(to right,transparent 0,#000 30px,#000 calc(100% - 30px),transparent 100%),
      linear-gradient(to bottom,transparent 0,#000 24px,#000 calc(100% - 24px),transparent 100%);
    -webkit-mask-composite:source-in;
    mask-image:linear-gradient(to right,transparent 0,#000 30px,#000 calc(100% - 30px),transparent 100%),
      linear-gradient(to bottom,transparent 0,#000 24px,#000 calc(100% - 24px),transparent 100%);
    mask-composite:intersect}

  /* 3) 立绘：实测 280x826 @ (0,30)
         left 0、宽 280/1508 = 18.57%、top 30/856 = 3.5%、高 826/856 = 96.5%
         object-fit:contain + 底部对齐，保持原始比例不拉伸 */
  .portrait{position:absolute;left:0;top:3.5%;width:18.57%;height:96.5%;
    object-fit:contain;object-position:center bottom;
    filter:drop-shadow(0 4px 10px rgba(40,20,40,.25))}

  canvas.fx{position:absolute;inset:0;z-index:5;pointer-events:none}

  figcaption{position:absolute;left:0;right:0;bottom:0;z-index:6;
    display:flex;justify-content:space-between;align-items:baseline;
    padding:12px 18px;background:linear-gradient(transparent,rgba(0,0,0,.5))}
  figcaption strong{color:#fff;font-size:1.05rem;letter-spacing:.12em;
    text-shadow:0 1px 8px rgba(0,0,0,.65)}
  figcaption span{color:rgba(255,255,255,.9);font-size:.74rem}

  nav{display:flex;align-items:center;justify-content:center;gap:18px;margin-top:15px}
  nav button{width:38px;height:38px;border-radius:50%;border:1px solid #e3d8de;
    background:#fff;color:#7a6472;font-size:.95rem;cursor:pointer;
    transition:transform .15s,box-shadow .15s;line-height:1}
  nav button:hover{transform:scale(1.1);box-shadow:0 4px 14px -4px rgba(120,80,100,.4)}
  .dots{display:flex;gap:8px}
  .dots b{width:8px;height:8px;border-radius:50%;background:#ded2d9;cursor:pointer;
    transition:transform .2s,background .2s}
  .dots b.on{background:var(--accent);transform:scale(1.4)}

  .strip{display:flex;gap:9px;flex-wrap:wrap;justify-content:center;
    margin:24px auto 44px;width:min(900px,95vw)}
  .thumb{width:100px;border:0;background:none;cursor:pointer;text-align:center;padding:5px;
    border-radius:9px;transition:background .2s}
  .thumb:hover{background:rgba(255,255,255,.9)}
  .thumb.on{background:#fff;box-shadow:0 5px 16px -8px rgba(120,80,100,.4)}
  .thumb .mini{width:100px;height:57px;border-radius:5px;background-size:cover;
    background-position:center;box-shadow:inset 0 0 0 1px rgba(0,0,0,.06)}
  .thumb span{display:block;margin-top:5px;font-size:.7rem;color:#8a7482}
  .thumb.on span{color:var(--accent);font-weight:600}
</style>
</head>
<body>
<header>
  <h1>Clannad Theme</h1>
  <p>六个角色主题 · 壁纸 / 磨砂玻璃 / 角色立绘 / 粒子动效</p>
</header>

<div class="viewer">
  <div class="viewport">
    <div class="slides" id="slides">
__CARDS__
    </div>
  </div>
  <nav>
    <button id="prev" title="上一个">←</button>
    <div class="dots" id="dots"></div>
    <button id="next" title="下一个">→</button>
  </nav>
</div>

<div class="strip" id="strip"></div>

<script>
var cards=[].slice.call(document.querySelectorAll('.card'));
var labels=[].slice.call(document.querySelectorAll('figcaption strong')).map(function(e){return e.textContent});
var idx=0;
var slides=document.getElementById('slides'),dots=document.getElementById('dots'),strip=document.getElementById('strip');

cards.forEach(function(c,i){
  var b=document.createElement('b');b.onclick=function(){go(i)};dots.appendChild(b);
  var t=document.createElement('button');t.className='thumb';
  var mini=document.createElement('div');mini.className='mini';
  mini.style.backgroundImage='url('+c.querySelector('.wallpaper').src+')';
  var cap=document.createElement('span');cap.textContent=labels[i];
  t.appendChild(mini);t.appendChild(cap);
  t.onclick=function(){go(i)};strip.appendChild(t);
});

function go(n){
  idx=(n+cards.length)%cards.length;
  slides.style.transform='translateX(-'+idx*100+'%)';
  document.documentElement.style.setProperty('--accent',cards[idx].getAttribute('data-accent'));
  [].slice.call(dots.children).forEach(function(d,i){d.classList.toggle('on',i===idx)});
  [].slice.call(strip.children).forEach(function(d,i){d.classList.toggle('on',i===idx)});
  cards.forEach(function(c,i){running[c.getAttribute('data-particle')]=(i===idx)});
}
document.getElementById('prev').onclick=function(){go(idx-1)};
document.getElementById('next').onclick=function(){go(idx+1)};
addEventListener('keydown',function(e){if(e.key==='ArrowLeft')go(idx-1);if(e.key==='ArrowRight')go(idx+1)});
var x0=null;
addEventListener('touchstart',function(e){x0=e.touches[0].clientX});
addEventListener('touchend',function(e){if(x0===null)return;var d=e.changedTouches[0].clientX-x0;
  if(Math.abs(d)>40)go(idx+(d<0?1:-1));x0=null});

var running={};
var cvs=[].slice.call(document.querySelectorAll('canvas.fx')).map(function(c,i){
  return {c:c,ctx:c.getContext('2d'),kind:cards[i].getAttribute('data-particle')};
});
var T=0;
function resize(){
  cvs.forEach(function(o){
    var r=o.c.parentElement.getBoundingClientRect();
    o.c.width=r.width;o.c.height=r.height;
  });
}
addEventListener('resize',resize);resize();

var CONF={};
function build(kind,n){
  var o={n:n,speeds:[],seedX:[],seedY:[],sizes:[],alphas:[]};
  for(var i=0;i<n;i++){
    o.speeds.push(40+Math.random()*70);
    o.seedX.push(Math.random());o.seedY.push(Math.random());
    o.sizes.push(kind==='orb'?2+Math.random()*4:2+Math.random()*2.5);
    o.alphas.push(.35+Math.random()*.45);
  }
  CONF[kind]=o;
}
build('petal',26);build('rain',70);build('snow',60);build('orb',18);

function draw(ctx,kind,w,h,t){
  var P=CONF[kind];if(!P)return;
  for(var i=0;i<P.n;i++){
    var px=(P.speeds[i]*t+w*((P.seedX[i]+1)*.5))%w;
    var py=(P.speeds[i]*t*.7+h*((P.seedY[i]+1)*.5))%h;
    var s=P.sizes[i],a=P.alphas[i];
    if(kind==='petal'){
      ctx.save();ctx.translate(px,py);ctx.rotate(t*2+i);
      ctx.fillStyle='rgba(255,'+(150+(i*37%60))+','+(190+(i*53%40))+','+a+')';
      ctx.beginPath();ctx.ellipse(0,0,s*1.5,s,0,0,7);ctx.fill();ctx.restore();
    }else if(kind==='rain'){
      ctx.strokeStyle='rgba(210,225,255,'+a+')';ctx.lineWidth=1.2;
      ctx.beginPath();ctx.moveTo(px,py);ctx.lineTo(px-3,py+s*3);ctx.stroke();
    }else if(kind==='snow'){
      ctx.fillStyle='rgba(255,255,255,'+a+')';
      ctx.beginPath();ctx.arc(px,py,s,0,7);ctx.fill();
    }else{
      var g=ctx.createRadialGradient(px,py,0,px,py,s*3);
      g.addColorStop(0,'rgba(255,242,190,'+(a*1.1)+')');
      g.addColorStop(1,'rgba(255,200,120,0)');
      ctx.fillStyle=g;ctx.beginPath();ctx.arc(px,py,s*3,0,7);ctx.fill();
    }
  }
}

(function loop(){
  T+=1/60;
  cvs.forEach(function(o){
    o.ctx.clearRect(0,0,o.c.width,o.c.height);
    if(running[o.kind]!==false) draw(o.ctx,o.kind,o.c.width,o.c.height,T);
  });
  requestAnimationFrame(loop);
})();

go(0);
</script>
</body>
</html>'''

html = html.replace('__CARDS__', '\n'.join(cards))
out = os.path.join(ROOT, 'docs', 'gallery.html')
open(out, 'w', encoding='utf-8').write(html)
print('\n✅ 已写 %s (%.2f MB)' % (out, os.path.getsize(out) / 1024 / 1024))
