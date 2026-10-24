"""Pipeline-wide configuration constants."""

# Stage 7 volume calibration
# The ArUco marker is identified as the "obj" cluster (non-box).
# REFERENCE_REAL_SIZE_CM is the real-world linear size of the ArUco marker cube.
REFERENCE_REAL_SIZE_CM = 10.0     # real linear size of reference in cm

# Stage 3 band detection
# These bounds describe a genuinely green band. MARKER_VAL_MIN is the one that
# matters most: hue is a ratio of channel differences to the channel maximum,
# so as a pixel darkens its hue becomes arbitrary, and an RGB(8, 6, 8) shadow
# reports a confident hue that means nothing. Without a brightness floor those
# pixels dominate the detection and smear the two bands into one cluster that
# runs the length of the limb.
MARKER_HUE_MIN = 70.0     # degrees; below this is yellow/orange/red
MARKER_HUE_MAX = 180.0    # degrees; above this is cyan/blue/magenta
MARKER_SAT_MIN = 25.0     # percent; washed-out pixels have no reliable hue
MARKER_VAL_MIN = 15.0     # percent; below this hue is noise
MARKER_EXG_MIN = 10       # excess green, 2*G - R - B

# Stage 1 frame limits
DEFAULT_MAX_FRAMES_MPS = 6

# Model weights
VGGT_MODEL_URL = "https://huggingface.co/facebook/VGGT-1B/resolve/main/model.pt"

# Image extensions accepted by the input loader
IMAGE_EXTENSIONS = (".png", ".jpg", ".jpeg", ".bmp", ".tiff", ".webp", ".heic", ".heif")
