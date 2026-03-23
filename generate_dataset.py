"""
EMFOX OMS — Generador de Dataset de Entrenamiento
===================================================
Genera imágenes sintéticas de bodega Yiwu con múltiples productos
y sus bounding boxes en formato YOLO para entrenar una red neuronal.

Uso:
    python3 generate_dataset.py --count 200 --output ./dataset

Requiere: pip install pillow (ya instalado)
No requiere: torch, CUDA, ni nada pesado

Genera:
    dataset/
    ├── images/
    │   ├── train/  (160 imágenes)
    │   └── val/    (40 imágenes)
    ├── labels/
    │   ├── train/  (160 .txt con bboxes YOLO)
    │   └── val/    (40 .txt)
    └── dataset.yaml  (config para YOLOv8)
"""

import random
import argparse
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageEnhance
import json
import math

# ─── COLORES Y TEXTURAS DE PRODUCTOS ──────────────────────────────────────────
PRODUCT_COLORS = [
    # Peluches / toys
    [(255, 182, 193), (255, 218, 224), (255, 240, 245)],  # rosa
    [(139, 90, 43),   (160, 110, 60),  (180, 130, 80)],   # marrón
    [(255, 255, 200), (255, 255, 150), (255, 255, 100)],  # amarillo
    [(173, 216, 230), (135, 206, 235), (100, 180, 210)],  # azul
    [(144, 238, 144), (100, 200, 100), (60, 160, 60)],    # verde
    [(255, 160, 122), (255, 120, 80),  (220, 80, 50)],    # naranja
    [(200, 162, 200), (180, 140, 180), (160, 100, 160)],  # lila
    [(255, 255, 255), (240, 240, 240), (220, 220, 220)],  # blanco
]

BACKGROUND_COLORS = [
    (245, 245, 240),  # blanco sucio (piso bodega)
    (230, 220, 210),  # beige suave
    (200, 200, 200),  # gris claro
    (240, 235, 225),  # crema
    (210, 210, 200),  # gris frío
]

PRODUCT_TYPES = [
    "Peluche", "Muñeca", "Juguete", "Decoracion",
    "Accesorio", "Bolso", "Ropa", "Electronico"
]


def random_color(palette):
    base = random.choice(palette)
    noise = [random.randint(-15, 15) for _ in range(3)]
    return tuple(max(0, min(255, base[i] + noise[i])) for i in range(3))


def draw_product(draw, x, y, w, h, color_palette, shape="rect"):
    """Draw a synthetic product shape."""
    c = random_color(color_palette)
    c_dark = tuple(max(0, v - 40) for v in c)

    if shape == "rect":
        draw.rectangle([x, y, x+w, y+h], fill=c, outline=c_dark, width=2)
        # Inner detail
        pad = w // 8
        if w > 40 and h > 40:
            inner_x0 = x + pad
            inner_y0 = y + pad
            inner_x1 = x + w - pad
            inner_y1 = y + h - pad
            if inner_x1 > inner_x0 and inner_y1 > inner_y0:
                draw.rectangle([inner_x0, inner_y0, inner_x1, inner_y1],
                             fill=random_color(color_palette), outline=c_dark, width=1)

    elif shape == "rounded":
        r = min(w, h) // 5
        draw.rounded_rectangle([x, y, x+w, y+h], radius=r, fill=c, outline=c_dark, width=2)
        # Eyes for peluche
        if w > 60:
            ey = y + h // 3
            ex1, ex2 = x + w // 3, x + 2 * w // 3
            er = max(3, w // 15)
            draw.ellipse([ex1-er, ey-er, ex1+er, ey+er], fill=(30, 30, 30))
            draw.ellipse([ex2-er, ey-er, ex2+er, ey+er], fill=(30, 30, 30))
            # Nose
            nx, ny = x + w // 2, y + h // 2
            nr = max(2, w // 20)
            draw.ellipse([nx-nr, ny-nr, nx+nr, ny+nr], fill=(80, 30, 30))

    elif shape == "circle":
        draw.ellipse([x, y, x+w, y+h], fill=c, outline=c_dark, width=2)

    elif shape == "bag":
        # Handle
        hx = x + w // 2
        draw.arc([hx - w//4, y - h//6, hx + w//4, y + h//5], 0, 180, fill=c_dark, width=3)
        # Body
        draw.rectangle([x, y + h//6, x+w, y+h], fill=c, outline=c_dark, width=2)
        # Zipper line
        draw.line([x + w//6, y + h//4, x + 5*w//6, y + h//4], fill=c_dark, width=2)


def add_handwritten_data(draw, x, y, w, h, price_cny, qty, cbm):
    """Add handwritten-style product data next to the product."""
    # Position: to the left or right of product
    text_x = max(5, x - 120) if x > 130 else x + w + 10
    text_y = y + h // 4

    lines = [
        f"{price_cny}元",
        f"{qty} UND",
        f"{cbm:.2f}m³",
    ]

    # Simple pixel font simulation (manual drawing)
    for i, line in enumerate(lines):
        ty = text_y + i * 22
        # Shadow for handwritten feel
        draw.text((text_x + 1, ty + 1), line, fill=(180, 180, 180))
        draw.text((text_x, ty), line, fill=(20, 20, 80))


def generate_image(img_w=1200, img_h=1600, n_products=None):
    """Generate one synthetic warehouse photo with multiple products."""
    if n_products is None:
        n_products = random.randint(2, 5)

    # Background
    bg_color = random.choice(BACKGROUND_COLORS)
    img = Image.new("RGB", (img_w, img_h), bg_color)
    draw = ImageDraw.Draw(img)

    # Subtle floor texture
    for _ in range(300):
        gx = random.randint(0, img_w)
        gy = random.randint(0, img_h)
        gl = random.randint(200, 230)
        draw.point((gx, gy), fill=(gl, gl, gl))

    bboxes = []  # YOLO format: [class_id, cx, cy, w, h] normalized

    # Divide image vertically for portrait photos (most common in Yiwu)
    section_h = img_h // n_products
    shapes = ["rect", "rounded", "circle", "bag", "rect"]
    color_palettes = random.sample(PRODUCT_COLORS, min(n_products, len(PRODUCT_COLORS)))

    for i in range(n_products):
        palette = color_palettes[i % len(color_palettes)]
        shape = shapes[i % len(shapes)]

        # Product zone
        zone_y = i * section_h
        zone_h = section_h

        # Product dimensions (60-80% of zone, centered, with offset)
        pw = int(img_w * random.uniform(0.35, 0.65))
        ph = int(zone_h * random.uniform(0.50, 0.75))
        px = random.randint(int(img_w * 0.15), int(img_w * 0.45))
        py = zone_y + random.randint(int(zone_h * 0.1), int(zone_h * 0.2))

        # Clamp
        px = max(0, min(img_w - pw - 1, px))
        py = max(0, min(img_h - ph - 1, py))

        # Draw product
        draw_product(draw, px, py, pw, ph, palette, shape)

        # Add handwritten data
        price = round(random.uniform(3.5, 35.0), 1)
        qty = random.choice([120, 240, 360, 480, 600, 720, 1200, 2400])
        cbm = round(random.uniform(0.2, 1.2), 2)
        add_handwritten_data(draw, px, py, pw, ph, price, qty, cbm)

        # Optional: scatter a few more items of the same product
        n_extra = random.randint(0, 3)
        for _ in range(n_extra):
            ex = px + random.randint(-80, 80)
            ey = py + random.randint(-30, 30)
            ew = int(pw * random.uniform(0.6, 0.9))
            eh = int(ph * random.uniform(0.6, 0.9))
            ex = max(0, min(img_w - ew - 1, ex))
            ey = max(0, min(img_h - eh - 1, ey))
            draw_product(draw, ex, ey, ew, eh, palette, shape)

        # YOLO bbox (normalized center x, center y, width, height)
        cx = (px + pw / 2) / img_w
        cy = (py + ph / 2) / img_h
        nw = pw / img_w
        nh = ph / img_h
        bboxes.append((0, cx, cy, nw, nh))  # class 0 = product

    # Post-processing: slight blur + noise for realism
    img = img.filter(ImageFilter.GaussianBlur(radius=0.5))
    enhancer = ImageEnhance.Brightness(img)
    img = enhancer.enhance(random.uniform(0.85, 1.15))

    return img, bboxes


def generate_dataset(count=200, output_dir="./dataset"):
    out = Path(output_dir)
    for split in ["train", "val"]:
        (out / "images" / split).mkdir(parents=True, exist_ok=True)
        (out / "labels" / split).mkdir(parents=True, exist_ok=True)

    val_count = max(1, count // 5)
    train_count = count - val_count

    print(f"Generando {train_count} imágenes de entrenamiento + {val_count} de validación...")

    for i in range(count):
        split = "train" if i < train_count else "val"
        idx = i if i < train_count else i - train_count

        n_products = random.randint(2, 5)
        img, bboxes = generate_image(
            img_w=random.choice([1200, 1536, 960]),
            img_h=random.choice([1600, 2048, 1200]),
            n_products=n_products,
        )

        img_path = out / "images" / split / f"yiwu_{idx:04d}.jpg"
        lbl_path = out / "labels" / split / f"yiwu_{idx:04d}.txt"

        img.save(str(img_path), "JPEG", quality=88)

        with open(lbl_path, "w") as f:
            for cls, cx, cy, w, h in bboxes:
                f.write(f"{cls} {cx:.6f} {cy:.6f} {w:.6f} {h:.6f}\n")

        if (i + 1) % 20 == 0:
            print(f"  {i+1}/{count} generadas...")

    # YOLO dataset.yaml
    yaml_content = f"""path: {out.resolve()}
train: images/train
val: images/val

nc: 1
names: ['product']

# Generated by EMFOX OMS — Fox Comercial Group
# {count} synthetic warehouse images (Yiwu style)
"""
    (out / "dataset.yaml").write_text(yaml_content)

    # Summary
    summary = {
        "total": count,
        "train": train_count,
        "val": val_count,
        "classes": ["product"],
        "format": "YOLO v8",
        "ready_to_train": True,
        "train_command": "yolo detect train data=dataset/dataset.yaml model=yolov8n.pt epochs=50 imgsz=640"
    }
    (out / "summary.json").write_text(json.dumps(summary, indent=2))

    print(f"\n✅ Dataset listo en {out.resolve()}")
    print(f"   Train: {train_count} imágenes")
    print(f"   Val:   {val_count} imágenes")
    print(f"\n🚀 Para entrenar YOLOv8-nano (cuando lo instales):")
    print(f"   yolo detect train data={out.resolve()}/dataset.yaml model=yolov8n.pt epochs=50 imgsz=640")
    print(f"\n📦 O con ultralytics en Python:")
    print(f"   from ultralytics import YOLO")
    print(f"   model = YOLO('yolov8n.pt')")
    print(f"   model.train(data='{out.resolve()}/dataset.yaml', epochs=50, imgsz=640)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Genera dataset sintético para EMFOX OMS")
    parser.add_argument("--count", type=int, default=200, help="Número de imágenes a generar")
    parser.add_argument("--output", type=str, default="./dataset", help="Directorio de salida")
    args = parser.parse_args()
    generate_dataset(args.count, args.output)
