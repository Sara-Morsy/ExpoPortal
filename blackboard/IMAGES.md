# Blackboard images

How the blackboard photos of 2026-11-10 were turned into single, readable
images. The work was done on 2026-11-10 and 2026-11-11.

## The problem

Two blackboards were photographed after a discussion on exposome workflows.
The orange marker reads well, but the purple marker is almost invisible on the
dark board in a straight-on photo. To capture the purple, extra photos were
taken at an angle, so that a nearby lamp gave the purple enough contrast.

## Input

| Folder | Photos | Content |
| :-- | :-- | :-- |
| `board1/` | 11 | Two overlapping overview photos (`…173729`, `…173737`) and nine angled close-ups. |
| `board2/` | 2 | One overview photo (`…182136`) and one angled close-up (`…182433`). |

The originals were not changed.

## Output

| File | Size | Content |
| :-- | :-- | :-- |
| `board1_combined.jpg` | 6400×2695 | Board 1, stitched and straightened, purple and orange readable. |
| `board2_combined.jpg` | 4000×3000 | Board 2 in the frame of its overview photo, purple and orange readable. |
| `board_merged.jpg` | 7450×2945 | Board 1 enlarged, with the content of board 2 inserted and new arrows. |

`board_merged-2.jpg` and `board_merged-3.jpg` are copies of the merged board
that were saved by hand during the session.

## Step 1: one image per board

1. **Stitch the overview.** The two overview photos of board 1 were matched on
   image features (SIFT) and joined with a homography. The board was then
   straightened to a rectangle from its four corners. Board 2 has only one
   overview photo, so it was used as it is.
2. **Align the close-ups.** Each angled close-up was matched onto the overview,
   warped, and matched again for a finer fit. One close-up of board 1 did not
   match automatically and was started from four hand-picked points.
3. **Extract the purple.** In every photo the board background was estimated
   with a wide median filter and subtracted. Purple ink was then found by its
   colour (more blue than green, and not the red of orange ink), which works
   whether the purple looks lighter or darker than the board.
4. **Fuse.** At each spot the purple is taken from the close-up that shows it
   most strongly. Taking one source per region avoids double strokes from small
   alignment errors.
5. **Render.** The purple strokes are drawn in a bright violet on the overview.
   The stroke shapes come from the photos; the colour is not the real marker
   colour.
6. **Brighten the orange.** The orange (and pink) ink keeps its own hue and
   shape but is made brighter, with a slight glow. Board 2 got about half the
   boost of board 1, because its orange was already bright.

## Step 2: the merged board

Board 2 holds the anthropogenic example (tires, 6PPD), board 1 the biogenic
one (α-pinene) and the shared biology. They were combined into one board.

- **Larger board.** Board 1 was extended by 1050 px to the left and 250 px
  upward. The new surface is made from ink-free parts of the real board, with
  the seams blended. Three of the four magnets moved up with the top border.
- **Board 2 inserted.** The writing of board 2 was lifted off its board (ink
  only, selected by colour, so no frame or board edge comes along), scaled to
  60 % and laid onto the surface of board 1, between "Biogenic" and
  "inhalation".
- **Moved items.** "Biogenic" moved to the far left, with "α-pinene" centred
  below it. The lines "non-exhaust emissions" and "non-tailpipe emissions"
  were shifted down slightly to make room for an arrow. Nothing else of
  board 2 was rearranged.
- **Arrows.** The original arrows and bracket between Biogenic, α-pinene and
  inhalation were removed. Four arrows were drawn in the orange and stroke
  width of the handwriting:

  | Arrow | Note |
  | :-- | :-- |
  | Biogenic → α-pinene | Straight down. |
  | Anthropogenic → Tires | Curves down the left side of the board 2 block. |
  | 6PPD → inhalation | Starts at the underline below "6PPD / anti-oxidant / plasticizer", because the word itself is boxed in by other writing. |
  | α-pinene → inhalation | Thin; runs around the board 2 block and arrives just below the 6PPD arrow. |

  The arrow Tires → 6PPD is the one already on board 2.

## Known limitations

- A few purple words are thicker and less crisp than the rest: "non-targeted",
  "individual", "wearable silicone", "blood", "milk" and the "ERK" lines.
- The small pink note at the bottom left of board 1 ("GT / SESIV") stays faint
  and could not be read with confidence.
- Where purple was written over orange (around "inhalation" and
  "heterogeneous oxidation" on board 2) the result stays cluttered, as on the
  real board.
- `board1_combined.jpg` has small black wedges outside the board, at the
  bottom-right edge and top-right corner, where no photo covers the scene.
- Close up, the merged board shows a slight change of tone near the rail and
  tray where the extension starts.
- The four new arrows are more even than real handwriting.

## Reproducing

The image processing was done with throw-away Python scripts (OpenCV and
NumPy) and ImageMagick in a temporary folder. These scripts are not part of
this repository, so the images cannot be rebuilt from here.
