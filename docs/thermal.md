# FLIR thermal images and recordings

Choose **Tools → FLIR Thermal Images and Video…** and open an original
radiometric `.jpg`/`.jpeg` or `.csq` recording. Ordinary JPEG previews and MP4
exports do not provide the per-pixel calibration data this tool requires.

The viewer displays the native thermal sensor image, rather than the camera's
visible-light or MSX composite. It shows minimum, maximum and mean temperatures
in Celsius, Fahrenheit or Kelvin. Move the pointer over the image to read a pixel's
temperature. Use the
frame slider, frame number, or Previous/Next buttons to browse a recording.
Displayed frame numbers start at 1; exported filenames use zero-based indices,
matching the existing video extraction tool.

The **Display** tab offers Iron, White hot, Black hot and Rainbow palettes.
Iron runs from dark blue/purple through red, orange and yellow to white.
**Lower display limit** and **Upper display limit** have sliders and numeric
inputs. Temperatures outside this interval use the palette's endpoint colours.
**Temperature linear** maps colours directly to the temperature interval;
**Histogram equalization** improves contrast using the distribution of valid
in-range temperatures. These controls do not change measurements. Invalid
temperature pixels are black and excluded from statistics; in grayscale palettes,
valid endpoint pixels can also be black, so use the pointer readout to distinguish them.

**Keep scale across frames** holds the display interval fixed while browsing.
Turn it off to fit each newly loaded frame, or click **Fit scale to this frame**
at any time. A constant-temperature frame gets a small nonzero display interval.

**Mark coldest / hottest pixels** adds cyan and red crosses respectively.
**Green isotherm highlight** selects temperatures at/above a threshold, at/below
a threshold, or within an inclusive interval. Its coverage readout reports the
selected fraction of valid pixels, independent of palette clipping.

## Measurement and analysis

Choose **Spot**, **Box**, **Circle** or **Line** above the viewer. Click to place
a spot; drag for the other tools. A circle drag runs from its centre to its
radius. Measurements remain in sensor coordinates and can be compared across
frames in the same recording. Opening a different source clears viewer
measurements and parameter overrides.

The **Measure** tab lists minimum, maximum and mean temperatures for each
measurement. Select a **Temperature difference reference** to show each mean's
signed difference from the reference mean. Fahrenheit differences are scaled
without applying the absolute-temperature offset. Select a line's table row to
see its temperature profile or export that profile as CSV with x/y coordinates,
distance in pixels and temperatures. **Remove viewer measurements** clears
measurements placed in the viewer.

While annotating an exported frame, select ordinary Labelme Shapes to measure
them in the same table. Points, rectangles, circles, lines, polygons and oriented
rectangles are supported. Shape editing refreshes the measurements. Area
measurements include pixel centres within the geometry; lines sample the
clipped segment in drawing order. Invalid pixels are excluded from statistics.
Measurements outside the image can have no valid pixels, shown as dashes.

The **Parameters** tab allows whole-frame correction of emissivity, object
distance, reflected apparent temperature, atmospheric temperature, relative
humidity, IR-window transmission and IR-window temperature. Parameter
temperature inputs are explicitly in °C. Click **Apply Measurement Parameters**
to recalculate from the preserved raw sensor values. Invalid settings leave the
previous calculation intact. **Restore Camera Parameters** returns to the
original recorded environment settings; factory calibration is never edited.

## Extraction and annotation

- **Save Current Frame…** creates a new `extracted_frames` folder containing
  the displayed PNG and a matching `.thermal.npz` temperature file.
- **Save and Open for Annotation…** also opens the exported folder in Labelme.
  Existing unsaved annotations go through Labelme's normal save/discard prompt.
- **Extract Recording Frames…** opens the usual extraction dialog with this CSQ
  selected and applies the current palette, interval, isotherm, markers and
  measurement parameters to every output frame. Raw sensor values and original
  camera parameters are retained.
- **Tools → Extract Video Frames…** also accepts CSQ alongside MP4 and AVI.
  Percentage/count, evenly spaced/random sampling, shared/separate folders,
  cancellation, and unique output folders work as for normal videos. For a CSQ
  opened here, the first selected frame sets a fixed palette interval.

**Keep each PNG and its `.thermal.npz` file together, with matching basenames.**
The temperature file retains the original 16-bit sensor values, calculated
temperatures, calibration/environmental metadata, source path and source frame
index. It is separate from Labelme's annotation JSON. Its image checksum guards
against accidentally pairing temperature measurements with an edited image.
PNG snapshots can be viewed normally without the temperature file.

Opening an exported PNG in Labelme automatically shows the **Thermal
Temperatures** panel. The same analysis controls remain available while
drawing Shapes. Changes preserve Shape coordinates, mark the Annotation
as changed, and save the display interval in `thermal_display_celsius` and
analysis settings in `thermal_analysis` in the Annotation File. Reopening the
Annotation restores the palette, units, isotherm, parameters and viewer
measurements. Internally temperatures and display intervals remain Celsius. The exported
PNG remains the colour snapshot made at extraction time. Brightness/contrast is
disabled for a thermal frame so the displayed colours retain their temperature
meaning. Use **View → Thermal Temperatures** to reopen the panel if closed.

## Exports

The **Export** tab provides a temperature matrix CSV and a self-contained HTML
report, using the current temperature units and measurement parameters.

- Matrix CSV: x coordinates in the header, y coordinates in the first column,
  six decimal places, blank cells for invalid temperatures. Palette changes do
  not affect these values.
- HTML report: colour image with numbered measurements, display interval,
  minimum/maximum/mean values, mean differences and source/calculation metadata.
  Open it in a browser to view, print, or save as PDF using the browser's print dialog.
- Line profile CSV is available from the **Measure** tab.

Changing palettes or parameters does not overwrite original camera files or
previously exported PNG snapshots. Save a new current frame to create a new
image/temperature pair with the current analysis state.

## Compatibility and interpretation

The reader supports FLIR FFF sensor/calibration records embedded in radiometric
JPEGs or CSQ recordings, with uncompressed 16-bit, PNG or JPEG-LS sensor data.
Compressed CSQ frames require `ffmpeg` on PATH; no FLIR SDK or ExifTool is
required. Existing MP4/AVI extraction still requires FFmpeg 5.1+ and ffprobe.
Unsupported/missing calibration is reported rather than assigning temperatures
from the visible image's colours.

Temperatures use the file's recorded factory Planck calibration, emissivity,
object distance, relative humidity, atmospheric temperature, reflected apparent
temperature and infrared-window transmission/temperature. These parameters are
editable in the Parameters tab. Results depend on these settings and
the validity of the calibration. Camera-specific processing may differ from
FLIR software; compare a known reference before using measurements for analysis.

Indexing runs in a cancellable worker and keeps only recording offsets in
memory. A malformed frame stops indexing and produces a warning: only preceding
complete frames are available. Extraction surfaces that warning in its results.
Cancelling extraction discards the unfinished recording's staged output and
keeps already completed recordings.

## Public validation samples

[Glenn Tattersall's ThermImageJ SampleFiles.zip](https://github.com/gtatters/ThermImageJ/blob/master/SampleFiles.zip)
contains `SampleJPG.jpg` (SC660), `SampleFLIRONE.jpg`, and `SampleCSQ.csq`
(T1030sc). These public samples were used for local decoder/viewer checks and
are not included in the repository. The CSQ has seven complete frames followed
by a truncated frame, useful for checking the warning and partial recovery.

Format references:
[ExifTool FLIR tags](https://exiftool.org/TagNames/FLIR.html) and
[Thermimage radiometric conversion](https://github.com/gtatters/Thermimage/blob/master/R/raw2temp.R).

See [the Thermal Studio feature research](thermal-studio-research.md) for the
scope and official product references used to choose these functions.
