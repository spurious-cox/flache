"""Build Flache's menu bar glyph and, once the artwork exists, its icon - v1.0.1

The menu bar mark is an Old English F in "Olde English", the same face as
Stache's S.  It is rendered here at build time into icon/Flache_glyph.png
and shipped in the bundle, so the app never depends on the font being
installed.  It is cropped to the glyph's own ink because AppKit centres
text on its line box, not on the letter.

The application icon is the author's own artwork, flache.png in the project
directory: a full-bleed square.  It is masked to Apple's 824-in-1024
squircle and built into icon/Flache.icns, which macOS 13-25 show.  macOS 26
uses icon/AppIcon.icon instead, made from the same file with
`~/bin/glass_icon --make flache.png icon/AppIcon.icon`.  Until flache.png
exists no icon is built and the app wears the generic one.

    ./venv/bin/python make_icon.py
"""

import io
import os
import shutil
import subprocess

from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
ICON_DIR = os.path.join(HERE, "icon")
SOURCE = os.path.join(HERE, "flache.png")

GLYPH_FONT = "Olde English"
GLYPH_PX = 36                     # 18pt in the menu bar, at 2x
# Apple's icon grid: the artwork on an 824-point squircle, corner radius
# 185.4, centred in a 1024-point canvas, the same as Stache's.
CANVAS = 1024
CONTENT = 824
RADIUS = 185.4
INSET = (CANVAS - CONTENT) // 2


def squircle_mask(size, radius):
    """A rounded-rectangle mask, drawn 4x and downsampled so the corners are
    smooth rather than stair-stepped."""
    mask = Image.new("L", (size * 4, size * 4), 0)
    ImageDraw.Draw(mask).rounded_rectangle(
        (0, 0, size * 4 - 1, size * 4 - 1), radius=radius * 4, fill=255)
    return mask.resize((size, size), Image.LANCZOS)


def build_png():
    """The full-bleed artwork, masked to the squircle and centred."""
    art = Image.open(SOURCE).convert("RGBA")
    plate = art.resize((CONTENT, CONTENT), Image.LANCZOS)
    plate.putalpha(squircle_mask(CONTENT, RADIUS))
    canvas = Image.new("RGBA", (CANVAS, CANVAS), (0, 0, 0, 0))
    canvas.paste(plate, (INSET, INSET), plate)
    return canvas


def build_icns(png):
    iconset = os.path.join(ICON_DIR, "Flache.iconset")
    shutil.rmtree(iconset, ignore_errors=True)
    os.makedirs(iconset)
    for size in (16, 32, 128, 256, 512):
        png.resize((size, size), Image.LANCZOS).save(
            os.path.join(iconset, "icon_%dx%d.png" % (size, size)))
        png.resize((size * 2, size * 2), Image.LANCZOS).save(
            os.path.join(iconset, "icon_%dx%d@2x.png" % (size, size)))
    out = os.path.join(ICON_DIR, "Flache.icns")
    subprocess.run(["/usr/bin/iconutil", "-c", "icns", iconset, "-o", out],
                   check=True)
    shutil.rmtree(iconset, ignore_errors=True)
    return out


def build_glyph():
    """The Old English F, cropped to its ink, as a menu bar template image."""
    from AppKit import (NSFont, NSColor, NSBitmapImageRep, NSGraphicsContext,
                        NSAttributedString, NSFontAttributeName,
                        NSForegroundColorAttributeName, NSDeviceRGBColorSpace,
                        NSBitmapImageFileTypePNG, NSMakePoint, NSApplication)
    NSApplication.sharedApplication()
    font = NSFont.fontWithName_size_(GLYPH_FONT, 300)
    if font is None:
        raise SystemExit("make_icon.py: the font %r is not installed"
                         % GLYPH_FONT)
    side = 500
    rep = NSBitmapImageRep.alloc().\
        initWithBitmapDataPlanes_pixelsWide_pixelsHigh_bitsPerSample_samplesPerPixel_hasAlpha_isPlanar_colorSpaceName_bytesPerRow_bitsPerPixel_(
            None, side, side, 8, 4, True, False, NSDeviceRGBColorSpace, 0, 0)
    ctx = NSGraphicsContext.graphicsContextWithBitmapImageRep_(rep)
    NSGraphicsContext.saveGraphicsState()
    NSGraphicsContext.setCurrentContext_(ctx)
    NSAttributedString.alloc().initWithString_attributes_("F", {
        NSFontAttributeName: font,
        NSForegroundColorAttributeName: NSColor.blackColor(),
    }).drawAtPoint_(NSMakePoint(90, 90))
    NSGraphicsContext.restoreGraphicsState()

    data = rep.representationUsingType_properties_(NSBitmapImageFileTypePNG, {})
    glyph = Image.open(io.BytesIO(bytes(data))).convert("RGBA")
    box = glyph.getchannel("A").getbbox()
    if box is None:
        raise SystemExit("make_icon.py: the glyph rendered empty")
    glyph = glyph.crop(box)
    width = max(1, round(glyph.width * GLYPH_PX / glyph.height))
    glyph = glyph.resize((width, GLYPH_PX), Image.LANCZOS)
    out = os.path.join(ICON_DIR, "Flache_glyph.png")
    glyph.save(out)
    return out, glyph.size


if __name__ == "__main__":
    os.makedirs(ICON_DIR, exist_ok=True)
    glyph, size = build_glyph()
    print("wrote %s (%dx%d)" % (glyph, size[0], size[1]))
    if os.path.exists(SOURCE):
        icns = build_icns(build_png())
        print("wrote %s (%d bytes)" % (icns, os.path.getsize(icns)))
    else:
        print("no %s yet - building without an app icon" %
              os.path.relpath(SOURCE, HERE))
