import maya.cmds as cmds
import re

# Global variable to store the camera file path
cameraFilePath = None

# Dictionary to track the last used shot number for each sequence
sequence_shot_tracker = {
    'A': 0,
    'B': 0,
    'C': 0,
    'D': 0,
    'E': 0,
    'F': 0,
    'G': 0
}

# Function to get the last shot number from existing references for a specific sequence
def get_last_shot_num_for_sequence(sequence):
    refs = cmds.file(q=True, reference=True)
    shot_nums = []

    # Regex to match shot code format: "SequenceName_###"
    pattern = re.compile(rf'^{sequence}_(\d{{3}})_CAM$')

    for ref in refs:
        ns = cmds.file(ref, q=True, namespace=True)
        match = pattern.search(ns)
        if match:
            # Extract the shot number and convert to integer
            shot_nums.append(int(match.group(1)))

    if shot_nums:
        return max(shot_nums)
    else:
        return sequence_shot_tracker[sequence]  # Default from tracker if no existing references

def reference_camera():
    global cameraFilePath, sequence_shot_tracker

    # Check if the camera file path is set
    if cameraFilePath is None:
        cmds.error("Camera file path not provided!")
        return

    # Get the selected sequence name
    seqName = cmds.optionMenu('seqMenu', query=True, value=True)

    # Get the last used shot number for the current sequence
    last_shot_num = get_last_shot_num_for_sequence(seqName)

    # If no references were found, start from 010
    if last_shot_num == 0:
        shotNum = 10
    else:
        shotNum = last_shot_num + 10  # Increment by 10

    # Update the tracker with the new shot number for this sequence
    sequence_shot_tracker[seqName] = shotNum

    # Create the shot code
    shotCode = seqName + '_' + '{:03d}'.format(shotNum) + '_CAM'

    # Reference the camera file with the selected file path
    cmds.file(cameraFilePath, r=True, namespace=shotCode)

# Create a function to set the camera file path based on the OS choice
def set_file_path(os_choice):
    global cameraFilePath
    if os_choice == "Windows":
        cameraFilePath = "G:/bobo/previs/Rigs/boboShotCam_v01.mb"
    elif os_choice == "Linux":
        cameraFilePath = "/groups/bobo/previs/Rigs/boboShotCam_v01.mb"
    else:
        cmds.error("Invalid OS selection!")
    reference_camera()  # Call the function to reference the camera after OS selection

# Create the main UI for selecting the operating system and sequence name
def show_camera_reference_ui():
    if cmds.window("CameraReferenceUI", exists=True):
        cmds.deleteUI("CameraReferenceUI")

    camera_window = cmds.window("CameraReferenceUI", title="Select Operating System and Sequence", widthHeight=(300, 150))
    cmds.columnLayout(adjustableColumn=True)

    # OS selection
    cmds.text(label='Select Operating System:')
    cmds.optionMenu('osMenu', label='Operating System')
    cmds.menuItem(label='Windows')
    cmds.menuItem(label='Linux')

    # Sequence selection
    cmds.text(label='Select Sequence Name:')
    cmds.optionMenu('seqMenu', label='Sequence Name')
    cmds.menuItem(label='A')
    cmds.menuItem(label='B')
    cmds.menuItem(label='C')
    cmds.menuItem(label='D')
    cmds.menuItem(label='E')
    cmds.menuItem(label='F')
    cmds.menuItem(label='G')

    # Button to apply the selection and reference the camera
    cmds.button(label='Reference Camera', command=lambda x: set_file_path(cmds.optionMenu('osMenu', query=True, value=True)))

    cmds.showWindow(camera_window)

# Call the UI to show the window
show_camera_reference_ui()
