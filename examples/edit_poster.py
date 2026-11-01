# Runs inside Krita via `bct paint script edit_poster.py IN.kra OUT.kra OUT.png`
from krita import Krita, InfoObject

def main(args):
    src, out_kra, out_png = args
    app = Krita.instance()
    doc = app.openDocument(src)
    doc.setBatchmode(True)
    root = doc.rootNode()
    wave = doc.nodeByName("wave")
    # a Krita filter on one layer: soft blur, then mark it for an artist with a colour label
    blur = app.filter("blur")
    cfg = blur.configuration(); cfg.setProperty("halfWidth", 2); cfg.setProperty("halfHeight", 2); blur.setConfiguration(cfg)
    blur.apply(wave, 0, 0, doc.width(), doc.height())
    wave.setColorLabel(4)
    # a new group with a glow made from a duplicate of the title, under the title
    title = doc.nodeByName("title")
    glow = title.duplicate(); glow.setName("title glow")
    gb = app.filter("gaussian blur"); c = gb.configuration()
    c.setProperty("horizRadius", 10); c.setProperty("vertRadius", 10); gb.setConfiguration(c)
    group = doc.createGroupLayer("title group")
    root.addChildNode(group, doc.nodeByName("shadow"))
    group.addChildNode(glow, None)
    title.remove(); group.addChildNode(title, glow)
    gb.apply(glow, 0, 0, doc.width(), doc.height())
    glow.setBlendingMode("screen"); glow.setOpacity(200)
    doc.refreshProjection(); doc.waitForDone()
    doc.saveAs(out_kra)
    doc.exportImage(out_png, InfoObject())
    names = [n.name() for n in root.childNodes()]
    doc.close()
    return {"top_level_layers": names, "filters": ["blur", "gaussian blur"]}
