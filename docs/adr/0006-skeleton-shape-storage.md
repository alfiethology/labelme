# Store each pose instance as one composite Skeleton Shape

A pose instance must remain one Shape through editing, Annotation File
round-trips, copying, and export. A Skeleton Shape therefore uses
`shape_type: skeleton`; its first four points are an oriented transform box,
and its remaining points are keypoints in the template's declared order. The
Shape's `other_data.pose` embeds keypoint names, bone edges,
horizontal-flip indices, and visibility values.

The reusable Skeleton Template is a separate, versioned `.skeleton.json` file.
It contains normalized neutral keypoint positions so it can be placed into an
arbitrary image-space bounding box. Placing a template copies its complete
definition into the new Skeleton Shape. Annotation loading must never require
the original template to remain at the same path.

Skeleton creation is an interaction-local Canvas state rather than a partially
committed collection of Shapes. Named nodes and bone edges render as a draft;
finishing computes a padded bounding box and commits exactly one Skeleton Shape.
Cancelling therefore leaves no partial Shapes or orphaned points in the
Annotation.

## Considered options

- **Store a rectangle and many point Shapes joined by `group_id`** (rejected):
  grouping does not define keypoint order, bone connectivity, or ownership.
  Partial selection, deletion, copying, and relabeling could silently corrupt a
  training row.
- **Store only keypoints and derive the object box** (rejected): Ultralytics
  pose rows require an object bounding box. A tight box around visible joints
  is not equivalent to an annotated animal extent and changes when joints are
  missing.
- **Reference the Skeleton Template by filesystem path** (rejected): moving a
  dataset or deleting a template would make existing Annotations incomplete.
- **Add fixed pose fields to every Shape and the base Annotation codec**
  (deferred): the existing forward-compatible `other_data` field preserves the
  pose metadata without expanding the wire schema for Shapes that do not use
  it. A typed field may become worthwhile if other consumers adopt Skeleton
  Shapes.

## Consequences

- The four transform-box corners are part of the Skeleton Shape's point array
  and precede all keypoints. Pose-aware code must account for that offset.
- Loading transparently upgrades early Skeleton Shapes that used two
  axis-aligned bounding-box corners. YOLO export uses the axis-aligned bounds of
  the current four-corner transform box.
- Each Skeleton Shape duplicates a small amount of template metadata. This is
  intentional: it makes every Annotation File self-contained.
- Ultralytics export is deterministic because Label, bounding box, keypoint
  order, and visibility live on one Shape.
- The current YOLO dataset format has one dataset-wide `kpt_shape` and
  `flip_idx`. Multi-class exports must therefore use templates with compatible
  keypoint counts and flip mappings.
