# Mask to Normal Map Generator

This program is a tool that generates normal maps from mask images.

---

## Features

This tool can generate normal maps with a three-dimensional feel even when using high-contrast images like masks as input.

- Live preview (realtime) of the normal map while editing parameters
- Language mode toggle (Japanese / English)
- Input preview visibility toggle
- Output directory selection
- Persistent settings (saved on app close): language, output directory, input preview toggle, default output resolution, radius, strength, overwrite setting

---

## How to Use

1. **Launch the Program**  
   Double-click `Normalmap_Generator.exe` to launch the application.

2. **Select Input File**  
   - Drag and drop an image (PNG or JPEG format) into the window, or select one using the browse button.
   - Note: JPEG files must have either .jpg or .jpeg extension.
   - The application never modifies or saves the input file itself.

3. **Adjust Settings (if necessary)**  
   ***Basic Settings***
   - **Slope Shape**: Choose from Linear, Curve 1 (Logarithmic), or Curve 2 (Exponential).
   - **Radius**: Specify the radius of the generated slope area (positive integer).
   - **Strength**: Specify the intensity of the normal map (positive number).
   - **Other Options**:
     - "Invert Slope Direction": Reverses whether slopes form inward or outward.
     - "Disable Slope Generation": Disables slope generation and creates a simple normal map based on pixel brightness differences.
     - "Overwrite Existing Files": Determines whether to overwrite output files when they already exist.
   
      ***Advanced Settings***
      - **Normal Map Type**: Choose DirectX (Y+) or OpenGL (Y-). Toggling this updates the live preview immediately.
      - **Output Directory**: Choose where to save outputs (defaults to an `output` subfolder next to the input when not specified).
      - "Show Input Preview": Show or hide the input image preview pane.
      - "Save Intermediate Files": Saves edge images and height maps generated during image processing.
      - "Enable English mode": Switches the UI language (persisted).

   Note: You can generate normal maps with default settings if no adjustments are needed.

4. **Generate Normal Map**  
   Click the "Generate Normal Map" button to start processing.  
   The normal map is saved in PNG format. If an output directory is specified, it will be used; otherwise an `output` folder is created next to the input file.

5. **Check Preview**  
   You can view previews of both the input image and the generated normal map.

---

## Live Preview (Realtime)

- When you load an image or change settings, a live preview of the normal map updates automatically.
- For performance, preview processing always runs at 512x512, regardless of the original image size. Only the displayed preview is resized to match the input preview area (about 300x300).
- For numeric inputs (Radius and Strength), updates are debounced: the preview refreshes after you finish typing (about 0.6 seconds of inactivity) or when you press Enter or move focus out of the field. Toggles and radio buttons update the preview immediately.

---

## About Input Files

For optimal results, mask images with the following characteristics are recommended:

- **High Contrast**: Images with clear contrast between black and white areas.
- **Simple Shapes**: Masks with shapes that are not overly complex.
- **Minimal Noise**: Images with less noise will improve edge detection accuracy.
- **Resolution**: Adjust resolution as needed (processing may slow down with very high-resolution images). For smooth normal maps, a certain level of resolution is necessary (2K or higher recommended).

Examples:  
- Images with black shapes on a white background.
- Simple designs like silhouettes or logos.
- Images with clear contrast and no gradients.
- Images without blur or noise.

Images that don't meet these conditions can still be processed, but results may not be optimal. In such cases, checking "Disable Slope Generation" in the settings might yield better results, though this is not guaranteed.

***If input images cannot be loaded***
- Verify that the image extension is `png`, `jpg`, or `jpeg`.
- Images that are too large may fail to load due to insufficient memory. Try reducing the resolution.
- The program generally supports file paths containing non-English characters, but some environments may have issues. If this occurs, try using paths with only alphanumeric characters.

---

## Output Files

- Generated normal maps are saved in PNG format.
- If an output directory is specified in Advanced Settings, outputs are saved there; otherwise an `output` folder is created next to the input.
- Whether to overwrite existing files when processing multiple times can be changed via the "Overwrite Existing Files" setting.

## Settings Persistence

The following settings are saved when the app closes and are restored on the next launch:

- UI language
- Output directory
- Show input preview (on/off)
- Default output resolution (preview/output target)
- Default radius
- Default strength
- Overwrite existing files (on/off)

Not saved on purpose:

- Input file path (for privacy and predictability)

---

## Notes

- PNG and JPEG input files are accepted as-is. The application never modifies or saves the input file.
- Errors may occur if the input file is not appropriate. Please use images that meet the recommended conditions.
- The application may appear unresponsive during processing, but the operation is continuing in the background.
- In some environments, software fonts may be replaced with other installed fonts, which might affect the GUI layout but not functionality.

---

## Installation (Windows)

- Download the installer from your release page (Normalmap_Generator_v3_Setup_<version>.exe).
- Double-click to run. The wizard will guide you through:
   - Choosing the install location (default: Program Files)
   - Optional desktop shortcut
   - Start Menu entry is created automatically
- After installation, launch from Start Menu or the desktop shortcut.
- To uninstall: open “Settings > Apps > Installed apps” (or “Apps & features”), find “Normalmap Generator v3”, and uninstall.

## Libraries Used
- This software uses the following libraries:
  - [OpenCV](https://opencv.org/) (Apache License 2.0)
  - [NumPy](https://numpy.org/) (BSD License)
  - [Pillow](https://pypi.org/project/pillow/) (PIL Software License)

For detailed license information, please refer to the `LICENSE` folder.