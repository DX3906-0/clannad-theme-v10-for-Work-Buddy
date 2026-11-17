# 生成 6 张主题预览图（模拟 WorkBuddy 真实界面布局）
# 真实几何（实测）：窗口 1508x856
#   立绘 280x826 @ (0,30)      → left 0, width 18.57%, top 3.5%, height 96.5%
#   玻璃层 1132x856 @ (328,0)  → left 21.75%, width 75.07%, height 100%
#   立绘图片 600x900，object-fit:cover + object-position:50% 0% → 放大裁两侧

import os, math, random
from PIL import Image, ImageDraw, ImageFont, ImageFilter

# 仓库根目录 = 本脚本所在 docs/ 的上一级，任何用户 clone 后都能直接跑
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WALL_DIR = os.path.join(ROOT, 'assets', 'wallpapers')
PORT_DIR = os.path.join(ROOT, 'assets', 'portraits')
OUT_DIR  = os.path.join(ROOT, 'docs', 'themes')

CW, CH = 720, 450          # 单卡尺寸（16:10，接近真实窗口比例）
SB_W   = int(CW * 0.1857)  # 侧栏宽（立绘宿主）
GL_L   = int(CW * 0.2175)  # 玻璃层左缘
GL_R   = int(CW * 0.9707)  # 玻璃层右缘

# 关键：key 必须与 clannad-theme-console.js 主题表的 key 一致
#   sakura = 樱花坡道（壁纸 sakura-petals.jpg，立绘 sakura-petals.png）
#   fuko   = 伊吹风子（壁纸 fuko-wp.jpg   = 主题表 wp 字段独有的新图，
#            立绘 fuko.png；旧图 assets/wallpapers/fuko.jpg 已废弃）
THEMES = [
    # key, 壁纸文件, 立绘文件, 角色名, 粒子, 主色
    ('nagisa', 'nagisa.jpg',        'nagisa.png',        '古河渚',   'petal', '#e8849c'),
    ('kyou',   'kyou.jpg',          'kyou.png',          '藤林杏',   'rain',  '#6fa8d0'),
    ('ryou',   'ryou.jpg',          'ryou.png',          '藤林椋',   'orb',   '#d9c96b'),
    ('tomoyo', 'tomoyo.jpg',        'tomoyo.png',        '坂上智代', 'snow',  '#7fb8d4'),
    ('fuko',   'fuko-wp.jpg',       'fuko.png',          '伊吹风子', 'light', '#e89ba8'),
    ('sakura', 'sakura-petals.jpg', 'sakura-petals.png', '樱花坡道', 'petal', '#f0a8c0'),
]


def cover(im, w, h, pos_y=0.0):
    """object-fit: cover，pos_y 控制纵向对齐（0=顶部）"""
    iw, ih = im.size
    scale = max(w / iw, h / ih)
    nw, nh = max(1, int(iw * scale + .5)), max(1, int(ih * scale + .5))
    im2 = im.resize((nw, nh), Image.LANCZOS)
    ox = (nw - w) // 2
    oy = int((nh - h) * pos_y)
    return im2.crop((ox, oy, ox + w, oy + h))


def draw_particles(draw, kind, w, h, seed=7):
    """在卡片上画粒子（模拟 #wbx-fx 层）"""
    rnd = random.Random(seed)
    if kind == 'petal':
        for _ in range(26):
            x, y = rnd.uniform(0, w), rnd.uniform(0, h)
            s = rnd.uniform(3.5, 7)
            a = rnd.randint(110, 200)
            # 椭圆花瓣，带旋转感用小圆点簇近似
            draw.ellipse([x, y, x + s * 1.5, y + s], fill=(255, 160, 190, a))
    elif kind == 'rain':
        for _ in range(70):
            x, y = rnd.uniform(0, w), rnd.uniform(0, h)
            ln = rnd.uniform(12, 26)
            a = rnd.randint(90, 170)
            draw.line([(x, y), (x - 2, y + ln)], fill=(200, 225, 255, a), width=1)
    elif kind == 'snow':
        for _ in range(55):
            x, y = rnd.uniform(0, w), rnd.uniform(0, h)
            r = rnd.uniform(1.8, 4.2)
            a = rnd.randint(120, 220)
            draw.ellipse([x, y, x + r * 2, y + r * 2], fill=(255, 255, 255, a))
    elif kind == 'orb':
        for _ in range(22):
            x, y = rnd.uniform(0, w), rnd.uniform(0, h)
            r = rnd.uniform(2.5, 6)
            a = rnd.randint(90, 170)
            draw.ellipse([x, y, x + r * 2, y + r * 2], fill=(255, 240, 170, a))
    elif kind == 'light':
        for _ in range(16):
            x, y = rnd.uniform(0, w), rnd.uniform(0, h)
            r = rnd.uniform(4, 10)
            for k in range(3):   # 光玉做成同心光晕
                rr = r * (1 + k * 0.8)
                aa = int(60 / (k + 1))
                draw.ellipse([x - rr, y - rr, x + rr, y + rr],
                             fill=(255, 235, 180, aa))


def make_card(key, wall_file, port_file, name, particle, accent):
    # 1) 壁纸 cover 铺满
    wall = Image.open(os.path.join(WALL_DIR, wall_file)).convert('RGB')
    card = cover(wall, CW, CH, 0.5)

    # 2) 中间阅读列磨砂：裁出 → 高斯模糊 → 叠白纱 → 贴回
    # ⚠️ 模糊半径要克制：真实 #wbx-glass 用的是"预模糊壁纸 + 白纱"，
    # 半径过大会把整幅壁纸糊成色块（用户评价"看不清是什么"）。
    # 卡片只有 720px 宽（真实窗口 1508px 的一半），半径按比例取 7 更接近观感。
    region = card.crop((GL_L, 0, GL_R, CH))
    blurred = region.filter(ImageFilter.GaussianBlur(7))
    veil = Image.new('RGBA', blurred.size, (255, 255, 255, 78))
    frosted = Image.alpha_composite(blurred.convert('RGBA'), veil).convert('RGB')
    card.paste(frosted, (GL_L, 0))

    # 3) 顶栏（浅色半透明条）—— 用 paste + 遮罩，避免 alpha_composite 尺寸必须一致
    card = card.convert('RGBA')
    bar_h = int(CH * 0.072)
    top = Image.new('RGBA', (CW, CH), (0, 0, 0, 0))
    ImageDraw.Draw(top).rectangle([0, 0, CW, bar_h], fill=(255, 255, 255, 120))
    card = Image.alpha_composite(card, top)

    # 4) 侧栏立绘：cover 到 (SB_W, CH)，顶部对齐——与真实 object-fit 一致
    port = Image.open(os.path.join(PORT_DIR, port_file)).convert('RGBA')
    port_fit = cover(port, SB_W, int(CH * 0.965), 0.0)
    card.paste(port_fit, (0, int(CH * 0.035)), port_fit)

    # 5) 粒子层
    fx = Image.new('RGBA', (CW, CH), (0, 0, 0, 0))
    draw_particles(ImageDraw.Draw(fx), particle, CW, CH, seed=hash(key) % 1000)
    card = Image.alpha_composite(card.convert('RGBA'), fx).convert('RGB')

    # 6) 角色名徽标（左下角，压在侧栏上）
    badge = Image.new('RGBA', (SB_W - 16, 46), (0, 0, 0, 0))
    d = ImageDraw.Draw(badge)
    d.rounded_rectangle([0, 0, badge.width - 1, badge.height - 1], 10,
                        fill=(255, 255, 255, 210))
    try:
        f = ImageFont.truetype('msyh.ttc', 21)
    except Exception:
        f = ImageFont.load_default()
    bb = d.textbbox((0, 0), name, font=f)
    d.text(((badge.width - (bb[2] - bb[0])) // 2, (badge.height - (bb[3] - bb[1])) // 2 - 2),
           name, fill=accent, font=f)
    card.paste(badge, (8, CH - 58), badge)

    # 7) 描边 + 圆角遮罩
    out = card.convert('RGBA')
    mask = Image.new('L', (CW, CH), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, CW - 1, CH - 1], 16, fill=255)
    out.putalpha(mask)
    d2 = ImageDraw.Draw(out)
    d2.rounded_rectangle([0, 0, CW - 1, CH - 1], 16, outline=accent + 'ff', width=0)  # 另存时再加
    return out


os.makedirs(OUT_DIR, exist_ok=True)
for key, wf, pf, name, pt, accent in THEMES:
    img = make_card(key, wf, pf, name, pt, accent)
    # 存 JPEG 而非 PNG：卡片是照片类内容，PNG 存同样的图要 300+KB，
    # JPEG q88 只要 40~55KB（-87%），肉眼看不出差别
    p = os.path.join(OUT_DIR, f'{key}.jpg')
    img.convert('RGB').save(p, 'JPEG', quality=88, optimize=True, progressive=True)
    print('%-8s %-7s -> %s  (%d KB)' % (key, name, os.path.basename(p), os.path.getsize(p) // 1024))
