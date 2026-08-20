> [!IMPORTANT]
> This project is a fork of [Labelme](https://github.com/wkentaro/labelme) by
> [Kentaro Wada](https://github.com/wkentaro). The original repository is
> available at <https://github.com/wkentaro/labelme>.
>
> This fork is maintained by [Alfiethology](https://github.com/alfiethology) and
> adds:
>
> - animal pose annotation with reusable skeleton templates, keypoint visibility,
>   rotation and YOLO pose export;
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
- Move, resize and rotate complete skeletons while retaining editable joints.
- Save skeleton layouts as reusable `.skeleton.json` templates.
- Export annotated directories as Ultralytics-compatible YOLO pose datasets.

See [Animal pose annotation](docs/pose-estimation.md) for the complete workflow.

### Model-assisted review and refinement

- Load a custom Ultralytics `.pt` model and run it on the current image.
- Pre-label a directory, review predicted shapes and save only corrected frames.
- Sample every _n_th frame from a video, skip easy frames and retain difficult or
  corrected examples as images with Labelme JSON annotations.
- Configure the model confidence threshold directly in the toolbar.

### Faster manual editing

- Snap new polygon vertices to points in existing annotations.
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

### Use a custom YOLO model

1. In the **Custom YOLO Detector** toolbar panel, choose an Ultralytics `.pt`
   model and set the confidence threshold.
1. Open an image and select **Run** to add the model's predictions to the current
   annotation.
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
1. Select **Finish Skeleton**, or press Enter or Space. The mirror-pairs box is
   optional: leave it empty if you do not need it. Otherwise, enter pairs such
   as `left_eye,right_eye`, one pair per line.
1. Adjust the finished skeleton if needed. Drag a point to move just that
   point, drag a box corner to resize the whole skeleton, or drag the round
   handle above the box to rotate it.
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
  select a finished skeleton and choose
  **Pose > Save Selected Skeleton As Template…**. On another image, use
  **Pose > Place Skeleton From File…**, then move its points onto the new
  animal.

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
