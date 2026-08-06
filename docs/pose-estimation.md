# Animal pose annotation

Labelme can store an animal pose as a **Skeleton Shape** and reuse its layout
through a **Skeleton Template**. The representation is designed to export to
the [Ultralytics YOLO pose dataset format](https://docs.ultralytics.com/datasets/pose).

## Create and reuse a skeleton

1. Open an image and choose **Pose > Draw Skeleton…**, then enter the animal
   class Label.
2. Keep **Place Nodes** selected. Click each joint on the animal and name it in
   the dialog that appears. Click order becomes the keypoint order in YOLO
   exports.
3. Select **Connect Nodes**, then click the two endpoints of each bone. Clicking
   an already-connected pair removes that bone.
4. Use **Undo Step** to remove the most recently placed node or bone when
   needed.
5. Select **Finish Skeleton** (or press Enter/Space). Optionally enter horizontal
   mirror pairs such as `left_eye,right_eye`, one pair per line. Press Escape or
   select **Cancel** to discard the draft.
6. Labelme creates a bounding box around the nodes. Drag a corner to stretch the
   whole pose: the box, joints, and bones scale together. Drag the circular
   handle above the box to rotate the entire pose. Drag an individual joint to
   refine just that joint.
7. Select one Skeleton Shape and use **Pose > Set Keypoint Visibility…**. Choose
   **Occluded (1)** when the joint is hidden but its position can still be
   inferred and annotated; choose **Missing (0)** when it cannot be located or
   lies outside the image. Occluded joints are shown in red and missing joints
   and their connected bones are hidden. Choose **Visible (2)** to restore one.
8. With the Skeleton Shape selected, choose
   **Pose > Save Selected Skeleton As Template…**.
9. On another image, choose **Pose > Place Skeleton From File…**, then adjust
   the box and joints for that animal.

The template uses the suffix `.skeleton.json`. A placed Skeleton Shape embeds
its keypoint definition in the Annotation File, so annotations remain loadable
if the original template is renamed or removed.

## Skeleton Template format

```json
{
  "version": 1,
  "label": "hen",
  "keypoints": ["beak", "left_foot", "right_foot"],
  "edges": [[0, 1], [0, 2]],
  "positions": [[0.5, 0.1], [0.25, 0.9], [0.75, 0.9]],
  "flip_idx": [0, 2, 1]
}
```

`positions` are normalized to the template bounding box. `flip_idx` maps each
keypoint index to its horizontal mirror; self-mapping is valid for midline
points and for skeletons where horizontal-flip augmentation is not used.

## YOLO pose compatibility

Each Skeleton Shape contains the data needed for one YOLO pose row:

```text
class x_center y_center width height x1 y1 visibility1 ... xN yN visibilityN
```

Coordinates are normalized during export. Keypoint visibility follows the
standard three-state convention: `0` missing, `1` labeled but occluded, and `2`
visible. Missing keypoints export as `0 0 0`. The on-screen transform box may
be rotated; YOLO receives the axis-aligned box enclosing it.

Ultralytics uses one dataset-wide `kpt_shape` and `flip_idx`. If a dataset has
multiple animal classes, their Skeleton Templates must currently have the same
number of keypoints and the same flip mapping.

## Export a training dataset

Choose **Pose > Export YOLO Pose Dataset…**, then select the directory containing
the Annotation Files and an empty output directory. Labelme recursively finds
Annotation Files, ignores `.skeleton.json` templates, and creates:

```text
dataset/
├── data.yaml
├── images/
│   ├── train/
│   └── val/
├── labels/
│   ├── train/
│   └── val/
└── skeletons/
```

The split is deterministic: 20% of images are assigned to validation (at least
one train and one validation image when the dataset contains more than one
image). Images without a Skeleton Shape are retained as negative samples. For a
single-image dataset, `data.yaml` uses the training image as validation data too.

Train from the exported directory with an Ultralytics pose checkpoint, for
example:

```bash
yolo pose train data=/path/to/dataset/data.yaml model=yolo26n-pose.pt epochs=100 imgsz=640
```

The exporter refuses a non-empty output directory so it cannot silently
overwrite an existing dataset.
