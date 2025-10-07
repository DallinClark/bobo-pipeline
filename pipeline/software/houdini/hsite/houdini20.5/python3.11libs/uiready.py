import hou

# Open Bobaris on startup
desks = {d.name(): d for d in hou.ui.desktops()}
if "Bobaris" in desks:
    desks["Bobaris"].setAsCurrent()
