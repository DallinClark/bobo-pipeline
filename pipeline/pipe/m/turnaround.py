import os
import maya.cmds as mc
import mtoa.utils as mutils  # type: ignore[import-not-found]


class Turnaround:
    def __init__(self):
        self.selected = mc.ls(selection=True)[0]

        self.bounding_box = mc.exactWorldBoundingBox(self.selected)
        self.minX, self.minY, self.minZ, self.maxX, self.maxY, self.maxZ = (
            self.bounding_box
        )
        self.sizeZ = self.maxZ - self.minZ
        self.sizeY = self.maxY - self.minY
        self.sizeX = self.maxX - self.minX

        initial_rotation = mc.getAttr(f"{self.selected}.rotateY")
        mc.setKeyframe(v=initial_rotation, at="rotateY", t=0)
        mc.setKeyframe(v=initial_rotation + 360, at="rotateY", t=121)

        self.set_up_lighting()
        self.camera = self.set_up_camera()
        self.create_background()
        self.set_render_settings()

    def create_background(self):
        sweep = mc.polyCube(
            width=(self.sizeX * 20.0),
            height=self.sizeY / 5.0,
            depth=(self.sizeZ * 10.0),
            subdivisionsX=1.0,
            subdivisionsY=1.0,
            subdivisionsZ=1.0,
        )[0]
        mc.select(f"{sweep}.f[0]")
        mc.polyExtrudeFacet(localTranslateZ=0.1)
        mc.polyExtrudeFacet(
            localTranslateZ=self.sizeZ,
            localTranslateY=self.sizeY * 5.0,
            localRotateX=-90,
        )
        mc.polyExtrudeFacet(localTranslateZ=self.sizeZ * 5.0)
        mc.select(sweep)
        mc.move(
            (self.maxX + self.minX) / 2,
            self.minY - (self.sizeY / 10.0),
            (self.maxX + self.minZ),
        )
        mc.polySmooth()

    def set_up_camera(self):
        camera_transform, camera_shape = mc.camera()
        mc.select(camera_shape)
        mc.move(
            (self.maxX + self.minX) / 2,
            self.maxY + (self.sizeY * 0.5),
            self.minZ - (self.sizeZ * 5.0),
        )
        mc.aimConstraint(self.selected, camera_transform)
        mc.rotate(0, -90, 0, r=True, os=True)
        mc.delete(
            mc.listRelatives(camera_transform, type="constraint")[0]
        )  # Deletes the aimConstraint
        return camera_shape

    def set_up_lighting(self):
        mutils.createLocator("aiAreaLight", asLight=True)
        mutils.createLocator("aiAreaLight", asLight=True)
        mutils.createLocator("aiAreaLight", asLight=True)
        key_light = mc.rename("aiAreaLight1", "Key")
        fill_light = mc.rename("aiAreaLight2", "Fill")
        rim_light = mc.rename("aiAreaLight3", "Rim")

        self.bounding_box = mc.exactWorldBoundingBox(self.selected)
        self.minX, self.minY, self.minZ, self.maxX, self.maxY, self.maxZ = (
            self.bounding_box
        )
        self.sizeZ = self.maxZ - self.minZ
        self.sizeY = self.maxY - self.minY
        self.sizeX = self.maxX - self.minX

        mc.select("Key")
        mc.move(
            self.maxX + (self.sizeX * 1.5),
            self.maxY + (self.sizeY * 2.0),
            self.minZ - (self.sizeZ * 0.5),
        )
        mc.aimConstraint(self.selected, key_light)
        mc.rotate(0, -90, 0, r=True, os=True)
        mc.delete(
            mc.listRelatives(key_light, type="constraint")[0]
        )  # Deletes the aimConstraint
        mc.scale(self.sizeX * 2.0, self.sizeY * 2.0, self.sizeZ * 2.0)
        mc.setAttr("KeyShape.exposure", 6)
        mc.setAttr("KeyShape.intensity", 30)

        mc.select("Fill")
        mc.move(
            self.minX - (self.sizeX * 2.5),
            self.maxY + (self.sizeY * 1.0),
            self.minZ - (self.sizeZ * 0.5),
        )
        mc.aimConstraint(self.selected, fill_light)
        mc.delete(
            mc.listRelatives(fill_light, type="constraint")[0]
        )  # Deletes the aimConstraint
        mc.rotate(0, -90, 0, r=True, os=True)
        mc.scale(self.sizeX * 1.5, self.sizeY * 1.5, self.sizeZ * 1.5)
        mc.setAttr("FillShape.exposure", 3)
        mc.setAttr("FillShape.intensity", 30)

        mc.select("Rim")
        mc.move(
            (self.maxX + self.minX) / 2.0, self.maxY, self.maxZ + (self.sizeZ * 1.0)
        )
        mc.aimConstraint(self.selected, rim_light)
        mc.delete(mc.listRelatives(rim_light, type="constraint")[0])
        mc.rotate(0, -90, 0, r=True, os=True)
        mc.scale(self.sizeX * 1.2, self.sizeY * 1.0, self.sizeZ * 1.2)
        mc.setAttr("RimShape.exposure", 2)
        mc.setAttr("RimShape.intensity", 30)

    def set_render_settings(self):
        output_dir = ""
        filename = self.selected
        if os.name == "nt":
            output_dir = "G:bobo/modeling/turnarounds/" + filename
        else:
            output_dir = "/groups/bobo/modeling/turnarounds/" + filename

        if not os.path.exists(output_dir):
            os.mkdir(output_dir)

        output_name = os.path.join(output_dir, filename + "_turnaround_")

        mc.setAttr("defaultRenderGlobals.imageFilePrefix", output_name, type="string")
        mc.setAttr("defaultRenderGlobals.useFrameExt", 1)

        mc.setAttr("defaultRenderGlobals.startFrame", 1)
        mc.setAttr("defaultRenderGlobals.endFrame", 121)

        mc.setAttr("defaultRenderGlobals.outFormatExt", type="png")
        mc.setAttr("defaultRenderGlobals.outFormatControl", 2)
        mc.setAttr("defaultRenderGlobals.outFormatExt", "name.#.ext", type="string")
        mc.setAttr("defaultRenderGlobals.outFormatControl", 0)
        mc.setMayaSoftwareFrameExt("3", 0)

        print("Turnaround rendering complete.")
