"""Crop algebra chains from real student answer sheets (images are NOT committed).

Source: Hugging Face dataset lokeshe09/handwritten-mathqa-vista_format (48 phone photos of grade-9
answer sheets; no licence stated, so images stay local and only labels/results are published).
Labels below were written by reading each crop; first_slip = 0-based index among maths lines.
"""
import json
import os
import sys

from PIL import Image

from redpen.adapters.imageio import load_rgb
from redpen.adapters.orient import upright

SRC = sys.argv[1] if len(sys.argv) > 1 else os.path.expanduser("~/dev/bh-data/sheets")
OUT = os.path.join(os.path.dirname(__file__), "real")

CROPS = [
    ("004", (0.22, 0.285, 0.60, 0.395), ["5((5)^2-3(10))", "=5(-4)", "=-20"], 1, "25-30 is -5, not -4"),
    ("005", (0.10, 0.295, 0.47, 0.445), ["5((5)^2-3(10))", "=5(-4)", "=-20"], 1, "25-30 is -5, not -4"),
    ("021", (0.10, 0.615, 0.60, 0.805), ["(5)^2+2(10)-3abc=-25", "25+20-3abc=-25", "45-3abc=-25", "3abc=-25-45", "3abc=-70", "abc=-70/3"], 3, "moving 45 across: 3abc = 25+45"),
    ("032", (0.17, 0.188, 0.52, 0.28), ["(2)^3+(2)^2-2(2)+a=0", "8+4-4+a=0", "8+a=0"], None, "correct"),
    ("029", (0.13, 0.24, 0.64, 0.425), ["=2x^3+5x^2-5x-2", "=2(1)^3+5(1)^2-5(1)-2", "=2+5-5-2", "=7-7", "=0"], None, "correct (value substitution)"),
    ("029", (0.24, 0.758, 0.60, 0.87), ["-7+sqrt((7)^2-4*2*2)", "-7+sqrt(49-16)", "-7+sqrt(33)"], None, "correct (x used as times sign)"),
    ("015", (0.10, 0.26, 0.74, 0.35), ["p(1)=2(1)^3+5(1)^2-5(1)-2", "=2+5-5-2=0"], None, "correct"),
]

# Held-out set (2026-10-10 21:1x): labelled by an independent reader AFTER the code was frozen for the
# orientation and verifier rules, rotation given explicitly ("cw" = 90 deg clockwise, "none").
HELDOUT = [
    ("002", (0.1, 0.22, 0.85, 0.36), ["a+b+c=18+10+c=42", "18+c=42", "c=42-18=24"], 1, "18+10+c=42 becomes 18+c=42 (the 10 is dropped; should be 28+c=42, c=14). Later lines follow from line 1.", "none"),
    ("002", (0.26, 0.651, 0.68, 0.713), ["sqrt(11(11-11)(11-6)(11-15))", "sqrt(11*11*5*-4)"], 1, "(11-11) evaluated as 11 instead of 0 (product should be 0; written product is -2420). Times signs written as x.", "none"),
    ("003", (0.2, 0.14, 0.8, 0.372), ["sqrt(21*(3)(11)(7))", "sqrt(21*231)", "sqrt(4851)", "95"], 3, "21*3*11*7=21*231=4851 correct; sqrt(4851)=69.65, not 95 (95^2=9025).", "none"),
    ("007", (0.115, 0.36, 0.575, 0.447), ["P(2)=4(2)^3+a(2)^2+6(2)-5", "4(8)+4(a)+12-5", "41+4a"], 2, "4(8)+4a+12-5 = 39+4a, student wrote 41+4a.", "cw"),
    ("007", (0.115, 0.462, 0.56, 0.552), ["Q(2)=(2)^3+(2)^2-2(2)+a", "8+4-4+a", "8+a"], None, "Correct substitution and simplification.", "cw"),
    ("007", (0.375, 0.568, 0.64, 0.69), ["41+4a=8+a", "41-8=a-4a", "33=-3a", "a=-11"], None, "Correct solving of the linear equation (starting value 41 is carried from an earlier slip, but each line follows). Line 0 is preceded on the sheet by 'P(x)=Q(x)=' which is outside the box.", "cw"),
    ("009", (0.17, 0.205, 0.63, 0.345), ["4x^3+6x^2-5x-2", "4(x-1)^3+6(x-1)^2-5(x-1)-2", "(x-1)(4x^2+7x+2)"], 1, "Replacing x by (x-1) does not give an equal expression; also (x-1)(4x^2+7x+2)=4x^3+3x^2-5x-2 differs from line 0 (f(1)=3, so x-1 is not a factor). Student's x looks like n.", "cw"),
    ("009", (0.2, 0.36, 0.49, 0.45), ["4x^2+7x+2", "(4x+1)(x+2)"], 1, "(4x+1)(x+2)=4x^2+9x+2, not 4x^2+7x+2 (bad factorisation). Leading '=' signs omitted; the 4 in line 0 is heavily overwritten but legible.", "cw"),
    ("010", (0.14, 0.858, 0.672, 0.932), ["f(1)=4(1)^3+6(1)^2-5(1)-2", "4+6-5-2=3"], None, "Correct evaluation (=3). The trailing '(is a root)' remark is outside the box.", "cw"),
    ("012", (0.2, 0.623, 0.5, 0.695), ["180-(69+31)", "180-100", "80°"], None, "Correct angle arithmetic; line 0's left side (angle BAC = ...) is excluded because a diagram overlaps it.", "cw"),
    ("012", (0.21, 0.893, 0.43, 0.965), ["90+2∠B=180", "2∠B=90", "∠B=45=∠C"], None, "Correct solving for angle B.", "cw"),
    ("014", (0.105, 0.13, 0.66, 0.25), ["p(2)=2(2)^3+-3(2)^2+3(2)-5", "16-12+6-5", "5"], None, "Correct (a=-3 substituted, written '+-3'). The 2 in p(2) is overwritten.", "cw"),
    ("014", (0.105, 0.282, 0.565, 0.396), ["g(2)=(2)^3+(2)^2-2(2)+(-3)", "8+4-4-3", "5"], None, "Correct. The two 4s in line 1 carry cancel strokes; the inner 2 of 2(2) is overwritten.", "cw"),
    ("015", (0.13, 0.13, 0.76, 0.25), ["p(-1)=2(-1)^3+5(-1)^2-5(-1)-2", "-2+5+5-2≠0"], None, "Correct: the value is 6, so ≠0 holds.", "cw"),
    ("018", (0.13, 0.443, 0.5, 0.522), ["∠BAC+69+31=180", "∠BAC=180-100", "∠BAC=80°"], None, "Correct; line 1 is prefixed by a therefore sign.", "cw"),
    ("020", (0.15, 0.611, 0.6, 0.722), ["69°+31°+∠BAC=180°", "100°+∠BAC=180°", "∠BAC=180°-100°", "∠BAC=80°"], None, "Correct angle-sum solving.", "cw"),
    ("023", (0.19, 0.72, 0.6, 0.882), ["∠A+∠B+∠C=180", "90+2∠B=180", "2∠B=180-90=90", "∠B=(90)/(2)=45°"], None, "Correct (uses the given ∠A=90 and ∠B=∠C).", "cw"),
    ("027", (0.08, 0.578, 0.5, 0.7), ["(2)^3+(2)^2-2(2)+a", "8+4-4+a", "8+a=0", "a=-8"], None, "Correct. Each line starts with '=>' on the sheet (omitted); '=0' comes from the remainder condition.", "cw"),
    ("031", (0.14, 0.395, 0.55, 0.474), ["(5)^2=a^2+b^2+c^2+2(10)", "25=a^2+b^2+c^2+20", "25-20=5=a^2+b^2+c^2"], None, "Correct.", "cw"),
    ("031", (0.18, 0.475, 0.59, 0.555), ["a^3+b^3+c^3-3abc=(5)(5-(10))", "(5)(-5)", "a^3+b^3+c^3-3ab=-25"], 2, "Arithmetic is right (=-25), but the final line copies the left side as -3ab instead of -3abc (copy slip: c dropped).", "cw"),
    ("034", (0.2, 0.6, 0.68, 0.645), ["P(1)=2(1)^3+5(1)^2-5(1)-2", "2+5-5-2=0"], None, "Correct evaluation.", "cw"),
    ("034", (0.23, 0.764, 0.63, 0.862), ["2x^2+3x-2", "2x^2+4x-1-2", "2x(x+2)-1(x+2)", "(2x-1)(x+2)"], 1, "Middle-term split written as +4x-1 (missing x): 2x^2+4x-3 ≠ 2x^2+3x-2. Lines 2-3 do equal line 0. (The quotient 2x^2+3x-2 itself comes from a wrong synthetic division; the correct quotient is 2x^2+7x+2. That error is outside this chain.)", "cw"),
    ("021", (0.165, 0.505, 0.735, 0.616), ["a^3+b^3+c^3-3abc=-25", "a^2+b^2+c^2+a+b+c-3abc=-25", "(a+b+c)^2+5-3abc=-25", "a^2+b^2+c^2+2ab+2bc+2ca-3abc=-25"], 1, "Cubes rewritten as a^2+b^2+c^2+a+b+c (not an identity); line 3 also drops the +5. This is a different chain from the already-labelled (5)^2+2(10)-3abc chain directly below; lines are slanted, so the box bottom grazes the top of that next line.", "cw"),
]

os.makedirs(OUT, exist_ok=True)
labels = []
for n, (sheet, (x0, y0, x1, y1), lines, slip, note) in enumerate(CROPS):
    img = upright(load_rgb(open(os.path.join(SRC, f"{sheet}.jpg"), "rb").read()))
    W, H = img.size
    crop = img.crop((int(x0 * W), int(y0 * H), int(x1 * W), int(y1 * H)))
    name = f"real{n + 1:02d}-{sheet}.jpg"
    crop.save(os.path.join(OUT, name), quality=92)
    labels.append({"file": name, "sheet": sheet, "lines": lines, "first_slip": slip, "note": note})
for k, (sheet, (x0, y0, x1, y1), lines, slip, note, rot) in enumerate(HELDOUT):
    img = load_rgb(open(os.path.join(SRC, f"{sheet}.jpg"), "rb").read())
    if rot == "cw":
        img = img.transpose(Image.Transpose.ROTATE_270)
    W, H = img.size
    crop = img.crop((int(x0 * W), int(y0 * H), int(x1 * W), int(y1 * H)))
    name = f"held{k + 1:02d}-{sheet}.jpg"
    crop.save(os.path.join(OUT, name), quality=92)
    labels.append({"file": name, "sheet": sheet, "lines": lines, "first_slip": slip, "note": note, "heldout": True})
json.dump(labels, open(os.path.join(OUT, "labels.json"), "w"), indent=1, ensure_ascii=False)
print(len(labels), "crops")
