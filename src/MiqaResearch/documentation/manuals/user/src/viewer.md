(heading-viewer)=
# The DICOM Viewer

The **DICOM Viewer** shows a participant's images (CT, MR, PET, X-ray, whole-slide pathology and
more) in the browser. You can measure, annotate, segment, fuse series and save your results back to
the project. Everything runs in your browser and nothing has to be installed.

A few terms appear throughout this page:

Base series
: The series the viewer shows. The tools, measurements and segmentations work on it.

Related Series
: The participant's other series, from every study. The viewer lists them so that you can fuse
  them onto the base series or show them instead of it.

Fusion
: One or more series drawn on top of the base series, each with its own window, colormap and
  opacity. A typical example is PET on CT.

Viewer Session
: One opening of the viewer in a browser tab. It lasts until you close or reload the tab.

(heading-viewer-access)=
## Who can do what

| Role | What you can do in the viewer |
|---|---|
| Annotator, PI, Site PI, Admin | Everything below: view, measure, annotate, segment, save, supersede and retire. |
| Other project roles (for example Investigator) | View, measure and show saved results, but not save. The annotate and segment tools and the **Save** buttons are hidden. |

You only see participants within your **Participant Visibility**. A Site-bound role, for example,
only sees participants with a consent at its Sites. Without access to the participant or one of its
series, the viewer page is *Not found*.

(heading-viewer-open)=
## Opening the viewer

The viewer opens in its own browser tab, for one participant, from a link that names the series to
open. The tab title is the participant's alias. The page never shows names, personal identity
numbers or other identifying data, and the link contains only pseudonymized identifiers.

- The **first** series in the link is the base series.
- If the link names more series, they are fused onto the base series when the viewer opens. If one
  can't be fused, the viewer says why (see [Fusion](#heading-viewer-fusion)).
- The series list on the left shows the opened series first, then the participant's other series
  from every study, newest study first. Saved annotations and segmentations aren't listed as
  series: they appear under the series they belong to (see
  [Saved results](#heading-viewer-results)).

Every opening of the viewer is recorded in the audit log with your name, the participant and the
series that were opened.

(heading-viewer-layout)=
## The screen

From left to right:

1. **Series list**: the participant's series, with modality, description and number of images.
   Saved results are listed under their series.
2. **Tool rail**: the tools, grouped into navigation, measurement, annotation and segmentation. Hover
   over a tool to see its name and keyboard key.
3. **View**: the image itself.
4. **Inspector**: panels for the current view, for example layout, layers, segments, calibration,
   mouse help and **Save**.

(heading-viewer-navigate)=
## Navigating the images

The mouse works as on a radiology workstation:

| Mouse | Image series | Whole-slide images |
|---|---|---|
| Left button | The selected tool | The selected tool |
| Right drag | Window/level | — |
| Middle drag | Pan | Pan |
| Wheel | Scroll through the images | Zoom |
| Ctrl + wheel | Zoom | — |

Keyboard shortcuts:

| Key | Action |
|---|---|
| `w` | Window/level |
| `p` | Pan |
| `z` | Zoom |
| `s` | Scroll |
| `x` | Crosshairs (three views only) |
| `v` | Next orientation (axial, sagittal, coronal, three views) |
| `i` | Invert the image |
| `Esc` | Reset the view |
| `0`–`8` | Window presets, see below |
| Ctrl/⌘ + `S` | Save |

Window presets depend on the modality. `0` always returns to the window stored in the images.

| Key | CT | PET |
|---|---|---|
| `1` | Soft tissue | |
| `2` | Lung | |
| `3` | Bone | |
| `4` | Brain | |
| `5` | Liver | |
| `6` | Mediastinum | |
| `7` | | SUV 0–5 |
| `8` | | SUV 0–10 |

(heading-viewer-volume)=
### Three views (MPR)

A series opens as a stack of images. If it can be reconstructed in 3D (a regular stack of slices),
the **Layout** panel also offers axial, sagittal and coronal views and **three views** side by
side. In three views, the big view is on the left, and you can drag the divider to resize it.
**Crosshairs** (`x`) links the three views to one point.

A very large series may not fit in the browser's memory in 3D. The viewer then shows it as a stack
with a banner, and the Layout panel offers **Open reduced 3D (view only)**: a lower-resolution 3D
view with navigation and crosshairs only.

(heading-viewer-measure)=
## Measuring

The measurement tools are **Length** (`l`), **Angle** (`a`), **Bidirectional** (`b`), **Probe**
(`o`), **Rectangle ROI** (`r`), **Ellipse ROI** (`e`) and **Freehand ROI** (`f`). Roles that may
annotate also have **Arrow** (`t`), which places a labelled arrow.

Measurements are shown in the units the image allows. When an image has no reliable pixel spacing,
the **Calibration** panel says so with a warning badge (for example *No spacing (px)* or
*Detector plane (Proj)*). Hover over a unit to see what it means. Roles that may annotate can calibrate such an image with
**Calibrate (known length)** (`c`): draw a line over something of known length and enter the length.
The calibration is saved with your annotations.

For PET, values are shown as **SUV** when the images contain what is needed to calculate it.
Otherwise the viewer warns that values are in Bq/ml, not SUV.

(heading-viewer-fusion)=
## Fusion

To fuse a series onto the one shown, drag it from the series list onto the view. While you drag,
the view shows two drop zones:

- **Top half: fuse.** The series is drawn on top of the base series in every view. If the view is a
  stack, it first switches to three views.
- **Bottom half: replace.** The series is shown instead of the current one.

A series can only be fused when it shares the base series' **Frame of Reference**, which in
practice means it was acquired in the same scanner session (for example PET and CT from one PET/CT
scan), and when both can be shown in 3D. If not, or if the browser lacks memory for it, the
viewer tells you why and changes nothing.

The **Layers** panel lists the base series and each fused series. Select a layer to adjust it:
right drag and window presets then apply to that layer. For each layer you can choose a colormap,
change its opacity and remove it. PET is fused in SUV with a colour scale from SUV 0 to 5, and is
transparent below SUV 2.

(heading-viewer-segment)=
## Segmenting

Roles that may annotate can draw a **Segmentation**: one or more named, coloured **segments**
painted on the base series. Select a segment tool, or **New segmentation** in the **Segments**
panel, to start one.

| Key | Tool |
|---|---|
| `g` | Brush |
| `d` | Eraser |
| `k` | Polygon (click the corners; double-click, or click the first corner, to close) |
| `q` | Rectangle scissors |
| `j` | Circle scissors |
| `y` | Sphere scissors |
| `m` | Rectangle ROI threshold |

With a paint tool, right drag erases with the same shape. In the **Segments** panel you add,
rename and recolour segments, choose the active one and set the brush size. For a threshold, draw
rectangles with `m`, enter the value range and select **Run threshold**. On a fusion, the threshold uses the
selected layer, for example SUV on PET.

Only one segmentation can be open at a time.

(heading-viewer-save)=
## Saving

The **Save** panel has one button for annotations and measurements, and one for the
segmentation. **Ctrl/⌘ + S** saves both. Saved results are stored in the project as DICOM objects
and appear under their series in the series list.

- **Save as new (v1)** creates a new result.
- **Supersede vN → vN+1** saves a new version on top of the one you opened. Earlier versions are
  kept. You may supersede your own results; PI, Site PI (in its Sites) and Admin may supersede
  anyone's.

If someone else saved a newer version while you were working, the viewer names them and asks what
to do: discard yours and load theirs, save yours as a separate result, or save yours on top.

A result made on a fusion records every series in view, and is shown with a **⊕** badge naming
the fused series.

(heading-viewer-drafts)=
### Unsaved work

The viewer keeps a draft of unsaved annotations and segmentations in your browser. If the tab is
closed or reloaded before you save, the next time you open the same series the viewer offers
**Restore** or **Discard**. Drafts stay only in this browser, for 7 days.

(heading-viewer-results)=
## Saved results

Saved annotations and segmentations are listed under the series they belong to. Click a result to
show it, and click it again (or ✕ on its chip over the view) to hide it. Showing a result switches
to its series and fuses any other series it was made on.

The **⋯** menu of a result has:

- **History**: every version, with author and time.
- **Retire…**: hides the result from use while keeping it and its history. Retiring needs the same
  rights as superseding. **Show retired** at the bottom of the list shows retired results again,
  read-only.

(heading-viewer-blinding)=
### Blinded Annotation

When the project uses **Blinded Annotation**, you only see your own annotations and segmentations,
and a lock row tells you how many are hidden. A PI, Site PI or Admin can select **Reveal for this
participant…** to show everyone's results for this participant. A reveal must be confirmed, is
recorded in the audit log and lasts only for the current Viewer Session: reloading or closing the tab hides the results
again. Annotators can never reveal.
