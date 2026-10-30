# Thermal Studio features applied to Labelme

Research checked on 30 October 2026 against
[FLIR's current edition comparison](https://flir.custhelp.com/app/answers/print/a_id/4590)
(updated 2 June 2026). Its core functions include opening radiometric media,
palette changes, spot/box/ellipse/line measurements, temperature differences and
basic reports. Availability of advanced functions varies by edition.

| Function | Labelme implementation |
| --- | --- |
| Temperature measurement | Spots, boxes, circles and lines in the viewer; selected annotation Shapes in the editor |
| Comparison | Signed mean-temperature differences relative to a chosen measurement |
| Line profiles | Temperature chart and CSV with pixel coordinates and distance |
| Thermal tuning | Manual/automatic limits, fixed scales, histogram contrast |
| Palettes and units | Iron, White hot, Black hot, Rainbow; Celsius, Fahrenheit, Kelvin |
| Highlights | Hot/cold markers and threshold/interval isotherm coverage |
| Environmental correction | Whole-frame parameters with reversible raw-data recalculation |
| Outputs | Temperature matrix CSV, profile CSV and self-contained HTML report |
| Batch workflow | Current analysis settings carried into CSQ frame extraction |

Parameter meanings follow the
[FLIR measurement-parameter documentation](https://docs.flir.com/T810587/en-US/latest/s13.html).
The implementation preserves factory calibration and original sensor values;
environmental adjustments remain reversible.

This is a native Labelme implementation of useful thermal-analysis functions.
FLIR-specific MSX/fusion alignment, DDE processing, live camera streaming,
inspection routes, proprietary report templates and radiometric JPEG authoring
remain outside this implementation. Thermal input remains radiometric JPEG and
CSQ. Reports export as HTML and can be printed from a browser. Circle areas are
supported; an independent ellipse tool is not included. Parameter corrections
apply to the whole frame, rather than individual Shapes.

See [the usage guide](thermal.md). Public sample checks exercise SC660 and
FLIR ONE images and a T1030sc recording; numerical agreement with FLIR Thermal
Studio and additional camera models remains to be verified.
