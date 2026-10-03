"""Build notebooks/train_panoramic_colab.ipynb (self-contained: embeds the training / conversion scripts).

Run from backend/:  python scripts/build_panoramic_notebook.py
"""
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "..", "..", "notebooks", "train_panoramic_colab.ipynb")
EMBED = ("train_panoramic_boneloss.py", "convert_aku_labelme.py", "convert_pdcnn_coco.py")


def md(text):
    return {"cell_type": "markdown", "metadata": {}, "source": text.strip("\n").splitlines(keepends=True)}


def code(text):
    return {"cell_type": "code", "metadata": {}, "execution_count": None, "outputs": [],
            "source": text.strip("\n").splitlines(keepends=True)}


cells = [md("""
# PerioVision AI: train the PANORAMIC models on a free Colab GPU

**How to use:** `Runtime` → `Change runtime type` → **T4 GPU** (or better) → Save, then `Runtime` → **Run all**
and allow Google Drive. Everything is downloaded from the public sources by the notebook itself.
If Colab disconnects, just **Run all** again: finished steps are skipped and training resumes from Drive.

| Model | Data (downloaded automatically) | Tested on |
|---|---|---|
| A. Bone-loss screen per jaw (yes / no) | [ToothXpert MM-OPG](https://huggingface.co/datasets/jeffrey423/ToothXpert.MM-OPG-Annotations), ~9,200 films | its official 450-film test split |
| B. Worst-tooth bone loss % + stage | [BRAR](https://doi.org/10.6084/m9.figshare.30155974), 988 films (fine-tuned from A) | held-out 15 % of BRAR |
| C. Per-tooth bone-loss detector | [PDCNN](https://github.com/PuckBlink/PDCNN), 1,747 films | held-out 10 % of PDCNN |
| D. Tooth detector fine-tune (FDI) | [Aga Khan OPG](https://zenodo.org/records/10538750), 152 films | held-out 15 %; kept only if better than the current detector |

**Before running D:** upload the current detector `backend/weights/dental_yolov8n.pt` to `MyDrive/PerioVision/current/`.
Without it, step D is skipped.

At the end, download `MyDrive/PerioVision/export_panoramic/` and give it to Claude: every model comes with
its held-out test metrics, and the app only switches a model on if those metrics pass.
"""),
         code("""
# 0. Settings (defaults chosen for a free T4 GPU)
# Which models to train in this session. Finished models are skipped anyway, so a short session can do one at a time.
RUN = {"A": True, "B": True, "C": True, "D": False}   # D (tooth-detector fine-tune) can also be trained on a CPU
ARCH        = "convnext_tiny"   # backbone for A and B: resnet18 | resnet50 | efficientnet_b3 | convnext_tiny
SIZE        = (1024, 512)       # panoramic film resized to W x H for A and B
EPOCHS_A, EPOCHS_B = 12, 30
BATCH_A, BATCH_B   = 16, 16
# C: per-tooth bone-loss detector. "yolo11s" at 1024 fits one free session (~1-1.5 h on a T4);
# with more GPU time use "yolo11m.pt", 1280, 150 for the most accuracy.
YOLO_C, IMGSZ_C, EPOCHS_C, PATIENCE_C = "yolo11s.pt", 1024, 60, 15
IMGSZ_D, EPOCHS_D = 1280, 40
"""),
         code("""
# 1. GPU + Google Drive
import subprocess, os, glob, json, shutil
print(subprocess.run(["nvidia-smi"], capture_output=True, text=True).stdout or "NO GPU: Runtime > Change runtime type > T4 GPU")
from google.colab import drive
drive.mount("/content/drive")
ROOT = "/content/drive/MyDrive/PerioVision"
EXPORT = f"{ROOT}/export_panoramic"
for d in ("runs", "current", "export_panoramic"):
    os.makedirs(f"{ROOT}/{d}", exist_ok=True)
"""),
         code("""
# 2. Same Ultralytics version as the PerioVision backend, plus the Google-Drive downloader
!pip -q install "ultralytics==8.4.21" gdown
import ultralytics; ultralytics.checks()
""")]

for name in EMBED:
    src = open(os.path.join(HERE, name), encoding="utf-8").read()
    cells.append(code(f"%%writefile /content/{name}\n{src}"))

cells += [code("""
# 3. Download the four datasets (skipped if already present)
import urllib.request, zipfile
D = "/content/data"; os.makedirs(D, exist_ok=True)
def fetch(url, path):
    if not os.path.exists(path):
        print("downloading", url); urllib.request.urlretrieve(url, path)
    return path

need_A = RUN["A"] and not os.path.exists(f"{EXPORT}/panoramic_screen_metrics.json")
need_B = RUN["B"] and not os.path.exists(f"{EXPORT}/panoramic_severity_metrics.json")
need_C = RUN["C"] and not os.path.exists(f"{EXPORT}/pdcnn_boneloss_metrics.json")
need_D = RUN["D"] and not os.path.exists(f"{EXPORT}/aku_detector_finetune_metrics.json")
print("still to train:", [k for k, v in (("A", need_A), ("B", need_B), ("C", need_C), ("D", need_D)) if v])

# MM-OPG (Hugging Face, Apache-2.0) - only needed for A
if need_A:
    os.makedirs(f"{D}/mmopg", exist_ok=True)
    HF = "https://huggingface.co/datasets/jeffrey423/ToothXpert.MM-OPG-Annotations/resolve/main"
    fetch(f"{HF}/MM-OPG-Train-Raw.json", f"{D}/mmopg/mmopg_train.json")
    fetch(f"{HF}/MM-OPG-Test.json", f"{D}/mmopg/mmopg_test.json")
    fetch(f"{HF}/images_resized_public.zip", f"{D}/mmopg/images.zip")

# BRAR (figshare, CC BY 4.0) - only needed for B
if need_B and not os.path.exists(f"{D}/brar/meta_data.csv"):
    zipfile.ZipFile(fetch("https://ndownloader.figshare.com/files/58062268", f"{D}/brar.zip")).extractall(f"{D}/brar")
    inner = glob.glob(f"{D}/brar/**/meta_data.csv", recursive=True)[0]
    if os.path.dirname(inner) != f"{D}/brar":
        for p in os.listdir(os.path.dirname(inner)): shutil.move(os.path.join(os.path.dirname(inner), p), f"{D}/brar")

# Aga Khan OPG (Zenodo, CC BY 4.0) - only needed for D
if need_D and not glob.glob(f"{D}/aku/**/annotations", recursive=True):
    zipfile.ZipFile(fetch("https://zenodo.org/api/records/10538750/files/Niihhaa/Dataset-v1.zip/content", f"{D}/aku.zip")).extractall(f"{D}/aku")

# PDCNN (public Google Drive folder) - only needed for C
if need_C:
    if not glob.glob(f"{D}/pdcnn/**/*.json", recursive=True):
        !gdown --folder "https://drive.google.com/drive/folders/18qUxeRPHPcCQT9o8AgV5400f05Fu3ISW" -O {D}/pdcnn
    for z in glob.glob(f"{D}/pdcnn/**/*.zip", recursive=True):
        if not os.path.isdir(z[:-4]): zipfile.ZipFile(z).extractall(z[:-4])
    print("PDCNN annotation files:", glob.glob(f"{D}/pdcnn/**/*.json", recursive=True))
print(subprocess.run("du -sh " + D + "/*", shell=True, capture_output=True, text=True).stdout)
"""),
          code("""
# 4. Model A: panoramic bone-loss screen per jaw (MM-OPG)
if need_A:
    !python /content/train_panoramic_boneloss.py --task screen --data {D}/mmopg --out {EXPORT}/panoramic_screen --arch {ARCH} --size {SIZE[0]} {SIZE[1]} --epochs {EPOCHS_A} --batch {BATCH_A} --lr 2e-4
if os.path.exists(f"{EXPORT}/panoramic_screen_metrics.json"): print(open(f"{EXPORT}/panoramic_screen_metrics.json").read())
"""),
          code("""
# 5. Model B: worst-tooth bone loss % and stage (BRAR), fine-tuned from model A
if need_B:
    !python /content/train_panoramic_boneloss.py --task severity --data {D}/brar --init {EXPORT}/panoramic_screen.pt --out {EXPORT}/panoramic_severity --arch {ARCH} --size {SIZE[0]} {SIZE[1]} --epochs {EPOCHS_B} --batch {BATCH_B} --lr 1e-4
if os.path.exists(f"{EXPORT}/panoramic_severity_metrics.json"): print(open(f"{EXPORT}/panoramic_severity_metrics.json").read())
"""),
          code("""
# 6. Model C: per-tooth bone-loss detector (PDCNN). Resumes from Drive after a disconnect.
from ultralytics import YOLO
if not need_C:
    print("Model C already trained or switched off in RUN - skipping")
else:
    bl = [p for p in glob.glob(f"{D}/pdcnn/**/*.json", recursive=True) if "BL" in os.path.basename(p)]
    assert bl, "PDCNN bone-loss JSON not found - check the printout of step 3"
    if not os.path.exists("/content/pdcnn_yolo/pdcnn.yaml"):
        !python /content/convert_pdcnn_coco.py --json "{bl[0]}" --images {D}/pdcnn --out /content/pdcnn_yolo
    print(open("/content/pdcnn_yolo/pdcnn.yaml").read())
    run_c = f"{ROOT}/runs/pdcnn_bl"
    if os.path.exists(f"{run_c}/weights/last.pt") and not os.path.exists(f"{run_c}/DONE"):
        YOLO(f"{run_c}/weights/last.pt").train(resume=True)
    elif not os.path.exists(f"{run_c}/DONE"):
        YOLO(YOLO_C).train(data="/content/pdcnn_yolo/pdcnn.yaml", imgsz=IMGSZ_C, epochs=EPOCHS_C, patience=PATIENCE_C, batch=-1,
                           project=f"{ROOT}/runs", name="pdcnn_bl", exist_ok=True, seed=0, deterministic=False,
                           fliplr=0.5, mosaic=0.5, close_mosaic=10, cache="ram", save_period=1)
    open(f"{run_c}/DONE", "w").close()

    # Honest test: detection mAP per class + per-tooth label accuracy on the held-out 10 %
    model_c = YOLO(f"{run_c}/weights/best.pt")
    r = model_c.val(data="/content/pdcnn_yolo/pdcnn.yaml", split="test", imgsz=IMGSZ_C, project=f"{ROOT}/runs", name="pdcnn_test", exist_ok=True)
    def iou(a, b):
        x1, y1, x2, y2 = max(a[0], b[0]), max(a[1], b[1]), min(a[2], b[2]), min(a[3], b[3])
        inter = max(0, x2 - x1) * max(0, y2 - y1); return inter / ((a[2]-a[0])*(a[3]-a[1]) + (b[2]-b[0])*(b[3]-b[1]) - inter + 1e-9)
    right = total = 0
    for img in glob.glob("/content/pdcnn_yolo/images/test/*"):
        lab = img.replace("/images/", "/labels/").rsplit(".", 1)[0] + ".txt"
        p = model_c(img, imgsz=IMGSZ_C, conf=0.25, verbose=False)[0]
        H, W = p.orig_shape
        preds = [(b.xyxy[0].tolist(), int(b.cls)) for b in p.boxes]
        for line in open(lab):
            c, cx, cy, w, h = map(float, line.split()); g = [(cx-w/2)*W, (cy-h/2)*H, (cx+w/2)*W, (cy+h/2)*H]
            best = max(preds, key=lambda q: iou(g, q[0]), default=None)
            total += 1
            if best is not None and iou(g, best[0]) >= 0.5 and best[1] == int(c): right += 1
    names = model_c.names
    mc = {"task": "per-tooth periodontal bone-loss boxes (PDCNN)", "classes": names,
          "test_mAP50": round(float(r.box.map50), 4), "test_mAP50_95": round(float(r.box.map), 4),
          "test_per_class_mAP50": {names[i]: round(float(v), 4) for i, v in enumerate(r.box.all_ap[:, 0])},
          "test_tooth_found_with_correct_label": round(right / max(total, 1), 4), "test_teeth": total}
    json.dump(mc, open(f"{EXPORT}/pdcnn_boneloss_metrics.json", "w"), indent=2)
    shutil.copy(f"{run_c}/weights/best.pt", f"{EXPORT}/pdcnn_boneloss.pt")
    print(json.dumps(mc, indent=2))
"""),
          code("""
# 7. Model D: fine-tune the current tooth detector on Aga Khan; keep it only if the held-out test improves
CUR = f"{ROOT}/current/dental_yolov8n.pt"
if not need_D:
    print("Model D already trained or switched off in RUN - skipping")
elif not os.path.exists(CUR):
    print("SKIPPED: upload backend/weights/dental_yolov8n.pt to MyDrive/PerioVision/current/ to run step D")
else:
    aku_src = os.path.dirname(glob.glob(f"{D}/aku/**/folder 1", recursive=True)[0])
    if not os.path.exists("/content/aku_yolo/aku.yaml"):
        !python /content/convert_aku_labelme.py --src "{aku_src}" --out /content/aku_yolo
    before = YOLO(CUR).val(data="/content/aku_yolo/aku.yaml", split="test", imgsz=IMGSZ_D, project=f"{ROOT}/runs", name="aku_before", exist_ok=True)
    run_d = f"{ROOT}/runs/aku_finetune"
    if not os.path.exists(f"{run_d}/weights/best.pt"):
        YOLO(CUR).train(data="/content/aku_yolo/aku.yaml", imgsz=IMGSZ_D, epochs=EPOCHS_D, patience=20, batch=-1, lr0=0.001,
                        freeze=10, fliplr=0.0, project=f"{ROOT}/runs", name="aku_finetune", exist_ok=True, seed=0)
    after = YOLO(f"{run_d}/weights/best.pt").val(data="/content/aku_yolo/aku.yaml", split="test", imgsz=IMGSZ_D, project=f"{ROOT}/runs", name="aku_after", exist_ok=True)
    md_ = {"test_mAP50_before": round(float(before.box.map50), 4), "test_mAP50_after": round(float(after.box.map50), 4),
           "test_mAP50_95_before": round(float(before.box.map), 4), "test_mAP50_95_after": round(float(after.box.map), 4),
           "note": "fliplr=0 because mirroring would swap left / right FDI numbers"}
    md_["adopted"] = md_["test_mAP50_95_after"] > md_["test_mAP50_95_before"]
    json.dump(md_, open(f"{EXPORT}/aku_detector_finetune_metrics.json", "w"), indent=2)
    if md_["adopted"]:
        shutil.copy(f"{run_d}/weights/best.pt", f"{EXPORT}/dental_yolov8n_aku.pt")
    print(json.dumps(md_, indent=2))
"""),
          code("""
# 8. Summary of everything in the export folder
for f in sorted(glob.glob(f"{EXPORT}/*")):
    print(f"{os.path.basename(f):45s} {os.path.getsize(f)/1e6:8.1f} MB")
for f in sorted(glob.glob(f"{EXPORT}/*metrics.json")):
    print("\\n==", os.path.basename(f)); print(open(f).read())
"""),
          md("""
## Done
Download `MyDrive/PerioVision/export_panoramic/` (right-click → Download), extract it into
`C:\\Users\\<you>\\Downloads\\export_panoramic`, and tell Claude. Each model is installed only if its held-out
test metrics pass; otherwise panoramic bone loss stays off.
""")]

def write(path, cell_list):
    nb = {"cells": cell_list, "metadata": {"accelerator": "GPU", "colab": {"provenance": []},
                                           "kernelspec": {"display_name": "Python 3", "name": "python3"}},
          "nbformat": 4, "nbformat_minor": 0}
    with open(path, "w", encoding="utf-8") as f:
        json.dump(nb, f, indent=1, ensure_ascii=False)
    print("wrote", os.path.abspath(path), len(cell_list), "cells")


write(OUT, cells)

# Single-model notebooks, so two Google accounts can train C and D at the same time.
SINGLE = {
    "C": ("train_panoramic_C_colab.ipynb", "the per-tooth bone-loss detector (model C, PDCNN)",
          "About 1-1.5 hours on a free T4."),
    "D": ("train_panoramic_D_colab.ipynb", "the tooth-detector fine-tune on Aga Khan films (model D)",
          "About 30-45 minutes on a free T4. **First** upload `backend/weights/dental_yolov8n.pt` to "
          "`MyDrive/PerioVision/current/` in THIS Google account."),
}
for key, (fname, what, note) in SINGLE.items():
    one = [md(f"""
# PerioVision AI: train {what} on a free Colab GPU

`Runtime` → `Change runtime type` → **T4 GPU** → Save, then `Runtime` → **Run all** and allow Google Drive.
{note} If Colab disconnects, Run all again: training resumes from Drive.

Results go to `MyDrive/PerioVision/export_panoramic/` in this account; download that folder and give it to Claude.
""")]
    for c in cells[1:]:
        src = "".join(c["source"])
        if c["cell_type"] == "markdown":
            continue
        if src.startswith("# 0. Settings"):
            src = src.replace('RUN = {"A": True, "B": True, "C": True, "D": False}',
                              "RUN = {" + ", ".join(f'"{k}": {k == key}' for k in "ABCD") + "}")
        if src.startswith(("# 4. Model A", "# 5. Model B")):
            continue
        if src.startswith("%%writefile /content/train_panoramic_boneloss.py"):
            continue
        if key == "C" and src.startswith(("# 7. Model D", "%%writefile /content/convert_aku_labelme.py")):
            continue
        if key == "D" and src.startswith(("# 6. Model C", "%%writefile /content/convert_pdcnn_coco.py")):
            continue
        one.append(code(src))
    write(os.path.join(os.path.dirname(OUT), fname), one)
