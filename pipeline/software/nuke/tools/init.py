import nuke

nuke.pluginAddPath("./NukeSurvivalToolkit_publicRelease/NukeSurvivalToolkit")
nuke.pluginAddPath("./BobukeTools")

# aspect ratio
nuke.addFormat("16 9 Bobo_aspect_ratio")

nuke.knobDefault("Root.format", "Bobo_aspect_ratio")

# color management
nuke.knobDefault("Root.colorManagement", "OCIO")
