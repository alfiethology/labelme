> [!IMPORTANT]
> This project is a fork of [Labelme](https://github.com/wkentaro/labelme) by
> [Kentaro Wada](https://github.com/wkentaro). The original repository is
> available at <https://github.com/wkentaro/labelme>.
>
> This fork is maintained by [Alfiethology](https://github.com/alfiethology) and
> adds:
>
> - animal pose annotation with reusable skeleton templates, keypoint visibility,
>   fixed-orientation bounding boxes and YOLO pose export;
> - custom Ultralytics YOLO inference plus review-and-refine workflows for image
>   directories and sampled video frames; and
> - faster manual annotation through point snapping, streamlined point editing,
>   improved vertex insertion and zoom fixes.

<h1 align="center">
  <img src="labelme/icons/icon-256.png" width="200" height="200"><br/>labelme
</h1>

<h4 align="center">
  Animal-focused image, video and pose annotation with Python.
</h4>

<div align="center">
  <a href="https://github.com/alfiethology/labelme/actions/workflows/test.yml"><img src="https://github.com/alfiethology/labelme/actions/workflows/test.yml/badge.svg?branch=main&event=push" alt="Tests"></a>
  <a href="https://github.com/alfiethology/labelme/actions/workflows/lint.yml"><img src="https://github.com/alfiethology/labelme/actions/workflows/lint.yml/badge.svg?branch=main&event=push" alt="Lint"></a>
  <a href="https://github.com/alfiethology/labelme"><img src="https://img.shields.io/badge/fork-Alfiethology-blue" alt="Alfiethology fork"></a>
</div>

<div align="center">
  <a href="#about-this-fork"><b>About this fork</b></a>
  | <a href="#fork-highlights"><b>Fork highlights</b></a>
  |
  <a href="#installation"><b>Installation</b></a>
  | <a href="#usage"><b>Usage</b></a>
  | <a href="#examples"><b>Examples</b></a>
</div>

<br/>

<div align="center">
  <img src="examples/instance_segmentation/.readme/annotation.jpg" width="70%">
</div>

## About this fork

This repository extends the original Labelme desktop application for
animal-behaviour and pose-estimation datasets. It keeps Labelme's familiar Qt
annotation interface and JSON format while adding workflows for skeleton
keypoints, model-assisted review and large collections of recorded frames.

The upstream project remains the right place for general Labelme documentation,
releases and community support. Issues concerning the features described under
**Fork highlights** should be reported in this repository.

## Fork highlights

### Animal pose annotation

- Draw named skeleton keypoints and connect them into bones.
- Mark individual keypoints as visible, occluded or missing.
- Move and resize complete skeletons while retaining editable joints.
- Save skeleton layouts as reusable `.skeleton.json` templates.
- Export annotated directories as Ultralytics-compatible YOLO pose datasets.

See [Animal pose annotation](docs/pose-estimation.md) for the complete workflow.

### Model-assisted review and refinement

- Load a custom Ultralytics `.pt` model and run it on the current image.
- Pre-label a directory, review predicted shapes and save only corrected frames.
- Sample every \_n_th frame from a video, skip easy frames and retain difficult or
  corrected examples as images with Labelme JSON annotations.
- Configure the model confidence threshold directly in the toolbar.

### Faster manual editing

- Snap new and existing polygon vertices to points in other annotations, then
  drag coincident polygon vertices together while snapping remains enabled.
- [Review existing annotations with Change Labels](#review-existing-annotations-with-change-labels)
  using configurable, multi-character keyboard sequences.
- Enter point-drawing mode with the `P` shortcut and remove points quickly while
  editing.
- Insert polygon vertices from edge interactions.
- Use corrected and more predictable canvas zoom behaviour.

## Upstream Labelme features

Labelme is a graphical image annotation tool inspired by
<http://labelme.csail.mit.edu>. It is written in Python and uses Qt for its
graphical interface.

<img src="examples/instance_segmentation/data_dataset_voc/JPEGImages/2011_000006.jpg" width="19%" /> <img src="examples/instance_segmentation/data_dataset_voc/SegmentationClass/2011_000006.png" width="19%" /> <img src="examples/instance_segmentation/data_dataset_voc/SegmentationClassVisualization/2011_000006.jpg" width="19%" /> <img src="examples/instance_segmentation/data_dataset_voc/SegmentationObject/2011_000006.png" width="19%" /> <img src="examples/instance_segmentation/data_dataset_voc/SegmentationObjectVisualization/2011_000006.jpg" width="19%" />\
<i>VOC dataset example of instance segmentation.</i>

<img src="examples/semantic_segmentation/.readme/annotation.jpg" width="30%" /> <img src="examples/bbox_detection/.readme/annotation.jpg" width="30%" /> <img src="examples/classification/.readme/annotation_cat.jpg" width="35%" />\
<i>Other examples (semantic segmentation, bbox detection, and classification).</i>

<img src="https://user-images.githubusercontent.com/4310419/47907116-85667800-de82-11e8-83d0-b9f4eb33268f.gif" width="30%" /> <img src="https://user-images.githubusercontent.com/4310419/47922172-57972880-deae-11e8-84f8-e4324a7c856a.gif" width="30%" /> <img src="https://user-images.githubusercontent.com/14256482/46932075-92145f00-d080-11e8-8d09-2162070ae57c.png" width="32%" />\
<i>Various primitives (polygon, rectangle, circle, line, and point).</i>

<img src="https://github.com/user-attachments/assets/53bf09db-b097-48b7-9f32-ab490da5ac53" width="32%" />
<p><i>Multi-language support (English, 中文, 日本語, 한국어, Deutsch, Français, and more).</i></p>

- [x] Image annotation for polygon, rectangle, circle, line and point ([tutorial](examples/tutorial))
- [x] Image flag annotation for classification and cleaning ([#166](https://github.com/wkentaro/labelme/pull/166))
- [x] Video annotation ([video annotation](examples/video_annotation))
- [x] GUI customization (predefined labels / flags, auto-saving, label validation, etc) ([#144](https://github.com/wkentaro/labelme/pull/144))
- [x] Exporting VOC-format dataset for [semantic segmentation](examples/semantic_segmentation), [instance segmentation](examples/instance_segmentation)
- [x] Exporting COCO-format dataset for [instance segmentation](examples/instance_segmentation)
- [x] AI-assisted point-to-polygon/mask annotation by SAM, EfficientSAM models
- [x] AI text-to-annotation by YOLO-world, SAM3 models

**🌏 Available in 20 languages** - English · 日本語 · 한국어 · 简体中文 · 繁體中文 · Deutsch · Ελληνικά · Français · Español · Italiano · Português · Nederlands · Magyar · Русский · ไทย · Tiếng Việt · Türkçe · Українська · Polski · فارسی (`LANG=ja_JP.UTF-8 labelme`)

## Installation

The GitHub source is currently the canonical distribution of this fork. PyPI,
labelme.io and Linux distribution packages provide the upstream project and do
not necessarily contain the fork features listed above.

> [!IMPORTANT]
> This fork requires **Python 3.12, 3.13 or 3.14**. Check the interpreter that
> will perform the installation with `python --version`; Python 3.11 and older
> cannot install the current version.

If you use Conda, create and activate a compatible environment first:

```bash
conda create --name labelme-env python=3.12 -y
conda activate labelme-env
python --version  # should report Python 3.12.x
```

### Install this fork from GitHub

Using `uv`:

```bash
git clone https://github.com/alfiethology/labelme.git
cd labelme
uv sync
uv run labelme
```

Or install the current fork directly with `pip`:

```bash
python -m pip install "labelme @ git+https://github.com/alfiethology/labelme.git"
labelme
```

For a previously cloned development checkout, `launch_labelme.sh` starts the
application with that checkout's `.venv`:

```bash
uv sync
./launch_labelme.sh
```

### Install upstream Labelme

If you do not need this fork's pose and refinement workflows, install the
upstream release from PyPI:

```bash
python -m pip install labelme
```

For more detail, see
[Install Labelme using Terminal](https://www.labelme.io/docs/install-labelme-terminal).

### Upstream standalone executable

If you're willing to invest in the convenience of simple installation without any dependencies (Python, Qt),
you can download the standalone executable from ["Install Labelme as App"](https://www.labelme.io/docs/install-labelme-app).

This executable is produced by the upstream project and may not include this
fork's features.

### Upstream Linux distribution packages

On some Linux distributions, labelme is also packaged in the system's native repository and can be installed with the distribution's standard package tooling. The badge below tracks which distributions currently ship labelme and which version each one provides:

[![Packaging status](https://repology.org/badge/vertical-allrepos/labelme.svg)](https://repology.org/project/labelme/versions)

### Supported Python and platforms

|        | Supported (v7.x)               | Maintenance (v6.3.x) |
| ------ | ------------------------------ | -------------------- |
| Python | 3.12 - 3.14                    | 3.10 - 3.11          |
| Qt     | Qt6 (PySide6)                  | Qt5                  |
| OS     | 64-bit macOS / Windows / Linux | older OSes           |

labelme follows [SPEC 0](https://scientific-python.org/specs/spec-0000/) (the successor to [NEP 29](https://numpy.org/neps/nep-0029-deprecation_policy.html)) for dropping Python versions, in step with its core scientific dependencies (numpy, scipy, scikit-image). v6.3.x is the maintenance line for Qt5 and Python 3.10 / 3.11 stragglers.

v6.3.x receives critical fixes only, on a best-effort basis with no release cadence or SLA. "Critical" is limited to:

- security vulnerabilities,
- data-loss or annotation-corruption bugs,
- install or launch breakage caused by upstream dependency drift.

Feature backports and non-critical bugs are out of scope; all new development happens on v7.x.

### Upgrading from v6.x to v7

v7.0.0 raises the platform floor:

- **Qt binding:** the GUI moved from PyQt5 (Qt5) to PySide6 (Qt6). `pip install labelme` now pulls PySide6 instead of PyQt5.
- **Python:** the minimum is now Python 3.12 (3.10 and 3.11 are dropped).
- **OS:** Qt6 requires a 64-bit macOS, Windows, or Linux; older OSes that only Qt5 supported are no longer covered.
- **No public Python API:** labelme is an application, not a library, and exposes no stable Python API. Its internal modules were privatized in v7 (renamed to underscore-prefixed names), so `import labelme.app`, `labelme.utils`, `labelme.widgets`, and similar imports no longer work. If you previously imported labelme internals, pin `labelme<7` and vendor the code you need; see [`examples/utils.py`](examples/utils.py) for copy-and-adapt reference code that reads the JSON annotation format without depending on labelme.

If you need to stay on PyQt5/Qt5, Python 3.10 or 3.11, or an older OS, pin to the v6.3.x maintenance line:

```bash
pip install 'labelme<7'
```

All previous releases remain installable from [PyPI](https://pypi.org/project/labelme/#history), so existing pins keep working.

v7.0.0 also changes config parsing:

- **Config booleans:** `~/.labelmerc` is now parsed with ruamel.yaml (YAML 1.2), so the boolean spellings `yes`/`no`/`on`/`off` (in any capitalization) are read as strings rather than booleans. If you set any boolean option this way, switch it to `true`/`false`.

### Public interface

labelme is an application. The interfaces you can build on and that we keep stable are:

- the **command-line interface** (`labelme ...`),
- the **on-disk JSON annotation format**, and
- the **`~/.labelmerc` config format**.

Everything else, including the Python import surface, is internal and may change or be renamed without notice. To consume annotations from your own code, read the JSON format directly (see [`examples/utils.py`](examples/utils.py)).

## Usage

Run `labelme --help` for detail.\
The annotations are saved as a [JSON](http://www.json.org/) file.

To align polygon edges precisely, enable **Edit > Snap to Existing Points**;
new polygon vertices will snap onto nearby vertices in existing annotations.
In edit mode, an existing polygon vertex also snaps into the exact position of a
nearby existing point. Dragging either of two polygon vertices already at the
same position then moves both vertices together while this option remains
enabled.

```bash
labelme  # just open gui

# tutorial (single image example)
cd examples/tutorial
labelme apc2016_obj3.jpg  # specify image file
labelme apc2016_obj3.jpg --output annotations/  # save annotation JSON files to a directory
labelme apc2016_obj3.jpg --with-image-data  # include image data in JSON file
labelme apc2016_obj3.jpg \
  --labels highland_6539_self_stick_notes,mead_index_cards,kong_air_dog_squeakair_tennis_ball  # specify label list

# semantic segmentation example
cd examples/semantic_segmentation
labelme data_annotated/  # Open directory to annotate all images in it
labelme data_annotated/ --labels labels.txt  # specify label list with a file
```

### Review existing annotations with Change Labels

**Tools > Change Labels…** is a keyboard-driven review mode for correcting the
labels on existing shapes. It keeps the normal image and editable shapes on the
main canvas, selects one shape at a time, and lets you replace its label by
typing a short code. It is useful for reviewing model predictions or cleaning a
large annotated image directory without repeatedly opening the label dialog.

Change Labels uses a separate shortcut file. This is not the same file as the
normal `--labels` file: a Change Labels file maps every allowed label to the
letter-and-number sequence you want to type.

#### 1. Create a label shortcut file

Create a UTF-8 text or CSV file with one `label,shortcut` pair per line. For
example, save the following as `bird-review.txt`:

```text
# label,shortcut
Great_tit,gt
Blue_tit,bt
Long_tailed_tit,ltt
Robin,r
Unknown_bird,u1
```

The first column is the exact label that will be written into the Labelme JSON
shape. The second column is the sequence you will type. In this example, type
`g`, then `t`, then Enter or Space to assign `Great_tit`.

The shortcut-file rules are:

- Every non-comment row must contain exactly two comma-separated columns:
  `label,shortcut`.
- A label must not be empty. Labels may contain spaces, underscores and other
  characters supported by Labelme. Quote a label containing a comma according
  to normal CSV syntax, for example `"Tern, common",tc`.
- A shortcut must contain one or more ASCII letters (`a`-`z`, `A`-`Z`) or digits
  (`0`-`9`) and nothing else. Sequences such as `g`, `gt`, `bird2` and `123` are
  valid. Spaces, punctuation, underscores and modifier-key notation such as
  `Ctrl+G` are not valid shortcuts.
- Shortcut length is not limited. Short sequences are usually faster to review
  and easier to remember.
- Matching is case-insensitive. `gt`, `GT` and typing `G` followed by `t` all
  refer to the same shortcut, so they cannot be assigned to different labels.
- Each label and each case-insensitive shortcut must be unique in the file.
- Empty lines are ignored. A line whose first field starts with `#` (allowing
  leading whitespace) is treated as a comment.
- Do not add a header row unless you want `label,shortcut` itself to become a
  real mapping. A comment such as `# label,shortcut` is safe.

Single-character shortcuts are still supported, but they must also be confirmed
with Enter or Space. This makes overlapping mappings unambiguous. For example,
the following is valid:

```text
Gull,g
Great_tit,gt
```

Type `g`, then Enter to choose `Gull`; type `g`, `t`, then Enter to choose
`Great_tit`. Labelme does not apply `Gull` as soon as the first `g` is typed.

#### 2. Open the images and annotations

Open the directory you want to review with **File > Open Dir**, or pass it when
starting Labelme:

```bash
labelme /home/user/current_working_labelling_directory
```

The images should already have Labelme JSON annotations if labels are to be
changed. By default, each JSON file is beside its corresponding image. A
separate labels directory also works; choose it with **File > Change Output
Directory** or `--output`:

```bash
labelme /home/user/review_job/images --output /home/user/review_job/annotations
```

Change Labels follows the order shown in Labelme's **File List**. Select the
image where review should begin before starting the mode. If an image has no
shapes, there is nothing to relabel; press Space to save if necessary and move
to the next image, or Shift+Space to move it to the skipped directory.

#### 3. Start Change Labels

1. With an image open, choose **Tools > Change Labels…**.
1. Select the shortcut file created above. The file chooser accepts `.txt` and
   `.csv` files, as well as other extensions through **All files**.
1. Labelme switches the canvas to edit mode and selects the first shape in the
   current image. The status bar lists the configured mappings and shows the
   sequence typed so far.

An invalid file is rejected before review starts. The error identifies the line
with a missing column, empty label, invalid shortcut, duplicate label or
duplicate shortcut, so the file can be corrected and selected again.

#### 4. Review shapes and images

For each selected shape, type its shortcut and confirm it. Nothing is changed
while the sequence is merely being typed.

| Input                                 | Result                                                                                                                                        |
| ------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------- |
| Letter or number                      | Append it to the pending shortcut shown in the status bar.                                                                                    |
| Enter or Space, with a sequence typed | Apply the matching label and select the next shape. After the final shape, save the annotation and open the next image automatically.         |
| Backspace                             | Remove the last character from the pending shortcut.                                                                                          |
| Enter, with no sequence typed         | Keep the selected shape's current label and select the next shape.                                                                            |
| Space, with no sequence typed         | Save the current image immediately and open the next image, even if some shapes were not reviewed.                                            |
| Shift+Space                           | Save the current annotation, move the image and JSON to `skipped_images`, remove the image from the current file list and load its successor. |
| Escape                                | Exit Change Labels mode. The current image stays open, and changes already made remain available to save or undo normally.                    |

If the confirmed sequence does not exactly match a configured shortcut, Labelme
does not change the shape or advance. The status bar reports the unknown
sequence. Use Backspace to correct it, or press Escape to leave review mode.

An image may contain any number of shapes. Change Labels reviews them one by
one, using the yellow selection shown on the normal canvas. You can still use
the mouse to inspect, move or resize shapes while reviewing. Plain letters and
numbers are reserved for the pending shortcut while this mode is active,
including letters that are normally Labelme shortcuts; Ctrl-, Alt- and
Meta-modified application shortcuts remain available.

When a valid shortcut is confirmed on the final shape, Labelme saves the JSON
and advances to the next image automatically. If saving fails, the image is not
advanced, allowing the filesystem or annotation problem to be corrected without
silently losing the edit. At the final image in the file list, Labelme saves it
and reports that the end has been reached.

#### Skipping an image

Shift+Space is intended for an image that should be removed from the current
review set rather than assigned a label. Labelme moves both the image and its
JSON annotation into a directory named `skipped_images`. That directory is a
**sibling of the current labels directory**, not a child of it. Keeping it
outside the active directory tree prevents a recursive directory session from
finding the skipped image again.

When images and labels share one directory:

```text
/home/user/current_working_labelling_directory/
    frame001.jpg
    frame001.json
/home/user/skipped_images/
    skipped_frame.jpg
    skipped_frame.json
```

When images and labels are separate:

```text
/home/user/review_job/images/
/home/user/review_job/annotations/
/home/user/review_job/skipped_images/
```

The destination is calculated from the directory containing the current JSON
annotation. If the JSON does not exist yet or has unsaved changes, Labelme first
writes it so the skipped image always travels with an annotation. The
`skipped_images` directory is created automatically and reused for later skips.

Labelme never overwrites a skipped file. If either destination filename already
exists, the skip is cancelled and an error identifies the collision. Rename or
move the existing file, then press Shift+Space again. A successful skip removes
the image from the current **File List** before loading the next available
image, so the review cannot cycle back to a file that was already skipped.

### Use a custom YOLO model

1. In the **Custom YOLO Detector** toolbar panel, choose an Ultralytics `.pt`
   model and set the confidence threshold.
1. Open an image and select **Run** to add the model's predictions to the current
   annotation.
   Detection models create rectangles, instance- and semantic-segmentation models
   create polygons, OBB models create oriented rectangles, and pose models create
   skeletons. **Point gap** controls the approximate spacing, in image pixels,
   between vertices of generated polygons.
1. To review a collection instead, choose **Refine > From Frames…** and select
   an image directory. Correct useful predictions with **SAVE AND NEXT**, or
   skip frames that do not need attention.
1. For recorded footage, choose **Refine > From Video…**, select a video and
   choose the sampling interval. Refined frames and their JSON annotations are
   written to `<video-name>_refined_frames` beside the video.

### Draw and save a skeleton

A skeleton is a set of named points, such as `nose`, `left_eye`, and
`right_knee`, joined by lines called bones.

1. Open an image, then choose **Pose > Draw Skeleton…**.
1. Enter the kind of animal you are marking, such as `dog` or `hen`.
1. Leave **Place Nodes** selected. Click each body point and give it a short,
   unique name. The order you add the points is also their order in a YOLO pose
   export.
1. Select **Connect Nodes**. Click one point and then another to draw a bone
   between them. Repeat for the other bones.
1. To correct a name, select **Rename Nodes** and click the node to rename.
1. Select **Finish Skeleton**, or press Enter or Space. The mirror-pairs box is
   optional: leave it empty if you do not need it. Otherwise, enter pairs such
   as `left_eye,right_eye`, one pair per line. A file browser then asks where
   to save the new reusable `.skeleton.json` template. Cancelling this browser
   keeps the skeleton annotation but skips saving the template.
1. Adjust the finished skeleton if needed. Drag a point to move just that
   point, or drag a box corner to adjust only the box while the keypoints stay
   stationary. Skeleton bounding boxes remain axis-aligned to match YOLO pose
   labels.
1. Save the annotation with **File > Save** (Ctrl+S). Auto Save is on by
   default, so Labelme will normally save it as soon as you finish drawing.

The finished skeleton is stored in the normal annotation file for that image.
For example, a skeleton drawn on `hen.jpg` is normally saved in `hen.json` next
to the image. If you chose a different annotation directory with
**File > Change Output Directory** or `--output`, the JSON file is saved there
instead.

The annotation file and a skeleton template are different:

- `hen.json` stores the skeleton you placed on one particular image.
- A file ending in `.skeleton.json` is a reusable blank layout. To make one,
  save it in the file browser shown after drawing a new skeleton, or select a
  finished skeleton and choose **Pose > Save Selected Skeleton As Template…**.
  On another image, use **Pose > Place Skeleton From File…**, then move its
  points onto the new animal.

To revise an existing template, choose **Pose > Edit Skeleton Template…** and
open its `.skeleton.json` file. Labelme displays it on the current image and
opens the skeleton toolbar. Use **Place Nodes**, **Connect Nodes**, or
**Rename Nodes**, then select **Finish Skeleton** to add the result to the
annotation and write the changed layout back to the same template file.

### Quick-draw skeleton annotations

Once you have a `.skeleton.json` template, **Quick-Draw Skeleton** avoids naming
and connecting the same points for every animal:

1. Open an image and choose **Quick-Draw Skeleton** from the left toolbar or
   **Pose > Quick-Draw Skeleton…**.
1. Choose a remembered template, or select **Browse for Template…**.
1. Click the animal's keypoints in the order shown in the status bar. This is
   the `keypoints` order stored in the template and used by the YOLO pose
   export. Node names and bones appear automatically as points are placed.
1. After the final node, drag a bounding box around the complete animal. The
   horizontal and vertical cursor guides work like rectangle drawing. The box
   must contain every placed keypoint.

Use Ctrl+Z to undo the last point and Escape to cancel the draft. To make dense
skeletons easier to see, use **Pose > Set Node Marker Size…** and
**Pose > Set Node Label Size…**. These display settings persist between Labelme
sessions and do not change the saved coordinates or YOLO export.

To mark a point as visible, hidden, or missing, right-click it. For more detail,
including how to export a YOLO pose dataset, see
[Animal pose annotation](docs/pose-estimation.md).

### Command Line Arguments

- `--output` specifies the location that annotations will be written to. If the location ends with .json, a single annotation will be written to this file. Only one image can be annotated if a location is specified with .json. If the location does not end with .json, the program will assume it is a directory. Annotations will be stored in this directory with a name that corresponds to the image that the annotation was made on.
- The first time you run labelme, it will create a config file at `~/.labelmerc`. Add only the settings you want to override. For all available options and their defaults, see [`default_config.yaml`](labelme/_config/default_config.yaml). If you would prefer to use a config file from another location, you can specify this file with the `--config` flag.
- Without the `--no-sort-labels` flag, the program will list labels in alphabetical order. When the program is run with this flag, it will display labels in the order that they are provided.
- Flags are assigned to an entire image. [Example](examples/classification)
- Labels are assigned to a single polygon. [Example](examples/bbox_detection)

### FAQ

- **How to convert JSON file to numpy array?** See [examples/tutorial](examples/tutorial#convert-to-dataset).
- **How to load label PNG file?** See [examples/tutorial](examples/tutorial#how-to-load-label-png-file).
- **How to get annotations for semantic segmentation?** See [examples/semantic_segmentation](examples/semantic_segmentation).
- **How to get annotations for instance segmentation?** See [examples/instance_segmentation](examples/instance_segmentation).

## Examples

- [Image Classification](examples/classification)
- [Bounding Box Detection](examples/bbox_detection)
- [Semantic Segmentation](examples/semantic_segmentation)
- [Instance Segmentation](examples/instance_segmentation)
- [Video Annotation](examples/video_annotation)

## How to build standalone executable

```bash
LABELME_PATH=./labelme
OSAM_PATH=$(python -c 'import os, osam; print(os.path.dirname(osam.__file__))')
pyinstaller labelme/labelme/__main__.py \
  --name=Labelme \
  --windowed \
  --noconfirm \
  --specpath=build \
  --add-data=$(OSAM_PATH)/_models/yoloworld/clip/bpe_simple_vocab_16e6.txt.gz:osam/_models/yoloworld/clip \
  --add-data=$(LABELME_PATH)/_config/default_config.yaml:labelme/_config \
  --add-data=$(LABELME_PATH)/icons/*:labelme/icons \
  --add-data=$(LABELME_PATH)/translate/*:translate \
  --icon=$(LABELME_PATH)/icons/icon-256.png \
  --onedir
```

## Acknowledgement

This repo is the fork of [wkentaro/labelme](https://github.com/wkentaro/labelme).
